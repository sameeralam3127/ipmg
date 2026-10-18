"""Scan comparison engine.

Pure, side-effect free logic: it takes two sets of host snapshots and returns
the changes between them. Nothing here touches the database, the filesystem or
the console, so it can be reused by the CLI, the web API and the tests alike.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

#: Statuses that mean the host answered the probe.
REACHABLE_STATUSES = frozenset({"Active"})


class ChangeType(str, Enum):
    """Every kind of difference IPMG can report between two scans."""

    NEW_HOST = "new_host"
    HOST_REMOVED = "host_removed"
    HOST_OFFLINE = "host_offline"
    HOST_ONLINE = "host_online"
    IP_CHANGED = "ip_changed"
    HOSTNAME_CHANGED = "hostname_changed"
    LATENCY_CHANGED = "latency_changed"
    SERVICE_CHANGED = "service_changed"
    #: A different MAC answers at the same IP (``--mac``): another device took
    #: the address, or something is impersonating it.
    MAC_CHANGED = "mac_changed"
    #: ``--http-check`` changes. The change's ``ip`` holds the checked URL.
    HTTP_FAILING = "http_failing"
    HTTP_RECOVERED = "http_recovered"
    HTTP_STATUS_CHANGED = "http_status_changed"
    #: ``--snmp`` changes, about the device at ``ip``: its uptime started
    #: again, an enabled interface stopped or resumed passing traffic, or its
    #: agent stopped or resumed answering.
    DEVICE_REBOOTED = "device_rebooted"
    INTERFACE_DOWN = "interface_down"
    INTERFACE_UP = "interface_up"
    SNMP_FAILING = "snmp_failing"
    SNMP_RECOVERED = "snmp_recovered"


#: Changes about a checked URL rather than a host.
HTTP_CHANGE_TYPES = frozenset(
    {ChangeType.HTTP_FAILING, ChangeType.HTTP_RECOVERED, ChangeType.HTTP_STATUS_CHANGED}
)


class Severity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


_SEVERITY_BY_TYPE: dict[ChangeType, Severity] = {
    ChangeType.HOST_OFFLINE: Severity.CRITICAL,
    ChangeType.IP_CHANGED: Severity.WARNING,
    ChangeType.NEW_HOST: Severity.WARNING,
    ChangeType.HOST_REMOVED: Severity.WARNING,
    ChangeType.SERVICE_CHANGED: Severity.WARNING,
    ChangeType.MAC_CHANGED: Severity.WARNING,
    ChangeType.HTTP_FAILING: Severity.CRITICAL,
    ChangeType.HTTP_STATUS_CHANGED: Severity.WARNING,
    ChangeType.HTTP_RECOVERED: Severity.INFO,
    ChangeType.DEVICE_REBOOTED: Severity.WARNING,
    ChangeType.INTERFACE_DOWN: Severity.WARNING,
    ChangeType.SNMP_FAILING: Severity.WARNING,
    ChangeType.INTERFACE_UP: Severity.INFO,
    ChangeType.SNMP_RECOVERED: Severity.INFO,
    ChangeType.HOST_ONLINE: Severity.INFO,
    ChangeType.HOSTNAME_CHANGED: Severity.INFO,
    ChangeType.LATENCY_CHANGED: Severity.INFO,
}

_SEVERITY_RANK = {Severity.CRITICAL: 0, Severity.WARNING: 1, Severity.INFO: 2}


def meets_severity(severity: Severity, minimum: Severity) -> bool:
    """Whether ``severity`` is at least as serious as ``minimum``."""
    return _SEVERITY_RANK[severity] <= _SEVERITY_RANK[minimum]


_TYPE_RANK = {change_type: index for index, change_type in enumerate(ChangeType)}

CHANGE_LABELS: dict[ChangeType, str] = {
    ChangeType.NEW_HOST: "New host",
    ChangeType.HOST_REMOVED: "Host removed",
    ChangeType.HOST_OFFLINE: "Host offline",
    ChangeType.HOST_ONLINE: "Host back online",
    ChangeType.IP_CHANGED: "IP address changed",
    ChangeType.HOSTNAME_CHANGED: "Hostname changed",
    ChangeType.LATENCY_CHANGED: "Latency changed",
    # The key stays "service_changed" for existing JSON consumers; the change
    # is a move between failure modes (Timeout -> Unreachable), not a service.
    ChangeType.SERVICE_CHANGED: "Status changed",
    ChangeType.MAC_CHANGED: "MAC address changed",
    ChangeType.HTTP_FAILING: "HTTP check failing",
    ChangeType.HTTP_RECOVERED: "HTTP check recovered",
    ChangeType.HTTP_STATUS_CHANGED: "HTTP status changed",
    ChangeType.DEVICE_REBOOTED: "Device rebooted",
    ChangeType.INTERFACE_DOWN: "Interface down",
    ChangeType.INTERFACE_UP: "Interface back up",
    ChangeType.SNMP_FAILING: "SNMP not answering",
    ChangeType.SNMP_RECOVERED: "SNMP answering again",
}

#: sysUpTime counts hundredths of a second in 32 bits, so it wraps to zero
#: every 497 days without a reboot.
UPTIME_WRAP_S = 2**32 / 100

#: Operational states that mean an enabled interface is not passing traffic.
INTERFACE_DOWN_STATES = frozenset({"down", "notPresent", "lowerLayerDown"})


def format_uptime(seconds: float | None) -> str:
    """``41d 3h``, ``5h 12m``, ``12m``, ``45s``: an uptime at a glance."""
    if seconds is None:
        return "-"
    whole = int(seconds)
    days, rest = divmod(whole, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, secs = divmod(rest, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m" if minutes else f"{secs}s"


@dataclass(frozen=True)
class HostSnapshot:
    """One host as observed by a single scan."""

    ip: str
    status: str
    latency: float | None = None
    hostname: str = ""
    #: Known only for scans run with ``--mac``.
    mac: str = ""

    @property
    def reachable(self) -> bool:
        return self.status in REACHABLE_STATUSES


@dataclass(frozen=True)
class HttpSnapshot:
    """One URL as checked by a single scan."""

    url: str
    ok: bool
    status_code: int | None = None
    failure: str = ""

    @property
    def label(self) -> str:
        """``200``, ``502``, ``timeout``: the check's result in one word."""
        if self.status_code is not None and self.failure in ("", "status"):
            return str(self.status_code)
        return self.failure or "unknown"


