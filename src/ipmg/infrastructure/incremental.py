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
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Dict, List, Optional, Sequence

import pandas as pd

from ipmg.core.engine import HostResult
from ipmg.reporting.frames import RESULT_COLUMNS, format_open_ports
from ipmg.utils.helpers import spreadsheet_escape

log = logging.getLogger(__name__)

#: Seconds between snapshots of the formats that cannot be appended to.
DEFAULT_AUTOSAVE_S = 30.0
MIN_AUTOSAVE_S = 1.0
MAX_AUTOSAVE_S = 3600.0

#: Every report format ``--formats`` accepts, in the order they are offered.
REPORT_FORMATS = ("xlsx", "csv", "json", "jsonl", "md")
#: What a scan writes when it is not told which formats to write.
DEFAULT_FORMAT = "xlsx"
#: Formats written one row at a time, and kept valid between rows.
STREAMING_FORMATS = ("csv", "jsonl")
#: Formats that only exist as a whole file, so they are re-snapshotted.
SNAPSHOT_FORMATS = ("xlsx", "json", "md")


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
    ) -> None:
        self.options = options.clamped()
        self._base = base
        self._timestamp = timestamp
        self._batch_timestamp = batch_timestamp
        self._formats = [fmt for fmt in dict.fromkeys(formats)]
        self._results: List[HostResult] = list(previous or ())
        self._rows: List[Dict[str, object]] = [
            result_row(result, batch_timestamp, None) for result in self._results
        ]
        self._handles: Dict[str, IO[str]] = {}
        self._written: Dict[str, None] = {}
        self._started_at = time.monotonic()
        self._last_snapshot = self._started_at
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
