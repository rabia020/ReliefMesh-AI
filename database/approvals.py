"""Phase 17: human approval of PROPOSED actions.

Approving only RECORDS a SIMULATED dispatch. No real-world resources are contacted.
Only a named human can approve, reject or ask for more information.
"""
import json
import re

from database.queries import log_audit, utc_now_iso

DECIDABLE = ("proposed", "info_requested")
NAME_PATTERN = re.compile(r"^[\w .\-]{2,40}$")
PRIORITY_RANK = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}


class ApprovalError(Exception):
    """kind is one of: not_found, conflict, invalid."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


# ---------------------------------------------------------------- helpers
def _rows(conn, sql, params=()):
    cursor = conn.execute(sql, params)
    columns = [c[0] for c in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _human(name) -> str:
    name = (name or "").strip()
    if not NAME_PATTERN.match(name):
        raise ApprovalError(
            "invalid", "Coordinator name is required (2-40 letters, numbers, spaces, . _ -)."
        )
    return f"human:{name}"


def _need_note(note) -> str:
    note = (note or "").strip()
    if len(note) < 3:
        raise ApprovalError("invalid", "A written note is required for this decision.")
    return note[:500]


def _load_action(conn, action_id: int) -> dict:
    rows = _rows(conn, "SELECT * FROM actions WHERE id = ?", (action_id,))
    if not rows:
        raise ApprovalError("not_found", f"Action {action_id} not found.")
    action = rows[0]
    try:
        action["resource_ids"] = json.loads(action["resource_ids"] or "[]")
    except (TypeError, ValueError):
        action["resource_ids"] = []
    return action


def _ensure_decidable(action: dict):
    if action["status"] not in DECIDABLE:
        raise ApprovalError(
            "conflict",
            f"Action {action['id']} is already {action['status']}. Decisions are final.",
        )


def describe_action(conn, action: dict) -> dict:
    """Action plus the incident and resource details a coordinator needs to decide."""
    incident = _rows(
        conn,
        "SELECT title, priority, evidence_confidence FROM incidents WHERE id = ?",
        (action["incident_id"],),
    )
    incident = incident[0] if incident else {}
    resources = []
    for rid in action["resource_ids"]:
        row = _rows(
            conn, "SELECT id, name, type, status FROM resources WHERE id = ?", (rid,)
        )
        resources.append(row[0] if row else {"id": rid, "name": rid, "type": "?", "status": "missing"})
    return {
        "id": action["id"],
        "incident_id": action["incident_id"],
        "incident_title": incident.get("title"),
        "incident_priority": incident.get("priority"),
        "evidence_confidence": incident.get("evidence_confidence"),
        "action_type": action["action_type"],
        "title": action["title"],
        "reason": action["reason"],
        "resources": resources,
        "status": action["status"],
        "proposed_by": action["proposed_by"],
        "proposed_at": action["proposed_at"],
        "decided_by": action["decided_by"],
        "decided_at": action["decided_at"],
        "decision_note": action["decision_note"],
        "executed_at": action["executed_at"],
        "result": action["result"],
    }


# ---------------------------------------------------------------- queries
def list_pending(conn) -> list:
    rows = _rows(
        conn,
        "SELECT * FROM actions WHERE status IN ('proposed', 'info_requested') ORDER BY id",
    )
    out = []
    for row in rows:
        row["resource_ids"] = json.loads(row["resource_ids"] or "[]")
        out.append(describe_action(conn, row))
    out.sort(key=lambda a: (PRIORITY_RANK.get(a["incident_priority"], 4), a["id"]))
    return out


def list_history(conn, limit: int = 20) -> list:
    limit = max(1, min(int(limit), 100))
    rows = _rows(
        conn,
        "SELECT * FROM actions WHERE status IN ('executed', 'rejected') "
        "ORDER BY decided_at DESC, id DESC LIMIT ?",
        (limit,),
    )
    for row in rows:
        row["resource_ids"] = json.loads(row["resource_ids"] or "[]")
    return [describe_action(conn, row) for row in rows]


def get_action(conn, action_id: int) -> dict:
    return describe_action(conn, _load_action(conn, action_id))


# -------------------------------------------------------------- decisions
def approve_action(conn, action_id: int, decided_by: str, note=None) -> dict:
    who = _human(decided_by)
    action = _load_action(conn, action_id)
    _ensure_decidable(action)

    # Check EVERYTHING before writing anything.
    ready, problems = [], []
    for rid in action["resource_ids"]:
        rows = _rows(conn, "SELECT id, name, status FROM resources WHERE id = ?", (rid,))
        if not rows:
            problems.append(f"{rid} does not exist")
        elif rows[0]["status"] != "available":
            problems.append(f"{rows[0]['name']} is {rows[0]['status']}")
        else:
            ready.append(rows[0])
    if problems:
        raise ApprovalError(
            "conflict",
            "Cannot approve: " + "; ".join(problems)
            + ". Reject this action or request more information.",
        )
    if not ready:
        raise ApprovalError("conflict", "This action has no resources to dispatch.")

    incident_id = action["incident_id"]
    now = utc_now_iso()
    names = ", ".join(r["name"] for r in ready)
    result = (f"SIMULATED dispatch recorded: {names} assigned to {incident_id}. "
              "No real-world resources were contacted.")
    note = (note or "").strip()[:500] or None
    try:
        conn.execute(
            "UPDATE actions SET status = 'executed', decided_by = ?, decided_at = ?, "
            "decision_note = ?, executed_at = ?, result = ? WHERE id = ?",
            (who, now, note, now, result, action_id),
        )
        for r in ready:
            conn.execute(
                "UPDATE resources SET status = 'deployed', current_assignment = ? WHERE id = ?",
                (incident_id, r["id"]),
            )
        conn.execute(
            "UPDATE incidents SET status = 'in_progress' WHERE id = ? AND status = 'open'",
            (incident_id,),
        )
        log_audit(
            conn, actor=who, event_type="action_approved",
            message=f"{who} APPROVED '{action['title']}' for {incident_id}. {result}",
            incident_id=incident_id, action_id=action_id,
            details={"resource_ids": [r["id"] for r in ready], "note": note, "result": result},
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return get_action(conn, action_id)


def reject_action(conn, action_id: int, decided_by: str, note) -> dict:
    who = _human(decided_by)
    note = _need_note(note)
    action = _load_action(conn, action_id)
    _ensure_decidable(action)
    now = utc_now_iso()
    result = "Rejected by coordinator. Nothing was dispatched."
    try:
        conn.execute(
            "UPDATE actions SET status = 'rejected', decided_by = ?, decided_at = ?, "
            "decision_note = ?, result = ? WHERE id = ?",
            (who, now, note, result, action_id),
        )
        log_audit(
            conn, actor=who, event_type="action_rejected",
            message=f"{who} REJECTED '{action['title']}' for {action['incident_id']}: {note}",
            incident_id=action["incident_id"], action_id=action_id,
            details={"note": note},
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return get_action(conn, action_id)


def request_info(conn, action_id: int, decided_by: str, note) -> dict:
    who = _human(decided_by)
    note = _need_note(note)
    action = _load_action(conn, action_id)
    _ensure_decidable(action)
    now = utc_now_iso()
    try:
        conn.execute(
            "UPDATE actions SET status = 'info_requested', decided_by = ?, decided_at = ?, "
            "decision_note = ? WHERE id = ?",
            (who, now, note, action_id),
        )
        log_audit(
            conn, actor=who, event_type="info_requested",
            message=(f"{who} REQUESTED MORE INFORMATION on '{action['title']}' "
                     f"for {action['incident_id']}: {note}"),
            incident_id=action["incident_id"], action_id=action_id,
            details={"note": note},
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return get_action(conn, action_id)