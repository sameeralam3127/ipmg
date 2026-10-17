"""The service templates in contrib/ must keep working as IPMG changes."""

import plistlib
import shlex
from pathlib import Path

import pytest

from ipmg.cli.parser import build_diff_parser, build_parser, build_web_parser

CONTRIB = Path(__file__).resolve().parents[1] / "contrib"
UNITS = sorted((CONTRIB / "systemd").glob("*.service"))
PLIST = CONTRIB / "launchd" / "io.github.sameeralam3127.ipmg.scan.plist"


def unit_entries(path):
    """(section, key, value) for every setting, continuation lines joined."""
    entries, section, pending = [], "", ""
    for raw in path.read_text().splitlines():
        line = pending + raw.strip()
        if line.endswith("\\"):
            pending = line[:-1] + " "
            continue
        pending = ""
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("["):
            section = line.strip("[]")
            continue
        key, _, value = line.partition("=")
        entries.append((section, key.strip(), value.strip()))
    return entries


def settings(path, section, key):
    return [value for sec, name, value in unit_entries(path) if sec == section and name == key]


def parse_ipmg(argv):
    """Parse an ipmg command line with the parser the command dispatches to."""
    args = argv[1:]
    parsers = {"web": build_web_parser, "diff": build_diff_parser}
    if args and args[0] in parsers:
        return args[0], parsers[args[0]]().parse_args(args[1:])
    return "scan", build_parser().parse_args(args)


def test_there_are_templates():
    assert {path.name for path in UNITS} >= {
        "ipmg-scan.service",
        "ipmg-check.service",
        "ipmg-web.service",
    }
    assert (CONTRIB / "systemd" / "ipmg-check.timer").exists()


@pytest.mark.parametrize("unit", UNITS, ids=lambda path: path.name)
def test_units_run_as_a_dedicated_non_root_user(unit):
    assert settings(unit, "Service", "User") == ["ipmg"]
    assert settings(unit, "Service", "StateDirectory") == ["ipmg"]
    assert settings(unit, "Service", "ProtectSystem") == ["strict"]


@pytest.mark.parametrize("unit", UNITS, ids=lambda path: path.name)
def test_every_command_in_a_unit_parses_with_today_s_flags(unit):
    commands = settings(unit, "Service", "ExecStart")
    assert commands
    for command in commands:
        argv = shlex.split(command)
        assert argv[0].endswith("/ipmg")
        parse_ipmg(argv)  # an unknown or misspelt flag exits here


def test_the_monitor_repeats_and_compares():
    [command] = settings(CONTRIB / "systemd" / "ipmg-scan.service", "Service", "ExecStart")
    _name, args = parse_ipmg(shlex.split(command))

    assert args.interval and args.compare
    assert settings(CONTRIB / "systemd" / "ipmg-scan.service", "Service", "Restart") == [
        "on-failure"
    ]


def test_the_check_fails_on_change_for_the_source_it_scanned():
    scan, diff = settings(CONTRIB / "systemd" / "ipmg-check.service", "Service", "ExecStart")
    _scan, scan_args = parse_ipmg(shlex.split(scan))
    name, diff_args = parse_ipmg(shlex.split(diff))

    assert name == "diff" and diff_args.fail_on_change
    assert diff_args.source == scan_args.input[0]
    assert diff_args.db == scan_args.db


def test_ipmg_web_listens_on_loopback_only():
    [command] = settings(CONTRIB / "systemd" / "ipmg-web.service", "Service", "ExecStart")
    name, args = parse_ipmg(shlex.split(command))

    assert name == "web"
    assert args.host == "127.0.0.1"
    assert args.no_browser


def test_the_launchd_agent_is_a_valid_plist_running_the_monitor():
    with PLIST.open("rb") as handle:
        agent = plistlib.load(handle)

    assert agent["Label"] == PLIST.stem
    _name, args = parse_ipmg(agent["ProgramArguments"])
    assert args.interval and args.compare
    assert agent["KeepAlive"] is True and agent["RunAtLoad"] is True
    assert agent["StandardOutPath"] and agent["StandardErrorPath"]
    assert "UserName" not in agent  # a user agent: it runs as you, never root
