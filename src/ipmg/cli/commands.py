"""Command dispatch for the ``ipmg`` executable."""

from __future__ import annotations

import logging
import sys
from typing import Callable, Dict, List, Optional

from ipmg.cli.parser import (
    build_dashboard_parser,
    build_diff_parser,
    build_history_parser,
    build_parser,
)
from ipmg.core.diff import DiffOptions
from ipmg.core.security import print_disclaimer_once
from ipmg.exceptions import IPMGError
from ipmg.reporting import ui
from ipmg.reporting.diff_report import export_diff, print_diff
from ipmg.reporting.summary import print_scan_history
from ipmg.services.history_service import HistoryService
from ipmg.services.scan_service import run_scan
from ipmg.utils.helpers import configure_logging

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_CHANGES_DETECTED = 2
EXIT_INTERRUPTED = 130

log = logging.getLogger(__name__)


def _scan_command(argv: List[str]) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(args.verbose)
    ui.header("scan")
    print_disclaimer_once()
    run_scan(args)
    return EXIT_OK


def _dashboard_command(argv: List[str]) -> int:
    args = build_dashboard_parser().parse_args(argv)
    configure_logging(args.verbose)
    ui.header("dashboard")
    print_disclaimer_once()

    # Imported lazily so plain CLI scans do not pay for the web stack.
    from ipmg.web.server import run_dashboard

    run_dashboard(
        host=args.host,
        port=args.port,
        open_browser=not args.no_browser,
        db_path=args.db,
    )
    return EXIT_OK


def _history_command(argv: List[str]) -> int:
    args = build_history_parser().parse_args(argv)
    configure_logging(args.verbose)
    ui.header("history")

    history = HistoryService.open(args.db)
    print_scan_history(history.list_scans(limit=args.limit, source=args.source))
    return EXIT_OK


def _diff_command(argv: List[str]) -> int:
    args = build_diff_parser().parse_args(argv)
    configure_logging(args.verbose)
    ui.header("diff")

    if len(args.scans) > 2:
        ui.blank()
        ui.error("Provide at most two scan ids: BASELINE TARGET.")
        return EXIT_ERROR

    history = HistoryService.open(args.db)
    options = DiffOptions(
        latency_abs_ms=max(args.latency_threshold, 0.0),
        latency_pct=max(args.latency_pct, 0.0),
    )

    if len(args.scans) == 2:
        diff = history.compare(args.scans[0], args.scans[1], options=options)
    elif len(args.scans) == 1:
        diff = history.compare_with_previous(args.scans[0], source=args.source, options=options)
    else:
        diff = history.compare_latest(source=args.source, options=options)

    print_diff(diff, limit=args.limit)
    if args.diff_formats:
        export_diff(diff, args.diff_output, args.diff_formats)

    if args.fail_on_change and diff.has_changes:
        return EXIT_CHANGES_DETECTED
    return EXIT_OK


_COMMANDS: Dict[str, Callable[[List[str]], int]] = {
    "dashboard": _dashboard_command,
    "web": _dashboard_command,
    "history": _history_command,
    "diff": _diff_command,
    "compare": _diff_command,
}


def run(argv: Optional[List[str]] = None) -> int:
    """Entry point: returns the process exit code."""
    argv = list(sys.argv[1:] if argv is None else argv)
    command = _COMMANDS.get(argv[0]) if argv else None
    handler, handler_argv = (command, argv[1:]) if command else (_scan_command, argv)

    try:
        return handler(handler_argv)
    except IPMGError as exc:
        ui.blank()
        ui.error(str(exc))
        log.debug("command failed", exc_info=True)
        return EXIT_ERROR
    except KeyboardInterrupt:
        ui.blank()
        ui.warn("Interrupted.")
        return EXIT_INTERRUPTED


def main() -> None:
    sys.exit(run())
