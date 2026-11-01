"""Unit tests for the pure parsers, run against real Pulselive payloads."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from custom_components.motogp_sensor import parsers
from custom_components.motogp_sensor.models import ClassificationRow

from .conftest import CATEGORY_ID, SEASON_ID, load_fixture


def _tz(short_name: str) -> ZoneInfo:
    return ZoneInfo(parsers.CIRCUITS[short_name][2])


def _events():
    return parsers.parse_events(load_fixture("events.json"))


def test_current_season_and_category() -> None:
    assert parsers.find_current_season(load_fixture("seasons.json")) == (SEASON_ID, 2026)
    # The MotoGP class, not Moto3 (whose legacy id v1 used by mistake).
    assert parsers.find_category_id(load_fixture("categories.json")) == CATEGORY_ID


def test_events_skip_tests_and_number_rounds_by_date() -> None:
    events = _events()
    assert len(events) == 22
    assert not any("TEST" in e.name for e in events)
    by_name = {e.short_name: e for e in events}
    assert by_name["THA"].round == 1
    # Qatar was moved: its legacy eventId is 4 but it is round 20.
    assert by_name["QAT"].round == 20
    assert by_name["VAL"].round == 22
    assert by_name["MAL"].circuit_name == "Petronas Sepang International Circuit"
    assert by_name["MAL"].country_iso == "MY"


@pytest.mark.parametrize(
    ("today", "expected"),
    [
        (date(2026, 10, 31), "MAL"),  # during the GP
        (date(2026, 11, 1), "MAL"),  # race day
        (date(2026, 11, 2), "QAT"),
        (date(2026, 12, 1), None),  # season over
    ],
)
def test_focus_event(today: date, expected: str | None) -> None:
    focus = parsers.find_focus_event(_events(), today)
    assert (focus.short_name if focus else None) == expected


def test_sessions_cover_the_modern_weekend_format() -> None:
    sessions = parsers.parse_sessions(load_fixture("sessions_mal.json"), _tz("MAL"))
    assert tuple(s.key for s in sessions) == parsers.SESSION_KEYS
    race = parsers.find_session(sessions, "race")
    assert race is not None and race.finished
    # "15:00+00:00" in the API is 15:00 in Sepang (UTC+8).
    assert race.start == datetime(2026, 11, 1, 7, 0, tzinfo=UTC)
    now = datetime(2026, 10, 31, 5, 0, tzinfo=UTC)
    assert parsers.next_session(sessions, now).key == "sprint"
    # Without the circuit time zone the labelled time is kept.
    raw = parsers.parse_sessions(load_fixture("sessions_mal.json"))
    assert parsers.find_session(raw, "race").start == datetime(2026, 11, 1, 15, 0, tzinfo=UTC)


def test_every_circuit_has_a_valid_time_zone() -> None:
    for short_name, (_lat, _lon, tz) in parsers.CIRCUITS.items():
        assert ZoneInfo(tz), short_name
    assert all(parsers.circuit_time_zone(e) for e in _events())


@pytest.mark.parametrize(
    ("option", "tz", "start", "end"),
    [
        ("monday", "UTC", datetime(2026, 11, 2, tzinfo=UTC), datetime(2026, 11, 9, tzinfo=UTC)),
        ("sunday", "UTC", datetime(2026, 11, 1, tzinfo=UTC), datetime(2026, 11, 9, tzinfo=UTC)),
        # v1 opened the "race weekend only" window on the previous Saturday.
        (
            "event_start",
            "UTC",
            datetime(2026, 11, 6, tzinfo=UTC),
            datetime(2026, 11, 9, tzinfo=UTC),
        ),
        # Race at 16:00 UTC: 3 h later is after midnight in Tokyo, the grace wins.
        (
            "monday",
            "Asia/Tokyo",
            datetime(2026, 11, 2, tzinfo=ZoneInfo("Asia/Tokyo")),
            datetime(2026, 11, 8, 19, 0, tzinfo=UTC),
        ),
    ],
)
def test_race_week_window(option: str, tz: str, start: datetime, end: datetime) -> None:
    qatar = next(e for e in _events() if e.short_name == "QAT")
    sessions = parsers.parse_sessions(load_fixture("sessions_qat.json"), _tz("QAT"))
    window = parsers.race_week_window(qatar, sessions, option, ZoneInfo(tz))
    assert window == (start, end)


def test_rider_standings() -> None:
    standings = parsers.parse_rider_standings(load_fixture("standings.json"))
    leader = standings[0]
    assert leader.position == 1
    assert leader.name == "Marc Marquez"
    assert leader.number == 93
    assert leader.points == 399
    assert leader.race_wins == 7  # v1 always reported 0 wins
    assert leader.team == "Ducati Lenovo Team"
    assert leader.constructor == "Ducati"


def test_classification() -> None:
    rows = parsers.parse_classification(load_fixture("classification_mal_rac.json"))
    winner, last = rows[0], rows[-1]
    assert winner.position == 1
    assert winner.rider_name == "Marc Marquez"
    assert winner.gap == "0.000"  # v1 showed the raw dict
    assert winner.time == "40:14.236"
    assert winner.points == 25
    assert last.position is None  # not classified


def _row(team: str, constructor: str, points: float, rider: str) -> ClassificationRow:
    return ClassificationRow(
        position=None, rider_name=rider, rider_number=None, country=None, team=team,
        constructor=constructor, time=None, gap=None, laps=None, points=points, status=None,
    )  # fmt: skip


def test_team_and_constructor_standings() -> None:
    race = [
        _row("Ducati Lenovo", "Ducati", 25, "A"),
        _row("Gresini", "Ducati", 20, "B"),
        _row("Ducati Lenovo", "Ducati", 16, "C"),
        _row("KTM Factory", "KTM", 13, "D"),
    ]
    # Rain shortened sprint: half points.
    sprint = [_row("KTM Factory", "KTM", 6, "D"), _row("Gresini", "Ducati", 4.5, "B")]

    teams = parsers.compute_team_standings([race, sprint])
    assert [(t.name, t.points) for t in teams] == [
        ("Ducati Lenovo", 41),
        ("Gresini", 24.5),
        ("KTM Factory", 19),
    ]
    assert teams[0].riders == ("A", "C")

    constructors = parsers.compute_constructor_standings([race, sprint])
    # Only the best placed rider of each make scores.
    assert [(c.name, c.points) for c in constructors] == [("Ducati", 29.5), ("KTM", 19)]
    assert parsers.number(24.5) == 24.5 and isinstance(parsers.number(41.0), int)


def test_team_standings_follow_sponsor_renames() -> None:
    early = [replace(_row("Trackhouse", "Aprilia", 10, "A"), team_id="t1")]
    late = [replace(_row("SuperFile Trackhouse", "Aprilia", 5, "A"), team_id="t1")]
    teams = parsers.compute_team_standings([early, late])
    assert [(t.name, t.points) for t in teams] == [("SuperFile Trackhouse", 15)]


def test_live_timing() -> None:
    live = parsers.parse_live_timing(load_fixture("livetiming.json"))
    assert live is not None
    assert live.status == "finished"
    assert live.session_type == "RAC"
    assert live.total_laps == 20
    assert live.remaining == "0"
    assert live.leader.name == "Marc Marquez"
    assert live.current_lap == 20
    retired = [r for r in live.riders if r.status == "RT"]
    assert retired and all(r.position is None and not r.in_pit for r in retired)
    # Classified riders first, in order.
    positions = [r.position for r in live.riders if r.position is not None]
    assert positions == sorted(positions)
    assert parsers.parse_live_timing(None) is None
    assert parsers.parse_live_timing({"foo": 1}) is None


@pytest.mark.parametrize(
    ("value", "seconds"),
    [("2'02.888", 122.888), ("1:59.5", 119.5), ("59,1", 59.1), ("", None), ("-", None)],
)
def test_parse_lap_time(value: str, seconds: float | None) -> None:
    result = parsers.parse_lap_time(value)
    if seconds is None:
        assert result is None
    else:
        assert result == pytest.approx(seconds)


def test_weather() -> None:
    from .conftest import forecast

    qatar = next(e for e in _events() if e.short_name == "QAT")
    race_start = datetime(2026, 11, 8, 19, 0, tzinfo=UTC)
    mal_sessions = parsers.parse_sessions(load_fixture("sessions_mal.json"))
    weather = parsers.parse_weather(forecast(), qatar, (25.49, 51.45), race_start, mal_sessions)
    assert weather.condition == "partly_cloudy"
    assert weather.temperature == 28.4
    assert weather.race_temperature == 29.5
    assert weather.race_precipitation_probability == 19
    assert weather.race_condition == "light_rain"
    assert weather.track_condition == "Dry"
    assert weather.track_temperature == 55
    assert parsers.circuit_coordinates(qatar) is not None
