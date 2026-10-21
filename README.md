# Cleaning Hours

A Home Assistant integration that tracks the hours of a cleaner from the doorbell, the private
door contact and a UniFi Protect camera. Every visit is **proposed** with camera snapshots, a
household member **confirms** it with one tap, and the integration works out what is owed on
payday. Terms used here are defined in [GLOSSARY.md](GLOSSARY.md).

## Installation

### HACS (recommended)

[![Open your Home Assistant instance and add this repository to HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=ChristophWeigert&repository=iris&category=integration)

1. Click the button above (or in HACS: ⋮ → *Custom repositories* → add
   `https://github.com/ChristophWeigert/iris`, type *Integration*).
2. Download **Cleaning Hours** in HACS and restart Home Assistant.
3. Add the integration:

[![Open your Home Assistant instance and start setting up Cleaning Hours.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=cleaning_hours)

### Manual

Copy `custom_components/cleaning_hours` into `<config>/custom_components/`, restart Home
Assistant, then add the integration with the button above or via
*Settings → Devices & services → Add integration → Cleaning Hours*.

### Requirements

- Home Assistant 2026.10 or newer with the recorder (default 10 days of history is enough).
- A doorbell `binary_sensor` that turns on when rung, and a door contact `binary_sensor`.
- Optional but recommended: the **UniFi Protect** integration. Snapshots come from the camera
  that owns the doorbell sensor and the vehicle sensor.
- Optional: the **Google Sheets** integration, for a row per confirmed visit.
- The **Home Assistant Companion app** for actionable notifications.

## Configuration

| Field | Description |
|---|---|
| Doorbell ring | Turns on when the cleaner rings; its camera takes the arrival snapshot. |
| Private door contact | The door the cleaner uses (on = open). |
| Front-yard vehicle detection | A hint only (🚗); its camera takes the departure car snapshot. |
| Notify service | Reaches every reviewer, e.g. a notify group like `notify.christoph_und_katharina`. |
| Dashboard path | Opened by the notification's *Open* button. |
| Google Sheets log | Optional Google Sheets config entry. |
| Worksheet | Tab inside the sheet, default `Visits`. |

All of it can be changed later via *Reconfigure*. After setup, set **Hourly rate** once.

## How it works

- **Scan** at 17:00 and again at 22:00 (catch-up). The day's recorder history is read:
  - an **arrival** is a doorbell ring followed by the private door opening within 2 minutes;
  - **departure candidates** are later private-door openings; paid time ends when the door closes;
  - a candidate gets 🚗 when the vehicle sensor fired (up to 30 min before the ring, or 5 min after
    a departure opening) and 🚗 candidates are preselected.
- Scanning is idempotent: one visit per day, reviewed visits are never changed, one notification
  per visit.
- **Review**: the notification shows the time span and warnings (*not expected day*, *no car*,
  *no departure*) with **Confirm**, **Dismiss** and **Open**.
- **Pay period** runs from the day after one month's last Wednesday through the next month's last
  Wednesday (payday). The payday visit is paid as an **estimate** (average of the last 4 confirmed
  visits, or set by hand); once confirmed, a difference over €10 becomes a **correction** on the
  next payout.

## Entities

| Entity | Purpose |
|---|---|
| `sensor.cleaning_hours_proposal` | Visit waiting for review, with `warnings` and `pending`. |
| `sensor.cleaning_hours_payout` | Euros owed on the coming payday, with a breakdown. |
| `select.cleaning_hours_arrival` / `_departure` | Pick another candidate. |
| `button.cleaning_hours_confirm` / `_dismiss` | Review the visit. |
| `image.cleaning_hours_arrival` / `_departure_door` / `_departure_car` | Protect snapshots 5 s after the door opened. |
| `number.cleaning_hours_hourly_rate` / `_payday_estimate` | Settings. |

## Actions

| Action | Fields | Does |
|---|---|---|
| `cleaning_hours.scan` | `date` (default today) | Scan a day still in the recorder history. Safe to repeat. |
| `cleaning_hours.confirm` | `date` | Confirm that day's proposed visit. |
| `cleaning_hours.dismiss` | `date` | Mark it as not a visit. |
| `cleaning_hours.add_visit` | `date`, `start`, `end` | Enter a confirmed visit by hand. |

## Example dashboard

```yaml
title: Cleaning
views:
  - path: cleaning
    cards:
      - type: entities
        entities:
          - sensor.cleaning_hours_proposal
          - select.cleaning_hours_arrival
          - select.cleaning_hours_departure
          - button.cleaning_hours_confirm
          - button.cleaning_hours_dismiss
      - type: picture-entity
        entity: image.cleaning_hours_arrival
      - type: picture-entity
        entity: image.cleaning_hours_departure_door
      - type: picture-entity
        entity: image.cleaning_hours_departure_car
      - type: entities
        entities:
          - sensor.cleaning_hours_payout
          - number.cleaning_hours_payday_estimate
          - number.cleaning_hours_hourly_rate
```

## Use cases

- Pay a weekly cleaner by the hour without writing times down.
- Check a disputed time against the camera snapshot of that moment.
- Keep a shareable log of every visit in Google Sheets.

## Known limitations

- Only one proposal is shown on the dashboard at a time (the oldest).
- Snapshots use the UniFi Protect integration's internal API and may break after a Protect update.
- Visits older than the recorder history can only be added by hand.
- Edits made directly in the Google Sheet are not read back.

## Troubleshooting

- **No visit found:** run `cleaning_hours.scan` for the day and check the doorbell and door history:
  the door must open within 2 minutes after the ring.
- **No snapshot:** the doorbell and vehicle sensors must belong to UniFi Protect devices, and
  Protect must still have the recording.
- **No notification:** check the notify service in *Reconfigure*; failures are logged.
- Download diagnostics from the integration page when reporting an issue.

## Removal

*Settings → Devices & services → Cleaning Hours → ⋮ → Delete*, then remove it in HACS (or delete
`custom_components/cleaning_hours`) and restart.

## Development

```bash
pip install -r requirements_test.txt
pytest --cov          # needs Linux/macOS or Docker (Home Assistant does not run on Windows)
mypy
ruff check .
```
