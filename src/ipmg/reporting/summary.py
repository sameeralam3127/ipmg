"""Terminal summaries for a finished scan and for the stored history."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import Any

from rich.text import Text

from ipmg.core.diff import format_uptime
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
    "interrupted": "danger",
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


def print_http_checks(results: Sequence[Any]) -> None:
    """One row per ``--http-check`` URL: passed or failed, status, time, and why."""
    ui.blank()
    ui.heading("HTTP checks")
    grid = ui.table(
        "",
        "URL",
        "Status",
        "Time",
        "Detail",
        justify=["left", "left", "right", "right", "left"],
        min_widths=[6, None, 6, 8, None],
    )
    for check in results:
        detail = check.error
        if not detail and check.final_url and check.final_url != check.url:
            detail = f"{ui.glyph('arrow')} {check.final_url}"
        if not detail and check.cert_expires:
            detail = f"certificate expires {check.cert_expires}"
        grid.add_row(
            Text(
                f"{ui.glyph('ok' if check.ok else 'fail')} {check.outcome}",
                style="success" if check.ok else "danger",
            ),
            check.url,
            check.summary,
            ui.format_latency(check.response_ms),
            Text(detail, style="muted"),
        )
    ui.print_table(grid)
    failed = sum(1 for check in results if not check.ok)
    ui.blank()
    ui.joined([ui.plural(len(results), "URL"), f"{failed} failed"])


def interface_counts(device: Any) -> str:
    """``20 up · 2 down`` for a polled device's interfaces."""
    if not device.interfaces:
        return "-"
    return f"{device.interfaces_up} up {ui.glyph('sep')} {len(device.interfaces_down)} down"


#: Characters of detail per SNMP row; a sysDescr can run to hundreds.
_SNMP_DETAIL_CHARS = 72


def _snmp_detail(device: Any) -> str:
    text = _snmp_reason(device)
    if len(text) > _SNMP_DETAIL_CHARS:
        text = text[: _SNMP_DETAIL_CHARS - 1].rstrip() + ui.glyph("ellipsis")
    return text


def _snmp_reason(device: Any) -> str:
    if device.error:
        return device.error
    down = [interface.name for interface in device.interfaces_down]
    if down:
        shown = ", ".join(down[:3])
        return f"down: {shown}" + (f" +{len(down) - 3} more" if len(down) > 3 else "")
    return device.sys_descr.splitlines()[0] if device.sys_descr else ""


def print_snmp(results: Sequence[Any]) -> None:
    """One row per ``--snmp`` device: answered or not, name, uptime, interfaces, and why."""
    ui.blank()
    ui.heading("SNMP")
    grid = ui.table(
        "",
        "Host",
        "Name",
        "Uptime",
        "Interfaces",
        "Detail",
        justify=["left", "left", "left", "right", "right", "left"],
        min_widths=[6, 15, 12, 7, 13, None],
    )
    for device in results:
        grid.add_row(
            Text(
                f"{ui.glyph('ok' if device.ok else 'fail')} {device.outcome}",
                style="success" if device.ok else "danger",
            ),
            device.ip,
            device.sys_name or "-",
            format_uptime(device.uptime_s),
            interface_counts(device),
            Text(_snmp_detail(device), style="muted"),
        )
    ui.print_table(grid)
    failed = sum(1 for device in results if not device.ok)
    down = sum(len(device.interfaces_down) for device in results)
    ui.blank()
    ui.joined(
        [
            ui.plural(len(results), "device"),
            f"{failed} not answering",
            ui.plural(down, "interface") + " down",
        ]
    )


def _short_timestamp(value: Any) -> str:
    """Drop the seconds: history is browsed by date and time, not by second."""
    text = str(value or "")
    return text[:16] if len(text) == 19 and text[13] == ":" else text


def _active_rate(scan: dict[str, Any]) -> str:
    total = scan.get("total") or 0
    active = (scan.get("status_counts") or {}).get("Active", 0)
    return ui.format_percent((active / total) * 100) if total else "-"


def print_scan_history(scans: Sequence[dict[str, Any]]) -> None:
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
