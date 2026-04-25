from types import SimpleNamespace

import pandas as pd

from ipmg.services.scan_service import run_scan


def test_run_scan_handles_worker_errors(monkeypatch):
    captured = {}

    def fake_load_targets(_source):
        return ["8.8.8.8", "1.1.1.1"]

    def fake_ping_ip(ip, _timeout, _count):
        if ip == "1.1.1.1":
            raise RuntimeError("boom")
        return "Active", 10.5

    def fake_save_results(df, _base, _formats):
        captured["df"] = df.copy()

    def fake_print_summary(df, batch_timestamp, duration_seconds):
        captured["summary"] = (df.copy(), batch_timestamp, duration_seconds)

    monkeypatch.setattr("ipmg.services.scan_service.load_targets", fake_load_targets)
    monkeypatch.setattr("ipmg.services.scan_service.ping_ip", fake_ping_ip)
    monkeypatch.setattr("ipmg.services.scan_service.save_results", fake_save_results)
    monkeypatch.setattr("ipmg.services.scan_service.print_summary", fake_print_summary)

    args = SimpleNamespace(
        input="targets.csv",
        output="results",
        timeout=1,
        count=1,
        threads=2,
        formats=["csv"],
        discover=False,
        resolve=False,
        interval=None,
    )

    run_scan(args)

    assert args.timeout == 1
    assert args.count == 1

    df: pd.DataFrame = captured["df"]
    statuses = dict(zip(df["IP Address"], df["Status"]))
    assert statuses["8.8.8.8"] == "Active"
    assert statuses["1.1.1.1"] == "Error"
    assert len(df["Batch Timestamp"].unique()) == 1
    assert (df["Scan Duration (s)"] >= 0).all()


def test_run_scan_clamps_resource_limits(monkeypatch):
    captured = {}

    def fake_ping_ip(_ip, timeout, count):
        captured["limits"] = (timeout, count)
        return "Active", 1.0

    monkeypatch.setattr("ipmg.services.scan_service.load_targets", lambda _source: ["8.8.8.8"])
    monkeypatch.setattr("ipmg.services.scan_service.ping_ip", fake_ping_ip)
    monkeypatch.setattr("ipmg.services.scan_service.save_results", lambda *_args: None)
    monkeypatch.setattr("ipmg.services.scan_service.print_summary", lambda *_args: None)

    args = SimpleNamespace(
        input="targets.csv",
        output="results",
        timeout=999,
        count=999,
        threads=999,
        formats=["csv"],
        discover=False,
        resolve=False,
        interval=None,
    )

    run_scan(args)

    assert args.threads == 500
    assert captured["limits"] == (60, 10)
