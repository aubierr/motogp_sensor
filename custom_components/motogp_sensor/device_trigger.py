"""Device triggers for the MotoGP Sensor integration."""

from __future__ import annotations

from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.components.homeassistant.triggers import state as state_trigger
from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_DOMAIN,
    CONF_ENTITY_ID,
    CONF_FOR,
    CONF_PLATFORM,
    CONF_TYPE,
    Platform,
)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo
from homeassistant.helpers.typing import ConfigType
import voluptuous as vol

from .const import DOMAIN

# trigger type -> (unique_id suffix, entity platform, target state)
TRIGGERS: dict[str, tuple[str, Platform, str]] = {
    "race_week_started": ("race_week_binary", Platform.BINARY_SENSOR, "on"),
    "race_week_ended": ("race_week_binary", Platform.BINARY_SENSOR, "off"),
    "session_in_progress": ("session_status", Platform.SENSOR, "in_progress"),
    "session_finished": ("session_status", Platform.SENSOR, "finished"),
    "session_red_flag": ("session_status", Platform.SENSOR, "red_flag"),
    "session_cancelled": ("session_status", Platform.SENSOR, "cancelled"),
    "session_delayed": ("session_status", Platform.SENSOR, "delayed"),
    "live_timing_online": ("live_timing_online", Platform.BINARY_SENSOR, "on"),
    "live_timing_offline": ("live_timing_online", Platform.BINARY_SENSOR, "off"),
}

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_ENTITY_ID): cv.entity_id_or_uuid,
        vol.Required(CONF_TYPE): vol.In(TRIGGERS),
        vol.Optional(CONF_FOR): cv.positive_time_period_dict,
    }
)


async def async_get_triggers(hass: HomeAssistant, device_id: str) -> list[dict[str, str]]:
    """List the triggers whose entity exists on this device."""
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        return []
    entity_registry = er.async_get(hass)
    triggers: list[dict[str, str]] = []
    for entry_id in device.config_entries:
        for trigger_type, (suffix, platform, _state) in TRIGGERS.items():
            entity_id = entity_registry.async_get_entity_id(
                platform, DOMAIN, f"{entry_id}_{suffix}"
            )
            if entity_id is None:
                continue
            triggers.append(
                {
                    CONF_PLATFORM: "device",
                    CONF_DOMAIN: DOMAIN,
                    CONF_DEVICE_ID: device_id,
                    CONF_TYPE: trigger_type,
                    CONF_ENTITY_ID: entity_registry.async_get(entity_id).id,
                }
            )
    return triggers


async def async_attach_trigger(
    hass: HomeAssistant,
    config: ConfigType,
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    """Attach a state trigger on the mapped entity."""
    _suffix, _platform, to_state = TRIGGERS[config[CONF_TYPE]]
    state_config: dict = {
        CONF_PLATFORM: "state",
        CONF_ENTITY_ID: config[CONF_ENTITY_ID],
        "to": to_state,
    }
    if CONF_FOR in config:
        state_config[CONF_FOR] = config[CONF_FOR]
    state_config = await state_trigger.async_validate_trigger_config(hass, state_config)
    return await state_trigger.async_attach_trigger(
        hass, state_config, action, trigger_info, platform_type="device"
    )
