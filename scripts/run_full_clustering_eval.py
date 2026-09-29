"""Runs the real Intake + clustering pipeline over all 43 baseline reports and
scores it against the ground truth recorded for those reports (Phase 9).

Costs real LLM calls the first time (about 43 extractions plus a few
same-place checks). Extractions are cached in data/cache/intake_cache.json, so
re-runs while tuning thresholds cost almost nothing. Use --fresh to ignore the
cache.

Run from the project root:  python scripts/run_full_clustering_eval.py
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agents.cache import cached_intake  # noqa: E402
from agents.clustering_eval import incident_match_report, pairwise_scores  # noqa: E402
from agents.embeddings import embed_texts  # noqa: E402
from agents.verification_agent import (  # noqa: E402
    build_embedding_text,
    cluster_reports,
    merge_cluster,
    merge_related_clusters_at_same_place,
)
from database.connection import get_connection  # noqa: E402
from database.queries import get_scenario, list_reports  # noqa: E402

CACHE_PATH = ROOT / "data" / "cache" / "intake_cache.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fresh", action="store_true",
                        help="ignore the cache and re-run every Intake extraction")
    args = parser.parse_args()

    conn = get_connection()
    try:
        reports = list_reports(conn, status="processed")
        if not reports:
            print("No baseline reports found. Run 'python scripts/init_db.py' first.")
            return 1

        # Ground truth: used ONLY to score, after the pipeline has decided on its own.
        true_groups = {r["id"]: r["incident_id"] for r in reports}

        print(f"Intake extraction for {len(reports)} baseline reports "
              f"({'ignoring cache' if args.fresh else 'cache used when available'})...")
        extractions = []
        for i, r in enumerate(reports, start=1):
            e = cached_intake(r, conn, CACHE_PATH, force=args.fresh)
            extractions.append(e)
            print(f"  [{i:>2}/{len(reports)}] {r['id']}: {e['incident_type']} @ {e['place_id']}")

        print("\nEmbedding and clustering...")
        embeddings = embed_texts([build_embedding_text(e) for e in extractions])
        raw_clusters = cluster_reports(extractions, embeddings)

        results = []
        for indices in raw_clusters:
            cluster_reports_ = [reports[i] for i in indices]
            cluster_extractions = [extractions[i] for i in indices]
            results.append({
                "reports": cluster_reports_, "extractions": cluster_extractions,
                "merged": merge_cluster(cluster_reports_, cluster_extractions),
                "evidence_confidence": None, "conflict_detected": False, "conflict_note": None,
            })
        print(f"Clusters after similarity pass:        {len(results)}")

        now_iso = get_scenario(conn)["now"]
        results = merge_related_clusters_at_same_place(results, now_iso, verbose=True)
        print(f"Clusters after same-place adjudication: {len(results)}  (ground truth: 19)\n")

        predicted = [c["merged"]["report_ids"] for c in results]
        scores = pairwise_scores(predicted, true_groups)
        print("Pairwise scores:")
        print(f"  precision: {scores['precision']:.3f}   (of pairs we grouped, how many belong together)")
        print(f"  recall:    {scores['recall']:.3f}   (of pairs that belong together, how many we grouped)")
        print(f"  f1:        {scores['f1']:.3f}")

        print("\nPer-incident results:")
        rows = incident_match_report(predicted, true_groups)
        for row in rows:
            tag = "EXACT  " if row["exact_match"] else "partial"
            print(f"  {row['incident_id']}: {tag} true={row['true_report_count']} "
                  f"cluster={row['best_matching_cluster_size']} overlap={row['overlap']}")
            if row["extra_reports_in_cluster"]:
                print(f"      wrongly merged in: {row['extra_reports_in_cluster']}")
            if row["missing_reports_from_cluster"]:
                print(f"      split off:         {row['missing_reports_from_cluster']}")
        exact = sum(1 for row in rows if row["exact_match"])
        print(f"\n{exact} / {len(rows)} ground-truth incidents reconstructed exactly.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())