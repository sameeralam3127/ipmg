"""Host health: availability, latency percentiles, outages, SLA, and maintenance.

Joins the stored checks, the host's SLA target, and the maintenance windows
that apply to it, and hands them to the pure functions in
:mod:`ipmg.core.availability`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ipmg.core.availability import (
    MaintenanceWindow,
    Sample,
    SlaTarget,
    TimeError,
    analyse,
    format_local,
    parse_local,
    window_bounds,
)
from ipmg.exceptions import HistoryError
from ipmg.infrastructure.database import Database

#: Longest window a report may cover.
MAX_DAYS = 365

#: Outages listed in full; the summary counts all of them.
MAX_LISTED_OUTAGES = 50

#: Longest reason a maintenance window may carry.
MAX_REASON = 200

#: What every figure rests on, repeated in the page and the report.
CAVEAT = (
    "Observed from scans, not a continuous probe: an outage between two scans is not "
    "seen, and durations have the resolution of the scan interval."
)


class AvailabilityService:
    def __init__(self, database: Database) -> None:
        self._db = database

    # --------------------------------------------------------------- health

    def health(
        self,
        ip: str,
        days: int = 30,
        source: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        """The host's health over the last ``days`` days, or ``None`` if never scanned."""
        if self._db.host_summary(ip) is None:
            return None
        days = max(1, min(days, MAX_DAYS))
        starts_at, ends_at = window_bounds(days, now or datetime.now())
        start_text, end_text = format_local(starts_at), format_local(ends_at)

        samples = [
            Sample(
                at=parsed,
                status=row["status"],
                latency=row["latency"],
                scan_id=row["scan_id"],
            )
            for row in self._db.host_samples(ip, start_text, end_text, source or None)
            if (parsed := _read_time(row["checked_at"])) is not None
        ]
        rows = self._db.list_maintenance(ip=ip, overlapping=(start_text, end_text))
        windows = [
            MaintenanceWindow(parse_local(row["starts_at"]), parse_local(row["ends_at"]))
            for row in rows
        ]
        stored = self._db.get_sla(ip)
        target = (
            SlaTarget(stored["availability_target"], stored["latency_p95_ms"]) if stored else None
        )

        report = analyse(samples, windows, starts_at, ends_at, target)
        listed = report["outage_list"]
        report["outage_list"] = listed[:MAX_LISTED_OUTAGES]
        report["outages_truncated"] = len(listed) > MAX_LISTED_OUTAGES
        return {
            "ip": ip,
            "window": {"starts_at": start_text, "ends_at": end_text, "days": days},
            "source": source or None,
            "sources": self._db.host_sources(ip, start_text, end_text),
            "maintenance": rows,
            "note": CAVEAT,
            **report,
        }

    # ---------------------------------------------------------- SLA targets

    def set_sla(
        self, ip: str, availability_target: float, latency_p95_ms: float | None = None
    ) -> dict[str, Any]:
        if not 0 < availability_target <= 100:
            raise HistoryError("The availability target must be above 0 and at most 100.")
        if latency_p95_ms is not None and not latency_p95_ms > 0:
            raise HistoryError("The latency limit must be above 0 ms.")
        return self._db.set_sla(ip, availability_target, latency_p95_ms)

    # ---------------------------------------------------------- maintenance

    def add_maintenance(
        self, ip: str | None, starts_at: str, ends_at: str, reason: str = ""
    ) -> dict[str, Any]:
        """Validate and store a window; times are local, ``YYYY-MM-DD HH:MM[:SS]``."""
        try:
            start, end = parse_local(starts_at), parse_local(ends_at)
        except TimeError as exc:
            raise HistoryError(str(exc)) from exc
        if end <= start:
            raise HistoryError("A maintenance window must end after it starts.")
        reason = reason.strip()
        if len(reason) > MAX_REASON:
            raise HistoryError(f"The reason is limited to {MAX_REASON} characters.")
        return self._db.add_maintenance(ip, format_local(start), format_local(end), reason)


def _read_time(text: str) -> datetime | None:
    try:
        return parse_local(text)
    except TimeError:
        return None
