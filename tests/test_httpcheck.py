import shutil
import socket
import ssl
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from ipmg.core.httpcheck import (
    FAILURE_CONNECT,
    FAILURE_DNS,
    FAILURE_INVALID,
    FAILURE_REDIRECTS,
    FAILURE_STATUS,
    FAILURE_TIMEOUT,
    FAILURE_TLS,
    HttpCheckOptions,
    check_url,
    format_expect,
    parse_expect,
    run_http_checks,
)


class Handler(BaseHTTPRequestHandler):
    """/status/N answers N; /redirect/N redirects N times then lands on /status/200."""

    seen_methods = []

    def log_message(self, *_args):
        pass

    def _answer(self):
        Handler.seen_methods.append(self.command)
        parts = self.path.strip("/").split("/")
        if parts[0] == "status":
            self.send_response(int(parts[1]))
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif parts[0] == "redirect":
            hops = int(parts[1])
            self.send_response(302)
            self.send_header("Location", f"/redirect/{hops - 1}" if hops > 1 else "/status/200")
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif parts[0] == "loop":
            self.send_response(301)
            self.send_header("Location", "/loop")
            self.end_headers()
        elif parts[0] == "slow":
            time.sleep(2)
            self.send_response(200)
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    do_GET = _answer
    do_HEAD = _answer


@pytest.fixture(scope="module")
def server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.daemon_threads = True
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


@pytest.fixture()
def closed_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


# ------------------------------------------------------------ status ranges


@pytest.mark.parametrize(
    "text, ranges",
    [
        ("200-399", ((200, 399),)),
        ("200,204", ((200, 200), (204, 204))),
        ("200-299, 401", ((200, 299), (401, 401))),
    ],
)
def test_expected_status_ranges_parse(text, ranges):
    assert parse_expect(text) == ranges
    assert parse_expect(format_expect(ranges)) == ranges


@pytest.mark.parametrize("text", ["", "abc", "399-200", "99", "200-700", "2000"])
def test_bad_status_ranges_are_rejected(text):
    with pytest.raises(ValueError):
        parse_expect(text)


def test_a_status_in_the_expected_range_passes(server):
    result = check_url(f"{server}/status/204")

    assert result.ok and result.outcome == "OK"
    assert result.status_code == 204
    assert result.response_ms is not None and result.response_ms >= 0
    assert result.failure == ""


def test_a_status_outside_the_range_fails_with_the_reason(server):
    result = check_url(f"{server}/status/502")

    assert not result.ok
    assert (result.status_code, result.failure) == (502, FAILURE_STATUS)
    assert result.error == "status 502, expected 200-399"
    assert result.summary == "502"


def test_a_custom_range_can_accept_an_error_status(server):
    options = HttpCheckOptions(expect=parse_expect("401"))

    assert check_url(f"{server}/status/401", options).ok
    assert not check_url(f"{server}/status/200", options).ok


# ---------------------------------------------------------------- redirects


def test_redirects_are_followed_to_the_final_url(server):
    result = check_url(f"{server}/redirect/3")

    assert result.ok and result.status_code == 200
    assert result.final_url == f"{server}/status/200"


def test_redirects_can_be_left_unfollowed(server):
    result = check_url(f"{server}/redirect/1", HttpCheckOptions(follow_redirects=False))

    # 302 is within the default 200-399, so not following still passes.
    assert (result.ok, result.status_code) == (True, 302)
    assert result.final_url == f"{server}/redirect/1"


def test_a_redirect_loop_fails(server):
    result = check_url(f"{server}/loop")

    assert (result.ok, result.failure) == (False, FAILURE_REDIRECTS)


def test_head_requests_are_sent_as_head(server):
    Handler.seen_methods = []

    assert check_url(f"{server}/status/200", HttpCheckOptions(method="HEAD")).ok
    assert Handler.seen_methods == ["HEAD"]


# ----------------------------------------------------------------- failures


