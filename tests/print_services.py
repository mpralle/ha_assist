"""Quick script to print Home Assistant domains and their available services."""

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

def print_services():
    url = f"{_HA_URL.rstrip('/')}/api/services"
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=30)
        resp.raise_for_status()
        
        for domain_info in resp.json():
            domain = domain_info.get("domain", "")
            services = list(domain_info.get("services", {}).keys())
            
            if domain and services:
                print(f"[{domain}]")
                for svc in services:
                    print(f"  - {svc}")
                print()
                
    except Exception as e:
        print(f"Failed to fetch services from Home Assistant: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    print_services()
