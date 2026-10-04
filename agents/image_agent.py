"""Phase 18: Image Intelligence (SIMULATED/demo use).

Photo -> shrink + strip EXIF -> vision model -> cleaned JSON -> cached in SQLite
-> small, explainable evidence-confidence adjustment for the incident.
AI image reading can be wrong. A human still approves every action.
"""
import hashlib
import io
import json
import re
import sqlite3
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from database.queries import utc_now_iso
from llm import vision
from llm.client import LLMError

MAX_SIDE = 1024
MAX_BOOST = 12.0       # image evidence can raise confidence by at most this many points
MAX_PENALTY = 15.0     # ...or lower it by at most this many points

WATER_LEVELS = ("none", "shallow", "knee_deep", "waist_deep", "deep", "unknown")
CROWDING_LEVELS = ("none", "few", "crowd", "unknown")
HAZARDS = ("downed_power_lines", "fire", "strong_current", "debris",
           "collapsed_building", "contamination", "landslide")

PROMPT = """You are helping an emergency coordinator read ONE photo from a flood or earthquake.
Describe only what is clearly visible. Do not guess. Do not identify any person.
If you cannot tell, use "unknown" or null.

Reply with ONE JSON object and nothing else, in exactly this shape:
{
  "flood_water": "none | shallow | knee_deep | waist_deep | deep | unknown",
  "road_blocked": true | false | null,
  "damaged_structures": true | false | null,
  "vehicles": {"count": integer or null, "submerged": true | false | null},
  "people_visible": integer or null,
  "crowding": "none | few | crowd | unknown",
  "hazards": [any of: "downed_power_lines", "fire", "strong_current", "debris", "collapsed_building", "contamination", "landslide"],
  "summary": "one short sentence",
  "confidence": number from 0 to 1 (how sure you are of this reading)
}"""


