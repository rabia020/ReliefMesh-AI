"""Automated tests for Phase 1."""

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_root_returns_message():
    response = client.get("/")
    assert response.status_code == 200
    assert "ReliefMesh AI" in response.json()["message"]


def test_health_is_ok():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["app"] == "ReliefMesh AI"
    assert "SIMULATED" in data["disclaimer"]