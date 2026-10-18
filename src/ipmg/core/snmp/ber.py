"""BER, the wire encoding SNMP messages use (X.690), for the types SNMP needs.

Only definite lengths and single-byte tags occur in SNMP, so that is all this
handles; anything else is malformed input and raises :class:`BerError`.
Decoding works on positions in the original bytes rather than on copies, so
the SNMPv3 code can find the authentication field inside a received message
and check its digest over exactly the bytes that were sent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Universal types.
INTEGER = 0x02
OCTET_STRING = 0x04
NULL = 0x05
OBJECT_IDENTIFIER = 0x06
SEQUENCE = 0x30

# Application types (RFC 2578).
IP_ADDRESS = 0x40
COUNTER32 = 0x41
GAUGE32 = 0x42
TIMETICKS = 0x43
OPAQUE = 0x44
COUNTER64 = 0x46

# What a varbind holds instead of a value (RFC 3416).
NO_SUCH_OBJECT = 0x80
NO_SUCH_INSTANCE = 0x81
END_OF_MIB_VIEW = 0x82
EXCEPTIONS = frozenset({NO_SUCH_OBJECT, NO_SUCH_INSTANCE, END_OF_MIB_VIEW})

# PDU types.
GET_REQUEST = 0xA0
GET_NEXT_REQUEST = 0xA1
RESPONSE = 0xA2
GET_BULK_REQUEST = 0xA5
REPORT = 0xA8

_UNSIGNED = frozenset({COUNTER32, GAUGE32, TIMETICKS, COUNTER64})

#: An object identifier as its arcs: (1, 3, 6, 1, 2, 1, 1, 5, 0).
Oid = tuple[int, ...]


class BerError(ValueError):
    """Bytes that are not a well-formed SNMP message."""


# ------------------------------------------------------------------ encoding


def encode_length(length: int) -> bytes:
    if length < 0x80:
        return bytes([length])
    body = length.to_bytes((length.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(body)]) + body


def tlv(tag: int, content: bytes) -> bytes:
    return bytes([tag]) + encode_length(len(content)) + content


def encode_int(value: int, tag: int = INTEGER) -> bytes:
    """A two's-complement INTEGER in the fewest bytes."""
    magnitude = value if value >= 0 else ~value
    return tlv(tag, value.to_bytes(magnitude.bit_length() // 8 + 1, "big", signed=True))


def encode_octets(value: bytes) -> bytes:
    return tlv(OCTET_STRING, value)


def encode_null() -> bytes:
    return tlv(NULL, b"")


def _base128(arc: int) -> bytes:
    chunks = [arc & 0x7F]
    arc >>= 7
    while arc:
        chunks.append(0x80 | (arc & 0x7F))
        arc >>= 7
    return bytes(reversed(chunks))


def encode_oid(oid: Oid) -> bytes:
    if len(oid) < 2 or oid[0] > 2 or (oid[0] < 2 and oid[1] >= 40):
        raise BerError(f"not a valid object identifier: {format_oid(oid)}")
    arcs = (oid[0] * 40 + oid[1], *oid[2:])
    return tlv(OBJECT_IDENTIFIER, b"".join(_base128(arc) for arc in arcs))


def parse_oid(text: str) -> Oid:
    try:
        return tuple(int(arc) for arc in text.strip(".").split("."))
    except ValueError:
        raise BerError(f"not an object identifier: {text!r}") from None


def format_oid(oid: Oid) -> str:
    return ".".join(str(arc) for arc in oid)


# ------------------------------------------------------------------ decoding


@dataclass(frozen=True)
class Element:
    """One TLV: its tag, and where its content sits in ``data``."""

    tag: int
    data: bytes
    start: int
    end: int

    @property
    def content(self) -> bytes:
        return self.data[self.start : self.end]

    def children(self) -> list[Element]:
        return decode_all(self.data, self.start, self.end)

    def expect(self, tag: int, what: str) -> Element:
        if self.tag != tag:
            raise BerError(f"{what}: expected tag 0x{tag:02x}, got 0x{self.tag:02x}")
        return self


def decode_element(data: bytes, offset: int = 0, limit: int | None = None) -> Element:
    """The TLV starting at ``offset``, which must end by ``limit``."""
    limit = len(data) if limit is None else limit
    if offset + 2 > limit:
        raise BerError("message truncated")
    tag, first = data[offset], data[offset + 1]
    start = offset + 2
    if tag & 0x1F == 0x1F:
        raise BerError("multi-byte tags do not occur in SNMP")
    if first & 0x80:
        count = first & 0x7F
        if not 1 <= count <= 4 or start + count > limit:
            raise BerError("bad length")
        length = int.from_bytes(data[start : start + count], "big")
        start += count
    else:
        length = first
    if start + length > limit:
        raise BerError("message truncated")
    return Element(tag, data, start, start + length)


def decode_all(data: bytes, start: int, end: int) -> list[Element]:
    """Every TLV between ``start`` and ``end``, in order."""
    elements = []
    offset = start
    while offset < end:
        element = decode_element(data, offset, end)
        elements.append(element)
        offset = element.end
    return elements


def decode_int(element: Element) -> int:
    content = element.content
    if not content:
        raise BerError("empty integer")
    signed = element.tag not in _UNSIGNED
    return int.from_bytes(content, "big", signed=signed)


def decode_oid(content: bytes) -> Oid:
    arcs: list[int] = []
    value = 0
    for byte in content:
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            arcs.append(value)
            value = 0
    if not arcs or content[-1] & 0x80:
        raise BerError("bad object identifier")
    first = arcs[0]
    head = (first // 40, first % 40) if first < 80 else (2, first - 80)
    return head + tuple(arcs[1:])


def decode_value(element: Element) -> Any:
    """A varbind's value as Python: int, bytes, str (IpAddress), Oid, or None."""
    tag = element.tag
    if tag == INTEGER or tag in _UNSIGNED:
        return decode_int(element)
    if tag in (OCTET_STRING, OPAQUE):
        return element.content
    if tag == OBJECT_IDENTIFIER:
        return decode_oid(element.content)
    if tag == IP_ADDRESS and len(element.content) == 4:
        return ".".join(str(byte) for byte in element.content)
    # NULL, the three exceptions, and anything unknown carry no usable value.
    return None


# ---------------------------------------------------------------------- PDUs


@dataclass(frozen=True)
class VarBind:
    oid: Oid
    tag: int
    value: Any

    @property
    def missing(self) -> bool:
        """noSuchObject, noSuchInstance, or endOfMibView instead of a value."""
        return self.tag in EXCEPTIONS


@dataclass(frozen=True)
class Pdu:
    type: int
    request_id: int
    error_status: int
    error_index: int
    varbinds: tuple[VarBind, ...]


def encode_pdu(
    pdu_type: int,
    request_id: int,
    oids: tuple[Oid, ...] | list[Oid],
    non_repeaters: int = 0,
    max_repetitions: int = 0,
) -> bytes:
    """A request PDU; GetBulk uses the two error fields for its own counts."""
    varbinds = b"".join(tlv(SEQUENCE, encode_oid(oid) + encode_null()) for oid in oids)
    return tlv(
        pdu_type,
        encode_int(request_id)
        + encode_int(non_repeaters)
        + encode_int(max_repetitions)
        + tlv(SEQUENCE, varbinds),
    )


def decode_pdu(element: Element) -> Pdu:
    if element.tag not in (RESPONSE, REPORT):
        raise BerError(f"unexpected PDU type 0x{element.tag:02x}")
    parts = element.children()
    if len(parts) != 4:
        raise BerError("malformed PDU")
    varbinds = []
    for item in parts[3].expect(SEQUENCE, "varbind list").children():
        pair = item.expect(SEQUENCE, "varbind").children()
        if len(pair) != 2:
            raise BerError("malformed varbind")
        name = pair[0].expect(OBJECT_IDENTIFIER, "varbind name")
        varbinds.append(VarBind(decode_oid(name.content), pair[1].tag, decode_value(pair[1])))
    return Pdu(
        type=element.tag,
        request_id=decode_int(parts[0].expect(INTEGER, "request-id")),
        error_status=decode_int(parts[1].expect(INTEGER, "error-status")),
        error_index=decode_int(parts[2].expect(INTEGER, "error-index")),
        varbinds=tuple(varbinds),
    )
