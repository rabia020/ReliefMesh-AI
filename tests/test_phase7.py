"""Automated tests for Phase 7 (Intake Agent). No real Gemini calls are made:
every test either checks the pure validation logic or injects a fake LLM client."""

import pytest

from agents.gazetteer import load_places, match_location
from agents.intake_agent import run_intake
from agents.schemas import normalize_extraction
from database.connection import get_connection
from database.queries import list_reports
from database.seed import init_database
from llm.client import LLMError


class FakeLLM:
    """A stand-in for llm.client.LLMClient. complete_json_return can be a dict
    (always returned) or a callable taking the prompt/system and returning one,
    or an exception instance/class to simulate a failure."""

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


def _report(**overrides):
    base = {
        "id": "R-TEST", "timestamp": "2026-08-14T08:00:00+05:00", "language": "en",
        "source_type": "whatsapp", "text": "Something happened.", "structured": None,
    }
    base.update(overrides)
    return base


# --------------------------------------------------------- normalize_extraction
def test_normalize_valid_input_passes_through_unchanged():
    raw = {
        "incident_type": "trapped_residents", "location_text": "Kabul River Bridge",
        "estimated_affected": 40, "vulnerable_people": 1, "medical_emergency": True,
        "medical_severity": 2, "required_resources": ["boat", "medical_team"],
        "isolation": 2, "reasoning": "flood",
    }
    clean, notes = normalize_extraction(raw)
    assert clean["incident_type"] == "trapped_residents"
    assert clean["estimated_affected"] == 40
    assert clean["required_resources"] == ["boat", "medical_team"]
    assert notes == []


def test_normalize_rejects_unknown_incident_type():
    clean, notes = normalize_extraction({"incident_type": "zombie_attack"})
    assert clean["incident_type"] == "trapped_residents"          # safe default
    assert any("not a known type" in n for n in notes)


def test_normalize_clamps_negative_and_non_numeric_counts():
    clean, notes = normalize_extraction({"estimated_affected": -5, "vulnerable_people": "many"})
    assert clean["estimated_affected"] == 0
    assert clean["vulnerable_people"] == 0
    assert any("estimated_affected" in n for n in notes)
    assert any("vulnerable_people" in n for n in notes)


def test_normalize_caps_vulnerable_people_to_affected():
    clean, notes = normalize_extraction({"estimated_affected": 5, "vulnerable_people": 20})
    assert clean["vulnerable_people"] == 5
    assert any("capped" in n for n in notes)


def test_normalize_drops_unknown_resource_needs():
    clean, notes = normalize_extraction({"required_resources": ["boat", "helicopter", "boat"]})
    assert clean["required_resources"] == ["boat"]
    assert any("helicopter" in n for n in notes)


def test_normalize_fixes_inconsistent_medical_flags():
    clean, _ = normalize_extraction({"medical_emergency": True, "medical_severity": 0})
    assert clean["medical_severity"] == 1

    clean2, _ = normalize_extraction({"medical_emergency": False, "medical_severity": 3})
    assert clean2["medical_emergency"] is True


def test_normalize_handles_completely_empty_input():
    clean, notes = normalize_extraction({})
    assert clean["incident_type"] == "trapped_residents"
    assert clean["estimated_affected"] == 0
    assert clean["required_resources"] == []
    assert len(notes) > 0


def test_normalize_handles_non_dict_input():
    clean, notes = normalize_extraction(None)
    assert clean["incident_type"] == "trapped_residents"


# --------------------------------------------------------------------- gazetteer
def test_gazetteer_exact_alias_match(db):
    places = load_places(db)
    result = match_location("pul", places)
    assert result["place_id"] == "L-BRIDGE"
    assert result["confidence"] == "exact"


def test_gazetteer_containment_match_with_extra_words(db):
    places = load_places(db)
    result = match_location("near the Kabul River Bridge east bank", places)
    assert result["place_id"] == "L-BRIDGE"
    assert result["confidence"] == "contains"


def test_gazetteer_matches_roman_urdu_alias(db):
    places = load_places(db)
    result = match_location("Sadiq Abad village", places)
    assert result["place_id"] == "L-SADIQ"


def test_gazetteer_matches_urdu_script(db):
    places = load_places(db)
    result = match_location("پل", places)
    assert result["place_id"] == "L-BRIDGE"


def test_gazetteer_fuzzy_match_on_typo(db):
    places = load_places(db)
    result = match_location("sadiq abd village", places)   # missing an 'a'
    assert result["place_id"] == "L-SADIQ"
    assert result["confidence"] == "fuzzy"


def test_gazetteer_no_match_for_nonsense(db):
    places = load_places(db)
    result = match_location("somewhere completely unrelated xyz", places)
    assert result["place_id"] is None
    assert result["confidence"] is None


def test_gazetteer_empty_text(db):
    places = load_places(db)
    result = match_location("", places)
    assert result["place_id"] is None


