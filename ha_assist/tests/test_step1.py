"""Quick test for Step 1: TaskExtractor.

Usage (with venv activated):
    export HA_URL="http://<your-ha-ip>:8123/api"
    export HA_TOKEN="<your-long-lived-access-token>"
    python test_step1.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from assist import get_ha_context
from prompts.task_extractor import _get_available_domains, build_prompt
from steps import TaskExtractor

# ── 1. Gather HA context ─────────────────────────────────────────────────────
print("=" * 60)
print("Fetching Home Assistant context...")
print("=" * 60)

ha_context = get_ha_context()
entities = ha_context["entities"]
print(f"\nTotal entities found: {len(entities)}")

domains = sorted(_get_available_domains(ha_context))
print(f"Available domains ({len(domains)}): {', '.join(domains)}\n")

# ── 2. Show generated prompt (truncated) ─────────────────────────────────────
print("=" * 60)
print("Generated system prompt (first 500 chars):")
print("=" * 60)
prompt = build_prompt(ha_context)
print(prompt[:500])
print("...\n")

# ── 3. Run Step 1 on a test input ────────────────────────────────────────────
USER_INPUT = "Turn off the schreibtischlampe."

print("=" * 60)
print(f"User input: {USER_INPUT}")
print("Calling TaskExtractor...")
print("=" * 60)

try:
    result = TaskExtractor().run(USER_INPUT, ha_context)
    print("\nTaskExtractor result:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
except Exception as exc:
    print(f"\nError: {exc}", file=sys.stderr)
    sys.exit(1)
