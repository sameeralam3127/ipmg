"""The Prometheus /metrics endpoint and the text it serves."""

import re

import pytest
from fastapi.testclient import TestClient

from ipmg import __version__
from ipmg.cli.parser import build_web_parser
from ipmg.core.engine import HostResult, ScanConfig
from ipmg.infrastructure.database import Database
from ipmg.reporting.metrics import CONTENT_TYPE, render_metrics
from ipmg.services.history_service import HistoryService
from ipmg.web.app import create_app


@pytest.fixture()
def database(tmp_path):
    return Database(tmp_path / "metrics.db")


def record(database, source, results, scan_ports=False, duration=2.5):
    return HistoryService(database).record_scan(
        source=source,
        results=results,
        config=ScanConfig(scan_ports=scan_ports),
        duration_s=duration,
    )


def samples(text):
    """{series: value} for every sample line, ignoring HELP and TYPE."""
    found = {}
    for line in text.splitlines():
        if line and not line.startswith("#"):
            series, value = line.rsplit(" ", 1)
            found[series] = float(value)
    return found


# ------------------------------------------------------------------ content


def test_hosts_are_reported_from_the_latest_scan_of_each_source(database):
    record(database, "targets.txt", [HostResult("10.0.0.1", "Timeout", None)])
    record(
        database,
        "targets.txt",
        [HostResult("10.0.0.1", "Active", 12.5, "gw.lan"), HostResult("10.0.0.2", "Timeout", None)],
        duration=4.0,
    )

    metrics = samples(render_metrics(database))

    assert metrics['ipmg_host_up{source="targets.txt",ip="10.0.0.1"}'] == 1
    assert metrics['ipmg_host_up{source="targets.txt",ip="10.0.0.2"}'] == 0
    assert metrics['ipmg_host_latency_seconds{source="targets.txt",ip="10.0.0.1"}'] == 0.0125
    assert 'ipmg_host_latency_seconds{source="targets.txt",ip="10.0.0.2"}' not in metrics
    assert metrics['ipmg_host_info{source="targets.txt",ip="10.0.0.1",hostname="gw.lan"}'] == 1
    assert metrics['ipmg_scan_hosts{source="targets.txt",status="Active"}'] == 1
    assert metrics['ipmg_scan_hosts{source="targets.txt",status="Timeout"}'] == 1
    assert metrics['ipmg_scan_duration_seconds{source="targets.txt"}'] == 4.0
    assert metrics['ipmg_scans_total{source="targets.txt"}'] == 2
    assert metrics['ipmg_scan_timestamp_seconds{source="targets.txt"}'] > 1.7e9
    assert metrics[f'ipmg_build_info{{version="{__version__}"}}'] == 1


def test_each_source_keeps_its_own_latest_scan(database):
    record(database, "office.txt", [HostResult("10.0.0.1", "Active", 1.0)])
    record(database, "lab.txt", [HostResult("10.0.0.1", "Timeout", None)])

    metrics = samples(render_metrics(database))

    assert metrics['ipmg_host_up{source="office.txt",ip="10.0.0.1"}'] == 1
    assert metrics['ipmg_host_up{source="lab.txt",ip="10.0.0.1"}'] == 0


def test_open_ports_only_appear_for_scans_that_checked_ports(database):
    record(
        database, "ports.txt", [HostResult("10.0.0.1", "Active", 1.0, open_ports=(22, 443))], True
    )
    record(database, "plain.txt", [HostResult("10.0.0.2", "Active", 1.0)])

    metrics = samples(render_metrics(database))

    assert metrics['ipmg_host_open_ports{source="ports.txt",ip="10.0.0.1"}'] == 2
    assert not any(key.startswith('ipmg_host_open_ports{source="plain.txt"') for key in metrics)


def test_running_and_failed_scans_are_not_reported(database):
    running = database.create_scan("live.txt", 1, {})
    database.add_result(running, HostResult("10.0.0.1", "Active", 1.0))

    assert "live.txt" not in render_metrics(database)


def test_the_source_limit_bounds_the_series_and_says_what_it_left_out(database):
    for name in ("a.txt", "b.txt", "c.txt"):
        record(database, name, [HostResult("10.0.0.1", "Active", 1.0)])

    text = render_metrics(database, max_sources=2)

    assert 'source="c.txt"' in text and 'source="b.txt"' in text  # the newest two
    assert 'source="a.txt"' not in text
    assert samples(text)["ipmg_metrics_sources_omitted"] == 1


def test_label_values_are_escaped(database):
    record(database, 'odd "name"\\path\nnext', [HostResult("10.0.0.1", "Active", 1.0)])

    assert 'source="odd \\"name\\"\\\\path\\nnext"' in render_metrics(database)


def test_every_family_is_declared_once_even_when_empty(database):
    text = render_metrics(database)

    assert len(re.findall(r"^# TYPE ipmg_host_up gauge$", text, re.MULTILINE)) == 1
    assert "# TYPE ipmg_scans_total counter" in text
    assert text.endswith("\n")
    assert samples(text)["ipmg_metrics_sources_omitted"] == 0


def test_ipv6_hosts_are_labelled_as_written(database):
    record(database, "v6.txt", [HostResult("fe80::1%eth0", "Active", 1.0)])

    assert 'ipmg_host_up{source="v6.txt",ip="fe80::1%eth0"} 1' in render_metrics(database)


# ------------------------------------------------------------------ endpoint


def test_metrics_are_off_unless_asked_for(database):
    with TestClient(create_app(database, token="t" * 20)) as client:
        response = client.get("/metrics", headers={"Authorization": "Bearer " + "t" * 20})

    assert response.status_code == 404


def test_the_endpoint_serves_prometheus_text_with_the_token(database):
    record(database, "targets.txt", [HostResult("10.0.0.1", "Active", 1.0)])
    app = create_app(database, token="t" * 20, metrics_sources=5)

    with TestClient(app) as client:
        anonymous = client.get("/metrics")
        scraped = client.get("/metrics", headers={"Authorization": "Bearer " + "t" * 20})

    assert anonymous.status_code == 401
    assert scraped.status_code == 200
    assert scraped.headers["content-type"] == CONTENT_TYPE
    assert 'ipmg_host_up{source="targets.txt",ip="10.0.0.1"} 1' in scraped.text


def test_the_endpoint_stays_out_of_the_api_schema(database):
    app = create_app(database, token="t" * 20, metrics_sources=5)

    assert "/metrics" not in app.openapi()["paths"]


def test_web_parser_metrics_flags():
    assert build_web_parser().parse_args([]).metrics is False
    args = build_web_parser().parse_args(["--metrics", "--metrics-sources", "3"])
    assert (args.metrics, args.metrics_sources) == (True, 3)
