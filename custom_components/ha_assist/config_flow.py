"""Config flow for HA Assist."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector, device_registry as dr, entity_registry as er
from .const import DOMAIN


class HAAssistConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="HA Assist", data=user_input)
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("api_key"): str,
                vol.Optional("model", default="gpt-4o"): str,
            })
        )

    @staticmethod
    def async_get_options_flow(entry):
        return HAAssistOptionsFlow(entry)


class HAAssistOptionsFlow(config_entries.OptionsFlow):

    def __init__(self, entry):
        self._entry = entry
        self._exposed: dict = dict(entry.options.get("exposed", {}))
        self._selected_entities: list[str] = list(entry.options.get("exposed", {}).keys())
        self._pending_entities: list[str] = []   # entities still needing service config
        self._current_entity: str | None = None

    async def async_step_init(self, user_input=None):
        """Step 1: Pick which entities to expose using HA's native entity selector."""
        if user_input is not None:
            newly_selected: list[str] = user_input.get("entities", [])

            # Remove entities that were deselected
            for entity_id in list(self._exposed.keys()):
                if entity_id not in newly_selected:
                    self._exposed.pop(entity_id)

            # Queue up newly added entities for service configuration
            self._pending_entities = [e for e in newly_selected if e not in self._exposed]

            if self._pending_entities:
                self._current_entity = self._pending_entities.pop(0)
                return await self.async_step_services()

            # Nothing new to configure, save immediately
            return self.async_create_entry(title="", data={"exposed": self._exposed})

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(
                    "entities",
                    default=self._selected_entities
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(multiple=True)
                ),
            }),
            description_placeholders={"count": str(len(self._exposed))}
        )

    async def async_step_services(self, user_input=None):
        """Step 2: For each newly added entity, pick which services to allow."""
        entity_id = self._current_entity
        domain = entity_id.split(".")[0]

        # Get available services for this domain
        all_services = sorted(
            self.hass.services.async_services().get(domain, {}).keys()
        )

        if user_input is not None:
            self._exposed[entity_id] = {
                "services": user_input.get("services", all_services)
            }

            # Move to the next pending entity, or finish
            if self._pending_entities:
                self._current_entity = self._pending_entities.pop(0)
                return await self.async_step_services()

            return self.async_create_entry(title="", data={"exposed": self._exposed})

        # Resolve friendly name for a nicer title
        state = self.hass.states.get(entity_id)
        friendly_name = (
            state.attributes.get("friendly_name", entity_id) if state else entity_id
        )

        return self.async_show_form(
            step_id="services",
            data_schema=vol.Schema({
                vol.Optional(
                    "services",
                    default=self._exposed.get(entity_id, {}).get("services", all_services)
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=all_services,
                        multiple=True,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                ),
            }),
            description_placeholders={
                "entity_id": entity_id,
                "friendly_name": friendly_name,
                "remaining": str(len(self._pending_entities)),
            }
        )