# ------------------------------------------------------------------ run_intake
def test_run_intake_end_to_end_clean_llm_output(db):
    report = _report(
        text="Bridge flooded, people stuck near the river bridge.", language="en",
    )
    fake = FakeLLM({
        "incident_type": "trapped_residents", "location_text": "Kabul River Bridge",
        "estimated_affected": 40, "vulnerable_people": 1, "medical_emergency": True,
        "medical_severity": 2, "required_resources": ["boat", "medical_team"],
        "isolation": 2, "reasoning": "Bridge flooding, people trapped.",
    })
    result = run_intake(report, conn=db, llm_client=fake)

    assert result["report_id"] == "R-TEST"
    assert result["language"] == "en"
    assert result["incident_type"] == "trapped_residents"
    assert result["place_id"] == "L-BRIDGE"
    assert result["place_match_confidence"] == "exact"    # "Kabul River Bridge" is the place's own name
    assert result["extraction_notes"] == []
    assert len(fake.calls) == 1
    assert "SYSTEM" not in fake.calls[0]["prompt"]  # system goes in `system`, not the prompt


def test_run_intake_cleans_messy_llm_output(db):
    report = _report(text="Something vague happened somewhere.")
    fake = FakeLLM({
        "incident_type": "meteor_strike",           # invalid
        "location_text": "", "estimated_affected": -3, "vulnerable_people": 900,
        "medical_emergency": "yes", "medical_severity": 99,
        "required_resources": ["boat", "spaceship"], "isolation": -1,
    })
    result = run_intake(report, conn=db, llm_client=fake)

    assert result["incident_type"] == "trapped_residents"       # corrected
    assert result["estimated_affected"] == 0
    assert result["medical_emergency"] is True
    assert result["medical_severity"] == 3
    assert result["required_resources"] == ["boat"]
    assert result["isolation"] == 0
    assert result["place_id"] is None
    assert len(result["extraction_notes"]) >= 5


def test_run_intake_handles_llm_failure_gracefully(db):
    report = _report()
    fake = FakeLLM(LLMError("simulated network failure"))
    result = run_intake(report, conn=db, llm_client=fake)

    assert result["incident_type"] == "trapped_residents"       # safe default, no crash
    assert any("LLM extraction failed" in n for n in result["extraction_notes"])


def test_run_intake_without_db_connection_skips_place_matching():
    report = _report()
    fake = FakeLLM({"incident_type": "trapped_residents", "location_text": "somewhere"})
    result = run_intake(report, conn=None, llm_client=fake)
    assert result["place_id"] is None
    assert result["place_match_confidence"] is None


def test_run_intake_overrides_with_structured_form_data(db):
    """Reproduces the real R-006 field form: the LLM might guess a lower
    headcount from the prose, but the structured form's counted numbers win."""
    report = _report(
        id="R-006", language="en", source_type="field_officer",
        text="FIELD FORM: Kabul River Bridge, east bank. 40 people stranded "
             "including 1 pregnant woman. Water 3 ft and rising.",
        structured={
            "location_text": "Kabul River Bridge, east bank", "people_affected": 40,
            "vulnerable_people": 1, "medical_emergency": True,
            "needs": ["boat", "medical_team"], "water_depth_ft": 3,
        },
    )
    fake = FakeLLM({
        "incident_type": "trapped_residents", "location_text": "the bridge",
        "estimated_affected": 15, "vulnerable_people": 0,          # LLM underestimates
        "medical_emergency": False, "medical_severity": 0,
        "required_resources": ["rescue_team"], "isolation": 2,
    })
    result = run_intake(report, conn=db, llm_client=fake)

    assert result["estimated_affected"] == 40                     # structured form wins
    assert result["vulnerable_people"] == 1
    assert result["medical_emergency"] is True
    assert result["medical_severity"] >= 2
    assert set(result["required_resources"]) == {"rescue_team", "boat", "medical_team"}
    assert any("overridden by structured form" in n for n in result["extraction_notes"])


def test_run_intake_on_all_seven_demo_reports_with_fake_llm(db):
    """Confirms the agent can run over every queued demo report without crashing,
    using a fake LLM that gives a plausible bridge-incident extraction each time."""
    def fake_answer(prompt, system):
        return {
            "incident_type": "trapped_residents", "location_text": "Kabul River Bridge",
            "estimated_affected": 40, "vulnerable_people": 1, "medical_emergency": True,
            "medical_severity": 2, "required_resources": ["boat", "medical_team"],
            "isolation": 2, "reasoning": "Bridge flood report.",
        }
    fake = FakeLLM(fake_answer)
    demo_reports = list_reports(db, status="queued")
    assert len(demo_reports) == 7

    results = [run_intake(r, conn=db, llm_client=fake) for r in demo_reports]
    assert all(r["place_id"] == "L-BRIDGE" for r in results)
    assert [r["report_id"] for r in results] == [f"R-00{i}" for i in range(1, 8)]