def test_a_slow_server_times_out_within_the_timeout(server):
    started = time.monotonic()
    result = check_url(f"{server}/slow", HttpCheckOptions(timeout_s=0.3))

    assert (result.ok, result.failure) == (False, FAILURE_TIMEOUT)
    assert time.monotonic() - started < 1.5


def test_a_refused_connection_is_a_connect_failure(closed_port):
    result = check_url(f"http://127.0.0.1:{closed_port}/")

    assert (result.ok, result.failure) == (False, FAILURE_CONNECT)
    assert result.status_code is None and result.response_ms is None


def test_a_name_that_does_not_resolve_is_a_dns_failure():
    # .invalid is reserved (RFC 2606): it never resolves.
    result = check_url("http://ipmg-test.invalid/")

    assert (result.ok, result.failure) == (False, FAILURE_DNS)


@pytest.mark.parametrize("url", ["ftp://example.com/", "not a url", "http://", "file:///etc"])
def test_a_url_that_is_not_http_is_rejected_without_a_request(url):
    result = check_url(url)

    assert (result.ok, result.failure) == (False, FAILURE_INVALID)


def test_https_to_a_plain_http_server_is_a_tls_failure(server):
    result = check_url(server.replace("http://", "https://") + "/status/200")

    assert (result.ok, result.failure) == (False, FAILURE_TLS)


@pytest.fixture(scope="module")
def tls_server(tmp_path_factory):
    """An HTTPS server with a self-signed certificate (needs the openssl tool)."""
    if shutil.which("openssl") is None:
        pytest.skip("openssl is not installed")
    directory = tmp_path_factory.mktemp("tls")
    cert, key = directory / "cert.pem", directory / "key.pem"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "30",
            "-subj",
            "/CN=127.0.0.1",
            "-keyout",
            str(key),
            "-out",
            str(cert),
        ],
        check=True,
        capture_output=True,
    )
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"https://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def test_an_untrusted_certificate_fails_by_default(tls_server):
    result = check_url(f"{tls_server}/status/200")

    assert (result.ok, result.failure) == (False, FAILURE_TLS)
    assert "certificate" in result.error.lower()


def test_verification_can_be_turned_off_explicitly(tls_server):
    result = check_url(f"{tls_server}/status/200", HttpCheckOptions(verify_tls=False))

    assert (result.ok, result.status_code) == (True, 200)


# -------------------------------------------------------------- concurrency


def test_checks_run_concurrently_and_keep_their_order(server):
    urls = [f"{server}/slow", f"{server}/status/200", f"{server}/slow", f"{server}/status/503"]
    started = time.monotonic()
    results = run_http_checks(urls, HttpCheckOptions(timeout_s=5), max_workers=4)

    # Three distinct URLs (one repeat), each slow one 2 s: together, not in turn.
    assert time.monotonic() - started < 3.5
    assert [result.url for result in results] == [urls[0], urls[1], urls[3]]
    assert [result.ok for result in results] == [True, True, False]


def test_no_urls_means_no_checks():
    assert run_http_checks([]) == []


# ------------------------------------------------------- the scan workflow

from fastapi.testclient import TestClient  # noqa: E402
from scan_helpers import scan_args  # noqa: E402

from ipmg.cli import commands  # noqa: E402
from ipmg.core.diff import ChangeType  # noqa: E402
from ipmg.core.health import HostsDownError  # noqa: E402
from ipmg.infrastructure.database import Database  # noqa: E402
from ipmg.services.history_service import HistoryService  # noqa: E402
from ipmg.services.scan_service import run_scan  # noqa: E402
from ipmg.web.app import create_app  # noqa: E402


def http_args(tmp_path, urls, **overrides):
    defaults = dict(
        input=None,
        http_check=urls,
        http_timeout=2.0,
        http_expect="200-399",
        http_method="GET",
        http_no_redirects=False,
        http_insecure=False,
        formats=["csv", "md"],
    )
    defaults.update(overrides)
    return scan_args(tmp_path, **defaults)


