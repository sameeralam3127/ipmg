"""Host health over the API: analytics, SLA targets, maintenance windows, reports."""

import csv
import io
import sqlite3
import time
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from ipmg.core.engine import HostResult
from ipmg.services.availability_service import MAX_DAYS, AvailabilityService
from ipmg.web.app import create_app
from ipmg.web.db import Database

IP = "10.0.0.5"
FMT = "%Y-%m-%d %H:%M:%S"


def stamp(moment: datetime) -> str:
    return moment.strftime(FMT)


def seed(
    db,
    pattern,
    *,
    ip=IP,
    source="lab",
    end=None,
    step=timedelta(minutes=10),
    latency=5.0,
    status="complete",
):
    """One scan per character, ending at ``end``: ``U`` replies, anything else times out."""
    end = end or datetime.now().replace(microsecond=0) - timedelta(minutes=1)
    ids = []
    for index, char in enumerate(pattern):
        when = end - step * (len(pattern) - 1 - index)
        scan_id = db.record_scan(
            source,
            [
                HostResult(
                    ip, "Active" if char == "U" else "Timeout", latency if char == "U" else None
                )
            ],
            {},
            1.0,
            status=status,
        )
        with sqlite3.connect(db.path) as conn:
            conn.execute(
                "UPDATE results SET checked_at = ? WHERE scan_id = ?", (stamp(when), scan_id)
            )
        ids.append(scan_id)
    return ids


@pytest.fixture()
def database(tmp_path):
    return Database(tmp_path / "health.db")


@pytest.fixture()
def client(database):
    app = create_app(database, token="t")
    with TestClient(app, headers={"Authorization": "Bearer t"}) as test_client:
        yield test_client


def health(client, ip=IP, **params):
    response = client.get(f"/api/v1/hosts/{ip}/health", params=params)
    assert response.status_code == 200, response.text
    return response.json()


# ------------------------------------------------------------- analytics


def test_health_reports_availability_latency_and_outages(client, database):
    seed(database, "UUUDDUUUUU")

    body = health(client)

    assert body["ip"] == IP
    assert (body["checks"], body["up"], body["down"], body["excluded"]) == (10, 8, 2, 0)
    assert body["availability_pct"] == 80.0
    assert body["latency"] == {
        "count": 8, "min": 5.0, "mean": 5.0, "p50": 5.0, "p95": 5.0, "p99": 5.0, "max": 5.0,
    }  # fmt: skip
    assert body["outages"]["count"] == 1
    assert body["outages"]["mttr_s"] == 20 * 60
    assert len(body["outage_list"]) == 1 and not body["outage_list"][0]["ongoing"]
    assert body["sla"] is None
    assert "scans" in body["note"]
    assert body["window"]["days"] == 30 and body["source"] is None


def test_health_percentiles_follow_the_replies(client, database):
    for latency in (10.0, 20.0, 30.0, 40.0):
        seed(database, "U", latency=latency, end=datetime.now() - timedelta(hours=latency))

    latency = health(client)["latency"]

    assert (latency["p50"], latency["min"], latency["max"]) == (25.0, 10.0, 40.0)
    assert latency["p95"] == 38.5 and latency["p99"] == 39.7


def test_a_host_that_is_down_now_has_an_ongoing_outage_and_no_mttr(client, database):
    seed(database, "UUDDD")

    outages = health(client)["outages"]

    assert (outages["count"], outages["ongoing"], outages["recovered"]) == (1, 1, 0)
    assert outages["mttr_s"] is None


def test_a_host_never_down_has_no_mttr_or_mtbf(client, database):
    seed(database, "UUUU")

    outages = health(client)["outages"]

    assert (outages["count"], outages["mttr_s"], outages["mtbf_s"]) == (0, None, None)


def test_a_host_that_never_answered_is_zero_available_with_no_latency(client, database):
    seed(database, "DDDD")

    body = health(client)

    assert body["availability_pct"] == 0.0
    assert body["latency"]["count"] == 0 and body["latency"]["p95"] is None


def test_an_unseen_host_is_a_404(client):
    assert client.get("/api/v1/hosts/10.9.9.9/health").status_code == 404


