"""MonitorStore – file-backed storage for monitor tasks with background polling.

Monitors wait for an entity state condition to become true, then execute the
``then`` branch.  All active monitors are persisted to a JSON file so they
survive Home Assistant restarts.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from typing import Any, Callable, Coroutine, Dict, List, Optional

logger = logging.getLogger(__name__)

# Default storage file location (inside HA config dir)
_DEFAULT_STORE_FILE = "ha_assist_monitors.json"


class MonitorStore:
    """In-memory + file-backed store of active monitor tasks."""

    def __init__(
        self,
        store_path: str,
        fetch_state_fn: Callable[[str, Any], Dict[str, Any]],
        execute_actions_fn: Callable[[List[Dict[str, Any]], Any], Coroutine],
        hass: Any = None,
    ) -> None:
        self._store_path = store_path
        self._monitors: Dict[str, Dict[str, Any]] = {}
        self._task: Optional[asyncio.Task] = None
        self._fetch_state = fetch_state_fn
        self._execute_actions = execute_actions_fn
        self._hass = hass
        self._on_change_callbacks: List[Callable[[], None]] = []

    # ── Persistence ──────────────────────────────────────────────────────

    def _save(self) -> None:
        """Write current monitors to disk."""
        try:
            with open(self._store_path, "w") as fh:
                json.dump(list(self._monitors.values()), fh, indent=2)
        except Exception as exc:
            logger.error("Failed to save monitor store: %s", exc)

    def _load(self) -> None:
        """Load monitors from disk (if the file exists)."""
        if not os.path.exists(self._store_path):
            return
        try:
            with open(self._store_path, "r") as fh:
                items = json.load(fh)
            for item in items:
                mid = item.get("id")
                if mid:
                    self._monitors[mid] = item
            logger.info("Loaded %d monitors from %s", len(self._monitors), self._store_path)
        except Exception as exc:
            logger.error("Failed to load monitor store: %s", exc)

    # ── Public API ───────────────────────────────────────────────────────

    def add_monitor(self, monitor: Dict[str, Any]) -> str:
        """Register a monitor task.  Returns the generated monitor id."""
        mid = str(uuid.uuid4())
        entry = {
            "id": mid,
            "check": monitor.get("check", {}),
            "condition": monitor.get("condition", {}),
            "then": monitor.get("then", []),
            "poll_seconds": monitor.get("poll_seconds", 60),
            "created_at": time.time(),
        }
        self._monitors[mid] = entry
        self._save()
        self._fire_on_change()
        logger.info("Monitor %s added (entity=%s)", mid, entry["check"].get("entity_id"))
        return mid

    def remove_monitor(self, mid: str) -> None:
        """Remove a monitor by id."""
        self._monitors.pop(mid, None)
        self._save()
        self._fire_on_change()

    def get_all(self) -> List[Dict[str, Any]]:
        """Return a copy of all active monitors."""
        return list(self._monitors.values())

    def is_empty(self) -> bool:
        return len(self._monitors) == 0

    def add_on_change(self, callback: Callable[[], None]) -> None:
        """Register a callback to be called when monitors change."""
        self._on_change_callbacks.append(callback)

    def _fire_on_change(self) -> None:
        """Notify all registered listeners."""
        for cb in self._on_change_callbacks:
            try:
                cb()
            except Exception as exc:
                logger.error("on_change callback failed: %s", exc)

    # ── Background polling ───────────────────────────────────────────────

    def start(self) -> None:
        """Start the background polling loop (call after event loop is running)."""
        self._load()
        if self._task is None or self._task.done():
            self._task = asyncio.ensure_future(self._poll_loop())
            logger.info("Monitor polling loop started")

    def stop(self) -> None:
        """Cancel the background polling loop."""
        if self._task and not self._task.done():
            self._task.cancel()
            logger.info("Monitor polling loop stopped")

    async def _poll_loop(self) -> None:
        """Check each monitor at its own cadence; fire ``then`` when met."""
        # Track last-poll timestamps so each monitor is checked at its own interval
        last_checked: Dict[str, float] = {}

        while True:
            try:
                await asyncio.sleep(1)  # tick every second
                now = time.time()

                # Iterate over a snapshot so we can mutate the dict
                for mid, monitor in list(self._monitors.items()):
                    poll_interval = monitor.get("poll_seconds", 60)
                    last = last_checked.get(mid, 0.0)
                    if now - last < poll_interval:
                        continue
                    last_checked[mid] = now

                    entity_id = monitor.get("check", {}).get("entity_id", "")
                    if not entity_id:
                        logger.warning("Monitor %s has no entity_id, removing", mid)
                        self.remove_monitor(mid)
                        continue

                    # Fetch current state
                    state_data = self._fetch_state(entity_id, self._hass)
                    condition_met = _evaluate_condition(monitor.get("condition", {}), state_data)

                    logger.debug(
                        "Monitor %s: %s %s %s → %s (actual: %s)",
                        mid,
                        monitor["condition"].get("attribute", "state"),
                        monitor["condition"].get("operator", "=="),
                        monitor["condition"].get("value"),
                        condition_met,
                        state_data.get("state"),
                    )

                    if condition_met:
                        logger.info("Monitor %s condition met – executing then branch", mid)
                        then_branch = monitor.get("then", [])
                        try:
                            await self._execute_actions(then_branch, self._hass)
                        except Exception as exc:
                            logger.error("Monitor %s then-branch execution failed: %s", mid, exc)
                        self.remove_monitor(mid)

            except asyncio.CancelledError:
                logger.info("Monitor poll loop cancelled")
                return
            except Exception as exc:
                logger.error("Monitor poll loop error: %s", exc)
                await asyncio.sleep(5)


# ── Condition evaluator (shared with executor.py) ────────────────────────────

from .condition import evaluate_condition as _evaluate_condition
