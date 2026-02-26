"""Conversation Agent for HA Assist."""
import logging
from homeassistant.components import conversation
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent
from homeassistant.config_entries import ConfigEntry

from .pipeline import async_run_pipeline, get_ha_context

_LOGGER = logging.getLogger(__name__)

class HAAssistAgent(conversation.AbstractConversationAgent):
    """HA Assist conversation agent."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the agent."""
        self.hass = hass
        self.entry = entry

    @property
    def supported_languages(self) -> list[str] | conversation.Literal["*"]:
        """Return a list of supported languages."""
        return ["en", "de"]

    async def async_process(self, user_input: conversation.ConversationInput) -> conversation.ConversationResult:
        """Process a sentence."""
        text = user_input.text
        
        try:
            # get_ha_context uses hass.states.async_all() safely inside an async context
            ha_context = get_ha_context(self.hass)
            
            # async_run_pipeline uses aiohttp, so it can run natively in the async event loop
            result = await async_run_pipeline(text, ha_context, self.hass)
            
            response_text = "Unknown error"
            if isinstance(result, dict) and "message" in result:
                response_text = result["message"]
            else:
                response_text = str(result)
                
            intent_response = intent.IntentResponse(language=user_input.language)
                
            intent_response.async_set_speech(response_text)
            
            return conversation.ConversationResult(
                response=intent_response,
                conversation_id=user_input.conversation_id
            )
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
