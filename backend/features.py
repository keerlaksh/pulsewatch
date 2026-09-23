import psycopg2
import pandas as pd


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

            COALESCE(STDDEV_POP(latency), 0) AS latency_stddev,

            COUNT(*) FILTER (
                WHERE status_code >= 400
            )::float / NULLIF(COUNT(*), 0) AS error_rate

        FROM request_metrics

        WHERE timestamp >= NOW() - INTERVAL '1 hour'

        GROUP BY minute

        ORDER BY minute;
    """

    df = pd.read_sql_query(query, connection)

    connection.close()

    return df


if __name__ == "__main__":

    df = get_features()

    print("\nPulseWatch Features\n")
    print(df.to_string(index=False))

    print("\nNumber of time windows:", len(df))