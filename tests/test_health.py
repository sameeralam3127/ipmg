import pytest

from ipmg.core.engine import HostResult
from ipmg.core.health import HealthPolicy, check_health


def results(*statuses):
    return [HostResult(f"10.0.0.{index}", status, None) for index, status in enumerate(statuses, 1)]


def test_the_default_policy_never_fails():
    assert not HealthPolicy().enabled
    assert check_health(results("Timeout", "Unreachable"), HealthPolicy()) is None


def test_fail_on_down_passes_when_every_host_is_active():
    assert check_health(results("Active", "Active"), HealthPolicy(fail_on_down=True)) is None


def test_fail_on_down_names_the_hosts_that_are_down():
    failure = check_health(
        results("Active", "Timeout", "Error"), HealthPolicy(fail_on_down=True)
    )

    assert failure == "2 of 3 hosts are not active: 10.0.0.2, 10.0.0.3."


def test_fail_on_down_lists_hosts_in_address_order():
    down = [HostResult(ip, "Timeout", None) for ip in ("10.0.0.10", "not-an-ip", "10.0.0.9")]

    failure = check_health(down, HealthPolicy(fail_on_down=True))

    assert failure.endswith("10.0.0.9, 10.0.0.10, not-an-ip.")


def test_fail_on_down_summarises_a_long_list_of_hosts():
    failure = check_health(results(*["Timeout"] * 8), HealthPolicy(fail_on_down=True))

    assert failure.endswith("10.0.0.5 and 3 more.")


@pytest.mark.parametrize(
    "statuses, threshold, passes",
    [
        (("Active", "Active", "Active", "Timeout"), 75, True),
        (("Active", "Active", "Timeout", "Timeout"), 75, False),
        (("Timeout",), 0, True),
        (("Active",), 100, True),
        ((), 50, False),
    ],
)
def test_min_active_compares_the_active_share_with_the_threshold(statuses, threshold, passes):
    failure = check_health(results(*statuses), HealthPolicy(min_active_pct=threshold))

    assert (failure is None) is passes


def test_min_active_failure_states_the_share_and_the_threshold():
    failure = check_health(
        results("Active", "Timeout", "Timeout"), HealthPolicy(min_active_pct=50)
    )

    assert failure == "Only 33.3% of 3 hosts are active, below --min-active 50%."


def test_min_active_alone_tolerates_some_hosts_being_down():
    assert check_health(results("Active", "Timeout"), HealthPolicy(min_active_pct=50)) is None
