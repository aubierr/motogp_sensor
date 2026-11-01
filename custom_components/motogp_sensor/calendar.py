"""Calendar platform: every Grand Prix, plus the sessions of the next one."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import MotoGPConfigEntry, ScheduleCoordinator
from .entity import MotoGPEntity
from .models import Event, ScheduleData, Session

PARALLEL_UPDATES = 0

# Calendar summaries are free text, so session names are in English.
_SESSION_NAMES = {
    "fp1": "Free Practice 1",
    "practice": "Practice",
    "fp2": "Free Practice 2",
    "q1": "Qualifying 1",
    "q2": "Qualifying 2",
    "sprint": "Tissot Sprint",
    "warm_up": "Warm Up",
    "race": "Grand Prix",
}
# The API only gives start times; these typical durations give an end time.
_SESSION_DURATIONS = {
    "fp1": timedelta(minutes=45),
    "practice": timedelta(hours=1),
    "fp2": timedelta(minutes=30),
    "q1": timedelta(minutes=15),
    "q2": timedelta(minutes=15),
    "sprint": timedelta(minutes=30),
    "warm_up": timedelta(minutes=10),
    "race": timedelta(minutes=45),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MotoGPConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([MotoGPSeasonCalendar(entry.runtime_data.schedule)])


def _gp_event(event: Event, season_year: int | None) -> CalendarEvent:
    location = ", ".join(p for p in (event.circuit_name, event.country_name) if p)
    return CalendarEvent(
        start=event.date_start,
        end=event.date_end + timedelta(days=1),  # exclusive end
        summary=event.sponsored_name or event.name,
        location=location or None,
        description=f"MotoGP {season_year} · Round {event.round}"
        if season_year
        else f"Round {event.round}",
        uid=event.id,
    )


def _session_event(session: Session, event: Event) -> CalendarEvent | None:
    if session.start is None:
        return None
    name = _SESSION_NAMES.get(session.key, session.key.upper())
    return CalendarEvent(
        start=session.start,
        end=session.start + _SESSION_DURATIONS.get(session.key, timedelta(minutes=45)),
        summary=f"{event.short_name or event.name} · {name}",
        location=event.circuit_name,
        description=f"{event.name} - {name} (end time estimated)",
        uid=session.id,
    )


def _all_events(data: ScheduleData) -> list[CalendarEvent]:
    items = [_gp_event(ev, data.season_year) for ev in data.events]
    if data.focus is not None:
        items += [
            item for s in data.focus_sessions if (item := _session_event(s, data.focus)) is not None
        ]
    return sorted(items, key=lambda e: e.start_datetime_local)


def _as_datetime(value: date | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    return dt_util.start_of_local_day(value)


class MotoGPSeasonCalendar(MotoGPEntity[ScheduleCoordinator], CalendarEntity):
    """All Grands Prix of the season as all-day events."""

    def __init__(self, coordinator: ScheduleCoordinator) -> None:
        super().__init__(coordinator, "season_calendar")

    @property
    def event(self) -> CalendarEvent | None:
        """Return the ongoing or next event."""
        if (data := self.data) is None:
            return None
        now = dt_util.now()
        return next((e for e in _all_events(data) if _as_datetime(e.end) > now), None)

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        if (data := self.data) is None:
            return []
        return [
            e
            for e in _all_events(data)
            if _as_datetime(e.start) < end_date and _as_datetime(e.end) > start_date
        ]
