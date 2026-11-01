"""Thin async HTTP client for the Pulselive MotoGP API and Open-Meteo."""

from __future__ import annotations

import asyncio
from datetime import date
import logging
from typing import Any

import aiohttp

from .const import OPEN_METEO_URL, PULSELIVE_BASE_URL, REQUEST_TIMEOUT

_LOGGER = logging.getLogger(__name__)


class MotoGPApiError(Exception):
    """Raised when an API request fails or returns something unusable."""


class MotoGPApiClient:
    """Fetch raw JSON payloads; parsing lives in ``parsers``."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def _get(
        self, url: str, params: dict[str, Any] | None = None, *, empty_ok: bool = False
    ) -> Any:
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                async with self._session.get(url, params=params) as resp:
                    if empty_ok and resp.status in (204, 404):
                        return None
                    resp.raise_for_status()
                    return await resp.json(content_type=None)
        except TimeoutError as err:
            raise MotoGPApiError(f"Timeout fetching {url}") from err
        except aiohttp.ClientResponseError as err:
            raise MotoGPApiError(f"HTTP {err.status} fetching {url}") from err
        except (aiohttp.ClientError, ValueError) as err:
            raise MotoGPApiError(f"Error fetching {url}: {err}") from err

    # ── Pulselive results API ────────────────────────────────────────────────

    async def seasons(self) -> Any:
        return await self._get(f"{PULSELIVE_BASE_URL}/results/seasons")

    async def categories(self, season_id: str) -> Any:
        return await self._get(
            f"{PULSELIVE_BASE_URL}/results/categories", {"seasonUuid": season_id}
        )

    async def events(self, season_id: str) -> Any:
        return await self._get(f"{PULSELIVE_BASE_URL}/results/events", {"seasonUuid": season_id})

    async def sessions(self, event_id: str, category_id: str) -> Any:
        return await self._get(
            f"{PULSELIVE_BASE_URL}/results/sessions",
            {"eventUuid": event_id, "categoryUuid": category_id},
        )

    async def standings(self, season_id: str, category_id: str) -> Any:
        return await self._get(
            f"{PULSELIVE_BASE_URL}/results/standings",
            {"seasonUuid": season_id, "categoryUuid": category_id},
        )

    async def classification(self, session_id: str) -> Any:
        return await self._get(
            f"{PULSELIVE_BASE_URL}/results/session/{session_id}/classification",
            {"test": "false"},
        )

    async def live_timing(self) -> Any:
        """Return the live timing payload, or None when nothing is published."""
        return await self._get(
            f"{PULSELIVE_BASE_URL}/timing-gateway/livetiming-lite", empty_ok=True
        )

    # ── Open-Meteo ───────────────────────────────────────────────────────────

    async def forecast(self, latitude: float, longitude: float, race_day: date | None) -> Any:
        params: dict[str, Any] = {
            "latitude": latitude,
            "longitude": longitude,
            "current": (
                "temperature_2m,relative_humidity_2m,precipitation,weather_code,"
                "wind_speed_10m,wind_direction_10m"
            ),
            "timezone": "UTC",
            "wind_speed_unit": "kmh",
        }
        if race_day is not None:
            params |= {
                "hourly": "temperature_2m,precipitation_probability,weather_code,wind_speed_10m",
                "start_date": race_day.isoformat(),
                "end_date": race_day.isoformat(),
            }
        return await self._get(OPEN_METEO_URL, params)
