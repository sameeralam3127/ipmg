"""Scan comparison engine.

Pure, side-effect free logic: it takes two sets of host snapshots and returns
the changes between them. Nothing here touches the database, the filesystem or
the console, so it can be reused by the CLI, the web API and the tests alike.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

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


class Severity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


_SEVERITY_BY_TYPE: Dict[ChangeType, Severity] = {
    ChangeType.HOST_OFFLINE: Severity.CRITICAL,
    ChangeType.IP_CHANGED: Severity.WARNING,
    ChangeType.NEW_HOST: Severity.WARNING,
    ChangeType.HOST_REMOVED: Severity.WARNING,
    ChangeType.SERVICE_CHANGED: Severity.WARNING,
    ChangeType.HOST_ONLINE: Severity.INFO,
    ChangeType.HOSTNAME_CHANGED: Severity.INFO,
    ChangeType.LATENCY_CHANGED: Severity.INFO,
}

_SEVERITY_RANK = {Severity.CRITICAL: 0, Severity.WARNING: 1, Severity.INFO: 2}

_TYPE_RANK = {change_type: index for index, change_type in enumerate(ChangeType)}

CHANGE_LABELS: Dict[ChangeType, str] = {
    ChangeType.NEW_HOST: "New host",
    ChangeType.HOST_REMOVED: "Host removed",
    ChangeType.HOST_OFFLINE: "Host offline",
    ChangeType.HOST_ONLINE: "Host back online",
    ChangeType.IP_CHANGED: "IP address changed",
    ChangeType.HOSTNAME_CHANGED: "Hostname changed",
    ChangeType.LATENCY_CHANGED: "Latency changed",
    ChangeType.SERVICE_CHANGED: "Service changed",
}


@dataclass(frozen=True)
class HostSnapshot:
    """One host as observed by a single scan."""

    ip: str
    status: str
    latency: Optional[float] = None
    hostname: str = ""

    @property
    def reachable(self) -> bool:
        return self.status in REACHABLE_STATUSES


@dataclass(frozen=True)
class ScanRef:
    """Identifying metadata for one side of a comparison."""

    id: Optional[int] = None
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

    def to_dict(self) -> Dict[str, Any]:
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

    def to_dict(self) -> Dict[str, Any]:
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
    previous: Optional[str] = None
    current: Optional[str] = None
    delta: Optional[float] = None

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

    def to_dict(self) -> Dict[str, Any]:
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
    changes: Tuple[HostChange, ...] = ()
    baseline_hosts: int = 0
    current_hosts: int = 0
    compared_hosts: int = 0
    options: DiffOptions = field(default_factory=DiffOptions)

    @property
    def has_changes(self) -> bool:
        return bool(self.changes)

    @property
    def counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for change in self.changes:
            counts[change.type.value] = counts.get(change.type.value, 0) + 1
        return counts

    @property
    def severity_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for change in self.changes:
            counts[change.severity.value] = counts.get(change.severity.value, 0) + 1
        return counts

    @property
    def changed_hosts(self) -> int:
        return len({change.ip for change in self.changes})

    @property
    def unchanged_hosts(self) -> int:
        changed_in_both = {
            change.ip
            for change in self.changes
            if change.type not in {ChangeType.NEW_HOST, ChangeType.HOST_REMOVED}
        }
        return max(self.compared_hosts - len(changed_in_both), 0)

    def of_type(self, change_type: ChangeType) -> List[HostChange]:
        return [change for change in self.changes if change.type is change_type]

    def to_dict(self) -> Dict[str, Any]:
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


def _index_by_ip(snapshots: Iterable[HostSnapshot]) -> Dict[str, HostSnapshot]:
    """Map IP -> snapshot, keeping the last observation for duplicate IPs."""
    return {snapshot.ip: snapshot for snapshot in snapshots}


def _index_by_hostname(snapshots: Mapping[str, HostSnapshot]) -> Dict[str, Set[str]]:
    """Map hostname -> set of IPs that resolved to it."""
    index: Dict[str, Set[str]] = {}
    for snapshot in snapshots.values():
        hostname = (snapshot.hostname or "").strip().lower()
        if not hostname or hostname == "unresolvable":
            continue
        index.setdefault(hostname, set()).add(snapshot.ip)
    return index


def ip_sort_key(value: str) -> Tuple[int, int, str]:
    """Sort key placing valid IPs first in numeric order; shared with the DB layer."""
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return (1, 0, value)
    return (0, int(address), "")


def _sort_changes(changes: Sequence[HostChange]) -> Tuple[HostChange, ...]:
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
) -> Optional[HostChange]:
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
    baseline_hostnames: Mapping[str, Set[str]],
    current_hostnames: Mapping[str, Set[str]],
    current_by_ip: Mapping[str, HostSnapshot],
) -> Tuple[List[HostChange], Set[str], Set[str]]:
    """Find hostnames that moved to a different IP.

    Returns the changes plus the sets of IPs that should therefore *not* be
    reported as brand new or removed hosts — they are the two ends of a move.
    """
    changes: List[HostChange] = []
    moved_to: Set[str] = set()
    moved_from: Set[str] = set()

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
) -> List[HostChange]:
    changes: List[HostChange] = []
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


# ---------------------------------------------------------------- public API


def compare_snapshots(
    baseline: Iterable[HostSnapshot],
    current: Iterable[HostSnapshot],
    options: Optional[DiffOptions] = None,
    baseline_ref: Optional[ScanRef] = None,
    current_ref: Optional[ScanRef] = None,
) -> ScanDiff:
    """Compare two sets of host snapshots and return every detected change."""
    options = options or DiffOptions()
    before_by_ip = _index_by_ip(baseline)
    after_by_ip = _index_by_ip(current)

    ip_changes, moved_to, moved_from = _detect_ip_moves(
        _index_by_hostname(before_by_ip),
        _index_by_hostname(after_by_ip),
        after_by_ip,
    )
    changes: List[HostChange] = list(ip_changes)

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

    return ScanDiff(
        baseline=baseline_ref or ScanRef(label="baseline"),
        current=current_ref or ScanRef(label="current"),
        changes=_sort_changes(changes),
        baseline_hosts=len(before_by_ip),
        current_hosts=len(after_by_ip),
        compared_hosts=len(common),
        options=options,
    )
