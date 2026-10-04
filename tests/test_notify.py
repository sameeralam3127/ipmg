import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace

import pytest

from ipmg.core.diff import HostSnapshot, ScanRef, Severity, compare_snapshots
from ipmg.exceptions import NotifyError
from ipmg.infrastructure import notify
from ipmg.infrastructure.notify import (
    NotifyOptions,
    SmtpSettings,
    email_message,
    headline,
    notify_options,
    post_json,
    send_email,
    send_notifications,
    slack_payload,
    teams_payload,
    webhook_payload,
)
from ipmg.utils.helpers import console

SLACK_URL = "https://hooks.slack.com/services/T000/B000/secret-token"


@pytest.fixture(autouse=True)
def wide_console():
    previous = console.width
    console.width = 200
    yield
    console.width = previous


def make_diff(baseline, current):
    return compare_snapshots(
        baseline,
        current,
        baseline_ref=ScanRef(id=1, started_at="2026-09-27 10:00:00", source="targets.txt"),
        current_ref=ScanRef(id=2, started_at="2026-09-27 11:00:00", source="targets.txt"),
    )


@pytest.fixture()
def diff():
    """One critical change (offline), one warning (new host), one info (latency)."""
    return make_diff(
        [
            HostSnapshot("10.0.0.1", "Active", 10.0, "gateway"),
            HostSnapshot("10.0.0.2", "Active", 5.0),
        ],
        [
            HostSnapshot("10.0.0.1", "Timeout", None, "gateway"),
            HostSnapshot("10.0.0.2", "Active", 40.0),
            HostSnapshot("10.0.0.3", "Active", 2.0),
        ],
    )


@pytest.fixture()
def info_only_diff():
    return make_diff(
        [HostSnapshot("10.0.0.2", "Active", 5.0)],
        [HostSnapshot("10.0.0.2", "Active", 40.0)],
    )


