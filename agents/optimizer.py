"""Phase 19 + cost and time factors: resource optimization with OR-Tools CP-SAT.
SIMULATED data. Creates PROPOSED actions only; a human approves every dispatch (Phase 17).

Time factors: arrival time (ETA) against a time window (60 min for a medical emergency,
              180 min otherwise), plus a small bonus for incidents that have waited longer.
Cost factors: a simulated cost per mission, an optional total budget, cost per person reached.
"""
import json
from datetime import datetime

from ortools.sat.python import cp_model

from agents.resource_agent import haversine_km
from database.queries import create_proposed_action

DISPATCHABLE = ("boat", "rescue_team", "ambulance", "medical_team")
PRIORITY_POINTS = {"Critical": 1.0, "High": 0.7, "Medium": 0.4, "Low": 0.15}

# Weights per resource type (each row adds up to 100).
WEIGHTS = {
    "boat":         {"priority": 30, "people": 30, "vulnerable": 10, "medical": 10, "isolation": 20},
    "rescue_team":  {"priority": 30, "people": 30, "vulnerable": 10, "medical": 10, "isolation": 20},
    "ambulance":    {"priority": 20, "people": 5,  "vulnerable": 15, "medical": 55, "isolation": 5},
    "medical_team": {"priority": 20, "people": 10, "vulnerable": 15, "medical": 50, "isolation": 5},
}

# ILLUSTRATIVE numbers in simulated units. Replace them with real figures when you have them.
CURRENCY = "simulated units"
ROAD_FACTOR = 1.3            # roads are longer than a straight line (boats ignore this)
DEFAULT_DISTANCE_KM = 10.0   # used when a location is unknown
TRIP_MODEL = {
    "boat":         {"speed_kmh": 15, "prep_min": 15, "base": 50,  "per_hour": 120, "per_km": 4.0, "on_scene_h": 2.0},
    "rescue_team":  {"speed_kmh": 35, "prep_min": 10, "base": 80,  "per_hour": 150, "per_km": 3.0, "on_scene_h": 3.0},
    "ambulance":    {"speed_kmh": 45, "prep_min": 3,  "base": 40,  "per_hour": 90,  "per_km": 2.5, "on_scene_h": 1.5},
    "medical_team": {"speed_kmh": 35, "prep_min": 10, "base": 100, "per_hour": 200, "per_km": 3.0, "on_scene_h": 3.0},
}
TIME_WINDOW_MIN = {"medical": 60, "other": 180}
WAIT_FULL_BONUS_MIN = 240.0   # waiting this long earns the full bonus
WAIT_MAX_BONUS = 0.10         # at most +10% value

OBJECTIVE_TEXT = (
    "Maximize total value = urgency x waiting bonus x evidence confidence x suitability x "
    "arrival-time factor x access, with each resource used once, at most one resource of each "
    "type per incident, and an optional total-cost budget. Cost is reported and capped by the "
    "budget; it does not lower a resource's value."
)
DISCLAIMER = ("SIMULATED data. This is a recommendation only. "
              "A human coordinator must approve every dispatch.")


# ---------------------------------------------------------------- helpers
def _label(rtype: str) -> str:
    return rtype.replace("_", " ")


def _has_coords(item: dict) -> bool:
    lat, lon = item.get("lat"), item.get("lon")
    return lat is not None and lon is not None and not (lat == 0 and lon == 0)


def _dispatch_needs(incident: dict) -> list:
    needs = []
    for need in incident.get("required_resources") or []:
        if need in DISPATCHABLE and need not in needs:
            needs.append(need)
    return needs


def _priority_allows(incident: dict) -> bool:
    priority = incident.get("priority")
    return priority in ("Critical", "High") or (
        priority == "Medium" and bool(incident.get("medical_emergency"))
    )


def _excluded(incident: dict, reason: str) -> dict:
    return {"incident_id": incident["id"], "title": incident.get("title"),
            "priority": incident.get("priority"), "reason": reason}


