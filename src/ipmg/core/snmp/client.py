"""One SNMP agent over UDP: v2c with a community string, or v3 with USM.

A :class:`Session` sends GET and GETBULK requests and returns the varbinds.
Every way a request can fail raises :class:`SnmpError` with a ``failure``
kind a report can show in one word (``timeout``, ``auth``, ``refused``...)
and a message that says what to check. Credentials never appear in either,
and :class:`Credentials` keeps its secrets out of its ``repr``.

SNMPv3 follows RFC 3414: the first request discovers the agent's engine ID
(an unauthenticated probe the agent answers with a report), and a request
the agent rejects as outside its time window is sent again once with the
boots and time that rejection carried.
"""

from __future__ import annotations

import ipaddress
import secrets
import socket
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from functools import partial
from typing import TypeVar

from ipmg.core.snmp import ber, usm
from ipmg.core.snmp.ber import (
    GET_BULK_REQUEST,
    GET_REQUEST,
    OCTET_STRING,
    REPORT,
    SEQUENCE,
    BerError,
    Element,
    Oid,
    Pdu,
    VarBind,
)

VERSIONS = ("2c", "3")

FAILURE_TIMEOUT = "timeout"
FAILURE_REFUSED = "refused"
FAILURE_AUTH = "auth"
FAILURE_ERROR = "error"
FAILURE_PROTOCOL = "protocol"
FAILURE_UNSUPPORTED = "unsupported"

#: Error statuses of RFC 3416, for the message when an agent returns one.
ERROR_NAMES = {
    1: "tooBig",
    2: "noSuchName",
    3: "badValue",
    4: "readOnly",
    5: "genErr",
    6: "noAccess",
    16: "authorizationError",
}
TOO_BIG = 1

_FLAG_AUTH = 0x01
_FLAG_PRIV = 0x02
_FLAG_REPORTABLE = 0x04
_USM = 3
_MAX_MESSAGE_SIZE = 65507
_RECV_BYTES = 65535

_USM_STATS = (1, 3, 6, 1, 6, 3, 15, 1, 1)
_NOT_IN_TIME_WINDOW = (*_USM_STATS, 2, 0)
_UNKNOWN_ENGINE_ID = (*_USM_STATS, 4, 0)
#: What each USM report means for the person running the scan.
_REPORTS: dict[Oid, str] = {
    (*_USM_STATS, 1, 0): "the agent does not allow this security level for the user",
    (*_USM_STATS, 3, 0): "the agent does not know this SNMPv3 user",
    (*_USM_STATS, 5, 0): "wrong SNMPv3 authentication key or protocol",
    (*_USM_STATS, 6, 0): "wrong SNMPv3 privacy key or protocol",
}

T = TypeVar("T")


class SnmpError(Exception):
    def __init__(self, failure: str, message: str, status: int = 0) -> None:
        super().__init__(message)
        self.failure = failure
        self.status = status


@dataclass(frozen=True)
class Credentials:
    """Who to authenticate as. The secrets are never part of the ``repr``."""

    community: str = field(default="public", repr=False)
    user: str = ""
    auth_protocol: str = "SHA"
    auth_key: str = field(default="", repr=False)
    priv_protocol: str = "AES"
    priv_key: str = field(default="", repr=False)
    #: SNMPv3 context name, for agents that serve several (a VRF, a VLAN).
    context: str = ""

    @property
    def security_level(self) -> str:
        if self.priv_key:
            return "authPriv"
        return "authNoPriv" if self.auth_key else "noAuthNoPriv"

    def problems(self, version: str) -> list[str]:
        """What is missing or inconsistent for ``version``; empty when usable."""
        if version != "3":
            return [] if self.community else ["an SNMP community string is empty"]
        problems = []
        if not self.user:
            problems.append("SNMPv3 needs a user name")
        if self.priv_key and not self.auth_key:
            problems.append("SNMPv3 privacy needs an authentication key as well")
        if self.auth_protocol not in usm.AUTH_PROTOCOLS:
            choices = ", ".join(usm.AUTH_PROTOCOLS)
            problems.append(f"unknown authentication protocol {self.auth_protocol!r} ({choices})")
        if self.priv_protocol not in usm.PRIV_PROTOCOLS:
            problems.append(f"unknown privacy protocol {self.priv_protocol!r} (AES)")
        for name, key in (("authentication", self.auth_key), ("privacy", self.priv_key)):
            if key and len(key) < 8:
                problems.append(f"the SNMPv3 {name} key must be at least 8 characters")
        return problems


