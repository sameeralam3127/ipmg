import logging
import socket
from datetime import datetime
from typing import Optional

from rich.console import Console
from rich.logging import RichHandler
from rich.theme import Theme
from rich.traceback import install as install_rich_traceback

RICH_THEME = Theme(
    {
        "info": "bold cyan",
        "warning": "bold yellow",
        "danger": "bold red",
        "success": "bold green",
        "muted": "dim white",
        "ipmg.accent": "bold bright_blue",
        "ipmg.status.active": "bold green",
        "ipmg.status.inactive": "bold red",
        "ipmg.status.timeout": "bold yellow",
        "ipmg.status.unreachable": "bold magenta",
        "ipmg.status.error": "bold bright_red",
        "ipmg.status.invalid": "bold bright_yellow",
    }
)

console = Console(theme=RICH_THEME)


def configure_logging(verbose: bool) -> None:
    install_rich_traceback(show_locals=verbose)
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True, show_path=verbose)],
        force=True,
    )


def resolve_hostname(ip: str) -> str:
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return "Unresolvable"


def current_timestamp() -> datetime:
    return datetime.now()


def timestamp_str() -> str:
    return current_timestamp().strftime("%Y%m%d_%H%M%S")


def clamp_int(value: int, minimum: Optional[int], maximum: Optional[int]) -> int:
    if minimum is not None:
        value = max(value, minimum)

    if maximum is not None:
        value = min(value, maximum)

    return value
