import pytest

from ipmg.cli import commands
from ipmg.web import network, server

TOKEN = "t" * 20


def fake_runner(answers):
    """A Runner answering each argv's first two words from ``answers``; records calls."""
    calls = []

    def run(argv):
        calls.append(list(argv))
        for prefix, answer in answers.items():
            if list(argv[: len(prefix)]) == list(prefix):
                return answer
        return None

    run.calls = calls
    return run


# ----------------------------------------------------------------- the link


def test_a_loopback_server_links_to_loopback():
    assert network.browse_urls("127.0.0.1", 8080, TOKEN) == [
        (f"http://127.0.0.1:8080/#token={TOKEN}", "")
    ]


def test_listening_everywhere_links_to_this_machine_s_lan_address(monkeypatch):
    monkeypatch.setattr(network, "in_container", lambda: False)
    monkeypatch.setattr(network, "local_ip_address", lambda: "192.168.0.201")

    urls = network.browse_urls("0.0.0.0", 8080, TOKEN)  # nosec B104

    assert urls == [
        (f"http://192.168.0.201:8080/#token={TOKEN}", "from other machines"),
        (f"http://127.0.0.1:8080/#token={TOKEN}", "on this machine"),
    ]


def test_without_a_lan_address_the_local_link_remains(monkeypatch):
    from ipmg.exceptions import DiscoveryError

    def none():
        raise DiscoveryError("offline")

    monkeypatch.setattr(network, "in_container", lambda: False)
    monkeypatch.setattr(network, "local_ip_address", none)

    assert network.browse_urls("::", 8080, TOKEN) == [
        (f"http://127.0.0.1:8080/#token={TOKEN}", "on this machine")
    ]


def test_in_a_container_the_container_address_is_not_offered(monkeypatch):
    monkeypatch.setattr(network, "in_container", lambda: True)
    monkeypatch.setattr(network, "local_ip_address", lambda: pytest.fail("not wanted"))

    [(url, audience)] = network.browse_urls("0.0.0.0", 8080, TOKEN)  # nosec B104

    assert url.startswith("http://127.0.0.1:8080/") and "published" in audience


def test_a_specific_address_is_linked_as_given_with_ipv6_in_brackets():
    assert network.browse_urls("10.0.0.5", 9000, TOKEN)[0][0].startswith("http://10.0.0.5:9000/")
    assert network.browse_urls("2001:db8::5", 9000, TOKEN)[0][0].startswith(
        "http://[2001:db8::5]:9000/"
    )


# -------------------------------------------------------------- firewalls


def test_firewalld_blocking_the_port():
    run = fake_runner(
        {
            ("firewall-cmd", "--state"): (0, "running\n"),
            ("firewall-cmd", "--query-port=8080/tcp"): (1, "no\n"),
        }
    )

    firewall = network.detect_firewall(8080, "Linux", run)

    assert (firewall.name, firewall.blocks) == ("firewalld", True)
    assert firewall.open_commands[0] == "sudo firewall-cmd --add-port=8080/tcp"
    assert "--permanent" in firewall.open_commands[1]
    assert firewall.close_argv == ("firewall-cmd", "--remove-port=8080/tcp")


def test_firewalld_already_allowing_the_port():
    run = fake_runner(
        {
            ("firewall-cmd", "--state"): (0, "running\n"),
            ("firewall-cmd", "--query-port=8080/tcp"): (0, "yes\n"),
        }
    )

    assert network.detect_firewall(8080, "Linux", run).blocks is False


def test_a_stopped_firewalld_falls_through_to_ufw():
    run = fake_runner(
        {
            ("firewall-cmd", "--state"): (252, "not running\n"),
            ("ufw", "status"): (
                0,
                "Status: active\n\nTo   Action  From\n--   ------  ----\n22/tcp  ALLOW  Anywhere\n",
            ),
        }
    )

    firewall = network.detect_firewall(8080, "Linux", run)

    assert (firewall.name, firewall.blocks) == ("ufw", True)
    assert firewall.open_commands == ("sudo ufw allow 8080/tcp",)


def test_ufw_allowing_the_port_and_ufw_inactive():
    allowed = fake_runner({("ufw", "status"): (0, "Status: active\n\n8080/tcp  ALLOW  Anywhere\n")})
    assert network.detect_firewall(8080, "Linux", allowed).blocks is False

    inactive = fake_runner({("ufw", "status"): (0, "Status: inactive\n")})
    assert network.detect_firewall(8080, "Linux", inactive) is None


def test_ufw_without_root_is_reported_as_unknown():
    run = fake_runner({("ufw", "status"): (1, "ERROR: You need to be root to run this script\n")})

    firewall = network.detect_firewall(8080, "Linux", run)

    assert (firewall.name, firewall.blocks) == ("ufw", None)
    assert "ufw is enabled" in firewall.note


def test_no_firewall_tools_means_nothing_to_say():
    assert network.detect_firewall(8080, "Linux", fake_runner({})) is None