@dataclass(frozen=True)
class InterfaceSnapshot:
    """One interface of a polled device, as one scan saw it."""

    name: str
    alias: str = ""
    admin_status: str = ""
    oper_status: str = ""

    @property
    def down(self) -> bool:
        return self.admin_status == "up" and self.oper_status in INTERFACE_DOWN_STATES

    @property
    def up(self) -> bool:
        return self.oper_status == "up"

    @property
    def label(self) -> str:
        return f"{self.name} ({self.alias})" if self.alias else self.name


@dataclass(frozen=True)
class SnmpSnapshot:
    """One device as a single scan polled it with ``--snmp``."""

    ip: str
    ok: bool
    uptime_s: float | None = None
    failure: str = ""
    sys_name: str = ""
    #: When it was polled, ``YYYY-MM-DD HH:MM:SS``, to tell a reboot from a wrap.
    polled_at: str = ""
    interfaces: tuple[InterfaceSnapshot, ...] = ()


@dataclass(frozen=True)
class ScanRef:
    """Identifying metadata for one side of a comparison."""

    id: int | None = None
    label: str = ""
    started_at: str = ""
    source: str = ""

    def display(self, separator: str = "·") -> str:
        """Human-readable identity; the caller picks a separator its output
        can render (reports use UTF-8, terminals may not)."""
        parts = [f"#{self.id}" if self.id is not None else self.label or "scan"]
        if self.started_at:
            parts.append(self.started_at)
        if self.source:
            parts.append(self.source)
        return f" {separator} ".join(part for part in parts if part)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label or self.display(),
            "started_at": self.started_at,
            "source": self.source,
        }


