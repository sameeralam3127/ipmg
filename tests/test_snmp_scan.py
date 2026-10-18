"""``--snmp`` in a scan: settings, credentials, history, change detection, reports, and the web."""

import csv
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from scan_helpers import scan_args
from snmp_agent import Agent, User, switch_mib

from ipmg.cli import config
from ipmg.cli.commands import _probe_kinds
from ipmg.cli.parser import build_parser
from ipmg.core.diff import (
    UPTIME_WRAP_S,
    ChangeType,
    HostSnapshot,
    InterfaceSnapshot,
    Severity,
    SnmpSnapshot,
    compare_snapshots,
    format_uptime,
)
from ipmg.core.snmp import SnmpInterface, SnmpResult
from ipmg.exceptions import ConfigError
from ipmg.infrastructure.database import Database
from ipmg.infrastructure.file_io import save_snmp_results, snmp_results_table
from ipmg.reporting import ui
from ipmg.reporting.summary import print_snmp
from ipmg.services import snmp_settings
from ipmg.services.history_service import HistoryService
from ipmg.services.scan_service import run_scan
from ipmg.web.app import create_app

TOKEN = "snmp-test-token-0123456789"
#: Test passphrases, for the fake agent only.
AUTH_SECRET = "authsecret1"  # pragma: allowlist secret
PRIV_SECRET = "privsecret1"  # pragma: allowlist secret


def snmp_args(tmp_path, agent=None, **overrides):
    settings = dict(
        snmp=True,
        snmp_version="2c",
        snmp_port=agent.port if agent else 161,
        snmp_timeout=0.5,
        snmp_retries=0,
        snmp_no_interfaces=False,
        snmp_credentials={},
        formats=["csv", "md"],
    )
    settings.update(overrides)
    return scan_args(tmp_path, **settings)


# ----------------------------------------------------------------- settings


def test_the_environment_wins_over_the_config_file():
    values, origins = snmp_settings.credential_values(
        {"community": "from-file", "user": "ops", "auth-protocol": "sha-256"},
        {"IPMG_SNMP_COMMUNITY": "from-env", "IPMG_SNMP_PRIV_PROTOCOL": "aes128"},
    )

    assert values == {
        "community": "from-env",
        "user": "ops",
        "auth_protocol": "SHA256",
        "priv_protocol": "AES",
    }
    assert origins["community"] == "environment" and origins["user"] == "config file"


@pytest.mark.parametrize(
    "table, message",
    [({"password": "x"}, "Unknown key"), ({"community": 7}, "must be a string")],
)
def test_bad_credential_tables_are_refused(table, message):
    with pytest.raises(ConfigError, match=message):
        snmp_settings.credential_values(table, {})


def test_no_options_without_snmp():
    assert snmp_settings.snmp_options(scan_args(Path("."))) is None


def test_v2c_defaults_to_public_and_says_so():
    args = snmp_args(Path("."), snmp_timeout=500, snmp_retries=9)
    snmp = snmp_settings.snmp_options(args, environ={})

    assert snmp.credentials.community == "public"
    assert (snmp.timeout_s, snmp.retries) == (60.0, 5)  # clamped
    assert snmp_settings.describe_credentials(args, environ={}) == "community public"
    env = {"IPMG_SNMP_COMMUNITY": "s3cret-community"}
    assert snmp_settings.describe_credentials(args, environ=env) == (
        "community from the environment"
    )


def test_v3_without_a_user_fails_before_any_scan(tmp_path, stub_scan):
    stub_scan["statuses"] = {"127.0.0.1": ("Active", 1.0)}
    args = snmp_args(tmp_path, snmp_version="3")

    with pytest.raises(ConfigError, match="IPMG_SNMP_USER"):
        run_scan(args)
    assert not Path(args.db).exists()


def test_v3_description_names_the_level_and_never_a_key():
    args = snmp_args(Path("."), snmp_version="3")
    env = {
        "IPMG_SNMP_USER": "netops",
        "IPMG_SNMP_AUTH_KEY": AUTH_SECRET,
        "IPMG_SNMP_PRIV_KEY": PRIV_SECRET,
        "IPMG_SNMP_CONTEXT": "vrf-blue",
    }

    text = snmp_settings.describe_credentials(args, environ=env)
    assert text == "user netops, authPriv (SHA, AES), context vrf-blue"
    assert "secret" not in text
    env.pop("IPMG_SNMP_PRIV_KEY")
    assert "authNoPriv (SHA)" in snmp_settings.describe_credentials(args, environ=env)
    env.pop("IPMG_SNMP_AUTH_KEY")
    assert "noAuthNoPriv" in snmp_settings.describe_credentials(args, environ=env)


