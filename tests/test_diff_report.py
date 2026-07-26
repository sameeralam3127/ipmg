import csv
import io
import json

import pytest

from ipmg.core.diff import HostSnapshot, ScanRef, compare_snapshots
from ipmg.exceptions import ReportError
from ipmg.reporting.diff_report import (
    diff_to_csv,
    diff_to_json,
    diff_to_markdown,
    export_diff,
    print_diff,
    render_diff,
)


@pytest.fixture()
def diff():
    return compare_snapshots(
        [
            HostSnapshot("10.0.0.1", "Active", 10.0, "gateway|1"),
            HostSnapshot("10.0.0.2", "Active", 5.0),
        ],
        [
            HostSnapshot("10.0.0.1", "Timeout", None, "gateway|1"),
            HostSnapshot("10.0.0.2", "Active", 40.0),
            HostSnapshot("10.0.0.3", "Active", 2.0),
        ],
        baseline_ref=ScanRef(id=1, started_at="2026-07-26 10:00:00", source="targets.csv"),
        current_ref=ScanRef(id=2, started_at="2026-07-26 11:00:00", source="targets.csv"),
    )


def test_markdown_report_lists_summary_and_changes(diff):
    report = diff_to_markdown(diff)

    assert report.startswith("# IPMG Change Report")
    assert "| Host offline | 1 |" in report
    assert "| New host | 1 |" in report
    assert "10.0.0.3" in report
    # Pipes inside values are escaped so the table stays valid.
    assert r"gateway\|1" in report


def test_markdown_report_without_changes():
    empty = compare_snapshots([], [])
    report = diff_to_markdown(empty)

    assert "| No changes | 0 |" in report
    assert "_No changes detected between these scans._" in report


def test_json_report_round_trips(diff):
    payload = json.loads(diff_to_json(diff))

    assert payload["summary"]["total_changes"] == len(diff.changes)
    assert payload["baseline"]["id"] == 1


def test_csv_report_has_one_row_per_change(diff):
    rows = list(csv.reader(io.StringIO(diff_to_csv(diff))))

    assert rows[0][0] == "Change"
    assert len(rows) == len(diff.changes) + 1
    assert {row[2] for row in rows[1:]} == {"10.0.0.1", "10.0.0.2", "10.0.0.3"}


def test_render_diff_rejects_unknown_format(diff):
    with pytest.raises(ReportError):
        render_diff(diff, "pdf")


def test_export_diff_writes_every_format(tmp_path, diff):
    base = str(tmp_path / "changes")
    paths = export_diff(diff, base, ["md", "json", "csv"])

    assert len(paths) == 3
    assert {path.rsplit(".", 1)[1] for path in paths} == {"md", "json", "csv"}
    for path in paths:
        assert len(open(path, encoding="utf-8").read()) > 0


def test_print_diff_renders_without_error(diff, capsys):
    print_diff(diff)
    out = capsys.readouterr().out

    assert "Changes" in out
    assert "Host offline" in out
    assert "10.0.0.1" in out
    assert "1 critical" in out


def test_print_diff_limit_is_reported(diff, capsys):
    print_diff(diff, limit=1)
    out = capsys.readouterr().out

    assert f"{len(diff.changes)} changes (1 shown)" in out
