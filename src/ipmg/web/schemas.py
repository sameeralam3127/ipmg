"""Request, response, and event models for the IPMG Web API (``/api/v1``).

These models are the API contract: FastAPI validates every response against
them and publishes them in ``/openapi.json``. ``/api/v1`` only changes
additively (new endpoints, new optional fields); anything that would break a
client goes to ``/api/v2``. ``tests/test_api_contract.py`` compares the
generated schema with the committed snapshot so a change is never accidental.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter


class ApiModel(BaseModel):
    """Base for response models; fields not declared here are never sent."""


# --------------------------------------------------------------------- errors


class ValidationIssue(ApiModel):
    loc: list[str | int] = Field(description="Where the problem is, e.g. ['body', 'threads']")
    msg: str = Field(description="Human-readable message")
    type: str = Field(description="Machine-readable error type")


class ErrorResponse(ApiModel):
    """The body of every 4xx/5xx response from ``/api/v1``."""

    detail: str = Field(description="Human-readable description of the problem")
    errors: list[ValidationIssue] | None = Field(
        default=None, description="Per-field problems; only present on 422 responses"
    )


# ---------------------------------------------------------------------- scans


class ScanSettings(BaseModel):
    """How to scan: the settings a scan and a schedule share."""

    timeout: int = Field(default=2, description="Seconds to wait per ping (clamped to 1-60)")
    count: int = Field(default=1, description="Pings per host (clamped to 1-10)")
    threads: int = Field(default=50, description="Concurrent workers (clamped to 1-500)")
    resolve: bool = Field(default=False, description="Reverse-resolve hostnames")
    dns_cache_ttl: int = Field(
        default=300, description="Seconds to cache DNS lookups (clamped to 0-86400)"
    )
    dns_timeout: float = Field(
        default=2.0,
        description="Seconds a reverse DNS lookup may take before the host is recorded "
        "as Unresolvable (clamped to 0.1-60)",
    )
    resolve_active_only: bool = Field(
        default=False, description="Only reverse-resolve hosts that answered"
    )
    mac_lookup: bool = Field(
        default=False,
        description="Add each responding host's MAC address and vendor, from the server's "
        "ARP/neighbour table (hosts on its local network only)",
    )
    probe: Literal["icmp", "tcp", "icmp,tcp"] = Field(
        default="icmp",
        description="How to tell a host is up: ping, a TCP connection to a common port, "
        "or TCP only for hosts that did not answer the ping",
    )

    def scan_settings(self) -> dict[str, Any]:
        """These settings alone, as a ScanConfig takes them."""
        return {name: getattr(self, name) for name in ScanSettings.model_fields}


class ScanRequest(ScanSettings):
    """Start a scan. Provide ``targets`` text or an ``ips`` list."""

    targets: str | None = Field(
        default=None,
        description="Free-form target text: IPs, CIDR ranges, and hostnames, "
        "separated by newlines, commas, or spaces",
    )
    ips: list[str] | None = Field(
        default=None, description="Pre-parsed target list; takes precedence over 'targets'"
    )
    source: str = Field(default="manual", description="Label stored with the scan")


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
    finished_at: str | None = Field(description="Null while the scan is running")
    duration_s: float | None = Field(description="Wall-clock seconds; null until finished")
    source: str = Field(description="Where the targets came from, e.g. 'manual' or a filename")
    total: int = Field(description="Number of targets")
    completed: int = Field(description="Targets checked so far")
    status: str = Field(
        description="'running', 'complete', 'cancelled', 'failed', or 'interrupted' "
        "(IPMG Web stopped before the scan finished)"
    )
    config: dict[str, Any] = Field(description="Scan settings used (timeout, count, threads, ...)")
    error: str | None = Field(description="Failure reason when status is 'failed' or 'interrupted'")


class ScanSummary(ScanRecord):
    """A stored scan with aggregate results."""

    status_counts: dict[str, int] = Field(description="Hosts per result status, e.g. {'Active': 3}")
    avg_latency: float | None = Field(description="Mean latency of active hosts in ms")


class HostResultRow(ApiModel):
    """One host's result as stored for a scan."""

    ip: str
    status: str = Field(description="'Active', 'Inactive', 'Timeout', or 'Error'")
    latency: float | None = Field(description="Round-trip time in ms; null if no reply")
    hostname: str = Field(description="Resolved hostname; empty when not resolved")
    open_ports: str = Field(description="Comma-separated open TCP ports; empty when none")
    checked_at: str = Field(description="Local time the result was stored")
    method: str = Field(
        default="",
        description="Which probe found the host, 'icmp' or 'tcp', when the scan used TCP "
        "probing; empty otherwise",
    )
    mac: str = Field(default="", description="MAC address, with mac_lookup; empty if unknown")
    vendor: str = Field(default="", description="Vendor of the MAC address's prefix")


