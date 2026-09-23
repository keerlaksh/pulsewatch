from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
import os
import socket
import psycopg2
import time

from anomaly_detector import detect_latest_anomalies
from kubernetes import client, config

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "pulsewatch")
DB_USER = os.getenv("DB_USER", "pulsewatch")
DB_PASSWORD = os.getenv("DB_PASSWORD", "pulsewatch")


def get_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )


def pod_name():
    return os.getenv("HOSTNAME", socket.gethostname())


def ensure_schema():
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        ALTER TABLE request_metrics
        ADD COLUMN IF NOT EXISTS pod_name VARCHAR(255);
    """)
    connection.commit()
    cursor.close()
    connection.close()


@app.on_event("startup")
def startup():
    try:
        ensure_schema()
    except Exception as error:
        print(f"Schema update skipped: {error}")


@app.middleware("http")
async def monitor_requests(request: Request, call_next):
    start_time = time.time()
    try:
        response = await call_next(request)
        status_code = response.status_code
    except Exception:
        response = None
        status_code = 500

    latency = time.time() - start_time

    if request.url.path not in ["/", "/metrics", "/anomalies", "/kubernetes", "/pod-stats"]:
        try:
            connection = get_connection()
            cursor = connection.cursor()
            cursor.execute("""
                INSERT INTO request_metrics
                (endpoint, status_code, latency, pod_name)
                VALUES (%s, %s, %s, %s)
            """, (request.url.path, status_code, latency, pod_name()))
            connection.commit()
            cursor.close()
            connection.close()
        except Exception as db_error:
            print(f"Request metric insert failed: {db_error}")

    print(
        f"{request.method} {request.url.path} | "
        f"Status: {status_code} | Latency: {latency:.4f}s | Pod: {pod_name()}"
    )

    if response is None:
        raise RuntimeError("Request failed")

    return response


@app.get("/", response_class=HTMLResponse)
def home():
    with open("index.html", "r", encoding="utf-8") as file:
        return file.read()


@app.get("/health")
def health():
    return {"status": "healthy", "service": "PulseWatch"}


@app.get("/instance")
def instance():
    return {"instance": pod_name()}


@app.get("/slow")
def slow():
    time.sleep(3)
    return {"message": "This request was intentionally slow", "delay_seconds": 3}


@app.get("/cpu-load")
def cpu_load():
    total = 0
    for i in range(8_000_000):
        total += i * i
    return {"status": "completed", "result": total}


@app.get("/error")
def error():
    return JSONResponse(
        status_code=500,
        content={"message": "This is an intentional test error"},
    )


@app.get("/kubernetes")
def kubernetes_status():
    try:
        config.load_incluster_config()
        apps_api = client.AppsV1Api()
        core_api = client.CoreV1Api()
        autoscaling_api = client.AutoscalingV2Api()

        deployment = apps_api.read_namespaced_deployment(
            name="pulsewatch-api", namespace="default"
        )

        pods = core_api.list_namespaced_pod(
            namespace="default", label_selector="app=pulsewatch-api"
        )

        pod_data = []
        for pod in pods.items:
            ready = bool(
                pod.status.container_statuses
                and all(c.ready for c in pod.status.container_statuses)
            )
            pod_data.append({
                "name": pod.metadata.name,
                "status": pod.status.phase,
                "ready": ready,
            })

        service = core_api.read_namespaced_service(
            name="pulsewatch-api", namespace="default"
        )

        endpoint_count = 0
        endpoint_obj = core_api.read_namespaced_endpoints(
            name="pulsewatch-api", namespace="default"
        )
        if endpoint_obj.subsets:
            for subset in endpoint_obj.subsets:
                if subset.addresses:
                    endpoint_count += len(subset.addresses)

        hpa_data = {
            "name": "pulsewatch-api-hpa",
            "min_replicas": None,
            "max_replicas": None,
            "current_replicas": None,
            "desired_replicas": None,
            "current_cpu_percent": None,
            "target_cpu_percent": None,
        }

        try:
            hpa = autoscaling_api.read_namespaced_horizontal_pod_autoscaler(
                name="pulsewatch-api-hpa", namespace="default"
            )
            hpa_data["min_replicas"] = hpa.spec.min_replicas
            hpa_data["max_replicas"] = hpa.spec.max_replicas
            hpa_data["current_replicas"] = hpa.status.current_replicas
            hpa_data["desired_replicas"] = hpa.status.desired_replicas

            if hpa.spec.metrics:
                for metric in hpa.spec.metrics:
                    if metric.resource and metric.resource.name == "cpu":
                        target = metric.resource.target
                        if target and target.average_utilization is not None:
                            hpa_data["target_cpu_percent"] = target.average_utilization

            if hpa.status.current_metrics:
                for metric in hpa.status.current_metrics:
                    if metric.resource and metric.resource.name == "cpu":
                        if metric.resource.current.average_utilization is not None:
                            hpa_data["current_cpu_percent"] = (
                                metric.resource.current.average_utilization
                            )
        except Exception as hpa_error:
            hpa_data["error"] = str(hpa_error)

        return {
            "status": "connected",
            "deployment": {
                "name": deployment.metadata.name,
                "desired_replicas": deployment.spec.replicas or 0,
                "ready_replicas": deployment.status.ready_replicas or 0,
                "available_replicas": deployment.status.available_replicas or 0,
            },
            "service": {
                "name": service.metadata.name,
                "type": service.spec.type,
                "port": service.spec.ports[0].port if service.spec.ports else None,
                "node_port": service.spec.ports[0].node_port if service.spec.ports else None,
                "endpoints": endpoint_count,
            },
            "hpa": hpa_data,
            "pods": pod_data,
        }
    except Exception as error:
        return {"status": "unavailable", "message": str(error)}


@app.get("/pod-stats")
def pod_stats():
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT pod_name, COUNT(*)
        FROM request_metrics
        WHERE endpoint = '/instance'
          AND timestamp >= NOW() - INTERVAL '5 minutes'
        GROUP BY pod_name
    """)
    counts = {row[0]: row[1] for row in cursor.fetchall() if row[0]}

    cursor.execute("""
        SELECT COUNT(*)
        FROM request_metrics
        WHERE endpoint = '/instance'
          AND timestamp >= NOW() - INTERVAL '5 minutes'
    """)
    total = cursor.fetchone()[0]

    cursor.close()
    connection.close()

    try:
        config.load_incluster_config()
        core_api = client.CoreV1Api()
        pods = core_api.list_namespaced_pod(
            namespace="default", label_selector="app=pulsewatch-api"
        )

        result = []
        for pod in pods.items:
            result.append({
                "name": pod.metadata.name,
                "status": pod.status.phase,
                "requests": counts.get(pod.metadata.name, 0),
            })

        return {
            "status": "connected",
            "window_minutes": 5,
            "total_instance_requests": total,
            "pods": result,
        }
    except Exception as error:
        return {"status": "unavailable", "message": str(error)}


@app.get("/metrics")
def metrics():
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT COUNT(*),
               COUNT(*) FILTER (WHERE status_code < 400),
               COUNT(*) FILTER (WHERE status_code >= 400),
               AVG(latency)
        FROM request_metrics
    """)
    total, successful, failed, average_latency = cursor.fetchone()

    error_rate = (failed / total * 100) if total else 0

    cursor.execute("""
        SELECT timestamp, endpoint, status_code, latency
        FROM request_metrics
        ORDER BY timestamp DESC
        LIMIT 10
    """)
    recent = [
        {
            "timestamp": row[0].isoformat(),
            "endpoint": row[1],
            "status_code": row[2],
            "latency": round(row[3], 4),
        }
        for row in cursor.fetchall()
    ]

    cursor.close()
    connection.close()

    return {
        "total_requests": total,
        "successful_requests": successful,
        "failed_requests": failed,
        "average_latency_seconds": round(average_latency or 0, 4),
        "error_rate_percent": round(error_rate, 2),
        "recent_requests": recent,
    }


@app.get("/anomalies")
def anomalies():
    return detect_latest_anomalies()
