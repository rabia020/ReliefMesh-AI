"""Draft a PROPOSED ACTION from Resource Agent rankings.

Never marks anything as executed. The supervisor (Phase 13) may write a
row with status='proposed'. Only a human (Phase 17) can approve it.
"""

from dataset.constants import RESOURCE_TYPES

# Medium-priority incidents only get a proposal if someone needs medical care.
# Low-priority incidents never auto-propose a dispatch.
PROPOSE_PRIORITIES = {"Critical", "High"}


def draft_proposed_action(incident: dict, resource_rec: dict | None) -> dict | None:
    priority = incident.get("priority")
    medical = bool(incident.get("medical_emergency"))
    if priority not in PROPOSE_PRIORITIES and not (priority == "Medium" and medical):
        return None

    picked = []
    shelter_note = None
    for need, rec in (resource_rec or {}).items():
        if not rec.get("supported"):
            continue
        for candidate in rec.get("candidates") or []:
            if candidate.get("type") in RESOURCE_TYPES and candidate.get("available"):
                if candidate["id"] not in {p["id"] for p in picked}:
                    picked.append(candidate)
                break
            if need == "shelter" and candidate.get("has_room") and shelter_note is None:
                shelter_note = candidate.get("name")
                break

    if not picked:
        return None

    names = " + ".join(p["name"] for p in picked)
    title = f"Dispatch {names}"
    reason_parts = [
        f"{incident.get('estimated_affected', 0)} affected people",
        f"{incident.get('vulnerable_people', 0)} vulnerable people",
        f"{'1 medical emergency' if medical else 'no medical emergency'}",
        f"{incident.get('evidence_confidence', 'n/a')}% evidence confidence",
    ]
    for p in picked:
        dist = p.get("distance_km")
        extra = f" ({dist} km away)" if dist is not None else ""
        reason_parts.append(f"{p['name']} is available{extra}")
    if shelter_note:
        reason_parts.append(f"Nearest shelter with room: {shelter_note}")
    if incident.get("route_note"):
        reason_parts.append(incident["route_note"])

    return {
        "action_type": "dispatch_resource",
        "title": title,
        "reason": "\n".join(reason_parts),
        "resource_ids": [p["id"] for p in picked],
        "proposed_by": "ai:supervisor",
    }
