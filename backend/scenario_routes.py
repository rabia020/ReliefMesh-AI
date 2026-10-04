import re
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agents.supervisor import run_pipeline
from database import queries as q
from llm.client import LLMError

NOMINATIM = "https://nominatim.openstreetmap.org/search"
PREPOSITIONS = r"\b(?:near|in|at|around|of|by|from)\b"
SKIP_WORDS = {"the", "a", "an", "this", "that", "my", "our", "town", "area", "water", "road"}


def geocode(place: str):
    if not place or not place.strip():
        return None
    try:
        response = httpx.get(
            NOMINATIM,
            params={"q": place.strip(), "format": "json", "limit": 1},
            headers={"User-Agent": "ReliefMeshAI/1.0"},
            timeout=8,
        )
        response.raise_for_status()
        rows = response.json()
        if rows:
            return float(rows[0]["lat"]), float(rows[0]["lon"]), rows[0].get("display_name")
    except Exception:
        pass
    return None


def geocode_many(query: str, limit: int = 5) -> list[dict]:
    if not query or not query.strip():
        return []
    try:
        response = httpx.get(
            NOMINATIM,
            params={"q": query.strip(), "format": "json", "limit": limit},
            headers={"User-Agent": "ReliefMeshAI/1.0"},
            timeout=8,
        )
        response.raise_for_status()
        return [
            {"name": row.get("display_name"), "lat": float(row["lat"]), "lon": float(row["lon"])}
            for row in response.json()
        ]
    except Exception:
        return []


def place_candidates(text: str) -> list[str]:
    sentence = re.split(r"[.;\n]", text or "")[0]
    parts = re.split(PREPOSITIONS, sentence, flags=re.I)[1:]
    cleaned = []
    for part in parts:
        name = part.split(",")[0].strip(" .-")
        if len(name) >= 3 and name.lower() not in SKIP_WORDS and len(name.split()) <= 5:
            cleaned.append(name)
    candidates = []
    if len(cleaned) >= 2:
        candidates.append(f"{cleaned[-2]}, {cleaned[-1]}")
    if cleaned:
        candidates.append(cleaned[-1])
    candidates.extend(cleaned[:-1])
    expanded = []
    for item in candidates:
        expanded.append(item)
        words = item.replace(",", " ").split()
        for size in (2, 1):
            if len(words) > size:
                expanded.append(" ".join(words[-size:]))
    seen, unique = set(), []
    for item in expanded:
        if item.lower() not in seen:
            seen.add(item.lower())
            unique.append(item)
    return unique


class ScenarioIn(BaseModel):
    text: str = Field(min_length=5, max_length=1500)
    language: str = Field(default="en", pattern="^(en|roman_ur|ur)$")
    location: str | None = Field(default=None, max_length=200)


class ScenarioSaveIn(ScenarioIn):
    lat: float | None = None
    lon: float | None = None


def _report(text: str, language: str, report_id: str) -> dict:
    return {
        "id": report_id,
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "language": language,
        "source_type": "manual",
        "text": text,
        "structured": None,
        "image_id": None,
        "status": "received",
    }


def _run(conn, text: str, language: str, report_id: str) -> dict:
    try:
        result = run_pipeline([_report(text, language, report_id)], conn, persist=False)
    except LLMError as error:
        raise HTTPException(status_code=502, detail=f"Language model unavailable: {error}")
    if not result["clusters"]:
        raise HTTPException(status_code=422, detail="No incident could be extracted from this text.")
    return result["clusters"][0]


def _locate(body: ScenarioIn, extracted: str | None):
    if body.location:
        options = [body.location]
    else:
        options = ([extracted] if extracted else []) + place_candidates(body.text)
    for option in options:
        geo = geocode(option)
        if geo:
            return option, geo
    return None, None


