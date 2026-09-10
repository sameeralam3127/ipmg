import pytest

from ipmg.ping import parse_latency, validate_ip


def test_ip_validation():
    assert validate_ip("8.8.8.8")
    assert not validate_ip("999.999.999.999")


def test_latency_parse():
    sample = "min/avg/max/mdev = 10.0/20.5/30.0/1.0 ms"
    assert parse_latency(sample) == 20.5


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
