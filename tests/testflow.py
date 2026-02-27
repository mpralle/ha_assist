"""Quick test for Steps 1–4: TaskExtractor → EntitySelector → Executor → Summary.

Usage (with venv activated, .env configured):
    python tests/testflow.py
"""

import json
import os
import sys
import time
import asyncio
import requests

from dotenv import load_dotenv

import sys
import os

# ── Mock Home Assistant Components before importing them ────────────────────
# We must mock the entire homeassistant tree, otherwise imports in conversation.py
# or pipeline.py will fail trying to load actual HA code (which requires hassil,
# voluptuous, etc. that aren't present in this basic venv).
from unittest.mock import MagicMock
import sys



class AttrDict(dict):
    def __init__(self, *args, **kwargs):
        super(AttrDict, self).__init__(*args, **kwargs)
        self.__dict__ = self

mock_ha = MagicMock()
mock_ha.core.HomeAssistant = MagicMock
mock_ha.config_entries.ConfigEntry = MagicMock
sys.modules['homeassistant'] = mock_ha
sys.modules['homeassistant.core'] = mock_ha.core
sys.modules['homeassistant.config_entries'] = mock_ha.config_entries
sys.modules['homeassistant.components'] = mock_ha.components
sys.modules['homeassistant.components.conversation'] = mock_ha.components.conversation
sys.modules['homeassistant.helpers'] = mock_ha.helpers
sys.modules['homeassistant.helpers.intent'] = mock_ha.helpers.intent
sys.modules['homeassistant.helpers.entity_registry'] = mock_ha.helpers.entity_registry
sys.modules['homeassistant.components.homeassistant'] = MagicMock()
sys.modules['voluptuous'] = MagicMock()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from custom_components.ha_assist.pipeline import async_run_pipeline
from custom_components.ha_assist.steps import TaskExtractor, EntitySelector, Summary
from custom_components.ha_assist.monitor_store import MonitorStore

# The new Executor natively uses `hass.services.async_call`.
# For testing locally without the HA Core runtime, we substitute
# local REST execution logic in order to use real configuration and run against
# the real home assistant instance defined in `.env`.
from custom_components.ha_assist.steps import executor


# Load real environment config
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

_HA_URL = os.environ.get("HA_URL", "")
_HA_TOKEN = os.environ.get("HA_TOKEN", "")

if not _HA_URL or not _HA_TOKEN:
    print("ERROR: HA_URL and HA_TOKEN must be set in .env for real testing.", file=sys.stderr)
    sys.exit(1)

_HEADERS = {
    "Authorization": f"Bearer {_HA_TOKEN}",
    "Content-Type": "application/json",
}

SLEEP_TIME = 0.1

# ── Choose test mode ────────────────────────────────────────────────────────
# Set to True to test monitor functionality, False for standard commands
TEST_MONITOR = False
TEST_LANGUAGE="de"
USER_INPUT_STANDARD = "Schalte die Schreibtischlampe aus"
USER_INPUT_MONITOR = "Warte bis es nach 13:16 ist und öffne die Vorhänge."
USER_INPUT = USER_INPUT_MONITOR if TEST_MONITOR else USER_INPUT_STANDARD

# ── Monitor polling settings ────────────────────────────────────────────────
MONITOR_POLL_SECONDS = 10      # how often to check entity state
MONITOR_MAX_WAIT = 300         # max seconds to wait for monitors to resolve

start_time = time.time()
sleep_time = 0

# ── Local REST Mocks & Context ──────────────────────────────────────────────