# ------------------------------------------------------------ flags and file


def parse(argv):
    parser = build_parser()
    config.apply(parser, build_parser, argv)
    return parser.parse_args(argv)


def write_user_config(tmp_path, text):
    path = tmp_path / "xdg" / "ipmg" / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_flags_have_safe_defaults_and_bounds(capsys):
    args = parse(["--snmp"])
    assert (args.snmp_version, args.snmp_port, args.snmp_timeout, args.snmp_retries) == (
        "2c",
        161,
        2.0,
        1,
    )
    for bad in (["--snmp-port", "0"], ["--snmp-port", "70000"], ["--snmp-retries", "6"]):
        with pytest.raises(SystemExit):
            parse(bad)
    assert "--snmp-retries" in capsys.readouterr().err


def test_credentials_come_from_the_user_config_table(tmp_path):
    write_user_config(
        tmp_path,
        'snmp = true\nsnmp-version = "3"\n\n[snmp-credentials]\nuser = "netops"\n'
        f'auth-key = "{AUTH_SECRET}"\n',
    )

    args = parse([])
    assert args.snmp and args.snmp_version == "3"
    assert args.snmp_credentials == {"user": "netops", "auth-key": AUTH_SECRET}
    assert snmp_settings.snmp_options(args, environ={}).credentials.user == "netops"


def test_a_project_file_may_not_hold_credentials(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "ipmg.toml").write_text('[snmp-credentials]\ncommunity = "x"\n')

    with pytest.raises(ConfigError, match="keep credentials out of a project file"):
        parse([])
    # A file named with --config is the user's own choice.
    assert parse(["--config", "ipmg.toml"]).snmp_credentials == {"community": "x"}


def test_the_credentials_table_must_be_a_table(tmp_path):
    write_user_config(tmp_path, 'snmp-credentials = "public"\n')
    with pytest.raises(ConfigError, match="must be a table"):
        parse([])


def test_the_notice_names_snmp():
    assert "SNMP" in _probe_kinds(snmp_args(Path(".")))
    assert "SNMP" not in _probe_kinds(scan_args(Path(".")))


# ---------------------------------------------------------------- comparing


def device(ip="10.0.0.1", ok=True, uptime=86400.0, polled_at="2026-10-18 10:00:00", **kw):
    interfaces = kw.pop(
        "interfaces",
        (
            InterfaceSnapshot("Gi1", "Uplink", "up", "up"),
            InterfaceSnapshot("Gi2", "", "up", "up"),
            InterfaceSnapshot("Gi3", "", "down", "down"),
        ),
    )
    return SnmpSnapshot(
        ip=ip, ok=ok, uptime_s=uptime, polled_at=polled_at, interfaces=interfaces, **kw
    )


def changes(before, after, hosts=()):
    diff = compare_snapshots(hosts, hosts, baseline_snmp=[before], current_snmp=[after])
    return [(change.type, change.describe(), change.severity) for change in diff.changes]


def test_an_uptime_that_starts_again_is_a_reboot():
    found = changes(
        device(uptime=90 * 86400.0), device(uptime=120.0, polled_at="2026-10-18 11:00:00")
    )
    assert found == [
        (ChangeType.DEVICE_REBOOTED, "Device rebooted: up 90d 0h -> up 2m", Severity.WARNING)
    ]


def test_the_497_day_wrap_is_not_a_reboot():
    before = device(uptime=UPTIME_WRAP_S - 600)
    after = device(uptime=3000.0, polled_at="2026-10-18 11:00:00")
    assert changes(before, after) == []


