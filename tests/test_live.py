import io
from types import SimpleNamespace

import pytest
from rich.console import Console

from ipmg.core.engine import HostResult, ScanConfig
from ipmg.reporting import live, ui
from ipmg.services.scan_service import _stream_options
from ipmg.utils.helpers import RICH_THEME, console


@pytest.fixture(autouse=True)
def wide_console():
    """Keep rich from truncating streamed rows in captured output."""
    previous = console.width
    console.width = 200
    yield
    console.width = previous


def render(text) -> str:
    with console.capture() as capture:
        console.print(text, no_wrap=True, crop=False)
    return capture.get().rstrip("\n")


PING_ONLY = ScanConfig()
FULL = ScanConfig(resolve=True, scan_ports=True)

ACTIVE = HostResult(
    ip="192.168.1.10",
    status="Active",
    latency=1.25,
    hostname="router.lan",
    open_ports=(22, 80),
)
DOWN = HostResult(ip="192.168.1.11", status="Timeout", latency=None)


def test_row_carries_status_ip_and_latency():
    row = render(live.format_result(ACTIVE, PING_ONLY))

    assert "Active" in row
    assert "192.168.1.10" in row
    assert "1.2 ms" in row


def test_row_omits_columns_the_scan_did_not_produce():
    row = render(live.format_result(ACTIVE, PING_ONLY))

    assert "router.lan" not in row
    assert "22, 80" not in row


def test_row_adds_hostname_and_ports_when_configured():
    row = render(live.format_result(ACTIVE, FULL))

    assert "router.lan" in row
    assert "22, 80" in row


def test_row_shows_a_dash_for_missing_values():
    row = render(live.format_result(DOWN, FULL))

    assert row.count(ui.glyph("dash")) == 2
    assert "-" in row  # latency


def test_row_and_header_share_their_column_positions():
    header = render(live.format_header(FULL))
    row = render(live.format_result(ACTIVE, FULL))

    assert header.index("Host") == row.index("192.168.1.10")
    assert header.index("Name") == row.index("router.lan")
    assert header.index("Open ports") == row.index("22, 80")


def test_long_hostnames_are_truncated_to_their_column():
    result = HostResult(ip="10.0.0.1", status="Active", latency=1.0, hostname="a" * 200)

    row = render(live.format_result(result, ScanConfig(resolve=True)))

    assert len(row) < 80
    assert "aaa" in row


def test_header_lists_only_the_configured_columns():
    header = render(live.format_header(PING_ONLY))

    assert "Status" in header and "Host" in header and "Latency" in header
    assert "Name" not in header
    assert "Open ports" not in header


def test_refresh_interval_is_clamped():
    assert live.StreamOptions(refresh_s=0.0).clamped().refresh_s == live.MIN_REFRESH_S
    assert live.StreamOptions(refresh_s=1000.0).clamped().refresh_s == live.MAX_REFRESH_S
    assert live.StreamOptions(refresh_s=0.5).clamped().refresh_s == 0.5


def _args(**overrides):
    return SimpleNamespace(**overrides)


def stream(options, results, config=PING_ONLY):
    """Feed results through the display and return what it printed."""
    with console.capture() as capture:
        with live.scan_display(len(results), config, options) as on_result:
            for index, result in enumerate(results, start=1):
                on_result(result, index, len(results))
    return capture.get()


def test_streaming_prints_responsive_hosts_as_they_finish():
    out = stream(live.StreamOptions(enabled=True), [ACTIVE, DOWN])

    assert "192.168.1.10" in out
    assert "192.168.1.11" not in out


def test_streaming_all_hosts_includes_the_ones_that_did_not_answer():
    out = stream(live.StreamOptions(enabled=True, all_hosts=True), [ACTIVE, DOWN])

    assert "192.168.1.10" in out
    assert "192.168.1.11" in out


def test_streaming_off_prints_no_rows():
    out = stream(live.StreamOptions(), [ACTIVE, DOWN])

    assert "192.168.1.10" not in out
    assert "Live" not in out


def test_stream_all_implies_streaming():
    options = _stream_options(_args(stream=False, stream_all=True))

    assert options.enabled is True
    assert options.all_hosts is True


def test_streaming_is_off_by_default():
    assert _stream_options(_args()).enabled is False


def test_stream_options_clamp_the_refresh_interval():
    assert _stream_options(_args(stream=True, stream_refresh=0.0)).refresh_s == live.MIN_REFRESH_S


def test_streaming_on_a_real_terminal_drives_the_live_progress_bar(monkeypatch):
    """The redrawing progress bar only runs on a terminal, so give it one."""
    terminal = Console(
        theme=RICH_THEME, force_terminal=True, width=120, record=True, file=io.StringIO()
    )
    monkeypatch.setattr(live, "console", terminal)
    monkeypatch.setattr(ui, "console", terminal)

    with live.scan_display(2, PING_ONLY, live.StreamOptions(enabled=True)) as on_result:
        on_result(ACTIVE, 1, 2)
        on_result(DOWN, 2, 2)

    out = terminal.export_text()
    assert "192.168.1.10" in out
    assert "Scanning" in out
    assert "2/2" in out
    assert "1 up" in out
