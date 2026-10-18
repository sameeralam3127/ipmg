"""Shared conversion from scan results to the canonical report table."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from ipmg.core.engine import HostResult

RESULT_COLUMNS: List[str] = [
    "IP Address",
    "Status",
    "Latency",
    "Hostname",
    "Open Ports",
    "Batch Timestamp",
    "Scan Duration (s)",
]

#: Which probe found the host, with ``--probe tcp`` or ``--probe icmp,tcp``.
PROBE_COLUMN = "Probe"
#: With ``--mac``: the host's MAC address and the vendor its prefix belongs to.
MAC_COLUMN = "MAC Address"
VENDOR_COLUMN = "Vendor"


def report_columns(config: Any = None) -> Tuple[str, ...]:
    """The columns a scan's report has.

    The default set, plus each optional column for something the scan was
    asked to find, placed after "Open Ports". A scan that asks for nothing
    extra writes exactly the report it always did. ``config`` is a
    :class:`~ipmg.core.engine.ScanConfig` or the dict stored with a scan.
    """

    def setting(name: str, default: Any) -> Any:
        if isinstance(config, Mapping):
            return config.get(name, default)
        return getattr(config, name, default)

    extra: List[str] = []
    if setting("probe", "icmp") not in ("icmp", "", None):
        extra.append(PROBE_COLUMN)
    if setting("mac_lookup", False):
        extra.extend([MAC_COLUMN, VENDOR_COLUMN])
    at = RESULT_COLUMNS.index("Open Ports") + 1
    return tuple(RESULT_COLUMNS[:at] + extra + RESULT_COLUMNS[at:])


def result_values(result: HostResult) -> Dict[str, Any]:
    """Every per-host column a report can carry, before choosing the ones it has."""
    return {
        "IP Address": result.ip,
        "Status": result.status,
        "Latency": result.latency,
        "Hostname": result.hostname,
        "Open Ports": format_open_ports(result.open_ports),
        PROBE_COLUMN: result.method,
        MAC_COLUMN: result.mac,
        VENDOR_COLUMN: result.vendor,
    }


Row = Dict[str, Any]


@dataclass(frozen=True)
class ReportTable:
    """A report's rows as plain dicts, every one carrying the same columns.

    What pandas used to hold for IPMG, minus pandas: a scan report is a few
    thousand rows at most, and every writer walks it row by row anyway.
    """

    rows: List[Row] = field(default_factory=list)
    columns: Sequence[str] = tuple(RESULT_COLUMNS)

    @classmethod
    def from_rows(cls, rows: Iterable[Row]) -> "ReportTable":
        """A table over ``rows``, its columns being every key they use, in order."""
        rows = [dict(row) for row in rows]
        return cls(rows, columns=tuple(dict.fromkeys(key for row in rows for key in row)))

    def __len__(self) -> int:
        return len(self.rows)

    def __iter__(self):
        return iter(self.rows)

    def column(self, name: str) -> List[Any]:
        return [row.get(name) for row in self.rows]


def format_open_ports(ports: Iterable[int]) -> str:
    return ", ".join(str(port) for port in ports)


def results_table(
    results: Iterable[HostResult],
    batch_timestamp: Any,
    duration_s: Optional[float],
    columns: Sequence[str] = tuple(RESULT_COLUMNS),
) -> ReportTable:
    """Build the report table, keeping the column set stable when empty."""
    duration = None if duration_s is None else round(duration_s, 3)
    rows = []
    for result in results:
        values = result_values(result)
        values["Batch Timestamp"] = batch_timestamp
        values["Scan Duration (s)"] = duration
        rows.append({column: values.get(column) for column in columns})
    return ReportTable(rows, columns=tuple(columns))
