import json
import time
from datetime import datetime

import openpyxl
import pytest

from ipmg.exceptions import FileIOError
from ipmg.infrastructure.file_io import (
    MAX_EXPANDED_TARGETS,
    create_sample_file,
    describe_sources,
    load_all_targets,
    load_targets,
    sanitize_table,
    save_results,
)
from ipmg.reporting.frames import ReportTable


def write_csv(path, header, values):
    path.write_text("\n".join([header, *values]) + "\n", encoding="utf-8")


def test_load_targets_from_csv(tmp_path):
    path = tmp_path / "targets.csv"
    write_csv(path, "IP Address", ["8.8.8.8", "192.168.1.0/30", "8.8.8.8"])

    assert load_targets(str(path)) == ["8.8.8.8", "192.168.1.1", "192.168.1.2"]


def test_load_targets_from_text(tmp_path):
    path = tmp_path / "targets.txt"
    path.write_text("8.8.4.4\n# comment\n192.168.2.0/30\n", encoding="utf-8")

    assert load_targets(str(path)) == ["8.8.4.4", "192.168.2.1", "192.168.2.2"]


def test_load_targets_from_literal_cidr():
    assert load_targets("10.0.0.0/30") == ["10.0.0.1", "10.0.0.2"]


def test_load_targets_rejects_large_cidr():
    with pytest.raises(Exception):
        load_targets("10.0.0.0/8")


def test_load_targets_requires_expected_column(tmp_path):
    path = tmp_path / "targets.csv"
    write_csv(path, "Address", ["8.8.8.8"])

    with pytest.raises(Exception):
        load_targets(str(path))


def test_save_results_writes_markdown_report(tmp_path, monkeypatch):
    monkeypatch.setattr("ipmg.infrastructure.file_io.timestamp_str", lambda: "20260628_120000")
    df = ReportTable.from_rows(
        [
            {
                "IP Address": "8.8.8.8",
                "Status": "Active",
                "Latency": 12.3456,
                "Hostname": "dns.google",
                "Batch Timestamp": "2026-06-28 12:00:00",
                "Scan Duration (s)": 1.234,
            },
            {
                "IP Address": "1.1.1.1",
                "Status": "Timeout",
                "Latency": None,
                "Hostname": "one.one.one.one",
                "Batch Timestamp": "2026-06-28 12:00:00",
                "Scan Duration (s)": 1.234,
            },
        ]
    )

    saved_paths = save_results(df, str(tmp_path / "scan"), ["md"])

    assert saved_paths == [str(tmp_path / "scan_20260628_120000.md")]
    report = (tmp_path / "scan_20260628_120000.md").read_text(encoding="utf-8")
    assert "# IPMG Scan Report" in report
    assert "- Total hosts: 2" in report
    assert "- Active rate: 50.00%" in report
    assert "| Active | 1 |" in report
    assert "| 8.8.8.8 | Active | 12.346 | dns.google |" in report


def test_load_targets_from_literal_range():
    assert load_targets("10.0.0.1-10.0.0.3") == ["10.0.0.1", "10.0.0.2", "10.0.0.3"]


def test_load_targets_rejects_reversed_range():
    with pytest.raises(Exception):
        load_targets("10.0.0.9-10.0.0.1")


def test_load_targets_skips_hostname_like_tokens_in_files(tmp_path):
    path = tmp_path / "targets.txt"
    path.write_text("8.8.4.4\nmy-host-name\n", encoding="utf-8")

    assert load_targets(str(path)) == ["8.8.4.4"]


def test_parse_manual_targets_mixed_input():
    from ipmg.infrastructure.file_io import parse_manual_targets

    parsed = parse_manual_targets("8.8.8.8\n# dns\n192.168.5.0/30, 10.0.0.1-10.0.0.2\n")

    assert parsed == [
        "8.8.8.8",
        "192.168.5.1",
        "192.168.5.2",
        "10.0.0.1",
        "10.0.0.2",
    ]


