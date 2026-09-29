"""A tiny JSON-file cache so repeated evaluation runs don't re-spend LLM
quota re-extracting reports that haven't changed.

Not used by the live pipeline itself — a real system processes each new
report exactly once. This exists purely to make iterative testing and
large-scale evaluation (Phase 9) practical and affordable, especially on a
rate-limited free-tier API key.

Important: a FAILED extraction (the LLM call errored, so the Intake Agent fell
back to safe defaults) is never cached. Caching it would make a temporary rate
limit look like a permanent, confident answer.
"""

import json
from pathlib import Path

FAILURE_MARKER = "LLM extraction failed"


def extraction_failed(result: dict) -> bool:
    """True if the Intake Agent fell back to defaults because the LLM call failed."""
    return any(str(n).startswith(FAILURE_MARKER) for n in result.get("extraction_notes", []))


def load_cache(cache_path) -> dict:
    path = Path(cache_path)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_cache(cache_path, cache: dict) -> None:
    path = Path(cache_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def prune_failed(cache_path) -> list[str]:
    """Removes any previously cached failed extractions. Returns their report ids."""
    cache = load_cache(cache_path)
    bad = [rid for rid, result in cache.items() if extraction_failed(result)]
    if bad:
        for rid in bad:
            del cache[rid]
        save_cache(cache_path, cache)
    return bad


def cached_intake(report: dict, conn, cache_path, llm_client=None, force: bool = False) -> dict:
    """Runs the Intake Agent on one report, unless a good cached result already
    exists for its id. Saves after every successful call (not just at the end),
    so a crash partway through never loses progress already paid for. Failed
    extractions are returned to the caller but NOT saved."""
    from agents.intake_agent import run_intake

    cache = load_cache(cache_path)
    cached = cache.get(report["id"])
    if not force and cached is not None and not extraction_failed(cached):
        return cached

    result = run_intake(report, conn=conn, llm_client=llm_client)
    if not extraction_failed(result):
        cache[report["id"]] = result
        save_cache(cache_path, cache)
    return result