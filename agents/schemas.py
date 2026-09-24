"""The extraction schema the Intake Agent asks Gemini to fill in, plus
deterministic validation and cleanup of whatever comes back.

Your prompt says the Priority Agent (Phase 10) must not rely solely on LLM
judgment for numerical priority. The same caution applies here one step
earlier: we let the LLM interpret free text, but every field it returns is
clamped to a valid range or a valid category before anything downstream
ever sees it. Nothing raw and unchecked is passed on.
"""

from dataset.constants import INCIDENT_TYPES, RESOURCE_NEEDS

# What we ask Gemini to return. Shown to the LLM inside the prompt, and used
# here as the single source of truth for validation.
EXTRACTION_FIELDS = (
    "incident_type", "location_text", "estimated_affected", "vulnerable_people",
    "medical_emergency", "medical_severity", "required_resources", "isolation",
    "reasoning",
)

DEFAULT_EXTRACTION = {
    "incident_type": "trapped_residents",
    "location_text": "",
    "estimated_affected": 0,
    "vulnerable_people": 0,
    "medical_emergency": False,
    "medical_severity": 0,
    "required_resources": [],
    "isolation": 0,
    "reasoning": "",
}


def _clamp_int(value, low, high, default=0):
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default, False
    clamped = max(low, min(high, n))
    return clamped, clamped == n


def _to_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "1")
    return bool(value)


def normalize_extraction(raw: dict) -> tuple[dict, list[str]]:
    """Cleans one LLM extraction into a valid, safe dictionary.

    Returns (clean_dict, notes). notes lists every correction that was made,
    so nothing is silently changed without a trace — useful for debugging
    prompts and for the Verification Agent (Phase 8) to see how much the
    raw model output was trusted as-is.
    """
    raw = raw if isinstance(raw, dict) else {}
    notes = []
    clean = dict(DEFAULT_EXTRACTION)

    incident_type = raw.get("incident_type")
    if incident_type in INCIDENT_TYPES:
        clean["incident_type"] = incident_type
    else:
        notes.append(f"incident_type {incident_type!r} is not a known type; "
                      f"defaulted to '{clean['incident_type']}'")

    location_text = raw.get("location_text")
    clean["location_text"] = str(location_text).strip() if location_text else ""
    if not clean["location_text"]:
        notes.append("location_text was empty")

    for field, high in (("estimated_affected", 100000), ("vulnerable_people", 100000)):
        value, ok = _clamp_int(raw.get(field), 0, high)
        clean[field] = value
        if not ok:
            notes.append(f"{field} value {raw.get(field)!r} was invalid or out of range; "
                          f"set to {value}")

    if clean["vulnerable_people"] > clean["estimated_affected"] and clean["estimated_affected"] > 0:
        notes.append("vulnerable_people exceeded estimated_affected; capped to match")
        clean["vulnerable_people"] = clean["estimated_affected"]

    clean["medical_emergency"] = _to_bool(raw.get("medical_emergency", False))

    severity, ok = _clamp_int(raw.get("medical_severity"), 0, 3)
    clean["medical_severity"] = severity
    if not ok:
        notes.append(f"medical_severity value {raw.get('medical_severity')!r} was invalid; "
                      f"set to {severity}")
    if clean["medical_emergency"] and clean["medical_severity"] == 0:
        clean["medical_severity"] = 1
        notes.append("medical_emergency was true but severity was 0; raised to 1")
    if not clean["medical_emergency"] and clean["medical_severity"] > 0:
        clean["medical_emergency"] = True
        notes.append("medical_severity was above 0 but medical_emergency was false; corrected to true")

    needs = raw.get("required_resources")
    valid_needs, dropped = [], []
    if isinstance(needs, list):
        for need in needs:
            if need in RESOURCE_NEEDS and need not in valid_needs:
                valid_needs.append(need)
            else:
                dropped.append(need)
    clean["required_resources"] = valid_needs
    if dropped:
        notes.append(f"dropped unrecognized resource needs: {dropped}")

    isolation, ok = _clamp_int(raw.get("isolation"), 0, 2)
    clean["isolation"] = isolation
    if not ok:
        notes.append(f"isolation value {raw.get('isolation')!r} was invalid; set to {isolation}")

    clean["reasoning"] = str(raw.get("reasoning", "")).strip()[:500]

    return clean, notes