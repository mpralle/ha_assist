"""Config flow for HA Assist."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import entity_registry as er
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
            })
        )

    @staticmethod
    def async_get_options_flow(entry):
        return HAAssistOptionsFlow(entry)


class HAAssistOptionsFlow(config_entries.OptionsFlow):

    def __init__(self, entry):
        self._entry = entry
        self._exposed: dict = dict(entry.options.get("exposed", {}))
        self._current_entity = None
        self._entity_ids: list = []

    async def async_step_init(self, user_input=None):
        """Show list of entities to configure."""
        registry = er.async_get(self.hass)
        self._entity_ids = sorted(e.entity_id for e in registry.entities.values())

        if user_input is not None:
            self._current_entity = user_input["entity_id"]
            return await self.async_step_entity()

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("entity_id"): vol.In(self._entity_ids)
            }),
            description_placeholders={"count": str(len(self._exposed))}
        )

    async def async_step_entity(self, user_input=None):
        """Configure allowed services for the selected entity."""
        entity_id = self._current_entity
        domain = entity_id.split(".")[0]
        all_services = sorted(self.hass.services.async_services().get(domain, {}).keys())
        current = self._exposed.get(entity_id, {})

        if user_input is not None:
            if user_input.get("expose"):
                self._exposed[entity_id] = {"services": user_input.get("services", [])}
            else:
                self._exposed.pop(entity_id, None)

            return self.async_create_entry(title="", data={"exposed": self._exposed})

        return self.async_show_form(
            step_id="entity",
            data_schema=vol.Schema({
                vol.Required("expose", default=entity_id in self._exposed): bool,
                vol.Optional(
                    "services",
                    default=current.get("services", all_services)
                ): vol.All([vol.In(all_services)], [str]),
            }),
            description_placeholders={"entity_id": entity_id}
        )