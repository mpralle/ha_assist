"""Step 2: EntitySelector."""

from __future__ import annotations

import json
from typing import Any, Dict

from jimmy_connection import sendMsg
from prompts.entity_selector import build_prompt


# The output schema: same as task_extractor but each action now includes
# entity_id and service fields.
_RESOLVED_ACTION: Dict[str, Any] = {
    "type": "object",
    "required": ["type"],
    "properties": {
        "type": {"type": "string"},
        "task": {"type": "string"},
        "entity_id": {"type": "string"},
        "service": {"type": "string"},
        "check": {"type": "object"},
        "logic": {"type": "string"},
        "then": {"type": "array"},
        "else": {"type": "array"},
        "steps": {"type": "array"},
        "poll_seconds": {"type": "number"},
        "timeout_seconds": {"type": "number"},
    },
    "additionalProperties": True,
}

SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["actions"],
    "additionalProperties": False,
    "properties": {
        "actions": {
            "type": "array",
            "items": _RESOLVED_ACTION,
        },
    },
}


class EntitySelector:
    """Step 2 of the agent pipeline."""

    def run(self, previous_output: Any, ha_context: Dict[str, Any]) -> Any:
        system_prompt = build_prompt(ha_context)
        # Pass the task_extractor result as the user message (JSON string)
        user_message = json.dumps(previous_output, ensure_ascii=False)
        return sendMsg(system_prompt, user_message, SCHEMA)
