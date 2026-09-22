"""ReliefMesh AI - Streamlit dashboard (Phase 4)."""

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from frontend import db, views  # noqa: E402

st.set_page_config(page_title="ReliefMesh AI", page_icon="🛟", layout="wide")

PAGES = {
    "🧭 Command Center": views.render_command_center,
    "🔍 Incident Intelligence": views.render_incident_intelligence,
    "🗺️ Live Map": views.render_live_map_placeholder,
    "🚑 Resource Center": views.render_resource_center,
    "🤖 AI Copilot": views.render_copilot_placeholder,
    "✅ Approval Center": views.render_approval_placeholder,
    "📜 Audit Log": views.render_audit_log,
}


def main():
    st.sidebar.title("🛟 ReliefMesh AI")
    st.sidebar.caption("SIMULATED demo data. Decision-support prototype only.")

    if not db.database_exists():
        st.error(
            "No database found. Open a terminal in the project root and run:\n\n"
            "`python scripts/init_db.py`\n\nthen refresh this page."
        )
        st.stop()

    page = st.sidebar.radio("Go to", list(PAGES.keys()), label_visibility="collapsed")

    with st.sidebar.expander("⚙️ Demo controls"):
        st.caption("Resets ALL data back to the original simulated starting state.")
        confirm = st.checkbox("I understand this erases current progress")
        if st.button("Reset demo data", disabled=not confirm, use_container_width=True):
            db.reset_demo_data()
            st.success("Demo data reset.")
            st.rerun()

    st.warning(
        "⚠️ SIMULATED DEMO DATA. ReliefMesh AI is a decision-support prototype. "
        "It does not replace emergency services, doctors, rescue professionals, "
        "or government authorities.",
        icon="⚠️",
    )

    PAGES[page]()


if __name__ == "__main__":
    main()