"""Write a scan report while the scan is still running.

A /16 sweep can take a long time, and until it finished IPMG wrote nothing:
one Ctrl+C, one dropped SSH session, one OOM kill, and the whole pass was
gone. So every result is handed to a writer the moment it lands.

Row-oriented formats (``csv``, ``jsonl``) are appended to and flushed per
host, which leaves a readable report on disk at every instant — even after a
``kill -9``, where the worst case is a truncated final line. The formats that
have no valid partial form (``xlsx``, ``json``, ``md``) are instead rewritten
from the results so far, at most every ``autosave_s`` seconds, through a
temporary file that is renamed into place; a reader therefore sees either the
previous snapshot or the next one, never a half-written file.

These files are the same paths :func:`ipmg.infrastructure.file_io.save_results`
writes at the end of the pass, which is why the scan shares its timestamp with
the writer. A completed scan overwrites every snapshot with the canonical
report, so incremental writing changes what survives an interruption without
changing what a finished scan produces.

That partial report is also where an interrupted scan picks up again:
:func:`load_partial_report` reads the hosts it already holds, and ``--resume``
scans only the rest, writing to the same files under the same timestamp.
"""

from __future__ import annotations

import io
import json
import logging
import math
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import IO, Dict, List, Optional, Sequence, Set, Tuple

import pandas as pd

from ipmg.core.engine import HostResult
from ipmg.exceptions import FileIOError
from ipmg.reporting.frames import RESULT_COLUMNS, format_open_ports
from ipmg.utils.helpers import FORMULA_PREFIXES, spreadsheet_escape

log = logging.getLogger(__name__)

#: Seconds between snapshots of the formats that cannot be appended to.
DEFAULT_AUTOSAVE_S = 30.0
MIN_AUTOSAVE_S = 1.0
MAX_AUTOSAVE_S = 3600.0

#: Every report format ``--formats`` accepts, in the order they are offered.
REPORT_FORMATS = ("xlsx", "csv", "json", "jsonl", "md")
#: Formats written one row at a time, and kept valid between rows.
STREAMING_FORMATS = ("csv", "jsonl")
#: Formats that only exist as a whole file, so they are re-snapshotted.
SNAPSHOT_FORMATS = ("xlsx", "json", "md")
#: Formats a scan can be resumed from, most faithful first. ``md`` only
#: previews the first 25 hosts, so it cannot stand in for the whole report.
RESUMABLE_FORMATS = ("jsonl", "csv", "json", "xlsx")

#: ``<base>_<YYYYMMDD_HHMMSS>.<format>``, the name every report is saved under.
_REPORT_NAME = re.compile(r"^(?P<prefix>.+)_(?P<timestamp>\d{8}_\d{6})\.(?P<fmt>[a-z]+)$")


@dataclass(frozen=True)
class IncrementalOptions:
    """How a running scan should write its report."""

    enabled: bool = True
    autosave_s: float = DEFAULT_AUTOSAVE_S

    def clamped(self) -> "IncrementalOptions":
        return IncrementalOptions(
            enabled=self.enabled,
            autosave_s=min(max(self.autosave_s, MIN_AUTOSAVE_S), MAX_AUTOSAVE_S),
        )


def _csv_cell(value: object) -> str:
    """One CSV field, escaped for both the format and the spreadsheet reading it."""
    text = "" if value is None else spreadsheet_escape(value)
    if any(char in text for char in ',"\n\r'):
        return '"' + text.replace('"', '""') + '"'
    return text


def jsonl_record(row: Dict[str, object]) -> str:
    """One JSON Lines record, rendered the same way mid-scan and at the end.

    ``default=str`` keeps timestamps readable as the text they print as,
    rather than the epoch milliseconds pandas would emit.
    """
    return json.dumps(dict(row), default=str) + "\n"


