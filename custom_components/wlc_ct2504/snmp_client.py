"""Pure-Python async SNMP v2c client for Cisco WLC CT2504.

Zero external dependencies — uses only Python stdlib (asyncio, socket, struct).
No MIB loading, no plugin discovery, no blocking I/O at any point.

Implements:
  - GET  (single OID)
  - GET-MULTI (multiple OIDs in one request)
  - GETNEXT walk (iterative table walk)

BER encoding/decoding is hand-rolled for the exact subset needed by SNMP v2c.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

_LOGGER = logging.getLogger(__name__)

# ── BER ENCODER ───────────────────────────────────────────────────────────────

def _enc_len(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    if n < 0x100:
        return bytes([0x81, n])
    return bytes([0x82, (n >> 8) & 0xFF, n & 0xFF])

def _tlv(tag: int, value: bytes) -> bytes:
    return bytes([tag]) + _enc_len(len(value)) + value

def _enc_int(value: int) -> bytes:
    if value == 0:
        return _tlv(0x02, b'\x00')
    parts: list[int] = []
    n = value
    while n:
        parts.append(n & 0xFF)
        n >>= 8
    parts.reverse()
    if parts[0] & 0x80:
        parts.insert(0, 0)
    return _tlv(0x02, bytes(parts))

def _enc_oid(oid: str) -> bytes:
    parts = list(map(int, oid.strip('.').split('.')))
    buf = bytes([40 * parts[0] + parts[1]])
    for part in parts[2:]:
        if part == 0:
            buf += b'\x00'
        else:
            septets: list[int] = []
            p = part
            while p:
                septets.append(p & 0x7F)
                p >>= 7
            septets.reverse()
            for i, s in enumerate(septets):
                buf += bytes([s | (0x80 if i < len(septets) - 1 else 0)])
    return _tlv(0x06, buf)

def _build_pdu(pdu_tag: int, oids: list[str], request_id: int) -> bytes:
    """Build a GET (0xA0) or GETNEXT (0xA1) PDU."""
    null = _tlv(0x05, b'')
    varbinds = b''.join(_tlv(0x30, _enc_oid(oid) + null) for oid in oids)
    pdu = _tlv(pdu_tag,
        _enc_int(request_id) + _enc_int(0) + _enc_int(0) + _tlv(0x30, varbinds)
    )
    return pdu

def _build_message(community: str, pdu: bytes) -> bytes:
    return _tlv(0x30, _enc_int(1) + _tlv(0x04, community.encode()) + pdu)

# ── BER DECODER ───────────────────────────────────────────────────────────────

def _dec_len(data: bytes, off: int) -> tuple[int, int]:
    b = data[off]
    if b < 0x80:
        return b, off + 1
    n = b & 0x7F
    length = 0
    for i in range(n):
        length = (length << 8) | data[off + 1 + i]
    return length, off + 1 + n

def _dec_oid(data: bytes, off: int, length: int) -> str:
    end = off + length
    first = data[off]
    parts = [first // 40, first % 40]
    off += 1
    while off < end:
        value = 0
        while True:
            b = data[off]; off += 1
            value = (value << 7) | (b & 0x7F)
            if not (b & 0x80):
                break
        parts.append(value)
    return '.'.join(map(str, parts))

def _dec_value(data: bytes, off: int, tag: int, length: int) -> str | None:
    raw = data[off:off + length]
    # Integer-like types: INTEGER, Counter32, Gauge32, TimeTicks, Counter64
    if tag in (0x02, 0x41, 0x42, 0x43, 0x46):
        val = 0
        for b in raw:
            val = (val << 8) | b
        return str(val)
    # OctetString / similar
    if tag in (0x04, 0x40, 0x44, 0x45):
        try:
            decoded = raw.decode('utf-8').strip('\x00\r\n')
            if any(ord(c) < 32 and c not in '\r\n\t' for c in decoded):
                return raw.hex()
            return decoded
        except UnicodeDecodeError:
            return raw.hex()
    # OID
    if tag == 0x06:
        return _dec_oid(data, off, length)
    # noSuchObject / noSuchInstance / endOfMibView
    if tag in (0x80, 0x81, 0x82):
        return None
    # Anything else: hex
    return raw.hex() if raw else None

def _parse_response(data: bytes) -> list[tuple[str, str | None]]:
    """Parse SNMP response, return [(oid, value), ...]."""
    results: list[tuple[str, str | None]] = []
    off = 0
    # Outer SEQUENCE
    off += 1
    _, off = _dec_len(data, off)
    # Version (skip)
    off += 1; l, off = _dec_len(data, off); off += l
    # Community (skip)
    off += 1; l, off = _dec_len(data, off); off += l
    # PDU tag (GetResponse = 0xA2, Report = 0xA8)
    off += 1
    _, off = _dec_len(data, off)
    # request-id, error-status, error-index (skip 3 ints)
    for _ in range(3):
        off += 1; l, off = _dec_len(data, off); off += l
    # VarBindList SEQUENCE
    off += 1; vbl_len, off = _dec_len(data, off)
    end = off + vbl_len
    while off < end:
        # VarBind SEQUENCE
        off += 1; vb_len, off = _dec_len(data, off)
        vb_end = off + vb_len
        # OID
        off += 1; oid_len, off = _dec_len(data, off)
        oid = _dec_oid(data, off, oid_len); off += oid_len
        # Value
        val_tag = data[off]; off += 1
        val_len, off = _dec_len(data, off)
        val = _dec_value(data, off, val_tag, val_len)
        off += val_len
        results.append((oid, val))
        off = vb_end
    return results

# ── ASYNC UDP TRANSPORT ───────────────────────────────────────────────────────

class _SnmpProtocol(asyncio.DatagramProtocol):
    def __init__(self, future: asyncio.Future) -> None:
        self._future = future

    def datagram_received(self, data: bytes, addr: Any) -> None:
        if not self._future.done():
            self._future.set_result(data)

    def error_received(self, exc: Exception) -> None:
        if not self._future.done():
            self._future.set_exception(exc)

    def connection_lost(self, exc: Exception | None) -> None:
        if not self._future.done():
            self._future.cancel()


async def _udp_send_recv(
    host: str,
    port: int,
    packet: bytes,
    timeout: float,
) -> bytes:
    """Send UDP packet and wait for response. Pure asyncio, no blocking I/O."""
    loop = asyncio.get_event_loop()
    future: asyncio.Future[bytes] = loop.create_future()

    transport, _ = await loop.create_datagram_endpoint(
        lambda: _SnmpProtocol(future),
        remote_addr=(host, port),
    )
    try:
        transport.sendto(packet)
        return await asyncio.wait_for(future, timeout=timeout)
    finally:
        transport.close()

# ── PUBLIC CLIENT ─────────────────────────────────────────────────────────────

_REQ_ID = 0

def _next_req_id() -> int:
    global _REQ_ID
    _REQ_ID = (_REQ_ID + 1) & 0x7FFFFFFF
    return _REQ_ID


class SnmpClient:
    """Pure asyncio SNMP v2c client. No external dependencies."""

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
        self._timeout = float(timeout)
        self._retries = retries

    async def _request(self, pdu_tag: int, oids: list[str]) -> list[tuple[str, str | None]]:
        """Send SNMP GET or GETNEXT and return parsed varbinds."""
        req_id = _next_req_id()
        pdu = _build_pdu(pdu_tag, oids, req_id)
        packet = _build_message(self._community, pdu)

        last_exc: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                raw = await _udp_send_recv(self._host, self._port, packet, self._timeout)
                return _parse_response(raw)
            except asyncio.TimeoutError:
                last_exc = asyncio.TimeoutError(f"SNMP timeout {self._host}:{self._port}")
                _LOGGER.debug("SNMP timeout attempt %d/%d [%s]", attempt + 1, self._retries + 1, oids[0] if oids else "")
            except Exception as exc:
                last_exc = exc
                _LOGGER.debug("SNMP error attempt %d: %s", attempt + 1, exc)

        _LOGGER.debug("SNMP failed after %d attempts: %s", self._retries + 1, last_exc)
        return []

    async def get(self, oid: str) -> str | None:
        """GET single OID."""
        results = await self._request(0xA0, [oid])
        if not results:
            return None
        return results[0][1]

    async def get_many(self, oids: list[str]) -> dict[str, str | None]:
        """GET multiple OIDs in one request."""
        if not oids:
            return {}
        # Split into chunks of 20 to avoid oversized packets
        chunk_size = 20
        result: dict[str, str | None] = {}
        for i in range(0, len(oids), chunk_size):
            chunk = oids[i:i + chunk_size]
            varbinds = await self._request(0xA0, chunk)
            for oid, val in zip(chunk, varbinds):
                result[oid] = val[1] if varbinds else None
            # Fill missing
            for oid in chunk:
                if oid not in result:
                    result[oid] = None
        return result

    async def walk(self, base_oid: str) -> dict[str, str]:
        """SNMP walk via iterative GETNEXT. Returns {suffix: value}."""
        results: dict[str, str] = {}
        current_oid = base_oid
        prefix = base_oid + "."
        max_iter = 500  # safety limit

        for _ in range(max_iter):
            varbinds = await self._request(0xA1, [current_oid])
            if not varbinds:
                break
            returned_oid, val = varbinds[0]
            # Stop if we've walked past the base OID subtree
            if not (returned_oid == base_oid or returned_oid.startswith(prefix)):
                break
            if val is None:
                break
            suffix = returned_oid[len(prefix):] if returned_oid.startswith(prefix) else returned_oid
            results[suffix] = val
            current_oid = returned_oid

        return results

    async def test_connection(self) -> bool:
        """Quick connectivity check — read sysDescr."""
        return await self.get("1.3.6.1.2.1.1.1.0") is not None
