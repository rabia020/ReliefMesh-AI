"""Resource Agent (Phase 11).

For ONE incident, recommends which available resources (rescue teams, boats,
ambulances, medical teams) and, if needed, which shelter, best match its
required_resources — ranked by availability, distance, and capacity.
Deterministic: no LLM calls, same input always gives the same ranking.

Cross-incident allocation of SCARCE resources (e.g. deciding which of five
Critical incidents gets the only two available boats) is Phase 19's job
(OR-Tools optimization). This agent answers the simpler, per-incident
question: "if we send help to just this one incident, what's the best
resource for each of its needs?" — Phase 19 will consume these rankings.
"""

import math

from dataset.constants import RESOURCE_TYPES

SHELTER_NEED = "shelter"
# Needs with no matching resource type in this scenario's inventory at all.
# Listed explicitly so the agent reports this honestly, rather than silently
# finding nothing and looking like a bug.
UNSUPPORTED_NEEDS = {"relief_supplies", "utility_crew", "engineering_team",
                     "search_team", "dewatering_pump"}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Straight-line distance in kilometers. Real road distance comes from
    the Routing Agent / OSRM in Phase 12; this is a fast, dependency-free
    stand-in, good enough to rank nearby candidates in the meantime."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _capability_bonus(incident: dict, resource: dict) -> float:
    """A small, explainable nudge toward a better-suited resource when two
    candidates are otherwise similar. Never large enough to override
    availability or outweigh a large distance difference on its own."""
    caps = resource.get("capabilities", [])
    bonus = 0.0
    if incident.get("medical_emergency") and incident.get("vulnerable_people", 0) > 0:
        if "maternity_transport" in caps or "maternity_support" in caps:
            bonus += 0.15
    if incident.get("isolation", 0) >= 2 and "water_rescue" in caps:
        bonus += 0.10
    return bonus


def rank_resources(incident: dict, candidates: list[dict]) -> list[dict]:

        # No coordinates -> we cannot measure distance, so we cannot rank by distance.
    if incident.get("lat") is None or incident.get("lon") is None:
        return []


    """candidates: resources of ONE type (already filtered by caller). Returns
    them annotated with distance_km, suitability_score, and sorted
    best-first. Unavailable resources are kept (for visibility, so a
    coordinator can see "Rescue Team C exists but is deployed elsewhere")
    but always rank below every available one."""
    ranked = []
    for r in candidates:
        distance = haversine_km(incident["lat"], incident["lon"], r["lat"], r["lon"])
        available = r["status"] == "available"
        distance_score = max(0.0, 1 - distance / 20)       # 20 km treated as "effectively far"
        capacity_score = min(
            r.get("capacity_people", 0) / max(incident.get("estimated_affected", 1), 1), 1.0)
        suitability = (0.5 * distance_score + 0.3 * capacity_score
                       + _capability_bonus(incident, r)) if available else 0.0
        ranked.append({**r, "distance_km": round(distance, 2),
                       "suitability_score": round(suitability, 3), "available": available})
    ranked.sort(key=lambda r: (not r["available"], -r["suitability_score"], r["distance_km"]))
    return ranked


def recommend_for_incident(incident: dict, resources: list[dict], shelters: list[dict]) -> dict:
    """incident needs: lat, lon, required_resources, estimated_affected,
    medical_emergency, vulnerable_people, isolation.
    resources: all rows from database.queries.list_resources().
    shelters: all rows from database.queries.list_shelters().

    Returns one entry per required_resources need:
    {"supported": True, "candidates": [...]} or
    {"supported": False, "message": "..."} for a need with nothing in
    inventory to match it.
    """
    by_type: dict = {}
    for r in resources:
        by_type.setdefault(r["type"], []).append(r)

    result = {}
    for need in incident.get("required_resources", []):
        if need in RESOURCE_TYPES:
            result[need] = {"supported": True, "candidates": rank_resources(incident, by_type.get(need, []))}
        elif need == SHELTER_NEED:
            open_shelters = [s for s in shelters if s["status"] == "open"]
            ranked = sorted(
                open_shelters,
                key=lambda s: (
                    (s["capacity"] - s["current_occupancy"]) < incident.get("estimated_affected", 0),
                    haversine_km(incident["lat"], incident["lon"], s["lat"], s["lon"]),
                ),
            )
            candidates = [
                {**s, "distance_km": round(
                    haversine_km(incident["lat"], incident["lon"], s["lat"], s["lon"]), 2),
                 "has_room": (s["capacity"] - s["current_occupancy"]) >= incident.get("estimated_affected", 0)}
                for s in ranked
            ]
            result[need] = {"supported": True, "candidates": candidates}
        elif need in UNSUPPORTED_NEEDS:
            result[need] = {"supported": False,
                            "message": f"No '{need}' resource type exists in the current inventory."}
        else:
            result[need] = {"supported": False, "message": f"Unknown resource need '{need}'."}
    return result