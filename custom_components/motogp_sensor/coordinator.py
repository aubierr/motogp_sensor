"""Data update coordinators for the MotoGP Sensor integration."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta, tzinfo
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from . import parsers
from .api import MotoGPApiClient, MotoGPApiError
from .const import (
    DOMAIN,
    LIVE_ACTIVE_STATUSES,
    LIVE_INTERVAL_ACTIVE,
    LIVE_INTERVAL_IDLE,
    RESULTS_INTERVAL_IDLE,
    RESULTS_INTERVAL_RACE_WEEKEND,
    RESULTS_SETTLE_TIME,
    RETRY_INTERVAL,
    SCHEDULE_INTERVAL,
    WEATHER_INTERVAL,
)
from .models import (
    ClassificationRow,
    Event,
    LiveTiming,
    RaceResult,
    ResultsData,
    ScheduleData,
    Session,
    WeatherData,
)
from .no_spoiler import NoSpoilerManager

_LOGGER = logging.getLogger(__name__)

# Pulselive rate limit is 1000 requests/minute; stay polite on the first load.
_MAX_PARALLEL_REQUESTS = 4
# Open-Meteo hourly forecasts cover today + 15 days.
_FORECAST_HORIZON_DAYS = 15
# Refresh the schedule more often while a GP is on (session status, track).
_SCHEDULE_INTERVAL_EVENT = timedelta(minutes=30)


@dataclass(slots=True)
class MotoGPRuntimeData:
    """Objects shared by the platforms of a config entry."""

    schedule: ScheduleCoordinator
    results: ResultsCoordinator
    live: LiveCoordinator
    weather: WeatherCoordinator
    no_spoiler: NoSpoilerManager


type MotoGPConfigEntry = ConfigEntry[MotoGPRuntimeData]


class MotoGPCoordinator[DataT](DataUpdateCoordinator[DataT]):
    """Base coordinator: maps API errors and adapts the refresh interval."""

    config_entry: MotoGPConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: MotoGPConfigEntry,
        client: MotoGPApiClient,
        name: str,
        interval: timedelta,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {name}",
            update_interval=interval,
            # Data are frozen dataclasses: skip state writes when unchanged.
            always_update=False,
        )
        self.client = client

    async def _async_update_data(self) -> DataT:
        try:
            data = await self._fetch()
        except MotoGPApiError as err:
            self.update_interval = RETRY_INTERVAL
            raise UpdateFailed(str(err)) from err
        self.update_interval = self._next_interval(data)
        return data

    async def _fetch(self) -> DataT:
        raise NotImplementedError

    def _next_interval(self, data: DataT) -> timedelta:
        raise NotImplementedError


_unknown_circuits: set[str] = set()


async def _circuit_tz(event: Event) -> tzinfo | None:
    """Return the circuit time zone, needed to read session times."""
    if (name := parsers.circuit_time_zone(event)) is None:
        if event.short_name not in _unknown_circuits:
            _unknown_circuits.add(event.short_name or "")
            _LOGGER.warning(
                "Unknown circuit %s: its session times are assumed to be UTC", event.short_name
            )
        return None
    return await dt_util.async_get_time_zone(name)


def _event_days(event: Event | None, now: datetime, extra_days: int = 0) -> bool:
    """Return True between the first day and the last day (+extra) of a GP."""
    if event is None:
        return False
    today = now.date()
    return event.date_start <= today <= event.date_end + timedelta(days=extra_days)


class ScheduleCoordinator(MotoGPCoordinator[ScheduleData]):
    """Current season, its Grands Prix and the sessions of the next one."""

    def __init__(
        self, hass: HomeAssistant, entry: MotoGPConfigEntry, client: MotoGPApiClient
    ) -> None:
        super().__init__(hass, entry, client, "schedule", SCHEDULE_INTERVAL)

    async def _fetch(self) -> ScheduleData:
        season = parsers.find_current_season(await self.client.seasons())
        if season is None:
            raise MotoGPApiError("No current MotoGP season found")
        season_id, season_year = season
        category_id = parsers.find_category_id(await self.client.categories(season_id))
        if category_id is None:
            raise MotoGPApiError(f"No MotoGP category in season {season_year}")
        events = parsers.parse_events(await self.client.events(season_id))
        focus = parsers.find_focus_event(events, dt_util.now().date())
        sessions: tuple[Session, ...] = ()
        if focus is not None:
            sessions = parsers.parse_sessions(
                await self.client.sessions(focus.id, category_id), await _circuit_tz(focus)
            )
        return ScheduleData(
            season_id=season_id,
            season_year=season_year,
            category_id=category_id,
            events=events,
            focus=focus,
            focus_sessions=sessions,
        )

    def _next_interval(self, data: ScheduleData) -> timedelta:
        now = dt_util.now()
        if data.focus is None:
            return SCHEDULE_INTERVAL
        if _event_days(data.focus, now):
            return _SCHEDULE_INTERVAL_EVENT
        # Refresh right after the focus GP ends so the next one takes over.
        rollover = (
            datetime.combine(data.focus.date_end + timedelta(days=1), time.min, now.tzinfo) - now
        )
        return max(timedelta(minutes=1), min(SCHEDULE_INTERVAL, rollover))


class ResultsCoordinator(MotoGPCoordinator[ResultsData]):
    """Rider standings, computed team/constructor standings, last results.

    Pulselive only publishes the rider championship, so the team and
    constructor championships are computed from every Race and Sprint
    classification of the season. Settled sessions are cached, so after the
    first load only the latest sessions are fetched.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: MotoGPConfigEntry,
        client: MotoGPApiClient,
        schedule: ScheduleCoordinator,
    ) -> None:
        super().__init__(hass, entry, client, "results", RESULTS_INTERVAL_IDLE)
        self._schedule = schedule
        self._sessions_cache: dict[str, tuple[Session, ...]] = {}
        self._classification_cache: dict[str, tuple[ClassificationRow, ...]] = {}
        self._semaphore = asyncio.Semaphore(_MAX_PARALLEL_REQUESTS)

    async def _limited[T](self, call: Awaitable[T]) -> T:
        async with self._semaphore:
            return await call

    async def _event_sessions(
        self, event: Event, category_id: str, now: datetime
    ) -> tuple[Session, ...]:
        if (cached := self._sessions_cache.get(event.id)) is not None:
            return cached
        sessions = parsers.parse_sessions(
            await self._limited(self.client.sessions(event.id, category_id)),
            await _circuit_tz(event),
        )
        if _settled(sessions, now):
            self._sessions_cache[event.id] = sessions
        return sessions

    async def _classification(
        self, session: Session, now: datetime
    ) -> tuple[ClassificationRow, ...]:
        if (cached := self._classification_cache.get(session.id)) is not None:
            return cached
        rows = parsers.parse_classification(
            await self._limited(self.client.classification(session.id))
        )
        if _settled((session,), now):
            self._classification_cache[session.id] = rows
        return rows

    async def _fetch(self) -> ResultsData:
        schedule = self._schedule.data
        if schedule is None:
            raise MotoGPApiError("Season schedule not available yet")
        now = dt_util.utcnow()
        events = parsers.completed_events(schedule.events, dt_util.now().date())

        standings_raw, *event_sessions = await asyncio.gather(
            self.client.standings(schedule.season_id, schedule.category_id),
            *(self._event_sessions(ev, schedule.category_id, now) for ev in events),
        )
        scoring: list[tuple[Event, Session]] = [
            (event, session)
            for event, sessions in zip(events, event_sessions, strict=True)
            for session in sessions
            if session.key in ("race", "sprint") and session.finished
        ]
        classifications = await asyncio.gather(
            *(self._classification(session, now) for _, session in scoring)
        )
        results = [
            RaceResult(event=event, session=session, rows=rows)
            for (event, session), rows in zip(scoring, classifications, strict=True)
            if rows
        ]
        return ResultsData(
            riders=parsers.parse_rider_standings(standings_raw),
            teams=parsers.compute_team_standings(r.rows for r in results),
            constructors=parsers.compute_constructor_standings(r.rows for r in results),
            last_race=_latest(r for r in results if r.session.key == "race"),
            last_sprint=_latest(r for r in results if r.session.key == "sprint"),
            rounds_completed=sum(1 for r in results if r.session.key == "race"),
        )

    def _next_interval(self, data: ResultsData) -> timedelta:
        # From the first day of a GP to the day after it (late penalties).
        schedule = self._schedule.data
        now = dt_util.now()
        if schedule and any(_event_days(ev, now, extra_days=1) for ev in schedule.events):
            return RESULTS_INTERVAL_RACE_WEEKEND
        return RESULTS_INTERVAL_IDLE


