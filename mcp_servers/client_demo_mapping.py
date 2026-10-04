"""Phase 16 demo: geocode a place, then find hospitals, shelters and a route.
Run from the project root:  python -m mcp_servers.client_demo_mapping
Needs internet for real OSRM routes; without it you get a clear fallback.
"""
import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from mcp_servers.client_utils import unpack

ROOT = Path(__file__).resolve().parents[1]


async def main():
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "mcp_servers.mapping_server"], cwd=str(ROOT)
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("TOOLS:", [t.name for t in tools.tools])

            geo = unpack(await session.call_tool(
                "geocode_location", {"name": "Kabul River Bridge"}), single=True)
            print(f"\nGEOCODE: found={geo['found']}")
            place = geo["matches"][0]
            print(f"  {place['id']} | {place['name']} | {place['lat']}, {place['lon']} "
                  f"| {place['match']}")
            here = {"lat": place["lat"], "lon": place["lon"]}

            hospitals = unpack(await session.call_tool(
                "find_nearby_hospitals", {**here, "limit": 2}))
            print("\nNEAREST HOSPITALS:")
            for h in hospitals:
                print(f"  {h['name']} | {h['distance_km']} km | {h['duration_min']} min "
                      f"| {h['route_source']} | beds {h['available_beds']} "
                      f"| ICU {h['icu_available']}")

            shelters = unpack(await session.call_tool(
                "find_nearby_shelters", {**here, "min_free": 30, "limit": 2}))
            print("\nNEAREST SHELTERS WITH 30+ FREE PLACES:")
            for s in shelters:
                print(f"  {s['name']} | free {s['free_space']} | {s['distance_km']} km "
                      f"| {s['duration_min']} min | {s['route_source']} "
                      f"| blocked={s['blocked']}")

            target = shelters[0]
            route = unpack(await session.call_tool("get_route", {
                "start_lat": place["lat"], "start_lon": place["lon"],
                "end_lat": target["lat"], "end_lon": target["lon"],
            }), single=True)
            print(f"\nROUTE TO {target['name']}:")
            print(f"  source={route['route_source']} | {route['distance_km']} km | "
                  f"{route['duration_min']} min | points={len(route['geometry'])}")
            print(f"  blocked={route['blocked']} | alternative_used={route['used_alternative']}")
            print(f"  note={route['note']} | osrm_error={route['osrm_error']}")

            dist = unpack(await session.call_tool("calculate_distance", {
                "lat1": place["lat"], "lon1": place["lon"],
                "lat2": target["lat"], "lon2": target["lon"],
            }), single=True)
            print(f"\nSTRAIGHT-LINE DISTANCE: {dist['distance_km']} km ({dist['method']})")

            nothing = unpack(await session.call_tool(
                "geocode_location", {"name": "Atlantis"}), single=True)
            print(f"\nUNKNOWN PLACE: found={nothing['found']}, matches={nothing['matches']}")


asyncio.run(main())