"""Helpers shared by the Resource and Mapping MCP servers (Phases 15-16).
Phase 14's incident_server.py keeps its own copies and is not changed.

IMPORTANT: MCP servers talk over stdio. Never use print() in server code.
"""
import json
import math
import os
from contextlib import contextmanager
from pathlib import Path

from database.connection import get_connection

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def db_path() -> Path:
    path = Path(os.getenv("DATABASE_PATH", "data/reliefmesh.db"))
    return path if path.is_absolute() else PROJECT_ROOT / path


def open_readonly(path):
    """Opens the database and blocks every write on this connection."""
    conn = get_connection(path)
    conn.execute("PRAGMA query_only = ON")
    return conn


@contextmanager
def connect():
    conn = open_readonly(db_path())
    try:
        yield conn
    finally:
        conn.close()


def query(conn, sql, params=()):
    """Runs a SELECT and returns a list of plain dicts."""
    cursor = conn.execute(sql, params)
    columns = [c[0] for c in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def parse_json_list(value):
    try:
        data = json.loads(value or "[]")
        return data if isinstance(data, list) else []
    except (TypeError, ValueError):
        return []


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    """Straight-line distance. Road distance comes from OSRM (Phase 16)."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
