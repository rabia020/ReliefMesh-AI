"""Query helpers for the ReliefMesh SQLite database.

Every function takes an open connection first and returns plain Python
dicts/lists (JSON columns already decoded). FastAPI, Streamlit, the agents
and the MCP servers will all reuse these functions.
"""

import json
from datetime import datetime, timezone

TABLES = (
    "meta", "places", "incidents", "reports", "resources",
    "shelters", "hospitals", "blocked_roads", "actions", "audit_logs",
)

_JSON_COLUMNS = {
    "required_resources", "capabilities", "facilities", "specialties",
    "aliases", "structured", "resource_ids", "details",
}
_BOOL_COLUMNS = {"medical_emergency", "emergency_open"}

_PRIORITY_ORDER = (
    "CASE priority WHEN 'Critical' THEN 0 WHEN 'High' THEN 1 "
    "WHEN 'Medium' THEN 2 WHEN 'Low' THEN 3 ELSE 4 END"
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _to_dict(row):
    if row is None:
        return None
    data = dict(row)
    for key in _JSON_COLUMNS.intersection(data):
        if data[key] is not None:
            data[key] = json.loads(data[key])
    for key in _BOOL_COLUMNS.intersection(data):
        data[key] = bool(data[key])
    return data


def _rows(cursor):
    return [_to_dict(row) for row in cursor.fetchall()]


# ---------------------------------------------------------------- general
def table_counts(conn) -> dict:
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}


def get_scenario(conn) -> dict:
    row = conn.execute("SELECT value FROM meta WHERE key = 'scenario'").fetchone()
    return json.loads(row["value"])


# -------------------------------------------------------------- incidents
def list_incidents(conn, priority=None, status=None, medical_only=False, active_only=False):
    """Incidents sorted Critical first, then by number of people affected."""
    sql = (
        "SELECT incidents.*, "
        "(SELECT COUNT(*) FROM reports WHERE reports.incident_id = incidents.id) AS report_count "
        "FROM incidents WHERE 1 = 1"
    )
    params = []
    if priority:
        sql += " AND priority = ?"
        params.append(priority)
    if status:
        sql += " AND status = ?"
        params.append(status)
    if active_only:
        sql += " AND status IN ('open', 'in_progress')"
    if medical_only:
        sql += " AND medical_emergency = 1"
    sql += f" ORDER BY {_PRIORITY_ORDER}, estimated_affected DESC, id"
    return _rows(conn.execute(sql, params))


def get_incident(conn, incident_id):
    """One incident with all of its reports, or None if it does not exist."""
    row = conn.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,)).fetchone()
    if row is None:
        return None
    incident = _to_dict(row)
    incident["reports"] = list_reports(conn, incident_id=incident_id)
    return incident


# ---------------------------------------------------------------- reports
def list_reports(conn, incident_id=None, status=None):
    sql = "SELECT * FROM reports WHERE 1 = 1"
    params = []
    if incident_id:
        sql += " AND incident_id = ?"
        params.append(incident_id)
    if status:
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY timestamp, id"
    return _rows(conn.execute(sql, params))


def inject_demo_reports(conn, actor="human:demo_operator"):
    """Demo step: moves the queued reports to 'received' so the agents can process them.
    Returns the injected report ids (empty list if nothing was queued)."""
    ids = [r["id"] for r in conn.execute(
        "SELECT id FROM reports WHERE status = 'queued' ORDER BY timestamp, id")]
    if not ids:
        return []
    conn.executemany("UPDATE reports SET status = 'received' WHERE id = ?", [(i,) for i in ids])
    log_audit(conn, actor=actor, event_type="reports_injected",
              message=f"{len(ids)} citizen reports injected into the system",
              details={"report_ids": ids})          # log_audit also commits the update
    return ids


# -------------------------------------------------------------- resources
def list_resources(conn, type=None, status=None):
    sql = "SELECT * FROM resources WHERE 1 = 1"
    params = []
    if type:
        sql += " AND type = ?"
        params.append(type)
    if status:
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY type, id"
    return _rows(conn.execute(sql, params))


def list_shelters(conn, min_free=None):
    """Shelters with a computed free_capacity. min_free keeps only shelters with room."""
    sql = "SELECT *, capacity - current_occupancy AS free_capacity FROM shelters WHERE 1 = 1"
    params = []
    if min_free is not None:
        sql += " AND capacity - current_occupancy >= ?"
        params.append(min_free)
    sql += " ORDER BY id"
    return _rows(conn.execute(sql, params))


