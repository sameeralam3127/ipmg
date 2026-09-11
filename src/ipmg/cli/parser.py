"""Argument parsers for every IPMG command."""

from __future__ import annotations

import argparse

from ipmg import __version__
from ipmg.core.portscan import DEFAULT_PORTS, parse_port_list
from ipmg.infrastructure.file_io import DEFAULT_INPUT_FILE
from ipmg.reporting.diff_report import DIFF_FORMATS
from ipmg.reporting.live import DEFAULT_REFRESH_S, MAX_REFRESH_S, MIN_REFRESH_S

PROG = "IPMG - IP Management & Ping Monitoring Tool"


def _port_list(value: str) -> tuple:
    try:
        return parse_port_list(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _add_database_argument(parser) -> None:
    parser.add_argument(
        "--db",
        default=None,
        metavar="PATH",
        help="Scan history database file (default: ~/.ipmg/dashboard.db).",
    )


def _add_diff_threshold_arguments(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("change detection thresholds")
    group.add_argument(
        "--latency-threshold",
        type=float,
        default=5.0,
        metavar="MS",
        help="Minimum latency delta in milliseconds before it is reported (default: 5).",
    )
    group.add_argument(
        "--latency-pct",
        type=float,
        default=25.0,
        metavar="PERCENT",
        help="Minimum relative latency change before it is reported (default: 25).",
    )


def _add_diff_export_arguments(parser) -> None:
    parser.add_argument(
        "--diff-formats",
        nargs="+",
        default=[],
        choices=list(DIFF_FORMATS),
        metavar="FORMAT",
        help=f"Export the change summary as {', '.join(DIFF_FORMATS)}.",
    )
    parser.add_argument(
        "--diff-output",
        default="changes",
        metavar="BASENAME",
        help="Base filename for exported change summaries (default: changes).",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        PROG,
        epilog=(
            "Commands: 'ipmg dashboard' (web UI), 'ipmg history' (stored scans), "
            "'ipmg diff' (compare two scans)."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    # No default here, so the scan service can tell "no --input given" (use the
    # sample file) apart from an explicit file name that does not exist (error).
    parser.add_argument(
        "--input",
        default=None,
        help=(
            "IP, CIDR block, range, or target file (.txt, .list, .csv, .xls, .xlsx). "
            f"Without --input or --discover, {DEFAULT_INPUT_FILE} is used and "
            "created with sample targets if it does not exist."
        ),
    )
    parser.add_argument("--output", default="results")
    parser.add_argument("--timeout", type=int, default=2)
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--threads", type=int, default=50)
    parser.add_argument(
        "--formats",
        nargs="+",
        default=["xlsx"],
        choices=["xlsx", "csv", "json", "md"],
    )
    parser.add_argument("--discover", action="store_true")
    parser.add_argument("--resolve", action="store_true")
    parser.add_argument(
        "--dns-cache-ttl",
        type=int,
        default=300,
        metavar="SECONDS",
        help="Cache reverse DNS results for this many seconds (default: 300).",
    )
    parser.add_argument("--interval", type=int)
    parser.add_argument("--verbose", action="store_true")

    ports_group = parser.add_argument_group("TCP service discovery")
    ports_group.add_argument(
        "--scan-ports",
        action="store_true",
        help="Probe common TCP ports on hosts that answer ICMP (off by default).",
    )
    ports_group.add_argument(
        "--ports",
        type=_port_list,
        default=DEFAULT_PORTS,
        metavar="PORTS",
        help=(
            "Comma-separated TCP ports to probe when --scan-ports is set "
            f"(default: {','.join(str(p) for p in DEFAULT_PORTS)})."
        ),
    )
    ports_group.add_argument(
        "--port-timeout",
        type=float,
        default=1.0,
        metavar="SECONDS",
        help="Connect timeout per port when --scan-ports is set (default: 1).",
    )

    live = parser.add_argument_group("live output")
    live.add_argument(
        "--stream",
        action="store_true",
        help="Print each host that answers as soon as its probe finishes.",
    )
    live.add_argument(
        "--stream-all",
        action="store_true",
        help="Stream every result, including hosts that did not answer (implies --stream).",
    )
    live.add_argument(
        "--stream-refresh",
        type=float,
        default=DEFAULT_REFRESH_S,
        metavar="SECONDS",
        help=(
            "Seconds between progress-bar redraws while streaming "
            f"(default: {DEFAULT_REFRESH_S}, range {MIN_REFRESH_S}-{MAX_REFRESH_S})."
        ),
    )

    history = parser.add_argument_group("scan history")
    history.add_argument(
        "--no-history",
        dest="history",
        action="store_false",
        help="Do not store this scan in the local history database.",
    )
    history.add_argument(
        "--compare",
        action="store_true",
        help="Compare this scan against the previous one and print a change report.",
    )
    history.add_argument(
        "--compare-any-source",
        action="store_true",
        help="Compare against the previous scan even if it used a different target source.",
    )
    _add_database_argument(history)
    _add_diff_export_arguments(history)
    _add_diff_threshold_arguments(parser)
    parser.set_defaults(history=True)
    return parser


def build_dashboard_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        "ipmg dashboard",
        description="Start the local IPMG web dashboard.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Interface to bind (default: 127.0.0.1, local only).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port to listen on (default: 8080).",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open the dashboard in a browser automatically.",
    )
    _add_database_argument(parser)
    parser.add_argument("--verbose", action="store_true")
    return parser


def build_history_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        "ipmg history",
        description="List scans stored in the local history database.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of scans to list (default: 20).",
    )
    parser.add_argument(
        "--source",
        default=None,
        help="Only list scans from this target source (input file or 'auto-discovery').",
    )
    _add_database_argument(parser)
    parser.add_argument("--verbose", action="store_true")
    return parser


def build_diff_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        "ipmg diff",
        description=(
            "Compare two stored scans and report new hosts, offline hosts, "
            "IP/hostname changes, latency shifts, and service changes."
        ),
    )
    parser.add_argument(
        "scans",
        nargs="*",
        type=int,
        metavar="SCAN_ID",
        help=(
            "No id compares the two most recent scans; one id compares it against "
            "the scan before it; two ids compare BASELINE against TARGET."
        ),
    )
    parser.add_argument(
        "--source",
        default=None,
        help="Restrict automatic baseline selection to this target source.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Only print the first N changes (exports always contain every change).",
    )
    parser.add_argument(
        "--fail-on-change",
        action="store_true",
        help="Exit with status 2 when any change is detected (useful in CI).",
    )
    _add_database_argument(parser)
    _add_diff_export_arguments(parser)
    _add_diff_threshold_arguments(parser)
    parser.add_argument("--verbose", action="store_true")
    return parser
