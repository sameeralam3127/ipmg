import sqlite3

from ipmg.core.engine import HostResult
from ipmg.web.db import Database  # backwards-compatible alias


def make_db(tmp_path):
    return Database(tmp_path / "test.db")


def test_scan_lifecycle(tmp_path):
    db = make_db(tmp_path)

    scan_id = db.create_scan("manual", 2, {"threads": 4})
    db.add_result(scan_id, HostResult("10.0.0.1", "Active", 4.2, "router"))
    db.add_result(scan_id, HostResult("10.0.0.2", "Timeout", None))
    db.finish_scan(scan_id, "complete", 1.5)

    scan = db.get_scan(scan_id)
    assert scan["status"] == "complete"
    assert scan["completed"] == 2
    assert scan["config"] == {"threads": 4}
    assert scan["status_counts"] == {"Active": 1, "Timeout": 1}
    assert scan["avg_latency"] == 4.2
    assert scan["duration_s"] == 1.5


def test_results_filtering(tmp_path):
    db = make_db(tmp_path)
    scan_id = db.create_scan("manual", 3, {})
    db.add_result(scan_id, HostResult("10.0.0.1", "Active", 1.0, "alpha"))
    db.add_result(scan_id, HostResult("10.0.0.2", "Inactive", None, "beta"))
    db.add_result(scan_id, HostResult("10.0.0.3", "Active", 2.0, "gamma"))

    assert len(db.get_results(scan_id)) == 3
    assert len(db.get_results(scan_id, status="Active")) == 2
    assert [row["ip"] for row in db.get_results(scan_id, search="beta")] == ["10.0.0.2"]
    assert [row["ip"] for row in db.get_results(scan_id, search="0.3")] == ["10.0.0.3"]


def test_open_ports_round_trip_through_storage(tmp_path):
    db = make_db(tmp_path)
    scan_id = db.create_scan("manual", 1, {})
    db.add_result(
        scan_id, HostResult("10.0.0.1", "Active", 1.0, "router", open_ports=(22, 80, 443))
    )

    results = db.get_results(scan_id)
    assert results[0]["open_ports"] == "22,80,443"


def test_open_ports_defaults_to_empty_string(tmp_path):
    db = make_db(tmp_path)
    scan_id = db.create_scan("manual", 1, {})
    db.add_result(scan_id, HostResult("10.0.0.1", "Timeout", None))

    results = db.get_results(scan_id)
    assert results[0]["open_ports"] == ""


def test_opening_a_pre_existing_database_adds_open_ports_column(tmp_path):
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            duration_s REAL,
            source TEXT NOT NULL,
            total INTEGER NOT NULL DEFAULT 0,
            completed INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'running',
            config TEXT NOT NULL DEFAULT '{}',
            error TEXT
        );
        CREATE TABLE results (
            scan_id INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
            ip TEXT NOT NULL,
            status TEXT NOT NULL,
            latency REAL,
            hostname TEXT NOT NULL DEFAULT '',
            checked_at TEXT NOT NULL
        );
        """
    )
    conn.commit()
    conn.close()

    db = Database(path)
    scan_id = db.create_scan("manual", 1, {})
    db.add_result(scan_id, HostResult("10.0.0.1", "Active", 1.0, open_ports=(22,)))

    assert db.get_results(scan_id)[0]["open_ports"] == "22"


def test_delete_scan_cascades(tmp_path):
    db = make_db(tmp_path)
    scan_id = db.create_scan("manual", 1, {})
    db.add_result(scan_id, HostResult("10.0.0.1", "Active", 1.0))

    assert db.delete_scan(scan_id) is True
    assert db.get_scan(scan_id) is None
    assert db.get_results(scan_id) == []
    assert db.delete_scan(scan_id) is False


def test_overview_and_inventory(tmp_path):
    db = make_db(tmp_path)

    first = db.create_scan("manual", 2, {})
    db.add_result(first, HostResult("10.0.0.2", "Active", 3.0, "old-name"))
    db.add_result(first, HostResult("10.0.0.10", "Inactive", None))
    db.finish_scan(first, "complete", 1.0)

    second = db.create_scan("manual", 2, {})
    db.add_result(second, HostResult("10.0.0.2", "Inactive", None))
    db.add_result(second, HostResult("10.0.0.10", "Active", 8.0, "new-name"))
    db.finish_scan(second, "complete", 2.0)

    overview = db.overview()
    assert overview["scan_count"] == 2
    assert overview["host_count"] == 2
    assert overview["latest_scan"]["id"] == second
    assert len(overview["trend"]) == 2
    assert overview["running_scans"] == []

    inventory = db.inventory()
    # numeric IP ordering, not lexicographic
    assert [row["ip"] for row in inventory] == ["10.0.0.2", "10.0.0.10"]
    by_ip = {row["ip"]: row for row in inventory}
    assert by_ip["10.0.0.2"]["status"] == "Inactive"
    assert by_ip["10.0.0.2"]["hostname"] == "old-name"
    assert by_ip["10.0.0.10"]["status"] == "Active"
    assert by_ip["10.0.0.10"]["hostname"] == "new-name"
    assert by_ip["10.0.0.10"]["scan_count"] == 2
