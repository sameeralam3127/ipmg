from ipmg.core.diff import (
    ChangeType,
    DiffOptions,
    HostSnapshot,
    ScanRef,
    Severity,
    compare_snapshots,
)


def snap(ip, status="Active", latency=1.0, hostname=""):
    return HostSnapshot(ip=ip, status=status, latency=latency, hostname=hostname)


def types(diff):
    return {change.type for change in diff.changes}


def only(diff, change_type):
    matches = diff.of_type(change_type)
    assert len(matches) == 1, f"expected exactly one {change_type}, got {matches}"
    return matches[0]


def test_detects_new_and_removed_hosts():
    diff = compare_snapshots([snap("10.0.0.1")], [snap("10.0.0.1"), snap("10.0.0.2")])

    assert only(diff, ChangeType.NEW_HOST).ip == "10.0.0.2"
    assert diff.baseline_hosts == 1
    assert diff.current_hosts == 2
    assert diff.compared_hosts == 1

    reverse = compare_snapshots([snap("10.0.0.1"), snap("10.0.0.2")], [snap("10.0.0.1")])
    assert only(reverse, ChangeType.HOST_REMOVED).ip == "10.0.0.2"


def test_detects_offline_and_recovered_hosts():
    diff = compare_snapshots(
        [snap("10.0.0.1"), snap("10.0.0.2", status="Timeout", latency=None)],
        [snap("10.0.0.1", status="Timeout", latency=None), snap("10.0.0.2")],
    )

    offline = only(diff, ChangeType.HOST_OFFLINE)
    assert (offline.ip, offline.previous, offline.current) == ("10.0.0.1", "Active", "Timeout")
    assert offline.severity is Severity.CRITICAL

    assert only(diff, ChangeType.HOST_ONLINE).ip == "10.0.0.2"


def test_status_change_between_unreachable_states_is_a_service_change():
    diff = compare_snapshots(
        [snap("10.0.0.1", status="Timeout", latency=None)],
        [snap("10.0.0.1", status="Unreachable", latency=None)],
    )

    change = only(diff, ChangeType.SERVICE_CHANGED)
    assert (change.previous, change.current) == ("Timeout", "Unreachable")
    assert ChangeType.HOST_OFFLINE not in types(diff)


def test_detects_hostname_change_but_ignores_first_resolution():
    diff = compare_snapshots(
        [snap("10.0.0.1", hostname="old.local"), snap("10.0.0.2")],
        [snap("10.0.0.1", hostname="new.local"), snap("10.0.0.2", hostname="fresh.local")],
    )

    change = only(diff, ChangeType.HOSTNAME_CHANGED)
    assert (change.ip, change.previous, change.current) == ("10.0.0.1", "old.local", "new.local")


def test_first_hostname_resolution_reported_when_requested():
    diff = compare_snapshots(
        [snap("10.0.0.2")],
        [snap("10.0.0.2", hostname="fresh.local")],
        options=DiffOptions(include_unresolved_hostnames=True),
    )

    change = only(diff, ChangeType.HOSTNAME_CHANGED)
    assert (change.previous, change.current) == ("(none)", "fresh.local")


def test_hostname_moving_to_another_ip_is_an_ip_change():
    diff = compare_snapshots(
        [snap("10.0.0.1", hostname="printer.local")],
        [snap("10.0.0.9", hostname="printer.local")],
    )

    change = only(diff, ChangeType.IP_CHANGED)
    assert (change.previous, change.current) == ("10.0.0.1", "10.0.0.9")
    # The move replaces the new-host/removed-host pair rather than duplicating it.
    assert types(diff) == {ChangeType.IP_CHANGED}


def test_latency_change_requires_both_thresholds():
    options = DiffOptions(latency_abs_ms=5.0, latency_pct=25.0)

    # +4 ms is above 25% but below the 5 ms floor.
    quiet = compare_snapshots(
        [snap("10.0.0.1", latency=10.0)], [snap("10.0.0.1", latency=14.0)], options=options
    )
    assert not quiet.has_changes

    # +6 ms on a 200 ms link is only 3%.
    also_quiet = compare_snapshots(
        [snap("10.0.0.1", latency=200.0)], [snap("10.0.0.1", latency=206.0)], options=options
    )
    assert not also_quiet.has_changes

    loud = compare_snapshots(
        [snap("10.0.0.1", latency=10.0)], [snap("10.0.0.1", latency=40.0)], options=options
    )
    change = only(loud, ChangeType.LATENCY_CHANGED)
    assert change.delta == 30.0
    assert change.severity is Severity.INFO


def test_latency_ignored_when_host_is_not_reachable():
    diff = compare_snapshots(
        [snap("10.0.0.1", latency=10.0)],
        [snap("10.0.0.1", status="Timeout", latency=999.0)],
    )

    assert types(diff) == {ChangeType.HOST_OFFLINE}


def test_identical_scans_produce_no_changes():
    hosts = [snap("10.0.0.1", hostname="a.local"), snap("10.0.0.2", status="Timeout", latency=None)]
    diff = compare_snapshots(hosts, list(hosts))

    assert not diff.has_changes
    assert diff.unchanged_hosts == 2


def test_changes_are_sorted_by_severity():
    diff = compare_snapshots(
        [snap("10.0.0.1"), snap("10.0.0.5", latency=10.0)],
        [
            snap("10.0.0.1", status="Timeout", latency=None),
            snap("10.0.0.5", latency=90.0),
            snap("10.0.0.7"),
        ],
    )

    severities = [change.severity for change in diff.changes]
    assert severities == sorted(
        severities, key=lambda s: ["critical", "warning", "info"].index(s.value)
    )


def test_duplicate_ips_use_the_latest_observation():
    diff = compare_snapshots(
        [snap("10.0.0.1")],
        [snap("10.0.0.1"), snap("10.0.0.1", status="Timeout", latency=None)],
    )

    assert only(diff, ChangeType.HOST_OFFLINE).ip == "10.0.0.1"


def test_to_dict_is_json_ready():
    diff = compare_snapshots(
        [snap("10.0.0.1")],
        [snap("10.0.0.1", status="Timeout", latency=None), snap("10.0.0.2")],
        baseline_ref=ScanRef(id=1, started_at="2026-07-26 10:00:00", source="targets.csv"),
        current_ref=ScanRef(id=2, started_at="2026-07-26 11:00:00", source="targets.csv"),
    )
    payload = diff.to_dict()

    assert payload["baseline"]["id"] == 1
    assert payload["current"]["id"] == 2
    assert payload["summary"]["total_changes"] == 2
    assert payload["summary"]["counts"]["host_offline"] == 1
    assert payload["summary"]["severity_counts"]["critical"] == 1
    assert payload["changes"][0]["description"] == "Host offline: Active -> Timeout"


def test_empty_scans_compare_cleanly():
    diff = compare_snapshots([], [])

    assert not diff.has_changes
    assert diff.unchanged_hosts == 0
    assert diff.counts == {}
