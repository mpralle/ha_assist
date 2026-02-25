"""Prompt builder for Step 2: EntitySelector."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Set


# Domains where entity_selector should resolve entities and services.
# Sensor-only domains are excluded since they don't have controllable actions.
CONTROLLABLE_DOMAINS: Set[str] = {
    "light", "switch", "lock", "cover", "climate", "fan",
    "media_player", "vacuum", "humidifier", "alarm_control_panel",
    "scene", "script", "automation", "input_boolean", "input_number",
    "input_select", "button",
}

STATE_DOMAINS: Set[str] = {
    "sensor", "binary_sensor", "weather", "person", "device_tracker",
}


def _build_entity_list(ha_context: Dict[str, Any]) -> str:
    """Build a formatted list of entities grouped by domain."""
    details: List[Dict[str, Any]] = ha_context.get("entity_details", [])
    services: Dict[str, List[str]] = ha_context.get("services", {})

    # Group entities by domain
    by_domain: Dict[str, List[Dict[str, Any]]] = {}
    for e in details:
        domain = e["domain"]
        if domain in CONTROLLABLE_DOMAINS or domain in STATE_DOMAINS:
            by_domain.setdefault(domain, []).append(e)

    if not by_domain:
        return "No entities available."

    lines: List[str] = []
    for domain in sorted(by_domain.keys()):
        entities = by_domain[domain]
        domain_services = services.get(domain, [])

        lines.append(f"## {domain}")
        if domain_services and domain in CONTROLLABLE_DOMAINS:
            lines.append(f"Available services: {', '.join(sorted(domain_services))}")
        for e in sorted(entities, key=lambda x: x["entity_id"]):
            lines.append(
                f"- {e['entity_id']}  "
                f"(name: \"{e['friendly_name']}\", state: {e['state']})"
            )
        lines.append("")

    return "\n".join(lines)


def build_prompt(ha_context: Dict[str, Any]) -> str:
    """Build the system prompt for the EntitySelector step."""
    entity_list = _build_entity_list(ha_context)

    return f"""\
You are an Entity Selector for a Home Assistant smart home system.

INPUT
You receive a JSON object with an "actions" array from the previous step (TaskExtractor).
Each action has a "type" and a "task" describing what the user wants.

YOUR JOB
For each action with type "device_control", resolve:
1. Which specific entity_id(s) are needed to fulfil the "task"
2. Which Home Assistant service to call on each entity

For each action with type "state", resolve:
1. Which specific entity_id to read the state from

For actions with type "list", "condition", "sequence", or "monitor", pass them through unchanged but resolve any nested actions inside "then", "else", or "steps".

OUTPUT FORMAT (STRICT)
Return a single JSON object with the same structure as the input, but each resolved action now includes:
- "entity_id": the exact Home Assistant entity_id (string)
- "service": the exact Home Assistant service to call (string, e.g. "light.turn_off")

For "state" type actions, only add "entity_id" (no service needed).

If a task maps to multiple entities, create separate action objects for each.

Example input:
{{ "actions": [{{ "type": "device_control", "task": "Turn off kitchen lights" }}] }}

Example output:
{{ "actions": [{{ "type": "device_control", "task": "Turn off kitchen lights", "entity_id": "light.kitchen", "service": "light.turn_off" }}] }}

Rules:
- Return ONLY valid JSON, no explanations, no markdown.
- Use exact entity_id values from the list below.
- Use exact service names from the available services listed.
- If you cannot match a task to an entity, set "entity_id" to "unknown" and "service" to "unknown".
- Match entities by their friendly_name or entity_id — pick the closest match.

AVAILABLE ENTITIES AND SERVICES

{entity_list}"""