def notify_args(**overrides):
    values = dict(
        notify_webhook=None,
        notify_slack=None,
        notify_teams=None,
        notify_email=None,
        notify_severity="warning",
        smtp_host=None,
        smtp_port=None,
        smtp_security=None,
        smtp_user=None,
        smtp_from=None,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


class Recorder:
    """Stands in for post_json and send_email."""

    def __init__(self, fail=()):
        self.posts = []
        self.mails = []
        self.fail = set(fail)

    def post(self, url, payload):
        if url in self.fail:
            raise OSError(f"connection refused by {url}")
        self.posts.append((url, payload))

    def mail(self, settings, message):
        if "mail" in self.fail:
            raise OSError("mail server down")
        self.mails.append((settings, message))


# ---------------------------------------------------------------- settings


def test_environment_alone_does_not_turn_notifications_on():
    options = notify_options(notify_args(), environ={"IPMG_NOTIFY_SLACK": SLACK_URL})

    assert not options.enabled


def test_url_flags_take_their_value_from_the_command_line():
    options = notify_options(notify_args(notify_slack=SLACK_URL), environ={})

    assert options.slack_url == SLACK_URL
    assert options.enabled


def test_url_flag_without_a_value_reads_the_environment():
    environ = {
        "IPMG_NOTIFY_WEBHOOK": "https://example.test/hook",
        "IPMG_NOTIFY_SLACK": SLACK_URL,
        "IPMG_NOTIFY_TEAMS": "https://example.test/teams",
    }

    options = notify_options(
        notify_args(notify_webhook="", notify_slack="", notify_teams=""), environ=environ
    )

    assert options.webhook_url == "https://example.test/hook"
    assert options.slack_url == SLACK_URL
    assert options.teams_url == "https://example.test/teams"


def test_url_flag_without_a_value_or_environment_is_an_error():
    with pytest.raises(NotifyError, match="IPMG_NOTIFY_SLACK"):
        notify_options(notify_args(notify_slack=""), environ={})


def test_a_non_http_url_is_rejected_without_echoing_it():
    with pytest.raises(NotifyError) as exc_info:
        notify_options(notify_args(notify_webhook="file:///etc/secret-token"), environ={})

    assert "secret-token" not in str(exc_info.value)


def test_email_settings_come_from_flags():
    options = notify_options(
        notify_args(
            notify_email=["ops@example.test", "noc@example.test"],
            smtp_host="mail.example.test",
            smtp_user="ipmg@example.test",
        ),
        environ={"IPMG_SMTP_PASSWORD": "hunter2"},  # pragma: allowlist secret
    )

    assert options.email == SmtpSettings(
        host="mail.example.test",
        port=587,
        security="starttls",
        sender="ipmg@example.test",
        recipients=("ops@example.test", "noc@example.test"),
        username="ipmg@example.test",
        password="hunter2",  # pragma: allowlist secret
    )


def test_email_settings_come_from_the_environment():
    environ = {
        "IPMG_NOTIFY_EMAIL": "ops@example.test, noc@example.test",
        "IPMG_SMTP_HOST": "mail.example.test",
        "IPMG_SMTP_SECURITY": "ssl",
        "IPMG_SMTP_FROM": "alerts@example.test",
    }

    settings = notify_options(notify_args(notify_email=[]), environ=environ).email

    assert settings.recipients == ("ops@example.test", "noc@example.test")
    assert settings.port == 465
    assert settings.security == "ssl"
    assert settings.sender == "alerts@example.test"
    assert settings.username == ""


def test_flags_override_the_environment():
    environ = {"IPMG_SMTP_HOST": "env.example.test", "IPMG_SMTP_PORT": "2525"}

    settings = notify_options(
        notify_args(notify_email=["a@example.test"], smtp_host="flag.example.test", smtp_port=26),
        environ=environ,
    ).email

    assert (settings.host, settings.port) == ("flag.example.test", 26)


@pytest.mark.parametrize(
    "overrides, environ, message",
    [
        ({"notify_email": []}, {"IPMG_SMTP_HOST": "mail"}, "at least one address"),
        ({"notify_email": ["a@example.test"]}, {}, "--smtp-host"),
        (
            {"notify_email": ["a@example.test"]},
            {"IPMG_SMTP_HOST": "mail", "IPMG_SMTP_PORT": "smtp"},
            "port number",
        ),
        (
            {"notify_email": ["a@example.test"], "smtp_port": 70000},
            {"IPMG_SMTP_HOST": "mail"},
            "out of range",
        ),
        (
            {"notify_email": ["a@example.test"]},
            {"IPMG_SMTP_HOST": "mail", "IPMG_SMTP_SECURITY": "tls"},
            "IPMG_SMTP_SECURITY",
        ),
    ],
)
def test_incomplete_email_settings_are_errors(overrides, environ, message):
    with pytest.raises(NotifyError, match=message):
        notify_options(notify_args(**overrides), environ=environ)


def test_smtp_user_with_security_none_is_refused_for_non_loopback_hosts():
    with pytest.raises(NotifyError, match=r"starttls.*ssl"):
        notify_options(
            notify_args(
                notify_email=["ops@example.test"],
                smtp_host="mail.example.test",
                smtp_security="none",
                smtp_user="ipmg@example.test",
            ),
            environ={},
        )


@pytest.mark.parametrize("loopback_host", ["localhost", "127.0.0.1", "::1"])
def test_smtp_user_with_security_none_is_allowed_for_loopback_hosts(loopback_host):
    settings = notify_options(
        notify_args(
            notify_email=["ops@example.test"],
            smtp_host=loopback_host,
            smtp_security="none",
            smtp_user="relay-user",
        ),
        environ={"IPMG_SMTP_PASSWORD": "relay-password"},  # pragma: allowlist secret
    ).email

    assert settings.host == loopback_host
    assert settings.security == "none"
    assert settings.username == "relay-user"
    assert settings.port == 25


# ---------------------------------------------------------------- messages


def test_headline_counts_changes_by_severity(diff):
    assert headline(diff) == "3 changes (1 critical, 1 warning, 1 info) in targets.txt"


def test_webhook_payload_carries_the_whole_change_report(diff):
    payload = webhook_payload(diff, Severity.WARNING)

    assert payload["event"] == "ipmg.changes"
    assert payload["min_severity"] == "warning"
    assert payload["summary"]["total_changes"] == 3
    assert [change["type"] for change in payload["changes"]] == [
        "host_offline",
        "new_host",
        "latency_changed",
    ]
    json.dumps(payload)


def test_slack_payload_lists_changes_most_severe_first(diff):
    payload = slack_payload(diff)
    body = payload["blocks"][-1]["text"]["text"]

    assert payload["text"].startswith("IPMG: 3 changes")
    assert body.splitlines()[0].startswith("• [critical] 10.0.0.1 (gateway): Host offline")


def test_slack_payload_escapes_control_characters():
    diff = make_diff(
        [HostSnapshot("10.0.0.1", "Active", 1.0, "<!channel>")],
        [HostSnapshot("10.0.0.1", "Timeout", None, "<!channel>")],
    )

    body = slack_payload(diff)["blocks"][-1]["text"]["text"]

    assert "<!channel>" not in body
    assert "&lt;!channel&gt;" in body


def test_chat_messages_cap_the_number_of_changes_listed():
    many = make_diff([], [HostSnapshot(f"10.0.1.{n}", "Active", 1.0) for n in range(1, 31)])

    slack_body = slack_payload(many)["blocks"][-1]["text"]["text"]
    teams_body = teams_payload(many)["attachments"][0]["content"]["body"][-1]["text"]

    assert slack_body.count("\n•") + 1 == notify.MAX_LISTED_CHANGES
    assert slack_body.endswith("…and 10 more")
    assert teams_body.endswith("…and 10 more")


def test_slack_section_stays_within_slacks_limit():
    long_name = "h" * 400
    many = make_diff([], [HostSnapshot(f"10.0.1.{n}", "Active", 1.0, long_name) for n in range(20)])

    body = slack_payload(many)["blocks"][-1]["text"]["text"]

    assert len(body) <= notify.SLACK_SECTION_LIMIT
    assert body.endswith("…")


def test_teams_payload_is_an_adaptive_card(diff):
    attachment = teams_payload(diff)["attachments"][0]
    card = attachment["content"]

    assert attachment["contentType"] == "application/vnd.microsoft.card.adaptive"
    assert card["type"] == "AdaptiveCard"
    assert card["body"][2]["facts"][0]["value"].startswith("#1")
    assert "- [critical] 10.0.0.1 (gateway): Host offline" in card["body"][-1]["text"]


def test_email_body_is_the_markdown_change_report(diff):
    settings = SmtpSettings("mail", 587, "starttls", "ipmg@example.test", ("ops@example.test",))

    message = email_message(diff, settings)

    assert message["Subject"] == "IPMG: 3 changes (1 critical, 1 warning, 1 info) in targets.txt"
    assert message["To"] == "ops@example.test"
    assert message.get_content().startswith("# IPMG Change Report")


# ---------------------------------------------------------------- sending


def everything(**overrides):
    values = dict(
        webhook_url="https://example.test/hook",
        slack_url=SLACK_URL,
        teams_url="https://example.test/teams",
        email=SmtpSettings("mail", 587, "starttls", "ipmg@x.test", ("ops@x.test",), "u", "pw"),
    )
    values.update(overrides)
    return NotifyOptions(**values)


def test_every_destination_is_notified(diff, capsys):
    recorder = Recorder()

    failed = send_notifications(diff, everything(), post=recorder.post, mail=recorder.mail)

    assert failed == []
    assert [url for url, _payload in recorder.posts] == [
        "https://example.test/hook",
        SLACK_URL,
        "https://example.test/teams",
    ]
    assert len(recorder.mails) == 1
    assert "Webhook, Slack, Teams, Email" in capsys.readouterr().out


def test_nothing_is_sent_without_changes():
    recorder = Recorder()
    unchanged = make_diff(
        [HostSnapshot("10.0.0.1", "Active", 1.0)], [HostSnapshot("10.0.0.1", "Active", 1.0)]
    )

    send_notifications(unchanged, everything(), post=recorder.post, mail=recorder.mail)

    assert recorder.posts == recorder.mails == []


def test_changes_below_the_severity_threshold_are_not_sent(info_only_diff, capsys):
    recorder = Recorder()

    send_notifications(info_only_diff, everything(), post=recorder.post, mail=recorder.mail)

    assert recorder.posts == recorder.mails == []
    assert "No change at or above warning" in capsys.readouterr().out


@pytest.mark.parametrize("severity", ["info", "warning", "critical"])
def test_a_critical_change_passes_every_threshold(diff, severity):
    recorder = Recorder()
    options = NotifyOptions(slack_url=SLACK_URL, min_severity=Severity(severity))

    send_notifications(diff, options, post=recorder.post)

    assert len(recorder.posts) == 1


def test_info_threshold_sends_info_changes(info_only_diff):
    recorder = Recorder()

    send_notifications(
        info_only_diff,
        NotifyOptions(slack_url=SLACK_URL, min_severity=Severity.INFO),
        post=recorder.post,
    )

    assert len(recorder.posts) == 1


def test_a_message_that_cannot_be_built_is_reported_not_raised(diff, monkeypatch, capsys):
    def broken(*_args):
        raise ValueError("cannot serialise")

    monkeypatch.setattr(notify, "webhook_payload", broken)
    recorder = Recorder()

    failed = send_notifications(diff, everything(), post=recorder.post, mail=recorder.mail)

    assert failed == ["Webhook"]
    assert "Webhook notification failed: cannot serialise" in capsys.readouterr().out
    assert len(recorder.posts) == 2


def test_a_failing_destination_is_reported_and_the_rest_still_sent(diff, capsys):
    recorder = Recorder(fail={SLACK_URL, "mail"})

    failed = send_notifications(diff, everything(), post=recorder.post, mail=recorder.mail)

    out = capsys.readouterr().out
    assert failed == ["Slack", "Email"]
    assert len(recorder.posts) == 2
    assert "Slack notification failed" in out
    assert "Email notification failed: mail server down" in out
    assert "secret-token" not in out
    assert "Webhook, Teams" in out


# ------------------------------------------------------------ transports


class _Handler(BaseHTTPRequestHandler):
    status = 204
    received = []

    def do_POST(self):  # noqa: N802 - the http.server API
        length = int(self.headers["Content-Length"])
        type(self).received.append((self.headers["Content-Type"], self.rfile.read(length)))
        self.send_response(type(self).status)
        self.end_headers()

    def log_message(self, *_args):
        pass


@pytest.fixture()
def http_server():
    _Handler.received = []
    _Handler.status = 204
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


def test_post_json_sends_a_json_body(http_server):
    url = f"http://127.0.0.1:{http_server.server_port}/hook"

    post_json(url, {"hello": "world"})

    content_type, body = _Handler.received[0]
    assert content_type == "application/json"
    assert json.loads(body) == {"hello": "world"}


def test_post_json_refuses_non_http_urls(tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("x")

    with pytest.raises(ValueError, match="http"):
        post_json(secret.as_uri(), {})


def test_post_json_raises_on_an_error_status(http_server):
    _Handler.status = 500
    url = f"http://127.0.0.1:{http_server.server_port}/hook"

    with pytest.raises(OSError, match="500"):
        post_json(url, {})


def test_a_real_webhook_failure_does_not_raise(diff, http_server, capsys):
    _Handler.status = 404
    url = f"http://127.0.0.1:{http_server.server_port}/secret-token"

    failed = send_notifications(diff, NotifyOptions(webhook_url=url))

    out = capsys.readouterr().out
    assert failed == ["Webhook"]
    assert "HTTP Error 404" in out
    assert "secret-token" not in out


class FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port, self.context = host, port, context
        self.calls = []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.calls.append("quit")

    def starttls(self, context=None):
        self.calls.append("starttls")

    def login(self, user, password):
        self.calls.append(("login", user, password))

    def send_message(self, message):
        self.calls.append(("send", message["To"]))


@pytest.fixture()
def fake_smtp(monkeypatch):
    FakeSMTP.instances = []
    monkeypatch.setattr(notify.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(notify.smtplib, "SMTP_SSL", FakeSMTP)
    return FakeSMTP.instances


@pytest.mark.parametrize(
    "security, user, expected",
    [
        ("starttls", "u", ["starttls", ("login", "u", "pw"), ("send", "ops@x.test"), "quit"]),
        ("ssl", "u", [("login", "u", "pw"), ("send", "ops@x.test"), "quit"]),
        ("none", "", [("send", "ops@x.test"), "quit"]),
    ],
)
def test_send_email_follows_the_security_setting(diff, fake_smtp, security, user, expected):
    settings = SmtpSettings("mail", 25, security, "ipmg@x.test", ("ops@x.test",), user, "pw")

    send_email(settings, email_message(diff, settings))

    assert fake_smtp[0].calls == expected
    assert (fake_smtp[0].context is not None) is (security == "ssl")


def test_send_email_refuses_cleartext_auth_on_remote_host(diff, fake_smtp):
    settings = SmtpSettings(
        "mail.example.test", 25, "none", "ipmg@x.test", ("ops@x.test",), "u", "pw"
    )

    with pytest.raises(NotifyError, match=r"starttls.*ssl"):
        send_email(settings, email_message(diff, settings))

    assert fake_smtp == []


def test_send_email_allows_cleartext_auth_on_loopback_host(diff, fake_smtp):
    settings = SmtpSettings("127.0.0.1", 25, "none", "ipmg@x.test", ("ops@x.test",), "u", "pw")

    send_email(settings, email_message(diff, settings))

    assert fake_smtp[0].calls == [("login", "u", "pw"), ("send", "ops@x.test"), "quit"]