def test_parse_manual_targets_rejects_invalid_token():
    from ipmg.infrastructure.file_io import parse_manual_targets

    with pytest.raises(Exception):
        parse_manual_targets("not-an-ip")


def test_parse_manual_targets_caps_total_expansion():
    from ipmg.exceptions import FileIOError
    from ipmg.infrastructure.file_io import parse_manual_targets

    # Each /16 stays under the per-token limit, but together they exceed it.
    with pytest.raises(FileIOError, match="expand to more than"):
        parse_manual_targets("10.0.0.0/16\n10.1.0.0/16\n")


HOSTILE_HOSTNAME = "=cmd|'/c calc'!A1"


def _hostile_frame():
    return ReportTable.from_rows(
        [
            {
                "IP Address": "10.0.0.1",
                "Status": "Active",
                "Latency": 12.3456,
                "Hostname": HOSTILE_HOSTNAME,
                "Open Ports": "@22, 80",
                "Batch Timestamp": "2026-06-28 12:00:00",
                "Scan Duration (s)": 1.234,
            }
        ]
    )


def test_sanitize_table_quotes_formula_cells_only():
    (safe,) = sanitize_table(_hostile_frame()).rows

    assert safe["Hostname"] == "'" + HOSTILE_HOSTNAME
    assert safe["Open Ports"] == "'@22, 80"
    assert safe["IP Address"] == "10.0.0.1"
    assert safe["Latency"] == 12.3456


def test_sanitize_table_leaves_the_original_untouched():
    table = _hostile_frame()
    sanitize_table(table)

    assert table.rows[0]["Hostname"] == HOSTILE_HOSTNAME


def test_save_results_neutralizes_formulas_in_csv_and_xlsx(tmp_path, monkeypatch):
    monkeypatch.setattr("ipmg.infrastructure.file_io.timestamp_str", lambda: "20260628_120000")

    save_results(_hostile_frame(), str(tmp_path / "scan"), ["csv", "xlsx", "md", "json"])

    csv_text = (tmp_path / "scan_20260628_120000.csv").read_text(encoding="utf-8")
    assert "'=cmd" in csv_text
    assert ",=cmd" not in csv_text

    sheet = openpyxl.load_workbook(tmp_path / "scan_20260628_120000.xlsx").active
    header = [cell.value for cell in sheet[1]]
    assert sheet.cell(2, header.index("Hostname") + 1).value == "'" + HOSTILE_HOSTNAME

    report = (tmp_path / "scan_20260628_120000.md").read_text(encoding="utf-8")
    assert r"'=cmd\|'/c calc'!A1" in report

    # JSON is data interchange, not a spreadsheet: it keeps the raw value.
    raw = json.loads((tmp_path / "scan_20260628_120000.json").read_text(encoding="utf-8"))
    assert raw[0]["Hostname"] == HOSTILE_HOSTNAME


def test_xlsx_writes_a_large_scan_in_linear_time(tmp_path, monkeypatch):
    monkeypatch.setattr("ipmg.infrastructure.file_io.timestamp_str", lambda: "20260628_120000")
    checked = datetime(2026, 6, 28, 12, 0, 0, 123456)
    table = ReportTable(
        rows=[
            {"IP Address": f"10.0.{i // 256}.{i % 256}", "Status": "Up", "Checked At": checked}
            for i in range(20_000)
        ],
        columns=("IP Address", "Status", "Checked At"),
    )

    started = time.perf_counter()
    save_results(table, str(tmp_path / "scan"), ["xlsx"])
    # The old writer rescanned the sheet per row: about a minute for 20k rows (#102).
    assert time.perf_counter() - started < 5

    sheet = openpyxl.load_workbook(tmp_path / "scan_20260628_120000.xlsx").active
    assert sheet.max_row == 20_001
    assert sheet["C2"].value == checked.replace(microsecond=123000)
    assert sheet["C2"].number_format == "YYYY-MM-DD HH:MM:SS"


