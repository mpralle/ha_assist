# HA Assist

A custom Home Assistant integration for building a local LLM-powered assistant without relying on an external Wyoming server.

## Installation via HACS

1. Go to **HACS** in your Home Assistant installation.
2. Select **Integrations**.
3. Click the three dots in the top right corner and select **Custom repositories**.
4. Add the URL to this repository and select **Integration** as the category.
5. Search for "HA Assist" in HACS and install it.
6. Restart Home Assistant.
7. Go to **Settings** -> **Devices & Services** -> **Add Integration** and search for "HA Assist" to configure it.

## Directory Structure

```
ha_assist/
├── custom_components/
│   └── ha_assist/          # The HACS integration folder
│       ├── __init__.py     # Integration setup
│       ├── manifest.json   # Integration metadata
│       ├── config_flow.py  # UI Configuration
│       ├── conversation.py # Conversation Agent entry point
│       ├── pipeline.py     # Pipeline execution 
│       └── steps/          # Logic for task parsing, entity matching, executing, summarizing
└── hacs.json               # HACS repository metadata
```
