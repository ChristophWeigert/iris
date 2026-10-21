"""Tests for the pure visit/pay logic."""

from datetime import date, datetime

from custom_components.cleaning_hours import logic


def t(hhmm: str) -> datetime:
    return datetime.fromisoformat(f"2026-10-21T{hhmm}:00+02:00")


DOOR = [
    (t("07:00"), False),
    (t("08:00"), True), (t("08:01"), False),   # parcel: ring + family opens, no car
    (t("09:31"), True), (t("09:32"), False),   # cleaner arrives, car seen 20 min before ring
    (t("12:00"), True), (t("12:01"), False),   # she takes rubbish out
    (t("15:30"), True), (t("15:31"), False),   # she leaves, car moves
    (t("16:10"), True), (t("16:11"), False),   # family comes home
]
CARS = [t("09:10"), t("15:33")]


def test_arrival_prefers_ring_with_car():
    doors = logic.door_periods(DOOR)
    cands = logic.arrival_candidates([t("07:59"), t("09:30")], doors, CARS)
    assert [c["time"][11:16] for c in cands] == ["08:00", "09:31"]
    assert cands[logic.preselect(cands, last=False)]["time"][11:16] == "09:31"


def test_departure_prefers_car_over_last_opening():
    doors = logic.door_periods(DOOR)
    cands = logic.departure_candidates(doors, t("09:31"), CARS)
    assert [c["time"][11:16] for c in cands] == ["12:01", "15:31", "16:11"]
    pick = cands[logic.preselect(cands, last=True)]
    assert pick["time"][11:16] == "15:31"
    assert logic.minutes_between(t("09:31").isoformat(), pick["time"]) == 360


def test_departure_without_car_takes_last_and_skips_open_door():
    doors = logic.door_periods(DOOR + [(t("16:30"), True)])  # still open: not a candidate
    cands = logic.departure_candidates(doors, t("09:31"), [])
    assert cands[logic.preselect(cands, last=True)]["time"][11:16] == "16:11"


def test_rising_edges_ignore_initial_on():
    changes = [(t("07:00"), True), (t("07:01"), False), (t("09:30"), True), (t("09:31"), False)]
    assert logic.rising_edges(changes) == [t("09:30")]


def test_pay_periods():
    assert logic.last_wednesday(2026, 10) == date(2026, 10, 28)
    assert logic.period_end(date(2026, 10, 28)) == date(2026, 10, 28)
    assert logic.period_end(date(2026, 10, 29)) == date(2026, 11, 25)
    assert logic.period_end(date(2026, 12, 31)) == date(2027, 1, 27)
    assert logic.period_start(date(2026, 11, 25)) == date(2026, 10, 29)


def v(minutes):
    return {"status": "confirmed", "minutes": minutes}


def test_payout_with_estimate_and_correction():
    visits = {
        "2026-09-02": v(240), "2026-09-09": v(240), "2026-09-16": v(240), "2026-09-23": v(240),
        "2026-09-30": v(360),  # payday visit: estimate was 240, two hours more
        "2026-10-07": v(240), "2026-10-14": {"status": "dismissed"},
    }
    p = logic.payout(visits, date(2026, 10, 28), {}, rate=15)
    assert p["confirmed_minutes"] == 240
    assert p["estimate_minutes"] == 270  # avg of 09-16, 09-23, 09-30, 10-07
    assert p["correction_eur"] == 30.0
    assert p["euros"] == round(510 / 60 * 15 + 30, 2)


def test_small_correction_is_dropped_and_override_wins():
    visits = {"2026-09-23": v(240), "2026-09-30": v(270)}  # +30 min at 15 €/h = 7.50 €
    assert logic.correction_eur(visits, date(2026, 9, 30), {}, 15) == 0.0
    assert logic.estimate_minutes(visits, date(2026, 10, 28), {"2026-10-28": 300}) == 300
