"""Tell someone when a scan comparison finds changes: webhook, Slack, Teams, email.

Configuration problems (a missing URL, email without an SMTP server) are
raised before the scan starts, so a broken cron job fails loudly on its first
run. Delivery problems are only reported: a notification that cannot be sent
never fails the scan or costs it its reports.
"""

from __future__ import annotations

import json
import logging
import os
import smtplib
import socket
import ssl
import urllib.request
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlsplit

from ipmg import __version__
from ipmg.core.diff import HostChange, ScanDiff, Severity, meets_severity
from ipmg.exceptions import NotifyError
from ipmg.reporting import ui
from ipmg.reporting.diff_report import diff_to_markdown

log = logging.getLogger(__name__)

NOTIFY_SEVERITIES = tuple(severity.value for severity in Severity)
DEFAULT_NOTIFY_SEVERITY = Severity.WARNING.value

SMTP_SECURITY = ("starttls", "ssl", "none")
DEFAULT_SMTP_PORTS = {"starttls": 587, "ssl": 465, "none": 25}

#: Seconds to wait on a webhook or mail server before giving up on it.
SEND_TIMEOUT_S = 10

#: Changes listed in a Slack or Teams message; the rest are counted.
MAX_LISTED_CHANGES = 20

#: Slack rejects a section whose text is longer than this.
SLACK_SECTION_LIMIT = 3000

ENV_WEBHOOK = "IPMG_NOTIFY_WEBHOOK"
ENV_SLACK = "IPMG_NOTIFY_SLACK"
ENV_TEAMS = "IPMG_NOTIFY_TEAMS"
ENV_EMAIL = "IPMG_NOTIFY_EMAIL"
ENV_SMTP_HOST = "IPMG_SMTP_HOST"
ENV_SMTP_PORT = "IPMG_SMTP_PORT"
ENV_SMTP_SECURITY = "IPMG_SMTP_SECURITY"
ENV_SMTP_USER = "IPMG_SMTP_USER"
# A variable name, not a password.
ENV_SMTP_PASSWORD = "IPMG_SMTP_PASSWORD"  # nosec B105  # pragma: allowlist secret
ENV_SMTP_FROM = "IPMG_SMTP_FROM"


@dataclass(frozen=True)
class SmtpSettings:
    host: str
    port: int
    security: str
    sender: str
    recipients: Tuple[str, ...]
    username: str = ""
    password: str = ""


@dataclass(frozen=True)
class NotifyOptions:
    """Where change notifications go, and which changes are worth one."""

    webhook_url: str = ""
    slack_url: str = ""
    teams_url: str = ""
    email: Optional[SmtpSettings] = None
    min_severity: Severity = Severity(DEFAULT_NOTIFY_SEVERITY)

    @property
    def enabled(self) -> bool:
        return bool(self.webhook_url or self.slack_url or self.teams_url or self.email)


# ---------------------------------------------------------------- settings


def _flag_or_env(value: Optional[str], environ: Mapping[str, str], name: str) -> str:
    """A flag's value, else its environment variable, else empty."""
    if value:
        return value.strip()
    return environ.get(name, "").strip()


def _url(value: Optional[str], environ: Mapping[str, str], flag: str, env: str) -> str:
    """The URL for a ``--notify-*`` flag. None means the flag was not given."""
    if value is None:
        return ""
    url = _flag_or_env(value, environ, env)
    if not url:
        raise NotifyError(f"{flag} needs a URL: pass it after the flag or set {env}.")
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        # The URL is often a secret, so the message names the setting, not the value.
        raise NotifyError(f"{flag} must be an http:// or https:// URL.")
    return url


