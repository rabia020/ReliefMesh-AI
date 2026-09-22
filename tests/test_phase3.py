"""Automated tests for Phase 3 (SQLite database)."""

import sqlite3

import pytest

from database.connection import ROOT, get_connection, resolve_db_path
from database.queries import (
    create_proposed_action,
    get_command_center_summary,
    get_incident,
    get_scenario,
    inject_demo_reports,
    list_actions,
    list_audit_logs,
    list_hospitals,
    list_incidents,
    list_reports,
    list_resources,
    list_shelters,
)
from database.seed import init_database

EXPECTED_COUNTS = {
    "meta": 1, "places": 30, "incidents": 19, "reports": 50, "resources": 10,
    "shelters": 8, "hospitals": 5, "blocked_roads": 5, "actions": 0, "audit_logs": 1,
}


@pytest.fixture()
def db(tmp_path):
    """A fresh, seeded database in a temporary folder (your real database is untouched)."""
    path = tmp_path / "test.db"
    init_database(path)
    conn = get_connection(path)
    yield conn
    conn.close()


def _dump(conn):
    tables = ("incidents", "reports", "resources", "shelters", "hospitals", "places", "blocked_roads")
    return {t: [tuple(r) for r in conn.execute(f"SELECT * FROM {t} ORDER BY 1")] for t in tables}


def test_resolve_db_path(tmp_path):
    assert resolve_db_path("data/x.db") == ROOT / "data" / "x.db"
    absolute = tmp_path / "y.db"
    assert resolve_db_path(absolute) == absolute


def test_init_creates_all_tables_with_expected_counts(tmp_path):
    assert init_database(tmp_path / "t.db") == EXPECTED_COUNTS


def test_no_ground_truth_in_database(db):
    tables = {r["name"] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "answer_key" not in tables
    report_cols = {r["name"] for r in db.execute("PRAGMA table_info(reports)")}
    incident_cols = {r["name"] for r in db.execute("PRAGMA table_info(incidents)")}
    assert not any(c.startswith("truth") for c in report_cols)
    assert not any(c.startswith("expected") for c in incident_cols)


def test_baseline_reports_and_demo_queue(db):
    processed = list_reports(db, status="processed")
    assert len(processed) == 43
    assert all(r["incident_id"] for r in processed)
    queued = list_reports(db, status="queued")
    assert [r["id"] for r in queued] == [f"R-00{i}" for i in range(1, 8)]
    assert all(r["incident_id"] is None and r["batch"] == "demo" for r in queued)


def test_seeded_incidents_are_the_19_baseline(db):
    incidents = list_incidents(db)
    ids = [i["id"] for i in incidents]
    assert len(ids) == 19
    assert "INC-001" not in ids
    assert all(i["origin"] == "seed" for i in incidents)
    assert all(i["priority"] and i["evidence_confidence"] is not None for i in incidents)
    by_id = {i["id"]: i for i in incidents}
    assert by_id["INC-002"]["evidence_confidence"] == 90
    assert by_id["INC-020"]["status"] == "unverified"
    assert get_scenario(db)["id"] == "flood-sim-001"


def test_command_center_summary_baseline(db):
    assert get_command_center_summary(db) == {
        "active_incidents": 18,
        "critical_incidents": 4,
        "unverified_incidents": 1,
        "medical_emergencies": 4,
        "available_rescue_teams": 2,
        "available_boats": 2,
        "available_ambulances": 2,
        "available_medical_teams": 1,
        "shelter_capacity_total": 1960,
        "shelter_occupied": 1213,
        "shelter_free": 747,
        "hospital_beds_available": 92,
        "icu_beds_available": 6,
        "queued_reports": 7,
        "pending_actions": 0,
    }


def test_list_incidents_sorted_by_priority(db):
    rank = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    incidents = list_incidents(db)
    ranks = [rank[i["priority"]] for i in incidents]
    assert ranks == sorted(ranks)
    assert incidents[0]["id"] == "INC-002"


def test_list_incidents_filters(db):
    critical = list_incidents(db, priority="Critical")
    assert {i["id"] for i in critical} == {"INC-002", "INC-003", "INC-004", "INC-005"}
    medical = list_incidents(db, medical_only=True)
    assert {i["id"] for i in medical} == {"INC-002", "INC-003", "INC-004", "INC-009"}
    assert [i["id"] for i in list_incidents(db, status="unverified")] == ["INC-020"]
    assert len(list_incidents(db, active_only=True)) == 18


def test_get_incident_with_reports(db):
    inc = get_incident(db, "INC-002")
    assert inc["medical_emergency"] is True
    assert inc["required_resources"] == ["boat", "medical_team"]
    assert [r["id"] for r in inc["reports"]] == ["R-008", "R-009", "R-010", "R-011", "R-012"]
    form = next(r for r in inc["reports"] if r["id"] == "R-011")
    assert form["structured"]["people_affected"] == 60
    assert form["image_file"] == "rooftops_flood.png"
    assert get_incident(db, "INC-001") is None   # not created until the demo
    assert get_incident(db, "NOPE") is None


def test_resource_shelter_hospital_queries(db):
    boats = list_resources(db, type="boat", status="available")
    assert sorted(b["id"] for b in boats) == ["BT-1", "BT-2"]
    assert isinstance(boats[0]["capabilities"], list)
    assert len(list_resources(db)) == 10

    roomy = list_shelters(db, min_free=30)
    assert len(roomy) == 5
    assert all(s["free_capacity"] >= 30 for s in roomy)
    s01 = next(s for s in list_shelters(db) if s["id"] == "S-01")
    assert s01["free_capacity"] == 15

    hospitals = list_hospitals(db)
    assert len(hospitals) == 5
    assert [h["id"] for h in hospitals if "dialysis" in h["specialties"]] == ["H-01"]
    assert isinstance(hospitals[0]["emergency_open"], bool)


def test_inject_demo_reports(db):
    before = len(list_audit_logs(db))
    ids = inject_demo_reports(db)
    assert ids == [f"R-00{i}" for i in range(1, 8)]
    assert list_reports(db, status="queued") == []
    assert len(list_reports(db, status="received")) == 7
    assert len(list_audit_logs(db)) == before + 1
    assert inject_demo_reports(db) == []                     # second call does nothing
    assert len(list_audit_logs(db)) == before + 1


def test_reseeding_is_deterministic(tmp_path):
    path = tmp_path / "t.db"
    init_database(path)
    conn = get_connection(path)
    first = _dump(conn)
    conn.close()

    counts = init_database(path)                              # reset on the same file
    conn = get_connection(path)
    second = _dump(conn)
    conn.close()

    assert first == second
    assert counts["audit_logs"] == 1


def test_foreign_keys_enforced(db):
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO reports (id, timestamp, language, source_type, text, batch, status, incident_id) "
            "VALUES ('R-999', '2026-08-14T10:00:00+05:00', 'en', 'sms', 'test', 'live', 'processed', 'INC-999')"
        )


