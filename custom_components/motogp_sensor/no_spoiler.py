"""No Spoiler Mode state, persisted across restarts.

While the mode is on, entities flagged as spoilers (results, standings, live
classification) keep the state they had when the mode was switched on. The
coordinators keep fetching, so switching the mode off catches up instantly.
"""

from __future__ import annotations

from collections.abc import Callable
import logging

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store

_LOGGER = logging.getLogger(__name__)

_STORAGE_KEY = "motogp_sensor_no_spoiler_v1"
_STORAGE_VERSION = 1


class NoSpoilerManager:
    """Hold the No Spoiler Mode flag and notify listeners on change."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store[dict[str, bool]] = Store(hass, _STORAGE_VERSION, _STORAGE_KEY)
        self._active = False
        self._listeners: list[Callable[[bool], None]] = []

    @property
    def is_active(self) -> bool:
        return self._active

    async def async_load(self) -> None:
        data = await self._store.async_load()
        self._active = bool(data and data.get("active"))

    @callback
    def async_add_listener(self, listener: Callable[[bool], None]) -> Callable[[], None]:
        """Register a listener called with the new state; return an unsubscribe."""
        self._listeners.append(listener)

        @callback
        def _remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return _remove

    async def async_set_active(self, active: bool) -> None:
        if active == self._active:
            return
        self._active = active
        await self._store.async_save({"active": active})
        _LOGGER.debug("No Spoiler Mode %s", "enabled" if active else "disabled")
        for listener in list(self._listeners):
            listener(active)
