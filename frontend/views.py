"""Render functions for each ReliefMesh dashboard page (Phase 4)."""

from pathlib import Path

import streamlit as st

from frontend import db

ROOT = Path(__file__).resolve().parent.parent
IMAGES_DIR = ROOT / "data" / "images"

PRIORITY_EMOJI = {"Critical": "🔴", "High": "🟠", "Medium": "🟡", "Low": "🟢"}


def _priority_label(priority: str) -> str:
    return f"{PRIORITY_EMOJI.get(priority, '⚪')} {priority}"


def _yes_no(value: bool) -> str:
    return "Yes" if value else "No"


# ------------------------------------------------------------ Command Center
def render_command_center():
    st.header("🧭 Command Center")

    scenario = db.get_scenario()
    st.caption(f"{scenario['name']} — demo clock: {scenario['now']}")

    summary = db.get_summary()

    if summary["queued_reports"] > 0:
        col1, col2 = st.columns([3, 1])
        with col1:
            st.info(
                f"📨 {summary['queued_reports']} new citizen reports are waiting "
                "to be injected into the system (live demo step)."
            )
        with col2:
            if st.button("Inject demo reports", use_container_width=True):
                ids = db.inject_demo_reports()
                st.success(f"Injected {len(ids)} reports: {', '.join(ids)}")
                st.rerun()
    else:
        st.success(
            "✅ All citizen reports have been injected. "
            "(They will turn into incidents once the Intake Agent is built in Phase 7.)"
        )

    st.subheader("Situation summary")
    row1 = st.columns(4)
    row1[0].metric("Active incidents", summary["active_incidents"])
    row1[1].metric("Critical", summary["critical_incidents"])
    row1[2].metric("Medical emergencies", summary["medical_emergencies"])
    row1[3].metric("Unverified", summary["unverified_incidents"])

    row2 = st.columns(4)
    row2[0].metric("Rescue teams available", summary["available_rescue_teams"])
    row2[1].metric("Boats available", summary["available_boats"])
    row2[2].metric("Ambulances available", summary["available_ambulances"])
    row2[3].metric("Medical teams available", summary["available_medical_teams"])

    row3 = st.columns(3)
    row3[0].metric(
        "Shelter space free",
        f"{summary['shelter_free']} / {summary['shelter_capacity_total']}",
    )
    row3[1].metric("Hospital beds free", summary["hospital_beds_available"])
    row3[2].metric("ICU beds free", summary["icu_beds_available"])

    st.subheader("Active incidents")
    incidents = db.get_incidents(active_only=True)
    if not incidents:
        st.write("No active incidents.")
        return

    table = [
        {
            "ID": inc["id"],
            "Priority": _priority_label(inc["priority"]),
            "Confidence": f"{inc['evidence_confidence']}%",
            "Title": inc["title"],
            "Affected": inc["estimated_affected"],
            "Medical": _yes_no(inc["medical_emergency"]),
            "Needs": ", ".join(inc["required_resources"]),
            "Reports": inc["report_count"],
        }
        for inc in incidents
    ]
    st.dataframe(table, use_container_width=True, hide_index=True)


# ------------------------------------------------------- Incident Intelligence
def render_incident_intelligence():
    st.header("🔍 Incident Intelligence")

    incidents = db.get_incidents()
    if not incidents:
        st.warning(
            "No incidents yet. Run `python scripts/init_db.py`, "
            "or inject demo reports from the Command Center."
        )
        return

    options = {f"{i['id']} — {i['title']}": i["id"] for i in incidents}
    choice = st.selectbox("Select an incident", list(options.keys()))
    incident = db.get_incident(options[choice])

    st.subheader(incident["title"])

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Priority", _priority_label(incident["priority"]))
    col2.metric("Evidence confidence", f"{incident['evidence_confidence']}%")
    col3.metric("Affected people", incident["estimated_affected"])
    col4.metric("Vulnerable people", incident["vulnerable_people"])

    st.write(f"**Type:** {incident['incident_type'].replace('_', ' ').title()}")
    st.write(f"**Location:** {incident['location_name']} "
              f"({incident['lat']:.4f}, {incident['lon']:.4f})")
    st.write(f"**Medical emergency:** {_yes_no(incident['medical_emergency'])} "
              f"(severity {incident['medical_severity']}/3)")
    st.write(f"**Isolation level:** {incident['isolation']}/2")
    st.write(f"**Required resources:** {', '.join(incident['required_resources']) or 'None listed'}")
    st.write(f"**Status:** {incident['status']}")

    if incident["conflict_note"]:
        st.warning(f"⚠️ Conflicting reports: {incident['conflict_note']}")

    if incident["summary"]:
        st.info(f"**AI summary:** {incident['summary']}")

    st.subheader(f"Linked reports ({len(incident['reports'])})")
    for r in incident["reports"]:
        with st.expander(f"{r['id']} · {r['language']} · {r['source_type']} · {r['timestamp']}"):
            st.write(r["text"])
            if r["structured"]:
                st.json(r["structured"])
            if r["image_file"]:
                image_path = IMAGES_DIR / r["image_file"]
                if image_path.exists():
                    st.image(str(image_path), caption="SIMULATED image evidence")


