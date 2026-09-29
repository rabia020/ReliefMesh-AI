"""Verification Agent (Phase 8).

Takes a batch of newly-received reports (already run through the Intake
Agent), and checks: duplicate reports, conflicting reports, source
confidence, report age, and nearby/related reports — then produces an
evidence confidence score for each resulting group, exactly as your prompt
requires.

Design: clustering (duplicate/near-duplicate detection) and the confidence
score are entirely deterministic arithmetic over known facts. The LLM is
used for exactly one narrow judgment call — whether a group of reports
actually contradicts itself — because "do these reports agree?" is a
genuinely semantic question that simple rules can't reliably answer, while
"how confident should we be?" can and should be computed the same way
every time (that's what makes the demo reproducible).
"""

import itertools
from datetime import datetime
from typing import Optional

from agents.embeddings import embed_texts
from agents.intake_agent import run_intake
from dataset.constants import SOURCE_CONFIDENCE
from llm.client import LLMError, get_llm_client

# Two reports at the SAME known place only need to be loosely similar to be
# linked, since the place match already carries most of the evidence.
# Calibrated against real sentence-transformers output during Phase 8 testing
# (0.45 was too low: it let two same-place, different-topic reports merge,
# since real embeddings rate any two same-disaster sentences as moderately
# similar). Use scripts/run_verification_demo.py's similarity printout to
# retune this for your own data if needed.
PLACE_MATCH_SIM_THRESHOLD = 0.60

# Two reports where neither resolved to a known place need to be very similar
# indeed, since content is the only signal we have.
NO_PLACE_SIM_THRESHOLD = 0.80

CORROBORATION_CAP = 4            # 5+ independent reports give no extra credit
FRESHNESS_WINDOW_MINUTES = 180   # confidence credit for freshness fades to 0 after 3 hours
CONFLICT_PENALTY = 0.30


def _dot(a, b) -> float:
    return sum(x * y for x, y in zip(a, b))


def similarity(vector_a: list[float], vector_b: list[float]) -> float:
    """Cosine similarity between two normalized embedding vectors (a plain
    dot product). Exposed publicly so debug/demo scripts can print actual
    numbers when tuning the clustering thresholds above."""
    return _dot(vector_a, vector_b)


def build_embedding_text(extraction: dict) -> str:
    """Turns one Intake Agent extraction into a short English sentence to embed.

    Reports arrive in English, Roman Urdu, or Urdu script, but the Intake
    Agent (Phase 7) already translates location_text and reasoning into
    English. Embedding THAT text — rather than the raw multilingual report —
    lets a small English sentence-embedding model correctly cluster
    cross-lingual duplicates (e.g. "Bridge flooded" and "Pul ke paas pani
    hai") without needing a heavier multilingual model.
    """
    parts = [
        extraction.get("incident_type", "").replace("_", " "),
        "at", extraction.get("location_text") or "an unknown location.",
        extraction.get("reasoning", ""),
        f"Affected: {extraction.get('estimated_affected', 0)}.",
    ]
    if extraction.get("medical_emergency"):
        parts.append("Medical emergency.")
    if extraction.get("required_resources"):
        parts.append("Needs: " + ", ".join(extraction["required_resources"]) + ".")
    return " ".join(p for p in parts if p)


def _minutes_between(t1_iso: str, t2_iso: str) -> float:
    t1, t2 = datetime.fromisoformat(t1_iso), datetime.fromisoformat(t2_iso)
    return abs((t2 - t1).total_seconds()) / 60.0