def new_id() -> int:
    """A request or message ID: random, so a stray or spoofed reply rarely matches."""
    return secrets.randbelow(2**31 - 2) + 1


# ---------------------------------------------------------------- transport


class _Transport:
    """A connected UDP socket that retries until a reply is accepted."""

    def __init__(self, host: str, port: int) -> None:
        try:
            family = socket.AF_INET6 if ipaddress.ip_address(host).version == 6 else socket.AF_INET
        except ValueError:
            family = socket.AF_INET
        self._port = port
        self._sock = socket.socket(family, socket.SOCK_DGRAM)
        try:
            # Connected, so the OS drops datagrams from anyone but the agent
            # and reports an ICMP port unreachable as a refused connection.
            self._sock.connect((host, port))
        except OSError:
            self._sock.close()
            raise

    def close(self) -> None:
        self._sock.close()

    def exchange(
        self,
        message: bytes,
        accept: Callable[[bytes], T | None],
        timeout_s: float,
        retries: int,
        check: str = "the community string is right",
    ) -> T:
        """Send ``message`` until ``accept`` returns a reply, up to ``retries`` resends.

        ``check`` names the credentials to suspect when nothing answers: an
        agent drops a request with a wrong community, or one it cannot decrypt,
        without a word.
        """
        malformed = ""
        for _attempt in range(retries + 1):
            self._send(message)
            deadline = time.perf_counter() + timeout_s
            while (remaining := deadline - time.perf_counter()) > 0:
                data = self._receive(remaining)
                if data is None:
                    break
                try:
                    result = accept(data)
                except BerError as exc:
                    malformed = str(exc)
                    continue
                if result is not None:
                    return result
        if malformed:
            raise SnmpError(FAILURE_PROTOCOL, f"the agent's reply could not be read: {malformed}")
        raise SnmpError(
            FAILURE_TIMEOUT,
            f"no SNMP answer within {timeout_s:g}s x {retries + 1}: "
            f"check that SNMP is enabled and {check}",
        )

    def _send(self, message: bytes) -> None:
        try:
            self._sock.send(message)
        except ConnectionError as exc:
            raise self._refused() from exc

    def _receive(self, timeout_s: float) -> bytes | None:
        self._sock.settimeout(timeout_s)
        try:
            return self._sock.recv(_RECV_BYTES)
        except TimeoutError:
            return None
        except ConnectionError as exc:
            # ECONNREFUSED on Linux and macOS, WSAECONNRESET on Windows.
            raise self._refused() from exc

    def _refused(self) -> SnmpError:
        return SnmpError(FAILURE_REFUSED, f"no SNMP agent on UDP port {self._port}")


# ------------------------------------------------------------------ SNMPv2c


def _encode_v2c(community: bytes, pdu: bytes) -> bytes:
    return ber.tlv(SEQUENCE, ber.encode_int(1) + ber.encode_octets(community) + pdu)


def _accept_v2c(request_id: int, data: bytes) -> Pdu | None:
    parts = ber.decode_element(data).expect(SEQUENCE, "message").children()
    if len(parts) != 3 or ber.decode_int(parts[0]) != 1:
        return None
    pdu = ber.decode_pdu(parts[2])
    return pdu if pdu.request_id == request_id else None


# ------------------------------------------------------------------- SNMPv3


@dataclass(frozen=True)
class _Engine:
    """The agent's engine as last learned, and when."""

    id: bytes
    boots: int
    time: int
    learned_at: float

    def now(self) -> int:
        return self.time + int(time.perf_counter() - self.learned_at)