class ImageError(Exception):
    """kind is one of: invalid, not_found."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


# ------------------------------------------------------------ image prep
def prepare_image(data: bytes) -> bytes:
    """Validates, shrinks and re-encodes as JPEG. Re-encoding drops EXIF (GPS)."""
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise ImageError("invalid", "The file is not a readable image (use JPG, PNG or WebP).")
    image = image.convert("RGB")
    image.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=85)
    return out.getvalue()


# ------------------------------------------------- model output cleaning
THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


def parse_model_json(text: str) -> dict:
    text = THINK_BLOCK.sub("", text or "")      # ignore any "thinking" text
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise LLMError("The vision model did not return JSON.")
    try:
        data = json.loads(text[start:end + 1])
    except ValueError as error:
        raise LLMError("The vision model returned broken JSON.") from error
    if not isinstance(data, dict):
        raise LLMError("The vision model returned the wrong JSON shape.")
    return data


def _bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("true", "yes"):
            return True
        if text in ("false", "no"):
            return False
    return None


def _int(value, high=500):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return max(0, min(number, high))


def _enum(value, allowed):
    value = str(value or "").strip().lower()
    return value if value in allowed else "unknown"


def normalize_analysis(raw: dict) -> dict:
    """Never trust model output: only known values survive."""
    vehicles = raw.get("vehicles") if isinstance(raw.get("vehicles"), dict) else {}
    level = _enum(raw.get("flood_water"), WATER_LEVELS)
    hazards = raw.get("hazards") if isinstance(raw.get("hazards"), list) else []
    clean_hazards = []
    for hazard in hazards:
        hazard = str(hazard).strip().lower()
        if hazard in HAZARDS and hazard not in clean_hazards:
            clean_hazards.append(hazard)
    try:
        confidence = max(0.0, min(1.0, float(raw.get("confidence"))))
    except (TypeError, ValueError):
        confidence = 0.3
    return {
        "flood_water": level,
        "flood_water_present": None if level == "unknown" else level != "none",
        "road_blocked": _bool(raw.get("road_blocked")),
        "damaged_structures": _bool(raw.get("damaged_structures")),
        "vehicles": {"count": _int(vehicles.get("count")), "submerged": _bool(vehicles.get("submerged"))},
        "people_visible": _int(raw.get("people_visible")),
        "crowding": _enum(raw.get("crowding"), CROWDING_LEVELS),
        "hazards": clean_hazards,
        "summary": str(raw.get("summary") or "")[:200],
        "confidence": round(confidence, 2),
    }


# ------------------------------------------------------------- database
def ensure_table(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS image_analyses ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, report_id TEXT, image_name TEXT, "
        "image_sha256 TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL, "
        "analysis_json TEXT NOT NULL, created_at TEXT NOT NULL)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_image_analyses_report ON image_analyses(report_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_image_analyses_sha ON image_analyses(image_sha256)")


def analyze_and_store(conn, image_bytes: bytes, image_name: str, report_id=None,
                      vision_fn=None, force=False) -> dict:
    ensure_table(conn)
    if report_id:
        report_id = report_id.strip()
        if report_id.upper().startswith("INC-"):
            row = conn.execute(
                "SELECT id FROM reports WHERE incident_id = ? ORDER BY timestamp LIMIT 1",
                (report_id.upper(),),
            ).fetchone()
            if row:
                report_id = row[0]
        found = conn.execute("SELECT 1 FROM reports WHERE id = ?", (report_id,)).fetchone()
        if not found:
            raise ImageError("not_found", f"No report or incident found for {report_id}.")
    jpeg = prepare_image(image_bytes)
    sha = hashlib.sha256(jpeg).hexdigest()

    cached_row = None
    if not force:
        cached_row = conn.execute(
            "SELECT analysis_json, provider, model FROM image_analyses "
            "WHERE image_sha256 = ? ORDER BY id DESC LIMIT 1", (sha,)
        ).fetchone()

    if cached_row:
        analysis = json.loads(cached_row[0])
        provider, model, cached = cached_row[1], cached_row[2], True
    else:
        text, provider, model = (vision_fn or vision.describe_image)(jpeg, PROMPT)
        analysis = normalize_analysis(parse_model_json(text))
        cached = False

    conn.execute(
        "INSERT INTO image_analyses (report_id, image_name, image_sha256, provider, model, "
        "analysis_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (report_id, image_name, sha, provider, model,
         json.dumps(analysis, ensure_ascii=False), utc_now_iso()),
    )
    conn.commit()
    return {"report_id": report_id, "image_name": image_name, "sha256": sha[:16],
            "provider": provider, "model": model, "cached": cached, "analysis": analysis}


def load_analyses(conn, report_ids) -> dict:
    """{report_id: analysis} using the latest analysis per report. Safe if the table is missing."""
    ids = [rid for rid in report_ids if rid]
    if not ids:
        return {}
    marks = ",".join("?" for _ in ids)
    try:
        rows = conn.execute(
            f"SELECT report_id, analysis_json FROM image_analyses "
            f"WHERE report_id IN ({marks}) ORDER BY id", ids
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {row[0]: json.loads(row[1]) for row in rows}


def list_report_analyses(conn, report_id: str) -> list:
    try:
        rows = conn.execute(
            "SELECT image_name, provider, model, analysis_json, created_at "
            "FROM image_analyses WHERE report_id = ? ORDER BY id DESC", (report_id,)
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [{"image_name": r[0], "provider": r[1], "model": r[2],
             "analysis": json.loads(r[3]), "created_at": r[4]} for r in rows]


# --------------------------------------------- evidence (deterministic)
def evidence_from_analysis(incident_type, analysis):
    """Compares what the text claims with what the photo shows.
    Returns (points, supports, conflicts). Points = rule points x model confidence."""
    kind = (incident_type or "").lower()
    expects_water = any(k in kind for k in ("flood", "trapped", "strand", "isolat", "water"))
    expects_road = any(k in kind for k in ("road", "underpass", "bridge", "blocked"))
    expects_damage = any(k in kind for k in ("collapse", "structur", "damage", "building"))

    points, supports, conflicts = 0.0, [], []
    if expects_water:
        if analysis["flood_water_present"] is True:
            points += 8
            supports.append("image shows flood water")
        elif analysis["flood_water_present"] is False:
            points -= 10
            conflicts.append("image shows no flood water")
    if expects_road:
        if analysis["road_blocked"] is True:
            points += 6
            supports.append("image shows a blocked road")
        elif analysis["road_blocked"] is False:
            points -= 4
            conflicts.append("image shows a passable road")
    if expects_damage:
        if analysis["damaged_structures"] is True:
            points += 6
            supports.append("image shows damaged structures")
        elif analysis["damaged_structures"] is False:
            points -= 8
            conflicts.append("image shows no structural damage")
    return round(points * analysis["confidence"], 1), supports, conflicts


def apply_image_evidence(conn, incident: dict, reports: list):
    """Called by the supervisor. Changes nothing unless stored image analyses exist."""
    if conn is None:
        return None
    analyses = load_analyses(conn, [r.get("id") for r in reports])
    if not analyses:
        return None

    total, supports, conflicts, hazards = 0.0, [], [], []
    for analysis in analyses.values():
        points, s, c = evidence_from_analysis(incident.get("incident_type"), analysis)
        total += points
        supports += s
        conflicts += c
        hazards += [h for h in analysis["hazards"] if h not in hazards]

    delta = max(-MAX_PENALTY, min(MAX_BOOST, total))
    before = incident.get("evidence_confidence") or 0
    after = int(max(0, min(100, round(before + delta))))
    incident["evidence_confidence"] = after
    incident["image_evidence"] = {
        "images": len(analyses),
        "confidence_before": before,
        "confidence_after": after,
        "delta_points": round(delta, 1),
        "supports": list(dict.fromkeys(supports)),
        "conflicts": list(dict.fromkeys(conflicts)),
        "hazards": hazards,
    }
    return f"image evidence {delta:+.0f} points from {len(analyses)} image(s)"


if __name__ == "__main__":
    # Quick model test without the server:
    #   python -m agents.image_agent path/to/photo.jpg
    import sys

    if len(sys.argv) != 2:
        print("Usage: python -m agents.image_agent path/to/photo.jpg")
        raise SystemExit(1)
    photo = Path(sys.argv[1])
    scratch = sqlite3.connect(":memory:")
    print(json.dumps(analyze_and_store(scratch, photo.read_bytes(), photo.name),
                     indent=2, ensure_ascii=False))