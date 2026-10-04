import streamlit as st

from frontend import theme
from frontend.api_client import post_json
from frontend.db import BackendError

EXAMPLES = [
    "Heavy flood on Nala Lai in Rawalpindi. About 40 people stuck on rooftops, two children sick, boat needed.",
    "Pul ke paas pani bohat barh gaya hai, 10 families phansi hui hain, Kabul River Bridge.",
]


def _pin_map(lat: float, lon: float, label: str):
    import folium

    fmap = folium.Map(location=[lat, lon], zoom_start=13, tiles="OpenStreetMap")
    folium.Marker([lat, lon], tooltip=label, icon=folium.Icon(color="red", icon="warning-sign")).add_to(fmap)
    return fmap


def render_scenario_box() -> None:
    with st.expander("Test a new scenario", expanded=False):
        st.caption(
            "Type a report in English, Roman Urdu or Urdu. Include how many people are affected and what "
            "is needed for the most realistic result. The analysis is a preview until you press Save."
        )
        ex = st.selectbox("Example", ["(write my own)"] + EXAMPLES, key="scn_example")
        text = st.text_area(
            "Report text", value="" if ex.startswith("(") else ex, height=90, key=f"scn_text_{ex}",
            placeholder="e.g. Heavy flood near Katarian in Rawalpindi, 40 people stuck, 2 children sick",
        )
        c1, c2 = st.columns(2)
        language = c1.selectbox("Language", ["en", "roman_ur", "ur"], key="scn_lang")
        location = c2.text_input("Location (optional, improves the map pin)", key="scn_loc",
                                 placeholder="e.g. Nala Lai, Rawalpindi")

        if st.button("Analyze report", type="primary", disabled=len(text.strip()) < 5, key="scn_go"):
            with st.spinner("The crew is reading the report (can take 20-60 seconds)..."):
                try:
                    st.session_state["scn"] = {
                        "result": post_json("/scenario/analyze", {
                            "text": text.strip(), "language": language, "location": location.strip() or None,
                        }),
                        "request": {"text": text.strip(), "language": language,
                                    "location": location.strip() or None},
                    }
                except BackendError as error:
                    st.session_state.pop("scn", None)
                    st.error(f"Could not analyse: {error}")

        saved = st.session_state.get("scn")
        if not saved:
            return
        r, req = saved["result"], saved["request"]
        theme.banner("info", "Preview only. Nothing has been saved yet.")
        st.markdown(f"**{r.get('title') or 'Untitled incident'}**")
        if r.get("summary"):
            st.write(r["summary"])
        a, b, c, d = st.columns(4)
        a.metric("Priority", r.get("priority") or "-")
        b.metric("Confidence", f"{r['confidence']}%" if r.get("confidence") is not None else "-")
        c.metric("People affected", r.get("affected") if r.get("affected") is not None else "-")
        d.metric("Medical", "Yes" if r.get("medical") else "No")
        if not r.get("affected"):
            st.info(
                "No number of people was found in the report, so priority reflects only what the text states. "
                "Add details such as '40 people stuck, 2 children sick' for a more realistic result."
            )
        st.write("**Needs:** " + (", ".join(n.replace("_", " ") for n in r["needs"]) or "-"))
        if r.get("proposed_action"):
            st.write(f"**Proposed action (needs human approval):** {r['proposed_action']['title']}")
            st.caption(r["proposed_action"]["reason"])
        else:
            st.write("**Proposed action:** none (priority too low or no resource available).")

        if r.get("lat") is not None:
            st.write(f"**Location:** {r.get('location_name')}  (found via {r['place_source']})")
            try:
                from streamlit_folium import st_folium

                st_folium(_pin_map(r["lat"], r["lon"], r.get("title") or "Scenario"),
                          height=260, use_container_width=True, returned_objects=[], key="scn_map")
            except ImportError:
                st.map([{"lat": r["lat"], "lon": r["lon"]}], height=260)
            if r.get("approximate"):
                st.caption("The pin is approximate (area level). Enter a more exact place in Location to refine it.")
            st.caption("Resource recommendations use the simulated resource pool around Kabul.")
        else:
            st.warning("Could not find this place on the map. Type a clearer location above and analyze again.")

        s1, s2 = st.columns(2)
        if s1.button("Save as incident", disabled=r.get("lat") is None, key="scn_save"):
            try:
                out = post_json("/scenario/save", {**req, "lat": r["lat"], "lon": r["lon"]})
                st.session_state.pop("scn", None)
                st.session_state["scn_saved_msg"] = (
                    f"Saved as {out['incident_id']}. It now appears in the ledger and on the map."
                )
                st.rerun()
            except BackendError as error:
                st.error(f"Could not save: {error}")
        if s2.button("Discard preview", key="scn_discard"):
            st.session_state.pop("scn", None)
            st.rerun()