"""CLI scan workflow: run a scan, save reports, store history, report changes."""

from __future__ import annotations

import concurrent.futures
import logging
import math
import os
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from ipmg.core.diff import DiffOptions
from ipmg.core.discovery import discover_targets
from ipmg.core.engine import DEFAULT_DNS_TIMEOUT_S, HostResult, ScanConfig, execute_scan
from ipmg.core.health import HealthPolicy, HostsDownError, check_health
from ipmg.core.httpcheck import (
    DEFAULT_EXPECT,
    DEFAULT_HTTP_TIMEOUT_S,
    HttpCheckOptions,
    HttpCheckResult,
    format_expect,
    parse_expect,
    run_http_checks,
)
from ipmg.core.portscan import DEFAULT_PORTS
from ipmg.exceptions import FileIOError, HistoryError, IPMGError
from ipmg.infrastructure.file_io import (
    DEFAULT_INPUT_FILE,
    create_sample_file,
    describe_sources,
    load_all_targets,
    save_http_results,
    save_results,
    save_snmp_results,
)
from ipmg.infrastructure.incremental import (
    DEFAULT_AUTOSAVE_S,
    IncrementalOptions,
    IncrementalReport,
    PartialReport,
    find_partial_report,
    load_partial_report,
)
from ipmg.infrastructure.notify import (
    NotifyOptions,
    notify_options,
    send_alert,
    send_notifications,
)
from ipmg.infrastructure.retention import prune_reports
from ipmg.reporting import ui
from ipmg.reporting.diff_report import export_diff, print_diff
from ipmg.reporting.frames import ReportTable, report_columns, results_table
from ipmg.reporting.live import DEFAULT_REFRESH_S, StreamOptions, scan_display
from ipmg.reporting.machine import MachineOutput, MachineStream, write_array
from ipmg.reporting.summary import print_http_checks, print_snmp, print_summary
from ipmg.services.history_service import HistoryService
from ipmg.services.snmp_settings import describe_credentials, snmp_options
from ipmg.utils.helpers import current_timestamp, timestamp_str

if TYPE_CHECKING:
    from ipmg.core.snmp import SnmpOptions, SnmpResult

log = logging.getLogger(__name__)

#: What a scan writes when --formats is not given.
DEFAULT_FORMATS = ("xlsx",)

#: How the Config line names each --probe method.
PROBE_LABELS = {"icmp": "ICMP", "tcp": "TCP", "icmp,tcp": "ICMP, then TCP"}

#: The history source of a run that only made HTTP checks (no --input).
HTTP_ONLY_SOURCE = "http-checks"


@dataclass(frozen=True)
class ScanOutcome:
    """Everything one scan pass produced."""

    results: list[HostResult]
    frame: ReportTable
    batch_timestamp: datetime
    duration_s: float
    source: str
    #: File-name stamp shared by the incremental writes and the final report.
    timestamp: str
    #: Report file name prefix; a resumed scan keeps the one it started with.
    output: str
    #: ``--http-check`` results, in the order the URLs were given.
    http_results: list[HttpCheckResult] = field(default_factory=list)
    #: Whether this pass probed hosts at all; a run of only HTTP checks does not.
    scanned_hosts: bool = True
    #: ``--snmp`` polls of the hosts that answered, in scan order.
    snmp_results: list[SnmpResult] = field(default_factory=list)


@dataclass(frozen=True)
class HistoryOptions:
    """How a scan should interact with the stored history."""

    enabled: bool = True
    compare: bool = False
    any_source: bool = False
    db_path: str | None = None
    export_formats: tuple[str, ...] = ()
    export_base: str = "changes"
    diff: DiffOptions = field(default_factory=DiffOptions)
    notify: NotifyOptions = field(default_factory=NotifyOptions)
    #: After storing a scan, keep only this many of its source's scans.
    keep_scans: int | None = None


