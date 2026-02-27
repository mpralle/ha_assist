"""Conversation Agent for HA Assist."""
import logging
from homeassistant.components import conversation
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry
from homeassistant.config_entries import ConfigEntry
from .pipeline import async_run_pipeline, get_ha_context

_LOGGER = logging.getLogger(__name__)


from homeassistant.components.homeassistant import async_should_expose

def get_filtered_ha_context(hass: HomeAssistant) -> dict:
    """Return only entities exposed to the conversation assistant in HA settings."""
    # Fetch aliases from entity registry
    ent_reg = async_get_entity_registry(hass)
    alias_map: dict[str, list[str]] = {}
    for entry in ent_reg.entities.values():
        if entry.aliases:
            alias_map[entry.entity_id] = list(entry.aliases)

    entity_details = []
    for state in hass.states.async_all():
        if not async_should_expose(hass, "conversation", state.entity_id):
            continue
        detail = {
            "entity_id": state.entity_id,
            "domain": state.domain,
            "state": state.state,
            "friendly_name": state.attributes.get("friendly_name", state.entity_id),
        }
        entity_aliases = alias_map.get(state.entity_id, [])
        if entity_aliases:
            detail["aliases"] = entity_aliases
        entity_details.append(detail)

    # Build services dict from exposed entity domains only
    exposed_domains = {e["domain"] for e in entity_details}
    all_services = hass.services.async_services()
    services = {
        domain: list(svcs.keys())
        for domain, svcs in all_services.items()
        if domain in exposed_domains
    }

    return {
        "entities": [e["entity_id"] for e in entity_details],
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
            ha_context = get_filtered_ha_context(self.hass)

            # Make monitor store available to the executor
            from .const import DOMAIN
            domain_data = self.hass.data.get(DOMAIN, {})
            store = domain_data.get("monitor_store")
            if store:
                ha_context["monitor_store"] = store

            result = await async_run_pipeline(text, ha_context, self.hass, language=user_input.language)

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