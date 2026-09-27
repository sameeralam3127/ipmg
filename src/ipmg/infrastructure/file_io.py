from __future__ import annotations

import calendar
import csv
import io
import ipaddress
import json
import math
import os
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, List, Sequence

from ipmg.core.ping import validate_ip
from ipmg.exceptions import FileIOError
from ipmg.infrastructure.incremental import atomic_write_bytes, jsonl_record
from ipmg.reporting import ui
from ipmg.reporting.frames import ReportTable
from ipmg.utils.helpers import markdown_cell, spreadsheet_escape, timestamp_str

SUPPORTED_INPUT_SUFFIXES = {".xlsx", ".csv", ".json", ".txt", ".list"}

#: How the xlsx report formats its timestamp column (what pandas wrote).
_XLSX_DATETIME_FORMAT = "YYYY-MM-DD HH:MM:SS"
MAX_EXPANDED_TARGETS = 65_536
DEFAULT_INPUT_FILE = "ip_list.xlsx"


def _deduplicate(targets: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(targets))


def _check_target_limit(count: int, source: str) -> None:
    if count > MAX_EXPANDED_TARGETS:
        raise FileIOError(
            f"Targets from {source} expand to more than {MAX_EXPANDED_TARGETS} hosts."
        )


def _expand_cidr(target: str) -> list[str]:
    try:
        parsed = ipaddress.ip_network(target, strict=False)
    except ValueError as exc:
        raise FileIOError(f"Unsupported target input: {target}") from exc

    if parsed.num_addresses == 1:
        return [str(parsed.network_address)]

    if parsed.num_addresses - 2 > MAX_EXPANDED_TARGETS:
        message = (
            f"CIDR target '{target}' expands to too many hosts. "
            f"Maximum allowed hosts: {MAX_EXPANDED_TARGETS}."
        )
        if parsed.version == 6:
            # A /64 is 2^64 addresses: no sweep can walk it, so point at what works.
            message += (
                " An IPv6 network cannot be swept address by address; use "
                "'--discover ipv6' to find the hosts on the local link, or scan "
                "a /112 or smaller."
            )
        raise FileIOError(message)

    return [str(ip) for ip in parsed.hosts()]


def _expand_range(target: str) -> list[str]:
    start_raw, _, end_raw = target.partition("-")
    try:
        start = ipaddress.ip_address(start_raw.strip())
        end = ipaddress.ip_address(end_raw.strip())
    except ValueError:
        # Not an IP range (e.g. a hostname containing dashes) — let callers
        # decide whether to skip or reject the token.
        return []

    if start.version != end.version or int(end) < int(start):
        raise FileIOError(f"Invalid IP range: {target}")

    total = int(end) - int(start) + 1
    if total > MAX_EXPANDED_TARGETS:
        raise FileIOError(
            f"IP range '{target}' expands to too many hosts. "
            f"Maximum allowed hosts: {MAX_EXPANDED_TARGETS}."
        )

    return [str(start + offset) for offset in range(total)]


def _expand_target(value: str) -> list[str]:
    """Expand a single target token: literal IP, CIDR block, or IP range."""
    if validate_ip(value):
        return [value]
    if "/" in value:
        return _expand_cidr(value)
    if "-" in value:
        return _expand_range(value)
    return []


def _collect_targets(values: Iterable[str], source: str, strict: bool) -> list[str]:
    """Expand every token, enforcing the overall host limit as we go.

    ``strict`` rejects tokens that expand to nothing (manual input) instead of
    silently skipping them (file input, where stray hostnames are tolerated).
    """
    targets: list[str] = []
    for value in values:
        expanded = _expand_target(value)
        if not expanded and strict:
            raise FileIOError(f"Unsupported target input: {value}")
        targets.extend(expanded)
        _check_target_limit(len(targets), source)
    return _deduplicate(targets)


def parse_manual_targets(text: str) -> list[str]:
    """Parse free-form target text: one IP, CIDR, or range per line/comma.

    Blank lines and ``#`` comments are ignored. Used by the web dashboard
    for manually entered targets.
    """
    tokens = [
        token
        for raw_line in text.splitlines()
        for token in raw_line.split("#", 1)[0].replace(",", " ").split()
    ]
    targets = _collect_targets(tokens, "manual input", strict=True)

    if not targets:
        raise FileIOError("No valid IP targets were provided.")

    return targets


