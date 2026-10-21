"""Cleaning Hours: propose cleaner visits from door, doorbell and car history for review."""

from __future__ import annotations

from collections.abc import Coroutine
from typing import Any

from homeassistant.const import Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.typing import ConfigType

from .const import ACTION_CONFIRM, ACTION_DISMISS, DOMAIN, SCAN_TIMES
from .services import async_setup_services
from .tracker import CleaningConfigEntry, Tracker

PLATFORMS = [Platform.BUTTON, Platform.IMAGE, Platform.NUMBER, Platform.SELECT, Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register services once, independent of config entries."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: CleaningConfigEntry) -> bool:
    """Load stored visits, schedule the daily scans and listen for notification actions."""
    tracker = Tracker(hass, entry)
    await tracker.async_load()
    entry.runtime_data = tracker

    for hour, minute in SCAN_TIMES:
        entry.async_on_unload(
            async_track_time_change(
                hass, tracker.async_scan_today, hour=hour, minute=minute, second=0
            )
        )

    @callback
    def on_action(event: Event) -> None:
        action, _, day = str(event.data.get("action", "")).partition(":")
        handler = {ACTION_CONFIRM: tracker.async_confirm, ACTION_DISMISS: tracker.async_dismiss}
        if action in handler:
            hass.async_create_task(_quietly(handler[action](day)))

    entry.async_on_unload(hass.bus.async_listen("mobile_app_notification_action", on_action))
    entry.async_on_unload(entry.add_update_listener(_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _quietly(coro: Coroutine[Any, Any, None]) -> None:
    """A tap on an already reviewed notification is not an error."""
    try:
        await coro
    except ServiceValidationError:
        pass


async def _reload(hass: HomeAssistant, entry: CleaningConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: CleaningConfigEntry) -> bool:
    """Unload platforms; listeners are removed via async_on_unload."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
