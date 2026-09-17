import csv
import json
import re
from types import SimpleNamespace

import pytest

from ipmg.exceptions import FileIOError
from ipmg.infrastructure.resume import load_partial_report
from ipmg.services.scan_service import run_scan
from ipmg.utils.helpers import console

HEADER = "IP Address,Status,Latency,Hostname,Open Ports,Batch Timestamp,Scan Duration (s)"
BATCH = "2026-09-17 12:00:00"


@pytest.fixture(autouse=True)
def wide_console():
    previous = console.width
    console.width = 200
    yield
    console.width = previous


def _partial_csv(tmp_path, rows, name="audit_20260917_120000.csv"):
    path = tmp_path / name
    path.write_text("\n".join([HEADER, *rows]) + "\n", encoding="utf-8")
    return path


def test_reads_back_the_hosts_a_report_already_covers(tmp_path):
    path = _partial_csv(
        tmp_path,
        [
            f'10.0.0.1,Active,1.5,\'=evil.example,"22, 80",{BATCH},1.2',
            f"10.0.0.2,Timeout,,,,{BATCH},2.4",
        ],
    )

    partial = load_partial_report(str(path))

    assert [result.ip for result in partial.results] == ["10.0.0.1", "10.0.0.2"]
    assert partial.results[0].latency == 1.5
    # The report escaped this hostname for spreadsheets; rewriting it must not
    # escape it a second time.
    assert partial.results[0].hostname == "=evil.example"
    assert partial.results[0].open_ports == (22, 80)
    assert partial.results[1].latency is None
    assert partial.fmt == "csv"


def test_a_line_cut_in_half_is_rescanned(tmp_path):
    path = _partial_csv(
        tmp_path,
        [f"10.0.0.1,Active,1.5,,,{BATCH},1.2", "10.0.0.2,Acti"],
    )

    partial = load_partial_report(str(path))

    # 10.0.0.2's row stops mid-status, so it is not a scanned host.
    assert [result.ip for result in partial.results] == ["10.0.0.1"]
    assert partial.remaining(["10.0.0.1", "10.0.0.2", "10.0.0.3"]) == ["10.0.0.2", "10.0.0.3"]


def test_rows_that_are_not_scan_results_are_ignored(tmp_path):
    path = _partial_csv(
        tmp_path,
        [
            f"not-an-ip,Active,1.0,,,{BATCH},1.0",
            f"10.0.0.9,Probably,1.0,,,{BATCH},1.0",
            f"10.0.0.1,Active,1.0,,,{BATCH},1.0",
            f"10.0.0.1,Timeout,,,,{BATCH},9.0",
        ],
    )

    partial = load_partial_report(str(path))

    # Unknown status, invalid address, and a repeat of a host already read.
    assert [result.ip for result in partial.results] == ["10.0.0.1"]
    assert partial.results[0].status == "Active"


def test_reads_jsonl_and_skips_a_truncated_line(tmp_path):
    path = tmp_path / "audit_20260917_120000.jsonl"
    rows = [
        {
            "IP Address": "10.0.0.1",
            "Status": "Active",
            "Latency": 1.5,
            "Hostname": "host.example",
            "Open Ports": "",
            "Batch Timestamp": BATCH,
            "Scan Duration (s)": 1.2,
        }
    ]
    path.write_text(json.dumps(rows[0]) + '\n{"IP Address": "10.0.0.2", "Sta', encoding="utf-8")

    partial = load_partial_report(str(path))

    assert [result.ip for result in partial.results] == ["10.0.0.1"]
    assert partial.fmt == "jsonl"


def test_resumed_report_keeps_its_own_name_and_stamp(tmp_path):
    partial = load_partial_report(str(_partial_csv(tmp_path, [])))

    assert partial.base == str(tmp_path / "audit")
    assert partial.timestamp == "20260917_120000"


def test_a_renamed_report_gets_a_fresh_stamp(tmp_path):
    partial = load_partial_report(str(_partial_csv(tmp_path, [], name="last-night.csv")))

    assert partial.base == str(tmp_path / "last-night")
    assert re.fullmatch(r"\d{8}_\d{6}", partial.timestamp)


