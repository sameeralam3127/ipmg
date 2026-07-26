import pytest

from ipmg.core import discovery
from ipmg.discover import discover_local_subnet
from ipmg.exceptions import DiscoveryError


def test_discover_local_subnet_with_custom_ip():
    # Using a fixed /24 subnet so behavior is deterministic
    ips = discover_local_subnet("192.168.1.10")

    # /24 -> 256 addresses, minus network + broadcast = 254 hosts
    assert len(ips) == 254
    assert "192.168.1.1" in ips
    assert "192.168.1.254" in ips
    # Edge: network/broadcast should not appear
    assert "192.168.1.0" not in ips
    assert "192.168.1.255" not in ips


def test_local_ip_prefers_the_outbound_interface(monkeypatch):
    class FakeSocket:
        def connect(self, _address):
            return None

        def getsockname(self):
            return ("192.168.5.20", 55000)

        def close(self):
            return None

    monkeypatch.setattr(discovery.socket, "socket", lambda *_args: FakeSocket())

    assert discovery.local_ip_address() == "192.168.5.20"


def test_local_ip_ignores_loopback_from_hostname(monkeypatch):
    def failing_socket(*_args):
        raise OSError("no route")

    monkeypatch.setattr(discovery.socket, "socket", failing_socket)
    monkeypatch.setattr(discovery.socket, "gethostname", lambda: "laptop")
    monkeypatch.setattr(discovery.socket, "gethostbyname", lambda _host: "127.0.0.1")

    with pytest.raises(DiscoveryError):
        discovery.local_ip_address()


def test_local_ip_falls_back_to_hostname(monkeypatch):
    def failing_socket(*_args):
        raise OSError("no route")

    monkeypatch.setattr(discovery.socket, "socket", failing_socket)
    monkeypatch.setattr(discovery.socket, "gethostname", lambda: "laptop")
    monkeypatch.setattr(discovery.socket, "gethostbyname", lambda _host: "10.1.2.3")

    assert discovery.local_ip_address() == "10.1.2.3"


def test_discover_rejects_an_invalid_address():
    with pytest.raises(DiscoveryError):
        discover_local_subnet("not-an-ip")


def test_discover_accepts_a_custom_prefix():
    assert len(discover_local_subnet("192.168.1.10", prefix=30)) == 2
