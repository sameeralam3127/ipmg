import socket
import sqlite3

import pytest

from ipmg.core import portscan
from ipmg.core.engine import HostResult, ScanConfig, execute_scan
from ipmg.core.portscan import connect, tcp_probe
from ipmg.infrastructure.database import Database
from ipmg.infrastructure.file_io import render_report
from ipmg.infrastructure.incremental import IncrementalReport, load_partial_report
from ipmg.reporting.frames import RESULT_COLUMNS, report_columns, results_table


@pytest.fixture()
def listening_port():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(8)
    yield server.getsockname()[1]
    server.close()


@pytest.fixture()
def closed_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


# ------------------------------------------------------------- connections


def test_an_accepted_connection_is_open_with_a_time(listening_port):
    outcome, latency = connect("127.0.0.1", listening_port, 1.0)

    assert outcome == portscan.OPEN
    assert latency is not None and latency >= 0


def test_a_refused_connection_still_answered(closed_port):
    outcome, latency = connect("127.0.0.1", closed_port, 1.0)

    assert outcome == portscan.REFUSED
    assert latency is not None


def test_tcp_probe_counts_a_refusal_as_up(closed_port):
    # A reset is an answer: the host is there, the service is not.
    assert tcp_probe("127.0.0.1", [closed_port], 1.0)[0] == "Active"


def test_tcp_probe_is_up_if_any_port_answers(monkeypatch):
    outcomes = {22: (portscan.TIMED_OUT, None), 443: (portscan.OPEN, 4.2)}
    monkeypatch.setattr(portscan, "connect", lambda _ip, port, _t: outcomes[port])

    assert tcp_probe("10.0.0.1", [22, 443], 1.0) == ("Active", 4.2)


def test_tcp_probe_reports_timeouts_and_unreachable_hosts(monkeypatch):
    monkeypatch.setattr(portscan, "connect", lambda *_a: (portscan.TIMED_OUT, None))
    assert tcp_probe("10.0.0.1", [22, 80], 1.0) == ("Timeout", None)

    outcomes = {22: (portscan.TIMED_OUT, None), 80: (portscan.UNREACHABLE, None)}
    monkeypatch.setattr(portscan, "connect", lambda _ip, port, _t: outcomes[port])
    assert tcp_probe("10.0.0.1", [22, 80], 1.0) == ("Unreachable", None)


# ----------------------------------------------------------------- engine


@pytest.fixture()
def scripted(monkeypatch):
    """Script ping and TCP answers per IP, and record which were tried."""
    state = {"ping": {}, "tcp": {}, "pinged": [], "connected": []}

    def fake_ping(ip, _timeout, _count):
        state["pinged"].append(ip)
        return state["ping"].get(ip, ("Timeout", None))

    def fake_tcp(ip, _ports, _timeout, _executor=None):
        state["connected"].append(ip)
        return state["tcp"].get(ip, ("Timeout", None))

    monkeypatch.setattr("ipmg.core.engine.ping_ip", fake_ping)
    monkeypatch.setattr("ipmg.core.engine.tcp_probe", fake_tcp)
    return state


def by_ip(results):
    return {result.ip: result for result in results}


def test_default_probe_is_icmp_only(scripted):
    scripted["ping"]["10.0.0.1"] = ("Active", 1.0)

    results = by_ip(execute_scan(["10.0.0.1", "10.0.0.2"], ScanConfig(threads=2)))

    assert scripted["connected"] == []
    assert results["10.0.0.1"] == HostResult("10.0.0.1", "Active", 1.0)
    assert results["10.0.0.2"].status == "Timeout"


def test_icmp_then_tcp_falls_back_only_for_hosts_that_did_not_answer(scripted):
    scripted["ping"]["10.0.0.1"] = ("Active", 1.0)
    scripted["tcp"]["10.0.0.2"] = ("Active", 7.5)
    scripted["ping"]["10.0.0.3"] = ("Unreachable", None)

    results = by_ip(
        execute_scan(["10.0.0.1", "10.0.0.2", "10.0.0.3"], ScanConfig(threads=3, probe="icmp,tcp"))
    )

    assert sorted(scripted["connected"]) == ["10.0.0.2", "10.0.0.3"]
    assert (results["10.0.0.1"].status, results["10.0.0.1"].method) == ("Active", "icmp")
    assert (results["10.0.0.2"].status, results["10.0.0.2"].method) == ("Active", "tcp")
    assert results["10.0.0.2"].latency == 7.5
    # Neither answered: ping's verdict stands.
    assert (results["10.0.0.3"].status, results["10.0.0.3"].method) == ("Unreachable", "")


