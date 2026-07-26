import pytest

from ipmg.cli import commands
from ipmg.core.engine import HostResult, ScanConfig
from ipmg.exceptions import FileIOError
from ipmg.infrastructure.database import Database
from ipmg.services.history_service import HistoryService
from ipmg.utils.helpers import console


@pytest.fixture()
def db_path(tmp_path):
    return str(tmp_path / "history.db")


@pytest.fixture(autouse=True)
def wide_console():
    """Keep rich from truncating table cells in captured output."""
    previous = console.width
    console.width = 200
    yield
    console.width = previous


def seed(db_path, *scans):
    history = HistoryService(Database(db_path))
    return [
        history.record_scan(
            source="targets.csv",
            results=list(results),
            config=ScanConfig(),
            duration_s=1.0,
        )
        for results in scans
    ]


def test_diff_command_compares_the_two_latest_scans(db_path, capsys):
    seed(
        db_path,
        [HostResult("10.0.0.1", "Active", 2.0)],
        [HostResult("10.0.0.1", "Timeout", None), HostResult("10.0.0.2", "Active", 1.0)],
    )

    assert commands.run(["diff", "--db", db_path]) == commands.EXIT_OK

    out = capsys.readouterr().out
    assert "Host offline" in out
    assert "New host" in out


def test_diff_command_accepts_explicit_ids_and_exports(db_path, tmp_path, capsys):
    first, second = seed(
        db_path,
        [HostResult("10.0.0.1", "Active", 2.0)],
        [HostResult("10.0.0.1", "Inactive", None)],
    )
    base = str(tmp_path / "changes")

    exit_code = commands.run(
        [
            "diff",
            str(first),
            str(second),
            "--db",
            db_path,
            "--diff-formats",
            "md",
            "--diff-output",
            base,
        ]
    )

    assert exit_code == commands.EXIT_OK
    assert list(tmp_path.glob("changes_*.md"))


def test_diff_command_fail_on_change_exit_code(db_path):
    seed(
        db_path,
        [HostResult("10.0.0.1", "Active", 2.0)],
        [HostResult("10.0.0.1", "Timeout", None)],
    )

    assert (
        commands.run(["diff", "--db", db_path, "--fail-on-change"])
        == commands.EXIT_CHANGES_DETECTED
    )


def test_diff_command_without_changes_succeeds(db_path):
    seed(
        db_path,
        [HostResult("10.0.0.1", "Active", 2.0)],
        [HostResult("10.0.0.1", "Active", 2.0)],
    )

    assert commands.run(["diff", "--db", db_path, "--fail-on-change"]) == commands.EXIT_OK


def test_diff_command_reports_missing_history(db_path, capsys):
    assert commands.run(["diff", "--db", db_path]) == commands.EXIT_ERROR
    assert "At least two stored scans" in capsys.readouterr().out


def test_diff_command_rejects_too_many_ids(db_path, capsys):
    assert commands.run(["diff", "1", "2", "3", "--db", db_path]) == commands.EXIT_ERROR
    assert "at most two scan ids" in capsys.readouterr().out


def test_history_command_lists_scans(db_path, capsys):
    seed(db_path, [HostResult("10.0.0.1", "Active", 2.0)])

    assert commands.run(["history", "--db", db_path]) == commands.EXIT_OK

    out = capsys.readouterr().out
    assert "Scan history" in out
    assert "targets.csv" in out


def test_history_command_on_empty_database(db_path, capsys):
    assert commands.run(["history", "--db", db_path]) == commands.EXIT_OK
    assert "No scans stored yet" in capsys.readouterr().out


def test_ipmg_errors_become_exit_code_one(monkeypatch, capsys):
    def boom(_args):
        raise FileIOError("bad input file")

    monkeypatch.setattr(commands, "run_scan", boom)

    assert commands.run([]) == commands.EXIT_ERROR
    assert "bad input file" in capsys.readouterr().out


def test_keyboard_interrupt_exit_code(monkeypatch):
    def interrupt(_args):
        raise KeyboardInterrupt

    monkeypatch.setattr(commands, "run_scan", interrupt)

    assert commands.run([]) == commands.EXIT_INTERRUPTED


def test_scan_arguments_are_forwarded(monkeypatch):
    captured = {}
    monkeypatch.setattr(commands, "run_scan", lambda args: captured.update(vars(args)))

    assert commands.run(["--input", "targets.csv", "--compare", "--no-history"]) == commands.EXIT_OK
    assert captured["input"] == "targets.csv"
    assert captured["compare"] is True
    assert captured["history"] is False
