"""Protect snapshots a few seconds after the picked arrival and departure door openings."""

from __future__ import annotations

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import CONF_DOORBELL, CONF_VEHICLE
from .entity import TrackerEntity
from .tracker import CleaningConfigEntry

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CleaningConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(
        [
            Snapshot(hass, entry, "arrival", "arrival", CONF_DOORBELL),
            Snapshot(hass, entry, "departure_door", "departure", CONF_DOORBELL),
            Snapshot(hass, entry, "departure_car", "departure", CONF_VEHICLE),
        ]
    )


class Snapshot(TrackerEntity, ImageEntity):
    """Camera is the device of the configured doorbell or vehicle sensor."""

    def __init__(
        self, hass: HomeAssistant, entry: CleaningConfigEntry, key: str, which: str, camera: str
    ) -> None:
        TrackerEntity.__init__(self, entry, key)
        ImageEntity.__init__(self, hass)
        self.which = which
        self.camera = camera
        self._attr_image_last_updated = dt_util.utcnow()

    def _when(self) -> str | None:
        visit = self.tracker.current()
        if not visit or not visit[self.which]:
            return None
        cand = visit[self.which][visit[f"{self.which}_idx"]]
        when: str = cand.get("opened", cand["time"])  # departure: the opening, not the close
        return when

    @property
    def available(self) -> bool:
        return self._when() is not None

    @callback
    def _updated(self) -> None:
        self._attr_image_last_updated = dt_util.utcnow()
        super()._updated()

    async def async_image(self) -> bytes | None:
        if (when := self._when()) is None:
            return None
        return await self.tracker.async_snapshot(self.tracker.conf[self.camera], when)
