"""IPv6 targets: probing, port checks, expansion, ordering, and discovery."""

import socket
import subprocess

import pytest

from ipmg.core import discovery, ping
from ipmg.core.diff import HostSnapshot, ScanRef, compare_snapshots, ip_sort_key
from ipmg.core.discovery import (
    discover_ipv6_neighbours,
    discover_targets,
    parse_bsd_neighbours,
    parse_linux_neighbours,
    parse_windows_neighbours,
)
from ipmg.core.portscan import scan_ports
from ipmg.exceptions import DiscoveryError, FileIOError
from ipmg.infrastructure.file_io import parse_manual_targets

# ------------------------------------------------------------------ probing


@pytest.mark.parametrize(
    "system, expected",
    [
        ("darwin", ["ping6", "-c", "1", "2001:db8::1"]),
        ("freebsd", ["ping6", "-c", "1", "2001:db8::1"]),
        ("linux", ["ping", "-c", "1", "-W", "2", "2001:db8::1"]),
        ("windows", ["ping", "-n", "1", "-w", "2000", "2001:db8::1"]),
    ],
)
def test_ipv6_uses_each_platforms_ping(system, expected):
    assert ping.build_ping_command("2001:db8::1", 2, 1, system=system) == expected


def test_ipv4_on_macos_keeps_ping_with_its_millisecond_timeout():
    assert ping.build_ping_command("10.0.0.1", 2, 1, system="darwin") == [
        "ping", "-c", "1", "-W", "2000", "10.0.0.1",
    ]  # fmt: skip


def test_a_scoped_link_local_address_is_valid():
    assert ping.validate_ip("fe80::1%eth0")
    assert ping.is_ipv6("fe80::1%eth0")
    assert not ping.is_ipv6("10.0.0.1")


def _deadline(output):
    def run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="ping6", timeout=3, output=output)

    return run


def test_replies_heard_before_the_deadline_still_count(monkeypatch):
    """macOS ping6 has no reply timeout, so the deadline can land after replies."""
    output = (
        "16 bytes from ::1, icmp_seq=0 hlim=64 time=0.100 ms\n"
        "16 bytes from ::1, icmp_seq=1 hlim=64 time=0.300 ms\n"
    )
    monkeypatch.setattr(ping.subprocess, "run", _deadline(output))

    status, latency = ping.ping_ip("::1", 1, 2)

    assert status == "Active"
    assert latency == pytest.approx(0.2)


@pytest.mark.parametrize("output", [None, "", b"PING6(56=40+8+8 bytes) --> 2001:db8::1\n"])
def test_silence_until_the_deadline_is_a_timeout(monkeypatch, output):
    monkeypatch.setattr(ping.subprocess, "run", _deadline(output))

    assert ping.ping_ip("2001:db8::1", 1, 1) == ("Timeout", None)


def _has_ipv6_loopback():
    try:
        with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as sock:
            sock.bind(("::1", 0))
        return True
    except OSError:
        return False


@pytest.mark.skipif(not _has_ipv6_loopback(), reason="no IPv6 loopback on this machine")
def test_port_checks_reach_ipv6_hosts():
    with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as listener:
        listener.bind(("::1", 0))
        listener.listen()
        port = listener.getsockname()[1]

        assert list(scan_ports("::1", [port], timeout=1.0)) == [port]


# ---------------------------------------------------------------- expansion


def test_mixed_ipv4_and_ipv6_targets_expand_together():
    assert parse_manual_targets("10.0.0.1\n2001:db8::1\n2001:db8::10-2001:db8::12") == [
        "10.0.0.1",
        "2001:db8::1",
        "2001:db8::10",
        "2001:db8::11",
        "2001:db8::12",
    ]


def test_a_small_ipv6_prefix_expands():
    assert len(parse_manual_targets("2001:db8::/120")) == 255


def test_an_ipv6_prefix_too_large_to_sweep_points_at_discovery():
    with pytest.raises(FileIOError, match=r"--discover ipv6.*/112 or smaller"):
        parse_manual_targets("2001:db8::/64")


def test_a_too_large_ipv4_prefix_keeps_its_plain_message():
    with pytest.raises(FileIOError) as exc_info:
        parse_manual_targets("10.0.0.0/8")

    assert "--discover" not in str(exc_info.value)


# ------------------------------------------------ ordering and change detection


def test_ipv4_sorts_before_ipv6_and_both_in_numeric_order():
    ips = ["2001:db8::2", "10.0.0.10", "::1", "not-an-ip", "10.0.0.9", "fe80::1%eth0"]

    assert sorted(ips, key=ip_sort_key) == [
        "10.0.0.9",
        "10.0.0.10",
        "::1",
        "2001:db8::2",
        "fe80::1%eth0",
        "not-an-ip",
    ]


def test_change_detection_handles_both_families():
    diff = compare_snapshots(
        [HostSnapshot("10.0.0.1", "Active", 1.0), HostSnapshot("2001:db8::1", "Active", 1.0)],
        [HostSnapshot("10.0.0.1", "Active", 1.0), HostSnapshot("2001:db8::1", "Timeout")],
        baseline_ref=ScanRef(id=1),
        current_ref=ScanRef(id=2),
    )

    assert [(change.type.value, change.ip) for change in diff.changes] == [
        ("host_offline", "2001:db8::1")
    ]


