import concurrent.futures
import os
import time
from pathlib import Path

import pandas as pd
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from ipmg.exceptions import PingError
from ipmg.core.discovery import discover_local_subnet
from ipmg.core.ping import ping_ip
from ipmg.infrastructure.file_io import (
    create_sample_file,
    load_targets,
    save_results,
)
from ipmg.reporting.summary import print_summary
from ipmg.utils.helpers import (
    clamp_int,
    console,
    current_timestamp,
    resolve_hostname,
)


def run_scan(args) -> None:
    args.threads = clamp_int(args.threads, 1, 500)
    args.timeout = clamp_int(args.timeout, 1, 60)
    args.count = clamp_int(args.count, 1, 10)

    if not os.path.exists(args.input) and not args.discover:
        if Path(args.input).suffix.lower() in {".xlsx", ".xls", ".csv", ".txt", ".list"}:
            create_sample_file(args.input)

    while True:
        batch_timestamp = current_timestamp()
        scan_started_at = time.perf_counter()
        ip_list = discover_local_subnet() if args.discover else load_targets(args.input)
        target_source = "auto-discovery" if args.discover else args.input

        console.print(
            Panel.fit(
                (
                    f"[ipmg.accent]Source:[/ipmg.accent] {target_source}\n"
                    f"[ipmg.accent]Targets:[/ipmg.accent] {len(ip_list)}\n"
                    f"[ipmg.accent]Threads:[/ipmg.accent] {args.threads}\n"
                    f"[ipmg.accent]Timeout:[/ipmg.accent] {args.timeout}s x {args.count}"
                ),
                title="[ipmg.accent]Scan Configuration[/ipmg.accent]",
                border_style="ipmg.accent",
            )
        )

        results = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.threads) as executor:
            futures = {executor.submit(ping_ip, ip, args.timeout, args.count): ip for ip in ip_list}

            with Progress(
                SpinnerColumn(style="ipmg.accent"),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(bar_width=None, complete_style="green", finished_style="bright_green"),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TextColumn("[bold]{task.completed}/{task.total}[/bold]"),
                TimeElapsedColumn(),
                console=console,
            ) as progress:
                task_id = progress.add_task("[ipmg.accent]Scanning hosts[/ipmg.accent]", total=len(ip_list))

                for future in concurrent.futures.as_completed(futures):
                    ip = futures[future]
                    try:
                        results[ip] = future.result()
                    except PingError:
                        raise
                    except Exception:
                        results[ip] = ("Error", None)
                    finally:
                        progress.advance(task_id)

        hostnames = {ip: resolve_hostname(ip) if args.resolve else "" for ip in ip_list}
        scan_duration = time.perf_counter() - scan_started_at

        df = pd.DataFrame(
            [
                {
                    "IP Address": ip,
                    "Status": status,
                    "Latency": latency,
                    "Hostname": hostnames[ip],
                    "Batch Timestamp": batch_timestamp,
                    "Scan Duration (s)": round(scan_duration, 3),
                }
                for ip, (status, latency) in results.items()
            ]
        )

        save_results(df, args.output, args.formats)
        print_summary(df, batch_timestamp, scan_duration)

        if not args.interval:
            break

        time.sleep(args.interval * 60)
