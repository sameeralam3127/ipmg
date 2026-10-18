"""Pass/fail checks on a finished scan, for cron jobs and monitoring probes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from ipmg.core.diff import ip_sort_key
from ipmg.core.engine import HostResult
from ipmg.core.httpcheck import HttpCheckResult
from ipmg.exceptions import IPMGError

ACTIVE_STATUS = "Active"

#: How many down hosts a failure message names before it summarises the rest.
MAX_NAMED_HOSTS = 5


class HostsDownError(IPMGError):
    """Raised after a finished scan fails --fail-on-down or --min-active."""


@dataclass(frozen=True)
class HealthPolicy:
    """When a scan counts as failed. The default policy never fails."""

    #: Fail if any target is not ``Active``, or any HTTP check failed.
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


def _name_urls(urls: Sequence[str]) -> str:
    named = ", ".join(urls[:MAX_NAMED_HOSTS])
    hidden = len(urls) - MAX_NAMED_HOSTS
    return f"{named} and {hidden} more" if hidden > 0 else named


def check_health(
    results: Sequence[HostResult],
    policy: HealthPolicy,
    http_results: Sequence[HttpCheckResult] = (),
) -> Optional[str]:
    """Why ``results`` fail ``policy``, or None when they pass."""
    if not policy.enabled:
        return None

    total = len(results)
    down = [result.ip for result in results if result.status != ACTIVE_STATUS]
    active_pct = (total - len(down)) / total * 100 if total else 0.0

    # A run of HTTP checks alone has no hosts to take a percentage of; an
    # empty host scan still fails, as it always has.
    hosts_checked = bool(total) or not http_results
    if policy.min_active_pct is not None and hosts_checked and active_pct < policy.min_active_pct:
        return (
            f"Only {_format_pct(active_pct)} of {total} hosts are active, "
            f"below --min-active {_format_pct(policy.min_active_pct)}."
        )
    if policy.fail_on_down and down:
        return f"{len(down)} of {total} hosts are not active: {_name_hosts(down)}."
    failing = [check.url for check in http_results if not check.ok]
    if policy.fail_on_down and failing:
        return f"{len(failing)} of {len(http_results)} HTTP checks failed: {_name_urls(failing)}."
    return None