@dataclass(frozen=True)
class DiffOptions:
    """Thresholds that decide when a difference is worth reporting.

    A latency change must clear *both* ``latency_abs_ms`` and ``latency_pct``
    so that noisy sub-millisecond jitter on fast links stays out of the report.
    """

    latency_abs_ms: float = 5.0
    latency_pct: float = 25.0
    include_unresolved_hostnames: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "latency_abs_ms": self.latency_abs_ms,
            "latency_pct": self.latency_pct,
            "include_unresolved_hostnames": self.include_unresolved_hostnames,
        }


@dataclass(frozen=True)
class HostChange:
    """A single detected difference for one host."""

    type: ChangeType
    ip: str
    hostname: str = ""
    previous: str | None = None
    current: str | None = None
    delta: float | None = None

    @property
    def severity(self) -> Severity:
        return _SEVERITY_BY_TYPE[self.type]

    @property
    def label(self) -> str:
        return CHANGE_LABELS[self.type]

    def describe(self) -> str:
        if self.previous is None and self.current is None:
            return self.label
        if self.previous is None:
            return f"{self.label}: {self.current}"
        if self.current is None:
            return f"{self.label}: was {self.previous}"
        return f"{self.label}: {self.previous} -> {self.current}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "label": self.label,
            "severity": self.severity.value,
            "ip": self.ip,
            "hostname": self.hostname,
            "previous": self.previous,
            "current": self.current,
            "delta": self.delta,
            "description": self.describe(),
        }


@dataclass(frozen=True)
class ScanDiff:
    """The full comparison between a baseline scan and a current scan."""

    baseline: ScanRef
    current: ScanRef
    changes: tuple[HostChange, ...] = ()
    baseline_hosts: int = 0
    current_hosts: int = 0
    compared_hosts: int = 0
    options: DiffOptions = field(default_factory=DiffOptions)

    @property
    def has_changes(self) -> bool:
        return bool(self.changes)

    @property
    def counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for change in self.changes:
            counts[change.type.value] = counts.get(change.type.value, 0) + 1
        return counts

    @property
    def severity_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for change in self.changes:
            counts[change.severity.value] = counts.get(change.severity.value, 0) + 1
        return counts

    @property
    def changed_hosts(self) -> int:
        return len({change.ip for change in self.changes if change.type not in HTTP_CHANGE_TYPES})

    @property
    def unchanged_hosts(self) -> int:
        changed_in_both = {
            change.ip
            for change in self.changes
            if change.type not in {ChangeType.NEW_HOST, ChangeType.HOST_REMOVED}
            and change.type not in HTTP_CHANGE_TYPES
        }
        return max(self.compared_hosts - len(changed_in_both), 0)

    def of_type(self, change_type: ChangeType) -> list[HostChange]:
        return [change for change in self.changes if change.type is change_type]

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline": self.baseline.to_dict(),
            "current": self.current.to_dict(),
            "options": self.options.to_dict(),
            "summary": {
                "baseline_hosts": self.baseline_hosts,
                "current_hosts": self.current_hosts,
                "compared_hosts": self.compared_hosts,
                "changed_hosts": self.changed_hosts,
                "unchanged_hosts": self.unchanged_hosts,
                "total_changes": len(self.changes),
                "counts": self.counts,
                "severity_counts": self.severity_counts,
            },
            "changes": [change.to_dict() for change in self.changes],
        }


# --------------------------------------------------------------------- helpers


def _index_by_ip(snapshots: Iterable[HostSnapshot]) -> dict[str, HostSnapshot]:
    """Map IP -> snapshot, keeping the last observation for duplicate IPs."""
    return {snapshot.ip: snapshot for snapshot in snapshots}


