"""Probe real addresses with the system ping on a BSD, through IPMG's own argv.

Run from the repository root with only a Python interpreter installed:

    PYTHONPATH=src python3 .github/scripts/bsd-ping-smoke.py

``ipmg.core.ping`` imports nothing outside the standard library, so this
needs no ``pip install``: the point is the ping(8) flags each BSD accepts,
which unit tests can only assert against the man pages.
"""

from __future__ import annotations

import platform
import sys
import time

from ipmg.core.ping import build_ping_command, ping_ip

#: TEST-NET-1 (RFC 5737): routable syntax, never answers.
SILENT = "192.0.2.1"
TIMEOUT_S = 2


def check(ip: str, count: int, expect_active: bool) -> bool:
    argv = build_ping_command(ip, TIMEOUT_S, count)
    started = time.monotonic()
    status, latency = ping_ip(ip, TIMEOUT_S, count)
    elapsed = time.monotonic() - started

    ok = (status == "Active") == expect_active
    # A silent host must still give up at the probe deadline, not ping(8)'s own.
    if not expect_active and elapsed > TIMEOUT_S * count + 2:
        ok = False
    verdict = "ok" if ok else "FAIL"
    print(f"{verdict:4} {' '.join(argv):45} -> {status} {latency} ({elapsed:.1f}s)")
    return ok


def main() -> int:
    print(platform.system(), platform.release())
    results = [
        check("127.0.0.1", 1, expect_active=True),
        check("127.0.0.1", 2, expect_active=True),
        check("::1", 1, expect_active=True),
        check(SILENT, 1, expect_active=False),
    ]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
