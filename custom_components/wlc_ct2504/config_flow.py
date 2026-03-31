"""Config flow for Cisco WLC CT2504 integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_COMMUNITY,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL_CLIENTS,
    CONF_COMMUNITY,
    CONF_SNMP_VERSION,
    CONF_SCAN_INTERVAL_CLIENTS,
    SNMP_VERSION_2C,
    SNMP_VERSION_OPTIONS,
)
from .snmp_client import SnmpClient
from .coordinator import WlcDataCoordinator

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_COMMUNITY, default=DEFAULT_COMMUNITY): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=65535)
        ),
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
    }
)


class WlcConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle config flow for WLC CT2504."""

    VERSION = 1

    def __init__(self) -> None:
        self._host: str = ""
        self._community: str = DEFAULT_COMMUNITY
        self._port: int = DEFAULT_PORT
        self._name: str = DEFAULT_NAME
        self._ap_indexes: list[str] = []
        self._ssid_indexes: list[int] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: connection details."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host      = user_input[CONF_HOST].strip()
            community = user_input[CONF_COMMUNITY].strip()
            port      = user_input.get(CONF_PORT, DEFAULT_PORT)
            name      = user_input.get(CONF_NAME, DEFAULT_NAME).strip()

            # Prevent duplicate entries
            await self.async_set_unique_id(f"wlc_{host}")
            self._abort_if_unique_id_configured()

            # Test SNMP connectivity

            client = SnmpClient(host, community, port)
            try:
                ok = await client.test_connection()
                if not ok:
                    errors["base"] = "cannot_connect"
                else:
                    # Run discovery
                    self._host      = host
                    self._community = community
                    self._port      = port
                    self._name      = name

                    self._ap_indexes, self._ssid_indexes = await coordinator.discover()

                    if not self._ap_indexes:
                        errors["base"] = "no_aps_found"
                    else:
                        return await self.async_step_discovery()

            except TimeoutError:
                errors["base"] = "snmp_timeout"
            except Exception as err:
                _LOGGER.exception("Unexpected error during WLC setup: %s", err)
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
            description_placeholders={
                "docs_url": "https://github.com/your-repo/wlc-ct2504-ha"
            },
        )

    async def async_step_discovery(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2: show discovery results and confirm."""
        if user_input is not None:
            return self.async_create_entry(
                title=self._name,
                data={
                    CONF_HOST:      self._host,
                    CONF_COMMUNITY: self._community,
                    CONF_PORT:      self._port,
                    CONF_NAME:      self._name,
                    "ap_indexes":   self._ap_indexes,
                    "ssid_indexes": self._ssid_indexes,
                },
            )

        return self.async_show_form(
            step_id="discovery",
            data_schema=vol.Schema({}),
            description_placeholders={
                "ap_count":   str(len(self._ap_indexes)),
                "ssid_count": str(len(self._ssid_indexes)),
                "ap_list":    ", ".join(str(i) for i in self._ap_indexes[:5]) + ("..." if len(self._ap_indexes) > 5 else ""),
                "ssid_list":  ", ".join(f"WLAN-{i}" for i in self._ssid_indexes),
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> WlcOptionsFlow:
        return WlcOptionsFlow(config_entry)


class WlcOptionsFlow(config_entries.OptionsFlow):
    """Options flow — poll intervals and community."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self._config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    "scan_interval",
                    default=current.get("scan_interval", DEFAULT_SCAN_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=10, max=300)),
                vol.Optional(
                    CONF_SCAN_INTERVAL_CLIENTS,
                    default=current.get(CONF_SCAN_INTERVAL_CLIENTS, DEFAULT_SCAN_INTERVAL_CLIENTS),
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=120)),
                vol.Optional(
                    CONF_COMMUNITY,
                    default=current.get(CONF_COMMUNITY, self._config_entry.data.get(CONF_COMMUNITY, DEFAULT_COMMUNITY)),
                ): str,
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
