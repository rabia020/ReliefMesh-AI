"""Builds the Live Map with folium. No Streamlit in this file, so it is easy to test."""
import html

import folium

PRIORITY_COLORS = {"Critical": "#d62728", "High": "#ff7f0e", "Medium": "#e6b800", "Low": "#2ca02c"}
RESOLVED_COLOR = "#7f7f7f"
RESOURCE_ICONS = {"boat": "ship", "ambulance": "ambulance", "rescue_team": "users",
                  "medical_team": "user-md"}
RESOURCE_COLORS = {"available": "green", "deployed": "darkblue", "maintenance": "gray"}
ROAD_COLORS = {"blocked": "#d62728", "partial": "#ff7f0e", "disputed": "#7f7f7f"}
DEFAULT_CENTER = (34.0, 71.98)


def _popup(lines):
    return folium.Popup("<br>".join(html.escape(str(line)) for line in lines), max_width=320)


def build_map(data: dict, route: dict | None = None) -> folium.Map:
    fmap = folium.Map(location=DEFAULT_CENTER, zoom_start=13, tiles="OpenStreetMap",
                      control_scale=True)
    groups = {name: folium.FeatureGroup(name=name) for name in
              ("Incidents", "Resources", "Shelters", "Hospitals", "Blocked roads", "Dispatches")}
    points = []

    for i in data.get("incidents", []):
        color = (RESOLVED_COLOR if i.get("status") == "resolved"
                 else PRIORITY_COLORS.get(i.get("priority"), "#1f77b4"))
        radius = 6 + min((i.get("estimated_affected") or 0) / 8, 14)
        folium.CircleMarker(
            location=[i["lat"], i["lon"]], radius=radius, color=color, weight=2,
            fill=True, fill_color=color, fill_opacity=0.7,
            tooltip=f"{i['id']} {i.get('priority') or '?'}",
            popup=_popup([
                f"{i['id']}: {i.get('title')}", f"Priority: {i.get('priority')}",
                f"Status: {i.get('status')}", f"Place: {i.get('location_name')}",
                f"Affected: {i.get('estimated_affected')}, vulnerable: {i.get('vulnerable_people')}",
                f"Medical emergency: {'yes' if i.get('medical_emergency') else 'no'}",
                f"Evidence confidence: {i.get('evidence_confidence')}%",
            ]),
        ).add_to(groups["Incidents"])
        points.append([i["lat"], i["lon"]])

    for r in data.get("resources", []):
        folium.Marker(
            location=[r["lat"], r["lon"]], tooltip=f"{r['name']} ({r['status']})",
            popup=_popup([f"{r['name']} ({r['type']})", f"Status: {r['status']}",
                          f"Crew: {r.get('crew_size')}", f"Capacity: {r.get('capacity_people')} people",
                          f"Assignment: {r.get('current_assignment') or 'none'}"]),
            icon=folium.Icon(color=RESOURCE_COLORS.get(r["status"], "gray"),
                             icon=RESOURCE_ICONS.get(r["type"], "question"), prefix="fa"),
        ).add_to(groups["Resources"])
        points.append([r["lat"], r["lon"]])

    for s in data.get("shelters", []):
        folium.Marker(
            location=[s["lat"], s["lon"]], tooltip=f"{s['name']}: {s['free_space']} free",
            popup=_popup([s["name"], f"Free space: {s['free_space']} of {s['capacity']}",
                          f"Status: {s['status']}", f"Road access: {s['road_access']}"]),
            icon=folium.Icon(color="purple", icon="home", prefix="fa"),
        ).add_to(groups["Shelters"])
        points.append([s["lat"], s["lon"]])

    for h in data.get("hospitals", []):
        folium.Marker(
            location=[h["lat"], h["lon"]],
            tooltip=f"{h['name']}: {h['available_beds']} beds",
            popup=_popup([h["name"], f"Beds free: {h['available_beds']}",
                          f"ICU free: {h['icu_available']}", f"Status: {h['status']}",
                          f"Emergency open: {'yes' if h.get('emergency_open') else 'no'}"]),
            icon=folium.Icon(color="darkred", icon="h-square", prefix="fa"),
        ).add_to(groups["Hospitals"])
        points.append([h["lat"], h["lon"]])

    for road in data.get("blocked_roads", []):
        color = ROAD_COLORS.get(road["status"], "#7f7f7f")
        folium.Circle(
            location=[road["lat"], road["lon"]], radius=road["radius_m"], color=color, weight=3,
            fill=True, fill_color=color, fill_opacity=0.25, dash_array="6",
            tooltip=f"{road['name']} ({road['status']})",
            popup=_popup([road["name"], f"Status: {road['status']}", f"Reason: {road.get('reason')}"]),
        ).add_to(groups["Blocked roads"])
        points.append([road["lat"], road["lon"]])

    for d in data.get("dispatches", []):
        done = d["status"] == "executed"
        folium.PolyLine(
            [[d["from"]["lat"], d["from"]["lon"]], [d["to"]["lat"], d["to"]["lon"]]],
            color="#2ca02c" if done else "#1f77b4", weight=3,
            dash_array=None if done else "8",
            tooltip=f"{d['status'].upper()}: {d['resource_name']} to {d['incident_id']}",
        ).add_to(groups["Dispatches"])

    if route and route.get("geometry"):
        group = folium.FeatureGroup(name="Selected route")
        folium.PolyLine(
            route["geometry"], color="#d62728" if route.get("blocked") else "#0057ff", weight=5,
            tooltip=(f"Road route ({route.get('route_source')}): "
                     f"{route.get('distance_km')} km, {route.get('duration_min')} min"),
        ).add_to(group)
        group.add_to(fmap)

    for group in groups.values():
        group.add_to(fmap)
    folium.LayerControl(collapsed=False).add_to(fmap)

    if len(points) >= 2:
        lats, lons = [p[0] for p in points], [p[1] for p in points]
        if max(lats) - min(lats) > 1e-6 or max(lons) - min(lons) > 1e-6:
            fmap.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]], padding=(30, 30))
    return fmap