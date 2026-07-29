"""SQLite persistence for scan history, shared by the CLI and the dashboard.

One row per scan in ``scans`` plus one row per probed host in ``results``.
Every public method is thread-safe: a lock guards a short-lived connection so
background scan threads and the web request loop can write concurrently.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from ipmg.core.diff import HostSnapshot, ScanRef, ip_sort_key
from ipmg.core.engine import HostResult

DEFAULT_DB_PATH = Path.home() / ".ipmg" / "dashboard.db"

#: Scan states whose results are complete enough to be used as a baseline.
COMPARABLE_STATUSES = ("complete", "cancelled")

# Written out rather than interpolated so no SQL is ever built from variables.
# The two ``?`` placeholders bind COMPARABLE_STATUSES, in order.
_PREVIOUS_SCAN_SQL = "SELECT id FROM scans WHERE id < ? AND status IN (?, ?)"
_LATEST_SCANS_SQL = "SELECT id FROM scans WHERE status IN (?, ?)"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    duration_s REAL,
    source TEXT NOT NULL,
    total INTEGER NOT NULL DEFAULT 0,
    completed INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'running',
    config TEXT NOT NULL DEFAULT '{}',
    error TEXT
);

CREATE TABLE IF NOT EXISTS results (
    scan_id INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    ip TEXT NOT NULL,
    status TEXT NOT NULL,
    latency REAL,
    hostname TEXT NOT NULL DEFAULT '',
    checked_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_results_scan ON results(scan_id);
CREATE INDEX IF NOT EXISTS idx_results_ip ON results(ip);
"""

#: ``ESCAPE`` character used to neutralise user-supplied LIKE wildcards.
_LIKE_ESCAPE = "\\"


def _now() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")


def _escape_like(term: str) -> str:
    """Escape ``%``/``_`` so a search term matches literally."""
    for char in (_LIKE_ESCAPE, "%", "_"):
        term = term.replace(char, _LIKE_ESCAPE + char)
    return term


