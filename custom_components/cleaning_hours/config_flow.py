"""UI setup and reconfiguration."""

from __future__ import annotations

from datetime import time
from typing import Any

import probatio as vol  # HA replaced voluptuous with probatio (same API)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import Platform
from homeassistant.helpers import selector

from .const import (
    CONF_DASHBOARD,
    CONF_DOOR,
    CONF_DOORBELL,
    CONF_NOTIFY,
    CONF_SHEET,
    CONF_VEHICLE,
    CONF_WINDOW_END,
    CONF_WINDOW_START,
    CONF_WORKSHEET,
    DEFAULT_DASHBOARD,
    DEFAULT_WINDOW_END,
    DEFAULT_WINDOW_START,
    DEFAULT_WORKSHEET,
    DOMAIN,
)

_SENSOR = selector.EntitySelector(selector.EntitySelectorConfig(domain=Platform.BINARY_SENSOR))


class CleaningHoursConfigFlow(ConfigFlow, domain=DOMAIN):
    """Pick the sensors, the notify service and the optional Google Sheet."""

    VERSION = 1

    def _schema(self, defaults: dict[str, Any]) -> vol.Schema:
        notify = sorted(f"notify.{s}" for s in self.hass.services.async_services_for_domain("notify"))
        return self.add_suggested_values_to_schema(
            vol.Schema(
                {
                    vol.Required(CONF_DOORBELL): _SENSOR,
                    vol.Required(CONF_DOOR): _SENSOR,
                    vol.Required(CONF_VEHICLE): _SENSOR,
                    vol.Required(CONF_NOTIFY): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=notify, custom_value=True)
                    ),
                    vol.Required(CONF_DASHBOARD, default=DEFAULT_DASHBOARD): str,
                    vol.Optional(CONF_SHEET): selector.ConfigEntrySelector(
                        selector.ConfigEntrySelectorConfig(integration="google_sheets")
                    ),
                    vol.Optional(CONF_WORKSHEET, default=DEFAULT_WORKSHEET): str,
                    vol.Required(
                        CONF_WINDOW_START, default=DEFAULT_WINDOW_START
                    ): selector.TimeSelector(),
                    vol.Required(CONF_WINDOW_END, default=DEFAULT_WINDOW_END): selector.TimeSelector(),
                }
            ),
            defaults,
        )

    def _errors(self, user_input: dict[str, Any]) -> dict[str, str]:
        domain, _, service = user_input[CONF_NOTIFY].partition(".")
        if not self.hass.services.has_service(domain, service):
            return {CONF_NOTIFY: "unknown_service"}
        if time.fromisoformat(user_input[CONF_WINDOW_END]) <= time.fromisoformat(
            user_input[CONF_WINDOW_START]
        ):
            return {CONF_WINDOW_END: "window_end_before_start"}
        return {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None and not (errors := self._errors(user_input)):
            return self.async_create_entry(title="Cleaning Hours", data=user_input)
        return self.async_show_form(
            step_id="user", data_schema=self._schema(user_input or {}), errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()
        if user_input is not None and not (errors := self._errors(user_input)):
            return self.async_update_reload_and_abort(entry, data=user_input)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self._schema(user_input or dict(entry.data)),
            errors=errors,
        )
