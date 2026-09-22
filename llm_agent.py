"""
llm_agent.py
------------
Optional LLM-powered reasoning layer. If an ANTHROPIC_API_KEY environment
variable is set and the `anthropic` package is installed, the AlertAgent
will use this module to turn the structured agent findings for a cycle
into a short natural-language operator briefing (the kind of "explain the
situation to a human on shift" step that's hard to do with pure
rule-based logic).

If no API key / package is available, `llm_available()` returns False and
the rest of the system falls back to purely rule-based alert text -- the
whole app works fine without this file doing anything.
"""

import os
import json

_client = None
_checked = False


def llm_available() -> bool:
    global _client, _checked
    if _checked:
        return _client is not None
    _checked = True
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return False
    try:
        import anthropic
        _client = anthropic.Anthropic(api_key=api_key)
        return True
    except Exception:
        _client = None
        return False


def explain_with_llm(state: dict) -> str:
    """Ask Claude to summarize this cycle's findings as a short briefing.
    `state` is the shared blackboard dict produced by the agent pipeline."""
    if not llm_available():
        raise RuntimeError("LLM not configured")

    payload = {
        "hotspots": [{"id": h[0], "name": h[1], "level": h[2]} for h in state.get("hotspots", [])],
        "incidents": state.get("incidents", []),
        "signal_recommendations": state.get("signal_recommendations", {}),
        "route_advisories": state.get("route_advisories", {}),
    }

    prompt = (
        "You are an assistant briefing a city traffic-control-room operator. "
        "Given this structured JSON of current hotspots, incidents, and the "
        "recommended signal/routing actions already decided by the automated "
        "system, write a concise 2-4 sentence spoken-style briefing a human "
        "operator could read aloud on shift handover. Be factual, do not "
        "invent details not present in the JSON.\n\n"
        f"JSON:\n{json.dumps(payload, indent=2)}"
    )

    response = _client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in response.content if hasattr(block, "text")).strip()
