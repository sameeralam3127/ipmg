import threading
import time

import pytest

from ipmg.core import neighbours
from ipmg.core.diff import ChangeType, HostSnapshot, compare_snapshots
from ipmg.core.engine import HostResult, ScanConfig, execute_scan
from ipmg.core.neighbours import (
    LOCALLY_ADMINISTERED,
    NeighbourCache,
    normalize_mac,
    parse_arp_an,
    parse_ip_neigh,
    parse_ndp_an,
    parse_proc_arp,
    parse_windows_arp,
    parse_windows_neighbors,
    read_neighbour_table,
    vendor_for,
)
from ipmg.infrastructure.database import Database
from ipmg.infrastructure.file_io import render_report
from ipmg.reporting.frames import report_columns, results_table


@pytest.mark.parametrize(
    "text",
    [
        "b8:27:eb:12:34:56",
        "B8-27-EB-12-34-56",
        "b827.eb12.3456",
        "b827eb123456",  # pragma: allowlist secret
        "b8:27:eb:12:34:56 ",
    ],
)
def test_every_common_spelling_normalises_the_same(text):
    assert normalize_mac(text) == "B8:27:EB:12:34:56"


def test_macos_unpadded_octets_are_padded():
    assert normalize_mac("0:1b:21:a:b:c") == "00:1B:21:0A:0B:0C"


@pytest.mark.parametrize(
    "text",
    ["ff:ff:ff:ff:ff:ff", "01:00:5e:00:00:fb", "00:00:00:00:00:00", "(incomplete)", "", "zz"],
)
def test_addresses_that_are_not_a_host_s_are_dropped(text):
    assert normalize_mac(text) == ""


# ------------------------------------------------------------------ tables

IP_NEIGH = """\
192.168.1.1 dev eth0 lladdr b8:27:eb:12:34:56 REACHABLE
192.168.1.20 dev eth0 lladdr 52:54:00:aa:bb:cc STALE
192.168.1.30 dev eth0  FAILED
192.168.1.31 dev eth0  INCOMPLETE
fe80::1 dev eth0 lladdr b8:27:eb:12:34:56 router REACHABLE
2001:db8::5 dev eth0 lladdr 52:54:00:aa:bb:cc DELAY
"""


def test_linux_ip_neigh():
    assert parse_ip_neigh(IP_NEIGH) == {
        "192.168.1.1": "B8:27:EB:12:34:56",
        "192.168.1.20": "52:54:00:AA:BB:CC",
        "fe80::1%eth0": "B8:27:EB:12:34:56",
        "2001:db8::5": "52:54:00:AA:BB:CC",
    }


def test_linux_proc_net_arp():
    text = """\
IP address       HW type     Flags       HW address            Mask     Device
192.168.1.1      0x1         0x2         b8:27:eb:12:34:56     *        eth0
192.168.1.30     0x1         0x0         00:00:00:00:00:00     *        eth0
"""
    assert parse_proc_arp(text) == {"192.168.1.1": "B8:27:EB:12:34:56"}


def test_bsd_arp_an():
    output = """\
? (192.168.1.1) at b8:27:eb:12:34:56 on en0 ifscope [ethernet]
? (192.168.1.30) at (incomplete) on en0 ifscope [ethernet]
? (192.168.1.255) at ff:ff:ff:ff:ff:ff on en0 ifscope [ethernet]
? (224.0.0.251) at 1:0:5e:0:0:fb on en0 ifscope permanent [ethernet]
? (192.168.1.40) at 2:42:ac:11:0:2 on en0 ifscope [ethernet]
"""
    assert parse_arp_an(output) == {
        "192.168.1.1": "B8:27:EB:12:34:56",
        "192.168.1.40": "02:42:AC:11:00:02",
    }


def test_bsd_ndp_an():
    output = """\
Neighbor                        Linklayer Address  Netif Expire    S Flags
fe80::1%en0                     b8:27:eb:12:34:56     en0 23h59m58s S R
2001:db8::5                     52:54:0:aa:bb:cc      en0 permanent R
fe80::9%en0                     (incomplete)          en0 expired   N
"""
    assert parse_ndp_an(output) == {
        "fe80::1%en0": "B8:27:EB:12:34:56",
        "2001:db8::5": "52:54:00:AA:BB:CC",
    }


def test_windows_arp_a():
    output = """\

Interface: 192.168.1.50 --- 0xb
  Internet Address      Physical Address      Type
  192.168.1.1           b8-27-eb-12-34-56     dynamic
  192.168.1.255         ff-ff-ff-ff-ff-ff     static
  224.0.0.22            01-00-5e-00-00-16     static
"""
    assert parse_windows_arp(output) == {"192.168.1.1": "B8:27:EB:12:34:56"}


