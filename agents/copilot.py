"""Phase 20: AI Copilot (SIMULATED data).

Read-only. Flow: question -> intent (rules first, LLM second) -> a FIXED plan of MCP
tool calls -> grounded answer (LLM, or a template if the LLM is down).
The copilot cannot approve or dispatch anything.
"""
import asyncio
import json
import re
import sys
import time
from contextlib import AsyncExitStack
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from agents import optimizer
from agents.priority_agent import assign_priority
from database.connection import get_connection
from llm.chat import default_chat_client
from llm.client import LLMError
from mcp_servers.client_utils import unpack
from mcp_servers.common import db_path as default_db_path

ROOT = Path(__file__).resolve().parents[1]

SERVER_MODULES = {
    "incident": "mcp_servers.incident_server",
    "resource": "mcp_servers.resource_server",
    "mapping": "mcp_servers.mapping_server",
}
INTENTS = ("top_urgent", "medical_incidents", "explain_incident", "allocate",
           "shelter_room", "availability", "nearby", "help")
RESOURCE_TYPES = ("boat", "ambulance", "rescue_team", "medical_team")
TOPICS = ("boats", "ambulances", "teams", "shelters", "hospitals")
PRIORITY_RANK = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
RANK_RULE = "priority level first, then people affected, vulnerable people and medical emergency"
DISCLAIMER = ("SIMULATED data. The copilot only reads data and recommends. "
              "A human approves every dispatch.")
SUPPORTED_QUESTIONS = [
    "What are the three most urgent incidents?",
    "Where should I send the two available boats?",
    "Which incidents involve medical emergencies?",
    "Why is Incident 2 critical?",
    "Which shelter can accommodate 30 people?",
    "How many ambulances and hospital beds are available?",
    "What is happening near the Kabul River Bridge?",
]


# ------------------------------------------------------- understanding
def _blank() -> dict:
    return {"intent": None, "n": None, "incident_id": None, "resource_type": None,
            "min_free": None, "place": None, "topics": []}


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_incident_id(value):
    if value is None:
        return None
    match = re.search(r"(\d{1,4})", str(value))
    return f"INC-{int(match.group(1)):03d}" if match else None


def _incident_id_from_text(text: str):
    match = re.search(r"\b(?:incident|inc)[\s\-#:]*(\d{1,4})\b", text, re.IGNORECASE)
    return f"INC-{int(match.group(1)):03d}" if match else None


def _count(text: str):
    for word in re.findall(r"[a-z]+|\d+", text.lower()):
        if word.isdigit():
            return int(word)
        if word in NUMBER_WORDS:
            return NUMBER_WORDS[word]
    return None


def _resource_type(q: str):
    if "ambulance" in q:
        return "ambulance"
    if "medical team" in q:
        return "medical_team"
    if "boat" in q:
        return "boat"
    if "team" in q:
        return "rescue_team"
    return None


def _topics(q: str) -> list:
    topics = []
    if "boat" in q:
        topics.append("boats")
    if "ambulance" in q:
        topics.append("ambulances")
    if "team" in q:
        topics.append("teams")
    if "shelter" in q:
        topics.append("shelters")
    if any(word in q for word in ("hospital", "bed", "icu")):
        topics.append("hospitals")
    return topics


def route_question(question: str):
    """Keyword rules for the known questions. Returns params, or None if no rule fits."""
    q = " ".join(question.lower().split())
    params = _blank()

    incident_id = _incident_id_from_text(q)
    if incident_id and any(w in q for w in ("why", "explain", "reason", "kyun", "kyon")):
        params.update(intent="explain_incident", incident_id=incident_id)
        return params

    if ("where" in q and any(v in q for v in ("send", "dispatch", "deploy", "assign", "allocate"))) \
            or "allocat" in q or "optimi" in q:
        params.update(intent="allocate", resource_type=_resource_type(q))
        return params

    if "shelter" in q and re.search(r"\d+", q) and any(
            w in q for w in ("people", "person", "accommodate", "hold", "fit", "room", "space")):
        params.update(intent="shelter_room", min_free=_count(q))
        return params

    if "medical" in q and "incident" in q:
        params.update(intent="medical_incidents")
        return params

    near = re.search(r"\b(?:near|around|close to|next to)\s+(?:the\s+)?(.+?)\s*[?.!]*$",
                     question.strip(), re.IGNORECASE)
    if near and any(w in q for w in ("incident", "happening", "going on", "reports")):
        params.update(intent="nearby", place=near.group(1).strip()[:80])
        return params

    if "incident" in q and any(w in q for w in ("urgent", "critical", "priority", "top", "worst", "serious")):
        params.update(intent="top_urgent", n=_count(q))
        return params

    topics = _topics(q)
    if topics or "resource" in q or "available" in q:
        params.update(intent="availability", topics=topics)
        return params
    return None