def result_row(
    result: HostResult,
    batch_timestamp: object,
    elapsed_s: Optional[float],
) -> Dict[str, object]:
    """One report row, with the same columns a finished scan writes.

    ``elapsed_s`` fills "Scan Duration (s)" with the time the scan had been
    running when this host answered. The finished report replaces it with the
    duration of the whole pass; until then, elapsed time is the only honest
    value available.
    """
    return {
        "IP Address": result.ip,
        "Status": result.status,
        "Latency": result.latency,
        "Hostname": result.hostname,
        "Open Ports": format_open_ports(result.open_ports),
        "Batch Timestamp": str(batch_timestamp),
        "Scan Duration (s)": None if elapsed_s is None else round(elapsed_s, 3),
    }


class IncrementalReport:
    """Keep a valid report on disk for a scan that has not finished yet.

    Used as a context manager around one scan pass; :meth:`record` is called
    for every host as it completes. Failures are logged and swallowed: a
    report that cannot be written must never take the scan down with it.
    """

    def __init__(
        self,
        base: str,
        formats: Sequence[str],
        timestamp: str,
        batch_timestamp: object,
        options: IncrementalOptions = IncrementalOptions(),
        previous: Optional[Sequence[HostResult]] = None,
        previous_elapsed_s: float = 0.0,
    ) -> None:
        self.options = options.clamped()
        self._base = base
        self._timestamp = timestamp
        self._batch_timestamp = batch_timestamp
        self._formats = [fmt for fmt in dict.fromkeys(formats)]
        self._results: List[HostResult] = list(previous or ())
        # Resumed rows keep the time the earlier run had reached, and new rows
        # count on from it, so a report interrupted twice still knows how long
        # the whole scan has taken.
        self._rows: List[Dict[str, object]] = [
            result_row(result, batch_timestamp, previous_elapsed_s if previous else None)
            for result in self._results
        ]
        self._handles: Dict[str, IO[str]] = {}
        self._written: Dict[str, None] = {}
        self._started_at = time.monotonic() - previous_elapsed_s
        self._last_snapshot = time.monotonic()
        self._closed = False

    # -- lifecycle ---------------------------------------------------------

    def path_for(self, fmt: str) -> str:
        return f"{self._base}_{self._timestamp}.{fmt}"

    @property
    def results(self) -> List[HostResult]:
        """Every result written so far, resumed rows first."""
        return list(self._results)

    @property
    def written_paths(self) -> List[str]:
        """Report files this writer has actually put on disk, in format order."""
        return list(self._written)

    def __enter__(self) -> "IncrementalReport":
        self.open()
        return self

    def __exit__(self, exc_type, _exc, _tb) -> None:
        # An exception means the scan is ending early — Ctrl+C, a ping
        # failure, a crash — which is exactly when the snapshot formats need
        # one last write before the handles go away.
        self.close(snapshot=exc_type is not None)

    def open(self) -> None:
        for fmt in self._formats:
            if fmt not in STREAMING_FORMATS:
                continue
            try:
                self._handles[fmt] = self._open_stream(fmt)
                self._written[self.path_for(fmt)] = None
            except OSError as exc:
                log.debug("incremental %s writer unavailable: %s", fmt, exc)

    def _open_stream(self, fmt: str) -> IO[str]:
        path = Path(self.path_for(fmt))
        # Resumed rows are replayed into a fresh file rather than appended to
        # the old one: the earlier file may have a truncated last line, and
        # rewriting it is cheap next to the scan itself.
        handle = open(path, "w", encoding="utf-8", newline="")
        if fmt == "csv":
            handle.write(",".join(RESULT_COLUMNS) + "\n")
        for row in self._rows:
            handle.write(self._render(fmt, row))
        handle.flush()
        return handle

    # -- writing -----------------------------------------------------------

    def record(self, result: HostResult) -> None:
        """Append one finished host to every report being written."""
        if self._closed:
            return

        row = result_row(result, self._batch_timestamp, time.monotonic() - self._started_at)
        self._results.append(result)
        self._rows.append(row)

        for fmt, handle in list(self._handles.items()):
            try:
                handle.write(self._render(fmt, row))
                handle.flush()
            except (OSError, ValueError) as exc:  # pragma: no cover - disk failure
                log.debug("incremental %s write failed: %s", fmt, exc)
                self._handles.pop(fmt, None)

        if self._due_for_snapshot():
            self.snapshot()

    def _render(self, fmt: str, row: Dict[str, object]) -> str:
        if fmt == "csv":
            return ",".join(_csv_cell(row[column]) for column in RESULT_COLUMNS) + "\n"
        return jsonl_record(row)

    def _due_for_snapshot(self) -> bool:
        if not any(fmt in SNAPSHOT_FORMATS for fmt in self._formats):
            return False
        now = time.monotonic()
        if now - self._last_snapshot < self.options.autosave_s:
            return False
        self._last_snapshot = now
        return True

    def snapshot(self) -> List[str]:
        """Rewrite the whole-file formats from the results collected so far."""
        formats = [fmt for fmt in self._formats if fmt in SNAPSHOT_FORMATS]
        if not formats or not self._rows:
            return []

        # file_io owns the canonical writers, and reusing them is what keeps a
        # snapshot indistinguishable from a finished report.
        from ipmg.infrastructure.file_io import write_report

        frame = pd.DataFrame(self._rows, columns=RESULT_COLUMNS)
        written: List[str] = []
        for fmt in formats:
            try:
                write_report(frame, self.path_for(fmt), fmt)
            except Exception as exc:  # pragma: no cover - snapshot is best effort
                log.debug("incremental %s snapshot failed: %s", fmt, exc)
                continue
            self._written[self.path_for(fmt)] = None
            written.append(self.path_for(fmt))
        self._last_snapshot = time.monotonic()
        return written

    def close(self, snapshot: bool = False) -> None:
        if self._closed:
            return
        self._closed = True

        if snapshot:
            self.snapshot()

        for fmt, handle in self._handles.items():
            try:
                handle.close()
            except OSError as exc:  # pragma: no cover - disk failure
                log.debug("incremental %s close failed: %s", fmt, exc)
        self._handles.clear()


