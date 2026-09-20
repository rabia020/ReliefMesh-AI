"""ReliefMesh AI - FastAPI backend (Phase 1: health check only)."""

from datetime import datetime, timezone

from fastapi import FastAPI

from backend import config

app = FastAPI(
    title=config.APP_NAME,
    version=config.APP_VERSION,
    description="Disaster-response coordination backend (simulated demo data).",
)


@app.get("/")
def root():
    """Simple welcome message."""
    return {"message": f"{config.APP_NAME} backend is running", "docs": "/docs"}


@app.get("/health")
def health():
    """Used by the frontend (and later by Render) to check the backend is alive."""
    return {
        "status": "ok",
        "app": config.APP_NAME,
        "version": config.APP_VERSION,
        "environment": config.ENVIRONMENT,
        "time_utc": datetime.now(timezone.utc).isoformat(),
        "disclaimer": config.SAFETY_DISCLAIMER,
    }