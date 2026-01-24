import concurrent.futures
import os
import time

import pandas as pd
from tqdm import tqdm

from ipmg.core.discovery import discover_local_subnet
from ipmg.core.ping import ping_ip
from ipmg.infrastructure.file_io import (
    create_sample_file,
    load_ip_file,
    save_results,
)
from ipmg.reporting.summary import print_summary
from ipmg.utils.helpers import (
    clamp_int,
    current_timestamp,
    resolve_hostname,
)


def run_scan(args) -> None:
    args.threads = clamp_int(args.threads, 1, 500)

    if not os.path.exists(args.input) and not args.discover:
        create_sample_file(args.input)

    while True:
        ip_list = discover_local_subnet() if args.discover else load_ip_file(args.input)

        results = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.threads) as executor:
            futures = {executor.submit(ping_ip, ip, args.timeout, args.count): ip for ip in ip_list}

            for future in tqdm(
                concurrent.futures.as_completed(futures),
                total=len(ip_list),
            ):
                results[futures[future]] = future.result()

        hostnames = {ip: resolve_hostname(ip) if args.resolve else "" for ip in ip_list}

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

        save_results(df, args.output, args.formats)
        print_summary(df)

        if not args.interval:
            break

        time.sleep(args.interval * 60)
