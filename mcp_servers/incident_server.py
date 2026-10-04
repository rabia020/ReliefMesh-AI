"""Phase 14: Incident MCP Server (READ-ONLY, SIMULATED data).

Tools: get_incidents, get_incident, get_critical_incidents,
       search_incidents, get_nearby_incidents.

IMPORTANT: this server talks over stdio, so never use print() in this file.
Anything written to stdout would corrupt the MCP messages.
"""

import json
import math
import os
from contextlib import contextmanager
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from database.connection import get_connection

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:  # python-dotenv is optional here
    pass

PROJECT_ROOT = Path(__file__).resolve().parents[1]

VALID_STATUS = {"open", "in_progress", "resolved", "unverified"}
VALID_PRIORITY = {"Critical", "High", "Medium", "Low"}

LIST_COLUMNS = (
    "id, title, incident_type, location_name, lat, lon, estimated_affected, "
    "vulnerable_people, medical_emergency, priority, priority_score, "
    "evidence_confidence, status, required_resources, summary"
)
ORDER_BY = (
    "ORDER BY CASE priority WHEN 'Critical' THEN 0 WHEN 'High' THEN 1 "
    "WHEN 'Medium' THEN 2 WHEN 'Low' THEN 3 ELSE 4 END, priority_score DESC, id"
)


# ------------------------------------------------------------------ helpers
def _db_path() -> Path:
    path = Path(os.getenv("DATABASE_PATH", "data/reliefmesh.db"))
    return path if path.is_absolute() else PROJECT_ROOT / path


def open_readonly(path):
    """Opens the database and blocks every write on this connection."""
    conn = get_connection(path)
    conn.execute("PRAGMA query_only = ON")
    return conn


@contextmanager
def _connect():
    conn = open_readonly(_db_path())
    try:
        yield conn
    finally:
        conn.close()


def _query(conn, sql, params=()):
    cursor = conn.execute(sql, params)
    columns = [c[0] for c in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _clean(row: dict) -> dict:
    row = dict(row)
    if "required_resources" in row:
        try:
            row["required_resources"] = json.loads(row["required_resources"] or "[]")
        except (TypeError, ValueError):
            row["required_resources"] = []
    if "medical_emergency" in row:
        row["medical_emergency"] = bool(row["medical_emergency"])
    return row


def _clamp(limit, default=50, high=200) -> int:
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        return default
    return max(1, min(limit, high))


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# ------------------------------------------------- plain logic (testable)
def list_incidents_logic(conn, status=None, priority=None, limit=50):
    sql = f"SELECT {LIST_COLUMNS} FROM incidents WHERE 1=1"
    params = []
    if status:
        if status not in VALID_STATUS:
            raise ValueError(f"status must be one of {sorted(VALID_STATUS)}")
        sql += " AND status = ?"
        params.append(status)
    if priority:
        if priority not in VALID_PRIORITY:
            raise ValueError(f"priority must be one of {sorted(VALID_PRIORITY)}")
        sql += " AND priority = ?"
        params.append(priority)
    sql += f" {ORDER_BY} LIMIT ?"
    params.append(_clamp(limit))
    return [_clean(r) for r in _query(conn, sql, params)]


def critical_incidents_logic(conn):
    sql = (
        f"SELECT {LIST_COLUMNS} FROM incidents "
        f"WHERE priority = 'Critical' AND status != 'resolved' {ORDER_BY}"
    )
    return [_clean(r) for r in _query(conn, sql)]


def get_incident_logic(conn, incident_id):
    rows = _query(conn, "SELECT * FROM incidents WHERE id = ?", (incident_id,))
    if not rows:
        return {"error": f"Incident {incident_id} not found"}
    incident = _clean(rows[0])
    incident["reports"] = _query(
        conn,
        "SELECT id, timestamp, language, source_type, text, status "
        "FROM reports WHERE incident_id = ? ORDER BY timestamp",
        (incident_id,),
    )
    incident["actions"] = _query(
        conn,
        "SELECT id, title, status, proposed_by, proposed_at "
        "FROM actions WHERE incident_id = ? ORDER BY id",
        (incident_id,),
    )
    return incident


def search_incidents_logic(conn, query, limit=20):
    words = (query or "").split()
    if not words:
        raise ValueError("query must not be empty")
    clauses, params = [], []
    for word in words:
        like = f"%{word}%"
        clauses.append(
            "(title LIKE ? OR summary LIKE ? OR location_name LIKE ? OR incident_type LIKE ?)"
        )
        params.extend([like, like, like, like])
    sql = (
        f"SELECT {LIST_COLUMNS} FROM incidents WHERE " + " AND ".join(clauses)
        + f" {ORDER_BY} LIMIT ?"
    )
    params.append(_clamp(limit, default=20))
    return [_clean(r) for r in _query(conn, sql, params)]


def nearby_incidents_logic(conn, lat, lon, radius_km=5.0, limit=20):
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("lat must be -90..90 and lon must be -180..180")
    if radius_km <= 0:
        raise ValueError("radius_km must be greater than 0")
    rows = _query(
        conn, f"SELECT {LIST_COLUMNS} FROM incidents WHERE NOT (lat = 0 AND lon = 0)"
    )
    found = []
    for row in rows:
        distance = _haversine_km(lat, lon, row["lat"], row["lon"])
        if distance <= radius_km:
            row = _clean(row)
            row["distance_km"] = round(distance, 2)  # straight-line, not road distance
            found.append(row)
    found.sort(key=lambda r: r["distance_km"])
    return found[:_clamp(limit, default=20)]


# --------------------------------------------------------------- MCP tools
mcp = FastMCP("reliefmesh-incidents")


@mcp.tool()
def get_incidents(status: str | None = None, priority: str | None = None,
                  limit: int = 50) -> list[dict]:
    """List incidents, most urgent first. Optional filters: status (open,
    in_progress, resolved, unverified) and priority (Critical, High, Medium, Low)."""
    with _connect() as conn:
        return list_incidents_logic(conn, status, priority, limit)


@mcp.tool()
def get_incident(incident_id: str) -> dict:
    """Get one incident by id (for example INC-001) with its linked reports
    and any proposed actions."""
    with _connect() as conn:
        return get_incident_logic(conn, incident_id)


@mcp.tool()
def get_critical_incidents() -> list[dict]:
    """List all unresolved incidents with priority Critical."""
    with _connect() as conn:
        return critical_incidents_logic(conn)


@mcp.tool()
def search_incidents(query: str, limit: int = 20) -> list[dict]:
    """Search incidents by words in title, summary, location or type.
    All words must match."""
    with _connect() as conn:
        return search_incidents_logic(conn, query, limit)


@mcp.tool()
def get_nearby_incidents(lat: float, lon: float, radius_km: float = 5.0,
                         limit: int = 20) -> list[dict]:
    """List incidents within radius_km of a point, nearest first.
    Distance is straight-line, not road distance."""
    with _connect() as conn:
        return nearby_incidents_logic(conn, lat, lon, radius_km, limit)


if __name__ == "__main__":
    mcp.run()  # stdio transport