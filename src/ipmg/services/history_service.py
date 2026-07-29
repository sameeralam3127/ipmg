"""Scan history: recording scans and comparing them.

Bridges the persistence layer (:mod:`ipmg.infrastructure.database`) and the
pure comparison engine (:mod:`ipmg.core.diff`) so the CLI and the web API can
share one implementation of "what changed since the last scan?".
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ipmg.core.diff import DiffOptions, ScanDiff, ScanRef, compare_snapshots
from ipmg.core.engine import HostResult, ScanConfig
from ipmg.exceptions import HistoryError
from ipmg.infrastructure.database import DEFAULT_DB_PATH, Database


class HistoryService:
    """High-level operations over the stored scan history."""

    def __init__(self, database: Database) -> None:
        self._db = database

    @classmethod
    def open(cls, db_path: Optional[str] = None) -> "HistoryService":
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
    ) -> int:
        """Store a finished scan and return its id."""
        return self._db.record_scan(
            source=source,
            results=results,
            config=asdict(config),
            duration_s=duration_s,
        )

    # ------------------------------------------------------------ listing

    def list_scans(self, limit: int = 20, source: Optional[str] = None) -> List[Dict[str, Any]]:
        return self._db.list_scans(limit=max(1, limit), source=source)

    # --------------------------------------------------------- comparison

    def compare(
        self,
        baseline_id: int,
        target_id: int,
        options: Optional[DiffOptions] = None,
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
        )

    def compare_with_previous(
        self,
        scan_id: int,
        source: Optional[str] = None,
        options: Optional[DiffOptions] = None,
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
        source: Optional[str] = None,
        options: Optional[DiffOptions] = None,
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

    # ------------------------------------------------------------ helpers

    def _require_ref(self, scan_id: int) -> ScanRef:
        ref = self._db.scan_ref(scan_id)
        if ref is None:
            raise HistoryError(f"Scan #{scan_id} was not found in the history database.")
        return ref
