import threading
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from ipmg.core.cron import next_interval_run, parse_cron
from ipmg.web.app import create_app
from ipmg.web.db import Database
from ipmg.web.manager import ScanManager
from ipmg.web.scheduler import Scheduler, next_run, schedule_source

AT = datetime(2026, 10, 17, 12, 7, 30)  # a Saturday


# --------------------------------------------------------------------- cron


@pytest.mark.parametrize(
    "expression, after, expected",
    [
        ("*/15 * * * *", AT, datetime(2026, 10, 17, 12, 15)),
        ("0 * * * *", AT, datetime(2026, 10, 17, 13, 0)),
        ("30 2 * * *", AT, datetime(2026, 10, 18, 2, 30)),
        ("0 9 * * mon-fri", AT, datetime(2026, 10, 19, 9, 0)),
        ("0 9 * * 1-5", AT, datetime(2026, 10, 19, 9, 0)),
        ("0 0 1 * *", AT, datetime(2026, 11, 1, 0, 0)),
        ("0 0 1 jan *", AT, datetime(2027, 1, 1, 0, 0)),
        ("@daily", AT, datetime(2026, 10, 18, 0, 0)),
        ("@hourly", AT, datetime(2026, 10, 17, 13, 0)),
        ("@weekly", AT, datetime(2026, 10, 18, 0, 0)),  # Sunday
        ("0 12 * * 7", AT, datetime(2026, 10, 18, 12, 0)),  # 7 is Sunday too
        ("5,35 8-9 * * *", AT, datetime(2026, 10, 18, 8, 5)),
        ("10-50/20 * * * *", AT, datetime(2026, 10, 17, 12, 10)),
        ("0 0 29 2 *", AT, datetime(2028, 2, 29, 0, 0)),
    ],
)
def test_cron_next_run(expression, after, expected):
    assert parse_cron(expression).next_after(after) == expected


def test_a_matching_minute_is_strictly_after():
    assert parse_cron("7 12 * * *").next_after(datetime(2026, 10, 17, 12, 7)) == datetime(
        2026, 10, 18, 12, 7
    )


def test_day_of_month_and_weekday_together_match_either():
    # Vixie cron: the 1st of the month OR any Monday.
    schedule = parse_cron("0 0 1 * mon")
    assert schedule.next_after(AT) == datetime(2026, 10, 19, 0, 0)  # Monday
    assert schedule.next_after(datetime(2026, 10, 27)) == datetime(2026, 11, 1, 0, 0)


@pytest.mark.parametrize(
    "expression, message",
    [
        ("* * * *", "five fields"),
        ("60 * * * *", "outside 0-59"),
        ("* 24 * * *", "outside 0-23"),
        ("* * 0 * *", "outside 1-31"),
        ("* * * 13 *", "outside 1-12"),
        ("* * * * 8", "outside 0-7"),
        ("*/0 * * * *", "at least 1"),
        ("30-10 * * * *", "runs backwards"),
        ("x * * * *", "invalid minute"),
        ("0 0 30 2 *", "never matches"),
    ],
)
def test_bad_cron_expressions_say_what_is_wrong(expression, message):
    with pytest.raises(ValueError, match=message):
        parse_cron(expression)


def test_interval_runs_keep_a_fixed_cadence():
    start = datetime(2026, 10, 17, 12, 0)
    every = timedelta(minutes=5)

    assert next_interval_run(start, every, datetime(2026, 10, 17, 12, 1)) == (
        datetime(2026, 10, 17, 12, 5),
        0,
    )
    # Down for 17 minutes: three slots missed, and the cadence holds.
    assert next_interval_run(start, every, datetime(2026, 10, 17, 12, 17)) == (
        datetime(2026, 10, 17, 12, 20),
        3,
    )


# ---------------------------------------------------------------- scheduler


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture()
def blocking_pings(monkeypatch):
    """Scans whose pings wait until released, so a run can still be going."""
    release = threading.Event()
    monkeypatch.setattr(
        "ipmg.core.engine.ping_ip", lambda *_a: (release.wait(5), ("Active", 1.0))[1]
    )
    yield release
    release.set()


def make(tmp_path, max_scans=2):
    db = Database(tmp_path / "s.db")
    manager = ScanManager(db, max_scans=max_scans)
    clock = Clock(datetime(2026, 10, 17, 12, 0))
    return db, manager, clock, Scheduler(db, manager, clock=clock)


