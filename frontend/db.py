"""Talks to the ReliefMesh FastAPI backend over HTTP.

frontend/views.py and frontend/app.py import this module without knowing (or
caring) whether the data comes from a direct database connection or an API
call. This file changed in Phase 5; the rest of the frontend did not.
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
TIMEOUT = 8


class BackendError(Exception):
    """Raised when the backend cannot be reached or returns an unexpected error."""


def _get(path, params=None):
    try:
        response = requests.get(f"{BACKEND_URL}{path}", params=params, timeout=TIMEOUT)
    except requests.exceptions.RequestException as error:
        raise BackendError(f"Could not reach the backend at {BACKEND_URL}: {error}") from error
    if response.status_code == 404:
        return None
    if not response.ok:
        raise BackendError(f"Backend returned {response.status_code} for {path}: {response.text}")
    return response.json()


def _post(path, params=None):
    try:
        response = requests.post(f"{BACKEND_URL}{path}", params=params, timeout=TIMEOUT)
    except requests.exceptions.RequestException as error:
        raise BackendError(f"Could not reach the backend at {BACKEND_URL}: {error}") from error
    if not response.ok:
        raise BackendError(f"Backend returned {response.status_code} for {path}: {response.text}")
    return response.json()


def backend_ready() -> bool:
    """True if the backend is reachable and its database is seeded."""
    try:
        health = _get("/health")
        if health is None:
            return False
        summary = _get("/summary")
        return summary is not None
    except BackendError:
        return False


# Kept as an alias so frontend/app.py's existing check still works unchanged.
def database_exists() -> bool:
    return backend_ready()


def get_summary():
    return _get("/summary")


def get_scenario():
    return _get("/scenario")


def get_incidents(**filters):
    return _get("/incidents", params=filters)


def get_incident(incident_id):
    return _get(f"/incidents/{incident_id}")


def get_resources(**filters):
    return _get("/resources", params=filters)


def get_shelters(**filters):
    return _get("/shelters", params=filters)


def get_hospitals():
    return _get("/hospitals")


def get_audit_logs(**filters):
    return _get("/audit-logs", params=filters)


def get_actions(**filters):
    return _get("/actions", params=filters)


def inject_demo_reports():
    body = _post("/reports/inject")
    return body["injected_report_ids"]


def reset_demo_data():
    return _post("/admin/reset-demo")

def test_llm(prompt: str = "Reply with exactly one word: OK"):
    """Calls POST /llm/test. Uses a longer timeout, since LLM calls are slower
    than the other endpoints."""
    try:
        response = requests.post(f"{BACKEND_URL}/llm/test", json={"prompt": prompt}, timeout=45)
    except requests.exceptions.RequestException as error:
        raise BackendError(f"Could not reach the backend at {BACKEND_URL}: {error}") from error
    if not response.ok:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise BackendError(detail)
    return response.json()