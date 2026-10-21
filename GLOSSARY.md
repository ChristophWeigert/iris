# Cleaning Hours

Tracks how long the cleaner is at the house, so the monthly cleaning fee can be paid on confirmed hours.

## Language

**Cleaner**:
The person whose time at the house is paid by the hour.
_Avoid_: Maid, helper, "she"

**Visit**:
One stay of the cleaner at the house, from arrival to departure.
_Avoid_: Session, shift, appointment

**Reviewer**:
A household member (either partner) who can confirm or correct a visit.
_Avoid_: Supervisor, admin, owner

**Proposed visit**:
A visit derived from the sensors and camera, shown to a reviewer with camera snapshots of its arrival and departure.
_Avoid_: Draft, detected visit, suggestion

**Departure candidate**:
A private-door opening after arrival; one of them is the visit's departure, picked by a reviewer.
_Avoid_: Exit event, leave time

**Confirmed visit**:
A visit whose times count towards pay, either accepted automatically or approved by a reviewer.
_Avoid_: Approved visit, final visit

**Pay period**:
The stretch from the day after one month's last Wednesday through the next month's last Wednesday (payday).
_Avoid_: Billing month, cycle

**Payday estimate**:
The rough guess of hours for the visit on payday itself, paid before that visit is confirmed.
_Avoid_: Advance, prepayment

**Correction**:
The difference between the payday estimate and that visit's confirmed hours, added to or deducted from the next pay period. Only made when it exceeds the tolerance (about €10).
_Avoid_: Adjustment, carry-over

**Private door**:
The family's front door, which the cleaner uses.
_Avoid_: Front door, house door, Haustür

**Practice door**:
The separate entrance for the medical practice's patients; never used by the cleaner.
_Avoid_: Second door, side door

**Expected day**:
The weekday the cleaner usually comes (Wednesday). A visit on any other day always needs a reviewer.
_Avoid_: Cleaning day, schedule
