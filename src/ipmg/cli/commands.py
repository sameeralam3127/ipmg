from ipmg.cli.parser import build_parser
from ipmg.core.security import print_disclaimer_once
from ipmg.services.scan_service import run_scan
from ipmg.utils.helpers import configure_logging


def run() -> None:
    args = build_parser().parse_args()
    configure_logging(args.verbose)
    print_disclaimer_once()
    run_scan(args)
