"""TCP connect checks: service discovery, and probing hosts that block ICMP."""

from __future__ import annotations

import concurrent.futures
import errno
import socket
import time
from collections.abc import Iterable

#: Common services worth a quick TCP connect once a host is known to be up.
DEFAULT_PORTS: tuple[int, ...] = (21, 22, 25, 53, 80, 443, 445, 1433, 3306, 3389, 5432)

PORT_SERVICES = {
    21: "FTP",
    22: "SSH",
    25: "SMTP",
    53: "DNS",
    80: "HTTP",
    443: "HTTPS",
    445: "SMB",
    1433: "MSSQL",
    3306: "MySQL",
    3389: "RDP",
    5432: "PostgreSQL",
}


def port_service_name(port: int) -> str:
    return PORT_SERVICES.get(port, "")


#: A refused connection is an answer: the host sent a TCP reset.
_REFUSED = frozenset(
    code for code in (errno.ECONNREFUSED, getattr(errno, "WSAECONNREFUSED", None)) if code
)
#: No route to the host or its network: a router said so, or nothing did.
_UNREACHABLE = frozenset(
    code
    for name in ("EHOSTUNREACH", "ENETUNREACH", "WSAEHOSTUNREACH", "WSAENETUNREACH")
    for code in (getattr(errno, name, None),)
    if code
)
_TIMED_OUT = frozenset(
    code
    for name in ("ETIMEDOUT", "EAGAIN", "EWOULDBLOCK", "WSAETIMEDOUT")
    for code in (getattr(errno, name, None),)
    if code
)

#: What one TCP connect attempt found.
OPEN = "open"
REFUSED = "refused"
TIMED_OUT = "timeout"
UNREACHABLE = "unreachable"
FAILED = "error"


def connect(ip: str, port: int, timeout: float) -> tuple[str, float | None]:
    """Try one TCP connection; returns the outcome and, if it answered, the time in ms.

    An accepted connection and a refused one (a TCP reset) both mean the
    host answered, so both carry a round-trip time.
    """
    try:
        # getaddrinfo picks the family (and an IPv6 scope id) from the address.
        family, kind, proto, _name, address = socket.getaddrinfo(
            ip, port, type=socket.SOCK_STREAM, flags=socket.AI_NUMERICHOST
        )[0]
        with socket.socket(family, kind, proto) as sock:
            sock.settimeout(timeout)
            started = time.perf_counter()
            code = sock.connect_ex(address)
            elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    except TimeoutError:
        return TIMED_OUT, None
    except OSError:
        return FAILED, None

    if code == 0:
        return OPEN, elapsed_ms
    if code in _REFUSED:
        return REFUSED, elapsed_ms
    if code in _UNREACHABLE:
        return UNREACHABLE, None
    if code in _TIMED_OUT:
        return TIMED_OUT, None
    return FAILED, None


def _probe(ip: str, port: int, timeout: float) -> bool:
    return connect(ip, port, timeout)[0] == OPEN


def tcp_probe(
    ip: str,
    ports: Iterable[int],
    timeout: float = 1.0,
    executor: concurrent.futures.Executor | None = None,
) -> tuple[str, float | None]:
    """Whether ``ip`` answers a TCP connection on any of ``ports``.

    Returns ``("Active", ms)`` as soon as one port accepts or refuses a
    connection, since either way the host answered. Otherwise the status the
    attempts point to: ``Unreachable`` if a router said there is no route,
    else ``Timeout``.
    """
    ports = list(ports)
    if not ports:
        return "Timeout", None
    if executor is None:
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(ports)) as own:
            return tcp_probe(ip, ports, timeout, executor=own)

    futures = [executor.submit(connect, ip, port, timeout) for port in ports]
    unreachable = False
    for future in concurrent.futures.as_completed(futures):
        outcome, latency = future.result()
        if outcome in (OPEN, REFUSED):
            # The rest finish on their own within the timeout; nobody waits.
            for other in futures:
                other.cancel()
            return "Active", latency
        unreachable = unreachable or outcome == UNREACHABLE
    return ("Unreachable" if unreachable else "Timeout"), None


def encode_ports(ports: Iterable[int]) -> str:
    """Compact comma-separated encoding used to persist open ports."""
    return ",".join(str(port) for port in ports)


def decode_ports(value: str) -> tuple[int, ...]:
    """Inverse of :func:`encode_ports`."""
    if not value:
        return ()
    return tuple(int(part) for part in value.split(",") if part.strip())


def parse_port_list(value: str) -> tuple[int, ...]:
    """Parse a comma-separated port list (e.g. ``"22,80,443"``), validating each entry."""
    ports: list[int] = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        port = int(part)
        if not 1 <= port <= 65535:
            raise ValueError(f"port out of range (1-65535): {port}")
        ports.append(port)
    if not ports:
        raise ValueError("port list must contain at least one port")
    return tuple(ports)


def scan_ports(
    ip: str,
    ports: Iterable[int],
    timeout: float = 1.0,
    executor: concurrent.futures.Executor | None = None,
) -> list[int]:
    """Probe ``ports`` on ``ip`` concurrently; return the ones that accepted a connection.

    Pass ``executor`` to share one bounded pool across many hosts; otherwise a
    pool with one worker per port is created for this call.
    """
    ports = list(ports)
    if not ports:
        return []

    if executor is None:
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(ports)) as own:
            return scan_ports(ip, ports, timeout, executor=own)

    futures = {executor.submit(_probe, ip, port, timeout): port for port in ports}
    open_ports = [
        futures[future] for future in concurrent.futures.as_completed(futures) if future.result()
    ]
    return sorted(open_ports)
