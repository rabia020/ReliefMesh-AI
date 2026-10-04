"""Phase 15 demo: use the Incident MCP and Resource MCP servers together.
Run from the project root:  python -m mcp_servers.client_demo_resource
"""
import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from mcp_servers.client_utils import unpack

ROOT = Path(__file__).resolve().parents[1]


def server(module):
    return StdioServerParameters(
        command=sys.executable, args=["-m", module], cwd=str(ROOT)
    )


async def main():
    # Step 1: ask the Incident MCP server for the most urgent incident.
    async with stdio_client(server("mcp_servers.incident_server")) as (r, w):
        async with ClientSession(r, w) as session:
            await session.initialize()
            critical = unpack(await session.call_tool("get_critical_incidents", {}))
    top = critical[0]
    print(f"TOP CRITICAL: {top['id']} | {top['title']}")

    # Step 2: ask the Resource MCP server what is available near it.
    async with stdio_client(server("mcp_servers.resource_server")) as (r, w):
        async with ClientSession(r, w) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("\nTOOLS:", [t.name for t in tools.tools])

            point = {"near_lat": top["lat"], "near_lon": top["lon"]}

            boats = unpack(await session.call_tool("get_available_boats", point))
            print(f"\nAVAILABLE BOATS NEAR {top['id']}:")
            for b in boats:
                print(f"  {b['id']} | {b['name']} | {b['distance_km']} km | crew {b['crew_size']}")

            teams = unpack(await session.call_tool("get_available_teams", point))
            print("\nAVAILABLE TEAMS:")
            for t in teams:
                print(f"  {t['id']} | {t['name']} | {t['type']} | {t['distance_km']} km")

            amb = unpack(await session.call_tool("get_available_ambulances", point))
            print("\nAVAILABLE AMBULANCES:", [(a["name"], a["distance_km"]) for a in amb])

            shelters = unpack(await session.call_tool("get_shelters", {"min_free": 30}))
            print("\nSHELTERS THAT CAN TAKE 30 PEOPLE:")
            for s in shelters:
                print(f"  {s['name']} | free {s['free_space']} | road {s['road_access']}")

            cap = unpack(await session.call_tool("get_shelter_capacity", {}), single=True)
            print(f"\nSHELTER TOTALS: capacity {cap['total_capacity']}, "
                  f"occupied {cap['occupied']}, free {cap['free_space']}")

            hosp = unpack(await session.call_tool("get_hospital_capacity", {}), single=True)
            print(f"HOSPITAL TOTALS: beds free {hosp['available_beds']}, "
                  f"ICU free {hosp['icu_available']}")


asyncio.run(main())