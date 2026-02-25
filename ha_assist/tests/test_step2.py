"""Quick test for Step 1 + Step 2: TaskExtractor → EntitySelector.

Usage (with venv activated, .env configured):
    python tests/test_step2.py
"""

import json
import os
import sys
import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from assist import get_ha_context
from prompts.entity_selector import _build_entity_list
from steps import TaskExtractor, EntitySelector

# ── 1. Gather HA context ─────────────────────────────────────────────────────
print("=" * 60)
print("Fetching Home Assistant context...")
print("=" * 60)

ha_context = get_ha_context()
entities = ha_context["entity_details"]
services = ha_context["services"]
print(f"\nTotal entities: {len(entities)}")
print(f"Service domains: {len(services)}")

# Show a few entity samples
print("\nSample entities:")
for e in entities[:5]:
    print(f"  {e['entity_id']}  ({e['friendly_name']})  state={e['state']}")
print()

# Show available services for key domains
for domain in ["light", "switch", "lock", "cover", "climate"]:
    if domain in services:
        print(f"  {domain}: {', '.join(services[domain][:8])}...")
print()

# ── 2. Run Step 1: TaskExtractor ─────────────────────────────────────────────
USER_INPUT = "Turn off the schreibtischlampe and schranklampe."

print("=" * 60)
print(f"Step 1 — User input: {USER_INPUT}")
print("=" * 60)

step1_result = TaskExtractor().run(USER_INPUT, ha_context)
print("\nTaskExtractor result:")
print(json.dumps(step1_result, indent=2, ensure_ascii=False))
time.sleep(2)
# ── 3. Run Step 2: EntitySelector ────────────────────────────────────────────
print("\n" + "=" * 60)
print("Step 2 — EntitySelector")
print("=" * 60)

step2_result = EntitySelector().run(step1_result, ha_context)
print("\nEntitySelector result:")
print(json.dumps(step2_result, indent=2, ensure_ascii=False))
