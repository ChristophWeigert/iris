"""Holds visits and settings; entities, services and notifications go through here."""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Any

from homeassistant.components.recorder import history
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.recorder import get_instance
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from . import logic
from .const import (
    ACTION_CONFIRM,
    ACTION_DISMISS,
    CONF_DASHBOARD,
    CONF_DOOR,
    CONF_DOORBELL,
    CONF_NOTIFY,
    CONF_SHEET,
    CONF_VEHICLE,
    CONF_WORKSHEET,
    DEFAULT_WORKSHEET,
    DOMAIN,
    SIGNAL,
    SNAPSHOT_DELAY,
)

_LOGGER = logging.getLogger(__name__)

type CleaningConfigEntry = ConfigEntry[Tracker]


async def fetch_changes(
    hass: HomeAssistant, entity_id: str, start: datetime, end: datetime
) -> logic.Changes:
    """On/off changes of one entity from the recorder."""
    states = await get_instance(hass).async_add_executor_job(
        history.state_changes_during_period, hass, start, end, entity_id, True
    )
    return [
        (dt_util.as_local(s.last_changed), s.state == "on")
        for s in states.get(entity_id, [])
        if s.state in ("on", "off")
    ]


class Tracker:
    """Visits, settings and the review workflow."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._store: Store[dict[str, Any]] = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        self.data: dict[str, Any] = {"visits": {}, "rate": 0.0, "estimates": {}}

    @property
    def conf(self) -> dict[str, Any]:
        return {**self.entry.data, **self.entry.options}

    async def async_load(self) -> None:
        if stored := await self._store.async_load():
            self.data = stored

    async def async_save(self) -> None:
        await self._store.async_save(self.data)
        async_dispatcher_send(self.hass, SIGNAL)

    @property
    def visits(self) -> logic.Visits:
        visits: logic.Visits = self.data["visits"]
        return visits

    def current_day(self) -> str | None:
        """Oldest visit still waiting for review."""
        pending = [d for d, v in self.visits.items() if v["status"] == "proposed"]
        return min(pending, default=None)

    def current(self) -> dict[str, Any] | None:
        day = self.current_day()
        return self.visits[day] if day else None

    @staticmethod
    def times(visit: dict[str, Any]) -> tuple[str, str] | None:
        """(start, end) of a visit, or None while no departure is known."""
        if "start" in visit:
            return visit["start"], visit["end"]
        if not visit["departure"]:
            return None
        start = visit["arrival"][visit["arrival_idx"]]["time"]
        return start, visit["departure"][visit["departure_idx"]]["time"]

    def payout(self) -> dict[str, Any]:
        payday = logic.period_end(dt_util.now().date())
        return logic.payout(self.visits, payday, self.data["estimates"], self.data["rate"])

    async def async_set_rate(self, rate: float) -> None:
        self.data["rate"] = rate
        await self.async_save()

    async def async_set_estimate(self, hours: float) -> None:
        payday = logic.period_end(dt_util.now().date()).isoformat()
        self.data["estimates"][payday] = round(hours * 60)
        await self.async_save()

    # --- scanning -------------------------------------------------------

    async def async_scan_today(self, _now: datetime | None = None) -> None:
        await self.async_scan(dt_util.now().date())

    async def _changes(self, key: str, day: date) -> logic.Changes:
        start = dt_util.start_of_local_day(day)
        end = min(start + timedelta(days=1), dt_util.utcnow())
        return await fetch_changes(self.hass, self.conf[key], start, end)

    async def async_scan(self, day: date) -> None:
        """Idempotent: one visit per day; reviewed visits are never touched."""
        key = day.isoformat()
        old = self.visits.get(key)
        if old and old["status"] != "proposed":
            return
        doors = logic.door_periods(await self._changes(CONF_DOOR, day))
        rings = logic.rising_edges(await self._changes(CONF_DOORBELL, day))
        cars = logic.rising_edges(await self._changes(CONF_VEHICLE, day))
        arrivals = logic.arrival_candidates(rings, doors, cars)
        if not arrivals:
            return
        visit: dict[str, Any] = {
            "status": "proposed",
            "notified": bool(old and old["notified"]),
            "arrival": arrivals,
            "arrival_idx": logic.preselect(arrivals, last=False),
            "cars": [c.isoformat() for c in cars],
            "doors": [(o.isoformat(), c and c.isoformat()) for o, c in doors],
        }
        if old and (picked := old["arrival"][old["arrival_idx"]]) in arrivals:
            visit["arrival_idx"] = arrivals.index(picked)  # keep a reviewer's pick
        self._set_departures(visit, keep=old)
        self.visits[key] = visit
        if not visit["notified"]:
            await self._notify(key, visit)
            visit["notified"] = True
        await self.async_save()

    @staticmethod
    def _set_departures(visit: dict[str, Any], keep: dict[str, Any] | None = None) -> None:
        arrival = datetime.fromisoformat(visit["arrival"][visit["arrival_idx"]]["time"])
        doors: logic.Doors = [
            (datetime.fromisoformat(o), datetime.fromisoformat(c) if c else None)
            for o, c in visit["doors"]
        ]
        cars = [datetime.fromisoformat(c) for c in visit["cars"]]
        deps = logic.departure_candidates(doors, arrival, cars)
        visit["departure"] = deps
        visit["departure_idx"] = logic.preselect(deps, last=True) if deps else 0
        if keep and keep["departure"] and (picked := keep["departure"][keep["departure_idx"]]) in deps:
            visit["departure_idx"] = deps.index(picked)

    async def async_select(self, which: str, idx: int) -> None:
        """Reviewer picks a different arrival or departure for the current visit."""
        if (visit := self.current()) is None:
            return
        visit[f"{which}_idx"] = idx
        if which == "arrival":
            self._set_departures(visit)
        await self.async_save()

    # --- review ---------------------------------------------------------

    @staticmethod
    def warnings(day: str, visit: dict[str, Any]) -> list[str]:
        out = []
        if date.fromisoformat(day).weekday() != logic.EXPECTED_WEEKDAY:
            out.append("not_expected_day")
        cars = [visit["arrival"][visit["arrival_idx"]]] + visit["departure"]
        if not any(c["car"] for c in cars):
            out.append("no_car")
        if not visit["departure"]:
            out.append("no_departure")
        return out

    async def _notify(self, day: str, visit: dict[str, Any]) -> None:
        times = self.times(visit)
        if times:
            hours = logic.minutes_between(*times) / 60
            text = f"{times[0][11:16]}–{times[1][11:16]}, {hours:.2f} h"
        else:
            text = "Departure not found yet"
        if warn := self.warnings(day, visit):
            text += " ⚠ " + ", ".join(w.replace("_", " ") for w in warn)
        domain, _, service = self.conf[CONF_NOTIFY].partition(".")
        try:
            await self.hass.services.async_call(
                domain,
                service,
                {
                    "title": f"Cleaning {day}",
                    "message": text,
                    "data": {
                        "image": f"/api/image_proxy/image.{DOMAIN}_arrival",
                        "actions": [
                            {"action": f"{ACTION_CONFIRM}:{day}", "title": "Confirm"},
                            {"action": f"{ACTION_DISMISS}:{day}", "title": "Dismiss"},
                            {"action": "URI", "title": "Open", "uri": self.conf[CONF_DASHBOARD]},
                        ],
                    },
                },
                blocking=True,
            )
        except HomeAssistantError:  # the proposal is saved; the dashboard still shows it
            _LOGGER.exception("Could not send notification for visit %s", day)

    def _pending(self, day: str) -> dict[str, Any]:
        visit = self.visits.get(day)
        if not visit or visit["status"] != "proposed":
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="no_proposed_visit",
                translation_placeholders={"date": day},
            )
        return visit

    async def async_confirm(self, day: str) -> None:
        visit = self._pending(day)
        if not (times := self.times(visit)):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="no_departure",
                translation_placeholders={"date": day},
            )
        visit.update(
            status="confirmed",
            start=times[0],
            end=times[1],
            minutes=logic.minutes_between(*times),
        )
        await self.async_save()
        await self._log_row(day, visit)

    async def async_dismiss(self, day: str) -> None:
        self._pending(day)["status"] = "dismissed"
        await self.async_save()

    async def async_add_manual(self, day: date, start: time, end: time) -> None:
        if end <= start:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="end_before_start"
            )
        tz = dt_util.get_default_time_zone()
        s, e = (datetime.combine(day, t, tz).isoformat() for t in (start, end))
        visit = {
            "status": "confirmed",
            "manual": True,
            "start": s,
            "end": e,
            "minutes": logic.minutes_between(s, e),
        }
        self.visits[day.isoformat()] = visit
        await self.async_save()
        await self._log_row(day.isoformat(), visit)

    async def _log_row(self, day: str, visit: dict[str, Any]) -> None:
        """Append a confirmed visit (and any payday correction) to the Google Sheet log."""
        if not (sheet := self.conf.get(CONF_SHEET)):
            return
        rate = self.data["rate"]
        rows: list[dict[str, Any]] = [
            {
                "Date": day,
                "Arrival": visit["start"][11:16],
                "Departure": visit["end"][11:16],
                "Hours": round(visit["minutes"] / 60, 2),
                "Euros": round(visit["minutes"] / 60 * rate, 2),
            }
        ]
        d = date.fromisoformat(day)
        if d == logic.period_end(d) and (
            corr := logic.correction_eur(self.visits, d, self.data["estimates"], rate)
        ):
            rows.append({"Date": day, "Note": "Correction for next pay period", "Euros": corr})
        try:
            await self.hass.services.async_call(
                "google_sheets",
                "append_sheet",
                {
                    "config_entry": sheet,
                    "worksheet": self.conf.get(CONF_WORKSHEET) or DEFAULT_WORKSHEET,
                    "data": rows,
                },
                blocking=True,
            )
        except HomeAssistantError:  # the visit is saved; the sheet is only a log
            _LOGGER.exception("Could not append visit %s to the Google Sheet", day)

    # --- snapshots ------------------------------------------------------

    async def async_snapshot(self, entity_id: str, when: str) -> bytes | None:
        """Protect recording snapshot from the camera owning entity_id, shortly after `when`."""
        ent = er.async_get(self.hass).async_get(entity_id)
        if not ent or not ent.device_id:
            return None
        device = dr.async_get(self.hass).async_get(ent.device_id, include_child_devices=False)
        if device is None:
            return None
        macs = [c[1] for c in device.connections if c[0] == dr.CONNECTION_NETWORK_MAC]
        # shortcut: uses the UniFi Protect integration's internals (runtime_data.api);
        # switch to a public API if one appears.
        for entry in self.hass.config_entries.async_loaded_entries("unifiprotect"):
            bootstrap = entry.runtime_data.api.bootstrap
            for mac in macs:
                if (cam := bootstrap.get_device_from_mac(mac)) is not None:
                    snapshot: bytes | None = await cam.get_snapshot(
                        dt=datetime.fromisoformat(when) + SNAPSHOT_DELAY
                    )
                    return snapshot
        return None
