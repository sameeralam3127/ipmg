"""Wake-on-LAN: wake a host by sending its "magic packet" (``ipmg wake``).

The packet is six ``0xFF`` bytes followed by the target's MAC address
repeated 16 times, sent as an ordinary UDP broadcast: no raw sockets and no
elevated privileges. The target's network card watches for it while the
machine sleeps, so the target must have Wake-on-LAN enabled and be reachable
by the broadcast: on the same network segment, or through a directed
broadcast address (``192.168.1.255``) a router forwards.
"""

from __future__ import annotations

import ipaddress
import socket

from ipmg.core.neighbours import normalize_mac
from ipmg.exceptions import IPMGError

DEFAULT_BROADCAST = "255.255.255.255"
#: The "discard" port. 7 (echo) is the other common choice.
DEFAULT_PORT = 9


class WakeError(IPMGError):
    """Raised for a magic packet that cannot be built or sent."""


def parse_mac(text: str) -> bytes:
    """The six bytes of a MAC written ``AA:BB:CC:DD:EE:FF``, ``AA-BB-...``, or ``AABBCCDDEEFF``."""
    mac = normalize_mac(text)
    if not mac:
        raise WakeError(
            f"Invalid MAC address: {text!r}. Write it as AA:BB:CC:DD:EE:FF, "
            "AA-BB-CC-DD-EE-FF, or AABBCCDDEEFF."
        )
    return bytes.fromhex(mac.replace(":", ""))


def magic_packet(mac: bytes) -> bytes:
    if len(mac) != 6:
        raise WakeError("A MAC address is 6 bytes.")
    return b"\xff" * 6 + mac * 16


def _check_destination(broadcast: str, port: int) -> None:
    try:
        address = ipaddress.ip_address(broadcast)
    except ValueError:
        raise WakeError(f"Invalid broadcast address: {broadcast!r}.") from None
    if address.version != 4:
        raise WakeError("Wake-on-LAN broadcasts need an IPv4 address, such as 192.168.1.255.")
    if not 0 < port < 65536:
        raise WakeError(f"Port out of range (1-65535): {port}")


def _udp_socket() -> socket.socket:
    return socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


def send_magic_packet(
    mac: str,
    broadcast: str = DEFAULT_BROADCAST,
    port: int = DEFAULT_PORT,
) -> str:
    """Send the magic packet for ``mac``; returns the MAC as it was sent."""
    packet = magic_packet(parse_mac(mac))
    _check_destination(broadcast, port)
    try:
        with _udp_socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(packet, (broadcast, port))
    except OSError as exc:
        raise WakeError(f"Could not send the magic packet to {broadcast}:{port}: {exc}") from exc
    return normalize_mac(mac)
