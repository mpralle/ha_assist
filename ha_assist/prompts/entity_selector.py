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
    """Build the system prompt for the EntitySelector step.

    The prompt is intentionally simple: the LLM receives a flat list of
    items that need entity resolution and returns a flat list of resolved
    items.  All structural nesting (conditions, sequences, etc.) is handled
    programmatically in the step, not by the LLM.
    """
    entity_list = _build_entity_list(ha_context)

    return f"""\
You are an Entity Selector for a Home Assistant smart home system.

INPUT
You receive a JSON object with an "items" array.
Each item has an "id" (number), "type" ("device_control" or "state"), and "task" (description).

YOUR JOB
For each item, resolve:
1. "entity_id": the exact Home Assistant entity_id that matches the task
2. "service": the exact Home Assistant service to call (only for "device_control" items; omit for "state" items)

OUTPUT FORMAT (STRICT)
Return a JSON object:
{{ "items": [
  {{ "id": 0, "entity_id": "light.kitchen", "service": "light.turn_off" }},
  {{ "id": 1, "entity_id": "sensor.temperature" }}
] }}

Rules:
- Return ONLY valid JSON, no explanations, no markdown.
- Each output item must have the same "id" as the input item.
- "entity_id" MUST be the FULL entity_id including the domain prefix, exactly as listed below (e.g. "light.kitchen", "media_player.musikanlage", NOT just "kitchen" or "musikanlage").
- Use exact service names from the available services listed (e.g. "light.turn_off", "media_player.turn_off").
- If you cannot match a task to an entity, set "entity_id" to "unknown" and "service" to "unknown".
- Match entities by their friendly_name or entity_id — pick the closest match.

AVAILABLE ENTITIES AND SERVICES

{entity_list}"""
