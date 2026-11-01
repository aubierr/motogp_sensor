"""Integration tests: setup, entities, migration, No Spoiler, triggers."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.device_automation import DeviceAutomationType
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_get_device_automations,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.motogp_sensor.const import (
    CONF_LEGACY_DISABLED,
    CONF_RACE_WEEK_START,
    DOMAIN,
    PULSELIVE_BASE_URL,
)

from .conftest import NOW, load_fixture


@pytest.fixture(autouse=True)
def _frozen_time(freezer: FrozenDateTimeFactory) -> None:
    freezer.move_to(NOW)


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_setup_creates_entities(
    hass: HomeAssistant, mock_api: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED

    next_race = hass.states.get("sensor.motogp_next_race")
    assert next_race.state == "GRAND PRIX OF QATAR"
    assert next_race.attributes["round"] == 20
    # 19:00 in Lusail (UTC+3).
    assert next_race.attributes["race_start"] == "2026-11-08T16:00:00+00:00"
    assert next_race.attributes["sprint_start"] == "2026-11-07T16:00:00+00:00"

    assert hass.states.get("sensor.motogp_next_session").state == "2026-11-06T11:45:00+00:00"
    assert hass.states.get("sensor.motogp_current_season").state == "2026"

    standings = hass.states.get("sensor.motogp_rider_standings")
    assert standings.state == "Marc Marquez"
    assert standings.attributes["standings"][0]["race_wins"] == 7

    last_race = hass.states.get("sensor.motogp_last_race_results")
    assert last_race.state == "GRAND PRIX OF MALAYSIA"
    assert last_race.attributes["winner"] == "Marc Marquez"
    assert last_race.attributes["round"] == 19
    assert last_race.attributes["results"][0]["gap"] == "0.000"

    assert (
        hass.states.get("sensor.motogp_last_sprint_results").attributes["results"][0]["points"]
        == 12.5
    )
    assert hass.states.get("sensor.motogp_team_standings").state == "Ducati Lenovo Team"
    assert hass.states.get("sensor.motogp_constructor_standings").state == "Ducati"

    assert hass.states.get("sensor.motogp_session_status").state == "finished"
    assert hass.states.get("sensor.motogp_leader").state == "Marc Marquez"
    assert hass.states.get("sensor.motogp_race_lap_count").state == "20"
    assert hass.states.get("binary_sensor.motogp_live_timing_online").state == STATE_ON

    weather = hass.states.get("sensor.motogp_track_weather")
    assert weather.state == "partly_cloudy"
    assert weather.attributes["race_condition"] == "light_rain"
    assert weather.attributes["track_condition"] is None  # Qatar not started yet

    # Monday of the Qatar GP week.
    race_week = hass.states.get("binary_sensor.motogp_race_week")
    assert race_week.state == STATE_ON
    assert race_week.attributes["event_name"] == "GRAND PRIX OF QATAR"

    assert hass.states.get("calendar.motogp_season_calendar") is not None
    assert hass.states.get("switch.motogp_no_spoiler_mode").state == STATE_OFF

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_retries_when_api_down(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    aioclient_mock.get(f"{PULSELIVE_BASE_URL}/results/seasons", status=503)
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_race_week_option_applies_without_reload(
    hass: HomeAssistant, mock_api: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    await _setup(hass, config_entry)
    hass.config_entries.async_update_entry(
        config_entry, options={CONF_RACE_WEEK_START: "event_start"}
    )
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.motogp_race_week").state == STATE_OFF


async def test_race_week_turns_on_at_window_start(
    hass: HomeAssistant, mock_api: AiohttpClientMocker, freezer: FrozenDateTimeFactory
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, title="MotoGP", version=2, options={CONF_RACE_WEEK_START: "event_start"}
    )
    await _setup(hass, entry)
    assert hass.states.get("binary_sensor.motogp_race_week").state == STATE_OFF
    # Friday 6 November, midnight in the test time zone (US/Pacific).
    freezer.move_to("2026-11-06T08:00:01+00:00")
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.motogp_race_week").state == STATE_ON


async def test_live_timing_offline(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    await _setup(hass, config_entry)
    mock_api.clear_requests()
    mock_api.get(f"{PULSELIVE_BASE_URL}/timing-gateway/livetiming-lite", status=500)
    freezer.tick(timedelta(minutes=6))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.motogp_live_timing_online").state == STATE_OFF
    assert hass.states.get("sensor.motogp_leader").state == STATE_UNAVAILABLE


async def test_no_spoiler_freezes_spoiler_entities(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    await _setup(hass, config_entry)
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.motogp_no_spoiler_mode"}, blocking=True
    )
    assert hass.states.get("switch.motogp_no_spoiler_mode").state == STATE_ON

    # A new leader appears in the live timing.
    live = load_fixture("livetiming.json")
    for rider in live["rider"].values():
        rider["pos"] = {1: 2, 2: 1}.get(rider["pos"], rider["pos"])
    mock_api.clear_requests()
    mock_api.get(f"{PULSELIVE_BASE_URL}/timing-gateway/livetiming-lite", json=live)
    freezer.tick(timedelta(minutes=6))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.motogp_leader").state == "Marc Marquez"
    # Not a spoiler: still updated.
    assert hass.states.get("sensor.motogp_session_status").state == "finished"

    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.motogp_no_spoiler_mode"}, blocking=True
    )
    assert hass.states.get("sensor.motogp_leader").state != "Marc Marquez"


async def test_no_spoiler_restored_after_restart(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    hass_storage: dict,
) -> None:
    hass_storage["motogp_sensor_no_spoiler_v1"] = {
        "version": 1,
        "key": "motogp_sensor_no_spoiler_v1",
        "data": {"active": True},
    }
    await _setup(hass, config_entry)
    assert hass.states.get("switch.motogp_no_spoiler_mode").state == STATE_ON
    # Nothing to show without leaking the latest results.
    assert hass.states.get("sensor.motogp_last_race_results").state == STATE_UNAVAILABLE
    assert hass.states.get("sensor.motogp_next_race").state == "GRAND PRIX OF QATAR"


async def test_device_triggers(
    hass: HomeAssistant, mock_api: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    await _setup(hass, config_entry)
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, config_entry.entry_id)})
    triggers = await async_get_device_automations(hass, DeviceAutomationType.TRIGGER, device.id)
    types = {t["type"] for t in triggers if t["domain"] == DOMAIN}
    # v1 never offered the race week triggers (unique_id suffix mismatch).
    assert {
        "race_week_started",
        "race_week_ended",
        "session_red_flag",
        "live_timing_offline",
    } <= types


async def test_migrate_v1_entry(
    hass: HomeAssistant, mock_api: AiohttpClientMocker, entity_registry: er.EntityRegistry
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="MotoGP",
        version=1,
        data={
            "sensor_name": "Moto",
            "live_source": "official",
            "race_week_start_day": "saturday",
            "disabled_sensors": ["pit_stops", "calendar"],
        },
    )
    entry.add_to_hass(hass)
    for platform, suffix in (("sensor", "official_live_diagnostic"), ("select", "live_source")):
        entity_registry.async_get_or_create(
            platform, DOMAIN, f"{entry.entry_id}_{suffix}", config_entry=entry
        )
    leader = entity_registry.async_get_or_create(
        "sensor", DOMAIN, f"{entry.entry_id}_leader", config_entry=entry,
        suggested_object_id="motogp_leader",
    )  # fmt: skip

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.version == 2
    assert entry.title == "Moto"
    assert entry.options == {CONF_RACE_WEEK_START: "event_start"}
    assert entry.data == {CONF_LEGACY_DISABLED: ["pit_stops", "season_calendar"]}
    assert (
        entity_registry.async_get_entity_id("select", DOMAIN, f"{entry.entry_id}_live_source")
        is None
    )
    # Existing entities keep their entity_id.
    assert hass.states.get(leader.entity_id).state == "Marc Marquez"
    # Sensors disabled in v1 start disabled.
    pit = entity_registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_pit_stops")
    assert entity_registry.async_get(pit).disabled_by is er.RegistryEntryDisabler.INTEGRATION


async def test_calendar_events(
    hass: HomeAssistant, mock_api: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    await _setup(hass, config_entry)
    response = await hass.services.async_call(
        "calendar",
        "get_events",
        {
            "entity_id": "calendar.motogp_season_calendar",
            "start_date_time": "2026-11-05T00:00:00+00:00",
            "end_date_time": "2026-11-10T00:00:00+00:00",
        },
        blocking=True,
        return_response=True,
    )
    summaries = [e["summary"] for e in response["calendar.motogp_season_calendar"]["events"]]
    assert "Qatar Airways Grand Prix of Qatar" in summaries
    assert "QAT · Tissot Sprint" in summaries
    assert "QAT · Grand Prix" in summaries
    # The calendar state follows the next event: the GP itself (all-day).
    state = hass.states.get("calendar.motogp_season_calendar")
    assert state.attributes["message"] == "Qatar Airways Grand Prix of Qatar"


async def test_diagnostics(
    hass: HomeAssistant, mock_api: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    import json

    from custom_components.motogp_sensor.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    await _setup(hass, config_entry)
    diag = await async_get_config_entry_diagnostics(hass, config_entry)
    assert diag["schedule"]["last_update_success"] is True
    assert diag["results"]["data"]["last_race"]["event"]["short_name"] == "MAL"
    # Serialisable once dates are handled (freezegun's FakeDate trips orjson).
    json.dumps(diag, default=lambda value: value.isoformat())