def _index_by_hostname(snapshots: Mapping[str, HostSnapshot]) -> dict[str, set[str]]:
    """Map hostname -> set of IPs that resolved to it."""
    index: dict[str, set[str]] = {}
    for snapshot in snapshots.values():
        hostname = (snapshot.hostname or "").strip().lower()
        if not hostname or hostname == "unresolvable":
            continue
        index.setdefault(hostname, set()).add(snapshot.ip)
    return index


def _index_by_mac(snapshots: Mapping[str, HostSnapshot]) -> dict[str, set[str]]:
    """Map MAC -> set of IPs it answered at. A device keeps its MAC when DHCP moves it."""
    index: dict[str, set[str]] = {}
    for snapshot in snapshots.values():
        mac = (snapshot.mac or "").strip().upper()
        if mac:
            index.setdefault(mac, set()).add(snapshot.ip)
    return index


def ip_sort_key(value: str) -> tuple[int, int, int, str]:
    """Sort key: IPv4 in numeric order, then IPv6, then anything unparsable.

    The family comes before the number, or ``::1`` (the integer 1) would sort
    ahead of every IPv4 address. Shared with the DB layer.
    """
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return (1, 0, 0, value)
    return (0, address.version, int(address), value)


def _sort_changes(changes: Sequence[HostChange]) -> tuple[HostChange, ...]:
    return tuple(
        sorted(
            changes,
            key=lambda change: (
                _SEVERITY_RANK[change.severity],
                _TYPE_RANK[change.type],
                ip_sort_key(change.ip),
            ),
        )
    )


def _latency_change(
    ip: str,
    hostname: str,
    before: HostSnapshot,
    after: HostSnapshot,
    options: DiffOptions,
) -> HostChange | None:
    if before.latency is None or after.latency is None:
        return None
    if not (before.reachable and after.reachable):
        return None

    delta = after.latency - before.latency
    if abs(delta) < options.latency_abs_ms:
        return None
    if before.latency > 0 and abs(delta) / before.latency * 100 < options.latency_pct:
        return None

    return HostChange(
        type=ChangeType.LATENCY_CHANGED,
        ip=ip,
        hostname=hostname,
        previous=f"{before.latency:.1f} ms",
        current=f"{after.latency:.1f} ms",
        delta=round(delta, 3),
    )


def _detect_ip_moves(
    baseline_hostnames: Mapping[str, set[str]],
    current_hostnames: Mapping[str, set[str]],
    current_by_ip: Mapping[str, HostSnapshot],
) -> tuple[list[HostChange], set[str], set[str]]:
    """Find hostnames that moved to a different IP.

    Returns the changes plus the sets of IPs that should therefore *not* be
    reported as brand new or removed hosts — they are the two ends of a move.
    """
    changes: list[HostChange] = []
    moved_to: set[str] = set()
    moved_from: set[str] = set()

    for hostname, current_ips in current_hostnames.items():
        baseline_ips = baseline_hostnames.get(hostname)
        if not baseline_ips or baseline_ips == current_ips:
            continue

        gained = current_ips - baseline_ips
        if not gained:
            continue

        lost = baseline_ips - current_ips
        previous = ", ".join(sorted(lost or baseline_ips, key=ip_sort_key))
        for ip in sorted(gained, key=ip_sort_key):
            snapshot = current_by_ip.get(ip)
            changes.append(
                HostChange(
                    type=ChangeType.IP_CHANGED,
                    ip=ip,
                    hostname=snapshot.hostname if snapshot else hostname,
                    previous=previous,
                    current=ip,
                )
            )
        moved_to.update(gained)
        moved_from.update(lost)

    return changes, moved_to, moved_from


