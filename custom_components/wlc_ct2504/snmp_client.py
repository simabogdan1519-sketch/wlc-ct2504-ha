"""SNMP client for Cisco WLC CT2504 — built on puresnmp.

Replaces pysnmp which has multiple breaking changes on Python 3.14 / HA 2024+:
  - UdpTransportTarget() constructor removed (must use await .create())
  - .create() raises NotImplementedError on _resolve_address in HA event loop
  - Blocking MIB I/O on SnmpEngine() init

puresnmp is a clean async-native SNMP v2c library with no MIB loading,
no event loop issues, and straightforward value extraction.
"""
from __future__ import annotations

import logging
from typing import Any

from puresnmp import Client
from puresnmp.credentials import V2C
from puresnmp.exc import NoSuchOID, Timeout, SnmpError
from x690.types import OctetString, Integer, ObjectIdentifier

_LOGGER = logging.getLogger(__name__)


def _to_str(val: Any) -> str | None:
    """Convert a puresnmp/x690 value to a plain Python string."""
    if val is None:
        return None
    # x690 types all have .pythonize() or .value
    raw = val.pythonize() if hasattr(val, "pythonize") else val
    if isinstance(raw, bytes):
        # Try UTF-8, fall back to hex representation
        try:
            decoded = raw.decode("utf-8").strip()
            # If it looks like a hex dump (non-printable), return hex
            if any(ord(c) < 32 and c not in "\r\n\t" for c in decoded):
                return raw.hex()
            return decoded
        except UnicodeDecodeError:
            return raw.hex()
    if isinstance(raw, int):
        return str(raw)
    return str(raw)


class SnmpClient:
    """Async SNMP v2c client — uses puresnmp (Python 3.14 / HA compatible)."""

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

    def _client(self) -> Client:
        return Client(
            self._host,
            V2C(self._community),
            port=self._port,
        )

    async def get(self, oid: str) -> str | None:
        """GET a single OID. Returns string or None."""
        client = self._client()
        try:
            val = await client.get(oid)
            return _to_str(val)
        except NoSuchOID:
            return None
        except Timeout:
            _LOGGER.debug("SNMP GET timeout [%s@%s]", oid, self._host)
            return None
        except SnmpError as err:
            _LOGGER.debug("SNMP GET error [%s]: %s", oid, err)
            return None
        except Exception as err:
            _LOGGER.debug("SNMP GET unexpected [%s]: %s", oid, err)
            return None

    async def get_many(self, oids: list[str]) -> dict[str, str | None]:
        """GET multiple OIDs in one request (multiget)."""
        if not oids:
            return {}
        client = self._client()
        try:
            results = await client.multiget(oids)
            return {
                oid: _to_str(val)
                for oid, val in zip(oids, results)
            }
        except Timeout:
            _LOGGER.debug("SNMP multiget timeout [%s]", self._host)
            return {oid: None for oid in oids}
        except SnmpError as err:
            _LOGGER.debug("SNMP multiget error: %s", err)
            return {oid: None for oid in oids}
        except Exception as err:
            _LOGGER.debug("SNMP multiget unexpected: %s", err)
            return {oid: None for oid in oids}

    async def walk(self, base_oid: str) -> dict[str, str]:
        """SNMP walk. Returns {suffix: value} where suffix follows base_oid."""
        client = self._client()
        results: dict[str, str] = {}
        prefix = base_oid + "."
        try:
            async for oid, val in client.walk(base_oid):
                oid_str = str(oid)
                val_str = _to_str(val)
                if val_str is None:
                    continue
                suffix = oid_str[len(prefix):] if oid_str.startswith(prefix) else oid_str
                results[suffix] = val_str
        except Timeout:
            _LOGGER.debug("SNMP walk timeout [%s@%s]", base_oid, self._host)
        except SnmpError as err:
            _LOGGER.debug("SNMP walk error [%s]: %s", base_oid, err)
        except Exception as err:
            _LOGGER.debug("SNMP walk unexpected [%s]: %s", base_oid, err)
        return results

    async def test_connection(self) -> bool:
        """Quick connectivity check — read sysDescr."""
        return await self.get("1.3.6.1.2.1.1.1.0") is not None
