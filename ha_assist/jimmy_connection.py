# chatjimmy.py
# Simple Python script to interact with ChatJimmy API.
#
# Requirements:
#   pip install requests jsonschema
#
# Optional (recommended) for robust JSON fixing:
#   pip install json-repair
#
# Usage:
#   from chatjimmy import sendMsg
#   result = sendMsg(system_prompt, user_input, schema, base_url="https://chatjimmy.ai")

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional, Union

import requests
from jsonschema import validate
from jsonschema.exceptions import ValidationError
from json_repair import repair_json


JsonType = Union[dict, list, str, int, float, bool, None]


def _extract_likely_json(text: str) -> str:
    """
    Extract the most likely JSON payload from a response that may include extra
    tokens like "<|stats|>" or other non-JSON text.
    """
    cut = text.split("<|stats|>", 1)[0].strip()

    # Prefer object (your system prompt requires { "actions": [...] }).
    first_brace = cut.find("{")
    if first_brace != -1:
        return cut[first_brace:].strip()

    # Fallback: maybe it returns an array
    first_bracket = cut.find("[")
    if first_bracket != -1:
        return cut[first_bracket:].strip()

    return cut


def parse_json_with_repair(raw: str) -> JsonType:
    """
    Parse JSON robustly:
      1) Try strict json.loads
      2) If it fails, try json-repair (if installed)
      3) Otherwise apply a small fallback repair and try again
    """
    candidate = _extract_likely_json(raw)

    try:
        return json.loads(candidate)
    except Exception:
        pass

    repaired = repair_json(candidate)
    return json.loads(repaired)


def sendMsg(
    system_prompt: str,
    user_input: str,
    schema: Dict[str, Any],
    *,
    base_url: str = "https://chatjimmy.ai",
    auth_header: Optional[str] = None,
    model: str = "llama3.1-8B",
    top_k: int = 8,
    timeout_seconds: int = 30,
) -> JsonType:
    """
    Send a single message to ChatJimmy and validate the returned JSON against a provided schema.

    Parameters:
      - system_prompt: your planner/system instruction string
      - user_input: the user message
      - schema: a JSON Schema dict to validate the parsed response against
      - base_url: default https://chatjimmy.ai
      - auth_header: e.g. "Bearer <token>" (if required)
      - model: model name
      - top_k: chat option
      - timeout_seconds: request timeout

    Returns:
      - Parsed JSON (dict/list/etc.) if parsing succeeds and schema validation passes

    Raises:
      - requests.HTTPError on non-2xx responses
      - json.JSONDecodeError if parsing fails even after repair attempts
      - jsonschema.ValidationError if schema validation fails
    """
    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ],
        "chatOptions": {
            "selectedModel": model,
            "systemPrompt": system_prompt,
            "topK": top_k,
        },
        "attachment": None,
    }

    headers = {
        "Content-Type": "application/json",
        "Referer": "https://chatjimmy.ai/",
        "Origin": "https://chatjimmy.ai",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) ChatJimmyPythonClient/1.0",
    }
    if auth_header:
        headers["Authorization"] = auth_header  # or use "Cookie" if your setup needs it

    url = f"{base_url.rstrip('/')}/api/chat"
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout_seconds)

    if not resp.ok:
        body_preview = (resp.text or "")[:1000]
        raise requests.HTTPError(
            f"API error: {resp.status_code} {resp.reason}\nBody: {body_preview}",
            response=resp,
        )

    raw_text = resp.text
    parsed = parse_json_with_repair(raw_text)

    # Validate against provided schema
    try:
        validate(instance=parsed, schema=schema)
    except ValidationError as e:
        # Include a short payload preview to help debugging
        preview = json.dumps(parsed, ensure_ascii=False)[:1000] if isinstance(parsed, (dict, list)) else str(parsed)[:1000]
        raise ValidationError(f"{e.message}\nParsed response preview: {preview}") from e

    return parsed