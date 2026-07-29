"""Rendering and export of scan comparisons produced by :mod:`ipmg.core.diff`."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from rich.text import Text

from ipmg.core.diff import CHANGE_LABELS, ChangeType, ScanDiff, Severity
from ipmg.exceptions import ReportError
from ipmg.reporting import ui
from ipmg.utils.helpers import markdown_escape, timestamp_str

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
    Severity.CRITICAL: "danger",
    Severity.WARNING: "warning",
    Severity.INFO: "info",
}

SEVERITY_GLYPHS: Dict[Severity, str] = {
    Severity.CRITICAL: "fail",
    Severity.WARNING: "warn",
    Severity.INFO: "dot",
}


def _cell(value: Optional[object]) -> str:
    return "" if value is None else str(value)


# ---------------------------------------------------------------- console


def _change_label(change) -> Text:
    """Severity glyph plus the change name, e.g. ``✗ Host offline``."""
    style = SEVERITY_STYLES[change.severity]
    text = Text(f"{ui.glyph(SEVERITY_GLYPHS[change.severity])} ", style=style)
    text.append(change.label, style="ipmg.value")
    return text


def print_diff(diff: ScanDiff, limit: Optional[int] = None) -> None:
    """Render a comparison to the terminal."""
    ui.blank()
    ui.heading("Changes")
    ui.fields(
        [
            ("Baseline", diff.baseline.display(ui.glyph("sep"))),
            ("Current", diff.current.display(ui.glyph("sep"))),
            (
                "Hosts",
                f"{diff.baseline_hosts} {ui.glyph('arrow')} {diff.current_hosts} "
                f"({diff.compared_hosts} compared)",
            ),
        ]
    )
    ui.blank()

    if not diff.has_changes:
        ui.success("No changes detected between these scans.")
        return

    grid = ui.table(
        "Change",
        "IP Address",
        "Hostname",
        "Previous",
        "Current",
        "Delta",
        justify=["left", "left", "left", "left", "left", "right"],
    )

    shown = diff.changes if limit is None else diff.changes[:limit]
    for change in shown:
        grid.add_row(
            _change_label(change),
            change.ip,
            change.hostname or "-",
            _cell(change.previous) or "-",
            _cell(change.current) or "-",
            f"{change.delta:+.1f} ms" if change.delta is not None else "-",
        )
    ui.print_table(grid)

    total = len(diff.changes)
    truncated = limit is not None and total > limit
    severity_counts = diff.severity_counts

    parts = [ui.plural(total, "change") + (f" ({limit} shown)" if truncated else "")]
    parts.extend(
        f"{severity_counts[severity.value]} {severity.value}"
        for severity in (Severity.CRITICAL, Severity.WARNING, Severity.INFO)
        if severity_counts.get(severity.value)
    )
    parts.append(f"{ui.plural(diff.unchanged_hosts, 'host')} unchanged")

    ui.blank()
    ui.joined(parts)


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
        f"- Baseline: {markdown_escape(diff.baseline.display())}",
        f"- Current: {markdown_escape(diff.current.display())}",
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
                markdown_escape(value)
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
        ui.blank()
        ui.field_list("Saved", saved)

    return saved