def test_unresumable_inputs_are_rejected(tmp_path):
    xlsx = tmp_path / "audit_20260917_120000.xlsx"
    xlsx.write_bytes(b"not really a workbook")
    with pytest.raises(FileIOError, match="Cannot resume"):
        load_partial_report(str(xlsx))

    with pytest.raises(FileIOError, match="was not found"):
        load_partial_report(str(tmp_path / "missing.csv"))

    other = tmp_path / "other.csv"
    other.write_text("Address,Status\n10.0.0.1,Active\n", encoding="utf-8")
    with pytest.raises(FileIOError, match="does not look like an IPMG report"):
        load_partial_report(str(other))


def _scan_args(tmp_path, **overrides):
    args = SimpleNamespace(
        input="targets.csv",
        output=str(tmp_path / "scan"),
        timeout=1,
        count=1,
        threads=1,
        formats=None,
        discover=False,
        resolve=False,
        interval=None,
        history=False,
        compare=False,
        verbose=False,
        resume=None,
    )
    for key, value in overrides.items():
        setattr(args, key, value)
    return args


@pytest.fixture()
def stub_scan(monkeypatch):
    """Answer every ping, remembering which hosts were actually probed."""
    pinged = []

    def fake_ping(ip, _timeout, _count):
        pinged.append(ip)
        return "Active", 1.0

    monkeypatch.setattr(
        "ipmg.services.scan_service.load_targets",
        lambda _source: ["10.0.0.1", "10.0.0.2", "10.0.0.3"],
    )
    monkeypatch.setattr("ipmg.core.engine.ping_ip", fake_ping)
    return pinged


def test_resume_scans_only_the_hosts_that_are_left(tmp_path, stub_scan, capsys):
    path = _partial_csv(tmp_path, [f"10.0.0.1,Timeout,,,,{BATCH},1.0"])

    run_scan(_scan_args(tmp_path, resume=str(path)))

    assert stub_scan == ["10.0.0.2", "10.0.0.3"]
    assert "Resuming" in capsys.readouterr().out

    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    assert [row["IP Address"] for row in rows] == ["10.0.0.1", "10.0.0.2", "10.0.0.3"]
    # The carried-over host keeps the result the earlier pass recorded.
    assert rows[0]["Status"] == "Timeout"
    # Nothing was written beside the report being resumed.
    assert sorted(entry.name for entry in tmp_path.iterdir()) == [path.name]


def test_resume_adds_requested_formats_without_dropping_the_resumed_one(tmp_path, stub_scan):
    path = _partial_csv(tmp_path, [f"10.0.0.1,Active,1.0,,,{BATCH},1.0"])

    run_scan(_scan_args(tmp_path, resume=str(path), formats=["jsonl"]))

    assert (tmp_path / "audit_20260917_120000.jsonl").exists()
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    assert len(rows) == 3


def test_resume_of_a_finished_report_scans_nothing(tmp_path, stub_scan):
    path = _partial_csv(
        tmp_path,
        [
            f"10.0.0.1,Active,1.0,,,{BATCH},1.0",
            f"10.0.0.2,Active,1.0,,,{BATCH},1.0",
            f"10.0.0.3,Active,1.0,,,{BATCH},1.0",
        ],
    )

    run_scan(_scan_args(tmp_path, resume=str(path)))

    assert stub_scan == []
    assert len(list(csv.DictReader(open(path, encoding="utf-8")))) == 3


def test_repeated_passes_do_not_resume_again(tmp_path, stub_scan, monkeypatch):
    path = _partial_csv(tmp_path, [f"10.0.0.1,Active,1.0,,,{BATCH},1.0"])
    passes = {"count": 0}

    def fake_sleep(_seconds):
        passes["count"] += 1
        if passes["count"] > 1:  # pragma: no cover - guards against a loop
            raise AssertionError("scan repeated more than once")
        raise KeyboardInterrupt

    monkeypatch.setattr("ipmg.services.scan_service.time.sleep", fake_sleep)

    with pytest.raises(KeyboardInterrupt):
        run_scan(_scan_args(tmp_path, resume=str(path), interval=1))

    # First pass skipped the resumed host; the repeat would have scanned all
    # three, but it never gets there — what matters is that the resumed report
    # is no longer in play once the first pass has finished with it.
    assert stub_scan == ["10.0.0.2", "10.0.0.3"]
