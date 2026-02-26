"""HA Assist – main entry point and pipeline orchestrator."""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any, Dict, List

import requests as http_requests
from dotenv import load_dotenv
load_dotenv()

from homeassistant_api import Client
from steps import TaskExtractor, EntitySelector, Executor, Summary

logger = logging.getLogger(__name__)

# ── HA connection settings ───────────────────────────────────────────────────
_SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN")

if _SUPERVISOR_TOKEN:
    # Prefer internal supervisor token access if running as an Add-on
    _HA_URL = "http://supervisor/core/api"
    _HA_TOKEN = _SUPERVISOR_TOKEN
else:
    # Fallback for local testing
    _HA_URL = os.environ.get("HA_URL", "")
    _HA_TOKEN = os.environ.get("HA_TOKEN", "")


def _get_client() -> Client:
    """Return an authenticated homeassistant_api Client."""
    return Client(_HA_URL, _HA_TOKEN)


def _fetch_services_rest() -> Dict[str, List[str]]:
    """Fetch available services via the HA REST API.

    Uses the REST API directly instead of the homeassistant_api library to
    avoid Pydantic validation errors for unknown selector types (e.g. 'app').
    """
    url = f"{_HA_URL.rstrip('/')}/services"
    headers = {
        "Authorization": f"Bearer {_HA_TOKEN}",
        "Content-Type": "application/json",
    }
    resp = http_requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    services: Dict[str, List[str]] = {}
    for domain_info in resp.json():
        domain = domain_info.get("domain", "")
        svc_map = domain_info.get("services", {})
        if domain and svc_map:
            services[domain] = list(svc_map.keys())
    return services


def get_ha_context() -> Dict[str, Any]:
    """Fetch current Home Assistant state / context.

    Returns a dict with:
        "entities": list of entity_id strings
        "entity_details": list of dicts with entity_id, state, friendly_name, domain
        "services": dict mapping domain -> list of available service names

    Entity and service fetching are independent; a failure in one does not
    prevent the other from succeeding.
    """
    entity_ids: List[str] = []
    entity_details: List[Dict[str, Any]] = []
    services: Dict[str, List[str]] = {}

    # ── Fetch entities ────────────────────────────────────────────────────
    try:
        client = _get_client()
        entity_groups = client.get_entities()

        for group in entity_groups.values():
            for entity_id, entity in group.entities.items():
                entity_ids.append(entity_id)
                state = entity.state
                entity_details.append({
                    "entity_id": entity_id,
                    "domain": entity_id.split(".")[0],
                    "state": state.state if state else "unknown",
                    "friendly_name": (
                        state.attributes.get("friendly_name", entity_id)
                        if state and state.attributes else entity_id
                    ),
                })
    except Exception as exc:
        logger.error("Failed to fetch HA entities: %s", exc)

    # ── Fetch services (via REST API to avoid strict model validation) ────
    try:
        services = _fetch_services_rest()
    except Exception as exc:
        logger.error("Failed to fetch HA services: %s", exc)

    logger.info("Fetched %d entities, %d service domains", len(entity_ids), len(services))
    return {
        "entities": entity_ids,
        "entity_details": entity_details,
        "services": services,
    }


def run_pipeline(user_input: str, ha_context: Dict[str, Any]) -> Any:
    """Run the four-step agent pipeline."""
    result = TaskExtractor().run(user_input, ha_context)
    result = EntitySelector().run(result, ha_context)
    result = Executor().run(result, ha_context)
    result = Summary().run(result, ha_context)
    return result


import argparse
import asyncio
from wyoming.event import Event
from wyoming.info import Describe, Info, HandleProgram
from wyoming.asr import Transcript
from wyoming.intent import Recognize
from wyoming.handle import Handled
from wyoming.server import AsyncEventHandler, AsyncTcpServer


class AssistEventHandler(AsyncEventHandler):
    """Event handler for the HA Assist Wyoming protocol."""

    async def handle_event(self, event: Event) -> bool:
        if Describe.is_type(event.type):
            await self.write_event(
                Info(
                    handle=[HandleProgram(name="ha_assist", description="HA Assist AI Logic")]
                ).event()
            )
            return True

        if Transcript.is_type(event.type) or Recognize.is_type(event.type):
            if Transcript.is_type(event.type):
                message = Transcript.from_event(event).text.strip()
            else:
                message = Recognize.from_event(event).text.strip()

            if message:
                logger.info("Received text: %s", message)
                # Run the pipeline in a separate thread so we don't block the async loop
                loop = asyncio.get_running_loop()
                ha_context = await loop.run_in_executor(None, get_ha_context)
                result = await loop.run_in_executor(None, run_pipeline, message, ha_context)
                
                # Extract the message returned by the summary step
                response_text = result.get("message", "I'm sorry, an error occurred in the pipeline.")
                
                await self.write_event(Handled(text=response_text).event())
            return True

        return True


async def _run_server(host: str, port: int) -> None:
    """Start the Wyoming server."""
    logger.info("Starting Wyoming server on %s:%s", host, port)
    server = AsyncTcpServer(host, port)
    await server.run(AssistEventHandler)


def main() -> None:
    """Main entry point for starting the Wyoming server or CLI fallback."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0", help="Host to listen on")
    parser.add_argument("--port", type=int, default=10400, help="Port to listen on")
    parser.add_argument("--cli", action="store_true", help="Run in CLI mode (stdin/stdout)")
    args = parser.parse_args()

    if args.cli:
        for line in sys.stdin:
            message = line.strip()
            if not message:
                continue
            ha_context = get_ha_context()
            result = run_pipeline(message, ha_context)
            print(json.dumps(result, ensure_ascii=False), flush=True)
    else:
        try:
            asyncio.run(_run_server(args.host, args.port))
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
