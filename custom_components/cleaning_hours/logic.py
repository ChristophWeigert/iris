"""Visit and pay logic. No Home Assistant imports, so it can be tested on its own."""

from __future__ import annotations

import calendar
from datetime import date, datetime, time, timedelta
from typing import Any

RING_TO_DOOR = timedelta(minutes=2)
CAR_BEFORE_RING = timedelta(minutes=30)  # she may sit in the car before ringing
CAR_AFTER_DOOR = timedelta(minutes=5)
EXPECTED_WEEKDAY = calendar.WEDNESDAY
TOLERANCE_EUR = 10.0
ESTIMATE_SAMPLE = 4

type Changes = list[tuple[datetime, bool]]  # (when, is_on), oldest first
type Doors = list[tuple[datetime, datetime | None]]  # (opened, closed)
type Candidate = dict[str, Any]
type Visits = dict[str, dict[str, Any]]


def rising_edges(changes: Changes) -> list[datetime]:
    """Times a sensor switched from off to on."""
    out: list[datetime] = []
    prev: bool | None = None
    for when, on in changes:
        if on and prev is False:
            out.append(when)
        prev = on
    return out


def door_periods(changes: Changes) -> Doors:
    """(opened, closed) per door opening; closed is None while still open."""
    out: Doors = []
    prev: bool | None = None
    for when, on in changes:
        if on and prev is False:
            out.append((when, None))
        elif not on and prev and out and out[-1][1] is None:
            out[-1] = (out[-1][0], when)
        prev = on
    return out


def _car_near(cars: list[datetime], start: datetime, end: datetime) -> bool:
    return any(start <= c <= end for c in cars)


def arrival_candidates(
    rings: list[datetime], doors: Doors, cars: list[datetime]
) -> list[Candidate]:
    """Private-door openings that follow a doorbell ring within RING_TO_DOOR."""
    out: list[Candidate] = []
    for opened, _closed in doors:
        ring = next((r for r in rings if r <= opened <= r + RING_TO_DOOR), None)
        if ring is not None:
            out.append(
                {
                    "time": opened.isoformat(),
                    "car": _car_near(cars, ring - CAR_BEFORE_RING, opened),
                }
            )
    return out


def departure_candidates(
    doors: Doors, arrival: datetime, cars: list[datetime]
) -> list[Candidate]:
    """Closed private-door openings after arrival; paid time ends at the close."""
    return [
        {
            "opened": o.isoformat(),
            "time": c.isoformat(),
            "car": _car_near(cars, o, o + CAR_AFTER_DOOR),
        }
        for o, c in doors
        if o > arrival and c is not None
    ]


def in_window(cand: Candidate, window: tuple[time, time]) -> bool:
    """Departures count from the door opening, arrivals from their time."""
    when: str = cand.get("opened") or cand["time"]
    return window[0] <= datetime.fromisoformat(when).time() <= window[1]


def preselect(cands: list[Candidate], *, last: bool, window: tuple[time, time]) -> int:
    """Inside the visit window first (all if none is), then a car seen,
    then the first (arrival) or last (departure)."""
    idx = [i for i, c in enumerate(cands) if in_window(c, window)] or list(range(len(cands)))
    idx = [i for i in idx if cands[i]["car"]] or idx
    return idx[-1] if last else idx[0]


def minutes_between(start: str, end: str) -> int:
    """Whole minutes between two ISO timestamps."""
    delta = datetime.fromisoformat(end) - datetime.fromisoformat(start)
    return round(delta.total_seconds() / 60)


# --- pay periods -----------------------------------------------------------


def last_wednesday(year: int, month: int) -> date:
    """Payday: the last Wednesday of a month."""
    last = date(year, month, calendar.monthrange(year, month)[1])
    return last - timedelta(days=(last.weekday() - EXPECTED_WEEKDAY) % 7)


def period_end(d: date) -> date:
    """Payday of the pay period containing d."""
    lw = last_wednesday(d.year, d.month)
    if d <= lw:
        return lw
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return last_wednesday(y, m)


def period_start(end: date) -> date:
    """First day of the pay period ending on payday `end`."""
    prev = end.replace(day=1) - timedelta(days=1)
    return last_wednesday(prev.year, prev.month) + timedelta(days=1)


def _confirmed(visits: Visits) -> dict[date, int]:
    return {
        date.fromisoformat(d): int(v["minutes"])
        for d, v in visits.items()
        if v["status"] == "confirmed"
    }


def estimate_minutes(visits: Visits, payday: date, overrides: dict[str, int]) -> int:
    """Payday estimate: override, else average of the last confirmed visits before payday."""
    if payday.isoformat() in overrides:
        return overrides[payday.isoformat()]
    before = [m for d, m in sorted(_confirmed(visits).items()) if d < payday]
    sample = before[-ESTIMATE_SAMPLE:]
    return round(sum(sample) / len(sample)) if sample else 0


def correction_eur(
    visits: Visits, payday: date, overrides: dict[str, int], rate: float
) -> float:
    """Confirmed minus estimated pay for a payday visit; 0 within tolerance or unconfirmed."""
    actual = _confirmed(visits).get(payday)
    if actual is None:
        return 0.0
    diff = (actual - estimate_minutes(visits, payday, overrides)) / 60 * rate
    return round(diff, 2) if abs(diff) > TOLERANCE_EUR else 0.0


def payout(
    visits: Visits, payday: date, overrides: dict[str, int], rate: float
) -> dict[str, Any]:
    """Owed on payday: confirmed visits before it, the payday estimate,
    and the correction from the previous payday."""
    start = period_start(payday)
    minutes = sum(m for d, m in _confirmed(visits).items() if start <= d < payday)
    est = estimate_minutes(visits, payday, overrides)
    corr = correction_eur(visits, start - timedelta(days=1), overrides, rate)
    return {
        "period_start": start.isoformat(),
        "payday": payday.isoformat(),
        "confirmed_minutes": minutes,
        "estimate_minutes": est,
        "correction_eur": corr,
        "euros": round((minutes + est) / 60 * rate + corr, 2),
    }
