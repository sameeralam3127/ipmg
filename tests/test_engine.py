import threading

import pytest

from ipmg.core.engine import HostResult, ScanConfig, execute_scan


def test_execute_scan_returns_result_per_host(monkeypatch):
    def fake_ping_ip(ip, _timeout, _count):
        return ("Active", 5.0) if ip == "8.8.8.8" else ("Inactive", None)

    monkeypatch.setattr("ipmg.core.engine.ping_ip", fake_ping_ip)

    results = execute_scan(["8.8.8.8", "1.1.1.1"], ScanConfig(threads=2))

    by_ip = {result.ip: result for result in results}
    assert by_ip["8.8.8.8"] == HostResult(ip="8.8.8.8", status="Active", latency=5.0)
    assert by_ip["1.1.1.1"].status == "Inactive"


def test_execute_scan_reports_progress_via_callback(monkeypatch):
    monkeypatch.setattr("ipmg.core.engine.ping_ip", lambda *_a: ("Active", 1.0))

    seen = []
    execute_scan(
        ["10.0.0.1", "10.0.0.2", "10.0.0.3"],
        ScanConfig(threads=1),
        on_result=lambda result, done, total: seen.append((result.ip, done, total)),
    )

    assert [done for _ip, done, _total in seen] == [1, 2, 3]
    assert all(total == 3 for _ip, _done, total in seen)


def test_execute_scan_converts_worker_errors(monkeypatch):
    def fake_ping_ip(ip, _timeout, _count):
        if ip == "10.0.0.2":
            raise RuntimeError("boom")
        return "Active", 1.0

    monkeypatch.setattr("ipmg.core.engine.ping_ip", fake_ping_ip)

    results = execute_scan(["10.0.0.1", "10.0.0.2"], ScanConfig(threads=2))

    statuses = {result.ip: result.status for result in results}
    assert statuses == {"10.0.0.1": "Active", "10.0.0.2": "Error"}


def test_execute_scan_resolves_hostnames_when_enabled(monkeypatch):
    monkeypatch.setattr("ipmg.core.engine.ping_ip", lambda *_a: ("Active", 1.0))
    monkeypatch.setattr(
        "ipmg.utils.helpers.socket.gethostbyaddr", lambda ip: (f"host-{ip}", [], [ip])
    )

    results = execute_scan(["10.0.0.1"], ScanConfig(resolve=True))

    assert results[0].hostname == "host-10.0.0.1"


def test_execute_scan_stops_early_when_requested(monkeypatch):
    monkeypatch.setattr("ipmg.core.engine.ping_ip", lambda *_a: ("Active", 1.0))

    stop = threading.Event()

    def on_result(_result, done, _total):
        if done == 2:
            stop.set()

    results = execute_scan(
        [f"10.0.0.{n}" for n in range(1, 50)],
        ScanConfig(threads=1),
        on_result=on_result,
        should_stop=stop.is_set,
    )

    assert len(results) < 49


def test_scan_config_clamps_limits():
    config = ScanConfig(timeout=999, count=999, threads=999, dns_cache_ttl=-5).clamped()

    assert (config.timeout, config.count, config.threads) == (60, 10, 500)
    assert config.dns_cache_ttl == 0


def test_execute_scan_propagates_ping_errors(monkeypatch):
    from ipmg.exceptions import PingError

    def fake_ping_ip(*_a):
        raise PingError("ping missing")

    monkeypatch.setattr("ipmg.core.engine.ping_ip", fake_ping_ip)

    with pytest.raises(PingError):
        execute_scan(["10.0.0.1"], ScanConfig())
