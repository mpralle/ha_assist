"""Step 3: Executor – execute actions against Home Assistant.

Handles:
  - device_control  → call an HA service
  - condition       → fetch entity state, evaluate, run then/else branch
  - monitor         → (placeholder) not yet implemented
  - other types     → pass through unchanged
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List
import asyncio

from homeassistant.core import HomeAssistant

logger = logging.getLogger(__name__)

# ── Helpers ──────────────────────────────────────────────────────────────────

def _call_service(domain: str, service: str, entity_id: str, hass: HomeAssistant) -> Dict[str, Any]:
    """Call a Home Assistant service."""
    full_service = f"{domain}.{service}"
    payload: Dict[str, Any] = {"entity_id": entity_id}

    try:
        # Run threadsafe from our background thread context:
        future = asyncio.run_coroutine_threadsafe(
            hass.services.async_call(domain, service, payload, blocking=True),
            hass.loop
        )
        future.result(timeout=30)
        logger.info("Service %s called on %s – OK", full_service, entity_id)
        return {"success": True, "entity_id": entity_id, "service": full_service}
    except Exception as exc:
        logger.error("Service %s on %s failed: %s", full_service, entity_id, exc)
        return {
            "success": False,
            "entity_id": entity_id,
            "service": full_service,
            "error": str(exc),
        }


def _fetch_entity_state(entity_id: str, hass: HomeAssistant) -> Dict[str, Any]:
    """Fetch the current state of an entity."""
    try:
        state_obj = hass.states.get(entity_id)
        if not state_obj:
            return {"entity_id": entity_id, "state": "unavailable", "attributes": {}}
        return {
            "entity_id": entity_id,
            "state": state_obj.state,
            "attributes": dict(state_obj.attributes)
        }
    except Exception as exc:
        logger.error("Failed to fetch state for %s: %s", entity_id, exc)
        return {"entity_id": entity_id, "state": "unavailable", "attributes": {}}


def _evaluate_condition(condition: Dict[str, Any], state_data: Dict[str, Any]) -> bool:
    """Evaluate a structured condition against entity state data.

    condition format:
        {"attribute": "state", "operator": "==", "value": "off"}

    For attribute "state", compares against the top-level state string.
    For other attributes, looks inside state_data["attributes"].
    """
    attribute = condition.get("attribute", "state")
    operator = condition.get("operator", "==")
    expected = condition.get("value")

    # Get the actual value from state data
    if attribute == "state":
        actual = state_data.get("state")
    else:
        actual = state_data.get("attributes", {}).get(attribute)

    if actual is None:
        logger.warning("Attribute %r not found in state data for %s",
                        attribute, state_data.get("entity_id", "?"))
        return False

    # Try numeric comparison if possible
    try:
        actual_num = float(actual)
        expected_num = float(expected)
        comparisons = {
            "==": actual_num == expected_num,
            "!=": actual_num != expected_num,
            ">":  actual_num > expected_num,
            "<":  actual_num < expected_num,
            ">=": actual_num >= expected_num,
            "<=": actual_num <= expected_num,
        }
        if operator in comparisons:
            return comparisons[operator]
    except (TypeError, ValueError):
        pass

    # Fall back to string comparison
    actual_str = str(actual).lower().strip()
    expected_str = str(expected).lower().strip()

    if operator == "==":
        return actual_str == expected_str
    elif operator == "!=":
        return actual_str != expected_str
    else:
        logger.warning("Cannot compare %r %s %r as strings", actual, operator, expected)
        return False


# ── Recursive action executor ────────────────────────────────────────────────

def _execute_actions(actions: List[Dict[str, Any]], hass: HomeAssistant) -> List[Dict[str, Any]]:
    """Recursively execute a list of actions and return results."""
    results: List[Dict[str, Any]] = []

    for action in actions:
        action_type = action.get("type")

        if action_type == "device_control":
            results.append(_execute_device_control(action, hass))

        elif action_type == "condition":
            results.append(_execute_condition(action, hass))

        else:
            # Pass through unknown types unchanged
            results.append(action)

    return results


def _execute_device_control(action: Dict[str, Any], hass: HomeAssistant) -> Dict[str, Any]:
    """Execute a device_control action."""
    service_full = action.get("service", "")
    entity_id = action.get("entity_id", "")

    if "." not in service_full or not entity_id:
        return {
            **action,
            "result": {
                "success": False,
                "entity_id": entity_id,
                "service": service_full,
                "error": "Missing or invalid service/entity_id",
            },
        }

    domain, service_name = service_full.split(".", 1)
    result = _call_service(domain, service_name, entity_id, hass)
    return {**action, "result": result}


def _execute_condition(action: Dict[str, Any], hass: HomeAssistant) -> Dict[str, Any]:
    """Evaluate a condition and execute the appropriate branch."""
    check = action.get("check", {})
    condition = action.get("condition", {})
    then_branch = action.get("then", [])
    else_branch = action.get("else", [])

    entity_id = check.get("entity_id", "")
    if not entity_id:
        return {
            **action,
            "result": {
                "evaluated": False,
                "error": "No entity_id in check object",
            },
        }

    # Fetch current state
    state_data = _fetch_entity_state(entity_id, hass)
    actual_state = state_data.get("state", "unavailable")

    # Evaluate
    condition_met = _evaluate_condition(condition, state_data)
    logger.info(
        "Condition on %s: %s %s %s → %s (actual: %s)",
        entity_id,
        condition.get("attribute", "state"),
        condition.get("operator", "=="),
        condition.get("value"),
        condition_met,
        actual_state,
    )

    # Execute the appropriate branch
    branch_name = "then" if condition_met else "else"
    branch = then_branch if condition_met else else_branch
    branch_results = _execute_actions(branch, hass)

    return {
        **action,
        "result": {
            "evaluated": True,
            "entity_id": entity_id,
            "actual_state": actual_state,
            "condition_met": condition_met,
            "branch_executed": branch_name,
            "branch_results": branch_results,
        },
    }


# ── Public API ───────────────────────────────────────────────────────────────

class Executor:
    """Step 3 of the agent pipeline.

    Evaluates conditions and calls HA services.
    """

    def run(self, previous_output: Any, ha_context: Dict[str, Any]) -> Any:
        actions: List[Dict[str, Any]] = previous_output.get("actions", [])
        hass = ha_context.get("hass")
        if not hass:
            raise RuntimeError("HA context missing 'hass' object.")
        results = _execute_actions(actions, hass)
        return {"actions": results}
