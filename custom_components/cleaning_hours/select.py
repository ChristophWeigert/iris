"""Pick the arrival and departure of the visit under review."""

from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import TrackerEntity
from .tracker import CleaningConfigEntry

PARALLEL_UPDATES = 0
NONE = "–"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CleaningConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([Pick(entry, "arrival"), Pick(entry, "departure")])


def _label(c: dict[str, Any]) -> str:
    return str(c["time"][11:19]) + (" 🚗" if c["car"] else "")


class Pick(TrackerEntity, SelectEntity):
    """Candidates as times; 🚗 marks a car seen nearby."""

    def __init__(self, entry: CleaningConfigEntry, which: str) -> None:
        super().__init__(entry, which)
        self.which = which

    def _labels(self) -> list[str]:
        visit = self.tracker.current()
        return [_label(c) for c in visit[self.which]] if visit else []

    @property
    def options(self) -> list[str]:
        return self._labels() or [NONE]

    @property
    def current_option(self) -> str:
        visit = self.tracker.current()
        if not visit or not visit[self.which]:
            return NONE
        return _label(visit[self.which][visit[f"{self.which}_idx"]])

    async def async_select_option(self, option: str) -> None:
        if option in (labels := self._labels()):
            await self.tracker.async_select(self.which, labels.index(option))