def _components(incident: dict) -> dict:
    medical = 0.0
    if incident.get("medical_emergency"):
        medical = max((incident.get("medical_severity") or 0) / 3.0, 0.34)
    return {
        "priority": PRIORITY_POINTS.get(incident.get("priority"), 0.0),
        "people": min((incident.get("estimated_affected") or 0) / 60.0, 1.0),
        "vulnerable": min((incident.get("vulnerable_people") or 0) / 5.0, 1.0),
        "medical": medical,
        "isolation": min((incident.get("isolation") or 0) / 2.0, 1.0),
    }


def urgency(incident: dict, rtype: str) -> float:
    weights, parts = WEIGHTS[rtype], _components(incident)
    return round(sum(weights[key] * parts[key] for key in weights), 2)


def _access_factor(incident: dict, rtype: str, blocked_roads: list) -> float:
    if rtype == "boat" or not _has_coords(incident):
        return 1.0
    factor = 1.0
    for road in blocked_roads:
        reach_km = road["radius_m"] / 1000.0 + 0.2
        if haversine_km(incident["lat"], incident["lon"], road["lat"], road["lon"]) <= reach_km:
            if road["status"] == "blocked":
                factor = min(factor, 0.6)
            elif road["status"] == "partial":
                factor = min(factor, 0.85)
    return factor


def _trip(incident: dict, resource: dict) -> dict:
    """Distance, arrival time and cost for one resource going to one incident."""
    spec = TRIP_MODEL[resource["type"]]
    if _has_coords(incident) and _has_coords(resource):
        straight = haversine_km(resource["lat"], resource["lon"], incident["lat"], incident["lon"])
        known = True
    else:
        straight, known = DEFAULT_DISTANCE_KM, False
    road_km = straight if resource["type"] == "boat" else straight * ROAD_FACTOR
    eta_min = spec["prep_min"] + road_km / spec["speed_kmh"] * 60.0
    mission_hours = 2 * (road_km / spec["speed_kmh"]) + spec["on_scene_h"]   # there and back
    cost = spec["base"] + spec["per_hour"] * mission_hours + spec["per_km"] * 2 * road_km
    return {"distance_km": round(straight, 2) if known else None,
            "eta_min": round(eta_min, 1), "cost": int(round(cost))}


def _time_factor(incident: dict, eta_min: float) -> float:
    window = TIME_WINDOW_MIN["medical" if incident.get("medical_emergency") else "other"]
    return max(0.3, 1.0 - eta_min / window)


def _pair_value(incident: dict, resource: dict, blocked_roads: list) -> dict:
    rtype = resource["type"]
    urg = urgency(incident, rtype)

    waiting = incident.get("waiting_min") or 0
    wait_mult = 1.0 + WAIT_MAX_BONUS * min(waiting / WAIT_FULL_BONUS_MIN, 1.0)

    confidence = incident.get("evidence_confidence")
    confidence = 50 if confidence is None else confidence
    conf_factor = 0.5 + 0.5 * confidence / 100.0

    capacity = resource.get("capacity_people") or 0
    affected = incident.get("estimated_affected") or 0
    if rtype in ("boat", "rescue_team"):
        suitability = (0.8 + 0.2 * min(1.0, capacity / affected)
                       if capacity > 0 and affected > 0 else 0.9)
    else:
        suitability = 1.0

    trip = _trip(incident, resource)
    time_factor = _time_factor(incident, trip["eta_min"])
    access = _access_factor(incident, rtype, blocked_roads)
    value = urg * wait_mult * conf_factor * suitability * time_factor * access
    return {
        "value": round(value, 2), "urgency": urg,
        "distance_km": trip["distance_km"], "eta_min": trip["eta_min"], "cost": trip["cost"],
        "waiting_min": int(round(waiting)),
        "factors": {"confidence": round(conf_factor, 3), "suitability": round(suitability, 3),
                    "time": round(time_factor, 3), "access": round(access, 3)},
    }