# ---------------------------------------------------------------- discovery

LINUX_NEIGH = """\
fe80::1 dev eth0 lladdr 52:54:00:12:34:56 router REACHABLE
2001:db8::20 dev eth0 lladdr 52:54:00:aa:bb:cc STALE
fe80::dead dev eth0 FAILED
2001:db8::30 dev eth0 INCOMPLETE
fe80::2 dev wlan0 lladdr 52:54:00:12:34:57 DELAY
"""

BSD_NDP = """\
Neighbor                             Linklayer Address  Netif Expire    S Flags
fe80::1%en0                          aa:bb:cc:dd:ee:ff    en0 23h59m58s S R
2001:db8::20                         aa:bb:cc:dd:ee:01    en0 23h59m58s S
fe80::dead%en0                       (incomplete)         en0 expired   I
ff02::fb                             33:33:0:0:0:fb       en0 permanent R
"""

WINDOWS_NETSH = """\

Interface 12: Ethernet


Internet Address                              Physical Address   Type
--------------------------------------------  -----------------  -----------
fe80::1                                       aa-bb-cc-dd-ee-ff  Reachable (Router)
2001:db8::20                                  aa-bb-cc-dd-ee-01  Stale
fe80::dead                                    00-00-00-00-00-00  Unreachable
ff02::1                                       33-33-00-00-00-01  Permanent

Interface 1: Loopback Pseudo-Interface 1

"""


def test_linux_neighbours_keep_live_entries_with_their_interface():
    assert parse_linux_neighbours(LINUX_NEIGH) == ["fe80::1%eth0", "2001:db8::20", "fe80::2%wlan0"]


def test_bsd_neighbours_skip_the_header_and_incomplete_entries():
    assert parse_bsd_neighbours(BSD_NDP) == ["fe80::1%en0", "2001:db8::20", "ff02::fb"]


def test_windows_neighbours_take_the_zone_from_the_interface_header():
    assert parse_windows_neighbours(WINDOWS_NETSH) == ["fe80::1%12", "2001:db8::20", "ff02::1"]


@pytest.fixture()
def fake_link(monkeypatch):
    """Stand in for the interface list and the commands discovery runs."""
    calls = []
    table = {"text": ""}

    def run(argv):
        calls.append(argv)
        return table["text"] if argv[0] in ("ip", "ndp", "netsh") else ""

    monkeypatch.setattr(discovery, "_run", run)
    monkeypatch.setattr(discovery.socket, "if_nameindex", lambda: [(1, "lo"), (2, "eth0")])
    return calls, table


def test_discovery_pings_all_nodes_then_reads_the_table(fake_link):
    calls, table = fake_link
    table["text"] = LINUX_NEIGH

    hosts = discover_ipv6_neighbours(system="linux")

    assert hosts == ["fe80::1%eth0", "2001:db8::20", "fe80::2%wlan0"]
    assert calls[0] == ["ping", "-6", "-c", "2", "-W", "1", "ff02::1%eth0"]  # not loopback
    assert calls[-1] == ["ip", "-6", "neigh", "show"]


def test_discovery_drops_multicast_and_table_furniture(fake_link):
    _calls, table = fake_link
    table["text"] = BSD_NDP

    assert discover_ipv6_neighbours(system="darwin") == ["fe80::1%en0", "2001:db8::20"]


def test_windows_discovery_uses_the_interface_index_as_the_zone(fake_link):
    calls, table = fake_link
    table["text"] = WINDOWS_NETSH

    discover_ipv6_neighbours(system="windows")

    assert calls[0] == ["ping", "-n", "2", "-w", "1000", "ff02::1%2"]


def test_discovery_with_no_neighbours_explains_itself(fake_link):
    with pytest.raises(DiscoveryError, match="No IPv6 neighbours"):
        discover_ipv6_neighbours(system="linux")


def test_a_missing_neighbour_command_is_not_a_crash(monkeypatch):
    def missing(*_args, **_kwargs):
        raise FileNotFoundError("ndp")

    monkeypatch.setattr(discovery.subprocess, "run", missing)
    monkeypatch.setattr(discovery.socket, "if_nameindex", lambda: [])

    with pytest.raises(DiscoveryError):
        discover_ipv6_neighbours(system="darwin")


@pytest.mark.parametrize(
    "family, sources",
    [
        ("ipv4", ["auto-discovery"]),
        ("ipv6", ["auto-discovery-ipv6"]),
        ("all", ["auto-discovery", "auto-discovery-ipv6"]),
    ],
)
def test_discover_targets_by_family(monkeypatch, family, sources):
    monkeypatch.setattr(discovery, "discover_local_subnet", lambda: ["10.0.0.1"])
    monkeypatch.setattr(discovery, "discover_ipv6_neighbours", lambda: ["fe80::1%eth0"])

    ips, found_sources = discover_targets(family)

    assert found_sources == sources
    assert ("10.0.0.1" in ips) is (family != "ipv6")
    assert ("fe80::1%eth0" in ips) is (family != "ipv4")