def _compare_common_host(
    ip: str,
    before: HostSnapshot,
    after: HostSnapshot,
    options: DiffOptions,
) -> list[HostChange]:
    changes: list[HostChange] = []
    hostname = after.hostname or before.hostname

    if before.status != after.status:
        if before.reachable and not after.reachable:
            change_type = ChangeType.HOST_OFFLINE
        elif after.reachable and not before.reachable:
            change_type = ChangeType.HOST_ONLINE
        else:
            change_type = ChangeType.SERVICE_CHANGED
        changes.append(
            HostChange(
                type=change_type,
                ip=ip,
                hostname=hostname,
                previous=before.status,
                current=after.status,
            )
        )

    before_mac = (before.mac or "").strip().upper()
    after_mac = (after.mac or "").strip().upper()
    if before_mac and after_mac and before_mac != after_mac:
        changes.append(
            HostChange(
                type=ChangeType.MAC_CHANGED,
                ip=ip,
                hostname=hostname,
                previous=before_mac,
                current=after_mac,
            )
        )

    before_host = (before.hostname or "").strip()
    after_host = (after.hostname or "").strip()
    hostname_known = bool(before_host) or options.include_unresolved_hostnames
    if hostname_known and before_host.lower() != after_host.lower():
        changes.append(
            HostChange(
                type=ChangeType.HOSTNAME_CHANGED,
                ip=ip,
                hostname=after_host,
                previous=before_host or "(none)",
                current=after_host or "(none)",
            )
        )

    latency = _latency_change(ip, hostname, before, after, options)
    if latency is not None:
        changes.append(latency)

    return changes


def _compare_http(
    baseline: Iterable[HttpSnapshot], current: Iterable[HttpSnapshot]
) -> list[HostChange]:
    """Changes in URLs both scans checked. A URL only one of them checked says
    nothing about the service, so it is not reported."""
    before = {check.url: check for check in baseline}
    changes: list[HostChange] = []
    for after in current:
        previous = before.get(after.url)
        if previous is None:
            continue
        if previous.ok and not after.ok:
            change_type = ChangeType.HTTP_FAILING
        elif after.ok and not previous.ok:
            change_type = ChangeType.HTTP_RECOVERED
        elif previous.label != after.label:
            change_type = ChangeType.HTTP_STATUS_CHANGED
        else:
            continue
        changes.append(
            HostChange(type=change_type, ip=after.url, previous=previous.label, current=after.label)
        )
    return changes


def _elapsed_s(before: SnmpSnapshot, after: SnmpSnapshot) -> float:
    try:
        then = datetime.fromisoformat(before.polled_at)
        now = datetime.fromisoformat(after.polled_at)
    except ValueError:
        return 0.0
    return max((now - then).total_seconds(), 0.0)


def _rebooted(before: SnmpSnapshot, after: SnmpSnapshot) -> bool:
    if before.uptime_s is None or after.uptime_s is None or after.uptime_s >= before.uptime_s:
        return False
    # Past the wrap the counter starts again from zero on its own; a reboot
    # in that window cannot be told apart from it, so neither is reported.
    return before.uptime_s + _elapsed_s(before, after) < UPTIME_WRAP_S


def _interface_changes(
    ip: str, name: str, before: SnmpSnapshot, after: SnmpSnapshot
) -> Iterator[HostChange]:
    """Interfaces both scans saw that went down, or came back up."""
    previous = {interface.name: interface for interface in before.interfaces}
    for interface in after.interfaces:
        old = previous.get(interface.name)
        if old is None:
            continue
        if old.up and interface.down:
            yield HostChange(ChangeType.INTERFACE_DOWN, ip, name, current=interface.label)
        elif old.down and interface.up:
            yield HostChange(ChangeType.INTERFACE_UP, ip, name, current=interface.label)


