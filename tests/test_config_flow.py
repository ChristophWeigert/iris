"""Config flow: setup, validation, single instance, reconfigure."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.cleaning_hours.const import DOMAIN

from .conftest import CONFIG


async def test_user_flow(hass: HomeAssistant, notify_calls: list[ServiceCall]) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {}

    bad = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**CONFIG, "notify": "notify.nobody"}
    )
    assert bad["type"] is FlowResultType.FORM
    assert bad["errors"] == {"notify": "unknown_service"}

    reversed_window = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**CONFIG, "window_start": "16:00:00", "window_end": "08:00:00"}
    )
    assert reversed_window["errors"] == {"window_end": "window_end_before_start"}

    done = await hass.config_entries.flow.async_configure(result["flow_id"], CONFIG)
    assert done["type"] is FlowResultType.CREATE_ENTRY
    assert done["title"] == "Cleaning Hours"
    assert done["data"] == CONFIG


async def test_single_instance(hass: HomeAssistant) -> None:
    MockConfigEntry(domain=DOMAIN, data=CONFIG).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_reconfigure(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    bad = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**CONFIG, "notify": "notify.nobody"}
    )
    assert bad["errors"] == {"notify": "unknown_service"}

    done = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**CONFIG, "door": "binary_sensor.other_door"}
    )
    assert done["type"] is FlowResultType.ABORT
    assert done["reason"] == "reconfigure_successful"
    assert entry.data["door"] == "binary_sensor.other_door"
