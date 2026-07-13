"""SQLite persistence for dashboard scan history. Thread-safe via a lock."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ipmg.core.engine import HostResult

DEFAULT_DB_PATH = Path.home() / ".ipmg" / "dashboard.db"

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


def _now() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")


class Database:
    def __init__(self, path: Path | str = DEFAULT_DB_PATH) -> None:
        self._path = str(path)
        self._lock = threading.Lock()
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        with self._session() as conn:
            conn.executescript(_SCHEMA)

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
        with self._session() as conn:
            conn.execute(
                "INSERT INTO results (scan_id, ip, status, latency, hostname, checked_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (scan_id, result.ip, result.status, result.latency, result.hostname, _now()),
            )
            conn.execute(
                "UPDATE scans SET completed = completed + 1 WHERE id = ?",
                (scan_id,),
            )

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

    def get_scan(self, scan_id: int) -> Optional[Dict[str, Any]]:
        with self._session() as conn:
            row = conn.execute("SELECT * FROM scans WHERE id = ?", (scan_id,)).fetchone()
            if row is None:
                return None
            scan = self._scan_dict(row)
            scan["status_counts"] = self._status_counts(conn, scan_id)
            scan["avg_latency"] = self._avg_latency(conn, scan_id)
            return scan

    def list_scans(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._session() as conn:
            rows = conn.execute("SELECT * FROM scans ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
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

    # ----------------------------------------------------------- results

    def get_results(
        self,
        scan_id: int,
        status: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        query = "SELECT ip, status, latency, hostname, checked_at " "FROM results WHERE scan_id = ?"
        params: List[Any] = [scan_id]
        if status:
            query += " AND status = ?"
            params.append(status)
        if search:
            query += " AND (ip LIKE ? OR hostname LIKE ?)"
            like = f"%{search}%"
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

        def sort_key(row: Dict[str, Any]):
            import ipaddress

            try:
                return (0, int(ipaddress.ip_address(row["ip"])))
            except ValueError:
                return (1, 0)

        rows.sort(key=sort_key)
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
