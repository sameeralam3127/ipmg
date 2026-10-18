"""SQLite persistence for scan history, shared by the CLI and the dashboard.

One row per scan in ``scans`` plus one row per probed host in ``results``.
Every public method is thread-safe: a lock guards a short-lived connection so
background scan threads and the web request loop can write concurrently.

The CLI and IPMG Web open the same file from separate processes, so the
database runs in WAL mode, where readers never block the writer, and every
connection waits up to :data:`BUSY_TIMEOUT_S` for a lock instead of failing.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ipmg.core.diff import HostSnapshot, HttpSnapshot, ScanRef, ip_sort_key
from ipmg.core.engine import HostResult
from ipmg.core.portscan import encode_ports

DEFAULT_DB_PATH = Path.home() / ".ipmg" / "dashboard.db"

#: Seconds a connection waits for another process's lock before giving up.
#: SQLite's default of 5 made a CLI scan that finished during a long web read
#: lose its history with "database is locked".
BUSY_TIMEOUT_S = 30.0

#: Scan states whose results are complete enough to be used as a baseline.
COMPARABLE_STATUSES = ("complete", "cancelled")

#: A scan whose process stopped before it finished: IPMG Web was stopped or
#: crashed mid-scan, or a scan row was otherwise left "running".
INTERRUPTED_STATUS = "interrupted"

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
    open_ports TEXT NOT NULL DEFAULT '',
    checked_at TEXT NOT NULL,
    method TEXT NOT NULL DEFAULT '',
    mac TEXT NOT NULL DEFAULT '',
    vendor TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_results_scan ON results(scan_id);
CREATE INDEX IF NOT EXISTS idx_results_ip ON results(ip);

CREATE TABLE IF NOT EXISTS http_checks (
    scan_id INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    ok INTEGER NOT NULL,
    status_code INTEGER,
    response_ms REAL,
    final_url TEXT NOT NULL DEFAULT '',
    failure TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    cert_expires TEXT NOT NULL DEFAULT '',
    checked_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_http_checks_scan ON http_checks(scan_id);

CREATE TABLE IF NOT EXISTS schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    targets TEXT NOT NULL,
    config TEXT NOT NULL DEFAULT '{}',
    interval_minutes INTEGER,
    cron TEXT,
    paused INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    next_run_at TEXT,
    last_run_at TEXT,
    last_scan_id INTEGER,
    last_skipped_at TEXT,
    last_skip_reason TEXT
);
"""

