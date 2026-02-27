"""Todo platform for HA Assist – exposes active monitors as a todo list."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

logger = logging.getLogger(__name__)


def _monitor_to_summary(monitor: dict[str, Any]) -> str:
    """Build a human-readable summary string for a monitor."""
    check = monitor.get("check", {})
    cond = monitor.get("condition", {})
    then = monitor.get("then", [])

    entity_id = check.get("entity_id", "?")
    attr = cond.get("attribute", "state")
    op = cond.get("operator", "==")
    value = cond.get("value", "?")

    actions = []
    for a in then:
        task = a.get("task", a.get("service", "?"))
        eid = a.get("entity_id", "")
        actions.append(f"{task} ({eid})" if eid else task)

    action_str = ", ".join(actions) if actions else "no actions"
    return f"{entity_id} {attr} {op} {value} → {action_str}"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the HA Assist monitor todo list."""
    store = hass.data[DOMAIN].get("monitor_store")
    if not store:
        logger.warning("MonitorStore not found, skipping todo platform")
        return

    entity = HAAssistMonitorTodoEntity(store)
    async_add_entities([entity])

    # Live-update when monitors change
    store.add_on_change(entity.async_write_ha_state)


class HAAssistMonitorTodoEntity(TodoListEntity):
    """Todo list entity backed by the MonitorStore."""

    _attr_has_entity_name = True
    _attr_name = "Monitors"
    _attr_unique_id = "ha_assist_monitors"
    _attr_supported_features = (
        TodoListEntityFeature.DELETE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
    )

    def __init__(self, store) -> None:
        self._store = store

    @property
    def todo_items(self) -> list[TodoItem]:
        """Return current monitors as todo items."""
        items: list[TodoItem] = []
        for monitor in self._store.get_all():
            items.append(
                TodoItem(
                    uid=monitor["id"],
                    summary=_monitor_to_summary(monitor),
                    status=TodoItemStatus.NEEDS_ACTION,
                )
            )
        return items

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        """Delete monitors by uid."""
        for uid in uids:
            self._store.remove_monitor(uid)
            logger.info("Monitor %s removed via todo list", uid)

    async def async_update_todo_item(self, item: TodoItem) -> None:
        """Mark a monitor as complete = remove it."""
        if item.status == TodoItemStatus.COMPLETED and item.uid:
            self._store.remove_monitor(item.uid)
            logger.info("Monitor %s completed (removed) via todo list", item.uid)
