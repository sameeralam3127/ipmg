"""Shared conversion from scan results to the canonical report DataFrame."""

from __future__ import annotations

from typing import Any, Iterable, List, Optional

import pandas as pd

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


def format_open_ports(ports: Iterable[int]) -> str:
    return ", ".join(str(port) for port in ports)


def results_dataframe(
    results: Iterable[HostResult],
    batch_timestamp: Any,
    duration_s: Optional[float],
) -> pd.DataFrame:
    """Build the report DataFrame, keeping the column set stable when empty."""
    duration = None if duration_s is None else round(duration_s, 3)
    rows = [
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
    return pd.DataFrame(rows, columns=RESULT_COLUMNS)
