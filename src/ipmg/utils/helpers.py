import concurrent.futures
import logging
import queue
import socket
import sys
import threading
import time
from datetime import datetime

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
    Both streams are covered because the UI moves to stderr whenever stdout is
    carrying machine-readable output.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(errors="replace")
        except (OSError, ValueError):  # pragma: no cover - stream already detached
            pass


_tolerate_unencodable_output()

# No file= here on purpose: rich resolves sys.stdout per write, which keeps
# output capturable by pytest and redirectable by callers.
console = Console(theme=RICH_THEME)


class _LookupPool:
    """Daemon threads that run blocking reverse DNS lookups.

    ``socket.gethostbyaddr`` takes no timeout and cannot be interrupted: with
    a slow or unreachable resolver one call blocks for the system resolver's
    whole retry period (often 5-30 s). The caller therefore waits on a future
    for as long as it is willing to, and the lookup itself runs here. A lookup
    that never returns ties up one of these threads, never a scan worker, and
    the threads are daemons, so a hung one cannot hold up Ctrl+C or exit.
    """

    def __init__(self, max_workers: int) -> None:
        self._max_workers = max(max_workers, 1)
        self._queue: queue.Queue[tuple[str, concurrent.futures.Future] | None] = queue.Queue()
        self._threads: list[threading.Thread] = []
        self._lock = threading.Lock()
        self._closed = False

    def submit(self, ip: str) -> "concurrent.futures.Future[str]":
        future: concurrent.futures.Future[str] = concurrent.futures.Future()
        with self._lock:
            if self._closed:
                raise RuntimeError("lookup pool is closed")
            self._queue.put((ip, future))
            # Grown on demand, so a scan that resolves a handful of hosts
            # starts a handful of threads, not --threads of them.
            if len(self._threads) < self._max_workers:
                thread = threading.Thread(
                    target=self._work,
                    name=f"ipmg-dns-{len(self._threads)}",
                    daemon=True,
                )
                self._threads.append(thread)
                thread.start()
        return future

    def _work(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            ip, future = item
            # A caller that gave up before the lookup started cancelled it.
            if not future.set_running_or_notify_cancel():
                continue
            try:
                future.set_result(socket.gethostbyaddr(ip)[0])
            except BaseException as exc:  # handed to the waiting caller
                future.set_exception(exc)

    def close(self) -> None:
        """Let every thread exit once it is idle; queued lookups are cancelled."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            while True:
                try:
                    item = self._queue.get_nowait()
                except queue.Empty:
                    break
                if item is not None:
                    item[1].cancel()
            for _thread in self._threads:
                self._queue.put(None)


class HostnameCache:
    """Thread-safe, TTL-based cache for reverse DNS lookups.

    With ``timeout_s`` set, a lookup that takes longer is recorded as
    ``Unresolvable`` instead of blocking its caller; the lookups then run on
    up to ``max_workers`` daemon threads. Call :meth:`close` when done.
    """

    def __init__(
        self,
        ttl_seconds: int = 300,
        timeout_s: float | None = None,
        max_workers: int = 32,
    ) -> None:
        self.ttl_seconds = max(ttl_seconds, 0)
        self.timeout_s = timeout_s
        self._cache: dict[str, tuple[float, str]] = {}
        self._in_flight: dict[str, threading.Event] = {}
        self._lock = threading.Lock()
        self._pool = _LookupPool(max_workers) if timeout_s is not None else None

    def close(self) -> None:
        if self._pool is not None:
            self._pool.close()

    def _lookup(self, ip: str) -> str:
        if self._pool is None:
            return socket.gethostbyaddr(ip)[0]
        future = self._pool.submit(ip)
        try:
            return future.result(timeout=self.timeout_s)
        except concurrent.futures.TimeoutError:
            # Still queued: never start it. Already running: it finishes on
            # its own thread and its answer is dropped.
            future.cancel()
            raise

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

        # Set before the lookup so the finally block always has a value to
        # cache and always releases threads waiting on this IP.
        hostname = "Unresolvable"
        try:
            hostname = self._lookup(ip)
        except Exception:
            # Any lookup failure, a timeout included, means "no name", never
            # a failed scan.
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


def clamp_int(value: int, minimum: int | None, maximum: int | None) -> int:
    if minimum is not None:
        value = max(value, minimum)

    if maximum is not None:
        value = min(value, maximum)

    return value


def markdown_escape(value: object) -> str:
    """Escape ``|`` so a value can sit inside a Markdown table cell."""
    return str(value).replace("|", r"\|")


#: Leading characters that make a spreadsheet evaluate a cell as a formula.
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _is_number(text: str) -> bool:
    try:
        float(text)
    except ValueError:
        return False
    return True


def spreadsheet_escape(value: object) -> str:
    """Neutralise a value a spreadsheet would otherwise evaluate as a formula.

    Report cells carry data we do not control — most notably hostnames taken
    from reverse DNS, which the scanned host itself publishes. A PTR record of
    ``=cmd|'/c calc'!A1`` becomes a live formula the moment the operator opens
    the exported CSV/XLSX, so prefix a single quote to force literal text.
    Signed numbers such as ``-12.5`` are left alone: they are values, not
    formulas, and quoting them would break the column's arithmetic.
    """
    text = str(value)
    if not text.startswith(FORMULA_PREFIXES):
        return text
    if text[0] in "+-" and _is_number(text):
        return text
    return "'" + text


def markdown_cell(value: object) -> str:
    """Escape a table cell for Markdown *and* for spreadsheets importing it."""
    return markdown_escape(spreadsheet_escape(value))
