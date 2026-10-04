"""Live Map endpoints: /map/data and /map/route (read-only, SIMULATED data)."""
import json

from fastapi import APIRouter, Depends, HTTPException

from mcp_servers.mapping_server import fetch_osrm, get_route_logic

DISCLAIMER = "SIMULATED data. Decision support only."


def _rows(conn, sql, params=()):
    cursor = conn.execute(sql, params)
    columns = [c[0] for c in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _has_location(row) -> bool:
    lat, lon = row["lat"], row["lon"]
    return lat is not None and lon is not None and not (lat == 0 and lon == 0)


def build_map_data(conn) -> dict:
    incidents = _rows(
        conn,
        "SELECT id, title, priority, estimated_affected, vulnerable_people, medical_emergency, "
        "evidence_confidence, status, location_name, lat, lon FROM incidents ORDER BY id",
    )
    located = [i for i in incidents if _has_location(i)]
    for incident in located:
        incident["medical_emergency"] = bool(incident["medical_emergency"])

    resources = _rows(
        conn,
        "SELECT id, name, type, status, lat, lon, crew_size, capacity_people, current_assignment "
        "FROM resources ORDER BY id",
    )
    shelters = _rows(
        conn,
        "SELECT id, name, lat, lon, capacity, current_occupancy, status, road_access "
        "FROM shelters ORDER BY id",
    )
    for shelter in shelters:
        shelter["free_space"] = shelter["capacity"] - shelter["current_occupancy"]
    hospitals = _rows(
        conn,
        "SELECT id, name, lat, lon, available_beds, icu_available, emergency_open, status "
        "FROM hospitals ORDER BY id",
    )
    for hospital in hospitals:
        hospital["emergency_open"] = bool(hospital["emergency_open"])
    blocked = _rows(
        conn, "SELECT id, name, lat, lon, radius_m, status, reason FROM blocked_roads ORDER BY id"
    )

    by_resource = {r["id"]: r for r in resources}
    by_incident = {i["id"]: i for i in located}
    dispatches = []
    actions = _rows(
        conn,
        "SELECT id, incident_id, resource_ids, status FROM actions "
        "WHERE status IN ('proposed', 'info_requested', 'executed') ORDER BY id",
    )
    for action in actions:
        incident = by_incident.get(action["incident_id"])
        if not incident:
            continue
        try:
            resource_ids = json.loads(action["resource_ids"] or "[]")
        except (TypeError, ValueError):
            resource_ids = []
        for resource_id in resource_ids:
            resource = by_resource.get(resource_id)
            if not resource:
                continue
            dispatches.append({
                "action_id": action["id"], "status": action["status"],
                "incident_id": incident["id"],
                "resource_id": resource_id, "resource_name": resource["name"],
                "from": {"lat": resource["lat"], "lon": resource["lon"]},
                "to": {"lat": incident["lat"], "lon": incident["lon"]},
            })

    return {
        "incidents": located,
        "incidents_without_location": len(incidents) - len(located),
        "resources": resources, "shelters": shelters, "hospitals": hospitals,
        "blocked_roads": blocked, "dispatches": dispatches,
        "disclaimer": DISCLAIMER,
    }


def build_map_router(get_db) -> APIRouter:
    router = APIRouter(prefix="/map", tags=["map"])

    @router.get("/data")
    def data(conn=Depends(get_db)):
        return build_map_data(conn)

    @router.get("/route")
    def route(start_lat: float, start_lon: float, end_lat: float, end_lon: float,
              use_osrm: bool = True, conn=Depends(get_db)):
        try:
            return get_route_logic(conn, start_lat, start_lon, end_lat, end_lon,
                                   fetch_osrm if use_osrm else None)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error))

    return router