def normalize_params(raw) -> dict:
    """Never trust the LLM: only known values survive."""
    params = _blank()
    if not isinstance(raw, dict):
        params["intent"] = "help"
        return params
    intent = str(raw.get("intent") or "").strip()
    params["intent"] = intent if intent in INTENTS else "help"
    n = _to_int(raw.get("n"))
    params["n"] = None if n is None else max(1, min(n, 10))
    params["incident_id"] = _normalize_incident_id(raw.get("incident_id"))
    rtype = str(raw.get("resource_type") or "").strip().lower()
    params["resource_type"] = rtype if rtype in RESOURCE_TYPES else None
    min_free = _to_int(raw.get("min_free"))
    params["min_free"] = min(min_free, 5000) if min_free is not None and min_free >= 1 else None
    params["place"] = str(raw.get("place") or "").strip()[:80] or None
    topics = raw.get("topics")
    params["topics"] = [t for t in topics if t in TOPICS] if isinstance(topics, list) else []
    return params


CLASSIFY_SYSTEM = "You route questions for an emergency-response copilot. Reply with ONE JSON object only."
CLASSIFY_PROMPT = """Pick the intent that fits the question. The question may be in English, Roman Urdu or Urdu.
Intents:
- top_urgent: most urgent / critical incidents
- medical_incidents: incidents that involve medical emergencies
- explain_incident: why an incident has its priority (needs an incident number)
- allocate: where to send boats, teams or ambulances
- shelter_room: which shelter has room for N people
- availability: how many boats, teams, ambulances, shelter space or hospital beds are available
- nearby: incidents near a named place
- help: anything else

Reply as JSON:
{"intent": "<one intent>", "n": integer or null, "incident_id": "INC-###" or null,
 "resource_type": "boat" | "ambulance" | "rescue_team" | "medical_team" | null,
 "min_free": integer or null, "place": string or null,
 "topics": any of ["boats", "ambulances", "teams", "shelters", "hospitals"]}
"""


def classify_with_llm(question: str, llm_client) -> dict:
    raw = llm_client.complete_json(CLASSIFY_PROMPT + "\nQuestion: " + question, system=CLASSIFY_SYSTEM)
    return normalize_params(raw)


# --------------------------------------------------------- MCP plumbing
class BaseHub:
    def __init__(self):
        self.calls = []

    def log_local(self, tool: str, summary: str, ms: int = 0):
        self.calls.append({"server": "local", "tool": tool, "args": {}, "ms": ms, "result": summary})

    async def call(self, server, tool, args=None, single=False):
        raise NotImplementedError


def _summarize(data) -> str:
    if isinstance(data, list):
        return f"{len(data)} item(s)"
    if isinstance(data, dict):
        if "error" in data:
            return f"error: {data['error']}"
        if "found" in data:
            return f"found={data['found']}"
        return f"{len(data)} field(s)"
    return str(data)[:60]


class McpHub(BaseHub):
    """Starts the MCP servers on demand and calls their tools over stdio."""

    def __init__(self, db_path):
        super().__init__()
        self.db_path = Path(db_path)
        self._stack = AsyncExitStack()
        self._sessions = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        await self._stack.aclose()

    async def _session(self, server: str):
        if server not in self._sessions:
            params = StdioServerParameters(
                command=sys.executable, args=["-m", SERVER_MODULES[server]],
                cwd=str(ROOT), env={"DATABASE_PATH": str(self.db_path)},
            )
            read, write = await self._stack.enter_async_context(stdio_client(params))
            session = await self._stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            self._sessions[server] = session
        return self._sessions[server]

    async def call(self, server, tool, args=None, single=False):
        session = await self._session(server)
        started = time.perf_counter()
        result = await session.call_tool(tool, args or {})
        if getattr(result, "isError", False):
            text = " ".join(getattr(block, "text", "") for block in result.content)
            raise RuntimeError(f"{server}.{tool} failed: {text}")
        data = unpack(result, single=single)
        self.calls.append({
            "server": server, "tool": tool, "args": args or {},
            "ms": int((time.perf_counter() - started) * 1000), "result": _summarize(data),
        })
        return data


