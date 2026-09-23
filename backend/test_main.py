from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


def test_home():

    response = client.get("/")

    assert response.status_code == 200

    assert response.json()["message"] == "PulseWatch is running!"


def test_health():

    response = client.get("/health")

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "healthy"


def test_metrics():

    response = client.get("/metrics")

    assert response.status_code == 200

    data = response.json()

    assert "total_requests" in data

    assert "error_rate_percent" in data

    assert "average_latency_seconds" in data


def test_anomalies():

    response = client.get("/anomalies")

    assert response.status_code == 200

    data = response.json()

    assert "status" in data

    assert "anomalies_detected" in data

    assert "windows_analyzed" in data