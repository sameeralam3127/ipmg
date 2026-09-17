"""Pick a scan back up from the report an interrupted run left behind.

Incremental writing means an interrupted scan leaves a real report on disk
(see :mod:`ipmg.infrastructure.incremental`). ``--resume`` reads that file
back, skips the hosts it already covers, and keeps writing to it — so a sweep
that died at host 40,000 costs the remaining hosts, not another full pass.

Only the row-oriented formats can be resumed: ``csv`` and ``jsonl`` are the
ones guaranteed to be readable after an abrupt exit. A truncated final line is
expected and skipped rather than treated as corruption.
"""

from __future__ import annotations

import csv
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

from ipmg.core.engine import HostResult
from ipmg.core.ping import validate_ip
from ipmg.exceptions import FileIOError
from ipmg.reporting.frames import RESULT_COLUMNS
from ipmg.utils.helpers import FORMULA_PREFIXES, timestamp_str

log = logging.getLogger(__name__)

#: Report formats a scan can be resumed from.
RESUMABLE_SUFFIXES = {".csv", ".jsonl"}

#: Every status a scan can record. A row carrying anything else was written
#: by something other than a finished probe — most likely a line cut in half.
KNOWN_STATUSES = {"Active", "Inactive", "Timeout", "Unreachable", "Invalid IP", "Error"}

#: The ``<base>_<YYYYMMDD>_<HHMMSS>`` tail every report file name carries.
_STAMP = re.compile(r"^(?P<base>.*)_(?P<stamp>\d{8}_\d{6})$")


@dataclass(frozen=True)
class PartialReport:
    """An interrupted scan's report, and where the resumed one should write."""

    path: str
    fmt: str
    base: str
    timestamp: str
    results: List[HostResult]

    @property
    def scanned_ips(self) -> Dict[str, None]:
        """The hosts already in the report, in the order they were scanned."""
        return {result.ip: None for result in self.results}

    def remaining(self, ip_list: List[str]) -> List[str]:
        """``ip_list`` without the hosts this report already covers."""
        done = self.scanned_ips
        return [ip for ip in ip_list if ip not in done]


def _unescape(value: str) -> str:
    """Undo :func:`spreadsheet_escape` so a resumed row is not escaped twice."""
    if value.startswith("'") and value[1:].startswith(FORMULA_PREFIXES):
        return value[1:]
    return value


def _latency(value: object) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _ports(value: object) -> Tuple[int, ...]:
    if not value:
        return ()
    ports: List[int] = []
    for token in str(value).replace(";", ",").split(","):
        token = token.strip()
        if token.isdigit():
            ports.append(int(token))
    return tuple(ports)


def _host_result(row: Dict[str, object]) -> Optional[HostResult]:
    """Rebuild one result, or ``None`` when the row cannot be trusted.

    A scan killed mid-write leaves a final line that stops in the middle of a
    field, which reads back as a short row — so a row is only accepted when
    every column is present and both the address and the status are ones a
    probe could actually have produced.
    """
    if any(row.get(column) is None for column in RESULT_COLUMNS):
        return None

    ip = str(row.get("IP Address") or "").strip()
    status = str(row.get("Status") or "").strip()
    if not validate_ip(ip) or status not in KNOWN_STATUSES:
        return None

    return HostResult(
        ip=ip,
        status=status,
        latency=_latency(row.get("Latency")),
        hostname=_unescape(str(row.get("Hostname") or "")),
        open_ports=_ports(row.get("Open Ports")),
    )


def _csv_rows(path: Path) -> Iterator[Dict[str, object]]:
    with open(path, encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or "IP Address" not in reader.fieldnames:
            raise FileIOError(
                f"'{path}' does not look like an IPMG report: no 'IP Address' column."
            )
        for row in reader:
            # A row cut off mid-write has missing keys; _host_result drops it.
            yield {key: value for key, value in row.items() if key is not None}


def _jsonl_rows(path: Path) -> Iterator[Dict[str, object]]:
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                # Only the final line of an abruptly killed scan can be
                # truncated, and the scan is about to rewrite it anyway.
                log.debug("skipping unreadable line in %s", path)
                continue
            if isinstance(record, dict):
                yield record


def _destination(path: Path) -> Tuple[str, str]:
    """Where a resumed scan should write: the report's own base and stamp.

    Reports are named ``<base>_<YYYYMMDD>_<HHMMSS>.<format>``. Keeping both
    parts means the resumed scan finishes the file it was handed instead of
    leaving a half-scanned report next to a complete one. A file that was
    renamed out of that shape keeps its name and gets a fresh stamp.
    """
    match = _STAMP.match(path.stem)
    if match is None:
        return str(path.with_name(path.stem)), timestamp_str()
    return str(path.with_name(match.group("base"))), match.group("stamp")


def load_partial_report(source: str) -> PartialReport:
    """Read an interrupted scan's report so the scan can be continued."""
    path = Path(source)
    suffix = path.suffix.lower()

    if suffix not in RESUMABLE_SUFFIXES:
        raise FileIOError(
            f"Cannot resume from '{suffix or '<none>'}' reports. "
            f"Supported: {', '.join(sorted(RESUMABLE_SUFFIXES))}."
        )
    if not path.is_file():
        raise FileIOError(f"Report to resume '{source}' was not found.")

    rows = _csv_rows(path) if suffix == ".csv" else _jsonl_rows(path)
    results: List[HostResult] = []
    seen: set = set()
    for row in rows:
        result = _host_result(row)
        # A host can appear twice if an earlier resume overlapped; the first
        # result is the one the report already told the operator about.
        if result is not None and result.ip not in seen:
            seen.add(result.ip)
            results.append(result)

    base, timestamp = _destination(path)
    return PartialReport(
        path=source,
        fmt=suffix.lstrip("."),
        base=base,
        timestamp=timestamp,
        results=results,
    )
