"""Diagnostics: configuration and stored visits (nothing secret)."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .tracker import CleaningConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: CleaningConfigEntry
) -> dict[str, Any]:
    return {"config": dict(entry.data), "data": entry.runtime_data.data}