class Database:
    def __init__(self, path: Path | str = DEFAULT_DB_PATH) -> None:
        self._path = str(path)
        self._lock = threading.Lock()
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        with self._session() as conn:
            conn.executescript(_SCHEMA)

    @property
    def path(self) -> str:
        return self._path

    @contextmanager
    def _session(self):
        with self._lock:
            conn = sqlite3.connect(self._path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            try:
                with conn:
                    yield conn
            finally:
                conn.close()

    # ------------------------------------------------------------- scans

    def create_scan(self, source: str, total: int, config: Dict[str, Any]) -> int:
        with self._session() as conn:
            cursor = conn.execute(
                "INSERT INTO scans (started_at, source, total, config) VALUES (?, ?, ?, ?)",
                (_now(), source, total, json.dumps(config)),
            )
            return int(cursor.lastrowid)

    def add_result(self, scan_id: int, result: HostResult) -> None:
        self.add_results(scan_id, (result,))

    def add_results(self, scan_id: int, results: Iterable[HostResult]) -> int:
        """Insert many results in one transaction; returns the number stored."""
        checked_at = _now()
        rows = [
            (scan_id, result.ip, result.status, result.latency, result.hostname, checked_at)
            for result in results
        ]
        if not rows:
            return 0

        with self._session() as conn:
            conn.executemany(
                "INSERT INTO results (scan_id, ip, status, latency, hostname, checked_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.execute(
                "UPDATE scans SET completed = completed + ? WHERE id = ?",
                (len(rows), scan_id),
            )
        return len(rows)

    def finish_scan(self, scan_id: int, status: str, duration_s: float) -> None:
        with self._session() as conn:
            conn.execute(
                "UPDATE scans SET status = ?, finished_at = ?, duration_s = ? WHERE id = ?",
                (status, _now(), round(duration_s, 3), scan_id),
            )

    def fail_scan(self, scan_id: int, error: str) -> None:
        with self._session() as conn:
            conn.execute(
                "UPDATE scans SET status = 'failed', finished_at = ?, error = ? WHERE id = ?",
                (_now(), error, scan_id),
            )

    def record_scan(
        self,
        source: str,
        results: Sequence[HostResult],
        config: Dict[str, Any],
        duration_s: float,
        status: str = "complete",
    ) -> int:
        """Persist an already-finished scan (used by the CLI) in one go."""
        scan_id = self.create_scan(source, len(results), config)
        self.add_results(scan_id, results)
        self.finish_scan(scan_id, status, duration_s)
        return scan_id

    def get_scan(self, scan_id: int) -> Optional[Dict[str, Any]]:
        with self._session() as conn:
            row = conn.execute("SELECT * FROM scans WHERE id = ?", (scan_id,)).fetchone()
            if row is None:
                return None
            scan = self._scan_dict(row)
            scan["status_counts"] = self._status_counts(conn, scan_id)
            scan["avg_latency"] = self._avg_latency(conn, scan_id)
            return scan

    def list_scans(self, limit: int = 50, source: Optional[str] = None) -> List[Dict[str, Any]]:
        query = "SELECT * FROM scans"
        params: List[Any] = []
        if source:
            query += " WHERE source = ?"
            params.append(source)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        with self._session() as conn:
            rows = conn.execute(query, params).fetchall()
            scans = []
            for row in rows:
                scan = self._scan_dict(row)
                scan["status_counts"] = self._status_counts(conn, scan["id"])
                scan["avg_latency"] = self._avg_latency(conn, scan["id"])
                scans.append(scan)
            return scans

    def delete_scan(self, scan_id: int) -> bool:
        with self._session() as conn:
            cursor = conn.execute("DELETE FROM scans WHERE id = ?", (scan_id,))
            return cursor.rowcount > 0

    # ----------------------------------------------------------- history

    def previous_scan_id(self, scan_id: int, source: Optional[str] = None) -> Optional[int]:
        """Newest comparable scan recorded before ``scan_id``."""
        query = _PREVIOUS_SCAN_SQL
        params: List[Any] = [scan_id, *COMPARABLE_STATUSES]
        if source:
            query += " AND source = ?"
            params.append(source)
        query += " ORDER BY id DESC LIMIT 1"

        with self._session() as conn:
            row = conn.execute(query, params).fetchone()
        return int(row["id"]) if row else None

    def latest_scan_ids(self, limit: int = 2, source: Optional[str] = None) -> List[int]:
        """IDs of the most recent comparable scans, newest first."""
        query = _LATEST_SCANS_SQL
        params: List[Any] = list(COMPARABLE_STATUSES)
        if source:
            query += " AND source = ?"
            params.append(source)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(max(limit, 0))

        with self._session() as conn:
            return [int(row["id"]) for row in conn.execute(query, params).fetchall()]

    def snapshot(self, scan_id: int) -> List[HostSnapshot]:
        """Every host recorded by a scan, as comparison-ready snapshots."""
        with self._session() as conn:
            rows = conn.execute(
                "SELECT ip, status, latency, hostname FROM results "
                "WHERE scan_id = ? ORDER BY rowid",
                (scan_id,),
            ).fetchall()
        return [
            HostSnapshot(
                ip=row["ip"],
                status=row["status"],
                latency=row["latency"],
                hostname=row["hostname"] or "",
            )
            for row in rows
        ]

    def scan_ref(self, scan_id: int) -> Optional[ScanRef]:
        """Identifying metadata for a scan, or ``None`` when it does not exist."""
        with self._session() as conn:
            row = conn.execute(
                "SELECT id, started_at, source FROM scans WHERE id = ?", (scan_id,)
            ).fetchone()
        if row is None:
            return None
        return ScanRef(
            id=int(row["id"]),
            label=f"Scan #{row['id']}",
            started_at=row["started_at"],
            source=row["source"],
        )

    # ----------------------------------------------------------- results

    def get_results(
        self,
        scan_id: int,
        status: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        query = "SELECT ip, status, latency, hostname, checked_at FROM results WHERE scan_id = ?"
        params: List[Any] = [scan_id]
        if status:
            query += " AND status = ?"
            params.append(status)
        if search:
            query += (
                f" AND (ip LIKE ? ESCAPE '{_LIKE_ESCAPE}' "
                f"OR hostname LIKE ? ESCAPE '{_LIKE_ESCAPE}')"
            )
            like = f"%{_escape_like(search)}%"
            params.extend([like, like])
        query += " ORDER BY rowid"

        with self._session() as conn:
            return [dict(row) for row in conn.execute(query, params).fetchall()]

    # ------------------------------------------------------- aggregates

    def overview(self) -> Dict[str, Any]:
        with self._session() as conn:
            scan_count = conn.execute("SELECT COUNT(*) FROM scans").fetchone()[0]
            host_count = conn.execute("SELECT COUNT(DISTINCT ip) FROM results").fetchone()[0]

            latest_row = conn.execute(
                "SELECT * FROM scans WHERE status != 'running' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            latest = None
            if latest_row is not None:
                latest = self._scan_dict(latest_row)
                latest["status_counts"] = self._status_counts(conn, latest["id"])
                latest["avg_latency"] = self._avg_latency(conn, latest["id"])

            running_rows = conn.execute(
                "SELECT * FROM scans WHERE status = 'running' ORDER BY id DESC"
            ).fetchall()

            trend_rows = conn.execute(
                "SELECT s.id, s.started_at, s.total, "
                "  (SELECT COUNT(*) FROM results r "
                "   WHERE r.scan_id = s.id AND r.status = 'Active') AS active, "
                "  (SELECT AVG(r.latency) FROM results r "
                "   WHERE r.scan_id = s.id AND r.status = 'Active') AS avg_latency "
                "FROM scans s WHERE s.status = 'complete' "
                "ORDER BY s.id DESC LIMIT 15"
            ).fetchall()

            return {
                "scan_count": scan_count,
                "host_count": host_count,
                "latest_scan": latest,
                "running_scans": [self._scan_dict(row) for row in running_rows],
                "trend": [dict(row) for row in reversed(trend_rows)],
            }

    def inventory(self) -> List[Dict[str, Any]]:
        query = (
            "SELECT r.ip, "
            "  (SELECT r2.hostname FROM results r2 "
            "   WHERE r2.ip = r.ip AND r2.hostname != '' "
            "   ORDER BY r2.rowid DESC LIMIT 1) AS hostname, "
            "  (SELECT r3.status FROM results r3 "
            "   WHERE r3.ip = r.ip ORDER BY r3.rowid DESC LIMIT 1) AS status, "
            "  AVG(CASE WHEN r.status = 'Active' THEN r.latency END) AS avg_latency, "
            "  MAX(CASE WHEN r.status = 'Active' THEN r.checked_at END) AS last_seen, "
            "  MAX(r.checked_at) AS last_checked, "
            "  MAX(r.scan_id) AS last_scan_id, "
            "  COUNT(DISTINCT r.scan_id) AS scan_count "
            "FROM results r GROUP BY r.ip"
        )
        with self._session() as conn:
            rows = [dict(row) for row in conn.execute(query).fetchall()]

        rows.sort(key=lambda row: ip_sort_key(row["ip"]))
        return rows

    # ------------------------------------------------------------ helpers

    @staticmethod
    def _scan_dict(row: sqlite3.Row) -> Dict[str, Any]:
        scan = dict(row)
        scan["config"] = json.loads(scan.get("config") or "{}")
        return scan

    @staticmethod
    def _status_counts(conn: sqlite3.Connection, scan_id: int) -> Dict[str, int]:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS count FROM results WHERE scan_id = ? GROUP BY status",
            (scan_id,),
        ).fetchall()
        return {row["status"]: row["count"] for row in rows}

    @staticmethod
    def _avg_latency(conn: sqlite3.Connection, scan_id: int) -> Optional[float]:
        value = conn.execute(
            "SELECT AVG(latency) FROM results WHERE scan_id = ? AND status = 'Active'",
            (scan_id,),
        ).fetchone()[0]
        return round(value, 2) if value is not None else None