def _fetch_services_rest():
    """Fetch services and their field schemas from HA REST API."""
    url = f"{_HA_URL.rstrip('/')}/api/services"
    resp = requests.get(url, headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    services = {}
    service_fields = {}
    for domain_info in resp.json():
        domain = domain_info.get("domain", "")
        svc_map = domain_info.get("services", {})
        if domain and svc_map:
            services[domain] = list(svc_map.keys())
            for svc_name, svc_info in svc_map.items():
                full_name = f"{domain}.{svc_name}"
                fields = svc_info.get("fields", {})
                if fields:
                    fields_info = {}
                    for fname, fval in fields.items():
                        if isinstance(fval, dict):
                            fields_info[fname] = {
                                "description": fval.get("description", ""),
                                "required": fval.get("required", False),
                                "example": fval.get("example"),
                            }
                    if fields_info:
                        service_fields[full_name] = {
                            "description": svc_info.get("description", ""),
                            "fields": fields_info,
                        }
    return services, service_fields


import asyncio
import json
import aiohttp
import socket
from urllib.parse import urlparse

async def _fetch_ws_data() -> tuple[set[str] | None, dict[str, list[str]]]:
    """Fetch exposed entity IDs and entity aliases via WebSocket.
    Returns (exposed_set_or_None, aliases_dict).
    """
    parsed = urlparse(_HA_URL)
    resolved_ip = socket.gethostbyname(parsed.hostname)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    ws_url = f"ws://{resolved_ip}:{port}/api/websocket"
    aliases: dict[str, list[str]] = {}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(ws_url) as ws:
                await ws.receive_json()  # auth_required
                await ws.send_json({"type": "auth", "access_token": _HA_TOKEN})
                if (await ws.receive_json()).get("type") != "auth_ok":
                    print("WARNING: WebSocket auth failed.")
                    return None, aliases

                # 1. Fetch exposed entities
                await ws.send_json({
                    "id": 1,
                    "type": "homeassistant/expose_entity/list"
                })
                result = await ws.receive_json()

                exposed = None
                if result.get("success"):
                    exposed = set()
                    for entity_id, config in result.get("result", {}).get("exposed_entities", {}).items():
                        if config.get("conversation") is True:
                            exposed.add(entity_id)
                    print(f"Found {len(exposed)} entities exposed to conversation assistant")
                    if not exposed:
                        exposed = None
                else:
                    print(f"WARNING: expose_entity/list failed: {result}")

                # 2. Fetch entity registry (for aliases)
                await ws.send_json({
                    "id": 2,
                    "type": "config/entity_registry/list"
                })
                reg_result = await ws.receive_json()

                if reg_result.get("success"):
                    for entry in reg_result.get("result", []):
                        eid = entry.get("entity_id", "")
                        entry_aliases = entry.get("aliases", [])
                        if eid and entry_aliases:
                            aliases[eid] = list(entry_aliases)
                    print(f"Fetched aliases for {len(aliases)} entities")
                else:
                    print(f"WARNING: entity_registry/list failed: {reg_result}")

                return exposed, aliases

    except Exception as e:
        print(f"WARNING: WebSocket fetch failed: {e}")
        return None, aliases


def get_real_ha_context() -> dict:
    exposed, aliases = asyncio.run(_fetch_ws_data())

    url = f"{_HA_URL.rstrip('/')}/api/states"
    resp = requests.get(url, headers=_HEADERS, timeout=30)
    resp.raise_for_status()

    all_states = resp.json()

    # If nothing explicitly exposed, fall back to all entities
    entity_details = []
    for s in all_states:
        eid = s["entity_id"]
        if exposed and eid not in exposed:
            continue
        detail = {
            "entity_id": eid,
            "domain": eid.split(".")[0],
            "state": s["state"],
            "friendly_name": s.get("attributes", {}).get("friendly_name", eid),
        }
        entity_aliases = aliases.get(eid, [])
        if entity_aliases:
            detail["aliases"] = entity_aliases
        entity_details.append(detail)

    exposed_domains = {e["domain"] for e in entity_details}
    all_services, all_service_fields = _fetch_services_rest()
    services = {k: v for k, v in all_services.items() if k in exposed_domains}
    service_fields = {k: v for k, v in all_service_fields.items()
                      if k.split(".", 1)[0] in exposed_domains}

    return {
        "hass": "DUMMY_HASS",
        "language": TEST_LANGUAGE,
        "entities": [e["entity_id"] for e in entity_details],
        "entity_details": entity_details,
        "services": services,
        "service_fields": service_fields,
    }


async def local_async_executor_call_service(domain, service, entity_id, hass, service_data=None):
    """Override Executor's native Service Call with REST for testing."""
    full_service = f"{domain}.{service}"
    url = f"{_HA_URL.rstrip('/')}/api/services/{domain}/{service}"
    payload = {"entity_id": entity_id}
    if service_data:
        payload.update(service_data)

    try:
        import asyncio
        loop = asyncio.get_event_loop()
        def _do_post():
            resp = requests.post(url, headers=_HEADERS, json=payload, timeout=30)
            resp.raise_for_status()
            return resp
            
        resp = await loop.run_in_executor(None, _do_post)
        print(f"--> REST: Service {full_service} called on {entity_id} – OK (data: {service_data})")
        return {"success": True, "entity_id": entity_id, "service": full_service}
    except Exception as exc:
        print(f"--> REST: Service {full_service} on {entity_id} failed: {exc}")
        return {
            "success": False,
            "entity_id": entity_id,
            "service": full_service,
            "error": str(exc),
        }

def local_executor_fetch_entity_state(entity_id, hass):
    """Override Executor's native State Fetch with REST for testing."""
    url = f"{_HA_URL.rstrip('/')}/api/states/{entity_id}"
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        print(f"Failed to fetch state for {entity_id}: {exc}")
        return {"entity_id": entity_id, "state": "unavailable", "attributes": {}}

# Inject overrides dynamically
executor._async_call_service = local_async_executor_call_service
executor._fetch_entity_state = local_executor_fetch_entity_state


# ── Testing Pipeline Execution ───────────────────────────────────────────────

print("=" * 60)
print("Fetching real Home Assistant context...")
print("=" * 60)

t0 = time.time()
try:
    # Our mocked context is synchronous REST, we'll keep it synchronous here
    ha_context = get_real_ha_context()
except Exception as e:
    print(f"Failed to connect to Home Assistant at {_HA_URL}: {e}")
    sys.exit(1)

time_ha_context = time.time() - t0
entities = ha_context["entity_details"]
services = ha_context["services"]
print(f"\nTotal entities: {len(entities)}")
print(f"Service domains: {len(services)}")
print()

# ── Set up local MonitorStore for testing ────────────────────────────────────
_STORE_FILE = os.path.join(os.path.dirname(__file__), "test_monitors.json")

monitor_store = MonitorStore(
    store_path=_STORE_FILE,
    fetch_state_fn=local_executor_fetch_entity_state,
    execute_actions_fn=executor._async_execute_actions,
    hass="DUMMY_HASS",
)

# Make monitor store available to executor via ha_context
ha_context["monitor_store"] = monitor_store

async def main():
    global sleep_time
    
    # ── 2. Run Step 1: TaskExtractor ─────────────────────────────────────────────
    
    print("=" * 60)
    print(f"Step 1 — User input: {USER_INPUT}")
    print("=" * 60)
    
    t0 = time.time()
    step1_result = await TaskExtractor().async_run(USER_INPUT, ha_context)
    time_step1 = time.time() - t0
    print("\nTaskExtractor result:")
    print(json.dumps(step1_result, indent=2, ensure_ascii=False))
    await asyncio.sleep(SLEEP_TIME)
    sleep_time += SLEEP_TIME
    
    # ── 3. Run Step 2: EntitySelector ────────────────────────────────────────────
    
    print("\n" + "=" * 60)
    print("Step 2 — EntitySelector")
    print("=" * 60)
    
    t0 = time.time()
    step2_result = await EntitySelector().async_run(step1_result, ha_context)
    time_step2 = time.time() - t0
    print("\nEntitySelector result:")
    print(json.dumps(step2_result, indent=2, ensure_ascii=False))
    
    # ── 4. Run Step 3: Executor ──────────────────────────────────────────────────
    
    print("\n" + "=" * 60)
    print("Step 3 — Executor")
    print("=" * 60)
    
    t0 = time.time()
    step3_result = await executor.Executor().async_run(step2_result, ha_context)
    time_step3 = time.time() - t0
    print("\nExecutor result:")
    print(json.dumps(step3_result, indent=2, ensure_ascii=False))
    await asyncio.sleep(SLEEP_TIME)
    sleep_time += SLEEP_TIME
    
    # ── 5. Run Step 4: Summary ───────────────────────────────────────────────────
    
    print("\n" + "=" * 60)
    print("Step 4 — Summary (include_errors=True)")
    print("=" * 60)
    
    t0 = time.time()
    step4_result = await Summary(include_errors=True).async_run(step3_result, ha_context)
    time_step4 = time.time() - t0
    print("\nSummary result:")
    print(json.dumps(step4_result, indent=2, ensure_ascii=False))
    
    # ── Timing ────────────────────────────────────────────────────────────────────
    
    end_time = time.time()
    total_time = end_time - start_time
    effective_time = total_time - sleep_time
    
    print("\n" + "=" * 60)
    print("Execution Time Overview:")
    print("-" * 60)
    print(f"HA Context Fetch:         {time_ha_context:.2f}s")
    print(f"Step 1 (TaskExtractor):   {time_step1:.2f}s")
    print(f"Step 2 (EntitySelector):  {time_step2:.2f}s")
    print(f"Step 3 (Executor):        {time_step3:.2f}s")
    print(f"Step 4 (Summary):         {time_step4:.2f}s")
    print("-" * 60)
    print(f"Total execution time:     {total_time:.2f}s")
    print(f"Sleep time:               {sleep_time:.2f}s")
    print(f"Effective execution time: {effective_time:.2f}s")
    print("=" * 60)

    # ── 6. Monitor idle loop — wait for all monitors to resolve ──────────────────
    
    if TEST_MONITOR and not monitor_store.is_empty():
        print("\n" + "=" * 60)
        print(f"Monitor idle loop — polling every {MONITOR_POLL_SECONDS}s")
        print(f"Active monitors: {len(monitor_store.get_all())}")
        print(f"Max wait: {MONITOR_MAX_WAIT}s")
        print("=" * 60)
        
        # Start the monitor store's background polling loop
        monitor_store.start()
        
        wait_start = time.time()
        while not monitor_store.is_empty():
            elapsed = time.time() - wait_start
            if elapsed > MONITOR_MAX_WAIT:
                print(f"\n⏰ Max wait time ({MONITOR_MAX_WAIT}s) reached. "
                      f"Remaining monitors: {len(monitor_store.get_all())}")
                break
            
            remaining = monitor_store.get_all()
            for m in remaining:
                entity_id = m.get("check", {}).get("entity_id", "?")
                cond = m.get("condition", {})
                attr = cond.get('attribute', 'state')
                current_state = local_executor_fetch_entity_state(entity_id, None)
                if attr == "state":
                    current_val = current_state.get("state", "?")
                else:
                    current_val = current_state.get("attributes", {}).get(attr, "?")
                print(f"  ⏳ [{elapsed:.0f}s] Waiting: {entity_id}: "
                      f"{current_val} {cond.get('operator','==')} "
                      f"{cond.get('value','?')}")
            
            await asyncio.sleep(MONITOR_POLL_SECONDS)
        
        monitor_store.stop()
        
        if monitor_store.is_empty():
            print("\n✅ All monitors resolved!")
        
        print(f"Monitor wait time: {time.time() - wait_start:.1f}s")
    
    elif TEST_MONITOR:
        print("\nℹ️  No monitors were registered (task may not have produced a monitor action).")

    # Clean up test store file
    if os.path.exists(_STORE_FILE):
        os.remove(_STORE_FILE)

if __name__ == "__main__":
    asyncio.run(main())

