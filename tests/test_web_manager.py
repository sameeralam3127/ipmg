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
