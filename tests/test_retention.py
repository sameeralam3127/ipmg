from datetime import datetime, timedelta

import pytest

from ipmg.cli import commands
from ipmg.core.engine import HostResult
from ipmg.infrastructure.database import Database
from ipmg.infrastructure.retention import parse_age, plan_prune, prune_reports, report_files
from ipmg.services.scan_service import run_scan
from scan_helpers import scan_args

NOW = datetime(2026, 10, 17, 12, 0, 0)


def scan(scan_id, source="a.txt", days_ago=0, status="complete", completed=3):
    started = (NOW - timedelta(days=days_ago)).isoformat(sep=" ", timespec="seconds")
    return {
        "id": scan_id,
        "source": source,
        "started_at": started,
        "status": status,
        "completed": completed,
    }


@pytest.mark.parametrize(
    "text, expected",
    [
        ("30d", timedelta(days=30)),
        ("12h", timedelta(hours=12)),
        ("90m", timedelta(minutes=90)),
        ("2w", timedelta(weeks=2)),
        ("45s", timedelta(seconds=45)),
        ("7", timedelta(days=7)),
        (" 3D ", timedelta(days=3)),
    ],
)
def test_parse_age(text, expected):
    assert parse_age(text) == expected


@pytest.mark.parametrize("text", ["", "d", "1y", "-3d", "1.5d", "30 days"])
def test_parse_age_rejects_what_it_cannot_read(text):
    with pytest.raises(ValueError, match="invalid age"):
        parse_age(text)


def test_keep_counts_each_source_separately():
    scans = [scan(n, "a.txt") for n in range(1, 6)] + [scan(n, "b.txt") for n in range(6, 9)]

    plan = plan_prune(scans, keep=2, now=NOW)

    assert sorted(plan.scan_ids) == [1, 2, 3, 6]
    assert plan.by_source() == {"a.txt": 3, "b.txt": 1}
    assert plan.result_count == 12


def test_older_than_deletes_by_age_alone():
    scans = [scan(1, days_ago=40), scan(2, days_ago=31), scan(3, days_ago=29), scan(4)]

    assert plan_prune(scans, older_than=timedelta(days=30), now=NOW).scan_ids == [2, 1]


def test_with_both_rules_a_scan_either_rule_keeps_survives():
    # The 2 newest are kept by count; the 2 within 30 days are kept by age.
    scans = [
        scan(1, days_ago=90),
        scan(2, days_ago=60),
        scan(3, days_ago=45),
        scan(4, days_ago=20),
        scan(5, days_ago=10),
    ]

    plan = plan_prune(scans, keep=1, older_than=timedelta(days=30), now=NOW)

    assert sorted(plan.scan_ids) == [1, 2, 3]
    plan = plan_prune(scans, keep=4, older_than=timedelta(days=30), now=NOW)
    assert plan.scan_ids == [1]


def test_running_scans_are_never_pruned():
    scans = [scan(1, status="running", days_ago=99), scan(2, days_ago=99), scan(3)]

    plan = plan_prune(scans, keep=0, now=NOW)

    assert sorted(plan.scan_ids) == [2, 3]


def test_a_policy_needs_a_rule():
    with pytest.raises(ValueError):
        plan_prune([scan(1)])


# ------------------------------------------------------------------ CLI


def stored(db_path, sources):
    db = Database(db_path)
    for source in sources:
        db.record_scan(source, [HostResult("10.0.0.1", "Active", 1.0)], {}, 1.0)
    return db


def test_history_prune_keeps_the_newest_of_each_source(tmp_path, capsys):
    db = stored(tmp_path / "h.db", ["a.txt"] * 4 + ["b.txt"] * 2)

    code = commands.run(["history", "prune", "--keep", "1", "--db", str(tmp_path / "h.db")])

    assert code == 0
    remaining = db.list_scans()
    assert sorted(row["source"] for row in remaining) == ["a.txt", "b.txt"]
    assert {row["id"] for row in remaining} == {4, 6}
    out = capsys.readouterr().out
    assert "Deleted" in out and "4 scans" in out
    assert "a.txt (3)" in out and "b.txt (1)" in out


def test_history_prune_dry_run_deletes_nothing(tmp_path, capsys):
    db = stored(tmp_path / "h.db", ["a.txt"] * 3)

    commands.run(["history", "prune", "--keep", "1", "--dry-run", "--db", str(tmp_path / "h.db")])

    assert len(db.list_scans()) == 3
    out = capsys.readouterr().out
    assert "Prunable" in out and "nothing was deleted" in out


