"""DataUpdateCoordinator for Cisco WLC CT2504 — validated from device walk."""
from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN, DEFAULT_SCAN_INTERVAL,
    AP_STATUS_MAP, SSID_SECURITY_MAP, SSID_BAND_MAP, TXPOWER_INDEX_TO_DBM,
    PORT_INDEXES,
    OID_SYS_NAME, OID_SYS_UPTIME, OID_SERIAL,
    OID_MODEL, OID_FIRMWARE, OID_WLC_MAC,
    OID_CPU, OID_MEM_FREE, OID_MEM_USED,
    OID_CLIENTS_ASSOC, OID_CLIENTS_AUTH,
    OID_AP_NAME, OID_AP_STATUS, OID_AP_MODEL, OID_AP_IP,
    OID_AP_CHANNEL, OID_AP_TXPOWER, OID_AP_CLIENTS_RADIO,
    OID_AP_CHANUTIL, OID_AP_RXUTIL,
    OID_SSID_NAME, OID_SSID_STATUS, OID_SSID_CLIENTS, OID_SSID_VLAN,
    OID_SSID_SECURITY, OID_SSID_BAND,
    OID_IF_NAME, OID_IF_OPER, OID_IF_SPEED,
    OID_IF_IN_OCTETS, OID_IF_OUT_OCTETS, OID_IF_IN_ERRORS,
)
from .snmp_client import SnmpClient

_LOGGER = logging.getLogger(__name__)


# ── HELPERS ───────────────────────────────────────────────────────────────────

def mac_suffix_to_slug(suffix: str) -> str:
    try:
        octets = [int(x) for x in suffix.split('.')]
        return 'mac_' + ''.join(f'{o:02x}' for o in octets)
    except Exception:
        return 'ap_' + suffix.replace('.', '_')


def mac_suffix_to_display(suffix: str) -> str:
    try:
        octets = [int(x) for x in suffix.split('.')]
        return ':'.join(f'{o:02X}' for o in octets)
    except Exception:
        return suffix


def _parse_uptime(raw: str | None) -> dict:
    """Parse '97 hours 16 min (35017400)' — extract ticks from parens."""
    if not raw:
        return {"raw": "—", "seconds": 0, "formatted": "—"}
    m = re.search(r'\((\d+)\)', raw)
    ticks_str = m.group(1) if m else raw
    try:
        secs = int(ticks_str) // 100
        d = secs // 86400
        h = (secs % 86400) // 3600
        mn = (secs % 3600) // 60
        return {"raw": raw, "seconds": secs,
                "formatted": f"{d}d {h}h {mn}m" if d > 0 else f"{h}h {mn}m"}
    except Exception:
        return {"raw": raw, "seconds": 0, "formatted": str(raw)[:30]}


def _txpower_to_dbm(val: str | None) -> str:
    if not val:
        return "—"
    dbm = TXPOWER_INDEX_TO_DBM.get(val.strip())
    return f"{dbm} dBm" if dbm is not None else f"idx {val}"


def _parse_chanutil(val: str | None) -> int:
    """First value from '16,13,10,7,4' → 16."""
    if not val:
        return 0
    try:
        return int(val.split(',')[0].strip())
    except Exception:
        return 0


def _port_speed(val: str | None) -> str:
    try:
        bps = int(val or 0)
        if bps >= 1_000_000_000: return "1G"
        if bps >= 100_000_000:   return "100M"
        if bps >= 10_000_000:    return "10M"
        return f"{bps}"
    except Exception:
        return val or "—"


def _port_status(val: str | None) -> str:
    if not val: return "unknown"
    v = val.strip()
    return "up" if (v == "1" or v.startswith("up")) else "down"


def _safe_int(val: str | None, default: int = 0) -> int:
    try:
        return int((val or "").strip()) if val else default
    except Exception:
        return default


def _safe_float(val: str | None, default: float = 0.0) -> float:
    try:
        v = float((val or "").strip()) if val else default
        return default if v != v else v
    except Exception:
        return default


