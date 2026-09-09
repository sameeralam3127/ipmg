import json

import pandas as pd
import pytest

from ipmg.infrastructure.file_io import load_targets, sanitize_export_frame, save_results


def test_load_targets_from_csv(tmp_path):
    path = tmp_path / "targets.csv"
    pd.DataFrame({"IP Address": ["8.8.8.8", "192.168.1.0/30", "8.8.8.8"]}).to_csv(path, index=False)

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
    pd.DataFrame({"Address": ["8.8.8.8"]}).to_csv(path, index=False)

    with pytest.raises(Exception):
        load_targets(str(path))


def test_save_results_writes_markdown_report(tmp_path, monkeypatch):
    monkeypatch.setattr("ipmg.infrastructure.file_io.timestamp_str", lambda: "20260628_120000")
    df = pd.DataFrame(
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
    return pd.DataFrame(
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


def test_sanitize_export_frame_quotes_formula_cells_only():
    safe = sanitize_export_frame(_hostile_frame())

    assert safe.loc[0, "Hostname"] == "'" + HOSTILE_HOSTNAME
    assert safe.loc[0, "Open Ports"] == "'@22, 80"
    assert safe.loc[0, "IP Address"] == "10.0.0.1"
    assert safe.loc[0, "Latency"] == 12.3456


def test_sanitize_export_frame_leaves_the_original_untouched():
    df = _hostile_frame()
    sanitize_export_frame(df)

    assert df.loc[0, "Hostname"] == HOSTILE_HOSTNAME


def test_save_results_neutralizes_formulas_in_csv_and_xlsx(tmp_path, monkeypatch):
    monkeypatch.setattr("ipmg.infrastructure.file_io.timestamp_str", lambda: "20260628_120000")

    save_results(_hostile_frame(), str(tmp_path / "scan"), ["csv", "xlsx", "md", "json"])

    csv_text = (tmp_path / "scan_20260628_120000.csv").read_text(encoding="utf-8")
    assert "'=cmd" in csv_text
    assert ",=cmd" not in csv_text

    xlsx = pd.read_excel(tmp_path / "scan_20260628_120000.xlsx")
    assert xlsx.loc[0, "Hostname"] == "'" + HOSTILE_HOSTNAME

    report = (tmp_path / "scan_20260628_120000.md").read_text(encoding="utf-8")
    assert r"'=cmd\|'/c calc'!A1" in report

    # JSON is data interchange, not a spreadsheet: it keeps the raw value.
    raw = json.loads((tmp_path / "scan_20260628_120000.json").read_text(encoding="utf-8"))
    assert raw[0]["Hostname"] == HOSTILE_HOSTNAME
