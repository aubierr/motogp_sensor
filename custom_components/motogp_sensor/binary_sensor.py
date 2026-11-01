"""Binary sensor platform for the MotoGP Sensor integration."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import CONF_RACE_WEEK_START, DEFAULT_RACE_WEEK_START
from .coordinator import LiveCoordinator, MotoGPConfigEntry, ScheduleCoordinator
from .entity import MotoGPEntity
from .parsers import race_week_window

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MotoGPConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = entry.runtime_data
    async_add_entities(
        [
            MotoGPRaceWeekBinarySensor(runtime.schedule),
            MotoGPLiveTimingOnlineBinarySensor(runtime.live),
        ]
    )


class MotoGPRaceWeekBinarySensor(MotoGPEntity[ScheduleCoordinator], BinarySensorEntity):
    """On from the configured start day of a GP week until after the race."""

    def __init__(self, coordinator: ScheduleCoordinator) -> None:
        # The "_binary" suffix keeps the v1 unique_id.
        super().__init__(coordinator, "race_week", unique_suffix="race_week_binary")

    def _window(self) -> tuple[datetime, datetime] | None:
        data = self.data
        if data is None or data.focus is None:
            return None
        option = self.coordinator.config_entry.options.get(
            CONF_RACE_WEEK_START, DEFAULT_RACE_WEEK_START
        )
        return race_week_window(
            data.focus, data.focus_sessions, option, dt_util.get_default_time_zone()
        )

    @property
    def is_on(self) -> bool:
        window = self._window()
        return window is not None and window[0] <= dt_util.now() < window[1]

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        window = self._window()
        data = self.data
        if window is None or data is None or data.focus is None:
            return None
        return {
            "event_name": data.focus.name,
            "short_name": data.focus.short_name,
            "circuit": data.focus.circuit_name,
            "country": data.focus.country_name,
            "date_start": data.focus.date_start.isoformat(),
            "date_end": data.focus.date_end.isoformat(),
            "window_start": window[0].isoformat(),
            "window_end": window[1].isoformat(),
        }

    def _next_time_update(self) -> datetime | None:
        if (window := self._window()) is None:
            return None
        now = dt_util.now()
        return next((edge for edge in window if edge > now), None)


class MotoGPLiveTimingOnlineBinarySensor(MotoGPEntity[LiveCoordinator], BinarySensorEntity):
    """On when the Pulselive live timing endpoint answers."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: LiveCoordinator) -> None:
        super().__init__(coordinator, "live_timing_online")

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        return {
            "session": data.session_type if data else None,
            "update_interval": (
                int(self.coordinator.update_interval.total_seconds())
                if self.coordinator.update_interval
                else None
            ),
        }
