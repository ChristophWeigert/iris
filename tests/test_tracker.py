"""Scan, review, entities, Google Sheet log and snapshots."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.cleaning_hours.const import DOMAIN
from custom_components.cleaning_hours.tracker import fetch_changes

from .conftest import DAY, DOOR, DOORBELL, at, changes


async def scan(hass: HomeAssistant, day: str = DAY) -> None:
    await hass.services.async_call(DOMAIN, "scan", {"date": day}, blocking=True)


def state(hass: HomeAssistant, entity_id: str) -> Any:
    return hass.states.get(entity_id)


async def test_scan_proposes_and_preselects(
    hass: HomeAssistant, entry: MockConfigEntry, history: Any, notify_calls: list[ServiceCall]
) -> None:
    await scan(hass)

    assert state(hass, "sensor.cleaning_hours_proposal").state == f"{DAY} 09:31–15:31 (6.00 h)"
    assert state(hass, "select.cleaning_hours_arrival").state == "09:31:00 🚗"
    assert state(hass, "select.cleaning_hours_arrival").attributes["options"] == [
        "08:00:00", "09:31:00 🚗"
    ]
    assert state(hass, "select.cleaning_hours_departure").state == "15:31:00 🚗"
    assert state(hass, "button.cleaning_hours_confirm").state != "unavailable"
    assert state(hass, "sensor.cleaning_hours_proposal").attributes["warnings"] == []

    msg = notify_calls[0].data
    assert msg["title"] == f"Cleaning {DAY}"
    assert msg["data"]["image"] == "/api/image_proxy/image.cleaning_hours_arrival"
    assert msg["data"]["actions"][0]["action"] == f"CLEANING_CONFIRM:{DAY}"


async def test_scan_is_idempotent(
    hass: HomeAssistant, entry: MockConfigEntry, history: Any, notify_calls: list[ServiceCall]
) -> None:
    await scan(hass)
    await hass.services.async_call(
        "select", "select_option",
        {"entity_id": "select.cleaning_hours_departure", "option": "16:11:00"}, blocking=True,
    )
    await scan(hass)  # refresh keeps the reviewer's pick and does not notify again
    assert len(notify_calls) == 1
    assert state(hass, "select.cleaning_hours_departure").state == "16:11:00"

    await hass.services.async_call(
        "button", "press", {"entity_id": "button.cleaning_hours_confirm"}, blocking=True
    )
    visit = entry.runtime_data.visits[DAY]
    assert visit["minutes"] == 400  # 09:31 → 16:11
    history[DOOR].clear()
    await scan(hass)  # confirmed visits are never touched
    assert entry.runtime_data.visits[DAY] == visit
    assert state(hass, "sensor.cleaning_hours_proposal").state == "none"
    assert state(hass, "button.cleaning_hours_confirm").state == "unavailable"


async def test_picking_arrival_recomputes_departures(
    hass: HomeAssistant, entry: MockConfigEntry, history: Any
) -> None:
    await scan(hass)
    await hass.services.async_call(
        "select", "select_option",
        {"entity_id": "select.cleaning_hours_arrival", "option": "08:00:00"}, blocking=True,
    )
    assert state(hass, "select.cleaning_hours_departure").attributes["options"] == [
        "09:32:00", "12:01:00", "15:31:00 🚗", "16:11:00"
    ]
    await hass.services.async_call(
        "select", "select_option",
        {"entity_id": "select.cleaning_hours_arrival", "option": "09:31:00 🚗"}, blocking=True,
    )
    assert state(hass, "select.cleaning_hours_arrival").state == "09:31:00 🚗"


async def test_outside_window_warning(
    hass: HomeAssistant, entry: MockConfigEntry, history: Any, notify_calls: list[ServiceCall]
) -> None:
    history[DOORBELL] = changes(("17:00", True), ("17:00:10", False))
    history[DOOR] = changes(("17:01", True), ("17:02", False), ("17:30", True), ("17:31", False))
    await scan(hass)

    assert "outside_window" in state(hass, "sensor.cleaning_hours_proposal").attributes["warnings"]
    assert "outside window" in notify_calls[0].data["message"]


async def test_departure_missing_and_warnings(
    hass: HomeAssistant, entry: MockConfigEntry, history: Any, notify_calls: list[ServiceCall]
) -> None:
    day = "2026-10-20"  # a Tuesday, she is still inside, no car seen
    history[DOORBELL] = changes(("10:00", True), ("10:00:10", False), day=day)
    history[DOOR] = changes(("10:01", True), ("10:02", False), day=day)
    await scan(hass, day)

    assert state(hass, "sensor.cleaning_hours_proposal").state == f"{day} departure missing"
    assert state(hass, "sensor.cleaning_hours_proposal").attributes["warnings"] == [
        "not_expected_day", "no_car", "no_departure"
    ]
    assert state(hass, "select.cleaning_hours_departure").state == "–"
    assert state(hass, "image.cleaning_hours_departure_door").state == "unavailable"
    assert "Departure not found yet" in notify_calls[0].data["message"]
    assert "not expected day" in notify_calls[0].data["message"]
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(DOMAIN, "confirm", {"date": day}, blocking=True)
    assert err.value.translation_key == "no_departure"
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.cleaning_hours_dismiss"}, blocking=True
    )
    assert entry.runtime_data.visits[day]["status"] == "dismissed"


async def test_no_pending_selects_and_buttons(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    assert state(hass, "select.cleaning_hours_arrival").state == "–"
    await entry.runtime_data.async_select("arrival", 0)  # nothing to select: no-op
    button = hass.data["entity_components"]["button"].get_entity("button.cleaning_hours_confirm")
    await button.async_press()  # nothing pending: no-op
    assert entry.runtime_data.visits == {}


async def test_payday_correction_goes_to_sheet(
    hass: HomeAssistant, entry: MockConfigEntry, history: Any, sheet_calls: list[ServiceCall]
) -> None:
    await hass.services.async_call(
        "number", "set_value",
        {"entity_id": "number.cleaning_hours_hourly_rate", "value": 15}, blocking=True,
    )
    for d in ("2026-09-02", "2026-09-09", "2026-09-16", "2026-09-23"):
        await hass.services.async_call(
            DOMAIN, "add_visit", {"date": d, "start": "09:00", "end": "13:00"}, blocking=True
        )
    # payday 2026-09-30: estimate 4 h, actual 6 h → +30 € correction
    await hass.services.async_call(
        DOMAIN, "add_visit", {"date": "2026-09-30", "start": "09:00", "end": "15:00"}, blocking=True
    )
    rows = sheet_calls[-1].data["data"]
    assert sheet_calls[-1].data["config_entry"] == "sheet123"
    assert rows[1] == {"Date": "2026-09-30", "Note": "Correction for next pay period", "Euros": 30.0}

    payout = state(hass, "sensor.cleaning_hours_payout")
    assert payout.attributes["correction_eur"] == 30.0
    assert payout.attributes["estimate_hours"] == 4.5  # avg of 09-09…09-30
    assert float(payout.state) == round(4.5 * 15 + 30, 2)

    await hass.services.async_call(
        "number", "set_value",
        {"entity_id": "number.cleaning_hours_payday_estimate", "value": 5}, blocking=True,
    )
    assert float(state(hass, "number.cleaning_hours_payday_estimate").state) == 5


async def test_failures_do_not_lose_visits(
    hass: HomeAssistant, entry: MockConfigEntry, history: Any, caplog: pytest.LogCaptureFixture
) -> None:
    async def fail(call: ServiceCall) -> None:
        raise HomeAssistantError("down")

    hass.services.async_register("notify", "family", fail)
    hass.services.async_register("google_sheets", "append_sheet", fail)
    await entry.runtime_data.async_scan(dt_util.parse_date(DAY))
    await entry.runtime_data.async_confirm(DAY)
    assert entry.runtime_data.visits[DAY]["status"] == "confirmed"
    assert "Could not send notification" in caplog.text
    assert "Could not append visit" in caplog.text


async def test_snapshots(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    history: Any,
    hass_client: ClientSessionGenerator,
) -> None:
    protect = MockConfigEntry(domain="unifiprotect")
    protect.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=protect.entry_id, connections={(dr.CONNECTION_NETWORK_MAC, "aa:bb")}
    )
    er.async_get(hass).async_get_or_create(
        "binary_sensor", "unifiprotect", "bell", device_id=device.id, suggested_object_id="doorbell"
    )
    camera = SimpleNamespace(get_snapshot=AsyncMock(return_value=b"jpeg"))
    bootstrap = SimpleNamespace(get_device_from_mac=lambda mac: camera if mac == "aa:bb" else None)
    protect.runtime_data = SimpleNamespace(api=SimpleNamespace(bootstrap=bootstrap))
    protect.mock_state(hass, ConfigEntryState.LOADED)

    await scan(hass)
    client = await hass_client()
    resp = await client.get("/api/image_proxy/image.cleaning_hours_arrival")
    assert resp.status == 200
    assert await resp.read() == b"jpeg"
    assert camera.get_snapshot.call_args.kwargs["dt"] == at("09:31:05")

    resp = await client.get("/api/image_proxy/image.cleaning_hours_departure_door")
    assert resp.status == 200
    assert camera.get_snapshot.call_args.kwargs["dt"] == at("15:30:05")  # opening, not close

    # vehicle sensor has no device → no image
    resp = await client.get("/api/image_proxy/image.cleaning_hours_departure_car")
    assert resp.status != 200
    # MAC not known to Protect → None
    bootstrap.get_device_from_mac = lambda mac: None
    when = at("09:31").isoformat()
    assert await entry.runtime_data.async_snapshot("binary_sensor.doorbell", when) is None
    protect.mock_state(hass, ConfigEntryState.NOT_LOADED)  # don't unload the real integration


async def test_image_without_visit(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    image = hass.data["entity_components"]["image"].get_entity("image.cleaning_hours_arrival")
    assert await image.async_image() is None


async def test_fetch_changes_reads_recorder(hass: HomeAssistant) -> None:
    from pytest_homeassistant_custom_component.components.recorder.common import (
        async_wait_recording_done,
    )

    start = dt_util.utcnow()
    for value in ("off", "on", "unavailable", "off"):
        hass.states.async_set("binary_sensor.door", value)
    await async_wait_recording_done(hass)
    result = await fetch_changes(hass, "binary_sensor.door", start, dt_util.utcnow())
    assert [on for _, on in result] == [False, True, False]
