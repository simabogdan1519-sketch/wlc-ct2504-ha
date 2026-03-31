"""DataUpdateCoordinator for Cisco WLC CT2504."""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    DEFAULT_SCAN_INTERVAL,
    AP_STATUS_MAP,
    SSID_SECURITY_MAP,
    SSID_BAND_MAP,
    OID_SYS_DESCR, OID_SYS_UPTIME, OID_SYS_NAME, OID_SERIAL,
    OID_CPU, OID_MEM_FREE, OID_MEM_TOTAL, OID_FLASH, OID_TEMPERATURE,
    OID_MGMT_IP, OID_AP_MGR_IP, OID_RF_COUNTRY, OID_CAPWAP,
    OID_CLIENTS_TOTAL,
    OID_AP_NAME, OID_AP_STATUS, OID_AP_MODEL, OID_AP_IP, OID_AP_CLIENTS,
    OID_AP_CHANNEL, OID_AP_TXPOWER, OID_AP_CLIENTS_RADIO,
    OID_SSID_NAME, OID_SSID_CLIENTS, OID_SSID_VLAN,
    OID_SSID_SECURITY, OID_SSID_BAND, OID_SSID_STATUS,
)
from .snmp_client import SnmpClient

_LOGGER = logging.getLogger(__name__)


def _parse_firmware(sys_descr: str) -> str:
    """Extract firmware version from sysDescr string.

    HA states are limited to 255 chars. sysDescr is multiline and often
    several hundred bytes — always extract just the version number.
    The raw value may arrive as a hex string (0x...) from pysnmp when
    the OctetString contains non-ASCII bytes (CRLF etc.).
    """
    if not sys_descr:
        return "Unknown"
    # pysnmp sometimes returns hex-encoded strings starting with 0x
    if sys_descr.startswith("0x"):
        try:
            sys_descr = bytes.fromhex(sys_descr[2:]).decode("ascii", errors="replace")
        except Exception:
            pass
    match = re.search(r"Version\s+([\d.]+)", sys_descr)
    if match:
        return match.group(1)[:50]  # version string only, max 50 chars
    # Fallback: first non-empty line, truncated
    first_line = sys_descr.split("\n")[0].strip()[:50]
    return first_line or "Unknown"


def _parse_uptime(ticks_str: str) -> dict:
    """Convert SNMP TimeTicks (centiseconds) to human readable + seconds."""
    try:
        ticks = int(ticks_str)
        secs = ticks // 100
    except (ValueError, TypeError):
        return {"raw": ticks_str, "seconds": 0, "formatted": "—"}
    d = secs // 86400
    h = (secs % 86400) // 3600
    m = (secs % 3600) // 60
    formatted = f"{d}d {h}h {m}m" if d > 0 else f"{h}h {m}m"
    return {"raw": ticks_str, "seconds": secs, "formatted": formatted}


def _safe_int(val: str | None, default: int = 0) -> int:
    try:
        return int(val) if val is not None else default
    except (ValueError, TypeError):
        return default


def _safe_float(val: str | None, default: float = 0.0) -> float:
    try:
        return float(val) if val is not None else default
    except (ValueError, TypeError):
        return default


