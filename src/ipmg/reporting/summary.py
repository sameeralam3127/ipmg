"""Terminal summaries for a finished scan and for the stored history."""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Sequence

from rich.text import Text

from ipmg.reporting import ui

STATUS_STYLES = {
    "Active": "ipmg.status.active",
    "Inactive": "ipmg.status.inactive",
    "Timeout": "ipmg.status.timeout",
    "Unreachable": "ipmg.status.unreachable",
    "Error": "ipmg.status.error",
    "Invalid IP": "ipmg.status.invalid",
}

SCAN_STATE_STYLES = {
    "complete": "success",
    "running": "warning",
    "cancelled": "muted",
    "failed": "danger",
}


def _status_style(status: str) -> str:
    return STATUS_STYLES.get(status, "info")


def status_dot(status: str) -> Text:
    """A coloured bullet plus the status name."""
    text = Text(f"{ui.glyph('dot')} ", style=_status_style(status))
    text.append(status, style="ipmg.value")
    return text


def _average_latency(table) -> float | None:
    active = [
        row["Latency"]
        for row in table.rows
        if row.get("Status") == "Active" and isinstance(row.get("Latency"), (int, float))
    ]
    return sum(active) / len(active) if active else None


def print_summary(table, batch_timestamp, duration_seconds: float) -> None:
    """Status breakdown plus a one-line scorecard for a finished scan."""
    counts = dict(Counter(table.column("Status")))
    total = len(table)
    active = counts.get("Active", 0)
    active_rate = (active / total) * 100 if total else 0.0

    ui.blank()
    ui.heading("Results")

    if not total:
        ui.note("No hosts were scanned.")
        return

    grid = ui.table("", "", "", "", justify=["left", "right", "left", "right"])
    for status, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        grid.add_row(
            status_dot(status),
            str(count),
            ui.bar(count / total, style=_status_style(status)),
            ui.format_percent((count / total) * 100),
        )
    ui.print_table(grid)

    average = _average_latency(table)
    ui.blank()
    ui.joined(
        [
            ui.plural(total, "host"),
            f"{ui.format_percent(active_rate)} active",
            f"{ui.format_latency(average)} avg" if average is not None else "no latency data",
            ui.format_duration(duration_seconds),
            batch_timestamp.isoformat(sep=" ", timespec="seconds"),
        ]
    )


def _short_timestamp(value: Any) -> str:
    """Drop the seconds: history is browsed by date and time, not by second."""
    text = str(value or "")
    return text[:16] if len(text) == 19 and text[13] == ":" else text


def _active_rate(scan: Dict[str, Any]) -> str:
    total = scan.get("total") or 0
    active = (scan.get("status_counts") or {}).get("Active", 0)
    return ui.format_percent((active / total) * 100) if total else "-"


def print_scan_history(scans: Sequence[Dict[str, Any]]) -> None:
    """Render stored scans, newest first."""
    ui.blank()
    ui.heading("Scan history")

    if not scans:
        ui.note(f"No scans stored yet {ui.glyph('dash')} run a scan to start building history.")
        return

    grid = ui.table(
        "#",
        "Started",
        "Source",
        "Hosts",
        "Active",
        "Latency",
        "Duration",
        "State",
        justify=["right", "left", "left", "right", "right", "right", "right", "left"],
        # Source is the only column allowed to shrink on a narrow terminal.
        min_widths=[1, 16, None, 5, 6, 8, 8, 9],
    )
    for scan in scans:
        state = str(scan.get("status", ""))
        style = SCAN_STATE_STYLES.get(state, "info")
        grid.add_row(
            str(scan.get("id", "")),
            _short_timestamp(scan.get("started_at")),
            str(scan.get("source", "")),
            str(scan.get("total", 0)),
            _active_rate(scan),
            ui.format_latency(scan.get("avg_latency")),
            ui.format_duration(scan.get("duration_s")),
            Text(state, style=style),
        )
    ui.print_table(grid)

    ui.blank()
    ui.joined([ui.plural(len(scans), "scan")])
