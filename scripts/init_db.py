"""Creates and seeds the ReliefMesh SQLite database (Phase 3).

Run from the project root:  python scripts/init_db.py
WARNING: this RESETS the database to the original demo state every time.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from database.connection import get_connection, resolve_db_path  # noqa: E402
from database.queries import (  # noqa: E402
    get_command_center_summary,
    list_incidents,
    list_reports,
)
from database.seed import init_database  # noqa: E402


def main() -> int:
    db_path = resolve_db_path()
    print("ReliefMesh AI - Phase 3 database setup")
    print("-" * 42)
    print(f"Database file: {db_path}")

    try:
        counts = init_database(db_path)
    except Exception as error:  # show a readable message instead of a long traceback
        print(f"\nDatabase setup FAILED: {error}")
        print("Tip: close any SQLite viewer and stop the backend, then try again.")
        return 1

    print("\nRows loaded:")
    for table, count in counts.items():
        print(f"  {table:<14} {count}")

    conn = get_connection(db_path)
    try:
        processed = len(list_reports(conn, status="processed"))
        queued = len(list_reports(conn, status="queued"))
        summary = get_command_center_summary(conn)
        top = list_incidents(conn)[:5]
    finally:
        conn.close()

    print(f"\nReports: {processed} processed (linked to incidents), "
          f"{queued} queued for the live demo")

    print("\nCommand Center numbers (starting state):")
    print(f"  Active incidents:          {summary['active_incidents']}")
    print(f"  Critical incidents:        {summary['critical_incidents']}")
    print(f"  Medical emergencies:       {summary['medical_emergencies']}")
    print(f"  Available rescue teams:    {summary['available_rescue_teams']}")
    print(f"  Available boats:           {summary['available_boats']}")
    print(f"  Available ambulances:      {summary['available_ambulances']}")
    print(f"  Available medical teams:   {summary['available_medical_teams']}")
    print(f"  Shelter free capacity:     {summary['shelter_free']} of {summary['shelter_capacity_total']}")
    print(f"  Hospital beds free:        {summary['hospital_beds_available']} "
          f"(ICU: {summary['icu_beds_available']})")

    print("\nTop 5 incidents:")
    for inc in top:
        print(f"  {inc['id']}  {inc['priority']:<8} {inc['evidence_confidence']:>3}%  {inc['title']}")

    print("-" * 42)
    print("Database ready. You can now start Phase 4.")
    return 0


if __name__ == "__main__":
    sys.exit(main())