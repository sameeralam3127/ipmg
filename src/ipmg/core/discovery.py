"""Local subnet discovery for ``ipmg --discover``."""

from __future__ import annotations

import concurrent.futures
import ipaddress
import logging
import platform
import re
import socket
import subprocess  # nosec B404
from typing import List, Optional, Tuple

from ipmg.exceptions import DiscoveryError

#: Reserved documentation address (RFC 5737). Connecting a UDP socket to it
#: sends no packets but makes the OS pick the outbound interface for us.
_PROBE_TARGET = ("192.0.2.1", 9)

log = logging.getLogger(__name__)


def _address_from_route() -> Optional[str]:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    except OSError:
        log.debug("could not open a probe socket", exc_info=True)
        return None

    try:
        sock.connect(_PROBE_TARGET)
        return sock.getsockname()[0]
    except OSError:
        log.debug("could not determine the outbound interface address", exc_info=True)
        return None
    finally:
        sock.close()


def _address_from_hostname() -> Optional[str]:
    try:
        return socket.gethostbyname(socket.gethostname())
    except OSError:
        log.debug("could not resolve the local hostname", exc_info=True)
        return None


def local_ip_address() -> str:
    """Best-effort primary IPv4 address of this machine.

    The outbound-route probe is tried first because resolving the hostname
    often yields 127.0.0.1, which would make ``--discover`` scan loopback.
    """
    for candidate in (_address_from_route(), _address_from_hostname()):
        if not candidate:
            continue
        try:
            address = ipaddress.ip_address(candidate)
        except ValueError:
            continue
        if not (address.is_loopback or address.is_link_local or address.is_unspecified):
            return candidate

    raise DiscoveryError(
        "Could not determine this machine's network address. "
        "Pass targets explicitly with --input instead of --discover."
    )


DISCOVERY_FAMILIES = ("ipv4", "ipv6", "all")


def discover_targets(family: str) -> Tuple[List[str], List[str]]:
    """The hosts ``--discover FAMILY`` scans, and the history source name for each part.

    IPv4 keeps the name "auto-discovery" it always had, so history comparisons
    against scans made before IPv6 existed still find their baseline.
    """
    ips: List[str] = []
    sources: List[str] = []
    if family in ("ipv4", "all"):
        ips += discover_local_subnet()
        sources.append("auto-discovery")
    if family in ("ipv6", "all"):
        ips += discover_ipv6_neighbours()
        sources.append("auto-discovery-ipv6")
    return ips, sources


def discover_local_subnet(local_ip: Optional[str] = None, prefix: int = 24) -> List[str]:
    """Every host address in the /24 (by default) around the local address."""
    address = local_ip or local_ip_address()

    try:
        network = ipaddress.ip_network(f"{address}/{prefix}", strict=False)
    except ValueError as exc:
        raise DiscoveryError(f"Invalid local network '{address}/{prefix}': {exc}") from exc

    return [str(ip) for ip in network.hosts()]


# ------------------------------------------------------------------- IPv6

#: The all-nodes multicast group: every IPv6 host on a link answers it, which
#: fills the neighbour table that discovery then reads.
_ALL_NODES = "ff02::1"

#: Neighbour-table states that mean the address is not (or no longer) there.
_DEAD_STATES = frozenset({"failed", "incomplete", "unreachable", "(incomplete)"})

#: Seconds allowed for the all-nodes ping and for reading the neighbour table.
_IPV6_COMMAND_TIMEOUT = 5


