"""Argument parsers for every IPMG command."""

from __future__ import annotations

import argparse

from ipmg import __version__
from ipmg.reporting.diff_report import DIFF_FORMATS

PROG = "IPMG - IP Management & Ping Monitoring Tool"


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
    parser.add_argument("--input", default="ip_list.xlsx")
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
