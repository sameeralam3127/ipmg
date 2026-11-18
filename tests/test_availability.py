"""The availability maths, on hand-written histories."""

import math
import random
from datetime import datetime, timedelta

import pytest

from ipmg.core.availability import (
    MaintenanceWindow,
    Sample,
    SlaTarget,
    TimeError,
    analyse,
    daily_breakdown,
    find_outages,
    format_local,
    in_maintenance,
    latency_stats,
    merge_windows,
    outage_summary,
    overlap_seconds,
    parse_local,
    percentile,
    sla_status,
    window_bounds,
)

T0 = datetime(2026, 11, 1, 0, 0, 0)


def at(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


def history(pattern: str, step_min: float = 10, latency: float | None = 5.0, start: float = 0):
    """``U`` is a reply, anything else a failed check; one check every ``step_min`` minutes."""
    return [
        Sample(
            at(start + index * step_min),
            "Active" if char == "U" else "Timeout",
            latency if char == "U" else None,
            index + 1,
        )
        for index, char in enumerate(pattern)
    ]


def window(start_min: float, end_min: float) -> MaintenanceWindow:
    return MaintenanceWindow(at(start_min), at(end_min))


# ---------------------------------------------------------------- parsing


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2026-11-18 02:00", datetime(2026, 11, 18, 2, 0)),
        ("2026-11-18 02:00:30", datetime(2026, 11, 18, 2, 0, 30)),
        ("2026-11-18T02:00", datetime(2026, 11, 18, 2, 0)),
        ("2026-11-18t02:00:30", datetime(2026, 11, 18, 2, 0, 30)),
        ("  2026-11-18 02:00  ", datetime(2026, 11, 18, 2, 0)),
        ("2026-11-18", datetime(2026, 11, 18, 0, 0)),
        ("2026-11-18 02:00:30.987654", datetime(2026, 11, 18, 2, 0, 30)),
        ("2028-02-29 23:59:59", datetime(2028, 2, 29, 23, 59, 59)),
    ],
)
def test_parse_local_reads_local_times(text, expected):
    assert parse_local(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "tomorrow",
        "2026-13-01 00:00",
        "2026-02-30 00:00",
        "2027-02-29 00:00",
        "2026-11-18 25:00",
        "2026-11-18 02:00Z",
        "2026-11-18 02:00z",
        "2026-11-18T02:00:00+05:30",
        "2026-11-18 02:00-08:00",
        "18/11/2026 02:00",
        "1700000000",
    ],
)
def test_parse_local_refuses_what_is_not_a_local_time(text):
    with pytest.raises(TimeError):
        parse_local(text)


def test_format_local_round_trips():
    moment = datetime(2026, 1, 2, 3, 4, 5)
    assert format_local(moment) == "2026-01-02 03:04:05"
    assert parse_local(format_local(moment)) == moment


def test_window_bounds_look_back_whole_days_and_drop_microseconds():
    start, end = window_bounds(7, datetime(2026, 11, 8, 12, 0, 0, 999999))
    assert end == datetime(2026, 11, 8, 12, 0, 0)
    assert start == datetime(2026, 11, 1, 12, 0, 0)


# ------------------------------------------------------------ percentiles


def test_percentile_of_nothing_is_none():
    assert percentile([], 0.5) is None


def test_percentile_of_one_value_is_that_value():
    assert [percentile([7.0], q) for q in (0, 0.5, 0.95, 1)] == [7.0] * 4


def test_percentile_interpolates_linearly():
    values = [1, 2, 3, 4]
    assert percentile(values, 0) == 1
    assert percentile(values, 0.5) == 2.5
    assert percentile(values, 1) == 4
    assert percentile(values, 0.95) == pytest.approx(3.85)
    assert percentile(values, 0.99) == pytest.approx(3.97)


def test_percentile_does_not_need_sorted_input_or_change_it():
    values = [9, 1, 5, 3]
    assert percentile(values, 0.5) == 4
    assert values == [9, 1, 5, 3]


def test_percentile_of_a_hundred_values_lands_on_known_ranks():
    values = list(range(1, 101))
    assert percentile(values, 0.50) == pytest.approx(50.5)
    assert percentile(values, 0.95) == pytest.approx(95.05)
    assert percentile(values, 0.99) == pytest.approx(99.01)