def test_check_constraints(db):
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE shelters SET current_occupancy = capacity + 1 WHERE id = 'S-01'")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE incidents SET priority = 'Urgent' WHERE id = 'INC-002'")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE incidents SET evidence_confidence = 150 WHERE id = 'INC-002'")


def test_executed_action_requires_human_decision(db):
    action_id = create_proposed_action(
        db, "INC-002", "dispatch_resource", "Dispatch Rescue Boat 1",
        "60 affected", ["BT-1"], "ai:resource_agent")

    # An AI cannot mark its own proposal as executed...
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "UPDATE actions SET status = 'executed', executed_at = 'x', "
            "decided_by = 'ai:resource_agent', decided_at = 'x' WHERE id = ?", (action_id,))
    # ...and nobody can execute it without a recorded decision.
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE actions SET status = 'executed', executed_at = 'x' WHERE id = ?", (action_id,))
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE actions SET status = 'rejected' WHERE id = ?", (action_id,))

    # A named human decision is accepted.
    db.execute(
        "UPDATE actions SET status = 'executed', decided_by = 'human:coordinator', "
        "decided_at = '2026-08-14T09:40:00+05:00', executed_at = '2026-08-14T09:40:00+05:00' "
        "WHERE id = ?", (action_id,))
    db.commit()
    assert list_actions(db)[0]["status"] == "executed"


def test_audit_log_is_append_only(db):
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        db.execute("UPDATE audit_logs SET message = 'tampered'")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        db.execute("DELETE FROM audit_logs")
    assert len(list_audit_logs(db)) == 1


def test_create_proposed_action_writes_audit(db):
    action_id = create_proposed_action(
        db, "INC-002", "dispatch_resource", "Dispatch Rescue Boat 1",
        "60 affected, 3 vulnerable", ["BT-1"], "ai:resource_agent")
    actions = list_actions(db)
    assert len(actions) == 1
    assert actions[0]["status"] == "proposed"
    assert actions[0]["resource_ids"] == ["BT-1"]
    assert actions[0]["decided_by"] is None

    logs = list_audit_logs(db, incident_id="INC-002")
    assert logs[0]["event_type"] == "action_proposed"
    assert logs[0]["action_id"] == action_id
    assert get_command_center_summary(db)["pending_actions"] == 1