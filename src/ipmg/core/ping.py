"""ICMP probing via the system ``ping`` binary."""

from __future__ import annotations

import ipaddress
import platform
import re
import shutil
import subprocess  # nosec B404
from typing import List, Optional, Tuple

from ipmg.exceptions import PingError

#: Platforms whose ``ping -W`` expects milliseconds instead of seconds.
_MILLISECOND_TIMEOUT_SYSTEMS = frozenset({"darwin", "freebsd", "openbsd", "netbsd"})

_WINDOWS_LATENCY = re.compile(r"Average = (\d+)ms")
#: Localised Windows builds translate "Average", but every locale keeps the
#: Minimum/Maximum/Average order, so the last "= NNms" is still the average.
_WINDOWS_LATENCY_FALLBACK = re.compile(r"[=<]\s*(\d+)\s*ms")
#: iputils prints "rtt min/avg/max/mdev = ...", busybox (Alpine, OpenWrt)
#: prints "round-trip min/avg/max = ..." with no mdev field.
_POSIX_LATENCY = re.compile(r"min/avg/max(?:/[^\s=]+)?\s*=\s*[\d.]+/([\d.]+)/")


def validate_ip(ip: str) -> bool:
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False


def parse_latency(output: str, system: Optional[str] = None) -> Optional[float]:
    """Pull the average round-trip time out of a ping's summary line.

    The wording differs by ping implementation and by system language, so
    each platform gets a precise pattern plus a looser fallback.
    """
    system = (system or platform.system()).lower()

    if system == "windows":
        match = _WINDOWS_LATENCY.search(output)
        if match is None:
            # Non-English Windows: take the last "= NNms" instead.
            matches = _WINDOWS_LATENCY_FALLBACK.findall(output)
            return float(matches[-1]) if matches else None
        return float(match.group(1))

    match = _POSIX_LATENCY.search(output)
    return float(match.group(1)) if match else None


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


#: How to install ping, keyed by the package manager that is present. Minimal
#: Ubuntu, RHEL, and SUSE images all ship without it, and "not available" on
#: its own leaves the operator guessing at the package name.
_PING_INSTALL_HINTS = (
    ("apt-get", "sudo apt-get install -y iputils-ping"),
    ("dnf", "sudo dnf install -y iputils"),
    ("yum", "sudo yum install -y iputils"),
    ("zypper", "sudo zypper install -y iputils"),
    ("pacman", "sudo pacman -S --noconfirm iputils"),
    ("apk", "sudo apk add iputils"),
)


def missing_ping_message() -> str:
    """Explain that ping is missing, and how to install it on this machine."""
    base = "The system 'ping' command is not available."

    if platform.system().lower() == "windows":  # pragma: no cover - platform specific
        return f"{base} Reinstall it from Windows optional features."

    for manager, hint in _PING_INSTALL_HINTS:
        if shutil.which(manager):
            return f"{base} Install it with: {hint}"
    return f"{base} Install your distribution's iputils package."


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

        latency = parse_latency(result.stdout)

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
        raise PingError(missing_ping_message()) from exc
