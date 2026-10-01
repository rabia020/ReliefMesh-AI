"""Prints the Resource Agent's recommendation for every incident currently in
the database (Phase 11). No LLM calls, no network — pure arithmetic, so this
runs instantly and costs nothing.

Run from the project root:  python scripts/run_resource_demo.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agents.resource_agent import recommend_for_incident  # noqa: E402
from database.connection import get_connection  # noqa: E402
from database.queries import get_incident, list_incidents, list_resources, list_shelters  # noqa: E402


def main() -> int:
    conn = get_connection()
    try:
        incidents = list_incidents(conn)
        if not incidents:
            print("No incidents found. Run 'python scripts/init_db.py' first.")
            return 1
        resources = list_resources(conn)
        shelters = list_shelters(conn)

        for inc in incidents:
            full = get_incident(conn, inc["id"])
            print(f"\n{'=' * 70}\n{inc['id']}: {inc['title']}  [{inc['priority']}]")
            rec = recommend_for_incident(full, resources, shelters)
            if not rec:
                print("  (no resources required)")
                continue
            for need, info in rec.items():
                if not info["supported"]:
                    print(f"  {need}: NOT SUPPORTED - {info['message']}")
                    continue
                candidates = info["candidates"]
                if not candidates:
                    print(f"  {need}: no candidates in inventory")
                    continue
                best = candidates[0]
                if "distance_km" in best and "suitability_score" in best:
                    print(f"  {need}: best = {best['name']} "
                          f"({best['distance_km']} km, available={best['available']}, "
                          f"score={best['suitability_score']})")
                else:  # shelter candidate
                    print(f"  {need}: best = {best['name']} "
                          f"({best['distance_km']} km, has_room={best['has_room']})")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())