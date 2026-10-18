"""Scheduled scans in IPMG Web: start each schedule's scan when it is due.

Schedules live in the history database, so they survive a restart. A thread
wakes every :data:`TICK_S` seconds and starts every due, unpaused schedule
through the same :class:`~ipmg.web.manager.ScanManager` an on-demand scan
uses, under the source ``schedule:<name>``, so its runs appear in History and
feed the Changes view like any other scan.

A run is skipped, never stacked, when the schedule's previous run is still
going, or when ``--max-scans`` scans are already running; the skip and its
reason are recorded and the schedule moves on to its next slot. Interval
schedules keep a fixed cadence: a run that started late does not push the
later ones back.
"""

from __future__ import annotations

import dataclasses
import logging
import threading
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from ipmg.core.cron import next_interval_run, parse_cron
from ipmg.core.engine import ScanConfig
from ipmg.exceptions import FileIOError
from ipmg.infrastructure.database import Database
from ipmg.infrastructure.file_io import parse_manual_targets
from ipmg.web.manager import ScanLimitError, ScanManager

log = logging.getLogger(__name__)

#: Seconds between checks for due schedules: a scheduled run starts at most
#: this late.
TICK_S = 15.0

SOURCE_PREFIX = "schedule:"

#: The ScanConfig settings a schedule may store.
_CONFIG_FIELDS = frozenset(field.name for field in dataclasses.fields(ScanConfig))


class ScheduleBusyError(Exception):
    """The schedule's previous run is still going."""


def schedule_source(name: str) -> str:
    """The history source a schedule's scans are stored under."""
    return f"{SOURCE_PREFIX}{name}"


def format_time(moment: datetime) -> str:
    """Local ``YYYY-MM-DD HH:MM:SS``, as every other time in the history."""
    return moment.isoformat(sep=" ", timespec="seconds")


def first_run(interval_minutes: int | None, cron: str | None, now: datetime) -> datetime:
    """When a new (or resumed) schedule runs first: an interval one at once, a cron one on time."""
    if cron:
        return parse_cron(cron).next_after(now)
    return now


def next_run(schedule: dict[str, Any], now: datetime) -> datetime:
    """The schedule's next slot after ``now``."""
    if schedule.get("cron"):
        return parse_cron(schedule["cron"]).next_after(now)
    interval = timedelta(minutes=int(schedule["interval_minutes"]))
    previous = schedule.get("next_run_at")
    anchor = datetime.fromisoformat(previous) if previous else now
    slot, _missed = next_interval_run(anchor, interval, now)
    return slot


def scan_config(settings: dict[str, Any]) -> ScanConfig:
    known = {key: value for key, value in settings.items() if key in _CONFIG_FIELDS}
    if "ports" in known:
        known["ports"] = tuple(known["ports"])
    return ScanConfig(**known).clamped()


class Scheduler:
    """Runs due schedules on a background thread."""

    def __init__(
        self,
        db: Database,
        manager: ScanManager,
        clock: Callable[[], datetime] = datetime.now,
        tick_s: float = TICK_S,
    ) -> None:
        self._db = db
        self._manager = manager
        self._clock = clock
        self._tick_s = tick_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        # One schedule start at a time, so a tick and "Run now" cannot both
        # see the previous run as finished and start two.
        self._lock = threading.Lock()

    # ----------------------------------------------------------- lifecycle

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="ipmg-scheduler", daemon=True)
        self._thread.start()

    def stop(self, wait_s: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(wait_s)

    def _loop(self) -> None:
        while True:
            try:
                self.tick()
            except Exception:  # one bad tick must not end every schedule
                log.warning("scheduled scans: tick failed", exc_info=True)
            if self._stop.wait(self._tick_s):
                return

    # ------------------------------------------------------------- running

    def tick(self) -> list[int]:
        """Start every due schedule; returns the ids of the scans started."""
        now = self._clock()
        started = []
        for schedule in self._db.due_schedules(format_time(now)):
            scan_id = self._run_due(schedule, now)
            if scan_id is not None:
                started.append(scan_id)
        return started

    def run_now(self, schedule_id: int) -> dict[str, Any]:
        """Start a schedule's scan at once, outside its timetable.

        Raises KeyError for an unknown schedule, and ScheduleBusyError,
        ScanLimitError, or FileIOError when it cannot start; its next run
        stays where it was.
        """
        schedule = self._db.get_schedule(schedule_id)
        if schedule is None:
            raise KeyError(schedule_id)
        now = self._clock()
        with self._lock:
            scan_id, total = self._start(schedule)
            self._db.record_schedule_run(
                schedule_id, format_time(now), scan_id, schedule.get("next_run_at")
            )
        return {"id": scan_id, "total": total}

    def _start(self, schedule: dict[str, Any]):
        last = schedule.get("last_scan_id")
        if last is not None and self._manager.is_running(int(last)):
            raise ScheduleBusyError(f"The previous run (scan #{last}) is still running.")
        ips = parse_manual_targets(schedule["targets"])
        scan_id = self._manager.start_scan(
            ips, scan_config(schedule.get("config") or {}), source=schedule_source(schedule["name"])
        )
        return scan_id, len(ips)

    def _run_due(self, schedule: dict[str, Any], now: datetime) -> int | None:
        upcoming = format_time(next_run(schedule, now))
        with self._lock:
            try:
                scan_id, _total = self._start(schedule)
            except (ScheduleBusyError, ScanLimitError, FileIOError) as exc:
                self._db.record_schedule_skip(schedule["id"], format_time(now), str(exc), upcoming)
                log.info("schedule %s skipped: %s", schedule["name"], exc)
                return None
            except Exception as exc:  # a broken schedule still moves on to its next slot
                self._db.record_schedule_skip(
                    schedule["id"], format_time(now), f"Could not start: {exc}", upcoming
                )
                log.warning("schedule %s could not start", schedule["name"], exc_info=True)
                return None
            self._db.record_schedule_run(schedule["id"], format_time(now), scan_id, upcoming)
        return scan_id