def _history_options(args) -> HistoryOptions:
    """Read history settings off the parsed arguments, with safe defaults."""
    notify = notify_options(args)
    return HistoryOptions(
        enabled=bool(getattr(args, "history", True)),
        # A notification is about changes, so asking for one asks for the comparison.
        compare=bool(getattr(args, "compare", False)) or notify.enabled,
        any_source=bool(getattr(args, "compare_any_source", False)),
        db_path=getattr(args, "db", None),
        export_formats=tuple(getattr(args, "diff_formats", None) or ()),
        export_base=getattr(args, "diff_output", "changes"),
        diff=DiffOptions(
            latency_abs_ms=max(float(getattr(args, "latency_threshold", 5.0)), 0.0),
            latency_pct=max(float(getattr(args, "latency_pct", 25.0)), 0.0),
        ),
        notify=notify,
        keep_scans=getattr(args, "keep_scans", None),
    )


def _incremental_options(args) -> IncrementalOptions:
    """Read incremental-report settings off the parsed arguments."""
    return IncrementalOptions(
        enabled=not bool(getattr(args, "no_incremental", False)),
        autosave_s=float(getattr(args, "autosave", DEFAULT_AUTOSAVE_S)),
    ).clamped()


def _load_resume(args) -> PartialReport | None:
    """The partial report ``--resume`` points at, or the newest one for ``--output``."""
    target = getattr(args, "resume", None)
    if target is None:
        return None
    path = target or find_partial_report(args.output)
    if path is None:
        raise FileIOError(
            f"No report to resume: nothing named {args.output}_<timestamp>.<format> "
            "was found. Pass the report's path, as in --resume results_20260917_120000.jsonl."
        )
    return load_partial_report(path)


def machine_output(args) -> MachineOutput:
    """Read the stdout-output settings off the parsed arguments.

    Public because the command has to know before it prints its banner, which
    happens before the scan starts.
    """
    return MachineOutput(
        array=bool(getattr(args, "json", False)),
        stream=bool(getattr(args, "jsonl", False)),
    )


def _report_formats(args, machine: MachineOutput) -> list[str]:
    """Which report files this scan should write.

    An explicit ``--formats`` always stands. Without one a scan writes xlsx,
    except when it is piping its results to stdout: a scan run for a script's
    benefit should not leave a spreadsheet behind that nobody asked for.
    """
    formats = getattr(args, "formats", None)
    if formats is not None:
        return list(formats)
    return [] if machine.enabled else list(DEFAULT_FORMATS)


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
        dns_timeout=getattr(args, "dns_timeout", DEFAULT_DNS_TIMEOUT_S),
        resolve_active_only=bool(getattr(args, "resolve_active_only", False)),
        probe=getattr(args, "probe", None) or "icmp",
        mac_lookup=bool(getattr(args, "mac", False)),
    ).clamped()


def http_check_urls(args) -> list[str]:
    return [url for url in (getattr(args, "http_check", None) or []) if url.strip()]


def _http_options(args) -> HttpCheckOptions:
    try:
        expect = parse_expect(getattr(args, "http_expect", None) or DEFAULT_EXPECT)
    except ValueError as exc:
        raise FileIOError(f"--http-expect: {exc}") from exc
    return HttpCheckOptions(
        timeout_s=float(getattr(args, "http_timeout", DEFAULT_HTTP_TIMEOUT_S)),
        method=getattr(args, "http_method", None) or "GET",
        expect=expect,
        follow_redirects=not bool(getattr(args, "http_no_redirects", False)),
        verify_tls=not bool(getattr(args, "http_insecure", False)),
    ).clamped()


def _health_policy(args) -> HealthPolicy:
    """Read the --fail-on-down and --min-active checks off the parsed arguments."""
    return HealthPolicy(
        fail_on_down=bool(getattr(args, "fail_on_down", False)),
        min_active_pct=getattr(args, "min_active", None),
    )


def _ensure_output_folder(args) -> None:
    """Create the folder ``--output`` names, before the scan rather than after it.

    A missing folder used to fail the save only once the whole scan had run,
    which for a service meant every pass was lost.
    """
    folder = Path(args.output).parent
    if not args.formats or folder == Path("."):
        return
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise FileIOError(f"Cannot create the report folder {folder}: {exc}") from exc


