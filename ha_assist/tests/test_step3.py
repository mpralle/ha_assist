"""Quick test for Steps 1–4: TaskExtractor → EntitySelector → Executor → Summary.

Usage (with venv activated, .env configured):
    python tests/test_step3.py
"""

import json
import os
import sys
import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from assist import get_ha_context
from steps import TaskExtractor, EntitySelector, Executor, Summary

# ── 1. Gather HA context ─────────────────────────────────────────────────────
print("=" * 60)
print("Fetching Home Assistant context...")
print("=" * 60)

ha_context = get_ha_context()
entities = ha_context["entity_details"]
services = ha_context["services"]
print(f"\nTotal entities: {len(entities)}")
print(f"Service domains: {len(services)}")
print()

# ── 2. Run Step 1: TaskExtractor ─────────────────────────────────────────────
USER_INPUT = "turn off the schreibtischlampe."

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

# ── 4. Run Step 3: Executor ──────────────────────────────────────────────────
print("\n" + "=" * 60)
print("Step 3 — Executor")
print("=" * 60)

step3_result = Executor().run(step2_result, ha_context)
print("\nExecutor result:")
print(json.dumps(step3_result, indent=2, ensure_ascii=False))
time.sleep(2)

# ── 5. Run Step 4: Summary ───────────────────────────────────────────────────
print("\n" + "=" * 60)
print("Step 4 — Summary (include_errors=True)")
print("=" * 60)

step4_result = Summary(include_errors=True).run(step3_result, ha_context)
print("\nSummary result:")
print(json.dumps(step4_result, indent=2, ensure_ascii=False))

