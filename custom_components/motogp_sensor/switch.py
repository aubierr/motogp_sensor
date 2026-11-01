"""Switch platform: No Spoiler Mode."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import MotoGPConfigEntry
from .entity import device_info

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MotoGPConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([MotoGPNoSpoilerSwitch(entry)])


class MotoGPNoSpoilerSwitch(SwitchEntity):
    """Freeze results, standings and live classification while on."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "no_spoiler_mode"
    # Same unique_id as v1 so the entity keeps its id and history.
    _attr_unique_id = "motogp_sensor_no_spoiler_mode"

    def __init__(self, entry: MotoGPConfigEntry) -> None:
        self._manager = entry.runtime_data.no_spoiler
        self._attr_device_info = device_info(entry)

    @property
    def is_on(self) -> bool:
        return self._manager.is_active

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            self._manager.async_add_listener(lambda _active: self.async_write_ha_state())
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._manager.async_set_active(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._manager.async_set_active(False)
