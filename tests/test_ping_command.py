from ipmg.core.ping import build_ping_command


def test_linux_timeout_is_seconds():
    assert build_ping_command("10.0.0.1", 2, 1, system="Linux") == [
        "ping",
        "-c",
        "1",
        "-W",
        "2",
        "10.0.0.1",
    ]


def test_bsd_timeout_is_milliseconds():
    # macOS/BSD ping -W takes milliseconds; sending "2" would wait 2 ms and
    # report healthy hosts as timed out.
    for system in ("Darwin", "FreeBSD", "OpenBSD", "NetBSD"):
        assert build_ping_command("10.0.0.1", 2, 1, system=system)[4] == "2000"


def test_windows_uses_n_and_w_in_milliseconds():
    assert build_ping_command("10.0.0.1", 3, 2, system="Windows") == [
        "ping",
        "-n",
        "2",
        "-w",
        "3000",
        "10.0.0.1",
    ]