# -------------------------------------------------------------- Resource Center
def render_resource_center():
    st.header("🚑 Resource Center")

    tab1, tab2, tab3 = st.tabs(["Teams, Boats & Ambulances", "Shelters", "Hospitals"])

    with tab1:
        resources = db.get_resources()
        table = [
            {
                "ID": r["id"],
                "Name": r["name"],
                "Type": r["type"].replace("_", " ").title(),
                "Status": r["status"].title(),
                "Base": r["base"],
                "Crew": r["crew_size"],
                "Capacity (people)": r["capacity_people"],
                "Current assignment": r["current_assignment"] or "—",
            }
            for r in resources
        ]
        st.dataframe(table, use_container_width=True, hide_index=True)

    with tab2:
        shelters = db.get_shelters()
        for s in shelters:
            fraction = s["current_occupancy"] / s["capacity"] if s["capacity"] else 0
            st.write(f"**{s['name']}** — {s['current_occupancy']} / {s['capacity']} "
                      f"({s['free_capacity']} free) · road access: {s['road_access']}")
            st.progress(min(fraction, 1.0))
            if s["notes"]:
                st.caption(s["notes"])

    with tab3:
        hospitals = db.get_hospitals()
        table = [
            {
                "ID": h["id"],
                "Name": h["name"],
                "Beds free": f"{h['available_beds']} / {h['total_beds']}",
                "ICU free": f"{h['icu_available']} / {h['icu_total']}",
                "Emergency open": _yes_no(h["emergency_open"]),
                "Specialties": ", ".join(h["specialties"]),
                "Status": h["status"],
            }
            for h in hospitals
        ]
        st.dataframe(table, use_container_width=True, hide_index=True)


# ------------------------------------------------------------------- Audit Log
def render_audit_log():
    st.header("📜 Audit Log")
    st.caption("Append-only history of every system and human action.")

    logs = db.get_audit_logs(limit=200)
    if not logs:
        st.write("No audit entries yet.")
        return

    table = [
        {
            "Time": log["timestamp"],
            "Actor": log["actor"],
            "Event": log["event_type"],
            "Incident": log["incident_id"] or "—",
            "Message": log["message"],
        }
        for log in logs
    ]
    st.dataframe(table, use_container_width=True, hide_index=True)


# ------------------------------------------------------------------ Placeholders
def render_live_map_placeholder():
    st.header("🗺️ Live Map")
    st.info(
        "Coming in Phase 11 (Routing Agent) and Phase 16 (Mapping MCP server). "
        "This page will show incidents, resources, shelters, hospitals, routes, "
        "and blocked roads on an OpenStreetMap/Folium map."
    )


def render_copilot_placeholder():
    st.header("🤖 AI Copilot")
    st.info(
        "Coming in Phase 20. You'll be able to ask natural-language questions such as "
        "\"What are the three most urgent incidents?\" or \"Where should I send the "
        "two available boats?\", answered using the MCP tools and the live database."
    )


def render_approval_placeholder():
    st.header("✅ Approval Center")
    st.info(
        "Coming in Phase 17 (Human-in-the-Loop). AI-proposed actions will appear here "
        "with Approve, Reject, and Request More Information buttons. No action is ever "
        "executed without a human decision — the database itself enforces this."
    )


def render_llm_test():
    st.header("🧪 LLM Connection Test")
    st.caption(
        "Temporary page for Phase 6, used to confirm your Gemini (or Ollama) setup works. "
        "This page will be replaced by the real AI Copilot in Phase 20."
    )
    prompt = st.text_area("Prompt to send", value="Reply with exactly one word: OK")
    if st.button("Send to LLM"):
        with st.spinner("Waiting for a response... (this can take up to 30 seconds)"):
            try:
                result = db.test_llm(prompt)
                st.success(
                    f"Provider: **{result['provider']}** · Model: **{result['model']}** · "
                    f"{result['elapsed_ms']} ms"
                )
                st.write(result["output"])
            except db.BackendError as error:
                st.error(str(error))