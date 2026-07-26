"""CLI scan workflow: run a scan, save reports, store history, report changes."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from ipmg.core.diff import DiffOptions
from ipmg.core.discovery import discover_local_subnet
from ipmg.core.engine import HostResult, ScanConfig, execute_scan
from ipmg.exceptions import HistoryError
from ipmg.infrastructure.file_io import (
    SUPPORTED_INPUT_SUFFIXES,
    create_sample_file,
    load_targets,
    save_results,
)
from ipmg.reporting.diff_report import export_diff, print_diff
from ipmg.reporting.frames import results_dataframe
from ipmg.reporting.summary import print_summary
from ipmg.services.history_service import HistoryService
from ipmg.utils.helpers import clamp_int, console, current_timestamp

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScanOutcome:
    """Everything one scan pass produced."""

    results: List[HostResult]
    frame: pd.DataFrame
    batch_timestamp: datetime
    duration_s: float
    source: str


@dataclass(frozen=True)
class HistoryOptions:
    """How a scan should interact with the stored history."""

    enabled: bool = True
    compare: bool = False
    any_source: bool = False
    db_path: Optional[str] = None
    export_formats: Tuple[str, ...] = ()
    export_base: str = "changes"
    diff: DiffOptions = field(default_factory=DiffOptions)


def _history_options(args) -> HistoryOptions:
    """Read history settings off the parsed arguments, with safe defaults."""
    return HistoryOptions(
        enabled=bool(getattr(args, "history", True)),
        compare=bool(getattr(args, "compare", False)),
        any_source=bool(getattr(args, "compare_any_source", False)),
        db_path=getattr(args, "db", None),
        export_formats=tuple(getattr(args, "diff_formats", None) or ()),
        export_base=getattr(args, "diff_output", "changes"),
        diff=DiffOptions(
            latency_abs_ms=max(float(getattr(args, "latency_threshold", 5.0)), 0.0),
            latency_pct=max(float(getattr(args, "latency_pct", 25.0)), 0.0),
        ),
    )


def _config_from_args(args) -> ScanConfig:
    return ScanConfig(
        timeout=args.timeout,
        count=args.count,
        threads=args.threads,
        resolve=args.resolve,
        dns_cache_ttl=getattr(args, "dns_cache_ttl", 300),
    ).clamped()


def _ensure_input_file(args) -> None:
    if args.discover or os.path.exists(args.input):
        return
    if Path(args.input).suffix.lower() in SUPPORTED_INPUT_SUFFIXES:
        create_sample_file(args.input)


def _print_configuration(source: str, targets: int, config: ScanConfig) -> None:
    console.print(
        Panel.fit(
            (
                f"[ipmg.accent]Source:[/ipmg.accent] {source}\n"
                f"[ipmg.accent]Targets:[/ipmg.accent] {targets}\n"
                f"[ipmg.accent]Threads:[/ipmg.accent] {config.threads}\n"
                f"[ipmg.accent]Timeout:[/ipmg.accent] {config.timeout}s x {config.count}"
            ),
            title="[ipmg.accent]Scan Configuration[/ipmg.accent]",
            border_style="ipmg.accent",
        )
    )


def _scan_with_progress(ip_list: List[str], config: ScanConfig) -> List[HostResult]:
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
        return execute_scan(
            ip_list,
            config,
            on_result=lambda _result, _done, _total: progress.advance(task_id),
        )


def _run_single_pass(args, config: ScanConfig) -> ScanOutcome:
    batch_timestamp = current_timestamp()
    started_at = time.perf_counter()

    ip_list = discover_local_subnet() if args.discover else load_targets(args.input)
    source = "auto-discovery" if args.discover else args.input

    _print_configuration(source, len(ip_list), config)
    results = _scan_with_progress(ip_list, config)
    duration = time.perf_counter() - started_at

    return ScanOutcome(
        results=results,
        frame=results_dataframe(results, batch_timestamp, duration),
        batch_timestamp=batch_timestamp,
        duration_s=duration,
        source=source,
    )


def _report_changes(
    history: HistoryService,
    options: HistoryOptions,
    scan_id: int,
    source: str,
) -> None:
    """Compare the scan just stored against the previous one from that source."""
    try:
        diff = history.compare_with_previous(
            scan_id,
            source=None if options.any_source else source,
            options=options.diff,
        )
    except HistoryError as exc:
        console.print(f"[warning]Change report skipped:[/warning] {exc}")
        return

    print_diff(diff)
    if options.export_formats:
        export_diff(diff, options.export_base, options.export_formats)


def _store_and_compare(
    options: HistoryOptions,
    config: ScanConfig,
    outcome: ScanOutcome,
) -> Optional[int]:
    if not options.enabled:
        if options.compare:
            console.print(
                "[warning]Change detection needs scan history; "
                "drop --no-history to enable it.[/warning]"
            )
        return None

    try:
        history = HistoryService.open(options.db_path)
        scan_id = history.record_scan(
            source=outcome.source,
            results=outcome.results,
            config=config,
            duration_s=outcome.duration_s,
        )
    except HistoryError as exc:
        console.print(f"[warning]Scan history unavailable:[/warning] {exc}")
        log.debug("history recording failed", exc_info=True)
        return None

    if options.compare:
        _report_changes(history, options, scan_id, outcome.source)
    return scan_id


def run_scan(args) -> None:
    args.threads = clamp_int(args.threads, 1, 500)
    args.timeout = clamp_int(args.timeout, 1, 60)
    args.count = clamp_int(args.count, 1, 10)
    args.dns_cache_ttl = clamp_int(getattr(args, "dns_cache_ttl", 300), 0, 86400)

    config = _config_from_args(args)
    history_options = _history_options(args)
    _ensure_input_file(args)

    while True:
        outcome = _run_single_pass(args, config)

        save_results(outcome.frame, args.output, args.formats)
        print_summary(outcome.frame, outcome.batch_timestamp, outcome.duration_s)
        _store_and_compare(history_options, config, outcome)

        if not args.interval:
            return

        time.sleep(args.interval * 60)
