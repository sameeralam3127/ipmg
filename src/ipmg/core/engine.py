"""Shared scan engine used by both the CLI and the web dashboard."""

from __future__ import annotations

import concurrent.futures
from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional

from ipmg.core.ping import ping_ip
from ipmg.exceptions import PingError
from ipmg.utils.helpers import HostnameCache, clamp_int


@dataclass(frozen=True)
class ScanConfig:
    timeout: int = 2
    count: int = 1
    threads: int = 50
    resolve: bool = False
    dns_cache_ttl: int = 300

    def clamped(self) -> "ScanConfig":
        return ScanConfig(
            timeout=clamp_int(self.timeout, 1, 60),
            count=clamp_int(self.count, 1, 10),
            threads=clamp_int(self.threads, 1, 500),
            resolve=self.resolve,
            dns_cache_ttl=clamp_int(self.dns_cache_ttl, 0, 86400),
        )


@dataclass(frozen=True)
class HostResult:
    ip: str
    status: str
    latency: Optional[float]
    hostname: str = ""


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

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=config.threads)
    try:
        futures = {executor.submit(ping_ip, ip, config.timeout, config.count): ip for ip in ips}

        for future in concurrent.futures.as_completed(futures):
            if should_stop is not None and should_stop():
                executor.shutdown(wait=False, cancel_futures=True)
                break

            ip = futures[future]
            try:
                status, latency = future.result()
            except PingError:
                executor.shutdown(wait=False, cancel_futures=True)
                raise
            except Exception:
                status, latency = "Error", None

            hostname = cache.resolve(ip) if cache else ""
            result = HostResult(ip=ip, status=status, latency=latency, hostname=hostname)
            results.append(result)

            if on_result is not None:
                on_result(result, len(results), len(ips))
    finally:
        executor.shutdown(wait=True)

    return results
