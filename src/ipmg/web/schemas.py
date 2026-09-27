"""Request, response, and event models for the IPMG Web API (``/api/v1``).

These models are the API contract: FastAPI validates every response against
them and publishes them in ``/openapi.json``. ``/api/v1`` only changes
additively (new endpoints, new optional fields); anything that would break a
client goes to ``/api/v2``. ``tests/test_api_contract.py`` compares the
generated schema with the committed snapshot so a change is never accidental.
"""

from __future__ import annotations

from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, TypeAdapter


class ApiModel(BaseModel):
    """Base for response models; fields not declared here are never sent."""


# --------------------------------------------------------------------- errors


class ValidationIssue(ApiModel):
    loc: List[Union[str, int]] = Field(description="Where the problem is, e.g. ['body', 'threads']")
    msg: str = Field(description="Human-readable message")
    type: str = Field(description="Machine-readable error type")


class ErrorResponse(ApiModel):
    """The body of every 4xx/5xx response from ``/api/v1``."""

    detail: str = Field(description="Human-readable description of the problem")
    errors: Optional[List[ValidationIssue]] = Field(
        default=None, description="Per-field problems; only present on 422 responses"
    )


# ---------------------------------------------------------------------- scans


class ScanRequest(BaseModel):
    """Start a scan. Provide ``targets`` text or an ``ips`` list."""

    targets: Optional[str] = Field(
        default=None,
        description="Free-form target text: IPs, CIDR ranges, and hostnames, "
        "separated by newlines, commas, or spaces",
    )
    ips: Optional[List[str]] = Field(
        default=None, description="Pre-parsed target list; takes precedence over 'targets'"
    )
    source: str = Field(default="manual", description="Label stored with the scan")
    timeout: int = Field(default=2, description="Seconds to wait per ping (clamped to 1-60)")
    count: int = Field(default=1, description="Pings per host (clamped to 1-10)")
    threads: int = Field(default=50, description="Concurrent workers (clamped to 1-500)")
    resolve: bool = Field(default=False, description="Reverse-resolve hostnames")
    dns_cache_ttl: int = Field(
        default=300, description="Seconds to cache DNS lookups (clamped to 0-86400)"
    )


class ScanCreated(ApiModel):
    id: int = Field(description="ID of the new scan")
    total: int = Field(description="Number of targets queued")


class ScanCancelled(ApiModel):
    id: int
    cancelling: bool = Field(description="Always true; the scan stops shortly after")


class ScanRecord(ApiModel):
    """A stored scan."""

    id: int
    started_at: str = Field(description="Local time, 'YYYY-MM-DD HH:MM:SS'")
    finished_at: Optional[str] = Field(description="Null while the scan is running")
    duration_s: Optional[float] = Field(description="Wall-clock seconds; null until finished")
    source: str = Field(description="Where the targets came from, e.g. 'manual' or a filename")
    total: int = Field(description="Number of targets")
    completed: int = Field(description="Targets checked so far")
    status: str = Field(description="'running', 'complete', 'cancelled', or 'failed'")
    config: Dict[str, Any] = Field(description="Scan settings used (timeout, count, threads, ...)")
    error: Optional[str] = Field(description="Failure reason when status is 'failed'")


class ScanSummary(ScanRecord):
    """A stored scan with aggregate results."""

    status_counts: Dict[str, int] = Field(description="Hosts per result status, e.g. {'Active': 3}")
    avg_latency: Optional[float] = Field(description="Mean latency of active hosts in ms")


class HostResultRow(ApiModel):
    """One host's result as stored for a scan."""

    ip: str
    status: str = Field(description="'Active', 'Inactive', 'Timeout', or 'Error'")
    latency: Optional[float] = Field(description="Round-trip time in ms; null if no reply")
    hostname: str = Field(description="Resolved hostname; empty when not resolved")
    open_ports: str = Field(description="Comma-separated open TCP ports; empty when none")
    checked_at: str = Field(description="Local time the result was stored")


# ------------------------------------------------------------------- overview


