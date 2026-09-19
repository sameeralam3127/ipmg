import csv
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from ipmg.core.engine import HostResult
from ipmg.infrastructure.file_io import save_results, write_report
from ipmg.infrastructure.incremental import (
    IncrementalOptions,
    IncrementalReport,
    atomic_write_bytes,
)
from ipmg.services.scan_service import run_scan
from ipmg.utils.helpers import console

BATCH = "2026-09-17 12:00:00"


@pytest.fixture(autouse=True)
def wide_console():
    """Keep rich from wrapping the paths this module asserts on."""
    previous = console.width
    console.width = 200
    yield
    console.width = previous


def _result(ip: str, status: str = "Active", latency: float = 1.5) -> HostResult:
    return HostResult(ip=ip, status=status, latency=latency, hostname="", open_ports=())


def _report(tmp_path, formats, **kwargs) -> IncrementalReport:
    return IncrementalReport(
        base=str(tmp_path / "scan"),
        formats=formats,
        timestamp="20260917_120000",
        batch_timestamp=BATCH,
        **kwargs,
    )


def test_csv_is_readable_after_every_host(tmp_path):
    with _report(tmp_path, ["csv"]) as report:
        report.record(_result("8.8.8.8"))
        after_first = list(csv.DictReader(open(report.path_for("csv"), encoding="utf-8")))
        report.record(_result("1.1.1.1", "Timeout", None))

    assert [row["IP Address"] for row in after_first] == ["8.8.8.8"]

    rows = list(csv.DictReader(open(report.path_for("csv"), encoding="utf-8")))
    assert [row["IP Address"] for row in rows] == ["8.8.8.8", "1.1.1.1"]
    assert rows[0]["Status"] == "Active"
    assert rows[1]["Latency"] == ""
    # The pass is unfinished, so each row carries the time it landed instead of
    # a total duration nobody knows yet.
    assert float(rows[0]["Scan Duration (s)"]) >= 0


def test_jsonl_rows_parse_one_by_one(tmp_path):
    with _report(tmp_path, ["jsonl"]) as report:
        report.record(_result("8.8.8.8"))
        report.record(_result("9.9.9.9"))

    lines = open(report.path_for("jsonl"), encoding="utf-8").read().splitlines()
    records = [json.loads(line) for line in lines]
    assert [record["IP Address"] for record in records] == ["8.8.8.8", "9.9.9.9"]
    assert records[0]["Batch Timestamp"] == BATCH


def test_streamed_cells_are_escaped(tmp_path):
    hostile = HostResult(
        ip="8.8.8.8",
        status="Active",
        latency=1.0,
        # A hostname is published by the host being scanned, so it may carry
        # both a formula and a field separator.
        hostname='=cmd|calc,"x"',
        open_ports=(22, 80),
    )

    with _report(tmp_path, ["csv", "jsonl"]) as report:
        report.record(hostile)

    rows = list(csv.DictReader(open(report.path_for("csv"), encoding="utf-8")))
    assert rows[0]["Hostname"] == '\'=cmd|calc,"x"'
    assert rows[0]["Open Ports"] == "22, 80"

    record = json.loads(open(report.path_for("jsonl"), encoding="utf-8").read().strip())
    assert record["Hostname"] == '=cmd|calc,"x"'


def test_snapshot_formats_are_written_on_interruption(tmp_path):
    report = _report(tmp_path, ["xlsx", "json", "md"], options=IncrementalOptions(autosave_s=3600))
    with pytest.raises(RuntimeError):
        with report:
            report.record(_result("8.8.8.8"))
            raise RuntimeError("scan died")

    assert len(pd.read_excel(report.path_for("xlsx"))) == 1
    assert json.loads(open(report.path_for("json"), encoding="utf-8").read())[0]["Status"] == (
        "Active"
    )
    assert "IPMG Scan Report" in open(report.path_for("md"), encoding="utf-8").read()


def test_snapshot_formats_wait_for_the_autosave_interval(tmp_path):
    with _report(tmp_path, ["xlsx"], options=IncrementalOptions(autosave_s=3600)) as report:
        report.record(_result("8.8.8.8"))
        # Nothing has been written yet: the interval has not elapsed, and a
        # clean exit leaves the final report to save_results.
        assert not (tmp_path / "scan_20260917_120000.xlsx").exists()

    assert report.written_paths == []


