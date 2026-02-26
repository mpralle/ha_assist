"""Print all HA entity states, optionally filtered by domain.

Usage:
    python3 tests/print_states.py              # all entities
    python3 tests/print_states.py media_player  # only media_player entities
    python3 tests/print_states.py light switch  # light + switch entities
"""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from assist import get_ha_context

ha_context = get_ha_context()
entities = ha_context["entity_details"]

# Optional domain filter from CLI args
filter_domains = set(sys.argv[1:]) if len(sys.argv) > 1 else None

for e in sorted(entities, key=lambda x: x["entity_id"]):
    if filter_domains and e["domain"] not in filter_domains:
        continue
    print(f"  {e['entity_id']:45s}  state={e['state']:15s}  ({e['friendly_name']})")

print(f"\nShowing {len([e for e in entities if not filter_domains or e['domain'] in filter_domains])} entities")
