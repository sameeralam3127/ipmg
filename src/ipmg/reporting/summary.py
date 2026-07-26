from typing import Any, Dict, Sequence

from rich.columns import Columns
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ipmg.utils.helpers import console

SCAN_STATE_STYLES = {
    "complete": "success",
    "running": "warning",
    "cancelled": "muted",
    "failed": "danger",
}

STATUS_STYLES = {
    "Active": "ipmg.status.active",
    "Inactive": "ipmg.status.inactive",
    "Timeout": "ipmg.status.timeout",
    "Unreachable": "ipmg.status.unreachable",
    "Error": "ipmg.status.error",
    "Invalid IP": "ipmg.status.invalid",
}


def print_summary(df, batch_timestamp, duration_seconds: float) -> None:
    summary = df["Status"].value_counts().to_dict()
    total = len(df)
    active = summary.get("Active", 0)
    successful = active + summary.get("Unreachable", 0)
    active_rate = (active / total) * 100 if total else 0
    completion_rate = (successful / total) * 100 if total else 0

    console.rule(Text("IPMG Summary", style="ipmg.accent"))

    table = Table(show_header=True, header_style="bold bright_white")
    table.add_column("Status", style="bold")
    table.add_column("Count", justify="right", style="bright_white")

    for status, count in summary.items():
        table.add_row(
            f"[{STATUS_STYLES.get(status, 'info')}]{status}[/{STATUS_STYLES.get(status, 'info')}]",
            str(count),
        )

    metrics = Columns(
        [
            Panel.fit(
                Group(
                    Text(str(total), style="bold bright_white"),
                    Text("Total Hosts", style="muted"),
                ),
                border_style="ipmg.accent",
            ),
            Panel.fit(
                Group(
                    Text(f"{active_rate:.2f}%", style="ipmg.status.active"),
                    Text("Active Rate", style="muted"),
                ),
                border_style="ipmg.status.active",
            ),
            Panel.fit(
                Group(
                    Text(f"{completion_rate:.2f}%", style="info"),
                    Text("Completion Rate", style="muted"),
                ),
                border_style="info",
            ),
            Panel.fit(
                Group(
                    Text(f"{duration_seconds:.2f}s", style="warning"),
                    Text("Scan Duration", style="muted"),
                ),
                border_style="warning",
            ),
        ],
        equal=True,
        expand=True,
    )

    console.print(table)
    console.print(metrics)
    console.print(
        Panel.fit(
            Text(
                batch_timestamp.isoformat(sep=" ", timespec="seconds"),
                style="bold bright_white",
            ),
            title="[ipmg.accent]Batch Timestamp[/ipmg.accent]",
            border_style="ipmg.accent",
        )
    )


def _active_rate(scan: Dict[str, Any]) -> str:
    total = scan.get("total") or 0
    active = (scan.get("status_counts") or {}).get("Active", 0)
    return f"{(active / total) * 100:.1f}%" if total else "-"


def print_scan_history(scans: Sequence[Dict[str, Any]]) -> None:
    """Render stored scans, newest first."""
    console.rule(Text("IPMG Scan History", style="ipmg.accent"))

    if not scans:
        console.print(
            Panel.fit(
                Text("No scans stored yet. Run a scan to build history.", style="warning"),
                border_style="warning",
            )
        )
        return

    table = Table(show_header=True, header_style="bold bright_white")
    table.add_column("#", justify="right", style="bold")
    table.add_column("Started")
    table.add_column("Source")
    table.add_column("Hosts", justify="right")
    table.add_column("Active", justify="right")
    table.add_column("Avg Latency", justify="right")
    table.add_column("Duration", justify="right")
    table.add_column("State")

    for scan in scans:
        state = str(scan.get("status", ""))
        style = SCAN_STATE_STYLES.get(state, "info")
        avg_latency = scan.get("avg_latency")
        duration = scan.get("duration_s")
        table.add_row(
            str(scan.get("id", "")),
            str(scan.get("started_at", "")),
            str(scan.get("source", "")),
            str(scan.get("total", 0)),
            _active_rate(scan),
            f"{avg_latency:.1f} ms" if avg_latency is not None else "-",
            f"{duration:.1f}s" if duration is not None else "-",
            f"[{style}]{state}[/{style}]",
        )

    console.print(table)