def _solve(pairs: list, budget=None):
    """Returns (chosen_indexes, solver_status_name)."""
    model = cp_model.CpModel()
    x = [model.NewBoolVar(f"x{i}") for i in range(len(pairs))]
    by_resource, by_slot = {}, {}
    for i, pair in enumerate(pairs):
        by_resource.setdefault(pair["resource"]["id"], []).append(x[i])
        by_slot.setdefault((pair["incident"]["id"], pair["resource"]["type"]), []).append(x[i])
    for group in list(by_resource.values()) + list(by_slot.values()):
        model.AddAtMostOne(group)
    if budget is not None:
        model.Add(sum(int(p["cost"]) * x[i] for i, p in enumerate(pairs)) <= int(budget))
    # "- i" is a tiny tie-breaker so the best plan is always unique and repeatable.
    model.Maximize(sum((int(round(p["value"] * 100)) * 1000 - i) * x[i]
                       for i, p in enumerate(pairs)))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 10.0
    solver.parameters.random_seed = 1
    try:
        solver.parameters.num_workers = 1
    except AttributeError:
        solver.parameters.num_search_workers = 1
    status = solver.Solve(model)
    name = solver.StatusName(status)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return [], name
    return [i for i in range(len(pairs)) if solver.Value(x[i])], name


# ------------------------------------------------------------- the plan
def build_plan(incidents: list, resources: list, blocked_roads: list,
               excluded=None, budget=None) -> dict:
    """Pure function: no database. Easy to test."""
    if budget is not None and budget <= 0:
        raise ValueError("budget must be greater than 0")
    excluded = list(excluded or [])
    eligible, needs_by_incident = [], {}
    for incident in sorted(incidents, key=lambda i: i["id"]):
        if not _priority_allows(incident):
            excluded.append(_excluded(
                incident, "priority is Low, or Medium without a medical emergency: no dispatch proposed"))
            continue
        needs = _dispatch_needs(incident)
        if not needs:
            excluded.append(_excluded(
                incident, "needs no dispatchable resource (boat, rescue team, ambulance, medical team)"))
            continue
        eligible.append(incident)
        needs_by_incident[incident["id"]] = needs

    resources = sorted(resources, key=lambda r: r["id"])
    pairs = []
    for incident in eligible:
        for resource in resources:
            if resource["type"] in needs_by_incident[incident["id"]]:
                scored = _pair_value(incident, resource, blocked_roads)
                if scored["value"] > 0:
                    pairs.append({"incident": incident, "resource": resource, **scored})

    chosen, status_name = _solve(pairs, budget) if pairs else ([], "NO_CANDIDATES")
    chosen_pairs = sorted(
        (pairs[i] for i in chosen),
        key=lambda p: (-p["value"], p["incident"]["id"], p["resource"]["id"]),
    )

    assignments = []
    for pair in chosen_pairs:
        incident, resource = pair["incident"], pair["resource"]
        alternatives = [p for p in pairs
                        if p["resource"]["id"] == resource["id"]
                        and p["incident"]["id"] != incident["id"]]
        alternatives.sort(key=lambda p: (-p["value"], p["incident"]["id"]))
        best_alt = ({"incident_id": alternatives[0]["incident"]["id"],
                     "value": alternatives[0]["value"]} if alternatives else None)

        parts = [
            f"{resource['name']} to {incident['id']} ({incident['priority']}): "
            f"{incident.get('estimated_affected') or 0} affected, "
            f"{incident.get('vulnerable_people') or 0} vulnerable, "
            f"{'medical emergency' if incident.get('medical_emergency') else 'no medical emergency'}",
            f"urgency {pair['urgency']:.0f}/100 for a {_label(resource['type'])}",
            f"evidence confidence {incident.get('evidence_confidence')}%",
            f"arrives in about {pair['eta_min']:.0f} min",
            f"estimated cost {pair['cost']} {CURRENCY}",
        ]
        if pair["distance_km"] is not None:
            parts.append(f"{pair['distance_km']:.1f} km away")
        if pair["waiting_min"] > 0:
            parts.append(f"waiting about {pair['waiting_min']} min since the first report")
        if pair["factors"]["access"] < 1:
            parts.append("a reported blocked road is nearby, so the route may be slow")
        if resource.get("capacity_people"):
            parts.append(f"carries up to {resource['capacity_people']} people")
        if best_alt:
            parts.append(f"next best use was {best_alt['incident_id']} (value {best_alt['value']})")

        assignments.append({
            "resource_id": resource["id"], "resource_name": resource["name"],
            "resource_type": resource["type"],
            "incident_id": incident["id"], "incident_title": incident.get("title"),
            "priority": incident["priority"],
            "value": pair["value"], "urgency": pair["urgency"],
            "distance_km": pair["distance_km"], "eta_min": pair["eta_min"], "cost": pair["cost"],
            "waiting_min": pair["waiting_min"], "factors": pair["factors"],
            "best_alternative": best_alt,
            "explanation": "; ".join(parts),
        })

    assigned_slots = {(a["incident_id"], a["resource_type"]) for a in assignments}
    available_by_type = {}
    for resource in resources:
        available_by_type[resource["type"]] = available_by_type.get(resource["type"], 0) + 1

    unassigned = []
    for incident in eligible:
        missing = []
        for need in needs_by_incident[incident["id"]]:
            if (incident["id"], need) in assigned_slots:
                continue
            count = available_by_type.get(need, 0)
            reason = (f"no available {_label(need)}" if count == 0 else
                      f"all {count} available {_label(need)}(s) went to more valuable incidents")
            if budget is not None and count > 0:
                reason += f", or the budget of {budget:g} {CURRENCY} ran out"
            missing.append({"need": need, "reason": reason})
        if missing:
            unassigned.append({"incident_id": incident["id"], "title": incident.get("title"),
                               "priority": incident["priority"], "missing": missing})

    used_ids = {a["resource_id"] for a in assignments}
    unused = [{"id": r["id"], "name": r["name"], "type": r["type"],
               "reason": f"no eligible incident needs a {_label(r['type'])}"}
              for r in resources if r["id"] not in used_ids]

    helped = {a["incident_id"] for a in assignments}
    people = sum((i.get("estimated_affected") or 0) for i in eligible if i["id"] in helped)
    total_cost = sum(a["cost"] for a in assignments)
    etas = [a["eta_min"] for a in assignments]
    summary = {
        "dispatches": len(assignments),
        "incidents_helped": len(helped),
        "people_in_helped_incidents": people,
        "incidents_with_unmet_needs": len(unassigned),
        "total_value": round(sum(a["value"] for a in assignments), 2),
        "total_cost": total_cost,
        "avg_eta_min": round(sum(etas) / len(etas), 1) if etas else None,
        "max_eta_min": max(etas) if etas else None,
        "cost_per_person": round(total_cost / people, 1) if people else None,
        "budget": budget,
        "budget_left": None if budget is None else round(budget - total_cost),
        "solver_status": status_name,
    }
    cost_text = (f" Estimated cost {total_cost} {CURRENCY}, average arrival "
                 f"{summary['avg_eta_min']:.0f} min." if assignments else "")
    summary_text = (
        f"Recommended {summary['dispatches']} dispatch(es) covering {summary['incidents_helped']} "
        f"incident(s) with about {people} people.{cost_text} "
        + (f"{len(unassigned)} incident(s) still have an unmet need. " if unassigned else
           "Every considered need is covered. ")
        + "A human must approve each action."
    )
    return {
        "assignments": assignments, "unassigned_incidents": unassigned,
        "unused_resources": unused, "excluded": excluded,
        "summary": summary, "summary_text": summary_text, "currency": CURRENCY,
        "objective": OBJECTIVE_TEXT, "disclaimer": DISCLAIMER,
    }


