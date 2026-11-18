"""The host page's API: ``/api/v1/hosts/{ip}`` and what hangs off it."""

import pytest
from fastapi.testclient import TestClient

from ipmg.core.engine import HostResult
from ipmg.core.snmp import SnmpInterface, SnmpResult
from ipmg.web.app import create_app
from ipmg.web.db import Database


def poll(ip="10.0.0.5", uptime=3600.0, oper="up"):
    return SnmpResult(
        ip=ip,
        ok=True,
        sys_name="core-sw",
        sys_descr="Switch OS 1.0",
        uptime_s=uptime,
        interfaces=(SnmpInterface(1, "Gi1", "Gi1", "Uplink", "up", oper, 1000, 10, 5),),
    )


@pytest.fixture()
def database(tmp_path):
    db = Database(tmp_path / "hosts.db")
    # lab: .5 is up, drops offline with a new name, then recovers; .6 is only in the first scan.
    db.record_scan(
        "lab",
        [
            HostResult("10.0.0.5", "Active", 4.0, "alpha", mac="AA:BB:CC:00:00:05", vendor="Acme"),
            HostResult("10.0.0.6", "Active", 6.0, "beta"),
        ],
        {},
        1.0,
        snmp_devices=[poll(uptime=9e5)],
    )
    db.record_scan(
        "lab",
        [HostResult("10.0.0.5", "Timeout", None, "alpha")],
        {},
        1.0,
        snmp_devices=[poll(uptime=60.0, oper="down")],
    )
    db.record_scan("lab", [HostResult("10.0.0.5", "Active", 5.0, "alpha")], {}, 1.0)
    # A second source never mixes with lab's comparisons.
    db.record_scan("office", [HostResult("10.0.0.5", "Active", 90.0, "alpha")], {}, 1.0)
    db.record_scan("lab", [HostResult("::1", "Active", 1.0, "v6")], {}, 1.0)
    return db


@pytest.fixture()
def client(database):
    app = create_app(database, token="t")
    with TestClient(app, headers={"Authorization": "Bearer t"}) as test_client:
        yield test_client


def test_the_summary_collects_what_the_history_knows(client):
    host = client.get("/api/v1/hosts/10.0.0.5").json()

    assert host["ip"] == "10.0.0.5"
    assert (host["hostname"], host["status"]) == ("alpha", "Active")
    assert (host["mac"], host["vendor"]) == ("AA:BB:CC:00:00:05", "Acme")
    assert (host["snmp_name"], host["snmp_descr"]) == ("core-sw", "Switch OS 1.0")
    assert host["scan_count"] == 4
    assert host["first_seen"] <= host["last_seen"]


def test_an_address_no_scan_recorded_is_a_404(client):
    response = client.get("/api/v1/hosts/10.9.9.9")

    assert response.status_code == 404
    assert "No scan" in response.json()["detail"]


def test_the_other_endpoints_are_empty_for_an_address_never_seen(client):
    for tail in ("results", "changes", "snmp"):
        assert client.get(f"/api/v1/hosts/10.9.9.9/{tail}").json() == []


@pytest.mark.parametrize("bad", ["not-an-ip", "10.0.0", "10.0.0.256", "fe80::1%eth0", "1.2.3.4.5"])
@pytest.mark.parametrize("tail", ["", "/results", "/changes", "/snmp"])
def test_anything_that_is_not_an_ip_is_a_400(client, bad, tail):
    assert client.get(f"/api/v1/hosts/{bad}{tail}").status_code == 400


def test_ipv6_works_and_is_matched_in_its_canonical_form(client):
    assert client.get("/api/v1/hosts/::1").json()["hostname"] == "v6"
    assert client.get("/api/v1/hosts/0:0:0:0:0:0:0:1").json()["hostname"] == "v6"
    assert client.get("/api/v1/hosts/%3A%3A1/results").json()[0]["hostname"] == "v6"


def test_results_have_one_row_per_scan_newest_first_with_the_scan(client):
    rows = client.get("/api/v1/hosts/10.0.0.5/results").json()

    assert [row["scan_id"] for row in rows] == [4, 3, 2, 1]
    assert [row["source"] for row in rows] == ["office", "lab", "lab", "lab"]
    assert [row["status"] for row in rows] == ["Active", "Active", "Timeout", "Active"]
    assert rows[0]["started_at"] and rows[0]["scan_status"] == "complete"
    assert client.get("/api/v1/hosts/10.0.0.5/results?limit=2").json() == rows[:2]


def test_changes_compare_scans_of_the_same_source_only(client):
    changes = client.get("/api/v1/hosts/10.0.0.5/changes").json()

    # Scan 4 is from another source, so its 90 ms never reads as a latency jump.
    assert {c["scan_id"] for c in changes} == {2, 3}
    assert all(c["ip"] == "10.0.0.5" and c["source"] == "lab" for c in changes)
    by_scan = {
        scan_id: {c["type"] for c in changes if c["scan_id"] == scan_id} for scan_id in (2, 3)
    }
    assert by_scan[3] == {"host_online"}
    assert {"host_offline", "device_rebooted", "interface_down"} <= by_scan[2]
    assert {c["baseline_id"] for c in changes if c["scan_id"] == 2} == {1}
    assert [c["scan_id"] for c in changes] == sorted((c["scan_id"] for c in changes), reverse=True)


def test_changes_leave_out_other_hosts_in_the_same_scans(client):
    # .6 vanished from lab in scan 2, but that is .6's story, not .5's.
    assert all(c["ip"] == "10.0.0.5" for c in client.get("/api/v1/hosts/10.0.0.5/changes").json())


def test_snmp_polls_come_back_newest_first_with_their_interfaces(client):
    polls = client.get("/api/v1/hosts/10.0.0.5/snmp").json()
    assert [p["scan_id"] for p in polls] == [2, 1]
    assert [p["uptime_s"] for p in polls] == [60.0, 9e5]
    assert polls[0]["interfaces"][0]["oper_status"] == "down"
    assert polls[1]["interfaces"][0]["oper_status"] == "up"


def test_changes_limit_bounds_how_many_scans_are_compared(client):
    changes = client.get("/api/v1/hosts/10.0.0.5/changes?limit=1").json()

    assert {c["scan_id"] for c in changes} == {3}