def _mbps(delta_bytes: int, delta_secs: float) -> float:
    """Convert byte delta over time to Mbps."""
    if delta_secs <= 0 or delta_bytes < 0:
        return 0.0
    return round((delta_bytes * 8) / (delta_secs * 1_000_000), 2)


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
        # Persistent cache — slow values survive fast cycles (no UI flicker)
        self._cache: dict[str, Any] = {}
        # Port traffic delta tracking
        self._port_prev: dict[str, int] = {}
        self._port_prev_time: float = 0.0

    def _cached(self, key: str, new_val: Any) -> Any:
        """Return new_val if not None/empty, else return cached value."""
        if new_val is not None and new_val != "" and new_val != "—":
            self._cache[key] = new_val
            return new_val
        return self._cache.get(key, new_val)

    # ── Discovery ─────────────────────────────────────────────────────────────

    async def discover(self) -> tuple[list[str], list[int]]:
        _LOGGER.info("WLC: Starting SNMP discovery...")
        ap_names, ssid_names = await asyncio.gather(
            self._client.walk(OID_AP_NAME),
            self._client.walk(OID_SSID_NAME),
        )
        ap_indexes   = [k for k in ap_names if k]
        ssid_indexes = sorted([int(k) for k in ssid_names if k.isdigit()])
        _LOGGER.info("WLC: %d APs, %d SSIDs", len(ap_indexes), len(ssid_indexes))
        self._ap_indexes   = ap_indexes
        self._ssid_indexes = ssid_indexes
        return ap_indexes, ssid_indexes

    # ── Main update ───────────────────────────────────────────────────────────

    async def _async_update_data(self) -> dict[str, Any]:
        self._slow_counter += 1
        do_slow = (self._slow_counter % max(1, self._scan_interval // 15)) == 0
        try:
            return await self._fetch_all(do_slow)
        except Exception as err:
            raise UpdateFailed(f"WLC SNMP error: {err}") from err

    async def _fetch_all(self, do_slow: bool) -> dict[str, Any]:

        # ── Fast OIDs — every poll ─────────────────────────────
        # CPU fetched separately (single GET more reliable than grouped)
        fast_sys = [OID_MEM_FREE, OID_MEM_USED,
                    OID_CLIENTS_ASSOC, OID_CLIENTS_AUTH]

        # ── Slow OIDs — every ~30s ─────────────────────────────
        slow_sys = [OID_SYS_UPTIME, OID_SYS_NAME, OID_SERIAL,
                    OID_MODEL, OID_FIRMWARE, OID_WLC_MAC]

        sys_oids = fast_sys + (slow_sys if do_slow else [])

        # ── Per-AP OIDs ───────────────────────────────────────
        ap_keyed: dict[str, str] = {}
        for suffix in self._ap_indexes:
            slug = mac_suffix_to_slug(suffix)
            ap_keyed[f"{slug}_status"]   = f"{OID_AP_STATUS}.{suffix}"
            ap_keyed[f"{slug}_cli_24"]   = f"{OID_AP_CLIENTS_RADIO}.{suffix}.0"
            ap_keyed[f"{slug}_cli_5"]    = f"{OID_AP_CLIENTS_RADIO}.{suffix}.1"
            if do_slow:
                ap_keyed[f"{slug}_name"] = f"{OID_AP_NAME}.{suffix}"
                ap_keyed[f"{slug}_model"]= f"{OID_AP_MODEL}.{suffix}"
                ap_keyed[f"{slug}_ip"]   = f"{OID_AP_IP}.{suffix}"
                ap_keyed[f"{slug}_ch24"] = f"{OID_AP_CHANNEL}.{suffix}.0"
                ap_keyed[f"{slug}_ch5"]  = f"{OID_AP_CHANNEL}.{suffix}.1"
                ap_keyed[f"{slug}_tx24"] = f"{OID_AP_TXPOWER}.{suffix}.0"
                ap_keyed[f"{slug}_tx5"]  = f"{OID_AP_TXPOWER}.{suffix}.1"
                ap_keyed[f"{slug}_u24"]  = f"{OID_AP_CHANUTIL}.{suffix}.0"
                ap_keyed[f"{slug}_u5"]   = f"{OID_AP_CHANUTIL}.{suffix}.1"

        # ── Per-SSID OIDs ─────────────────────────────────────
        ssid_keyed: dict[str, str] = {}
        for idx in self._ssid_indexes:
            ssid_keyed[f"ssid_{idx}_clients"] = f"{OID_SSID_CLIENTS}.{idx}"
            if do_slow:
                ssid_keyed[f"ssid_{idx}_name"]     = f"{OID_SSID_NAME}.{idx}"
                ssid_keyed[f"ssid_{idx}_vlan"]     = f"{OID_SSID_VLAN}.{idx}"
                ssid_keyed[f"ssid_{idx}_security"] = f"{OID_SSID_SECURITY}.{idx}"
                ssid_keyed[f"ssid_{idx}_band"]     = f"{OID_SSID_BAND}.{idx}"
                ssid_keyed[f"ssid_{idx}_status"]   = f"{OID_SSID_STATUS}.{idx}"

        # ── Port OIDs — always slow ────────────────────────────
        port_keyed: dict[str, str] = {}
        if do_slow:
            for i in PORT_INDEXES:
                port_keyed[f"port_{i}_name"]  = f"{OID_IF_NAME}.{i}"
                port_keyed[f"port_{i}_oper"]  = f"{OID_IF_OPER}.{i}"
                port_keyed[f"port_{i}_speed"] = f"{OID_IF_SPEED}.{i}"
                port_keyed[f"port_{i}_in"]    = f"{OID_IF_IN_OCTETS}.{i}"
                port_keyed[f"port_{i}_out"]   = f"{OID_IF_OUT_OCTETS}.{i}"
                port_keyed[f"port_{i}_errin"] = f"{OID_IF_IN_ERRORS}.{i}"

        all_keyed = {**ap_keyed, **ssid_keyed, **port_keyed}

        # ── Fetch all in parallel + CPU separately ─────────────
        cpu_raw, sys_vals, keyed_vals = await asyncio.gather(
            self._client.get(OID_CPU),
            self._client.get_many(sys_oids),
            self._client.get_many(list(all_keyed.values())),
        )

        # Build kv with persistent cache fallback
        kv: dict[str, Any] = {}
        for key, oid in all_keyed.items():
            val = keyed_vals.get(oid)
            kv[key] = self._cached(f"kv_{key}", val)

        # Cache slow system vals
        for oid in slow_sys:
            v = sys_vals.get(oid)
            if v is not None and v != "":
                self._cache[f"sys_{oid}"] = v
            elif f"sys_{oid}" in self._cache and oid not in sys_vals:
                sys_vals[oid] = self._cache[f"sys_{oid}"]

        # ── Parse system ───────────────────────────────────────
        # CPU — fetched separately, still cache it
        cpu = _safe_float(self._cached("cpu", cpu_raw))

        mem_free  = _safe_int(sys_vals.get(OID_MEM_FREE))
        mem_used  = _safe_int(sys_vals.get(OID_MEM_USED))
        mem_total = mem_free + mem_used
        mem_pct   = round((mem_used / mem_total) * 100, 1) if mem_total > 0 else 0.0

        # Temperature — not available on CT2504 via SNMP, use 0 as sentinel
        # (OID exists but returns empty string)

        uptime   = _parse_uptime(sys_vals.get(OID_SYS_UPTIME))
        firmware = self._cached("firmware", sys_vals.get(OID_FIRMWARE)) or "Unknown"
        model    = self._cached("model",    sys_vals.get(OID_MODEL))    or "AIR-CT2504-K9"
        sys_name = self._cached("sys_name", sys_vals.get(OID_SYS_NAME)) or "WLC-CT2504"
        serial   = self._cached("serial",   sys_vals.get(OID_SERIAL))   or "—"
        wlc_mac  = self._cached("wlc_mac",  sys_vals.get(OID_WLC_MAC))  or "—"

        clients_assoc = _safe_int(sys_vals.get(OID_CLIENTS_ASSOC))
        clients_auth  = _safe_int(sys_vals.get(OID_CLIENTS_AUTH))

        # ── Parse APs ──────────────────────────────────────────
        aps: dict[str, dict] = {}
        for suffix in self._ap_indexes:
            slug   = mac_suffix_to_slug(suffix)
            status_raw = (kv.get(f"{slug}_status") or "2").strip()
            cli_24 = _safe_int(kv.get(f"{slug}_cli_24"))
            cli_5  = _safe_int(kv.get(f"{slug}_cli_5"))
            aps[suffix] = {
                "slug":    slug,
                "mac":     mac_suffix_to_display(suffix),
                "name":    kv.get(f"{slug}_name")  or f"AP-{mac_suffix_to_display(suffix)}",
                "model":   kv.get(f"{slug}_model") or "—",
                "ip":      kv.get(f"{slug}_ip")    or "—",
                "status":  AP_STATUS_MAP.get(status_raw, "down"),
                "clients": cli_24 + cli_5,
                "cli_24":  cli_24,
                "cli_5":   cli_5,
                "ch24":    kv.get(f"{slug}_ch24") or "—",
                "ch5":     kv.get(f"{slug}_ch5")  or "—",
                "tx24":    _txpower_to_dbm(kv.get(f"{slug}_tx24")),
                "tx5":     _txpower_to_dbm(kv.get(f"{slug}_tx5")),
                "util24":  _parse_chanutil(kv.get(f"{slug}_u24")),
                "util5":   _parse_chanutil(kv.get(f"{slug}_u5")),
            }

        ap_up      = sum(1 for ap in aps.values() if ap["status"] == "associated")
        ap_down    = len(aps) - ap_up
        clients_24 = sum(ap["cli_24"] for ap in aps.values())
        clients_5  = sum(ap["cli_5"]  for ap in aps.values())

        # ── Parse SSIDs ────────────────────────────────────────
        ssids: dict[int, dict] = {}
        for idx in self._ssid_indexes:
            sec_raw  = (kv.get(f"ssid_{idx}_security") or "4").strip()
            band_raw = (kv.get(f"ssid_{idx}_band")     or "0").strip()
            ssids[idx] = {
                "name":     kv.get(f"ssid_{idx}_name") or f"WLAN-{idx}",
                "clients":  _safe_int(kv.get(f"ssid_{idx}_clients")),
                "vlan":     kv.get(f"ssid_{idx}_vlan") or "—",
                "security": SSID_SECURITY_MAP.get(sec_raw, "WPA2"),
                "band":     SSID_BAND_MAP.get(band_raw, "dual"),
                "enabled":  (kv.get(f"ssid_{idx}_status") or "0") == "1",
            }

        # ── Parse Ports with throughput delta ──────────────────
        now = time.monotonic()
        delta_secs = now - self._port_prev_time if self._port_prev_time else 0.0

        ports: dict[int, dict] = {}
        for i in PORT_INDEXES:
            name_raw = kv.get(f"port_{i}_name") or f"Port {i}"
            label    = re.sub(r'GigabitEthernet', 'Ge', name_raw)
            label    = re.sub(r'FastEthernet', 'Fa', label)

            in_now  = _safe_int(kv.get(f"port_{i}_in"),  0)
            out_now = _safe_int(kv.get(f"port_{i}_out"), 0)
            in_prev  = self._port_prev.get(f"{i}_in",  in_now)
            out_prev = self._port_prev.get(f"{i}_out", out_now)

            # Delta (handle counter rollover: ignore if delta is negative)
            d_in  = max(0, in_now  - in_prev)
            d_out = max(0, out_now - out_prev)

            rx_mbps = _mbps(d_in,  delta_secs)
            tx_mbps = _mbps(d_out, delta_secs)

            ports[i] = {
                "name":       label,
                "status":     _port_status(kv.get(f"port_{i}_oper")),
                "speed":      _port_speed(kv.get(f"port_{i}_speed")),
                "in_octets":  in_now,
                "out_octets": out_now,
                "rx_mbps":    rx_mbps,
                "tx_mbps":    tx_mbps,
                "in_errors":  _safe_int(kv.get(f"port_{i}_errin")),
            }
            self._port_prev[f"{i}_in"]  = in_now
            self._port_prev[f"{i}_out"] = out_now

        if do_slow:
            self._port_prev_time = now

        return {
            "cpu": cpu, "memory": mem_pct,
            "uptime": uptime, "firmware": firmware, "model": model,
            "sys_name": sys_name, "serial": serial, "wlc_mac": wlc_mac,
            "clients_total": clients_assoc,
            "clients_auth":  clients_auth,
            "clients_24":    clients_24,
            "clients_5":     clients_5,
            "ap_total": len(aps), "ap_up": ap_up, "ap_down": ap_down,
            "aps": aps,
            "ssid_total": len(ssids), "ssids": ssids,
            "ports": ports,
        }

    @property
    def ap_indexes(self) -> list[str]:
        return self._ap_indexes

    @property
    def ssid_indexes(self) -> list[int]:
        return self._ssid_indexes
