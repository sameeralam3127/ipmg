from __future__ import annotations

import io
import ipaddress
import json
from pathlib import Path
from typing import Any, Iterable, Sequence

import pandas as pd

from ipmg.core.ping import validate_ip
from ipmg.exceptions import FileIOError
from ipmg.infrastructure.incremental import atomic_write_bytes, frame_rows, jsonl_record
from ipmg.reporting import ui
from ipmg.utils.helpers import markdown_cell, spreadsheet_escape, timestamp_str

SUPPORTED_INPUT_SUFFIXES = {".xlsx", ".xls", ".csv", ".json", ".txt", ".list"}
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
        raise FileIOError(
            f"CIDR target '{target}' expands to too many hosts. "
            f"Maximum allowed hosts: {MAX_EXPANDED_TARGETS}."
        )

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


def _load_from_dataframe(df: pd.DataFrame, source: str) -> list[str]:
    if "IP Address" not in df.columns:
        raise FileIOError(f"Input file '{source}' must contain an 'IP Address' column.")

    values = (value.strip() for value in df["IP Address"].dropna().astype(str) if value.strip())
    targets = _collect_targets(values, f"'{source}'", strict=False)

    if not targets:
        raise FileIOError(f"No valid IP targets were found in '{source}'.")

    return targets


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
        if suffix in {".xlsx", ".xls"}:
            return _load_from_dataframe(pd.read_excel(path), source)
        if suffix == ".csv":
            return _load_from_dataframe(pd.read_csv(path), source)
        if suffix == ".json":
            return _load_from_json(source)
        if suffix in {".txt", ".list"}:
            return _load_from_text(source)
        raise FileIOError(
            f"Unsupported input file type '{suffix or '<none>'}'. "
            f"Supported types: {', '.join(sorted(SUPPORTED_INPUT_SUFFIXES))}."
        )

    if path.suffix.lower() in SUPPORTED_INPUT_SUFFIXES:
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


def create_sample_file(path: str) -> None:
    df = pd.DataFrame({"IP Address": ["8.8.8.8", "1.1.1.1"]})
    suffix = Path(path).suffix.lower()

    if suffix == ".csv":
        df.to_csv(path, index=False)
        return

    if suffix == ".json":
        Path(path).write_text(json.dumps(["8.8.8.8", "1.1.1.1"], indent=2) + "\n", encoding="utf-8")
        return

    if suffix in {".txt", ".list"}:
        Path(path).write_text("8.8.8.8\n1.1.1.1\n", encoding="utf-8")
        return

    df.to_excel(path, index=False)


def sanitize_export_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Copy ``df`` with every text cell neutralised for spreadsheet export.

    Applied to CSV and XLSX output on both the CLI and dashboard paths so a
    hostname harvested from reverse DNS cannot smuggle a formula into the
    operator's spreadsheet. See :func:`spreadsheet_escape`.
    """
    safe = df.copy()
    for column in safe.columns:
        # Every column is walked rather than filtered by dtype: pandas stores
        # text as ``object`` or ``str`` depending on the version, and numbers
        # pass straight through the isinstance guard anyway.
        safe[column] = safe[column].map(
            lambda value: spreadsheet_escape(value) if isinstance(value, str) else value,
            na_action="ignore",
        )
    return safe


def _format_markdown_value(value) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return markdown_cell(value)


def build_markdown_report(df: pd.DataFrame) -> str:
    total = len(df)
    status_counts = df["Status"].value_counts().to_dict() if "Status" in df else {}
    active = status_counts.get("Active", 0)
    active_rate = (active / total) * 100 if total else 0
    duration = df["Scan Duration (s)"].max() if "Scan Duration (s)" in df and total else 0
    batch_timestamp = ""
    if "Batch Timestamp" in df and total:
        batch_timestamp = str(df["Batch Timestamp"].iloc[0])

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
        if column in df.columns
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
        for _, row in df.head(25).iterrows():
            lines.append(
                "| "
                + " | ".join(_format_markdown_value(row[column]) for column in preview_columns)
                + " |"
            )

        if total > 25:
            lines.extend(["", f"_Showing 25 of {total} hosts._"])

    lines.append("")
    return "\n".join(lines)


def write_report(df: pd.DataFrame, path: str, fmt: str) -> None:
    """Write ``df`` to ``path`` in one format, replacing the file atomically.

    The whole file is rendered in memory and swapped into place, so a reader
    — or an incremental snapshot interrupted halfway — never finds a report
    that is only partly written. Raises :class:`ValueError` for an unknown
    format so callers can tell "not written" from "silently skipped".
    """
    if fmt == "xlsx":
        buffer = io.BytesIO()
        sanitize_export_frame(df).to_excel(buffer, index=False)
        data = buffer.getvalue()
    elif fmt == "csv":
        data = sanitize_export_frame(df).to_csv(index=False).encode("utf-8")
    elif fmt == "json":
        data = df.to_json(orient="records").encode("utf-8")
    elif fmt == "jsonl":
        # Rendered row by row rather than through pandas, so the finished file
        # is written exactly like the one a running scan appends to.
        data = "".join(jsonl_record(row) for row in frame_rows(df)).encode("utf-8")
    elif fmt == "md":
        data = build_markdown_report(df).encode("utf-8")
    else:
        raise ValueError(f"Unsupported report format: {fmt}")

    atomic_write_bytes(path, data)


def save_results(df, base: str, formats: list[str], timestamp: str | None = None) -> list[str]:
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
            write_report(df, output_path, fmt)
        except ValueError:
            continue

        saved_paths.append(output_path)

    if saved_paths:
        ui.blank()
        ui.field_list("Saved", saved_paths)

    return saved_paths
