"""Config flow for HA Assist."""
import voluptuous as vol
from homeassistant import config_entries

from .const import DOMAIN

class HAAssistConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for HA Assist."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is not None:
            return self.async_create_entry(title="HA Assist", data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("api_key"): str,
                vol.Optional("model", default="gpt-4o"): str,
            })
        )