class _UnionFind:
    """Standard disjoint-set structure used to group linked reports into clusters."""

    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def cluster_reports(extractions: list[dict], embeddings: list[list[float]],
                     place_threshold: float = PLACE_MATCH_SIM_THRESHOLD,
                     no_place_threshold: float = NO_PLACE_SIM_THRESHOLD) -> list[list[int]]:
    """Groups report indices into duplicate/related-report clusters.

    Three steps, in this order:
    1. Reports at the SAME known place are linked if their content is similar
       enough (place_threshold).
    2. Reports at two DIFFERENT known places are NEVER linked by similarity
       alone. (An earlier version allowed this at a high similarity, and real
       Intake output is often generic enough that unrelated reports from
       different places looked alike, which chained into one giant cluster.)
    3. A report with no resolved place is attached to its single best-matching
       report, only if that match is very similar (no_place_threshold). Each
       such report attaches to at most one cluster, so it can never bridge two
       separate clusters together. Unresolved reports with no good match are
       grouped only with each other.
    """
    n = len(extractions)
    uf = _UnionFind(n)
    place_of = [e.get("place_id") for e in extractions]
    resolved = [i for i in range(n) if place_of[i]]
    unresolved = [i for i in range(n) if not place_of[i]]

    for i, j in itertools.combinations(resolved, 2):
        if place_of[i] == place_of[j] and _dot(embeddings[i], embeddings[j]) >= place_threshold:
            uf.union(i, j)

    unattached = []
    for u in unresolved:
        best_idx, best_sim = None, 0.0
        for r in resolved:
            sim = _dot(embeddings[u], embeddings[r])
            if sim > best_sim:
                best_idx, best_sim = r, sim
        if best_idx is not None and best_sim >= no_place_threshold:
            uf.union(u, best_idx)
        else:
            unattached.append(u)

    for a, b in itertools.combinations(unattached, 2):
        if _dot(embeddings[a], embeddings[b]) >= no_place_threshold:
            uf.union(a, b)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(uf.find(i), []).append(i)
    return list(groups.values())


def compute_evidence_confidence(reports: list[dict], now_iso: str, conflict_detected: bool) -> int:
    """A deterministic 0-100 confidence score, combining:
    - source confidence (from dataset.constants.SOURCE_CONFIDENCE)
    - corroboration (how many independent reports agree)
    - freshness (how recently the newest report in the group came in)
    - whether any report includes image evidence
    - a penalty if the reports conflict with each other

    Everything here is plain arithmetic over known facts. Your prompt asks
    the Priority Agent (Phase 10) not to rely solely on LLM judgment for
    numbers; the same discipline is applied a step earlier here.
    """
    n = len(reports)
    source_scores = [SOURCE_CONFIDENCE.get(r["source_type"], 0.5) for r in reports]
    avg_source = sum(source_scores) / n
    max_source = max(source_scores)
    source_score = 0.6 * avg_source + 0.4 * max_source

    corroboration_score = min(1.0, (n - 1) / CORROBORATION_CAP)

    newest_ts = max(r["timestamp"] for r in reports)
    age_minutes = _minutes_between(newest_ts, now_iso)
    freshness_score = max(0.0, 1 - age_minutes / FRESHNESS_WINDOW_MINUTES)

    image_score = 1.0 if any(r.get("image_id") for r in reports) else 0.0

    raw = (0.5 * source_score + 0.25 * corroboration_score
           + 0.15 * freshness_score + 0.10 * image_score)
    if conflict_detected:
        raw -= CONFLICT_PENALTY
    return round(max(0.0, min(1.0, raw)) * 100)


CONFLICT_SYSTEM_PROMPT = """You are the Verification Agent for ReliefMesh AI, a \
disaster-response system. You will be shown several citizen or field reports \
that have been grouped as describing the same real-world situation. Decide \
whether they meaningfully CONTRADICT each other about an important fact — for \
example: one says a structure has completely failed while another says it is \
only cracked and holding; one says a road is blocked while another says it is \
open; one claims an event happened while a more reliable source says it did \
not; or the number of people affected differs by several times over. Minor \
differences in wording, or headcounts that are roughly in the same range, are \
NOT a conflict.

Respond with a single JSON object:
{"conflict_detected": true or false, "conflict_note": a one-sentence, neutral \
description of the disagreement if conflict_detected is true, otherwise null}"""


def detect_conflict(reports: list[dict], llm_client=None) -> tuple[bool, Optional[str]]:
    """A single report can't conflict with itself, so this is skipped (and no
    LLM call made) for clusters of size 1."""
    if len(reports) < 2:
        return False, None
    client = llm_client or get_llm_client()
    lines = [f"- [{r['source_type']}, {r['timestamp']}] {r['text']}" for r in reports]
    prompt = "Reports:\n" + "\n".join(lines)
    try:
        result = client.complete_json(prompt, system=CONFLICT_SYSTEM_PROMPT)
    except LLMError:
        return False, None      # a failed check should not block the pipeline
    detected = bool(result.get("conflict_detected", False))
    note = result.get("conflict_note")
    return detected, (str(note).strip() if detected and note else None)


