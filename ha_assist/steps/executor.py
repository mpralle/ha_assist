"""Step 3: Executor – call Home Assistant services for device_control actions."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List

import requests as http_requests

logger = logging.getLogger(__name__)

_HA_URL = os.environ.get("HA_URL", "http://supervisor/core/api")
_SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN")
_HA_TOKEN = os.environ.get("HA_TOKEN", _SUPERVISOR_TOKEN or "")


def _call_service(domain: str, service: str, entity_id: str) -> Dict[str, Any]:
    """Call a Home Assistant service via the REST API.

    Returns a dict with:
        "success": bool
        "entity_id": the entity acted on
        "service": the full service string (domain.service)
        "error": error message (only when success is False)
    """
    full_service = f"{domain}.{service}"
    url = f"{_HA_URL.rstrip('/')}/services/{domain}/{service}"
    headers = {
        "Authorization": f"Bearer {_HA_TOKEN}",
        "Content-Type": "application/json",
    }
    payload: Dict[str, Any] = {"entity_id": entity_id}

    try:
        resp = http_requests.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
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


class Executor:
    """Step 3 of the agent pipeline.

    For each action with type ``device_control``, calls the corresponding
    Home Assistant service via the REST API.  Other action types are passed
    through unchanged.
    """

    def run(self, previous_output: Any, ha_context: Dict[str, Any]) -> Any:
        actions: List[Dict[str, Any]] = previous_output.get("actions", [])
        results: List[Dict[str, Any]] = []

        for action in actions:
            action_type = action.get("type")

            if action_type == "device_control":
                service_full = action.get("service", "")
                entity_id = action.get("entity_id", "")

                if "." not in service_full or not entity_id:
                    results.append({
                        **action,
                        "result": {
                            "success": False,
                            "entity_id": entity_id,
                            "service": service_full,
                            "error": "Missing or invalid service/entity_id",
                        },
                    })
                    continue

                domain, service_name = service_full.split(".", 1)
                result = _call_service(domain, service_name, entity_id)
                results.append({**action, "result": result})
            else:
                # Pass non-device_control actions through unchanged
                results.append(action)

        return {"actions": results}