@dataclass(frozen=True)
class PartialReport:
    """The hosts an interrupted scan left in its report, ready to resume."""

    path: str
    #: The ``--output`` prefix and timestamp the report was saved under, so a
    #: resumed scan writes back to the same files.
    base: str
    timestamp: str
    results: Tuple[HostResult, ...]
    batch_timestamp: Optional[datetime]
    #: How long the earlier run had been scanning when it stopped.
    elapsed_s: float

    @property
    def scanned(self) -> Set[str]:
        return {result.ip for result in self.results}


def find_partial_report(base: str) -> Optional[str]:
    """The newest report saved under ``base`` that a scan can resume from.

    When one scan left several formats behind, the most faithful one wins:
    ``jsonl`` and ``csv`` hold every host up to the moment of interruption,
    while ``json`` and ``xlsx`` are only as recent as their last autosave.
    """
    directory = Path(base).parent
    prefix = Path(base).name
    candidates = []
    try:
        entries = list(directory.iterdir())
    except OSError:
        return None
    for entry in entries:
        match = _REPORT_NAME.match(entry.name)
        if not match or match["prefix"] != prefix or match["fmt"] not in RESUMABLE_FORMATS:
            continue
        rank = RESUMABLE_FORMATS.index(match["fmt"])
        candidates.append((match["timestamp"], -rank, str(entry)))
    return max(candidates)[2] if candidates else None


