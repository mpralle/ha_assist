"""HA Assist Custom Component."""
import os

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.conversation import async_set_agent, async_unset_agent

from .conversation import HAAssistAgent
from .const import DOMAIN
from .monitor_store import MonitorStore
from .steps.executor import _async_execute_actions, _fetch_entity_state

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HA Assist from a config entry."""
    agent = HAAssistAgent(hass, entry)
    async_set_agent(hass, entry, agent)
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = agent

    # ── Monitor Store ────────────────────────────────────────────────────
    store_path = os.path.join(hass.config.config_dir, "ha_assist_monitors.json")
    store = MonitorStore(
        store_path=store_path,
        fetch_state_fn=_fetch_entity_state,
        execute_actions_fn=_async_execute_actions,
        hass=hass,
    )
    store.start()
    hass.data[DOMAIN]["monitor_store"] = store

    # Forward platforms
    await hass.config_entries.async_forward_entry_setups(entry, ["todo"])

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    async_unset_agent(hass, entry)

    # Unload platforms
    await hass.config_entries.async_unload_platforms(entry, ["todo"])

    # Stop monitor polling
    store = hass.data[DOMAIN].get("monitor_store")
    if store:
        store.stop()
        hass.data[DOMAIN].pop("monitor_store", None)

    if entry.entry_id in hass.data[DOMAIN]:
        hass.data[DOMAIN].pop(entry.entry_id)
    return True
