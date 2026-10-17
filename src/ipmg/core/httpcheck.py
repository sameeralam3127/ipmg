"""HTTP(S) checks: is the service on a host working, not just the host? (``--http-check``)

A host can answer ping while the service on it is broken: a web server
returning 502s, an expired certificate, a login page that times out. An HTTP
check requests a URL and records the status code, the response time, where
redirects ended up, and, when it fails, why: DNS, connect, TLS, timeout, an
unexpected status, or a broken response.

Only the standard library is used (:mod:`http.client` and :mod:`ssl`).
Redirects are followed by hand so the final URL, the total time, and the
certificate of the server that answered are all known. TLS certificates are
verified unless the check is explicitly told not to.
"""

from __future__ import annotations

import concurrent.futures
import http.client
import re
import socket
import ssl
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urljoin, urlsplit

from ipmg import __version__

DEFAULT_HTTP_TIMEOUT_S = 5.0
DEFAULT_EXPECT = "200-399"
HTTP_METHODS = ("GET", "HEAD")
MAX_REDIRECTS = 10

_REDIRECTS = frozenset({301, 302, 303, 307, 308})
_RANGE = re.compile(r"^\s*(\d{3})\s*(?:-\s*(\d{3})\s*)?$")

#: Why a check failed; "" when it passed.
FAILURE_INVALID = "invalid"
FAILURE_DNS = "dns"
FAILURE_CONNECT = "connect"
FAILURE_TLS = "tls"
FAILURE_TIMEOUT = "timeout"
FAILURE_STATUS = "status"
FAILURE_PROTOCOL = "protocol"
FAILURE_REDIRECTS = "redirects"


def parse_expect(text: str) -> Tuple[Tuple[int, int], ...]:
    """``200-399``, ``200,204``, or ``200-299,401``: the status codes that count as success."""
    ranges = []
    for part in str(text).split(","):
        if not part.strip():
            continue
        match = _RANGE.match(part)
        if match is None:
            raise ValueError(f"invalid status range {part.strip()!r}: use 200-399 or 200,204")
        low = int(match.group(1))
        high = int(match.group(2) or low)
        if not 100 <= low <= high <= 599:
            raise ValueError(f"status range out of order or outside 100-599: {part.strip()}")
        ranges.append((low, high))
    if not ranges:
        raise ValueError("give at least one status code or range, such as 200-399")
    return tuple(ranges)


def format_expect(ranges: Sequence[Tuple[int, int]]) -> str:
    return ",".join(str(low) if low == high else f"{low}-{high}" for low, high in ranges)


@dataclass(frozen=True)
class HttpCheckOptions:
    timeout_s: float = DEFAULT_HTTP_TIMEOUT_S
    method: str = "GET"
    expect: Tuple[Tuple[int, int], ...] = ((200, 399),)
    follow_redirects: bool = True
    verify_tls: bool = True

    def clamped(self) -> "HttpCheckOptions":
        return HttpCheckOptions(
            timeout_s=min(max(float(self.timeout_s), 0.1), 120.0),
            method=self.method.upper() if self.method.upper() in HTTP_METHODS else "GET",
            expect=tuple(self.expect) or ((200, 399),),
            follow_redirects=self.follow_redirects,
            verify_tls=self.verify_tls,
        )

    def expects(self, status: int) -> bool:
        return any(low <= status <= high for low, high in self.expect)


@dataclass(frozen=True)
class HttpCheckResult:
    """One URL's check."""

    url: str
    ok: bool
    status_code: Optional[int] = None
    response_ms: Optional[float] = None
    #: Where redirects ended; the URL itself when there were none.
    final_url: str = ""
    #: One of the ``FAILURE_*`` kinds, or "" when the check passed.
    failure: str = ""
    error: str = ""
    #: ``YYYY-MM-DD`` (UTC) the server's certificate expires, for verified HTTPS.
    cert_expires: str = ""

    @property
    def outcome(self) -> str:
        return "OK" if self.ok else "Failed"

    @property
    def summary(self) -> str:
        """``200``, ``502``, ``timeout``: what to show for the check in one word."""
        if self.status_code is not None and self.failure in ("", FAILURE_STATUS):
            return str(self.status_code)
        return self.failure or "-"


class _Failed(Exception):
    def __init__(self, failure: str, message: str) -> None:
        super().__init__(message)
        self.failure = failure


def _tls_context(verify: bool) -> ssl.SSLContext:
    context = ssl.create_default_context()
    if not verify:
        # Asked for explicitly with --http-insecure, for self-signed lab hosts.
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE  # nosec B501
    return context