@pytest.mark.parametrize("fraction", [-0.01, 1.01, 2, -1])
def test_percentile_rejects_a_fraction_outside_zero_to_one(fraction):
    with pytest.raises(ValueError, match="between 0 and 1"):
        percentile([1, 2], fraction)


def test_percentiles_are_ordered_and_bounded_for_random_data():
    rng = random.Random(1)
    for _ in range(200):
        values = [rng.uniform(0, 500) for _ in range(rng.randint(1, 60))]
        stats = latency_stats(values)
        assert stats["min"] <= stats["p50"] <= stats["p95"] <= stats["p99"] <= stats["max"]
        assert stats["count"] == len(values)


def test_latency_stats_ignores_missing_and_non_finite_values():
    stats = latency_stats([10, None, 20, float("nan"), float("inf"), 30])
    assert stats == {
        "count": 3,
        "min": 10,
        "mean": 20,
        "p50": 20,
        "p95": 29,
        "p99": 29.8,
        "max": 30,
    }


def test_latency_stats_with_nothing_to_measure_are_all_none():
    for empty in ([], [None, None], [float("nan")]):
        stats = latency_stats(empty)
        assert stats["count"] == 0
        assert all(stats[key] is None for key in ("min", "mean", "p50", "p95", "p99", "max"))


def test_latency_stats_of_identical_values_are_that_value():
    stats = latency_stats([4.2] * 50)
    assert (stats["p50"], stats["p95"], stats["p99"], stats["mean"]) == (4.2, 4.2, 4.2, 4.2)


def test_latency_stats_of_zero_latency_is_not_treated_as_missing():
    assert latency_stats([0.0, 0.0])["count"] == 2


# ------------------------------------------------------------ maintenance


def test_a_window_includes_its_start_and_excludes_its_end():
    w = window(60, 120)
    assert not w.covers(at(59.99))
    assert w.covers(at(60))
    assert w.covers(at(119.99))
    assert not w.covers(at(120))
    assert in_maintenance(at(90), [window(0, 10), w])
    assert not in_maintenance(at(90), [])


def test_merge_windows_joins_overlapping_and_touching_ones():
    merged = merge_windows([window(50, 70), window(0, 10), window(5, 20), window(20, 30)])
    assert merged == [window(0, 30), window(50, 70)]


def test_merge_windows_keeps_a_nested_window_inside_its_parent():
    assert merge_windows([window(0, 100), window(10, 20)]) == [window(0, 100)]


def test_merge_windows_drops_empty_and_inverted_windows():
    assert merge_windows([window(10, 10), window(30, 20)]) == []
    assert merge_windows([]) == []


def test_overlap_seconds_counts_only_the_part_inside_windows():
    windows = merge_windows([window(10, 20), window(40, 50)])
    assert overlap_seconds(at(0), at(100), windows) == 20 * 60
    assert overlap_seconds(at(15), at(45), windows) == (5 + 5) * 60
    assert overlap_seconds(at(20), at(40), windows) == 0
    assert overlap_seconds(at(5), at(5), windows) == 0
    assert overlap_seconds(at(50), at(10), windows) == 0
    assert overlap_seconds(at(0), at(100), []) == 0


# ---------------------------------------------------------------- outages


def test_no_checks_and_all_up_have_no_outages():
    assert find_outages([]) == []
    assert find_outages(history("UUUU")) == []


def test_one_outage_runs_from_the_first_failed_check_to_the_recovery():
    (outage,) = find_outages(history("UUDDDUU"))
    assert outage.started_at == at(20)
    assert outage.ended_at == at(50)
    assert outage.duration_s == 30 * 60
    assert outage.checks == 3
    assert not outage.ongoing


def test_an_outage_still_failing_at_the_last_check_is_ongoing():
    (outage,) = find_outages(history("UUDDD"))
    assert outage.ongoing and outage.ended_at is None
    assert outage.started_at == at(20)
    assert outage.duration_s == 20 * 60
    assert outage.checks == 3


def test_a_single_failed_last_check_is_an_ongoing_outage_of_no_length():
    (outage,) = find_outages(history("UUD"))
    assert outage.ongoing and outage.duration_s == 0 and outage.checks == 1


