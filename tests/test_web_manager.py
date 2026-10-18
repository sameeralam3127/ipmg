import asyncio

from ipmg.web.manager import OVERFLOW, SUBSCRIBER_QUEUE_LIMIT, ScanManager


def run_broadcasts(count):
    """Subscribe, broadcast ``count`` events, and return (manager, queue)."""

    async def scenario():
        manager = ScanManager(db=None)
        manager.attach_loop(asyncio.get_running_loop())
        queue = manager.subscribe()
        for n in range(count):
            manager._broadcast({"type": "result", "n": n})
        # Let the scheduled call_soon_threadsafe callbacks run.
        for _ in range(3):
            await asyncio.sleep(0)
        return manager, queue

    return asyncio.run(scenario())


def test_subscriber_receives_events_in_order():
    manager, queue = run_broadcasts(5)
    assert [queue.get_nowait()["n"] for _ in range(5)] == [0, 1, 2, 3, 4]
    assert queue in manager._subscribers


def test_subscriber_queue_never_grows_past_the_limit():
    manager, queue = run_broadcasts(SUBSCRIBER_QUEUE_LIMIT * 3)

    # The stalled subscriber is dropped: its backlog is discarded and replaced
    # by a single close marker, and later events are no longer queued for it.
    assert queue.qsize() == 1
    assert queue.get_nowait() is OVERFLOW
    assert queue not in manager._subscribers


class RecordingDb:
    """Stands in for the database: records each batch add_results receives."""

    def __init__(self, fail_times=0):
        self.batches = []
        self.fail_times = fail_times

    def add_results(self, _scan_id, results):
        if self.fail_times:
            self.fail_times -= 1
            raise OSError("disk I/O error")
        self.batches.append([result.ip for result in results])
        return len(self.batches[-1])


def _result(n):
    from ipmg.core.engine import HostResult

    return HostResult(ip=f"10.0.{n // 256}.{n % 256}", status="Active", latency=1.0)


def test_result_writer_stores_results_in_batches_in_arrival_order():
    from ipmg.web.manager import RESULT_BATCH_SIZE, ResultWriter

    db = RecordingDb()
    writer = ResultWriter(db, scan_id=1)
    for n in range(RESULT_BATCH_SIZE * 2 + 50):
        writer.add(_result(n))
    writer.close()

    stored = [ip for batch in db.batches for ip in batch]
    assert stored == [_result(n).ip for n in range(RESULT_BATCH_SIZE * 2 + 50)]
    # A handful of transactions, not one per host.
    assert len(db.batches) <= 6


def test_result_writer_flushes_a_slow_scan_without_waiting_for_a_full_batch():
    import time

    from ipmg.web.manager import RESULT_FLUSH_S, ResultWriter

    db = RecordingDb()
    writer = ResultWriter(db, scan_id=1)
    try:
        writer.add(_result(1))
        deadline = time.monotonic() + RESULT_FLUSH_S * 20
        while not db.batches and time.monotonic() < deadline:
            time.sleep(0.01)
        assert db.batches == [[_result(1).ip]]
    finally:
        writer.close()


def test_result_writer_retries_a_batch_that_failed_to_write():
    from ipmg.web.manager import ResultWriter

    db = RecordingDb(fail_times=1)
    writer = ResultWriter(db, scan_id=1)
    writer.add(_result(1))
    try:
        writer.flush()
    except OSError:
        pass
    writer.add(_result(2))
    writer.close()

    assert [ip for batch in db.batches for ip in batch] == [_result(1).ip, _result(2).ip]
