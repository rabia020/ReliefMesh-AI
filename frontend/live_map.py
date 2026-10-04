import os

import folium
import httpx
import streamlit as st
from streamlit_folium import st_folium

try:
    from frontend.map_builder import build_map
except ImportError:
    from map_builder import build_map

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")


def _call(path, params=None):
    try:
        response = httpx.get(f"{BACKEND_URL}{path}", params=params, timeout=30.0)
    except httpx.HTTPError as error:
        return None, f"Cannot reach the backend at {BACKEND_URL}: {error}"
    if response.status_code >= 400:
        return None, f"{response.status_code}: {response.text}"
    return response.json(), None


def _place_search():
    with st.form("lm_search_form", clear_on_submit=False):
        left, right = st.columns([5, 1])
        query = left.text_input(
            "Search a place", key="lm_query", label_visibility="collapsed",
            placeholder="Search any place: city, area, street or landmark (e.g. Nala Lai Rawalpindi)",
        )
        submitted = right.form_submit_button("Search", use_container_width=True)
    if submitted and query.strip():
        data, error = _call("/geocode", {"q": query.strip()})
        if error:
            st.warning(error)
        else:
            st.session_state["lm_results"] = data["results"]
            st.session_state["lm_place"] = data["results"][0] if data["results"] else None
            if not data["results"]:
                st.info("No place found. Try a more specific name.")
    results = st.session_state.get("lm_results") or []
    if len(results) > 1:
        names = [r["name"] for r in results]
        current = st.session_state.get("lm_place")
        index = names.index(current["name"]) if current and current["name"] in names else 0
        pick = st.selectbox("Matching places", names, index=index, key="lm_pick")
        st.session_state["lm_place"] = results[names.index(pick)]
    if st.session_state.get("lm_place") and st.button("Clear search", key="lm_clear"):
        st.session_state.pop("lm_place", None)
        st.session_state.pop("lm_results", None)
        st.rerun()


def render_live_map():
    st.header("Live Map")
    data, error = _call("/map/data")
    if error:
        st.error(error)
        return

    available = sum(1 for r in data["resources"] if r["status"] == "available")
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Incidents on map", len(data["incidents"]))
    col2.metric("Resources available", f"{available} of {len(data['resources'])}")
    col3.metric("Shelters", len(data["shelters"]))
    col4.metric("Blocked roads", len(data["blocked_roads"]))
    col5.metric("Dispatches", len(data["dispatches"]))
    st.button("Refresh map")

    _place_search()

    labels = {f"#{d['action_id']} {d['status']}: {d['resource_name']} to {d['incident_id']}": d
              for d in data["dispatches"]}
    choice = st.selectbox("Show the road route for a dispatch", ["(none)"] + list(labels))
    use_osrm = st.checkbox("Use OpenStreetMap routing (needs internet)", value=True)

    route = None
    if choice != "(none)":
        d = labels[choice]
        route, route_error = _call("/map/route", params={
            "start_lat": d["from"]["lat"], "start_lon": d["from"]["lon"],
            "end_lat": d["to"]["lat"], "end_lon": d["to"]["lon"], "use_osrm": str(use_osrm).lower(),
        })
        if route_error:
            st.warning(route_error)
        else:
            st.info(f"{route['route_source']} route: {route['distance_km']} km, "
                    f"about {route['duration_min']} min. {route.get('note') or ''}")

    fmap = build_map(data, route)
    place = st.session_state.get("lm_place")
    if place:
        folium.Marker(
            [place["lat"], place["lon"]], tooltip=place["name"],
            icon=folium.Icon(color="purple", icon="search"),
        ).add_to(fmap)
        fmap.fit_bounds([[place["lat"] - 0.03, place["lon"] - 0.03],
                         [place["lat"] + 0.03, place["lon"] + 0.03]])
    st_folium(fmap, height=620, use_container_width=True, returned_objects=[])

    st.caption(
        "Red / orange / yellow / green circles = incident priority (gray = resolved). "
        "Green icon = available resource, dark blue = deployed. Purple = shelter, dark red H = hospital. "
        "Dashed circle = blocked road. Dashed blue line = proposed dispatch, solid green = approved. "
        "Purple search pin = the place you searched for. SIMULATED data."
    )
    if data["incidents_without_location"]:
        st.caption(f"{data['incidents_without_location']} incident(s) have no location yet "
                   "and are not on the map.")


if __name__ == "__main__":
    st.set_page_config(page_title="ReliefMesh Live Map", layout="wide")
    render_live_map()