def _ensure_input_file(args) -> None:
    """Fall back to the default input file, creating a sample only for that default.

    An explicit ``--input`` that does not exist is deliberately left alone:
    creating it would silently scan the sample addresses instead of the hosts
    the user meant, so ``load_targets`` reports it as missing.
    """
    if args.discover or args.input or http_check_urls(args):
        return
    args.input = [DEFAULT_INPUT_FILE]
    if not os.path.exists(DEFAULT_INPUT_FILE):
        create_sample_file(DEFAULT_INPUT_FILE)
        ui.blank()
        ui.note(
            f"Created {DEFAULT_INPUT_FILE} with sample targets (8.8.8.8, 1.1.1.1). "
            "Edit it, or pass --input to scan your own hosts."
        )


def snmp_description(args, snmp: SnmpOptions) -> str:
    """The SNMP line of the Config block: how devices are polled, and as whom."""
    sep = f" {ui.glyph('sep')} "
    parts = [
        f"v{snmp.version}",
        f"port {snmp.port}",
        f"{snmp.timeout_s:g}s timeout",
        f"{snmp.retries} {'retry' if snmp.retries == 1 else 'retries'}",
        describe_credentials(args),
    ]
    if not snmp.interfaces:
        parts.append("system group only")
    return sep.join(parts)


def _print_configuration(
    sources: list[str],
    targets: int,
    config: ScanConfig,
    urls: Sequence[str] = (),
    http: HttpCheckOptions | None = None,
    snmp_line: str = "",
) -> None:
    ping_word = "ping" if config.count == 1 else "pings"
    ui.blank()
    if urls and http is not None:
        ui.field(
            "HTTP",
            f"{ui.plural(len(urls), 'URL')} {ui.glyph('sep')} {http.method} {ui.glyph('sep')} "
            f"{http.timeout_s:g}s timeout {ui.glyph('sep')} expect {format_expect(http.expect)}"
            + ("" if http.verify_tls else f" {ui.glyph('sep')} TLS not verified"),
        )
        if not targets:
            return
    # One source per line: a scan that merges a file with a few extra hosts
    # should show which hosts those were, not one run-together line.
    ui.field_list("Source", sources)
    ui.fields(
        [
            ("Targets", ui.plural(targets, "host")),
            (
                "Config",
                f"{config.threads} threads {ui.glyph('sep')} {config.timeout}s timeout "
                f"{ui.glyph('sep')} {config.count} {ping_word}"
                + (f" {ui.glyph('sep')} reverse DNS" if config.resolve else "")
                + (f" {ui.glyph('sep')} MAC lookup" if config.mac_lookup else "")
                + (
                    f" {ui.glyph('sep')} {ui.plural(len(config.ports), 'port')} scan"
                    if config.scan_ports
                    else ""
                )
                + (
                    f" {ui.glyph('sep')} {PROBE_LABELS[config.probe]} probe"
                    if config.probe != "icmp"
                    else ""
                ),
            ),
        ]
    )
    if snmp_line:
        ui.field("SNMP", snmp_line)


def _poll_snmp(
    results: Sequence[HostResult], options: SnmpOptions, threads: int
) -> list[SnmpResult]:
    """Poll the hosts that answered, within ``--threads``, after the sweep."""
    from ipmg.core.snmp import poll_device

    ips = [result.ip for result in results if result.status == "Active"]
    if not ips:
        ui.blank()
        ui.note("SNMP: no host answered, so none was polled.")
        return []
    with (
        ui.progress("SNMP") as bar,
        concurrent.futures.ThreadPoolExecutor(
            max_workers=max(1, min(threads, len(ips))), thread_name_prefix="ipmg-snmp"
        ) as pool,
    ):
        task = bar.add_task("snmp", total=len(ips))
        futures = [pool.submit(poll_device, ip, options) for ip in ips]
        for _done in concurrent.futures.as_completed(futures):
            bar.advance(task)
        return [future.result() for future in futures]


