"""Shared conversion from scan results to the canonical report table."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

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
) -> ReportTable:
    """Build the report table, keeping the column set stable when empty."""
    duration = None if duration_s is None else round(duration_s, 3)
    return ReportTable(
        [
            {
                "IP Address": result.ip,
                "Status": result.status,
                "Latency": result.latency,
                "Hostname": result.hostname,
                "Open Ports": format_open_ports(result.open_ports),
                "Batch Timestamp": batch_timestamp,
                "Scan Duration (s)": duration,
            }
            for result in results
        ]
    )
