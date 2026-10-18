"""A small SNMP agent for the tests: v2c, and v3 with USM, on a loopback UDP port.

It answers GET and GETBULK from a dictionary MIB, and can be told to
misbehave the ways real agents do: stay silent, reject the time window, send
garbage, answer for someone else, or downgrade its security. It reuses IPMG's
own encoding, so interoperability with other agents is not what it proves;
``tests/test_snmp_agents.py`` runs against net-snmp and snmpsim for that.
"""

from __future__ import annotations

import socket
import threading
from dataclasses import dataclass, field

from ipmg.core.snmp import ber, usm
from ipmg.core.snmp.ber import (
    COUNTER32,
    COUNTER64,
    END_OF_MIB_VIEW,
    GAUGE32,
    GET_BULK_REQUEST,
    NO_SUCH_OBJECT,
    REPORT,
    RESPONSE,
    SEQUENCE,
    TIMETICKS,
    Oid,
)
from ipmg.core.snmp.client import _encode_v3, _parse_v3, _usm_parameters

_USM_STATS = (1, 3, 6, 1, 6, 3, 15, 1, 1)
UNSUPPORTED_SEC_LEVEL = (*_USM_STATS, 1, 0)
NOT_IN_TIME_WINDOW = (*_USM_STATS, 2, 0)
UNKNOWN_USER = (*_USM_STATS, 3, 0)
UNKNOWN_ENGINE_ID = (*_USM_STATS, 4, 0)
WRONG_DIGEST = (*_USM_STATS, 5, 0)
DECRYPTION_ERROR = (*_USM_STATS, 6, 0)


# ------------------------------------------------------------------ values


def octets(text: str | bytes) -> bytes:
    return ber.encode_octets(text.encode() if isinstance(text, str) else text)


def integer(value: int) -> bytes:
    return ber.encode_int(value)


def timeticks(value: int) -> bytes:
    return ber.encode_int(value, TIMETICKS)


def counter32(value: int) -> bytes:
    return ber.encode_int(value, COUNTER32)


def counter64(value: int) -> bytes:
    return ber.encode_int(value, COUNTER64)


def gauge32(value: int) -> bytes:
    return ber.encode_int(value, GAUGE32)


def object_id(oid: Oid) -> bytes:
    return ber.encode_oid(oid)


def ip_address(text: str) -> bytes:
    return ber.tlv(ber.IP_ADDRESS, bytes(int(part) for part in text.split(".")))


def switch_mib(
    name: str = "lab-switch",
    uptime_ticks: int = 360_000,
    ports: tuple[tuple[str, str, int, int], ...] = (
        ("Gi1/0/1", "Uplink", 1, 1),
        ("Gi1/0/2", "Printer", 1, 2),
        ("Gi1/0/3", "", 2, 2),
    ),
) -> dict[Oid, bytes]:
    """A switch: the system group, and ifTable and ifXTable for ``ports``.

    Each port is (ifName, ifAlias, ifAdminStatus, ifOperStatus).
    """
    mib: dict[Oid, bytes] = {
        (1, 3, 6, 1, 2, 1, 1, 1, 0): octets(f"{name} software\r\nline two"),
        (1, 3, 6, 1, 2, 1, 1, 2, 0): object_id((1, 3, 6, 1, 4, 1, 9, 1, 1)),
        (1, 3, 6, 1, 2, 1, 1, 3, 0): timeticks(uptime_ticks),
        (1, 3, 6, 1, 2, 1, 1, 5, 0): octets(name),
        (1, 3, 6, 1, 2, 1, 1, 6, 0): octets("rack 3"),
    }
    for index, (port, alias, admin, oper) in enumerate(ports, start=1):
        mib.update(
            {
                (1, 3, 6, 1, 2, 1, 2, 2, 1, 2, index): octets(f"GigabitEthernet{port[2:]}"),
                (1, 3, 6, 1, 2, 1, 2, 2, 1, 5, index): gauge32(1_000_000_000),
                (1, 3, 6, 1, 2, 1, 2, 2, 1, 7, index): integer(admin),
                (1, 3, 6, 1, 2, 1, 2, 2, 1, 8, index): integer(oper),
                (1, 3, 6, 1, 2, 1, 2, 2, 1, 10, index): counter32(1000 * index),
                (1, 3, 6, 1, 2, 1, 2, 2, 1, 16, index): counter32(500 * index),
                (1, 3, 6, 1, 2, 1, 31, 1, 1, 1, 1, index): octets(port),
                (1, 3, 6, 1, 2, 1, 31, 1, 1, 1, 6, index): counter64(2**40 + index),
                (1, 3, 6, 1, 2, 1, 31, 1, 1, 1, 10, index): counter64(2**39 + index),
                (1, 3, 6, 1, 2, 1, 31, 1, 1, 1, 15, index): gauge32(1000),
                (1, 3, 6, 1, 2, 1, 31, 1, 1, 1, 18, index): octets(alias),
            }
        )
    return mib


