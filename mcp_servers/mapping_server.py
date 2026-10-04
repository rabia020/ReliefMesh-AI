"""Phase 16: Mapping MCP Server (READ-ONLY, SIMULATED data).

Tools: geocode_location, calculate_distance, get_route,
       find_nearby_hospitals, find_nearby_shelters.

Routing: OSRM (OpenStreetMap) with an honest straight-line fallback.
IMPORTANT: never use print() in this file (stdio transport).
"""
import os

import httpx
from mcp.server.fastmcp import FastMCP

from mcp_servers.common import connect, haversine_km, parse_json_list, query

OSRM_URL = os.getenv("OSRM_BASE_URL", "https://router.project-osrm.org").rstrip("/")
ASSUMED_SPEED_KMH = 25.0      # only used for the straight-line fallback estimate
MAX_GEOMETRY_POINTS = 150     # keeps tool results small


# ------------------------------------------------------------------ OSRM
def fetch_osrm(start_lat, start_lon, end_lat, end_lon, alternatives=False):
    """Asks OSRM for driving routes. Returns OSRM-style route dicts:
    {"distance": meters, "duration": seconds, "geometry": {"coordinates": [[lon, lat], ...]}}
    """
    url = f"{OSRM_URL}/route/v1/driving/{start_lon},{start_lat};{end_lon},{end_lat}"
    params = {
        "overview": "full",
        "geometries": "geojson",
        "alternatives": "true" if alternatives else "false",
    }
    response = httpx.get(url, params=params, timeout=8.0)
    response.raise_for_status()
    data = response.json()
    if data.get("code") != "Ok":
        raise RuntimeError(f"OSRM said: {data.get('code')}")
    return data["routes"]


# --------------------------------------------------------------- helpers
def _norm(text) -> str:
    return " ".join((text or "").lower().split())


def _check_latlon(lat, lon, label="point"):
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError(f"{label}: lat must be -90..90 and lon must be -180..180")


def _clamp(limit, default=3, high=10) -> int:
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        return default
    return max(1, min(limit, high))


def _densify(a, b, steps=50):
    return [
        (a[0] + (b[0] - a[0]) * i / steps, a[1] + (b[1] - a[1]) * i / steps)
        for i in range(steps + 1)
    ]