class HttpCheckRow(ApiModel):
    """One ``--http-check`` URL as a scan checked it."""

    url: str
    ok: bool = Field(description="Whether the status was one the check expected")
    status_code: int | None = Field(description="Final HTTP status; null if none came back")
    response_ms: float | None = Field(description="Time to the final response, in ms")
    final_url: str = Field(description="Where redirects ended; the URL itself without any")
    failure: str = Field(
        description="Why it failed: dns, connect, tls, timeout, status, protocol, redirects, "
        "or invalid; empty when it passed"
    )
    error: str = Field(description="Human-readable failure reason")
    cert_expires: str = Field(description="Certificate expiry date (UTC) for verified HTTPS")
    checked_at: str


class SnmpInterfaceRow(ApiModel):
    """One interface of a device, from ifTable and ifXTable."""

    if_index: int = Field(description="ifIndex")
    name: str = Field(description="ifName, else ifDescr")
    description: str = Field(description="ifDescr")
    alias: str = Field(description="ifAlias, the description an operator gave the interface")
    admin_status: str = Field(description="up, down, or testing; empty if unknown")
    oper_status: str = Field(
        description="up, down, testing, unknown, dormant, notPresent, or lowerLayerDown"
    )
    speed_mbps: int | None = Field(description="Speed in Mbit/s")
    in_octets: int | None = Field(description="Octets received (64-bit counter where available)")
    out_octets: int | None = Field(description="Octets sent (64-bit counter where available)")


class SnmpDeviceRow(ApiModel):
    """One device as a scan polled it with ``ipmg --snmp``."""

    ip: str
    ok: bool = Field(description="Whether the agent answered")
    version: str = Field(description="SNMP version used: 2c or 3")
    sys_name: str = Field(description="sysName")
    sys_descr: str = Field(description="sysDescr")
    sys_object_id: str = Field(description="sysObjectID, the vendor's identifier for the model")
    sys_location: str = Field(description="sysLocation")
    uptime_s: float | None = Field(description="Seconds since the agent started, from sysUpTime")
    response_ms: float | None = Field(description="Time to the system group's answer, in ms")
    failure: str = Field(
        description="Why it failed: timeout, refused, auth, error, protocol, unsupported, or "
        "network; empty when it answered"
    )
    error: str = Field(description="Human-readable failure reason, or a note on a partial answer")
    polled_at: str
    interfaces: list[SnmpInterfaceRow]


# ------------------------------------------------------------------- overview


class TrendPoint(ApiModel):
    id: int = Field(description="Scan ID")
    started_at: str
    total: int
    active: int = Field(description="Hosts that replied")
    avg_latency: float | None = Field(description="Mean latency of active hosts in ms")


class Stats(ApiModel):
    scan_count: int
    host_count: int = Field(description="Distinct IPs ever scanned")
    latest_scan: ScanSummary | None = Field(description="Newest scan that is not running")
    running_scans: list[ScanRecord]
    trend: list[TrendPoint] = Field(description="Up to 15 most recent complete scans, oldest first")


class Asset(ApiModel):
    """A host aggregated across every scan that saw it."""

    ip: str
    hostname: str | None = Field(description="Most recent non-empty hostname")
    status: str = Field(description="Status in the most recent scan")
    mac: str | None = Field(default=None, description="Most recent MAC address seen")
    vendor: str | None = Field(default=None, description="Vendor of that MAC address")
    snmp_name: str | None = Field(default=None, description="Most recent SNMP sysName")
    snmp_descr: str | None = Field(default=None, description="Most recent SNMP sysDescr")
    avg_latency: float | None = Field(description="Mean latency when active, in ms")
    last_seen: str | None = Field(description="Last time the host was active")
    last_checked: str
    last_scan_id: int
    scan_count: int


# ------------------------------------------------------------------ schedules


