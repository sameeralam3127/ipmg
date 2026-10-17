"""Shared scan engine used by both the CLI and the web dashboard."""

from __future__ import annotations

import concurrent.futures
import time
from dataclasses import dataclass, field
from typing import Callable, Iterable, List, Optional, Tuple

from ipmg.core.neighbours import NeighbourCache, mac_and_vendor
from ipmg.core.ping import ping_ip, validate_ip
from ipmg.core.portscan import DEFAULT_PORTS, scan_ports, tcp_probe
from ipmg.exceptions import PingError
from ipmg.utils.helpers import HostnameCache, clamp_int

#: Upper bound on TCP connect probes in flight across a whole scan. Every host
#: worker shares this one pool, so --scan-ports cannot create
#: threads x ports probe threads.
MAX_PORT_PROBE_WORKERS = 128

#: Seconds a reverse DNS lookup may take before the host is recorded as
#: Unresolvable. The system resolver's own retries can take 30 s.
DEFAULT_DNS_TIMEOUT_S = 2.0

#: How a scan decides a host is up. ``icmp,tcp`` tries TCP only for hosts
#: that did not answer the ping, so hosts that block ICMP are not missed.
PROBE_METHODS = ("icmp", "tcp", "icmp,tcp")


@dataclass(frozen=True)
class ScanConfig:
    timeout: int = 2
    count: int = 1
    threads: int = 50
    resolve: bool = False
    dns_cache_ttl: int = 300
    scan_ports: bool = False
    ports: Tuple[int, ...] = DEFAULT_PORTS
    port_timeout: float = 1.0
    dns_timeout: float = DEFAULT_DNS_TIMEOUT_S
    #: Skip the PTR lookup for hosts that did not answer.
    resolve_active_only: bool = False
    #: One of :data:`PROBE_METHODS`; TCP probes connect to ``ports``.
    probe: str = "icmp"
    #: Read each responding host's MAC from the OS neighbour table.
    mac_lookup: bool = False

    @property
    def uses_tcp_probe(self) -> bool:
        return "tcp" in self.probe.split(",")

    def clamped(self) -> "ScanConfig":
        return ScanConfig(
            timeout=clamp_int(self.timeout, 1, 60),
            count=clamp_int(self.count, 1, 10),
            threads=clamp_int(self.threads, 1, 500),
            resolve=self.resolve,
            dns_cache_ttl=clamp_int(self.dns_cache_ttl, 0, 86400),
            scan_ports=self.scan_ports,
            ports=tuple(self.ports),
            port_timeout=max(min(self.port_timeout, 30.0), 0.1),
            dns_timeout=max(min(float(self.dns_timeout), 60.0), 0.1),
            resolve_active_only=self.resolve_active_only,
            probe=self.probe if self.probe in PROBE_METHODS else "icmp",
            mac_lookup=self.mac_lookup,
        )


@dataclass(frozen=True)
class HostResult:
    ip: str
    status: str
    latency: Optional[float]
    hostname: str = ""
    open_ports: Tuple[int, ...] = field(default_factory=tuple)
    #: Which probe found the host ("icmp" or "tcp"); set only when a scan
    #: uses TCP probing, and only for hosts that answered.
    method: str = ""
    #: ``AA:BB:CC:DD:EE:FF`` with ``--mac``, for responding hosts on a local link.
    mac: str = ""
    vendor: str = ""


ResultCallback = Callable[[HostResult, int, int], None]


