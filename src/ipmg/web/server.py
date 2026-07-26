"""Launches the dashboard: uvicorn server plus automatic browser opening."""

from __future__ import annotations

import ipaddress
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
    ui.blank()

    if open_browser:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()

    uvicorn.run(app, host=host, port=port, log_level="warning")