def load_partial_report(path: str) -> PartialReport:
    """Read the hosts a report already holds, including one cut off mid-write."""
    name = _REPORT_NAME.match(Path(path).name)
    if name is None:
        raise FileIOError(
            f"Cannot resume from {path}: expected a report named like "
            "results_20260917_120000.jsonl, as IPMG saves them."
        )
    fmt = name["fmt"]
    if fmt not in RESUMABLE_FORMATS:
        raise FileIOError(
            f"Cannot resume from a .{fmt} report; use the "
            f"{', '.join(RESUMABLE_FORMATS)} report from the same scan instead."
        )

    try:
        frame = _read_report(path, fmt)
    except FileNotFoundError:
        raise FileIOError(f"Report to resume not found: {path}") from None
    except (OSError, ValueError) as exc:
        raise FileIOError(f"Cannot read report {path}: {exc}") from exc

    missing = [column for column in ("IP Address", "Status") if column not in frame.columns]
    if missing:
        raise FileIOError(f"{path} is not an IPMG report: missing {', '.join(missing)}.")

    # A spreadsheet format stores cells escaped against formula injection;
    # the scan itself needs the text the host actually reported.
    unescape = fmt in ("csv", "xlsx")
    by_ip: Dict[str, HostResult] = {}
    for row in frame.to_dict(orient="records"):
        result = _row_result(row, unescape)
        if result is not None:
            by_ip[result.ip] = result

    base = str(Path(path).parent / name["prefix"])
    return PartialReport(
        path=path,
        base=base,
        timestamp=name["timestamp"],
        results=tuple(by_ip.values()),
        batch_timestamp=_batch_timestamp(frame),
        elapsed_s=_elapsed(frame),
    )


def _read_report(path: str, fmt: str) -> pd.DataFrame:
    if fmt == "xlsx":
        return pd.read_excel(path, dtype=object)
    if fmt == "json":
        with open(path, encoding="utf-8") as handle:
            return pd.DataFrame(json.load(handle))

    with open(path, encoding="utf-8", newline="") as handle:
        text = handle.read()
    # Rows are flushed whole, so a last line without its newline is one the
    # previous run was killed while writing. It is dropped, and that host is
    # simply scanned again.
    if text and not text.endswith("\n"):
        text = text[: text.rfind("\n") + 1]

    if fmt == "csv":
        if not text.strip():
            return pd.DataFrame(columns=RESULT_COLUMNS)
        return pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)

    records = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"line {number} is not valid JSON ({exc.msg})") from None
    return pd.DataFrame(records)


def _is_blank(value: object) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value)) or value == ""


def _text(value: object, unescape: bool = False) -> str:
    if _is_blank(value):
        return ""
    text = str(value).strip()
    if unescape and text.startswith("'") and text[1:].startswith(FORMULA_PREFIXES):
        return text[1:]
    return text


def _latency(value: object) -> Optional[float]:
    if _is_blank(value):
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _open_ports(value: object) -> Tuple[int, ...]:
    ports = []
    for piece in _text(value).split(","):
        try:
            ports.append(int(float(piece)))
        except ValueError:
            continue
    return tuple(ports)


def _row_result(row: Dict[str, object], unescape: bool) -> Optional[HostResult]:
    ip = _text(row.get("IP Address"))
    status = _text(row.get("Status"))
    if not ip or not status:
        return None
    return HostResult(
        ip=ip,
        status=status,
        latency=_latency(row.get("Latency")),
        hostname=_text(row.get("Hostname"), unescape),
        open_ports=_open_ports(row.get("Open Ports")),
    )


def _batch_timestamp(frame: pd.DataFrame) -> Optional[datetime]:
    """The resumed scan's start time, so both runs report as one batch."""
    if "Batch Timestamp" not in frame.columns:
        return None
    for value in frame["Batch Timestamp"]:
        if _is_blank(value):
            continue
        try:
            # A finished json report stores it as epoch milliseconds.
            unit = "ms" if isinstance(value, (int, float)) else None
            return pd.to_datetime(value, unit=unit).to_pydatetime()
        except (TypeError, ValueError, OverflowError):
            return None
    return None


def _elapsed(frame: pd.DataFrame) -> float:
    if "Scan Duration (s)" not in frame.columns:
        return 0.0
    durations = pd.to_numeric(frame["Scan Duration (s)"], errors="coerce").dropna()
    return float(durations.max()) if not durations.empty else 0.0


def atomic_write_bytes(path: str, data: bytes) -> None:
    """Replace ``path`` with ``data`` in one step, or leave it untouched.

    Reports are read by other tools — and by the operator, mid-scan — so a
    file must never be observed half-written. The temporary file sits beside
    the target so the rename stays within one filesystem.
    """
    target = Path(path)
    tmp = target.with_name(f".{target.name}.tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