def test_autosave_interval_is_clamped():
    assert IncrementalOptions(autosave_s=0.01).clamped().autosave_s == 1.0
    assert IncrementalOptions(autosave_s=10_000).clamped().autosave_s == 3600.0


def test_atomic_write_keeps_the_previous_file_on_failure(tmp_path, monkeypatch):
    target = tmp_path / "report.csv"
    target.write_text("original", encoding="utf-8")

    def failing_replace(_src, _dst):
        raise OSError("disk full")

    monkeypatch.setattr("ipmg.infrastructure.incremental.os.replace", failing_replace)

    with pytest.raises(OSError):
        atomic_write_bytes(str(target), b"new")

    assert target.read_text(encoding="utf-8") == "original"
    assert list(tmp_path.glob(".*.tmp")) == []


def test_write_report_rejects_unknown_formats(tmp_path):
    with pytest.raises(ValueError):
        write_report(pd.DataFrame([{"IP Address": "8.8.8.8"}]), str(tmp_path / "x.pdf"), "pdf")


def test_save_results_reuses_a_supplied_timestamp(tmp_path):
    frame = pd.DataFrame([{"IP Address": "8.8.8.8", "Status": "Active"}])

    paths = save_results(frame, str(tmp_path / "scan"), ["csv", "jsonl"], timestamp="stamp")

    assert [Path(path).name for path in paths] == ["scan_stamp.csv", "scan_stamp.jsonl"]
    assert json.loads(open(paths[1], encoding="utf-8").read().strip())["IP Address"] == "8.8.8.8"


def _scan_args(tmp_path, **overrides):
    args = SimpleNamespace(
        input="targets.csv",
        output=str(tmp_path / "scan"),
        timeout=1,
        count=1,
        threads=1,
        formats=["csv"],
        discover=False,
        resolve=False,
        interval=None,
        history=False,
        compare=False,
        verbose=False,
    )
    for key, value in overrides.items():
        setattr(args, key, value)
    return args


def _interrupted_ping(stop_at: str):
    def ping_ip(ip, _timeout, _count):
        if ip == stop_at:
            raise KeyboardInterrupt
        return "Active", 1.0

    return ping_ip


def test_interrupted_scan_keeps_the_hosts_already_scanned(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        "ipmg.services.scan_service.load_targets", lambda _source: ["8.8.8.8", "1.1.1.1"]
    )
    monkeypatch.setattr("ipmg.core.engine.ping_ip", _interrupted_ping("1.1.1.1"))

    with pytest.raises(KeyboardInterrupt):
        run_scan(_scan_args(tmp_path))

    reports = list(tmp_path.glob("scan_*.csv"))
    assert len(reports) == 1
    rows = list(csv.DictReader(open(reports[0], encoding="utf-8")))
    assert [row["IP Address"] for row in rows] == ["8.8.8.8"]
    assert "Partial report" in capsys.readouterr().out


def test_no_incremental_leaves_nothing_behind_when_interrupted(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "ipmg.services.scan_service.load_targets", lambda _source: ["8.8.8.8", "1.1.1.1"]
    )
    monkeypatch.setattr("ipmg.core.engine.ping_ip", _interrupted_ping("1.1.1.1"))

    with pytest.raises(KeyboardInterrupt):
        run_scan(_scan_args(tmp_path, no_incremental=True))

    assert list(tmp_path.glob("scan_*")) == []


def test_finished_scan_writes_one_set_of_reports(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "ipmg.services.scan_service.load_targets", lambda _source: ["8.8.8.8", "1.1.1.1"]
    )
    monkeypatch.setattr("ipmg.core.engine.ping_ip", lambda *_args: ("Active", 1.0))

    run_scan(_scan_args(tmp_path, formats=["csv", "xlsx"]))

    # The incremental writes and the final report share one timestamp, so a
    # finished scan leaves exactly the files it always did.
    assert len(list(tmp_path.glob("scan_*.csv"))) == 1
    assert len(list(tmp_path.glob("scan_*.xlsx"))) == 1

    rows = list(csv.DictReader(open(next(iter(tmp_path.glob("scan_*.csv"))), encoding="utf-8")))
    assert sorted(row["IP Address"] for row in rows) == ["1.1.1.1", "8.8.8.8"]
    # Every row carries the duration of the whole pass, as it did before.
    assert len({row["Scan Duration (s)"] for row in rows}) == 1
