from ipmg.core.engine import HostResult
from ipmg.infrastructure.database import Database


def make_db(tmp_path):
    return Database(tmp_path / "history.db")


def test_add_results_bulk_updates_completed(tmp_path):
    db = make_db(tmp_path)
    scan_id = db.create_scan("manual", 2, {})

    stored = db.add_results(
        scan_id,
        [HostResult("10.0.0.1", "Active", 1.0), HostResult("10.0.0.2", "Timeout", None)],
    )

    assert stored == 2
    assert db.get_scan(scan_id)["completed"] == 2
    assert db.add_results(scan_id, []) == 0


def test_record_scan_writes_a_finished_scan(tmp_path):
    db = make_db(tmp_path)

    scan_id = db.record_scan(
        "targets.csv",
        [HostResult("10.0.0.1", "Active", 2.0, "gw")],
        {"threads": 8},
        duration_s=0.5,
    )

    scan = db.get_scan(scan_id)
    assert scan["status"] == "complete"
    assert scan["duration_s"] == 0.5
    assert scan["config"] == {"threads": 8}


def test_snapshot_returns_comparison_ready_hosts(tmp_path):
    db = make_db(tmp_path)
    scan_id = db.record_scan(
        "manual", [HostResult("10.0.0.1", "Active", 2.5, "gw")], {}, duration_s=1.0
    )

    snapshot = db.snapshot(scan_id)

    assert len(snapshot) == 1
    assert snapshot[0].ip == "10.0.0.1"
    assert snapshot[0].reachable is True
    assert snapshot[0].hostname == "gw"
    assert db.snapshot(999) == []


def test_previous_scan_id_skips_running_scans(tmp_path):
    db = make_db(tmp_path)
    first = db.record_scan("manual", [HostResult("10.0.0.1", "Active", 1.0)], {}, 1.0)
    running = db.create_scan("manual", 1, {})
    second = db.record_scan("manual", [HostResult("10.0.0.1", "Active", 1.0)], {}, 1.0)

    assert db.previous_scan_id(second) == first
    assert db.previous_scan_id(running) == first
    assert db.previous_scan_id(first) is None


def test_previous_and_latest_can_filter_by_source(tmp_path):
    db = make_db(tmp_path)
    csv_scan = db.record_scan("targets.csv", [HostResult("10.0.0.1", "Active", 1.0)], {}, 1.0)
    auto_scan = db.record_scan("auto-discovery", [HostResult("10.0.0.2", "Active", 1.0)], {}, 1.0)
    latest = db.record_scan("targets.csv", [HostResult("10.0.0.1", "Active", 1.0)], {}, 1.0)

    assert db.previous_scan_id(latest) == auto_scan
    assert db.previous_scan_id(latest, source="targets.csv") == csv_scan
    assert db.latest_scan_ids(limit=3) == [latest, auto_scan, csv_scan]
    assert db.latest_scan_ids(limit=2, source="targets.csv") == [latest, csv_scan]


def test_scan_ref_describes_the_scan(tmp_path):
    db = make_db(tmp_path)
    scan_id = db.record_scan("targets.csv", [HostResult("10.0.0.1", "Active", 1.0)], {}, 1.0)

    ref = db.scan_ref(scan_id)

    assert ref.id == scan_id
    assert ref.source == "targets.csv"
    assert ref.started_at
    assert db.scan_ref(999) is None


def test_result_search_treats_wildcards_literally(tmp_path):
    db = make_db(tmp_path)
    scan_id = db.create_scan("manual", 2, {})
    db.add_results(
        scan_id,
        [
            HostResult("10.0.0.1", "Active", 1.0, "web%prod"),
            HostResult("10.0.0.2", "Active", 1.0, "web-staging"),
        ],
    )

    assert [row["ip"] for row in db.get_results(scan_id, search="web%prod")] == ["10.0.0.1"]
    # A bare wildcard matches the literal '%' only, not every row.
    assert [row["ip"] for row in db.get_results(scan_id, search="%")] == ["10.0.0.1"]
    assert db.get_results(scan_id, search="_") == []
