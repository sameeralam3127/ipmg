"""Scan history: recording scans and comparing them.

Bridges the persistence layer (:mod:`ipmg.infrastructure.database`) and the
pure comparison engine (:mod:`ipmg.core.diff`) so the CLI and the web API can
share one implementation of "what changed since the last scan?".
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path
from typing import Any

from ipmg.core.diff import ChangeType, DiffOptions, ScanDiff, ScanRef, compare_snapshots
from ipmg.core.engine import HostResult, ScanConfig
from ipmg.exceptions import HistoryError
from ipmg.infrastructure.database import DEFAULT_DB_PATH, Database
from ipmg.infrastructure.retention import PrunePlan, plan_prune

#: The most scans of one host looked at to pair them up. Cheap, since only ids are read.
HOST_SCAN_WINDOW = 2000


class HistoryService:
    """High-level operations over the stored scan history."""

    def __init__(self, database: Database) -> None:
        self._db = database

    @classmethod
    def open(cls, db_path: str | None = None) -> HistoryService:
        try:
            return cls(Database(Path(db_path) if db_path else DEFAULT_DB_PATH))
        except OSError as exc:
            raise HistoryError(f"Could not open scan history database: {exc}") from exc

    @property
    def database(self) -> Database:
        return self._db

    # ----------------------------------------------------------- recording

    def record_scan(
        self,
        source: str,
        results: Sequence[HostResult],
        config: ScanConfig,
        duration_s: float,
        http_checks: Sequence[Any] = (),
        snmp_devices: Sequence[Any] = (),
    ) -> int:
        """Store a finished scan, its HTTP checks, and its SNMP polls, and return its id."""
        return self._db.record_scan(
            source=source,
            results=results,
            config=asdict(config),
            duration_s=duration_s,
            http_checks=http_checks,
            snmp_devices=snmp_devices,
        )

    # ------------------------------------------------------------ listing

    def list_scans(self, limit: int = 20, source: str | None = None) -> list[dict[str, Any]]:
        return self._db.list_scans(limit=max(1, limit), source=source)

    # ----------------------------------------------------------- retention

    def plan_prune(
        self,
        keep: int | None = None,
        older_than: timedelta | None = None,
        source: str | None = None,
    ) -> PrunePlan:
        """The scans a retention policy would delete, without deleting anything."""
        return plan_prune(self._db.scan_rows(source), keep=keep, older_than=older_than)

    def prune(self, plan: PrunePlan) -> int:
        """Delete the scans in ``plan``; returns how many were deleted."""
        return self._db.delete_scans(plan.scan_ids)

    # --------------------------------------------------------- comparison

    def compare(
        self,
        baseline_id: int,
        target_id: int,
        options: DiffOptions | None = None,
    ) -> ScanDiff:
        """Compare two stored scans by id."""
        baseline_ref = self._require_ref(baseline_id)
        target_ref = self._require_ref(target_id)

        return compare_snapshots(
            self._db.snapshot(baseline_id),
            self._db.snapshot(target_id),
            options=options,
            baseline_ref=baseline_ref,
            current_ref=target_ref,
            baseline_http=self._db.http_snapshot(baseline_id),
            current_http=self._db.http_snapshot(target_id),
            baseline_snmp=self._db.snmp_snapshot(baseline_id),
            current_snmp=self._db.snmp_snapshot(target_id),
        )

    def compare_with_previous(
        self,
        scan_id: int,
        source: str | None = None,
        options: DiffOptions | None = None,
    ) -> ScanDiff:
        """Compare a scan against the newest comparable scan before it."""
        self._require_ref(scan_id)
        baseline_id = self._db.previous_scan_id(scan_id, source=source)
        if baseline_id is None:
            raise HistoryError(
                f"No earlier scan is stored to compare scan #{scan_id} against. "
                "Run at least two scans first."
            )
        return self.compare(baseline_id, scan_id, options=options)

    def compare_latest(
        self,
        source: str | None = None,
        options: DiffOptions | None = None,
    ) -> ScanDiff:
        """Compare the two most recent stored scans."""
        recent = self._db.latest_scan_ids(limit=2, source=source)
        if len(recent) < 2:
            raise HistoryError(
                "At least two stored scans are required to compare. "
                "Run 'ipmg' twice, then try again."
            )
        target_id, baseline_id = recent[0], recent[1]
        return self.compare(baseline_id, target_id, options=options)

    def host_changes(
        self, ip: str, limit: int = 25, options: DiffOptions | None = None
    ) -> list[dict[str, Any]]:
        """What changed for one host, newest first.

        Each scan that recorded ``ip`` is compared with the scan of the same
        source just before it, and a scan just after one that recorded it is
        compared with that one. Where the host is in both, every change to it
        counts. Where it is in only one, only an IP move does (the same
        hostname or MAC now at a different address), so a host that simply was
        not in a scan is not read as vanishing. ``limit`` bounds how many scan
        pairs are compared, each a whole-scan comparison.
        """
        seen = self._db.host_comparable_scans(ip, HOST_SCAN_WINDOW)
        if not seen:
            return []
        recorded = {scan["id"] for scan in seen}
        # Start one scan early per source, so the first appearance has a baseline.
        starts = []
        for source in {scan["source"] for scan in seen}:
            first = min(scan["id"] for scan in seen if scan["source"] == source)
            starts.append(self._db.previous_scan_id(first, source=source) or first)
        sequence = self._db.comparable_scan_sequence(
            sorted({scan["source"] for scan in seen}), min(starts)
        )
        previous_by_source: dict[str, dict[str, Any]] = {}
        pairs: list[tuple[dict[str, Any], dict[str, Any], bool]] = []
        for scan in sequence:
            earlier = previous_by_source.get(scan["source"])
            if earlier is not None:
                both = earlier["id"] in recorded and scan["id"] in recorded
                if both or earlier["id"] in recorded or scan["id"] in recorded:
                    pairs.append((earlier, scan, both))
            previous_by_source[scan["source"]] = scan

        newest_first = sorted(pairs, key=lambda pair: -pair[1]["id"])
        full = [pair for pair in newest_first if pair[2]][:limit]
        # Boundary pairs only matter for IP moves; keep those within the same
        # stretch of history as the full comparisons, and no more than ``limit``.
        cutoff = full[-1][1]["id"] if len(full) == limit and full else 0
        edges = [pair for pair in newest_first if not pair[2] and pair[1]["id"] >= cutoff][:limit]
        chosen = sorted(full + edges, key=lambda pair: -pair[1]["id"])

        rows: list[dict[str, Any]] = []
        for baseline, current, both in chosen:
            diff = self.compare(baseline["id"], current["id"], options=options)
            rows.extend(
                {
                    **change.to_dict(),
                    "scan_id": current["id"],
                    "baseline_id": baseline["id"],
                    "started_at": current["started_at"],
                    "source": current["source"],
                }
                for change in diff.changes
                if _concerns_host(change, ip, both)
            )
        return rows

    # ------------------------------------------------------------ helpers

    def _require_ref(self, scan_id: int) -> ScanRef:
        ref = self._db.scan_ref(scan_id)
        if ref is None:
            raise HistoryError(f"Scan #{scan_id} was not found in the history database.")
        return ref


def _concerns_host(change: Any, ip: str, in_both: bool) -> bool:
    """Whether a change belongs on ``ip``'s page, given whether both scans recorded it."""
    if in_both and change.ip == ip:
        return True
    if change.type is ChangeType.IP_CHANGED:
        # Reported on the address gained; ``previous`` names the ones given up.
        return change.ip == ip or ip in (change.previous or "").split(", ")
    return False