def test_interfaces_going_down_and_coming_back_are_changes():
    down = device(
        polled_at="2026-10-18 11:00:00",
        uptime=90000.0,
        interfaces=(
            InterfaceSnapshot("Gi1", "Uplink", "up", "lowerLayerDown"),
            InterfaceSnapshot("Gi2", "", "up", "up"),
            # Switched off: never reported.
            InterfaceSnapshot("Gi3", "", "down", "down"),
            # Only in this scan: nothing to compare.
            InterfaceSnapshot("Gi4", "", "up", "down"),
        ),
    )

    assert changes(device(), down) == [
        (ChangeType.INTERFACE_DOWN, "Interface down: Gi1 (Uplink)", Severity.WARNING)
    ]
    assert changes(down, device(uptime=99999.0, polled_at="2026-10-18 12:00:00")) == [
        (ChangeType.INTERFACE_UP, "Interface back up: Gi1 (Uplink)", Severity.INFO)
    ]


def test_an_agent_that_stops_and_starts_answering_is_a_change():
    silent = device(ok=False, uptime=None, failure="timeout", interfaces=())

    assert changes(device(), silent) == [
        (ChangeType.SNMP_FAILING, "SNMP not answering: timeout", Severity.WARNING)
    ]
    assert changes(silent, device()) == [
        (ChangeType.SNMP_RECOVERED, "SNMP answering again: was timeout", Severity.INFO)
    ]
    assert changes(silent, silent) == []


def test_a_device_polled_once_has_nothing_to_compare():
    diff = compare_snapshots(
        [],
        [],
        baseline_snmp=[device(ip="10.0.0.1")],
        current_snmp=[device(ip="10.0.0.2", ok=False)],
    )
    assert diff.changes == ()


def test_changes_name_the_host_or_else_the_device():
    hosts = [HostSnapshot("10.0.0.1", "Active", hostname="core-sw.example")]
    silent = device(ok=False, failure="auth", sys_name="sw-from-snmp", interfaces=())
    diff = compare_snapshots(hosts, hosts, baseline_snmp=[device()], current_snmp=[silent])
    assert diff.changes[0].hostname == "core-sw.example"

    diff = compare_snapshots([], [], baseline_snmp=[device()], current_snmp=[silent])
    assert diff.changes[0].hostname == "sw-from-snmp"
    assert diff.changed_hosts == 1


@pytest.mark.parametrize(
    "seconds, text",
    [
        (None, "-"),
        (45, "45s"),
        (720, "12m"),
        (5 * 3600 + 720, "5h 12m"),
        (41 * 86400 + 3 * 3600, "41d 3h"),
    ],
)
def test_uptimes_read_at_a_glance(seconds, text):
    assert format_uptime(seconds) == text


# ------------------------------------------------------------------ storing


def snmp_result(ip="10.0.0.1", ok=True, name="core-sw", uptime=3600.0, oper="up", **kw):
    return SnmpResult(
        ip=ip,
        ok=ok,
        sys_name=name if ok else "",
        sys_descr="Switch OS 1.0" if ok else "",
        uptime_s=uptime if ok else None,
        interfaces=(
            SnmpInterface(1, "Gi1", "GigabitEthernet1", "Uplink", "up", oper, 1000, 2**64 - 1, 5),
            SnmpInterface(2, "Gi2", admin_status="down", oper_status="down"),
        )
        if ok
        else (),
        failure="" if ok else "timeout",
        error="" if ok else "no SNMP answer",
        **kw,
    )


def test_polls_are_stored_with_their_interfaces_and_removed_with_their_scan(tmp_path):
    database = Database(tmp_path / "history.db")
    scan_id = database.record_scan(
        "lab", [], {}, 1.0, snmp_devices=[snmp_result(), snmp_result(ip="10.0.0.2", ok=False)]
    )

    first, second = database.get_snmp_devices(scan_id)
    assert (first["ok"], first["sys_name"], first["uptime_s"]) == (True, "core-sw", 3600.0)
    uplink = first["interfaces"][0]
    assert (uplink["name"], uplink["alias"], uplink["speed_mbps"]) == ("Gi1", "Uplink", 1000)
    # Above SQLite's signed 64 bits: unknown rather than an error.
    assert (uplink["in_octets"], uplink["out_octets"]) == (None, 5)
    assert (second["ok"], second["failure"], second["interfaces"]) == (False, "timeout", [])

    [snapshot, _second] = database.snmp_snapshot(scan_id)
    assert snapshot.interfaces[0] == InterfaceSnapshot("Gi1", "Uplink", "up", "up")

    assert database.delete_scan(scan_id)
    assert database.get_snmp_devices(scan_id) == []


