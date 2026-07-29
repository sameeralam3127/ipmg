import ipaddress
from pathlib import Path
from typing import Iterable

import pandas as pd

from ipmg.core.ping import validate_ip
from ipmg.exceptions import FileIOError
from ipmg.reporting import ui
from ipmg.utils.helpers import markdown_escape, timestamp_str

SUPPORTED_INPUT_SUFFIXES = {".xlsx", ".xls", ".csv", ".txt", ".list"}
MAX_EXPANDED_TARGETS = 65_536


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


def load_targets(source: str) -> list[str]:
    path = Path(source)

    if path.exists():
        suffix = path.suffix.lower()
        if suffix in {".xlsx", ".xls"}:
            return _load_from_dataframe(pd.read_excel(path), source)
        if suffix == ".csv":
            return _load_from_dataframe(pd.read_csv(path), source)
        if suffix in {".txt", ".list"}:
            return _load_from_text(source)
        raise FileIOError(
            f"Unsupported input file type '{suffix or '<none>'}'. "
            f"Supported types: {', '.join(sorted(SUPPORTED_INPUT_SUFFIXES))}."
        )

    expanded = _expand_target(source.strip())
    if expanded:
        return expanded

    raise FileIOError(
        f"Input '{source}' is neither a readable file nor a valid IP/CIDR/range target."
    )


def create_sample_file(path: str) -> None:
    df = pd.DataFrame({"IP Address": ["8.8.8.8", "1.1.1.1"]})
    suffix = Path(path).suffix.lower()

    if suffix == ".csv":
        df.to_csv(path, index=False)
        return

    if suffix in {".txt", ".list"}:
        Path(path).write_text("8.8.8.8\n1.1.1.1\n", encoding="utf-8")
        return

    df.to_excel(path, index=False)


def _format_markdown_value(value) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return markdown_escape(value)


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
            lines.append(f"| {markdown_escape(status)} | {count} |")
    else:
        lines.append("| No results | 0 |")

    preview_columns = [
        column for column in ["IP Address", "Status", "Latency", "Hostname"] if column in df.columns
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


def save_results(df, base: str, formats: list[str]) -> list[str]:
    ts = timestamp_str()
    saved_paths: list[str] = []

    for fmt in formats:
        if fmt == "xlsx":
            output_path = f"{base}_{ts}.xlsx"
            df.to_excel(output_path, index=False)
        elif fmt == "csv":
            output_path = f"{base}_{ts}.csv"
            df.to_csv(output_path, index=False)
        elif fmt == "json":
            output_path = f"{base}_{ts}.json"
            df.to_json(output_path, orient="records")
        elif fmt == "md":
            output_path = f"{base}_{ts}.md"
            Path(output_path).write_text(build_markdown_report(df), encoding="utf-8")
        else:
            continue

        saved_paths.append(output_path)

    if saved_paths:
        ui.blank()
        ui.field_list("Saved", saved_paths)

    return saved_paths