@dataclass(frozen=True)
class _V3Message:
    msg_id: int
    flags: int
    engine_id: bytes
    boots: int
    time: int
    user: bytes
    auth_params: bytes
    priv_params: bytes
    msg_data: Element
    #: The whole message with its authentication parameters zeroed, as signed.
    zeroed: bytes


class _Resync(Exception):
    def __init__(self, engine: _Engine) -> None:
        super().__init__("time window")
        self.engine = engine


def _usm_parameters(
    engine_id: bytes, boots: int, engine_time: int, user: bytes, auth: bytes, priv: bytes
) -> tuple[bytes, int]:
    """The USM security parameters, and where the auth digest sits in them."""
    head = (
        ber.encode_octets(engine_id)
        + ber.encode_int(boots)
        + ber.encode_int(engine_time)
        + ber.encode_octets(user)
    )
    auth_tlv = ber.encode_octets(auth)
    body = head + auth_tlv + ber.encode_octets(priv)
    encoded = ber.tlv(SEQUENCE, body)
    return encoded, len(encoded) - len(body) + len(head) + len(auth_tlv) - len(auth)


def _encode_v3(
    msg_id: int, flags: int, security: tuple[bytes, int], msg_data: bytes
) -> tuple[bytes, int]:
    """An SNMPv3 message, and the offset of the auth digest in it."""
    parameters, auth_at = security
    version = ber.encode_int(3)
    header = ber.tlv(
        SEQUENCE,
        ber.encode_int(msg_id)
        + ber.encode_int(_MAX_MESSAGE_SIZE)
        + ber.encode_octets(bytes([flags]))
        + ber.encode_int(_USM),
    )
    security_tlv = ber.encode_octets(parameters)
    body = version + header + security_tlv + msg_data
    message = ber.tlv(SEQUENCE, body)
    prefix = len(message) - len(body) + len(version) + len(header)
    return message, prefix + len(security_tlv) - len(parameters) + auth_at


def _parse_v3(data: bytes) -> _V3Message:
    parts = ber.decode_element(data).expect(SEQUENCE, "message").children()
    if len(parts) != 4 or ber.decode_int(parts[0]) != 3:
        raise BerError("not an SNMPv3 message")
    header = parts[1].expect(SEQUENCE, "header").children()
    if len(header) != 4 or ber.decode_int(header[3]) != _USM:
        raise BerError("not a USM message")
    flags = header[2].expect(OCTET_STRING, "flags").content
    security = parts[2].expect(OCTET_STRING, "security parameters")
    fields = ber.decode_element(data, security.start, security.end)
    usm_fields = fields.expect(SEQUENCE, "USM parameters").children()
    if len(usm_fields) != 6:
        raise BerError("malformed USM parameters")
    engine_id, boots, engine_time, user, auth, priv = usm_fields
    return _V3Message(
        msg_id=ber.decode_int(header[0]),
        flags=flags[0] if flags else 0,
        engine_id=engine_id.content,
        boots=ber.decode_int(boots),
        time=ber.decode_int(engine_time),
        user=user.content,
        auth_params=auth.content,
        priv_params=priv.content,
        msg_data=parts[3],
        zeroed=data[: auth.start] + bytes(auth.end - auth.start) + data[auth.end :],
    )


# ------------------------------------------------------------------ session