class ScheduleRequest(ScanSettings):
    """Create a schedule: scan ``targets`` every ``interval_minutes``, or on ``cron``."""

    name: str = Field(
        min_length=1,
        max_length=100,
        description="Unique name; the scans are stored under the source 'schedule:<name>'",
    )
    targets: str = Field(description="Target text, as for a scan; parsed again for every run")
    interval_minutes: int | None = Field(
        default=None, ge=1, le=10080, description="Run every N minutes (1 minute to 1 week)"
    )
    cron: str | None = Field(
        default=None,
        description="Or a five-field cron expression in the server's local time, "
        "such as '*/15 * * * *' or '@daily'",
    )
    paused: bool = Field(default=False, description="Create it paused")


class SchedulePatch(BaseModel):
    paused: bool | None = Field(default=None, description="Pause or resume the schedule")


class Schedule(ApiModel):
    """A stored schedule and how its runs have gone."""

    id: int
    name: str
    source: str = Field(description="History source of its scans: 'schedule:<name>'")
    targets: str
    interval_minutes: int | None
    cron: str | None
    paused: bool
    config: dict[str, Any] = Field(description="Scan settings each run uses")
    created_at: str
    next_run_at: str | None = Field(description="Local time of the next run; null if paused")
    last_run_at: str | None
    last_scan_id: int | None
    last_status: str | None = Field(description="Status of the last scan it started")
    last_skipped_at: str | None = Field(description="When a run was last skipped")
    last_skip_reason: str | None = Field(
        description="Why: the previous run was still going, --max-scans was reached, ..."
    )


class WakeRequest(BaseModel):
    """Send a Wake-on-LAN magic packet."""

    mac: str = Field(description="MAC address: AA:BB:CC:DD:EE:FF, AA-BB-..., or AABBCCDDEEFF")
    broadcast: str = Field(
        default="255.255.255.255",
        description="IPv4 broadcast address; a directed one such as 192.168.1.255 "
        "reaches another subnet",
    )
    port: int = Field(default=9, description="UDP port (1-65535)")


class WakeSent(ApiModel):
    mac: str = Field(description="The MAC address the packet was built for")
    broadcast: str
    port: int


class UploadResult(ApiModel):
    filename: str | None
    count: int = Field(description="Number of targets parsed")
    targets: list[str]


# ----------------------------------------------------------------------- diff


class ScanRefModel(ApiModel):
    id: int | None
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
    counts: dict[str, int] = Field(description="Changes per change type")
    severity_counts: dict[str, int] = Field(description="Changes per severity")


class HostChangeModel(ApiModel):
    type: str = Field(
        description="new_host, host_removed, host_offline, host_online, ip_changed, "
        "hostname_changed, latency_changed, service_changed, mac_changed, http_failing, "
        "http_recovered, or http_status_changed"
    )
    label: str
    severity: str = Field(description="'critical', 'warning', or 'info'")
    ip: str = Field(description="The host's IP; for http_* changes, the checked URL")
    hostname: str
    previous: str | None
    current: str | None
    delta: float | None = Field(description="Latency change in ms, for latency_changed")
    description: str


class ScanDiffModel(ApiModel):
    baseline: ScanRefModel
    current: ScanRefModel
    options: DiffOptionsModel
    summary: DiffSummary
    changes: list[HostChangeModel]


# ------------------------------------------------------------ WebSocket events


class HostResultModel(ApiModel):
    ip: str
    status: str = Field(description="'Active', 'Inactive', 'Timeout', or 'Error'")
    latency: float | None = Field(description="Round-trip time in ms; null if no reply")
    hostname: str
    open_ports: list[int] = Field(description="Open TCP ports, when port scanning was on")
    method: str = Field(default="", description="Which probe found the host, as in results")
    mac: str = Field(default="", description="MAC address, with mac_lookup")
    vendor: str = Field(default="", description="Vendor of the MAC address's prefix")


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
    ScanStartedEvent | ResultEvent | ScanFinishedEvent,
    Field(discriminator="type"),
]

WEBSOCKET_EVENT_MODELS = (ScanStartedEvent, ResultEvent, ScanFinishedEvent)


def websocket_event_schemas(ref_template: str) -> dict[str, Any]:
    """JSON schemas for the WebSocket events, keyed by name, for ``/openapi.json``."""
    schema = TypeAdapter(WebSocketEvent).json_schema(ref_template=ref_template)
    definitions = schema.pop("$defs", {})
    definitions["WebSocketEvent"] = schema
    return definitions
