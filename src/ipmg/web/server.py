"""Launches the dashboard: uvicorn server plus automatic browser opening."""

from __future__ import annotations

import ipaddress
import threading
import webbrowser
from pathlib import Path
from typing import Optional

import uvicorn
from rich.panel import Panel

from ipmg.utils.helpers import console
from ipmg.web.app import create_app
from ipmg.web.db import DEFAULT_DB_PATH, Database


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

    console.print(
        Panel.fit(
            (
                "[ipmg.accent]Starting IPMG Dashboard...[/ipmg.accent]\n\n"
                f"Dashboard Available:\n\n[bold bright_white]{url}[/bold bright_white]\n\n"
                "Press CTRL+C to stop."
            ),
            title="[ipmg.accent]IPMG Dashboard[/ipmg.accent]",
            border_style="ipmg.accent",
        )
    )

    if open_browser:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()

    uvicorn.run(app, host=host, port=port, log_level="warning")
