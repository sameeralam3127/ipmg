"""Presentation primitives for the IPMG command line.

The house style is deliberately flat: no boxes, one accent colour, dim
labels in a fixed column, and values left-aligned next to them. Every
glyph degrades to ASCII on terminals that cannot encode it, so the same
code renders on a modern terminal and on a legacy Windows console.
"""

from __future__ import annotations

from typing import Iterable, Optional, Sequence, Tuple

from rich.padding import Padding
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from rich.text import Text

from ipmg import __version__
from ipmg.utils.helpers import console

INDENT = "  "
LABEL_WIDTH = 9
BAR_WIDTH = 22

_UNICODE_GLYPHS = {
    "ok": "✓",
    "fail": "✗",
    "warn": "▲",
    "dot": "●",
    "arrow": "→",
    "sep": "·",
    "dash": "—",
    "bar_full": "━",
    "bar_empty": "─",
}

_ASCII_GLYPHS = {
    "ok": "+",
    "fail": "x",
    "warn": "!",
    "dot": "*",
    "arrow": "->",
    "sep": "-",
    "dash": "-",
    "bar_full": "#",
    "bar_empty": ".",
}

_glyphs: Optional[dict] = None


def _detect_glyphs(target=None) -> dict:
    """Pick the glyph set the target console can encode."""
    target = console if target is None else target

    if target.legacy_windows:
        return _ASCII_GLYPHS

    encoding = getattr(target.file, "encoding", None) or "utf-8"
    try:
        "".join(_UNICODE_GLYPHS.values()).encode(encoding)
    except (LookupError, UnicodeEncodeError):
        return _ASCII_GLYPHS
    return _UNICODE_GLYPHS


def glyph(name: str) -> str:
    """Return a symbol the current terminal can actually render."""
    global _glyphs

    if _glyphs is None:
        _glyphs = _detect_glyphs()
    return _glyphs[name]


def reset_glyphs() -> None:
    """Forget the cached glyph set (used when the console changes)."""
    global _glyphs

    _glyphs = None


# ------------------------------------------------------------------ blocks


def blank() -> None:
    console.line()


def header(subtitle: Optional[str] = None) -> None:
    """The one-line product banner: ``ipmg 1.6.1 · scan``."""
    text = Text(INDENT)
    text.append("ipmg", style="ipmg.brand")
    text.append(f" {__version__}", style="muted")
    if subtitle:
        text.append(f"  {glyph('sep')}  {subtitle}", style="muted")
    console.print(text)


def heading(title: str) -> None:
    console.print(Text(INDENT + title, style="ipmg.heading"))


def field(label: str, value: object, value_style: str = "ipmg.value") -> None:
    """One aligned ``label   value`` line."""
    text = Text(INDENT)
    text.append(f"{label:<{LABEL_WIDTH}}", style="ipmg.label")
    text.append(str(value), style=value_style)
    console.print(text)


def fields(pairs: Iterable[Tuple[str, object]]) -> None:
    for label, value in pairs:
        field(label, value)


def field_list(label: str, values: Sequence[object], value_style: str = "ipmg.value") -> None:
    """A label followed by one value per line, aligned under the first."""
    for index, value in enumerate(values):
        field(label if index == 0 else "", value, value_style=value_style)


def note(message: str) -> None:
    console.print(Text(INDENT + message, style="muted"))


def _status(symbol: str, message: str, style: str) -> None:
    text = Text(INDENT)
    text.append(f"{symbol} ", style=style)
    text.append(message, style="ipmg.value")
    console.print(text)


def success(message: str) -> None:
    _status(glyph("ok"), message, "success")


def warn(message: str) -> None:
    _status(glyph("warn"), message, "warning")


def error(message: str) -> None:
    _status(glyph("fail"), message, "danger")


def joined(parts: Sequence[str]) -> None:
    """A dim footer line: ``2 hosts · 100% active · 0.08s``."""
    if not parts:
        return
    console.print(Text(INDENT + f" {glyph('sep')} ".join(parts), style="muted"))


def bar(fraction: float, width: int = BAR_WIDTH, style: str = "ipmg.bar") -> Text:
    """A proportional block bar, clamped to [0, 1]."""
    fraction = min(max(fraction, 0.0), 1.0)
    filled = int(round(fraction * width))
    text = Text(glyph("bar_full") * filled, style=style)
    text.append(glyph("bar_empty") * (width - filled), style="ipmg.bar.empty")
    return text


def table(
    *columns: str,
    justify: Optional[Sequence[str]] = None,
    min_widths: Optional[Sequence[Optional[int]]] = None,
) -> Table:
    """A borderless table with dim headers; pass '' for unlabelled columns.

    ``min_widths`` protects columns that must stay readable on a narrow
    terminal — the ones without a minimum give up their space first.
    """
    grid = Table(
        box=None,
        pad_edge=False,
        show_edge=False,
        show_header=any(columns),
        header_style="ipmg.label",
        padding=(0, 2, 0, 0),
    )
    for index, name in enumerate(columns):
        grid.add_column(
            name,
            justify=justify[index] if justify and index < len(justify) else "left",
            min_width=min_widths[index] if min_widths and index < len(min_widths) else None,
            # Rows stay on one line: a wrapped timestamp is harder to read
            # than a truncated one.
            overflow="ellipsis",
            no_wrap=True,
        )
    return grid


def print_table(grid: Table) -> None:
    console.print(Padding(grid, (0, 0, 0, len(INDENT)), expand=False))


def progress(description: str) -> Progress:
    """A compact, self-erasing progress bar (silent when output is piped)."""
    return Progress(
        TextColumn(INDENT),
        SpinnerColumn(style="ipmg.accent", finished_text=" "),
        TextColumn(f"[ipmg.value]{description}"),
        BarColumn(
            bar_width=BAR_WIDTH,
            complete_style="ipmg.bar",
            finished_style="ipmg.bar",
            style="ipmg.bar.empty",
            pulse_style="ipmg.bar",
        ),
        TextColumn("[muted]{task.percentage:>3.0f}%"),
        TextColumn("[muted]{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
        # A progress bar in a log file or a pipe is noise, not information.
        disable=not console.is_terminal,
    )


def format_duration(seconds: Optional[float]) -> str:
    if seconds is None:
        return "-"
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    if seconds < 60:
        return f"{seconds:.2f}s"
    minutes, remainder = divmod(seconds, 60)
    return f"{int(minutes)}m {remainder:.0f}s"


def format_latency(latency: Optional[float]) -> str:
    return "-" if latency is None else f"{latency:.1f} ms"


def format_percent(value: float) -> str:
    return f"{value:.1f}%"


def plural(count: int, singular: str, suffix: str = "s") -> str:
    """``3 hosts`` / ``1 host``."""
    return f"{count} {singular}" if count == 1 else f"{count} {singular}{suffix}"
