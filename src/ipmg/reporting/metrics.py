"""Prometheus metrics for the most recent completed scan of each source.

Rendered by hand in the text exposition format (version 0.0.4), so serving
``/metrics`` adds no dependency. Every per-host series is labelled by
``source`` and ``ip`` only; the hostname, which changes, lives on a separate
``ipmg_host_info`` series so a rename does not start a new latency series.

Cardinality is bounded by what is in the history database: one series per
host per metric for the newest completed scan of each of the ``max_sources``
most recently scanned sources, and a scan holds at most 65,536 hosts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from ipmg import __version__
from ipmg.core.portscan import decode_ports
from ipmg.infrastructure.database import Database

CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"

#: Sources exported by default: the most recently scanned ones.
DEFAULT_MAX_SOURCES = 20

Labels = Sequence[Tuple[str, str]]


def _escape(value: str) -> str:
    """Escape a label value as the exposition format requires."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _number(value: float) -> str:
    return repr(float(value)) if not float(value).is_integer() else str(int(value))


class _Exposition:
    """Collects samples per metric, then writes each family under one header."""

    def __init__(self) -> None:
        self._families: Dict[str, Tuple[str, str, List[str]]] = {}

    def declare(self, name: str, kind: str, help_text: str) -> None:
        self._families[name] = (kind, help_text, [])

    def sample(self, name: str, labels: Labels, value: float) -> None:
        rendered = ",".join(f'{key}="{_escape(str(val))}"' for key, val in labels)
        series = f"{name}{{{rendered}}}" if rendered else name
        self._families[name][2].append(f"{series} {_number(value)}")

    def render(self) -> str:
        lines: List[str] = []
        for name, (kind, help_text, samples) in self._families.items():
            lines.append(f"# HELP {name} {help_text}")
            lines.append(f"# TYPE {name} {kind}")
            lines.extend(samples)
        return "\n".join(lines) + "\n"


_FAMILIES = (
    ("ipmg_build_info", "gauge", "IPMG version serving these metrics (always 1)."),
    ("ipmg_host_up", "gauge", "1 if the host answered in its source's latest scan, else 0."),
    (
        "ipmg_host_latency_seconds",
        "gauge",
        "Round-trip time in the latest scan, hosts that answered.",
    ),
    ("ipmg_host_open_ports", "gauge", "Open TCP ports found, for scans that checked ports."),
    ("ipmg_host_info", "gauge", "The host's reverse DNS name in the latest scan (always 1)."),
    ("ipmg_scan_hosts", "gauge", "Hosts in the source's latest scan, by status."),
    ("ipmg_scan_duration_seconds", "gauge", "How long the source's latest scan took."),
    ("ipmg_scan_timestamp_seconds", "gauge", "When the source's latest scan finished (Unix time)."),
    ("ipmg_scans_total", "counter", "Completed scans stored for the source."),
    ("ipmg_metrics_sources_omitted", "gauge", "Sources left out by the --metrics-sources limit."),
)


def _finished_at(scan: Dict) -> Optional[float]:
    try:
        return datetime.fromisoformat(scan["finished_at"]).timestamp()
    except (KeyError, TypeError, ValueError):
        return None


def _host_samples(out: _Exposition, source: str, rows: Iterable[Dict], ports: bool) -> None:
    for row in rows:
        labels = (("source", source), ("ip", row["ip"]))
        out.sample("ipmg_host_up", labels, 1 if row["status"] == "Active" else 0)
        if row["latency"] is not None:
            out.sample("ipmg_host_latency_seconds", labels, row["latency"] / 1000)
        if ports:
            out.sample("ipmg_host_open_ports", labels, len(decode_ports(row["open_ports"])))
        if row["hostname"]:
            out.sample("ipmg_host_info", (*labels, ("hostname", row["hostname"])), 1)


def render_metrics(database: Database, max_sources: int = DEFAULT_MAX_SOURCES) -> str:
    """The metrics page for ``database``, in Prometheus text format."""
    out = _Exposition()
    for name, kind, help_text in _FAMILIES:
        out.declare(name, kind, help_text)
    out.sample("ipmg_build_info", (("version", __version__),), 1)

    scans, source_count = database.latest_completed_scans(max_sources)
    for scan in scans:
        source = scan["source"]
        rows = database.get_results(scan["id"])
        _host_samples(out, source, rows, bool(scan["config"].get("scan_ports")))

        counts: Dict[str, int] = {}
        for row in rows:
            counts[row["status"]] = counts.get(row["status"], 0) + 1
        for status, count in sorted(counts.items()):
            out.sample("ipmg_scan_hosts", (("source", source), ("status", status)), count)

        out.sample("ipmg_scan_duration_seconds", (("source", source),), scan["duration_s"] or 0)
        finished = _finished_at(scan)
        if finished is not None:
            out.sample("ipmg_scan_timestamp_seconds", (("source", source),), finished)
        out.sample("ipmg_scans_total", (("source", source),), scan["completed_count"])

    out.sample("ipmg_metrics_sources_omitted", (), max(source_count - len(scans), 0))
    return out.render()
