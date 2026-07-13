import argparse

from ipmg import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        "IPMG - IP Management & Ping Monitoring Tool",
        epilog="Run 'ipmg dashboard' to start the local web dashboard.",
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
    parser.add_argument(
        "--db",
        default=None,
        metavar="PATH",
        help="Scan history database file (default: ~/.ipmg/dashboard.db).",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser
