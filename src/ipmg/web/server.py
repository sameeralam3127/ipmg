"""Launches the dashboard: uvicorn server plus automatic browser opening."""

from __future__ import annotations

import ipaddress
import os
import re
import secrets
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Optional

import uvicorn

from ipmg.infrastructure.database import DEFAULT_DB_PATH, Database
from ipmg.reporting import ui
from ipmg.web.app import create_app


def _display_host(host: str) -> str:
    try:
        if ipaddress.ip_address(host).is_unspecified:
            return "127.0.0.1"
    except ValueError:
        pass
    return host


def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


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


def run_dashboard(
    host: str = "127.0.0.1",
    port: int = 8080,
    open_browser: bool = True,
    db_path: Optional[str] = None,
) -> None:
    database = Database(Path(db_path) if db_path else DEFAULT_DB_PATH)
    token = _access_token()
    app = create_app(database, token)
    # The token goes in the fragment, which browsers never send to the server,
    # so it stays out of access logs and proxies.
    url = f"http://{_display_host(host)}:{port}/#token={token}"

    ui.blank()
    ui.fields(
        [
            ("Open", url),
            ("History", database.path),
        ]
    )
    ui.blank()
    ui.note("Press CTRL+C to stop.")

    headless = open_browser and not _has_display()
    if headless:
        ui.note("No display detected — skipping automatic browser launch.")
    elif open_browser:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()

    ui.note("The link carries this session's access token; the API refuses requests without it.")
    if _is_loopback(host):
        ui.note(
            f"Remote access: ssh -L {port}:127.0.0.1:{port} user@this-host, then open the link."
        )
    else:
        ui.note(
            "Listening beyond this machine over plain HTTP: anyone who can see the traffic "
            "can read the token. Prefer an SSH tunnel, or a reverse proxy with TLS (see SECURITY.md)."
        )

    ui.blank()

    uvicorn.run(app, host=host, port=port, log_level="warning")
