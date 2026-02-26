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
sys.modules['voluptuous'] = MagicMock()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from custom_components.ha_assist.pipeline import async_run_pipeline
from custom_components.ha_assist.steps import TaskExtractor, EntitySelector, Summary

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

SLEEP_TIME = 2
USER_INPUT = "open the curtains."

start_time = time.time()
sleep_time = 0

# ── Local REST Mocks & Context ──────────────────────────────────────────────

def _fetch_services_rest():
    url = f"{_HA_URL.rstrip('/')}/api/services"
    resp = requests.get(url, headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    services = {}
    for domain_info in resp.json():
        domain = domain_info.get("domain", "")
        svc_map = domain_info.get("services", {})
        if domain and svc_map:
            services[domain] = list(svc_map.keys())
    return services


def get_real_ha_context():
    """Fetch current Home Assistant state via REST for local testing."""
    entity_ids = []
    entity_details = []
    
    url = f"{_HA_URL.rstrip('/')}/api/states"
    resp = requests.get(url, headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    
    for state_obj in resp.json():
        entity_id = state_obj["entity_id"]
        entity_ids.append(entity_id)
        entity_details.append({
            "entity_id": entity_id,
            "domain": entity_id.split(".")[0],
            "state": state_obj["state"],
            "friendly_name": state_obj.get("attributes", {}).get("friendly_name", entity_id),
        })

    services = _fetch_services_rest()

    return {
        "hass": "DUMMY_HASS", # For executor signature compat
        "entities": entity_ids,
        "entity_details": entity_details,
        "services": services,
    }


async def local_async_executor_call_service(domain, service, entity_id, hass):
    """Override Executor's native Service Call with REST for testing."""
    full_service = f"{domain}.{service}"
    url = f"{_HA_URL.rstrip('/')}/api/services/{domain}/{service}"
    payload = {"entity_id": entity_id}

    try:
        # Since this is a test script, we can keep requests here, or use aiohttp. 
        # Using requests is fine since it runs in the main thread of the test.
        # But to be safe and avoid blocking the async event loop, we can wrap it.
        # However, for this simple test, just doing it synchronously in the async function is acceptable.
        import asyncio
        loop = asyncio.get_event_loop()
        def _do_post():
            resp = requests.post(url, headers=_HEADERS, json=payload, timeout=30)
            resp.raise_for_status()
            return resp
            
        resp = await loop.run_in_executor(None, _do_post)
        print(f"--> REST: Service {full_service} called on {entity_id} – OK")
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

if __name__ == "__main__":
    asyncio.run(main())
