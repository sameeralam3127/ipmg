"""MAC addresses and vendors of hosts on the local links (``--mac``).

On a local network the IP alone rarely identifies a device; its MAC address
and vendor (Apple, Cisco, Raspberry Pi...) usually do, and they stay put when
DHCP moves the device to another IP.

Probing a host on the local link makes the operating system resolve its MAC
(ARP for IPv4, neighbour discovery for IPv6), so after the probe the address
is in the OS neighbour table. This module reads that table with the system's
own tools: no raw sockets and no elevated privileges. A host beyond a router
is never in the table (the router's own MAC is listed under the router's IP),
so it gets an empty MAC rather than the router's.

Vendors come from the IEEE assignment lists bundled in ``ipmg/data``.
"""

from __future__ import annotations

import gzip
import logging
import platform
import re
import threading
import time
from importlib import resources
from typing import Callable, Dict, Optional, Tuple

from ipmg.core import discovery

log = logging.getLogger(__name__)

#: How a locally administered MAC is labelled in place of a vendor. Phones
#: and laptops randomise their MAC per network, and VMs and containers make
#: one up; neither has a registered vendor.
LOCALLY_ADMINISTERED = "Locally administered"

#: Neighbour states that mean the address did not (or no longer) answer.
_DEAD_STATES = frozenset({"failed", "incomplete", "none", "(incomplete)", "unreachable"})

_HEX_PAIRS = re.compile(r"^[0-9a-f]{1,2}([:-][0-9a-f]{1,2}){5}$", re.IGNORECASE)
_CISCO_DOTTED = re.compile(r"^[0-9a-f]{4}\.[0-9a-f]{4}\.[0-9a-f]{4}$", re.IGNORECASE)
_BARE = re.compile(r"^[0-9a-f]{12}$", re.IGNORECASE)


def normalize_mac(text: str) -> str:
    """``AA:BB:CC:DD:EE:FF`` for any common spelling, or "" if it is not a host's MAC.

    Accepts ``aa:bb:cc:dd:ee:ff``, ``aa-bb-...``, ``aabb.ccdd.eeff``,
    ``aabbccddeeff``, and macOS's unpadded ``0:1b:21:a:b:c``. Broadcast,
    multicast, and all-zero addresses are not a host's and give "".
    """
    value = (text or "").strip()
    if _HEX_PAIRS.match(value):
        octets = [int(part, 16) for part in re.split(r"[:-]", value)]
    elif _CISCO_DOTTED.match(value) or _BARE.match(value):
        digits = value.replace(".", "")
        octets = [int(digits[index : index + 2], 16) for index in range(0, 12, 2)]
    else:
        return ""
    if octets[0] & 0x01 or not any(octets):
        return ""
    return ":".join(f"{octet:02X}" for octet in octets)


# ----------------------------------------------------------------- parsers


def _key(ip: str, zone: str = "") -> str:
    """Link-local addresses are only meaningful with their interface."""
    if "%" not in ip and ip.lower().startswith("fe80:") and zone:
        return f"{ip}%{zone}"
    return ip


def parse_ip_neigh(output: str) -> Dict[str, str]:
    """Linux ``ip neigh show``: ``10.0.0.1 dev eth0 lladdr 52:54:00:12:34:56 REACHABLE``."""
    table: Dict[str, str] = {}
    for line in output.splitlines():
        fields = line.split()
        if len(fields) < 4 or "lladdr" not in fields or fields[-1].lower() in _DEAD_STATES:
            continue
        mac = normalize_mac(fields[fields.index("lladdr") + 1])
        zone = fields[fields.index("dev") + 1] if "dev" in fields[:-1] else ""
        if mac:
            table[_key(fields[0], zone)] = mac
    return table


def parse_proc_arp(text: str) -> Dict[str, str]:
    """Linux ``/proc/net/arp``, for systems without ``ip``; flags 0x0 is incomplete."""
    table: Dict[str, str] = {}
    for line in text.splitlines()[1:]:
        fields = line.split()
        if len(fields) < 4 or fields[2] == "0x0":
            continue
        mac = normalize_mac(fields[3])
        if mac:
            table[fields[0]] = mac
    return table


_BSD_ARP = re.compile(r"\((?P<ip>[0-9.]+)\) at (?P<mac>\S+)(?: on (?P<dev>\S+))?")


def parse_arp_an(output: str) -> Dict[str, str]:
    """macOS/BSD ``arp -an``: ``? (10.0.0.1) at 52:54:0:12:34:56 on en0 ifscope [ethernet]``."""
    table: Dict[str, str] = {}
    for line in output.splitlines():
        match = _BSD_ARP.search(line)
        if match is None:
            continue
        mac = normalize_mac(match["mac"])
        if mac:
            table[match["ip"]] = mac
    return table


def parse_ndp_an(output: str) -> Dict[str, str]:
    """macOS/BSD ``ndp -an``: ``fe80::1%en0  aa:bb:cc:dd:ee:ff  en0  23h59m  S R``."""
    table: Dict[str, str] = {}
    for line in output.splitlines():
        fields = line.split()
        if len(fields) < 3 or ":" not in fields[0]:
            continue
        mac = normalize_mac(fields[1])
        if mac:
            table[_key(fields[0], fields[2])] = mac
    return table


_WINDOWS_ARP = re.compile(r"^\s*(?P<ip>[0-9.]+)\s+(?P<mac>[0-9a-fA-F-]{17})\s+\S+")
_WINDOWS_INTERFACE = re.compile(r"^\S.*?\s(\d+):")


