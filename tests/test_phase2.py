"""Automated tests for Phase 2 (synthetic dataset)."""

import json

from dataset.build import (
    SEED_DIR,
    build_dataset,
    render_json,
    validate,
    write_dataset,
)


def test_dataset_passes_validation():
    assert validate(build_dataset()) == []


def test_required_counts():
    ds = build_dataset()
    assert len(ds["reports"]) == 50
    assert len(ds["incidents"]) == 20
    assert len(ds["resources"]) == 10
    assert len(ds["shelters"]) == 8
    assert len(ds["hospitals"]) == 5
    assert sum(1 for r in ds["reports"] if r["image_id"]) == 6
    assert sum(1 for r in ds["reports"] if r["structured"]) == 5


def test_three_languages_present():
    langs = {r["language"] for r in build_dataset()["reports"]}
    assert langs == {"en", "roman_ur", "ur"}


def test_demo_needs_two_boats_and_five_critical():
    ds = build_dataset()
    boats = [r for r in ds["resources"] if r["type"] == "boat" and r["status"] == "available"]
    critical = [i for i in ds["incidents"] if i["expected_priority"] == "Critical"]
    assert len(boats) == 2
    assert len(critical) >= 5
    # More critical incidents need boats than we have boats (that is the point of the demo).
    needing_boats = [i for i in critical if "boat" in i["required_resources"]]
    assert len(needing_boats) > len(boats)


def test_duplicates_and_conflicts_exist():
    ds = build_dataset()
    clusters = [i for i in ds["incidents"] if len(i["report_ids"]) >= 3]
    conflicts = [i for i in ds["incidents"] if i["conflict_note"]]
    assert len(clusters) >= 5
    assert len(conflicts) >= 3


def test_demo_batch_is_the_bridge_incident():
    ds = build_dataset()
    demo_reports = [r for r in ds["reports"] if r["batch"] == "demo"]
    assert len(demo_reports) == 7
    assert all(ds["answer_key"][r["id"]]["incident_id"] == "INC-001" for r in demo_reports)
    not_in_baseline = [i["id"] for i in ds["incidents"] if not i["in_baseline"]]
    assert not_in_baseline == ["INC-001"]


def test_generation_is_deterministic():
    first, second = build_dataset(), build_dataset()
    for key in first:
        assert render_json(first[key]) == render_json(second[key])


def test_write_dataset_creates_files(tmp_path):
    ds = build_dataset()
    write_dataset(ds, tmp_path / "seed", tmp_path / "images")
    json_files = sorted(p.name for p in (tmp_path / "seed").glob("*.json"))
    assert json_files == sorted(f"{key}.json" for key in ds)
    for image in ds["images"]:
        assert (tmp_path / "images" / image["file"]).exists()


def test_urdu_survives_json_roundtrip(tmp_path):
    ds = build_dataset()
    write_dataset(ds, tmp_path / "seed", tmp_path / "images")
    loaded = json.loads((tmp_path / "seed" / "reports.json").read_text(encoding="utf-8"))
    assert loaded == ds["reports"]
    urdu = [r for r in loaded if r["language"] == "ur"]
    assert len(urdu) == 13
    assert any(ord(ch) > 1500 for ch in urdu[0]["text"])


def test_committed_seed_files_are_up_to_date():
    """Fails if you edited the dataset code but forgot to run generate_dataset.py."""
    ds = build_dataset()
    for key, value in ds.items():
        path = SEED_DIR / f"{key}.json"
        assert path.exists(), f"{path} is missing. Run: python scripts/generate_dataset.py"
        assert path.read_text(encoding="utf-8") == render_json(value), (
            f"{path.name} is out of date. Run: python scripts/generate_dataset.py"
        )


def test_validator_catches_bad_data():
    ds = build_dataset()
    ds["reports"][0]["language"] = "ur"          # English text labelled as Urdu
    ds["incidents"][0]["expected_priority"] = "Urgent"   # not a valid priority
    errors = validate(ds)
    assert len(errors) >= 2
