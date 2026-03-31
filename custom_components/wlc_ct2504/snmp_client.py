"""SNMP client helper for Cisco WLC CT2504.

Compatible with pysnmp 6.x (asyncio hlapi).
- UdpTransportTarget: timeout/retries are now positional in 6.x, not kwargs.
- SnmpEngine() does blocking MIB file I/O on first init — created lazily via executor.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from pysnmp.hlapi.asyncio import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    getCmd,
    nextCmd,
)

_LOGGER = logging.getLogger(__name__)


def _make_engine() -> SnmpEngine:
    """Create SnmpEngine — blocking MIB I/O, must run in executor."""
    return SnmpEngine()


class SnmpClient:
    """Async SNMP v2c client wrapper — compatible with pysnmp 5.x and 6.x."""

    def __init__(self, host: str, community: str, port: int = 161, timeout: int = 5, retries: int = 2) -> None:
        self._host = host
        self._community = community
        self._port = port
        self._timeout = timeout
        self._retries = retries
        self._engine: SnmpEngine | None = None  # lazy, created in executor

    async def _get_engine(self) -> SnmpEngine:
        """Return (or lazily create) the SnmpEngine without blocking the event loop."""
        if self._engine is None:
            loop = asyncio.get_event_loop()
            self._engine = await loop.run_in_executor(None, _make_engine)
        return self._engine

    def _community_data(self) -> CommunityData:
        return CommunityData(self._community, mpModel=1)  # mpModel=1 → SNMPv2c

    def _transport(self) -> UdpTransportTarget:
        """Build UdpTransportTarget compatible with pysnmp 5.x and 6.x.

        pysnmp 6.x changed the constructor: timeout and retries are positional
        (2nd and 3rd args), not keyword args. Passing as kwargs raises
        'got multiple values for argument timeout'.
        """
        try:
            # pysnmp 6.x — positional args
            return UdpTransportTarget(
                (self._host, self._port),
                self._timeout,
                self._retries,
            )
        except TypeError:
            # pysnmp 5.x fallback — keyword args
            return UdpTransportTarget(
                (self._host, self._port),
                timeout=self._timeout,
                retries=self._retries,
            )

    async def get(self, oid: str) -> str | None:
        """GET a single OID. Returns string value or None."""
        engine = await self._get_engine()
        error_indication, error_status, error_index, var_binds = await getCmd(
            engine,
            self._community_data(),
            self._transport(),
            ContextData(),
            ObjectType(ObjectIdentity(oid)),
        )
        if error_indication:
            _LOGGER.debug("SNMP GET error for %s: %s", oid, error_indication)
            return None
        if error_status:
            _LOGGER.debug("SNMP GET status error for %s: %s", oid, error_status.prettyPrint())
            return None
        if var_binds:
            val = var_binds[0][1]
            raw = val.prettyPrint()
            # pysnmp returns "No Such Object" for missing OIDs
            if "No Such" in raw or "No more" in raw:
                return None
            return raw
        return None

    async def get_many(self, oids: list[str]) -> dict[str, str | None]:
        """GET multiple OIDs in one request."""
        obj_types = [ObjectType(ObjectIdentity(o)) for o in oids]
        engine = await self._get_engine()
        error_indication, error_status, error_index, var_binds = await getCmd(
            engine,
            self._community_data(),
            self._transport(),
            ContextData(),
            *obj_types,
        )
        result: dict[str, str | None] = {}
        if error_indication or error_status:
            _LOGGER.debug("SNMP GET_MANY error: %s %s", error_indication, error_status)
            for oid in oids:
                result[oid] = None
            return result
        for oid, (var_oid, val) in zip(oids, var_binds):
            raw = val.prettyPrint()
            result[oid] = None if ("No Such" in raw or "No more" in raw) else raw
        return result

    async def walk(self, base_oid: str) -> dict[str, str]:
        """SNMP WALK — returns {oid_suffix: value} dict."""
        engine = await self._get_engine()
        results: dict[str, str] = {}
        async for (error_indication, error_status, error_index, var_binds) in nextCmd(
            engine,
            self._community_data(),
            self._transport(),
            ContextData(),
            ObjectType(ObjectIdentity(base_oid)),
            lexicographicMode=False,
        ):
            if error_indication:
                _LOGGER.debug("SNMP WALK error for %s: %s", base_oid, error_indication)
                break
            if error_status:
                _LOGGER.debug("SNMP WALK status for %s: %s", base_oid, error_status)
                break
            for var_bind in var_binds:
                oid_str = str(var_bind[0])
                val_str = var_bind[1].prettyPrint()
                if "No Such" in val_str or "No more" in val_str:
                    continue
                # Extract suffix after base_oid
                if oid_str.startswith(base_oid + "."):
                    suffix = oid_str[len(base_oid) + 1:]
                else:
                    suffix = oid_str
                results[suffix] = val_str
        return results

    async def test_connection(self) -> bool:
        """Test connectivity — try to read sysDescr."""
        val = await self.get("1.3.6.1.2.1.1.1.0")
        return val is not None
