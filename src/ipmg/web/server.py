"""Launches the dashboard: uvicorn server plus automatic browser opening."""

from __future__ import annotations

import os
import re
import secrets
import sys
import threading
import webbrowser
from pathlib import Path

import uvicorn

from ipmg.infrastructure.database import DEFAULT_DB_PATH, Database
from ipmg.reporting import ui
from ipmg.web import network
from ipmg.web.app import create_app
from ipmg.web.manager import DEFAULT_MAX_SCANS


def _is_loopback(host: str) -> bool:
    return network.is_loopback(host)


#: Characters that survive a URL fragment and a WebSocket subprotocol unescaped.
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9._~-]{16,}")


def _access_token() -> str:
    """``IPMG_WEB_TOKEN`` when set (e.g. behind a reverse proxy), else a fresh one.

    Like Jupyter, every start gets a new random token unless one is pinned.
    """
    pinned = os.environ.get("IPMG_WEB_TOKEN", "").strip()
    if not pinned:
        return secrets.token_urlsafe(32)
    if not _TOKEN_PATTERN.fullmatch(pinned):
        raise SystemExit(
            "IPMG_WEB_TOKEN must be at least 16 characters of letters, digits, '.', '_', '~' "
            "or '-'. Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
        )
    return pinned


def _has_display() -> bool:
    """False on a Linux session with no X11/Wayland display (e.g. over plain SSH)."""
    if sys.platform.startswith("linux"):
        return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    return True


def _open_firewall(firewall: network.Firewall, port: int) -> bool:
    """Open the port for --open-firewall; True if IPMG Web now owns a rule to remove."""
    if not firewall.can_manage:
        ui.warn(f"--open-firewall cannot change the {firewall.name}; see the step below.")
    elif not network.is_admin():
        ui.warn("--open-firewall needs root: run IPMG Web with sudo, or open the port as below.")
    elif network.open_port(firewall):
        ui.field("Firewall", f"opened {port}/tcp in {firewall.name} until IPMG Web stops")
        return True
    else:
        ui.warn(f"Could not open {port}/tcp in {firewall.name}; open it as below.")
    return False


def _explain_firewall(firewall: network.Firewall, port: int) -> None:
    """Say whether the firewall lets other machines in, and how to let them."""
    if firewall.blocks is False:
        ui.field("Firewall", f"{firewall.name} allows {port}/tcp")
        return
    if firewall.blocks:
        headline = f"{firewall.name} blocks {port}/tcp, so other machines cannot connect yet."
    else:
        headline = f"{firewall.name} is on and may block {port}/tcp."
    ui.field("Firewall", headline)
    if firewall.open_commands:
        ui.field("", "Allow it with:")
        for command in firewall.open_commands:
            ui.field("", f"  {command}", wrap=False)
        if firewall.can_manage:
            ui.field("", "or restart with --open-firewall to open it only while IPMG Web runs.")
    if firewall.note:
        ui.field("", firewall.note)


def _print_firewall(port: int, open_firewall: bool) -> network.Firewall | None:
    """Say what stands between other machines and IPMG Web, and open it on request.

    Returns the firewall whose rule IPMG Web added, so it can be removed again.
    """
    firewall = network.detect_firewall(port)
    if firewall is None:
        if open_firewall:
            ui.note("--open-firewall: no firewall found that needs opening.")
        return None
    if open_firewall and firewall.blocks is not False and _open_firewall(firewall, port):
        return firewall
    _explain_firewall(firewall, port)
    return None


def run_dashboard(
    host: str = "127.0.0.1",
    port: int = 8080,
    open_browser: bool = True,
    db_path: str | None = None,
    metrics_sources: int | None = None,
    max_scans: int = DEFAULT_MAX_SCANS,
    open_firewall: bool = False,
) -> None:
    database = Database(Path(db_path) if db_path else DEFAULT_DB_PATH)
    token = _access_token()
    app = create_app(database, token, metrics_sources=metrics_sources, max_scans=max_scans)
    urls = network.browse_urls(host, port, token)
    url = urls[0][0]
    local = _is_loopback(host)

    ui.blank()
    for index, (link, audience) in enumerate(urls):
        label = "Open" if index == 0 else ""
        ui.field(label, f"{link}  ({audience})" if audience else link, wrap=False)
    ui.field("History", database.path, wrap=False)

    opened: network.Firewall | None = None
    if not local and not network.in_container():
        opened = _print_firewall(port, open_firewall)

    ui.blank()
    ui.note("Press CTRL+C to stop.")

    headless = open_browser and not _has_display()
    if headless:
        ui.note("No display detected — skipping automatic browser launch.")
    elif open_browser:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()

    ui.note("The link carries this session's access token; the API refuses requests without it.")
    if metrics_sources is not None:
        base = url.split("/#", 1)[0]
        ui.note(
            f"Prometheus metrics at {base}/metrics "
            "(send the token as a Bearer credential; pin it with IPMG_WEB_TOKEN)."
        )
    if local:
        ui.note(
            "Open it from other machines: ipmg web --lan (it prints the link and any "
            f"firewall step), or ssh -L {port}:127.0.0.1:{port} user@this-host."
        )
    else:
        ui.note(
            "Listening on the network over plain HTTP: anyone who can see the traffic can "
            "read the token. Use it on networks you trust, or put a reverse proxy with TLS in "
            "front (see .github/SECURITY.md)."
        )

    ui.blank()

    try:
        uvicorn.run(app, host=host, port=port, log_level="warning")
    finally:
        if opened is not None and network.close_port(opened):
            ui.note(f"Closed {port}/tcp in {opened.name} again.")
