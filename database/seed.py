"""Loads the Phase 2 JSON dataset (data/seed/*.json) into SQLite.

This is the ONLY code that reads answer_key.json. It uses it once, to link the
43 baseline reports to their incidents (the 'already processed' starting state).
The answer key is never stored in the database.
"""

import json
from pathlib import Path

from database.connection import get_connection
from database.queries import log_audit, table_counts
from database.schema import create_schema

ROOT = Path(__file__).resolve().parent.parent
SEED_DIR = ROOT / "data" / "seed"


def _load(seed_dir: Path, name: str):
    return json.loads((seed_dir / f"{name}.json").read_text(encoding="utf-8"))


def _j(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def _with_json(item: dict, *fields) -> dict:
    row = dict(item)
    for field in fields:
        row[field] = _j(row[field])
    return row


def seed_database(conn, seed_dir=SEED_DIR) -> None:
    seed_dir = Path(seed_dir)
    names = ("scenario", "places", "incidents", "reports", "answer_key",
             "resources", "shelters", "hospitals", "blocked_roads")
    data = {name: _load(seed_dir, name) for name in names}

    conn.execute("INSERT INTO meta (key, value) VALUES ('scenario', ?)", (_j(data["scenario"]),))

    conn.executemany(
        "INSERT INTO places (id, name, name_ur, kind, lat, lon, aliases) "
        "VALUES (:id, :name, :name_ur, :kind, :lat, :lon, :aliases)",
        [_with_json(p, "aliases") for p in data["places"]],
    )

    # Only baseline incidents exist at the start. INC-001 is created live in the demo.
    incident_rows = []
    for inc in data["incidents"]:
        if not inc["in_baseline"]:
            continue
        low, high = inc["expected_confidence_range"]
        incident_rows.append({
            "id": inc["id"], "title": inc["title"], "incident_type": inc["incident_type"],
            "place_id": inc["place_id"], "location_name": inc["location_name"],
            "lat": inc["lat"], "lon": inc["lon"],
            "estimated_affected": inc["estimated_affected"],
            "vulnerable_people": inc["vulnerable_people"],
            "medical_emergency": int(inc["medical_emergency"]),
            "medical_severity": inc["medical_severity"],
            "isolation": inc["isolation"],
            "required_resources": _j(inc["required_resources"]),
            # Starting values only. The agents recompute these in Phases 8 and 10.
            "priority": inc["expected_priority"],
            "evidence_confidence": (low + high) // 2,
            "status": inc["status"], "conflict_note": inc["conflict_note"],
            "first_report_time": inc["first_report_time"],
            "last_report_time": inc["last_report_time"],
            "origin": "seed",
        })
    conn.executemany(
        "INSERT INTO incidents (id, title, incident_type, place_id, location_name, lat, lon, "
        "estimated_affected, vulnerable_people, medical_emergency, medical_severity, isolation, "
        "required_resources, priority, evidence_confidence, status, conflict_note, "
        "first_report_time, last_report_time, origin) "
        "VALUES (:id, :title, :incident_type, :place_id, :location_name, :lat, :lon, "
        ":estimated_affected, :vulnerable_people, :medical_emergency, :medical_severity, :isolation, "
        ":required_resources, :priority, :evidence_confidence, :status, :conflict_note, "
        ":first_report_time, :last_report_time, :origin)",
        incident_rows,
    )

    report_rows = []
    for r in data["reports"]:
        baseline = r["batch"] == "baseline"
        report_rows.append({
            "id": r["id"], "timestamp": r["timestamp"], "language": r["language"],
            "source_type": r["source_type"], "text": r["text"],
            "image_id": r["image_id"], "image_file": r["image_file"],
            "structured": _j(r["structured"]) if r["structured"] else None,
            "batch": r["batch"],
            "status": "processed" if baseline else "queued",
            "incident_id": data["answer_key"][r["id"]]["incident_id"] if baseline else None,
        })
    conn.executemany(
        "INSERT INTO reports (id, timestamp, language, source_type, text, image_id, image_file, "
        "structured, batch, status, incident_id) "
        "VALUES (:id, :timestamp, :language, :source_type, :text, :image_id, :image_file, "
        ":structured, :batch, :status, :incident_id)",
        report_rows,
    )

    conn.executemany(
        "INSERT INTO resources (id, name, type, status, base, lat, lon, crew_size, "
        "capacity_people, capabilities, current_assignment) "
        "VALUES (:id, :name, :type, :status, :base, :lat, :lon, :crew_size, "
        ":capacity_people, :capabilities, :current_assignment)",
        [_with_json(x, "capabilities") for x in data["resources"]],
    )
    conn.executemany(
        "INSERT INTO shelters (id, name, lat, lon, capacity, current_occupancy, status, "
        "road_access, facilities, notes) "
        "VALUES (:id, :name, :lat, :lon, :capacity, :current_occupancy, :status, "
        ":road_access, :facilities, :notes)",
        [_with_json(x, "facilities") for x in data["shelters"]],
    )
    hospital_rows = []
    for h in data["hospitals"]:
        row = _with_json(h, "specialties")
        row["emergency_open"] = int(row["emergency_open"])
        hospital_rows.append(row)
    conn.executemany(
        "INSERT INTO hospitals (id, name, lat, lon, total_beds, available_beds, icu_total, "
        "icu_available, emergency_open, status, specialties, notes) "
        "VALUES (:id, :name, :lat, :lon, :total_beds, :available_beds, :icu_total, "
        ":icu_available, :emergency_open, :status, :specialties, :notes)",
        hospital_rows,
    )
    conn.executemany(
        "INSERT INTO blocked_roads (id, name, lat, lon, radius_m, status, reason, reported_at, source) "
        "VALUES (:id, :name, :lat, :lon, :radius_m, :status, :reason, :reported_at, :source)",
        data["blocked_roads"],
    )

    log_audit(  # also commits everything above
        conn, actor="system", event_type="database_seeded",
        message=f"Loaded simulated scenario: {data['scenario']['name']}",
        details={
            "scenario_id": data["scenario"]["id"],
            "incidents_loaded": len(incident_rows),
            "reports_processed": sum(1 for r in report_rows if r["status"] == "processed"),
            "reports_queued": sum(1 for r in report_rows if r["status"] == "queued"),
        },
    )


def init_database(db_path=None, seed_dir=SEED_DIR) -> dict:
    """Resets the database to the original demo state. Returns the row count of every table."""
    conn = get_connection(db_path)
    try:
        create_schema(conn)
        seed_database(conn, seed_dir)
        return table_counts(conn)
    finally:
        conn.close()