def test_a_history_of_one_failed_check_is_one_ongoing_outage():
    (outage,) = find_outages(history("D"))
    assert (outage.ongoing, outage.duration_s, outage.checks) == (True, 0, 1)


def test_flapping_makes_one_outage_per_run():
    outages = find_outages(history("UDUDUDU"))
    assert len(outages) == 3
    assert [o.duration_s for o in outages] == [600, 600, 600]


def test_every_non_reachable_status_is_a_failure():
    statuses = ["Active", "Inactive", "Timeout", "Error", "Unreachable", "Unresolvable", "Active"]
    samples = [Sample(at(i), status) for i, status in enumerate(statuses)]
    (outage,) = find_outages(samples)
    assert outage.checks == 5


def test_maintenance_inside_an_outage_is_taken_off_its_length():
    # Down from minute 20, recovered at 80; maintenance covers 30-50.
    samples = history("UUDDDDDDU", step_min=10)
    (outage,) = find_outages(samples, merge_windows([window(30, 50)]))
    assert outage.started_at == at(20) and outage.ended_at == at(80)
    assert outage.duration_s == (60 - 20) * 60


def test_maintenance_longer_than_the_outage_cannot_make_it_negative():
    (outage,) = find_outages(history("UDDU"), merge_windows([window(0, 1000)]))
    assert outage.duration_s == 0


def test_outage_to_dict_formats_times():
    (outage,) = find_outages(history("UDU"))
    assert outage.to_dict() == {
        "started_at": "2026-11-01 00:10:00",
        "ended_at": "2026-11-01 00:20:00",
        "duration_s": 600.0,
        "checks": 1,
        "ongoing": False,
    }


def test_summary_of_a_history_without_outages_has_no_mttr_or_mtbf():
    samples = history("UUUU")
    summary = outage_summary(find_outages(samples), samples)
    assert summary == {
        "count": 0, "recovered": 0, "ongoing": 0, "downtime_s": 0, "longest_s": 0,
        "mttr_s": None, "mtbf_s": None,
    }  # fmt: skip


def test_mttr_and_mtbf_for_a_worked_example():
    # 10-minute checks over 100 minutes. Down 20-40 (20 min) and 60-70 (10 min).
    samples = history("UUDDUUDUUUU")
    summary = outage_summary(find_outages(samples), samples)
    assert summary["count"] == 2 and summary["recovered"] == 2
    assert summary["downtime_s"] == 30 * 60
    assert summary["longest_s"] == 20 * 60
    assert summary["mttr_s"] == 15 * 60
    # Span 100 min, minus 30 min down, over two outages.
    assert summary["mtbf_s"] == 35 * 60


def test_an_ongoing_outage_counts_for_mtbf_but_not_mttr():
    samples = history("UUUUDD")  # down at 40, last check at 50
    summary = outage_summary(find_outages(samples), samples)
    assert (summary["count"], summary["recovered"], summary["ongoing"]) == (1, 0, 1)
    assert summary["mttr_s"] is None
    assert summary["downtime_s"] == 10 * 60
    assert summary["mtbf_s"] == (50 - 10) * 60


def test_mtbf_is_never_negative_when_downtime_fills_the_span():
    samples = history("DD")
    summary = outage_summary(find_outages(samples), samples)
    assert summary["mtbf_s"] == 0


def test_mtbf_leaves_out_maintenance_time():
    samples = history("UUUUUUUUUUDU")  # 110 min span, one 10 min outage
    windows = merge_windows([window(20, 40)])
    summary = outage_summary(find_outages(samples, windows), samples, windows)
    assert summary["mtbf_s"] == (110 - 20 - 10) * 60


# -------------------------------------------------------------------- SLA


@pytest.mark.parametrize(
    ("up", "checks", "target", "met"),
    [
        (999, 1000, 99.9, True),  # exactly on target; a float comparison gets this wrong
        (998, 1000, 99.9, False),
        (1000, 1000, 100, True),
        (999, 1000, 100, False),
        (1, 3, 33.3, True),
        (1, 3, 33.4, False),
        (0, 5, 0.1, False),
        (95, 100, 95, True),
        (94, 100, 95, False),
        (9995, 10000, 99.95, True),
        (9994, 10000, 99.95, False),
    ],
)
def test_availability_target_is_compared_exactly(up, checks, target, met):
    status = sla_status(SlaTarget(target), up, checks, None, [])
    assert status["availability_met"] is met


