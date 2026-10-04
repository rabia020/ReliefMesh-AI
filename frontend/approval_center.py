"""Phase 17: Approval Center (Streamlit).
Run on its own:  streamlit run frontend/approval_center.py
The function render_approval_center() can also be called from your dashboard.
"""
import os

import httpx
import streamlit as st

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")


def _call(method, path, **kwargs):
    """Returns (data, error_text)."""
    try:
        response = httpx.request(method, f"{BACKEND_URL}{path}", timeout=15.0, **kwargs)
    except httpx.HTTPError as error:
        return None, f"Cannot reach the backend at {BACKEND_URL}: {error}"
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        if isinstance(detail, list):
            detail = "; ".join(str(d.get("msg", d)) for d in detail)
        return None, f"{response.status_code}: {detail}"
    return response.json(), None


def _decide(action_id, verb, name, note):
    data, error = _call(
        "POST", f"/approvals/{action_id}/{verb}",
        json={"decided_by": name, "note": note or None},
    )
    if error:
        st.error(error)
        return
    st.session_state["approval_flash"] = (
        f"Action {data['id']} is now {data['status']}. {data.get('result') or ''}"
    )
    st.rerun()


def render_approval_center():
    st.header("Approval Center")


    flash = st.session_state.pop("approval_flash", None)
    if flash:
        st.success(flash)

    name = st.text_input("Your name (recorded in the audit log)", key="coordinator_name")

    pending, error = _call("GET", "/approvals/pending")
    if error:
        st.error(error)
        return

    st.subheader(f"Pending AI proposals: {pending['count']}")
    if pending["count"] == 0:
        st.info("No pending proposals.")

    for action in pending["actions"]:
        with st.container(border=True):
            label = ("WAITING FOR MORE INFORMATION" if action["status"] == "info_requested"
                     else "PROPOSED ACTION")
            st.markdown(f"**{label} #{action['id']}**")
            st.markdown(f"**Action:** {action['title']}")
            st.markdown(
                f"**Incident:** {action['incident_id']}, {action['incident_title']} "
                f"({action['incident_priority']}, {action['evidence_confidence']}% confidence)"
            )
            st.markdown("**Reason:**")
            st.text(action["reason"])
            st.markdown("**Resources:** " + ", ".join(
                f"{r['name']} ({r['status']})" for r in action["resources"]))
            if action["status"] == "info_requested":
                st.info(f"{action['decided_by']} asked: {action['decision_note']}")

            note = st.text_area(
                "Note (required for Reject and Request more information)",
                key=f"note_{action['id']}",
            )
            ready = bool(name.strip())
            if not ready:
                st.caption("Enter your name above to enable the buttons.")
            col1, col2, col3 = st.columns(3)
            if col1.button("APPROVE", type="primary", key=f"approve_{action['id']}",
                           disabled=not ready):
                _decide(action["id"], "approve", name, note)
            if col2.button("REJECT", key=f"reject_{action['id']}", disabled=not ready):
                _decide(action["id"], "reject", name, note)
            if col3.button("REQUEST MORE INFORMATION", key=f"info_{action['id']}",
                           disabled=not ready):
                _decide(action["id"], "request-info", name, note)

    with st.expander("Recent decisions"):
        history, error = _call("GET", "/approvals/history")
        if error:
            st.error(error)
        else:
            for action in history["actions"]:
                st.markdown(
                    f"**#{action['id']} {action['status'].upper()}**: {action['title']} "
                    f"({action['incident_id']}) by {action['decided_by']} at {action['decided_at']}"
                )
                if action["decision_note"]:
                    st.caption(f"Note: {action['decision_note']}")
            if not history["actions"]:
                st.write("No decisions yet.")


if __name__ == "__main__":
    st.set_page_config(page_title="ReliefMesh Approval Center", layout="wide")
    render_approval_center()