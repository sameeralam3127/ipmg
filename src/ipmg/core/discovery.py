"""Local subnet discovery for ``ipmg --discover``."""

from __future__ import annotations

import ipaddress
import logging
import socket
from typing import List, Optional

from ipmg.exceptions import DiscoveryError

#: Reserved documentation address (RFC 5737). Connecting a UDP socket to it
#: sends no packets but makes the OS pick the outbound interface for us.
_PROBE_TARGET = ("192.0.2.1", 9)

log = logging.getLogger(__name__)


def _address_from_route() -> Optional[str]:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    except OSError:
        log.debug("could not open a probe socket", exc_info=True)
        return None

    try:
        sock.connect(_PROBE_TARGET)
        return sock.getsockname()[0]
    except OSError:
        log.debug("could not determine the outbound interface address", exc_info=True)
        return None
    finally:
        sock.close()


def _address_from_hostname() -> Optional[str]:
    try:
        return socket.gethostbyname(socket.gethostname())
    except OSError:
        log.debug("could not resolve the local hostname", exc_info=True)
        return None


def local_ip_address() -> str:
    """Best-effort primary IPv4 address of this machine.

    The outbound-route probe is tried first because resolving the hostname
    often yields 127.0.0.1, which would make ``--discover`` scan loopback.
    """
    for candidate in (_address_from_route(), _address_from_hostname()):
        if not candidate:
            continue
        try:
            address = ipaddress.ip_address(candidate)
        except ValueError:
            continue
        if not (address.is_loopback or address.is_link_local or address.is_unspecified):
            return candidate

    raise DiscoveryError(
        "Could not determine this machine's network address. "
        "Pass targets explicitly with --input instead of --discover."
    )


def discover_local_subnet(local_ip: Optional[str] = None, prefix: int = 24) -> List[str]:
    """Every host address in the /24 (by default) around the local address."""
    address = local_ip or local_ip_address()

    try:
        network = ipaddress.ip_network(f"{address}/{prefix}", strict=False)
    except ValueError as exc:
        raise DiscoveryError(f"Invalid local network '{address}/{prefix}': {exc}") from exc

    return [str(ip) for ip in network.hosts()]