def test_windows_ipv6_neighbors():
    output = """\

Interface 11: Ethernet


Internet Address                              Physical Address   Type
--------------------------------------------  -----------------  -----------
fe80::1                                       b8-27-eb-12-34-56  Reachable (Router)
fe80::9                                       00-00-00-00-00-00  Unreachable
ff02::1                                       33-33-00-00-00-01  Permanent
"""
    assert parse_windows_neighbors(output) == {"fe80::1%11": "B8:27:EB:12:34:56"}


def test_each_system_reads_its_own_tools(monkeypatch):
    ran = []

    def fake_run(argv):
        ran.append(argv[0])
        return ""

    monkeypatch.setattr(neighbours, "_run_command", fake_run)
    monkeypatch.setattr(neighbours, "_read_proc_arp", lambda: "")
    for system in ("Linux", "Windows", "Darwin", "FreeBSD"):
        read_neighbour_table(system)
    assert ran == ["ip", "arp", "netsh", "arp", "ndp", "arp", "ndp"]


def test_linux_without_iproute2_falls_back_to_proc(monkeypatch):
    monkeypatch.setattr(neighbours, "_run_command", lambda _argv: "")
    monkeypatch.setattr(
        neighbours,
        "_read_proc_arp",
        lambda: "IP address HW type Flags HW address Mask Device\n"
        "10.0.0.1 0x1 0x2 b8:27:eb:12:34:56 * eth0\n",
    )
    assert read_neighbour_table("Linux") == {"10.0.0.1": "B8:27:EB:12:34:56"}


# ------------------------------------------------------------------- cache


def test_the_cache_rereads_the_table_for_a_host_that_answered_after_the_last_read():
    tables = [{}, {"10.0.0.1": "B8:27:EB:12:34:56"}]
    reads = []

    def reader():
        reads.append(1)
        return tables[min(len(reads) - 1, 1)]

    cache = NeighbourCache(reader, min_interval_s=0)
    first = time.perf_counter()
    assert cache.lookup("10.0.0.2", first) == ""
    assert cache.lookup("10.0.0.1", time.perf_counter()) == "B8:27:EB:12:34:56"
    # Answered before the second read: no third read needed.
    assert cache.lookup("10.0.0.1", first) == "B8:27:EB:12:34:56"
    assert len(reads) == 2


def test_hosts_answering_together_share_one_read():
    reads = []
    gate = threading.Event()

    def slow_reader():
        reads.append(1)
        gate.wait(1)
        return {f"10.0.0.{n}": f"02:00:00:00:00:{n:02X}" for n in range(1, 9)}

    cache = NeighbourCache(slow_reader, min_interval_s=0)
    answered = time.perf_counter()
    found = []
    threads = [
        threading.Thread(target=lambda n=n: found.append(cache.lookup(f"10.0.0.{n}", answered)))
        for n in range(1, 9)
    ]
    for thread in threads:
        thread.start()
    time.sleep(0.05)
    gate.set()
    for thread in threads:
        thread.join(2)

    assert len(reads) == 1
    assert len([mac for mac in found if mac]) == 8


def test_a_host_beyond_a_router_has_no_mac():
    # Off-link traffic resolves the router's MAC, listed under the router's IP.
    cache = NeighbourCache(lambda: {"192.168.1.1": "B8:27:EB:12:34:56"}, min_interval_s=0)

    assert cache.lookup("8.8.8.8") == ""


def test_an_unreadable_table_means_no_mac():
    def broken():
        raise OSError("no arp here")

    assert NeighbourCache(broken, min_interval_s=0).lookup("10.0.0.1") == ""


def test_a_scoped_address_matches_the_table_without_its_zone():
    cache = NeighbourCache(lambda: {"2001:db8::5": "52:54:00:AA:BB:CC"}, min_interval_s=0)

    assert cache.lookup("2001:db8::5%eth0") == "52:54:00:AA:BB:CC"


# ----------------------------------------------------------------- vendors


@pytest.mark.parametrize(
    "mac, vendor",
    [
        ("b8:27:eb:12:34:56", "Raspberry Pi Foundation"),
        ("dc:a6:32:00:00:01", "Raspberry Pi Trading Ltd"),
        ("00:00:00:00:00:01", "XEROX CORPORATION"),
        # The most specific registration wins over the large block it is cut from.
        ("8c:1f:64:af:a0:01", "DATA ELECTRONIC DEVICES, INC"),
        ("c8:5c:e2:70:00:01", "SYNERGY SYSTEMS AND SOLUTIONS"),
    ],
)
def test_vendors_come_from_the_bundled_ieee_lists(mac, vendor):
    assert vendor_for(mac) == vendor


def test_a_locally_administered_mac_has_no_vendor():
    # Docker, VMs, and phones' per-network random MACs set the "local" bit.
    assert vendor_for("02:42:ac:11:00:02") == LOCALLY_ADMINISTERED
    assert vendor_for("da:a1:19:00:00:01") == LOCALLY_ADMINISTERED


