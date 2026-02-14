import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser("IPMG - IP Management & Ping Monitoring Tool")
    parser.add_argument("--input", default="ip_list.xlsx")
    parser.add_argument("--output", default="results")
    parser.add_argument("--timeout", type=int, default=2)
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--threads", type=int, default=50)
    parser.add_argument(
        "--formats",
        nargs="+",
        default=["xlsx"],
        choices=["xlsx", "csv", "json"],
    )
    parser.add_argument("--discover", action="store_true")
    parser.add_argument("--resolve", action="store_true")
    parser.add_argument("--interval", type=int)
    parser.add_argument("--verbose", action="store_true")
    return parser
