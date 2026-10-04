"""CrewAI-style supervisor (Phase 13).

LangGraph is not used. The crew is a fixed sequential process with
conditional skips:

START → Supervisor → Intake → Verification → Priority → Resource →
Routing → Reporter → Human Review → END

Each specialist is the Python agent already built in Phases 7–12. The
supervisor does NOT let an LLM decide whether to call them, because that
would make the demo non-reproducible. CrewAI (see agents/crew.py) supplies
the role names, task descriptions, and optional LLM crew wrapper.

Agents never execute real-world dispatch. Human Review only creates a
PROPOSED ACTION row.
"""

from agents.intake_agent import run_intake
from agents.priority_agent import assign_priority
from agents.proposed import draft_proposed_action
from agents.reporter_agent import run_reporter
from agents.resource_agent import recommend_for_incident
from agents.routing_agent import nearest_hospital, nearest_shelter
from agents.verification_agent import verify_reports
from database import queries as q
from agents.image_agent import apply_image_evidence

CREW_SEQUENCE = (
    "supervisor",
    "intake",
    "verification",
    "priority",
    "resource",
    "routing",
    "reporter",
    "human_review",
)
DISCLAIMER = (
    "SIMULATED data. ReliefMesh AI is decision support only. "
    "No real-world dispatch was executed."
)


def _trace(agent, status, detail=None):
    entry = {"agent": agent, "status": status}
    if detail:
        entry["detail"] = detail
    return entry


def _attach_place(conn, merged: dict) -> dict:
    incident = dict(merged)
    incident["location_name"] = merged.get("place_name") or merged.get("location_text") or ""
    incident["lat"] = None
    incident["lon"] = None
    place_id = merged.get("place_id")
    if place_id and conn is not None:
        place = q.get_place(conn, place_id)
        if place:
            incident["location_name"] = place["name"]
            incident["lat"] = place["lat"]
            incident["lon"] = place["lon"]
    return incident


def _simplify_route_hits(hits):
    return [{"id": h.get("id"), "name": h.get("name"), "status": h.get("status")} for h in hits or []]


def _run_routing(incident, shelters, hospitals, blocked_roads, call_osrm_fn=None) -> tuple[dict, dict]:
    """Returns (routing_result, trace_entry). Skips when there are no coordinates."""
    if incident.get("lat") is None or incident.get("lon") is None:
        return (
            {"skipped": True, "reason": "no_coordinates"},
            _trace("routing", "skipped", "no_coordinates"),
        )

    lat, lon = incident["lat"], incident["lon"]
    need_room = incident.get("estimated_affected", 0) or 0
    shelters_ranked = nearest_shelter(
        lat, lon, shelters, blocked_roads,
        require_room_for=need_room, call_osrm_fn=call_osrm_fn,
    )
    hospitals_ranked = []
    hospital_skipped = not bool(incident.get("medical_emergency"))
    if not hospital_skipped:
        hospitals_ranked = nearest_hospital(
            lat, lon, hospitals, blocked_roads, call_osrm_fn=call_osrm_fn,
        )

    def _slim(rows, n=3):
        slim = []
        for row in rows[:n]:
            slim.append({
                "id": row.get("id"),
                "name": row.get("name"),
                "distance_km": row.get("distance_km"),
                "duration_min": row.get("duration_min"),
                "route_source": row.get("route_source"),
                "blocked_by": _simplify_route_hits(row.get("blocked_by")),
            })
        return slim

    note = None
    if shelters_ranked and shelters_ranked[0].get("blocked_by"):
        note = "Nearest shelter route passes a reported blocked road; alternatives may be needed."
    routing = {
        "skipped": False,
        "nearest_shelters": _slim(shelters_ranked),
        "nearest_hospitals": _slim(hospitals_ranked),
        "hospital_skipped": hospital_skipped,
        "note": note,
    }
    return routing, _trace("routing", "ran")