@pytest.mark.parametrize(
    "name", ["targts.txt", "hosts.list", "hosts.csv", "hosts.json", "hosts.xlsx", "hosts.xls"]
)
def test_load_targets_reports_a_missing_input_file(tmp_path, name):
    from ipmg.exceptions import FileIOError

    missing = tmp_path / name

    with pytest.raises(FileIOError, match="was not found"):
        load_targets(str(missing))
    assert not missing.exists()


def test_load_targets_still_rejects_text_that_is_not_a_target():
    from ipmg.exceptions import FileIOError

    with pytest.raises(FileIOError, match="neither a readable file"):
        load_targets("not-a-target")


@pytest.mark.parametrize(
    "document",
    [
        ["8.8.8.8", "192.168.5.0/30"],
        [{"IP Address": "8.8.8.8"}, {"IP Address": "192.168.5.0/30"}],
        [{"ip": "8.8.8.8"}, {"target": "192.168.5.0/30"}],
        {"targets": ["8.8.8.8", "192.168.5.0/30"]},
        {"ips": ["8.8.8.8", "192.168.5.0/30"]},
    ],
)
def test_load_targets_from_json(tmp_path, document):
    """Every shape the dashboard uploader accepts also works as --input."""
    path = tmp_path / "targets.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    assert load_targets(str(path)) == ["8.8.8.8", "192.168.5.1", "192.168.5.2"]


def test_load_targets_round_trips_a_json_report(tmp_path, monkeypatch):
    """A report IPMG wrote with --formats json is valid input again."""
    monkeypatch.setattr("ipmg.infrastructure.file_io.timestamp_str", lambda: "20260628_120000")
    frame = ReportTable.from_rows(
        [
            {"IP Address": "8.8.8.8", "Status": "Active", "Latency": 1.0, "Hostname": "dns.google"},
            {"IP Address": "1.1.1.1", "Status": "Timeout", "Latency": None, "Hostname": ""},
        ]
    )
    (report,) = save_results(frame, str(tmp_path / "scan"), ["json"])

    assert load_targets(report) == ["8.8.8.8", "1.1.1.1"]


@pytest.mark.parametrize("document", ['"8.8.8.8"', '{"targets": {"a": "8.8.8.8"}}'])
def test_load_targets_rejects_json_that_is_not_a_list(tmp_path, document):
    path = tmp_path / "targets.json"
    path.write_text(document, encoding="utf-8")

    with pytest.raises(FileIOError, match="must contain a list of targets"):
        load_targets(str(path))


def test_load_targets_rejects_malformed_json(tmp_path):
    path = tmp_path / "targets.json"
    path.write_text("[8.8.8.8", encoding="utf-8")

    with pytest.raises(FileIOError, match="is not valid JSON"):
        load_targets(str(path))


def test_load_targets_names_a_bad_entry_in_json(tmp_path):
    """JSON is structured, so a non-target entry is an error, not a skipped line."""
    path = tmp_path / "targets.json"
    path.write_text(json.dumps(["8.8.8.8", "nonsense"]), encoding="utf-8")

    with pytest.raises(FileIOError, match="Unsupported target input: nonsense"):
        load_targets(str(path))


@pytest.mark.parametrize(
    "entry",
    [42, None, {"host": "10.0.0.1"}, {"ip": 167772161}, ["10.0.0.1"]],
)
def test_load_targets_names_a_json_entry_that_is_not_a_target(tmp_path, entry):
    """Numbers, nulls, and objects without a known key used to be dropped silently."""
    path = tmp_path / "targets.json"
    path.write_text(json.dumps(["8.8.8.8", entry]), encoding="utf-8")

    with pytest.raises(FileIOError, match="Unsupported entry in .*IP Address, ip, target"):
        load_targets(str(path))


