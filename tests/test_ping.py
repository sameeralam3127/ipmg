import subprocess

import pytest

from ipmg.core import ping
from ipmg.core.ping import parse_latency, ping_ip, validate_ip


def test_ip_validation():
    assert validate_ip("8.8.8.8")
    assert not validate_ip("999.999.999.999")


def test_latency_parse():
    # Name the platform: without it this reads the host's own OS, so the
    # assertion silently changed meaning depending on where CI ran.
    sample = "min/avg/max/mdev = 10.0/20.5/30.0/1.0 ms"
    assert parse_latency(sample, system="Linux") == 20.5


# One real summary line per ping implementation IPMG can end up talking to.
POSIX_SUMMARIES = [
    # iputils: Ubuntu, Debian, RHEL, SUSE
    ("rtt min/avg/max/mdev = 19.694/20.100/21.000/0.400 ms", 20.1),
    # macOS and the BSDs
    ("round-trip min/avg/max/stddev = 0.077/0.079/0.081/0.002 ms", 0.079),
    # busybox: Alpine, OpenWrt, most slim container images — no mdev field
    ("round-trip min/avg/max = 0.043/0.055/0.070 ms", 0.055),
]


@pytest.mark.parametrize("summary, expected", POSIX_SUMMARIES)
def test_latency_parse_covers_every_posix_ping_implementation(summary, expected):
    assert parse_latency(summary, system="Linux") == expected


def test_busybox_ping_is_not_silently_dropped():
    """Alpine reports no mdev; the stricter pattern used to return None."""
    assert parse_latency("round-trip min/avg/max = 1.0/2.0/3.0 ms", system="Linux") == 2.0


WINDOWS_SUMMARIES = [
    ("English", "    Minimum = 0ms, Maximum = 2ms, Average = 1ms"),
    ("German", "    Minimum = 0ms, Maximum = 2ms, Mittelwert = 1ms"),
    ("French", "    Minimum = 0ms, Maximum = 2ms, Moyenne = 1ms"),
    ("Spanish", "    Mínimo = 0ms, Máximo = 2ms, Media = 1ms"),
]


@pytest.mark.parametrize("language, summary", WINDOWS_SUMMARIES)
def test_windows_latency_survives_a_translated_console(language, summary):
    """Only the word changes between locales; the Min/Max/Average order does not."""
    assert parse_latency(summary, system="Windows") == 1.0


def test_windows_latency_is_none_when_nothing_answered():
    assert parse_latency("Destination host unreachable.", system="Windows") is None


def test_posix_latency_is_none_when_nothing_answered():
    assert parse_latency("100% packet loss", system="Linux") is None


def fake_ping(monkeypatch, system, returncode, stdout):
    """Run ping_ip as if on ``system``, with ``stdout`` as ping's output."""
    monkeypatch.setattr(ping.platform, "system", lambda: system)
    monkeypatch.setattr(
        ping.subprocess,
        "run",
        lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, returncode, stdout, ""),
    )


WINDOWS_ROUTER_UNREACHABLE = """
Pinging 192.168.1.250 with 32 bytes of data:
Reply from 192.168.1.10: Destination host unreachable.

Ping statistics for 192.168.1.250:
    Packets: Sent = 1, Received = 1, Lost = 0 (0% loss),
"""

WINDOWS_ECHO_REPLY = """
Pinging 8.8.8.8 with 32 bytes of data:
Reply from 8.8.8.8: bytes=32 time=12ms TTL=117

Ping statistics for 8.8.8.8:
    Packets: Sent = 1, Received = 1, Lost = 0 (0% loss),
Approximate round trip times in milli-seconds:
    Minimum = 12ms, Maximum = 12ms, Average = 12ms
"""


def test_windows_unreachable_reply_is_not_active(monkeypatch):
    """Windows ping exits 0 on "Destination host unreachable" from a router."""
    fake_ping(monkeypatch, "Windows", 0, WINDOWS_ROUTER_UNREACHABLE)
    assert ping_ip("192.168.1.250", timeout=1, count=1) == ("Unreachable", None)


def test_windows_echo_reply_is_active(monkeypatch):
    fake_ping(monkeypatch, "Windows", 0, WINDOWS_ECHO_REPLY)
    assert ping_ip("8.8.8.8", timeout=1, count=1) == ("Active", 12.0)


def test_posix_success_does_not_depend_on_the_summary(monkeypatch):
    """Only Windows is second-guessed; elsewhere exit 0 means an echo reply."""
    fake_ping(monkeypatch, "Linux", 0, "64 bytes from 10.0.0.1: icmp_seq=1 ttl=64")
    assert ping_ip("10.0.0.1", timeout=1, count=1) == ("Active", None)
