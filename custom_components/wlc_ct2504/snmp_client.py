"""SNMP client helper for Cisco WLC CT2504.

pysnmp 6.x breaking change: UdpTransportTarget MUST be created with
    await UdpTransportTarget.create(...)
NOT with UdpTransportTarget(...) directly.

Also: SnmpEngine() does blocking MIB file I/O — offloaded to executor.
"""
from __future__ import annotations

import asyncio
import logging

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
    """Instantiate SnmpEngine — blocking MIB I/O, must run in executor."""
    return SnmpEngine()


class SnmpClient:
    """Async SNMP v2c client — pysnmp 6.x / Python 3.14 compatible."""

    def __init__(
        self,
        host: str,
        community: str,
        port: int = 161,
        timeout: int = 5,
        retries: int = 2,
    ) -> None:
        self._host = host
        self._community = community
        self._port = port
        self._timeout = timeout
        self._retries = retries
        self._engine: SnmpEngine | None = None

    async def _get_engine(self) -> SnmpEngine:
        """Lazy SnmpEngine via executor — avoids blocking the event loop."""
        if self._engine is None:
            loop = asyncio.get_event_loop()
            self._engine = await loop.run_in_executor(None, _make_engine)
        return self._engine

    async def _transport(self) -> UdpTransportTarget:
        """Create transport via async factory (required by pysnmp 6.x)."""
        return await UdpTransportTarget.create(
            (self._host, self._port),
            timeout=self._timeout,
            retries=self._retries,
        )

    def _community_data(self) -> CommunityData:
        return CommunityData(self._community, mpModel=1)  # 1 = SNMPv2c

    async def get(self, oid: str) -> str | None:
        """GET single OID. Returns string or None."""
        engine    = await self._get_engine()
        transport = await self._transport()

        error_indication, error_status, _, var_binds = await getCmd(
            engine,
            self._community_data(),
            transport,
            ContextData(),
            ObjectType(ObjectIdentity(oid)),
        )
        if error_indication:
            _LOGGER.debug("SNMP GET error [%s]: %s", oid, error_indication)
            return None
        if error_status:
            _LOGGER.debug("SNMP GET status [%s]: %s", oid, error_status.prettyPrint())
            return None
        if not var_binds:
            return None
        raw = var_binds[0][1].prettyPrint()
        return None if ("No Such" in raw or "No more" in raw) else raw

    async def get_many(self, oids: list[str]) -> dict[str, str | None]:
        """GET multiple OIDs in one request."""
        if not oids:
            return {}
        engine    = await self._get_engine()
        transport = await self._transport()
        obj_types = [ObjectType(ObjectIdentity(o)) for o in oids]

        error_indication, error_status, _, var_binds = await getCmd(
            engine,
            self._community_data(),
            transport,
            ContextData(),
            *obj_types,
        )
        if error_indication or error_status:
            _LOGGER.debug("SNMP GET_MANY error: %s %s", error_indication, error_status)
            return {oid: None for oid in oids}

        result: dict[str, str | None] = {}
        for oid, (_, val) in zip(oids, var_binds):
            raw = val.prettyPrint()
            result[oid] = None if ("No Such" in raw or "No more" in raw) else raw
        return result

    async def walk(self, base_oid: str) -> dict[str, str]:
        """SNMP walk. Returns {suffix: value} dict."""
        engine    = await self._get_engine()
        transport = await self._transport()
        results: dict[str, str] = {}

        async for (error_indication, error_status, _, var_binds) in nextCmd(
            engine,
            self._community_data(),
            transport,
            ContextData(),
            ObjectType(ObjectIdentity(base_oid)),
            lexicographicMode=False,
        ):
            if error_indication:
                _LOGGER.debug("SNMP WALK error [%s]: %s", base_oid, error_indication)
                break
            if error_status:
                _LOGGER.debug("SNMP WALK status [%s]: %s", base_oid, error_status)
                break
            for var_bind in var_binds:
                oid_str = str(var_bind[0])
                val_str = var_bind[1].prettyPrint()
                if "No Such" in val_str or "No more" in val_str:
                    continue
                prefix = base_oid + "."
                suffix = oid_str[len(prefix):] if oid_str.startswith(prefix) else oid_str
                results[suffix] = val_str
        return results

    async def test_connection(self) -> bool:
        """Quick connectivity check — read sysDescr."""
        return await self.get("1.3.6.1.2.1.1.1.0") is not None
