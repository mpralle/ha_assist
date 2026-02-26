"""HA Assist – main entry point and pipeline orchestrator."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from homeassistant.core import HomeAssistant

from .steps import TaskExtractor, EntitySelector, Executor, Summary

logger = logging.getLogger(__name__)

def get_ha_context(hass: HomeAssistant) -> Dict[str, Any]:
    """Fetch current Home Assistant state / context.

    Returns a dict with:
        "entities": list of entity_id strings
        "entity_details": list of dicts with entity_id, state, friendly_name, domain
        "services": dict mapping domain -> list of available service names
    """
    entity_ids: List[str] = []
    entity_details: List[Dict[str, Any]] = []
    services: Dict[str, List[str]] = {}

    # ── Fetch entities ────────────────────────────────────────────────────
    try:
        # async_all() can be called from sync thread safely as it just returns the state dictates.
        # However, to be completely thread-safe we can use hass.states.async_all() in async loop
        # or hass.states.all() in sync context. We are in a sync thread or async...
        # Wait, get_ha_context is called from async loop! So we use `hass.states.async_all()`
        for state in hass.states.async_all():
            entity_id = state.entity_id
            entity_ids.append(entity_id)
            entity_details.append({
                "entity_id": entity_id,
                "domain": state.domain,
                "state": state.state,
                "friendly_name": state.attributes.get("friendly_name", entity_id),
            })
    except Exception as exc:
        logger.error("Failed to fetch HA entities: %s", exc)

    # ── Fetch services ────────────────────────────────────────────────────
    try:
        # hass.services.async_services() returns Dict[str, Dict[str, Service]]
        # We process it safely.
        srvs = hass.services.async_services()
        for domain, srv_map in srvs.items():
            services[domain] = list(srv_map.keys())
    except Exception as exc:
        logger.error("Failed to fetch HA services: %s", exc)

    logger.debug("Fetched %d entities, %d service domains", len(entity_ids), len(services))
    return {
        "entities": entity_ids,
        "entity_details": entity_details,
        "services": services,
    }


async def async_run_pipeline(user_input: str, ha_context: Dict[str, Any], hass: HomeAssistant) -> Any:
    """Run the four-step agent pipeline."""
    # We pass hass down into the context for Executor to use
    ha_context["hass"] = hass

    result = await TaskExtractor().async_run(user_input, ha_context)
    result = await EntitySelector().async_run(result, ha_context)
    result = await Executor().async_run(result, ha_context)
    result = await Summary().async_run(result, ha_context)
    return result
