import json
import re

from fastapi import APIRouter, Depends

from database import queries as q

_PRIORITY_ORDER = (
    "CASE priority WHEN 'Critical' THEN 0 WHEN 'High' THEN 1 "
    "WHEN 'Medium' THEN 2 WHEN 'Low' THEN 3 ELSE 4 END"
)

_CLOCK_KEYS = ("demo_clock", "demo_time", "current_time", "scenario_time", "now")
_SCENARIO_KEYS = ("scenario_name", "scenario", "scenario_title", "title")


def _first(meta: dict, keys, default):
    for key in keys:
        if meta.get(key):
            return str(meta[key])
    return default


def _split_list(raw):
    import json

    try:
        value = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    return [str(v) for v in value] if isinstance(value, list) else []

def _scenario_info(meta: dict):
    data = {}
    for value in meta.values():
        try:
            obj = json.loads(value)
        except (TypeError, ValueError):
            continue
        if isinstance(obj, dict) and ("name" in obj or "now" in obj):
            data = obj
            break
    name = re.sub(r"\s*\(simulated\)", "", str(data.get("name") or "Kabul River Flood"), flags=re.I)
    now = str(data.get("now") or "")
    label = f"{name} / {now[:10]}" if now else name
    clock = f"{now[11:16]} {now[19:]}".strip() if len(now) >= 16 else "09:30 +05:00"
    return label, clock


def build_dashboard_router(get_db) -> APIRouter:
    router = APIRouter(tags=["dashboard"])

    @router.get("/dashboard")
    def dashboard(conn=Depends(get_db)):
        summary = q.get_command_center_summary(conn)
        meta = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM meta")}

        rows = conn.execute(
            f"""
            SELECT i.id, i.title, i.priority, i.priority_score, i.evidence_confidence,
                   i.estimated_affected, i.medical_emergency, i.required_resources,
                    i.status, i.lat, i.lon, i.location_name,
                   (SELECT COUNT(*) FROM reports r WHERE r.incident_id = i.id) AS report_count
            FROM incidents i
            WHERE i.status <> 'resolved'
            ORDER BY {_PRIORITY_ORDER}, i.priority_score DESC, i.id
            """
        ).fetchall()

        incidents = [
            {
                "id": r["id"],
                "title": r["title"],
                "priority": r["priority"] or "Unrated",
                "confidence": r["evidence_confidence"],
                "affected": r["estimated_affected"],
                "medical": bool(r["medical_emergency"]),
                "needs": _split_list(r["required_resources"]),
                "reports": r["report_count"],
                "status": r["status"],
                "location": r["location_name"],
                "lat": r["lat"],
                "lon": r["lon"],
            }
            for r in rows
        ]

        scenario_label, demo_clock = _scenario_info(meta)
        return {
            "summary": summary,
            "incidents": incidents,
            "scenario": scenario_label,
            "demo_clock": demo_clock,
            "disclaimer": "SIMULATED data. Decision support only.",
        }

    return router