def _smtp_settings(args, environ: Mapping[str, str]) -> Optional[SmtpSettings]:
    recipients_arg = getattr(args, "notify_email", None)
    if recipients_arg is None:
        return None

    recipients = [address.strip() for address in recipients_arg if address.strip()]
    if not recipients:
        recipients = [
            address.strip() for address in environ.get(ENV_EMAIL, "").split(",") if address.strip()
        ]
    if not recipients:
        raise NotifyError(f"--notify-email needs at least one address, or set {ENV_EMAIL}.")

    host = _flag_or_env(getattr(args, "smtp_host", None), environ, ENV_SMTP_HOST)
    if not host:
        raise NotifyError(
            f"--notify-email needs a mail server: pass --smtp-host or set {ENV_SMTP_HOST}."
        )

    security = _flag_or_env(getattr(args, "smtp_security", None), environ, ENV_SMTP_SECURITY)
    security = (security or "starttls").lower()
    if security not in SMTP_SECURITY:
        raise NotifyError(f"{ENV_SMTP_SECURITY} must be one of {', '.join(SMTP_SECURITY)}.")

    port_arg = getattr(args, "smtp_port", None)
    port_text = str(port_arg) if port_arg is not None else environ.get(ENV_SMTP_PORT, "").strip()
    try:
        port = int(port_text) if port_text else DEFAULT_SMTP_PORTS[security]
    except ValueError:
        raise NotifyError(f"{ENV_SMTP_PORT} must be a port number.") from None
    if not 0 < port < 65536:
        raise NotifyError(f"SMTP port out of range (1-65535): {port}")

    username = _flag_or_env(getattr(args, "smtp_user", None), environ, ENV_SMTP_USER)
    sender = _flag_or_env(getattr(args, "smtp_from", None), environ, ENV_SMTP_FROM)
    return SmtpSettings(
        host=host,
        port=port,
        security=security,
        sender=sender or username or f"ipmg@{socket.getfqdn()}",
        recipients=tuple(recipients),
        username=username,
        # Only ever read from the environment: a password on the command line
        # would be visible to every user on the machine in the process list.
        password=environ.get(ENV_SMTP_PASSWORD, ""),
    )


def notify_options(args, environ: Optional[Mapping[str, str]] = None) -> NotifyOptions:
    """Read the ``--notify-*`` and ``--smtp-*`` settings, falling back to the environment.

    Raises NotifyError for a destination that is asked for but cannot work.
    """
    environ = os.environ if environ is None else environ
    return NotifyOptions(
        webhook_url=_url(
            getattr(args, "notify_webhook", None), environ, "--notify-webhook", ENV_WEBHOOK
        ),
        slack_url=_url(getattr(args, "notify_slack", None), environ, "--notify-slack", ENV_SLACK),
        teams_url=_url(getattr(args, "notify_teams", None), environ, "--notify-teams", ENV_TEAMS),
        email=_smtp_settings(args, environ),
        min_severity=Severity(getattr(args, "notify_severity", None) or DEFAULT_NOTIFY_SEVERITY),
    )


# ---------------------------------------------------------------- messages


def headline(diff: ScanDiff) -> str:
    """One line for a subject or a chat preview: ``3 changes (1 critical, 2 warning)``."""
    counts = diff.severity_counts
    breakdown = ", ".join(
        f"{counts[severity.value]} {severity.value}"
        for severity in Severity
        if counts.get(severity.value)
    )
    total = len(diff.changes)
    text = f"{total} change{'' if total == 1 else 's'} ({breakdown})"
    if diff.current.source:
        text += f" in {diff.current.source}"
    return text


def _listed(diff: ScanDiff) -> Tuple[Sequence[HostChange], int]:
    """The changes a chat message lists (most severe first), and how many it leaves out."""
    shown = diff.changes[:MAX_LISTED_CHANGES]
    return shown, len(diff.changes) - len(shown)


def _change_line(change: HostChange) -> str:
    host = f"{change.ip} ({change.hostname})" if change.hostname else change.ip
    return f"[{change.severity.value}] {host}: {change.describe()}"


def webhook_payload(diff: ScanDiff, min_severity: Severity) -> Dict[str, Any]:
    """The JSON a generic webhook receives: the whole change report plus context."""
    return {
        "event": "ipmg.changes",
        "ipmg_version": __version__,
        "headline": headline(diff),
        "min_severity": min_severity.value,
        **diff.to_dict(),
    }


def _slack_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def slack_payload(diff: ScanDiff) -> Dict[str, Any]:
    """A Slack incoming-webhook message."""
    shown, hidden = _listed(diff)
    lines = [f"• {_slack_escape(_change_line(change))}" for change in shown]
    if hidden:
        lines.append(f"…and {hidden} more")
    body = "\n".join(lines)
    if len(body) > SLACK_SECTION_LIMIT:
        body = body[: SLACK_SECTION_LIMIT - 1].rsplit("\n", 1)[0] + "\n…"

    return {
        "text": f"IPMG: {headline(diff)}",
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "IPMG detected network changes"},
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": _slack_escape(
                            f"{headline(diff)} · baseline {diff.baseline.display()} "
                            f"→ current {diff.current.display()}"
                        ),
                    }
                ],
            },
            {"type": "section", "text": {"type": "mrkdwn", "text": body}},
        ],
    }