def _scan_with_progress(
    ip_list: list[str],
    config: ScanConfig,
    stream: StreamOptions,
    report: IncrementalReport | None = None,
    machine: MachineStream | None = None,
) -> list[HostResult]:
    # The incremental report and the stdout stream take the same record(result)
    # call, so one callback can feed both.
    writers = [writer for writer in (report, machine) if writer is not None]

    with scan_display(len(ip_list), config, stream) as on_progress:
        if not writers:
            return execute_scan(ip_list, config, on_result=on_progress)

        def on_result(result: HostResult, done: int, total: int) -> None:
            # Everything is written before the row is drawn, so what the
            # operator sees on screen is never ahead of what was written out.
            for writer in writers:
                writer.record(result)
            on_progress(result, done, total)

        return execute_scan(ip_list, config, on_result=on_result)


def _open_report(
    args,
    incremental: IncrementalOptions,
    output: str,
    timestamp: str,
    batch_timestamp: datetime,
    previous: list[HostResult],
    previous_elapsed_s: float,
    columns: tuple[str, ...],
) -> IncrementalReport | None:
    """Start writing this pass's report, unless incremental writing is off."""
    if not incremental.enabled or not args.formats:
        return None
    return IncrementalReport(
        base=output,
        formats=args.formats,
        timestamp=timestamp,
        batch_timestamp=batch_timestamp,
        options=incremental,
        previous=previous,
        previous_elapsed_s=previous_elapsed_s,
        columns=columns,
    )


def _announce_resume(resume: PartialReport, done: int, total: int) -> None:
    ui.fields(
        [
            ("Resuming", resume.path),
            ("Left", f"{ui.plural(total - done, 'host')} of {total} still to scan"),
        ]
    )


def _announce_partial(report: IncrementalReport) -> None:
    """Point at the reports an interrupted pass left behind."""
    paths = report.written_paths
    if not paths:
        return
    ui.blank()
    ui.field_list("Partial report", paths)


def _run_pass(
    ip_list: list[str],
    config: ScanConfig,
    stream: StreamOptions,
    report: IncrementalReport | None,
    machine: MachineStream | None = None,
) -> list[HostResult]:
    """Scan every host, keeping the partial report if the pass is cut short."""
    if report is None:
        return _scan_with_progress(ip_list, config, stream, machine=machine)

    try:
        with report:
            return _scan_with_progress(ip_list, config, stream, report, machine)
    except BaseException:
        # BaseException, not Exception: Ctrl+C is the interruption this
        # feature exists for, and it must not pass by unannounced.
        _announce_partial(report)
        raise


