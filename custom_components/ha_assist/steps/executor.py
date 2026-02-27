"""Step 3: Executor – execute actions against Home Assistant.

Handles:
  - device_control  → call an HA service
  - condition       → fetch entity state, evaluate, run then/else branch
  - monitor         → register in MonitorStore for background polling
  - other types     → pass through unchanged
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List
import asyncio

from homeassistant.core import HomeAssistant

logger = logging.getLogger(__name__)

# ── Helpers ──────────────────────────────────────────────────────────────────

async def _async_call_service(domain: str, service: str, entity_id: str, hass: HomeAssistant, service_data: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Call a Home Assistant service incrementally using asyncio."""
    full_service = f"{domain}.{service}"
    payload: Dict[str, Any] = {"entity_id": entity_id}
    if service_data:
        payload.update(service_data)

    try:
        await hass.services.async_call(domain, service, payload, blocking=True)
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


from ..condition import evaluate_condition as _evaluate_condition


# ── Recursive action executor ────────────────────────────────────────────────

def _execute_actions(actions: List[Dict[str, Any]], hass: HomeAssistant) -> List[Dict[str, Any]]:
    pass # Replaced temporarily
    
async def _async_execute_actions(actions: List[Dict[str, Any]], hass: HomeAssistant, ha_context: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    """Recursively execute a list of actions and return results."""
    results: List[Dict[str, Any]] = []

    for action in actions:
        action_type = action.get("type")

        if action_type in ("device_control", "list"):
            results.append(await _async_execute_device_control(action, hass))

        elif action_type == "condition":
            results.append(await _async_execute_condition(action, hass))

        elif action_type == "monitor":
            results.append(_execute_monitor(action, hass, ha_context))

        else:
            # Pass through unknown types unchanged
            results.append(action)

    return results


async def _async_execute_device_control(action: Dict[str, Any], hass: HomeAssistant) -> Dict[str, Any]:
    """Execute a device_control action."""
    service_full = action.get("service", "")
    entity_id = action.get("entity_id", "")

    if not entity_id:
        return {
            **action,
            "result": {
                "success": False,
                "entity_id": entity_id,
                "service": service_full,
                "error": "Missing entity_id",
            },
        }

    # If service is missing the domain prefix, infer it from entity_id
    if service_full and "." not in service_full and "." in entity_id:
        domain = entity_id.split(".", 1)[0]
        service_full = f"{domain}.{service_full}"
        logger.info("Inferred service domain: %s", service_full)

    if "." not in service_full:
        return {
            **action,
            "result": {
                "success": False,
                "entity_id": entity_id,
                "service": service_full,
                "error": "Missing or invalid service",
            },
        }

    domain, service_name = service_full.split(".", 1)
    service_data = action.get("service_data")
    result = await _async_call_service(domain, service_name, entity_id, hass, service_data)
    return {**action, "result": result}


async def _async_execute_condition(action: Dict[str, Any], hass: HomeAssistant) -> Dict[str, Any]:
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
    branch_results = await _async_execute_actions(branch, hass)

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


def _execute_monitor(action: Dict[str, Any], hass: HomeAssistant, ha_context: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Register a monitor task in the MonitorStore."""
    store = None
    if ha_context:
        store = ha_context.get("monitor_store")

    if store is None:
        logger.warning("No MonitorStore available – cannot register monitor")
        return {
            **action,
            "result": {
                "monitor_created": False,
                "error": "MonitorStore not available",
            },
        }

    monitor_id = store.add_monitor(action)
    entity_id = action.get("check", {}).get("entity_id", "unknown")
    condition = action.get("condition", {})
    poll_seconds = action.get("poll_seconds", 60)

    desc = (
        f"Monitoring {entity_id}: {condition.get('attribute', 'state')} "
        f"{condition.get('operator', '==')} {condition.get('value')} "
        f"(every {poll_seconds}s)"
    )

    logger.info("Monitor registered: %s – %s", monitor_id, desc)
    return {
        **action,
        "result": {
            "monitor_created": True,
            "monitor_id": monitor_id,
            "description": desc,
        },
    }


# ── Public API ───────────────────────────────────────────────────────────────

class Executor:
    """Step 3 of the agent pipeline.

    Evaluates conditions and calls HA services.
    """

    async def async_run(self, previous_output: Any, ha_context: Dict[str, Any]) -> Any:
        actions: List[Dict[str, Any]] = previous_output.get("actions", [])
        hass = ha_context.get("hass")
        if not hass:
            raise RuntimeError("HA context missing 'hass' object.")
        results = await _async_execute_actions(actions, hass, ha_context)
        return {"actions": results}