def test_an_unknown_or_invalid_mac_has_no_vendor():
    assert vendor_for("") == ""
    assert vendor_for("not a mac") == ""


# ----------------------------------------------------------------- engine


def test_mac_lookup_fills_responding_hosts_only(monkeypatch):
    statuses = {"10.0.0.1": ("Active", 1.0), "10.0.0.2": ("Timeout", None)}
    monkeypatch.setattr("ipmg.core.engine.ping_ip", lambda ip, *_a: statuses[ip])
    monkeypatch.setattr(
        "ipmg.core.neighbours.read_neighbour_table",
        lambda: {"10.0.0.1": "B8:27:EB:12:34:56", "10.0.0.2": "52:54:00:AA:BB:CC"},
    )

    results = {r.ip: r for r in execute_scan(list(statuses), ScanConfig(mac_lookup=True))}

    assert results["10.0.0.1"].mac == "B8:27:EB:12:34:56"
    assert results["10.0.0.1"].vendor == "Raspberry Pi Foundation"
    assert (results["10.0.0.2"].mac, results["10.0.0.2"].vendor) == ("", "")


def test_without_mac_lookup_the_table_is_never_read(monkeypatch):
    monkeypatch.setattr("ipmg.core.engine.ping_ip", lambda *_a: ("Active", 1.0))
    monkeypatch.setattr(
        "ipmg.core.neighbours.read_neighbour_table", lambda: pytest.fail("table was read")
    )

    assert execute_scan(["10.0.0.1"], ScanConfig())[0].mac == ""


def test_mac_columns_reach_the_report():
    columns = report_columns(ScanConfig(mac_lookup=True))
    table = results_table(
        [HostResult("10.0.0.1", "Active", 1.0, mac="B8:27:EB:12:34:56", vendor="Raspberry Pi")],
        "2026-10-17 12:00:00",
        1.0,
        columns,
    )

    header, row = render_report(table, "csv").decode().splitlines()
    assert header.split(",")[5:7] == ["MAC Address", "Vendor"]
    assert "B8:27:EB:12:34:56,Raspberry Pi" in row
    assert "| MAC Address | Vendor |" in render_report(table, "md").decode()


# ------------------------------------------------------- change detection


def snap(ip, mac, hostname="", status="Active"):
    return HostSnapshot(ip=ip, status=status, latency=1.0, hostname=hostname, mac=mac)


def test_a_device_moved_by_dhcp_is_one_ip_change_not_a_new_and_a_removed_host():
    diff = compare_snapshots(
        [snap("10.0.0.5", "B8:27:EB:12:34:56")], [snap("10.0.0.9", "B8:27:EB:12:34:56")]
    )

    [change] = diff.changes
    assert change.type is ChangeType.IP_CHANGED
    assert (change.previous, change.current) == ("10.0.0.5", "10.0.0.9")


def test_a_move_seen_by_both_hostname_and_mac_is_reported_once():
    diff = compare_snapshots(
        [snap("10.0.0.5", "B8:27:EB:12:34:56", "pi.lan")],
        [snap("10.0.0.9", "B8:27:EB:12:34:56", "pi.lan")],
    )

    assert [change.type for change in diff.changes] == [ChangeType.IP_CHANGED]


def test_another_device_at_the_same_ip_is_a_mac_change():
    diff = compare_snapshots(
        [snap("10.0.0.5", "B8:27:EB:12:34:56")], [snap("10.0.0.5", "52:54:00:AA:BB:CC")]
    )

    [change] = diff.changes
    assert change.type is ChangeType.MAC_CHANGED
    assert change.severity.value == "warning"
    assert change.describe() == "MAC address changed: B8:27:EB:12:34:56 -> 52:54:00:AA:BB:CC"


def test_scans_without_macs_never_report_mac_changes():
    diff = compare_snapshots([snap("10.0.0.5", "")], [snap("10.0.0.5", "52:54:00:AA:BB:CC")])

    assert diff.changes == ()


# ------------------------------------------------------------------ history


def test_mac_and_vendor_are_stored_and_reach_the_inventory(tmp_path):
    db = Database(tmp_path / "h.db")
    db.record_scan(
        "lan",
        [HostResult("10.0.0.1", "Active", 1.0, mac="B8:27:EB:12:34:56", vendor="Raspberry Pi")],
        {"mac_lookup": True},
        1.0,
    )
    # A later scan without --mac keeps the inventory's known MAC.
    later = db.record_scan("lan", [HostResult("10.0.0.1", "Active", 1.0)], {}, 1.0)

    [asset] = db.inventory()
    assert (asset["mac"], asset["vendor"]) == ("B8:27:EB:12:34:56", "Raspberry Pi")
    assert db.get_results(later)[0]["mac"] == ""
    assert db.snapshot(1)[0].mac == "B8:27:EB:12:34:56"
