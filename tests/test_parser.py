import pytest

from ipmg import __version__
from ipmg.cli.parser import build_parser


def test_version_flag_prints_package_version(capsys):
    parser = build_parser()

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--version"])

    assert exc_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"IPMG - IP Management & Ping Monitoring Tool {__version__}"
