"""DataUpdateCoordinator for Cisco WLC CT2504.

NOTE on AP indexes:
  The CT2504 uses the AP's MAC address as the SNMP table index,
  encoded as 6 decimal octets separated by dots.
  Example: '0.167.66.179.98.192' = MAC 00:A7:42:B3:62:C0

  We store these MAC-suffix strings as AP keys throughout.
  For entity/sensor naming we convert to a safe slug: mac_00a742b362c0
"""
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
    OID_SSID_SECURITY, OID_SSID_BAND,
)
from .snmp_client import SnmpClient

_LOGGER = logging.getLogger(__name__)


# ── HELPERS ───────────────────────────────────────────────────────────────────

def mac_suffix_to_slug(suffix: str) -> str:
    """Convert '0.167.66.179.98.192' → 'mac_00a742b362c0' (safe entity slug)."""
    try:
        octets = [int(x) for x in suffix.split('.')]
        return 'mac_' + ''.join(f'{o:02x}' for o in octets)
    except Exception:
        # fallback: replace dots with underscores
        return 'ap_' + suffix.replace('.', '_')


def mac_suffix_to_display(suffix: str) -> str:
    """Convert '0.167.66.179.98.192' → '00:A7:42:B3:62:C0' (human readable)."""
    try:
        octets = [int(x) for x in suffix.split('.')]
        return ':'.join(f'{o:02X}' for o in octets)
    except Exception:
        return suffix


def _parse_firmware(sys_descr: str) -> str:
    """Extract firmware version string from sysDescr, max 50 chars."""
    if not sys_descr:
        return "Unknown"
    if sys_descr.startswith("0x"):
        try:
            sys_descr = bytes.fromhex(sys_descr[2:]).decode("ascii", errors="replace")
        except Exception:
            pass
    match = re.search(r"Version\s+([\d.]+)", sys_descr)
    if match:
        return match.group(1)[:50]
    return sys_descr.split("\n")[0].strip()[:50] or "Unknown"


def _parse_uptime(ticks_str: str) -> dict:
    try:
        secs = int(ticks_str) // 100
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


# ── COORDINATOR ───────────────────────────────────────────────────────────────

