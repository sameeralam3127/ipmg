import logging
import socket
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
    install_rich_traceback(show_locals=verbose)
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True, show_path=verbose)],
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
