"""The MotoGP Sensor integration."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import MotoGPApiClient
from .const import (
    CONF_LEGACY_DISABLED,
    CONF_RACE_WEEK_START,
    DEFAULT_NAME,
    DEFAULT_RACE_WEEK_START,
    DOMAIN,
    PLATFORMS,
    RACE_WEEK_START_EVENT,
    RACE_WEEK_START_OPTIONS,
)
from .coordinator import (
    LiveCoordinator,
    MotoGPConfigEntry,
    MotoGPRuntimeData,
    ResultsCoordinator,
    ScheduleCoordinator,
    WeatherCoordinator,
)
from .no_spoiler import NoSpoilerManager

_LOGGER = logging.getLogger(__name__)

# Sensor keys selectable in the v1 config flow.
_V1_SENSOR_KEYS = frozenset(
    {
        "next_race", "current_season", "rider_standings", "last_race_results",
        "session_status", "current_session", "race_lap_count", "rider_list",
        "rider_positions", "top_three", "leader", "fastest_lap",
        "session_time_remaining", "live_timing_source", "official_live_diagnostic",
        "race_week", "live_timing_online", "calendar", "constructor_standings",
        "track_weather", "pit_stops",
    }
)  # fmt: skip
# v1 entities without a v2 equivalent (the motogp.com feed no longer exists).
_V1_REMOVED_ENTITIES = (
    (Platform.SENSOR, "live_timing_source"),
    (Platform.SENSOR, "official_live_diagnostic"),
    (Platform.SELECT, "live_source"),
)
# v1 calendar key differs from its translation key.
_V1_KEY_ALIASES = {"calendar": "season_calendar"}


async def async_setup_entry(hass: HomeAssistant, entry: MotoGPConfigEntry) -> bool:
    """Set up MotoGP Sensor from a config entry."""
    client = MotoGPApiClient(async_get_clientsession(hass))
    no_spoiler = NoSpoilerManager(hass)
    await no_spoiler.async_load()

    schedule = ScheduleCoordinator(hass, entry, client)
    # The schedule is required by everything else: retry setup until it loads.
    await schedule.async_config_entry_first_refresh()

    results = ResultsCoordinator(hass, entry, client, schedule)
    live = LiveCoordinator(hass, entry, client, schedule)
    weather = WeatherCoordinator(hass, entry, client, schedule)
    # Their failures only make their own entities unavailable until a retry.
    await asyncio.gather(results.async_refresh(), live.async_refresh(), weather.async_refresh())

    entry.runtime_data = MotoGPRuntimeData(
        client=client,
        schedule=schedule,
        results=results,
        live=live,
        weather=weather,
        no_spoiler=no_spoiler,
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: MotoGPConfigEntry) -> None:
    """Options only change how the race week is computed: refresh its state."""
    entry.runtime_data.schedule.async_update_listeners()


async def async_unload_entry(hass: HomeAssistant, entry: MotoGPConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_migrate_entry(hass: HomeAssistant, entry: MotoGPConfigEntry) -> bool:
    """Migrate a v1 entry (settings in data) to v2 (settings in options)."""
    if entry.version > 2:
        return False

    if entry.version == 1:
        data = dict(entry.data)
        if "disabled_sensors" in data:
            disabled = set(data["disabled_sensors"] or ())
        elif "enabled_sensors" in data:
            disabled = _V1_SENSOR_KEYS - set(data["enabled_sensors"] or ())
        else:
            disabled = set()
        disabled = {_V1_KEY_ALIASES.get(key, key) for key in disabled}

        start = data.get(CONF_RACE_WEEK_START, DEFAULT_RACE_WEEK_START)
        if start == "saturday":
            # v1 "Saturday (race weekend only)" actually opened the Saturday
            # *before* the GP; v2 implements what the label promised.
            start = RACE_WEEK_START_EVENT
        if start not in RACE_WEEK_START_OPTIONS:
            start = DEFAULT_RACE_WEEK_START

        registry = er.async_get(hass)
        for platform, suffix in _V1_REMOVED_ENTITIES:
            if entity_id := registry.async_get_entity_id(
                platform, DOMAIN, f"{entry.entry_id}_{suffix}"
            ):
                registry.async_remove(entity_id)

        hass.config_entries.async_update_entry(
            entry,
            title=data.get("sensor_name") or entry.title or DEFAULT_NAME,
            data={CONF_LEGACY_DISABLED: sorted(disabled)},
            options={CONF_RACE_WEEK_START: start},
            version=2,
        )
        _LOGGER.info("Migrated MotoGP Sensor config entry to version 2")

    return True
