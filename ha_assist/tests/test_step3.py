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

SLEEP_TIME = 2

start_time = time.time()
sleep_time = 0

# ── 1. Gather HA context ─────────────────────────────────────────────────────
print("=" * 60)
print("Fetching Home Assistant context...")
print("=" * 60)

t0 = time.time()
ha_context = get_ha_context()
time_ha_context = time.time() - t0
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

t0 = time.time()
step1_result = TaskExtractor().run(USER_INPUT, ha_context)
time_step1 = time.time() - t0
print("\nTaskExtractor result:")
print(json.dumps(step1_result, indent=2, ensure_ascii=False))
time.sleep(SLEEP_TIME)
sleep_time += SLEEP_TIME

# ── 3. Run Step 2: EntitySelector ────────────────────────────────────────────
print("\n" + "=" * 60)
print("Step 2 — EntitySelector")
print("=" * 60)

t0 = time.time()
step2_result = EntitySelector().run(step1_result, ha_context)
time_step2 = time.time() - t0
print("\nEntitySelector result:")
print(json.dumps(step2_result, indent=2, ensure_ascii=False))

# ── 4. Run Step 3: Executor ──────────────────────────────────────────────────
print("\n" + "=" * 60)
print("Step 3 — Executor")
print("=" * 60)

t0 = time.time()
step3_result = Executor().run(step2_result, ha_context)
time_step3 = time.time() - t0
print("\nExecutor result:")
print(json.dumps(step3_result, indent=2, ensure_ascii=False))
time.sleep(SLEEP_TIME)
sleep_time += SLEEP_TIME

# ── 5. Run Step 4: Summary ───────────────────────────────────────────────────
print("\n" + "=" * 60)
print("Step 4 — Summary (include_errors=True)")
print("=" * 60)

t0 = time.time()
step4_result = Summary(include_errors=True).run(step3_result, ha_context)
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

