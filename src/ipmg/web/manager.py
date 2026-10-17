"""Runs scans in background threads and broadcasts progress to WebSockets."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import asdict
from typing import Any, Dict, List, Optional, Set

from ipmg.core.engine import HostResult, ScanConfig, execute_scan
from ipmg.web.db import Database
from ipmg.web.schemas import (
    HostResultModel,
    ResultEvent,
    ScanFinishedEvent,
    ScanStartedEvent,
)

#: Events buffered per WebSocket subscriber. A client this far behind is
#: disconnected instead of letting its backlog grow without bound; the browser
#: reconnects and reloads the scan from the REST API.
SUBSCRIBER_QUEUE_LIMIT = 1000

#: Queued in place of an event to tell the WebSocket handler to close.
OVERFLOW = None

#: A running scan stores its results this many hosts at a time, or whatever
#: has arrived every RESULT_FLUSH_S seconds, whichever comes first. One
#: transaction per host was ~100x slower and held the database lock, which
#: every API request also takes, for the whole of a large scan.
RESULT_BATCH_SIZE = 200
RESULT_FLUSH_S = 0.25

log = logging.getLogger(__name__)


class ResultWriter:
    """Batch one scan's results into the database as they arrive.

    :meth:`add` is called for every host. Results are written when a batch
    fills, and a background thread writes whatever is waiting every
    :data:`RESULT_FLUSH_S` seconds, so a slow scan's results still reach the
    REST API promptly. :meth:`close` writes the rest.
    """

    def __init__(self, db: Database, scan_id: int) -> None:
        self._db = db
        self._scan_id = scan_id
        self._pending: List[HostResult] = []
        self._lock = threading.Lock()
        # Held across each write, so batches are stored in arrival order.
        self._write_lock = threading.Lock()
        self._stop = threading.Event()
        self._flusher = threading.Thread(
            target=self._flush_periodically, name=f"ipmg-results-{scan_id}", daemon=True
        )
        self._flusher.start()

    def add(self, result: HostResult) -> None:
        with self._lock:
            self._pending.append(result)
            full = len(self._pending) >= RESULT_BATCH_SIZE
        if full:
            self.flush()

    def flush(self) -> None:
        with self._write_lock:
            with self._lock:
                batch, self._pending = self._pending, []
            if not batch:
                return
            try:
                self._db.add_results(self._scan_id, batch)
            except BaseException:
                # Put them back for the next attempt; close() raises if that
                # one fails too, which fails the scan.
                with self._lock:
                    self._pending[:0] = batch
                raise

    def _flush_periodically(self) -> None:
        while not self._stop.wait(RESULT_FLUSH_S):
            try:
                self.flush()
            except Exception:
                log.debug("periodic result flush failed", exc_info=True)

    def close(self) -> None:
        self._stop.set()
        self._flusher.join()
        self.flush()


#: Recorded on a scan that IPMG Web could not finish because it was stopped.
INTERRUPTED_ERROR = "IPMG Web stopped during the scan"

#: Scans IPMG Web runs at once unless ``--max-scans`` says otherwise. Each one
#: may use up to 500 threads, each running a ``ping`` process.
DEFAULT_MAX_SCANS = 2


class ScanLimitError(Exception):
    """Raised by :meth:`ScanManager.start_scan` when ``max_scans`` are already running."""

    def __init__(self, running: int, limit: int) -> None:
        self.running = running
        self.limit = limit
        already = "A scan is" if running == 1 else f"{running} scans are"
        super().__init__(
            f"{already} already running, the most IPMG Web runs at once "
            f"(--max-scans {limit}). Wait for one to finish, or cancel it."
        )


#: Seconds shutdown waits for running scans to stop before marking them.
SHUTDOWN_WAIT_S = 5.0


class ScanManager:
    def __init__(self, db: Database, max_scans: int = DEFAULT_MAX_SCANS) -> None:
        self._db = db
        self.max_scans = max(max_scans, 1)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._subscribers: Set[asyncio.Queue] = set()
        self._stops: Dict[int, threading.Event] = {}
        self._threads: Dict[int, threading.Thread] = {}
        self._lock = threading.Lock()
        # Held from the limit check until the new scan is registered, so two
        # requests arriving together cannot both take the last slot.
        self._start_lock = threading.Lock()

    # ------------------------------------------------------ subscriptions

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=SUBSCRIBER_QUEUE_LIMIT)
        with self._lock:
            self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        with self._lock:
            self._subscribers.discard(queue)

    def _broadcast(self, event: Dict[str, Any]) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        with self._lock:
            queues = list(self._subscribers)
        for queue in queues:
            loop.call_soon_threadsafe(self._offer, queue, event)

    def _offer(self, queue: asyncio.Queue, event: Dict[str, Any]) -> None:
        """Queue an event for one subscriber; runs on the event loop."""
        with self._lock:
            if queue not in self._subscribers:
                return
        if queue.full():
            # The client is not reading. Drop its backlog and close it.
            self.unsubscribe(queue)
            while not queue.empty():
                queue.get_nowait()
            queue.put_nowait(OVERFLOW)
            return
        queue.put_nowait(event)

    # -------------------------------------------------------------- scans

    def start_scan(self, ips: List[str], config: ScanConfig, source: str) -> int:
        """Start a scan in the background and return its id.

        Raises :class:`ScanLimitError`, before anything is stored, when
        ``max_scans`` scans are already running.
        """
        with self._start_lock:
            running = self.running_count()
            if running >= self.max_scans:
                raise ScanLimitError(running, self.max_scans)

            scan_id = self._db.create_scan(source, len(ips), asdict(config))
            stop = threading.Event()
            thread = threading.Thread(
                target=self._run,
                args=(scan_id, ips, config, stop),
                name=f"ipmg-scan-{scan_id}",
                daemon=True,
            )
            with self._lock:
                self._stops[scan_id] = stop
                self._threads[scan_id] = thread
        thread.start()
        return scan_id

    def is_running(self, scan_id: int) -> bool:
        """Whether this process has a live worker for ``scan_id``."""
        with self._lock:
            return scan_id in self._stops

    def running_count(self) -> int:
        with self._lock:
            return len(self._stops)

    def recover(self) -> int:
        """Mark scans another run of IPMG Web left ``running`` as interrupted.

        Called at startup, before this process starts any scan of its own, so
        every ``running`` row belongs to a process that stopped (a Ctrl+C, a
        container restart, a crash) and no worker will ever finish it.
        """
        return self._db.interrupt_scans(INTERRUPTED_ERROR)

    def shutdown(self, wait_s: float = SHUTDOWN_WAIT_S) -> None:
        """Stop every running scan, and record any that do not stop in time."""
        with self._lock:
            stops = dict(self._stops)
            threads = dict(self._threads)
        for stop in stops.values():
            stop.set()

        # A stopped worker records its scan as cancelled on its way out; it
        # only has the probes already in flight to wait for.
        deadline = time.monotonic() + wait_s
        for thread in threads.values():
            thread.join(max(deadline - time.monotonic(), 0))
        stuck = [scan_id for scan_id, thread in threads.items() if thread.is_alive()]
        if stuck:
            self._db.interrupt_scans(INTERRUPTED_ERROR, stuck)

    def cancel(self, scan_id: int) -> bool:
        with self._lock:
            stop = self._stops.get(scan_id)
        if stop is None:
            return False
        stop.set()
        return True

    # ------------------------------------------------------------ worker

    def _run(
        self,
        scan_id: int,
        ips: List[str],
        config: ScanConfig,
        stop: threading.Event,
    ) -> None:
        started_at = time.perf_counter()
        self._broadcast(ScanStartedEvent(scan_id=scan_id, total=len(ips)).model_dump())
        writer = ResultWriter(self._db, scan_id)

        def on_result(result: HostResult, completed: int, total: int) -> None:
            writer.add(result)
            # Events still go out per host: the live view should not wait
            # for the database batch.
            event = ResultEvent(
                scan_id=scan_id,
                completed=completed,
                total=total,
                result=HostResultModel(**asdict(result)),
            )
            self._broadcast(event.model_dump())

        try:
            try:
                execute_scan(ips, config, on_result=on_result, should_stop=stop.is_set)
            finally:
                writer.close()
        except Exception as exc:
            self._db.fail_scan(scan_id, str(exc))
            final_status = "failed"
        else:
            final_status = "cancelled" if stop.is_set() else "complete"
            self._db.finish_scan(scan_id, final_status, time.perf_counter() - started_at)
        finally:
            with self._lock:
                self._stops.pop(scan_id, None)
                self._threads.pop(scan_id, None)

        finished = ScanFinishedEvent(
            scan_id=scan_id,
            status=final_status,
            duration_s=round(time.perf_counter() - started_at, 3),
        )
        self._broadcast(finished.model_dump())
