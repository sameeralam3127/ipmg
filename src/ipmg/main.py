import argparse
import concurrent.futures
import os
import time

import pandas as pd
from tqdm import tqdm

from ipmg.discover import discover_local_subnet
from ipmg.io_handlers import create_sample_file, load_ip_file, save_results
from ipmg.ping import ping_ip
from ipmg.reporting import print_summary
from ipmg.security import print_disclaimer_once
from ipmg.utils import (
    clamp_int,
    configure_logging,
    current_timestamp,
    resolve_hostname,
)


def main():
    parser = argparse.ArgumentParser(description="IPMG - IP Management & Ping Monitoring Tool")

    parser.add_argument("--input", default="ip_list.xlsx", help="Excel file containing IPs to ping")
    parser.add_argument("--output", default="results", help="Base name for output files")
    parser.add_argument("--timeout", type=int, default=2, help="Ping timeout in seconds")
    parser.add_argument("--count", type=int, default=1, help="Ping count per IP")
    parser.add_argument("--threads", type=int, default=50, help="Number of concurrent workers")
    parser.add_argument(
        "--formats",
        nargs="+",
        default=["xlsx"],
        choices=["xlsx", "csv", "json"],
        help="Output file formats",
    )
    parser.add_argument(
        "--discover",
        action="store_true",
        help="Auto-discover local subnet IPs instead of reading file",
    )
    parser.add_argument(
        "--resolve", action="store_true", help="Resolve IP addresses to hostnames (slower)"
    )
    parser.add_argument("--interval", type=int, help="Repeat the scan every N minutes (optional)")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    # Setup logging
    configure_logging(verbose=args.verbose)

    # Print warning / compliance notice only once
    print_disclaimer_once()

    # Safety clamp
    args.threads = clamp_int(args.threads, minimum=1, maximum=500)

    # Create sample file if missing
    if not os.path.exists(args.input) and not args.discover:
        print(f"[INFO] '{args.input}' not found. Creating sample file...")
        create_sample_file(args.input)

    while True:
        # --- Load IPs ---
        if args.discover:
            ip_list = discover_local_subnet()
            print(f"[INFO] Discovered {len(ip_list)} hosts in local subnet.")
        else:
            ip_list = load_ip_file(args.input)
            print(f"[INFO] Loaded {len(ip_list)} valid IPs from {args.input}")

        # --- Ping in parallel ---
        print("[INFO] Starting pinging...")

        results = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.threads) as executor:
            futures = {executor.submit(ping_ip, ip, args.timeout, args.count): ip for ip in ip_list}

            for future in tqdm(concurrent.futures.as_completed(futures), total=len(ip_list)):
                ip = futures[future]
                results[ip] = future.result()  # (status, latency)

        # --- Resolve hostnames (optional) ---
        hostnames = {}
        if args.resolve:
            print("[INFO] Resolving hostnames...")
            for ip in ip_list:
                hostnames[ip] = resolve_hostname(ip)
        else:
            hostnames = {ip: "" for ip in ip_list}

        # --- Prepare DataFrame ---
        df = pd.DataFrame(
            [
                {
                    "IP Address": ip,
                    "Status": status,
                    "Latency": latency,
                    "Hostname": hostnames[ip],
                    "Timestamp": current_timestamp(),
                }
                for ip, (status, latency) in results.items()
            ]
        )

        # --- Save results ---
        save_results(df, args.output, args.formats)

        # --- Print CLI summary ---
        print_summary(df)

        # --- If interval is NOT set, stop here ---
        if not args.interval:
            break

        # --- Repeat mode ---
        print(f"[INFO] Waiting {args.interval} minutes before next run...")
        time.sleep(args.interval * 60)
