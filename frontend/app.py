import importlib
import inspect
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

st.set_page_config(page_title="ReliefMesh AI", page_icon="🛟", layout="wide")

from frontend import db, theme, views  # noqa: E402
from frontend.command_center import render_command_center  # noqa: E402
from frontend.db import BackendError  # noqa: E402


def _resolve(module_name, *preferred):
    try:
        module = importlib.import_module(module_name)
    except Exception:
        return None
    for name in preferred:
        fn = getattr(module, name, None)
        if callable(fn):
            return fn
    candidates = [
        fn for name, fn in inspect.getmembers(module, inspect.isfunction)
        if name.startswith("render") and fn.__module__ == module.__name__
    ]
    return candidates[0] if len(candidates) == 1 else None


def _or_missing(fn, name):
    if fn:
        return fn

    def page():
        st.info(f"The {name} page was not found. See the note in frontend/app.py (_resolve).")

    return page


PAGES = {
    "Command Center": ("dashboard", lambda: render_command_center("Audit Log")),
    "Incident Intelligence": ("monitoring", views.render_incident_intelligence),
    "Live Map": ("map", _or_missing(
        _resolve("frontend.live_map", "render_live_map", "render"), "Live Map")),
    "Resource Center": ("groups", views.render_resource_center),
    "AI Copilot": ("smart_toy", _or_missing(
        _resolve("frontend.copilot", "render_copilot", "render"), "AI Copilot")),
    "Resource Optimization": ("balance", _or_missing(
        _resolve("frontend.optimizer", "render_optimizer", "render"), "Resource Optimization")),
    "Approval Center": ("assignment_turned_in", _or_missing(
        _resolve("frontend.approval_center", "render_approval_center", "render"), "Approval Center")),
    "Image Intelligence": ("image", _or_missing(
        _resolve("frontend.image_intel", "render_image_intel", "render"), "Image Intelligence")),
    "Audit Log": ("fact_check", views.render_audit_log),
    
}


def main():
    theme.inject_css()
    theme.sidebar_brand()

    if not db.database_exists():
        st.error(
            "Cannot reach the backend or its database.\n\n"
            "1. Make sure the backend is running: `uvicorn backend.main:app --reload --port 8000`\n"
            "2. Make sure the database is seeded: `python scripts/init_db.py`\n"
            "3. Check that BACKEND_URL matches the backend's address."
        )
        st.stop()

    page = st.sidebar.radio(
        "Go to", list(PAGES.keys()), key="nav", label_visibility="collapsed",
        format_func=lambda name: f":material/{PAGES[name][0]}: {name}",
    )

    st.sidebar.divider()
    with st.sidebar.expander("Demo controls"):
        st.caption("Resets ALL data back to the original simulated starting state.")
        confirm = st.checkbox("I understand this erases current progress")
        if st.button("Reset demo data", disabled=not confirm, use_container_width=True):
            db.reset_demo_data()
            st.success("Demo data reset.")
            st.rerun()

    try:
        PAGES[page][1]()
    except BackendError as error:
        st.error(f"Lost connection to the backend while loading this page: {error}")


if __name__ == "__main__":
    main()
