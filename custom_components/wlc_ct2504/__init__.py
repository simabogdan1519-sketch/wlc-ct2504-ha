"""Cisco WLC CT2504 Home Assistant Integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    DOMAIN,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL_CLIENTS,
    CONF_COMMUNITY,
    CONF_SCAN_INTERVAL_CLIENTS,
    DEFAULT_COMMUNITY,
)
from .coordinator import WlcDataCoordinator
from .snmp_client import SnmpClient

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up WLC CT2504 from a config entry."""
    host      = entry.data[CONF_HOST]
    community = entry.options.get(CONF_COMMUNITY, entry.data.get(CONF_COMMUNITY, DEFAULT_COMMUNITY))
    port      = entry.data.get(CONF_PORT, DEFAULT_PORT)

    scan_interval         = entry.options.get("scan_interval", DEFAULT_SCAN_INTERVAL)
    scan_interval_clients = entry.options.get(CONF_SCAN_INTERVAL_CLIENTS, DEFAULT_SCAN_INTERVAL_CLIENTS)

    ap_indexes   = entry.data.get("ap_indexes", [])
    ssid_indexes = entry.data.get("ssid_indexes", [])

    client = SnmpClient(host, community, port)


    # Quick connectivity check
    if not await client.test_connection():
        raise ConfigEntryNotReady(f"Cannot connect to WLC at {host}:{port}")

    coordinator = WlcDataCoordinator(
        hass,
        client,
        scan_interval=scan_interval,
        scan_interval_clients=scan_interval_clients,
        ap_indexes=ap_indexes,
        ssid_indexes=ssid_indexes,
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Listen for options updates
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload WLC config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update — reload entry to apply new settings."""
    await hass.config_entries.async_reload(entry.entry_id)
