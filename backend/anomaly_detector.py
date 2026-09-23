import os

import psycopg2
import pandas as pd

from sklearn.ensemble import IsolationForest


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
# FEATURE EXTRACTION
# ==================================================

def get_features():

    connection = get_connection()

    query = """
        SELECT

            date_trunc(
                'minute',
                timestamp
            ) AS minute,

            COUNT(*) AS requests_per_minute,

            AVG(latency) AS avg_latency,

            COALESCE(
                STDDEV_POP(latency),
                0
            ) AS latency_stddev,

            COUNT(*) FILTER (
                WHERE status_code >= 400
            )::float
            / NULLIF(
                COUNT(*),
                0
            ) AS error_rate

        FROM request_metrics

        WHERE endpoint NOT IN (
            '/metrics',
            '/anomalies'
        )

        GROUP BY minute

        ORDER BY minute;
    """

    df = pd.read_sql_query(
        query,
        connection
    )

    connection.close()

    return df


# ==================================================
# ANOMALY DETECTION
# ==================================================

def detect_latest_anomalies():

    df = get_features()

    # ----------------------------------------------
    # Not enough data
    # ----------------------------------------------

    if len(df) < 10:

        return {
            "status": "INSUFFICIENT_DATA",
            "message": "Not enough monitoring data.",
            "anomalies_detected": 0,
            "windows_analyzed": 0,
            "results": []
        }

    # ----------------------------------------------
    # Features used by Isolation Forest
    # ----------------------------------------------

    feature_columns = [
        "requests_per_minute",
        "avg_latency",
        "latency_stddev",
        "error_rate"
    ]

    # ----------------------------------------------
    # Latest windows are treated as test data
    # ----------------------------------------------

    test_window_count = min(
        3,
        len(df) // 4
    )

    training_data = df.iloc[
        :-test_window_count
    ]

    test_data = df.iloc[
        -test_window_count:
    ]

    # ----------------------------------------------
    # Isolation Forest
    # ----------------------------------------------

    model = IsolationForest(
        n_estimators=200,
        contamination="auto",
        random_state=42
    )

    model.fit(
        training_data[feature_columns]
    )

    # ----------------------------------------------
    # Predictions
    # ----------------------------------------------

    predictions = model.predict(
        test_data[feature_columns]
    )

    scores = model.decision_function(
        test_data[feature_columns]
    )

    # ----------------------------------------------
    # Build results
    # ----------------------------------------------

    results = test_data.copy()

    results["anomaly_score"] = scores

    results["status"] = [
        "ANOMALY"
        if prediction == -1
        else "NORMAL"
        for prediction in predictions
    ]

    # ----------------------------------------------
    # Format output
    # ----------------------------------------------

    output = []

    for _, row in results.iterrows():

        output.append(
            {
                "minute":
                    row["minute"].isoformat(),

                "requests_per_minute":
                    int(
                        row["requests_per_minute"]
                    ),

                "avg_latency":
                    round(
                        float(
                            row["avg_latency"]
                        ),
                        4
                    ),

                "latency_stddev":
                    round(
                        float(
                            row["latency_stddev"]
                        ),
                        4
                    ),

                "error_rate":
                    round(
                        float(
                            row["error_rate"]
                        ),
                        4
                    ),

                "anomaly_score":
                    round(
                        float(
                            row["anomaly_score"]
                        ),
                        4
                    ),

                "status":
                    row["status"]
            }
        )

    # ----------------------------------------------
    # Count anomalies
    # ----------------------------------------------

    anomaly_count = sum(
        1
        for item in output
        if item["status"] == "ANOMALY"
    )

    # ----------------------------------------------
    # Final response
    # ----------------------------------------------

    return {
        "status":
            "ANOMALY"
            if anomaly_count > 0
            else "NORMAL",

        "anomalies_detected":
            anomaly_count,

        "windows_analyzed":
            len(output),

        "results":
            output
    }