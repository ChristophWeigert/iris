"""Hourly rate, and the payday estimate for the current pay period."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory, UnitOfTime
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
    async_add_entities([Rate(entry, "hourly_rate"), Estimate(entry, "payday_estimate")])


class Rate(TrackerEntity, NumberEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_unit_of_measurement = "EUR/h"
    _attr_native_max_value = 100
    _attr_native_step = 0.5
    _attr_mode = NumberMode.BOX

    @property
    def native_value(self) -> float:
        rate: float = self.tracker.data["rate"]
        return rate

    async def async_set_native_value(self, value: float) -> None:
        await self.tracker.async_set_rate(value)


class Estimate(TrackerEntity, NumberEntity):
    """Hours; setting it overrides the average for this pay period."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_native_max_value = 12
    _attr_native_step = 0.25
    _attr_mode = NumberMode.BOX

    @property
    def native_value(self) -> float:
        minutes: int = self.tracker.payout()["estimate_minutes"]
        return round(minutes / 60, 2)

    async def async_set_native_value(self, value: float) -> None:
        await self.tracker.async_set_estimate(value)