def merge_cluster(reports: list[dict], extractions: list[dict]) -> dict:
    """Combines one cluster's reports and extractions into a single set of
    aggregated facts. Deliberately factual only — no incident title or
    written summary. That belongs to the Reporter Agent (Phase 13)."""
    n = len(reports)
    best_idx = max(range(n), key=lambda i: SOURCE_CONFIDENCE.get(reports[i]["source_type"], 0.5))
    best = extractions[best_idx]

    type_votes: dict[str, int] = {}
    for e in extractions:
        type_votes[e["incident_type"]] = type_votes.get(e["incident_type"], 0) + 1
    top_count = max(type_votes.values())
    tied_types = {t for t, c in type_votes.items() if c == top_count}
    incident_type = best["incident_type"] if best["incident_type"] in tied_types else sorted(tied_types)[0]

    place_id = best.get("place_id") or next((e["place_id"] for e in extractions if e.get("place_id")), None)
    place_name = best.get("place_name") or next(
        (e["place_name"] for e in extractions if e.get("place_name")), None)

    return {
        "incident_type": incident_type,
        "place_id": place_id,
        "place_name": place_name,
        "estimated_affected": best["estimated_affected"] or max(
            (e["estimated_affected"] for e in extractions), default=0),
        "vulnerable_people": best["vulnerable_people"] or max(
            (e["vulnerable_people"] for e in extractions), default=0),
        "medical_emergency": any(e["medical_emergency"] for e in extractions),
        "medical_severity": max(e["medical_severity"] for e in extractions),
        "isolation": max(e["isolation"] for e in extractions),
        "required_resources": sorted({need for e in extractions for need in e["required_resources"]}),
        "report_ids": [r["id"] for r in reports],
        "report_count": n,
        "first_report_time": min(r["timestamp"] for r in reports),
        "last_report_time": max(r["timestamp"] for r in reports),
        "languages": sorted({r["language"] for r in reports}),
    }

CLUSTER_MERGE_SYSTEM_PROMPT = """You are the Verification Agent for ReliefMesh AI, \
a disaster-response system. You will be shown two GROUPS of reports that were \
independently identified as being about the same real-world LOCATION during a \
flood, but did not automatically merge into one group.

Decide whether the two groups should be treated as ONE incident for dispatch \
purposes, or as TWO SEPARATE incidents a coordinator would track and respond \
to independently.

They are the SAME incident only if they need essentially the same response \
(for example: two accounts of the same trapped people, one emphasizing a \
blocked road and the other emphasizing people needing rescue — still one \
rescue operation. Or: an unverified rumor and a field officer's report that \
confirms or denies it — the field report IS the resolution of the rumor).

They are DIFFERENT incidents if they involve different people or things \
affected, or need different resources — even if both are part of the same \
broader flood at the same place. Being part of the same flood is NOT enough \
by itself. For example: people needing rescue vs. livestock needing rescue \
are DIFFERENT incidents (different beneficiaries), even though both are at \
the same flooded village. A flooded shop and a missing child at the same \
market are DIFFERENT incidents.

When genuinely unsure, prefer keeping them SEPARATE: a coordinator can merge \
two incidents after seeing both, but a wrongly-merged incident can hide one \
of the two needs entirely.

Respond with a single JSON object:
{"same_incident": true or false, "reason": a short one-sentence explanation}"""

def _same_incident_check(cluster_a: dict, cluster_b: dict, llm_client=None) -> tuple[bool, str]:
    client = llm_client or get_llm_client()
    text_a = "\n".join(f"- {r['text']}" for r in cluster_a["reports"])
    text_b = "\n".join(f"- {r['text']}" for r in cluster_b["reports"])
    prompt = f"Group A:\n{text_a}\n\nGroup B:\n{text_b}"
    try:
        result = client.complete_json(prompt, system=CLUSTER_MERGE_SYSTEM_PROMPT)
    except LLMError as error:
        return False, f"LLM check failed ({error}); kept separate as a precaution"
    return bool(result.get("same_incident", False)), str(result.get("reason", ""))