@pytest.mark.parametrize("bad", ["nope", "10.0.0.256", "fe80::1%eth0"])
def test_an_invalid_address_is_a_400(client, bad):
    assert client.get(f"/api/v1/hosts/{bad}/health").status_code == 400
    assert client.get(f"/api/v1/hosts/{bad}/sla").status_code == 400
    assert client.get(f"/api/v1/hosts/{bad}/availability/report").status_code == 400
    assert (
        client.put(f"/api/v1/hosts/{bad}/sla", json={"availability_target": 99}).status_code == 400
    )


def test_a_host_seen_only_outside_the_window_has_no_checks_not_an_error(client, database):
    seed(database, "UUU", end=datetime.now() - timedelta(days=100))

    body = health(client, days=30)

    assert body["checks"] == 0 and body["availability_pct"] is None
    assert body["outages"]["count"] == 0 and body["daily"] == []
    assert health(client, days=365)["checks"] == 3


@pytest.mark.parametrize(
    ("asked", "used"),
    [(0, 1), (-5, 1), (1, 1), (7, 7), (365, 365), (366, MAX_DAYS), (99999, MAX_DAYS)],
)
def test_days_are_clamped(client, database, asked, used):
    seed(database, "U")
    assert health(client, days=asked)["window"]["days"] == used


def test_days_must_be_a_number(client, database):
    seed(database, "U")
    assert client.get(f"/api/v1/hosts/{IP}/health?days=many").status_code == 422


def test_the_window_decides_which_checks_count(client, database):
    seed(database, "D", end=datetime.now() - timedelta(days=10))
    seed(database, "UUU", end=datetime.now() - timedelta(hours=1))

    assert health(client, days=7)["availability_pct"] == 100.0
    assert health(client, days=30)["availability_pct"] == 75.0


def test_only_completed_and_cancelled_scans_count(client, database):
    seed(database, "UU", status="complete")
    seed(database, "UU", status="cancelled", end=datetime.now() - timedelta(hours=2))
    seed(database, "DDDD", status="interrupted", end=datetime.now() - timedelta(hours=3))
    running = database.create_scan("lab", 1, {})
    database.add_result(running, HostResult(IP, "Timeout", None))

    body = health(client)

    assert (body["checks"], body["down"]) == (4, 0)


def test_source_narrows_the_history_and_lists_every_source(client, database):
    seed(database, "UUUU", source="lab")
    seed(database, "DD", source="office", end=datetime.now() - timedelta(hours=2))

    everything = health(client)
    lab = health(client, source="lab")
    office = health(client, source="office")

    assert everything["sources"] == ["lab", "office"] and everything["checks"] == 6
    assert (lab["checks"], lab["availability_pct"], lab["source"]) == (4, 100.0, "lab")
    assert (office["checks"], office["availability_pct"]) == (2, 0.0)
    assert lab["sources"] == ["lab", "office"]


def test_an_unknown_source_has_no_checks(client, database):
    seed(database, "UU")
    body = health(client, source="nowhere")
    assert body["checks"] == 0 and body["availability_pct"] is None


def test_source_is_matched_literally(client, database):
    seed(database, "UU", source="a%b")
    seed(database, "D", source="axb", end=datetime.now() - timedelta(hours=2))
    assert health(client, source="a%b")["checks"] == 2


def test_other_hosts_do_not_leak_in(client, database):
    seed(database, "UUUU")
    seed(database, "DDDD", ip="10.0.0.6")
    assert health(client)["availability_pct"] == 100.0
    assert health(client, ip="10.0.0.6")["availability_pct"] == 0.0


def test_ipv6_hosts_work_in_every_form(client, database):
    seed(database, "UUD", ip="::1")
    for form in ("::1", "0:0:0:0:0:0:0:1", "%3A%3A1"):
        assert health(client, ip=form)["checks"] == 3
    assert health(client, ip="::1")["ip"] == "::1"


def test_daily_breakdown_covers_each_day_with_checks(client, database):
    seed(database, "UUUD", step=timedelta(days=1), end=datetime.now() - timedelta(hours=1))

    daily = health(client)["daily"]

    assert len(daily) == 4
    assert [d["availability_pct"] for d in daily] == [100.0, 100.0, 100.0, 0.0]
    assert daily == sorted(daily, key=lambda d: d["date"])