def test_http_checks_alone_skip_the_host_scan(tmp_path, server, monkeypatch, capsys):
    monkeypatch.setattr(
        "ipmg.core.engine.ping_ip", lambda *_a: pytest.fail("no host should be pinged")
    )

    run_scan(http_args(tmp_path, [f"{server}/status/200", f"{server}/status/503"]))

    out = capsys.readouterr().out
    assert "HTTP checks" in out and "2 URLs" in out and "1 failed" in out
    # No host report, an HTTP report per format.
    assert not list(tmp_path.glob("results_2*"))
    [csv_report] = tmp_path.glob("results_http_*.csv")
    header, ok_row, failed_row = csv_report.read_text().splitlines()
    assert header.startswith("URL,Result,Status Code,Response Time (ms),Final URL,Failure")
    assert ",OK,200," in ok_row and ",Failed,503," in failed_row
    assert "# IPMG HTTP Check Report" in next(tmp_path.glob("results_http_*.md")).read_text()

    [scan] = Database(tmp_path / "history.db").list_scans()
    assert scan["source"] == "http-checks"
    checks = Database(tmp_path / "history.db").get_http_checks(scan["id"])
    assert [(check["ok"], check["status_code"]) for check in checks] == [(True, 200), (False, 503)]


def test_http_checks_run_beside_a_host_scan(tmp_path, server, stub_scan):
    stub_scan["statuses"] = {"10.0.0.1": ("Active", 1.0)}

    run_scan(http_args(tmp_path, [f"{server}/status/200"], input=["targets.csv"]))

    [scan] = Database(tmp_path / "history.db").list_scans()
    assert scan["total"] == 1
    assert len(Database(tmp_path / "history.db").get_http_checks(scan["id"])) == 1


def test_a_check_that_starts_failing_is_a_critical_change(tmp_path, server):
    run_scan(http_args(tmp_path, [f"{server}/status/200"], formats=[]))
    # The same URL and answer, but the second pass expects a redirect: it fails.
    run_scan(http_args(tmp_path, [f"{server}/status/200"], formats=[], http_expect="300-399"))

    diff = HistoryService.open(str(tmp_path / "history.db")).compare_latest()
    [change] = diff.changes
    assert change.type is ChangeType.HTTP_FAILING
    assert change.severity.value == "critical"
    assert change.ip == f"{server}/status/200"
    # URLs are not hosts: the host counts stay out of it.
    assert diff.changed_hosts == 0


def test_fail_on_down_also_fails_on_a_failing_http_check(tmp_path, server):
    with pytest.raises(HostsDownError, match="1 of 1 HTTP checks failed"):
        run_scan(http_args(tmp_path, [f"{server}/status/500"], formats=[], fail_on_down=True))


def test_a_bad_expect_range_from_the_command_line_is_rejected(capsys):
    with pytest.raises(SystemExit):
        commands.run(["--http-check", "http://x.test/", "--http-expect", "abc", "--no-config"])
    assert "invalid status range" in capsys.readouterr().err


def test_the_notice_says_an_http_only_run_sends_only_http(monkeypatch, capsys):
    from ipmg.core import security

    monkeypatch.setattr(security, "_DISCLAIMER_SHOWN", False)
    monkeypatch.setattr("ipmg.cli.commands.run_scan", lambda _args: None)

    commands.run(["--http-check", "http://x.test/", "--no-config"])
    assert "HTTP probes only" in capsys.readouterr().out


def test_the_api_lists_a_scan_s_http_checks(tmp_path, server):
    run_scan(http_args(tmp_path, [f"{server}/status/200"], formats=[]))
    db = Database(tmp_path / "history.db")
    scan_id = db.list_scans()[0]["id"]

    app = create_app(db, token="test-token")
    with TestClient(app, headers={"Authorization": "Bearer test-token"}) as client:
        [row] = client.get(f"/api/v1/scans/{scan_id}/http").json()
        missing = client.get("/api/v1/scans/999/http")

    assert (row["url"], row["ok"], row["status_code"]) == (f"{server}/status/200", True, 200)
    assert missing.status_code == 404
