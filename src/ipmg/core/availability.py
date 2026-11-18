"""Availability, outage, latency, and SLA figures for one host, from its checks.

Pure functions over a list of :class:`Sample` (one per scan that checked the
host), so every figure can be tested with hand-written histories. Nothing here
touches the database or the clock.

These are *observed* figures. A scan is a sample, not a continuous probe: an
outage that starts and ends between two scans is invisible, and an outage's
length has the resolution of the scan interval.

Definitions, all over the checks in the window that fall outside a maintenance
window:

* **availability**: reachable checks divided by all checks.
* **outage**: a run of failed checks, from the first failed one to the first
  successful check after it. One still failing at the last check is *ongoing*.
* **MTTR**: the mean length of the outages that recovered.
* **MTBF**: operating time (the observed span less downtime and maintenance)
  divided by the number of outages, ongoing one included.
* **SLA violation**: a calendar day whose availability is below the target, or
  whose P95 latency is above the limit.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from fractions import Fraction
from typing import Any

from ipmg.core.diff import REACHABLE_STATUSES

#: The timestamp format scans are stored in: local time, to the second.
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


class TimeError(ValueError):
    """Raised for a time that cannot be read as local ``YYYY-MM-DD HH:MM[:SS]``."""


def parse_local(text: str) -> datetime:
    """Read a local time such as ``2026-11-18 02:00`` or ``2026-11-18T02:00:30``.

    Times are the server's local time, like every other time IPMG stores, so an
    offset (``Z``, ``+05:30``) is refused rather than guessed at.
    """
    cleaned = str(text).strip()
    if not cleaned:
        raise TimeError("A time is required.")
    if cleaned.endswith(("Z", "z")):
        raise TimeError(f"Give local time without a UTC offset: {text!r}")
    try:
        parsed = datetime.fromisoformat(cleaned.replace("T", " ").replace("t", " "))
    except ValueError as exc:
        raise TimeError(f"Not a time (use YYYY-MM-DD HH:MM): {text!r}") from exc
    if parsed.tzinfo is not None:
        raise TimeError(f"Give local time without a UTC offset: {text!r}")
    return parsed.replace(microsecond=0)


def format_local(moment: datetime) -> str:
    return moment.strftime(TIME_FORMAT)


@dataclass(frozen=True)
class Sample:
    """One check of the host by one scan."""

    at: datetime
    status: str
    latency: float | None = None
    scan_id: int | None = None

    @property
    def reachable(self) -> bool:
        return self.status in REACHABLE_STATUSES


@dataclass(frozen=True)
class MaintenanceWindow:
    """Planned downtime: ``starts_at`` is inside it, ``ends_at`` is not."""

    starts_at: datetime
    ends_at: datetime

    def covers(self, moment: datetime) -> bool:
        return self.starts_at <= moment < self.ends_at


@dataclass(frozen=True)
class SlaTarget:
    #: Percent of checks that must be reachable, above 0 and at most 100.
    availability: float
    #: Optional ceiling for P95 latency, in ms.
    latency_p95_ms: float | None = None


# ----------------------------------------------------------------- latency


def percentile(values: Sequence[float], fraction: float) -> float | None:
    """The ``fraction`` (0-1) quantile by linear interpolation; ``None`` if empty.

    The same method as NumPy's default, so a figure here can be reproduced in a
    spreadsheet with ``PERCENTILE.INC``.
    """
    if not values:
        return None
    if not 0.0 <= fraction <= 1.0:
        raise ValueError("fraction must be between 0 and 1")
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return float(ordered[low])
    return float(ordered[low] + (ordered[high] - ordered[low]) * (position - low))


def latency_stats(latencies: Iterable[float | None]) -> dict[str, Any]:
    """Count, min, mean, P50, P95, P99, and max of the latencies that exist."""
    values = [
        float(value) for value in latencies if value is not None and math.isfinite(float(value))
    ]
    if not values:
        return {key: None for key in ("min", "mean", "p50", "p95", "p99", "max")} | {"count": 0}
    return {
        "count": len(values),
        "min": _round(min(values)),
        "mean": _round(sum(values) / len(values)),
        "p50": _round(percentile(values, 0.50)),
        "p95": _round(percentile(values, 0.95)),
        "p99": _round(percentile(values, 0.99)),
        "max": _round(max(values)),
    }


def reply_latencies(samples: Iterable[Sample]) -> list[float]:
    """Latencies of the checks that were answered and measured, finite only."""
    return [
        float(sample.latency)
        for sample in samples
        if sample.reachable and sample.latency is not None and math.isfinite(float(sample.latency))
    ]


def _round(value: float | None, places: int = 2) -> float | None:
    return None if value is None else round(value, places)


# ------------------------------------------------------------- maintenance


def merge_windows(windows: Iterable[MaintenanceWindow]) -> list[MaintenanceWindow]:
    """Overlapping or touching windows joined, in time order."""
    merged: list[MaintenanceWindow] = []
    for window in sorted(windows, key=lambda item: (item.starts_at, item.ends_at)):
        if window.ends_at <= window.starts_at:
            continue
        if merged and window.starts_at <= merged[-1].ends_at:
            if window.ends_at > merged[-1].ends_at:
                merged[-1] = MaintenanceWindow(merged[-1].starts_at, window.ends_at)
        else:
            merged.append(window)
    return merged


def in_maintenance(moment: datetime, windows: Iterable[MaintenanceWindow]) -> bool:
    return any(window.covers(moment) for window in windows)


def overlap_seconds(
    start: datetime, end: datetime, merged_windows: Sequence[MaintenanceWindow]
) -> float:
    """Seconds of ``[start, end)`` that fall inside already-merged windows."""
    if end <= start:
        return 0.0
    total = 0.0
    for window in merged_windows:
        low = max(start, window.starts_at)
        high = min(end, window.ends_at)
        if high > low:
            total += (high - low).total_seconds()
    return total


# ----------------------------------------------------------------- outages


@dataclass(frozen=True)
class Outage:
    started_at: datetime
    #: ``None`` while the host is still failing at the last check.
    ended_at: datetime | None
    #: Seconds, less any maintenance inside it. For an ongoing outage, up to the last check.
    duration_s: float
    #: Failed checks in a row.
    checks: int

    @property
    def ongoing(self) -> bool:
        return self.ended_at is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": format_local(self.started_at),
            "ended_at": format_local(self.ended_at) if self.ended_at else None,
            "duration_s": round(self.duration_s, 1),
            "checks": self.checks,
            "ongoing": self.ongoing,
        }


def find_outages(
    samples: Sequence[Sample], merged_windows: Sequence[MaintenanceWindow] = ()
) -> list[Outage]:
    """Outages in ``samples``, which must already be in time order and exclude maintenance."""
    outages: list[Outage] = []
    started: datetime | None = None
    failed = 0
    for sample in samples:
        if not sample.reachable:
            if started is None:
                started, failed = sample.at, 0
            failed += 1
        elif started is not None:
            outages.append(
                Outage(
                    started,
                    sample.at,
                    max((sample.at - started).total_seconds(), 0.0)
                    - overlap_seconds(started, sample.at, merged_windows),
                    failed,
                )
            )
            started = None
    if started is not None and samples:
        last = samples[-1].at
        outages.append(
            Outage(
                started,
                None,
                max((last - started).total_seconds(), 0.0)
                - overlap_seconds(started, last, merged_windows),
                failed,
            )
        )
    return [
        Outage(item.started_at, item.ended_at, max(item.duration_s, 0.0), item.checks)
        for item in outages
    ]


def outage_summary(
    outages: Sequence[Outage],
    samples: Sequence[Sample],
    merged_windows: Sequence[MaintenanceWindow] = (),
) -> dict[str, Any]:
    recovered = [outage for outage in outages if not outage.ongoing]
    downtime = sum(outage.duration_s for outage in outages)
    mttr = sum(outage.duration_s for outage in recovered) / len(recovered) if recovered else None

    mtbf = None
    if outages and samples:
        first, last = samples[0].at, samples[-1].at
        span = (last - first).total_seconds() - overlap_seconds(first, last, merged_windows)
        mtbf = max(span - downtime, 0.0) / len(outages)

    return {
        "count": len(outages),
        "recovered": len(recovered),
        "ongoing": len(outages) - len(recovered),
        "downtime_s": round(downtime, 1),
        "longest_s": round(max((outage.duration_s for outage in outages), default=0.0), 1),
        "mttr_s": _round(mttr, 1),
        "mtbf_s": _round(mtbf, 1),
    }


# --------------------------------------------------------------------- SLA


def _below_target(up: int, checks: int, target: float) -> bool:
    """Whether ``up / checks`` is under ``target`` percent, without float error.

    ``999 / 1000`` against a 99.9% target is exactly on it; a float comparison
    would call it a miss.
    """
    return Fraction(up * 100, checks) < Fraction(str(target))


def daily_breakdown(samples: Sequence[Sample]) -> list[dict[str, Any]]:
    """Checks, availability, and P95 latency for each local calendar day with checks."""
    by_day: dict[date, list[Sample]] = {}
    for sample in samples:
        by_day.setdefault(sample.at.date(), []).append(sample)
    days = []
    for day in sorted(by_day):
        group = by_day[day]
        up = sum(1 for sample in group if sample.reachable)
        days.append(
            {
                "date": day.isoformat(),
                "checks": len(group),
                "up": up,
                "availability_pct": _percent(up, len(group)),
                "latency_p95": latency_stats(
                    sample.latency for sample in group if sample.reachable
                )["p95"],
            }
        )
    return days


def _percent(up: int, checks: int) -> float | None:
    return round(up * 100 / checks, 4) if checks else None


def sla_status(
    target: SlaTarget,
    up: int,
    checks: int,
    latency_p95: float | None,
    days: Sequence[dict],
    daily_p95: dict[str, float | None] | None = None,
) -> dict[str, Any]:
    """Whether the window met ``target``, and the days that broke it.

    ``latency_p95`` and ``daily_p95`` are the *unrounded* percentiles: a P95 of
    10.004 ms is over a 10 ms limit even though it displays as 10.0. Without
    ``daily_p95`` the days' own (rounded) figures are used.
    """
    violations: list[dict[str, Any]] = []
    for day in days:
        day_p95 = day["latency_p95"] if daily_p95 is None else daily_p95.get(day["date"])
        if day["checks"] and _below_target(day["up"], day["checks"], target.availability):
            violations.append(
                {
                    "date": day["date"],
                    "kind": "availability",
                    "observed": day["availability_pct"],
                    "target": target.availability,
                }
            )
        limit = target.latency_p95_ms
        if limit is not None and day_p95 is not None and day_p95 > limit:
            violations.append(
                {
                    "date": day["date"],
                    "kind": "latency",
                    "observed": _round(day_p95),
                    "target": limit,
                }
            )
    return {
        "availability_target": target.availability,
        "latency_p95_ms": target.latency_p95_ms,
        "availability_met": None
        if not checks
        else not _below_target(up, checks, target.availability),
        "latency_met": None
        if target.latency_p95_ms is None or latency_p95 is None
        else latency_p95 <= target.latency_p95_ms,
        "violations": violations,
    }


# ----------------------------------------------------------------- the lot


def analyse(
    samples: Iterable[Sample],
    windows: Iterable[MaintenanceWindow] = (),
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
    sla: SlaTarget | None = None,
) -> dict[str, Any]:
    """Everything the host's health page shows, for checks within ``[starts_at, ends_at]``."""
    maintenance = merge_windows(windows)
    ordered = sorted(
        (
            sample
            for sample in samples
            if (starts_at is None or sample.at >= starts_at)
            and (ends_at is None or sample.at <= ends_at)
        ),
        key=lambda sample: (sample.at, sample.scan_id if sample.scan_id is not None else 0),
    )
    counted = [sample for sample in ordered if not in_maintenance(sample.at, maintenance)]
    up = sum(1 for sample in counted if sample.reachable)

    outages = find_outages(counted, maintenance)
    latency = latency_stats(sample.latency for sample in counted if sample.reachable)
    daily = daily_breakdown(counted)
    by_day: dict[str, list[Sample]] = {}
    for sample in counted:
        by_day.setdefault(sample.at.date().isoformat(), []).append(sample)
    daily_p95 = {day: percentile(reply_latencies(group), 0.95) for day, group in by_day.items()}

    return {
        "checks": len(counted),
        "up": up,
        "down": len(counted) - up,
        "excluded": len(ordered) - len(counted),
        "availability_pct": _percent(up, len(counted)),
        "latency": latency,
        "outages": outage_summary(outages, counted, maintenance),
        "outage_list": [outage.to_dict() for outage in reversed(outages)],
        "daily": daily,
        "sla": (
            sla_status(
                sla, up, len(counted), percentile(reply_latencies(counted), 0.95), daily, daily_p95
            )
            if sla
            else None
        ),
    }


def window_bounds(days: int, now: datetime) -> tuple[datetime, datetime]:
    """The last ``days`` days up to ``now``, to the second."""
    now = now.replace(microsecond=0)
    return now - timedelta(days=days), now
