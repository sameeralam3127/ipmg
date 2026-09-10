"""Live per-host output for a scan that is still running.

A scan of a /24 can take a minute, and printing nothing until the last
host answers hides the very thing the operator is waiting for. Streaming
mode prints one aligned row per finished host above a progress bar that
also carries the running count of hosts that answered.

Rows are printed, never redrawn: the terminal's own scrollback keeps the
history, so a 65k-host scan costs no more memory than a two-host one.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, List, Tuple

from rich.text import Text

from ipmg.core.engine import HostResult, ResultCallback, ScanConfig
from ipmg.reporting import ui
from ipmg.reporting.frames import format_open_ports
from ipmg.reporting.summary import status_dot
from ipmg.utils.helpers import console

#: Seconds between progress-bar redraws when the caller does not choose.
DEFAULT_REFRESH_S = 0.25
MIN_REFRESH_S = 0.05
MAX_REFRESH_S = 5.0

STATUS_WIDTH = 14
IP_WIDTH = 18
LATENCY_WIDTH = 11
HOSTNAME_WIDTH = 32
PORTS_WIDTH = 26

#: Blank space kept between columns so truncated cells never touch.
COLUMN_GAP = 2


@dataclass(frozen=True)
class StreamOptions:
    """How a running scan should report itself while it works."""

    enabled: bool = False
    all_hosts: bool = False
    refresh_s: float = DEFAULT_REFRESH_S

    def clamped(self) -> "StreamOptions":
        return StreamOptions(
            enabled=self.enabled,
            all_hosts=self.all_hosts,
            refresh_s=min(max(self.refresh_s, MIN_REFRESH_S), MAX_REFRESH_S),
        )


def _cell(value: str, width: int, style: str, justify: str = "left") -> Text:
    """One fixed-width column: truncated when long, padded to the full width."""
    text = Text(value, style=style, no_wrap=True)
    text.truncate(width - COLUMN_GAP, overflow="ellipsis")
    # Align inside the content width, then add the gap, so a right-aligned
    # value keeps its distance from the column that follows it.
    text.align(justify, width - COLUMN_GAP)
    text.pad_right(COLUMN_GAP)
    return text


def _columns(config: ScanConfig) -> List[Tuple[str, int, str]]:
    """The columns this scan's configuration actually produces values for."""
    columns = [
        ("Status", STATUS_WIDTH, "left"),
        ("Host", IP_WIDTH, "left"),
        ("Latency", LATENCY_WIDTH, "right"),
    ]
    if config.resolve:
        columns.append(("Name", HOSTNAME_WIDTH, "left"))
    if config.scan_ports:
        columns.append(("Open ports", PORTS_WIDTH, "left"))
    return columns


def format_header(config: ScanConfig) -> Text:
    """The dim column header printed once, above the streamed rows."""
    header = Text(ui.INDENT)
    for name, width, justify in _columns(config):
        header.append_text(_cell(name, width, "ipmg.label", justify))
    header.rstrip()
    return header


def format_result(result: HostResult, config: ScanConfig) -> Text:
    """One streamed row, aligned with :func:`format_header`."""
    dash = ui.glyph("dash")
    status = status_dot(result.status)
    status.align("left", STATUS_WIDTH - COLUMN_GAP)
    status.pad_right(COLUMN_GAP)

    row = Text(ui.INDENT)
    row.append_text(status)
    row.append_text(_cell(result.ip, IP_WIDTH, "ipmg.value"))
    row.append_text(_cell(ui.format_latency(result.latency), LATENCY_WIDTH, "muted", "right"))
    if config.resolve:
        row.append_text(_cell(result.hostname or dash, HOSTNAME_WIDTH, "muted"))
    if config.scan_ports:
        row.append_text(_cell(format_open_ports(result.open_ports) or dash, PORTS_WIDTH, "muted"))
    row.rstrip()
    return row


@contextmanager
def scan_display(
    total: int, config: ScanConfig, options: StreamOptions
) -> Iterator[ResultCallback]:
    """Yield the ``on_result`` callback that reports a scan while it runs.

    Without streaming that is just a progress bar. With it, every result
    (or only the hosts that answered) is printed the moment it lands, and
    the bar gains a live count of active hosts.
    """
    options = options.clamped()

    if not options.enabled:
        with ui.progress("Scanning") as progress:
            task_id = progress.add_task("scan", total=total)
            yield lambda _result, _done, _total: progress.advance(task_id)
        return

    ui.blank()
    ui.heading("Live")
    console.print(format_header(config), no_wrap=True, overflow="ellipsis", crop=True)

    with ui.progress(
        "Scanning",
        columns=(ui.active_column(),),
        refresh_per_second=1 / options.refresh_s,
    ) as progress:
        task_id = progress.add_task("scan", total=total, active=0)
        active = 0

        def on_result(result: HostResult, done: int, _total: int) -> None:
            nonlocal active

            if result.status == "Active":
                active += 1
            progress.update(task_id, completed=done, active=active)

            if options.all_hosts or result.status == "Active":
                # Printing through the progress console keeps the bar pinned
                # below the rows instead of letting them overwrite it.
                progress.console.print(
                    format_result(result, config), no_wrap=True, overflow="ellipsis", crop=True
                )

        yield on_result
