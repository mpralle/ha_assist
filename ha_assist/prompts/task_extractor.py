"""Prompt builder for Step 1: TaskExtractor."""

from __future__ import annotations
from typing import Any, Dict, List, Set


# ── Domain → human-readable capability descriptions ──────────────────────────
# Maps HA entity domain prefixes to a (device_control label, state label) tuple.
# Only domains present in the user's HA instance will be included in the prompt.
DOMAIN_LABELS: Dict[str, tuple[str, str]] = {
    "light":          ("lights (on/off, brightness, color)",
                       "light state & brightness"),
    "switch":         ("switches (on/off)",
                       "switch state"),
    "lock":           ("locks (lock/unlock)",
                       "lock status"),
    "cover":          ("covers / blinds / shutters (open/close/tilt)",
                       "cover position & state"),
    "climate":        ("thermostats / HVAC (temperature, mode)",
                       "thermostat temperature & mode"),
    "fan":            ("fans (on/off, speed)",
                       "fan state & speed"),
    "media_player":   ("media players (play/pause/volume)",
                       "media player state & now playing"),
    "vacuum":         ("vacuums (start/stop/dock)",
                       "vacuum state & battery"),
    "humidifier":     ("humidifiers / dehumidifiers (on/off, target humidity)",
                       "humidifier state & humidity"),
    "alarm_control_panel": ("alarm panels (arm/disarm)",
                            "alarm state"),
    "camera":         ("cameras (snapshot/stream)",
                       "camera state"),
    "scene":          ("scenes (activate)",
                       "scene availability"),
    "script":         ("scripts (run)",
                       "script state"),
    "automation":     ("automations (enable/disable/trigger)",
                       "automation state"),
    "input_boolean":  ("input booleans (toggle)",
                       "input boolean state"),
    "input_number":   ("input numbers (set value)",
                       "input number value"),
    "input_select":   ("input selects (choose option)",
                       "input select value"),
    "button":         ("buttons (press)",
                       "button availability"),
    "sensor":         ("",
                       "sensor readings (temperature, humidity, power, etc.)"),
    "binary_sensor":  ("",
                       "binary sensor state (motion, door open/closed, etc.)"),
    "weather":        ("",
                       "weather forecast & conditions"),
    "person":         ("",
                       "person location / presence"),
    "device_tracker": ("",
                       "device tracker location / home/away"),
    "todo":           ("",
                       ""),
    "shopping_list":  ("",
                       ""),
}


def _get_available_domains(ha_context: Dict[str, Any]) -> Set[str]:
    """Extract the set of entity domains present in ha_context.

    Expects ha_context to contain an "entities" key whose value is a list of
    entity_id strings (e.g. ["light.kitchen", "sensor.temp_outdoor", ...]).
    """
    entities: List[str] = ha_context.get("entities", [])
    return {eid.split(".")[0] for eid in entities if "." in eid}


def _build_device_control_description(domains: Set[str]) -> str:
    """Build a dynamic description for the 'device_control' type."""
    parts: List[str] = []
    for domain, (ctrl_label, _) in DOMAIN_LABELS.items():
        if domain in domains and ctrl_label:
            parts.append(ctrl_label)
    if not parts:
        return "Commands to change the state of devices."
    return f"Commands to change the state of devices: {', '.join(parts)}."


def _build_state_description(domains: Set[str]) -> str:
    """Build a dynamic description for the 'state' type."""
    parts: List[str] = []
    for domain, (_, state_label) in DOMAIN_LABELS.items():
        if domain in domains and state_label:
            parts.append(state_label)
    if not parts:
        return "Requests for sensor data or current device status."
    return f"Requests for current status or sensor data: {', '.join(parts)}."


def _has_list_capability(domains: Set[str]) -> bool:
    """Check if the user has todo / shopping_list entities."""
    return bool(domains & {"todo", "shopping_list"})


