"""Typed data models for the MotoGP Sensor integration.

This module has no Home Assistant dependency so it can be unit tested alone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class Event:
    """A Grand Prix of the current season (test events are filtered out)."""

    id: str
    name: str
    short_name: str | None
    sponsored_name: str | None
    round: int
    date_start: date
    date_end: date
    status: str | None
    circuit_name: str | None
    circuit_place: str | None
    country_iso: str | None
    country_name: str | None


@dataclass(frozen=True, slots=True)
class Session:
    """A MotoGP class session (FP1, Practice, Q1, Sprint, Race, ...)."""

    id: str
    key: str  # canonical key, see parsers.SESSION_KEYS
    type: str  # raw API type ("FP", "PR", "Q", "SPR", "WUP", "RAC")
    number: int | None
    start: datetime | None  # timezone aware, UTC
    status: str | None
    condition: dict[str, Any] = field(default_factory=dict)

    @property
    def finished(self) -> bool:
        return (self.status or "").upper() == "FINISHED"


@dataclass(frozen=True, slots=True)
class ScheduleData:
    """Season calendar and the sessions of the event in focus."""

    season_id: str
    season_year: int | None
    category_id: str
    events: tuple[Event, ...]
    # Ongoing or next Grand Prix; None once the season is over.
    focus: Event | None
    focus_sessions: tuple[Session, ...]


@dataclass(frozen=True, slots=True)
class RiderStanding:
    position: int | None
    points: float
    race_wins: int
    podiums: int
    sprint_wins: int
    sprint_podiums: int
    rider_id: str | None
    name: str | None
    number: int | None
    country: str | None
    team: str | None
    constructor: str | None


@dataclass(frozen=True, slots=True)
class TeamStanding:
    position: int
    name: str
    points: float
    constructor: str | None = None
    riders: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ClassificationRow:
    position: int | None
    rider_name: str | None
    rider_number: int | None
    country: str | None
    team: str | None
    constructor: str | None
    time: str | None
    gap: str | None
    laps: int | None
    points: float
    status: str | None
    team_id: str | None = None


@dataclass(frozen=True, slots=True)
class RaceResult:
    event: Event
    session: Session
    rows: tuple[ClassificationRow, ...]


@dataclass(frozen=True, slots=True)
class ResultsData:
    riders: tuple[RiderStanding, ...]
    teams: tuple[TeamStanding, ...]
    constructors: tuple[TeamStanding, ...]
    last_race: RaceResult | None
    last_sprint: RaceResult | None
    rounds_completed: int


@dataclass(frozen=True, slots=True)
class LiveRider:
    number: str
    name: str | None
    short_name: str | None
    team: str | None
    bike: str | None
    nation: str | None
    color: str | None
    position: int | None
    gap_to_leader: str | None
    interval: str | None
    last_lap: str | None
    laps: int | None
    in_pit: bool
    status: str | None  # "CL" classified, "RT" retired, ...


@dataclass(frozen=True, slots=True)
class LiveTiming:
    event: str | None
    event_short_name: str | None
    circuit: str | None
    session_name: str | None
    session_type: str | None  # "FP1", "PR", "Q2", "SPR", "RAC", ...
    status: str | None  # key of const.SESSION_STATUS_MAP values
    total_laps: int | None
    remaining: str | None
    riders: tuple[LiveRider, ...]  # sorted by position, unclassified last

    @property
    def leader(self) -> LiveRider | None:
        return next((r for r in self.riders if r.position == 1), None)

    @property
    def current_lap(self) -> int | None:
        laps = [r.laps for r in self.riders if r.laps is not None]
        return max(laps) if laps else None


@dataclass(frozen=True, slots=True)
class WeatherData:
    circuit: str | None
    latitude: float
    longitude: float
    condition: str | None
    weather_code: int | None
    temperature: float | None
    humidity: float | None
    precipitation: float | None
    wind_speed: float | None
    wind_direction: float | None
    race_start: datetime | None
    race_temperature: float | None
    race_precipitation_probability: float | None
    race_wind_speed: float | None
    race_condition: str | None
    track_condition: str | None
    track_temperature: float | None
