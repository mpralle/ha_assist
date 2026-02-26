"""Step 1: TaskExtractor."""

from __future__ import annotations

from typing import Any, Dict

from ..jimmy_connection import async_send_msg
from ..prompts.task_extractor import build_prompt


# Recursive schema: task objects can nest inside condition/sequence/monitor.
_TASK_OBJECT: Dict[str, Any] = {
    "type": "object",
    "required": ["type"],
    "properties": {
        "type": {"type": "string"},
        "task": {"type": "string"},
        "check": {"type": "object"},
        "condition": {"type": "object"},
        "then": {"type": "array"},
        "else": {"type": "array"},
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
            "items": _TASK_OBJECT,
        },
    },
}


class TaskExtractor:
    """Step 1 of the agent pipeline."""

    async def async_run(self, user_input: str, ha_context: Dict[str, Any]) -> Any:
        system_prompt = build_prompt(ha_context)
        return await async_send_msg(system_prompt, user_input, SCHEMA)
