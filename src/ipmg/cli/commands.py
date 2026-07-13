import sys

from ipmg.cli.parser import build_dashboard_parser, build_parser
from ipmg.core.security import print_disclaimer_once
from ipmg.services.scan_service import run_scan
from ipmg.utils.helpers import configure_logging

DASHBOARD_COMMANDS = {"dashboard", "web"}


def run() -> None:
    argv = sys.argv[1:]

    if argv and argv[0] in DASHBOARD_COMMANDS:
        args = build_dashboard_parser().parse_args(argv[1:])
        configure_logging(args.verbose)
        print_disclaimer_once()

        from ipmg.web.server import run_dashboard

        run_dashboard(
            host=args.host,
            port=args.port,
            open_browser=not args.no_browser,
            db_path=args.db,
        )
        return

    args = build_parser().parse_args(argv)
    configure_logging(args.verbose)
    print_disclaimer_once()
    run_scan(args)
