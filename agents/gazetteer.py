"""A lightweight, best-effort location matcher for the Intake Agent.

This is NOT the real geocoder. Your prompt puts proper geocoding in the
Mapping MCP server (Phase 16) and OSRM-based routing in the Routing Agent
(Phase 12). This module only does simple alias matching against the 30-place
gazetteer that already exists from Phase 2, so the dashboard and Phase 8's
duplicate detection have something usable right away. Phase 16 will replace
match_location() with a proper MCP tool call; the return shape here
(place_id, confidence, matched_alias) is designed to stay compatible with
that later replacement.
"""

import difflib
import re


def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s\u0600-\u06ff]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def load_places(conn) -> list[dict]:
    """Loads places with a pre-normalized alias list for fast matching."""
    from database.queries import list_places

    places = list_places(conn)
    for place in places:
        names = [place["name"]] + (place["aliases"] or [])
        if place.get("name_ur"):
            names.append(place["name_ur"])
        place["_normalized_aliases"] = sorted({_normalize(n) for n in names if n})
    return places


def match_location(location_text: str, places: list[dict]):
    """Best-effort match of free text to a known place.

    Returns a dict: {place_id, place_name, confidence, matched_alias}
    confidence is one of "exact", "contains", "fuzzy", or None if nothing matched.
    """
    result = {"place_id": None, "place_name": None, "confidence": None, "matched_alias": None}
    if not location_text or not location_text.strip():
        return result

    normalized_text = _normalize(location_text)
    if not normalized_text:
        return result

    # 1. Exact match: the whole (normalized) text equals a known alias.
    for place in places:
        if normalized_text in place["_normalized_aliases"]:
            return {"place_id": place["id"], "place_name": place["name"],
                    "confidence": "exact", "matched_alias": normalized_text}

    # 2. Containment: a known alias appears inside the text, or vice versa.
    #    Longer aliases first, so "old bus stand" wins over a short alias like "bus".
    candidates = sorted(
        ((place, alias) for place in places for alias in place["_normalized_aliases"]),
        key=lambda pair: len(pair[1]), reverse=True,
    )
    for place, alias in candidates:
        if len(alias) >= 4 and (alias in normalized_text or normalized_text in alias):
            return {"place_id": place["id"], "place_name": place["name"],
                    "confidence": "contains", "matched_alias": alias}

    # 3. Fuzzy fallback for near-misses (typos, transliteration variants).
    all_aliases = [alias for place in places for alias in place["_normalized_aliases"]]
    close = difflib.get_close_matches(normalized_text, all_aliases, n=1, cutoff=0.8)
    if close:
        matched_alias = close[0]
        for place in places:
            if matched_alias in place["_normalized_aliases"]:
                return {"place_id": place["id"], "place_name": place["name"],
                        "confidence": "fuzzy", "matched_alias": matched_alias}

    return result