def _run_async(coro):
    """Runs a coroutine from normal code. On Windows, 'uvicorn --reload' uses an event
    loop that cannot start subprocesses, so we create our own Proactor loop there."""
    if sys.platform == "win32":
        loop = asyncio.ProactorEventLoop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
    return asyncio.run(coro)


# ----------------------------------------------------------- the intents
def _has_coords(lat, lon) -> bool:
    return lat is not None and lon is not None and not (lat == 0 and lon == 0)


def _rank_key(incident: dict):
    size = ((incident.get("estimated_affected") or 0)
            + 5 * (incident.get("vulnerable_people") or 0)
            + (20 if incident.get("medical_emergency") else 0))
    return (PRIORITY_RANK.get(incident.get("priority"), 4),
            -(incident.get("priority_score") or 0), -size, incident.get("id") or "")


def _slim_incident(i: dict) -> dict:
    keys = ("id", "title", "priority", "estimated_affected", "vulnerable_people",
            "medical_emergency", "evidence_confidence", "status", "location_name")
    return {k: i.get(k) for k in keys}


async def _top_urgent(hub, params, conn, use_osrm):
    rows = await hub.call("incident", "get_incidents", {"limit": 200})
    rows = sorted((r for r in rows if r.get("status") != "resolved"), key=_rank_key)
    n = params.get("n") or 5
    return {"ranking_rule": RANK_RULE, "total_open": len(rows),
            "incidents": [_slim_incident(r) for r in rows[:n]]}


async def _medical(hub, params, conn, use_osrm):
    rows = await hub.call("incident", "get_incidents", {"limit": 200})
    rows = sorted((r for r in rows if r.get("medical_emergency") and r.get("status") != "resolved"),
                  key=_rank_key)
    return {"count": len(rows), "incidents": [_slim_incident(r) for r in rows]}


async def _explain(hub, params, conn, use_osrm):
    incident_id = params.get("incident_id")
    if not incident_id:
        return {"error": "Please give an incident number, for example: Why is Incident 2 critical?"}
    inc = await hub.call("incident", "get_incident", {"incident_id": incident_id}, single=True)
    if inc.get("error"):
        return {"error": inc["error"]}
    check = None
    try:
        got = assign_priority(dict(inc))
        check = {"priority": got.get("priority"), "priority_score": got.get("priority_score")}
    except Exception:  # noqa: BLE001 - the check is a bonus, never a failure
        check = None
    keys = ("id", "title", "incident_type", "location_name", "priority", "priority_score",
            "evidence_confidence", "status", "estimated_affected", "vulnerable_people",
            "medical_emergency", "medical_severity", "isolation", "required_resources",
            "conflict_note", "summary")
    reports = inc.get("reports") or []
    return {
        "incident": {k: inc.get(k) for k in keys},
        "report_count": len(reports),
        "reports": [{"id": r.get("id"), "language": r.get("language"),
                     "source_type": r.get("source_type"), "text": (r.get("text") or "")[:160]}
                    for r in reports[:6]],
        "proposed_actions": [{"id": a.get("id"), "title": a.get("title"), "status": a.get("status")}
                             for a in (inc.get("actions") or [])],
        "priority_agent_check": check,
    }