def add_schedule(db, name="lan", interval=5, cron=None, next_run_at="2026-10-17 12:00:00"):
    return db.create_schedule(
        name=name,
        targets="10.0.0.1",
        config={"threads": 1},
        interval_minutes=None if cron else interval,
        cron=cron,
        next_run_at=next_run_at,
    )


def wait_idle(manager, timeout=5.0):
    deadline = datetime.now() + timedelta(seconds=timeout)
    while manager.running_count() and datetime.now() < deadline:
        threading.Event().wait(0.02)


def test_a_due_schedule_runs_under_its_own_source(tmp_path, monkeypatch):
    monkeypatch.setattr("ipmg.core.engine.ping_ip", lambda *_a: ("Active", 1.0))
    db, manager, clock, scheduler = make(tmp_path)
    schedule_id = add_schedule(db)

    [scan_id] = scheduler.tick()
    wait_idle(manager)

    schedule = db.get_schedule(schedule_id)
    assert schedule["last_scan_id"] == scan_id
    assert schedule["last_run_at"] == "2026-10-17 12:00:00"
    assert schedule["next_run_at"] == "2026-10-17 12:05:00"
    assert db.get_scan(scan_id)["source"] == schedule_source("lan") == "schedule:lan"
    # Not due again until 12:05.
    assert scheduler.tick() == []


def test_an_overlapping_run_is_skipped_not_stacked(tmp_path, blocking_pings):
    db, manager, clock, scheduler = make(tmp_path)
    schedule_id = add_schedule(db, interval=1)

    [first] = scheduler.tick()
    clock.now += timedelta(minutes=1)
    assert scheduler.tick() == []

    schedule = db.get_schedule(schedule_id)
    assert schedule["last_scan_id"] == first
    assert "still running" in schedule["last_skip_reason"]
    assert schedule["next_run_at"] == "2026-10-17 12:02:00"
    assert manager.running_count() == 1


def test_a_run_is_skipped_while_max_scans_are_running(tmp_path, blocking_pings):
    db, manager, clock, scheduler = make(tmp_path, max_scans=1)
    add_schedule(db, name="a")
    busy = add_schedule(db, name="b")

    assert len(scheduler.tick()) == 1

    assert "already running" in db.get_schedule(busy)["last_skip_reason"]


def test_paused_schedules_never_run(tmp_path):
    db, manager, clock, scheduler = make(tmp_path)
    schedule_id = add_schedule(db)
    db.set_schedule_paused(schedule_id, True, None)

    assert scheduler.tick() == []


def test_schedules_survive_a_restart_and_catch_up_once(tmp_path, monkeypatch):
    monkeypatch.setattr("ipmg.core.engine.ping_ip", lambda *_a: ("Active", 1.0))
    db, manager, clock, scheduler = make(tmp_path)
    schedule_id = add_schedule(db, interval=5)

    # A new process, 23 minutes later, on the same database.
    db = Database(tmp_path / "s.db")
    manager = ScanManager(db)
    clock = Clock(datetime(2026, 10, 17, 12, 23))
    assert len(Scheduler(db, manager, clock=clock).tick()) == 1
    wait_idle(manager)

    # One catch-up run, then back on the 5-minute grid.
    assert db.get_schedule(schedule_id)["next_run_at"] == "2026-10-17 12:25:00"


def test_cron_schedules_move_to_their_next_match(tmp_path, monkeypatch):
    monkeypatch.setattr("ipmg.core.engine.ping_ip", lambda *_a: ("Active", 1.0))
    db, manager, clock, scheduler = make(tmp_path)
    schedule_id = add_schedule(db, cron="0 */6 * * *")

    scheduler.tick()
    wait_idle(manager)

    assert db.get_schedule(schedule_id)["next_run_at"] == "2026-10-17 18:00:00"


def test_next_run_of_an_interval_schedule_without_a_slot_starts_from_now():
    schedule = {"interval_minutes": 10, "cron": None, "next_run_at": None}

    assert next_run(schedule, datetime(2026, 10, 17, 12, 0)) == datetime(2026, 10, 17, 12, 10)


def test_bad_targets_are_a_recorded_skip_not_a_crash(tmp_path):
    db, manager, clock, scheduler = make(tmp_path)
    schedule_id = db.create_schedule("broken", "not-a-host", {}, 5, None, "2026-10-17 12:00:00")

    assert scheduler.tick() == []

    schedule = db.get_schedule(schedule_id)
    assert schedule["last_skip_reason"]
    assert schedule["next_run_at"] == "2026-10-17 12:05:00"