def test_sla_with_no_checks_is_neither_met_nor_missed():
    status = sla_status(SlaTarget(99.9, 50), 0, 0, None, [])
    assert status["availability_met"] is None
    assert status["latency_met"] is None
    assert status["violations"] == []


def test_sla_violations_are_the_days_that_missed_the_target():
    days = [
        {
            "date": "2026-11-01",
            "checks": 100,
            "up": 100,
            "availability_pct": 100.0,
            "latency_p95": 5,
        },
        {"date": "2026-11-02", "checks": 100, "up": 98, "availability_pct": 98.0, "latency_p95": 5},
        {
            "date": "2026-11-03",
            "checks": 10,
            "up": 10,
            "availability_pct": 100.0,
            "latency_p95": 80,
        },
    ]
    status = sla_status(SlaTarget(99.0, 50.0), 208, 210, 80, days)
    assert [(v["date"], v["kind"], v["observed"], v["target"]) for v in status["violations"]] == [
        ("2026-11-02", "availability", 98.0, 99.0),
        ("2026-11-03", "latency", 80, 50.0),
    ]
    # 208 of 210 is 99.05%: the window meets 99% overall though one day did not.
    assert status["availability_met"] is True
    assert status["latency_met"] is False


def test_latency_limit_is_optional_and_inclusive():
    day = [{"date": "d", "checks": 1, "up": 1, "availability_pct": 100.0, "latency_p95": 50.0}]
    assert sla_status(SlaTarget(99), 1, 1, 50.0, day)["violations"] == []
    assert sla_status(SlaTarget(99, 50.0), 1, 1, 50.0, day)["latency_met"] is True
    assert sla_status(SlaTarget(99, 49.9), 1, 1, 50.0, day)["latency_met"] is False


def test_a_day_without_replies_cannot_break_the_latency_limit():
    day = [{"date": "d", "checks": 4, "up": 0, "availability_pct": 0.0, "latency_p95": None}]
    kinds = [v["kind"] for v in sla_status(SlaTarget(50, 10), 0, 4, None, day)["violations"]]
    assert kinds == ["availability"]


def test_daily_breakdown_splits_at_local_midnight():
    samples = [
        Sample(datetime(2026, 11, 1, 23, 59, 59), "Active", 5.0),
        Sample(datetime(2026, 11, 2, 0, 0, 0), "Timeout"),
        Sample(datetime(2026, 11, 2, 0, 30, 0), "Active", 7.0),
    ]
    first, second = daily_breakdown(samples)
    assert first == {
        "date": "2026-11-01",
        "checks": 1,
        "up": 1,
        "availability_pct": 100.0,
        "latency_p95": 5.0,
    }
    assert (second["date"], second["checks"], second["up"]) == ("2026-11-02", 2, 1)
    assert second["availability_pct"] == 50.0 and second["latency_p95"] == 7.0


def test_days_without_checks_are_left_out_of_the_breakdown():
    samples = [
        Sample(datetime(2026, 11, 1, 1), "Active"),
        Sample(datetime(2026, 11, 5, 1), "Active"),
    ]
    assert [d["date"] for d in daily_breakdown(samples)] == ["2026-11-01", "2026-11-05"]
    assert daily_breakdown([]) == []


# ---------------------------------------------------------------- analyse


def test_analysing_nothing_divides_by_nothing():
    report = analyse([])
    assert report["checks"] == report["up"] == report["down"] == report["excluded"] == 0
    assert report["availability_pct"] is None
    assert report["latency"]["p95"] is None
    assert report["outages"]["count"] == 0 and report["outages"]["mtbf_s"] is None
    assert report["outage_list"] == [] and report["daily"] == [] and report["sla"] is None


def test_a_single_reply_is_fully_available():
    report = analyse(history("U", latency=3.0))
    assert (report["checks"], report["availability_pct"]) == (1, 100.0)
    assert report["latency"]["p50"] == report["latency"]["p99"] == 3.0