#: Keys a JSON target object may carry its address under, most explicit first.
#: ``IP Address`` comes first because it is the column IPMG's own JSON report
#: writes, which is what makes a report usable as input again.
JSON_TARGET_KEYS = ("IP Address", "ip", "target")


def targets_from_json(data: Any, source: str = "JSON input") -> list[str]:
    """Expand targets from already-parsed JSON, in any shape IPMG accepts.

    A list of address strings, a list of objects keyed by any of
    :data:`JSON_TARGET_KEYS`, or an object with a ``targets`` or ``ips`` array.
    Shared by the CLI loader and the dashboard uploader so both accept exactly
    the same documents.
    """
    if isinstance(data, dict):
        data = data.get("targets") or data.get("ips") or []
    if not isinstance(data, list):
        raise FileIOError(f"{source} must contain a list of targets.")

    tokens: list[str] = []
    for entry in data:
        if isinstance(entry, dict):
            entry_value = next((entry[key] for key in JSON_TARGET_KEYS if entry.get(key)), None)
        else:
            entry_value = entry
        if isinstance(entry_value, str):
            tokens.append(entry_value)
        else:
            raise FileIOError(
                f"Unsupported entry in {source}: {entry!r}. Each entry must be an address "
                f"or an object with one of: {', '.join(JSON_TARGET_KEYS)}."
            )

    # strict=True: a JSON document is structured, so an entry that is not a
    # target is a mistake worth naming, not a stray line to skip.
    targets = _collect_targets(tokens, source, strict=True)

    if not targets:
        raise FileIOError(f"No valid IP targets were found in {source}.")

    return targets


def _load_from_rows(header: Sequence[Any], rows: Iterable[Sequence[Any]], source: str) -> list[str]:
    """Targets from a table whose ``header`` names an ``IP Address`` column."""
    names = [str(name).strip() if name is not None else "" for name in header]
    if "IP Address" not in names:
        raise FileIOError(f"Input file '{source}' must contain an 'IP Address' column.")
    index = names.index("IP Address")

    cells = (row[index] if index < len(row) else None for row in rows)
    values = (str(cell).strip() for cell in cells if cell is not None and str(cell).strip())
    targets = _collect_targets(values, f"'{source}'", strict=False)

    if not targets:
        raise FileIOError(f"No valid IP targets were found in '{source}'.")

    return targets


def _load_from_xlsx(path: str) -> list[str]:
    from openpyxl import load_workbook

    try:
        workbook = load_workbook(path, read_only=True, data_only=True)
    except Exception as exc:  # openpyxl raises a zoo of zip and XML errors
        raise FileIOError(f"Input file '{path}' is not a readable .xlsx workbook: {exc}") from exc
    try:
        rows = workbook.worksheets[0].iter_rows(values_only=True)
        header = next(rows, ())
        return _load_from_rows(header, rows, path)
    finally:
        workbook.close()


def _load_from_csv(path: str) -> list[str]:
    # utf-8-sig: Excel saves CSV with a byte-order mark, which would otherwise
    # glue itself to the first column's name.
    with open(path, encoding="utf-8-sig", newline="") as handle:
        rows = csv.reader(handle)
        header = next(rows, [])
        return _load_from_rows(header, rows, path)


def _load_from_text(path: str) -> list[str]:
    with open(path, encoding="utf-8") as handle:
        values = [
            line.strip() for line in handle if line.strip() and not line.strip().startswith("#")
        ]
    targets = _collect_targets(values, f"'{path}'", strict=False)

    if not targets:
        raise FileIOError(f"No valid IP targets were found in '{path}'.")

    return targets


def _load_from_json(path: str) -> list[str]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise FileIOError(f"Input file '{path}' is not valid JSON: {exc}") from exc
    return targets_from_json(data, f"'{path}'")


def load_targets(source: str) -> list[str]:
    path = Path(source)

    if path.exists():
        suffix = path.suffix.lower()
        if suffix == ".xlsx":
            return _load_from_xlsx(source)
        if suffix == ".xls":
            raise FileIOError(
                f"'{source}' is an Excel 97-2003 (.xls) workbook, which IPMG cannot "
                "read. Save it as .xlsx or .csv and pass that instead."
            )
        if suffix == ".csv":
            return _load_from_csv(source)
        if suffix == ".json":
            return _load_from_json(source)
        if suffix in {".txt", ".list"}:
            return _load_from_text(source)
        raise FileIOError(
            f"Unsupported input file type '{suffix or '<none>'}'. "
            f"Supported types: {', '.join(sorted(SUPPORTED_INPUT_SUFFIXES))}."
        )

    if path.suffix.lower() in SUPPORTED_INPUT_SUFFIXES | {".xls"}:
        raise FileIOError(f"Input file '{source}' was not found.")

    expanded = _expand_target(source.strip())
    if expanded:
        return expanded

    raise FileIOError(
        f"Input '{source}' is neither a readable file nor a valid IP/CIDR/range target."
    )


