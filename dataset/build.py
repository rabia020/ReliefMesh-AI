"""Assembles, validates and writes the ReliefMesh synthetic dataset.

build_dataset()  -> returns everything as one dictionary (no files touched)
validate()       -> returns a list of problems (empty list means all good)
write_dataset()  -> writes data/seed/*.json and data/images/*.png
"""

import copy
import json
from pathlib import Path

from dataset.constants import (
    INCIDENT_TYPES,
    LANGUAGES,
    PRIORITIES,
    REPORT_DATE,
    RESOURCE_NEEDS,
    RESOURCE_STATUSES,
    RESOURCE_TYPES,
    SCENARIO,
    SOURCE_CONFIDENCE,
)
from dataset.images import IMAGE_SPECS, generate_images
from dataset.incidents import INCIDENTS
from dataset.infrastructure import (
    BLOCKED_ROADS,
    HOSPITALS,
    LOCALITIES,
    RESOURCES,
    SHELTERS,
)
from dataset.reports import REPORTS

ROOT = Path(__file__).resolve().parent.parent
SEED_DIR = ROOT / "data" / "seed"
IMAGES_DIR = ROOT / "data" / "images"

EXPECTED_COUNTS = {"reports": 50, "incidents": 20, "resources": 10, "shelters": 8, "hospitals": 5}


def build_dataset() -> dict:
    """Builds the full dataset. Uses deep copies so repeated calls never interfere."""
    shelters = copy.deepcopy(SHELTERS)
    hospitals = copy.deepcopy(HOSPITALS)

    # One combined gazetteer: localities + shelters + hospitals.
    places = copy.deepcopy(LOCALITIES)
    for item, kind in [(s, "shelter") for s in shelters] + [(h, "hospital") for h in hospitals]:
        places.append({
            "id": item["id"], "name": item["name"], "name_ur": None, "kind": kind,
            "lat": item["lat"], "lon": item["lon"], "aliases": list(item["aliases"]),
        })
    place_by_id = {p["id"]: p for p in places}

    images = [{k: v for k, v in spec.items() if k != "scene"} for spec in copy.deepcopy(IMAGE_SPECS)]
    image_file = {img["id"]: img["file"] for img in images}

    # Split each raw report into agent-visible fields and hidden ground truth.
    reports, answer_key = [], {}
    for raw in copy.deepcopy(REPORTS):
        reports.append({
            "id": raw["id"],
            "timestamp": raw["timestamp"],
            "language": raw["language"],
            "source_type": raw["source_type"],
            "text": raw["text"],
            "image_id": raw["image_id"],
            "image_file": image_file.get(raw["image_id"]),
            "structured": raw["structured"],
            "batch": raw["batch"],
        })
        answer_key[raw["id"]] = {
            "incident_id": raw["truth_incident"],
            "place_id": raw["truth_place"],
        }

    report_time = {r["id"]: r["timestamp"] for r in reports}
    incidents = []
    for inc in copy.deepcopy(INCIDENTS):
        place = place_by_id[inc["place_id"]]
        rids = sorted(rid for rid, key in answer_key.items() if key["incident_id"] == inc["id"])
        times = [report_time[rid] for rid in rids]
        inc["location_name"] = place["name"]
        inc["lat"] = place["lat"]
        inc["lon"] = place["lon"]
        inc["report_ids"] = rids
        inc["first_report_time"] = min(times) if times else None
        inc["last_report_time"] = max(times) if times else None
        incidents.append(inc)

    return {
        "scenario": copy.deepcopy(SCENARIO),
        "reports": reports,
        "answer_key": answer_key,
        "incidents": incidents,
        "resources": copy.deepcopy(RESOURCES),
        "shelters": shelters,
        "hospitals": hospitals,
        "places": places,
        "blocked_roads": copy.deepcopy(BLOCKED_ROADS),
        "images": images,
    }


def _has_urdu(text: str) -> bool:
    return any("\u0600" <= ch <= "\u06ff" for ch in text)


