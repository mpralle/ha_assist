"""Centralized condition evaluator for HA Assist.

Used by both the Executor (step 3) and the MonitorStore background poller.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict

logger = logging.getLogger(__name__)


def evaluate_condition(condition: Dict[str, Any], state_data: Dict[str, Any]) -> bool:
    """Evaluate a structured condition against entity state data.

    condition format:
        {"attribute": "state", "operator": "==", "value": "off"}

    For attribute "state", compares against the top-level state string.
    For other attributes, looks inside state_data["attributes"].
    """
    attribute = condition.get("attribute", "state")
    operator = condition.get("operator", "==")
    expected = condition.get("value")

    # Get the actual value from state data
    if attribute == "state":
        actual = state_data.get("state")
    else:
        actual = state_data.get("attributes", {}).get(attribute)

    if actual is None:
        logger.warning("Attribute %r not found in state data for %s",
                        attribute, state_data.get("entity_id", "?"))
        return False

    # Try numeric comparison if possible
    try:
        actual_num = float(actual)
        expected_num = float(expected)
        comparisons = {
            "==": actual_num == expected_num,
            "!=": actual_num != expected_num,
            ">":  actual_num > expected_num,
            "<":  actual_num < expected_num,
            ">=": actual_num >= expected_num,
            "<=": actual_num <= expected_num,
        }
        if operator in comparisons:
            return comparisons[operator]
    except (TypeError, ValueError):
        pass

    # Try time comparison (HH:MM or H:MM formats)
    try:
        actual_time = datetime.strptime(str(actual).strip(), "%H:%M").time()
        expected_time = datetime.strptime(str(expected).strip(), "%H:%M").time()
        comparisons = {
            "==": actual_time == expected_time,
            "!=": actual_time != expected_time,
            ">":  actual_time > expected_time,
            "<":  actual_time < expected_time,
            ">=": actual_time >= expected_time,
            "<=": actual_time <= expected_time,
        }
        if operator in comparisons:
            return comparisons[operator]
    except (TypeError, ValueError):
        pass

    # Fall back to string comparison
    actual_str = str(actual).lower().strip()
    expected_str = str(expected).lower().strip()

    if operator == "==":
        return actual_str == expected_str
    elif operator == "!=":
        return actual_str != expected_str
    else:
        logger.warning("Cannot compare %r %s %r as strings", actual, operator, expected)
        return False