async def _allocate(hub, params, conn, use_osrm):
    rtype = params.get("resource_type")
    tools = {"boat": ["get_available_boats"], "ambulance": ["get_available_ambulances"],
             "rescue_team": ["get_available_teams"], "medical_team": ["get_available_teams"]}
    names = (["get_available_boats", "get_available_ambulances", "get_available_teams"]
             if rtype is None else tools[rtype])
    available = []
    for tool in dict.fromkeys(names):
        available += await hub.call("resource", tool)
    if rtype:
        available = [r for r in available if r.get("type") == rtype]

    started = time.perf_counter()
    plan = optimizer.optimize(conn)
    hub.log_local(
        "optimizer.plan (OR-Tools)",
        f"{plan['summary']['dispatches']} dispatch(es), solver {plan['summary']['solver_status']}",
        int((time.perf_counter() - started) * 1000),
    )
    assignments = [a for a in plan["assignments"] if rtype is None or a["resource_type"] == rtype]
    unassigned = plan["unassigned_incidents"]
    if rtype:
        unassigned = [dict(u, missing=[m for m in u["missing"] if m["need"] == rtype])
                      for u in unassigned if any(m["need"] == rtype for m in u["missing"])]

    by_id = {r["id"]: r for r in available}
    routes = []
    for item in assignments[:3]:
        resource = by_id.get(item["resource_id"])
        if not resource or not _has_coords(resource.get("lat"), resource.get("lon")):
            continue
        inc = await hub.call("incident", "get_incident", {"incident_id": item["incident_id"]}, single=True)
        if inc.get("error") or not _has_coords(inc.get("lat"), inc.get("lon")):
            continue
        route = await hub.call("mapping", "get_route", {
            "start_lat": resource["lat"], "start_lon": resource["lon"],
            "end_lat": inc["lat"], "end_lon": inc["lon"], "use_osrm": use_osrm,
        }, single=True)
        routes.append({
            "resource": item["resource_name"], "incident": item["incident_id"],
            "distance_km": route.get("distance_km"), "duration_min": route.get("duration_min"),
            "route_source": route.get("route_source"), "blocked": route.get("blocked"),
            "used_alternative": route.get("used_alternative"), "note": route.get("note"),
        })

    return {
        "resource_type": rtype or "all",
        "available": [{k: r.get(k) for k in ("id", "name", "type", "crew_size", "capacity_people")}
                      for r in available],
        "assignments": [{k: a.get(k) for k in ("resource_name", "resource_type", "incident_id",
                                               "incident_title", "priority", "value",
                                               "eta_min", "cost", "explanation")}
                        for a in assignments],
        "unassigned": unassigned,
        "unused_resources": [u for u in plan["unused_resources"] if rtype is None or u["type"] == rtype],
        "routes": routes,
        "plan_summary": plan["summary_text"],
        "next_step": ("To turn this into proposals, open Resource Optimization and click "
                      "'Send plan to Approval Center'. Nothing has been dispatched."),
    }


async def _shelter_room(hub, params, conn, use_osrm):
    need = params.get("min_free")
    if not need:
        return {"error": "Please say how many people, for example: Which shelter can accommodate 30 people?"}
    rows = await hub.call("resource", "get_shelters", {"min_free": need})
    out = {"min_free": need, "matching_count": len(rows),
           "shelters": [{k: r.get(k) for k in ("id", "name", "free_space", "capacity",
                                               "road_access", "status", "facilities")}
                        for r in rows[:5]]}
    if not rows:
        cap = await hub.call("resource", "get_shelter_capacity", single=True)
        out["total_free_space_all_open_shelters"] = cap.get("free_space")
        out["note"] = "No single open shelter has room for that many people."
    return out


async def _availability(hub, params, conn, use_osrm):
    topics = params.get("topics") or list(TOPICS)
    out = {}
    if "boats" in topics:
        rows = await hub.call("resource", "get_available_boats")
        out["boats"] = {"count": len(rows), "names": [r.get("name") for r in rows]}
    if "ambulances" in topics:
        rows = await hub.call("resource", "get_available_ambulances")
        out["ambulances"] = {"count": len(rows), "names": [r.get("name") for r in rows]}
    if "teams" in topics:
        rows = await hub.call("resource", "get_available_teams")
        out["teams"] = {
            "rescue_teams": sum(r.get("type") == "rescue_team" for r in rows),
            "medical_teams": sum(r.get("type") == "medical_team" for r in rows),
            "names": [r.get("name") for r in rows],
        }
    if "shelters" in topics:
        cap = await hub.call("resource", "get_shelter_capacity", single=True)
        out["shelters"] = {k: cap.get(k) for k in
                           ("shelters_open", "total_capacity", "occupied", "free_space")}
    if "hospitals" in topics:
        cap = await hub.call("resource", "get_hospital_capacity", single=True)
        out["hospitals"] = {k: cap.get(k) for k in
                            ("hospitals_usable", "available_beds", "icu_available")}
    return out


async def _nearby(hub, params, conn, use_osrm):
    place = params.get("place")
    if not place:
        return {"error": "Please name a place, for example: What is happening near the Kabul River Bridge?"}
    geo = await hub.call("mapping", "geocode_location", {"name": place}, single=True)
    if not geo.get("found"):
        return {"error": f"I could not find '{place}' in the place list."}
    spot = geo["matches"][0]
    near = await hub.call("incident", "get_nearby_incidents",
                          {"lat": spot["lat"], "lon": spot["lon"], "radius_km": 3.0, "limit": 10})
    return {
        "place": {k: spot.get(k) for k in ("id", "name", "lat", "lon", "match")},
        "radius_km": 3,
        "incidents": [dict(_slim_incident(i), distance_km=i.get("distance_km")) for i in near],
    }