# --------------------------------------------------------------------- API


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("ipmg.core.engine.ping_ip", lambda *_a: ("Active", 1.0))
    # A long tick: the tests drive the scheduler themselves.
    app = create_app(Database(tmp_path / "api.db"), token="test-token", schedule_tick_s=3600)
    with TestClient(app, headers={"Authorization": "Bearer test-token"}) as test_client:
        yield test_client


def test_create_list_pause_resume_and_delete(client):
    created = client.post(
        "/api/v1/schedules",
        json={"name": "office", "targets": "10.0.0.1, 10.0.0.2", "interval_minutes": 15},
    )
    assert created.status_code == 201
    schedule = created.json()
    assert schedule["source"] == "schedule:office"
    assert schedule["paused"] is False and schedule["next_run_at"]
    assert schedule["config"]["threads"] == 50

    [listed] = client.get("/api/v1/schedules").json()
    assert listed["id"] == schedule["id"]

    paused = client.patch(f"/api/v1/schedules/{schedule['id']}", json={"paused": True}).json()
    assert (paused["paused"], paused["next_run_at"]) == (True, None)
    resumed = client.patch(f"/api/v1/schedules/{schedule['id']}", json={"paused": False}).json()
    assert resumed["paused"] is False and resumed["next_run_at"]

    assert client.delete(f"/api/v1/schedules/{schedule['id']}").status_code == 204
    assert client.get(f"/api/v1/schedules/{schedule['id']}").status_code == 404
    assert client.get("/api/v1/schedules").json() == []


def test_run_now_starts_a_scan_that_appears_in_history(client):
    schedule = client.post(
        "/api/v1/schedules", json={"name": "lab", "targets": "10.0.0.1", "cron": "@daily"}
    ).json()

    scan = client.post(f"/api/v1/schedules/{schedule['id']}/run")
    assert scan.status_code == 201

    scans = client.get("/api/v1/scans").json()
    assert [row["source"] for row in scans] == ["schedule:lab"]
    after = client.get(f"/api/v1/schedules/{schedule['id']}").json()
    assert after["last_scan_id"] == scan.json()["id"]
    # Running it by hand leaves the timetable alone.
    assert after["next_run_at"] == schedule["next_run_at"]


@pytest.mark.parametrize(
    "body, status, message",
    [
        ({"name": "x", "targets": "10.0.0.1"}, 400, "interval_minutes or cron"),
        (
            {"name": "x", "targets": "10.0.0.1", "interval_minutes": 5, "cron": "@daily"},
            400,
            "interval_minutes or cron",
        ),
        ({"name": "x", "targets": "10.0.0.1", "cron": "61 * * * *"}, 400, "Invalid cron"),
        ({"name": "x", "targets": "nonsense", "interval_minutes": 5}, 400, ""),
        ({"name": "x", "targets": "10.0.0.1", "interval_minutes": 0}, 422, ""),
        ({"name": "", "targets": "10.0.0.1", "interval_minutes": 5}, 422, ""),
    ],
)
def test_invalid_schedules_are_refused(client, body, status, message):
    response = client.post("/api/v1/schedules", json=body)

    assert response.status_code == status
    assert message in response.json()["detail"]


def test_schedule_names_are_unique(client):
    body = {"name": "Office", "targets": "10.0.0.1", "interval_minutes": 5}
    assert client.post("/api/v1/schedules", json=body).status_code == 201

    duplicate = client.post("/api/v1/schedules", json={**body, "name": "office"})
    assert duplicate.status_code == 409


def test_unknown_schedules_are_404(client):
    assert client.patch("/api/v1/schedules/9", json={"paused": True}).status_code == 404
    assert client.delete("/api/v1/schedules/9").status_code == 404
    assert client.post("/api/v1/schedules/9/run").status_code == 404


def test_the_app_starts_and_stops_its_scheduler(tmp_path):
    db = Database(tmp_path / "life.db")
    db.create_schedule("due", "10.0.0.1", {}, 5, None, "2000-01-01 00:00:00")
    app = create_app(db, token="t" * 16, schedule_tick_s=0.05)
    with TestClient(app):
        deadline = datetime.now() + timedelta(seconds=5)
        while db.get_schedule(1)["last_scan_id"] is None and datetime.now() < deadline:
            threading.Event().wait(0.02)
    assert db.get_schedule(1)["last_scan_id"] is not None
    assert not app.state.scheduler._thread.is_alive()