def _compare_device(
    ip: str, name: str, before: SnmpSnapshot, after: SnmpSnapshot
) -> list[HostChange]:
    if before.ok and not after.ok:
        return [HostChange(ChangeType.SNMP_FAILING, ip, name, current=after.failure or "failed")]
    if after.ok and not before.ok:
        return [
            HostChange(ChangeType.SNMP_RECOVERED, ip, name, previous=before.failure or "failed")
        ]
    if not after.ok:
        return []
    changes = []
    if _rebooted(before, after):
        changes.append(
            HostChange(
                ChangeType.DEVICE_REBOOTED,
                ip,
                name,
                previous=f"up {format_uptime(before.uptime_s)}",
                current=f"up {format_uptime(after.uptime_s)}",
            )
        )
    changes.extend(_interface_changes(ip, name, before, after))
    return changes


def _compare_snmp(
    baseline: Iterable[SnmpSnapshot],
    current: Iterable[SnmpSnapshot],
    hosts: Mapping[str, HostSnapshot],
) -> list[HostChange]:
    """Changes in devices both scans polled. A device polled once has nothing to compare."""
    before = {device.ip: device for device in baseline}
    changes: list[HostChange] = []
    for after in current:
        previous = before.get(after.ip)
        if previous is None:
            continue
        host = hosts.get(after.ip)
        name = (host.hostname if host else "") or after.sys_name or previous.sys_name
        changes.extend(_compare_device(after.ip, name, previous, after))
    return changes


# ---------------------------------------------------------------- public API


def compare_snapshots(
    baseline: Iterable[HostSnapshot],
    current: Iterable[HostSnapshot],
    options: DiffOptions | None = None,
    baseline_ref: ScanRef | None = None,
    current_ref: ScanRef | None = None,
    baseline_http: Iterable[HttpSnapshot] = (),
    current_http: Iterable[HttpSnapshot] = (),
    baseline_snmp: Iterable[SnmpSnapshot] = (),
    current_snmp: Iterable[SnmpSnapshot] = (),
) -> ScanDiff:
    """Compare two sets of host snapshots (and HTTP checks and SNMP polls)."""
    options = options or DiffOptions()
    before_by_ip = _index_by_ip(baseline)
    after_by_ip = _index_by_ip(current)

    ip_changes, moved_to, moved_from = _detect_ip_moves(
        _index_by_hostname(before_by_ip),
        _index_by_hostname(after_by_ip),
        after_by_ip,
    )
    # The same device, recognised by its MAC rather than its name. A move
    # both identities saw is reported once.
    mac_changes, mac_to, mac_from = _detect_ip_moves(
        _index_by_mac(before_by_ip), _index_by_mac(after_by_ip), after_by_ip
    )
    ip_changes += [change for change in mac_changes if change.ip not in moved_to]
    moved_to |= mac_to
    moved_from |= mac_from
    changes: list[HostChange] = list(ip_changes)

    for ip in after_by_ip.keys() - before_by_ip.keys():
        if ip in moved_to:
            continue
        snapshot = after_by_ip[ip]
        changes.append(
            HostChange(
                type=ChangeType.NEW_HOST,
                ip=ip,
                hostname=snapshot.hostname,
                current=snapshot.status,
            )
        )

    for ip in before_by_ip.keys() - after_by_ip.keys():
        if ip in moved_from:
            continue
        snapshot = before_by_ip[ip]
        changes.append(
            HostChange(
                type=ChangeType.HOST_REMOVED,
                ip=ip,
                hostname=snapshot.hostname,
                previous=snapshot.status,
            )
        )

    common = before_by_ip.keys() & after_by_ip.keys()
    for ip in common:
        changes.extend(_compare_common_host(ip, before_by_ip[ip], after_by_ip[ip], options))
    changes.extend(_compare_http(baseline_http, current_http))
    changes.extend(_compare_snmp(baseline_snmp, current_snmp, after_by_ip))

    return ScanDiff(
        baseline=baseline_ref or ScanRef(label="baseline"),
        current=current_ref or ScanRef(label="current"),
        changes=_sort_changes(changes),
        baseline_hosts=len(before_by_ip),
        current_hosts=len(after_by_ip),
        compared_hosts=len(common),
        options=options,
    )