def describe_sources(sources: Sequence[str]) -> str:
    """The one-line name for a set of target sources, as reports record it."""
    return ", ".join(sources)


def load_all_targets(sources: Sequence[str]) -> list[str]:
    """Expand every target source and merge them into one de-duplicated list.

    Sources are any mix of files, IPs, CIDR blocks, and ranges; each one is
    expanded by :func:`load_targets`. Hosts keep the order they were first
    seen in, and duplicates across sources collapse — scanning a file plus one
    host already in it probes that host once.

    De-duplication happens as each source lands rather than at the end, so the
    :data:`MAX_EXPANDED_TARGETS` limit bounds the distinct hosts of the whole
    run: two overlapping /17 blocks are the union they describe, not its sum.
    """
    if not sources:
        raise FileIOError("No target source was given.")
    if len(sources) == 1:
        return load_targets(sources[0])

    merged: dict[str, None] = {}
    for source in sources:
        merged.update(dict.fromkeys(load_targets(source)))
        _check_target_limit(len(merged), describe_sources(sources))
    return list(merged)


SAMPLE_TARGETS = ["8.8.8.8", "1.1.1.1"]


def create_sample_file(path: str) -> None:
    suffix = Path(path).suffix.lower()

    if suffix == ".json":
        Path(path).write_text(json.dumps(SAMPLE_TARGETS, indent=2) + "\n", encoding="utf-8")
        return

    if suffix in {".txt", ".list"}:
        Path(path).write_text("\n".join(SAMPLE_TARGETS) + "\n", encoding="utf-8")
        return

    sample = ReportTable([{"IP Address": ip} for ip in SAMPLE_TARGETS], columns=("IP Address",))
    atomic_write_bytes(path, render_report(sample, "csv" if suffix == ".csv" else "xlsx"))


def _is_missing(value: Any) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def sanitize_table(table: ReportTable) -> ReportTable:
    """Copy ``table`` with every text cell neutralised for spreadsheet export.

    Applied to CSV and XLSX output on both the CLI and dashboard paths so a
    hostname harvested from reverse DNS cannot smuggle a formula into the
    operator's spreadsheet. See :func:`spreadsheet_escape`.
    """
    return ReportTable(
        [
            {
                column: spreadsheet_escape(value) if isinstance(value, str) else value
                for column, value in row.items()
            }
            for row in table.rows
        ],
        columns=table.columns,
    )


def _format_markdown_value(value) -> str:
    if _is_missing(value):
        return ""
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return markdown_cell(value)


def build_markdown_report(table: ReportTable) -> str:
    total = len(table)
    # most_common keeps first-seen order among equal counts, as pandas did.
    status_counts = dict(Counter(table.column("Status")).most_common()) if total else {}
    active = status_counts.get("Active", 0)
    active_rate = (active / total) * 100 if total else 0
    durations = [value for value in table.column("Scan Duration (s)") if not _is_missing(value)]
    duration = max(durations) if durations else 0
    batch_timestamp = str(table.rows[0].get("Batch Timestamp") or "") if total else ""

    lines = [
        "# IPMG Scan Report",
        "",
        "## Scan Metrics",
        "",
        f"- Batch timestamp: {batch_timestamp or 'Unknown'}",
        f"- Total hosts: {total}",
        f"- Active hosts: {active}",
        f"- Active rate: {active_rate:.2f}%",
        f"- Scan duration: {duration:.3f}s",
        "",
        "## Status Summary",
        "",
        "| Status | Count |",
        "| --- | ---: |",
    ]

    if status_counts:
        for status, count in status_counts.items():
            lines.append(f"| {markdown_cell(status)} | {count} |")
    else:
        lines.append("| No results | 0 |")

    preview_columns = [
        column
        for column in ["IP Address", "Status", "Latency", "Hostname", "Open Ports"]
        if column in table.columns
    ]
    if preview_columns:
        lines.extend(
            [
                "",
                "## Host Preview",
                "",
                "| " + " | ".join(preview_columns) + " |",
                "| " + " | ".join("---" for _ in preview_columns) + " |",
            ]
        )
        for row in table.rows[:25]:
            lines.append(
                "| "
                + " | ".join(_format_markdown_value(row.get(column)) for column in preview_columns)
                + " |"
            )

        if total > 25:
            lines.extend(["", f"_Showing 25 of {total} hosts._"])

    lines.append("")
    return "\n".join(lines)


