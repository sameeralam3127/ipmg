"""CLI scan workflow: run a scan, save reports, store history, report changes."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Tuple

import pandas as pd

from ipmg.core.diff import DiffOptions
from ipmg.core.discovery import discover_local_subnet
from ipmg.core.engine import HostResult, ScanConfig, execute_scan
from ipmg.core.portscan import DEFAULT_PORTS
from ipmg.exceptions import HistoryError
from ipmg.infrastructure.file_io import (
    DEFAULT_INPUT_FILE,
    create_sample_file,
    load_targets,
    save_results,
)
from ipmg.infrastructure.incremental import (
    DEFAULT_AUTOSAVE_S,
    DEFAULT_FORMAT,
    IncrementalOptions,
    IncrementalReport,
)
from ipmg.infrastructure.resume import PartialReport, load_partial_report
from ipmg.reporting import ui
from ipmg.reporting.diff_report import export_diff, print_diff
from ipmg.reporting.frames import results_dataframe
from ipmg.reporting.live import DEFAULT_REFRESH_S, StreamOptions, scan_display
from ipmg.reporting.summary import print_summary
from ipmg.services.history_service import HistoryService
from ipmg.utils.helpers import current_timestamp, timestamp_str

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReportTarget:
    """Where one pass writes its report, and in which formats.

    The base name and stamp are shared by the incremental writes and the final
    save, so both land on the same files. A resumed pass takes them from the
    report it was handed instead of starting a new set.
    """

    base: str
    timestamp: str
    formats: Tuple[str, ...]


@dataclass(frozen=True)
class ScanOutcome:
    """Everything one scan pass produced."""

    results: List[HostResult]
    frame: pd.DataFrame
    batch_timestamp: datetime
    duration_s: float
    source: str
    target: ReportTarget


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


def _incremental_options(args) -> IncrementalOptions:
    """Read incremental-report settings off the parsed arguments."""
    return IncrementalOptions(
        enabled=not bool(getattr(args, "no_incremental", False)),
        autosave_s=float(getattr(args, "autosave", DEFAULT_AUTOSAVE_S)),
    ).clamped()


def _stream_options(args) -> StreamOptions:
    """Read live-output settings off the parsed arguments."""
    all_hosts = bool(getattr(args, "stream_all", False))
    return StreamOptions(
        # --stream-all is a stronger form of --stream, so it implies it.
        enabled=bool(getattr(args, "stream", False)) or all_hosts,
        all_hosts=all_hosts,
        refresh_s=float(getattr(args, "stream_refresh", DEFAULT_REFRESH_S)),
    ).clamped()


def _config_from_args(args) -> ScanConfig:
    return ScanConfig(
        timeout=args.timeout,
        count=args.count,
        threads=args.threads,
        resolve=args.resolve,
        dns_cache_ttl=getattr(args, "dns_cache_ttl", 300),
        scan_ports=getattr(args, "scan_ports", False),
        ports=tuple(getattr(args, "ports", None) or DEFAULT_PORTS),
        port_timeout=getattr(args, "port_timeout", 1.0),
    ).clamped()


def _ensure_input_file(args) -> None:
    """Fall back to the default input file, creating a sample only for that default.

    An explicit ``--input`` that does not exist is deliberately left alone:
    creating it would silently scan the sample addresses instead of the hosts
    the user meant, so ``load_targets`` reports it as missing.
    """
    if args.discover or args.input is not None:
        return
    args.input = DEFAULT_INPUT_FILE
    if not os.path.exists(DEFAULT_INPUT_FILE):
        create_sample_file(DEFAULT_INPUT_FILE)
        ui.blank()
        ui.note(
            f"Created {DEFAULT_INPUT_FILE} with sample targets (8.8.8.8, 1.1.1.1). "
            "Edit it, or pass --input to scan your own hosts."
        )


def _print_configuration(source: str, targets: int, config: ScanConfig) -> None:
    ping_word = "ping" if config.count == 1 else "pings"
    ui.blank()
    ui.fields(
        [
            ("Source", source),
            ("Targets", ui.plural(targets, "host")),
            (
                "Config",
                f"{config.threads} threads {ui.glyph('sep')} {config.timeout}s timeout "
                f"{ui.glyph('sep')} {config.count} {ping_word}"
                + (f" {ui.glyph('sep')} reverse DNS" if config.resolve else "")
                + (
                    f" {ui.glyph('sep')} {ui.plural(len(config.ports), 'port')} scan"
                    if config.scan_ports
                    else ""
                ),
            ),
        ]
    )


def _scan_with_progress(
    ip_list: List[str],
    config: ScanConfig,
    stream: StreamOptions,
    report: Optional[IncrementalReport] = None,
) -> List[HostResult]:
    with scan_display(len(ip_list), config, stream) as on_progress:
        if report is None:
            return execute_scan(ip_list, config, on_result=on_progress)

        def on_result(result: HostResult, done: int, total: int) -> None:
            # The report is written before the row is drawn, so what the
            # operator sees on screen is never ahead of what is on disk.
            report.record(result)
            on_progress(result, done, total)

        return execute_scan(ip_list, config, on_result=on_result)


def _report_target(args, partial: Optional[PartialReport]) -> ReportTarget:
    """Decide where this pass writes, honouring a report being resumed."""
    formats = list(dict.fromkeys(getattr(args, "formats", None) or ()))

    if partial is None:
        return ReportTarget(args.output, timestamp_str(), tuple(formats or [DEFAULT_FORMAT]))

    if not formats:
        # Resuming without --formats finishes the report it was handed, rather
        # than also starting a default xlsx nobody asked for.
        formats = [partial.fmt]
    elif partial.fmt not in formats:
        # Whatever --formats says, the file being resumed has to keep being
        # written: it is the one holding the hosts already scanned.
        formats.insert(0, partial.fmt)
    return ReportTarget(partial.base, partial.timestamp, tuple(formats))


def _open_report(
    target: ReportTarget,
    incremental: IncrementalOptions,
    batch_timestamp: datetime,
    partial: Optional[PartialReport],
) -> Optional[IncrementalReport]:
    """Start writing this pass's report, unless incremental writing is off."""
    if not incremental.enabled or not target.formats:
        return None
    return IncrementalReport(
        base=target.base,
        formats=target.formats,
        timestamp=target.timestamp,
        batch_timestamp=batch_timestamp,
        options=incremental,
        previous=partial.results if partial else None,
    )