def test_outage_list_is_capped_but_the_summary_counts_them_all(client, database):
    seed(database, "UD" * 60, step=timedelta(minutes=1))

    body = health(client)

    assert body["outages"]["count"] == 60
    assert len(body["outage_list"]) == 50 and body["outages_truncated"] is True
    starts = [o["started_at"] for o in body["outage_list"]]
    assert starts == sorted(starts, reverse=True)


def test_a_long_history_is_answered_quickly(client, database):
    rows = [
        (1, IP, "Active" if i % 7 else "Timeout", 4.0 if i % 7 else None, "", "",
         stamp(datetime.now() - timedelta(minutes=i)), "", "", "")
        for i in range(5000)
    ]  # fmt: skip
    scan_id = database.create_scan("lab", 1, {})
    database.finish_scan(scan_id, "complete", 1.0)
    with sqlite3.connect(database.path) as conn:
        conn.executemany(
            "INSERT INTO results (scan_id, ip, status, latency, hostname, open_ports, checked_at, "
            "method, mac, vendor) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(scan_id, *row[1:]) for row in rows],
        )

    started = time.perf_counter()
    body = health(client, days=30)

    assert body["checks"] == 5000
    assert time.perf_counter() - started < 3


def test_service_takes_the_clock_as_an_argument(database):
    seed(database, "UUUU", end=datetime(2026, 1, 10, 12, 0, 0))
    service = AvailabilityService(database)

    assert service.health(IP, days=1, now=datetime(2026, 1, 10, 13, 0, 0))["checks"] == 4
    assert service.health(IP, days=1, now=datetime(2026, 3, 1))["checks"] == 0
    assert service.health("10.9.9.9") is None


# ------------------------------------------------------------ SLA targets


def test_no_sla_target_until_one_is_set(client, database):
    seed(database, "U")
    assert client.get(f"/api/v1/hosts/{IP}/sla").status_code == 404


def test_set_read_replace_and_delete_a_target(client, database):
    seed(database, "U")

    saved = client.put(
        f"/api/v1/hosts/{IP}/sla", json={"availability_target": 99.9, "latency_p95_ms": 50}
    )
    assert saved.status_code == 200
    assert saved.json()["availability_target"] == 99.9 and saved.json()["latency_p95_ms"] == 50
    assert client.get(f"/api/v1/hosts/{IP}/sla").json()["ip"] == IP

    replaced = client.put(f"/api/v1/hosts/{IP}/sla", json={"availability_target": 95}).json()
    assert (replaced["availability_target"], replaced["latency_p95_ms"]) == (95, None)

    assert client.delete(f"/api/v1/hosts/{IP}/sla").status_code == 204
    assert client.get(f"/api/v1/hosts/{IP}/sla").status_code == 404
    assert client.delete(f"/api/v1/hosts/{IP}/sla").status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"availability_target": 0},
        {"availability_target": -1},
        {"availability_target": 100.01},
        {"availability_target": "high"},
        {"availability_target": None},
        {},
        {"availability_target": 99, "latency_p95_ms": 0},
        {"availability_target": 99, "latency_p95_ms": -3},
        {"availability_target": 99, "latency_p95_ms": 3_600_001},
        {"availability_target": 99, "latency_p95_ms": "fast"},
    ],
)
def test_an_invalid_target_is_refused_and_stores_nothing(client, database, body):
    seed(database, "U")

    assert client.put(f"/api/v1/hosts/{IP}/sla", json=body).status_code == 422
    assert client.get(f"/api/v1/hosts/{IP}/sla").status_code == 404


@pytest.mark.parametrize("target", [100, 0.01, 99.999])
def test_the_edges_of_a_valid_target_are_accepted(client, target):
    response = client.put("/api/v1/hosts/10.7.7.7/sla", json={"availability_target": target})
    assert response.status_code == 200 and response.json()["availability_target"] == target


def test_a_target_can_be_set_before_the_host_is_ever_scanned(client):
    assert (
        client.put("/api/v1/hosts/10.7.7.7/sla", json={"availability_target": 99}).status_code
        == 200
    )
    assert client.get("/api/v1/hosts/10.7.7.7/health").status_code == 404


def test_health_reports_whether_the_target_was_met_and_the_days_that_missed_it(client, database):
    seed(database, "UUUUUUUUUD", step=timedelta(hours=1), end=datetime.now() - timedelta(hours=1))
    client.put(f"/api/v1/hosts/{IP}/sla", json={"availability_target": 99, "latency_p95_ms": 2})

    sla = health(client)["sla"]

    assert sla["availability_met"] is False and sla["latency_met"] is False
    assert {v["kind"] for v in sla["violations"]} == {"availability", "latency"}
    assert sla["availability_target"] == 99 and sla["latency_p95_ms"] == 2


def test_a_target_that_is_met_has_no_violations(client, database):
    seed(database, "UUUUUUUUUU")
    client.put(f"/api/v1/hosts/{IP}/sla", json={"availability_target": 99.9, "latency_p95_ms": 10})

    sla = health(client)["sla"]

    assert (sla["availability_met"], sla["latency_met"], sla["violations"]) == (True, True, [])


def test_exactly_on_target_is_met(client, database):
    seed(database, "U" * 999 + "D", step=timedelta(minutes=1))
    client.put(f"/api/v1/hosts/{IP}/sla", json={"availability_target": 99.9})

    assert health(client)["sla"]["availability_met"] is True


def test_a_target_on_a_host_with_no_checks_in_the_window_is_not_met_or_missed(client, database):
    seed(database, "U", end=datetime.now() - timedelta(days=90))
    client.put(f"/api/v1/hosts/{IP}/sla", json={"availability_target": 99})

    sla = health(client, days=7)["sla"]

    assert sla["availability_met"] is None and sla["violations"] == []


def test_targets_are_per_host(client, database):
    seed(database, "U")
    seed(database, "U", ip="10.0.0.6")
    client.put(f"/api/v1/hosts/{IP}/sla", json={"availability_target": 99})

    assert health(client)["sla"] is not None
    assert health(client, ip="10.0.0.6")["sla"] is None


def test_targets_and_windows_survive_reopening_the_database(tmp_path):
    path = tmp_path / "persist.db"
    first = Database(path)
    first.set_sla(IP, 99.5, 20)
    first.add_maintenance(IP, "2026-01-01 00:00:00", "2026-01-01 01:00:00", "patching")

    again = Database(path)

    assert again.get_sla(IP)["availability_target"] == 99.5
    assert again.list_maintenance(ip=IP)[0]["reason"] == "patching"


# ------------------------------------------------------ maintenance windows


def window_body(start, end, **extra):
    return {"starts_at": stamp(start), "ends_at": stamp(end), **extra}


def test_create_list_and_delete_a_window(client):
    now = datetime.now().replace(microsecond=0)

    created = client.post(
        "/api/v1/maintenance",
        json=window_body(now, now + timedelta(hours=2), ip=IP, reason="  kernel update  "),
    )

    assert created.status_code == 201
    row = created.json()
    assert (row["ip"], row["reason"], row["starts_at"]) == (IP, "kernel update", stamp(now))
    assert client.get("/api/v1/maintenance").json() == [row]

    assert client.delete(f"/api/v1/maintenance/{row['id']}").status_code == 204
    assert client.get("/api/v1/maintenance").json() == []
    assert client.delete(f"/api/v1/maintenance/{row['id']}").status_code == 404


def test_a_window_without_a_host_covers_every_host(client):
    now = datetime.now()
    row = client.post("/api/v1/maintenance", json=window_body(now, now + timedelta(hours=1))).json()
    assert row["ip"] is None and row["reason"] == ""