class WlcDataCoordinator(DataUpdateCoordinator):
    """Fetches and caches all WLC SNMP data."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: SnmpClient,
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
        scan_interval_clients: int = 15,
        ap_indexes: list[int] | None = None,
        ssid_indexes: list[int] | None = None,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=min(scan_interval, scan_interval_clients)),
        )
        self._client = client
        self._scan_interval = scan_interval
        self._scan_interval_clients = scan_interval_clients
        self._ap_indexes: list[int] = ap_indexes or []
        self._ssid_indexes: list[int] = ssid_indexes or []
        self._slow_counter = 0

    # ── DISCOVERY ────────────────────────────────────────────────

    async def discover(self) -> tuple[list[int], list[int]]:
        """Walk AP and SSID tables to find all indexes. Returns (ap_indexes, ssid_indexes)."""
        _LOGGER.info("WLC: Starting SNMP discovery...")

        ap_names, ssid_names = await asyncio.gather(
            self._client.walk(OID_AP_NAME),
            self._client.walk(OID_SSID_NAME),
        )

        # AP indexes: suffix is just the integer index
        ap_indexes = sorted(
            [int(k) for k in ap_names if k.isdigit()],
        )

        # SSID indexes
        ssid_indexes = sorted(
            [int(k) for k in ssid_names if k.isdigit()],
        )

        _LOGGER.info(
            "WLC discovery: found %d APs %s, %d SSIDs %s",
            len(ap_indexes), ap_indexes,
            len(ssid_indexes), ssid_indexes,
        )

        self._ap_indexes = ap_indexes
        self._ssid_indexes = ssid_indexes
        return ap_indexes, ssid_indexes

    # ── MAIN UPDATE ──────────────────────────────────────────────

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch all data from WLC via SNMP."""
        self._slow_counter += 1
        do_slow = (self._slow_counter % max(1, self._scan_interval // 15)) == 0

        try:
            data = await self._fetch_all(do_slow)
        except Exception as err:
            raise UpdateFailed(f"WLC SNMP error: {err}") from err

        return data

    async def _fetch_all(self, do_slow: bool) -> dict[str, Any]:
        # ── Fast OIDs (every poll) ────────────────────────────
        fast_oids = [
            OID_CPU,
            OID_MEM_FREE,
            OID_MEM_TOTAL,
            OID_TEMPERATURE,
            OID_CLIENTS_TOTAL,
        ]

        # ── Slow OIDs (every ~5min) ───────────────────────────
        slow_oids = [
            OID_SYS_DESCR,
            OID_SYS_UPTIME,
            OID_SYS_NAME,
            OID_SERIAL,
            OID_FLASH,
            OID_MGMT_IP,
            OID_AP_MGR_IP,
            OID_RF_COUNTRY,
            OID_CAPWAP,
        ]

        oids_to_fetch = fast_oids + (slow_oids if do_slow else [])

        # ── Per-AP OIDs ───────────────────────────────────────
        ap_fast_oids: dict[str, str] = {}  # key → oid
        ap_slow_oids: dict[str, str] = {}

        for idx in self._ap_indexes:
            ap_fast_oids[f"ap_{idx}_status"]  = f"{OID_AP_STATUS}.{idx}"
            ap_fast_oids[f"ap_{idx}_clients"] = f"{OID_AP_CLIENTS}.{idx}"
            ap_fast_oids[f"ap_{idx}_cli_24"]  = f"{OID_AP_CLIENTS_RADIO}.{idx}.0"
            ap_fast_oids[f"ap_{idx}_cli_5"]   = f"{OID_AP_CLIENTS_RADIO}.{idx}.1"
            if do_slow:
                ap_slow_oids[f"ap_{idx}_name"]    = f"{OID_AP_NAME}.{idx}"
                ap_slow_oids[f"ap_{idx}_model"]   = f"{OID_AP_MODEL}.{idx}"
                ap_slow_oids[f"ap_{idx}_ip"]      = f"{OID_AP_IP}.{idx}"
                ap_slow_oids[f"ap_{idx}_ch24"]    = f"{OID_AP_CHANNEL}.{idx}.0"
                ap_slow_oids[f"ap_{idx}_ch5"]     = f"{OID_AP_CHANNEL}.{idx}.1"
                ap_slow_oids[f"ap_{idx}_tx24"]    = f"{OID_AP_TXPOWER}.{idx}.0"
                ap_slow_oids[f"ap_{idx}_tx5"]     = f"{OID_AP_TXPOWER}.{idx}.1"

        # ── Per-SSID OIDs ─────────────────────────────────────
        ssid_fast_oids: dict[str, str] = {}
        ssid_slow_oids: dict[str, str] = {}

        for idx in self._ssid_indexes:
            ssid_fast_oids[f"ssid_{idx}_clients"] = f"{OID_SSID_CLIENTS}.{idx}"
            if do_slow:
                ssid_slow_oids[f"ssid_{idx}_name"]     = f"{OID_SSID_NAME}.{idx}"
                ssid_slow_oids[f"ssid_{idx}_vlan"]     = f"{OID_SSID_VLAN}.{idx}"
                ssid_slow_oids[f"ssid_{idx}_security"] = f"{OID_SSID_SECURITY}.{idx}"
                ssid_slow_oids[f"ssid_{idx}_band"]     = f"{OID_SSID_BAND}.{idx}"

        # ── Fetch in parallel ─────────────────────────────────
        all_keyed_oids = {**ap_fast_oids, **ssid_fast_oids}
        if do_slow:
            all_keyed_oids.update(ap_slow_oids)
            all_keyed_oids.update(ssid_slow_oids)

        system_vals, keyed_vals = await asyncio.gather(
            self._client.get_many(oids_to_fetch),
            self._client.get_many(list(all_keyed_oids.values())),
        )

        # Map keyed values back by key
        keyed = {}
        for key, oid in all_keyed_oids.items():
            keyed[key] = keyed_vals.get(oid)

        # ── Parse system data ─────────────────────────────────
        cpu       = _safe_float(system_vals.get(OID_CPU))
        mem_free  = _safe_int(system_vals.get(OID_MEM_FREE))
        mem_total = _safe_int(system_vals.get(OID_MEM_TOTAL))
        mem_pct   = round(((mem_total - mem_free) / mem_total) * 100, 1) if mem_total > 0 else 0.0
        flash     = _safe_float(system_vals.get(OID_FLASH))
        temp      = _safe_float(system_vals.get(OID_TEMPERATURE))
        clients   = _safe_int(system_vals.get(OID_CLIENTS_TOTAL))

        uptime_raw = system_vals.get(OID_SYS_UPTIME)
        uptime = _parse_uptime(uptime_raw) if uptime_raw else {"formatted": "—", "seconds": 0}

        firmware = _parse_firmware(system_vals.get(OID_SYS_DESCR, ""))
        sys_name = system_vals.get(OID_SYS_NAME, "WLC-CT2504")
        serial   = system_vals.get(OID_SERIAL, "—")
        mgmt_ip  = system_vals.get(OID_MGMT_IP, "—")
        ap_mgr   = system_vals.get(OID_AP_MGR_IP, "—")
        capwap_raw = system_vals.get(OID_CAPWAP, "0")
        capwap   = "Enabled" if capwap_raw == "1" else "Disabled"
        rf_country = system_vals.get(OID_RF_COUNTRY, "—")

        # ── Parse AP data ─────────────────────────────────────
        aps: dict[int, dict] = {}
        for idx in self._ap_indexes:
            status_raw = keyed.get(f"ap_{idx}_status", "2")
            aps[idx] = {
                "name":    keyed.get(f"ap_{idx}_name",  f"AP-{idx}"),
                "model":   keyed.get(f"ap_{idx}_model", "—"),
                "ip":      keyed.get(f"ap_{idx}_ip",    "—"),
                "status":  AP_STATUS_MAP.get(status_raw, "down"),
                "clients": _safe_int(keyed.get(f"ap_{idx}_clients")),
                "cli_24":  _safe_int(keyed.get(f"ap_{idx}_cli_24")),
                "cli_5":   _safe_int(keyed.get(f"ap_{idx}_cli_5")),
                "ch24":    keyed.get(f"ap_{idx}_ch24", "—"),
                "ch5":     keyed.get(f"ap_{idx}_ch5",  "—"),
                "tx24":    keyed.get(f"ap_{idx}_tx24", "—"),
                "tx5":     keyed.get(f"ap_{idx}_tx5",  "—"),
            }

        ap_up   = sum(1 for ap in aps.values() if ap["status"] == "associated")
        ap_down = len(aps) - ap_up

        # Clients per radio (aggregate from APs)
        clients_24 = sum(ap["cli_24"] for ap in aps.values())
        clients_5  = sum(ap["cli_5"]  for ap in aps.values())

        # ── Parse SSID data ───────────────────────────────────
        ssids: dict[int, dict] = {}
        for idx in self._ssid_indexes:
            sec_raw  = keyed.get(f"ssid_{idx}_security", "4")
            band_raw = keyed.get(f"ssid_{idx}_band", "0")
            ssids[idx] = {
                "name":     keyed.get(f"ssid_{idx}_name", f"WLAN-{idx}"),
                "clients":  _safe_int(keyed.get(f"ssid_{idx}_clients")),
                "vlan":     keyed.get(f"ssid_{idx}_vlan", "—"),
                "security": SSID_SECURITY_MAP.get(sec_raw, "WPA2"),
                "band":     SSID_BAND_MAP.get(band_raw, "dual"),
            }

        return {
            # System
            "cpu":        cpu,
            "memory":     mem_pct,
            "flash":      flash,
            "temperature": temp,
            "uptime":     uptime,
            "firmware":   firmware,
            "sys_name":   sys_name,
            "serial":     serial,
            "mgmt_ip":    mgmt_ip,
            "ap_mgr_ip":  ap_mgr,
            "capwap":     capwap,
            "rf_country": rf_country,
            # Clients
            "clients_total": clients,
            "clients_24":    clients_24,
            "clients_5":     clients_5,
            # APs
            "ap_total": len(aps),
            "ap_up":    ap_up,
            "ap_down":  ap_down,
            "aps":      aps,
            # SSIDs
            "ssid_total": len(ssids),
            "ssids":      ssids,
        }

    @property
    def ap_indexes(self) -> list[int]:
        return self._ap_indexes

    @property
    def ssid_indexes(self) -> list[int]:
        return self._ssid_indexes
