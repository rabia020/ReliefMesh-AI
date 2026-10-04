"""Reporter Agent (Phase 13).

Turns one verified, prioritized incident into a short briefing a coordinator
can read in a few seconds: a title, a summary, and a handful of bullets.

The LLM writes the prose. Numbers come from the earlier agents and are
copied into the prompt so the model is describing facts, not inventing them.
If the LLM fails, a deterministic fallback briefing is used instead — the
pipeline must never stall because a language model is down.
"""

from llm.client import LLMError, get_llm_client

SYSTEM_PROMPT = """You are the Reporter Agent for ReliefMesh AI, a disaster-response \
coordination prototype that uses SIMULATED data. Write a briefing for an emergency \
coordinator. Use ONLY the facts you are given. Do not invent numbers, places, or \
resources. Do not tell the coordinator to dispatch anyone — you summarize, a human \
approves actions later.

Respond with a single JSON object:
{
  "title": a clear incident title of at most 120 characters, in English,
  "summary": 2-4 sentences for the coordinator, in English,
  "briefing": 3-6 short bullet lines separated by newlines, each starting with "- "
}"""


def fallback_report(incident: dict) -> dict:
    location = incident.get("location_name") or incident.get("place_name") or "an unknown location"
    itype = (incident.get("incident_type") or "incident").replace("_", " ")
    title = f"{itype.title()} at {location}"
    affected = incident.get("estimated_affected", 0)
    vulnerable = incident.get("vulnerable_people", 0)
    medical = "Yes" if incident.get("medical_emergency") else "No"
    conf = incident.get("evidence_confidence")
    conf_text = f"{conf}%" if conf is not None else "n/a"
    priority = incident.get("priority") or "unassigned"
    needs = ", ".join(incident.get("required_resources") or []) or "none listed"
    conflict = incident.get("conflict_note")
    summary = (
        f"{affected} people estimated affected at {location} ({itype}). "
        f"Medical emergency: {medical}. Priority {priority} with evidence confidence {conf_text}. "
        f"Required resources: {needs}."
    )
    if conflict:
        summary += f" Conflicting reports: {conflict}"
    briefing = "\n".join([
        f"- Type: {itype}",
        f"- Estimated affected people: {affected}",
        f"- Vulnerable people: {vulnerable}",
        f"- Medical emergency: {medical}",
        f"- Required resources: {needs}",
        f"- Priority: {priority}",
        f"- Evidence confidence: {conf_text}",
    ])
    return {"title": title[:180], "summary": summary, "briefing": briefing, "used_fallback": True}


def _normalize_report(raw: dict, incident: dict) -> dict:
    fallback = fallback_report(incident)
    raw = raw if isinstance(raw, dict) else {}
    title = str(raw.get("title") or "").strip()[:180] or fallback["title"]
    summary = str(raw.get("summary") or "").strip()[:1500] or fallback["summary"]
    briefing = str(raw.get("briefing") or "").strip()[:1500] or fallback["briefing"]
    return {"title": title, "summary": summary, "briefing": briefing, "used_fallback": False}


def _facts_prompt(incident: dict) -> str:
    return (
        f"Incident type: {incident.get('incident_type')}\n"
        f"Location: {incident.get('location_name') or incident.get('place_name') or 'unknown'}\n"
        f"Estimated affected people: {incident.get('estimated_affected', 0)}\n"
        f"Vulnerable people: {incident.get('vulnerable_people', 0)}\n"
        f"Medical emergency: {bool(incident.get('medical_emergency'))}\n"
        f"Medical severity (0-3): {incident.get('medical_severity', 0)}\n"
        f"Isolation (0-2): {incident.get('isolation', 0)}\n"
        f"Required resources: {incident.get('required_resources') or []}\n"
        f"Priority: {incident.get('priority')} (score {incident.get('priority_score')})\n"
        f"Evidence confidence: {incident.get('evidence_confidence')}\n"
        f"Conflict note: {incident.get('conflict_note')}\n"
        f"Report count: {incident.get('report_count')}\n"
        f"Languages of reports: {incident.get('languages')}\n"
        "All of this is SIMULATED demo data."
    )


def run_reporter(incident: dict, llm_client=None) -> dict:
    """Returns title, summary, briefing, used_fallback."""
    client = llm_client or get_llm_client()
    try:
        raw = client.complete_json(_facts_prompt(incident), system=SYSTEM_PROMPT)
    except LLMError:
        result = fallback_report(incident)
        result["notes"] = ["LLM briefing failed; used deterministic fallback"]
        return result
    clean = _normalize_report(raw, incident)
    clean["notes"] = []
    return clean
