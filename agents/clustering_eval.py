"""Evaluation metrics for the clustering pipeline (Phase 9).

Ground truth (the incident each baseline report truly belongs to) is used
ONLY here, for scoring. Nothing in agents/intake_agent.py or
agents/verification_agent.py ever sees it — the same separation kept since
Phase 2, so the pipeline is judged fairly on unseen data, like a real
incoming report would be.
"""

import itertools


def pairwise_scores(predicted_groups: list[list[str]], true_groups: dict[str, str]) -> dict:
    """predicted_groups: one list of report ids per cluster the pipeline formed.
    true_groups: report_id -> true incident id.

    Looks at every pair of reports: a pair is 'together' if both are in the
    same predicted cluster, and 'truly together' if they share a true incident.
    precision = of the pairs we grouped, how many really belong together
    recall    = of the pairs that really belong together, how many we grouped
    """
    predicted_of = {}
    for gi, group in enumerate(predicted_groups):
        for rid in group:
            predicted_of[rid] = gi
    report_ids = sorted(rid for rid in predicted_of if rid in true_groups)

    tp = fp = fn = tn = 0
    for a, b in itertools.combinations(report_ids, 2):
        same_pred = predicted_of[a] == predicted_of[b]
        same_true = true_groups[a] == true_groups[b]
        if same_pred and same_true:
            tp += 1
        elif same_pred:
            fp += 1
        elif same_true:
            fn += 1
        else:
            tn += 1

    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "precision": precision, "recall": recall, "f1": f1,
        "true_positive_pairs": tp, "false_positive_pairs": fp,
        "false_negative_pairs": fn, "true_negative_pairs": tn,
    }


def incident_match_report(predicted_groups: list[list[str]], true_groups: dict[str, str]) -> list[dict]:
    """For each TRUE incident, finds the predicted cluster overlapping it most
    and reports how clean the match is: which reports were wrongly pulled in
    (false merges) and which were left out (splits)."""
    true_incidents: dict[str, set] = {}
    for rid, inc in true_groups.items():
        true_incidents.setdefault(inc, set()).add(rid)

    rows = []
    for inc_id, members in sorted(true_incidents.items()):
        best_group, best_overlap = [], 0
        for group in predicted_groups:
            overlap = len(set(group) & members)
            if overlap > best_overlap:
                best_group, best_overlap = group, overlap
        rows.append({
            "incident_id": inc_id,
            "true_report_count": len(members),
            "best_matching_cluster_size": len(best_group),
            "overlap": best_overlap,
            "exact_match": set(best_group) == members,
            "extra_reports_in_cluster": sorted(set(best_group) - members),
            "missing_reports_from_cluster": sorted(members - set(best_group)),
        })
    return rows