# Changelog

## 2.0.0

Rewrite following the Home Assistant integration guidelines (`entry.runtime_data`, coordinator entities, entity descriptions, options flow, translations and icon translations, diagnostics, tests). Existing config entries are migrated automatically and entities keep their entity ids.

### Breaking changes

- **Home Assistant 2025.1 or newer** is required (1.x declared 2023.8 but did not work on it).
- **Official / Auto live sources removed**: `www.motogp.com/en/json/live_timing` no longer exists (HTTP 404). The `Live source` select, the `Live timing source` and `Official live timing diagnostic` sensors are removed.
- **One instance only**, settings moved to the integration options. The device name option is gone: rename the device in Home Assistant.
- **Choosing sensors in the config flow is gone**: disable entities from the entity settings. Sensors disabled in 1.x start disabled.
- **Race week option "Saturday (race weekend only)"** is now *First day of the GP*. In 1.x it opened on the Saturday *before* the GP week, earlier than the Monday option.
- **Session status** states are now translated keys: `in_progress`, `finished`, `red_flag`, `delayed`, `cancelled`, `not_started` (was `In Progress`, …). Device triggers keep working; update state triggers and templates.
- **Track weather** state is a translated condition key (`partly_cloudy`, `rain`, …). Attributes renamed: `air_temp` → `temperature`, `current_*` → no prefix.
- **Next race** session attributes: `<session>_start` (UTC, ISO 8601) for `fp1`, `practice`, `fp2`, `q1`, `q2`, `sprint`, `warm_up`, `race`, replacing `first_practice_start_local/utc`, … (the "local" values were UTC anyway, and Sprint/Practice/Q2 were missing).
- **Standings sensors** state is now the leader instead of a row count. `rider_standings` rows use flat keys (`name`, `number`, `points`, `race_wins`, …).
- **Rider positions** `positions` attribute is a list sorted by position (was a dict keyed by number).

### Fixes

- Session times were wrong by the circuit's UTC offset: Pulselive gives circuit local times labelled "+00:00" (FP1 is "10:45" everywhere). They are now converted with each circuit's time zone, which also fixes the live polling windows, the end of the race week and the race-time forecast.
- No Spoiler mode had no effect; it now freezes standings, results and live classification.
- The No Spoiler switch disappeared after a reconfiguration.
- The race week device triggers were never offered (unique id mismatch).
- `Live timing online` never updated after start-up.
- The race week turned off at midnight UTC: it now stays on until 3 h after the race start, whatever the time zone, and switches exactly at the window edges.
- Constructor standings showed the rider standings (the `type=team` parameter is ignored by the API). Team and constructor standings are now computed from the classifications, following team renames.
- Wins were always 0, gaps in race results showed a raw dict, half points were truncated.
- Pre-season and in-season tests were mixed with Grands Prix; the round number was wrong for rescheduled GPs (Qatar 2026 showed round 4 instead of 20).
- `Next race` could show the session times of another event, and switched to the next GP during the race weekend.
- Retired riders were counted as pit stops; the leader fallback could pick an unclassified rider.
- Live timing dropped to 5 minute polling during red flags and could start up to 5 minutes late.
- Data failing at start-up were only retried 24 h later; standings and results lagged up to a day after a race.
- Long attribute lists were written to the recorder every 10 seconds.
- Entity names ignored the Home Assistant language.
- Brand icon was a WebP file named `.png`.

### New

- `Next session` timestamp sensor, `Team standings` and `Last sprint results` sensors.
- Session times of the next GP in the calendar.
- Race-time forecast and official track condition in `Track weather`.
- Diagnostics download.
- Translations for the languages of the MotoGP host countries: Czech, Dutch, French, German, Hungarian, Indonesian, Japanese, Portuguese, Portuguese (Brazil), Spanish and Thai (in addition to English and Italian).
