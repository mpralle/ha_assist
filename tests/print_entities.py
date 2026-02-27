"""Print the entities fetched for the HA Assist pipeline (exposed to conversation)."""

import os
import sys
import asyncio
import socket
import requests
import aiohttp
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

_HA_URL = os.environ.get("HA_URL", "")
_HA_TOKEN = os.environ.get("HA_TOKEN", "")

if not _HA_URL or not _HA_TOKEN:
    print("ERROR: HA_URL and HA_TOKEN must be set in .env", file=sys.stderr)
    sys.exit(1)

_HEADERS = {
    "Authorization": f"Bearer {_HA_TOKEN}",
    "Content-Type": "application/json",
}


async def _fetch_ws_data() -> tuple[set[str] | None, dict[str, list[str]]]:
    """Fetch exposed entity IDs and aliases via WebSocket."""
    parsed = urlparse(_HA_URL)
    resolved_ip = socket.gethostbyname(parsed.hostname)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    ws_url = f"ws://{resolved_ip}:{port}/api/websocket"
    aliases: dict[str, list[str]] = {}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(ws_url) as ws:
                await ws.receive_json()
                await ws.send_json({"type": "auth", "access_token": _HA_TOKEN})
                if (await ws.receive_json()).get("type") != "auth_ok":
                    return None, aliases

                await ws.send_json({"id": 1, "type": "homeassistant/expose_entity/list"})
                result = await ws.receive_json()
                exposed = None
                if result.get("success"):
                    exposed = set()
                    for entity_id, config in result.get("result", {}).get("exposed_entities", {}).items():
                        if config.get("conversation") is True:
                            exposed.add(entity_id)
                    if not exposed:
                        exposed = None

                await ws.send_json({"id": 2, "type": "config/entity_registry/list"})
                reg_result = await ws.receive_json()
                if reg_result.get("success"):
                    for entry in reg_result.get("result", []):
                        eid = entry.get("entity_id", "")
                        entry_aliases = entry.get("aliases", [])
                        if eid and entry_aliases:
                            aliases[eid] = list(entry_aliases)

                return exposed, aliases
    except Exception as e:
        print(f"WARNING: WebSocket fetch failed: {e}")
        return None, aliases


def print_entities():
    exposed, aliases = asyncio.run(_fetch_ws_data())

    resp = requests.get(f"{_HA_URL.rstrip('/')}/api/states", headers=_HEADERS, timeout=30)
    resp.raise_for_status()

    entities = [
        {
            "entity_id": s["entity_id"],
            "domain": s["entity_id"].split(".")[0],
            "state": s.get("state", "?"),
            "friendly_name": s.get("attributes", {}).get("friendly_name", s["entity_id"]),
            "aliases": aliases.get(s["entity_id"], []),
        }
        for s in resp.json()
        if not exposed or s["entity_id"] in exposed
    ]

    print(f"Fetched {len(entities)} entities" +
          (f" (filtered to {len(exposed)} exposed)" if exposed else " (all — no exposure filter)"))
    print()

    by_domain = {}
    for e in entities:
        by_domain.setdefault(e["domain"], []).append(e)

    for domain in sorted(by_domain.keys()):
        print(f"[{domain}]")
        for e in sorted(by_domain[domain], key=lambda x: x["entity_id"]):
            alias_str = f"  (aliases: {', '.join(e['aliases'])})" if e["aliases"] else ""
            print(f"  {e['entity_id']:45s}  {e['state']:15s}  {e['friendly_name']}{alias_str}")
        print()


if __name__ == "__main__":
    print_entities()
