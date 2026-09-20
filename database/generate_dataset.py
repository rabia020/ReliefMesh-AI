"""Builds the synthetic flood dataset and writes it as JSON files in data/.

Run from the project root:
    python -m database.generate_dataset

No random numbers are used, so the output is identical every time.
"""

import hashlib
import json
from collections import Counter
from pathlib import Path

from database import seed_content as c

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _rows_to_dicts(fields, rows):
    """Turn tuples into dictionaries. strict=True stops us if a row has a missing/extra value."""
    return [dict(zip(fields, row, strict=True)) for row in rows]


def build_dataset() -> dict:
    """Builds every table in memory and returns it as a dictionary of lists."""
    incidents = _rows_to_dicts(c.INCIDENT_FIELDS, c.INCIDENT_ROWS)
    incident_by_id = {item["incident_id"]: item for item in incidents}

    reports = []
    for index, row in enumerate(c.REPORT_ROWS, start=1):
        incident_id, when, language, source, has_gps, image, label, text = row
        incident = incident_by_id[incident_id]
        day, clock = when.split()

        # Reports with GPS get a small, fixed offset from the incident location.
        latitude = longitude = None
        if has_gps:
            latitude = round(incident["latitude"] + ((index % 5) - 2) * 0.0003, 6)
            longitude = round(incident["longitude"] + (((index * 3) % 5) - 2) * 0.0003, 6)

        report_id = f"R-{index:03d}"
        reports.append({
            "report_id": report_id,
            "timestamp": f"2026-08-{day}T{clock}:00+05:00",
            "language": language,
            "source_type": source,
            "source_confidence": c.SOURCE_CONFIDENCE[source],
            "text": text,
            "latitude": latitude,
            "longitude": longitude,
            "image_file": image,
            # --- answer key (tests only; agents must never read these) ---
            "true_incident_id": incident_id,
            "label": label,
        })
        incident.setdefault("report_ids", []).append(report_id)

    return {
        "meta": {
            "scenario_name": "Daryab River Flood (SIMULATED)",
            "scenario_now": c.SCENARIO_NOW,
            "timezone": "UTC+05:00",
            "center_latitude": 31.60,
            "center_longitude": 74.30,
            "disclaimer": (
                "All data is SIMULATED for demonstration. Names, places, numbers and "
                "events are invented. ReliefMesh AI is a decision-support prototype."
            ),
            "answer_key_fields": [
                "true_incident_id", "label",
                "expected_priority", "expected_confidence_band", "report_ids",
            ],
        },
        "reports": reports,
        "incidents": incidents,
        "resources": _rows_to_dicts(c.RESOURCE_FIELDS, c.RESOURCE_ROWS),
        "shelters": _rows_to_dicts(c.SHELTER_FIELDS, c.SHELTER_ROWS),
        "hospitals": _rows_to_dicts(c.HOSPITAL_FIELDS, c.HOSPITAL_ROWS),
        "blocked_roads": _rows_to_dicts(c.ROAD_FIELDS, c.ROAD_ROWS),
    }


def write_dataset(dataset: dict) -> str:
    """Writes one JSON file per table. Returns a SHA-256 fingerprint of all the output."""
    DATA_DIR.mkdir(exist_ok=True)
    digest = hashlib.sha256()
    for name, content in dataset.items():
        text = json.dumps(content, ensure_ascii=False, indent=2) + "\n"
        (DATA_DIR / f"{name}.json").write_text(text, encoding="utf-8", newline="\n")
        digest.update(text.encode("utf-8"))
    return digest.hexdigest()


def main() -> None:
    dataset = build_dataset()
    fingerprint = write_dataset(dataset)

    languages = Counter(r["language"] for r in dataset["reports"])
    priorities = Counter(i["expected_priority"] for i in dataset["incidents"])
    boats = [
        r for r in dataset["resources"]
        if r["resource_type"] == "rescue_boat" and r["status"] == "available"
    ]

    print(f"Dataset written to: {DATA_DIR}")
    for name in ("reports", "incidents", "resources", "shelters", "hospitals", "blocked_roads"):
        print(f"  {name + '.json':<20}: {len(dataset[name])}")
    print(
        "Languages : "
        + ", ".join(f"{k}={languages[k]}" for k in ("en", "roman_ur", "ur"))
    )
    print(
        "Priorities: "
        + ", ".join(f"{k}={priorities[k]}" for k in ("Critical", "High", "Medium", "Low"))
    )
    print(f"Available boats: {len(boats)}")
    print(f"Fingerprint (SHA-256): {fingerprint}")


if __name__ == "__main__":
    main()