class TrendPoint(ApiModel):
    id: int = Field(description="Scan ID")
    started_at: str
    total: int
    active: int = Field(description="Hosts that replied")
    avg_latency: Optional[float] = Field(description="Mean latency of active hosts in ms")


class Stats(ApiModel):
    scan_count: int
    host_count: int = Field(description="Distinct IPs ever scanned")
    latest_scan: Optional[ScanSummary] = Field(description="Newest scan that is not running")
    running_scans: List[ScanRecord]
    trend: List[TrendPoint] = Field(description="Up to 15 most recent complete scans, oldest first")


class Asset(ApiModel):
    """A host aggregated across every scan that saw it."""

    ip: str
    hostname: Optional[str] = Field(description="Most recent non-empty hostname")
    status: str = Field(description="Status in the most recent scan")
    avg_latency: Optional[float] = Field(description="Mean latency when active, in ms")
    last_seen: Optional[str] = Field(description="Last time the host was active")
    last_checked: str
    last_scan_id: int
    scan_count: int


class UploadResult(ApiModel):
    filename: Optional[str]
    count: int = Field(description="Number of targets parsed")
    targets: List[str]


# ----------------------------------------------------------------------- diff


class ScanRefModel(ApiModel):
    id: Optional[int]
    label: str
    started_at: str
    source: str


class DiffOptionsModel(ApiModel):
    latency_abs_ms: float
    latency_pct: float
    include_unresolved_hostnames: bool


class DiffSummary(ApiModel):
    baseline_hosts: int
    current_hosts: int
    compared_hosts: int
    changed_hosts: int
    unchanged_hosts: int
    total_changes: int
    counts: Dict[str, int] = Field(description="Changes per change type")
    severity_counts: Dict[str, int] = Field(description="Changes per severity")


class HostChangeModel(ApiModel):
    type: str = Field(
        description="new_host, host_removed, host_offline, host_online, ip_changed, "
        "hostname_changed, latency_changed, or service_changed"
    )
    label: str
    severity: str = Field(description="'critical', 'warning', or 'info'")
    ip: str
    hostname: str
    previous: Optional[str]
    current: Optional[str]
    delta: Optional[float] = Field(description="Latency change in ms, for latency_changed")
    description: str


class ScanDiffModel(ApiModel):
    baseline: ScanRefModel
    current: ScanRefModel
    options: DiffOptionsModel
    summary: DiffSummary
    changes: List[HostChangeModel]


# ------------------------------------------------------------ WebSocket events


class HostResultModel(ApiModel):
    ip: str
    status: str = Field(description="'Active', 'Inactive', 'Timeout', or 'Error'")
    latency: Optional[float] = Field(description="Round-trip time in ms; null if no reply")
    hostname: str
    open_ports: List[int] = Field(description="Open TCP ports, when port scanning was on")


class ScanStartedEvent(ApiModel):
    type: Literal["scan_started"] = "scan_started"
    scan_id: int
    total: int


class ResultEvent(ApiModel):
    type: Literal["result"] = "result"
    scan_id: int
    completed: int
    total: int
    result: HostResultModel


class ScanFinishedEvent(ApiModel):
    type: Literal["scan_finished"] = "scan_finished"
    scan_id: int
    status: str = Field(description="'complete', 'cancelled', or 'failed'")
    duration_s: float


WebSocketEvent = Annotated[
    Union[ScanStartedEvent, ResultEvent, ScanFinishedEvent],
    Field(discriminator="type"),
]

WEBSOCKET_EVENT_MODELS = (ScanStartedEvent, ResultEvent, ScanFinishedEvent)


def websocket_event_schemas(ref_template: str) -> Dict[str, Any]:
    """JSON schemas for the WebSocket events, keyed by name, for ``/openapi.json``."""
    schema = TypeAdapter(WebSocketEvent).json_schema(ref_template=ref_template)
    definitions = schema.pop("$defs", {})
    definitions["WebSocketEvent"] = schema
    return definitions
