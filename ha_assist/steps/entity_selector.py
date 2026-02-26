"""Step 2: EntitySelector — resolve entity_ids and services.

Strategy for small-model reliability:
  1. FLATTEN: Walk the nested action tree and extract every item that needs
     entity resolution into a flat numbered list.
  2. RESOLVE: Send the flat list to the LLM — it only needs to match names
     to entity_ids and pick a service. No structural understanding required.
  3. MERGE: Programmatically merge the resolved entity_ids back into the
     original nested structure.
"""

from __future__ import annotations

import copy
import json
from typing import Any, Dict, List, Tuple

from jimmy_connection import sendMsg
from prompts.entity_selector import build_prompt


# ── JSON-Schema for the LLM response ────────────────────────────────────────

_RESOLVED_ITEM: Dict[str, Any] = {
    "type": "object",
    "required": ["id", "entity_id"],
    "properties": {
        "id": {"type": "integer"},
        "entity_id": {"type": "string"},
        "service": {"type": "string"},
    },
    "additionalProperties": False,
}

SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["items"],
    "additionalProperties": False,
    "properties": {
        "items": {
            "type": "array",
            "items": _RESOLVED_ITEM,
        },
    },
}


# ── Flatten / Merge helpers ──────────────────────────────────────────────────

def _flatten_actions(
    actions: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Tuple[str, int, str]]]:
    """Extract every resolvable item from a (possibly nested) action tree.

    Returns:
        items:  flat list of dicts like {"id": 0, "type": "device_control", "task": "..."}
        paths:  parallel list of (json_path, index, field) tuples so we know
                where to write the resolved values back.  We use a simple
                location string instead of actual JSONPath.
    """
    items: List[Dict[str, Any]] = []
    paths: List[Tuple[str, int, str]] = []  # not used directly; we use the id

    counter = 0

    def _walk(action_list: List[Dict[str, Any]]) -> None:
        nonlocal counter
        for action in action_list:
            action_type = action.get("type")

            if action_type == "device_control":
                action["_resolve_id"] = counter
                items.append({
                    "id": counter,
                    "type": "device_control",
                    "task": action.get("task", ""),
                })
                counter += 1

            elif action_type == "state":
                action["_resolve_id"] = counter
                items.append({
                    "id": counter,
                    "type": "state",
                    "task": action.get("task", ""),
                })
                counter += 1

            # For condition / monitor: resolve the check object too
            if action_type in ("condition", "monitor"):
                check = action.get("check")
                if check and check.get("type") == "state":
                    check["_resolve_id"] = counter
                    items.append({
                        "id": counter,
                        "type": "state",
                        "task": check.get("task", ""),
                    })
                    counter += 1

            # Recurse into nested branches
            for key in ("then", "else"):
                nested = action.get(key)
                if isinstance(nested, list):
                    _walk(nested)

    _walk(actions)
    return items, paths


def _merge_resolved(
    actions: List[Dict[str, Any]],
    resolved_map: Dict[int, Dict[str, Any]],
) -> None:
    """Walk the action tree and merge resolved entity_ids back in-place."""
    for action in actions:
        rid = action.pop("_resolve_id", None)
        if rid is not None and rid in resolved_map:
            r = resolved_map[rid]
            action["entity_id"] = r.get("entity_id", "unknown")
            if "service" in r and r["service"]:
                action["service"] = r["service"]

        # Merge into check objects
        check = action.get("check")
        if isinstance(check, dict):
            rid = check.pop("_resolve_id", None)
            if rid is not None and rid in resolved_map:
                r = resolved_map[rid]
                check["entity_id"] = r.get("entity_id", "unknown")

        # Recurse
        for key in ("then", "else"):
            nested = action.get(key)
            if isinstance(nested, list):
                _merge_resolved(nested, resolved_map)


# ── Public API ───────────────────────────────────────────────────────────────

class EntitySelector:
    """Step 2 of the agent pipeline."""

    def run(self, previous_output: Any, ha_context: Dict[str, Any]) -> Any:
        # Deep-copy so we don't mutate the original
        actions = copy.deepcopy(previous_output.get("actions", []))

        # 1. Flatten: collect all items needing resolution
        items, _ = _flatten_actions(actions)

        if not items:
            return {"actions": actions}

        # 2. Resolve: send flat list to LLM
        system_prompt = build_prompt(ha_context)
        user_message = json.dumps({"items": items}, ensure_ascii=False)
        llm_result = sendMsg(system_prompt, user_message, SCHEMA)

        # Build a map from id → resolved fields
        resolved_map: Dict[int, Dict[str, Any]] = {}
        for item in llm_result.get("items", []):
            resolved_map[item["id"]] = item

        # 3. Merge: write resolved entity_ids back into the nested structure
        _merge_resolved(actions, resolved_map)

        return {"actions": actions}