def _run(argv: List[str]) -> str:
    """Run a fixed, trusted argv and return its output, or "" if it cannot run."""
    try:
        # A fixed argv, no shell; the only variable part is an interface name
        # the operating system itself reported.
        result = subprocess.run(  # nosec B603
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=_IPV6_COMMAND_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        log.debug("could not run %s", argv[0], exc_info=True)
        return ""
    return result.stdout


def _interfaces() -> List[Tuple[int, str]]:
    """Network interfaces other than loopback, as (index, name)."""
    try:
        interfaces = socket.if_nameindex()
    except OSError:
        log.debug("could not list network interfaces", exc_info=True)
        return []
    return [(index, name) for index, name in interfaces if not name.lower().startswith("lo")]


def _all_nodes_ping(system: str, index: int, name: str) -> List[str]:
    zone = str(index) if system == "windows" else name
    target = f"{_ALL_NODES}%{zone}"
    if system == "windows":
        return ["ping", "-n", "2", "-w", "1000", target]
    if system == "linux":
        return ["ping", "-6", "-c", "2", "-W", "1", target]
    return ["ping6", "-c", "2", target]


def _prime_neighbour_table(system: str) -> None:
    """Ping all-nodes on every link at once, so the table lists who answered."""
    argvs = [_all_nodes_ping(system, index, name) for index, name in _interfaces()]
    if not argvs:
        return
    # Capped: a container host can have dozens of bridge and veth interfaces.
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(argvs), 16)) as pool:
        list(pool.map(_run, argvs))


def _is_address(text: str) -> bool:
    """Whether a table row starts with an address, not a header or a ruler."""
    try:
        ipaddress.ip_address(text)
    except ValueError:
        return False
    return True


def _scoped(address: str, zone: str) -> str:
    """Link-local addresses only mean something with their interface attached."""
    if "%" not in address and address.lower().startswith("fe80:") and zone:
        return f"{address}%{zone}"
    return address


def parse_linux_neighbours(output: str) -> List[str]:
    """``ip -6 neigh show``: ``fe80::1 dev eth0 lladdr 52:54:00:12:34:56 REACHABLE``."""
    found = []
    for line in output.splitlines():
        fields = line.split()
        if not fields or not _is_address(fields[0]) or fields[-1].lower() in _DEAD_STATES:
            continue
        zone = fields[fields.index("dev") + 1] if "dev" in fields[:-1] else ""
        found.append(_scoped(fields[0], zone))
    return found


def parse_bsd_neighbours(output: str) -> List[str]:
    """``ndp -an``: ``fe80::1%en0  aa:bb:cc:dd:ee:ff  en0  23h59m  S R``."""
    found = []
    for line in output.splitlines():
        fields = line.split()
        if len(fields) < 3 or not _is_address(fields[0]) or fields[1].lower() in _DEAD_STATES:
            continue
        found.append(_scoped(fields[0], fields[2]))
    return found


_WINDOWS_INTERFACE = re.compile(r"^\S.*?\s(\d+):")


def parse_windows_neighbours(output: str) -> List[str]:
    """``netsh interface ipv6 show neighbors``, one table per ``Interface 12: ...``."""
    found = []
    zone = ""
    for line in output.splitlines():
        header = _WINDOWS_INTERFACE.match(line)
        if header:
            zone = header.group(1)
            continue
        fields = line.split()
        if len(fields) < 3 or not _is_address(fields[0]) or fields[-1].lower() in _DEAD_STATES:
            continue
        found.append(_scoped(fields[0], zone))
    return found


def _read_neighbour_table(system: str) -> List[str]:
    if system == "linux":
        return parse_linux_neighbours(_run(["ip", "-6", "neigh", "show"]))
    if system == "windows":
        return parse_windows_neighbours(_run(["netsh", "interface", "ipv6", "show", "neighbors"]))
    return parse_bsd_neighbours(_run(["ndp", "-an"]))


def _is_host(candidate: str) -> bool:
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        return False
    return address.version == 6 and not (
        address.is_multicast or address.is_unspecified or address.is_loopback
    )


def discover_ipv6_neighbours(system: Optional[str] = None) -> List[str]:
    """IPv6 hosts on the local links, found through neighbour discovery.

    An IPv6 subnet is far too large to sweep, so instead every link is asked
    who is there (a ping to all-nodes), and the neighbour table that fills is
    read back. Link-local addresses carry their interface, as in fe80::1%eth0.
    """
    system = (system or platform.system()).lower()
    _prime_neighbour_table(system)
    hosts = [address for address in _read_neighbour_table(system) if _is_host(address)]
    if not hosts:
        raise DiscoveryError(
            "No IPv6 neighbours were found on the local links. Check that IPv6 is "
            "enabled, or pass IPv6 targets explicitly with --input."
        )
    return list(dict.fromkeys(hosts))