@pytest.mark.parametrize(
    ("starts", "ends"),
    [
        ("2026-11-18 02:00", "2026-11-18 02:00"),
        ("2026-11-18 03:00", "2026-11-18 02:00"),
        ("garbage", "2026-11-18 02:00"),
        ("2026-11-18 02:00", ""),
        ("2026-11-18 02:00", "2026-11-18 03:00Z"),
        ("2026-11-18 02:00", "2026-11-18T03:00:00+01:00"),
        ("2026-02-30 02:00", "2026-03-01 02:00"),
        ("", ""),
    ],
)
def test_an_unusable_window_is_a_400_and_stores_nothing(client, starts, ends):
    response = client.post("/api/v1/maintenance", json={"starts_at": starts, "ends_at": ends})

    assert response.status_code == 400
    assert response.json()["detail"]
    assert client.get("/api/v1/maintenance").json() == []


def test_the_t_separator_and_missing_seconds_are_normalised(client):
    row = client.post(
        "/api/v1/maintenance",
        json={"starts_at": "2026-11-18T02:00", "ends_at": "2026-11-18 03:30:15"},
    ).json()
    assert (row["starts_at"], row["ends_at"]) == ("2026-11-18 02:00:00", "2026-11-18 03:30:15")


def test_a_reason_over_the_limit_is_refused(client):
    now = datetime.now()
    body = window_body(now, now + timedelta(hours=1), reason="x" * 201)
    assert client.post("/api/v1/maintenance", json=body).status_code == 422
    body["reason"] = "x" * 200
    assert client.post("/api/v1/maintenance", json=body).status_code == 201


def test_an_invalid_host_on_a_window_is_a_400(client):
    now = datetime.now()
    body = window_body(now, now + timedelta(hours=1), ip="not-an-ip")
    assert client.post("/api/v1/maintenance", json=body).status_code == 400
    assert client.get("/api/v1/maintenance?ip=not-an-ip").status_code == 400


def test_listing_for_a_host_includes_its_own_and_the_every_host_windows(client):
    now = datetime.now()
    mine = client.post(
        "/api/v1/maintenance", json=window_body(now, now + timedelta(hours=1), ip=IP)
    ).json()
    other = client.post(
        "/api/v1/maintenance", json=window_body(now, now + timedelta(hours=1), ip="10.0.0.6")
    ).json()
    everyone = client.post(
        "/api/v1/maintenance", json=window_body(now, now + timedelta(hours=1))
    ).json()

    ids = {row["id"] for row in client.get(f"/api/v1/maintenance?ip={IP}").json()}

    assert ids == {mine["id"], everyone["id"]}
    assert {row["id"] for row in client.get("/api/v1/maintenance").json()} == {
        mine["id"], other["id"], everyone["id"],
    }  # fmt: skip


def test_listing_is_soonest_first(client):
    base = datetime(2026, 5, 1)
    for hours in (5, 1, 3):
        client.post(
            "/api/v1/maintenance",
            json=window_body(base + timedelta(hours=hours), base + timedelta(hours=hours + 1)),
        )
    starts = [row["starts_at"] for row in client.get("/api/v1/maintenance").json()]
    assert starts == sorted(starts)


def test_checks_inside_a_window_leave_availability_and_the_sla(client, database):
    end = datetime.now().replace(microsecond=0) - timedelta(minutes=1)
    seed(database, "UUDDDDUU", end=end)
    client.put(f"/api/v1/hosts/{IP}/sla", json={"availability_target": 99})
    assert health(client)["sla"]["availability_met"] is False

    # The four failed checks sit at end-60 ... end-30 minutes.
    client.post(
        "/api/v1/maintenance",
        json=window_body(
            end - timedelta(minutes=55), end - timedelta(minutes=15), ip=IP, reason="swap"
        ),
    )
    body = health(client)

    assert (body["checks"], body["excluded"], body["down"]) == (4, 4, 0)
    assert body["availability_pct"] == 100.0
    assert body["outages"]["count"] == 0
    assert body["sla"]["availability_met"] is True and body["sla"]["violations"] == []
    assert [m["reason"] for m in body["maintenance"]] == ["swap"]


def test_a_window_for_another_host_changes_nothing(client, database):
    end = datetime.now().replace(microsecond=0) - timedelta(minutes=1)
    seed(database, "UUDDUU", end=end)
    before = health(client)
    client.post(
        "/api/v1/maintenance", json=window_body(end - timedelta(hours=2), end, ip="10.0.0.99")
    )

    after = health(client)

    assert after["availability_pct"] == before["availability_pct"] and after["maintenance"] == []


