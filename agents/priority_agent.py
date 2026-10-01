"""Priority Agent (Phase 10).

Calculates a priority level (Critical/High/Medium/Low) for a verified
incident using only deterministic arithmetic over known facts: population
affected, medical urgency, vulnerable people, isolation, and the evidence
confidence score from the Verification Agent (Phase 8). Your prompt is
explicit that priority must not rely solely on LLM judgment — this agent
makes no LLM calls at all, and produces the same score every time for the
same input.
"""

# How urgent an incident TYPE inherently is, before looking at any numbers.
# A missing child or a live wire is urgent even with a small headcount; a
# flooded shop is not urgent even with a large one. Calibrated against the
# 20 reference incidents in dataset/incidents.py — tune here if real-world
# use suggests a type is mis-weighted.
TYPE_BASE_SEVERITY = {
    "missing_person": 0.80,
    "medical_emergency": 0.60,
    "trapped_residents": 0.55,
    "electrical_hazard": 0.55,
    "structural_damage": 0.40,
    "stranded_vehicle": 0.35,
    "food_water_shortage": 0.25,
    "shelter_request": 0.20,
    "road_blocked": 0.20,
    "flooded_property": 0.15,
    "livestock_stranded": 0.10,
}
DEFAULT_TYPE_SEVERITY = 0.30

# Priority score (0-100) cutoffs. Calibrated so the formula separates the 20
# reference incidents' priority levels exactly in 16/20 cases, and never by
# more than one tier in the other 4 — see tests/test_phase10.py. Tunable.
CRITICAL_CUTOFF = 60
HIGH_CUTOFF = 33
MEDIUM_CUTOFF = 14

PRIORITIES = ("Critical", "High", "Medium", "Low")


def compute_priority_score(incident: dict) -> int:
    """incident needs: incident_type, estimated_affected, vulnerable_people,
    medical_emergency, medical_severity (0-3), isolation (0-2),
    evidence_confidence (0-100, defaults to 100 if missing).
    Returns an integer 0-100 — never a raw, unclamped value.

    Design: a single severe factor (life-threatening medical need, total
    isolation, or an inherently urgent incident type) is enough to drive the
    score up on its own (the three are combined with max, not summed), since
    one person with a life-threatening injury is not "less urgent" just
    because only one person is affected. Scale of the incident (headcount,
    vulnerable people) then adds a smaller bonus on top. Low evidence
    confidence dampens the whole score at the end, so an unverified rumor
    never outranks a well-corroborated report of the same claimed severity.
    """
    medical = (incident.get("medical_severity", 0) / 3) if incident.get("medical_emergency") else 0.0
    isolation = (incident.get("isolation", 0) / 2) * 0.7
    type_base = TYPE_BASE_SEVERITY.get(incident.get("incident_type"), DEFAULT_TYPE_SEVERITY)
    core = max(type_base, medical, isolation)

    scale = (min(max(incident.get("estimated_affected", 0), 0) / 120, 1.0) * 0.15
             + min(max(incident.get("vulnerable_people", 0), 0) / 15, 1.0) * 0.10)

    raw = min(core + scale, 1.0)
    confidence = max(0, min(100, incident.get("evidence_confidence", 100))) / 100
    return round(raw * confidence * 100)


def priority_label(score: int) -> str:
    if score >= CRITICAL_CUTOFF:
        return "Critical"
    if score >= HIGH_CUTOFF:
        return "High"
    if score >= MEDIUM_CUTOFF:
        return "Medium"
    return "Low"


def assign_priority(incident: dict) -> dict:
    """The main entry point. Returns {"priority_score": int, "priority": str}."""
    score = compute_priority_score(incident)
    return {"priority_score": score, "priority": priority_label(score)}