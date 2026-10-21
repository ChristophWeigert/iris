"""Confirm or dismiss the visit under review."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import TrackerEntity
from .tracker import CleaningConfigEntry

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CleaningConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([Review(entry, "confirm"), Review(entry, "dismiss")])


class Review(TrackerEntity, ButtonEntity):
    """Unavailable while nothing waits for review."""

    def __init__(self, entry: CleaningConfigEntry, action: str) -> None:
        super().__init__(entry, action)
        self.action = action

    @property
    def available(self) -> bool:
        return self.tracker.current_day() is not None

    async def async_press(self) -> None:
        if day := self.tracker.current_day():
            if self.action == "confirm":
                await self.tracker.async_confirm(day)
            else:
                await self.tracker.async_dismiss(day)
