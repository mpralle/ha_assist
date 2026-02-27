"""Quick script to print Home Assistant entity states."""

import os
import sys
import requests
from dotenv import load_dotenv

# Load real environment config
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

def print_states():
    url = f"{_HA_URL.rstrip('/')}/api/states"
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=30)
        resp.raise_for_status()

        by_domain = {}
        for s in resp.json():
            domain = s["entity_id"].split(".")[0]
            by_domain.setdefault(domain, []).append(s)

        for domain in sorted(by_domain.keys()):
            print(f"[{domain}]")
            for s in sorted(by_domain[domain], key=lambda x: x["entity_id"]):
                name = s.get("attributes", {}).get("friendly_name", "")
                state = s.get("state", "?")
                attrs = s.get("attributes", {})

                # Show a few key attributes if present
                extras = []
                for attr in ("temperature", "current_temperature", "humidity",
                             "brightness", "battery_level", "unit_of_measurement"):
                    if attr in attrs:
                        extras.append(f"{attr}={attrs[attr]}")

                extra_str = f"  ({', '.join(extras)})" if extras else ""
                print(f"  {s['entity_id']:45s}  {state:15s}  {name}{extra_str}")
            print()

    except Exception as e:
        print(f"Failed to fetch states from Home Assistant: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    print_states()
