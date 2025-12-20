from rich.console import Console
from rich.table import Table
from rich.text import Text

console = Console()


def print_summary(df):
    summary = df["Status"].value_counts().to_dict()
    total = len(df)
    active = summary.get("Active", 0)
    success_rate = (active / total) * 100 if total else 0

    console.print()  # blank line

    title = Text("IPMG Summary", style="bold cyan")
    console.rule(title)

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Status", style="bold")
    table.add_column("Count", justify="right")

    for status, count in summary.items():
        if status.lower() == "active":
            style = "green"
        elif status.lower() in {"inactive", "unreachable"}:
            style = "yellow"
        else:
            style = "red"

        table.add_row(status, str(count), style=style)

    console.print(table)

    console.print(
        f"[bold]Success Rate:[/bold] " f"[green]{success_rate:.2f}%[/green]"
        if success_rate >= 80
        else f"[bold]Success Rate:[/bold] [red]{success_rate:.2f}%[/red]"
    )
