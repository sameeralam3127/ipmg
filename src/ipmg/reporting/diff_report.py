"""Rendering and export of scan comparisons produced by :mod:`ipmg.core.diff`."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from rich.columns import Columns
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ipmg.core.diff import CHANGE_LABELS, ChangeType, ScanDiff, Severity
from ipmg.exceptions import ReportError
from ipmg.utils.helpers import console, timestamp_str

DIFF_FORMATS = ("md", "json", "csv")

CSV_COLUMNS = (
    "Change",
    "Severity",
    "IP Address",
    "Hostname",
    "Previous",
    "Current",
    "Delta (ms)",
)

SEVERITY_STYLES: Dict[Severity, str] = {
    Severity.CRITICAL: "ipmg.status.inactive",
    Severity.WARNING: "warning",
    Severity.INFO: "info",
}


def _escape_markdown(value: object) -> str:
    return str(value).replace("|", r"\|")


def _cell(value: Optional[object]) -> str:
    return "" if value is None else str(value)


# ---------------------------------------------------------------- console


def print_diff(diff: ScanDiff, limit: Optional[int] = None) -> None:
    """Render a comparison to the terminal."""
    console.rule(Text("IPMG Change Report", style="ipmg.accent"))
    console.print(
        Panel.fit(
            (
                f"[ipmg.accent]Baseline:[/ipmg.accent] {diff.baseline.display()}\n"
                f"[ipmg.accent]Current:[/ipmg.accent] {diff.current.display()}\n"
                f"[ipmg.accent]Hosts:[/ipmg.accent] "
                f"{diff.baseline_hosts} -> {diff.current_hosts} "
                f"({diff.compared_hosts} compared)"
            ),
            title="[ipmg.accent]Comparison[/ipmg.accent]",
            border_style="ipmg.accent",
        )
    )

    severity_counts = diff.severity_counts
    console.print(
        Columns(
            [
                Panel.fit(
                    Group(
                        Text(str(len(diff.changes)), style="bold bright_white"),
                        Text("Total Changes", style="muted"),
                    ),
                    border_style="ipmg.accent",
                ),
                Panel.fit(
                    Group(
                        Text(str(severity_counts.get("critical", 0)), style="ipmg.status.inactive"),
                        Text("Critical", style="muted"),
                    ),
                    border_style="ipmg.status.inactive",
                ),
                Panel.fit(
                    Group(
                        Text(str(severity_counts.get("warning", 0)), style="warning"),
                        Text("Warning", style="muted"),
                    ),
                    border_style="warning",
                ),
                Panel.fit(
                    Group(
                        Text(str(diff.unchanged_hosts), style="ipmg.status.active"),
                        Text("Unchanged Hosts", style="muted"),
                    ),
                    border_style="ipmg.status.active",
                ),
            ],
            equal=True,
            expand=True,
        )
    )

    if not diff.has_changes:
        console.print(
            Panel.fit(
                Text("No changes detected between these scans.", style="success"),
                border_style="success",
            )
        )
        return

    table = Table(show_header=True, header_style="bold bright_white")
    table.add_column("Change", style="bold")
    table.add_column("IP Address")
    table.add_column("Hostname")
    table.add_column("Previous")
    table.add_column("Current")
    table.add_column("Delta", justify="right")

    shown = diff.changes if limit is None else diff.changes[:limit]
    for change in shown:
        style = SEVERITY_STYLES[change.severity]
        table.add_row(
            f"[{style}]{change.label}[/{style}]",
            change.ip,
            change.hostname or "-",
            _cell(change.previous) or "-",
            _cell(change.current) or "-",
            f"{change.delta:+.1f} ms" if change.delta is not None else "-",
        )

    console.print(table)
    if limit is not None and len(diff.changes) > limit:
        console.print(
            Text(f"Showing {limit} of {len(diff.changes)} changes.", style="muted"),
        )


# ----------------------------------------------------------- serializers


def diff_to_json(diff: ScanDiff) -> str:
    return json.dumps(diff.to_dict(), indent=2)


def diff_to_csv(diff: ScanDiff) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for change in diff.changes:
        writer.writerow(
            [
                change.label,
                change.severity.value,
                change.ip,
                change.hostname,
                _cell(change.previous),
                _cell(change.current),
                "" if change.delta is None else f"{change.delta:+.3f}",
            ]
        )
    return buffer.getvalue()


def _markdown_summary_rows(diff: ScanDiff) -> Iterable[str]:
    counts = diff.counts
    for change_type in ChangeType:
        count = counts.get(change_type.value, 0)
        if count:
            yield f"| {CHANGE_LABELS[change_type]} | {count} |"


def diff_to_markdown(diff: ScanDiff) -> str:
    lines: List[str] = [
        "# IPMG Change Report",
        "",
        f"- Baseline: {_escape_markdown(diff.baseline.display())}",
        f"- Current: {_escape_markdown(diff.current.display())}",
        f"- Hosts: {diff.baseline_hosts} -> {diff.current_hosts} "
        f"({diff.compared_hosts} compared, {diff.unchanged_hosts} unchanged)",
        f"- Total changes: {len(diff.changes)}",
        "",
        "## Change Summary",
        "",
        "| Change | Count |",
        "| --- | ---: |",
    ]

    summary_rows = list(_markdown_summary_rows(diff))
    lines.extend(summary_rows or ["| No changes | 0 |"])

    lines.extend(
        [
            "",
            "## Detected Changes",
            "",
        ]
    )

    if not diff.has_changes:
        lines.extend(["_No changes detected between these scans._", ""])
        return "\n".join(lines)

    lines.extend(
        [
            "| Change | Severity | IP Address | Hostname | Previous | Current | Delta (ms) |",
            "| --- | --- | --- | --- | --- | --- | ---: |",
        ]
    )
    for change in diff.changes:
        delta = "" if change.delta is None else f"{change.delta:+.1f}"
        lines.append(
            "| "
            + " | ".join(
                _escape_markdown(value)
                for value in (
                    change.label,
                    change.severity.value,
                    change.ip,
                    change.hostname,
                    _cell(change.previous),
                    _cell(change.current),
                    delta,
                )
            )
            + " |"
        )

    lines.append("")
    return "\n".join(lines)


_RENDERERS = {
    "md": diff_to_markdown,
    "json": diff_to_json,
    "csv": diff_to_csv,
}


def render_diff(diff: ScanDiff, fmt: str) -> str:
    """Serialise a comparison to one of :data:`DIFF_FORMATS`."""
    try:
        return _RENDERERS[fmt](diff)
    except KeyError as exc:
        raise ReportError(
            f"Unsupported change report format '{fmt}'. Supported: {', '.join(DIFF_FORMATS)}."
        ) from exc


def export_diff(diff: ScanDiff, base: str, formats: Iterable[str]) -> List[str]:
    """Write the comparison to ``{base}_{timestamp}.{fmt}`` files."""
    stamp = timestamp_str()
    saved: List[str] = []

    for fmt in formats:
        content = render_diff(diff, fmt)
        path = Path(f"{base}_{stamp}.{fmt}")
        try:
            path.write_text(content, encoding="utf-8")
        except OSError as exc:
            raise ReportError(f"Could not write change report '{path}': {exc}") from exc
        saved.append(str(path))

    if saved:
        console.print(
            Panel.fit(
                "\n".join(f"[success]-[/success] {path}" for path in saved),
                title="[success]Saved Change Reports[/success]",
                border_style="success",
            )
        )

    return saved