def _run_single_pass(
    args,
    config: ScanConfig,
    stream: StreamOptions,
    incremental: IncrementalOptions,
    machine: MachineOutput,
    resume: PartialReport | None = None,
    snmp: SnmpOptions | None = None,
) -> ScanOutcome:
    batch_timestamp = (resume and resume.batch_timestamp) or current_timestamp()
    timestamp = resume.timestamp if resume else timestamp_str()
    output = resume.base if resume else args.output
    started_at = time.perf_counter()

    urls = http_check_urls(args)
    http = _http_options(args) if urls else None
    if args.discover:
        ip_list, sources = discover_targets(args.discover)
    elif args.input:
        sources = list(args.input)
        ip_list = load_all_targets(sources)
    else:
        # --http-check on its own: there are no hosts to probe.
        ip_list, sources = [], [HTTP_ONLY_SOURCE]
    source = describe_sources(sources)
    scanned_hosts = bool(args.discover or args.input)

    # Hosts the earlier run finished are kept only if they are still targets,
    # so resuming against an edited list never reports hosts it no longer has.
    targets = set(ip_list)
    previous = [result for result in resume.results if result.ip in targets] if resume else []
    previous_elapsed_s = resume.elapsed_s if resume else 0.0
    scanned = {result.ip for result in previous}
    remaining = [ip for ip in ip_list if ip not in scanned]

    _print_configuration(
        sources,
        len(ip_list) if scanned_hosts else 0,
        config,
        urls,
        http,
        snmp_description(args, snmp) if snmp is not None and scanned_hosts else "",
    )
    if resume:
        _announce_resume(resume, len(previous), len(ip_list))
    columns = report_columns(config)
    report = _open_report(
        args, incremental, output, timestamp, batch_timestamp, previous, previous_elapsed_s, columns
    )
    machine_stream = (
        MachineStream(batch_timestamp, previous, previous_elapsed_s, columns)
        if machine.stream
        else None
    )
    results = previous
    if scanned_hosts:
        results = previous + _run_pass(remaining, config, stream, report, machine_stream)
    snmp_results: list[SnmpResult] = []
    if snmp is not None and scanned_hosts:
        snmp_results = _poll_snmp(results, snmp, config.threads)
    http_results: list[HttpCheckResult] = []
    if urls:
        # Within --threads, like the host probes, and after them, so the two
        # never compete for the same budget.
        http_results = run_http_checks(urls, http, max_workers=config.threads)
    duration = previous_elapsed_s + time.perf_counter() - started_at

    return ScanOutcome(
        results=results,
        frame=results_table(results, batch_timestamp, duration, columns),
        batch_timestamp=batch_timestamp,
        duration_s=duration,
        source=source,
        timestamp=timestamp,
        output=output,
        http_results=http_results,
        scanned_hosts=scanned_hosts,
        snmp_results=snmp_results,
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
    # Last, so an alert that cannot be delivered has already cost nothing.
    send_notifications(diff, options.notify)


def _store_and_compare(
    options: HistoryOptions,
    config: ScanConfig,
    outcome: ScanOutcome,
) -> int | None:
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
            http_checks=outcome.http_results,
            snmp_devices=outcome.snmp_results,
        )
    except HistoryError as exc:
        ui.blank()
        ui.warn(f"Scan history unavailable: {exc}")
        log.debug("history recording failed", exc_info=True)
        return None

    if options.compare:
        _report_changes(history, options, scan_id, outcome.source)
    if options.keep_scans:
        # After the comparison, which needs the previous scan.
        _prune_history(history, options.keep_scans, outcome.source)
    return scan_id


def _prune_history(history: HistoryService, keep: int, source: str) -> None:
    try:
        plan = history.plan_prune(keep=keep, source=source)
        deleted = history.prune(plan)
    except HistoryError as exc:
        ui.blank()
        ui.warn(f"Old scans not pruned: {exc}")
        return
    if deleted:
        ui.blank()
        ui.note(f"Removed {ui.plural(deleted, 'older scan')} of {source} (--keep-scans {keep}).")


def _prune_reports(args, outcome: ScanOutcome) -> None:
    keep = getattr(args, "keep_reports", None)
    if not keep:
        return
    snmp_base = snmp_report_base(outcome.output)
    removed = prune_reports(
        [outcome.output, http_report_base(outcome.output), snmp_base, f"{snmp_base}_interfaces"],
        keep,
        protect=outcome.timestamp,
    )
    if removed:
        ui.blank()
        ui.note(f"Removed {ui.plural(len(removed), 'older report')} (--keep-reports {keep}).")


def _scan_pass(
    args,
    config: ScanConfig,
    stream: StreamOptions,
    incremental: IncrementalOptions,
    machine: MachineOutput,
    history_options: HistoryOptions,
    health: HealthPolicy,
    resume: PartialReport | None,
    snmp: SnmpOptions | None = None,
) -> str | None:
    """Scan once, write the reports and history, and say why it failed --fail-on-down."""
    outcome = _run_single_pass(args, config, stream, incremental, machine, resume, snmp)

    if outcome.scanned_hosts:
        print_summary(outcome.frame, outcome.batch_timestamp, outcome.duration_s)
    if outcome.snmp_results:
        print_snmp(outcome.snmp_results)
    if outcome.http_results:
        print_http_checks(outcome.http_results)
    if machine.array:
        write_array(outcome.frame)
    if outcome.scanned_hosts:
        # Overwrites whatever the incremental writer left on those same paths,
        # so a finished scan produces exactly the report it always did.
        save_results(outcome.frame, outcome.output, args.formats, timestamp=outcome.timestamp)
    if outcome.http_results:
        save_http_results(
            outcome.http_results,
            http_report_base(outcome.output),
            args.formats,
            batch_timestamp=outcome.batch_timestamp,
            timestamp=outcome.timestamp,
        )
    if outcome.snmp_results:
        save_snmp_results(
            outcome.snmp_results,
            snmp_report_base(outcome.output),
            args.formats,
            batch_timestamp=outcome.batch_timestamp,
            timestamp=outcome.timestamp,
        )
    _prune_reports(args, outcome)
    _store_and_compare(history_options, config, outcome)
    return check_health(outcome.results, health, outcome.http_results)


