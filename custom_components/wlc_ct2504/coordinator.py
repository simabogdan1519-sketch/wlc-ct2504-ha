"""DataUpdateCoordinator for Cisco WLC CT2504.
All OIDs fetched every poll via parallel individual GETs. No fast/slow split.
"""
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
    OID_CPU, OID_MEM_FREE, OID_TEMPERATURE,
    OID_CLIENTS_ASSOC, OID_CLIENTS_AUTH,
    OID_AP_NAME, OID_AP_STATUS, OID_AP_MODEL, OID_AP_IP,
    OID_AP_CHANNEL, OID_AP_TXPOWER, OID_AP_CLIENTS_RADIO, OID_AP_CHANUTIL,
    OID_SSID_NAME, OID_SSID_STATUS, OID_SSID_CLIENTS, OID_SSID_VLAN,
    OID_SSID_SECURITY, OID_SSID_BAND,
    OID_IF_NAME, OID_IF_OPER, OID_IF_SPEED,
    OID_IF_IN_OCTETS, OID_IF_OUT_OCTETS, OID_IF_IN_ERRORS,
)
from .snmp_client import SnmpClient

_LOGGER = logging.getLogger(__name__)


def mac_suffix_to_slug(suffix: str) -> str:
    try:
        return 'mac_' + ''.join(f'{int(x):02x}' for x in suffix.split('.'))
    except Exception:
        return 'ap_' + suffix.replace('.', '_')


def mac_suffix_to_display(suffix: str) -> str:
    try:
        return ':'.join(f'{int(x):02X}' for x in suffix.split('.'))
    except Exception:
        return suffix


def _decode_hex_ip(val: str | None) -> str:
    if not val: return "—"
    if '.' in val: return val
    try:
        if len(val) == 8:
            return '.'.join(str(b) for b in bytes.fromhex(val))
    except Exception:
        pass
    return val


def _fmt_mac(val: str | None) -> str:
    if not val: return "—"
    if ':' in val: return val.upper()
    if '-' in val: return val.upper().replace('-', ':')
    try:
        clean = re.sub(r'[^0-9a-fA-F]', '', val)
        if len(clean) == 12:
            return ':'.join(clean[i:i+2].upper() for i in range(0, 12, 2))
    except Exception:
        pass
    return val


def _parse_uptime(raw: str | None) -> dict:
    if not raw:
        return {"seconds": 0, "formatted": "—"}
    m = re.search(r'\((\d+)\)', raw)
    try:
        secs = int(m.group(1) if m else raw) // 100
        d = secs // 86400
        h = (secs % 86400) // 3600
        mn = (secs % 3600) // 60
        return {"seconds": secs,
                "formatted": f"{d}d {h}h {mn}m" if d > 0 else f"{h}h {mn}m"}
    except Exception:
        return {"seconds": 0, "formatted": "—"}


def _txpower_to_dbm(val: str | None) -> str:
    if not val: return "—"
    dbm = TXPOWER_INDEX_TO_DBM.get((val or "").strip())
    return f"{dbm} dBm" if dbm is not None else "—"


def _parse_chanutil(val: str | None) -> int:
    if not val: return 0
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
    except Exception:
        pass
    return "—"


def _port_status(val: str | None) -> str:
    if not val: return "unknown"
    v = val.strip()
    return "up" if (v == "1" or v.startswith("up")) else "down"


def _int(val: str | None, default: int = 0) -> int:
    try:
        return int((val or "").strip())
    except Exception:
        return default


def _float(val: str | None, default: float = 0.0) -> float:
    try:
        return float((val or "").strip())
    except Exception:
        return default