def test_an_every_host_window_applies_to_every_host(client, database):
    end = datetime.now().replace(microsecond=0) - timedelta(minutes=1)
    seed(database, "UD", end=end)
    seed(database, "UD", ip="10.0.0.6", end=end)
    client.post(
        "/api/v1/maintenance",
        json=window_body(end - timedelta(minutes=5), end + timedelta(minutes=5)),
    )

    for ip in (IP, "10.0.0.6"):
        body = health(client, ip=ip)
        assert body["excluded"] == 1 and body["down"] == 0


def test_a_window_outside_the_period_is_not_listed(client, database):
    seed(database, "UU")
    old = datetime.now() - timedelta(days=200)
    client.post("/api/v1/maintenance", json=window_body(old, old + timedelta(hours=1), ip=IP))
    future = datetime.now() + timedelta(days=5)
    client.post("/api/v1/maintenance", json=window_body(future, future + timedelta(hours=1), ip=IP))

    assert health(client)["maintenance"] == []


def test_an_outage_spanning_a_window_is_shortened_by_it(client, database):
    end = datetime.now().replace(microsecond=0) - timedelta(minutes=1)
    seed(database, "UDDDDDU", end=end)  # failing from end-50m, recovered at end
    plain = health(client)["outage_list"][0]["duration_s"]
    assert plain == 50 * 60

    client.post(
        "/api/v1/maintenance",
        json=window_body(end - timedelta(minutes=35), end - timedelta(minutes=15), ip=IP),
    )

    assert health(client)["outage_list"][0]["duration_s"] == 30 * 60


def test_deleting_a_window_brings_its_checks_back(client, database):
    end = datetime.now().replace(microsecond=0) - timedelta(minutes=1)
    seed(database, "UUDD", end=end)
    window = client.post(
        "/api/v1/maintenance",
        json=window_body(end - timedelta(minutes=15), end + timedelta(minutes=5), ip=IP),
    ).json()
    assert health(client)["excluded"] == 2

    client.delete(f"/api/v1/maintenance/{window['id']}")

    assert health(client)["excluded"] == 0


# ---------------------------------------------------------------- reports


def report(client, fmt, ip=IP, **params):
    return client.get(f"/api/v1/hosts/{ip}/availability/report", params={"fmt": fmt, **params})


def test_the_report_downloads_in_every_format(client, database):
    seed(database, "UUUDDUUUUU")
    client.put(f"/api/v1/hosts/{IP}/sla", json={"availability_target": 99})

    markdown, as_json, as_csv = report(client, "md"), report(client, "json"), report(client, "csv")

    for response, media in (
        (markdown, "text/markdown"),
        (as_json, "application/json"),
        (as_csv, "text/csv"),
    ):
        assert response.status_code == 200
        assert response.headers["content-type"].startswith(media)
        assert response.headers["content-disposition"].startswith("attachment; filename=")

    assert as_json.json() == health(client) | {"window": as_json.json()["window"]}
    assert "# Availability report: 10.0.0.5" in markdown.text
    assert "| Availability | 80.0% |" in markdown.text
    assert "## Outages" in markdown.text and "NOT met" in markdown.text
    assert "Observed from scans" in markdown.text
    rows = list(csv.reader(io.StringIO(as_csv.text)))
    assert ["Availability", "80.0%"] in rows and ["IP Address", IP] in rows


def test_the_default_format_is_markdown_and_an_unknown_one_is_a_400(client, database):
    seed(database, "U")
    assert (
        client.get(f"/api/v1/hosts/{IP}/availability/report")
        .headers["content-type"]
        .startswith("text/markdown")
    )
    bad = report(client, "pdf")
    assert bad.status_code == 400 and "md, json, csv" in bad.json()["detail"]


def test_the_report_of_an_unseen_host_is_a_404(client):
    assert report(client, "csv", ip="10.9.9.9").status_code == 404


