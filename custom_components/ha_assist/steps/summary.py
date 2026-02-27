"""Step 4: Summary – produce a user-friendly message from executor results."""

from __future__ import annotations

import json
from typing import Any, Dict

from ..jimmy_connection import async_send_msg, parse_json_with_repair
from ..prompts.summary import build_prompt, _flatten_results
import aiohttp


SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["message"],
    "additionalProperties": False,
    "properties": {
        "message": {"type": "string"},
    },
}


class Summary:
    """Step 4 of the agent pipeline.

    Args:
        include_errors: If True (default), the summary will mention failures.
                        If False, only successful actions are summarised.
    """

    def __init__(self, *, include_errors: bool = True) -> None:
        self.include_errors = include_errors

    async def async_run(self, previous_output: Any, ha_context: Dict[str, Any]) -> Any:
        actions = previous_output.get("actions", [])

        # Flatten the nested executor results into a simple list
        flat_results = _flatten_results(actions)
        language = ha_context.get("language", "en")

        if not flat_results:
            fallback = "Es wurde nichts ausgeführt." if language == "de" else "Nothing was executed."
            return {"message": fallback}

        system_prompt = build_prompt(ha_context, include_errors=self.include_errors, language=language)
        user_message = json.dumps(flat_results, ensure_ascii=False)

        try:
            result = await async_send_msg(system_prompt, user_message, SCHEMA)
            return result
        except Exception:
            # Small models may return plain text instead of JSON.
            payload = {
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                "chatOptions": {
                    "selectedModel": "llama3.1-8B",
                    "systemPrompt": system_prompt,
                    "topK": 8,
                },
                "attachment": None,
            }
            headers = {
                "Content-Type": "application/json",
                "Referer": "https://chatjimmy.ai/",
                "Origin": "https://chatjimmy.ai",
                "User-Agent": "Mozilla/5.0 ChatJimmyPythonClient/1.0",
            }
            
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    "https://chatjimmy.ai/api/chat",
                    headers=headers,
                    json=payload,
                ) as resp:
                    raw_text = await resp.text()

            raw = raw_text.split("<|stats|>", 1)[0].strip()
            # Try to parse as JSON first
            try:
                parsed = parse_json_with_repair(raw)
                if isinstance(parsed, dict) and "message" in parsed:
                    return parsed
            except Exception:
                pass
            return {"message": raw}
