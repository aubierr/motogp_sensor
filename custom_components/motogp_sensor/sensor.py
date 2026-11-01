"""Sensor platform for the MotoGP Sensor integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.util import dt as dt_util

from .const import SESSION_STATUS_OPTIONS
from .coordinator import MotoGPConfigEntry, MotoGPCoordinator
from .entity import MotoGPEntity
from .models import (
    ClassificationRow,
    Event,
    LiveRider,
    LiveTiming,
    RaceResult,
    ResultsData,
    ScheduleData,
    TeamStanding,
    WeatherData,
)
from .parsers import WEATHER_CONDITIONS, fastest_last_lap, next_session, number

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class MotoGPSensorDescription(SensorEntityDescription):
    """Describe a MotoGP sensor; callables receive non-None coordinator data."""

    coordinator: str  # attribute of MotoGPRuntimeData
    value_fn: Callable[[Any, datetime], StateType | datetime]
    attrs_fn: Callable[[Any, datetime], dict[str, Any] | None] = lambda _data, _now: None
    next_update_fn: Callable[[Any, datetime], datetime | None] | None = None
    spoiler: bool = False


# ── Attribute helpers ─────────────────────────────────────────────────────────


def _event_attrs(event: Event) -> dict[str, Any]:
    return {
        "round": event.round,
        "race_name": event.name,
        "sponsored_name": event.sponsored_name,
        "short_name": event.short_name,
        "circuit": event.circuit_name,
        "circuit_locality": event.circuit_place,
        "country": event.country_name,
        "country_code": event.country_iso,
        "date_start": event.date_start.isoformat(),
        "date_end": event.date_end.isoformat(),
    }


def _next_race_attrs(data: ScheduleData, _now: datetime) -> dict[str, Any] | None:
    if data.focus is None:
        return None
    attrs = _event_attrs(data.focus) | {"season": data.season_year}
    for session in data.focus_sessions:
        attrs[f"{session.key}_start"] = session.start.isoformat() if session.start else None
    attrs["sessions"] = [
        {
            "session": s.key,
            "start": s.start.isoformat() if s.start else None,
            "status": s.status,
        }
        for s in data.focus_sessions
    ]
    return attrs


def _next_session_attrs(data: ScheduleData, now: datetime) -> dict[str, Any] | None:
    session = next_session(data.focus_sessions, now)
    if session is None or data.focus is None:
        return None
    return {"session": session.key, "event": data.focus.name, "round": data.focus.round}


def _next_session_start(data: ScheduleData, now: datetime) -> datetime | None:
    session = next_session(data.focus_sessions, now)
    return session.start if session else None


def _standings_attrs(rows: tuple[TeamStanding, ...]) -> list[dict[str, Any]]:
    return [
        {
            "position": row.position,
            "name": row.name,
            "points": number(row.points),
            **({"constructor": row.constructor, "riders": list(row.riders)} if row.riders else {}),
        }
        for row in rows
    ]


def _rider_standings_attrs(data: ResultsData, _now: datetime) -> dict[str, Any]:
    return {
        "round": data.rounds_completed,
        "standings": [
            {
                "position": r.position,
                "name": r.name,
                "number": r.number,
                "country": r.country,
                "team": r.team,
                "constructor": r.constructor,
                "points": number(r.points),
                "race_wins": r.race_wins,
                "podiums": r.podiums,
                "sprint_wins": r.sprint_wins,
                "sprint_podiums": r.sprint_podiums,
            }
            for r in data.riders
        ],
    }


def _row_attrs(row: ClassificationRow) -> dict[str, Any]:
    return {
        "position": row.position,
        "rider_name": row.rider_name,
        "rider_number": row.rider_number,
        "country": row.country,
        "team": row.team,
        "constructor": row.constructor,
        "time": row.time,
        "gap": row.gap,
        "laps": row.laps,
        "points": number(row.points),
        "status": row.status,
    }


def _result_attrs(result: RaceResult | None) -> dict[str, Any] | None:
    if result is None:
        return None
    winner = next((r for r in result.rows if r.position == 1), None)
    return {
        "round": result.event.round,
        "circuit": result.event.circuit_name,
        "date": result.event.date_end.isoformat(),
        "session_start": result.session.start.isoformat() if result.session.start else None,
        "winner": winner.rider_name if winner else None,
        "results": [_row_attrs(row) for row in result.rows],
    }


def _live_rider_attrs(rider: LiveRider) -> dict[str, Any]:
    return {
        "position": rider.position,
        "number": rider.number,
        "name": rider.name,
        "short_name": rider.short_name,
        "team": rider.team,
        "bike": rider.bike,
        "nation": rider.nation,
        "gap_to_leader": rider.gap_to_leader,
        "interval": rider.interval,
        "last_lap": rider.last_lap,
        "laps": rider.laps,
        "in_pit": rider.in_pit,
        "status": rider.status,
    }


_IDENTITY_KEYS = frozenset({"number", "name", "short_name", "team", "bike", "nation"})


def _rider_list_attrs(data: LiveTiming, _now: datetime) -> dict[str, Any]:
    by_number = sorted(data.riders, key=lambda r: int(r.number) if r.number.isdigit() else 999)
    return {
        "riders": [
            {k: v for k, v in _live_rider_attrs(r).items() if k in _IDENTITY_KEYS}
            for r in by_number
        ]
    }


def _live_session_attrs(data: LiveTiming) -> dict[str, Any]:
    return {
        "session_name": data.session_name,
        "session_type": data.session_type,
        "event": data.event,
        "circuit": data.circuit,
        "total_laps": data.total_laps,
        "status": data.status,
    }


def _top_three_attrs(data: LiveTiming, _now: datetime) -> dict[str, Any]:
    podium = [r for r in data.riders if r.position in (1, 2, 3)]
    return {f"p{r.position}": _live_rider_attrs(r) for r in podium}


def _leader_name(data: LiveTiming, _now: datetime) -> str | None:
    leader = data.leader
    return (leader.name or leader.short_name) if leader else None


def _fastest_lap_attrs(data: LiveTiming, _now: datetime) -> dict[str, Any]:
    rider = fastest_last_lap(data.riders)
    return {
        "rider_name": rider.name if rider else None,
        "rider_number": rider.number if rider else None,
        "approximate": True,
    }


def _weather_attrs(data: WeatherData, _now: datetime) -> dict[str, Any]:
    return {
        "circuit": data.circuit,
        "latitude": data.latitude,
        "longitude": data.longitude,
        "temperature": data.temperature,
        "humidity": data.humidity,
        "precipitation": data.precipitation,
        "wind_speed": data.wind_speed,
        "wind_direction": data.wind_direction,
        "weather_code": data.weather_code,
        "race_start": data.race_start.isoformat() if data.race_start else None,
        "race_condition": data.race_condition,
        "race_temperature": data.race_temperature,
        "race_precipitation_probability": data.race_precipitation_probability,
        "race_wind_speed": data.race_wind_speed,
        "track_condition": data.track_condition,
        "track_temperature": data.track_temperature,
    }


# ── Descriptions ──────────────────────────────────────────────────────────────

SENSORS: tuple[MotoGPSensorDescription, ...] = (
    # Schedule
    MotoGPSensorDescription(
        key="next_race",
        coordinator="schedule",
        value_fn=lambda d, _: d.focus.name if d.focus else None,
        attrs_fn=_next_race_attrs,
    ),
    MotoGPSensorDescription(
        key="next_session",
        coordinator="schedule",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_next_session_start,
        attrs_fn=_next_session_attrs,
        next_update_fn=_next_session_start,
    ),
    MotoGPSensorDescription(
        key="current_season",
        coordinator="schedule",
        value_fn=lambda d, _: d.season_year,
        attrs_fn=lambda d, _: {"season_id": d.season_id, "total_events": len(d.events)},
    ),
    # Results
    MotoGPSensorDescription(
        key="rider_standings",
        coordinator="results",
        spoiler=True,
        value_fn=lambda d, _: d.riders[0].name if d.riders else None,
        attrs_fn=_rider_standings_attrs,
    ),
    MotoGPSensorDescription(
        key="team_standings",
        coordinator="results",
        spoiler=True,
        value_fn=lambda d, _: d.teams[0].name if d.teams else None,
        attrs_fn=lambda d, _: {"standings": _standings_attrs(d.teams)},
    ),
    MotoGPSensorDescription(
        key="constructor_standings",
        coordinator="results",
        spoiler=True,
        value_fn=lambda d, _: d.constructors[0].name if d.constructors else None,
        attrs_fn=lambda d, _: {"standings": _standings_attrs(d.constructors)},
    ),
    MotoGPSensorDescription(
        key="last_race_results",
        coordinator="results",
        spoiler=True,
        value_fn=lambda d, _: d.last_race.event.name if d.last_race else None,
        attrs_fn=lambda d, _: _result_attrs(d.last_race),
    ),
    MotoGPSensorDescription(
        key="last_sprint_results",
        coordinator="results",
        spoiler=True,
        value_fn=lambda d, _: d.last_sprint.event.name if d.last_sprint else None,
        attrs_fn=lambda d, _: _result_attrs(d.last_sprint),
    ),
    # Live timing
    MotoGPSensorDescription(
        key="session_status",
        coordinator="live",
        device_class=SensorDeviceClass.ENUM,
        options=SESSION_STATUS_OPTIONS,
        value_fn=lambda d, _: d.status,
        attrs_fn=lambda d, _: _live_session_attrs(d),
    ),
    MotoGPSensorDescription(
        key="current_session",
        coordinator="live",
        value_fn=lambda d, _: d.session_type,
        attrs_fn=lambda d, _: _live_session_attrs(d),
    ),
    MotoGPSensorDescription(
        key="race_lap_count",
        coordinator="live",
        value_fn=lambda d, _: d.current_lap,
        attrs_fn=lambda d, _: {"total_laps": d.total_laps},
    ),
    MotoGPSensorDescription(
        key="session_time_remaining",
        coordinator="live",
        value_fn=lambda d, _: d.remaining,
    ),
    MotoGPSensorDescription(
        key="rider_list",
        coordinator="live",
        value_fn=lambda d, _: len(d.riders),
        attrs_fn=_rider_list_attrs,
    ),
    MotoGPSensorDescription(
        key="rider_positions",
        coordinator="live",
        spoiler=True,
        value_fn=lambda d, _: len(d.riders),
        attrs_fn=lambda d, _: {"positions": [_live_rider_attrs(r) for r in d.riders]},
    ),
    MotoGPSensorDescription(
        key="top_three",
        coordinator="live",
        spoiler=True,
        value_fn=_leader_name,
        attrs_fn=_top_three_attrs,
    ),
    MotoGPSensorDescription(
        key="leader",
        coordinator="live",
        spoiler=True,
        value_fn=_leader_name,
        attrs_fn=lambda d, _: _live_rider_attrs(d.leader) if d.leader else None,
    ),
    MotoGPSensorDescription(
        key="fastest_lap",
        coordinator="live",
        spoiler=True,
        value_fn=lambda d, _: r.last_lap if (r := fastest_last_lap(d.riders)) else None,
        attrs_fn=_fastest_lap_attrs,
    ),
    MotoGPSensorDescription(
        key="pit_stops",
        coordinator="live",
        spoiler=True,
        value_fn=lambda d, _: sum(1 for r in d.riders if r.in_pit),
        attrs_fn=lambda d, _: {
            "riders_in_pit": [_live_rider_attrs(r) for r in d.riders if r.in_pit]
        },
    ),
    # Weather
    MotoGPSensorDescription(
        key="track_weather",
        coordinator="weather",
        device_class=SensorDeviceClass.ENUM,
        options=WEATHER_CONDITIONS,
        value_fn=lambda d, _: d.condition,
        attrs_fn=_weather_attrs,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MotoGPConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = entry.runtime_data
    async_add_entities(
        MotoGPSensor(getattr(runtime, description.coordinator), description)
        for description in SENSORS
    )


class MotoGPSensor(MotoGPEntity[MotoGPCoordinator[Any]], SensorEntity):
    """A MotoGP sensor defined by a MotoGPSensorDescription."""

    entity_description: MotoGPSensorDescription
    # Large lists: keep them out of the recorder database.
    _unrecorded_attributes = frozenset(
        {"standings", "results", "riders", "positions", "riders_in_pit", "sessions"}
    )

    def __init__(
        self, coordinator: MotoGPCoordinator[Any], description: MotoGPSensorDescription
    ) -> None:
        self.entity_description = description
        self._spoiler = description.spoiler
        super().__init__(coordinator, description.key)

    @property
    def native_value(self) -> StateType | datetime:
        if (data := self.data) is None:
            return None
        return self.entity_description.value_fn(data, dt_util.utcnow())

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if (data := self.data) is None:
            return None
        return self.entity_description.attrs_fn(data, dt_util.utcnow())

    def _next_time_update(self) -> datetime | None:
        fn = self.entity_description.next_update_fn
        if fn is None or (data := self.data) is None:
            return None
        return fn(data, dt_util.utcnow())
