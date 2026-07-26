"""ICMP probing via the system ``ping`` binary."""

from __future__ import annotations

import ipaddress
import platform
import re
import subprocess  # nosec B404
from typing import List, Optional, Tuple

from ipmg.exceptions import PingError

#: Platforms whose ``ping -W`` expects milliseconds instead of seconds.
_MILLISECOND_TIMEOUT_SYSTEMS = frozenset({"darwin", "freebsd", "openbsd", "netbsd"})

_WINDOWS_LATENCY = re.compile(r"Average = (\d+)ms")
_POSIX_LATENCY = re.compile(r"min/avg/max/[^=]+=\s*[\d.]+/([\d.]+)/")


def validate_ip(ip: str) -> bool:
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False


def _parse_latency(output: str) -> Optional[float]:
    system = platform.system().lower()
    pattern = _WINDOWS_LATENCY if system == "windows" else _POSIX_LATENCY
    match = pattern.search(output)
    return float(match.group(1)) if match else None


def parse_latency(output: str) -> Optional[float]:
    return _parse_latency(output)


def build_ping_command(
    ip: str, timeout: int, count: int, system: Optional[str] = None
) -> List[str]:
    """Build the platform-specific ping argv.

    The timeout flag is not portable: Windows ``-w`` and BSD/macOS ``-W`` take
    milliseconds, while Linux ``-W`` takes seconds. Sending seconds everywhere
    made macOS wait 2 ms per host and report healthy hosts as timed out.
    """
    system = (system or platform.system()).lower()

    if system == "windows":
        return ["ping", "-n", str(count), "-w", str(timeout * 1000), ip]

    wait = timeout * 1000 if system in _MILLISECOND_TIMEOUT_SYSTEMS else timeout
    return ["ping", "-c", str(count), "-W", str(wait), ip]


def ping_ip(ip: str, timeout: int, count: int) -> Tuple[str, Optional[float]]:
    if not validate_ip(ip):
        return "Invalid IP", None

    cmd = build_ping_command(ip, timeout, count)

    try:
        # Fixed argv list, no shell, and ip is validated before this call.
        result = subprocess.run(  # nosec B603
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout * count + 1,
        )

        latency = _parse_latency(result.stdout)

        if result.returncode == 0:
            return "Active", latency

        output = result.stdout.lower()
        if "unreachable" in output:
            return "Unreachable", None
        if "timed out" in output:
            return "Timeout", None

        return "Inactive", None

    except subprocess.TimeoutExpired:
        return "Timeout", None
    except FileNotFoundError as exc:
        raise PingError("The system 'ping' command is not available.") from exc
