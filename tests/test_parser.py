import pytest

from ipmg import __version__
from ipmg.cli.parser import build_parser


def test_version_flag_prints_package_version(capsys):
    parser = build_parser()

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--version"])

    assert exc_info.value.code == 0
    assert capsys.readouterr().out.strip() == (
        f"IPMG - IP Management & Ping Monitoring Tool {__version__}"
    )


def test_parser_accepts_markdown_output_format():
    args = build_parser().parse_args(["--formats", "md", "csv"])

    assert args.formats == ["md", "csv"]


def test_parser_exit_status_checks_default_off():
    args = build_parser().parse_args([])

    assert args.fail_on_down is False
    assert args.min_active is None


def test_parser_accepts_exit_status_checks():
    args = build_parser().parse_args(["--fail-on-down", "--min-active", "90.5"])

    assert args.fail_on_down is True
    assert args.min_active == 90.5


@pytest.mark.parametrize("value", ["-1", "101", "most"])
def test_parser_rejects_an_invalid_min_active(value, capsys):
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--min-active", value])

    assert "--min-active" in capsys.readouterr().err


def test_parser_port_scanning_defaults_off():
    args = build_parser().parse_args([])

    assert args.scan_ports is False
    assert args.ports == (21, 22, 25, 53, 80, 443, 445, 1433, 3306, 3389, 5432)
    assert args.port_timeout == 1.0


def test_parser_accepts_custom_port_list():
    args = build_parser().parse_args(["--scan-ports", "--ports", "22,80,443"])

    assert args.scan_ports is True
    assert args.ports == (22, 80, 443)


def test_parser_rejects_invalid_port():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--ports", "not-a-port"])


def test_parser_streaming_defaults_off():
    args = build_parser().parse_args([])

    assert args.stream is False
    assert args.stream_all is False
    assert args.stream_refresh == 0.25


def test_parser_notifications_default_off():
    args = build_parser().parse_args([])

    assert args.notify_webhook is None
    assert args.notify_slack is None
    assert args.notify_teams is None
    assert args.notify_email is None
    assert args.notify_severity == "warning"


def test_parser_notification_urls_are_optional_values():
    args = build_parser().parse_args(
        [
            "--notify-slack",
            "--notify-webhook",
            "https://example.test/hook",
            "--notify-severity",
            "critical",
        ]
    )

    assert args.notify_slack == ""
    assert args.notify_webhook == "https://example.test/hook"
    assert args.notify_severity == "critical"


def test_parser_accepts_email_notification_settings():
    args = build_parser().parse_args(
        [
            "--notify-email",
            "a@example.test",
            "b@example.test",
            "--smtp-host",
            "mail",
            "--smtp-port",
            "2525",
        ]
    )

    assert args.notify_email == ["a@example.test", "b@example.test"]
    assert (args.smtp_host, args.smtp_port) == ("mail", 2525)


def test_diff_parser_accepts_notification_flags():
    from ipmg.cli.parser import build_diff_parser

    args = build_diff_parser().parse_args(["--notify-teams", "https://example.test/teams"])

    assert args.notify_teams == "https://example.test/teams"


def test_parser_accepts_streaming_flags():
    args = build_parser().parse_args(["--stream-all", "--stream-refresh", "1"])

    assert args.stream_all is True
    assert args.stream_refresh == 1.0


def test_parser_resume_takes_an_optional_report():
    parser = build_parser()

    assert parser.parse_args([]).resume is None
    assert parser.parse_args(["--resume"]).resume == ""
    assert parser.parse_args(["--resume", "scan_20260917_120000.csv"]).resume == (
        "scan_20260917_120000.csv"
    )


def test_parser_input_takes_several_sources():
    args = build_parser().parse_args(["--input", "targets.txt", "10.0.0.0/30", "10.0.0.5"])

    assert args.input == ["targets.txt", "10.0.0.0/30", "10.0.0.5"]


def test_parser_input_can_be_repeated():
    """Repeating the flag adds sources, so an alias carrying --input stays usable."""
    args = build_parser().parse_args(["--input", "targets.txt", "--input", "10.0.0.5"])

    assert args.input == ["targets.txt", "10.0.0.5"]


def test_parser_input_defaults_to_nothing():
    assert build_parser().parse_args([]).input is None


@pytest.mark.parametrize(
    "argv, expected",
    [
        ([], None),
        (["--discover"], "ipv4"),
        (["--discover", "ipv6"], "ipv6"),
        (["--discover", "all"], "all"),
    ],
)
def test_parser_discover_takes_an_optional_family(argv, expected):
    assert build_parser().parse_args(argv).discover == expected


def test_parser_rejects_an_unknown_discovery_family(capsys):
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--discover", "ipv5"])

    assert "--discover" in capsys.readouterr().err
