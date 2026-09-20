"""Automated tests for Phase 2 (synthetic disaster dataset)."""

import json
import re
from collections import Counter
from datetime import datetime

import pytest

from database.generate_dataset import DATA_DIR, build_dataset

ARABIC_SCRIPT = re.compile(r"[\u0600-\u06FF]")
LAT_RANGE = (31.55, 31.65)
LON_RANGE = (74.25, 74.36)


def load(name):
    path = DATA_DIR / f"{name}.json"
    assert path.exists(), f"{path} is missing. Run: python -m database.generate_dataset"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def meta():
    return load("meta")


@pytest.fixture(scope="module")
def reports():
    return load("reports")


@pytest.fixture(scope="module")
def incidents():
    return load("incidents")


@pytest.fixture(scope="module")
def resources():
    return load("resources")


@pytest.fixture(scope="module")
def shelters():
    return load("shelters")


@pytest.fixture(scope="module")
def hospitals():
    return load("hospitals")


@pytest.fixture(scope="module")
def roads():
    return load("blocked_roads")


def free_beds(shelter):
    """Free space in a shelter (0 if it is full or closed)."""
    if shelter["status"] != "open":
        return 0
    return shelter["capacity"] - shelter["current_occupancy"]


def test_record_counts(reports, incidents, resources, shelters, hospitals, roads):
    assert len(reports) == 50
    assert len(incidents) == 20
    assert len(resources) == 10
    assert len(shelters) == 8
    assert len(hospitals) == 5
    assert len(roads) == 4


def test_unique_ids(reports, incidents, resources, shelters, hospitals, roads):
    groups = [
        (reports, "report_id"), (incidents, "incident_id"), (resources, "resource_id"),
        (shelters, "shelter_id"), (hospitals, "hospital_id"), (roads, "road_id"),
    ]
    for records, key in groups:
        ids = [record[key] for record in records]
        assert len(ids) == len(set(ids)), f"Duplicate values found in {key}"


def test_languages(reports):
    counts = Counter(r["language"] for r in reports)
    assert counts["en"] >= 20
    assert counts["roman_ur"] >= 15
    assert counts["ur"] >= 8
    # Urdu-script text must be labelled "ur"; English/Roman Urdu must have no Urdu script.
    for r in reports:
        has_urdu_script = bool(ARABIC_SCRIPT.search(r["text"]))
        assert has_urdu_script == (r["language"] == "ur"), r["report_id"]


def test_every_report_links_to_an_incident(reports, incidents):
    incident_ids = {i["incident_id"] for i in incidents}
    for r in reports:
        assert r["true_incident_id"] in incident_ids
    for i in incidents:
        linked = [r["report_id"] for r in reports if r["true_incident_id"] == i["incident_id"]]
        assert len(linked) >= 2, f"{i['incident_id']} has fewer than 2 reports"
        assert linked == i["report_ids"]


def test_duplicate_clusters_exist(incidents):
    sizes = {i["incident_id"]: len(i["report_ids"]) for i in incidents}
    assert sizes["INC-101"] == 6
    assert sum(1 for size in sizes.values() if size >= 3) >= 7


def test_conflicts_and_rumours(reports):
    labels = Counter(r["label"] for r in reports)
    assert labels["conflicting"] >= 3
    assert labels["rumor"] >= 1
    assert labels["correction"] >= 1


def test_stale_report_is_old(reports, meta):
    now = datetime.fromisoformat(meta["scenario_now"])
    ages_in_hours = {
        r["report_id"]: (now - datetime.fromisoformat(r["timestamp"])).total_seconds() / 3600
        for r in reports
    }
    assert ages_in_hours["R-006"] > 12          # the old "bridge is passable" report
    assert all(age >= 0 for age in ages_in_hours.values())  # nothing from the future


def test_image_reports(reports):
    assert sum(1 for r in reports if r["image_file"]) >= 5


def test_spec_example_sentence_is_present(reports):
    assert reports[0]["text"] == (
        "Pul ke paas 10 families phansi hui hain aur ek pregnant woman ko medical help chahiye."
    )


def test_priority_distribution(incidents):
    counts = Counter(i["expected_priority"] for i in incidents)
    assert counts["Critical"] == 5
    critical_ids = {i["incident_id"] for i in incidents if i["expected_priority"] == "Critical"}
    assert critical_ids == {"INC-101", "INC-102", "INC-105", "INC-108", "INC-113"}


def test_two_boats_available(resources):
    boats = [
        r for r in resources
        if r["resource_type"] == "rescue_boat" and r["status"] == "available"
    ]
    assert len(boats) == 2
    assert sum(1 for r in resources if r["status"] == "available") == 7


def test_shelter_capacity_cases(shelters):
    can_take_30 = [s for s in shelters if free_beds(s) >= 30]
    assert len(can_take_30) >= 3
    assert any(s["status"] == "full" for s in shelters)
    assert any(s["status"] == "closed" for s in shelters)
    assert any(s["status"] == "open" and 0 < free_beds(s) < 30 for s in shelters)


def test_hospital_cases(hospitals):
    assert any(h["available_beds"] == 0 for h in hospitals)
    assert any("dialysis" in h["services"] and h["available_beds"] > 0 for h in hospitals)
    assert any("maternity" in h["services"] and h["available_beds"] > 0 for h in hospitals)


def test_coordinates_inside_area(reports, incidents, resources, shelters, hospitals):
    points = []
    for group in (incidents, resources, shelters, hospitals):
        points += [(p["latitude"], p["longitude"]) for p in group]
    points += [(r["latitude"], r["longitude"]) for r in reports if r["latitude"] is not None]
    for lat, lon in points:
        assert LAT_RANGE[0] <= lat <= LAT_RANGE[1], lat
        assert LON_RANGE[0] <= lon <= LON_RANGE[1], lon


def test_generator_is_reproducible_and_files_are_current():
    first = build_dataset()
    second = build_dataset()
    assert first == second  # building twice gives identical data
    for name, content in first.items():
        assert load(name) == content, f"{name}.json is out of date. Re-run the generator."