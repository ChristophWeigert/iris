"""Constants for Cleaning Hours."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "cleaning_hours"
SIGNAL: Final = f"{DOMAIN}_updated"

CONF_DOORBELL: Final = "doorbell"
CONF_DOOR: Final = "door"
CONF_VEHICLE: Final = "vehicle"
CONF_NOTIFY: Final = "notify"
CONF_DASHBOARD: Final = "dashboard"
CONF_SHEET: Final = "sheet_config_entry"
CONF_WORKSHEET: Final = "worksheet"
CONF_WINDOW_START: Final = "window_start"
CONF_WINDOW_END: Final = "window_end"

DEFAULT_DASHBOARD: Final = "/lovelace/cleaning"
DEFAULT_WORKSHEET: Final = "Visits"
DEFAULT_WINDOW_START: Final = "08:00:00"
DEFAULT_WINDOW_END: Final = "16:00:00"
SCAN_TIMES: Final = ((17, 0), (22, 0))  # she is mostly gone by 15:30; 22:00 is a catch-up
SNAPSHOT_DELAY: Final = timedelta(seconds=5)  # she is in frame a few seconds after the door opens

ACTION_CONFIRM: Final = "CLEANING_CONFIRM"
ACTION_DISMISS: Final = "CLEANING_DISMISS"
