"""Automated tests for Phase 8 (Verification Agent).

No real sentence-transformers model or Gemini call is used: a small
deterministic FakeEmbedder stands in for the real model (feature-hashing
bag-of-words, so shared vocabulary => high similarity, different topics =>
low similarity — enough to exercise the clustering LOGIC), and FakeLLM
stands in for Gemini exactly as in test_phase7.py.
"""

import hashlib
import math
import re

import pytest

from agents.intake_agent import run_intake
from agents.verification_agent import (
    build_embedding_text,
    cluster_reports,
    compute_evidence_confidence,
    detect_conflict,
    merge_cluster,
    verify_reports,
)
from agents.verification_agent import (
    build_embedding_text,
    cluster_reports,
    compute_evidence_confidence,
    detect_conflict,
    merge_cluster,
    merge_related_clusters_at_same_place,
    verify_reports,
)
from database.connection import get_connection
from database.queries import list_reports
from database.seed import init_database


class PositionalEmbedder:
    """Returns pre-set vectors matching input order, ignoring the actual text
    — used to reconstruct a specific real-world similarity structure exactly,
    rather than relying on a toy embedder's approximation of it."""

    def __init__(self, vectors):
        self.vectors = vectors

    def encode(self, texts, normalize_embeddings=True):
        assert len(texts) == len(self.vectors), "PositionalEmbedder vector count mismatch"
        return self.vectors


class FakeEmbedder:
    """Deterministic stand-in for a real sentence-transformer. Hashes words
    into fixed buckets (feature hashing) so texts sharing vocabulary get high
    cosine similarity and texts about different topics get low similarity."""

    def __init__(self, dims=64):
        self.dims = dims

    def _vector(self, text):
        vec = [0.0] * self.dims
        for word in re.findall(r"[a-zA-Z]+", text.lower()):
            bucket = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16) % self.dims
            vec[bucket] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def encode(self, texts, normalize_embeddings=True):
        return [self._vector(t) for t in texts]


class FakeLLM:
    def __init__(self, complete_json_return):
        self._return = complete_json_return
        self.calls = []

    def complete_json(self, prompt, system=None, **kwargs):
        self.calls.append({"prompt": prompt, "system": system})
        if isinstance(self._return, Exception):
            raise self._return
        if callable(self._return):
            return self._return(prompt, system)
        return self._return


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "test.db"
    init_database(path)
    conn = get_connection(path)
    yield conn
    conn.close()


def _extraction(**overrides):
    base = {
        "incident_type": "trapped_residents", "location_text": "Kabul River Bridge",
        "estimated_affected": 40, "vulnerable_people": 1, "medical_emergency": True,
        "medical_severity": 2, "required_resources": ["boat", "medical_team"],
        "isolation": 2, "reasoning": "Bridge flooding.",
        "place_id": "L-BRIDGE", "place_name": "Kabul River Bridge",
    }
    base.update(overrides)
    return base