def test_load_targets_rejects_empty_json(tmp_path):
    path = tmp_path / "targets.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(FileIOError, match="No valid IP targets"):
        load_targets(str(path))


def test_create_sample_file_writes_json(tmp_path):
    path = tmp_path / "ip_list.json"

    create_sample_file(str(path))

    assert json.loads(path.read_text(encoding="utf-8")) == ["8.8.8.8", "1.1.1.1"]
    assert load_targets(str(path)) == ["8.8.8.8", "1.1.1.1"]


def test_load_all_targets_merges_a_file_with_extra_hosts(tmp_path):
    path = tmp_path / "targets.txt"
    path.write_text("10.0.0.1\n10.0.0.2\n", encoding="utf-8")

    targets = load_all_targets([str(path), "10.0.0.0/30", "10.0.0.5"])

    # The file first, then the CIDR's new host, then the loose one; 10.0.0.1
    # and 10.0.0.2 appear in two sources and are scanned once.
    assert targets == ["10.0.0.1", "10.0.0.2", "10.0.0.5"]


def test_load_all_targets_keeps_a_single_source_unchanged():
    assert load_all_targets(["10.0.0.0/30"]) == load_targets("10.0.0.0/30")


def test_load_all_targets_rejects_no_sources():
    with pytest.raises(FileIOError, match="No target source"):
        load_all_targets([])


def test_load_all_targets_reports_a_bad_source_among_good_ones(tmp_path):
    path = tmp_path / "targets.txt"
    path.write_text("10.0.0.1\n", encoding="utf-8")

    with pytest.raises(FileIOError, match="neither a readable file"):
        load_all_targets([str(path), "nonsense"])


def test_load_all_targets_limits_the_combined_total():
    """The host cap applies to the union, not to each source on its own."""
    blocks = ["10.0.0.0/17", "10.1.0.0/17", "10.2.0.0/17"]

    with pytest.raises(FileIOError, match="expand to more than"):
        load_all_targets(blocks)


def test_load_all_targets_counts_overlapping_sources_once():
    """Two copies of a block are the union it describes, not twice its size."""
    block = "10.0.0.0/16"

    assert len(load_all_targets([block, block])) < MAX_EXPANDED_TARGETS


def test_describe_sources_lists_every_source():
    assert describe_sources(["targets.txt", "10.0.0.5"]) == "targets.txt, 10.0.0.5"


def test_an_xls_workbook_is_rejected_with_what_to_do(tmp_path):
    path = tmp_path / "hosts.xls"
    path.write_bytes(b"\xd0\xcf\x11\xe0")  # the OLE2 signature of a real .xls

    with pytest.raises(FileIOError, match="Save it as .xlsx or .csv"):
        load_targets(str(path))


def test_load_targets_from_xlsx_finds_the_column_anywhere(tmp_path):
    path = tmp_path / "hosts.xlsx"
    workbook = openpyxl.Workbook()
    workbook.active.append(["Name", "IP Address"])
    workbook.active.append(["router", "10.0.0.1"])
    workbook.active.append(["blank", None])
    workbook.active.append(["net", "10.0.1.0/30"])
    workbook.save(path)

    assert load_targets(str(path)) == ["10.0.0.1", "10.0.1.1", "10.0.1.2"]


def test_load_targets_from_a_csv_saved_by_excel(tmp_path):
    """Excel writes a byte-order mark, which must not hide the column name."""
    path = tmp_path / "hosts.csv"
    path.write_bytes("﻿IP Address\r\n10.0.0.1\r\n".encode())

    assert load_targets(str(path)) == ["10.0.0.1"]


def test_a_corrupt_xlsx_is_a_clear_error(tmp_path):
    path = tmp_path / "hosts.xlsx"
    path.write_bytes(b"not a zip file")

    with pytest.raises(FileIOError, match="not a readable .xlsx"):
        load_targets(str(path))
