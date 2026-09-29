"""Automated tests for Phase 9 (full-scale clustering validation).

No real LLM or embedding-model calls. The full-scale test builds synthetic
extractions from the known ground truth (test-only use of ground truth, like
the hidden answer key has been used only for seeding and scoring since Phase 2)
to prove the clustering MECHANICS hold up at all 43 reports. Real extraction
accuracy is what scripts/run_full_clustering_eval.py measures with a live LLM.
"""

import hashlib
import json
import math
import re

import pytest

from agents.cache import cached_intake, extraction_failed, load_cache, prune_failed, save_cache
from agents.clustering_eval import incident_match_report, pairwise_scores
from agents.verification_agent import build_embedding_text, cluster_reports
from database.connection import get_connection
from database.queries import list_reports
from database.seed import init_database
from dataset.incidents import INCIDENTS


class FakeEmbedder:
    def __init__(self, dims=64):
        self.dims = dims

    def _vector(self, text):
        vec = [0.0] * self.dims
        for word in re.findall(r"[a-zA-Z]+", text.lower()):
            vec[int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16) % self.dims] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def encode(self, texts, normalize_embeddings=True):
        return [self._vector(t) for t in texts]


class CountingFakeLLM:
    def __init__(self):
        self.calls = 0

    def complete_json(self, prompt, system=None, **kwargs):
        self.calls += 1
        return {"incident_type": "trapped_residents", "location_text": "Kabul River Bridge",
                "estimated_affected": 10, "vulnerable_people": 1, "medical_emergency": False,
                "medical_severity": 0, "required_resources": ["boat"], "isolation": 1,
                "reasoning": "test"}

class FailingLLM:
    def complete_json(self, prompt, system=None, **kwargs):
        from llm.client import LLMError
        raise LLMError("simulated rate limit")

@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "test.db"
    init_database(path)
    conn = get_connection(path)
    yield conn
    conn.close()


# ------------------------------------------------------------------------ cache
def test_cache_load_missing_file_returns_empty(tmp_path):
    assert load_cache(tmp_path / "nope.json") == {}


def test_cache_save_and_load_roundtrip_with_urdu(tmp_path):
    path = tmp_path / "sub" / "cache.json"
    data = {"R-1": {"text": "پل کے قریب", "n": 3}}
    save_cache(path, data)
    assert load_cache(path) == data
    assert "پل" in path.read_text(encoding="utf-8")       # stored readable, not escaped


def test_cached_intake_only_calls_llm_once_per_report(db, tmp_path):
    cache_path = tmp_path / "cache.json"
    report = list_reports(db, status="queued")[0]
    llm = CountingFakeLLM()

    first = cached_intake(report, db, cache_path, llm_client=llm)
    second = cached_intake(report, db, cache_path, llm_client=llm)

    assert llm.calls == 1, "second call must come from the cache"
    assert first == second


def test_cached_intake_force_bypasses_cache(db, tmp_path):
    cache_path = tmp_path / "cache.json"
    report = list_reports(db, status="queued")[0]
    llm = CountingFakeLLM()
    cached_intake(report, db, cache_path, llm_client=llm)
    cached_intake(report, db, cache_path, llm_client=llm, force=True)
    assert llm.calls == 2


def test_cached_intake_saves_progress_after_each_report(db, tmp_path):
    cache_path = tmp_path / "cache.json"
    reports = list_reports(db, status="queued")[:3]
    llm = CountingFakeLLM()
    for r in reports:
        cached_intake(r, db, cache_path, llm_client=llm)
    assert set(json.loads(cache_path.read_text(encoding="utf-8"))) == {r["id"] for r in reports}


def test_extraction_failed_detects_llm_failure_notes():
    good = {"extraction_notes": ["some minor cleanup note"]}
    bad = {"extraction_notes": ["LLM extraction failed, using defaults: simulated rate limit"]}
    assert extraction_failed(good) is False
    assert extraction_failed(bad) is True


def test_cached_intake_never_caches_a_failed_extraction(db, tmp_path):
    """Regression test for a real bug found in a Phase 9 live run: a Groq
    429 rate-limit caused several reports to fall back to safe defaults, and
    those defaults got cached as if they were real answers."""
    cache_path = tmp_path / "cache.json"
    report = list_reports(db, status="queued")[0]

    result = cached_intake(report, db, cache_path, llm_client=FailingLLM())
    assert extraction_failed(result) is True
    assert load_cache(cache_path) == {}, "a failed extraction must never be written to the cache"


def test_cached_intake_retries_a_previously_failed_entry(db, tmp_path):
    cache_path = tmp_path / "cache.json"
    report = list_reports(db, status="queued")[0]

    cached_intake(report, db, cache_path, llm_client=FailingLLM())     # fails, not cached
    llm = CountingFakeLLM()
    result = cached_intake(report, db, cache_path, llm_client=llm)     # should actually retry
    assert llm.calls == 1
    assert extraction_failed(result) is False
    assert load_cache(cache_path)                                     # now cached for real


