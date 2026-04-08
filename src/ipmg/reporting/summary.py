from rich.columns import Columns
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ipmg.utils.helpers import console

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
        table.add_row(f"[{STATUS_STYLES.get(status, 'info')}]{status}[/{STATUS_STYLES.get(status, 'info')}]", str(count))

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
