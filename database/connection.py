"""Opens SQLite connections for ReliefMesh AI."""

import sqlite3
from pathlib import Path

from backend import config

ROOT = Path(__file__).resolve().parent.parent


def resolve_db_path(db_path=None) -> Path:
    path = Path(db_path or config.DATABASE_PATH)
    if not path.is_absolute():
        path = ROOT / path
    return path


def get_connection(db_path=None) -> sqlite3.Connection:
    path = resolve_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn