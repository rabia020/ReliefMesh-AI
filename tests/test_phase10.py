"""Automated tests for Phase 10 (Priority Agent). Purely deterministic
arithmetic — no LLM, no network, no database needed."""

from agents.priority_agent import (
    assign_priority,
    compute_priority_score,
    priority_label,
)
from dataset.incidents import INCIDENTS

ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}


def _incident(**overrides):
    base = {
        "incident_type": "trapped_residents", "estimated_affected": 10,
        "vulnerable_people": 0, "medical_emergency": False, "medical_severity": 0,
        "isolation": 0, "evidence_confidence": 100,
    }
    base.update(overrides)
    return base


# ------------------------------------------------------------------- basics
def test_score_is_always_a_valid_percentage():
    for ov in ({}, {"estimated_affected": 10000}, {"evidence_confidence": -50},
               {"evidence_confidence": 500}, {"vulnerable_people": -5}):
        score = compute_priority_score(_incident(**ov))
        assert 0 <= score <= 100


def test_assign_priority_returns_both_fields():
    result = assign_priority(_incident(medical_emergency=True, medical_severity=3))
    assert set(result) == {"priority_score", "priority"}
    assert result["priority"] in ("Critical", "High", "Medium", "Low")


def test_priority_label_boundaries():
    assert priority_label(60) == "Critical"
    assert priority_label(59) == "High"
    assert priority_label(33) == "High"
    assert priority_label(32) == "Medium"
    assert priority_label(14) == "Medium"
    assert priority_label(13) == "Low"
    assert priority_label(0) == "Low"


# --------------------------------------------------------- behavior rules
def test_life_threatening_medical_need_is_critical_even_with_one_person():
    """One person with a life-threatening injury must not be deprioritized
    just because only one person is affected (the Old Bus Stand wall
    collapse, INC-004, is exactly this case)."""
    result = assign_priority(_incident(
        incident_type="medical_emergency", estimated_affected=1, vulnerable_people=0,
        medical_emergency=True, medical_severity=3, isolation=0, evidence_confidence=85,
    ))
    assert result["priority"] == "Critical"


def test_missing_person_is_urgent_despite_tiny_headcount():
    """A missing child (1 affected, no medical flag at all) must not score
    near zero just because the numeric fields are all small."""
    result = assign_priority(_incident(
        incident_type="missing_person", estimated_affected=1, vulnerable_people=1,
        medical_emergency=False, medical_severity=0, isolation=0, evidence_confidence=75,
    ))
    assert result["priority_score"] >= 33   # at least High


def test_large_headcount_alone_does_not_force_critical():
    """200 people with no medical emergency and no isolation (e.g. a water
    shortage) should NOT automatically outrank a smaller, more urgent case."""
    result = assign_priority(_incident(
        incident_type="food_water_shortage", estimated_affected=200, vulnerable_people=30,
        medical_emergency=False, medical_severity=0, isolation=1, evidence_confidence=85,
    ))
    assert result["priority"] != "Critical"


def test_more_affected_people_never_lowers_the_score():
    low = compute_priority_score(_incident(estimated_affected=5))
    high = compute_priority_score(_incident(estimated_affected=50))
    assert high >= low


def test_higher_medical_severity_never_lowers_the_score():
    scores = [compute_priority_score(_incident(medical_emergency=True, medical_severity=s))
              for s in (0, 1, 2, 3)]
    assert scores == sorted(scores)


def test_more_isolation_never_lowers_the_score():
    scores = [compute_priority_score(_incident(isolation=i)) for i in (0, 1, 2)]
    assert scores == sorted(scores)


def test_lower_confidence_never_raises_the_score():
    high_conf = compute_priority_score(_incident(medical_emergency=True, medical_severity=3,
                                                   evidence_confidence=90))
    low_conf = compute_priority_score(_incident(medical_emergency=True, medical_severity=3,
                                                  evidence_confidence=10))
    assert low_conf < high_conf


def test_unverified_rumor_scores_low_despite_high_claimed_severity():
    """INC-020: a social-media dam-burst rumor refuted by a field officer.
    Even with a severe incident_type guess, very low confidence should pull
    it down to Low."""
    result = assign_priority(_incident(
        incident_type="structural_damage", estimated_affected=0, vulnerable_people=0,
        medical_emergency=False, medical_severity=0, isolation=0, evidence_confidence=10,
    ))
    assert result["priority"] == "Low"


def test_unknown_incident_type_does_not_crash():
    result = assign_priority(_incident(incident_type="something_not_in_the_table"))
    assert result["priority"] in ("Critical", "High", "Medium", "Low")


def test_missing_optional_fields_default_safely():
    assert assign_priority({"incident_type": "trapped_residents"})["priority"] in (
        "Critical", "High", "Medium", "Low")


# -------------------------------------------- calibration against ground truth
def test_calibration_against_the_20_reference_incidents():
    """Doesn't require an exact match (dataset/build.py's own comments say
    expected_priority is a reference label the agent independently
    recomputes), but holds the formula to two concrete bars: it must
    separate all 5 true-Critical incidents from everything else perfectly
    (the one distinction that matters most for safety), and it must never
    be off by more than one priority tier for any incident."""
    exact = 0
    for inc in INCIDENTS:
        lo, hi = inc["expected_confidence_range"]
        confidence = (lo + hi) / 2
        predicted = assign_priority({
            "incident_type": inc["incident_type"],
            "estimated_affected": inc["estimated_affected"],
            "vulnerable_people": inc["vulnerable_people"],
            "medical_emergency": inc["medical_emergency"],
            "medical_severity": inc["medical_severity"],
            "isolation": inc["isolation"],
            "evidence_confidence": confidence,
        })["priority"]
        true = inc["expected_priority"]
        diff = abs(ORDER[predicted] - ORDER[true])
        assert diff <= 1, f"{inc['id']}: predicted {predicted}, true {true} (off by {diff} tiers)"
        exact += diff == 0
    assert exact >= 16, f"expected at least 16/20 exact matches, got {exact}/20"


def test_all_true_critical_incidents_score_above_all_others():
    """The single most important property: nothing non-Critical should ever
    outscore a genuinely Critical incident."""
    critical_scores, other_scores = [], []
    for inc in INCIDENTS:
        lo, hi = inc["expected_confidence_range"]
        score = compute_priority_score({
            "incident_type": inc["incident_type"],
            "estimated_affected": inc["estimated_affected"],
            "vulnerable_people": inc["vulnerable_people"],
            "medical_emergency": inc["medical_emergency"],
            "medical_severity": inc["medical_severity"],
            "isolation": inc["isolation"],
            "evidence_confidence": (lo + hi) / 2,
        })
        (critical_scores if inc["expected_priority"] == "Critical" else other_scores).append(score)
    assert min(critical_scores) > max(other_scores)