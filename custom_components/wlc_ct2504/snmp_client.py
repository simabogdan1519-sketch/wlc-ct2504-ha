"""Pure-Python async SNMP v2c client — stdlib only, no external dependencies."""
from __future__ import annotations

import asyncio
import logging

_LOGGER = logging.getLogger(__name__)

# ── BER ENCODER ───────────────────────────────────────────────────────────────

def _enc_len(n: int) -> bytes:
    if n < 0x80: return bytes([n])
    if n < 0x100: return bytes([0x81, n])
    return bytes([0x82, (n >> 8) & 0xFF, n & 0xFF])

def _tlv(tag: int, value: bytes) -> bytes:
    return bytes([tag]) + _enc_len(len(value)) + value

def _enc_int(value: int) -> bytes:
    if value == 0: return _tlv(0x02, b'\x00')
    parts: list[int] = []
    n = value
    while n:
        parts.append(n & 0xFF)
        n >>= 8
    parts.reverse()
    if parts[0] & 0x80: parts.insert(0, 0)
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
    if b < 0x80: return b, off + 1
    n = b & 0x7F
    length = 0
    for i in range(n): length = (length << 8) | data[off + 1 + i]
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
            if not (b & 0x80): break
        parts.append(value)
    return '.'.join(map(str, parts))

def _dec_value(data: bytes, off: int, tag: int, length: int) -> str | None:
    raw = data[off:off + length]
    if tag in (0x02, 0x41, 0x42, 0x43, 0x46):
        val = 0
        for b in raw: val = (val << 8) | b
        return str(val)
    if tag in (0x04, 0x40, 0x44, 0x45):
        try:
            decoded = raw.decode('utf-8').strip('\x00\r\n')
            if any(ord(c) < 32 and c not in '\r\n\t' for c in decoded):
                return raw.hex()
            return decoded
        except UnicodeDecodeError:
            return raw.hex()
    if tag == 0x06:
        return _dec_oid(data, off, length)
    if tag in (0x80, 0x81, 0x82):
        return None
    return raw.hex() if raw else None

def _parse_response(data: bytes) -> list[tuple[str, str | None]]:
    results: list[tuple[str, str | None]] = []
    off = 0
    off += 1; _, off = _dec_len(data, off)
    off += 1; l, off = _dec_len(data, off); off += l   # version
    off += 1; l, off = _dec_len(data, off); off += l   # community
    off += 1; _, off = _dec_len(data, off)              # pdu tag+len
    for _ in range(3): off += 1; l, off = _dec_len(data, off); off += l  # req/err/idx
    off += 1; vbl_len, off = _dec_len(data, off)
    end = off + vbl_len
    while off < end:
        off += 1; vb_len, off = _dec_len(data, off)
        vb_end = off + vb_len
        off += 1; oid_len, off = _dec_len(data, off)
        oid = _dec_oid(data, off, oid_len); off += oid_len
        val_tag = data[off]; off += 1
        val_len, off = _dec_len(data, off)
        val = _dec_value(data, off, val_tag, val_len)
        off += val_len
        results.append((oid, val))
        off = vb_end
    return results

# ── ASYNC UDP ─────────────────────────────────────────────────────────────────

class _SnmpProtocol(asyncio.DatagramProtocol):
    def __init__(self, future: asyncio.Future) -> None:
        self._future = future
    def datagram_received(self, data: bytes, addr) -> None:
        if not self._future.done(): self._future.set_result(data)
    def error_received(self, exc: Exception) -> None:
        if not self._future.done(): self._future.set_exception(exc)
    def connection_lost(self, exc) -> None:
        if not self._future.done(): self._future.cancel()

async def _udp_send_recv(host: str, port: int, packet: bytes, timeout: float) -> bytes:
    loop = asyncio.get_event_loop()
    future: asyncio.Future = loop.create_future()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: _SnmpProtocol(future),
        remote_addr=(host, port),
    )
    try:
        transport.sendto(packet)
        return await asyncio.wait_for(future, timeout=timeout)
    finally:
        transport.close()

# ── CLIENT ────────────────────────────────────────────────────────────────────

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
        req_id = _next_req_id()
        pdu = _build_pdu(pdu_tag, oids, req_id)
        packet = _build_message(self._community, pdu)
        for attempt in range(self._retries + 1):
            try:
                raw = await _udp_send_recv(self._host, self._port, packet, self._timeout)
                return _parse_response(raw)
            except asyncio.TimeoutError:
                _LOGGER.debug("SNMP timeout attempt %d [%s]", attempt + 1, oids[0] if oids else "")
            except Exception as exc:
                _LOGGER.debug("SNMP error attempt %d: %s", attempt + 1, exc)
        return []

    async def get(self, oid: str) -> str | None:
        """GET single OID."""
        results = await self._request(0xA0, [oid])
        if not results:
            return None
        return results[0][1]

    async def get_many(self, oids: list[str]) -> dict[str, str | None]:
        """GET multiple OIDs — each fetched individually in parallel.
        
        Individual GETs are more reliable than multi-OID GET on WLC:
        - No packet size issues
        - One OID failure doesn't affect others
        - WLC firmware quirks with multi-varbind responses avoided
        """
        if not oids:
            return {}

        async def _get_one(oid: str) -> tuple[str, str | None]:
            val = await self.get(oid)
            return oid, val

        results = await asyncio.gather(*[_get_one(oid) for oid in oids])
        return dict(results)

    async def walk(self, base_oid: str) -> dict[str, str]:
        """SNMP walk via iterative GETNEXT."""
        results: dict[str, str] = {}
        current_oid = base_oid
        prefix = base_oid + "."
        for _ in range(500):
            varbinds = await self._request(0xA1, [current_oid])
            if not varbinds:
                break
            returned_oid, val = varbinds[0]
            if not (returned_oid == base_oid or returned_oid.startswith(prefix)):
                break
            if val is None:
                break
            suffix = returned_oid[len(prefix):] if returned_oid.startswith(prefix) else returned_oid
            results[suffix] = val
            current_oid = returned_oid
        return results

    async def test_connection(self) -> bool:
        return await self.get("1.3.6.1.2.1.1.1.0") is not None
