import pytest

from ipmg.core.diff import ChangeType, DiffOptions
from ipmg.core.engine import HostResult, ScanConfig
from ipmg.exceptions import HistoryError
from ipmg.infrastructure.database import Database
from ipmg.services.history_service import HistoryService


@pytest.fixture()
def history(tmp_path):
    return HistoryService(Database(tmp_path / "history.db"))


def record(history, *results, source="targets.csv"):
    return history.record_scan(
        source=source,
        results=list(results),
        config=ScanConfig(threads=4),
        duration_s=1.25,
    )


def test_record_scan_stores_results_and_config(history):
    scan_id = record(history, HostResult("10.0.0.1", "Active", 3.0, "gw"))

    scan = history.database.get_scan(scan_id)
    assert scan["status"] == "complete"
    assert scan["total"] == 1
    assert scan["completed"] == 1
    assert scan["duration_s"] == 1.25
    assert scan["config"]["threads"] == 4
    assert history.database.snapshot(scan_id)[0].hostname == "gw"


def test_compare_two_stored_scans(history):
    first = record(history, HostResult("10.0.0.1", "Active", 3.0))
    second = record(
        history, HostResult("10.0.0.1", "Timeout", None), HostResult("10.0.0.2", "Active", 1.0)
    )

    diff = history.compare(first, second)

    assert diff.baseline.id == first
    assert diff.current.id == second
    assert {change.type for change in diff.changes} == {
        ChangeType.HOST_OFFLINE,
        ChangeType.NEW_HOST,
    }


def test_compare_with_previous_picks_the_scan_before(history):
    first = record(history, HostResult("10.0.0.1", "Active", 3.0))
    second = record(history, HostResult("10.0.0.1", "Active", 3.0))
    third = record(history, HostResult("10.0.0.1", "Inactive", None))

    diff = history.compare_with_previous(third)
    assert diff.baseline.id == second

    with pytest.raises(HistoryError, match="No earlier scan"):
        history.compare_with_previous(first)


def test_compare_with_previous_can_filter_by_source(history):
    first = record(history, HostResult("10.0.0.1", "Active", 3.0), source="targets.csv")
    record(history, HostResult("10.0.0.9", "Active", 3.0), source="auto-discovery")
    third = record(history, HostResult("10.0.0.1", "Timeout", None), source="targets.csv")

    diff = history.compare_with_previous(third, source="targets.csv")
    assert diff.baseline.id == first


def test_compare_latest_needs_two_scans(history):
    with pytest.raises(HistoryError, match="At least two"):
        history.compare_latest()

    record(history, HostResult("10.0.0.1", "Active", 3.0))
    with pytest.raises(HistoryError, match="At least two"):
        history.compare_latest()

    second = record(history, HostResult("10.0.0.1", "Active", 30.0))
    diff = history.compare_latest(options=DiffOptions(latency_abs_ms=1.0, latency_pct=10.0))

    assert diff.current.id == second
    assert diff.of_type(ChangeType.LATENCY_CHANGED)[0].delta == 27.0


def test_unknown_scan_id_is_reported(history):
    with pytest.raises(HistoryError, match="was not found"):
        history.compare(1, 2)


def test_list_scans_filters_by_source(history):
    record(history, HostResult("10.0.0.1", "Active", 1.0), source="targets.csv")
    record(history, HostResult("10.0.0.2", "Active", 1.0), source="auto-discovery")

    assert len(history.list_scans()) == 2
    assert [scan["source"] for scan in history.list_scans(source="auto-discovery")] == [
        "auto-discovery"
    ]


def test_open_uses_the_given_database_file(tmp_path):
    path = tmp_path / "nested" / "custom.db"
    service = HistoryService.open(str(path))

    assert path.exists()
    assert service.database.path == str(path)