_SCHEDULE_SQL = (
    "SELECT sc.*, s.status AS last_status FROM schedules sc "
    "LEFT JOIN scans s ON s.id = sc.last_scan_id"
)

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
            # Persistent, so this only does work the first time. Filesystems
            # without shared memory (some network shares) keep the old
            # journal, which is slower but still correct.
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(_SCHEMA)
            self._migrate(conn)

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        """Add columns introduced after a database was first created."""
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(results)")}
        if "open_ports" not in columns:
            conn.execute("ALTER TABLE results ADD COLUMN open_ports TEXT NOT NULL DEFAULT ''")
        # One fixed statement per column added after release, in release order.
        for column, statement in (
            ("method", "ALTER TABLE results ADD COLUMN method TEXT NOT NULL DEFAULT ''"),
            ("mac", "ALTER TABLE results ADD COLUMN mac TEXT NOT NULL DEFAULT ''"),
            ("vendor", "ALTER TABLE results ADD COLUMN vendor TEXT NOT NULL DEFAULT ''"),
        ):
            if column not in columns:
                conn.execute(statement)

    @property
    def path(self) -> str:
        return self._path

    @contextmanager
    def _session(self):
        with self._lock:
            conn = sqlite3.connect(self._path, timeout=BUSY_TIMEOUT_S)
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
        with self._session() as conn:
            return self._insert_results(conn, scan_id, results)

    @staticmethod
    def _insert_results(
        conn: sqlite3.Connection, scan_id: int, results: Iterable[HostResult]
    ) -> int:
        checked_at = _now()
        rows = [
            (
                scan_id,
                result.ip,
                result.status,
                result.latency,
                result.hostname,
                encode_ports(result.open_ports),
                checked_at,
                result.method,
                result.mac,
                result.vendor,
            )
            for result in results
        ]
        if not rows:
            return 0
        conn.executemany(
            "INSERT INTO results "
            "(scan_id, ip, status, latency, hostname, open_ports, checked_at, method, mac, vendor) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
        http_checks: Sequence[Any] = (),
    ) -> int:
        """Persist an already-finished scan (used by the CLI) in one go.

        One transaction: a CLI killed halfway leaves no scan behind, rather
        than one stuck at "running" that nothing would ever finish.
        """
        now = _now()
        with self._session() as conn:
            cursor = conn.execute(
                "INSERT INTO scans "
                "(started_at, finished_at, duration_s, source, total, status, config) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (now, now, round(duration_s, 3), source, len(results), status, json.dumps(config)),
            )
            scan_id = int(cursor.lastrowid)
            self._insert_results(conn, scan_id, results)
            conn.executemany(
                "INSERT INTO http_checks (scan_id, url, ok, status_code, response_ms, "
                "final_url, failure, error, cert_expires, checked_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        scan_id,
                        check.url,
                        int(check.ok),
                        check.status_code,
                        check.response_ms,
                        check.final_url,
                        check.failure,
                        check.error,
                        check.cert_expires,
                        now,
                    )
                    for check in http_checks
                ],
            )
        return scan_id

    def get_http_checks(self, scan_id: int) -> List[Dict[str, Any]]:
        """A scan's ``--http-check`` results, in the order they were checked."""
        with self._session() as conn:
            rows = conn.execute(
                "SELECT url, ok, status_code, response_ms, final_url, failure, error, "
                "cert_expires, checked_at FROM http_checks WHERE scan_id = ? ORDER BY rowid",
                (scan_id,),
            ).fetchall()
        return [{**dict(row), "ok": bool(row["ok"])} for row in rows]

    def http_snapshot(self, scan_id: int) -> List[HttpSnapshot]:
        return [
            HttpSnapshot(
                url=row["url"],
                ok=row["ok"],
                status_code=row["status_code"],
                failure=row["failure"],
            )
            for row in self.get_http_checks(scan_id)
        ]

    def interrupt_scans(self, error: str, scan_ids: Optional[Sequence[int]] = None) -> int:
        """Mark ``running`` scans as interrupted; all of them unless ``scan_ids`` is given.

        Returns how many were marked. Only rows still ``running`` change, so a
        scan that finished in the meantime keeps its real outcome.
        """
        update = "UPDATE scans SET status = ?, finished_at = ?, error = ? WHERE status = 'running'"
        params = (INTERRUPTED_STATUS, _now(), error)
        with self._session() as conn:
            if scan_ids is None:
                return conn.execute(update, params).rowcount
            return sum(
                conn.execute(update + " AND id = ?", (*params, scan_id)).rowcount
                for scan_id in scan_ids
            )

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

    def scan_rows(self, source: Optional[str] = None) -> List[Dict[str, Any]]:
        """Every stored scan's own row (no aggregates), newest first."""
        query = "SELECT id, started_at, source, status, completed FROM scans"
        params: List[Any] = []
        if source:
            query += " WHERE source = ?"
            params.append(source)
        query += " ORDER BY id DESC"
        with self._session() as conn:
            return [dict(row) for row in conn.execute(query, params).fetchall()]

    def delete_scans(self, scan_ids: Iterable[int]) -> int:
        """Delete many scans, and their results, in one transaction."""
        ids = [(int(scan_id),) for scan_id in scan_ids]
        if not ids:
            return 0
        with self._session() as conn:
            # Running scans are skipped here too, not only by the caller's plan.
            return conn.executemany(
                "DELETE FROM scans WHERE id = ? AND status != 'running'", ids
            ).rowcount

    def vacuum(self) -> None:
        """Give the space freed by deleted scans back to the filesystem."""
        with self._session() as conn:
            conn.execute("VACUUM")

    def size_bytes(self) -> int:
        """The database file plus its write-ahead log."""
        return sum(
            Path(self._path + suffix).stat().st_size
            for suffix in ("", "-wal")
            if Path(self._path + suffix).exists()
        )

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
                "SELECT ip, status, latency, hostname, mac FROM results "
                "WHERE scan_id = ? ORDER BY rowid",
                (scan_id,),
            ).fetchall()
        return [
            HostSnapshot(
                ip=row["ip"],
                status=row["status"],
                latency=row["latency"],
                hostname=row["hostname"] or "",
                mac=row["mac"] or "",
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
        query = (
            "SELECT ip, status, latency, hostname, open_ports, checked_at, method, mac, vendor "
            "FROM results WHERE scan_id = ?"
        )
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

    def latest_completed_scans(self, limit: int) -> Tuple[List[Dict[str, Any]], int]:
        """The newest completed scan of each source, most recent source first.

        Returns at most ``limit`` scans, each with a ``completed_count`` of the
        completed scans its source has, plus how many sources exist in all, so
        a caller can say how many it left out.
        """
        with self._session() as conn:
            rows = conn.execute(
                "SELECT s.*, latest.completed_count FROM scans s JOIN ("
                "  SELECT source, MAX(id) AS id, COUNT(*) AS completed_count "
                "  FROM scans WHERE status = 'complete' GROUP BY source"
                ") latest ON s.id = latest.id ORDER BY s.id DESC"
            ).fetchall()
        return [self._scan_dict(row) for row in rows[:limit]], len(rows)

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
            "  (SELECT r4.mac FROM results r4 "
            "   WHERE r4.ip = r.ip AND r4.mac != '' "
            "   ORDER BY r4.rowid DESC LIMIT 1) AS mac, "
            "  (SELECT r5.vendor FROM results r5 "
            "   WHERE r5.ip = r.ip AND r5.mac != '' "
            "   ORDER BY r5.rowid DESC LIMIT 1) AS vendor, "
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

    # ---------------------------------------------------------- schedules

    def create_schedule(
        self,
        name: str,
        targets: str,
        config: Dict[str, Any],
        interval_minutes: Optional[int],
        cron: Optional[str],
        next_run_at: Optional[str],
        paused: bool = False,
    ) -> int:
        with self._session() as conn:
            cursor = conn.execute(
                "INSERT INTO schedules (name, targets, config, interval_minutes, cron, paused, "
                "created_at, next_run_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    name,
                    targets,
                    json.dumps(config),
                    interval_minutes,
                    cron,
                    int(paused),
                    _now(),
                    next_run_at,
                ),
            )
            return int(cursor.lastrowid)

    def list_schedules(self) -> List[Dict[str, Any]]:
        with self._session() as conn:
            rows = conn.execute(_SCHEDULE_SQL + " ORDER BY sc.id").fetchall()
        return [self._schedule_dict(row) for row in rows]

    def get_schedule(self, schedule_id: int) -> Optional[Dict[str, Any]]:
        with self._session() as conn:
            row = conn.execute(_SCHEDULE_SQL + " WHERE sc.id = ?", (schedule_id,)).fetchone()
        return self._schedule_dict(row) if row is not None else None

    def due_schedules(self, now: str) -> List[Dict[str, Any]]:
        """Schedules that are not paused and whose next run is at or before ``now``."""
        with self._session() as conn:
            rows = conn.execute(
                _SCHEDULE_SQL + " WHERE sc.paused = 0 AND sc.next_run_at IS NOT NULL "
                "AND sc.next_run_at <= ? ORDER BY sc.next_run_at, sc.id",
                (now,),
            ).fetchall()
        return [self._schedule_dict(row) for row in rows]

    def set_schedule_paused(
        self, schedule_id: int, paused: bool, next_run_at: Optional[str]
    ) -> bool:
        with self._session() as conn:
            cursor = conn.execute(
                "UPDATE schedules SET paused = ?, next_run_at = ? WHERE id = ?",
                (int(paused), next_run_at, schedule_id),
            )
            return cursor.rowcount > 0

    def record_schedule_run(
        self, schedule_id: int, ran_at: str, scan_id: int, next_run_at: Optional[str]
    ) -> None:
        with self._session() as conn:
            conn.execute(
                "UPDATE schedules SET last_run_at = ?, last_scan_id = ?, next_run_at = ? "
                "WHERE id = ?",
                (ran_at, scan_id, next_run_at, schedule_id),
            )

    def record_schedule_skip(
        self, schedule_id: int, skipped_at: str, reason: str, next_run_at: Optional[str]
    ) -> None:
        with self._session() as conn:
            conn.execute(
                "UPDATE schedules SET last_skipped_at = ?, last_skip_reason = ?, "
                "next_run_at = ? WHERE id = ?",
                (skipped_at, reason, next_run_at, schedule_id),
            )

    def delete_schedule(self, schedule_id: int) -> bool:
        """Delete a schedule. The scans it ran stay in the history."""
        with self._session() as conn:
            cursor = conn.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
            return cursor.rowcount > 0

    # ------------------------------------------------------------ helpers

    @staticmethod
    def _schedule_dict(row: sqlite3.Row) -> Dict[str, Any]:
        schedule = dict(row)
        schedule["config"] = json.loads(schedule.get("config") or "{}")
        schedule["paused"] = bool(schedule["paused"])
        return schedule

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