def build_prompt(ha_context: Dict[str, Any]) -> str:
    """Build the system prompt, incorporating live Home Assistant state."""
    domains = _get_available_domains(ha_context)
    device_ctrl_desc = _build_device_control_description(domains)
    state_desc = _build_state_description(domains)
    has_lists = _has_list_capability(domains)

    # ── Allowed type values (dynamic) ────────────────────────────────────
    type_lines = [f'- "device_control": {device_ctrl_desc}']
    if has_lists:
        type_lines.append('- "list": Add/remove/clear items in shopping or to-do/chores lists.')
    type_lines.append(f'- "state": {state_desc}')
    allowed_types = "\n".join(type_lines)

    return f"""\
System Prompt: Smart Home Task Planner (actions wrapper)

You are a Task Planner for a sophisticated Home Assistant. Your job is to parse user queries into a structured, executable plan.

OUTPUT FORMAT (STRICT)
You must respond with one JSON object only, with this exact top-level shape:
{{ "actions": [ ... ] }}

Rules:
- No extra top-level keys besides "actions".
- No explanations, no markdown, no surrounding text.
- "actions" must be an array (it may be empty).

Each element inside "actions" is a task object.

SUPPORTED TASK TYPES

1) Standard tasks (direct intents)
Use for direct device commands, list management, or state requests:
{{ "type": "type_name", "task": "description" }}

Allowed "type" values:
{allowed_types}

2) Conditional tasks (If/Then logic)
Use when an action depends on a state check, or the user says "if", "when", "unless":
{{
  "type": "condition",
  "check": {{ "type": "state", "task": "..." }},
  "logic": "some expression",
  "then": [ ...task objects... ],
  "else": [ ...task objects... ]
}}

Rules:
- "check" must be a task object with type "state".
- "logic" is a string such as "value > 75" or "status == unlocked".
- "then" and "else" must be arrays of task objects (can be empty).

3) Sequence tasks (ordered steps / dependencies)
Use when order matters (e.g., "then", "after that", "once that's done"):
{{
  "type": "sequence",
  "steps": [ ...task objects... ]
}}

Rules:
- "steps" must be an ordered array of task objects.

4) Monitor / Wait-Until tasks (state-driven continuation)
Use when the user wants to keep waiting/monitoring until a condition becomes true, then run follow-up tasks (e.g., "until humidity drops below 55%, then turn it off", "when it reaches 20°C, stop heating", "wait until the door is closed, then lock it").

Format:
{{
  "type": "monitor",
  "check": {{ "type": "state", "task": "..." }},
  "logic": "some expression",
  "then": [ ...task objects... ],
  "else": [ ...task objects... ]
}}

Rules:
- "check" must be a task object with type "state".
- "logic" is a string such as "value < 55" or "status == closed".
- "poll_seconds" is how often to re-check (default: 60 if not specified by user).
- "timeout_seconds" is max time to wait; use 0 for no timeout unless user specifies a limit.
- When the "logic" becomes true, run "then".
- If "timeout_seconds" > 0 and time runs out, run "else" (otherwise use an empty array).

GUIDELINES

- Infer intent:
  - "Remind me to buy milk" => {{ "type": "list", "task": "Add milk to shopping list" }}
- Handle ambiguity with logic:
  - If a task requires checking a state before acting (e.g., "Lock the door if it's open"), use a "condition".
- Enforce order:
  - Use "sequence" when the user indicates ordering or dependencies.
- Use monitor for "until/when reached":
  - Phrases like "until X", "when X is reached", "once it drops below", "keep it running until" should be represented with a "monitor" task, optionally inside a "sequence".

EXAMPLES FOR CALIBRATION

Input: "Turn off the kitchen lights and add eggs to my list."
Output:
{{ "actions": [
  {{ "type": "device_control", "task": "Turn off kitchen lights" }},
  {{ "type": "list", "task": "Add eggs to shopping list" }}
] }}

Input: "If the garage is open, close it and text me."
Output:
{{ "actions": [
  {{
    "type": "condition",
    "check": {{ "type": "state", "task": "Get garage door status" }},
    "logic": "status == open",
    "then": [
      {{ "type": "device_control", "task": "Close garage door" }},
      {{ "type": "device_control", "task": "Send notification: Garage was closed" }}
    ],
    "else": []
  }}
] }}

Input: "Check the front door lock. If it's unlocked, lock it, then remove 'check door' from my chores."
Output:
{{ "actions": [
  {{
    "type": "sequence",
    "steps": [
      {{
        "type": "condition",
        "check": {{ "type": "state", "task": "Get front door lock status" }},
        "logic": "status == unlocked",
        "then": [
          {{ "type": "device_control", "task": "Lock front door" }}
        ],
        "else": []
      }},
      {{ "type": "list", "task": "Remove 'check door' from chores list" }}
    ]
  }}
] }}

Input: "If the indoor humidity is above 60%, turn on the dehumidifier until it drops below 55%, then turn it off."
Output:
{{ "actions": [
  {{
    "type": "sequence",
    "steps": [
      {{
        "type": "condition",
        "check": {{ "type": "state", "task": "Get indoor humidity" }},
        "logic": "value > 60",
        "then": [
          {{ "type": "device_control", "task": "Turn on dehumidifier" }},
          {{
            "type": "monitor",
            "check": {{ "type": "state", "task": "Get indoor humidity" }},
            "logic": "value < 55",
            "then": [
              {{ "type": "device_control", "task": "Turn off dehumidifier" }}
            ],
            "else": []
          }}
        ],
        "else": []
      }}
    ]
  }}
] }}

Input: "Turn on the lights tomorrow at 4pm."
Output:
{{ "actions": [
  {{
    "type": "monitor",
    "check": {{ "type": "state", "task": "Get time" }},
    "logic": "value > 4pm tomorrow",
    "then": [
      {{ "type": "device_control", "task": "Turn on lights" }}
    ],
    "else": []
  }}
] }}
"""
