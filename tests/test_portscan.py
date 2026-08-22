import pytest

from ipmg.core.portscan import (
    DEFAULT_PORTS,
    decode_ports,
    encode_ports,
    parse_port_list,
    port_service_name,
    scan_ports,
)


def test_scan_ports_returns_only_open_ports(monkeypatch):
    def fake_probe(_ip, port, _timeout):
        return port in (22, 443)

    monkeypatch.setattr("ipmg.core.portscan._probe", fake_probe)

    assert scan_ports("10.0.0.1", [22, 80, 443, 3389]) == [22, 443]


def test_scan_ports_empty_list_returns_empty():
    assert scan_ports("10.0.0.1", []) == []


def test_scan_ports_no_open_ports(monkeypatch):
    monkeypatch.setattr("ipmg.core.portscan._probe", lambda *_a: False)

    assert scan_ports("10.0.0.1", DEFAULT_PORTS) == []


def test_port_service_name():
    assert port_service_name(22) == "SSH"
    assert port_service_name(9999) == ""


def test_encode_decode_ports_round_trip():
    ports = (22, 80, 443)
    assert decode_ports(encode_ports(ports)) == ports


def test_decode_ports_handles_empty_string():
    assert decode_ports("") == ()


def test_parse_port_list_accepts_comma_separated_values():
    assert parse_port_list("22, 80,443") == (22, 80, 443)


def test_parse_port_list_rejects_out_of_range_port():
    with pytest.raises(ValueError):
        parse_port_list("70000")


def test_parse_port_list_rejects_empty_input():
    with pytest.raises(ValueError):
        parse_port_list("  ")
