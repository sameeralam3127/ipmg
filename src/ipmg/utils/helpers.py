import logging
import socket
import sys
import threading
import time
from datetime import datetime
from typing import Dict, Optional, Tuple

from rich.console import Console
from rich.logging import RichHandler
from rich.theme import Theme
from rich.traceback import install as install_rich_traceback

RICH_THEME = Theme(
    {
        "info": "cyan",
        "warning": "yellow",
        "danger": "red",
        "success": "green",
        "muted": "dim",
        # Layout roles: one accent, dim labels, plain values.
        "ipmg.accent": "bold bright_blue",
        "ipmg.brand": "bold bright_blue",
        "ipmg.heading": "bold",
        "ipmg.label": "dim",
        "ipmg.value": "default",
        "ipmg.bar": "bright_blue",
        "ipmg.bar.empty": "dim",
        "ipmg.status.active": "green",
        "ipmg.status.inactive": "red",
        "ipmg.status.timeout": "yellow",
        "ipmg.status.unreachable": "magenta",
        "ipmg.status.error": "bright_red",
        "ipmg.status.invalid": "bright_yellow",
    }
)


def _tolerate_unencodable_output() -> None:
    """Substitute characters the terminal cannot encode instead of crashing.

    Scan results carry data we do not control (IDN hostnames, file names), so
    a byte that ASCII cannot represent must never abort the whole command.
    """
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is None:
        return
    try:
        reconfigure(errors="replace")
    except (OSError, ValueError):  # pragma: no cover - stream already detached
        pass


_tolerate_unencodable_output()

# No file= here on purpose: rich resolves sys.stdout per write, which keeps
# output capturable by pytest and redirectable by callers.
console = Console(theme=RICH_THEME)


class HostnameCache:
    """Thread-safe, TTL-based cache for reverse DNS lookups."""

    def __init__(self, ttl_seconds: int = 300) -> None:
        self.ttl_seconds = max(ttl_seconds, 0)
        self._cache: Dict[str, Tuple[float, str]] = {}
        self._in_flight: Dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    def resolve(self, ip: str) -> str:
        with self._lock:
            cached = self._cache.get(ip)
            if cached and cached[0] > time.monotonic():
                return cached[1]

            completed = self._in_flight.get(ip)
            if completed is None:
                completed = threading.Event()
                self._in_flight[ip] = completed
                is_resolver = True
            else:
                is_resolver = False

        if not is_resolver:
            completed.wait()
            with self._lock:
                return self._cache.get(ip, (0.0, "Unresolvable"))[1]

        try:
            hostname = socket.gethostbyaddr(ip)[0]
        except OSError:
            hostname = "Unresolvable"
        finally:
            with self._lock:
                self._cache[ip] = (time.monotonic() + self.ttl_seconds, hostname)
                self._in_flight.pop(ip).set()

        return hostname


def configure_logging(verbose: bool) -> None:
    """Keep the terminal quiet unless something goes wrong (or --verbose)."""
    install_rich_traceback(show_locals=verbose)
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[
            RichHandler(
                console=console,
                rich_tracebacks=True,
                show_path=verbose,
                show_time=verbose,
                markup=False,
            )
        ],
        force=True,
    )


def resolve_hostname(ip: str) -> str:
    return HostnameCache(ttl_seconds=0).resolve(ip)


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


def markdown_escape(value: object) -> str:
    """Escape ``|`` so a value can sit inside a Markdown table cell."""
    return str(value).replace("|", r"\|")