def teams_payload(diff: ScanDiff) -> Dict[str, Any]:
    """A Microsoft Teams message: an Adaptive Card, as Teams Workflows webhooks expect."""
    shown, hidden = _listed(diff)
    lines = [f"- {_change_line(change)}" for change in shown]
    if hidden:
        lines.append(f"- …and {hidden} more")

    card = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": [
            {
                "type": "TextBlock",
                "text": "IPMG detected network changes",
                "size": "Medium",
                "weight": "Bolder",
                "wrap": True,
            },
            {"type": "TextBlock", "text": headline(diff), "wrap": True, "isSubtle": True},
            {
                "type": "FactSet",
                "facts": [
                    {"title": "Baseline", "value": diff.baseline.display()},
                    {"title": "Current", "value": diff.current.display()},
                ],
            },
            {"type": "TextBlock", "text": "\n".join(lines), "wrap": True},
        ],
    }
    return {
        "type": "message",
        "attachments": [
            {"contentType": "application/vnd.microsoft.card.adaptive", "content": card}
        ],
    }


def email_message(diff: ScanDiff, settings: SmtpSettings) -> EmailMessage:
    """An email whose body is the Markdown change report."""
    message = EmailMessage()
    message["Subject"] = f"IPMG: {headline(diff)}"
    message["From"] = settings.sender
    message["To"] = ", ".join(settings.recipients)
    message.set_content(diff_to_markdown(diff))
    return message


# ---------------------------------------------------------------- delivery


def post_json(url: str, payload: Mapping[str, Any]) -> None:
    """POST ``payload`` as JSON; any HTTP error status raises."""
    # urlopen also opens file:// and ftp:// URLs; a webhook is only ever http(s).
    if urlsplit(url).scheme not in ("http", "https"):
        raise ValueError("only http:// and https:// webhook URLs are allowed")
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": f"ipmg/{__version__}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=SEND_TIMEOUT_S) as response:  # nosec B310
        response.read()


def send_email(settings: SmtpSettings, message: EmailMessage) -> None:
    context = ssl.create_default_context()
    if settings.security == "ssl":
        client = smtplib.SMTP_SSL(
            settings.host, settings.port, timeout=SEND_TIMEOUT_S, context=context
        )
    else:
        client = smtplib.SMTP(settings.host, settings.port, timeout=SEND_TIMEOUT_S)
    with client:
        if settings.security == "starttls":
            client.starttls(context=context)
        if settings.username:
            client.login(settings.username, settings.password)
        client.send_message(message)


def _redact(text: str, options: NotifyOptions) -> str:
    """Strip secrets out of an error message: webhook URLs carry their token."""
    secrets = [options.webhook_url, options.slack_url, options.teams_url]
    if options.email:
        secrets.append(options.email.password)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text


Delivery = Tuple[str, Callable[[], None]]


def _deliveries(diff: ScanDiff, options: NotifyOptions, post, mail) -> List[Delivery]:
    """One named, deferred send per destination. Each builds its own message
    when called, so an error while building one is caught like a send error."""
    deliveries: List[Delivery] = []
    if options.webhook_url:
        deliveries.append(
            (
                "Webhook",
                lambda: post(options.webhook_url, webhook_payload(diff, options.min_severity)),
            )
        )
    if options.slack_url:
        deliveries.append(("Slack", lambda: post(options.slack_url, slack_payload(diff))))
    if options.teams_url:
        deliveries.append(("Teams", lambda: post(options.teams_url, teams_payload(diff))))
    if options.email:
        settings = options.email
        deliveries.append(("Email", lambda: mail(settings, email_message(diff, settings))))
    return deliveries


def send_notifications(
    diff: ScanDiff,
    options: NotifyOptions,
    post: Optional[Callable[[str, Mapping[str, Any]], None]] = None,
    mail: Optional[Callable[[SmtpSettings, EmailMessage], None]] = None,
) -> List[str]:
    """Send ``diff`` to every configured destination; returns the ones that failed.

    Nothing is sent unless a change reaches ``options.min_severity``. A
    destination that fails is reported and skipped, never raised.
    """
    if not options.enabled or not diff.has_changes:
        return []
    if not any(meets_severity(change.severity, options.min_severity) for change in diff.changes):
        ui.blank()
        ui.note(f"No change at or above {options.min_severity.value}; no notification sent.")
        return []

    sent: List[str] = []
    failed: List[str] = []
    for name, deliver in _deliveries(diff, options, post or post_json, mail or send_email):
        try:
            deliver()
        except Exception as exc:  # a failed alert must never fail the scan
            ui.blank()
            ui.warn(f"{name} notification failed: {_redact(str(exc), options)}")
            log.debug("%s notification failed", name, exc_info=True)
            failed.append(name)
        else:
            sent.append(name)

    if sent:
        ui.blank()
        ui.field("Notified", ", ".join(sent))
    return failed
