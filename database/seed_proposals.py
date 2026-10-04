"""Dev helper: create 2 demo PROPOSED actions (no LLM needed).
Run from the project root:  python -m database.seed_proposals
To reset the demo afterwards, re-run your Phase 3 seed command.
"""
import os
from pathlib import Path

from database.connection import get_connection
from database.queries import create_proposed_action

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def _rows(conn, sql, params=()):
    cursor = conn.execute(sql, params)
    columns = [c[0] for c in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def main():
    path = Path(os.getenv("DATABASE_PATH", "data/reliefmesh.db"))
    conn = get_connection(path)

    if _rows(conn, "SELECT id FROM actions WHERE status = 'proposed'"):
        print("Proposed actions already exist. Nothing created.")
        return

    incidents = _rows(
        conn,
        "SELECT id, title, estimated_affected, vulnerable_people, medical_emergency, "
        "evidence_confidence FROM incidents WHERE priority = 'Critical' AND status = 'open' "
        "ORDER BY id LIMIT 2",
    )
    boats = _rows(conn, "SELECT id, name FROM resources WHERE type = 'boat' AND status = 'available' ORDER BY id")
    medical = _rows(conn, "SELECT id, name FROM resources WHERE type IN ('medical_team', 'ambulance') AND status = 'available' ORDER BY id")

    created = 0
    for index, incident in enumerate(incidents):
        picks = []
        if index < len(boats):
            picks.append(boats[index])
        if incident["medical_emergency"] and index < len(medical):
            picks.append(medical[index])
        if not picks:
            continue
        reason = "\n".join([
            f"{incident['estimated_affected']} affected people",
            f"{incident['vulnerable_people']} vulnerable people",
            "1 medical emergency" if incident["medical_emergency"] else "no medical emergency",
            f"{incident['evidence_confidence']}% evidence confidence",
            *[f"{p['name']} is available" for p in picks],
        ])
        action_id = create_proposed_action(
            conn,
            incident_id=incident["id"],
            action_type="dispatch_resource",
            title="Dispatch " + " + ".join(p["name"] for p in picks),
            reason=reason,
            resource_ids=[p["id"] for p in picks],
            proposed_by="ai:supervisor",
        )
        conn.commit()
        created += 1
        print(f"Created proposed action {action_id} for {incident['id']}: {incident['title']}")
    print(f"Done. {created} proposed action(s) created (SIMULATED data).")


if __name__ == "__main__":
    main()