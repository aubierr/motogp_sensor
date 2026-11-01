"""Pure functions turning Pulselive / Open-Meteo payloads into models.

Nothing in here talks to the network or to Home Assistant: every function
takes the raw JSON (and the current time when it matters) and returns models,
which keeps the parsing logic easy to unit test against real API fixtures.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, date, datetime, time, timedelta, tzinfo
import re
from typing import Any

from .const import (
    LIVE_WAKE_AFTER,
    LIVE_WAKE_BEFORE,
    MOTOGP_CATEGORY_PREFIX,
    RACE_WEEK_GRACE,
    RACE_WEEK_START_EVENT,
    RACE_WEEK_START_SUNDAY,
    SESSION_STATUS_MAP,
)
from .models import (
    ClassificationRow,
    Event,
    LiveRider,
    LiveTiming,
    RiderStanding,
    Session,
    TeamStanding,
    WeatherData,
)

# ── Primitive helpers ─────────────────────────────────────────────────────────


def _str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _list(raw: Any, *keys: str) -> list[dict[str, Any]]:
    """Return the list of dicts in ``raw`` or under the first matching key."""
    if isinstance(raw, dict):
        raw = next((raw[k] for k in keys if isinstance(raw.get(k), list)), [])
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _datetime(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).strip())
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def number(value: float) -> int | float:
    """Return whole numbers as int so 25.0 is shown as 25 but 12.5 stays."""
    return int(value) if float(value).is_integer() else value


# ── Season / category ─────────────────────────────────────────────────────────


def find_current_season(raw: Any) -> tuple[str, int | None] | None:
    """Return (uuid, year) of the current season."""
    seasons = [s for s in _list(raw, "seasons", "items") if _str(s.get("id"))]
    if not seasons:
        return None
    season = next(
        (s for s in seasons if s.get("current") is True),
        max(seasons, key=lambda s: _int(s.get("year")) or 0),
    )
    return str(season["id"]), _int(season.get("year"))


def find_category_id(raw: Any) -> str | None:
    """Return the uuid of the MotoGP class (not Moto2/Moto3)."""
    for category in _list(raw, "categories", "items"):
        name = (_str(category.get("name")) or "").lower()
        if name.startswith(MOTOGP_CATEGORY_PREFIX) and _str(category.get("id")):
            return str(category["id"])
    return None


# ── Events ────────────────────────────────────────────────────────────────────


def parse_events(raw: Any) -> tuple[Event, ...]:
    """Return the Grands Prix sorted by date, rounds numbered in that order.

    Test events are dropped. The round is the position in the calendar, not
    the legacy ``eventId`` which keeps its original value when a GP moves.
    """
    candidates: list[tuple[date, date, dict[str, Any]]] = []
    for item in _list(raw, "events", "items"):
        if item.get("test") is True or not _str(item.get("id")):
            continue
        start, end = _date(item.get("date_start")), _date(item.get("date_end"))
        if start is None or end is None:
            continue
        candidates.append((start, end, item))
    candidates.sort(key=lambda c: c[0])

    events: list[Event] = []
    for index, (start, end, item) in enumerate(candidates, start=1):
        circuit = item.get("circuit") if isinstance(item.get("circuit"), dict) else {}
        country = item.get("country") if isinstance(item.get("country"), dict) else {}
        events.append(
            Event(
                id=str(item["id"]),
                name=_str(item.get("name")) or _str(item.get("sponsored_name")) or "",
                short_name=_str(item.get("short_name")),
                sponsored_name=_str(item.get("sponsored_name")),
                round=index,
                date_start=start,
                date_end=end,
                status=_str(item.get("status")),
                circuit_name=_str(circuit.get("name")),
                circuit_place=_str(circuit.get("place")),
                country_iso=_str(country.get("iso")),
                country_name=_str(country.get("name")),
            )
        )
    return tuple(events)


def find_focus_event(events: Iterable[Event], today: date) -> Event | None:
    """Return the ongoing Grand Prix, or the next one."""
    return next((ev for ev in events if ev.date_end >= today), None)


def completed_events(events: Iterable[Event], today: date) -> list[Event]:
    """Return the Grands Prix that have at least started."""
    return [ev for ev in events if ev.date_start <= today]


# ── Sessions ──────────────────────────────────────────────────────────────────

# Canonical session keys in weekend order.
SESSION_KEYS: tuple[str, ...] = (
    "fp1",
    "practice",
    "fp2",
    "q1",
    "q2",
    "sprint",
    "warm_up",
    "race",
)
_SESSION_TYPE_KEYS = {"PR": "practice", "SPR": "sprint", "WUP": "warm_up", "RAC": "race"}


def session_key(session_type: str, session_number: int | None) -> str:
    stype = session_type.upper()
    if stype in _SESSION_TYPE_KEYS:
        return _SESSION_TYPE_KEYS[stype]
    if stype in ("FP", "Q") and session_number is not None:
        return f"{stype.lower()}{session_number}"
    return f"{stype.lower()}{session_number or ''}"


def parse_sessions(raw: Any) -> tuple[Session, ...]:
    """Return the sessions of an event sorted by start time."""
    sessions: list[Session] = []
    for item in _list(raw, "sessions", "items"):
        session_id, stype = _str(item.get("id")), _str(item.get("type"))
        if not session_id or not stype:
            continue
        num = _int(item.get("number"))
        condition = item.get("condition") if isinstance(item.get("condition"), dict) else {}
        sessions.append(
            Session(
                id=session_id,
                key=session_key(stype, num),
                type=stype.upper(),
                number=num,
                start=_datetime(item.get("date")),
                status=_str(item.get("status")),
                condition=dict(condition),
            )
        )
    far_future = datetime.max.replace(tzinfo=UTC)
    return tuple(sorted(sessions, key=lambda s: s.start or far_future))


def find_session(sessions: Iterable[Session], key: str) -> Session | None:
    return next((s for s in sessions if s.key == key), None)


def next_session(sessions: Iterable[Session], now: datetime) -> Session | None:
    """Return the next session that has not started yet."""
    return next((s for s in sessions if s.start and s.start > now), None)


def in_session_window(sessions: Iterable[Session], now: datetime) -> bool:
    """Return True around the scheduled start of any session."""
    return any(
        s.start - LIVE_WAKE_BEFORE <= now <= s.start + LIVE_WAKE_AFTER
        for s in sessions
        if s.start is not None
    )


def race_week_window(
    event: Event,
    sessions: Iterable[Session],
    start_option: str,
    tz: tzinfo,
) -> tuple[datetime, datetime]:
    """Return the [start, end) window during which the race week is on."""
    if start_option == RACE_WEEK_START_EVENT:
        first_day = event.date_start
    else:
        first_day = event.date_start - timedelta(days=event.date_start.weekday())
        if start_option == RACE_WEEK_START_SUNDAY:
            first_day -= timedelta(days=1)
    start = datetime.combine(first_day, time.min, tz)
    end = datetime.combine(event.date_end + timedelta(days=1), time.min, tz)
    race = find_session(sessions, "race")
    if race is not None and race.start is not None:
        end = max(end, race.start + RACE_WEEK_GRACE)
    return start, end


# ── Standings and classifications ─────────────────────────────────────────────


def _rider_fields(item: dict[str, Any]) -> tuple[str | None, str | None, int | None, str | None]:
    rider = item.get("rider") if isinstance(item.get("rider"), dict) else {}
    country = rider.get("country") if isinstance(rider.get("country"), dict) else {}
    name = _str(rider.get("full_name")) or _str(
        " ".join(p for p in (_str(rider.get("name")), _str(rider.get("surname"))) if p)
    )
    return _str(rider.get("id")), name, _int(rider.get("number")), _str(country.get("iso"))


def _named(item: dict[str, Any], key: str) -> str | None:
    value = item.get(key)
    return _str(value.get("name")) if isinstance(value, dict) else _str(value)


def parse_rider_standings(raw: Any) -> tuple[RiderStanding, ...]:
    rows: list[RiderStanding] = []
    for item in _list(raw, "classification", "standings", "items"):
        rider_id, name, num, country = _rider_fields(item)
        rows.append(
            RiderStanding(
                position=_int(item.get("position")),
                points=_float(item.get("points")) or 0.0,
                race_wins=_int(item.get("race_wins")) or 0,
                podiums=_int(item.get("podiums")) or 0,
                sprint_wins=_int(item.get("sprint_wins")) or 0,
                sprint_podiums=_int(item.get("sprint_podiums")) or 0,
                rider_id=rider_id,
                name=name,
                number=num,
                country=country,
                team=_named(item, "team"),
                constructor=_named(item, "constructor"),
            )
        )
    return tuple(sorted(rows, key=lambda r: (r.position is None, r.position or 0)))


def parse_classification(raw: Any) -> tuple[ClassificationRow, ...]:
    rows: list[ClassificationRow] = []
    for item in _list(raw, "classification", "results", "items"):
        _, name, num, country = _rider_fields(item)
        gap = item.get("gap")
        team = item.get("team") if isinstance(item.get("team"), dict) else {}
        rows.append(
            ClassificationRow(
                position=_int(item.get("position")),
                rider_name=name,
                rider_number=num,
                country=country,
                team=_named(item, "team"),
                constructor=_named(item, "constructor"),
                time=_str(item.get("time")),
                gap=_str(gap.get("first")) if isinstance(gap, dict) else _str(gap),
                laps=_int(item.get("total_laps")),
                points=_float(item.get("points")) or 0.0,
                status=_str(item.get("status")),
                team_id=_str(team.get("id")),
            )
        )
    return tuple(sorted(rows, key=lambda r: (r.position is None, r.position or 0)))


def _ranked(totals: dict[str, float], extra: dict[str, dict[str, Any]]) -> tuple[TeamStanding, ...]:
    ordered = sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))
    return tuple(
        TeamStanding(position=pos, name=name, points=points, **extra.get(name, {}))
        for pos, (name, points) in enumerate(ordered, start=1)
    )


def compute_team_standings(
    classifications: Iterable[Iterable[ClassificationRow]],
) -> tuple[TeamStanding, ...]:
    """Team championship: every point scored by the team's riders.

    Teams are matched by id and shown under their latest name, as sponsors
    rename teams during the season. ``classifications`` must be chronological.
    """
    rows = [row for session in classifications for row in session if row.team]
    latest_name = {row.team_id or row.team: row.team for row in rows}
    totals: dict[str, float] = defaultdict(float)
    riders: dict[str, dict[str, None]] = defaultdict(dict)
    constructors: dict[str, str | None] = {}
    for row in rows:
        team = latest_name[row.team_id or row.team]
        totals[team] += row.points
        constructors[team] = row.constructor
        if row.rider_name:
            riders[team][row.rider_name] = None
    extra = {
        team: {"constructor": constructors.get(team), "riders": tuple(riders[team])}
        for team in totals
    }
    return _ranked(totals, extra)


def compute_constructor_standings(
    classifications: Iterable[Iterable[ClassificationRow]],
) -> tuple[TeamStanding, ...]:
    """Constructor championship: best placed rider of each make, per race."""
    totals: dict[str, float] = defaultdict(float)
    for rows in classifications:
        best: dict[str, float] = {}
        for row in rows:
            if row.constructor:
                best[row.constructor] = max(best.get(row.constructor, 0.0), row.points)
        for constructor, points in best.items():
            totals[constructor] += points
    return _ranked(totals, {})


# ── Live timing ───────────────────────────────────────────────────────────────


def parse_live_timing(raw: Any) -> LiveTiming | None:
    """Normalise a ``livetiming-lite`` payload; None when it is not one."""
    if not isinstance(raw, dict) or not isinstance(raw.get("head"), dict):
        return None
    head: dict[str, Any] = raw["head"]
    riders_raw = raw.get("rider") if isinstance(raw.get("rider"), dict) else {}

    riders: list[LiveRider] = []
    for key, item in riders_raw.items():
        if not isinstance(item, dict):
            continue
        status = _str(item.get("status_name"))
        position = _int(item.get("pos"))
        name = " ".join(
            p
            for p in (_str(item.get("rider_name")), (_str(item.get("rider_surname")) or "").title())
            if p
        )
        riders.append(
            LiveRider(
                number=_str(item.get("rider_number")) or str(key),
                name=name or None,
                short_name=_str(item.get("rider_shortname")),
                team=_str(item.get("team_name")),
                bike=_str(item.get("bike_name")),
                nation=_str(item.get("rider_nation")),
                color=_str(item.get("color")),
                position=position if position and position > 0 else None,
                gap_to_leader=_str(item.get("gap_first")),
                interval=_str(item.get("gap_prev")),
                last_lap=_str(item.get("last_lap_time")),
                laps=_int(item.get("num_lap")),
                # Retired riders are reported "on pit" too: only count riders
                # still in the session.
                in_pit=item.get("on_pit") is True and status != "RT",
                status=status,
            )
        )
    riders.sort(key=lambda r: (r.position is None, r.position or 0, r.number))

    status_id = _str(head.get("session_status_id")) or ""
    return LiveTiming(
        event=_str(head.get("event_tv_name")),
        event_short_name=_str(head.get("event_shortname")),
        circuit=_str(head.get("circuit_name")),
        session_name=_str(head.get("session_name")),
        session_type=_str(head.get("session_shortname")),
        status=SESSION_STATUS_MAP.get(status_id.upper()),
        total_laps=_int(head.get("num_laps")),
        remaining=_str(head.get("remaining")),
        riders=tuple(riders),
    )


# Minutes separator: apostrophe, prime (U+2032) or colon.
_LAP_TIME = re.compile(r"^(?:(\d+)['\u2032:])?(\d+(?:[.,]\d+)?)$")


def parse_lap_time(value: str | None) -> float | None:
    """Convert ``"1'59.123"``, ``"1:59.123"`` or ``"59.123"`` to seconds."""
    match = _LAP_TIME.match((value or "").strip())
    if not match:
        return None
    minutes, seconds = match.groups()
    return int(minutes or 0) * 60 + float(seconds.replace(",", "."))


def fastest_last_lap(riders: Iterable[LiveRider]) -> LiveRider | None:
    """Return the rider with the quickest *last* lap.

    livetiming-lite does not expose the session best lap, so this is an
    approximation of the fastest lap.
    """
    best: tuple[float, LiveRider] | None = None
    for rider in riders:
        seconds = parse_lap_time(rider.last_lap)
        if seconds is not None and seconds > 0 and (best is None or seconds < best[0]):
            best = (seconds, rider)
    return best[1] if best else None


# ── Weather ───────────────────────────────────────────────────────────────────

WMO_CONDITIONS: dict[int, str] = {
    0: "clear_sky",
    1: "mainly_clear",
    2: "partly_cloudy",
    3: "overcast",
    45: "fog",
    48: "fog",
    51: "drizzle",
    53: "drizzle",
    55: "drizzle",
    56: "freezing_drizzle",
    57: "freezing_drizzle",
    61: "light_rain",
    63: "rain",
    65: "heavy_rain",
    66: "freezing_rain",
    67: "freezing_rain",
    71: "snow",
    73: "snow",
    75: "snow",
    77: "snow",
    80: "showers",
    81: "showers",
    82: "heavy_showers",
    85: "snow",
    86: "snow",
    95: "thunderstorm",
    96: "thunderstorm",
    99: "thunderstorm",
}
WEATHER_CONDITIONS: list[str] = sorted(set(WMO_CONDITIONS.values()))

# Keyed by the event short name returned by Pulselive.
CIRCUIT_COORDINATES: dict[str, tuple[float, float]] = {
    "AME": (30.1328, -97.6411),  # Circuit of the Americas
    "ARA": (41.0786, -0.2047),  # MotorLand Aragón
    "ARG": (-27.5056, -64.9133),  # Termas de Río Hondo
    "AUS": (-38.5022, 145.2302),  # Phillip Island
    "AUT": (47.2197, 14.7647),  # Red Bull Ring
    "BRA": (-16.6829, -49.4054),  # Autódromo Internacional de Goiânia
    "CAT": (41.5700, 2.2610),  # Circuit de Barcelona-Catalunya
    "CZE": (49.2036, 16.4447),  # Automotodrom Brno
    "EMI": (43.9612, 12.6830),  # Misano (Emilia-Romagna GP)
    "FRA": (47.9561, 0.2072),  # Le Mans
    "GBR": (52.0786, -1.0169),  # Silverstone
    "GER": (50.7915, 12.6880),  # Sachsenring
    "HUN": (46.9562, 18.0832),  # Balaton Park
    "INA": (-8.8986, 116.3053),  # Mandalika
    "IND": (28.3487, 77.5331),  # Buddh International Circuit
    "ITA": (43.9975, 11.3719),  # Mugello
    "JPN": (36.5322, 140.2275),  # Mobility Resort Motegi
    "KAZ": (43.3372, 77.0089),  # Sokol International Racetrack
    "MAL": (2.7608, 101.7381),  # Sepang
    "NED": (52.9603, 6.5228),  # TT Circuit Assen
    "POR": (37.2276, -8.6267),  # Algarve International Circuit
    "QAT": (25.4900, 51.4542),  # Lusail
    "RSM": (43.9612, 12.6830),  # Misano
    "SPA": (36.7083, -6.0319),  # Jerez
    "THA": (14.9575, 103.0847),  # Chang International Circuit
    "USA": (30.1328, -97.6411),  # Circuit of the Americas
    "VAL": (39.4851, -0.6280),  # Ricardo Tormo
}


def circuit_coordinates(event: Event) -> tuple[float, float] | None:
    return CIRCUIT_COORDINATES.get((event.short_name or "").upper())


_DEGREES = re.compile(r"-?\d+(?:[.,]\d+)?")


def _degrees(value: Any) -> float | None:
    match = _DEGREES.search(str(value or ""))
    return float(match.group().replace(",", ".")) if match else None


def latest_track_condition(sessions: Iterable[Session]) -> dict[str, Any] | None:
    """Return the official track condition of the latest finished session."""
    for session in reversed([s for s in sessions if s.finished]):
        condition = session.condition
        if _str(condition.get("track")):
            return condition
    return None


def parse_weather(
    raw: Any,
    event: Event,
    coords: tuple[float, float],
    race_start: datetime | None,
    sessions: Iterable[Session] = (),
) -> WeatherData:
    """Build WeatherData from an Open-Meteo forecast (``timezone=UTC``)."""
    data = raw if isinstance(raw, dict) else {}
    current = data.get("current") if isinstance(data.get("current"), dict) else {}
    hourly = data.get("hourly") if isinstance(data.get("hourly"), dict) else {}

    race: dict[str, Any] = {}
    if race_start is not None:
        wanted = race_start.astimezone(UTC).strftime("%Y-%m-%dT%H:00")
        times = hourly.get("time") or []
        if wanted in times:
            idx = times.index(wanted)
            for key in (
                "temperature_2m",
                "precipitation_probability",
                "wind_speed_10m",
                "weather_code",
            ):
                values = hourly.get(key) or []
                race[key] = values[idx] if idx < len(values) else None

    code = _int(current.get("weather_code"))
    race_code = _int(race.get("weather_code"))
    track = latest_track_condition(sessions) or {}
    return WeatherData(
        circuit=event.circuit_name,
        latitude=coords[0],
        longitude=coords[1],
        condition=WMO_CONDITIONS.get(code) if code is not None else None,
        weather_code=code,
        temperature=_float(current.get("temperature_2m")),
        humidity=_float(current.get("relative_humidity_2m")),
        precipitation=_float(current.get("precipitation")),
        wind_speed=_float(current.get("wind_speed_10m")),
        wind_direction=_float(current.get("wind_direction_10m")),
        race_start=race_start,
        race_temperature=_float(race.get("temperature_2m")),
        race_precipitation_probability=_float(race.get("precipitation_probability")),
        race_wind_speed=_float(race.get("wind_speed_10m")),
        race_condition=WMO_CONDITIONS.get(race_code) if race_code is not None else None,
        track_condition=_str(track.get("track")),
        track_temperature=_degrees(track.get("ground")),
    )
