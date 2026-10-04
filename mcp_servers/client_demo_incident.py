"""Phase 14 demo: talk to the Incident MCP server like an agent would.
Run from the project root:  python -m mcp_servers.client_demo_incident
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
        command=sys.executable,
        args=["-m", "mcp_servers.incident_server"],
        cwd=str(ROOT),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("TOOLS:", [t.name for t in tools.tools])

            result = await session.call_tool("get_critical_incidents", {})
            critical = unpack(result)
            print(f"\nCRITICAL INCIDENTS: {len(critical)}")
            for inc in critical:
                score = inc["priority_score"] if inc["priority_score"] is not None else "n/a"
                print(f"  {inc['id']} | {inc['title']} | score {score} "
                      f"| confidence {inc['evidence_confidence']}%")

            top = critical[0]
            result = await session.call_tool("get_incident", {"incident_id": top["id"]})
            detail = unpack(result, single=True)
            print(f"\nDETAIL {detail['id']}: {len(detail['reports'])} linked reports")

            result = await session.call_tool(
                "get_nearby_incidents",
                {"lat": top["lat"], "lon": top["lon"], "radius_km": 3},
            )
            near = unpack(result)
            print(f"\nWITHIN 3 KM OF {top['id']}: {[n['id'] for n in near]}")

            word = top["title"].split()[0]
            result = await session.call_tool("search_incidents", {"query": word})
            print(f"\nSEARCH '{word}':", [i["id"] for i in unpack(result)])

            result = await session.call_tool("get_incident", {"incident_id": "INC-999"})
            print("\nMISSING INCIDENT:", unpack(result, single=True))


asyncio.run(main())