def _downsample(points):
    step = max(1, len(points) // MAX_GEOMETRY_POINTS)
    out = points[::step]
    if out[-1] != points[-1]:
        out.append(points[-1])
    return out


def _blocked_hits(points, blocked_roads):
    hits = []
    for road in blocked_roads:
        limit_km = road["radius_m"] / 1000.0
        if any(haversine_km(lat, lon, road["lat"], road["lon"]) <= limit_km
               for lat, lon in points):
            hits.append({"id": road["id"], "name": road["name"], "status": road["status"]})
    return hits


def _summarize_osrm_route(route, blocked_roads):
    points = [(lat, lon) for lon, lat in route["geometry"]["coordinates"]]
    return {
        "distance_km": round(route["distance"] / 1000.0, 2),
        "duration_min": round(route["duration"] / 60.0, 1),
        "blocked_by": _blocked_hits(points, blocked_roads),
        "geometry": [[round(p[0], 5), round(p[1], 5)] for p in _downsample(points)],
    }


# ------------------------------------------------- plain logic (testable)
def geocode_logic(conn, name, limit=5):
    wanted = _norm(name)
    if not wanted:
        raise ValueError("name must not be empty")
    rows = query(
        conn, "SELECT id, name, name_ur, kind, lat, lon, aliases FROM places ORDER BY id"
    )
    exact, partial = [], []
    for row in rows:
        row["aliases"] = parse_json_list(row["aliases"])
        names = [_norm(row["name"]), _norm(row["name_ur"])] + [_norm(a) for a in row["aliases"]]
        names = [n for n in names if n]
        if wanted in names:
            row["match"] = "exact"
            exact.append(row)
        elif any(wanted in n or (len(n) >= 3 and n in wanted) for n in names):
            row["match"] = "partial"
            partial.append(row)
    matches = (exact + partial)[:_clamp(limit, default=5, high=10)]
    return {
        "query": name,
        "found": bool(matches),
        "matches": matches,
        "source": "places table (simulated gazetteer)",
    }


def distance_logic(lat1, lon1, lat2, lon2):
    _check_latlon(lat1, lon1, "point 1")
    _check_latlon(lat2, lon2, "point 2")
    return {
        "distance_km": round(haversine_km(lat1, lon1, lat2, lon2), 2),
        "method": "straight_line",
        "note": "Straight-line distance, not road distance. Use get_route for roads.",
    }


def get_route_logic(conn, start_lat, start_lon, end_lat, end_lon, osrm_fn=fetch_osrm):
    """osrm_fn=None means: skip OSRM and give a straight-line estimate."""
    _check_latlon(start_lat, start_lon, "start")
    _check_latlon(end_lat, end_lon, "end")
    blocked_roads = query(
        conn, "SELECT id, name, lat, lon, radius_m, status FROM blocked_roads ORDER BY id"
    )

    routes, osrm_error = [], None
    if osrm_fn is not None:
        try:
            routes = osrm_fn(start_lat, start_lon, end_lat, end_lon, alternatives=True) or []
        except Exception as exc:  # noqa: BLE001 - any network/parse problem -> fallback
            osrm_error = f"{type(exc).__name__}: {exc}"

    if routes:
        summaries = [_summarize_osrm_route(r, blocked_roads) for r in routes]
        best_index = min(
            range(len(summaries)),
            key=lambda i: (
                sum(h["status"] == "blocked" for h in summaries[i]["blocked_by"]),
                len(summaries[i]["blocked_by"]),
                i,
            ),
        )
        best = summaries[best_index]
        source, checked, used_alt = "osrm", len(summaries), best_index != 0
        note = None
    else:
        line = _densify((start_lat, start_lon), (end_lat, end_lon))
        km = haversine_km(start_lat, start_lon, end_lat, end_lon)
        best = {
            "distance_km": round(km, 2),
            "duration_min": round(km / ASSUMED_SPEED_KMH * 60, 1),
            "blocked_by": _blocked_hits(line, blocked_roads),
            "geometry": [[round(p[0], 5), round(p[1], 5)] for p in (line[0], line[-1])],
        }
        source, checked, used_alt = "straight_line", 0, False
        note = ("Straight-line estimate only, not a real road route "
                "(OSRM disabled or unavailable).")

    blocked = any(h["status"] == "blocked" for h in best["blocked_by"])
    if blocked:
        note = ((note + " ") if note else "") + "Route passes a reported blocked road."
    elif used_alt:
        note = "Alternative route chosen to avoid a reported blocked road."

    return {
        "start": {"lat": start_lat, "lon": start_lon},
        "end": {"lat": end_lat, "lon": end_lon},
        "route_source": source,
        "distance_km": best["distance_km"],
        "duration_min": best["duration_min"],
        "blocked": blocked,
        "blocked_by": best["blocked_by"],
        "used_alternative": used_alt,
        "routes_checked": checked,
        "geometry": best["geometry"],
        "note": note,
        "osrm_error": osrm_error,
    }


def _attach_route(conn, row, lat, lon, osrm_fn):
    route = get_route_logic(conn, lat, lon, row["lat"], row["lon"], osrm_fn)
    row["distance_km"] = route["distance_km"]
    row["duration_min"] = route["duration_min"]
    row["route_source"] = route["route_source"]
    row["blocked"] = route["blocked"]
    row["blocked_by"] = route["blocked_by"]
    return row


def nearby_hospitals_logic(conn, lat, lon, limit=3, osrm_fn=fetch_osrm):
    _check_latlon(lat, lon)
    rows = query(
        conn,
        "SELECT id, name, lat, lon, available_beds, icu_available, emergency_open, "
        "status, specialties FROM hospitals WHERE status != 'closed' ORDER BY id",
    )
    for row in rows:
        row["emergency_open"] = bool(row["emergency_open"])
        row["specialties"] = parse_json_list(row["specialties"])
        row["straight_km"] = round(haversine_km(lat, lon, row["lat"], row["lon"]), 2)
    rows.sort(key=lambda r: r["straight_km"])
    rows = rows[:_clamp(limit)]
    for row in rows:  # only the closest few get a (slower) road route
        _attach_route(conn, row, lat, lon, osrm_fn)
    rows.sort(key=lambda r: r["duration_min"])
    return rows


def nearby_shelters_logic(conn, lat, lon, min_free=0, limit=3,
                          include_blocked=False, osrm_fn=fetch_osrm):
    _check_latlon(lat, lon)
    if min_free < 0:
        raise ValueError("min_free must be 0 or more")
    rows = query(
        conn,
        "SELECT id, name, lat, lon, capacity, current_occupancy, status, road_access "
        "FROM shelters WHERE status = 'open' ORDER BY id",
    )
    keep = []
    for row in rows:
        row["free_space"] = row["capacity"] - row["current_occupancy"]
        if row["free_space"] < min_free:
            continue
        if row["road_access"] == "blocked" and not include_blocked:
            continue
        row["straight_km"] = round(haversine_km(lat, lon, row["lat"], row["lon"]), 2)
        keep.append(row)
    keep.sort(key=lambda r: r["straight_km"])
    keep = keep[:_clamp(limit)]
    for row in keep:
        _attach_route(conn, row, lat, lon, osrm_fn)
    keep.sort(key=lambda r: r["duration_min"])
    return keep


# --------------------------------------------------------------- MCP tools
mcp = FastMCP("reliefmesh-mapping")


@mcp.tool()
def geocode_location(name: str) -> dict:
    """Find coordinates for a place name (English, Roman Urdu or Urdu).
    Uses the simulated gazetteer. Returns found=false if there is no match."""
    with connect() as conn:
        return geocode_logic(conn, name)


@mcp.tool()
def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> dict:
    """Straight-line distance in km between two points (not road distance)."""
    return distance_logic(lat1, lon1, lat2, lon2)


@mcp.tool()
def get_route(start_lat: float, start_lon: float, end_lat: float, end_lon: float,
              use_osrm: bool = True) -> dict:
    """Driving route with distance, time, blocked-road check and an alternative
    when one avoids a blocked road. use_osrm=false gives a straight-line estimate."""
    with connect() as conn:
        return get_route_logic(
            conn, start_lat, start_lon, end_lat, end_lon,
            fetch_osrm if use_osrm else None,
        )


@mcp.tool()
def find_nearby_hospitals(lat: float, lon: float, limit: int = 3,
                          use_osrm: bool = True) -> list[dict]:
    """Nearest hospitals that are not closed, fastest route first, with
    available beds and ICU beds."""
    with connect() as conn:
        return nearby_hospitals_logic(
            conn, lat, lon, limit, fetch_osrm if use_osrm else None
        )


@mcp.tool()
def find_nearby_shelters(lat: float, lon: float, min_free: int = 0, limit: int = 3,
                         include_blocked: bool = False,
                         use_osrm: bool = True) -> list[dict]:
    """Nearest open shelters with at least min_free free places, fastest route
    first. Shelters whose road access is blocked are skipped unless
    include_blocked=true."""
    with connect() as conn:
        return nearby_shelters_logic(
            conn, lat, lon, min_free, limit, include_blocked,
            fetch_osrm if use_osrm else None,
        )


if __name__ == "__main__":
    mcp.run()  # stdio transport