def test_prune_failed_removes_only_bad_entries(tmp_path):
    cache_path = tmp_path / "cache.json"
    save_cache(cache_path, {
        "R-1": {"extraction_notes": ["LLM extraction failed, using defaults: boom"]},
        "R-2": {"extraction_notes": ["a harmless note"]},
    })
    removed = prune_failed(cache_path)
    assert removed == ["R-1"]
    assert list(load_cache(cache_path)) == ["R-2"]


# ---------------------------------------------------------------- scoring metrics
def test_pairwise_scores_perfect_clustering():
    true = {"a": "X", "b": "X", "c": "Y", "d": "Y"}
    scores = pairwise_scores([["a", "b"], ["c", "d"]], true)
    assert scores["precision"] == 1.0 and scores["recall"] == 1.0 and scores["f1"] == 1.0


def test_pairwise_scores_penalise_a_split_incident():
    true = {"a": "X", "b": "X", "c": "X"}
    scores = pairwise_scores([["a", "b"], ["c"]], true)       # incident X was split
    assert scores["precision"] == 1.0
    assert scores["recall"] < 1.0
    assert scores["false_negative_pairs"] == 2


def test_pairwise_scores_penalise_a_false_merge():
    true = {"a": "X", "b": "Y"}
    scores = pairwise_scores([["a", "b"]], true)              # two incidents wrongly merged
    assert scores["precision"] == 0.0
    assert scores["false_positive_pairs"] == 1


def test_incident_match_report_flags_extra_and_missing():
    true = {"a": "X", "b": "X", "c": "Y"}
    rows = {r["incident_id"]: r for r in incident_match_report([["a", "c"], ["b"]], true)}
    assert rows["X"]["exact_match"] is False
    assert rows["X"]["missing_reports_from_cluster"] or rows["X"]["extra_reports_in_cluster"]
    perfect = {r["incident_id"]: r for r in incident_match_report([["a", "b"], ["c"]], true)}
    assert perfect["X"]["exact_match"] and perfect["Y"]["exact_match"]


# ------------------------------------------------------------- full-scale clustering
def test_clustering_reconstructs_all_19_baseline_incidents_at_scale(db):
    """All 43 baseline reports, not just the hand-picked cases from Phase 8.
    Extractions are built from ground truth (test-only) so this proves the
    clustering math scales; it does not prove real-LLM extraction accuracy."""
    reports = list_reports(db, status="processed")
    assert len(reports) == 43
    by_id = {i["id"]: i for i in INCIDENTS}

    extractions = []
    for r in reports:
        inc = by_id[r["incident_id"]]
        extractions.append({
            "incident_type": inc["incident_type"], "location_text": inc["title"],
            "estimated_affected": inc["estimated_affected"],
            "vulnerable_people": inc["vulnerable_people"],
            "medical_emergency": inc["medical_emergency"],
            "medical_severity": inc["medical_severity"],
            "required_resources": inc["required_resources"], "isolation": inc["isolation"],
            "reasoning": inc["title"], "place_id": inc["place_id"], "place_name": inc["place_id"],
        })

    embeddings = FakeEmbedder().encode([build_embedding_text(e) for e in extractions])
    clusters = cluster_reports(extractions, embeddings)
    predicted = [[reports[i]["id"] for i in idxs] for idxs in clusters]
    true = {r["id"]: r["incident_id"] for r in reports}

    assert len(predicted) == 19
    assert pairwise_scores(predicted, true)["f1"] == 1.0
    assert all(row["exact_match"] for row in incident_match_report(predicted, true))


def test_full_scale_keeps_same_place_hard_negatives_apart(db):
    """INC-003/INC-019 (both at Mian Gujjar Basti) and INC-004/INC-013 (both at
    Old Bus Stand) share a place but are different incidents."""
    reports = list_reports(db, status="processed")
    by_id = {i["id"]: i for i in INCIDENTS}
    extractions = [{
        "incident_type": by_id[r["incident_id"]]["incident_type"],
        "location_text": by_id[r["incident_id"]]["title"],
        "estimated_affected": by_id[r["incident_id"]]["estimated_affected"],
        "vulnerable_people": 0, "medical_emergency": by_id[r["incident_id"]]["medical_emergency"],
        "medical_severity": 0, "required_resources": by_id[r["incident_id"]]["required_resources"],
        "isolation": 0, "reasoning": by_id[r["incident_id"]]["title"],
        "place_id": by_id[r["incident_id"]]["place_id"], "place_name": None,
    } for r in reports]

    embeddings = FakeEmbedder().encode([build_embedding_text(e) for e in extractions])
    predicted_of = {}
    for gi, idxs in enumerate(cluster_reports(extractions, embeddings)):
        for i in idxs:
            predicted_of[reports[i]["id"]] = gi

    by_report = {r["id"]: r["incident_id"] for r in reports}
    gujjar_003 = next(rid for rid, inc in by_report.items() if inc == "INC-003")
    gujjar_019 = next(rid for rid, inc in by_report.items() if inc == "INC-019")
    bus_004 = next(rid for rid, inc in by_report.items() if inc == "INC-004")
    bus_013 = next(rid for rid, inc in by_report.items() if inc == "INC-013")
    assert predicted_of[gujjar_003] != predicted_of[gujjar_019]
    assert predicted_of[bus_004] != predicted_of[bus_013]