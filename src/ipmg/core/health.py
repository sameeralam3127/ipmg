"""Pass/fail checks on a finished scan, for cron jobs and monitoring probes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from ipmg.core.diff import ip_sort_key
from ipmg.core.engine import HostResult

ACTIVE_STATUS = "Active"

#: How many down hosts a failure message names before it summarises the rest.
MAX_NAMED_HOSTS = 5


@dataclass(frozen=True)
class HealthPolicy:
    """When a scan counts as failed. The default policy never fails."""

    #: Fail if any target is not ``Active``.
    fail_on_down: bool = False
    #: Fail if fewer than this percentage of targets are ``Active``.
    min_active_pct: Optional[float] = None

    @property
    def enabled(self) -> bool:
        return self.fail_on_down or self.min_active_pct is not None


def _name_hosts(ips: Sequence[str]) -> str:
    # Results arrive in completion order; the message should read like the target list.
    ips = sorted(ips, key=ip_sort_key)
    named = ", ".join(ips[:MAX_NAMED_HOSTS])
    hidden = len(ips) - MAX_NAMED_HOSTS
    return f"{named} and {hidden} more" if hidden > 0 else named


def _format_pct(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".") + "%"


def check_health(results: Sequence[HostResult], policy: HealthPolicy) -> Optional[str]:
    """Why ``results`` fail ``policy``, or None when they pass."""
    if not policy.enabled:
        return None

    total = len(results)
    down = [result.ip for result in results if result.status != ACTIVE_STATUS]
    active_pct = (total - len(down)) / total * 100 if total else 0.0

    if policy.min_active_pct is not None and active_pct < policy.min_active_pct:
        return (
            f"Only {_format_pct(active_pct)} of {total} hosts are active, "
            f"below --min-active {_format_pct(policy.min_active_pct)}."
        )
    if policy.fail_on_down and down:
        return f"{len(down)} of {total} hosts are not active: {_name_hosts(down)}."
    return None