# ------------------------------------------------------------------- agent


@dataclass
class User:
    auth_protocol: str = ""
    auth_key: str = ""
    priv_key: str = ""


@dataclass
class Agent:
    """Answers on 127.0.0.1 (or ::1) until :meth:`stop`."""

    mib: dict[Oid, bytes] = field(default_factory=switch_mib)
    community: str = "public"
    users: dict[str, User] = field(default_factory=dict)
    context: str = ""
    engine_id: bytes = b"\x80\x00\x1f\x88\x80ipmg-test"
    boots: int = 7
    time: int = 1234
    host: str = "127.0.0.1"
    #: Misbehaviour switches.
    silent: bool = False
    time_window_rejects: int = 0
    garbage: bool = False
    stray_reply: bool = False
    downgrade: bool = False
    error_status: int = 0
    too_big_above: int = 0
    unknown_engine_rejects: int = 0
    #: GETBULK answered with genErr.
    bulk_error: bool = False
    #: The reply's digest is spoiled after signing.
    bad_reply_digest: bool = False
    #: Replies encrypted even to a request that was not.
    encrypt_always: bool = False
    #: Only ever answer with bytes that are not SNMP.
    only_garbage: bool = False
    received: int = 0

    def __post_init__(self) -> None:
        family = socket.AF_INET6 if ":" in self.host else socket.AF_INET
        self._sock = socket.socket(family, socket.SOCK_DGRAM)
        self._sock.bind((self.host, 0))
        self.port = self._sock.getsockname()[1]
        self._oids = sorted(self.mib)
        self._salt = 0
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._sock.close()
        self._thread.join(timeout=2)

    def __enter__(self) -> Agent:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.stop()

    # ---------------------------------------------------------- serving

    def _serve(self) -> None:
        while True:
            try:
                data, peer = self._sock.recvfrom(65535)
            except ConnectionResetError:
                # Windows reports an earlier reply's ICMP "port unreachable"
                # (a client that had already gone) on the next receive.
                continue
            except OSError:
                return
            self.received += 1
            if self.silent:
                continue
            try:
                replies = [b"\x30\x03\x02\x01"] if self.only_garbage else self._handle(data)
            except (ber.BerError, ValueError):
                continue
            for reply in replies:
                try:
                    self._sock.sendto(reply, peer)
                except OSError:
                    return

    def _handle(self, data: bytes) -> list[bytes]:
        version = ber.decode_int(ber.decode_element(data).children()[0])
        if version == 1:
            return self._v2c(data)
        return self._v3(data)

    # ------------------------------------------------------------- PDUs

    def _answer(self, pdu: ber.Element) -> tuple[int, bytes]:
        """(request-id, response PDU) for a GET or GETBULK PDU element."""
        request_id, first, second, varbinds = pdu.children()
        names = [ber.decode_oid(item.children()[0].content) for item in varbinds.children()]
        rid = ber.decode_int(request_id)
        if pdu.tag == GET_BULK_REQUEST:
            repetitions = ber.decode_int(second)
            if self.too_big_above and repetitions > self.too_big_above:
                return rid, self._response(rid, [], error_status=1)
            if self.bulk_error:
                return rid, self._response(rid, [], error_status=5)
            pairs = self._bulk(names, repetitions)
        else:
            pairs = [(oid, self.mib.get(oid, ber.tlv(NO_SUCH_OBJECT, b""))) for oid in names]
        return rid, self._response(rid, pairs, error_status=self.error_status)

    def _bulk(self, names: list[Oid], repetitions: int) -> list[tuple[Oid, bytes]]:
        pairs = []
        cursors = list(names)
        for _round in range(repetitions):
            for position, cursor in enumerate(cursors):
                following = [oid for oid in self._oids if oid > cursor]
                if following:
                    cursors[position] = following[0]
                    pairs.append((following[0], self.mib[following[0]]))
                else:
                    pairs.append((cursor, ber.tlv(END_OF_MIB_VIEW, b"")))
        return pairs

    @staticmethod
    def _response(
        request_id: int, pairs: list[tuple[Oid, bytes]], error_status: int = 0, tag: int = RESPONSE
    ) -> bytes:
        varbinds = b"".join(ber.tlv(SEQUENCE, ber.encode_oid(oid) + value) for oid, value in pairs)
        return ber.tlv(
            tag,
            ber.encode_int(request_id)
            + ber.encode_int(error_status)
            + ber.encode_int(0)
            + ber.tlv(SEQUENCE, varbinds),
        )

    # ------------------------------------------------------------ SNMPv2c

    def _v2c(self, data: bytes) -> list[bytes]:
        _version, community, pdu = ber.decode_element(data).children()
        if community.content.decode() != self.community:
            return []
        rid, response = self._answer(pdu)
        message = ber.tlv(SEQUENCE, ber.encode_int(1) + octets(self.community) + response)
        replies = []
        if self.stray_reply:
            stray = self._response(rid + 1, [])
            replies.append(ber.tlv(SEQUENCE, ber.encode_int(1) + octets(self.community) + stray))
        if self.garbage:
            replies.append(b"\x30\x05garbage")
        return [*replies, message]

    # ------------------------------------------------------------- SNMPv3

    def _report(self, message, oid: Oid, keys: usm.LocalKeys | None = None) -> list[bytes]:
        # An encrypted request's ID cannot be read without the key; 0 then.
        rid = 0
        if message.msg_data.tag == SEQUENCE:
            rid = ber.decode_int(message.msg_data.children()[2].children()[0])
        pdu = self._response(rid, [(oid, counter32(1))], tag=REPORT)
        return [self._reply(message.msg_id, pdu, keys, encrypt=False)]

    def _reply(
        self, msg_id: int, pdu: bytes, keys: usm.LocalKeys | None, encrypt: bool, user: bytes = b""
    ) -> bytes:
        scoped = ber.tlv(SEQUENCE, octets(self.engine_id) + octets(self.context) + pdu)
        flags = 0
        priv = b""
        data = scoped
        if keys is not None:
            flags |= 0x01
            if encrypt:
                flags |= 0x02
                self._salt += 1
                priv = self._salt.to_bytes(8, "big")
                data = octets(usm.encrypt(scoped, keys.priv_key, self.boots, self.time, priv))
        auth = bytes(usm.digest_length(keys.auth_protocol)) if keys is not None else b""
        security = _usm_parameters(self.engine_id, self.boots, self.time, user, auth, priv)
        reply, auth_at = _encode_v3(msg_id, flags, security, data)
        if keys is not None:
            digest = usm.sign(reply, keys.auth_key, keys.auth_protocol)
            if self.bad_reply_digest:
                digest = bytes(byte ^ 0xFF for byte in digest)
            reply = reply[:auth_at] + digest + reply[auth_at + len(digest) :]
        return reply

    def _v3(self, data: bytes) -> list[bytes]:
        message = _parse_v3(data)
        if not message.engine_id:
            return self._report(message, UNKNOWN_ENGINE_ID)
        if self.unknown_engine_rejects:
            self.unknown_engine_rejects -= 1
            return self._report(message, UNKNOWN_ENGINE_ID)
        user = self.users.get(message.user.decode())
        if user is None:
            return self._report(message, UNKNOWN_USER)
        return self._v3_authorized(message, user)

    def _v3_authorized(self, message, user: User) -> list[bytes]:
        keys = None
        if user.auth_key:
            keys = usm.local_keys(self.engine_id, user.auth_protocol, user.auth_key, user.priv_key)
        wants_auth, wants_priv = bool(message.flags & 0x01), bool(message.flags & 0x02)
        level_matches = wants_auth == bool(keys) and wants_priv == bool(user.priv_key)
        if not level_matches and not self.encrypt_always:
            return self._report(message, UNSUPPORTED_SEC_LEVEL)
        if keys is not None and not usm.verify(
            message.zeroed, keys.auth_key, keys.auth_protocol, message.auth_params
        ):
            return self._report(message, WRONG_DIGEST)
        if self.time_window_rejects:
            self.time_window_rejects -= 1
            return self._report(message, NOT_IN_TIME_WINDOW, keys)
        scoped = message.msg_data
        if wants_priv and keys is not None:
            plain = usm.decrypt(
                scoped.content, keys.priv_key, message.boots, message.time, message.priv_params
            )
            try:
                _engine, context, pdu = ber.decode_element(plain).children()
            except (ber.BerError, ValueError):
                return self._report(message, DECRYPTION_ERROR)
        else:
            _engine, context, pdu = scoped.children()
        if context.content.decode() != self.context:
            return []
        _rid, response = self._answer(pdu)
        if self.downgrade:
            return [self._reply(message.msg_id, response, None, encrypt=False, user=message.user)]
        encrypt = wants_priv or (self.encrypt_always and keys is not None and bool(keys.priv_key))
        return [self._reply(message.msg_id, response, keys, encrypt=encrypt, user=message.user)]