def test_an_older_history_database_gains_the_snmp_tables(tmp_path):
    import sqlite3

    path = tmp_path / "old.db"
    Database(path)
    with sqlite3.connect(path) as conn:
        # A 4.0 database: everything but the SNMP tables.
        conn.execute("DROP TABLE snmp_interfaces")
        conn.execute("DROP TABLE snmp_devices")

    database = Database(path)
    scan_id = database.record_scan("lab", [], {}, 1.0, snmp_devices=[snmp_result()])
    assert database.get_snmp_devices(scan_id)[0]["sys_name"] == "core-sw"


def test_the_inventory_shows_the_latest_snmp_name(tmp_path, stub_scan):
    stub_scan["statuses"] = {"127.0.0.1": ("Active", 1.0)}
    with Agent(mib=switch_mib(name="first-name")) as agent:
        run_scan(snmp_args(tmp_path, agent, formats=[]))
    with Agent(mib=switch_mib(name="second-name")) as agent:
        run_scan(snmp_args(tmp_path, agent, formats=[]))

    [asset] = Database(tmp_path / "history.db").inventory()
    assert (asset["snmp_name"], asset["snmp_descr"]) == (
        "second-name",
        "second-name software\r\nline two",
    )


def test_history_compares_polls(tmp_path):
    history = HistoryService(Database(tmp_path / "history.db"))
    first = history.record_scan("lab", [], _config(), 1.0, snmp_devices=[snmp_result(uptime=9e5)])
    second = history.record_scan(
        "lab", [], _config(), 1.0, snmp_devices=[snmp_result(uptime=60.0, oper="down")]
    )

    diff = history.compare(first, second)
    assert [change.type for change in diff.changes] == [
        ChangeType.DEVICE_REBOOTED,
        ChangeType.INTERFACE_DOWN,
    ]


def _config():
    from ipmg.core.engine import ScanConfig

    return ScanConfig(timeout=1, count=1, threads=1, resolve=False)


# ------------------------------------------------------------- a whole scan


def test_a_scan_polls_the_hosts_that_answered(tmp_path, stub_scan, monkeypatch, capsys):
    stub_scan["statuses"] = {"127.0.0.1": ("Active", 1.0), "192.0.2.9": ("Timeout", None)}
    monkeypatch.setenv("IPMG_SNMP_COMMUNITY", "lab-community")
    with Agent(community="lab-community") as agent:
        run_scan(snmp_args(tmp_path, agent))
        polled = agent.received

    # The console wraps long lines; compare the words, not the layout.
    out = " ".join(capsys.readouterr().out.split())
    assert "SNMP" in out and "community from the environment" in out
    assert "lab-community" not in out
    assert "lab-switch" in out and f"1 up {ui.glyph('sep')} 1 down" in out
    assert "down: Gi1/0/2" in out
    assert polled >= 2  # the system group, then the interface walk

    [devices_csv] = tmp_path.glob("results_snmp_2*.csv")
    [interfaces_csv] = tmp_path.glob("results_snmp_interfaces_*.csv")
    [devices_md] = tmp_path.glob("results_snmp_2*.md")
    assert not list(tmp_path.glob("results_snmp_interfaces_*.md"))
    with devices_csv.open(newline="") as handle:
        header, row = csv.reader(handle)
    assert header[:7] == ["IP", "Result", "Name", "Description", "Location", "Uptime", "Uptime (s)"]
    assert row[:4] == ["127.0.0.1", "OK", "lab-switch", "lab-switch software\r\nline two"]
    assert len(interfaces_csv.read_text().splitlines()) == 4
    markdown = devices_md.read_text()
    assert "# IPMG SNMP Report" in markdown and "## Interfaces down" in markdown

    [scan] = Database(tmp_path / "history.db").list_scans()
    [stored] = Database(tmp_path / "history.db").get_snmp_devices(scan["id"])
    assert stored["ip"] == "127.0.0.1" and len(stored["interfaces"]) == 3
    assert "lab-community" not in str(scan["config"])


def test_no_answering_host_means_no_poll(tmp_path, stub_scan, capsys):
    stub_scan["statuses"] = {"192.0.2.9": ("Timeout", None)}
    run_scan(snmp_args(tmp_path))

    assert "no host answered, so none was polled" in capsys.readouterr().out
    assert not list(tmp_path.glob("results_snmp_*"))


