import psycopg2
import pandas as pd

from sklearn.ensemble import IsolationForest


def get_connection():
    return psycopg2.connect(
        host="localhost",
        port=5432,
        database="pulsewatch",
        user="pulsewatch",
        password="pulsewatch"
    )


def get_features():

    connection = get_connection()

    query = """
        SELECT
            date_trunc('minute', timestamp) AS minute,

            COUNT(*) AS requests_per_minute,

            AVG(latency) AS avg_latency,

            COALESCE(
                STDDEV_POP(latency),
                0
            ) AS latency_stddev,

            COUNT(*) FILTER (
                WHERE status_code >= 400
            )::float / NULLIF(COUNT(*), 0) AS error_rate

        FROM request_metrics

        GROUP BY minute

        ORDER BY minute;
    """

    df = pd.read_sql_query(query, connection)

    connection.close()

    return df


def train_model(training_data):

    feature_columns = [
        "requests_per_minute",
        "avg_latency",
        "latency_stddev",
        "error_rate"
    ]

    X_train = training_data[feature_columns]

    model = IsolationForest(
        n_estimators=200,
        contamination="auto",
        random_state=42
    )

    model.fit(X_train)

    return model


def detect_anomalies(model, data):

    feature_columns = [
        "requests_per_minute",
        "avg_latency",
        "latency_stddev",
        "error_rate"
    ]

    X = data[feature_columns]

    predictions = model.predict(X)
    scores = model.decision_function(X)

    results = data.copy()

    results["anomaly_score"] = scores

    results["status"] = [
        "ANOMALY" if prediction == -1 else "NORMAL"
        for prediction in predictions
    ]

    return results


if __name__ == "__main__":

    print("\nLoading monitoring data...")

    df = get_features()

    print(
        f"Loaded {len(df)} time windows."
    )

    # -----------------------------------------------
    # Find the abnormal incident we just generated.
    #
    # The new abnormal traffic started around 08:08.
    # Everything before that becomes our baseline.
    # -----------------------------------------------

    incident_start = pd.Timestamp("2026-09-23 08:08:00")

    training_data = df[
        df["minute"] < incident_start
    ]

    incident_data = df[
        df["minute"] >= incident_start
    ]

    print(
        f"Baseline windows: {len(training_data)}"
    )

    print(
        f"Incident windows: {len(incident_data)}"
    )

    if len(training_data) < 10:

        print(
            "\nNot enough baseline data."
        )

        exit()

    if incident_data.empty:

        print(
            "\nNo incident data found."
        )

        exit()

    # -----------------------------------------------
    # Train
    # -----------------------------------------------

    print("\nTraining Isolation Forest...")

    model = train_model(training_data)

    print("Model trained successfully.")

    # -----------------------------------------------
    # Detect
    # -----------------------------------------------

    print("\nAnalyzing incident traffic...")

    results = detect_anomalies(
        model,
        incident_data
    )

    print("\n================================")
    print("PULSEWATCH INCIDENT DETECTION")
    print("================================\n")

    print(
        results[
            [
                "minute",
                "requests_per_minute",
                "avg_latency",
                "latency_stddev",
                "error_rate",
                "anomaly_score",
                "status"
            ]
        ].to_string(index=False)
    )

    anomaly_count = (
        results["status"] == "ANOMALY"
    ).sum()

    print(
        f"\nAnomalies detected: {anomaly_count}"
    )

    if anomaly_count > 0:

        print(
            "\n🚨 PulseWatch detected abnormal application behavior!"
        )