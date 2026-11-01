"""Constants for the MotoGP Sensor integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "motogp_sensor"
PLATFORMS: Final = [
    Platform.BINARY_SENSOR,
    Platform.CALENDAR,
    Platform.SENSOR,
    Platform.SWITCH,
]

# ── Config entry ─────────────────────────────────────────────────────────────
CONF_RACE_WEEK_START: Final = "race_week_start_day"
RACE_WEEK_START_MONDAY: Final = "monday"
RACE_WEEK_START_SUNDAY: Final = "sunday"
RACE_WEEK_START_EVENT: Final = "event_start"
RACE_WEEK_START_OPTIONS: Final = [
    RACE_WEEK_START_MONDAY,
    RACE_WEEK_START_SUNDAY,
    RACE_WEEK_START_EVENT,
]
DEFAULT_RACE_WEEK_START: Final = RACE_WEEK_START_MONDAY

# Sensor keys the user disabled in v1; they start disabled in the entity registry.
CONF_LEGACY_DISABLED: Final = "legacy_disabled_sensors"

DEFAULT_NAME: Final = "MotoGP"

# ── Endpoints ────────────────────────────────────────────────────────────────
PULSELIVE_BASE_URL: Final = "https://api.motogp.pulselive.com/motogp/v1"
OPEN_METEO_URL: Final = "https://api.open-meteo.com/v1/forecast"
REQUEST_TIMEOUT: Final = 15

# Name of the premier class as returned by /results/categories ("MotoGP™").
MOTOGP_CATEGORY_PREFIX: Final = "motogp"

# ── Refresh intervals ────────────────────────────────────────────────────────
SCHEDULE_INTERVAL: Final = timedelta(hours=6)
RESULTS_INTERVAL_IDLE: Final = timedelta(hours=6)
RESULTS_INTERVAL_RACE_WEEKEND: Final = timedelta(minutes=15)
WEATHER_INTERVAL: Final = timedelta(minutes=30)
LIVE_INTERVAL_ACTIVE: Final = timedelta(seconds=10)
LIVE_INTERVAL_IDLE: Final = timedelta(minutes=5)
RETRY_INTERVAL: Final = timedelta(minutes=5)

# Live polling switches to the fast interval this long before a scheduled
# session and keeps it at least this long after the scheduled start.
LIVE_WAKE_BEFORE: Final = timedelta(minutes=15)
LIVE_WAKE_AFTER: Final = timedelta(minutes=30)

# The race week stays on until at least this long after the race start.
RACE_WEEK_GRACE: Final = timedelta(hours=3)

# Finished classifications younger than this are re-fetched (penalties can
# still change the provisional result).
RESULTS_SETTLE_TIME: Final = timedelta(days=2)

# ── Live session status ──────────────────────────────────────────────────────
SESSION_STATUS_MAP: Final[dict[str, str]] = {
    "C": "cancelled",
    "D": "delayed",
    "F": "finished",
    "I": "in_progress",
    "N": "not_started",
    "R": "red_flag",
}
SESSION_STATUS_OPTIONS: Final = sorted(SESSION_STATUS_MAP.values())
# Statuses for which live timing is polled at the fast interval.
LIVE_ACTIVE_STATUSES: Final = frozenset({"in_progress", "red_flag", "delayed"})