def validate(ds: dict) -> list:
    """Returns a list of problems. An empty list means the dataset is valid."""
    errors = []

    for name, want in EXPECTED_COUNTS.items():
        ids = [item["id"] for item in ds[name]]
        if len(ids) != want:
            errors.append(f"{name}: expected {want}, found {len(ids)}")
        if len(ids) != len(set(ids)):
            errors.append(f"{name}: duplicate ids found")

    box = ds["scenario"]["bounding_box"]
    for group in ("places", "resources", "shelters", "hospitals", "blocked_roads"):
        for item in ds[group]:
            inside = (box["min_lat"] <= item["lat"] <= box["max_lat"]
                      and box["min_lon"] <= item["lon"] <= box["max_lon"])
            if not inside:
                errors.append(f"{group} {item['id']}: coordinates outside the scenario area")

    place_ids = {p["id"] for p in ds["places"]}
    incident_ids = {i["id"] for i in ds["incidents"]}
    image_ids = {i["id"] for i in ds["images"]}
    now = ds["scenario"]["now"]

    # ---- reports
    for r in ds["reports"]:
        rid = r["id"]
        if r["language"] not in LANGUAGES:
            errors.append(f"{rid}: unknown language {r['language']!r}")
        elif r["language"] == "ur" and not _has_urdu(r["text"]):
            errors.append(f"{rid}: labelled Urdu but contains no Urdu script")
        elif r["language"] != "ur" and not r["text"].isascii():
            errors.append(f"{rid}: labelled {r['language']} but contains non-ASCII characters")
        if r["source_type"] not in SOURCE_CONFIDENCE:
            errors.append(f"{rid}: unknown source type {r['source_type']!r}")
        if not r["timestamp"].startswith(REPORT_DATE):
            errors.append(f"{rid}: timestamp is not on the scenario date")
        if r["timestamp"] > now:
            errors.append(f"{rid}: timestamp is later than the scenario clock")
        if r["image_id"] and r["image_id"] not in image_ids:
            errors.append(f"{rid}: unknown image {r['image_id']}")
        truth = ds["answer_key"].get(rid)
        if truth is None:
            errors.append(f"{rid}: missing from answer_key")
            continue
        if truth["incident_id"] not in incident_ids:
            errors.append(f"{rid}: answer key points to unknown incident {truth['incident_id']}")
        if truth["place_id"] not in place_ids:
            errors.append(f"{rid}: answer key points to unknown place {truth['place_id']}")

    for spec in ds["images"]:
        match = [r for r in ds["reports"] if r["id"] == spec["report_id"]]
        if not match or match[0]["image_id"] != spec["id"]:
            errors.append(f"{spec['id']}: report {spec['report_id']} does not point back to this image")

    if {r["language"] for r in ds["reports"]} != set(LANGUAGES):
        errors.append("reports: all three languages (en, roman_ur, ur) must be present")

    # ---- incidents
    report_batch = {r["id"]: r["batch"] for r in ds["reports"]}
    for inc in ds["incidents"]:
        iid = inc["id"]
        if inc["incident_type"] not in INCIDENT_TYPES:
            errors.append(f"{iid}: unknown incident type {inc['incident_type']!r}")
        if inc["expected_priority"] not in PRIORITIES:
            errors.append(f"{iid}: unknown priority {inc['expected_priority']!r}")
        for need in inc["required_resources"]:
            if need not in RESOURCE_NEEDS:
                errors.append(f"{iid}: unknown resource need {need!r}")
        if inc["place_id"] not in place_ids:
            errors.append(f"{iid}: unknown place {inc['place_id']}")
        if not inc["report_ids"]:
            errors.append(f"{iid}: has no reports")
        lo, hi = inc["expected_confidence_range"]
        if not (0 <= lo < hi <= 100):
            errors.append(f"{iid}: bad expected_confidence_range")
        batches = {report_batch.get(rid) for rid in inc["report_ids"]}
        if inc["in_baseline"] and batches != {"baseline"}:
            errors.append(f"{iid}: baseline incident must only have baseline reports")
        if not inc["in_baseline"] and batches != {"demo"}:
            errors.append(f"{iid}: demo incident must only have demo reports")

    # ---- resources, shelters, hospitals
    for res in ds["resources"]:
        if res["type"] not in RESOURCE_TYPES:
            errors.append(f"{res['id']}: unknown resource type {res['type']!r}")
        if res["status"] not in RESOURCE_STATUSES:
            errors.append(f"{res['id']}: unknown status {res['status']!r}")
    available_boats = [r for r in ds["resources"] if r["type"] == "boat" and r["status"] == "available"]
    if len(available_boats) != 2:
        errors.append(f"demo needs exactly 2 available boats, found {len(available_boats)}")
    critical = sum(1 for i in ds["incidents"] if i["expected_priority"] == "Critical")
    if critical < 5:
        errors.append(f"demo needs at least 5 Critical incidents, found {critical}")
    for s in ds["shelters"]:
        if s["current_occupancy"] > s["capacity"]:
            errors.append(f"{s['id']}: occupancy is above capacity")
    if not any(s["capacity"] - s["current_occupancy"] >= 30 for s in ds["shelters"]):
        errors.append("no shelter has room for 30 people")
    for h in ds["hospitals"]:
        if h["available_beds"] > h["total_beds"]:
            errors.append(f"{h['id']}: available beds above total beds")

    return errors


def render_json(obj) -> str:
    """One place that decides how JSON is formatted (Urdu kept readable)."""
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def write_dataset(ds: dict, seed_dir: Path = SEED_DIR, images_dir: Path = IMAGES_DIR) -> None:
    seed_dir.mkdir(parents=True, exist_ok=True)
    for key, value in ds.items():
        (seed_dir / f"{key}.json").write_text(render_json(value), encoding="utf-8", newline="\n")
    generate_images(images_dir)
