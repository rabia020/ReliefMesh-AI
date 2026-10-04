import pandas as pd
import streamlit as st

from frontend import theme
from frontend.api_client import get_json
from frontend.scenario_box import render_scenario_box

PRIORITIES = ["Critical", "High", "Medium", "Low", "Unrated"]
PRIORITY_COLORS = {
    "Critical": "#c8242f", "High": "#e07b1a", "Medium": "#d4a800",
    "Low": "#1a8a5a", "Unrated": "#6b7f8a",
}


def _matches(incident: dict, query: str) -> bool:
    words = query.lower().split()
    text = " ".join(
        str(incident.get(k) or "") for k in ("id", "title", "location", "priority", "status")
    ).lower()
    return all(w in text for w in words)


def _build_map(points: list[dict]):
    import folium

    lats = [p["lat"] for p in points]
    lons = [p["lon"] for p in points]
    fmap = folium.Map(
        location=[sum(lats) / len(lats), sum(lons) / len(lons)],
        zoom_start=12, control_scale=True,
        tiles="OpenStreetMap",
    )
    for p in points:
        color = PRIORITY_COLORS.get(p["priority"], PRIORITY_COLORS["Unrated"])
        folium.CircleMarker(
            [p["lat"], p["lon"]],
            radius=9 if p["priority"] == "Critical" else 7,
            color="#ffffff", weight=2, fill=True, fill_color=color, fill_opacity=0.95,
            tooltip=f'{p["id"]}: {p["title"]}',
            popup=folium.Popup(
                f'<b>{p["id"]}</b> ({p["priority"]})<br>{p["title"]}<br>'
                f'<i>{p.get("location") or ""}</i><br>Affected: {p["affected"]}',
                max_width=280,
            ),
        ).add_to(fmap)
    if len(points) > 1:
        fmap.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]], padding=(30, 30))
    else:
        fmap.location = [lats[0], lons[0]]
        fmap.options["zoom"] = 15
    return fmap


def _go(page_label: str) -> None:
    st.session_state["nav"] = page_label


def render_command_center(audit_page_label: str = "Audit Log") -> None:
    data = get_json("/dashboard")
    s = data["summary"]
    incidents = data["incidents"]

    theme.page_header("Command Center")
    

    waiting = (s.get("queued_reports") or 0) + (s.get("received_reports") or 0)
    if s.get("received_reports"):
        theme.banner("info", f"{s['received_reports']} injected report(s) are waiting for the crew to process.")
    

    theme.section("Situation summary", "Simulated snapshot")
    theme.metric_grid([
        ("Active incidents", s["active_incidents"], ""),
        ("Critical", s["critical_incidents"], "red"),
        ("Medical emergencies", s["medical_emergencies"], ""),
        ("Unverified", s["unverified_incidents"], "orange"),
        ("Rescue teams available", s["available_rescue_teams"], "green" if s["available_rescue_teams"] else "red"),
        ("Boats available", s["available_boats"], "green" if s["available_boats"] else "red"),
        ("Ambulances available", s["available_ambulances"], "green" if s["available_ambulances"] else "red"),
        ("Medical teams available", s["available_medical_teams"], "green" if s["available_medical_teams"] else "red"),
        ("Shelter space free", f"{s['shelter_free']} / {s['shelter_capacity_total']}", ""),
        ("Hospital beds free", s["hospital_beds_available"], ""),
        ("ICU beds free", s["icu_beds_available"], ""),
        ("Pending approvals", s["pending_actions"], "orange" if s["pending_actions"] else ""),
    ])


    if st.session_state.get("scn_saved_msg"):
        theme.banner("ok", st.session_state.pop("scn_saved_msg"))
    render_scenario_box()


    left, mid, right = st.columns([6, 1.3, 1.3])
    with left:
        query = st.text_input(
            "Search", key="cc_search", label_visibility="collapsed",
            placeholder="Search by place, incident ID or keyword (e.g. Bridge, INC-002, boat)",
        )
    with mid:
        with st.popover("Filters", use_container_width=True):
            chosen = st.multiselect("Priority", PRIORITIES, default=PRIORITIES, key="cc_prio")
            medical_only = st.checkbox("Medical emergencies only", key="cc_med")
    shown = [
        i for i in incidents
        if i["priority"] in chosen and (i["medical"] or not medical_only)
        and (not query.strip() or _matches(i, query))
    ]
    with right:
        frame = pd.DataFrame(shown)
        if not frame.empty:
            frame["needs"] = frame["needs"].apply(", ".join)
        st.download_button(
            "Export data", frame.to_csv(index=False).encode("utf-8"),
            file_name="reliefmesh_incidents.csv", mime="text/csv", use_container_width=True,
        )
    if query.strip():
        st.caption(f"{len(shown)} incident(s) match '{query.strip()}'. The map below shows the same results.")
    if not shown:
        st.info("No incidents match your search or filters.")

    limit = 10
    visible = shown[:limit]
    st.markdown(
        theme.ledger_html(
            "Active incidents ledger",
            f"{len(visible)} of {len(incidents)} simulated incidents shown",
            visible,
        ),
        unsafe_allow_html=True,
    )
    if len(shown) > limit:
        with st.expander(f"Show all {len(shown)} incidents"):
            st.markdown(theme.ledger_html("All incidents", f"{len(shown)} shown", shown), unsafe_allow_html=True)


    map_col, status_col = st.columns([2.1, 1])
    with map_col:
        st.markdown(
            '<div class="rm-panel-head" style="background:#fff;border:1px solid #dfe6eb;border-bottom:0;margin-top:6px">'
            "<h3>Regional overview</h3><p>Simulated incident locations (same style as Live Map)</p></div>",
            unsafe_allow_html=True,
        )
        points = [i for i in shown if i["lat"] is not None]
        if not points:
            st.info("No incident coordinates to show.")
        else:
            try:
                from streamlit_folium import st_folium

                st_folium(_build_map(points), height=380, use_container_width=True,
                          returned_objects=[], key="cc_map")
            except ImportError:
                st.map(pd.DataFrame(points)[["lat", "lon"]], height=380)
            st.markdown(
                " ".join(
                    f'<span style="font-size:13px;margin-right:14px"><span style="color:{c}">●</span> {n}</span>'
                    for n, c in PRIORITY_COLORS.items() if n != "Unrated"
                ),
                unsafe_allow_html=True,
            )
    with status_col:
        text = (
            "All injected reports have been processed by the crew (or none are waiting)."
            if not waiting
            else f"{waiting} report(s) still to be processed."
        )
        st.markdown(
            theme.dark_status_panel(
                "Processing status", text, "Demo record",
                "This interface shows simulated data. Nothing is dispatched automatically: "
                "every action needs a human decision in the Approval Center.",
            ),
            unsafe_allow_html=True,
        )
        st.button("View audit status", on_click=_go, args=(audit_page_label,), key="cc_audit")
