# ReliefMesh AI

AI-powered disaster-response coordination platform (hackathon prototype).
Uses SIMULATED data. Decision support only.

## Quick start (Windows)

    python -m venv .venv
    .venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    copy .env.example .env

Backend:  `uvicorn backend.main:app --reload --port 8000`
Frontend: `streamlit run frontend/app.py`