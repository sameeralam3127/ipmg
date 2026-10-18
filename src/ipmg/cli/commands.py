"""Command dispatch for the ``ipmg`` executable."""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable

from ipmg.cli import completion, config
from ipmg.cli.parser import (
    build_completion_parser,
    build_diff_parser,
    build_history_parser,
    build_parser,
    build_prune_parser,
    build_wake_parser,
    build_web_parser,
)
from ipmg.core.diff import DiffOptions
from ipmg.core.health import HostsDownError
from ipmg.core.security import print_disclaimer_once
from ipmg.core.wake import parse_mac, send_magic_packet
from ipmg.exceptions import IPMGError
from ipmg.infrastructure.notify import notify_options, send_notifications
from ipmg.reporting import ui
from ipmg.reporting.diff_report import export_diff, print_diff
from ipmg.reporting.summary import print_scan_history
from ipmg.services.history_service import HistoryService
from ipmg.services.scan_service import machine_output, run_scan
from ipmg.utils.helpers import configure_logging

#: Top-level modules of the `web` extra, to tell a missing extra from a bug.
WEB_PACKAGES = frozenset({"fastapi", "pydantic", "starlette", "uvicorn", "websockets", "multipart"})

WEB_EXTRA_MISSING = (
    "IPMG Web needs the optional 'web' packages, which this install does not have. "
    "Add them with whichever tool installed IPMG:\n"
    "  uv tool install --force 'ipmg[web]'\n"
    "  pipx install --force 'ipmg[web]'\n"
    "  pip install 'ipmg[web]'"
)

#: Where ``ipmg web --lan`` listens; only ever used when asked for with --lan.
ALL_INTERFACES = "0.0.0.0"  # nosec B104

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_CHANGES_DETECTED = 2
EXIT_HOSTS_DOWN = 3
EXIT_INTERRUPTED = 130

log = logging.getLogger(__name__)


def _scan_command(argv: list[str]) -> int:
    parser = build_parser()
    # Before parsing: the file supplies the defaults, so anything on the
    # command line still overrides it.
    config.apply(parser, build_parser, argv)
    args = parser.parse_args(argv)
    configure_logging(args.verbose)
    if machine_output(args).enabled:
        # Before the banner: with --json or --jsonl stdout carries the results
        # and nothing else, so every line a person reads goes to stderr.
        ui.use_stderr()
    ui.header("scan")
    print_disclaimer_once(_probe_kinds(args))
    run_scan(args)
    return EXIT_OK


def _probe_kinds(args) -> list[str]:
    """What a scan will send, for the authorization notice."""
    kinds = []
    if getattr(args, "http_check", None) and not (args.input or args.discover):
        return ["HTTP"]
    probe = (getattr(args, "probe", None) or "icmp").split(",")
    if "icmp" in probe:
        kinds.append("ICMP")
    if "tcp" in probe or getattr(args, "scan_ports", False):
        kinds.append("TCP connect")
    if getattr(args, "http_check", None):
        kinds.append("HTTP")
    return kinds


def _web_command(argv: list[str]) -> int:
    args = build_web_parser().parse_args(argv)
    configure_logging(args.verbose)
    ui.header("web")
    print_disclaimer_once()

    # Imported lazily so plain CLI scans do not pay for the web stack, which
    # is the optional `web` extra.
    try:
        from ipmg.web.server import run_dashboard
    except ModuleNotFoundError as exc:
        if exc.name not in WEB_PACKAGES:
            raise
        raise IPMGError(WEB_EXTRA_MISSING) from exc

    host = args.host or (ALL_INTERFACES if args.lan or args.open_firewall else "127.0.0.1")
    run_dashboard(
        host=host,
        port=args.port,
        open_browser=not args.no_browser,
        db_path=args.db,
        metrics_sources=max(args.metrics_sources, 1) if args.metrics else None,
        max_scans=max(args.max_scans, 1),
        open_firewall=args.open_firewall,
    )
    return EXIT_OK


def _format_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"  # pragma: no cover - the loop always returns


