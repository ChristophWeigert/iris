"""Setup, unload, scheduled scans, notification actions, services, diagnostics."""

from __future__ import annotations

from typing import Any

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.cleaning_hours.const import DOMAIN
from custom_components.cleaning_hours.diagnostics import async_get_config_entry_diagnostics

from .conftest import CONFIG, DAY, at


async def test_setup_and_unload(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.cleaning_hours_proposal").state == "none"
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_scheduled_scan_and_notification_actions(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    history: Any,
    notify_calls: list[ServiceCall],
    sheet_calls: list[ServiceCall],
) -> None:
    freezer.move_to(at("16:00"))
    entry = MockConfigEntry(domain=DOMAIN, data=CONFIG)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)

    freezer.move_to(at("17:00"))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert len(notify_calls) == 1
    assert "09:31–15:31" in notify_calls[0].data["message"]

    hass.bus.async_fire("mobile_app_notification_action", {"action": f"CLEANING_CONFIRM:{DAY}"})
    await hass.async_block_till_done()
    assert entry.runtime_data.visits[DAY]["status"] == "confirmed"
    assert sheet_calls == []  # no sheet configured

    # a second tap on an old notification is ignored quietly
    hass.bus.async_fire("mobile_app_notification_action", {"action": f"CLEANING_DISMISS:{DAY}"})
    hass.bus.async_fire("mobile_app_notification_action", {"action": "SOMETHING_ELSE"})
    await hass.async_block_till_done()
    assert entry.runtime_data.visits[DAY]["status"] == "confirmed"


async def test_services(
    hass: HomeAssistant, entry: MockConfigEntry, history: Any, sheet_calls: list[ServiceCall]
) -> None:
    await hass.services.async_call(DOMAIN, "scan", {"date": DAY}, blocking=True)
    await hass.services.async_call(DOMAIN, "dismiss", {"date": DAY}, blocking=True)
    assert entry.runtime_data.visits[DAY]["status"] == "dismissed"

    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(DOMAIN, "confirm", {"date": DAY}, blocking=True)
    assert err.value.translation_key == "no_proposed_visit"

    await hass.services.async_call(
        DOMAIN, "add_visit", {"date": "2026-10-14", "start": "09:00", "end": "13:15"}, blocking=True
    )
    assert entry.runtime_data.visits["2026-10-14"]["minutes"] == 255
    assert sheet_calls[-1].data["data"][0]["Hours"] == 4.25

    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN, "add_visit", {"start": "13:00", "end": "09:00"}, blocking=True
        )
    assert err.value.translation_key == "end_before_start"

    # defaults to today; scanning an empty day does nothing
    history.clear()
    await hass.services.async_call(DOMAIN, "scan", {"date": "2026-10-20"}, blocking=True)
    assert "2026-10-20" not in entry.runtime_data.visits


async def test_services_need_a_loaded_entry(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await hass.config_entries.async_unload(entry.entry_id)
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(DOMAIN, "scan", {}, blocking=True)
    assert err.value.translation_key == "not_loaded"


async def test_reconfigure_reloads(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    hass.config_entries.async_update_entry(entry, options={"worksheet": "Other"})
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.conf["worksheet"] == "Other"


async def test_diagnostics(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["config"]["door"] == "binary_sensor.private_door"
    assert diag["data"]["visits"] == {}


async def test_data_survives_restart(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await entry.runtime_data.async_set_rate(15)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.data["rate"] == 15
