"""Argument parsers for every IPMG command."""

from __future__ import annotations

import argparse

from ipmg import __version__
from ipmg.core.portscan import DEFAULT_PORTS, parse_port_list
from ipmg.reporting.diff_report import DIFF_FORMATS
from ipmg.reporting.live import DEFAULT_REFRESH_S, MAX_REFRESH_S, MIN_REFRESH_S

PROG = "IPMG - IP Management & Ping Monitoring Tool"

#: Subcommands, named here so an argument error can point at them. argparse
#: prints the epilog on --help but never on an error, which is exactly when
#: someone who typed "--dashboard" needs to see them.
COMMANDS_HINT = (
    "Commands: 'ipmg dashboard' (web UI), 'ipmg history' (stored scans), "
    "'ipmg diff' (compare two scans)."
)


class ScanParser(argparse.ArgumentParser):
    """Argument parser that mentions the subcommands when a flag misses."""

    def error(self, message: str):  # pragma: no cover - exercised via parse_args
        if "unrecognized arguments" in message:
            message = f"{message}\n\n{COMMANDS_HINT}"
        super().error(message)


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
    parser = ScanParser(
        prog="ipmg",
        description=PROG,
        epilog=COMMANDS_HINT,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"{PROG} {__version__}",
    )
    parser.add_argument(
        "--input",
        default="ip_list.xlsx",
        metavar="TARGETS",
        help=(
            "What to scan: a file (.xlsx, .xls, .csv, .txt, .list), a single IP, "
            "a CIDR block, or a range like 10.0.0.1-10.0.0.50 (default: ip_list.xlsx)."
        ),
    )
    parser.add_argument(
        "--output",
        default="results",
        metavar="PREFIX",
        help="Report file name prefix; the timestamp is appended (default: results).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=2,
        metavar="SECONDS",
        help="Seconds to wait for a reply from each host (default: 2).",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=1,
        metavar="N",
        help="Pings per host; raise it on a lossy link (default: 1).",
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=50,
        metavar="N",
        help="How many hosts to probe at once (default: 50).",
    )
    parser.add_argument(
        "--formats",
        nargs="+",
        default=["xlsx"],
        choices=["xlsx", "csv", "json", "md"],
        metavar="FORMAT",
        help="One or more report formats: xlsx, csv, json, md (default: xlsx).",
    )
    parser.add_argument(
        "--discover",
        action="store_true",
        help="Auto-detect this machine's subnet and scan it instead of --input.",
    )
    parser.add_argument(
        "--resolve",
        action="store_true",
        help="Look up each host's name with a reverse DNS (PTR) query.",
    )
    parser.add_argument(
        "--dns-cache-ttl",
        type=int,
        default=300,
        metavar="SECONDS",
        help="Cache reverse DNS results for this many seconds (default: 300).",
    )
    parser.add_argument(
        "--interval",
        type=int,
        metavar="MINUTES",
        help="Repeat the whole scan every N minutes until interrupted.",
    )
    parser.add_argument("--verbose", action="store_true", help="Debug logging.")

    # People reach for a flag before a subcommand, so accept both spellings
    # rather than answering "unrecognized arguments: --dashboard".
    parser.add_argument(
        "--dashboard",
        "--web",
        dest="dashboard",
        action="store_true",
        help="Start the local web dashboard (same as 'ipmg dashboard').",
    )

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
