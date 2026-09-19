"""Shared scan engine used by both the CLI and the web dashboard."""

from __future__ import annotations

import concurrent.futures
from dataclasses import dataclass, field
from typing import Callable, Iterable, List, Optional, Tuple

from ipmg.core.ping import ping_ip
from ipmg.core.portscan import DEFAULT_PORTS, scan_ports
from ipmg.exceptions import PingError
from ipmg.utils.helpers import HostnameCache, clamp_int

#: Upper bound on TCP connect probes in flight across a whole scan. Every host
#: worker shares this one pool, so --scan-ports cannot create
#: threads x ports probe threads.
MAX_PORT_PROBE_WORKERS = 128


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
        )


@dataclass(frozen=True)
class HostResult:
    ip: str
    status: str
    latency: Optional[float]
    hostname: str = ""
    open_ports: Tuple[int, ...] = field(default_factory=tuple)


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
    cache = HostnameCache(config.dns_cache_ttl) if config.resolve else None
    results: List[HostResult] = []

    port_executor: Optional[concurrent.futures.ThreadPoolExecutor] = None
    if config.scan_ports and config.ports:
        port_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=min(MAX_PORT_PROBE_WORKERS, config.threads * len(config.ports)),
            thread_name_prefix="ipmg-port",
        )

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=config.threads)
    try:
        futures = [executor.submit(_probe_host, ip, config, cache, port_executor) for ip in ips]

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
        executor.shutdown(wait=True)
        if port_executor is not None:
            port_executor.shutdown(wait=True)

    return results


def _probe_host(
    ip: str,
    config: ScanConfig,
    cache: Optional[HostnameCache],
    port_executor: Optional[concurrent.futures.Executor],
) -> HostResult:
    """Ping one host, then resolve its name and probe its ports.

    Runs on a pool worker, so reverse DNS is spread across ``config.threads``
    workers instead of running one host at a time on the thread that collects
    results. Port probes go to the scan's shared, bounded ``port_executor``.
    """
    try:
        status, latency = ping_ip(ip, config.timeout, config.count)
    except PingError:
        raise
    except Exception:
        status, latency = "Error", None

    hostname = cache.resolve(ip) if cache else ""
    open_ports: Tuple[int, ...] = ()
    if config.scan_ports and status == "Active":
        open_ports = tuple(
            scan_ports(ip, config.ports, config.port_timeout, executor=port_executor)
        )

    return HostResult(
        ip=ip, status=status, latency=latency, hostname=hostname, open_ports=open_ports
    )