def test_history_prune_can_limit_itself_to_one_source(tmp_path):
    db = stored(tmp_path / "h.db", ["a.txt", "a.txt", "b.txt", "b.txt"])

    commands.run(
        ["history", "prune", "--keep", "1", "--source", "b.txt", "--db", str(tmp_path / "h.db")]
    )

    assert [row["id"] for row in db.list_scans()] == [4, 2, 1]


def test_history_prune_vacuums_on_request(tmp_path, capsys):
    stored(tmp_path / "h.db", ["a.txt"] * 3)

    code = commands.run(
        ["history", "prune", "--keep", "1", "--vacuum", "--db", str(tmp_path / "h.db")]
    )

    assert code == 0
    assert "Database" in capsys.readouterr().out


def test_history_prune_needs_a_rule(tmp_path, capsys):
    with pytest.raises(SystemExit):
        commands.run(["history", "prune", "--db", str(tmp_path / "h.db")])
    assert "--keep N, --older-than AGE, or both" in capsys.readouterr().err


def test_history_prune_with_nothing_to_do(tmp_path, capsys):
    stored(tmp_path / "h.db", ["a.txt"])

    commands.run(["history", "prune", "--keep", "5", "--db", str(tmp_path / "h.db")])

    assert "Nothing to prune" in capsys.readouterr().out


def test_plain_history_still_lists(tmp_path, capsys):
    stored(tmp_path / "h.db", ["a.txt"])

    assert commands.run(["history", "--db", str(tmp_path / "h.db")]) == 0
    assert "Scan history" in capsys.readouterr().out


# ------------------------------------------------------- scan-time limits


def test_keep_scans_bounds_the_history_after_every_scan(tmp_path, stub_scan):
    stub_scan["statuses"] = {"10.0.0.1": ("Active", 1.0)}
    for _ in range(4):
        run_scan(scan_args(tmp_path, keep_scans=2, compare=True))

    scans = Database(tmp_path / "history.db").list_scans()
    assert [row["id"] for row in scans] == [4, 3]


def touch_reports(base, stamps, formats=("csv", "md")):
    for stamp in stamps:
        for fmt in formats:
            (base.parent / f"{base.name}_{stamp}.{fmt}").write_text("x")


def test_prune_reports_keeps_the_newest_of_each_format(tmp_path):
    base = tmp_path / "results"
    touch_reports(base, ["20261001_000000", "20261002_000000", "20261003_000000"])
    unrelated = [
        tmp_path / "results_notes.txt",
        tmp_path / "other_20261001_000000.csv",
        tmp_path / "results_20261001_000000.xlsx.bak",
    ]
    for path in unrelated:
        path.write_text("keep me")

    removed = prune_reports([str(base)], keep=2)

    assert sorted(removed) == sorted(
        [str(tmp_path / "results_20261001_000000.csv"), str(tmp_path / "results_20261001_000000.md")]
    )
    assert all(path.exists() for path in unrelated)
    assert [path.name for path in report_files(str(base))["csv"]] == [
        "results_20261002_000000.csv",
        "results_20261003_000000.csv",
    ]


def test_prune_reports_never_removes_the_pass_just_written(tmp_path):
    base = tmp_path / "results"
    # A clock that went backwards makes the new pass sort oldest.
    touch_reports(base, ["20261001_000000", "20261005_000000"], formats=("csv",))

    removed = prune_reports([str(base)], keep=1, protect="20261001_000000")

    assert removed == []


def test_keep_reports_runs_after_every_pass(tmp_path, stub_scan, monkeypatch):
    from ipmg.infrastructure import file_io

    stamps = iter(["20261001_000000", "20261002_000000", "20261003_000000"])
    monkeypatch.setattr("ipmg.services.scan_service.timestamp_str", lambda: next(stamps))
    monkeypatch.setattr("ipmg.services.scan_service.save_results", file_io.save_results)
    stub_scan["statuses"] = {"10.0.0.1": ("Active", 1.0)}

    for _ in range(3):
        run_scan(scan_args(tmp_path, history=False, formats=["csv"], keep_reports=2))

    assert sorted(path.name for path in tmp_path.glob("results_*.csv")) == [
        "results_20261002_000000.csv",
        "results_20261003_000000.csv",
    ]


def test_retention_flags_can_be_set_in_the_config_file(tmp_path, monkeypatch):
    from ipmg.cli import config
    from ipmg.cli.parser import build_parser

    (tmp_path / "ipmg.toml").write_text("keep-scans = 500\nkeep-reports = 10\n")
    monkeypatch.chdir(tmp_path)
    parser = build_parser()
    config.apply(parser, build_parser, [])
    args = parser.parse_args([])

    assert (args.keep_scans, args.keep_reports) == (500, 10)
