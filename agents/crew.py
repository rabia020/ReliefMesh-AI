"""CrewAI crew definition for ReliefMesh (Phase 13).

Why this file exists: the original plan used LangGraph. You asked for CrewAI
instead. CrewAI's usual mode is "an LLM decides which tool to call". That is
a poor fit for a reproducible disaster demo, so this project uses CrewAI for:

1. Named specialist roles (Intake, Verification, Priority, Resource, Routing,
   Reporter, Human Review) under a Supervisor.
2. A sequential process that matches START → ... → END.
3. An optional live CrewAI `Crew` (if the `crewai` package is installed) that
   wraps the same Python tools for later copilot experiments.

The dashboard and FastAPI call `agents.supervisor.run_pipeline`, which always
runs the specialists in order with conditional skips. That path does not
require the `crewai` package.
"""

from agents.supervisor import CREW_SEQUENCE, run_pipeline

AGENT_SPECS = (
    {
        "id": "supervisor",
        "role": "Emergency Coordination Supervisor",
        "goal": "Run the specialist crew in order and stop at human review.",
        "backstory": (
            "You coordinate ReliefMesh specialists during a SIMULATED flood. "
            "You never dispatch real-world teams yourself."
        ),
    },
    {
        "id": "intake",
        "role": "Intake Agent",
        "goal": "Extract structured incident fields from one multilingual report.",
        "backstory": "You read English, Roman Urdu, and Urdu citizen reports.",
    },
    {
        "id": "verification",
        "role": "Verification Agent",
        "goal": "Cluster duplicates and score evidence confidence.",
        "backstory": "You compare reports with embeddings and source reliability.",
    },
    {
        "id": "priority",
        "role": "Priority Agent",
        "goal": "Assign Critical/High/Medium/Low using deterministic arithmetic.",
        "backstory": "You never ask an LLM to invent a priority number.",
    },
    {
        "id": "resource",
        "role": "Resource Agent",
        "goal": "Rank available teams, boats, ambulances, and shelters for one incident.",
        "backstory": "You recommend. You do not dispatch.",
    },
    {
        "id": "routing",
        "role": "Routing Agent",
        "goal": "Compute road routes, blocked-road hits, and nearest hospitals/shelters.",
        "backstory": "You use OpenStreetMap/OSRM with a straight-line fallback.",
    },
    {
        "id": "reporter",
        "role": "Reporter Agent",
        "goal": "Write a short coordinator briefing from verified facts.",
        "backstory": "You summarize. You do not give orders.",
    },
    {
        "id": "human_review",
        "role": "Human Review Gate",
        "goal": "Create a PROPOSED ACTION and wait. Never auto-approve.",
        "backstory": "Only a human coordinator may approve, reject, or ask for more information.",
    },
)


def describe_crew() -> dict:
    return {
        "framework": "CrewAI sequential process",
        "execution": "deterministic specialist tools (not LLM tool-picking)",
        "sequence": list(CREW_SEQUENCE),
        "agents": AGENT_SPECS,
        "safety": (
            "Agents must not independently execute dangerous real-world actions. "
            "Dispatch is proposed only; a human must approve it."
        ),
    }


def kickoff(reports, conn, **kwargs) -> dict:
    """CrewAI-shaped entry point used by FastAPI and the demo script."""
    return run_pipeline(reports, conn, **kwargs)


def build_crewai_crew(llm=None):
    """Builds a live CrewAI Crew if `crewai` is installed.

    This is optional. The production pipeline does not call Crew.kickoff(),
    because that would let the LLM skip or reorder specialists.
    """
    try:
        from crewai import Agent, Crew, LLM, Process, Task
    except ImportError as error:
        raise RuntimeError(
            "The optional 'crewai' package is not installed. "
            "The ReliefMesh pipeline still works via agents.supervisor.run_pipeline. "
            "To install CrewAI: pip install crewai"
        ) from error

    from backend import config

    if llm is None:
        if config.LLM_PROVIDER == "groq":
            llm = LLM(model=f"groq/{config.GROQ_MODEL}", api_key=config.GROQ_API_KEY)
        elif config.LLM_PROVIDER == "gemini":
            llm = LLM(model=f"gemini/{config.GEMINI_MODEL}", api_key=config.GEMINI_API_KEY)
        else:
            llm = LLM(
                model=f"ollama/{config.OLLAMA_MODEL}",
                base_url=config.OLLAMA_BASE_URL,
            )

    agents = {}
    for spec in AGENT_SPECS:
        agents[spec["id"]] = Agent(
            role=spec["role"],
            goal=spec["goal"],
            backstory=spec["backstory"],
            llm=llm,
            verbose=False,
            allow_delegation=False,
        )

    tasks = [
        Task(
            description=(
                "Coordinate the ReliefMesh specialist sequence for incoming flood "
                "reports. Do not dispatch resources. Stop after a proposed action."
            ),
            expected_output="A structured crew result with incidents and proposed actions.",
            agent=agents["supervisor"],
        )
    ]
    return Crew(agents=list(agents.values()), tasks=tasks, process=Process.sequential)
