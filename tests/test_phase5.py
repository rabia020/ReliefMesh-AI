"""Automated tests for Phase 5 (FastAPI endpoints)."""

import pytest
from fastapi.testclient import TestClient

from backend.main import app, get_db
from database.connection import get_connection
from database.seed import init_database


@pytest.fixture()
def client(tmp_path):
    """A TestClient wired to a fresh, seeded database in a temp folder
    (your real data/reliefmesh.db is never touched by these tests)."""
    db_path = tmp_path / "test.db"
    init_database(db_path)

    def override_get_db():
        conn = get_connection(db_path)
        try:
            yield conn
        finally:
            conn.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health_still_works_without_db(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_scenario_and_summary(client):
    scenario = client.get("/scenario").json()
    assert scenario["id"] == "flood-sim-001"

    summary = client.get("/summary").json()
    assert summary["active_incidents"] == 18
    assert summary["critical_incidents"] == 4
    assert summary["available_boats"] == 2
    assert summary["queued_reports"] == 7


def test_list_incidents_and_filters(client):
    all_incidents = client.get("/incidents").json()
    assert len(all_incidents) == 19

    critical = client.get("/incidents", params={"priority": "Critical"}).json()
    assert {i["id"] for i in critical} == {"INC-002", "INC-003", "INC-004", "INC-005"}

    medical = client.get("/incidents", params={"medical_only": True}).json()
    assert {i["id"] for i in medical} == {"INC-002", "INC-003", "INC-004", "INC-009"}


def test_get_incident_found_and_not_found(client):
    found = client.get("/incidents/INC-002")
    assert found.status_code == 200
    body = found.json()
    assert body["medical_emergency"] is True
    assert len(body["reports"]) == 5

    missing = client.get("/incidents/NOPE")
    assert missing.status_code == 404


def test_resources_shelters_hospitals(client):
    boats = client.get("/resources", params={"type": "boat", "status": "available"}).json()
    assert sorted(b["id"] for b in boats) == ["BT-1", "BT-2"]

    roomy = client.get("/shelters", params={"min_free": 30}).json()
    assert len(roomy) == 5

    hospitals = client.get("/hospitals").json()
    assert len(hospitals) == 5


def test_inject_reports_endpoint(client):
    response = client.post("/reports/inject")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 7
    assert body["injected_report_ids"][0] == "R-001"

    # Second call is safe and injects nothing further.
    second = client.post("/reports/inject").json()
    assert second["count"] == 0

    logs = client.get("/audit-logs").json()
    assert any(log["event_type"] == "reports_injected" for log in logs)


def test_actions_list_starts_empty(client):
    assert client.get("/actions").json() == []