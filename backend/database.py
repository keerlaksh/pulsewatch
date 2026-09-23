import psycopg2

connection = psycopg2.connect(
    host="localhost",
    port=5432,
    database="pulsewatch",
    user="pulsewatch",
    password="pulsewatch"
)

cursor = connection.cursor()

cursor.execute("""
    CREATE TABLE IF NOT EXISTS request_metrics (
        id SERIAL PRIMARY KEY,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        endpoint VARCHAR(255),
        status_code INTEGER,
        latency FLOAT
    )
""")

connection.commit()

print("Database connected!")
print("request_metrics table created!")

cursor.close()
connection.close()