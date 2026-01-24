from rich.console import Console
from rich.table import Table
from rich.text import Text

console = Console()


def print_summary(df) -> None:
    summary = df["Status"].value_counts().to_dict()
    total = len(df)
    active = summary.get("Active", 0)
    rate = (active / total) * 100 if total else 0

    console.rule(Text("IPMG Summary", style="bold cyan"))

    table = Table(show_header=True)
    table.add_column("Status")
    table.add_column("Count", justify="right")

    for status, count in summary.items():
        table.add_row(status, str(count))

    console.print(table)
    console.print(f"Success Rate: {rate:.2f}%")
