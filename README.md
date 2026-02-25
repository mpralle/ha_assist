# HA Assist

A custom Home Assistant add-on repository for building an assistant.

## Add-ons

| Add-on                              | Description                                          |
| ----------------------------------- | ---------------------------------------------------- |
| [HA Assist](./ha_assist)            | A custom assistant add-on for Home Assistant          |

## Installation

1. In Home Assistant go to **Settings → Add-ons → Add-on Store**.
2. Click the **⋮** menu (top-right) → **Repositories**.
3. Paste the URL of this repository and click **Add**.
4. Refresh the page — *HA Assist* will appear in the store.
5. Click it, then **Install**.

## Development

The add-on lives in the `ha_assist/` directory. Key files:

```
ha_assist/
├── config.yaml       # Add-on metadata & options
├── Dockerfile         # Container build instructions
├── build.yaml         # Base image per architecture
├── run.sh             # Entrypoint script
├── DOCS.md            # User-facing documentation
├── CHANGELOG.md       # Version history
├── translations/
│   └── en.yaml        # English UI strings
└── rootfs/            # Files overlaid into the container
```
