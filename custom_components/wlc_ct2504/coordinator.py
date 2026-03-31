"""DataUpdateCoordinator for Cisco WLC CT2504.

AP indexes: CT2504 uses MAC address as SNMP table index (6 decimal octets).
Example: '0.167.66.179.98.192' = MAC 00:A7:42:B3:62:C0
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
    DOMAIN, DEFAULT_SCAN_INTERVAL,
    AP_STATUS_MAP, SSID_SECURITY_MAP, SSID_BAND_MAP, TXPOWER_INDEX_TO_DBM,
    OID_SYS_DESCR, OID_SYS_UPTIME, OID_SYS_NAME, OID_SERIAL,
    OID_CPU, OID_MEM_FREE, OID_MEM_USED, OID_TEMPERATURE,
    OID_AP_MGR_IP, OID_CAPWAP, OID_CLIENTS_TOTAL,
    OID_AP_NAME, OID_AP_STATUS, OID_AP_MODEL, OID_AP_IP, OID_AP_CLIENTS,
    OID_AP_CHANNEL, OID_AP_TXPOWER, OID_AP_CLIENTS_RADIO,
    OID_SSID_NAME, OID_SSID_CLIENTS, OID_SSID_VLAN, OID_SSID_SECURITY, OID_SSID_BAND,
)
from .snmp_client import SnmpClient

_LOGGER = logging.getLogger(__name__)


# ── HELPERS ───────────────────────────────────────────────────────────────────

def mac_suffix_to_slug(suffix: str) -> str:
    """'0.167.66.179.98.192' → 'mac_00a742b362c0'"""
    try:
        octets = [int(x) for x in suffix.split('.')]
        return 'mac_' + ''.join(f'{o:02x}' for o in octets)
    except Exception:
        return 'ap_' + suffix.replace('.', '_')


def mac_suffix_to_display(suffix: str) -> str:
    """'0.167.66.179.98.192' → '00:A7:42:B3:62:C0'"""
    try:
        octets = [int(x) for x in suffix.split('.')]
        return ':'.join(f'{o:02X}' for o in octets)
    except Exception:
        return suffix


def _decode_hex_ip(val: str | None) -> str:
    """Decode hex IP 'c0a864d2' → '192.168.100.210'."""
    if not val:
        return "—"
    # Already dotted notation
    if '.' in val:
        return val
    # Hex string (8 chars = 4 bytes)
    try:
        if len(val) == 8:
            b = bytes.fromhex(val)
            return '.'.join(str(x) for x in b)
    except Exception:
        pass
    return val


def _parse_uptime(ticks_str: str | None) -> dict:
    if not ticks_str:
        return {"raw": "—", "seconds": 0, "formatted": "—"}
    try:
        secs = int(ticks_str) // 100
    except (ValueError, TypeError):
        return {"raw": ticks_str, "seconds": 0, "formatted": "—"}
    d = secs // 86400
    h = (secs % 86400) // 3600
    m = (secs % 3600) // 60
    return {
        "raw": ticks_str,
        "seconds": secs,
        "formatted": f"{d}d {h}h {m}m" if d > 0 else f"{h}h {m}m",
    }


def _parse_firmware(sys_descr: str | None) -> str:
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


def _txpower_to_dbm(val: str | None) -> str:
    """Convert TxPower index (1-8) to dBm string."""
    if not val:
        return "—"
    dbm = TXPOWER_INDEX_TO_DBM.get(val)
    return f"{dbm} dBm" if dbm is not None else f"idx {val}"


def _safe_int(val: str | None, default: int = 0) -> int:
    try:
        return int(val) if val is not None else default
    except (ValueError, TypeError):
        return default


def _safe_float(val: str | None, default: float = 0.0) -> float:
    try:
        v = float(val) if val is not None else default
        return default if (v != v) else v  # NaN guard
    except (ValueError, TypeError):
        return default


# ── COORDINATOR ───────────────────────────────────────────────────────────────

class WlcDataCoordinator(DataUpdateCoordinator):

    def __init__(
        self,
        hass: HomeAssistant,
        client: SnmpClient,
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
        scan_interval_clients: int = 15,
        ap_indexes: list[str] | None = None,
        ssid_indexes: list[int] | None = None,
    ) -> None:
        super().__init__(
            hass, _LOGGER, name=DOMAIN,
            update_interval=timedelta(seconds=min(scan_interval, scan_interval_clients)),
        )
        self._client = client
        self._scan_interval = scan_interval
        self._ap_indexes: list[str] = ap_indexes or []
        self._ssid_indexes: list[int] = ssid_indexes or []
        self._slow_counter = 0
        # Cache for slow-polled values — persists between fast cycles so UI never flickers
        self._slow_cache: dict[str, str | None] = {}

    async def discover(self) -> tuple[list[str], list[int]]:
        _LOGGER.info("WLC: Starting SNMP discovery...")
        ap_names, ssid_names = await asyncio.gather(
            self._client.walk(OID_AP_NAME),
            self._client.walk(OID_SSID_NAME),
        )
        _LOGGER.debug("WLC AP walk: %s", ap_names)
        _LOGGER.debug("WLC SSID walk: %s", ssid_names)

        ap_indexes   = [k for k in ap_names if k]
        ssid_indexes = sorted([int(k) for k in ssid_names if k.isdigit()])

        _LOGGER.info("WLC: %d APs, %d SSIDs", len(ap_indexes), len(ssid_indexes))
        self._ap_indexes   = ap_indexes
        self._ssid_indexes = ssid_indexes
        return ap_indexes, ssid_indexes

    async def _async_update_data(self) -> dict[str, Any]:
        self._slow_counter += 1
        do_slow = (self._slow_counter % max(1, self._scan_interval // 15)) == 0
        try:
            return await self._fetch_all(do_slow)
        except Exception as err:
            raise UpdateFailed(f"WLC SNMP error: {err}") from err

    async def _fetch_all(self, do_slow: bool) -> dict[str, Any]:
        # System OIDs
        fast_sys = [OID_CPU, OID_MEM_FREE, OID_MEM_USED, OID_CLIENTS_TOTAL]
        slow_sys = [OID_SYS_DESCR, OID_SYS_UPTIME, OID_SYS_NAME, OID_SERIAL,
                    OID_TEMPERATURE, OID_AP_MGR_IP, OID_CAPWAP]
        sys_oids = fast_sys + (slow_sys if do_slow else [])

        # Per-AP OIDs
        ap_keyed: dict[str, str] = {}
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

        # Per-SSID OIDs
        ssid_keyed: dict[str, str] = {}
        for idx in self._ssid_indexes:
            ssid_keyed[f"ssid_{idx}_clients"] = f"{OID_SSID_CLIENTS}.{idx}"
            if do_slow:
                ssid_keyed[f"ssid_{idx}_name"]     = f"{OID_SSID_NAME}.{idx}"
                ssid_keyed[f"ssid_{idx}_vlan"]     = f"{OID_SSID_VLAN}.{idx}"
                ssid_keyed[f"ssid_{idx}_security"] = f"{OID_SSID_SECURITY}.{idx}"
                ssid_keyed[f"ssid_{idx}_band"]     = f"{OID_SSID_BAND}.{idx}"

        all_keyed = {**ap_keyed, **ssid_keyed}

        sys_vals, keyed_vals = await asyncio.gather(
            self._client.get_many(sys_oids),
            self._client.get_many(list(all_keyed.values())),
        )

        # Build kv — for slow keys, update cache only when do_slow=True,
        # otherwise fall back to cached value so data never disappears mid-cycle
        kv: dict[str, str | None] = {}
        for key, oid in all_keyed.items():
            val = keyed_vals.get(oid)
            if val is not None:
                kv[key] = val
                self._slow_cache[key] = val  # always update cache on fresh data
            elif key in self._slow_cache:
                kv[key] = self._slow_cache[key]  # use last known value
            else:
                kv[key] = None

        # ── System data ───────────────────────────────────────
        cpu       = _safe_float(sys_vals.get(OID_CPU))

        # Memory: OID_MEM_FREE = free KB, OID_MEM_USED = used KB
        # (MIB naming is misleading — .5.3.0 is actually used, not total)
        mem_free = _safe_int(sys_vals.get(OID_MEM_FREE))
        mem_used = _safe_int(sys_vals.get(OID_MEM_USED))
        mem_total = mem_free + mem_used
        mem_pct = round((mem_used / mem_total) * 100, 1) if mem_total > 0 else 0.0

        # Temperature — may be empty string on some firmware
        temp_raw = sys_vals.get(OID_TEMPERATURE) or ""
        temp = _safe_float(temp_raw.strip()) if temp_raw.strip() else 0.0

        # Merge slow system OIDs with cache
        for oid in [OID_SYS_DESCR, OID_SYS_UPTIME, OID_SYS_NAME, OID_SERIAL,
                    OID_TEMPERATURE, OID_AP_MGR_IP, OID_CAPWAP]:
            v = sys_vals.get(oid)
            if v is not None:
                self._slow_cache[f'sys_{oid}'] = v
            elif f'sys_{oid}' in self._slow_cache and oid not in sys_vals:
                sys_vals[oid] = self._slow_cache[f'sys_{oid}']

        uptime = _parse_uptime(sys_vals.get(OID_SYS_UPTIME))
        firmware = _parse_firmware(sys_vals.get(OID_SYS_DESCR))

        # sysName is more reliable than the broken MgmtIP OID
        sys_name = sys_vals.get(OID_SYS_NAME) or "WLC-CT2504"
        serial   = sys_vals.get(OID_SERIAL) or "—"
        capwap_raw = sys_vals.get(OID_CAPWAP) or "0"
        capwap = "Enabled" if capwap_raw.strip() == "1" else "Disabled"

        # ── AP data ───────────────────────────────────────────
        aps: dict[str, dict] = {}
        for suffix in self._ap_indexes:
            slug = mac_suffix_to_slug(suffix)
            status_raw = kv.get(f"{slug}_status") or "2"
            tx24_raw   = kv.get(f"{slug}_tx24")
            tx5_raw    = kv.get(f"{slug}_tx5")
            aps[suffix] = {
                "slug":    slug,
                "mac":     mac_suffix_to_display(suffix),
                "name":    kv.get(f"{slug}_name") or f"AP-{mac_suffix_to_display(suffix)}",
                "model":   kv.get(f"{slug}_model") or "—",
                "ip":      _decode_hex_ip(kv.get(f"{slug}_ip")),
                "status":  AP_STATUS_MAP.get(status_raw.strip(), "down"),
                "clients": _safe_int(kv.get(f"{slug}_clients")),
                "cli_24":  _safe_int(kv.get(f"{slug}_cli_24")),
                "cli_5":   _safe_int(kv.get(f"{slug}_cli_5")),
                "ch24":    kv.get(f"{slug}_ch24") or "—",
                "ch5":     kv.get(f"{slug}_ch5")  or "—",
                "tx24":    _txpower_to_dbm(tx24_raw),
                "tx5":     _txpower_to_dbm(tx5_raw),
            }

        ap_up      = sum(1 for ap in aps.values() if ap["status"] == "associated")
        ap_down    = len(aps) - ap_up
        clients_24 = sum(ap["cli_24"] for ap in aps.values())
        clients_5  = sum(ap["cli_5"]  for ap in aps.values())
        # Use sum from radios — total OID unreliable on CT2504
        clients_total = clients_24 + clients_5

        # ── SSID data ─────────────────────────────────────────
        ssids: dict[int, dict] = {}
        for idx in self._ssid_indexes:
            sec_raw  = kv.get(f"ssid_{idx}_security") or "4"
            band_raw = kv.get(f"ssid_{idx}_band")     or "0"
            ssids[idx] = {
                "name":     kv.get(f"ssid_{idx}_name") or f"WLAN-{idx}",
                "clients":  _safe_int(kv.get(f"ssid_{idx}_clients")),
                "vlan":     kv.get(f"ssid_{idx}_vlan") or "—",
                "security": SSID_SECURITY_MAP.get(sec_raw.strip(), "WPA2"),
                "band":     SSID_BAND_MAP.get(band_raw.strip(), "dual"),
            }

        return {
            "cpu": cpu, "memory": mem_pct,
            "temperature": temp,
            "uptime": uptime,
            "firmware": firmware,
            "sys_name": sys_name,
            "serial": serial,
            "capwap": capwap,
            "clients_total": clients_total,
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