def _report(**overrides):
    base = {
        "id": "R-X", "timestamp": "2026-08-14T08:00:00+05:00", "language": "en",
        "source_type": "whatsapp", "text": "text", "image_id": None, "structured": None,
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------- embedding text
def test_build_embedding_text_includes_key_fields():
    text = build_embedding_text(_extraction())
    assert "trapped residents" in text
    assert "Kabul River Bridge" in text
    assert "Medical emergency." in text
    assert "boat" in text


# ------------------------------------------------------------------ clustering
def test_cluster_same_place_and_similar_content_links():
    extractions = [
        _extraction(place_id="L-BRIDGE"),
        _extraction(place_id="L-BRIDGE", reasoning="Bridge flooding, people trapped."),
    ]
    embeddings = [[1.0, 0.0], [0.9, 0.1]]     # high similarity
    clusters = cluster_reports(extractions, embeddings)
    assert len(clusters) == 1
    assert set(clusters[0]) == {0, 1}


def test_cluster_same_place_but_different_content_does_not_link():
    """The Mian Gujjar Basti hard negative: trapped families vs. stranded
    livestock, same place, very different content — must NOT merge."""
    extractions = [
        _extraction(place_id="L-GUJJAR", place_name="Mian Gujjar Basti",
                    incident_type="trapped_residents", required_resources=["boat", "ambulance"],
                    reasoning="Elderly dialysis patient trapped, water rising, no road access."),
        _extraction(place_id="L-GUJJAR", place_name="Mian Gujjar Basti",
                    incident_type="livestock_stranded", required_resources=["rescue_team"],
                    reasoning="Twenty buffaloes stranded in floodwater, need rescue."),
    ]
    embedder = FakeEmbedder()
    texts = [build_embedding_text(e) for e in extractions]
    embeddings = embedder.encode(texts)
    clusters = cluster_reports(extractions, embeddings)
    assert len(clusters) == 2, "same-place-different-topic reports must stay separate"


def test_cluster_different_place_stays_separate_even_if_similar():
    extractions = [_extraction(place_id="L-BRIDGE"), _extraction(place_id="L-SADIQ")]
    embeddings = [[1.0, 0.0], [0.7, 0.3]]     # moderately similar, but not enough without a place match
    clusters = cluster_reports(extractions, embeddings)
    assert len(clusters) == 2


def test_cluster_unresolved_place_needs_very_high_similarity():
    extractions = [_extraction(place_id=None), _extraction(place_id=None)]
    close = cluster_reports(extractions, [[1.0, 0.0], [0.9, 0.1]])   # sim ~0.9 > 0.80 threshold
    assert len(close) == 1
    far = cluster_reports(extractions, [[1.0, 0.0], [0.6, 0.4]])     # sim well below threshold
    assert len(far) == 2


def test_cluster_transitive_grouping_of_three_reports():
    extractions = [_extraction(place_id="L-BRIDGE") for _ in range(3)]
    embeddings = [[1.0, 0.0], [0.9, 0.1], [0.85, 0.15]]
    clusters = cluster_reports(extractions, embeddings)
    assert len(clusters) == 1
    assert set(clusters[0]) == {0, 1, 2}


def test_cluster_single_report_is_its_own_group():
    clusters = cluster_reports([_extraction()], [[1.0, 0.0]])
    assert clusters == [[0]]


# ---------------------------------------------------------- evidence confidence
def test_confidence_higher_with_more_corroboration():
    now = "2026-08-14T08:10:00+05:00"
    one = [_report(source_type="whatsapp", timestamp="2026-08-14T08:00:00+05:00")]
    five = one * 5
    assert (compute_evidence_confidence(five, now, False)
            > compute_evidence_confidence(one, now, False))


def test_confidence_higher_with_trusted_source():
    now = "2026-08-14T08:10:00+05:00"
    weak = [_report(source_type="social_media", timestamp="2026-08-14T08:00:00+05:00")]
    strong = [_report(source_type="field_officer", timestamp="2026-08-14T08:00:00+05:00")]
    assert (compute_evidence_confidence(strong, now, False)
            > compute_evidence_confidence(weak, now, False))


def test_confidence_drops_with_report_age():
    fresh = [_report(timestamp="2026-08-14T09:25:00+05:00")]
    stale = [_report(timestamp="2026-08-14T06:00:00+05:00")]
    now = "2026-08-14T09:30:00+05:00"
    assert (compute_evidence_confidence(fresh, now, False)
            > compute_evidence_confidence(stale, now, False))


def test_confidence_drops_sharply_with_conflict():
    reports = [_report(source_type="field_officer"), _report(source_type="field_officer")]
    now = "2026-08-14T08:10:00+05:00"
    assert (compute_evidence_confidence(reports, now, False)
            > compute_evidence_confidence(reports, now, True))


def test_confidence_is_always_a_valid_percentage():
    now = "2026-08-14T09:30:00+05:00"
    lo = compute_evidence_confidence(
        [_report(source_type="social_media", timestamp="2026-08-14T06:00:00+05:00")], now, True)
    hi = compute_evidence_confidence(
        [_report(source_type="field_officer", image_id="IMG-01")] * 6, now, False)
    assert 0 <= lo <= 100 and 0 <= hi <= 100
    assert hi > lo


# --------------------------------------------------------------- conflict detection
def test_detect_conflict_skips_llm_for_single_report():
    fake = FakeLLM({"conflict_detected": True, "conflict_note": "should never be seen"})
    detected, note = detect_conflict([_report()], llm_client=fake)
    assert detected is False
    assert note is None
    assert fake.calls == []


def test_detect_conflict_reports_true_with_note():
    fake = FakeLLM({"conflict_detected": True, "conflict_note": "One report claims a breach; another says only a crack."})
    detected, note = detect_conflict([_report(), _report()], llm_client=fake)
    assert detected is True
    assert "crack" in note


def test_detect_conflict_reports_false():
    fake = FakeLLM({"conflict_detected": False, "conflict_note": None})
    detected, note = detect_conflict([_report(), _report()], llm_client=fake)
    assert detected is False
    assert note is None


def test_detect_conflict_llm_failure_defaults_to_no_conflict():
    from llm.client import LLMError
    fake = FakeLLM(LLMError("simulated failure"))
    detected, note = detect_conflict([_report(), _report()], llm_client=fake)
    assert detected is False
    assert note is None


# --------------------------------------------------------------------- merging
def test_merge_cluster_unions_resources_and_maxes_severity():
    reports = [_report(id="R-1", source_type="whatsapp"), _report(id="R-2", source_type="field_officer")]
    extractions = [
        _extraction(required_resources=["boat"], medical_severity=1, isolation=1, vulnerable_people=0),
        _extraction(required_resources=["medical_team"], medical_severity=2, isolation=2, vulnerable_people=1),
    ]
    merged = merge_cluster(reports, extractions)
    assert merged["required_resources"] == ["boat", "medical_team"]
    assert merged["medical_severity"] == 2
    assert merged["isolation"] == 2
    assert merged["report_count"] == 2
    assert merged["report_ids"] == ["R-1", "R-2"]


def test_merge_cluster_trusts_the_best_source_for_headcount():
    """A field officer's counted 40 should win over a passer-by's vague guess."""
    reports = [_report(id="R-1", source_type="social_media"), _report(id="R-2", source_type="field_officer")]
    extractions = [
        _extraction(estimated_affected=15, place_id=None, place_name=None),
        _extraction(estimated_affected=40, place_id="L-BRIDGE", place_name="Kabul River Bridge"),
    ]
    merged = merge_cluster(reports, extractions)
    assert merged["estimated_affected"] == 40
    assert merged["place_id"] == "L-BRIDGE"


def test_merge_cluster_majority_vote_on_incident_type():
    reports = [_report(id=f"R-{i}") for i in range(3)]
    extractions = [
        _extraction(incident_type="trapped_residents"),
        _extraction(incident_type="trapped_residents"),
        _extraction(incident_type="road_blocked"),
    ]
    merged = merge_cluster(reports, extractions)
    assert merged["incident_type"] == "trapped_residents"


# -------------------------------------------------------------- verify_reports
def test_verify_reports_clusters_the_seven_bridge_reports_into_one(db):
    def fake_intake_answer(prompt, system):
        return {
            "incident_type": "trapped_residents", "location_text": "Kabul River Bridge",
            "estimated_affected": 40, "vulnerable_people": 1, "medical_emergency": True,
            "medical_severity": 2, "required_resources": ["boat", "medical_team"],
            "isolation": 2, "reasoning": "Bridge flood, people trapped, pregnant woman needs help.",
        }
    fake_intake_llm = FakeLLM(fake_intake_answer)
    fake_conflict_llm = FakeLLM({"conflict_detected": False, "conflict_note": None})

    demo_reports = list_reports(db, status="queued")
    assert len(demo_reports) == 7

    intake_results = [run_intake(r, conn=db, llm_client=fake_intake_llm) for r in demo_reports]
    results = verify_reports(demo_reports, db, llm_client=fake_conflict_llm,
                              embedder=FakeEmbedder(), intake_results=intake_results)

    assert len(results) == 1, "all seven bridge reports should form exactly one cluster"
    cluster = results[0]
    assert cluster["merged"]["report_count"] == 7
    assert cluster["merged"]["place_id"] == "L-BRIDGE"
    assert cluster["merged"]["medical_emergency"] is True
    assert 0 <= cluster["evidence_confidence"] <= 100
    assert cluster["conflict_detected"] is False


def test_verify_reports_keeps_gujjar_hard_negative_separate(db):
    """Reuses the real baseline reports for INC-003 (trapped family, dialysis
    patient) and INC-019 (stranded livestock) — same place, different topics —
    and confirms the Verification Agent keeps them apart, using the real
    FakeEmbedder (feature hashing) rather than hand-crafted vectors."""
    gujjar_reports = [r for r in list_reports(db) if r["id"] in ("R-016", "R-048")]
    assert len(gujjar_reports) == 2

    def fake_intake_answer(prompt, system):
        if "buffal" in prompt.lower() or "بھینس" in prompt:
            return {"incident_type": "livestock_stranded", "location_text": "Mian Gujjar Basti",
                     "estimated_affected": 0, "vulnerable_people": 0, "medical_emergency": False,
                     "medical_severity": 0, "required_resources": ["rescue_team"], "isolation": 1,
                     "reasoning": "Twenty buffaloes stranded in floodwater, need rescue."}
        return {"incident_type": "trapped_residents", "location_text": "Mian Gujjar Basti",
                 "estimated_affected": 25, "vulnerable_people": 3, "medical_emergency": True,
                 "medical_severity": 2, "required_resources": ["boat", "ambulance"], "isolation": 2,
                 "reasoning": "Elderly dialysis patient trapped, water rising, no road access."}

    fake_intake_llm = FakeLLM(fake_intake_answer)
    intake_results = [run_intake(r, conn=db, llm_client=fake_intake_llm) for r in gujjar_reports]
    assert intake_results[0]["place_id"] == "L-GUJJAR"
    assert intake_results[1]["place_id"] == "L-GUJJAR"

    results = verify_reports(gujjar_reports, db, llm_client=FakeLLM({}),
                              embedder=FakeEmbedder(), intake_results=intake_results)
    assert len(results) == 2, "trapped family vs. stranded livestock must not be merged"


def test_verify_reports_returns_empty_list_for_no_reports(db):
    assert verify_reports([], db) == []




# ------------------------------------------------- merge_related_clusters_at_same_place
def test_merge_related_clusters_merges_when_llm_confirms_same_incident():
    """Reconstructs a real finding from a live Phase 8 test run: one bridge
    report about a blocked road fell below the similarity threshold against
    the rest of the bridge cluster (0.51 vs. a 0.60 bar) and formed its own
    cluster. The LLM adjudication pass should recombine it."""
    now = "2026-08-14T09:30:00+05:00"
    orphan = {
        "reports": [_report(id="R-001", timestamp="2026-08-14T08:41:00+05:00")],
        "extractions": [_extraction(incident_type="road_blocked", required_resources=["dewatering_pump"],
                                     estimated_affected=0, medical_emergency=False, medical_severity=0)],
        "merged": {"place_id": "L-BRIDGE", "report_count": 1},
        "evidence_confidence": 41, "conflict_detected": False, "conflict_note": None,
    }
    main = {
        "reports": [_report(id=f"R-{i}", timestamp="2026-08-14T09:05:00+05:00") for i in range(2, 8)],
        "extractions": [_extraction() for _ in range(6)],
        "merged": {"place_id": "L-BRIDGE", "report_count": 6},
        "evidence_confidence": 85, "conflict_detected": False, "conflict_note": None,
    }
    fake = FakeLLM({"same_incident": True, "reason": "Both describe the same bridge flooding event."})
    results = merge_related_clusters_at_same_place([orphan, main], now, llm_client=fake)
    assert len(results) == 1
    assert results[0]["merged"]["report_count"] == 7
    assert results[0]["merged"]["report_ids"].count("R-001") == 1


def test_merge_related_clusters_keeps_separate_when_llm_says_different_incidents():
    """The Mian Gujjar Basti hard negative, reconstructed as two singleton
    clusters at the same place — the LLM must keep them apart."""
    now = "2026-08-14T09:30:00+05:00"
    dialysis = {
        "reports": [_report(id="R-016", timestamp="2026-08-14T08:00:00+05:00")],
        "extractions": [_extraction(incident_type="trapped_residents", place_id="L-GUJJAR")],
        "merged": {"place_id": "L-GUJJAR", "report_count": 1},
        "evidence_confidence": 52, "conflict_detected": False, "conflict_note": None,
    }
    livestock = {
        "reports": [_report(id="R-048", timestamp="2026-08-14T07:20:00+05:00")],
        "extractions": [_extraction(incident_type="livestock_stranded", place_id="L-GUJJAR")],
        "merged": {"place_id": "L-GUJJAR", "report_count": 1},
        "evidence_confidence": 34, "conflict_detected": False, "conflict_note": None,
    }
    fake = FakeLLM({"same_incident": False, "reason": "One is about people, the other about livestock."})
    results = merge_related_clusters_at_same_place([dialysis, livestock], now, llm_client=fake)
    assert len(results) == 2
    assert len(fake.calls) == 1


def test_merge_related_clusters_never_calls_llm_for_different_places():
    now = "2026-08-14T09:30:00+05:00"
    a = {"reports": [_report(id="R-A")], "extractions": [_extraction(place_id="L-BRIDGE")],
         "merged": {"place_id": "L-BRIDGE", "report_count": 1},
         "evidence_confidence": 50, "conflict_detected": False, "conflict_note": None}
    b = {"reports": [_report(id="R-B")], "extractions": [_extraction(place_id="L-SADIQ")],
         "merged": {"place_id": "L-SADIQ", "report_count": 1},
         "evidence_confidence": 50, "conflict_detected": False, "conflict_note": None}
    fake = FakeLLM({"same_incident": True, "reason": "n/a"})
    results = merge_related_clusters_at_same_place([a, b], now, llm_client=fake)
    assert len(results) == 2
    assert fake.calls == []


def test_verify_reports_full_pipeline_recovers_one_bridge_incident_via_merge_pass(db):
    """End-to-end reconstruction of the real live-run finding: the embedding
    pass alone splits the 7 bridge reports into 2 clusters (one report about
    a blocked road, six about trapped people); the LLM adjudication pass
    should recombine them into one incident."""
    demo_reports = list_reports(db, status="queued")
    assert [r["id"] for r in demo_reports][0] == "R-001"

    def fake_intake_answer(prompt, system):
        if "cannot pass" in prompt.lower():
            return {"incident_type": "road_blocked", "location_text": "Kabul River Bridge",
                     "estimated_affected": 0, "vulnerable_people": 0, "medical_emergency": False,
                     "medical_severity": 0, "required_resources": ["dewatering_pump"], "isolation": 0,
                     "reasoning": "Bridge flooded, cars cannot pass."}
        return {"incident_type": "trapped_residents", "location_text": "Kabul River Bridge",
                 "estimated_affected": 40, "vulnerable_people": 1, "medical_emergency": True,
                 "medical_severity": 2, "required_resources": ["boat", "medical_team"], "isolation": 2,
                 "reasoning": "Bridge flood, people trapped, pregnant woman needs help."}

    intake_results = [run_intake(r, conn=db, llm_client=FakeLLM(fake_intake_answer)) for r in demo_reports]
    assert all(e["place_id"] == "L-BRIDGE" for e in intake_results)

    # Reconstructs the real measured structure: report 0 (R-001) at ~0.51
    # similarity to the rest (below the 0.60 threshold); the other six at
    # 1.0 similarity to each other (above it).
    vectors = [[1.0, 0.0]] + [[0.51, 0.860]] * 6
    embedder = PositionalEmbedder(vectors)
    merge_llm = FakeLLM({"same_incident": True, "reason": "Both describe the same bridge flooding event."})

    results = verify_reports(demo_reports, db, llm_client=merge_llm,
                              embedder=embedder, intake_results=intake_results)

    assert len(results) == 1, "the LLM adjudication pass should recombine the split-off report"
    assert results[0]["merged"]["report_count"] == 7
    assert "R-001" in results[0]["merged"]["report_ids"]