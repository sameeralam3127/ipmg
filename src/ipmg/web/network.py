"""Reaching IPMG Web from other machines: the link to print and the host firewall.

IPMG Web listens on 127.0.0.1 unless told otherwise. With ``--lan`` (or any
non-loopback ``--host``) other machines can connect, but only if they know
this machine's address and the host firewall lets them in, and the
unprinted step was always the one that failed. This module works both out:
the LAN address to put in the link, and which firewall is in the way with the
exact command that opens the port.

The firewall is only ever changed on request (``--open-firewall``), only for
the port IPMG Web uses, and only while it runs: the rule it added is removed
again when IPMG Web stops.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import platform
import shutil
import subprocess  # nosec B404
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

from ipmg.core.discovery import local_ip_address
from ipmg.exceptions import DiscoveryError

log = logging.getLogger(__name__)

#: Seconds allowed for each firewall query.
_COMMAND_TIMEOUT_S = 5

Runner = Callable[[Sequence[str]], Optional[Tuple[int, str]]]


def _run(argv: Sequence[str]) -> Optional[Tuple[int, str]]:
    """Run a fixed argv; (exit status, output), or None if it cannot run at all."""
    if shutil.which(argv[0]) is None and not Path(argv[0]).exists():
        return None
    try:
        # A fixed argv, no shell; the only variable part is the port number.
        result = subprocess.run(  # nosec B603
            list(argv),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=_COMMAND_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError):
        log.debug("could not run %s", argv[0], exc_info=True)
        return None
    return result.returncode, result.stdout or ""


# ----------------------------------------------------------------- the link


def in_container() -> bool:
    """Inside Docker or Podman, where this machine's own address means nothing outside."""
    return Path("/.dockerenv").exists() or Path("/run/.containerenv").exists()


def is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _url_host(host: str) -> str:
    try:
        if ipaddress.ip_address(host).version == 6:
            return f"[{host}]"
    except ValueError:
        pass
    return host


def browse_urls(host: str, port: int, token: str) -> List[Tuple[str, str]]:
    """The links to print, as (url, who it is for), the one to open first."""

    def link(address: str) -> str:
        # The token goes in the fragment, which browsers never send to the
        # server, so it stays out of access logs and proxies.
        return f"http://{_url_host(address)}:{port}/#token={token}"

    local = link("127.0.0.1")
    if is_loopback(host):
        return [(local, "")]
    try:
        unspecified = ipaddress.ip_address(host).is_unspecified
    except ValueError:
        unspecified = False
    if not unspecified:
        return [(link(host), "")]
    if in_container():
        return [(local, "on the port you published")]
    try:
        address = local_ip_address()
    except DiscoveryError:
        return [(local, "on this machine")]
    return [(link(address), "from other machines"), (local, "on this machine")]


# -------------------------------------------------------------- the firewall


@dataclass(frozen=True)
class Firewall:
    """The firewall in front of IPMG Web, and what it takes to let others in."""

    name: str
    #: True: the port is closed. False: it is open. None: it cannot tell.
    blocks: Optional[bool]
    #: Commands that open the port, to print.
    open_commands: Tuple[str, ...] = ()
    note: str = ""
    #: argv pairs IPMG Web can run itself (as root) to open and close the port.
    open_argv: Tuple[str, ...] = field(default_factory=tuple)
    close_argv: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def can_manage(self) -> bool:
        return bool(self.open_argv)


def _firewalld(port: int, run: Runner) -> Optional[Firewall]:
    state = run(["firewall-cmd", "--state"])
    if state is None or state[0] != 0 or "running" not in state[1]:
        return None
    query = run(["firewall-cmd", f"--query-port={port}/tcp"])
    blocks: Optional[bool] = None
    if query is not None and query[1].strip() in ("yes", "no"):
        blocks = query[1].strip() == "no"
    return Firewall(
        name="firewalld",
        blocks=blocks,
        open_commands=(
            f"sudo firewall-cmd --add-port={port}/tcp",
            f"sudo firewall-cmd --permanent --add-port={port}/tcp   # keep it after a reboot",
        ),
        # A runtime rule: gone at the next reload or reboot even if IPMG Web
        # is killed before it can remove it.
        open_argv=("firewall-cmd", f"--add-port={port}/tcp"),
        close_argv=("firewall-cmd", f"--remove-port={port}/tcp"),
    )


def _ufw(port: int, run: Runner) -> Optional[Firewall]:
    status = run(["ufw", "status"])
    if status is None:
        return None
    code, output = status
    if code == 0 and "Status: inactive" in output:
        return None
    blocks: Optional[bool] = None
    if code == 0 and "Status: active" in output:
        allowed = any(
            line.split()[:1] in ([f"{port}/tcp"], [str(port)]) and "ALLOW" in line
            for line in output.splitlines()
        )
        blocks = not allowed
    elif code == 0:
        return None
    return Firewall(
        name="ufw",
        blocks=blocks,
        open_commands=(f"sudo ufw allow {port}/tcp",),
        note="" if blocks is not None else "Only needed if ufw is enabled (sudo ufw status).",
        open_argv=("ufw", "allow", f"{port}/tcp"),
        close_argv=("ufw", "delete", "allow", f"{port}/tcp"),
    )


def _windows(port: int, run: Runner) -> Optional[Firewall]:
    state = run(["netsh", "advfirewall", "show", "currentprofile", "state"])
    if state is None or "ON" not in state[1].upper():
        return None
    return Firewall(
        name="Windows Defender Firewall",
        blocks=None,
        open_commands=(
            f'netsh advfirewall firewall add rule name="IPMG Web {port}" dir=in '
            f"action=allow protocol=TCP localport={port}   # as Administrator",
        ),
        note="Windows may also ask whether Python may accept connections: allow it "
        "for Private networks.",
    )


_SOCKETFILTERFW = "/usr/libexec/ApplicationFirewall/socketfilterfw"


def _macos(port: int, run: Runner) -> Optional[Firewall]:
    state = run([_SOCKETFILTERFW, "--getglobalstate"])
    if state is None or "enabled" not in state[1].lower():
        return None
    return Firewall(
        name="macOS firewall",
        blocks=None,
        note="macOS asks whether Python may accept incoming connections the first "
        "time IPMG Web starts: click Allow.",
    )


def detect_firewall(
    port: int, system: Optional[str] = None, run: Optional[Runner] = None
) -> Optional[Firewall]:
    """The firewall that could keep other machines out, or None if there is none to see."""
    system = (system or platform.system()).lower()
    run = run or _run
    if system == "linux":
        return _firewalld(port, run) or _ufw(port, run)
    if system == "windows":
        return _windows(port, run)
    if system == "darwin":
        return _macos(port, run)
    return None


def is_admin() -> bool:
    geteuid = getattr(os, "geteuid", None)
    return bool(geteuid and geteuid() == 0)


def open_port(firewall: Firewall, run: Optional[Runner] = None) -> bool:
    """Run the firewall's own command to open the port; True if it worked."""
    if not firewall.can_manage:
        return False
    result = (run or _run)(list(firewall.open_argv))
    return result is not None and result[0] == 0


def close_port(firewall: Firewall, run: Optional[Runner] = None) -> bool:
    if not firewall.can_manage:
        return False
    result = (run or _run)(list(firewall.close_argv))
    return result is not None and result[0] == 0
