from types import SimpleNamespace

import openpyxl
import pytest

from ipmg.core.health import HostsDownError
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


def test_run_scan_handles_worker_errors(tmp_path, monkeypatch):
    captured = {}

    def fake_load_all_targets(_sources):
        return ["8.8.8.8", "1.1.1.1"]

    def fake_ping_ip(ip, _timeout, _count):
        if ip == "1.1.1.1":
            raise RuntimeError("boom")
        return "Active", 10.5

    def fake_save_results(df, _base, _formats, timestamp=None):
        captured["df"] = df

    def fake_print_summary(df, batch_timestamp, duration_seconds):
        captured["summary"] = (df, batch_timestamp, duration_seconds)

    monkeypatch.setattr("ipmg.services.scan_service.load_all_targets", fake_load_all_targets)
    monkeypatch.setattr("ipmg.core.engine.ping_ip", fake_ping_ip)
    monkeypatch.setattr("ipmg.services.scan_service.save_results", fake_save_results)
    monkeypatch.setattr("ipmg.services.scan_service.print_summary", fake_print_summary)

    args = SimpleNamespace(
        input=["targets.csv"],
        output=str(tmp_path / "results"),
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

    df = captured["df"]
    statuses = dict(zip(df.column("IP Address"), df.column("Status")))
    assert statuses["8.8.8.8"] == "Active"
    assert statuses["1.1.1.1"] == "Error"
    assert len(set(df.column("Batch Timestamp"))) == 1
    assert all(duration >= 0 for duration in df.column("Scan Duration (s)"))


def test_run_scan_clamps_resource_limits(tmp_path, monkeypatch):
    captured = {}

    def fake_ping_ip(_ip, timeout, count):
        captured["limits"] = (timeout, count)
        return "Active", 1.0

    monkeypatch.setattr("ipmg.services.scan_service.load_all_targets", lambda _sources: ["8.8.8.8"])
    monkeypatch.setattr("ipmg.core.engine.ping_ip", fake_ping_ip)
    monkeypatch.setattr("ipmg.services.scan_service.save_results", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("ipmg.services.scan_service.print_summary", lambda *_args, **_kwargs: None)

    args = SimpleNamespace(
        input=["targets.csv"],
        output=str(tmp_path / "results"),
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

    assert captured["limits"] == (60, 10)


def scan_args(tmp_path, **overrides):
    args = dict(
        input=["targets.csv"],
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
        "ipmg.services.scan_service.load_all_targets",
        lambda _sources: list(state["statuses"]),
    )
    monkeypatch.setattr("ipmg.services.scan_service.save_results", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("ipmg.services.scan_service.print_summary", lambda *_args, **_kwargs: None)
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


def test_run_scan_ignores_down_hosts_without_exit_status_checks(tmp_path, stub_scan):
    stub_scan["statuses"] = {"10.0.0.1": ("Timeout", None)}

    run_scan(scan_args(tmp_path, history=False))


def test_run_scan_reports_hosts_down_after_writing_the_reports(tmp_path, stub_scan, monkeypatch):
    saved = []
    monkeypatch.setattr(
        "ipmg.services.scan_service.save_results",
        lambda df, *_args, **_kwargs: saved.append(len(df)),
    )
    stub_scan["statuses"] = {"10.0.0.1": ("Active", 1.0), "10.0.0.2": ("Timeout", None)}

    with pytest.raises(HostsDownError, match=r"^1 of 2 hosts are not active: 10\.0\.0\.2\.$"):
        run_scan(scan_args(tmp_path, fail_on_down=True))

    assert saved == [2]
    assert len(Database(tmp_path / "history.db").list_scans()) == 1


def test_run_scan_min_active_passes_above_the_threshold(tmp_path, stub_scan):
    stub_scan["statuses"] = {"10.0.0.1": ("Active", 1.0), "10.0.0.2": ("Timeout", None)}

    run_scan(scan_args(tmp_path, history=False, min_active=50.0))
    with pytest.raises(HostsDownError, match="below --min-active 60%"):
        run_scan(scan_args(tmp_path, history=False, min_active=60.0))


def test_run_scan_keeps_repeating_when_hosts_are_down(tmp_path, stub_scan, monkeypatch, capsys):
    passes = []

    def fake_sleep(_seconds):
        passes.append(1)
        if len(passes) == 2:
            raise KeyboardInterrupt

    monkeypatch.setattr("ipmg.services.scan_service.time.sleep", fake_sleep)
    stub_scan["statuses"] = {"10.0.0.1": ("Timeout", None)}

    with pytest.raises(KeyboardInterrupt):
        run_scan(scan_args(tmp_path, history=False, interval=1, fail_on_down=True))

    assert capsys.readouterr().out.count("hosts are not active") == 2


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


@pytest.fixture()
def captured_posts(monkeypatch):
    """Record every webhook post instead of sending it."""
    posts = []
    monkeypatch.setattr(
        "ipmg.infrastructure.notify.post_json", lambda url, payload: posts.append((url, payload))
    )
    return posts


def test_run_scan_notification_implies_compare(tmp_path, stub_scan, captured_posts, capsys):
    stub_scan["statuses"] = {"10.0.0.1": ("Active", 5.0)}
    run_scan(scan_args(tmp_path))

    stub_scan["statuses"] = {"10.0.0.1": ("Timeout", None)}
    run_scan(scan_args(tmp_path, notify_webhook="https://example.test/hook"))

    assert "Host offline" in capsys.readouterr().out
    [(url, payload)] = captured_posts
    assert url == "https://example.test/hook"
    assert payload["changes"][0]["type"] == "host_offline"


def test_run_scan_notifies_on_every_interval_pass_that_changes(
    tmp_path, stub_scan, captured_posts, monkeypatch
):
    timeline = [
        {"10.0.0.1": ("Active", 5.0)},
        {"10.0.0.1": ("Timeout", None)},
        {"10.0.0.1": ("Timeout", None)},
        {"10.0.0.1": ("Timeout", None), "10.0.0.2": ("Active", 1.0)},
    ]
    stub_scan["statuses"] = timeline.pop(0)

    def next_pass(_seconds):
        if not timeline:
            raise KeyboardInterrupt
        stub_scan["statuses"] = timeline.pop(0)

    monkeypatch.setattr("ipmg.services.scan_service.time.sleep", next_pass)

    with pytest.raises(KeyboardInterrupt):
        run_scan(scan_args(tmp_path, interval=1, notify_slack="https://example.test/slack"))

    # Pass 1 has no baseline and pass 3 changed nothing, so only 2 and 4 alert.
    headlines = [payload["text"] for _url, payload in captured_posts]
    assert headlines == [
        "IPMG: 1 change (1 critical) in targets.csv",
        "IPMG: 1 change (1 warning) in targets.csv",
    ]


def test_run_scan_keeps_its_results_when_a_notification_fails(
    tmp_path, stub_scan, monkeypatch, capsys
):
    def refuse(_url, _payload):
        raise OSError("connection refused")

    saved = []
    monkeypatch.setattr("ipmg.infrastructure.notify.post_json", refuse)
    monkeypatch.setattr(
        "ipmg.services.scan_service.save_results", lambda df, *_a, **_k: saved.append(len(df))
    )
    stub_scan["statuses"] = {"10.0.0.1": ("Active", 5.0)}
    run_scan(scan_args(tmp_path))

    stub_scan["statuses"] = {"10.0.0.1": ("Timeout", None)}
    run_scan(
        scan_args(
            tmp_path,
            notify_webhook="https://example.test/hook",
            diff_formats=["md"],
        )
    )

    assert "Webhook notification failed: connection refused" in capsys.readouterr().out
    assert saved == [1, 1]
    assert len(Database(tmp_path / "history.db").list_scans()) == 2
    assert list(tmp_path.glob("changes_*.md"))


def test_run_scan_rejects_notification_settings_before_scanning(tmp_path, monkeypatch):
    from ipmg.exceptions import NotifyError

    pinged = record_pings(monkeypatch)
    monkeypatch.delenv("IPMG_NOTIFY_SLACK", raising=False)

    with pytest.raises(NotifyError, match="IPMG_NOTIFY_SLACK"):
        run_scan(scan_args(tmp_path, notify_slack=""))

    assert pinged == []


def test_run_scan_streams_each_host_as_it_finishes(tmp_path, stub_scan, capsys):
    stub_scan["statuses"] = {
        "10.0.0.1": ("Active", 1.0),
        "10.0.0.2": ("Timeout", None),
    }

    run_scan(scan_args(tmp_path, history=False, stream=True, stream_all=True))

    out = capsys.readouterr().out
    assert "Live" in out
    assert "10.0.0.1" in out
    assert "10.0.0.2" in out


def test_run_scan_without_streaming_prints_no_per_host_rows(tmp_path, stub_scan, capsys):
    stub_scan["statuses"] = {"10.0.0.1": ("Active", 1.0)}

    run_scan(scan_args(tmp_path, history=False))

    assert "10.0.0.1" not in capsys.readouterr().out


def record_pings(monkeypatch):
    """Answer every ping and remember which hosts were probed."""
    pinged = []

    def fake_ping(ip, _timeout, _count):
        pinged.append(ip)
        return "Active", 1.0

    monkeypatch.setattr("ipmg.core.engine.ping_ip", fake_ping)
    monkeypatch.setattr("ipmg.services.scan_service.save_results", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("ipmg.services.scan_service.print_summary", lambda *_args, **_kwargs: None)
    return pinged


def test_run_scan_rejects_a_missing_input_file_instead_of_creating_it(tmp_path, monkeypatch):
    from ipmg.exceptions import FileIOError

    pinged = record_pings(monkeypatch)
    missing = tmp_path / "targts.txt"

    with pytest.raises(FileIOError, match="was not found"):
        run_scan(scan_args(tmp_path, input=[str(missing)], history=False))

    # A typo used to create this file with sample public addresses and scan them.
    assert not missing.exists()
    assert pinged == []


def test_run_scan_without_input_creates_the_default_sample_file(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    pinged = record_pings(monkeypatch)
    args = scan_args(tmp_path, input=None, history=False)

    run_scan(args)

    assert args.input == ["ip_list.xlsx"]
    assert (tmp_path / "ip_list.xlsx").exists()
    assert sorted(pinged) == ["1.1.1.1", "8.8.8.8"]
    assert "Created ip_list.xlsx" in capsys.readouterr().out


def test_run_scan_without_input_reuses_an_existing_default_file(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    workbook = openpyxl.Workbook()
    workbook.active.append(["IP Address"])
    workbook.active.append(["10.0.0.1"])
    workbook.save(tmp_path / "ip_list.xlsx")
    pinged = record_pings(monkeypatch)

    run_scan(scan_args(tmp_path, input=None, history=False))

    assert pinged == ["10.0.0.1"]
    assert "Created" not in capsys.readouterr().out


def test_run_scan_merges_a_file_with_extra_cli_targets(tmp_path, monkeypatch, capsys):
    """A file and loose targets in one run: the union, de-duplicated."""
    pinged = record_pings(monkeypatch)
    path = tmp_path / "targets.txt"
    path.write_text("10.0.0.1\n10.0.0.2\n", encoding="utf-8")
    sources = [str(path), "10.0.0.0/30", "10.0.0.5"]

    run_scan(scan_args(tmp_path, input=sources, history=False))

    assert sorted(pinged) == ["10.0.0.1", "10.0.0.2", "10.0.0.5"]


def test_run_scan_header_lists_every_source(tmp_path, monkeypatch, capsys):
    record_pings(monkeypatch)

    run_scan(scan_args(tmp_path, input=["10.0.0.1", "10.0.0.5"], history=False))

    out = capsys.readouterr().out
    assert "Source" in out
    assert "10.0.0.1" in out
    assert "10.0.0.5" in out


def test_run_scan_records_every_source_in_history(tmp_path, monkeypatch):
    """The stored source names both, so the next run compares against it."""
    record_pings(monkeypatch)
    db = str(tmp_path / "history.db")

    run_scan(scan_args(tmp_path, input=["10.0.0.1", "10.0.0.5"], db=db))

    stored = Database(db).list_scans(limit=1)
    assert stored[0]["source"] == "10.0.0.1, 10.0.0.5"
