"""Automated tests for Phase 11 (Resource Agent). Deterministic — no LLM,
no network. Uses the real seeded database for realistic resource data."""

import pytest

from agents.resource_agent import haversine_km, rank_resources, recommend_for_incident
from database.connection import get_connection
from database.queries import get_incident, list_resources, list_shelters
from database.seed import init_database


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "test.db"
    init_database(path)
    conn = get_connection(path)
    yield conn
    conn.close()


def _resource(**overrides):
    base = {
        "id": "R-1", "name": "Test Resource", "type": "boat", "status": "available",
        "lat": 34.0, "lon": 72.0, "crew_size": 3, "capacity_people": 10, "capabilities": [],
    }
    base.update(overrides)
    return base


def _incident(**overrides):
    base = {
        "lat": 34.0, "lon": 72.0, "required_resources": [], "estimated_affected": 10,
        "medical_emergency": False, "vulnerable_people": 0, "isolation": 0,
    }
    base.update(overrides)
    return base


# ------------------------------------------------------------------- distance
def test_haversine_zero_distance_for_same_point():
    assert haversine_km(34.0, 72.0, 34.0, 72.0) == 0.0


def test_haversine_known_rough_distance():
    # Roughly 1 degree of latitude is about 111 km.
    d = haversine_km(34.0, 72.0, 35.0, 72.0)
    assert 108 <= d <= 113


# -------------------------------------------------------------- rank_resources
def test_closer_available_resource_ranks_first():
    incident = _incident()
    near = _resource(id="R-near", lat=34.001, lon=72.001)
    far = _resource(id="R-far", lat=34.5, lon=72.5)
    ranked = rank_resources(incident, [far, near])
    assert ranked[0]["id"] == "R-near"


def test_unavailable_resource_always_ranks_below_available_ones():
    incident = _incident()
    close_but_deployed = _resource(id="R-deployed", status="deployed", lat=34.0, lon=72.0)
    far_but_available = _resource(id="R-available", status="available", lat=34.3, lon=72.3)
    ranked = rank_resources(incident, [close_but_deployed, far_but_available])
    assert ranked[0]["id"] == "R-available"
    assert ranked[0]["available"] is True
    assert ranked[1]["available"] is False
    assert ranked[1]["suitability_score"] == 0.0


def test_maintenance_resource_is_included_but_unavailable():
    incident = _incident()
    ranked = rank_resources(incident, [_resource(status="maintenance")])
    assert ranked[0]["available"] is False


def test_higher_capacity_breaks_a_near_tie_in_distance():
    incident = _incident(estimated_affected=20)
    small = _resource(id="R-small", capacity_people=5, lat=34.001, lon=72.001)
    big = _resource(id="R-big", capacity_people=20, lat=34.001, lon=72.001)
    ranked = rank_resources(incident, [small, big])
    assert ranked[0]["id"] == "R-big"


def test_maternity_capability_bonus_for_pregnant_related_need():
    incident = _incident(medical_emergency=True, vulnerable_people=1)
    plain = _resource(id="R-plain", capabilities=["patient_transport"])
    maternity = _resource(id="R-maternity", capabilities=["patient_transport", "maternity_transport"])
    ranked = rank_resources(incident, [plain, maternity])
    assert ranked[0]["id"] == "R-maternity"


def test_empty_candidate_list_returns_empty():
    assert rank_resources(_incident(), []) == []


# --------------------------------------------------------- recommend_for_incident
def test_recommend_flags_unsupported_needs_honestly():
    result = recommend_for_incident(
        _incident(required_resources=["engineering_team", "dewatering_pump"]), [], [])
    assert result["engineering_team"]["supported"] is False
    assert "engineering_team" in result["engineering_team"]["message"]
    assert result["dewatering_pump"]["supported"] is False


def test_recommend_flags_unknown_need():
    result = recommend_for_incident(_incident(required_resources=["helicopter"]), [], [])
    assert result["helicopter"]["supported"] is False


def test_recommend_routes_shelter_need_to_shelters_table_not_resources():
    shelters = [
        {"id": "S-1", "name": "Full Shelter", "lat": 34.0, "lon": 72.0,
         "capacity": 10, "current_occupancy": 10, "status": "open"},
        {"id": "S-2", "name": "Roomy Shelter", "lat": 34.01, "lon": 72.01,
         "capacity": 100, "current_occupancy": 5, "status": "open"},
        {"id": "S-3", "name": "Closed Shelter", "lat": 34.0, "lon": 72.0,
         "capacity": 100, "current_occupancy": 0, "status": "closed"},
    ]
    result = recommend_for_incident(
        _incident(required_resources=["shelter"], estimated_affected=20), [], shelters)
    candidates = result["shelter"]["candidates"]
    assert {c["id"] for c in candidates} == {"S-1", "S-2"}          # closed shelter excluded
    assert candidates[0]["id"] == "S-2"                             # has room, ranks first
    assert candidates[0]["has_room"] is True
    full = next(c for c in candidates if c["id"] == "S-1")
    assert full["has_room"] is False


def test_recommend_handles_multiple_needs_at_once():
    resources = [_resource(id="R-boat", type="boat"), _resource(id="R-amb", type="ambulance")]
    result = recommend_for_incident(
        _incident(required_resources=["boat", "ambulance", "shelter"]), resources, [])
    assert set(result) == {"boat", "ambulance", "shelter"}
    assert result["boat"]["candidates"][0]["id"] == "R-boat"
    assert result["ambulance"]["candidates"][0]["id"] == "R-amb"
    assert result["shelter"]["candidates"] == []    # no shelters passed in


def test_recommend_no_candidates_of_a_type_returns_empty_list_not_error():
    result = recommend_for_incident(_incident(required_resources=["medical_team"]), [], [])
    assert result["medical_team"]["supported"] is True
    assert result["medical_team"]["candidates"] == []


# ---------------------------------------------------------- real database checks
def test_sadiq_abad_recommends_available_boats_not_the_one_in_maintenance(db):
    incident = get_incident(db, "INC-002")        # needs boat + medical_team
    resources = list_resources(db)
    result = recommend_for_incident(incident, resources, [])
    boat_ids = [c["id"] for c in result["boat"]["candidates"]]
    assert "BT-3" in boat_ids                      # shown for visibility...
    bt3 = next(c for c in result["boat"]["candidates"] if c["id"] == "BT-3")
    assert bt3["available"] is False                # ...but correctly marked unavailable
    assert result["boat"]["candidates"][0]["available"] is True
    assert result["boat"]["candidates"][0]["id"] in ("BT-1", "BT-2")


def test_gulshan_shelter_recommendation_from_real_data(db):
    incident = get_incident(db, "INC-007")         # needs shelter + relief_supplies
    shelters = list_shelters(db)
    result = recommend_for_incident(incident, [], shelters)
    assert result["shelter"]["supported"] is True
    assert len(result["shelter"]["candidates"]) > 0
    assert result["relief_supplies"]["supported"] is False


def test_every_baseline_incident_runs_without_crashing(db):
    from database.queries import list_incidents
    resources = list_resources(db)
    shelters = list_shelters(db)
    for inc in list_incidents(db):
        full = get_incident(db, inc["id"])
        result = recommend_for_incident(full, resources, shelters)
        assert set(result) == set(full["required_resources"])