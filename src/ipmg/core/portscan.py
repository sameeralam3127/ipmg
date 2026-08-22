"""Optional TCP service discovery for hosts that already answered ICMP."""

from __future__ import annotations

import concurrent.futures
import socket
from typing import Iterable, List, Tuple

#: Common services worth a quick TCP connect once a host is known to be up.
DEFAULT_PORTS: Tuple[int, ...] = (21, 22, 25, 53, 80, 443, 445, 1433, 3306, 3389, 5432)

PORT_SERVICES = {
    21: "FTP",
    22: "SSH",
    25: "SMTP",
    53: "DNS",
    80: "HTTP",
    443: "HTTPS",
    445: "SMB",
    1433: "MSSQL",
    3306: "MySQL",
    3389: "RDP",
    5432: "PostgreSQL",
}


def port_service_name(port: int) -> str:
    return PORT_SERVICES.get(port, "")


def _probe(ip: str, port: int, timeout: float) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            return sock.connect_ex((ip, port)) == 0
    except OSError:
        return False


def encode_ports(ports: Iterable[int]) -> str:
    """Compact comma-separated encoding used to persist open ports."""
    return ",".join(str(port) for port in ports)


def decode_ports(value: str) -> Tuple[int, ...]:
    """Inverse of :func:`encode_ports`."""
    if not value:
        return ()
    return tuple(int(part) for part in value.split(",") if part.strip())


def parse_port_list(value: str) -> Tuple[int, ...]:
    """Parse a comma-separated port list (e.g. ``"22,80,443"``), validating each entry."""
    ports: List[int] = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        port = int(part)
        if not 1 <= port <= 65535:
            raise ValueError(f"port out of range (1-65535): {port}")
        ports.append(port)
    if not ports:
        raise ValueError("port list must contain at least one port")
    return tuple(ports)


def scan_ports(ip: str, ports: Iterable[int], timeout: float = 1.0) -> List[int]:
    """Probe ``ports`` on ``ip`` concurrently; return the ones that accepted a connection."""
    ports = list(ports)
    if not ports:
        return []

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(ports)) as executor:
        futures = {executor.submit(_probe, ip, port, timeout): port for port in ports}
        open_ports = [
            futures[future]
            for future in concurrent.futures.as_completed(futures)
            if future.result()
        ]

    return sorted(open_ports)