class WlcDataCoordinator(DataUpdateCoordinator):
    """Fetches and caches all WLC SNMP data."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: SnmpClient,
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
        scan_interval_clients: int = 15,
        ap_indexes: list[str] | None = None,   # MAC-suffix strings
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
        self._ap_indexes: list[str] = ap_indexes or []
        self._ssid_indexes: list[int] = ssid_indexes or []
        self._slow_counter = 0

    # ── DISCOVERY ─────────────────────────────────────────────────

    async def discover(self) -> tuple[list[str], list[int]]:
        """Walk AP and SSID tables. Returns (ap_mac_suffixes, ssid_int_indexes)."""
        _LOGGER.info("WLC: Starting SNMP discovery...")

        ap_names, ssid_names = await asyncio.gather(
            self._client.walk(OID_AP_NAME),
            self._client.walk(OID_SSID_NAME),
        )

        _LOGGER.debug("WLC raw AP walk result: %s", ap_names)
        _LOGGER.debug("WLC raw SSID walk result: %s", ssid_names)

        # AP suffixes: accept any non-empty key (MAC-encoded or integer)
        ap_indexes: list[str] = [k for k in ap_names if k]

        # SSID suffixes: integer WLAN IDs
        ssid_indexes: list[int] = sorted(
            [int(k) for k in ssid_names if k.isdigit()]
        )

        _LOGGER.info(
            "WLC discovery: %d APs found: %s | %d SSIDs: %s",
            len(ap_indexes), ap_indexes,
            len(ssid_indexes), ssid_indexes,
        )

        self._ap_indexes = ap_indexes
        self._ssid_indexes = ssid_indexes
        return ap_indexes, ssid_indexes

    # ── MAIN UPDATE ───────────────────────────────────────────────

    async def _async_update_data(self) -> dict[str, Any]:
        self._slow_counter += 1
        do_slow = (self._slow_counter % max(1, self._scan_interval // 15)) == 0
        try:
            return await self._fetch_all(do_slow)
        except Exception as err:
            raise UpdateFailed(f"WLC SNMP error: {err}") from err

    async def _fetch_all(self, do_slow: bool) -> dict[str, Any]:
        # ── Fast system OIDs ──────────────────────────────────
        fast_oids = [OID_CPU, OID_MEM_FREE, OID_MEM_TOTAL, OID_TEMPERATURE, OID_CLIENTS_TOTAL]
        slow_oids = [OID_SYS_DESCR, OID_SYS_UPTIME, OID_SYS_NAME, OID_SERIAL,
                     OID_FLASH, OID_MGMT_IP, OID_AP_MGR_IP, OID_RF_COUNTRY, OID_CAPWAP]
        oids_to_fetch = fast_oids + (slow_oids if do_slow else [])

        # ── Per-AP OIDs — suffix is the MAC string ─────────────
        ap_keyed: dict[str, str] = {}  # internal_key → full OID
        for suffix in self._ap_indexes:
            slug = mac_suffix_to_slug(suffix)
            ap_keyed[f"{slug}_status"]  = f"{OID_AP_STATUS}.{suffix}"
            ap_keyed[f"{slug}_clients"] = f"{OID_AP_CLIENTS}.{suffix}"
            ap_keyed[f"{slug}_cli_24"]  = f"{OID_AP_CLIENTS_RADIO}.{suffix}.0"
            ap_keyed[f"{slug}_cli_5"]   = f"{OID_AP_CLIENTS_RADIO}.{suffix}.1"
            if do_slow:
                ap_keyed[f"{slug}_name"]  = f"{OID_AP_NAME}.{suffix}"
                ap_keyed[f"{slug}_model"] = f"{OID_AP_MODEL}.{suffix}"
                ap_keyed[f"{slug}_ip"]    = f"{OID_AP_IP}.{suffix}"
                ap_keyed[f"{slug}_ch24"]  = f"{OID_AP_CHANNEL}.{suffix}.0"
                ap_keyed[f"{slug}_ch5"]   = f"{OID_AP_CHANNEL}.{suffix}.1"
                ap_keyed[f"{slug}_tx24"]  = f"{OID_AP_TXPOWER}.{suffix}.0"
                ap_keyed[f"{slug}_tx5"]   = f"{OID_AP_TXPOWER}.{suffix}.1"

        # ── Per-SSID OIDs ──────────────────────────────────────
        ssid_keyed: dict[str, str] = {}
        for idx in self._ssid_indexes:
            ssid_keyed[f"ssid_{idx}_clients"] = f"{OID_SSID_CLIENTS}.{idx}"
            if do_slow:
                ssid_keyed[f"ssid_{idx}_name"]     = f"{OID_SSID_NAME}.{idx}"
                ssid_keyed[f"ssid_{idx}_vlan"]     = f"{OID_SSID_VLAN}.{idx}"
                ssid_keyed[f"ssid_{idx}_security"] = f"{OID_SSID_SECURITY}.{idx}"
                ssid_keyed[f"ssid_{idx}_band"]     = f"{OID_SSID_BAND}.{idx}"

        all_keyed = {**ap_keyed, **ssid_keyed}

        # ── Fetch in parallel ──────────────────────────────────
        system_vals, keyed_vals = await asyncio.gather(
            self._client.get_many(oids_to_fetch),
            self._client.get_many(list(all_keyed.values())),
        )

        # Map back internal_key → value
        kv: dict[str, str | None] = {}
        for key, oid in all_keyed.items():
            kv[key] = keyed_vals.get(oid)

        # ── Parse system ───────────────────────────────────────
        cpu      = _safe_float(system_vals.get(OID_CPU))
        mem_free  = _safe_int(system_vals.get(OID_MEM_FREE))
        mem_total = _safe_int(system_vals.get(OID_MEM_TOTAL))
        mem_pct   = round(((mem_total - mem_free) / mem_total) * 100, 1) if mem_total > 0 else 0.0
        flash    = _safe_float(system_vals.get(OID_FLASH))
        temp     = _safe_float(system_vals.get(OID_TEMPERATURE))
        clients  = _safe_int(system_vals.get(OID_CLIENTS_TOTAL))

        uptime_raw = system_vals.get(OID_SYS_UPTIME)
        uptime = _parse_uptime(uptime_raw) if uptime_raw else {"formatted": "—", "seconds": 0}

        firmware   = _parse_firmware(system_vals.get(OID_SYS_DESCR, ""))
        sys_name   = system_vals.get(OID_SYS_NAME, "WLC-CT2504")
        serial     = system_vals.get(OID_SERIAL, "—")
        mgmt_ip    = system_vals.get(OID_MGMT_IP, "—")
        ap_mgr     = system_vals.get(OID_AP_MGR_IP, "—")
        capwap_raw = system_vals.get(OID_CAPWAP, "0")
        capwap     = "Enabled" if capwap_raw == "1" else "Disabled"
        rf_country = system_vals.get(OID_RF_COUNTRY, "—")

        # ── Parse APs ──────────────────────────────────────────
        aps: dict[str, dict] = {}
        for suffix in self._ap_indexes:
            slug = mac_suffix_to_slug(suffix)
            status_raw = kv.get(f"{slug}_status", "2") or "2"
            aps[suffix] = {
                "slug":    slug,
                "mac":     mac_suffix_to_display(suffix),
                "name":    kv.get(f"{slug}_name") or f"AP-{mac_suffix_to_display(suffix)}",
                "model":   kv.get(f"{slug}_model") or "—",
                "ip":      kv.get(f"{slug}_ip")    or "—",
                "status":  AP_STATUS_MAP.get(status_raw, "down"),
                "clients": _safe_int(kv.get(f"{slug}_clients")),
                "cli_24":  _safe_int(kv.get(f"{slug}_cli_24")),
                "cli_5":   _safe_int(kv.get(f"{slug}_cli_5")),
                "ch24":    kv.get(f"{slug}_ch24") or "—",
                "ch5":     kv.get(f"{slug}_ch5")  or "—",
                "tx24":    kv.get(f"{slug}_tx24") or "—",
                "tx5":     kv.get(f"{slug}_tx5")  or "—",
            }

        ap_up      = sum(1 for ap in aps.values() if ap["status"] == "associated")
        ap_down    = len(aps) - ap_up
        clients_24 = sum(ap["cli_24"] for ap in aps.values())
        clients_5  = sum(ap["cli_5"]  for ap in aps.values())

        # ── Parse SSIDs ────────────────────────────────────────
        ssids: dict[int, dict] = {}
        for idx in self._ssid_indexes:
            sec_raw  = kv.get(f"ssid_{idx}_security") or "4"
            band_raw = kv.get(f"ssid_{idx}_band")     or "0"
            ssids[idx] = {
                "name":     kv.get(f"ssid_{idx}_name") or f"WLAN-{idx}",
                "clients":  _safe_int(kv.get(f"ssid_{idx}_clients")),
                "vlan":     kv.get(f"ssid_{idx}_vlan") or "—",
                "security": SSID_SECURITY_MAP.get(sec_raw, "WPA2"),
                "band":     SSID_BAND_MAP.get(band_raw, "dual"),
            }

        return {
            "cpu": cpu, "memory": mem_pct, "flash": flash,
            "temperature": temp, "uptime": uptime,
            "firmware": firmware, "sys_name": sys_name,
            "serial": serial, "mgmt_ip": mgmt_ip,
            "ap_mgr_ip": ap_mgr, "capwap": capwap,
            "rf_country": rf_country,
            "clients_total": clients,
            "clients_24": clients_24,
            "clients_5": clients_5,
            "ap_total": len(aps),
            "ap_up": ap_up,
            "ap_down": ap_down,
            "aps": aps,
            "ssid_total": len(ssids),
            "ssids": ssids,
        }

    @property
    def ap_indexes(self) -> list[str]:
        return self._ap_indexes

    @property
    def ssid_indexes(self) -> list[int]:
        return self._ssid_indexes
