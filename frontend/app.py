"""ReliefMesh AI - Streamlit frontend (Phase 1: status page)."""

import os

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")

st.set_page_config(page_title="ReliefMesh AI", page_icon="🛟", layout="wide")

st.title("🛟 ReliefMesh AI")
st.caption(
    "When disaster creates information chaos, ReliefMesh turns that chaos "
    "into coordinated action."
)

st.warning(
    "SIMULATED DEMO DATA. ReliefMesh AI is a decision-support prototype. "
    "It does not replace emergency services, doctors, rescue professionals, "
    "or government authorities."
)

st.subheader("System status")
col1, col2 = st.columns(2)

with col1:
    st.metric("Frontend (Streamlit)", "Online")

with col2:
    try:
        response = requests.get(f"{BACKEND_URL}/health", timeout=3)
        response.raise_for_status()
        st.metric("Backend (FastAPI)", "Online")
        with st.expander("Backend response"):
            st.json(response.json())
    except requests.exceptions.RequestException:
        st.metric("Backend (FastAPI)", "Offline")
        st.info(
            "Start the backend in a second terminal:\n\n"
            "`uvicorn backend.main:app --reload --port 8000`"
        )

st.subheader("Build progress")
st.markdown(
    "- ✅ Phase 1: Project setup\n"
    "- ⬜ Phase 2: Synthetic disaster dataset\n"
    "- ⬜ Phase 3: SQLite database\n"
    "- ⬜ Phase 4+: Dashboard, agents, MCP, approvals..."
)