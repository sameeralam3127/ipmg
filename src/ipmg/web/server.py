"""Launches the dashboard: uvicorn server plus automatic browser opening."""

from __future__ import annotations

import ipaddress
import os
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
    app = create_app(database)
    url = f"http://{_display_host(host)}:{port}"

    ui.blank()
    ui.fields(
        [
            ("Local", url),
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

    if _is_loopback(host):
        ui.note(f"Remote access: ssh -L {port}:127.0.0.1:{port} user@this-host, then open {url}.")
        ui.note("Or run with --host 0.0.0.0 (exposes an unauthenticated API — see SECURITY.md).")

    ui.blank()

    uvicorn.run(app, host=host, port=port, log_level="warning")
