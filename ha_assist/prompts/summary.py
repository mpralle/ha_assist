"""Prompt builder for Step 4: Summary."""

from __future__ import annotations
from typing import Any, Dict


def build_prompt(ha_context: Dict[str, Any]) -> str:
    """Build the system prompt, incorporating live Home Assistant state."""
    # TODO: use ha_context to enrich the prompt
    return ""
