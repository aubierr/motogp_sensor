"""Config flow for the MotoGP Sensor integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
import voluptuous as vol

from .api import MotoGPApiClient, MotoGPApiError
from .const import (
    CONF_RACE_WEEK_START,
    DEFAULT_NAME,
    DEFAULT_RACE_WEEK_START,
    DOMAIN,
    RACE_WEEK_START_OPTIONS,
)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_RACE_WEEK_START, default=DEFAULT_RACE_WEEK_START): SelectSelector(
            SelectSelectorConfig(
                options=RACE_WEEK_START_OPTIONS,
                translation_key=CONF_RACE_WEEK_START,
                mode=SelectSelectorMode.DROPDOWN,
            )
        ),
    }
)


class MotoGPConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up MotoGP Sensor (one instance, settings stored as options)."""

    VERSION = 2

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await MotoGPApiClient(async_get_clientsession(self.hass)).seasons()
            except MotoGPApiError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(title=DEFAULT_NAME, data={}, options=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(OPTIONS_SCHEMA, user_input),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> MotoGPOptionsFlow:
        return MotoGPOptionsFlow()


class MotoGPOptionsFlow(OptionsFlow):
    """Change the race week window."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, self.config_entry.options
            ),
        )
