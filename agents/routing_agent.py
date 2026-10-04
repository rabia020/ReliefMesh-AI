"""Routing Agent (Phase 12).

Uses OSRM (the free public demo router at router.project-osrm.org, since your
coordinates sit in a real part of the world) to compute real road routes,
detect when a route passes through a reported blocked road, and find the
nearest reachable shelter or hospital.

The public OSRM demo server is a free, best-effort service, not meant for
heavy production traffic, and can be slow or briefly unavailable. Every
function here falls back to a straight-line (haversine) estimate, clearly
labeled as such, if OSRM cannot be reached — so the system stays usable, and
a live demo never breaks because of an external service, even though it
loses real-road accuracy in that moment.
"""

import requests

from agents.resource_agent import haversine_km
from backend import config

PROFILE = "driving"


class RoutingError(Exception):
    pass


def _osrm_url(start_lat, start_lon, end_lat, end_lon, alternatives=False) -> str:
    coords = f"{start_lon},{start_lat};{end_lon},{end_lat}"
    alt = "true" if alternatives else "false"
    return (f"{config.OSRM_BASE_URL}/route/v1/{PROFILE}/{coords}"
            f"?overview=full&geometries=geojson&alternatives={alt}")


def call_osrm(start_lat, start_lon, end_lat, end_lon, alternatives=False) -> list:
    """Returns OSRM's raw list of route dicts. Raises RoutingError on any
    failure — network, timeout, or a non-'Ok' OSRM response."""
    url = _osrm_url(start_lat, start_lon, end_lat, end_lon, alternatives)
    try:
        response = requests.get(url, timeout=config.OSRM_TIMEOUT_SECONDS)
        response.raise_for_status()
        body = response.json()
    except requests.exceptions.RequestException as error:
        raise RoutingError(f"Could not reach OSRM: {error}") from error
    if body.get("code") != "Ok":
        raise RoutingError(f"OSRM returned: {body.get('code')} - {body.get('message', '')}")
    return body["routes"]


def _route_from_osrm_route(route: dict) -> dict:
    coords = route["geometry"]["coordinates"]            # OSRM gives [lon, lat] pairs
    return {
        "distance_km": round(route["distance"] / 1000, 2),
        "duration_min": round(route["duration"] / 60, 1),
        "geometry": [[lat, lon] for lon, lat in coords],  # normalized to [lat, lon]
        "source": "osrm",
    }


def _straight_line_route(start_lat, start_lon, end_lat, end_lon) -> dict:
    distance = haversine_km(start_lat, start_lon, end_lat, end_lon)
    return {
        "distance_km": round(distance, 2),
        "duration_min": round(distance / 30 * 60, 1),     # a rough 30 km/h assumption
        "geometry": [[start_lat, start_lon], [end_lat, end_lon]],
        "source": "estimated",
    }


def _blocks_route(geometry: list, blocked_roads: list) -> list:
    """Returns the blocked_roads entries whose reported point lies within its
    radius of ANY point along the route's geometry."""
    hits = []
    for block in blocked_roads:
        if block["status"] not in ("blocked", "partial"):
            continue
        for lat, lon in geometry:
            if haversine_km(lat, lon, block["lat"], block["lon"]) * 1000 <= block["radius_m"]:
                hits.append(block)
                break
    return hits


def find_route(start_lat: float, start_lon: float, end_lat: float, end_lon: float,
               blocked_roads: list, call_osrm_fn=None) -> dict:
    """Finds a route from start to end, checks it against known blocked
    roads, and tries an alternative route if the primary one is blocked.

    call_osrm_fn: inject a fake in tests; defaults to the real call_osrm().

    Returns a dict with distance_km, duration_min, geometry, source
    ("osrm" or "estimated"), blocked_by (list of blocked_roads entries the
    chosen route still passes through, empty if clear), used_alternative
    (bool), and an optional "note" explaining anything unusual.
    """
    osrm = call_osrm_fn or call_osrm
    try:
        raw_routes = osrm(start_lat, start_lon, end_lat, end_lon, alternatives=True)
    except RoutingError as error:
        route = _straight_line_route(start_lat, start_lon, end_lat, end_lon)
        route["blocked_by"] = []
        route["used_alternative"] = False
        route["note"] = f"OSRM unavailable ({error}); showing a straight-line estimate, not a real road route."
        return route

    candidates = [_route_from_osrm_route(r) for r in raw_routes]
    for i, candidate in enumerate(candidates):
        blocks = _blocks_route(candidate["geometry"], blocked_roads)
        if not blocks:
            candidate["blocked_by"] = []
            candidate["used_alternative"] = i > 0
            return candidate

    # Every candidate passes through something blocked. Return the shortest
    # one anyway — a partially-blocked route is still useful information for
    # a human coordinator to see and act on, not something to hide.
    best = min(candidates, key=lambda r: r["distance_km"])
    best["blocked_by"] = _blocks_route(best["geometry"], blocked_roads)
    best["used_alternative"] = False
    best["note"] = "All available routes pass through a reported blocked road."
    return best


def _nearest_of(lat: float, lon: float, places: list, blocked_roads: list,
                top_n_to_route: int = 3, call_osrm_fn=None) -> list:
    """Pre-ranks candidates by straight-line distance (free, no network), then
    asks OSRM for a real route only for the closest few, to be considerate of
    the free public OSRM server rather than routing every candidate."""
    prelim = sorted(places, key=lambda p: haversine_km(lat, lon, p["lat"], p["lon"]))
    shortlist = prelim[:top_n_to_route]
    results = []
    for place in shortlist:
        route = find_route(lat, lon, place["lat"], place["lon"], blocked_roads, call_osrm_fn=call_osrm_fn)
        results.append({**place, "distance_km": route["distance_km"], "duration_min": route["duration_min"],
                        "route_source": route["source"], "blocked_by": route["blocked_by"]})
    results.sort(key=lambda r: r["distance_km"])
    return results


def nearest_shelter(lat: float, lon: float, shelters: list, blocked_roads: list = (),
                    require_room_for: int = 0, call_osrm_fn=None) -> list:
    candidates = [s for s in shelters if s["status"] == "open"
                  and (s["capacity"] - s["current_occupancy"]) >= require_room_for]
    return _nearest_of(lat, lon, candidates, list(blocked_roads), call_osrm_fn=call_osrm_fn)


def nearest_hospital(lat: float, lon: float, hospitals: list, blocked_roads: list = (),
                     require_specialty: str = None, call_osrm_fn=None) -> list:
    candidates = [h for h in hospitals if h["status"] in ("operational", "limited")
                  and h.get("emergency_open", True)]
    if require_specialty:
        candidates = [h for h in candidates if require_specialty in h.get("specialties", [])]
    return _nearest_of(lat, lon, candidates, list(blocked_roads), call_osrm_fn=call_osrm_fn)