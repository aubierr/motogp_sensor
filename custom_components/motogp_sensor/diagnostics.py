"""Diagnostics for the MotoGP Sensor integration (no personal data involved)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.core import HomeAssistant

from .coordinator import MotoGPConfigEntry, MotoGPCoordinator


def _coordinator(coordinator: MotoGPCoordinator[Any]) -> dict[str, Any]:
    data = coordinator.data
    return {
        "last_update_success": coordinator.last_update_success,
        "update_interval": str(coordinator.update_interval),
        "data": asdict(data) if data is not None else None,
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: MotoGPConfigEntry
) -> dict[str, Any]:
    runtime = entry.runtime_data
    return {
        "entry": {
            "version": entry.version,
            "data": dict(entry.data),
            "options": dict(entry.options),
        },
        "no_spoiler_active": runtime.no_spoiler.is_active,
        "schedule": _coordinator(runtime.schedule),
        "results": _coordinator(runtime.results),
        "live": _coordinator(runtime.live),
        "weather": _coordinator(runtime.weather),
    }
