from types import SimpleNamespace

import pandas as pd
import pytest

from ipmg.infrastructure.database import Database
from ipmg.services.scan_service import run_scan
from ipmg.utils.helpers import console


@pytest.fixture(autouse=True)
def wide_console():
    """Keep rich from truncating table cells in captured output."""
    previous = console.width
    console.width = 200
    yield
    console.width = previous


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
    monkeypatch.setattr("ipmg.core.engine.ping_ip", fake_ping_ip)
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
        history=False,
        compare=False,
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
    monkeypatch.setattr("ipmg.core.engine.ping_ip", fake_ping_ip)
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
        history=False,
        compare=False,
    )

    run_scan(args)

    assert args.threads == 500
    assert captured["limits"] == (60, 10)


def scan_args(tmp_path, **overrides):
    args = dict(
        input="targets.csv",
        output=str(tmp_path / "results"),
        timeout=1,
        count=1,
        threads=2,
        formats=[],
        discover=False,
        resolve=False,
        interval=None,
        history=True,
        compare=False,
        compare_any_source=False,
        db=str(tmp_path / "history.db"),
        diff_formats=[],
        diff_output=str(tmp_path / "changes"),
        latency_threshold=5.0,
        latency_pct=25.0,
    )
    args.update(overrides)
    return SimpleNamespace(**args)


@pytest.fixture()
def stub_scan(monkeypatch):
    """Run scans against a scripted set of ping results."""
    state = {"statuses": {}}

    monkeypatch.setattr(
        "ipmg.services.scan_service.load_targets",
        lambda _source: list(state["statuses"]),
    )
    monkeypatch.setattr("ipmg.services.scan_service.save_results", lambda *_args: None)
    monkeypatch.setattr("ipmg.services.scan_service.print_summary", lambda *_args: None)
    monkeypatch.setattr(
        "ipmg.core.engine.ping_ip",
        lambda ip, _timeout, _count: state["statuses"][ip],
    )
    return state


def test_run_scan_records_history(tmp_path, stub_scan):
    stub_scan["statuses"] = {"10.0.0.1": ("Active", 5.0)}
    args = scan_args(tmp_path)

    run_scan(args)

    scans = Database(tmp_path / "history.db").list_scans()
    assert len(scans) == 1
    assert scans[0]["source"] == "targets.csv"
    assert scans[0]["status_counts"] == {"Active": 1}


def test_run_scan_can_skip_history(tmp_path, stub_scan):
    stub_scan["statuses"] = {"10.0.0.1": ("Active", 5.0)}

    run_scan(scan_args(tmp_path, history=False))

    assert not (tmp_path / "history.db").exists()


def test_run_scan_compare_prints_and_exports_changes(tmp_path, stub_scan, capsys):
    stub_scan["statuses"] = {"10.0.0.1": ("Active", 5.0)}
    run_scan(scan_args(tmp_path))

    stub_scan["statuses"] = {"10.0.0.1": ("Timeout", None), "10.0.0.2": ("Active", 1.0)}
    run_scan(scan_args(tmp_path, compare=True, diff_formats=["md"]))

    out = capsys.readouterr().out
    assert "Host offline" in out
    assert "New host" in out
    assert list(tmp_path.glob("changes_*.md"))


def test_run_scan_compare_without_a_baseline_is_not_fatal(tmp_path, stub_scan, capsys):
    stub_scan["statuses"] = {"10.0.0.1": ("Active", 5.0)}

    run_scan(scan_args(tmp_path, compare=True))

    assert "Change report skipped" in capsys.readouterr().out


def test_run_scan_warns_when_comparing_without_history(tmp_path, stub_scan, capsys):
    stub_scan["statuses"] = {"10.0.0.1": ("Active", 5.0)}

    run_scan(scan_args(tmp_path, history=False, compare=True))

    assert "Change detection needs scan history" in capsys.readouterr().out