def list_hospitals(conn):
    return _rows(conn.execute("SELECT * FROM hospitals ORDER BY id"))


# ---------------------------------------------------------- command center
def get_command_center_summary(conn) -> dict:
    def one(sql):
        return conn.execute(sql).fetchone()[0] or 0

    active = "status IN ('open', 'in_progress')"
    available = "status = 'available'"
    return {
        "active_incidents": one(f"SELECT COUNT(*) FROM incidents WHERE {active}"),
        "critical_incidents": one(
            f"SELECT COUNT(*) FROM incidents WHERE {active} AND priority = 'Critical'"),
        "unverified_incidents": one("SELECT COUNT(*) FROM incidents WHERE status = 'unverified'"),
        "medical_emergencies": one(
            f"SELECT COUNT(*) FROM incidents WHERE {active} AND medical_emergency = 1"),
        "available_rescue_teams": one(
            f"SELECT COUNT(*) FROM resources WHERE type = 'rescue_team' AND {available}"),
        "available_boats": one(
            f"SELECT COUNT(*) FROM resources WHERE type = 'boat' AND {available}"),
        "available_ambulances": one(
            f"SELECT COUNT(*) FROM resources WHERE type = 'ambulance' AND {available}"),
        "available_medical_teams": one(
            f"SELECT COUNT(*) FROM resources WHERE type = 'medical_team' AND {available}"),
        "shelter_capacity_total": one("SELECT SUM(capacity) FROM shelters WHERE status = 'open'"),
        "shelter_occupied": one("SELECT SUM(current_occupancy) FROM shelters WHERE status = 'open'"),
        "shelter_free": one(
            "SELECT SUM(capacity - current_occupancy) FROM shelters WHERE status = 'open'"),
        "hospital_beds_available": one("SELECT SUM(available_beds) FROM hospitals"),
        "icu_beds_available": one("SELECT SUM(icu_available) FROM hospitals"),
        "queued_reports": one("SELECT COUNT(*) FROM reports WHERE status = 'queued'"),
        "pending_actions": one("SELECT COUNT(*) FROM actions WHERE status = 'proposed'"),
    }


# ---------------------------------------------------- actions and audit log
def log_audit(conn, actor, event_type, message, incident_id=None,
              action_id=None, details=None, timestamp=None):
    """Adds one line to the append-only audit log and saves it."""
    conn.execute(
        "INSERT INTO audit_logs (timestamp, actor, event_type, incident_id, action_id, message, details) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (timestamp or utc_now_iso(), actor, event_type, incident_id, action_id,
         message, json.dumps(details or {}, ensure_ascii=False)),
    )
    conn.commit()


def list_audit_logs(conn, incident_id=None, limit=200):
    sql = "SELECT * FROM audit_logs WHERE 1 = 1"
    params = []
    if incident_id:
        sql += " AND incident_id = ?"
        params.append(incident_id)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    return _rows(conn.execute(sql, params))


def create_proposed_action(conn, incident_id, action_type, title, reason,
                           resource_ids, proposed_by):
    """Stores an AI proposal with status 'proposed'. Nothing is dispatched.
    (Approve/reject logic comes in Phase 17.)"""
    cursor = conn.execute(
        "INSERT INTO actions (incident_id, action_type, title, reason, resource_ids, "
        "status, proposed_by, proposed_at) VALUES (?, ?, ?, ?, ?, 'proposed', ?, ?)",
        (incident_id, action_type, title, reason,
         json.dumps(resource_ids, ensure_ascii=False), proposed_by, utc_now_iso()),
    )
    action_id = cursor.lastrowid
    log_audit(conn, actor=proposed_by, event_type="action_proposed",
              incident_id=incident_id, action_id=action_id,
              message=f"Proposed: {title}",
              details={"reason": reason, "resource_ids": resource_ids})
    return action_id


def list_actions(conn, status=None, incident_id=None):
    sql = "SELECT * FROM actions WHERE 1 = 1"
    params = []
    if status:
        sql += " AND status = ?"
        params.append(status)
    if incident_id:
        sql += " AND incident_id = ?"
        params.append(incident_id)
    sql += " ORDER BY id DESC"
    return _rows(conn.execute(sql, params))