def parse_windows_arp(output: str) -> Dict[str, str]:
    """``arp -a``: ``  10.0.0.1           52-54-00-12-34-56     dynamic``."""
    table: Dict[str, str] = {}
    for line in output.splitlines():
        match = _WINDOWS_ARP.match(line)
        if match is None:
            continue
        mac = normalize_mac(match["mac"])
        if mac:
            table[match["ip"]] = mac
    return table


def parse_windows_neighbors(output: str) -> Dict[str, str]:
    """``netsh interface ipv6 show neighbors``, one table per ``Interface 12: ...``."""
    table: Dict[str, str] = {}
    zone = ""
    for line in output.splitlines():
        header = _WINDOWS_INTERFACE.match(line)
        if header:
            zone = header.group(1)
            continue
        fields = line.split()
        if len(fields) < 3 or ":" not in fields[0] or fields[-1].lower() in _DEAD_STATES:
            continue
        mac = normalize_mac(fields[1])
        if mac:
            table[_key(fields[0], zone)] = mac
    return table


def _run_command(argv) -> str:
    return discovery._run(argv)


def _read_proc_arp() -> str:
    try:
        with open("/proc/net/arp", encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return ""


def read_neighbour_table(system: Optional[str] = None) -> Dict[str, str]:
    """The OS neighbour table as IP -> MAC, for IPv4 and IPv6."""
    system = (system or platform.system()).lower()
    if system == "linux":
        table = parse_ip_neigh(_run_command(["ip", "neigh", "show"]))
        # Minimal images often lack iproute2; the kernel's table is still there.
        return table or parse_proc_arp(_read_proc_arp())
    if system == "windows":
        table = parse_windows_arp(_run_command(["arp", "-a"]))
        table.update(
            parse_windows_neighbors(
                _run_command(["netsh", "interface", "ipv6", "show", "neighbors"])
            )
        )
        return table
    table = parse_arp_an(_run_command(["arp", "-an"]))
    table.update(parse_ndp_an(_run_command(["ndp", "-an"])))
    return table


class NeighbourCache:
    """The neighbour table, shared by a scan's workers and re-read as hosts answer.

    A host's entry appears once its probe has finished, so :meth:`lookup`
    takes the time the probe ended (on :func:`time.perf_counter`) and re-reads
    the table when the copy held is older than that. Workers that need a fresh copy at the same moment
    share one read, and reads are at least ``min_interval_s`` apart, so a big
    scan runs the system tool a few times a second at most.
    """

    def __init__(
        self,
        reader: Optional[Callable[[], Dict[str, str]]] = None,
        min_interval_s: float = 0.25,
    ) -> None:
        self._reader = reader or read_neighbour_table
        self._min_interval_s = min_interval_s
        self._table: Dict[str, str] = {}
        self._read_at = float("-inf")
        self._reading = False
        self._condition = threading.Condition()

    def lookup(self, ip: str, answered_at: Optional[float] = None) -> str:
        """The MAC of ``ip``, or "" when the table has none for it."""
        answered_at = time.perf_counter() if answered_at is None else answered_at
        with self._condition:
            while self._read_at < answered_at:
                if self._reading:
                    self._condition.wait()
                    continue
                wait = self._read_at + self._min_interval_s - time.perf_counter()
                if wait > 0:
                    self._condition.wait(wait)
                    continue
                self._reading = True
                # perf_counter, not monotonic: on Windows monotonic ticks every
                # ~16 ms, so a probe that ended just after a read started looked
                # no newer than it, and its MAC was never read.
                started = time.perf_counter()
                self._condition.release()
                try:
                    table = self._reader()
                except Exception:  # a table that cannot be read means "no MAC"
                    log.debug("could not read the neighbour table", exc_info=True)
                    table = {}
                finally:
                    self._condition.acquire()
                    self._reading = False
                self._table = table
                self._read_at = started
                self._condition.notify_all()
            return self._table.get(ip) or self._table.get(ip.split("%", 1)[0], "")


# ----------------------------------------------------------------- vendors

_vendors: Optional[Dict[str, str]] = None
_vendors_lock = threading.Lock()


def _load_vendors() -> Dict[str, str]:
    global _vendors
    with _vendors_lock:
        if _vendors is None:
            vendors: Dict[str, str] = {}
            try:
                data = resources.files("ipmg").joinpath("data/oui.tsv.gz").read_bytes()
                for line in gzip.decompress(data).decode("utf-8").splitlines():
                    if not line or line.startswith("#"):
                        continue
                    prefix, _, name = line.partition("\t")
                    vendors[prefix] = name
            except (OSError, ValueError):
                log.debug("the bundled vendor database could not be read", exc_info=True)
            _vendors = vendors
        return _vendors


def vendor_for(mac: str) -> str:
    """The organisation the IEEE assigned ``mac``'s prefix to, or "" if unknown.

    The most specific block wins: 36-bit (MA-S), then 28-bit (MA-M), then
    24-bit (MA-L), since the large blocks are subdivided for small vendors.
    """
    normal = normalize_mac(mac)
    if not normal:
        return ""
    digits = normal.replace(":", "")
    if int(digits[:2], 16) & 0x02:
        return LOCALLY_ADMINISTERED
    vendors = _load_vendors()
    for length in (9, 7, 6):
        name = vendors.get(digits[:length])
        if name:
            return name
    return ""


def mac_and_vendor(cache: NeighbourCache, ip: str, answered_at: float) -> Tuple[str, str]:
    mac = cache.lookup(ip, answered_at)
    return mac, (vendor_for(mac) if mac else "")
