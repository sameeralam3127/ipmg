"""Runs scans in background threads and broadcasts progress to WebSockets."""

from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import asdict
from typing import Any, Dict, List, Optional, Set

from ipmg.core.engine import HostResult, ScanConfig, execute_scan
from ipmg.web.db import Database


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
        queue: asyncio.Queue = asyncio.Queue()
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
            loop.call_soon_threadsafe(queue.put_nowait, event)

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
        self._broadcast({"type": "scan_started", "scan_id": scan_id, "total": len(ips)})

        def on_result(result: HostResult, completed: int, total: int) -> None:
            self._db.add_result(scan_id, result)
            self._broadcast(
                {
                    "type": "result",
                    "scan_id": scan_id,
                    "completed": completed,
                    "total": total,
                    "result": asdict(result),
                }
            )

        try:
            execute_scan(ips, config, on_result=on_result, should_stop=stop.is_set)
        except Exception as exc:
            self._db.fail_scan(scan_id, str(exc))
            final_status = "failed"
        else:
            final_status = "cancelled" if stop.is_set() else "complete"
            self._db.finish_scan(scan_id, final_status, time.perf_counter() - started_at)
        finally:
            with self._lock:
                self._stops.pop(scan_id, None)

        self._broadcast(
            {
                "type": "scan_finished",
                "scan_id": scan_id,
                "status": final_status,
                "duration_s": round(time.perf_counter() - started_at, 3),
            }
        )