def _announce_partial(report: IncrementalReport) -> None:
    """Point at the reports an interrupted pass left behind."""
    paths = report.written_paths
    if not paths:
        return
    ui.blank()
    ui.field_list("Partial report", paths)


def _run_pass(
    ip_list: List[str],
    config: ScanConfig,
    stream: StreamOptions,
    report: Optional[IncrementalReport],
) -> List[HostResult]:
    """Scan every host, keeping the partial report if the pass is cut short."""
    if report is None:
        return _scan_with_progress(ip_list, config, stream)

    try:
        with report:
            return _scan_with_progress(ip_list, config, stream, report)
    except BaseException:
        # BaseException, not Exception: Ctrl+C is the interruption this
        # feature exists for, and it must not pass by unannounced.
        _announce_partial(report)
        raise


def _announce_resume(partial: PartialReport, remaining: int) -> None:
    ui.blank()
    ui.note(
        f"Resuming {partial.path}: {ui.plural(len(partial.results), 'host')} already scanned, "
        f"{ui.plural(remaining, 'host')} left."
    )


def _run_single_pass(
    args,
    config: ScanConfig,
    stream: StreamOptions,
    incremental: IncrementalOptions,
    partial: Optional[PartialReport] = None,
) -> ScanOutcome:
    batch_timestamp = current_timestamp()
    target = _report_target(args, partial)
    started_at = time.perf_counter()

    ip_list = discover_local_subnet() if args.discover else load_targets(args.input)
    source = "auto-discovery" if args.discover else args.input

    if partial is not None:
        ip_list = partial.remaining(ip_list)

    _print_configuration(source, len(ip_list), config)
    if partial is not None:
        _announce_resume(partial, len(ip_list))

    report = _open_report(target, incremental, batch_timestamp, partial)
    # The hosts carried over come first, so the report reads in scan order.
    results = list(partial.results) if partial else []
    results.extend(_run_pass(ip_list, config, stream, report))
    duration = time.perf_counter() - started_at

    return ScanOutcome(
        results=results,
        frame=results_dataframe(results, batch_timestamp, duration),
        batch_timestamp=batch_timestamp,
        duration_s=duration,
        source=source,
        target=target,
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
        ui.blank()
        ui.warn(f"Change report skipped: {exc}")
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
            ui.blank()
            ui.warn("Change detection needs scan history; drop --no-history to enable it.")
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
        ui.blank()
        ui.warn(f"Scan history unavailable: {exc}")
        log.debug("history recording failed", exc_info=True)
        return None

    if options.compare:
        _report_changes(history, options, scan_id, outcome.source)
    return scan_id


def run_scan(args) -> None:
    config = _config_from_args(args)
    history_options = _history_options(args)
    stream = _stream_options(args)
    incremental = _incremental_options(args)
    _ensure_input_file(args)

    # Only the first pass resumes: --interval repeats are scans of their own.
    resume_from = getattr(args, "resume", None)
    partial = load_partial_report(resume_from) if resume_from else None

    while True:
        outcome = _run_single_pass(args, config, stream, incremental, partial)
        partial = None

        print_summary(outcome.frame, outcome.batch_timestamp, outcome.duration_s)
        # Overwrites whatever the incremental writer left on those same paths,
        # so a finished scan produces exactly the report it always did.
        save_results(
            outcome.frame,
            outcome.target.base,
            list(outcome.target.formats),
            timestamp=outcome.target.timestamp,
        )
        _store_and_compare(history_options, config, outcome)

        if not args.interval:
            return

        time.sleep(args.interval * 60)
