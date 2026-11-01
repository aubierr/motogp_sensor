"""Shared fixtures: real Pulselive payloads served through aioclient_mock."""

from __future__ import annotations

from collections.abc import Generator
import copy
import json
from pathlib import Path
from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.motogp_sensor.const import (
    CONF_RACE_WEEK_START,
    DOMAIN,
    OPEN_METEO_URL,
    PULSELIVE_BASE_URL,
)

pytest_plugins = "pytest_homeassistant_custom_component"

FIXTURES = Path(__file__).parent / "fixtures"

SEASON_ID = "e88b4e43-2209-47aa-8e83-0e0b1cedde6e"
CATEGORY_ID = "e8c110ad-64aa-4e8e-8a86-f2f152f6a942"
MAL_RACE_ID = "f8adeb74-3941-43e1-91cd-e1883f341ded"
MAL_SPRINT_ID = "dd4734d2-1b5f-4c61-9b6c-7129824319c3"
# Monday after the Malaysian GP, the Qatar GP starts on Friday.
NOW = "2026-11-02T10:00:00+00:00"


def load_fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def event_id(short_name: str) -> str:
    return next(e["id"] for e in load_fixture("events.json") if e["short_name"] == short_name)


def sprint_classification() -> dict[str, Any]:
    """Derive a Sprint classification from the race one (half points)."""
    data = copy.deepcopy(load_fixture("classification_mal_rac.json"))
    for row in data["classification"]:
        row["points"] = (row.get("points") or 0) / 2
    return data


def forecast() -> dict[str, Any]:
    hours = [f"2026-11-08T{h:02d}:00" for h in range(24)]
    return {
        "current": {
            "temperature_2m": 28.4,
            "relative_humidity_2m": 60,
            "precipitation": 0.0,
            "weather_code": 2,
            "wind_speed_10m": 12.0,
            "wind_direction_10m": 300,
        },
        "hourly": {
            "time": hours,
            "temperature_2m": [20 + h / 2 for h in range(24)],
            "precipitation_probability": [h for h in range(24)],
            "weather_code": [61] * 24,
            "wind_speed_10m": [10.0] * 24,
        },
    }


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> Generator[None]:
    yield


@pytest.fixture
def mock_api(aioclient_mock: AiohttpClientMocker) -> AiohttpClientMocker:
    """Register every endpoint used by the integration."""
    base = PULSELIVE_BASE_URL
    aioclient_mock.get(f"{base}/results/seasons", json=load_fixture("seasons.json"))
    aioclient_mock.get(f"{base}/results/categories", json=load_fixture("categories.json"))
    aioclient_mock.get(f"{base}/results/events", json=load_fixture("events.json"))
    aioclient_mock.get(
        f"{base}/results/sessions?eventUuid={event_id('MAL')}",
        json=load_fixture("sessions_mal.json"),
    )
    aioclient_mock.get(
        f"{base}/results/sessions?eventUuid={event_id('QAT')}",
        json=load_fixture("sessions_qat.json"),
    )
    aioclient_mock.get(f"{base}/results/sessions", json=[])
    aioclient_mock.get(f"{base}/results/standings", json=load_fixture("standings.json"))
    aioclient_mock.get(
        f"{base}/results/session/{MAL_RACE_ID}/classification",
        json=load_fixture("classification_mal_rac.json"),
    )
    aioclient_mock.get(
        f"{base}/results/session/{MAL_SPRINT_ID}/classification",
        json=sprint_classification(),
    )
    aioclient_mock.get(
        f"{base}/timing-gateway/livetiming-lite", json=load_fixture("livetiming.json")
    )
    aioclient_mock.get(OPEN_METEO_URL, json=forecast())
    return aioclient_mock


@pytest.fixture
def config_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="MotoGP",
        version=2,
        data={},
        options={CONF_RACE_WEEK_START: "monday"},
    )