def _recompute_cluster(reports: list[dict], extractions: list[dict], now_iso: str, llm_client=None) -> dict:
    conflict_detected, conflict_note = detect_conflict(reports, llm_client=llm_client)
    confidence = compute_evidence_confidence(reports, now_iso, conflict_detected)
    merged = merge_cluster(reports, extractions)
    return {
        "reports": reports, "extractions": extractions, "merged": merged,
        "evidence_confidence": confidence, "conflict_detected": conflict_detected,
        "conflict_note": conflict_note,
    }


def merge_related_clusters_at_same_place(results: list[dict], now_iso: str, llm_client=None,
                                          verbose: bool = False) -> list[dict]:
    """A second pass for a genuinely hard case: two reports about the very
    same incident can emphasize such different aspects (a blocked road vs.
    trapped people, both from one bridge flood) that their content similarity
    falls below PLACE_MATCH_SIM_THRESHOLD even though they share a place.
    Raising that threshold to catch such cases would also catch same-place,
    DIFFERENT-incident report pairs like the Mian Gujjar Basti hard negative
    — the two goals are mathematically incompatible for a single fixed
    number in real embedding output. So instead: only when a place ends up
    with more than one cluster, ask the LLM directly whether they're the
    same incident. This runs rarely (most places produce exactly one
    cluster) and resolves exactly the cases pure similarity can't.
    """
    results = list(results)
    rejected: set = set()      # remembers exact-membership pairs already answered "no"
    changed = True
    while changed:
        changed = False
        for i, j in itertools.combinations(range(len(results)), 2):
            place_i = results[i]["merged"]["place_id"]
            place_j = results[j]["merged"]["place_id"]
            if not place_i or place_i != place_j:
                continue
            ids_i = frozenset(r["id"] for r in results[i]["reports"])
            ids_j = frozenset(r["id"] for r in results[j]["reports"])
            key = frozenset((ids_i, ids_j))
            if key in rejected:
                continue    # already asked this exact pair of groups; don't ask again
            same, reason = _same_incident_check(results[i], results[j], llm_client=llm_client)
            if verbose:
                print(f"[verification] same-place check at {place_i}: "
                      f"{sorted(ids_i)} vs {sorted(ids_j)} -> same_incident={same} ({reason})")
            if same:
                combined = _recompute_cluster(
                    results[i]["reports"] + results[j]["reports"],
                    results[i]["extractions"] + results[j]["extractions"],
                    now_iso, llm_client,
                )
                combined["merge_reason"] = reason
                results = [r for k, r in enumerate(results) if k not in (i, j)] + [combined]
                changed = True
                break
            rejected.add(key)
    return results

def verify_reports(reports: list[dict], conn, now_iso: str = None,
                    llm_client=None, embedder=None, intake_results: list[dict] = None,
                    verbose: bool = False) -> list[dict]:
    """Top-level Verification Agent entry point.

    reports:  rows shaped like database.queries.list_reports() (e.g. status='received')
    conn:     open DB connection, passed through to the Intake Agent for gazetteer matching
    now_iso:  the scenario 'now' timestamp used for report-age scoring;
              defaults to the scenario clock stored in the database
    intake_results: pass in already-computed Phase 7 extractions (same order
              as `reports`) to avoid re-running the LLM extraction step

    Returns one dict per cluster: reports, extractions, merged,
    evidence_confidence, conflict_detected, conflict_note.
    """
    if not reports:
        return []

    if now_iso is None:
        from database.queries import get_scenario
        now_iso = get_scenario(conn)["now"]

    extractions = intake_results or [run_intake(r, conn=conn, llm_client=llm_client) for r in reports]
    texts = [build_embedding_text(e) for e in extractions]
    embeddings = embed_texts(texts, embedder=embedder)

    clusters = cluster_reports(extractions, embeddings)

    results = []
    for indices in clusters:
        cluster_reports_ = [reports[i] for i in indices]
        cluster_extractions = [extractions[i] for i in indices]
        conflict_detected, conflict_note = detect_conflict(cluster_reports_, llm_client=llm_client)
        confidence = compute_evidence_confidence(cluster_reports_, now_iso, conflict_detected)
        merged = merge_cluster(cluster_reports_, cluster_extractions)
        results.append({
            "reports": cluster_reports_,
            "extractions": cluster_extractions,
            "merged": merged,
            "evidence_confidence": confidence,
            "conflict_detected": conflict_detected,
            "conflict_note": conflict_note,
        })
    return merge_related_clusters_at_same_place(results, now_iso, llm_client=llm_client, verbose=verbose)

