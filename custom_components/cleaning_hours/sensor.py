"""Payout for the current pay period, and the visit waiting for review."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import logic
from .entity import TrackerEntity
from .tracker import CleaningConfigEntry

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CleaningConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([Payout(entry, "payout"), Proposal(entry, "proposal")])


class Payout(TrackerEntity, SensorEntity):
    """What is owed on the coming payday."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "EUR"

    @property
    def native_value(self) -> float:
        euros: float = self.tracker.payout()["euros"]
        return euros

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        p = self.tracker.payout()
        return {
            **p,
            "confirmed_hours": round(p["confirmed_minutes"] / 60, 2),
            "estimate_hours": round(p["estimate_minutes"] / 60, 2),
        }


class Proposal(TrackerEntity, SensorEntity):
    """State like '2026-10-21 09:31–15:31 (6.00 h)', or 'none'."""

    @property
    def native_value(self) -> str:
        day = self.tracker.current_day()
        if day is None:
            return "none"
        times = self.tracker.times(self.tracker.visits[day])
        if not times:
            return f"{day} departure missing"
        hours = logic.minutes_between(*times) / 60
        return f"{day} {times[0][11:16]}–{times[1][11:16]} ({hours:.2f} h)"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        day = self.tracker.current_day()
        return {
            "date": day,
            "pending": sum(v["status"] == "proposed" for v in self.tracker.visits.values()),
            "warnings": self.tracker.warnings(day, self.tracker.visits[day]) if day else [],
        }