def _cert_expiry(sock: Optional[socket.socket]) -> str:
    if not isinstance(sock, ssl.SSLSocket):
        return ""
    cert = sock.getpeercert() or {}
    not_after = cert.get("notAfter")
    if not not_after:
        return ""
    try:
        seconds = ssl.cert_time_to_seconds(str(not_after))
    except ValueError:
        return ""
    return datetime.fromtimestamp(seconds, tz=timezone.utc).date().isoformat()


def _request_once(url: str, options: HttpCheckOptions, timeout_s: float) -> Tuple[int, str, str]:
    """One request: (status, Location header, certificate expiry)."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise _Failed(FAILURE_INVALID, "not an http:// or https:// URL")
    try:
        port = parts.port
    except ValueError as exc:
        raise _Failed(FAILURE_INVALID, str(exc)) from exc
    path = parts.path or "/"
    if parts.query:
        path = f"{path}?{parts.query}"

    if parts.scheme == "https":
        connection: http.client.HTTPConnection = http.client.HTTPSConnection(
            parts.hostname, port, timeout=timeout_s, context=_tls_context(options.verify_tls)
        )
    else:
        connection = http.client.HTTPConnection(parts.hostname, port, timeout=timeout_s)
    try:
        connection.request(
            options.method,
            path,
            headers={
                "User-Agent": f"ipmg/{__version__}",
                "Accept": "*/*",
                "Connection": "close",
            },
        )
        response = connection.getresponse()
        expires = _cert_expiry(connection.sock) if options.verify_tls else ""
        # The response time is the time to the status line; the body may be
        # huge, so it is never downloaded.
        return response.status, response.getheader("Location") or "", expires
    finally:
        connection.close()


def _describe(exc: BaseException) -> str:
    text = str(exc).strip()
    return text or type(exc).__name__


@dataclass
class _Progress:
    """Where a check has got to, so a failure can say how far it went."""

    url: str
    status: Optional[int] = None
    expires: str = ""


def _follow(progress: _Progress, options: HttpCheckOptions, deadline: float) -> None:
    """Request ``progress.url``, following redirects, until a final response."""
    for _hop in range(MAX_REDIRECTS + 1):
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            raise socket.timeout("timed out")
        progress.status, location, progress.expires = _request_once(
            progress.url, options, remaining
        )
        if not (options.follow_redirects and progress.status in _REDIRECTS and location):
            return
        progress.url = urljoin(progress.url, location)
    raise _Failed(FAILURE_REDIRECTS, f"more than {MAX_REDIRECTS} redirects")


def _classify(exc: Exception, options: HttpCheckOptions) -> Tuple[str, str]:
    """The failure kind and message for an exception a request raised."""
    if isinstance(exc, _Failed):
        return exc.failure, str(exc)
    if isinstance(exc, socket.gaierror):
        return FAILURE_DNS, _describe(exc)
    if isinstance(exc, socket.timeout):
        return FAILURE_TIMEOUT, f"no response within {options.timeout_s:g}s"
    # Before OSError and ValueError: SSL errors are both.
    if isinstance(exc, ssl.SSLError):
        return FAILURE_TLS, _describe(exc)
    if isinstance(exc, (http.client.HTTPException, ValueError)):
        return FAILURE_PROTOCOL, _describe(exc)
    return FAILURE_CONNECT, _describe(exc)


def check_url(url: str, options: Optional[HttpCheckOptions] = None) -> HttpCheckResult:
    """Request ``url`` and say how it went. Never raises: a failure is a result."""
    options = (options or HttpCheckOptions()).clamped()
    url = url.strip()
    started = time.perf_counter()
    progress = _Progress(url)

    failure, message = "", ""
    try:
        _follow(progress, options, started + options.timeout_s)
    except (OSError, ValueError, http.client.HTTPException, _Failed) as exc:
        failure, message = _classify(exc, options)
    else:
        if progress.status is None or not options.expects(progress.status):
            failure = FAILURE_STATUS
            message = f"status {progress.status}, expected {format_expect(options.expect)}"

    answered = progress.status is not None
    return HttpCheckResult(
        url=url,
        ok=not failure,
        status_code=progress.status,
        response_ms=round((time.perf_counter() - started) * 1000, 3) if answered else None,
        final_url=progress.url,
        failure=failure,
        error=message,
        cert_expires=progress.expires,
    )


def run_http_checks(
    urls: Iterable[str],
    options: Optional[HttpCheckOptions] = None,
    max_workers: int = 50,
) -> List[HttpCheckResult]:
    """Check every URL concurrently (at most ``max_workers`` at once), in the order given."""
    urls = list(dict.fromkeys(url.strip() for url in urls if url and url.strip()))
    if not urls:
        return []
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=max(1, min(max_workers, len(urls))), thread_name_prefix="ipmg-http"
    ) as pool:
        return list(pool.map(lambda url: check_url(url, options), urls))