def test_windows_and_macos_firewalls_explain_the_prompt():
    windows = network.detect_firewall(
        8080,
        "Windows",
        fake_runner({("netsh", "advfirewall"): (0, "State                                 ON\n")}),
    )
    assert "netsh advfirewall firewall add rule" in windows.open_commands[0]
    assert "Private networks" in windows.note
    assert not windows.can_manage

    macos = network.detect_firewall(
        8080,
        "Darwin",
        fake_runner({(network._SOCKETFILTERFW, "--getglobalstate"): (0, "Firewall is enabled.\n")}),
    )
    assert "click Allow" in macos.note


# ------------------------------------------------------ what IPMG Web prints


@pytest.fixture()
def started(tmp_path, monkeypatch):
    """Run run_dashboard without serving, and capture what it printed."""
    monkeypatch.setattr(server.uvicorn, "run", lambda *a, **k: None)
    monkeypatch.setattr(server, "_has_display", lambda: False)
    monkeypatch.setattr(network, "in_container", lambda: False)
    monkeypatch.setattr(network, "local_ip_address", lambda: "192.168.0.201")
    monkeypatch.setenv("IPMG_WEB_TOKEN", TOKEN)
    return lambda **kwargs: server.run_dashboard(db_path=str(tmp_path / "w.db"), **kwargs)


def test_a_lan_server_prints_the_lan_link_and_the_firewall_step(started, monkeypatch, capsys):
    blocked = network.Firewall(
        "firewalld",
        True,
        ("sudo firewall-cmd --add-port=8080/tcp",),
        open_argv=("firewall-cmd", "--add-port=8080/tcp"),
        close_argv=("firewall-cmd", "--remove-port=8080/tcp"),
    )
    monkeypatch.setattr(network, "detect_firewall", lambda port: blocked)

    started(host="0.0.0.0", open_browser=False)  # nosec B104

    out = capsys.readouterr().out
    assert f"http://192.168.0.201:8080/#token={TOKEN}" in out
    assert "firewalld blocks 8080/tcp" in out
    assert "sudo firewall-cmd --add-port=8080/tcp" in out
    assert "--open-firewall" in out


def test_open_firewall_opens_the_port_and_closes_it_on_exit(started, monkeypatch, capsys):
    run = fake_runner(
        {
            ("firewall-cmd", "--state"): (0, "running\n"),
            ("firewall-cmd", "--query-port=8080/tcp"): (1, "no\n"),
            ("firewall-cmd", "--add-port=8080/tcp"): (0, "success\n"),
            ("firewall-cmd", "--remove-port=8080/tcp"): (0, "success\n"),
        }
    )
    monkeypatch.setattr(network, "_run", run)
    monkeypatch.setattr(network.platform, "system", lambda: "Linux")
    monkeypatch.setattr(network, "is_admin", lambda: True)

    started(host="0.0.0.0", open_browser=False, open_firewall=True)  # nosec B104

    out = capsys.readouterr().out
    assert "opened 8080/tcp in firewalld until IPMG Web stops" in out
    assert "Closed 8080/tcp in firewalld again." in out
    assert ["firewall-cmd", "--add-port=8080/tcp"] in run.calls
    assert ["firewall-cmd", "--remove-port=8080/tcp"] in run.calls


def test_open_firewall_without_root_says_so_and_changes_nothing(started, monkeypatch, capsys):
    blocked = network.Firewall(
        "ufw", True, ("sudo ufw allow 8080/tcp",), open_argv=("ufw", "allow", "8080/tcp")
    )
    monkeypatch.setattr(network, "detect_firewall", lambda port: blocked)
    monkeypatch.setattr(network, "is_admin", lambda: False)
    monkeypatch.setattr(network, "open_port", lambda fw: pytest.fail("must not open"))

    started(host="0.0.0.0", open_browser=False, open_firewall=True)  # nosec B104

    out = capsys.readouterr().out
    assert "needs root" in out and "sudo ufw allow 8080/tcp" in out


def test_a_loopback_server_points_at_lan_and_skips_the_firewall(started, monkeypatch, capsys):
    monkeypatch.setattr(network, "detect_firewall", lambda port: pytest.fail("not checked"))

    started(open_browser=False)

    out = capsys.readouterr().out
    assert f"http://127.0.0.1:8080/#token={TOKEN}" in out
    assert "ipmg web --lan" in out


# ------------------------------------------------------------------- CLI


@pytest.mark.parametrize(
    "argv, host, open_firewall",
    [
        (["web"], "127.0.0.1", False),
        (["web", "--lan"], "0.0.0.0", False),  # nosec B104
        (["web", "--open-firewall"], "0.0.0.0", True),  # nosec B104
        (["web", "--host", "10.0.0.5"], "10.0.0.5", False),
    ],
)
def test_web_flags_choose_where_to_listen(argv, host, open_firewall, monkeypatch):
    captured = {}
    monkeypatch.setattr("ipmg.web.server.run_dashboard", lambda **kw: captured.update(kw))

    assert commands.run([*argv, "--no-browser"]) == 0
    assert (captured["host"], captured["open_firewall"]) == (host, open_firewall)


def test_lan_and_host_cannot_be_combined(capsys):
    with pytest.raises(SystemExit):
        commands.run(["web", "--lan", "--host", "10.0.0.5"])
    assert "not allowed with" in capsys.readouterr().err