def test_the_filename_names_the_host_and_the_period_and_is_safe_for_ipv6(client, database):
    seed(database, "U", ip="fe80::1")
    seed(database, "U")

    assert (
        'filename="ipmg_availability_10.0.0.5_7d.csv"'
        in report(client, "csv", days=7).headers["content-disposition"]
    )
    v6 = report(client, "json", ip="fe80::1", days=30).headers["content-disposition"]
    assert ":" not in v6.split("filename=")[1]


def test_the_report_follows_the_days_and_source_it_was_asked_for(client, database):
    seed(database, "UUUU", source="lab")
    seed(database, "DD", source="office", end=datetime.now() - timedelta(hours=3))

    body = report(client, "json", source="office", days=2).json()

    assert body["source"] == "office" and body["window"]["days"] == 2
    assert (body["checks"], body["availability_pct"]) == (2, 0.0)


def test_a_report_with_no_checks_and_no_outages_is_still_well_formed(client, database):
    seed(database, "U", end=datetime.now() - timedelta(days=90))

    md = report(client, "md", days=7).text
    as_csv = report(client, "csv", days=7).text

    assert (
        "No outages observed." in md
        and "No checks in this period." in md
        and "None in this period." in md
    )
    assert "| Availability | n/a |" in md and "n/a" in md
    assert list(csv.reader(io.StringIO(as_csv)))[0] == ["Metric", "Value"]


def test_text_from_users_cannot_become_a_spreadsheet_formula(client, database):
    seed(database, "UU")
    now = datetime.now()
    client.post(
        "/api/v1/maintenance",
        json=window_body(
            now - timedelta(hours=1),
            now + timedelta(hours=1),
            ip=IP,
            reason='=HYPERLINK("http://evil","x")',
        ),
    )
    client.post(
        "/api/v1/maintenance",
        json=window_body(
            now - timedelta(hours=1), now + timedelta(hours=1), ip=IP, reason="@SUM(1+1)"
        ),
    )

    cells = [cell for row in csv.reader(io.StringIO(report(client, "csv").text)) for cell in row]

    assert not any(cell.startswith(("=", "@", "+")) for cell in cells)
    assert any(cell.startswith("'=HYPERLINK") for cell in cells)
    assert any(cell.startswith("'@SUM") for cell in cells)


def test_pipes_and_newlines_in_a_reason_cannot_break_the_markdown_table(client, database):
    seed(database, "UU")
    now = datetime.now()
    client.post(
        "/api/v1/maintenance",
        json=window_body(
            now - timedelta(hours=1), now + timedelta(hours=1), ip=IP, reason="a | b\n## injected"
        ),
    )

    md = report(client, "md").text

    row = next(line for line in md.splitlines() if "injected" in line)
    assert row.startswith("| ") and row.count("|") - row.count("\\|") == 5
    assert "\n## injected" not in md


def test_the_report_matches_the_health_figures(client, database):
    seed(database, "UUDDUUUDUU")
    body = health(client)

    text = report(client, "md").text

    assert f"| Availability | {body['availability_pct']}% |" in text
    assert f"| Outages | {body['outages']['count']} (0 ongoing) |" in text


# --------------------------------------------------------------------- auth


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", f"/api/v1/hosts/{IP}/health"),
        ("get", f"/api/v1/hosts/{IP}/availability/report"),
        ("get", f"/api/v1/hosts/{IP}/sla"),
        ("put", f"/api/v1/hosts/{IP}/sla"),
        ("delete", f"/api/v1/hosts/{IP}/sla"),
        ("get", "/api/v1/maintenance"),
        ("post", "/api/v1/maintenance"),
        ("delete", "/api/v1/maintenance/1"),
    ],
)
def test_every_new_endpoint_needs_the_token(database, method, path):
    app = create_app(database, token="t")
    with TestClient(app) as anonymous:
        assert getattr(anonymous, method)(path).status_code == 401
        assert (
            getattr(anonymous, method)(path, headers={"Authorization": "Bearer wrong"}).status_code
            == 401
        )


def test_deleting_a_scan_removes_its_checks_from_the_figures(client, database):
    ids = seed(database, "UUDD")
    assert health(client)["checks"] == 4

    client.delete(f"/api/v1/scans/{ids[-1]}")

    assert health(client)["checks"] == 3
