"""Step 4: Summary."""

from __future__ import annotations

from typing import Any, Dict

from jimmy_connection import sendMsg
from prompts.summary import build_prompt


SCHEMA: Dict[str, Any] = {
    # TODO: define expected output schema
}


class Summary:
    """Step 4 of the agent pipeline."""

    def run(self, previous_output: Any, ha_context: Dict[str, Any]) -> Any:
        system_prompt = build_prompt(ha_context)
        return sendMsg(system_prompt, str(previous_output), SCHEMA)
