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


def test_execute_scan_resolves_hostnames_in_parallel_on_workers(monkeypatch):
    # Four lookups must be in flight at once to get past the barrier; if they
    # ran one at a time on the collecting thread, the barrier would time out.
    barrier = threading.Barrier(4, timeout=5)
    resolver_threads = set()

    def slow_lookup(ip):
        resolver_threads.add(threading.current_thread())
        barrier.wait()
        return (f"host-{ip}", [], [ip])

    monkeypatch.setattr("ipmg.core.engine.ping_ip", lambda *_a: ("Active", 1.0))
    monkeypatch.setattr("ipmg.utils.helpers.socket.gethostbyaddr", slow_lookup)

    ips = [f"10.0.0.{n}" for n in range(1, 5)]
    results = execute_scan(ips, ScanConfig(resolve=True, threads=4))

    assert sorted(r.hostname for r in results) == [f"host-{ip}" for ip in ips]
    assert threading.current_thread() not in resolver_threads


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


def test_scan_config_clamps_port_timeout():
    config = ScanConfig(port_timeout=999).clamped()

    assert config.port_timeout == 30.0


def test_execute_scan_probes_ports_only_for_active_hosts_when_enabled(monkeypatch):
    def fake_ping_ip(ip, _timeout, _count):
        return ("Active", 1.0) if ip == "10.0.0.1" else ("Timeout", None)

    monkeypatch.setattr("ipmg.core.engine.ping_ip", fake_ping_ip)
    monkeypatch.setattr("ipmg.core.engine.scan_ports", lambda ip, _ports, _timeout, **_k: [22, 443])

    results = execute_scan(
        ["10.0.0.1", "10.0.0.2"],
        ScanConfig(scan_ports=True, ports=(22, 443)),
    )

    by_ip = {result.ip: result for result in results}
    assert by_ip["10.0.0.1"].open_ports == (22, 443)
    assert by_ip["10.0.0.2"].open_ports == ()


def test_execute_scan_skips_port_scan_when_disabled(monkeypatch):
    monkeypatch.setattr("ipmg.core.engine.ping_ip", lambda *_a: ("Active", 1.0))

    called = []
    monkeypatch.setattr(
        "ipmg.core.engine.scan_ports",
        lambda *args: called.append(args) or [],
    )

    results = execute_scan(["10.0.0.1"], ScanConfig(scan_ports=False))

    assert results[0].open_ports == ()
    assert called == []


def test_execute_scan_propagates_ping_errors(monkeypatch):
    from ipmg.exceptions import PingError

    def fake_ping_ip(*_a):
        raise PingError("ping missing")

    monkeypatch.setattr("ipmg.core.engine.ping_ip", fake_ping_ip)

    with pytest.raises(PingError):
        execute_scan(["10.0.0.1"], ScanConfig())


def test_port_probes_share_one_bounded_pool(monkeypatch):
    # 10 hosts x 5 ports on 10 workers would mean 50 probes at once without
    # the shared pool; with MAX_PORT_PROBE_WORKERS = 4 no more than 4 may run.
    import time

    monkeypatch.setattr("ipmg.core.engine.MAX_PORT_PROBE_WORKERS", 4)
    monkeypatch.setattr("ipmg.core.engine.ping_ip", lambda *_a: ("Active", 1.0))

    lock = threading.Lock()
    in_flight = 0
    peak = 0

    def fake_probe(_ip, port, _timeout):
        nonlocal in_flight, peak
        with lock:
            in_flight += 1
            peak = max(peak, in_flight)
        time.sleep(0.01)
        with lock:
            in_flight -= 1
        return port == 22

    monkeypatch.setattr("ipmg.core.portscan._probe", fake_probe)

    ips = [f"10.0.0.{n}" for n in range(1, 11)]
    config = ScanConfig(threads=10, scan_ports=True, ports=(22, 80, 443, 3389, 5432))
    results = execute_scan(ips, config)

    assert peak <= 4
    assert all(result.open_ports == (22,) for result in results)
