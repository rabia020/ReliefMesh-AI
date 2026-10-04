"""Phase 15: Resource MCP Server (READ-ONLY, SIMULATED data).

Tools: get_available_teams, get_available_boats, get_available_ambulances,
       get_shelters, get_shelter_capacity, get_hospital_capacity.
"""
from mcp.server.fastmcp import FastMCP

from mcp_servers.common import connect, haversine_km, parse_json_list, query

RESOURCE_COLUMNS = (
    "id, name, type, status, base, lat, lon, crew_size, capacity_people, "
    "capabilities, current_assignment"
)
SHELTER_COLUMNS = (
    "id, name, lat, lon, capacity, current_occupancy, status, road_access, "
    "facilities, notes"
)
HOSPITAL_COLUMNS = (
    "id, name, lat, lon, total_beds, available_beds, icu_total, icu_available, "
    "emergency_open, status, specialties, notes"
)


# ------------------------------------------------- plain logic (testable)
def _check_point(lat, lon):
    if (lat is None) != (lon is None):
        raise ValueError("give both near_lat and near_lon, or neither")
    if lat is not None and not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("lat must be -90..90 and lon must be -180..180")


def available_resources_logic(conn, types, near_lat=None, near_lon=None):
    """Resources with status 'available' of the given types.
    With a point, adds distance_km and sorts nearest first."""
    _check_point(near_lat, near_lon)
    marks = ",".join("?" for _ in types)
    rows = query(
        conn,
        f"SELECT {RESOURCE_COLUMNS} FROM resources "
        f"WHERE status = 'available' AND type IN ({marks}) ORDER BY id",
        tuple(types),
    )
    for row in rows:
        row["capabilities"] = parse_json_list(row["capabilities"])
        if near_lat is not None:
            row["distance_km"] = round(
                haversine_km(near_lat, near_lon, row["lat"], row["lon"]), 2
            )
    if near_lat is not None:
        rows.sort(key=lambda r: r["distance_km"])
    return rows


def shelters_logic(conn, min_free=0, include_closed=False):
    if min_free < 0:
        raise ValueError("min_free must be 0 or more")
    rows = query(conn, f"SELECT {SHELTER_COLUMNS} FROM shelters ORDER BY id")
    out = []
    for row in rows:
        row["free_space"] = row["capacity"] - row["current_occupancy"]
        row["facilities"] = parse_json_list(row["facilities"])
        if not include_closed and row["status"] != "open":
            continue
        if row["free_space"] < min_free:
            continue
        out.append(row)
    out.sort(key=lambda r: (-r["free_space"], r["id"]))
    return out


def shelter_capacity_logic(conn):
    """Totals count OPEN shelters only (a closed shelter has no usable space)."""
    rows = shelters_logic(conn, include_closed=True)
    open_rows = [r for r in rows if r["status"] == "open"]
    return {
        "shelters_total": len(rows),
        "shelters_open": len(open_rows),
        "total_capacity": sum(r["capacity"] for r in open_rows),
        "occupied": sum(r["current_occupancy"] for r in open_rows),
        "free_space": sum(r["free_space"] for r in open_rows),
        "per_shelter": [
            {
                "id": r["id"], "name": r["name"], "capacity": r["capacity"],
                "current_occupancy": r["current_occupancy"],
                "free_space": r["free_space"], "status": r["status"],
                "road_access": r["road_access"],
            }
            for r in rows
        ],
    }


def hospital_capacity_logic(conn):
    """Totals count hospitals that are not 'closed'."""
    rows = query(conn, f"SELECT {HOSPITAL_COLUMNS} FROM hospitals ORDER BY id")
    for row in rows:
        row["specialties"] = parse_json_list(row["specialties"])
        row["emergency_open"] = bool(row["emergency_open"])
    usable = [r for r in rows if r["status"] != "closed"]
    return {
        "hospitals_total": len(rows),
        "hospitals_usable": len(usable),
        "total_beds": sum(r["total_beds"] for r in usable),
        "available_beds": sum(r["available_beds"] for r in usable),
        "icu_total": sum(r["icu_total"] for r in usable),
        "icu_available": sum(r["icu_available"] for r in usable),
        "per_hospital": rows,
    }


# --------------------------------------------------------------- MCP tools
mcp = FastMCP("reliefmesh-resources")


@mcp.tool()
def get_available_teams(near_lat: float | None = None,
                        near_lon: float | None = None) -> list[dict]:
    """List available rescue teams and medical teams. Give near_lat and
    near_lon to sort nearest first (straight-line distance_km)."""
    with connect() as conn:
        return available_resources_logic(
            conn, ("rescue_team", "medical_team"), near_lat, near_lon
        )


@mcp.tool()
def get_available_boats(near_lat: float | None = None,
                        near_lon: float | None = None) -> list[dict]:
    """List available rescue boats. Give near_lat and near_lon to sort
    nearest first (straight-line distance_km)."""
    with connect() as conn:
        return available_resources_logic(conn, ("boat",), near_lat, near_lon)


@mcp.tool()
def get_available_ambulances(near_lat: float | None = None,
                             near_lon: float | None = None) -> list[dict]:
    """List available ambulances. Give near_lat and near_lon to sort
    nearest first (straight-line distance_km)."""
    with connect() as conn:
        return available_resources_logic(conn, ("ambulance",), near_lat, near_lon)


@mcp.tool()
def get_shelters(min_free: int = 0, include_closed: bool = False) -> list[dict]:
    """List shelters with free_space and road_access, most free space first.
    Use min_free=30 to find shelters that can take 30 more people."""
    with connect() as conn:
        return shelters_logic(conn, min_free, include_closed)


@mcp.tool()
def get_shelter_capacity() -> dict:
    """Total shelter capacity, occupancy and free space (open shelters),
    plus a per-shelter breakdown."""
    with connect() as conn:
        return shelter_capacity_logic(conn)


@mcp.tool()
def get_hospital_capacity() -> dict:
    """Total hospital beds and ICU beds available (hospitals not closed),
    plus a per-hospital breakdown."""
    with connect() as conn:
        return hospital_capacity_logic(conn)


if __name__ == "__main__":
    mcp.run()  # stdio transport