def _settled(sessions: Iterable[Session], now: datetime) -> bool:
    """Return True when every session is finished and old enough to be final."""
    sessions = tuple(sessions)
    return bool(sessions) and all(
        s.finished and s.start is not None and now - s.start > RESULTS_SETTLE_TIME for s in sessions
    )


def _latest(results: Iterable[RaceResult]) -> RaceResult | None:
    oldest = datetime.min.replace(tzinfo=UTC)
    return max(results, key=lambda r: r.session.start or oldest, default=None)


class LiveCoordinator(MotoGPCoordinator[LiveTiming | None]):
    """Pulselive live timing, polled fast only around sessions."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: MotoGPConfigEntry,
        client: MotoGPApiClient,
        schedule: ScheduleCoordinator,
    ) -> None:
        super().__init__(hass, entry, client, "live timing", LIVE_INTERVAL_IDLE)
        self._schedule = schedule

    async def _fetch(self) -> LiveTiming | None:
        return parsers.parse_live_timing(await self.client.live_timing())

    def _next_interval(self, data: LiveTiming | None) -> timedelta:
        if data is not None and data.status in LIVE_ACTIVE_STATUSES:
            return LIVE_INTERVAL_ACTIVE
        schedule = self._schedule.data
        if schedule and parsers.in_session_window(schedule.focus_sessions, dt_util.utcnow()):
            return LIVE_INTERVAL_ACTIVE
        return LIVE_INTERVAL_IDLE


class WeatherCoordinator(MotoGPCoordinator[WeatherData | None]):
    """Open-Meteo weather at the circuit of the ongoing or next GP."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: MotoGPConfigEntry,
        client: MotoGPApiClient,
        schedule: ScheduleCoordinator,
    ) -> None:
        super().__init__(hass, entry, client, "weather", WEATHER_INTERVAL)
        self._schedule = schedule

    async def _fetch(self) -> WeatherData | None:
        schedule = self._schedule.data
        event = schedule.focus if schedule else None
        if schedule is None or event is None:
            return None
        coords = parsers.circuit_coordinates(event)
        if coords is None:
            _LOGGER.debug("No coordinates known for circuit %s", event.short_name)
            return None

        race = parsers.find_session(schedule.focus_sessions, "race")
        race_start = race.start if race else None
        race_day = race_start.date() if race_start else None
        days_ahead = (race_day - dt_util.utcnow().date()).days if race_day else -1
        if not 0 <= days_ahead <= _FORECAST_HORIZON_DAYS:
            race_day = race_start = None

        raw = await self.client.forecast(coords[0], coords[1], race_day)
        return parsers.parse_weather(raw, event, coords, race_start, schedule.focus_sessions)

    def _next_interval(self, data: WeatherData | None) -> timedelta:
        return WEATHER_INTERVAL