class Session:
    """Requests to one agent. Use as a context manager, or call :meth:`close`."""

    def __init__(
        self,
        host: str,
        port: int = 161,
        version: str = "2c",
        credentials: Credentials | None = None,
        timeout_s: float = 2.0,
        retries: int = 1,
    ) -> None:
        if version not in VERSIONS:
            raise ValueError(f"unsupported SNMP version {version!r}")
        self.version = version
        self._credentials = credentials or Credentials()
        self._timeout_s = timeout_s
        self._retries = retries
        self._engine: _Engine | None = None
        self._keys: usm.LocalKeys | None = None
        self._salt = secrets.randbits(64)
        self._transport = _Transport(host, port)

    def __enter__(self) -> Session:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._transport.close()

    # --------------------------------------------------------- requests

    def get(self, oids: Sequence[Oid]) -> tuple[VarBind, ...]:
        return self._request(GET_REQUEST, oids).varbinds

    def get_bulk(self, oids: Sequence[Oid], max_repetitions: int) -> tuple[VarBind, ...]:
        return self._request(GET_BULK_REQUEST, oids, max_repetitions=max_repetitions).varbinds

    def _request(self, pdu_type: int, oids: Sequence[Oid], max_repetitions: int = 0) -> Pdu:
        request_id = new_id()
        pdu = ber.encode_pdu(pdu_type, request_id, list(oids), 0, max_repetitions)
        if self.version == "2c":
            community = self._credentials.community.encode("utf-8")
            response = self._exchange(_encode_v2c(community, pdu), partial(_accept_v2c, request_id))
        else:
            response = self._v3_request(pdu, request_id)
        if response.error_status:
            name = ERROR_NAMES.get(response.error_status, str(response.error_status))
            raise SnmpError(
                FAILURE_ERROR, f"the agent answered with {name}", status=response.error_status
            )
        return response

    def _exchange(self, message: bytes, accept: Callable[[bytes], T | None]) -> T:
        check = "the community string is right"
        if self.version == "3":
            check = (
                "the user, keys, protocols, and context are right"
                if self._credentials.auth_key
                else "the user and context are right"
            )
        return self._transport.exchange(message, accept, self._timeout_s, self._retries, check)

    # ----------------------------------------------------------- SNMPv3

    def _v3_request(self, pdu: bytes, request_id: int) -> Pdu:
        engine = self._engine
        if engine is None:
            engine = self._discover()
            self._use_engine(engine)
        for _attempt in range(3):
            try:
                return self._v3_exchange(engine, pdu, request_id)
            except _Resync as resync:
                engine = resync.engine
                self._use_engine(engine)
        raise SnmpError(
            FAILURE_AUTH,
            "the agent kept rejecting the request as outside its time window",
        )

    def _use_engine(self, engine: _Engine) -> None:
        """Talk to ``engine`` from now on, with keys localized to its ID."""
        credentials = self._credentials
        if credentials.auth_key and (self._engine is None or self._engine.id != engine.id):
            self._keys = usm.local_keys(
                engine.id, credentials.auth_protocol, credentials.auth_key, credentials.priv_key
            )
        self._engine = engine

    def _discover(self) -> _Engine:
        """RFC 3414 4: an empty, unauthenticated request the agent answers with a report."""
        msg_id = new_id()
        scoped = ber.tlv(
            SEQUENCE,
            ber.encode_octets(b"")
            + ber.encode_octets(b"")
            + ber.encode_pdu(GET_REQUEST, new_id(), []),
        )
        security = _usm_parameters(b"", 0, 0, b"", b"", b"")
        message, _ = _encode_v3(msg_id, _FLAG_REPORTABLE, security, scoped)

        def accept(data: bytes) -> _Engine | None:
            reply = _parse_v3(data)
            if reply.msg_id != msg_id:
                return None
            if not reply.engine_id:
                raise SnmpError(FAILURE_PROTOCOL, "the agent did not report its engine ID")
            return _Engine(reply.engine_id, reply.boots, reply.time, time.perf_counter())

        return self._exchange(message, accept)

    def _flags(self) -> int:
        flags = _FLAG_REPORTABLE
        if self._keys is not None:
            flags |= _FLAG_AUTH
            if self._keys.priv_key:
                flags |= _FLAG_PRIV
        return flags

    def _next_salt(self) -> bytes:
        self._salt = (self._salt + 1) % 2**64
        return self._salt.to_bytes(8, "big")

    def _v3_exchange(self, engine: _Engine, pdu: bytes, request_id: int) -> Pdu:
        flags = self._flags()
        boots, engine_time = engine.boots, engine.now()
        context = self._credentials.context.encode("utf-8")
        scoped = ber.tlv(SEQUENCE, ber.encode_octets(engine.id) + ber.encode_octets(context) + pdu)
        msg_data, priv_params = scoped, b""
        if flags & _FLAG_PRIV and self._keys is not None:
            priv_params = self._next_salt()
            try:
                cipher_text = usm.encrypt(
                    scoped, self._keys.priv_key, boots, engine_time, priv_params
                )
            except usm.PrivacyUnavailable as exc:
                raise SnmpError(FAILURE_UNSUPPORTED, str(exc)) from exc
            msg_data = ber.encode_octets(cipher_text)

        auth = b""
        if self._keys is not None:
            auth = bytes(usm.digest_length(self._keys.auth_protocol))
        user = self._credentials.user.encode("utf-8")
        security = _usm_parameters(engine.id, boots, engine_time, user, auth, priv_params)
        msg_id = new_id()
        message, auth_at = _encode_v3(msg_id, flags, security, msg_data)
        if self._keys is not None:
            digest = usm.sign(message, self._keys.auth_key, self._keys.auth_protocol)
            message = message[:auth_at] + digest + message[auth_at + len(digest) :]
        return self._exchange(message, partial(self._accept_v3, msg_id, request_id, flags))

    def _accept_v3(self, msg_id: int, request_id: int, sent_flags: int, data: bytes) -> Pdu | None:
        reply = _parse_v3(data)
        if reply.msg_id != msg_id:
            return None
        self._check_authentication(reply)
        pdu = ber.decode_pdu(self._scoped_pdu(reply))
        if pdu.type == REPORT:
            raise self._report(pdu, reply)
        if pdu.request_id != request_id:
            return None
        # A reply to a protected request must be protected as well, or
        # anyone on the path could have written it.
        security = _FLAG_AUTH | _FLAG_PRIV
        if reply.flags & security != sent_flags & security:
            raise SnmpError(FAILURE_AUTH, "the agent replied with a lower security level")
        return pdu

    def _check_authentication(self, reply: _V3Message) -> None:
        if not reply.flags & _FLAG_AUTH:
            return
        keys = self._keys
        if keys is None or not usm.verify(
            reply.zeroed, keys.auth_key, keys.auth_protocol, reply.auth_params
        ):
            raise SnmpError(FAILURE_AUTH, "the agent's reply failed authentication")

    def _scoped_pdu(self, reply: _V3Message) -> Element:
        scoped = reply.msg_data
        if reply.flags & _FLAG_PRIV:
            if self._keys is None or not self._keys.priv_key:
                raise SnmpError(FAILURE_PROTOCOL, "the agent encrypted a reply nobody asked for")
            cipher_text = scoped.expect(OCTET_STRING, "encrypted PDU").content
            try:
                plain = usm.decrypt(
                    cipher_text, self._keys.priv_key, reply.boots, reply.time, reply.priv_params
                )
            except usm.PrivacyUnavailable as exc:
                raise SnmpError(FAILURE_UNSUPPORTED, str(exc)) from exc
            except ValueError as exc:
                raise BerError(str(exc)) from exc
            scoped = ber.decode_element(plain)
        parts = scoped.expect(SEQUENCE, "scoped PDU").children()
        if len(parts) != 3:
            raise BerError("malformed scoped PDU")
        return parts[2]

    def _report(self, pdu: Pdu, reply: _V3Message) -> Exception:
        """What a USM report means: resynchronize, or a failure to report."""
        oid = pdu.varbinds[0].oid if pdu.varbinds else ()
        if oid in (_NOT_IN_TIME_WINDOW, _UNKNOWN_ENGINE_ID):
            return _Resync(_Engine(reply.engine_id, reply.boots, reply.time, time.perf_counter()))
        message = _REPORTS.get(oid)
        if message is not None:
            return SnmpError(FAILURE_AUTH, message)
        return SnmpError(
            FAILURE_PROTOCOL, f"the agent rejected the request ({ber.format_oid(oid) or 'report'})"
        )