def _mbps(delta_bytes: int, delta_secs: float) -> float:
    if delta_secs <= 0 or delta_bytes <= 0: return 0.0
    return round((delta_bytes * 8) / (delta_secs * 1_000_000), 2)


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
            update_interval=timedelta(seconds=scan_interval),
        )
        self._client = client
        self._ap_indexes: list[str] = ap_indexes or []
        self._ssid_indexes: list[int] = ssid_indexes or []
        self._port_prev: dict[str, int] = {}
        self._port_prev_time: float = 0.0

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

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self._fetch()
        except Exception as err:
            raise UpdateFailed(f"WLC SNMP error: {err}") from err

    async def _fetch(self) -> dict[str, Any]:
        oids: dict[str, str] = {
            "cpu":          OID_CPU,
            "mem_free":     OID_MEM_FREE,       # KB free memory
            "temperature":  OID_TEMPERATURE,    # raw integer / 10000 = °C
            "clients":      OID_CLIENTS_ASSOC,
            "clients_auth": OID_CLIENTS_AUTH,
            "uptime":       OID_SYS_UPTIME,
            "sys_name":     OID_SYS_NAME,
            "serial":       OID_SERIAL,
            "model":        OID_MODEL,
            "firmware":     OID_FIRMWARE,
            "wlc_mac":      OID_WLC_MAC,
        }

        for suffix in self._ap_indexes:
            slug = mac_suffix_to_slug(suffix)
            oids[f"{slug}_status"] = f"{OID_AP_STATUS}.{suffix}"
            oids[f"{slug}_cli_24"] = f"{OID_AP_CLIENTS_RADIO}.{suffix}.0"
            oids[f"{slug}_cli_5"]  = f"{OID_AP_CLIENTS_RADIO}.{suffix}.1"
            oids[f"{slug}_name"]   = f"{OID_AP_NAME}.{suffix}"
            oids[f"{slug}_model"]  = f"{OID_AP_MODEL}.{suffix}"
            oids[f"{slug}_ip"]     = f"{OID_AP_IP}.{suffix}"
            oids[f"{slug}_ch24"]   = f"{OID_AP_CHANNEL}.{suffix}.0"
            oids[f"{slug}_ch5"]    = f"{OID_AP_CHANNEL}.{suffix}.1"
            oids[f"{slug}_tx24"]   = f"{OID_AP_TXPOWER}.{suffix}.0"
            oids[f"{slug}_tx5"]    = f"{OID_AP_TXPOWER}.{suffix}.1"
            oids[f"{slug}_u24"]    = f"{OID_AP_CHANUTIL}.{suffix}.0"
            oids[f"{slug}_u5"]     = f"{OID_AP_CHANUTIL}.{suffix}.1"

        for idx in self._ssid_indexes:
            oids[f"ssid_{idx}_name"]     = f"{OID_SSID_NAME}.{idx}"
            oids[f"ssid_{idx}_clients"]  = f"{OID_SSID_CLIENTS}.{idx}"
            oids[f"ssid_{idx}_vlan"]     = f"{OID_SSID_VLAN}.{idx}"
            oids[f"ssid_{idx}_security"] = f"{OID_SSID_SECURITY}.{idx}"
            oids[f"ssid_{idx}_band"]     = f"{OID_SSID_BAND}.{idx}"
            oids[f"ssid_{idx}_status"]   = f"{OID_SSID_STATUS}.{idx}"

        for i in PORT_INDEXES:
            oids[f"port_{i}_name"]  = f"{OID_IF_NAME}.{i}"
            oids[f"port_{i}_oper"]  = f"{OID_IF_OPER}.{i}"
            oids[f"port_{i}_speed"] = f"{OID_IF_SPEED}.{i}"
            oids[f"port_{i}_in"]    = f"{OID_IF_IN_OCTETS}.{i}"
            oids[f"port_{i}_out"]   = f"{OID_IF_OUT_OCTETS}.{i}"
            oids[f"port_{i}_errin"] = f"{OID_IF_IN_ERRORS}.{i}"

        # Fetch everything in parallel
        raw = await self._client.get_many(list(oids.values()))
        v: dict[str, str | None] = {key: raw.get(oid) for key, oid in oids.items()}

        # ── System ────────────────────────────────────────────
        cpu      = _float(v["cpu"])
        mem_free = _int(v["mem_free"])   # KB free — display as-is

        # Temperature: raw integer / 10000 = °C (e.g. 434792 / 10000 = 43.4°C)
        temp_raw = _int(v["temperature"])
        temperature = round(temp_raw / 10000, 1) if temp_raw > 1000 else float(temp_raw)

        uptime   = _parse_uptime(v["uptime"])
        firmware = v["firmware"] or "Unknown"
        model    = v["model"]    or "AIR-CT2504-K9"
        sys_name = v["sys_name"] or "WLC-CT2504"
        serial   = v["serial"]   or "—"
        wlc_mac  = _fmt_mac(v["wlc_mac"])

        clients_assoc = _int(v["clients"])
        clients_auth  = _int(v["clients_auth"])

        # ── APs ───────────────────────────────────────────────
        aps: dict[str, dict] = {}
        for suffix in self._ap_indexes:
            slug   = mac_suffix_to_slug(suffix)
            status = AP_STATUS_MAP.get((v[f"{slug}_status"] or "2").strip(), "down")
            cli_24 = _int(v[f"{slug}_cli_24"])
            cli_5  = _int(v[f"{slug}_cli_5"])
            aps[suffix] = {
                "slug":    slug,
                "mac":     mac_suffix_to_display(suffix),
                "name":    v[f"{slug}_name"]  or f"AP-{mac_suffix_to_display(suffix)}",
                "model":   v[f"{slug}_model"] or "—",
                "ip":      _decode_hex_ip(v[f"{slug}_ip"]),
                "status":  status,
                "clients": cli_24 + cli_5,
                "cli_24":  cli_24,
                "cli_5":   cli_5,
                "ch24":    v[f"{slug}_ch24"] or "—",
                "ch5":     v[f"{slug}_ch5"]  or "—",
                "tx24":    _txpower_to_dbm(v[f"{slug}_tx24"]),
                "tx5":     _txpower_to_dbm(v[f"{slug}_tx5"]),
                "util24":  _parse_chanutil(v[f"{slug}_u24"]),
                "util5":   _parse_chanutil(v[f"{slug}_u5"]),
            }

        ap_up      = sum(1 for ap in aps.values() if ap["status"] == "associated")
        ap_down    = len(aps) - ap_up
        clients_24 = sum(ap["cli_24"] for ap in aps.values())
        clients_5  = sum(ap["cli_5"]  for ap in aps.values())

        # ── SSIDs ─────────────────────────────────────────────
        ssids: dict[int, dict] = {}
        for idx in self._ssid_indexes:
            sec  = SSID_SECURITY_MAP.get((v[f"ssid_{idx}_security"] or "4").strip(), "WPA2")
            band = SSID_BAND_MAP.get((v[f"ssid_{idx}_band"] or "0").strip(), "dual")
            ssids[idx] = {
                "name":     v[f"ssid_{idx}_name"] or f"WLAN-{idx}",
                "clients":  _int(v[f"ssid_{idx}_clients"]),
                "vlan":     v[f"ssid_{idx}_vlan"] or "—",
                "security": sec,
                "band":     band,
                "enabled":  (v[f"ssid_{idx}_status"] or "0") == "1",
            }

        # ── Ports ─────────────────────────────────────────────
        now = time.monotonic()
        delta_secs = now - self._port_prev_time if self._port_prev_time else 0.0
        self._port_prev_time = now

        ports: dict[int, dict] = {}
        for i in PORT_INDEXES:
            name_raw = v[f"port_{i}_name"] or f"Port {i}"
            label    = re.sub(r'GigabitEthernet', 'Ge', name_raw)
            in_now   = _int(v[f"port_{i}_in"])
            out_now  = _int(v[f"port_{i}_out"])
            in_prev  = self._port_prev.get(f"{i}_in",  in_now)
            out_prev = self._port_prev.get(f"{i}_out", out_now)
            ports[i] = {
                "name":      label,
                "status":    _port_status(v[f"port_{i}_oper"]),
                "speed":     _port_speed(v[f"port_{i}_speed"]),
                "in_octets": in_now,
                "out_octets":out_now,
                "rx_mbps":   _mbps(max(0, in_now  - in_prev),  delta_secs),
                "tx_mbps":   _mbps(max(0, out_now - out_prev), delta_secs),
                "in_errors": _int(v[f"port_{i}_errin"]),
            }
            self._port_prev[f"{i}_in"]  = in_now
            self._port_prev[f"{i}_out"] = out_now

        return {
            "cpu": cpu, "memory": mem_free, "temperature": temperature,
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
