"""``--json`` and ``--jsonl``: the scan's results on stdout, nothing else."""

import json

import pytest

from ipmg.cli import commands
from ipmg.reporting.frames import RESULT_COLUMNS

#: Fields that legitimately differ between two runs of the same scan.
_TIMING_FIELDS = {"Latency", "Batch Timestamp", "Scan Duration (s)"}


@pytest.fixture()
def answering_hosts(monkeypatch):
    """Answer every ping, so a scan's output is the only thing under test."""
    monkeypatch.setattr("ipmg.core.engine.ping_ip", lambda *_args: ("Active", 1.5))


def scan(tmp_path, *extra):
    return commands.run(
        ["--input", "10.0.0.1", "10.0.0.2", "--no-history", "--output", str(tmp_path / "out")]
        + list(extra)
    )


def test_json_prints_one_array_and_nothing_else(tmp_path, answering_hosts, capsys):
    assert scan(tmp_path, "--json") == commands.EXIT_OK

    captured = capsys.readouterr()
    rows = json.loads(captured.out)
    assert [row["IP Address"] for row in rows] == ["10.0.0.1", "10.0.0.2"]
    assert {row["Status"] for row in rows} == {"Active"}


def test_json_keeps_the_human_output_on_stderr(tmp_path, answering_hosts, capsys):
    scan(tmp_path, "--json")

    captured = capsys.readouterr()
    # The banner, the configuration block, and the summary all land on stderr,
    # which is what leaves stdout parseable.
    assert "ipmg" in captured.err
    assert "Targets" in captured.err
    assert "Results" in captured.err
    json.loads(captured.out)


def test_json_field_names_match_the_report_columns(tmp_path, answering_hosts, capsys):
    scan(tmp_path, "--json")

    rows = json.loads(capsys.readouterr().out)
    assert list(rows[0]) == RESULT_COLUMNS


def test_json_is_the_array_form_of_the_jsonl_report(tmp_path, answering_hosts, capsys):
    """Piping and --formats jsonl must not be two different documents."""
    scan(tmp_path, "--json", "--formats", "jsonl")

    piped = json.loads(capsys.readouterr().out)
    (report,) = tmp_path.glob("out_*.jsonl")
    lines = report.read_text(encoding="utf-8").splitlines()
    assert piped == [json.loads(line) for line in lines]


def test_json_and_jsonl_agree_on_every_field(tmp_path, answering_hosts, capsys):
    """A script must not have to care which of the two flags produced a host."""
    scan(tmp_path, "--json")
    array = json.loads(capsys.readouterr().out)

    scan(tmp_path, "--jsonl")
    streamed = [json.loads(line) for line in capsys.readouterr().out.splitlines()]

    def comparable(rows):
        # Latency and elapsed time differ between two runs; nothing else may.
        return [
            {key: value for key, value in row.items() if key not in _TIMING_FIELDS}
            for row in sorted(rows, key=lambda row: row["IP Address"])
        ]

    assert comparable(array) == comparable(streamed)


def test_a_timestamp_reads_as_text_not_epoch_milliseconds(tmp_path, answering_hosts, capsys):
    scan(tmp_path, "--json")

    batch = json.loads(capsys.readouterr().out)[0]["Batch Timestamp"]
    assert isinstance(batch, str)
    assert batch.startswith("20")


def test_jsonl_prints_one_object_per_host(tmp_path, answering_hosts, capsys):
    assert scan(tmp_path, "--jsonl") == commands.EXIT_OK

    lines = capsys.readouterr().out.splitlines()
    rows = [json.loads(line) for line in lines]
    assert sorted(row["IP Address"] for row in rows) == ["10.0.0.1", "10.0.0.2"]
    assert list(rows[0]) == RESULT_COLUMNS


def test_json_and_jsonl_are_mutually_exclusive(tmp_path, capsys):
    """Both on one stdout would interleave an array with its own rows."""
    with pytest.raises(SystemExit):
        scan(tmp_path, "--json", "--jsonl")

    assert "not allowed with argument" in capsys.readouterr().err


def test_piping_writes_no_report_file_unless_asked(tmp_path, answering_hosts, capsys):
    scan(tmp_path, "--json")
    capsys.readouterr()

    assert list(tmp_path.glob("out_*")) == []


def test_an_explicit_format_still_writes_its_file(tmp_path, answering_hosts, capsys):
    scan(tmp_path, "--json", "--formats", "csv")
    capsys.readouterr()

    assert len(list(tmp_path.glob("out_*.csv"))) == 1


def test_a_scan_without_piping_still_writes_xlsx(tmp_path, answering_hosts, capsys):
    scan(tmp_path)
    capsys.readouterr()

    assert len(list(tmp_path.glob("out_*.xlsx"))) == 1


def test_exit_code_is_unchanged_by_piping(tmp_path, monkeypatch, capsys):
    """A scan where nothing answers still succeeds, piped or not."""
    monkeypatch.setattr("ipmg.core.engine.ping_ip", lambda *_args: ("Timeout", None))

    assert scan(tmp_path, "--json") == commands.EXIT_OK
    assert json.loads(capsys.readouterr().out)[0]["Status"] == "Timeout"


def test_a_failing_scan_still_reports_its_error_and_exit_code(tmp_path, capsys):
    exit_code = commands.run(["--input", str(tmp_path / "missing.txt"), "--json"])

    captured = capsys.readouterr()
    assert exit_code == commands.EXIT_ERROR
    # Errors are for the operator, so they follow the rest of the UI to stderr
    # and leave stdout empty rather than emitting a half-written document.
    # Rich wraps at the console width, and where it breaks depends on how long
    # the temp path is, so compare with the wrapping undone.
    assert "was not found" in " ".join(captured.err.split())
    assert captured.out == ""
