"""Read/write helpers the Streamlit dashboard uses to talk to the SQLite database.

Every function opens its own short-lived connection. The database is small,
so this is simpler and safer than sharing one connection across Streamlit's
worker threads.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database import queries as q
from database.connection import get_connection, resolve_db_path
from database.seed import init_database


def database_exists() -> bool:
    return resolve_db_path().exists()


def run(fn, *args, **kwargs):
    """Opens a connection, calls fn(conn, *args, **kwargs), then closes it."""
    conn = get_connection()
    try:
        return fn(conn, *args, **kwargs)
    finally:
        conn.close()


def get_summary():
    return run(q.get_command_center_summary)


def get_scenario():
    return run(q.get_scenario)


def get_incidents(**filters):
    return run(q.list_incidents, **filters)


def get_incident(incident_id):
    return run(q.get_incident, incident_id)


def get_resources(**filters):
    return run(q.list_resources, **filters)


def get_shelters(**filters):
    return run(q.list_shelters, **filters)


def get_hospitals():
    return run(q.list_hospitals)


def get_audit_logs(**filters):
    return run(q.list_audit_logs, **filters)


def get_actions(**filters):
    return run(q.list_actions, **filters)


def inject_demo_reports():
    return run(q.inject_demo_reports)


def reset_demo_data():
    """Rebuilds the database from data/seed/*.json (the sidebar 'Reset demo' button)."""
    return init_database()