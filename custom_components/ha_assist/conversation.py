"""Conversation Agent for HA Assist."""
import logging
from homeassistant.components import conversation
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent
from homeassistant.config_entries import ConfigEntry
from .pipeline import async_run_pipeline, get_ha_context

_LOGGER = logging.getLogger(__name__)


def get_filtered_ha_context(hass: HomeAssistant, options: dict) -> dict:
    """Return HA context filtered to only exposed entities and their allowed services."""
    exposed: dict = options.get("exposed", {})

    # Nothing configured yet — fall back to full context
    if not exposed:
        return get_ha_context(hass)

    entity_details = [
        {
            "entity_id": state.entity_id,
            "domain": state.domain,
            "state": state.state,
            "friendly_name": state.attributes.get("friendly_name", state.entity_id),
            "allowed_services": exposed[state.entity_id]["services"],
        }
        for state in hass.states.async_all()
        if state.entity_id in exposed
    ]

    # Only expose the specific services the user allowed, per domain
    services: dict = {}
    for entity_id, config in exposed.items():
        domain = entity_id.split(".")[0]
        if domain not in services:
            services[domain] = []
        for svc in config["services"]:
            if svc not in services[domain]:
                services[domain].append(svc)

    return {
        "entities": list(exposed.keys()),
        "entity_details": entity_details,
        "services": services,
    }


class HAAssistAgent(conversation.AbstractConversationAgent):
    """HA Assist conversation agent."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry

    @property
    def supported_languages(self) -> list[str] | conversation.Literal["*"]:
        return ["en", "de"]

    async def async_process(self, user_input: conversation.ConversationInput) -> conversation.ConversationResult:
        """Process a sentence."""
        text = user_input.text
        try:
            ha_context = get_filtered_ha_context(self.hass, self.entry.options)
            result = await async_run_pipeline(text, ha_context, self.hass)

            response_text = result["message"] if isinstance(result, dict) and "message" in result else str(result)

            intent_response = intent.IntentResponse(language=user_input.language)
            intent_response.async_set_speech(response_text)

        except Exception as err:
            _LOGGER.exception("Error processing in HA Assist Agent")
            intent_response = intent.IntentResponse(language=user_input.language)
            intent_response.async_set_error(
                intent.IntentResponseErrorCode.UNKNOWN,
                f"Error: {err}"
            )

        return conversation.ConversationResult(
            response=intent_response,
            conversation_id=user_input.conversation_id
        )