def test_a_single_failure_is_zero_available_and_ongoing():
    report = analyse(history("D"))
    assert report["availability_pct"] == 0.0
    assert report["outages"]["ongoing"] == 1 and report["outages"]["mttr_s"] is None
    assert report["latency"]["count"] == 0


def test_availability_is_reachable_checks_over_all_checks():
    report = analyse(history("UUUDUUUUUD"))
    assert (report["up"], report["down"], report["checks"]) == (8, 2, 10)
    assert report["availability_pct"] == 80.0


def test_availability_keeps_four_decimals():
    report = analyse(history("U" * 2 + "D"))
    assert report["availability_pct"] == 66.6667


def test_a_reply_without_a_latency_counts_as_up_but_not_in_the_percentiles():
    samples = [Sample(at(0), "Active", None), Sample(at(1), "Active", 10.0)]
    report = analyse(samples)
    assert report["up"] == 2 and report["latency"]["count"] == 1


def test_only_replies_feed_the_latency_percentiles():
    samples = [Sample(at(0), "Active", 10.0), Sample(at(1), "Timeout", 9999.0)]
    assert analyse(samples)["latency"]["max"] == 10.0


def test_checks_are_analysed_in_time_order_whatever_order_they_arrive_in():
    samples = history("UUDDUU")
    shuffled = random.Random(3).sample(samples, len(samples))
    assert analyse(shuffled) == analyse(samples)


def test_window_edges_include_both_ends():
    samples = history("UUUUU")  # minutes 0..40
    report = analyse(samples, starts_at=at(10), ends_at=at(30))
    assert report["checks"] == 3
    assert analyse(samples, starts_at=at(10.01), ends_at=at(29.99))["checks"] == 1
    assert analyse(samples, starts_at=at(100), ends_at=at(200))["checks"] == 0


def test_checks_in_maintenance_are_neither_up_nor_down():
    samples = history("UUDDDUUU")  # down at 20, 30, 40
    report = analyse(samples, [window(20, 41)])
    assert (report["checks"], report["excluded"], report["down"]) == (5, 3, 0)
    assert report["availability_pct"] == 100.0
    assert report["outages"]["count"] == 0


def test_a_window_end_is_the_first_moment_counted_again():
    samples = history("UDDUU")  # checks at 0, 10, 20, 30, 40
    report = analyse(samples, [window(10, 20)])
    assert (report["excluded"], report["down"]) == (1, 1)  # the check at 20 counts


def test_a_window_start_is_excluded_from_the_first_moment():
    report = analyse(history("UDU"), [window(10, 11)])
    assert report["excluded"] == 1 and report["down"] == 0


def test_a_failure_before_maintenance_and_recovery_after_is_one_shortened_outage():
    samples = history("UDDDDDU")  # failing 10..50, recovered at 60
    report = analyse(samples, [window(25, 45)])
    outage = report["outage_list"][0]
    assert report["outages"]["count"] == 1
    assert outage["duration_s"] == (50 - 20) * 60


def test_overlapping_maintenance_is_not_counted_twice():
    samples = history("UDDDDDU")
    once = analyse(samples, [window(25, 45)])
    twice = analyse(samples, [window(25, 45), window(30, 40), window(25, 45)])
    assert once["outage_list"] == twice["outage_list"]
    assert once["outages"]["mtbf_s"] == twice["outages"]["mtbf_s"]


def test_outage_list_is_newest_first():
    report = analyse(history("UDUUDDU"))
    assert [o["started_at"] for o in report["outage_list"]] == [
        "2026-11-01 00:40:00",
        "2026-11-01 00:10:00",
    ]


def test_duplicate_timestamps_are_ordered_by_scan_id():
    samples = [
        Sample(at(0), "Timeout", None, 2),
        Sample(at(0), "Active", 5.0, 1),
        Sample(at(10), "Active", 5.0, 3),
    ]
    (outage,) = analyse(samples)["outage_list"]
    # Read in input order the failure would start after the reply and never recover.
    assert outage["started_at"] == "2026-11-01 00:00:00" and not outage["ongoing"]
    assert outage["ended_at"] == "2026-11-01 00:10:00" and outage["duration_s"] == 600


