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


class ScanManager:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._subscribers: Set[asyncio.Queue] = set()
        self._stops: Dict[int, threading.Event] = {}
        self._lock = threading.Lock()

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
        scan_id = self._db.create_scan(source, len(ips), asdict(config))
        stop = threading.Event()
        with self._lock:
            self._stops[scan_id] = stop

        thread = threading.Thread(
            target=self._run,
            args=(scan_id, ips, config, stop),
            name=f"ipmg-scan-{scan_id}",
            daemon=True,
        )
        thread.start()
        return scan_id

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

        finished = ScanFinishedEvent(
            scan_id=scan_id,
            status=final_status,
            duration_s=round(time.perf_counter() - started_at, 3),
        )
        self._broadcast(finished.model_dump())
