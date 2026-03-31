"""SNMP client for Cisco WLC CT2504 — built on puresnmp.

puresnmp loads plugins via importlib.import_module + os.listdir on the
FIRST Client() instantiation only. After that the results are cached in
the Loader object and subsequent Client() calls are instant.

HA's event loop detects these blocking calls, so we must run the first
instantiation in an executor to warm the cache before any async code
calls Client() directly.

Call `await SnmpClient.warmup()` once at integration setup. After that
all Client() calls inside async methods are safe (cache hit, no I/O).
"""
from __future__ import annotations

import asyncio
import logging
from ipaddress import ip_address
from socket import gethostbyname
from typing import Any

from puresnmp import Client
from puresnmp.credentials import V2C
from puresnmp.exc import NoSuchOID, Timeout, SnmpError

_LOGGER = logging.getLogger(__name__)
_WARMED_UP = False


def _warmup_sync() -> None:
    """Run in executor: instantiate one Client to trigger plugin discovery."""
    Client("127.0.0.1", V2C("public"))


async def warmup() -> None:
    """Pre-warm puresnmp plugin cache in executor (call once at HA startup)."""
    global _WARMED_UP
    if _WARMED_UP:
        return
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _warmup_sync)
    _WARMED_UP = True
    _LOGGER.debug("puresnmp plugin cache warmed up")


def _to_str(val: Any) -> str | None:
    """Convert a puresnmp/x690 value to a plain Python string."""
    if val is None:
        return None
    raw = val.pythonize() if hasattr(val, "pythonize") else val
    if isinstance(raw, bytes):
        try:
            decoded = raw.decode("utf-8").strip()
            # reject strings with non-printable control chars (except \r\n\t)
            if any(ord(c) < 32 and c not in "\r\n\t" for c in decoded):
                return raw.hex()
            return decoded
        except UnicodeDecodeError:
            return raw.hex()
    if isinstance(raw, int):
        return str(raw)
    return str(raw)


class SnmpClient:
    """Async SNMP v2c client — puresnmp, HA / Python 3.14 compatible."""

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
        """Return a Client instance. Plugin cache must already be warm."""
        return Client(
            self._host,
            V2C(self._community),
            port=self._port,
        )

    async def get(self, oid: str) -> str | None:
        """GET single OID. Returns string or None."""
        try:
            val = await self._client().get(oid)
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
        """GET multiple OIDs in one request."""
        if not oids:
            return {}
        try:
            results = await self._client().multiget(oids)
            return {oid: _to_str(val) for oid, val in zip(oids, results)}
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
        """SNMP walk. Returns {suffix: value}."""
        results: dict[str, str] = {}
        prefix = base_oid + "."
        try:
            async for oid, val in self._client().walk(base_oid):
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