def test_analyse_attaches_sla_status_only_when_there_is_a_target():
    samples = history("UUUUUUUUUD")
    assert analyse(samples)["sla"] is None
    sla = analyse(samples, sla=SlaTarget(95))["sla"]
    assert sla["availability_met"] is False
    assert [v["kind"] for v in sla["violations"]] == ["availability"]
    assert analyse(samples, sla=SlaTarget(90))["sla"]["availability_met"] is True


def test_maintenance_can_rescue_an_sla_day():
    samples = history("UUUUDUUUU")
    assert analyse(samples, sla=SlaTarget(99))["sla"]["violations"]
    assert analyse(samples, [window(35, 45)], sla=SlaTarget(99))["sla"]["violations"] == []


def test_one_hundred_percent_target_tolerates_no_failure_at_all():
    assert analyse(history("U" * 50), sla=SlaTarget(100))["sla"]["availability_met"] is True
    assert analyse(history("U" * 49 + "D"), sla=SlaTarget(100))["sla"]["availability_met"] is False


# ---------------------------------------------- checked against a simple model


def reference(pattern: str, step_min: int, maintenance: list[tuple[int, int]]):
    """The same figures by plain loops, sharing no code with the module."""
    kept = []
    for index, char in enumerate(pattern):
        minute = index * step_min
        if any(start <= minute < end for start, end in maintenance):
            continue
        kept.append((minute, char == "U"))
    up = sum(1 for _, ok in kept if ok)
    runs, current = [], None
    for minute, ok in kept:
        if not ok and current is None:
            current = minute
        elif ok and current is not None:
            runs.append((current, minute))
            current = None
    ongoing = current is not None
    return len(kept), up, len(runs) + (1 if ongoing else 0), ongoing


def test_random_histories_agree_with_a_plain_reference():
    rng = random.Random(2026)
    for _ in range(400):
        pattern = "".join(rng.choice("UUUD") for _ in range(rng.randint(0, 40)))
        step = rng.choice([1, 5, 15])
        windows = [
            (a := rng.randint(0, 300), a + rng.randint(1, 60)) for _ in range(rng.randint(0, 3))
        ]
        report = analyse(history(pattern, step_min=step), [window(a, b) for a, b in windows])
        checks, up, outages, ongoing = reference(pattern, step, windows)
        assert report["checks"] == checks
        assert report["up"] == up
        assert report["outages"]["count"] == outages
        assert report["outages"]["ongoing"] == (1 if ongoing else 0)
        assert report["availability_pct"] == (round(up * 100 / checks, 4) if checks else None)
        assert report["outages"]["downtime_s"] >= 0
        assert report["outages"]["mtbf_s"] is None or report["outages"]["mtbf_s"] >= 0
        for key in ("mttr_s", "mtbf_s", "longest_s"):
            value = report["outages"][key]
            assert value is None or math.isfinite(value)


# ----------------------------------------- limits compare unrounded latencies


def test_a_p95_that_only_rounds_to_the_limit_still_breaks_it():
    samples = [Sample(at(i), "Active", 10.004) for i in range(5)]
    report = analyse(samples, sla=SlaTarget(99, 10.0))
    assert report["latency"]["p95"] == 10.0  # displayed rounded
    assert report["sla"]["latency_met"] is False
    assert [v["kind"] for v in report["sla"]["violations"]] == ["latency"]
    assert report["sla"]["violations"][0]["observed"] == 10.0


def test_a_latency_exactly_on_the_limit_stays_compliant():
    samples = [Sample(at(i), "Active", 10.0) for i in range(5)]
    sla = analyse(samples, sla=SlaTarget(99, 10.0))["sla"]
    assert sla["latency_met"] is True and sla["violations"] == []


def test_the_overall_and_daily_verdicts_use_the_same_unrounded_figure():
    day_one = [Sample(datetime(2026, 11, 1, 1, i), "Active", 9.996) for i in range(5)]
    day_two = [Sample(datetime(2026, 11, 2, 1, i), "Active", 10.004) for i in range(5)]
    sla = analyse(day_one + day_two, sla=SlaTarget(99, 10.0))["sla"]
    assert [v["date"] for v in sla["violations"]] == ["2026-11-02"]