def _prune_command(argv: list[str]) -> int:
    parser = build_prune_parser()
    args = parser.parse_args(argv)
    if args.keep is None and args.older_than is None:
        parser.error("give --keep N, --older-than AGE, or both")
    if args.keep is not None and args.keep < 0:
        parser.error("--keep cannot be negative")
    configure_logging(args.verbose)
    ui.header("history prune")

    history = HistoryService.open(args.db)
    plan = history.plan_prune(keep=args.keep, older_than=args.older_than, source=args.source)

    ui.blank()
    if not plan.scans:
        ui.note("Nothing to prune: the policy keeps every stored scan.")
        return EXIT_OK

    summary = (
        f"{ui.plural(len(plan.scans), 'scan')} {ui.glyph('sep')} "
        f"{ui.plural(plan.result_count, 'result')}"
    )
    sources = [f"{source} ({count})" for source, count in sorted(plan.by_source().items())]
    if args.dry_run:
        ui.field("Prunable", summary)
        ui.field_list("From", sources)
        ui.blank()
        ui.note("Dry run: nothing was deleted. Run it again without --dry-run to delete.")
        return EXIT_OK

    size_before = history.database.size_bytes()
    history.prune(plan)
    ui.field("Deleted", summary)
    ui.field_list("From", sources)
    if args.vacuum:
        history.database.vacuum()
        ui.field(
            "Database",
            f"{_format_bytes(size_before)} {ui.glyph('arrow')} "
            f"{_format_bytes(history.database.size_bytes())}",
        )
    return EXIT_OK


def _history_command(argv: list[str]) -> int:
    if argv and argv[0] == "prune":
        return _prune_command(argv[1:])
    args = build_history_parser().parse_args(argv)
    configure_logging(args.verbose)
    ui.header("history")

    history = HistoryService.open(args.db)
    print_scan_history(history.list_scans(limit=args.limit, source=args.source))
    return EXIT_OK


def _diff_command(argv: list[str]) -> int:
    args = build_diff_parser().parse_args(argv)
    configure_logging(args.verbose)
    ui.header("diff")

    if len(args.scans) > 2:
        ui.blank()
        ui.error("Provide at most two scan ids: BASELINE TARGET.")
        return EXIT_ERROR

    notify = notify_options(args)
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
    send_notifications(diff, notify)

    if args.fail_on_change and diff.has_changes:
        return EXIT_CHANGES_DETECTED
    return EXIT_OK


def _wake_command(argv: list[str]) -> int:
    args = build_wake_parser().parse_args(argv)
    configure_logging(args.verbose)
    ui.header("wake")

    # Every address is checked before any packet goes out.
    for mac in args.macs:
        parse_mac(mac)
    ui.blank()
    for mac in args.macs:
        sent = send_magic_packet(mac, broadcast=args.broadcast, port=args.port)
        ui.success(f"Magic packet sent to {sent} via {args.broadcast}:{args.port}")
    ui.blank()
    ui.note("A host that wakes takes a little while to answer pings.")
    return EXIT_OK


def _completion_command(argv: list[str]) -> int:
    args = build_completion_parser().parse_args(argv)
    # Only the script on stdout, no banner: it is eval'd or saved to a file.
    sys.stdout.write(completion.script(args.shell))
    return EXIT_OK


_COMMANDS: dict[str, Callable[[list[str]], int]] = {
    "web": _web_command,
    "history": _history_command,
    "diff": _diff_command,
    "compare": _diff_command,
    "wake": _wake_command,
    "completion": _completion_command,
}

#: Flag spellings of a command. Reaching for "--web" before "web" is the
#: obvious guess, and refusing it teaches nothing.
_COMMAND_FLAGS: dict[str, Callable[[list[str]], int]] = {
    "--web": _web_command,
}


def _dispatch(argv: list[str]):
    """Pick the handler for this command line, and the arguments it keeps."""
    if argv and argv[0] in _COMMANDS:
        return _COMMANDS[argv[0]], argv[1:]

    for index, argument in enumerate(argv):
        if argument in _COMMAND_FLAGS:
            # Everything else is passed through, so `ipmg --web --port 9000`
            # reaches the web parser intact.
            return _COMMAND_FLAGS[argument], argv[:index] + argv[index + 1 :]

    return _scan_command, argv


def run(argv: list[str] | None = None) -> int:
    """Entry point: returns the process exit code."""
    argv = list(sys.argv[1:] if argv is None else argv)
    handler, handler_argv = _dispatch(argv)

    try:
        return handler(handler_argv)
    except HostsDownError as exc:
        # Not an error: the scan finished and wrote its reports, but failed
        # the check it was asked to make.
        ui.blank()
        ui.warn(str(exc))
        return EXIT_HOSTS_DOWN
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
