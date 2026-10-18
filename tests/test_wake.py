import socket

import pytest
from fastapi.testclient import TestClient

from ipmg.cli import commands
from ipmg.core import wake
from ipmg.core.wake import WakeError, magic_packet, parse_mac, send_magic_packet
from ipmg.web.app import create_app
from ipmg.web.db import Database

MAC = bytes.fromhex("AABBCCDDEEFF")


class FakeSocket:
    """Records what a magic packet send would have done."""

    sent = []

    def __init__(self, family=socket.AF_INET, kind=socket.SOCK_DGRAM):
        self.family, self.kind = family, kind
        self.options = {}

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def setsockopt(self, level, option, value):
        self.options[(level, option)] = value

    def sendto(self, data, address):
        FakeSocket.sent.append((self.family, self.kind, self.options.copy(), data, address))


@pytest.fixture()
def fake_socket(monkeypatch):
    FakeSocket.sent = []
    monkeypatch.setattr(wake, "_udp_socket", FakeSocket)
    return FakeSocket.sent


def test_the_magic_packet_is_six_ff_bytes_then_the_mac_sixteen_times():
    packet = magic_packet(MAC)

    assert len(packet) == 102
    assert packet[:6] == b"\xff" * 6
    assert packet[6:] == bytes.fromhex("AABBCCDDEEFF" * 16)


@pytest.mark.parametrize("text", ["AA:BB:CC:DD:EE:FF", "aa-bb-cc-dd-ee-ff", "AABBCCDDEEFF"])
def test_every_documented_spelling_is_accepted(text):
    assert parse_mac(text) == MAC


@pytest.mark.parametrize(
    "text", ["", "AA:BB:CC:DD:EE", "AA:BB:CC:DD:EE:GG", "FF:FF:FF:FF:FF:FF", "00:00:00:00:00:00"]
)
def test_invalid_macs_are_rejected_clearly(text):
    with pytest.raises(WakeError, match="Invalid MAC address"):
        parse_mac(text)


def test_the_packet_goes_out_as_a_udp_broadcast(fake_socket):
    assert send_magic_packet("aa-bb-cc-dd-ee-ff", broadcast="192.168.1.255", port=7) == (
        "AA:BB:CC:DD:EE:FF"
    )

    [(family, kind, options, data, address)] = fake_socket
    assert (family, kind) == (socket.AF_INET, socket.SOCK_DGRAM)
    assert options[(socket.SOL_SOCKET, socket.SO_BROADCAST)] == 1
    assert data == magic_packet(MAC)
    assert address == ("192.168.1.255", 7)


@pytest.mark.parametrize(
    "broadcast, port, message",
    [
        ("not-an-ip", 9, "Invalid broadcast address"),
        ("ff02::1", 9, "need an IPv4 address"),
        ("255.255.255.255", 0, "Port out of range"),
    ],
)
def test_a_bad_destination_is_rejected_before_sending(fake_socket, broadcast, port, message):
    with pytest.raises(WakeError, match=message):
        send_magic_packet("AA:BB:CC:DD:EE:FF", broadcast=broadcast, port=port)
    assert fake_socket == []


def test_a_send_failure_is_a_clear_error(monkeypatch):
    class Refusing(FakeSocket):
        def sendto(self, _data, _address):
            raise PermissionError("Permission denied")

    monkeypatch.setattr(wake, "_udp_socket", Refusing)
    with pytest.raises(WakeError, match="Could not send the magic packet"):
        send_magic_packet("AA:BB:CC:DD:EE:FF")


# --------------------------------------------------------------------- CLI


def test_ipmg_wake_sends_one_packet_per_mac(fake_socket, capsys):
    code = commands.run(["wake", "AA:BB:CC:DD:EE:FF", "AABBCCDDEE01", "--broadcast", "10.0.0.255"])

    assert code == 0
    assert [address for *_rest, address in fake_socket] == [("10.0.0.255", 9)] * 2
    out = capsys.readouterr().out
    assert "Magic packet sent to AA:BB:CC:DD:EE:FF via 10.0.0.255:9" in out
    assert "AA:BB:CC:DD:EE:01" in out


def test_ipmg_wake_rejects_an_invalid_mac_with_exit_1_and_sends_nothing(fake_socket, capsys):
    code = commands.run(["wake", "AA:BB:CC:DD:EE:FF", "not-a-mac"])

    assert code == 1
    assert fake_socket == []
    assert "Invalid MAC address: 'not-a-mac'" in capsys.readouterr().out


# --------------------------------------------------------------------- API


@pytest.fixture()
def client(tmp_path):
    app = create_app(Database(tmp_path / "wake.db"), token="test-token")
    with TestClient(app, headers={"Authorization": "Bearer test-token"}) as test_client:
        yield test_client


def test_the_api_wakes_a_host(client, fake_socket):
    response = client.post("/api/v1/wake", json={"mac": "aa:bb:cc:dd:ee:ff"})

    assert response.status_code == 200
    assert response.json() == {
        "mac": "AA:BB:CC:DD:EE:FF",
        "broadcast": "255.255.255.255",
        "port": 9,
    }
    assert len(fake_socket) == 1


def test_the_api_rejects_an_invalid_mac(client, fake_socket):
    response = client.post("/api/v1/wake", json={"mac": "nope"})

    assert response.status_code == 400
    assert "Invalid MAC address" in response.json()["detail"]
    assert fake_socket == []


def test_waking_needs_the_token(tmp_path, fake_socket):
    app = create_app(Database(tmp_path / "anon.db"), token="test-token")
    with TestClient(app) as anonymous:
        assert anonymous.post("/api/v1/wake", json={"mac": "AA:BB:CC:DD:EE:FF"}).status_code == 401
    assert fake_socket == []
