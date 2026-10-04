"""Query helpers for the ReliefMesh SQLite database."""

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


def table_counts(conn) -> dict:
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}


def get_scenario(conn) -> dict:
    row = conn.execute("SELECT value FROM meta WHERE key = 'scenario'").fetchone()
    return json.loads(row["value"])


def list_incidents(conn, priority=None, status=None, medical_only=False, active_only=False):
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
    row = conn.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,)).fetchone()
    if row is None:
        return None
    incident = _to_dict(row)
    incident["reports"] = list_reports(conn, incident_id=incident_id)
    return incident


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


def get_report(conn, report_id):
    """One report by id, or None if it does not exist. (Added in Phase 7 for the
    Intake Agent, which needs to load a single report to run extraction on.)"""
    row = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
    return _to_dict(row)


def inject_demo_reports(conn, actor="human:demo_operator"):
    ids = [r["id"] for r in conn.execute(
        "SELECT id FROM reports WHERE status = 'queued' ORDER BY timestamp, id")]
    if not ids:
        return []
    conn.executemany("UPDATE reports SET status = 'received' WHERE id = ?", [(i,) for i in ids])
    log_audit(conn, actor=actor, event_type="reports_injected",
              message=f"{len(ids)} citizen reports injected into the system",
              details={"report_ids": ids})
    return ids


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
    sql = "SELECT *, capacity - current_occupancy AS free_capacity FROM shelters WHERE 1 = 1"
    params = []
    if min_free is not None:
        sql += " AND capacity - current_occupancy >= ?"
        params.append(min_free)
    sql += " ORDER BY id"
    return _rows(conn.execute(sql, params))

def list_places(conn):
    return _rows(conn.execute("SELECT * FROM places ORDER BY id"))


def list_hospitals(conn):
    return _rows(conn.execute("SELECT * FROM hospitals ORDER BY id"))


def list_blocked_roads(conn):
    return _rows(conn.execute("SELECT * FROM blocked_roads ORDER BY id"))


def get_place(conn, place_id):
    row = conn.execute("SELECT * FROM places WHERE id = ?", (place_id,)).fetchone()
    return _to_dict(row)


def get_action(conn, action_id):
    row = conn.execute("SELECT * FROM actions WHERE id = ?", (action_id,)).fetchone()
    return _to_dict(row)


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
        "received_reports": one("SELECT COUNT(*) FROM reports WHERE status = 'received'"),
        "pending_actions": one("SELECT COUNT(*) FROM actions WHERE status = 'proposed'"),
    }


def log_audit(conn, actor, event_type, message, incident_id=None,
              action_id=None, details=None, timestamp=None):
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


def next_pipeline_incident_id(conn, merged: dict) -> str:
    """Picks an id for a newly created pipeline incident.

    The demo's missing baseline incident is INC-001 (Kabul River Bridge,
    trapped residents). If that slot is still empty and this cluster matches
    it, reuse INC-001 so the 3-minute demo always produces the same id.
    Otherwise allocate INC-P-001, INC-P-002, ...
    """
    existing = {row[0] for row in conn.execute("SELECT id FROM incidents")}
    if (
        merged.get("place_id") == "L-BRIDGE"
        and merged.get("incident_type") == "trapped_residents"
        and "INC-001" not in existing
    ):
        return "INC-001"
    n = 1
    while f"INC-P-{n:03d}" in existing:
        n += 1
    return f"INC-P-{n:03d}"


def save_pipeline_incident(conn, incident: dict, report_ids: list, actor="ai:supervisor") -> str:
    """Inserts one pipeline-created incident and links its reports.

    Does not dispatch resources. That only happens after a human approval
    (Phase 17 / decide_action).
    """
    incident_id = incident["id"]
    conn.execute(
        "INSERT INTO incidents (id, title, incident_type, place_id, location_name, lat, lon, "
        "estimated_affected, vulnerable_people, medical_emergency, medical_severity, isolation, "
        "required_resources, priority, priority_score, evidence_confidence, status, conflict_note, "
        "summary, first_report_time, last_report_time, origin) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pipeline')",
        (
            incident_id,
            incident["title"],
            incident["incident_type"],
            incident.get("place_id"),
            incident.get("location_name") or "Unknown location",
            incident.get("lat") if incident.get("lat") is not None else 0.0,
            incident.get("lon") if incident.get("lon") is not None else 0.0,
            incident.get("estimated_affected", 0),
            incident.get("vulnerable_people", 0),
            1 if incident.get("medical_emergency") else 0,
            incident.get("medical_severity", 0),
            incident.get("isolation", 0),
            json.dumps(incident.get("required_resources") or [], ensure_ascii=False),
            incident.get("priority"),
            incident.get("priority_score"),
            incident.get("evidence_confidence"),
            incident.get("status", "open"),
            incident.get("conflict_note"),
            incident.get("summary"),
            incident.get("first_report_time"),
            incident.get("last_report_time"),
        ),
    )
    if report_ids:
        conn.executemany(
            "UPDATE reports SET status = 'processed', incident_id = ? WHERE id = ?",
            [(incident_id, rid) for rid in report_ids],
        )
    log_audit(
        conn,
        actor=actor,
        event_type="incident_created",
        incident_id=incident_id,
        message=f"Pipeline created incident {incident_id}: {incident['title']}",
        details={
            "priority": incident.get("priority"),
            "evidence_confidence": incident.get("evidence_confidence"),
            "report_ids": report_ids,
        },
    )
    return incident_id


def decide_action(conn, action_id: int, decision: str, decided_by: str, note: str = "") -> dict:
    """Human-in-the-loop decision. AI callers are rejected by the schema
    (`decided_by` must start with 'human:'). Never call this from an agent."""
    if not decided_by or not str(decided_by).startswith("human:"):
        raise ValueError("Only a human actor (id starting with 'human:') can decide an action.")

    allowed = {"approve": "executed", "reject": "rejected", "request_info": "info_requested"}
    if decision not in allowed:
        raise ValueError(f"Unknown decision '{decision}'. Use approve, reject, or request_info.")

    action = get_action(conn, action_id)
    if action is None:
        raise KeyError(f"Action {action_id} not found")
    if action["status"] not in ("proposed", "info_requested"):
        raise ValueError(f"Action {action_id} is already {action['status']}")

    new_status = allowed[decision]
    now = utc_now_iso()
    executed_at = now if new_status == "executed" else None
    conn.execute(
        "UPDATE actions SET status = ?, decided_by = ?, decided_at = ?, "
        "decision_note = ?, executed_at = ?, result = ? WHERE id = ?",
        (
            new_status,
            decided_by,
            now,
            note or None,
            executed_at,
            "executed after human approval" if new_status == "executed" else None,
            action_id,
        ),
    )

    if new_status == "executed":
        for resource_id in action.get("resource_ids") or []:
            conn.execute(
                "UPDATE resources SET status = 'deployed', current_assignment = ? WHERE id = ?",
                (action["title"], resource_id),
            )

    event = {
        "approve": "action_approved",
        "reject": "action_rejected",
        "request_info": "action_info_requested",
    }[decision]
    log_audit(
        conn,
        actor=decided_by,
        event_type=event,
        incident_id=action["incident_id"],
        action_id=action_id,
        message=f"{decision}: {action['title']}",
        details={"note": note, "resource_ids": action.get("resource_ids")},
    )
    return get_action(conn, action_id)