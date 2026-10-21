"""Shared fixtures."""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime
from typing import Any
from unittest.mock import patch

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.cleaning_hours.const import DOMAIN

DOORBELL = "binary_sensor.doorbell"
DOOR = "binary_sensor.private_door"
VEHICLE = "binary_sensor.vehicle"
CONFIG = {
    "doorbell": DOORBELL,
    "door": DOOR,
    "vehicle": VEHICLE,
    "notify": "notify.family",
    "dashboard": "/lovelace/cleaning",
    "worksheet": "Visits",
    "window_start": "08:00:00",
    "window_end": "16:00:00",
}
DAY = "2026-10-21"  # a Wednesday


def at(hhmm: str, day: str = DAY) -> datetime:
    """Local time on the test day."""
    return datetime.fromisoformat(f"{day}T{hhmm}").replace(tzinfo=dt_util.get_default_time_zone())


def changes(*events: tuple[str, bool], day: str = DAY) -> list[tuple[datetime, bool]]:
    return [(at("00:00", day), False)] + [(at(t, day), on) for t, on in events]


# Parcel at 08:00 (no car), cleaner rings 09:30 (car at 09:10), takes rubbish out at 12:00,
# leaves 15:30 (car moves 15:33), family comes home 16:10.
def default_history() -> dict[str, list[tuple[datetime, bool]]]:
    """Built lazily: the test time zone is only set once hass exists."""
    return {
        DOORBELL: changes(("07:59", True), ("07:59:30", False), ("09:30", True), ("09:30:20", False)),
        DOOR: changes(
            ("08:00", True), ("08:01", False),
            ("09:31", True), ("09:32", False),
            ("12:00", True), ("12:01", False),
            ("15:30", True), ("15:31", False),
            ("16:10", True), ("16:11", False),
        ),
        VEHICLE: changes(("09:10", True), ("09:11", False), ("15:33", True), ("15:34", False)),
    }


@pytest.fixture(autouse=True)
def auto_enable(recorder_mock: Any, enable_custom_integrations: None) -> None:
    """Recorder (a dependency) and custom integrations for every test."""


@pytest.fixture
def history(hass: HomeAssistant) -> Generator[dict[str, list[tuple[datetime, bool]]]]:
    """Recorder history served per entity; tests may edit it."""
    data = default_history()

    async def fetch(hass: HomeAssistant, entity_id: str, start: datetime, end: datetime) -> Any:
        return [c for c in data.get(entity_id, []) if start <= c[0] <= end]

    with patch("custom_components.cleaning_hours.tracker.fetch_changes", fetch):
        yield data


@pytest.fixture
def notify_calls(hass: HomeAssistant) -> list[ServiceCall]:
    return async_mock_service(hass, "notify", "family")


@pytest.fixture
def sheet_calls(hass: HomeAssistant) -> list[ServiceCall]:
    return async_mock_service(hass, "google_sheets", "append_sheet")


@pytest.fixture
async def entry(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, notify_calls: list[ServiceCall]
) -> MockConfigEntry:
    """Set-up config entry (with Google Sheet log) at 18:00 on the test day."""
    freezer.move_to(at("18:00"))
    entry = MockConfigEntry(
        domain=DOMAIN, data={**CONFIG, "sheet_config_entry": "sheet123"}, entry_id="abc"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry
