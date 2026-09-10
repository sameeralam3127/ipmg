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


def test_parser_accepts_streaming_flags():
    args = build_parser().parse_args(["--stream-all", "--stream-refresh", "1"])

    assert args.stream_all is True
    assert args.stream_refresh == 1.0
