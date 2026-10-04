"""Runs the real Routing Agent (real calls to the public OSRM demo server)
for a few representative incidents: a real road route, a route that should
hit a known blocked road, and nearest-shelter/nearest-hospital lookups.

Needs internet access to router.project-osrm.org. If that server is slow or
briefly down, every result below should still print, just labeled
source='estimated' instead of source='osrm' — that fallback is the point.

Run from the project root:  python scripts/run_routing_demo.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agents.routing_agent import find_route, nearest_hospital, nearest_shelter  # noqa: E402
from database.connection import get_connection  # noqa: E402
from database.queries import get_incident, list_hospitals, list_shelters  # noqa: E402


def _print_route(label, route):
    print(f"\n{label}")
    print(f"  source:           {route['source']}")
    print(f"  distance_km:      {route['distance_km']}")
    print(f"  duration_min:     {route['duration_min']}")
    print(f"  used_alternative: {route['used_alternative']}")
    print(f"  blocked_by:       {[b['id'] for b in route['blocked_by']]}")
    if route.get("note"):
        print(f"  note:             {route['note']}")


def main() -> int:
    conn = get_connection()
    try:
        blocked_roads = conn.execute("SELECT * FROM blocked_roads").fetchall()
        blocked_roads = [dict(b) for b in blocked_roads]

        bridge = get_incident(conn, "INC-005") or get_incident(conn, "INC-002")
        if bridge is None:
            print("No incidents found. Run 'python scripts/init_db.py' first.")
            return 1

        print("=" * 70)
        print("1) A real route near the bridge (check it against known blocked roads)")
        route = find_route(bridge["lat"], bridge["lon"], 34.0105, 71.9800, blocked_roads)
        _print_route(f"{bridge['id']} -> Kabul River Bridge", route)

        print("\n" + "=" * 70)
        print("2) A route that should hit BR-02 (Tehsil Road Underpass, reported blocked)")
        route2 = find_route(34.0230, 71.9780, 34.0110, 71.9810, blocked_roads)
        _print_route("Railway Colony -> Boat Launch East (crosses the underpass)", route2)

        print("\n" + "=" * 70)
        print("3) Nearest open shelter with room, from the bridge incident")
        shelters = list_shelters(conn)
        shelter_hits = nearest_shelter(bridge["lat"], bridge["lon"], shelters,
                                       blocked_roads, require_room_for=bridge["estimated_affected"])
        for s in shelter_hits:
            print(f"  {s['name']:35s} {s['distance_km']:6.2f} km  {s['duration_min']:5.1f} min  "
                  f"source={s['route_source']}")

        print("\n" + "=" * 70)
        print("4) Nearest hospital with dialysis, from the Gujjar incident")
        gujjar = get_incident(conn, "INC-003")
        hospitals = list_hospitals(conn)
        hosp_hits = nearest_hospital(gujjar["lat"], gujjar["lon"], hospitals,
                                     blocked_roads, require_specialty="dialysis")
        for h in hosp_hits:
            print(f"  {h['name']:35s} {h['distance_km']:6.2f} km  {h['duration_min']:5.1f} min  "
                  f"source={h['route_source']}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())