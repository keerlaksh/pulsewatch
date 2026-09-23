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


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# DATABASE CONFIGURATION
# ============================================================

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
        password=DB_PASSWORD
    )


# ============================================================
# REQUEST MONITORING MIDDLEWARE
# ============================================================

@app.middleware("http")
async def monitor_requests(request: Request, call_next):

    start_time = time.time()

    try:
        response = await call_next(request)

    except Exception:

        latency = time.time() - start_time

        # Do not count dashboard page or dashboard polling
        if request.url.path not in [
            "/",
            "/metrics",
            "/anomalies",
            "/kubernetes"
        ]:

            connection = get_connection()
            cursor = connection.cursor()

            cursor.execute(
                """
                INSERT INTO request_metrics
                (
                    endpoint,
                    status_code,
                    latency
                )
                VALUES (%s, %s, %s)
                """,
                (
                    request.url.path,
                    500,
                    latency
                )
            )

            connection.commit()
            cursor.close()
            connection.close()

        raise

    latency = time.time() - start_time

    # Do not count dashboard page or dashboard polling
    if request.url.path not in [
        "/",
        "/metrics",
        "/anomalies",
        "/kubernetes"
    ]:

        connection = get_connection()
        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO request_metrics
            (
                endpoint,
                status_code,
                latency
            )
            VALUES (%s, %s, %s)
            """,
            (
                request.url.path,
                response.status_code,
                latency
            )
        )

        connection.commit()
        cursor.close()
        connection.close()

    print(
        f"{request.method} "
        f"{request.url.path} | "
        f"Status: "
        f"{response.status_code} | "
        f"Latency: "
        f"{latency:.4f}s"
    )

    return response


# ============================================================
# DASHBOARD
# ============================================================

@app.get("/", response_class=HTMLResponse)
def home():

    with open(
        "index.html",
        "r",
        encoding="utf-8"
    ) as file:

        return file.read()


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
def health():

    return {
        "status": "healthy",
        "service": "PulseWatch"
    }


# ============================================================
# POD / INSTANCE IDENTIFICATION
# ============================================================

@app.get("/instance")
def instance():

    return {
        "instance": os.getenv(
            "HOSTNAME",
            socket.gethostname()
        )
    }


# ============================================================
# INTENTIONALLY SLOW REQUEST
# ============================================================

@app.get("/slow")
def slow():

    time.sleep(3)

    return {
        "message": "This request was intentionally slow",
        "delay_seconds": 3
    }


# ============================================================
# CPU LOAD TEST
# ============================================================

@app.get("/cpu-load")
def cpu_load():

    total = 0

    for i in range(8_000_000):
        total += i * i

    return {
        "status": "completed",
        "result": total
    }


# ============================================================
# INTENTIONALLY FAILED REQUEST
# ============================================================

@app.get("/error")
def error():

    return JSONResponse(
        status_code=500,
        content={
            "message": "This is an intentional test error"
        }
    )


# ============================================================
# KUBERNETES CLUSTER STATUS
# ============================================================

@app.get("/kubernetes")
def kubernetes_status():

    try:

        # ----------------------------------------------------
        # Load Kubernetes configuration from inside the pod
        # ----------------------------------------------------

        config.load_incluster_config()

        apps_api = client.AppsV1Api()
        core_api = client.CoreV1Api()

        # ----------------------------------------------------
        # Get PulseWatch deployment
        # ----------------------------------------------------

        deployment = apps_api.read_namespaced_deployment(
            name="pulsewatch-api",
            namespace="default"
        )

        # ----------------------------------------------------
        # Get PulseWatch API pods
        # ----------------------------------------------------

        pods = core_api.list_namespaced_pod(
            namespace="default",
            label_selector="app=pulsewatch-api"
        )

        pod_data = []

        for pod in pods.items:

            ready = False

            if pod.status.container_statuses:

                ready = all(
                    container.ready
                    for container in pod.status.container_statuses
                )

            pod_data.append(
                {
                    "name": pod.metadata.name,
                    "status": pod.status.phase,
                    "ready": ready
                }
            )

        # ----------------------------------------------------
        # Get Service endpoints
        # ----------------------------------------------------

        service = core_api.read_namespaced_service(
            name="pulsewatch-api",
            namespace="default"
        )

        endpoints = core_api.list_namespaced_endpoints(
            namespace="default"
        )

        endpoint_count = 0

        for endpoint in endpoints.items:

            if endpoint.metadata.name == "pulsewatch-api":

                if endpoint.subsets:

                    for subset in endpoint.subsets:

                        if subset.addresses:

                            endpoint_count += len(
                                subset.addresses
                            )

        # ----------------------------------------------------
        # Return Kubernetes information
        # ----------------------------------------------------

        return {

            "status": "connected",

            "deployment": {

                "name": deployment.metadata.name,

                "desired_replicas":
                    deployment.spec.replicas or 0,

                "ready_replicas":
                    deployment.status.ready_replicas or 0,

                "available_replicas":
                    deployment.status.available_replicas or 0
            },

            "service": {

                "name": service.metadata.name,

                "type":
                    service.spec.type,

                "port":
                    service.spec.ports[0].port
                    if service.spec.ports
                    else None,

                "node_port":
                    service.spec.ports[0].node_port
                    if service.spec.ports
                    else None,

                "endpoints":
                    endpoint_count
            },

            "pods": pod_data
        }

    except Exception as error:

        return {

            "status": "unavailable",

            "message": str(error)
        }


# ============================================================
# APPLICATION METRICS
# ============================================================

@app.get("/metrics")
def metrics():

    connection = get_connection()
    cursor = connection.cursor()

    # --------------------------------------------------------
    # Overall metrics
    # --------------------------------------------------------

    cursor.execute(
        """
        SELECT
            COUNT(*),
            COUNT(*) FILTER (
                WHERE status_code < 400
            ),
            COUNT(*) FILTER (
                WHERE status_code >= 400
            ),
            AVG(latency)
        FROM request_metrics
        """
    )

    result = cursor.fetchone()

    total_requests = result[0]
    successful_requests = result[1]
    failed_requests = result[2]

    average_latency = result[3] or 0

    # --------------------------------------------------------
    # Error rate
    # --------------------------------------------------------

    if total_requests > 0:

        error_rate = (
            failed_requests /
            total_requests
        ) * 100

    else:

        error_rate = 0

    # --------------------------------------------------------
    # Recent requests
    # --------------------------------------------------------

    cursor.execute(
        """
        SELECT
            timestamp,
            endpoint,
            status_code,
            latency
        FROM request_metrics
        ORDER BY timestamp DESC
        LIMIT 10
        """
    )

    rows = cursor.fetchall()

    recent_requests = []

    for row in rows:

        recent_requests.append(
            {
                "timestamp": row[0].isoformat(),
                "endpoint": row[1],
                "status_code": row[2],
                "latency": round(
                    row[3],
                    4
                )
            }
        )

    cursor.close()
    connection.close()

    return {

        "total_requests":
            total_requests,

        "successful_requests":
            successful_requests,

        "failed_requests":
            failed_requests,

        "average_latency_seconds":
            round(
                average_latency,
                4
            ),

        "error_rate_percent":
            round(
                error_rate,
                2
            ),

        "recent_requests":
            recent_requests
    }


# ============================================================
# ML ANOMALY DETECTION
# ============================================================

@app.get("/anomalies")
def anomalies():

    return detect_latest_anomalies()