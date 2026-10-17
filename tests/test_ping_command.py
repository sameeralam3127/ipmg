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


def test_macos_and_freebsd_timeout_is_milliseconds():
    # macOS/FreeBSD ping -W takes milliseconds; sending "2" would wait 2 ms
    # and report healthy hosts as timed out.
    for system in ("Darwin", "FreeBSD"):
        assert build_ping_command("10.0.0.1", 2, 1, system=system) == [
            "ping",
            "-c",
            "1",
            "-W",
            "2000",
            "10.0.0.1",
        ]


def test_openbsd_waits_with_lowercase_w_in_seconds():
    # OpenBSD ping has no -W: passing one fails every probe with
    # "illegal option" and reports the whole network as down.
    assert build_ping_command("10.0.0.1", 2, 3, system="OpenBSD") == [
        "ping",
        "-c",
        "3",
        "-w",
        "2",
        "10.0.0.1",
    ]


def test_openbsd_ipv6_uses_ping6_with_the_same_wait():
    assert build_ping_command("2001:db8::1", 2, 1, system="OpenBSD") == [
        "ping6",
        "-c",
        "1",
        "-w",
        "2",
        "2001:db8::1",
    ]


def test_netbsd_deadline_covers_every_probe():
    # NetBSD ping -w is a deadline for the whole run, in seconds: the reply
    # wait plus one second per extra probe at the default interval.
    assert build_ping_command("10.0.0.1", 2, 1, system="NetBSD") == [
        "ping",
        "-c",
        "1",
        "-w",
        "2",
        "10.0.0.1",
    ]
    assert build_ping_command("10.0.0.1", 2, 3, system="NetBSD")[4] == "4"


def test_netbsd_ipv6_waits_per_reply_in_milliseconds():
    assert build_ping_command("2001:db8::1", 2, 1, system="NetBSD") == [
        "ping6",
        "-c",
        "1",
        "-x",
        "2000",
        "2001:db8::1",
    ]


def test_no_bsd_command_passes_an_unsupported_flag():
    # The flags each system's ping(8) documents, besides the address.
    supported = {
        "Darwin": {"-c", "-W"},
        "FreeBSD": {"-c", "-W"},
        "OpenBSD": {"-c", "-w"},
        "NetBSD": {"-c", "-w", "-x"},
    }
    for system, flags in supported.items():
        for ip in ("10.0.0.1", "2001:db8::1"):
            argv = build_ping_command(ip, 2, 2, system=system)
            assert {arg for arg in argv if arg.startswith("-")} <= flags, (system, argv)


def test_windows_uses_n_and_w_in_milliseconds():
    assert build_ping_command("10.0.0.1", 3, 2, system="Windows") == [
        "ping",
        "-n",
        "2",
        "-w",
        "3000",
        "10.0.0.1",
    ]
