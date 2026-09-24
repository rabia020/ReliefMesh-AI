"""Intake Agent (Phase 7).

Takes one raw citizen/field report (English, Roman Urdu, or Urdu; plain text
or a structured form) and produces a structured incident extraction:
incident type, location, affected people, vulnerable people, medical
emergency, required resources, timestamp, and language — the exact fields
your prompt's example shows.

The LLM interprets meaning; agents/schemas.py enforces that the result is
always safe and valid before it goes anywhere else.
"""

from dataset.constants import INCIDENT_TYPES, RESOURCE_NEEDS
from agents.gazetteer import load_places, match_location
from agents.schemas import normalize_extraction
from llm.client import LLMError, get_llm_client

SYSTEM_PROMPT = """You are the Intake Agent for ReliefMesh AI, a disaster-response \
coordination system used during a flood emergency. You will be given ONE citizen \
or field report. Reports may be written in English, Roman Urdu (Urdu written with \
Latin letters, e.g. "pani", "madad", "phanse"), or Urdu script. Read carefully in \
whichever language is used and extract the facts objectively. Do not invent \
numbers or details the report does not support: if something is not mentioned, \
use 0, false, or an empty value rather than guessing a plausible-sounding number.

Respond with a single JSON object with exactly these fields:
{
  "incident_type": one of """ + str(list(INCIDENT_TYPES)) + """,
  "location_text": the place name(s) mentioned in the report, in your own words, \
in English (translate if needed),
  "estimated_affected": integer, best estimate of the number of people affected,
  "vulnerable_people": integer, count of children, elderly, pregnant, disabled, \
or chronically ill people mentioned (this is a subset of estimated_affected),
  "medical_emergency": true or false,
  "medical_severity": integer 0-3 (0 = no medical issue, 1 = minor/chronic, \
2 = serious, 3 = life-threatening),
  "required_resources": a list using only these values: """ + str(list(RESOURCE_NEEDS)) + """,
  "isolation": integer 0-2 (0 = reachable by road, 1 = partly cut off, \
2 = fully cut off / unreachable by road),
  "reasoning": one short sentence explaining your extraction
}"""


def _build_user_prompt(report: dict) -> str:
    lines = [
        f"Report language: {report['language']}",
        f"Source type: {report['source_type']}",
        f"Report text:\n{report['text']}",
    ]
    if report.get("structured"):
        lines.append(
            "\nThis report also includes a structured field form with these "
            f"human-verified facts (you may still infer incident_type, isolation, "
            f"and anything not listed here):\n{report['structured']}"
        )
    return "\n".join(lines)


def _apply_structured_overrides(clean: dict, structured: dict, notes: list) -> None:
    """Structured field/volunteer forms carry human-counted numbers, which are
    more reliable than an LLM's guess from surrounding prose. They override
    the LLM's numeric/boolean fields but not incident_type or isolation,
    which the form doesn't capture."""
    field_map = {
        "people_affected": "estimated_affected",
        "vulnerable_people": "vulnerable_people",
        "medical_emergency": "medical_emergency",
    }
    for src_field, dest_field in field_map.items():
        if src_field in structured and structured[src_field] is not None:
            if clean[dest_field] != structured[src_field]:
                notes.append(
                    f"{dest_field} overridden by structured form: "
                    f"{clean[dest_field]} -> {structured[src_field]}"
                )
            clean[dest_field] = structured[src_field]

    if structured.get("needs"):
        valid = [n for n in structured["needs"] if n in RESOURCE_NEEDS]
        merged = sorted(set(clean["required_resources"]) | set(valid))
        if merged != clean["required_resources"]:
            notes.append(f"required_resources merged with structured form needs: {merged}")
        clean["required_resources"] = merged

    if structured.get("location_text") and not clean["location_text"]:
        clean["location_text"] = structured["location_text"]

    if structured.get("medical_emergency") and clean["medical_severity"] == 0:
        clean["medical_severity"] = 2
        notes.append("structured form confirmed a medical emergency; severity raised to 2")


def run_intake(report: dict, conn=None, llm_client=None) -> dict:
    """Runs the Intake Agent on one report.

    report: a dict shaped like database.queries.list_reports() rows
            (id, timestamp, language, source_type, text, structured, ...)
    conn:   an open database connection, used only for gazetteer place matching.
            Pass None to skip location matching (used in unit tests).
    llm_client: inject a fake client in tests; defaults to the real Gemini/Ollama client.

    Returns a dict with the extraction fields, plus report_id, timestamp,
    language (passed through, not re-guessed), place match info, and
    extraction_notes listing every correction that was made.
    """
    client = llm_client or get_llm_client()

    try:
        raw = client.complete_json(_build_user_prompt(report), system=SYSTEM_PROMPT)
    except LLMError as error:
        # A failed extraction should not crash the pipeline. Phase 8's
        # Verification Agent will see zero confidence and can route this
        # report to a human review queue instead of losing it.
        raw = {}
        llm_failed_note = f"LLM extraction failed, using defaults: {error}"
    else:
        llm_failed_note = None

    clean, notes = normalize_extraction(raw)
    if llm_failed_note:
        notes.insert(0, llm_failed_note)

    if report.get("structured"):
        _apply_structured_overrides(clean, report["structured"], notes)

    place_match = {"place_id": None, "place_name": None, "confidence": None, "matched_alias": None}
    if conn is not None:
        places = load_places(conn)
        place_match = match_location(clean["location_text"], places)
        if place_match["place_id"] is None:
            notes.append(f"could not match location_text {clean['location_text']!r} to a known place")

    return {
        "report_id": report["id"],
        "timestamp": report["timestamp"],
        "language": report["language"],
        **clean,
        "place_id": place_match["place_id"],
        "place_name": place_match["place_name"],
        "place_match_confidence": place_match["confidence"],
        "extraction_notes": notes,
    }