def http_report_base(output: str) -> str:
    """HTTP check reports sit beside the host reports: ``results_http_<timestamp>.csv``."""
    return f"{output}_http"


def snmp_report_base(output: str) -> str:
    """SNMP reports sit beside the host reports: ``results_snmp_<timestamp>.csv``."""
    return f"{output}_snmp"


def next_pass_delay(cadence_start: float, period_s: float, now: float) -> float:
    """Seconds until the next ``--interval`` slot, counted from the first pass.

    Passes start at ``cadence_start + n * period_s``, so ``--interval 5`` means
    every five minutes whatever each scan takes, rather than five minutes of
    sleep after it. A pass that overruns its slot skips to the next free one
    instead of starting the next pass straight away.
    """
    elapsed = max(now - cadence_start, 0.0)
    slots_done = math.floor(elapsed / period_s) + 1
    return cadence_start + slots_done * period_s - now


def _report_failed_pass(exc: BaseException, notify: NotifyOptions) -> None:
    """Keep the monitor going after a pass that could not scan, and say so."""
    reason = str(exc).strip() or type(exc).__name__
    if not reason.endswith((".", "!", "?")):
        reason += "."
    ui.blank()
    ui.warn(f"This pass could not scan: {reason} The monitor continues at the next interval.")
    log.debug("interval pass failed", exc_info=True)
    # A monitor that cannot scan is itself worth an alert.
    send_alert("IPMG could not scan", str(exc), notify)


def run_scan(args) -> None:
    machine = machine_output(args)
    if machine.enabled:
        # Normally done by the command before its banner; repeated here, since
        # it must also hold for anything that calls run_scan directly.
        ui.use_stderr()
    args.formats = _report_formats(args, machine)

    config = _config_from_args(args)
    history_options = _history_options(args)
    health = _health_policy(args)
    stream = _stream_options(args)
    incremental = _incremental_options(args)
    # Before anything is scanned: missing SNMPv3 credentials are a mistake
    # to fix now, not after the sweep.
    snmp = snmp_options(args)
    _ensure_input_file(args)
    _ensure_output_folder(args)
    resume = _load_resume(args)

    period_s = (args.interval or 0) * 60
    cadence_start = time.monotonic()
    first_pass = True
    while True:
        pass_started = time.monotonic()
        try:
            failure = _scan_pass(
                args, config, stream, incremental, machine, history_options, health, resume, snmp
            )
        except (IPMGError, OSError) as exc:
            # A one-off scan reports its error and exits, and so does a monitor
            # whose very first pass fails: that is a mistake to fix, not a
            # blip to ride out. After that a failed pass (a target file being
            # rewritten, --discover during a network blip, a full disk) must
            # not end the watch.
            if not args.interval or first_pass:
                raise
            _report_failed_pass(exc, history_options.notify)
            failure = None
        # Only the first pass picks up where an earlier run stopped; every
        # --interval pass after it is a fresh scan.
        resume = None
        first_pass = False

        if not args.interval:
            if failure:
                # Raised only now, with the reports and history already written.
                raise HostsDownError(failure)
            return

        # A repeating scan keeps going when hosts are down: it is the monitor,
        # and stopping it would end the watch at the moment it matters.
        if failure:
            ui.blank()
            ui.warn(failure)

        now = time.monotonic()
        if now - pass_started > period_s:
            ui.blank()
            ui.note(
                f"That pass took longer than --interval {args.interval}; "
                "the next one starts at the following interval."
            )
        time.sleep(next_pass_delay(cadence_start, period_s, now))
