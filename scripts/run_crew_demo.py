"""Runs the Phase 13 crew on injected demo reports (real LLM + OSRM).

Usage (from project root, venv active):

    python scripts/init_db.py
    python -c "from database.connection import get_connection; from database.queries import inject_demo_reports; c=get_connection(); inject_demo_reports(c); c.close()"
    python scripts/run_crew_demo.py

This costs API quota. Automated tests (pytest) do not call this script.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agents.crew import describe_crew  # noqa: E402
from agents.supervisor import run_received_reports  # noqa: E402
from database.connection import get_connection  # noqa: E402
from database.queries import inject_demo_reports, list_reports  # noqa: E402


def main() -> int:
    print("ReliefMesh AI - Phase 13 CrewAI supervisor demo")
    print("=" * 70)
    crew = describe_crew()
    print("Framework:", crew["framework"])
    print("Sequence: ", " → ".join(crew["sequence"]))
    print("Safety:   ", crew["safety"])
    print("=" * 70)

    conn = get_connection()
    try:
        if not list_reports(conn, status="received"):
            injected = inject_demo_reports(conn)
            print(f"Injected {len(injected)} queued demo reports: {injected}")
        result = run_received_reports(conn, persist=True, verbose=True)
        print(f"\nClusters: {len(result['clusters'])}")
        for cluster in result["clusters"]:
            inc = cluster["incident"]
            print(f"\n--- {inc['id']} [{inc['priority']}] conf={inc['evidence_confidence']}% ---")
            print(f"Title:    {inc['title']}")
            print(f"Type:     {inc['incident_type']}")
            print(f"Location: {inc.get('location_name')} ({inc.get('lat')}, {inc.get('lon')})")
            print(f"Affected: {inc['estimated_affected']}  vulnerable={inc['vulnerable_people']}")
            print(f"Medical:  {inc['medical_emergency']}")
            print(f"Needs:    {inc['required_resources']}")
            print(f"Summary:  {inc.get('summary')}")
            proposal = cluster["proposed_action"]
            if proposal:
                print(f"PROPOSED: {proposal['title']}")
                print(proposal["reason"])
                print("(status=proposed — not dispatched)")
            else:
                print("PROPOSED: none")
            routing = cluster["routing"]
            print(f"Routing skipped: {routing.get('skipped')}  hospitals skipped: {routing.get('hospital_skipped')}")
        print("\n" + result["disclaimer"])
        print("\nJSON trace:")
        print(json.dumps(result["trace"], indent=2))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
