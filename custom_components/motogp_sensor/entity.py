"""Base entity for the MotoGP Sensor integration."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.core import CALLBACK_TYPE, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_LEGACY_DISABLED, DOMAIN
from .coordinator import MotoGPConfigEntry, MotoGPCoordinator

_MISSING: Any = object()


def device_info(entry: MotoGPConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="MotoGP (unofficial)",
        model="Season and live timing",
        entry_type=DeviceEntryType.SERVICE,
        configuration_url="https://www.motogp.com",
    )


class MotoGPEntity[CoordinatorT: MotoGPCoordinator[Any]](CoordinatorEntity[CoordinatorT]):
    """Coordinator entity with No Spoiler support and time based refreshes.

    Subclasses read ``self.data`` instead of ``self.coordinator.data``: while
    No Spoiler Mode is on, spoiler entities get the data frozen when the mode
    was switched on (or become unavailable after a restart).
    """

    _attr_has_entity_name = True
    _spoiler = False

    def __init__(
        self, coordinator: CoordinatorT, key: str, unique_suffix: str | None = None
    ) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.entry_id}_{unique_suffix or key}"
        self._attr_device_info = device_info(entry)
        if key in entry.data.get(CONF_LEGACY_DISABLED, ()):
            self._attr_entity_registry_enabled_default = False
        self._frozen: Any = _MISSING
        self._unsub_timer: CALLBACK_TYPE | None = None

    # ── No Spoiler Mode ──────────────────────────────────────────────────────

    @property
    def _hidden(self) -> bool:
        return self._spoiler and self.coordinator.config_entry.runtime_data.no_spoiler.is_active

    @property
    def data(self) -> Any:
        if self._hidden:
            return None if self._frozen is _MISSING else self._frozen
        return self.coordinator.data

    @property
    def available(self) -> bool:
        if self._hidden:
            return self._frozen is not _MISSING
        return super().available

    @callback
    def _async_no_spoiler_changed(self, active: bool) -> None:
        if active and self.coordinator.last_update_success:
            self._frozen = self.coordinator.data
        else:
            self._frozen = _MISSING
        self.async_write_ha_state()

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self._spoiler:
            self.async_on_remove(
                self.coordinator.config_entry.runtime_data.no_spoiler.async_add_listener(
                    self._async_no_spoiler_changed
                )
            )
        self.async_on_remove(self._async_cancel_timer)
        self._async_schedule_time_update()

    @callback
    def _handle_coordinator_update(self) -> None:
        if self._hidden:
            return
        super()._handle_coordinator_update()
        self._async_schedule_time_update()

    # ── Time based refresh ───────────────────────────────────────────────────

    def _next_time_update(self) -> datetime | None:
        """Return when the state changes without new data (override)."""
        return None

    @callback
    def _async_cancel_timer(self) -> None:
        if self._unsub_timer is not None:
            self._unsub_timer()
            self._unsub_timer = None

    @callback
    def _async_schedule_time_update(self) -> None:
        self._async_cancel_timer()
        if (when := self._next_time_update()) is not None:
            self._unsub_timer = async_track_point_in_utc_time(
                self.hass, self._async_time_update, when
            )

    @callback
    def _async_time_update(self, _now: datetime) -> None:
        self._unsub_timer = None
        self.async_write_ha_state()
        self._async_schedule_time_update()