def test_tcp_only_never_pings(scripted):
    scripted["tcp"]["10.0.0.1"] = ("Active", 2.0)

    results = by_ip(execute_scan(["10.0.0.1", "10.0.0.2", "bogus"], ScanConfig(probe="tcp")))

    assert scripted["pinged"] == []
    assert (results["10.0.0.1"].status, results["10.0.0.1"].method) == ("Active", "tcp")
    assert results["10.0.0.2"].status == "Timeout"
    assert results["bogus"].status == "Invalid IP"


def test_tcp_probe_finds_a_real_listener(listening_port):
    results = execute_scan(
        ["127.0.0.1"], ScanConfig(probe="tcp", ports=(listening_port,), port_timeout=1.0)
    )

    assert (results[0].status, results[0].method) == ("Active", "tcp")


def test_an_unknown_probe_method_falls_back_to_icmp():
    assert ScanConfig(probe="udp").clamped().probe == "icmp"


# ----------------------------------------------------------------- reports


def test_a_default_scan_report_has_exactly_the_old_columns():
    assert report_columns(ScanConfig()) == tuple(RESULT_COLUMNS)
    assert report_columns({}) == tuple(RESULT_COLUMNS)


def test_tcp_probing_adds_a_probe_column_after_open_ports():
    columns = report_columns(ScanConfig(probe="icmp,tcp"))

    assert columns[columns.index("Open Ports") + 1] == "Probe"
    assert report_columns({"probe": "tcp"}) == columns


def test_the_probe_column_reaches_every_format(tmp_path):
    results = [HostResult("10.0.0.1", "Active", 2.0, method="tcp")]
    columns = report_columns(ScanConfig(probe="tcp"))
    table = results_table(results, "2026-10-17 12:00:00", 1.0, columns)

    csv_text = render_report(table, "csv").decode()
    assert csv_text.splitlines()[0].split(",")[5] == "Probe"
    assert ",tcp," in csv_text.splitlines()[1]
    assert '"Probe": "tcp"' in render_report(table, "jsonl").decode()


def test_incremental_csv_and_resume_carry_the_probe(tmp_path):
    columns = report_columns(ScanConfig(probe="tcp"))
    report = IncrementalReport(
        base=str(tmp_path / "results"),
        formats=["csv"],
        timestamp="20261017_120000",
        batch_timestamp="2026-10-17 12:00:00",
        columns=columns,
    )
    with report:
        report.record(HostResult("10.0.0.1", "Active", 2.0, method="tcp"))

    path = tmp_path / "results_20261017_120000.csv"
    assert path.read_text().splitlines()[0] == ",".join(columns)
    [resumed] = load_partial_report(str(path)).results
    assert resumed.method == "tcp"


# ---------------------------------------------------------------- history


def test_the_probe_method_is_stored_with_each_result(tmp_path):
    db = Database(tmp_path / "h.db")
    scan_id = db.record_scan("x", [HostResult("10.0.0.1", "Active", 1.0, method="tcp")], {}, 1.0)

    assert db.get_results(scan_id)[0]["method"] == "tcp"


def test_an_older_database_gains_the_method_column(tmp_path):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:
        conn.executescript(
            "CREATE TABLE scans (id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT NOT NULL,"
            " finished_at TEXT, duration_s REAL, source TEXT NOT NULL,"
            " total INTEGER NOT NULL DEFAULT 0, completed INTEGER NOT NULL DEFAULT 0,"
            " status TEXT NOT NULL DEFAULT 'running', config TEXT NOT NULL DEFAULT '{}',"
            " error TEXT);"
            "CREATE TABLE results (scan_id INTEGER NOT NULL, ip TEXT NOT NULL,"
            " status TEXT NOT NULL, latency REAL, hostname TEXT NOT NULL DEFAULT '',"
            " open_ports TEXT NOT NULL DEFAULT '', checked_at TEXT NOT NULL);"
            "INSERT INTO scans (started_at, source, status) VALUES ('2026-01-01 00:00:00', 'x',"
            " 'complete');"
            "INSERT INTO results VALUES (1, '10.0.0.1', 'Active', 1.0, '', '', '2026-01-01');"
        )

    db = Database(path)

    assert db.get_results(1)[0]["method"] == ""


@pytest.mark.parametrize(
    "argv, notice",
    [
        ([], "ICMP probes only"),
        (["--probe", "icmp,tcp"], "ICMP and TCP connect probes only"),
        (["--probe", "tcp"], "TCP connect probes only"),
        (["--scan-ports"], "ICMP and TCP connect probes only"),
    ],
)
def test_the_authorization_notice_names_what_the_scan_sends(argv, notice, monkeypatch, capsys):
    from ipmg.cli import commands
    from ipmg.core import security

    monkeypatch.setattr(security, "_DISCLAIMER_SHOWN", False)
    monkeypatch.setattr("ipmg.cli.commands.run_scan", lambda _args: None)

    assert commands.run(["--input", "127.0.0.1", "--no-config", *argv]) == 0
    assert notice in capsys.readouterr().out
