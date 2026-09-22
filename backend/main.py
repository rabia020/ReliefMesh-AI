"""ReliefMesh AI - FastAPI backend (Phase 5: read endpoints + demo controls)."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from backend import config
from database import queries as q
from database.connection import get_connection
from database.seed import init_database
from pydantic import BaseModel

from llm.client import LLMError, get_llm_client

app = FastAPI(
    title=config.APP_NAME,
    version=config.APP_VERSION,
    description="Disaster-response coordination backend (simulated demo data).",
)

# Hackathon setting: the frontend (Streamlit Cloud) and backend (Render) run as
# separate services with no login system, so we allow any origin to call this API.
# Tighten this before any real deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    """One short-lived SQLite connection per request."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


# --------------------------------------------------------------------- basic
@app.get("/")
def root():
    return {"message": f"{config.APP_NAME} backend is running", "docs": "/docs"}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "app": config.APP_NAME,
        "version": config.APP_VERSION,
        "environment": config.ENVIRONMENT,
        "time_utc": datetime.now(timezone.utc).isoformat(),
        "disclaimer": config.SAFETY_DISCLAIMER,
    }


@app.get("/scenario")
def scenario(conn=Depends(get_db)):
    return q.get_scenario(conn)


@app.get("/summary")
def summary(conn=Depends(get_db)):
    return q.get_command_center_summary(conn)


# ---------------------------------------------------------------- incidents
@app.get("/incidents")
def list_incidents(
    priority: Optional[str] = None,
    status: Optional[str] = None,
    medical_only: bool = False,
    active_only: bool = False,
    conn=Depends(get_db),
):
    return q.list_incidents(
        conn, priority=priority, status=status,
        medical_only=medical_only, active_only=active_only,
    )


@app.get("/incidents/{incident_id}")
def get_incident(incident_id: str, conn=Depends(get_db)):
    incident = q.get_incident(conn, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    return incident


# ------------------------------------------------------------------ reports
@app.get("/reports")
def list_reports(
    incident_id: Optional[str] = None,
    status: Optional[str] = None,
    conn=Depends(get_db),
):
    return q.list_reports(conn, incident_id=incident_id, status=status)


@app.post("/reports/inject")
def inject_reports(conn=Depends(get_db)):
    """Demo step: moves queued citizen reports to 'received'."""
    ids = q.inject_demo_reports(conn)
    return {"injected_report_ids": ids, "count": len(ids)}


# -------------------------------------------------------- resources & sites
@app.get("/resources")
def list_resources(
    type: Optional[str] = Query(None, alias="type"),
    status: Optional[str] = None,
    conn=Depends(get_db),
):
    return q.list_resources(conn, type=type, status=status)


@app.get("/shelters")
def list_shelters(min_free: Optional[int] = None, conn=Depends(get_db)):
    return q.list_shelters(conn, min_free=min_free)


@app.get("/hospitals")
def list_hospitals(conn=Depends(get_db)):
    return q.list_hospitals(conn)


# --------------------------------------------------------- actions & audit
@app.get("/actions")
def list_actions(
    status: Optional[str] = None,
    incident_id: Optional[str] = None,
    conn=Depends(get_db),
):
    return q.list_actions(conn, status=status, incident_id=incident_id)


@app.get("/audit-logs")
def list_audit_logs(
    incident_id: Optional[str] = None,
    limit: int = 200,
    conn=Depends(get_db),
):
    return q.list_audit_logs(conn, incident_id=incident_id, limit=limit)


# --------------------------------------------------------------------- LLM
class LLMTestRequest(BaseModel):
    prompt: str = "Reply with exactly one word: OK"


@app.post("/llm/test")
def llm_test(body: LLMTestRequest):
    """Manual connectivity check for the configured LLM provider (Phase 6)."""
    client = get_llm_client()
    try:
        result = client.complete(body.prompt)
    except LLMError as error:
        raise HTTPException(status_code=502, detail=str(error))
    return {
        "provider": result.provider,
        "model": result.model,
        "output": result.output,
        "elapsed_ms": result.elapsed_ms,
    }


# ------------------------------------------------------------------- admin
@app.post("/admin/reset-demo")
def reset_demo():
    """Rebuilds the database from data/seed/*.json (used by the dashboard's
    'Reset demo data' button). Not covered by automated tests, since it
    would overwrite the real database file."""
    counts = init_database()
    return {"status": "reset", "row_counts": counts}