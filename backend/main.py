from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse

import os
import psycopg2
import time

from anomaly_detector import detect_latest_anomalies


app = FastAPI()


# ==================================================
# CORS
# ==================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================================================
# DATABASE CONFIGURATION
# ==================================================

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "pulsewatch")
DB_USER = os.getenv("DB_USER", "pulsewatch")
DB_PASSWORD = os.getenv("DB_PASSWORD", "pulsewatch")


# ==================================================
# DATABASE CONNECTION
# ==================================================

def get_connection():

    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )


# ==================================================
# REQUEST MONITORING
# ==================================================

@app.middleware("http")
async def monitor_requests(
    request: Request,
    call_next
):

    start_time = time.time()

    # ----------------------------------------------
    # Process request
    # ----------------------------------------------

    try:

        response = await call_next(request)

    except Exception:

        latency = time.time() - start_time

        # ------------------------------------------
        # Do not record internal monitoring endpoints
        # ------------------------------------------

        if request.url.path not in [
            "/metrics",
            "/anomalies"
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

    # ----------------------------------------------
    # Calculate latency
    # ----------------------------------------------

    latency = time.time() - start_time

    # ----------------------------------------------
    # Save request metrics
    # ----------------------------------------------

    if request.url.path not in [
        "/metrics",
        "/anomalies"
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

    # ----------------------------------------------
    # Print request information
    # ----------------------------------------------

    print(
        f"{request.method} "
        f"{request.url.path} | "
        f"Status: "
        f"{response.status_code} | "
        f"Latency: "
        f"{latency:.4f}s"
    )

    return response


# ==================================================
# HOME / DASHBOARD
# ==================================================

@app.get("/", response_class=HTMLResponse)
def home():

    with open("index.html", "r", encoding="utf-8") as file:
        return file.read()


# ==================================================
# HEALTH
# ==================================================

@app.get("/health")
def health():

    return {
        "status": "healthy",
        "service": "PulseWatch"
    }


# ==================================================
# SLOW TEST ENDPOINT
# ==================================================

@app.get("/slow")
def slow():

    time.sleep(3)

    return {
        "message": "This request was intentionally slow",
        "delay_seconds": 3
    }


# ==================================================
# ERROR TEST ENDPOINT
# ==================================================

@app.get("/error")
def error():

    return JSONResponse(
        status_code=500,
        content={
            "message": "This is an intentional test error"
        }
    )


# ==================================================
# METRICS
# ==================================================

@app.get("/metrics")
def metrics():

    connection = get_connection()

    cursor = connection.cursor()

    # ----------------------------------------------
    # Overall metrics
    # ----------------------------------------------

    cursor.execute(
        """
        SELECT
            COUNT(*),

            COUNT(*)
            FILTER (
                WHERE status_code < 400
            ),

            COUNT(*)
            FILTER (
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

    # ----------------------------------------------
    # Error rate
    # ----------------------------------------------

    if total_requests > 0:

        error_rate = (
            failed_requests
            / total_requests
        ) * 100

    else:

        error_rate = 0

    # ----------------------------------------------
    # Recent requests
    # ----------------------------------------------

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
                "latency": round(row[3], 4)
            }
        )

    cursor.close()

    connection.close()

    # ----------------------------------------------
    # Return metrics
    # ----------------------------------------------

    return {
        "total_requests": total_requests,

        "successful_requests": successful_requests,

        "failed_requests": failed_requests,

        "average_latency_seconds": round(
            average_latency,
            4
        ),

        "error_rate_percent": round(
            error_rate,
            2
        ),

        "recent_requests": recent_requests
    }


# ==================================================
# ML ANOMALY DETECTION
# ==================================================

@app.get("/anomalies")
def anomalies():

    return detect_latest_anomalies()