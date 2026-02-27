"""Prompt builder for Step 4: Summary."""

from __future__ import annotations

from typing import Any, Dict, List


def _flatten_results(actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Walk the executor output and collect all executed actions with results."""
    flat: List[Dict[str, Any]] = []

    for action in actions:
        action_type = action.get("type")

        if action_type == "device_control" and "result" in action:
            flat.append({
                "entity_id": action.get("entity_id", "unknown"),
                "service": action.get("service", "unknown"),
                "success": action["result"].get("success", False),
                "error": action["result"].get("error"),
            })

        elif action_type == "condition" and "result" in action:
            result = action["result"]
            flat.append({
                "type": "condition",
                "entity_id": result.get("entity_id", "unknown"),
                "actual_state": result.get("actual_state", "unknown"),
                "condition_met": result.get("condition_met", False),
                "branch_executed": result.get("branch_executed", "none"),
            })
            # Include results from the executed branch
            for branch_action in result.get("branch_results", []):
                if branch_action.get("type") == "device_control" and "result" in branch_action:
                    flat.append({
                        "entity_id": branch_action.get("entity_id", "unknown"),
                        "service": branch_action.get("service", "unknown"),
                        "success": branch_action["result"].get("success", False),
                        "error": branch_action["result"].get("error"),
                    })

        elif action_type == "monitor" and "result" in action:
            result = action["result"]
            flat.append({
                "type": "monitor",
                "monitor_created": result.get("monitor_created", False),
                "description": result.get("description", ""),
            })

        # Recurse into nested branches (for conditions without executor results)
        for key in ("then", "else"):
            nested = action.get(key)
            if isinstance(nested, list):
                flat.extend(_flatten_results(nested))

    return flat


def build_prompt(ha_context: Dict[str, Any], *, include_errors: bool = True) -> str:
    """Build the system prompt for the Summary step."""
    error_instruction = ""
    if include_errors:
        error_instruction = (
            "If any action failed, mention the failure and the reason briefly. "
        )
    else:
        error_instruction = (
            "Only mention successful actions. Do not mention any errors or failures. "
        )

    return f"""\
You are a friendly smart home assistant summarizing what just happened.

INPUT
You receive a JSON list of action results. Each item has:
- "entity_id": the device acted on
- "service": the service called (e.g. "light.turn_off")
- "success": true or false
- "error": error message (if failed)
Some items may be condition checks with "type": "condition", "actual_state", and "condition_met".
Some items may be monitor tasks with "type": "monitor", "monitor_created", and "description".

YOUR JOB
Write a short, natural, user-friendly summary of what happened.

Rules:
- Use friendly device names (e.g. "Schreibtischlampe" instead of "light.schreibtischlampe").
- Use natural language (e.g. "I turned off the Schreibtischlampe" not "light.turn_off on light.schreibtischlampe").
- For conditions, briefly mention what was checked and the outcome.
- For monitors, confirm that the monitoring task was set up and briefly say what is being watched.
- {error_instruction}
- Keep it concise — one or two sentences.
- You MUST return valid JSON: {{ "message": "your summary here" }}
- No markdown, no extra text outside the JSON.

Example input: [{{"entity_id": "light.kitchen", "service": "light.turn_off", "success": true}}]
Example output: {{ "message": "I turned off the kitchen light." }}

Example input: [{{"type": "condition", "entity_id": "media_player.tv", "actual_state": "on", "condition_met": true, "branch_executed": "then"}}, {{"entity_id": "light.desk", "service": "light.turn_off", "success": true}}]
Example output: {{ "message": "The TV was on, so I turned off the desk light." }}"""