def _process_cluster(cluster, conn, resources, shelters, hospitals, blocked_roads,
                     llm_client, call_osrm_fn, persist, trace) -> dict:
    merged = cluster["merged"]
    incident = _attach_place(conn, merged)
    incident["evidence_confidence"] = cluster["evidence_confidence"]
    incident["conflict_detected"] = cluster["conflict_detected"]
    incident["conflict_note"] = cluster.get("conflict_note") or merged.get("conflict_note")
    incident["report_count"] = merged["report_count"]
    incident["languages"] = merged.get("languages")

    image_note = apply_image_evidence(conn, incident, cluster["reports"])
    if image_note:
        trace.append(_trace("verification", "ran", image_note))

    if incident["evidence_confidence"] < 35:
        incident["status"] = "unverified"
    else:
        incident["status"] = "open"

    priority = assign_priority(incident)
    incident.update(priority)
    trace.append(_trace("priority", "ran", incident["priority"]))

    if incident.get("required_resources"):
        resource_rec = recommend_for_incident(incident, resources, shelters)
        trace.append(_trace("resource", "ran"))
    else:
        resource_rec = {}
        trace.append(_trace("resource", "skipped", "no_required_resources"))

    routing, routing_trace = _run_routing(
        incident, shelters, hospitals, blocked_roads, call_osrm_fn=call_osrm_fn,
    )
    trace.append(routing_trace)
    if routing.get("note"):
        incident["route_note"] = routing["note"]

    report = run_reporter(incident, llm_client=llm_client)
    incident["title"] = report["title"]
    incident["summary"] = report["summary"]
    incident["briefing"] = report["briefing"]
    trace.append(_trace("reporter", "ran", "fallback" if report.get("used_fallback") else "llm"))

    proposal = draft_proposed_action(incident, resource_rec)
    action_id = None
    if persist and conn is not None:
        incident["id"] = q.next_pipeline_incident_id(conn, merged)
        q.save_pipeline_incident(conn, incident, merged["report_ids"])
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
            proposal["id"] = action_id
            proposal["status"] = "proposed"
            trace.append(_trace("human_review", "ran", "proposed"))
        else:
            trace.append(_trace("human_review", "ran", "no_dispatch_proposed"))
    else:
        incident["id"] = incident.get("id") or "PENDING"
        if proposal:
            proposal["status"] = "proposed"
            proposal["id"] = None
            trace.append(_trace("human_review", "ran", "proposed_not_persisted"))
        else:
            trace.append(_trace("human_review", "ran", "no_dispatch_proposed"))

    return {
        "incident": incident,
        "reports": cluster["reports"],
        "extractions": cluster["extractions"],
        "resource_recommendation": resource_rec,
        "routing": routing,
        "proposed_action": proposal,
        "trace": list(trace),
    }


def run_pipeline(reports, conn, *, llm_client=None, embedder=None, intake_results=None,
                 call_osrm_fn=None, persist=False, now_iso=None, verbose=False) -> dict:
    """Runs the full crew over a batch of reports. Returns a dict with
    clusters (one result per unique incident) and a top-level agent trace.

    persist=True writes incidents and PROPOSED actions to SQLite. Resource
    rows are never flipped to 'deployed' here.
    """
    top_trace = [_trace("supervisor", "ran", f"{len(reports)} reports")]
    if not reports:
        return {
            "clusters": [],
            "trace": top_trace + [_trace("intake", "skipped", "no_reports")],
            "disclaimer": DISCLAIMER,
        }

    if intake_results is None:
        intake_results = [run_intake(r, conn=conn, llm_client=llm_client) for r in reports]
    top_trace.append(_trace("intake", "ran", f"{len(intake_results)} extractions"))

    clusters = verify_reports(
        reports, conn, now_iso=now_iso, llm_client=llm_client, embedder=embedder,
        intake_results=intake_results, verbose=verbose,
    )
    top_trace.append(_trace("verification", "ran", f"{len(clusters)} clusters"))

    resources = q.list_resources(conn) if conn is not None else []
    shelters = q.list_shelters(conn) if conn is not None else []
    hospitals = q.list_hospitals(conn) if conn is not None else []
    blocked_roads = q.list_blocked_roads(conn) if conn is not None else []

    results = []
    for cluster in clusters:
        cluster_trace = list(top_trace)
        results.append(_process_cluster(
            cluster, conn, resources, shelters, hospitals, blocked_roads,
            llm_client, call_osrm_fn, persist, cluster_trace,
        ))

    return {
        "clusters": results,
        "trace": top_trace,
        "disclaimer": (
            "SIMULATED data. ReliefMesh AI is decision support only. "
            "No real-world dispatch was executed."
        ),
    }


def run_received_reports(conn, **kwargs) -> dict:
    """Convenience: process every report currently in status='received'."""
    reports = q.list_reports(conn, status="received")
    return run_pipeline(reports, conn, **kwargs)
