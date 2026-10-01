"""Runs the Priority Agent over every incident already in the database and
prints its score next to the value seeded in Phase 3 (Phase 10).

No LLM calls, no network, nothing to retry — this is pure arithmetic, so it
costs nothing and always gives the same answer.

Run from the project root:  python scripts/run_priority_eval.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agents.priority_agent import assign_priority  # noqa: E402
from database.connection import get_connection  # noqa: E402
from database.queries import list_incidents  # noqa: E402

ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}


def main() -> int:
    conn = get_connection()
    try:
        incidents = list_incidents(conn)
        if not incidents:
            print("No incidents found. Run 'python scripts/init_db.py' first.")
            return 1

        print(f"{'ID':8s} {'score':>5s}  {'computed':9s} {'seeded':9s}")
        exact = 0
        for inc in incidents:
            result = assign_priority(inc)
            match = result["priority"] == inc["priority"]
            exact += match
            tag = "" if match else "  <-- differs"
            print(f"{inc['id']:8s} {result['priority_score']:5d}  "
                  f"{result['priority']:9s} {inc['priority']:9s}{tag}")
        print(f"\n{exact}/{len(incidents)} match the value already stored from seeding.")
        print("A difference here is expected and fine: the seeded value is a reference "
              "label; this agent computes its own, independently, as your spec requires.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())