async def _help(hub, params, conn, use_osrm):
    return {"supported_questions": SUPPORTED_QUESTIONS}


RUNNERS = {
    "top_urgent": _top_urgent, "medical_incidents": _medical, "explain_incident": _explain,
    "allocate": _allocate, "shelter_room": _shelter_room, "availability": _availability,
    "nearby": _nearby, "help": _help,
}


# -------------------------------------------------------------- answers
def _incident_line(i: dict) -> str:
    medical = "medical emergency" if i.get("medical_emergency") else "no medical emergency"
    return (f"{i.get('id')} ({i.get('priority')}): {i.get('title')} - "
            f"{i.get('estimated_affected') or 0} affected, {i.get('vulnerable_people') or 0} vulnerable, "
            f"{medical}, {i.get('evidence_confidence')}% confidence")


def fallback_answer(intent: str, results: dict) -> str:
    """Plain template answers, used when the LLM is unavailable or fails the grounding check."""
    if results.get("error"):
        return results["error"]
    if intent == "top_urgent":
        lines = [f"Top {len(results['incidents'])} open incidents (ranked by {results['ranking_rule']}):"]
        lines += [f"{n}. {_incident_line(i)}" for n, i in enumerate(results["incidents"], 1)]
        return "\n".join(lines)
    if intent == "medical_incidents":
        lines = [f"{results['count']} open incident(s) involve a medical emergency:"]
        lines += [f"- {_incident_line(i)}" for i in results["incidents"]]
        return "\n".join(lines)
    if intent == "explain_incident":
        i = results["incident"]
        lines = [f"{i['id']} is {i.get('priority')}: {i.get('title')}.",
                 f"Facts: {i.get('estimated_affected') or 0} affected, "
                 f"{i.get('vulnerable_people') or 0} vulnerable, "
                 f"{'a medical emergency' if i.get('medical_emergency') else 'no medical emergency'}, "
                 f"isolation level {i.get('isolation')}, evidence confidence {i.get('evidence_confidence')}%.",
                 f"Based on {results['report_count']} linked report(s)."]
        check = results.get("priority_agent_check")
        if check:
            lines.append(f"Priority Agent formula check: {check.get('priority')} "
                         f"(score {check.get('priority_score')}).")
        if i.get("conflict_note"):
            lines.append(f"Conflict note: {i['conflict_note']}")
        return "\n".join(lines)
    if intent == "allocate":
        lines = [results["plan_summary"]]
        lines += [f"- {a['explanation']}" for a in results["assignments"]]
        for r in results["routes"]:
            extra = " (a blocked road is on the route)" if r.get("blocked") else ""
            lines.append(f"Route {r['resource']} to {r['incident']}: {r['distance_km']} km, "
                         f"{r['duration_min']} min ({r['route_source']}){extra}")
        for u in results["unassigned"]:
            lines.append(f"Unmet: {u['incident_id']} - " + "; ".join(m["reason"] for m in u["missing"]))
        if not results["assignments"]:
            lines.append("No allocation to recommend right now.")
        lines.append(results["next_step"])
        return "\n".join(lines)
    if intent == "shelter_room":
        if results["shelters"]:
            lines = [f"{results['matching_count']} open shelter(s) can take {results['min_free']} more people:"]
            lines += [f"- {s['name']}: {s['free_space']} free, road access {s['road_access']}"
                      for s in results["shelters"]]
            return "\n".join(lines)
        return (f"No single open shelter has room for {results['min_free']} people. Total free space "
                f"across open shelters is {results.get('total_free_space_all_open_shelters')}.")
    if intent == "availability":
        lines = []
        if "boats" in results:
            lines.append(f"Boats available: {results['boats']['count']}")
        if "ambulances" in results:
            lines.append(f"Ambulances available: {results['ambulances']['count']}")
        if "teams" in results:
            lines.append(f"Rescue teams available: {results['teams']['rescue_teams']}, "
                         f"medical teams: {results['teams']['medical_teams']}")
        if "shelters" in results:
            s = results["shelters"]
            lines.append(f"Shelters: {s['occupied']} of {s['total_capacity']} places used, "
                         f"{s['free_space']} free in {s['shelters_open']} open shelter(s)")
        if "hospitals" in results:
            h = results["hospitals"]
            lines.append(f"Hospitals: {h['available_beds']} beds free, {h['icu_available']} ICU beds free")
        return "\n".join(lines)
    if intent == "nearby":
        place = results["place"]
        lines = [f"{len(results['incidents'])} incident(s) within {results['radius_km']} km of {place['name']}:"]
        lines += [f"- {_incident_line(i)} ({i.get('distance_km')} km)" for i in results["incidents"]]
        return "\n".join(lines)
    return "I can answer questions like:\n" + "\n".join(f"- {q}" for q in SUPPORTED_QUESTIONS)


