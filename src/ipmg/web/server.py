"""Launches the dashboard: uvicorn server plus automatic browser opening."""

from __future__ import annotations

import ipaddress
import os
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
    # IPMG_WEB_TOKEN pins the token (e.g. behind a reverse proxy or in a
    # service); otherwise every start gets a fresh one, like Jupyter.
    token = os.environ.get("IPMG_WEB_TOKEN", "").strip() or secrets.token_urlsafe(32)
    app = create_app(database, token)
    base_url = f"http://{_display_host(host)}:{port}"
    url = f"{base_url}/?token={token}"

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
