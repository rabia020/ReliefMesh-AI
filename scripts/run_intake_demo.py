"""Runs the real Intake Agent (real Gemini calls) over the queued demo reports.

This is a manual, human-eyeball check, not part of the automated test suite,
since it costs real API quota and its output depends on the live model.

Run from the project root:  python scripts/run_intake_demo.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agents.intake_agent import run_intake  # noqa: E402
from database.connection import get_connection  # noqa: E402
from database.queries import list_reports  # noqa: E402


def main() -> int:
    conn = get_connection()
    try:
        reports = list_reports(conn, status="queued")
        if not reports:
            reports = list_reports(conn, status="received")
        if not reports:
            print("No queued or received reports found. Run 'python scripts/init_db.py' first,")
            print("or use the dashboard's 'Reset demo data' button, then try again.")
            return 1

        print(f"ReliefMesh AI - Phase 7 Intake Agent demo ({len(reports)} reports)")
        print("=" * 70)
        for report in reports:
            print(f"\n--- {report['id']} [{report['language']}] {report['source_type']} ---")
            print(f"Text: {report['text'][:100]}{'...' if len(report['text']) > 100 else ''}")
            result = run_intake(report, conn=conn)
            print(f"  incident_type:       {result['incident_type']}")
            print(f"  location_text:       {result['location_text']!r}  "
                  f"-> place_id: {result['place_id']} ({result['place_match_confidence']})")
            print(f"  estimated_affected:  {result['estimated_affected']}")
            print(f"  vulnerable_people:   {result['vulnerable_people']}")
            print(f"  medical_emergency:   {result['medical_emergency']} "
                  f"(severity {result['medical_severity']})")
            print(f"  required_resources:  {result['required_resources']}")
            print(f"  isolation:           {result['isolation']}")
            if result["extraction_notes"]:
                print(f"  notes: {result['extraction_notes']}")
        print("\n" + "=" * 70)
        print("Done. Expected: all 7 reports should resolve place_id to L-BRIDGE, and")
        print("most should set incident_type to trapped_residents with medical_emergency")
        print("true (from R-004/R-006's pregnant woman). Occasional LLM disagreement on")
        print("borderline fields (e.g. isolation, exact headcount for R-007) is normal at")
        print("this stage; the Verification Agent (Phase 8) will reconcile duplicates.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())