# MotoGP Sensor for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=aubierr&repository=motogp_sensor&category=integration)
[![Last commit](https://img.shields.io/github/last-commit/aubierr/motogp_sensor)](https://github.com/aubierr/motogp_sensor/commits)
[![Version](https://img.shields.io/github/v/release/aubierr/motogp_sensor)](https://github.com/aubierr/motogp_sensor/releases)
[![HA Community forum](https://img.shields.io/badge/Home%20Assistant-Community%20Forum-319fee?logo=home-assistant)](https://community.home-assistant.io/)

## Your home, in sync with MotoGP

**`MotoGP Sensor`** is a custom [Home Assistant](https://www.home-assistant.io/) integration that brings the MotoGP season into your smart home: calendar and session times, championship standings, race and sprint results, live timing and the weather at the circuit.

> This project is inspired by the excellent [F1 Sensor](https://github.com/Nicxe/f1_sensor) integration by [@Nicxe](https://github.com/Nicxe).

> [!IMPORTANT]
> Version 2 is a rewrite with breaking changes. Read the [changelog](CHANGELOG.md) before upgrading from 1.x.

---

## Features

### 📅 Season

| Entity | State | Main attributes |
|--------|-------|-----------------|
| Next race | Name of the ongoing or next GP | `round`, circuit, country, dates, `<session>_start` for `fp1`, `practice`, `fp2`, `q1`, `q2`, `sprint`, `warm_up`, `race`, `sessions` |
| Next session | Start time of the next session (timestamp) | `session`, `event`, `round` |
| Current season | Season year | `total_events` |
| Season calendar | Calendar of every GP (all day) and the sessions of the next GP | |
| Race week (binary) | On from the configured day until the end of the race day (at least 3 h after the race start) | `window_start`, `window_end` |

Tests (pre-season and in-season) are ignored, and rounds follow the calendar order.

### 🏆 Championship and results

| Entity | State | Main attributes |
|--------|-------|-----------------|
| Rider standings | Championship leader | `standings` (points, race and sprint wins/podiums) |
| Team standings | Leading team | `standings` |
| Constructor standings | Leading make | `standings` |
| Last race results | Name of the GP | `winner`, `results` (position, time, gap, points, status) |
| Last sprint results | Name of the GP | same as above |

Pulselive only publishes the rider championship: team and constructor standings are computed from every Race and Sprint classification of the season (team: all points of its riders; constructor: best placed rider of each make per race). Half points are kept.

### 📡 Live timing

| Entity | State |
|--------|-------|
| Session status | `not_started`, `in_progress`, `red_flag`, `delayed`, `finished`, `cancelled` (translated) |
| Current session | Session code (`FP1`, `PR`, `Q2`, `SPR`, `RAC`, …) |
| Race lap count | Current lap (`total_laps` attribute) |
| Session time remaining | As published by the live timing |
| Rider list | Number of riders (`riders` attribute) |
| Rider positions | Number of riders (`positions`: full board with gaps and last lap) |
| Top three / Leader | Leader's name |
| Fastest lap | Quickest *last* lap (approximation: the feed has no session best) |
| Pit stops | Riders currently in the pit lane (retired riders excluded) |
| Live timing online (binary, diagnostic) | Whether the feed answers |

Live timing is polled every **10 seconds** while a session is running, red flagged or delayed, and from 15 minutes before each scheduled session; every **5 minutes** otherwise.

### 🌦️ Track weather

Current conditions at the circuit of the ongoing or next GP ([Open-Meteo](https://open-meteo.com/), no API key), the forecast at the race start hour (up to 15 days ahead), and the official track condition and temperature of the latest session.

### 🙈 No Spoiler mode

A switch that freezes standings, results and the live classification (leader, top three, positions, fastest lap, pit stops) at their current state, for when you watch a race on delay. Data keep being fetched, so turning the switch off catches up immediately. After a restart with the mode on, those entities are unavailable until it is turned off. The calendar, session status and weather are never hidden.

### ⚙️ Device triggers

`race_week_started`, `race_week_ended`, `session_in_progress`, `session_finished`, `session_red_flag`, `session_cancelled`, `session_delayed`, `live_timing_online`, `live_timing_offline`

---

## Installation

Requires Home Assistant **2025.1** or newer.

### HACS (recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=aubierr&repository=motogp_sensor&category=integration)

### Manual

1. Copy the `custom_components/motogp_sensor` folder into your HA `custom_components` directory
2. Restart Home Assistant

## Setup

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=motogp_sensor)

Or go to **Settings → Devices & services → Add integration → MotoGP Sensor**, then choose when the race week starts:

| Option | Race week turns on |
|--------|--------------------|
| Monday of the GP week (default) | Monday 00:00 of the GP week |
| Sunday before the GP week | The day before |
| First day of the GP | On the first day of the GP (race weekend only) |

Change it later with **Configure** on the integration. Entities you do not need can be disabled from the entity settings.

## Languages

Entity names, states, the setup dialog and the device triggers follow the Home Assistant language:
English, Czech, Dutch, French, German, Hungarian, Indonesian, Italian, Japanese, Portuguese, Portuguese (Brazil), Spanish and Thai. Corrections from native speakers are welcome.

## Data sources

| Source | Used for |
|--------|----------|
| `api.motogp.pulselive.com/motogp/v1` | Seasons, events, sessions, standings, classifications, live timing |
| `api.open-meteo.com` | Weather |

Refresh: schedule every 6 h (30 min during a GP), results every 6 h (15 min from the first day of a GP until the day after), weather every 30 min. Failed requests are retried after 5 minutes.

## Development

```bash
pip install -r requirements_test.txt
pytest
ruff check . && ruff format --check .
```

Tests run against real API payloads stored in `tests/fixtures`. The Home Assistant test harness only supports Linux (or WSL).

---

> [!NOTE]
> MotoGP Sensor is an unofficial project and is not affiliated with or endorsed by Dorna Sports or MotoGP. MotoGP, the MotoGP logo, and related marks are trademarks of Dorna Sports S.L.