def execute_scan(
    ip_list: Iterable[str],
    config: ScanConfig,
    on_result: Optional[ResultCallback] = None,
    should_stop: Optional[Callable[[], bool]] = None,
) -> List[HostResult]:
    """Ping every target concurrently and return one result per host.

    ``on_result`` is invoked from the calling thread as each host finishes,
    with the result plus completed/total counters. ``should_stop`` is polled
    between results; returning True cancels the remaining hosts.
    """
    config = config.clamped()
    ips = list(ip_list)
    cache = (
        HostnameCache(
            config.dns_cache_ttl, timeout_s=config.dns_timeout, max_workers=config.threads
        )
        if config.resolve
        else None
    )
    neighbours = NeighbourCache() if config.mac_lookup else None
    results: List[HostResult] = []

    port_executor: Optional[concurrent.futures.ThreadPoolExecutor] = None
    if (config.scan_ports or config.uses_tcp_probe) and config.ports:
        port_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=min(MAX_PORT_PROBE_WORKERS, config.threads * len(config.ports)),
            thread_name_prefix="ipmg-port",
        )

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=config.threads)
    try:
        futures = [
            executor.submit(_probe_host, ip, config, cache, port_executor, neighbours) for ip in ips
        ]

        for future in concurrent.futures.as_completed(futures):
            if should_stop is not None and should_stop():
                executor.shutdown(wait=False, cancel_futures=True)
                break

            try:
                result = future.result()
            except PingError:
                executor.shutdown(wait=False, cancel_futures=True)
                raise
            results.append(result)

            if on_result is not None:
                on_result(result, len(results), len(ips))
    except BaseException:
        # Ctrl+C must not be followed by minutes of queued pings: drop the
        # hosts that have not started, and let the finally below wait only
        # for the handful already in flight.
        executor.shutdown(wait=False, cancel_futures=True)
        raise
    finally:
        # Each in-flight probe waits at most dns_timeout for its name, so
        # this returns promptly even when the resolver has stopped answering.
        executor.shutdown(wait=True)
        if port_executor is not None:
            port_executor.shutdown(wait=True)
        if cache is not None:
            cache.close()

    return results


def _probe_host(
    ip: str,
    config: ScanConfig,
    cache: Optional[HostnameCache],
    port_executor: Optional[concurrent.futures.Executor],
    neighbours: Optional[NeighbourCache] = None,
) -> HostResult:
    """Probe one host, then resolve its name and MAC, and probe its ports.

    Runs on a pool worker, so reverse DNS is spread across ``config.threads``
    workers instead of running one host at a time on the thread that collects
    results. Port probes go to the scan's shared, bounded ``port_executor``.
    """
    status, latency, method = _reachability(ip, config, port_executor)
    mac = vendor = ""
    if neighbours is not None and status == "Active":
        # The probe just made the OS resolve the host's MAC, if it is on a local link.
        mac, vendor = mac_and_vendor(neighbours, ip, time.monotonic())

    resolve = cache is not None and (status == "Active" or not config.resolve_active_only)
    hostname = cache.resolve(ip) if resolve else ""
    open_ports: Tuple[int, ...] = ()
    if config.scan_ports and status == "Active":
        open_ports = tuple(
            scan_ports(ip, config.ports, config.port_timeout, executor=port_executor)
        )

    return HostResult(
        ip=ip,
        status=status,
        latency=latency,
        hostname=hostname,
        open_ports=open_ports,
        method=method,
        mac=mac,
        vendor=vendor,
    )


def _reachability(
    ip: str,
    config: ScanConfig,
    port_executor: Optional[concurrent.futures.Executor],
) -> Tuple[str, Optional[float], str]:
    """Status, latency, and the method that found the host, per ``config.probe``."""
    methods = config.probe.split(",")
    # Only a scan that can use more than one method says which one answered.
    tagged = "tcp" in methods
    status, latency = "Timeout", None
    if "icmp" in methods:
        try:
            status, latency = ping_ip(ip, config.timeout, config.count)
        except PingError:
            raise
        except Exception:
            status, latency = "Error", None
        if status == "Active":
            return status, latency, "icmp" if tagged else ""
        if status == "Invalid IP" or not tagged:
            return status, latency, ""
    elif not validate_ip(ip):
        return "Invalid IP", None, ""

    tcp_status, tcp_latency = tcp_probe(ip, config.ports, config.port_timeout, port_executor)
    if tcp_status == "Active":
        return "Active", tcp_latency, "tcp"
    # Both missed: ping's verdict (it says more) stands, else TCP's.
    return (status, latency, "") if "icmp" in methods else (tcp_status, None, "")
