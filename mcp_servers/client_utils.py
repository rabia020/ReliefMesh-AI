"""Shared helper for reading MCP tool results in our demo clients."""
import json


def unpack(result, single=False):
    """Turn an MCP tool result into normal Python data.

    single=False -> the tool returns a list (get_incidents, ...)
    single=True  -> the tool returns one object (get_incident, ...)
    """
    data = result.structuredContent
    if data is not None and isinstance(data, dict) and "result" in data:
        data = data["result"]
    elif data is None:
        data = [json.loads(block.text) for block in result.content]

    if single:
        if isinstance(data, list):
            return data[0] if data else {}
        return data
    if isinstance(data, dict):
        return [data]
    return data