def _xlsx_cell(value: Any) -> Any:
    if _is_missing(value):
        return ""  # an empty text cell, as pandas wrote a missing value
    if isinstance(value, datetime):
        # Excel keeps milliseconds, and so did the pandas writer before this.
        return value.replace(microsecond=value.microsecond // 1000 * 1000)
    return value


def _render_xlsx(table: ReportTable) -> bytes:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sheet1"
    sheet.append(list(table.columns))
    for row in sanitize_table(table).rows:
        sheet.append([_xlsx_cell(row.get(column)) for column in table.columns])
        for cell in sheet[sheet.max_row]:
            if isinstance(cell.value, datetime):
                cell.number_format = _XLSX_DATETIME_FORMAT
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _csv_text(value: Any) -> str:
    return "" if _is_missing(value) else str(value)


def _render_csv(table: ReportTable) -> bytes:
    buffer = io.StringIO()
    # os.linesep, as pandas' to_csv used: CRLF on Windows, LF elsewhere.
    writer = csv.writer(buffer, lineterminator=os.linesep)
    writer.writerow(table.columns)
    for row in sanitize_table(table).rows:
        writer.writerow([_csv_text(row.get(column)) for column in table.columns])
    return buffer.getvalue().encode("utf-8")


def _json_value(value: Any) -> Any:
    """A cell as the json report has always held it (pandas' ``to_json``)."""
    if _is_missing(value):
        return None
    if isinstance(value, datetime):
        # Epoch milliseconds, reading a naive time as UTC, exactly as before.
        return calendar.timegm(value.timetuple()) * 1000 + value.microsecond // 1000
    if isinstance(value, float):
        return round(value, 10)
    return value


def _render_json(table: ReportTable) -> bytes:
    records: List[dict] = [
        {column: _json_value(row.get(column)) for column in table.columns} for row in table.rows
    ]
    # Compact, ASCII-only, and with "/" escaped: byte for byte the old format.
    text = json.dumps(records, separators=(",", ":"), ensure_ascii=True).replace("/", "\\/")
    return text.encode("utf-8")


def render_report(table: ReportTable, fmt: str) -> bytes:
    """``table`` rendered in one report format. Raises ValueError for an unknown one."""
    if fmt == "xlsx":
        return _render_xlsx(table)
    if fmt == "csv":
        return _render_csv(table)
    if fmt == "json":
        return _render_json(table)
    if fmt == "jsonl":
        # Rendered exactly like the lines a running scan appends to the file.
        return "".join(jsonl_record(row) for row in table.rows).encode("utf-8")
    if fmt == "md":
        return build_markdown_report(table).encode("utf-8")
    raise ValueError(f"Unsupported report format: {fmt}")


def write_report(table: ReportTable, path: str, fmt: str) -> None:
    """Write ``table`` to ``path`` in one format, replacing the file atomically.

    The whole file is rendered in memory and swapped into place, so a reader
    — or an incremental snapshot interrupted halfway — never finds a report
    that is only partly written. Raises :class:`ValueError` for an unknown
    format so callers can tell "not written" from "silently skipped".
    """
    atomic_write_bytes(path, render_report(table, fmt))


def save_results(
    table: ReportTable, base: str, formats: list[str], timestamp: str | None = None
) -> list[str]:
    """Write the finished report in every requested format.

    ``timestamp`` is passed in when a scan has already been writing reports
    incrementally, so the final write lands on those same files instead of
    creating a second, differently named set.
    """
    ts = timestamp or timestamp_str()
    saved_paths: list[str] = []

    for fmt in formats:
        output_path = f"{base}_{ts}.{fmt}"
        try:
            write_report(table, output_path, fmt)
        except ValueError:
            continue

        saved_paths.append(output_path)

    if saved_paths:
        ui.blank()
        ui.field_list("Saved", saved_paths)

    return saved_paths