ANSWER_SYSTEM = (
    "You are the ReliefMesh copilot for an emergency-response coordinator. Use ONLY the tool "
    "results you are given. Never invent incidents, numbers or resources. Be concise (at most "
    "8 short lines). Mention incident ids and resource names. If the data does not answer the "
    "question, say so. Never say anything was dispatched: dispatch needs a human to approve it "
    "in the Approval Center. Answer in the same language and script as the question."
)


def _grounded(answer: str, results_text: str) -> bool:
    """Every incident id in the answer must appear in the tool results."""
    return set(re.findall(r"INC-\d+", answer)) <= set(re.findall(r"INC-\d+", results_text))


def compose_answer(question: str, intent: str, results: dict, llm_client) -> str:
    text = json.dumps(results, ensure_ascii=False, default=str)
    if len(text) > 7000:
        text = text[:7000] + "..."
    prompt = ("Question: " + question + "\nIntent: " + intent
              + "\nTool results (JSON):\n" + text
              + '\n\nReply as JSON: {"answer": "<your answer>"}')
    data = llm_client.complete_json(prompt, system=ANSWER_SYSTEM)
    answer = str(data.get("answer") or "").strip()
    if not answer:
        raise LLMError("The model returned an empty answer.")
    if not _grounded(answer, text):
        raise LLMError("The answer mentioned an incident that is not in the data.")
    return answer


# ------------------------------------------------------------- the entry
async def _execute(params, conn, db_path, use_osrm):
    hub = McpHub(db_path)
    try:
        async with hub:
            results = await RUNNERS[params["intent"]](hub, params, conn, use_osrm)
    except Exception as error:  # noqa: BLE001 - keep the tool log even when something fails
        results = {"error": f"Could not read the data: {error}"}
    return results, hub.calls


def ask(question: str, db_path=None, llm_client=None, use_llm=True, use_osrm=True) -> dict:
    question = (question or "").strip()[:500]
    if not question:
        raise ValueError("question must not be empty")
    path = Path(db_path) if db_path else default_db_path()

    llm = None
    if use_llm:
        try:
            llm = llm_client or default_chat_client()
        except Exception:  # noqa: BLE001
            llm = None

    params, routed_by = route_question(question), "rules"
    if params is None:
        routed_by = "llm"
        if llm is not None:
            try:
                params = classify_with_llm(question, llm)
            except Exception:  # noqa: BLE001
                params = None
        if params is None:
            params, routed_by = normalize_params(None), "none"

    conn = get_connection(path)
    try:
        results, calls = _run_async(_execute(params, conn, path, use_osrm))
    finally:
        conn.close()

    answer, answered_by = None, "template"
    if llm is not None and params["intent"] != "help" and "error" not in results:
        try:
            answer, answered_by = compose_answer(question, params["intent"], results, llm), "llm"
        except Exception:  # noqa: BLE001
            answer = None
    if answer is None:
        answer = fallback_answer(params["intent"], results)

    return {"question": question, "intent": params["intent"], "routed_by": routed_by,
            "answer": answer, "answered_by": answered_by, "tool_calls": calls,
            "results": results, "disclaimer": DISCLAIMER}


if __name__ == "__main__":
    # Quick test without the server:
    #   python -m agents.copilot "Which incidents involve medical emergencies?"
    #   add --no-llm to use the template answers only
    args = [a for a in sys.argv[1:] if a != "--no-llm"]
    if not args:
        print('Usage: python -m agents.copilot "your question" [--no-llm]')
        raise SystemExit(1)
    out = ask(" ".join(args), use_llm="--no-llm" not in sys.argv)
    print(f"INTENT: {out['intent']} (routed by {out['routed_by']})")
    print(f"ANSWER ({out['answered_by']}):\n{out['answer']}\n")
    print("MCP TOOLS USED:")
    for call in out["tool_calls"]:
        print(f"  {call['server']}.{call['tool']} {json.dumps(call['args'])} -> {call['result']} ({call['ms']} ms)")
    print("\n" + out["disclaimer"])