def _analyze(conn, body: ScenarioIn, report_id: str):
    text = body.text + (f" Location: {body.location}." if body.location else "")
    cluster = _run(conn, text, body.language, report_id)
    incident = dict(cluster["incident"])

    known_place = incident.get("lat") is not None
    extractions = cluster.get("extractions") or []
    extracted = extractions[0].get("location_text") if extractions else None
    place_text, geo = (None, None)

    if not known_place:
        place_text, geo = _locate(body, extracted)
        if geo:
            if not body.location:
                try:
                    cluster = _run(conn, f"{body.text} Location: {place_text}.", body.language, report_id)
                    incident = dict(cluster["incident"])
                except HTTPException:
                    pass
            incident["lat"], incident["lon"] = geo[0], geo[1]
            incident["location_name"] = place_text
    return cluster, incident, place_text, known_place, geo


def build_scenario_router(get_db) -> APIRouter:
    router = APIRouter(tags=["scenario"])

    @router.get("/geocode")
    def search_places(q: str, limit: int = 5):
       return {"query": q, "results": geocode_many(q, min(max(limit, 1), 10))}

    @router.post("/scenario/analyze")
    def analyze(body: ScenarioIn, conn=Depends(get_db)):
        cluster, incident, place_text, known_place, geo = _analyze(conn, body, "R-PREVIEW")
        proposal = cluster.get("proposed_action")
        return {
            "preview_only": True,
            "title": incident.get("title"),
            "summary": incident.get("summary"),
            "incident_type": incident.get("incident_type"),
            "priority": incident.get("priority"),
            "priority_score": incident.get("priority_score"),
            "confidence": incident.get("evidence_confidence"),
            "affected": incident.get("estimated_affected"),
            "medical": bool(incident.get("medical_emergency")),
            "needs": incident.get("required_resources") or [],
            "location_text": place_text,
            "location_name": incident.get("location_name"),
            "lat": incident.get("lat"),
            "lon": incident.get("lon"),
            "place_source": "known place list" if known_place else ("OpenStreetMap search" if geo else "not found"),
            "approximate": bool(geo) and not body.location,
            "proposed_action": (
                {"title": proposal.get("title"), "reason": proposal.get("reason")} if proposal else None
            ),
        }

    @router.post("/scenario/save")
    def save(body: ScenarioSaveIn, conn=Depends(get_db)):
        count = conn.execute("SELECT COUNT(*) FROM reports WHERE id LIKE 'R-LIVE-%'").fetchone()[0]
        report_id = f"R-LIVE-{count + 1:03d}"
        cluster, incident, _, _, _ = _analyze(conn, body, report_id)
        if body.lat is not None and body.lon is not None:
            incident["lat"], incident["lon"] = body.lat, body.lon
        if incident.get("lat") is None or incident.get("lon") is None:
            raise HTTPException(status_code=422, detail="No coordinates found. Enter a clearer location and try again.")
        try:
            ids = conn.execute("SELECT id FROM incidents WHERE id GLOB 'INC-[0-9]*'").fetchall()
            numbers = [int(row[0][4:]) for row in ids if row[0][4:].isdigit()]
            incident["id"] = f"INC-{(max(numbers) if numbers else 0) + 1:03d}"
            incident["origin"] = "pipeline"
            report = _report(body.text, body.language, report_id)
            conn.execute(
                "INSERT INTO reports(id, timestamp, language, source_type, text, image_id, image_file,"
                " structured, batch, status, incident_id) VALUES (?,?,?,?,?,?,?,?,?,?,NULL)",
                (report_id, report["timestamp"], report["language"], "manual", report["text"],
                 None, None, None, "live", "received"),
            )
            q.save_pipeline_incident(conn, incident, [report_id])
            proposal = cluster.get("proposed_action")
            action_id = None
            if proposal:
                action_id = q.create_proposed_action(
                    conn,
                    incident_id=incident["id"],
                    action_type=proposal["action_type"],
                    title=proposal["title"],
                    reason=proposal["reason"],
                    resource_ids=proposal["resource_ids"],
                    proposed_by=proposal["proposed_by"],
                )
            conn.commit()
        except HTTPException:
            raise
        except Exception as error:
            conn.rollback()
            raise HTTPException(status_code=500, detail=f"Could not save: {error}")
        return {"incident_id": incident["id"], "action_id": action_id, "status": "saved"}

    return router