# --------------------------------------------------------- database side
def _rows(conn, sql, params=()):
    cursor = conn.execute(sql, params)
    columns = [c[0] for c in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _parse_time(value):
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _waiting_minutes(first_report_time, clock) -> float:
    start = _parse_time(first_report_time)
    if start is None or clock is None:
        return 0.0
    try:
        return max(0.0, (clock - start).total_seconds() / 60.0)
    except TypeError:   # one time has a time zone and the other does not
        return 0.0


def load_inputs(conn):
    pending = _rows(
        conn,
        "SELECT incident_id, resource_ids FROM actions WHERE status IN ('proposed', 'info_requested')",
    )
    pending_incidents = {p["incident_id"] for p in pending}
    reserved = set()
    for row in pending:
        try:
            reserved.update(json.loads(row["resource_ids"] or "[]"))
        except (TypeError, ValueError):
            pass

    rows = _rows(
        conn,
        "SELECT id, title, incident_type, location_name, lat, lon, estimated_affected, "
        "vulnerable_people, medical_emergency, medical_severity, isolation, required_resources, "
        "priority, evidence_confidence, status, first_report_time, last_report_time "
        "FROM incidents WHERE status IN ('open', 'unverified') ORDER BY id",
    )
    # The "demo clock" is the newest report in the data, so results never depend on today's date.
    times = [t for t in (_parse_time(r["last_report_time"]) for r in rows) if t is not None]
    try:
        clock = max(times) if times else None
    except TypeError:
        clock = None

    incidents, excluded = [], []
    for row in rows:
        try:
            row["required_resources"] = json.loads(row["required_resources"] or "[]")
        except (TypeError, ValueError):
            row["required_resources"] = []
        row["medical_emergency"] = bool(row["medical_emergency"])
        row["waiting_min"] = _waiting_minutes(row["first_report_time"], clock)
        if row["status"] == "unverified":
            excluded.append(_excluded(row, "unverified: check the evidence before allocating resources"))
        elif row["id"] in pending_incidents:
            excluded.append(_excluded(row, "already has a pending proposal waiting for a human decision"))
        else:
            incidents.append(row)

    resources = [
        r for r in _rows(
            conn,
            "SELECT id, name, type, lat, lon, capacity_people, crew_size FROM resources "
            "WHERE status = 'available' ORDER BY id")
        if r["id"] not in reserved
    ]
    blocked = _rows(conn, "SELECT id, name, lat, lon, radius_m, status FROM blocked_roads")
    return incidents, resources, blocked, excluded


def optimize(conn, budget=None) -> dict:
    """Read-only: computes the plan from the current database."""
    incidents, resources, blocked, excluded = load_inputs(conn)
    return build_plan(incidents, resources, blocked, excluded, budget)


def propose_plan(conn, plan: dict) -> list:
    """Turns a plan into PROPOSED actions (one per incident). Dispatches nothing."""
    by_incident = {}
    for item in plan["assignments"]:
        by_incident.setdefault(item["incident_id"], []).append(item)

    created = []
    for incident_id in sorted(by_incident):
        items = by_incident[incident_id]
        incident = _rows(
            conn,
            "SELECT estimated_affected, vulnerable_people, medical_emergency, evidence_confidence "
            "FROM incidents WHERE id = ?", (incident_id,))[0]
        lines = [
            f"{incident['estimated_affected']} affected people",
            f"{incident['vulnerable_people']} vulnerable people",
            "1 medical emergency" if incident["medical_emergency"] else "no medical emergency",
            f"{incident['evidence_confidence']}% evidence confidence",
        ]
        for item in items:
            distance = f" ({item['distance_km']} km away)" if item["distance_km"] is not None else ""
            lines.append(
                f"{item['resource_name']} is available{distance}, arrives in about "
                f"{item['eta_min']:.0f} min, estimated cost {item['cost']} {CURRENCY}")
        lines.append(f"Total estimated cost for this action: {sum(i['cost'] for i in items)} {CURRENCY}")
        lines.append("Chosen by the resource optimizer to maximize total value across incidents.")
        action_id = create_proposed_action(
            conn, incident_id=incident_id, action_type="dispatch_resource",
            title="Dispatch " + " + ".join(i["resource_name"] for i in items),
            reason="\n".join(lines),
            resource_ids=[i["resource_id"] for i in items],
            proposed_by="ai:optimizer",
        )
        created.append({"action_id": action_id, "incident_id": incident_id,
                        "resource_ids": [i["resource_id"] for i in items]})
    conn.commit()
    return created


def optimize_and_propose(conn, budget=None) -> dict:
    plan = optimize(conn, budget)
    actions = propose_plan(conn, plan)
    return {"created": len(actions), "actions": actions, "plan": plan}


if __name__ == "__main__":
    # See the plan from your real database (read-only):  python -m agents.optimizer
    import os
    from pathlib import Path

    from database.connection import get_connection

    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    connection = get_connection(Path(os.getenv("DATABASE_PATH", "data/reliefmesh.db")))
    result = optimize(connection)
    print(result["summary_text"], "\n")
    for item in result["assignments"]:
        print("-", item["explanation"])
    for item in result["unassigned_incidents"]:
        print("UNMET:", item["incident_id"], [m["reason"] for m in item["missing"]])
    for item in result["excluded"]:
        print("SKIPPED:", item["incident_id"], "-", item["reason"])
    print("\nSolver:", result["summary"]["solver_status"])