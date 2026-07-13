import threading
import time

from ipmg.utils import HostnameCache, clamp_int, resolve_hostname, timestamp_str


def test_timestamp_str_format():
    ts = timestamp_str()
    # Basic sanity: only digits + underscore
    assert len(ts) >= 8
    assert all(ch.isdigit() or ch == "_" for ch in ts)


def test_clamp_int_min_max():
    assert clamp_int(5, minimum=1, maximum=10) == 5
    assert clamp_int(-1, minimum=0, maximum=10) == 0
    assert clamp_int(999, minimum=0, maximum=10) == 10


def test_resolve_hostname_safe():
    # Should not raise, even for nonsense IP
    host = resolve_hostname("203.0.113.123")  # TEST-NET-3, often unrouted
    assert isinstance(host, str)
    assert len(host) > 0


def test_hostname_cache_reuses_lookup_until_ttl_expires(monkeypatch):
    calls = []
    monotonic_values = iter([100.0, 101.0, 105.0, 105.0])

    monkeypatch.setattr("ipmg.utils.helpers.time.monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(
        "ipmg.utils.helpers.socket.gethostbyaddr",
        lambda ip: calls.append(ip) or ("router.local", [], [ip]),
    )

    cache = HostnameCache(ttl_seconds=5)

    assert cache.resolve("192.0.2.1") == "router.local"
    assert cache.resolve("192.0.2.1") == "router.local"
    assert cache.resolve("192.0.2.1") == "router.local"
    assert calls == ["192.0.2.1", "192.0.2.1"]


def test_hostname_cache_coordinates_simultaneous_lookups(monkeypatch):
    calls = []
    lookup_started = threading.Event()
    allow_lookup_to_finish = threading.Event()

    def fake_lookup(ip):
        calls.append(ip)
        lookup_started.set()
        allow_lookup_to_finish.wait(timeout=1)
        return "router.local", [], [ip]

    monkeypatch.setattr("ipmg.utils.helpers.socket.gethostbyaddr", fake_lookup)
    cache = HostnameCache(ttl_seconds=60)
    results = []

    first = threading.Thread(target=lambda: results.append(cache.resolve("192.0.2.1")))
    second = threading.Thread(target=lambda: results.append(cache.resolve("192.0.2.1")))
    first.start()
    assert lookup_started.wait(timeout=1)
    second.start()
    time.sleep(0.01)
    allow_lookup_to_finish.set()
    first.join(timeout=1)
    second.join(timeout=1)

    assert calls == ["192.0.2.1"]
    assert results == ["router.local", "router.local"]
