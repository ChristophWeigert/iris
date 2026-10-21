"""Services: scan a day, confirm, dismiss, or add a visit by hand."""

from __future__ import annotations

from datetime import date

import probatio as vol  # HA replaced voluptuous with probatio (same API)
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .tracker import Tracker

DAY_SCHEMA = vol.Schema({vol.Optional("date"): cv.date})
ADD_SCHEMA = DAY_SCHEMA.extend({vol.Required("start"): cv.time, vol.Required("end"): cv.time})


def _tracker(hass: HomeAssistant) -> Tracker:
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="not_loaded")
    tracker: Tracker = entries[0].runtime_data
    return tracker


def _day(call: ServiceCall) -> date:
    day: date = call.data.get("date") or dt_util.now().date()
    return day


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    async def scan(call: ServiceCall) -> None:
        await _tracker(hass).async_scan(_day(call))

    async def confirm(call: ServiceCall) -> None:
        await _tracker(hass).async_confirm(_day(call).isoformat())

    async def dismiss(call: ServiceCall) -> None:
        await _tracker(hass).async_dismiss(_day(call).isoformat())

    async def add_visit(call: ServiceCall) -> None:
        await _tracker(hass).async_add_manual(_day(call), call.data["start"], call.data["end"])

    hass.services.async_register(DOMAIN, "scan", scan, DAY_SCHEMA)
    hass.services.async_register(DOMAIN, "confirm", confirm, DAY_SCHEMA)
    hass.services.async_register(DOMAIN, "dismiss", dismiss, DAY_SCHEMA)
    hass.services.async_register(DOMAIN, "add_visit", add_visit, ADD_SCHEMA)