def test_old_snmp_reports_are_pruned_with_the_rest(tmp_path, stub_scan):
    stub_scan["statuses"] = {"127.0.0.1": ("Active", 1.0)}
    for stamp in ("20260101_000000", "20260102_000000"):
        for name in (f"results_snmp_{stamp}.csv", f"results_snmp_interfaces_{stamp}.csv"):
            (tmp_path / name).write_text("old")
    with Agent() as agent:
        run_scan(snmp_args(tmp_path, agent, formats=["csv"], keep_reports=1))

    assert len(list(tmp_path.glob("results_snmp_2*.csv"))) == 1
    assert len(list(tmp_path.glob("results_snmp_interfaces_*.csv"))) == 1


def test_a_v3_scan_end_to_end(tmp_path, stub_scan, monkeypatch, capsys):
    stub_scan["statuses"] = {"127.0.0.1": ("Active", 1.0)}
    monkeypatch.setenv("IPMG_SNMP_AUTH_KEY", AUTH_SECRET)
    monkeypatch.setenv("IPMG_SNMP_PRIV_KEY", PRIV_SECRET)
    users = {"netops": User("SHA", AUTH_SECRET, PRIV_SECRET)}
    with Agent(users=users) as agent:
        run_scan(snmp_args(tmp_path, agent, snmp_version="3", snmp_credentials={"user": "netops"}))

    # The console wraps long lines; compare the words, not the layout.
    out = " ".join(capsys.readouterr().out.split())
    assert "v3" in out and "user netops, authPriv (SHA, AES)" in out
    assert "secret1" not in out
    assert "lab-switch" in out


def test_an_snmp_report_lists_failures_and_down_interfaces(tmp_path):
    results = [snmp_result(oper="down"), snmp_result(ip="10.0.0.2", ok=False)]
    saved = save_snmp_results(
        results, str(tmp_path / "r_snmp"), ["md", "json", "xlsx"], "2026-10-18 10:00"
    )

    assert {Path(path).name.split("_2")[0] for path in saved} == {"r_snmp", "r_snmp_interfaces"}
    table = snmp_results_table(results, "now")
    assert table.rows[0]["Down Interfaces"] == "Gi1"
    assert table.rows[1]["Result"] == "Failed" and table.rows[1]["Uptime"] == ""
    markdown = Path(next(path for path in saved if path.endswith(".md"))).read_text()
    assert "| Failed | 10.0.0.2 |" in markdown and "no SNMP answer" in markdown


def test_the_summary_keeps_long_descriptions_short(capsys):
    long = replace(snmp_result(), sys_descr="Very long vendor description " * 10)
    print_snmp([long, snmp_result(ip="10.0.0.2", ok=False)])

    # The console wraps long lines; compare the words, not the layout.
    out = " ".join(capsys.readouterr().out.split())
    assert "1 not answering" in out and "2 devices" in out
    assert "Very long vendor description " * 3 not in out


def test_snmp_code_is_only_loaded_for_snmp(tmp_path):
    program = (
        "import sys\n"
        "from ipmg.cli.commands import run\n"
        "from ipmg.services import scan_service\n"
        "run(['--no-config', '--input', '127.0.0.1', '--timeout', '1', '--no-history',\n"
        f"     '--formats', 'csv', '--output', {str(tmp_path / 'r')!r}])\n"
        "assert 'ipmg.core.snmp' not in sys.modules, 'SNMP was imported'\n"
    )
    environment = {**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")}
    completed = subprocess.run(
        [sys.executable, "-c", program], capture_output=True, text=True, env=environment
    )
    assert completed.returncode == 0, completed.stderr[-2000:]


# --------------------------------------------------------------------- web


def test_the_web_api_serves_a_scan_s_polls(tmp_path):
    database = Database(tmp_path / "history.db")
    scan_id = database.record_scan("lab", [], {}, 1.0, snmp_devices=[snmp_result()])
    headers = {"Authorization": f"Bearer {TOKEN}"}

    with TestClient(create_app(database, token=TOKEN), headers=headers) as client:
        [polled] = client.get(f"/api/v1/scans/{scan_id}/snmp").json()
        missing = client.get("/api/v1/scans/999/snmp")
    assert polled["sys_name"] == "core-sw" and polled["interfaces"][0]["alias"] == "Uplink"
    assert missing.status_code == 404
