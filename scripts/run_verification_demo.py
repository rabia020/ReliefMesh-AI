"""Runs the real Verification Agent (real Gemini + real sentence-transformers)
over the queued demo reports and, for comparison, over the Mian Gujjar Basti
hard-negative pair from the baseline data.

Manual, human-eyeball check, not part of the automated test suite: it costs
real API quota, downloads a ~90 MB embedding model on first run, and its
output depends on the live model.

Run from the project root:  python scripts/run_verification_demo.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agents.embeddings import embed_texts  # noqa: E402
from agents.intake_agent import run_intake  # noqa: E402
from agents.verification_agent import (  # noqa: E402
    build_embedding_text,
    similarity,
    verify_reports,
)
from database.connection import get_connection  # noqa: E402
from database.queries import list_reports  # noqa: E402


def _print_similarity_matrix(reports, conn):
    """Prints every pairwise similarity plus each report's resolved place, so
    you can see the actual numbers behind a clustering decision and retune
    PLACE_MATCH_SIM_THRESHOLD / NO_PLACE_SIM_THRESHOLD in
    agents/verification_agent.py with real data instead of guessing.
    Returns the extractions so the caller can reuse them (avoids re-running
    the Intake Agent's Gemini calls a second time)."""
    extractions = [run_intake(r, conn=conn) for r in reports]
    texts = [build_embedding_text(e) for e in extractions]
    embeddings = embed_texts(texts)

    print("\nResolved places:")
    for r, e in zip(reports, extractions):
        print(f"  {r['id']}: place_id={e['place_id']}  location_text={e['location_text']!r}")

    print("\nPairwise similarity (place match marked with *):")
    for i in range(len(reports)):
        for j in range(i + 1, len(reports)):
            sim = similarity(embeddings[i], embeddings[j])
            same_place = extractions[i]["place_id"] and extractions[i]["place_id"] == extractions[j]["place_id"]
            mark = "*" if same_place else " "
            print(f"  {reports[i]['id']} <-> {reports[j]['id']}: {sim:.3f} {mark}")

    return extractions


def _print_cluster(cluster, index):
    m = cluster["merged"]
    print(f"\nCluster {index}: {m['report_count']} report(s) -> {m['report_ids']}")
    print(f"  incident_type:       {m['incident_type']}")
    print(f"  place:               {m['place_name']} ({m['place_id']})")
    print(f"  estimated_affected:  {m['estimated_affected']}")
    print(f"  vulnerable_people:   {m['vulnerable_people']}")
    print(f"  medical_emergency:   {m['medical_emergency']} (severity {m['medical_severity']})")
    print(f"  required_resources:  {m['required_resources']}")
    print(f"  languages:           {m['languages']}")
    print(f"  evidence_confidence: {cluster['evidence_confidence']}%")
    print(f"  conflict_detected:   {cluster['conflict_detected']}")
    if cluster["conflict_note"]:
        print(f"  conflict_note:       {cluster['conflict_note']}")


def main() -> int:
    conn = get_connection()
    try:
        print("Loading the sentence-transformers model (first run downloads ~90 MB)...")

        print("\n" + "=" * 70)
        print("PART 1: the 7 queued/received bridge reports (should form ONE cluster)")
        print("=" * 70)
        demo_reports = list_reports(conn, status="queued")
        if not demo_reports:
            demo_reports = list_reports(conn, status="received")
        if not demo_reports:
            print("No queued or received reports found. Run 'python scripts/init_db.py' first.")
            return 1
        demo_extractions = _print_similarity_matrix(demo_reports, conn)
        results = verify_reports(demo_reports, conn, verbose=True, intake_results=demo_extractions)

        for i, cluster in enumerate(results, start=1):
            _print_cluster(cluster, i)
        if len(results) == 1:
            print(f"\n[OK] All {len(demo_reports)} bridge reports formed exactly one cluster.")
        else:
            print(f"\n[NOTE] Formed {len(results)} clusters instead of 1. If some reports split "
                  "off, they were likely too dissimilar in the embedding model's view — "
                  "inspect the printed clusters above and consider lowering "
                  "PLACE_MATCH_SIM_THRESHOLD in agents/verification_agent.py slightly.")

        print("\n" + "=" * 70)
        print("PART 2: the Mian Gujjar Basti hard negative (should stay as TWO clusters)")
        print("=" * 70)
        gujjar_reports = [r for r in list_reports(conn) if r["id"] in ("R-016", "R-048")]
        if len(gujjar_reports) == 2:
            gujjar_extractions = _print_similarity_matrix(gujjar_reports, conn)
            results2 = verify_reports(gujjar_reports, conn, verbose=True, intake_results=gujjar_extractions)
            for i, cluster in enumerate(results2, start=1):
                _print_cluster(cluster, i)
            if len(results2) == 2:
                print("\n[OK] Trapped-family and stranded-livestock reports stayed separate.")
            else:
                print("\n[NOTE] These merged into one cluster — the model saw them as too "
                      "similar. Consider raising PLACE_MATCH_SIM_THRESHOLD slightly.")
        else:
            print("R-016 and/or R-048 were not found (already injected/processed differently);"
                  " skipping this comparison.")

        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())