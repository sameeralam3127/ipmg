"""The SNMP implementation: BER, USM security, sessions, and the MIB-II poller."""

import socket

import pytest
from snmp_agent import Agent, User, counter32, counter64, ip_address, octets, switch_mib

from ipmg.core.snmp import (
    FAILURE_AUTH,
    FAILURE_ERROR,
    FAILURE_NETWORK,
    FAILURE_PROTOCOL,
    FAILURE_REFUSED,
    FAILURE_TIMEOUT,
    FAILURE_UNSUPPORTED,
    Credentials,
    Session,
    SnmpOptions,
    ber,
    poll_device,
    poll_devices,
    usm,
)
from ipmg.core.snmp.poller import bulk_walk

SYS_NAME = (1, 3, 6, 1, 2, 1, 1, 5, 0)
#: Test passphrases, for the fake agent only.
AUTH_KEY = "authpass123"  # pragma: allowlist secret
PRIV_KEY = "privpass123"  # pragma: allowlist secret
WRONG_AUTH_KEY = "wrongpass99"  # pragma: allowlist secret
WRONG_PRIV_KEY = "wrongpriv99"  # pragma: allowlist secret
SECRETS = ("c0mmunity", "authsecret", "privsecret")  # pragma: allowlist secret


def options(agent, **overrides):
    """Poll ``agent`` quickly: one short attempt, unless a test says otherwise."""
    settings = {"port": agent.port, "timeout_s": 0.5, "retries": 0}
    settings.update(overrides)
    return SnmpOptions(**settings)


def v3(user, **credentials):
    return Credentials(user=user, **credentials)


# ---------------------------------------------------------------------- BER


@pytest.mark.parametrize(
    "value, encoded",
    [
        (0, "020100"),
        (127, "02017f"),
        (128, "02020080"),
        (256, "02020100"),
        (-1, "0201ff"),
        (-128, "020180"),
        (-129, "0202ff7f"),
        (2**31 - 1, "02047fffffff"),
    ],
)
def test_integers_use_the_fewest_bytes(value, encoded):
    assert ber.encode_int(value).hex() == encoded
    assert ber.decode_int(ber.decode_element(ber.encode_int(value))) == value


def test_unsigned_types_decode_as_unsigned():
    assert ber.decode_int(ber.decode_element(counter32(2**32 - 1))) == 2**32 - 1
    assert ber.decode_int(ber.decode_element(counter64(2**64 - 1))) == 2**64 - 1


def test_long_lengths_round_trip():
    content = bytes(300)
    encoded = ber.tlv(ber.OCTET_STRING, content)

    assert encoded[:4] == bytes([0x04, 0x82, 0x01, 0x2C])
    assert ber.decode_element(encoded).content == content


def test_object_identifiers_round_trip():
    assert ber.encode_oid(SYS_NAME).hex() == "06082b06010201010500"
    for oid in [SYS_NAME, (1, 3, 6, 1, 4, 1, 2021, 4294967295), (2, 999, 3), (0, 0)]:
        assert ber.decode_oid(ber.decode_element(ber.encode_oid(oid)).content) == oid
    assert ber.parse_oid(".1.3.6.1") == (1, 3, 6, 1)
    assert ber.format_oid(SYS_NAME) == "1.3.6.1.2.1.1.5.0"


@pytest.mark.parametrize("oid", [(1,), (3, 1), (1, 40)])
def test_invalid_object_identifiers_are_refused(oid):
    with pytest.raises(ber.BerError):
        ber.encode_oid(oid)


@pytest.mark.parametrize(
    "data",
    [
        b"\x30",  # no length
        b"\x30\x05ab",  # shorter than it says
        b"\x30\x85\x00\x00\x00\x00\x01",  # a five-byte length
        b"\x30\x80",  # indefinite length
        b"\x1f\x01\x00",  # a multi-byte tag
    ],
)
def test_malformed_elements_are_refused(data):
    with pytest.raises(ber.BerError):
        ber.decode_element(data)


def test_bad_values_are_refused():
    with pytest.raises(ber.BerError):
        ber.decode_oid(b"\x81")
    with pytest.raises(ber.BerError):
        ber.decode_int(ber.Element(ber.INTEGER, b"\x02\x00", 2, 2))
    with pytest.raises(ber.BerError):
        ber.parse_oid("1.3.six")


def test_values_decode_to_python():
    def value(encoded):
        return ber.decode_value(ber.decode_element(encoded))

    assert value(ip_address("10.0.0.1")) == "10.0.0.1"
    assert value(octets("text")) == b"text"
    assert value(ber.encode_oid(SYS_NAME)) == SYS_NAME
    assert value(ber.encode_null()) is None
    assert value(ber.tlv(ber.END_OF_MIB_VIEW, b"")) is None


def test_response_pdus_decode_and_requests_do_not():
    varbind = ber.tlv(ber.SEQUENCE, ber.encode_oid(SYS_NAME) + octets("sw1"))
    response = ber.tlv(
        ber.RESPONSE,
        ber.encode_int(42) + ber.encode_int(0) + ber.encode_int(0) + ber.tlv(ber.SEQUENCE, varbind),
    )

    pdu = ber.decode_pdu(ber.decode_element(response))
    assert (pdu.request_id, pdu.varbinds[0].oid, pdu.varbinds[0].value) == (42, SYS_NAME, b"sw1")
    assert not pdu.varbinds[0].missing

    with pytest.raises(ber.BerError):
        ber.decode_pdu(ber.decode_element(ber.encode_pdu(ber.GET_REQUEST, 1, [SYS_NAME])))
    with pytest.raises(ber.BerError):
        ber.decode_pdu(ber.decode_element(ber.tlv(ber.RESPONSE, ber.encode_int(1))))


# ---------------------------------------------------------------------- USM

ENGINE = bytes.fromhex("000000000000000000000002")


@pytest.mark.parametrize(
    "protocol, key, localized",
    [
        # RFC 3414 A.3.1 and A.3.2: the password "maplesyrup".
        (
            "MD5",
            "9faf3283884e92834ebc9847d8edd963",  # pragma: allowlist secret
            "526f5eed9fcce26f8964c2930787d82b",  # pragma: allowlist secret
        ),
        (
            "SHA",
            "9fb5cc0381497b3793528939ff788d5d79145211",  # pragma: allowlist secret
            "6695febc9288e36282235fc7151f128497b38f3f",  # pragma: allowlist secret
        ),
    ],
)
def test_keys_match_rfc_3414(protocol, key, localized):
    derived = usm.password_to_key("maplesyrup", protocol)

    assert derived.hex() == key
    assert usm.localize_key(derived, ENGINE, protocol).hex() == localized


@pytest.mark.parametrize("protocol", list(usm.AUTH_PROTOCOLS))
def test_digests_are_truncated_and_verified(protocol):
    key = usm.local_keys(ENGINE, protocol, AUTH_KEY).auth_key
    digest = usm.sign(b"message", key, protocol)

    assert len(digest) == usm.digest_length(protocol)
    assert usm.verify(b"message", key, protocol, digest)
    assert not usm.verify(b"messagE", key, protocol, digest)


def test_bad_passwords_and_protocols_are_refused():
    with pytest.raises(ValueError, match="empty"):
        usm.password_to_key("", "SHA")
    with pytest.raises(ValueError, match="unknown"):
        usm.password_to_key(AUTH_KEY, "SHA3")


def test_aes_round_trips_with_the_engine_s_boots_time_and_salt():
    keys = usm.local_keys(ENGINE, "SHA", AUTH_KEY, PRIV_KEY)
    salt = bytes(range(8))
    cipher_text = usm.encrypt(b"scoped pdu", keys.priv_key, 7, 1234, salt)

    assert len(keys.priv_key) == 16
    assert cipher_text != b"scoped pdu"
    assert usm.decrypt(cipher_text, keys.priv_key, 7, 1234, salt) == b"scoped pdu"
    assert usm.decrypt(cipher_text, keys.priv_key, 7, 1235, salt) != b"scoped pdu"
    with pytest.raises(ValueError):
        usm.decrypt(cipher_text, keys.priv_key, 7, 1234, b"short")


@pytest.mark.filterwarnings("ignore:CFB has been moved")
def test_older_cryptography_without_the_decrepit_module_still_works(monkeypatch):
    monkeypatch.setitem(
        __import__("sys").modules, "cryptography.hazmat.decrepit.ciphers.modes", None
    )
    keys = usm.local_keys(ENGINE, "SHA", AUTH_KEY, PRIV_KEY)

    cipher_text = usm.encrypt(b"pdu", keys.priv_key, 1, 2, bytes(8))
    assert usm.decrypt(cipher_text, keys.priv_key, 1, 2, bytes(8)) == b"pdu"


def without_cryptography(monkeypatch):
    def unavailable(_iv):
        raise ImportError("no cryptography")

    monkeypatch.setattr(usm, "_cfb_mode", unavailable)


def test_encryption_without_cryptography_names_the_extra(monkeypatch):
    without_cryptography(monkeypatch)

    with pytest.raises(usm.PrivacyUnavailable, match=r"ipmg\[snmp\]"):
        usm.encrypt(b"pdu", bytes(16), 1, 2, bytes(8))


# -------------------------------------------------------------- credentials


def test_secrets_never_appear_in_repr():
    credentials = Credentials(
        community=SECRETS[0],
        user="ops",
        auth_key=SECRETS[1],
        priv_key=SECRETS[2],
    )

    text = repr(credentials)
    assert "ops" in text
    for secret in SECRETS:
        assert secret not in text


@pytest.mark.parametrize(
    "version, credentials, problem",
    [
        ("2c", Credentials(community=""), "community"),
        ("3", Credentials(), "user name"),
        (
            "3",
            Credentials(user="ops", priv_key=PRIV_KEY),
            "authentication key as well",
        ),
        ("3", Credentials(user="ops", auth_protocol="SHA3", auth_key="x" * 8), "SHA3"),
        ("3", Credentials(user="ops", priv_protocol="DES"), "DES"),
        ("3", Credentials(user="ops", auth_key="s" * 7), "at least 8"),
    ],
)
def test_credential_problems_are_named(version, credentials, problem):
    assert problem in "; ".join(credentials.problems(version))


def test_usable_credentials_have_no_problems():
    assert Credentials().problems("2c") == []
    assert Credentials(user="ops").problems("3") == []
    assert Credentials(user="ops", auth_key=AUTH_KEY).security_level == "authNoPriv"
    assert Credentials(user="ops", auth_key="a" * 8, priv_key="p" * 8).security_level == "authPriv"
    assert Credentials(user="ops").security_level == "noAuthNoPriv"


def test_sessions_only_speak_v2c_and_v3():
    with pytest.raises(ValueError):
        Session("127.0.0.1", version="1")


# --------------------------------------------------------------- polling v2c


def test_a_v2c_poll_reads_the_system_group_and_interfaces():
    with Agent(community="lab") as agent:
        result = poll_device("127.0.0.1", options(agent, credentials=Credentials(community="lab")))

    assert result.ok and result.failure == "" and result.error == ""
    assert (result.sys_name, result.sys_location) == ("lab-switch", "rack 3")
    assert result.sys_descr == "lab-switch software\r\nline two"
    assert result.sys_object_id == "1.3.6.1.4.1.9.1.1"
    assert result.uptime_s == 3600.0
    assert result.response_ms is not None and result.outcome == "OK"

    uplink, printer, unused = result.interfaces
    assert (uplink.name, uplink.alias, uplink.description) == (
        "Gi1/0/1",
        "Uplink",
        "GigabitEthernet1/0/1",
    )
    assert (uplink.speed_mbps, uplink.in_octets, uplink.out_octets) == (1000, 2**40 + 1, 2**39 + 1)
    assert printer.down and not uplink.down
    # Switched off is not "down": nobody expects traffic on it.
    assert unused.admin_status == "down" and not unused.down
    assert result.interfaces_up == 1
    assert result.interfaces_down == (printer,)


def test_ipv6_agents_are_polled():
    try:
        agent = Agent(host="::1")
    except OSError:
        pytest.skip("no IPv6 loopback here")
    with agent:
        result = poll_device("::1", options(agent))
    assert result.ok and result.sys_name == "lab-switch"


def test_agents_without_ifxtable_fall_back_to_iftable():
    mib = {
        oid: value for oid, value in switch_mib().items() if oid[:9] != (1, 3, 6, 1, 2, 1, 31, 1, 1)
    }
    with Agent(mib=mib) as agent:
        result = poll_device("127.0.0.1", options(agent))

    first = result.interfaces[0]
    assert (first.name, first.alias) == ("GigabitEthernet1/0/1", "")
    assert (first.speed_mbps, first.in_octets, first.out_octets) == (1000, 1000, 500)


def test_missing_system_objects_are_left_empty():
    mib = {SYS_NAME: octets("only-a-name")}
    with Agent(mib=mib) as agent:
        result = poll_device("127.0.0.1", options(agent))

    assert result.ok and result.sys_name == "only-a-name"
    assert (result.sys_descr, result.sys_object_id, result.uptime_s) == ("", "", None)
    assert result.interfaces == ()


def test_the_interface_walk_can_be_skipped():
    with Agent() as agent:
        result = poll_device("127.0.0.1", options(agent, interfaces=False))
        assert agent.received == 1
    assert result.ok and result.interfaces == ()


def test_a_wrong_community_times_out_and_says_what_to_check():
    with Agent(community="secret") as agent:
        result = poll_device(
            "127.0.0.1", options(agent, retries=1, credentials=Credentials(community="guess"))
        )
        assert agent.received == 2

    assert (result.ok, result.failure, result.outcome) == (False, FAILURE_TIMEOUT, "Failed")
    assert "community string" in result.error
    assert "guess" not in result.error and "secret" not in result.error


def test_a_closed_port_is_refused_quickly():
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()

    result = poll_device("127.0.0.1", SnmpOptions(port=port, timeout_s=2, retries=1))

    assert result.failure in (FAILURE_REFUSED, FAILURE_TIMEOUT)
    if result.failure == FAILURE_REFUSED:
        assert str(port) in result.error


def test_an_address_that_cannot_be_used_is_a_network_failure():
    result = poll_device("256.1.1.1", SnmpOptions(timeout_s=0.2, retries=0))
    assert (result.ok, result.failure) == (False, FAILURE_NETWORK)


def test_stray_and_garbled_replies_are_ignored():
    with Agent(stray_reply=True, garbage=True) as agent:
        result = poll_device("127.0.0.1", options(agent))
    assert result.ok


def test_only_garbled_replies_are_a_protocol_failure():
    with Agent(only_garbage=True) as agent:
        result = poll_device("127.0.0.1", options(agent))
    assert result.failure == FAILURE_PROTOCOL
    assert "could not be read" in result.error


def test_an_agent_error_is_reported_by_name():
    with Agent(error_status=5) as agent:
        result = poll_device("127.0.0.1", options(agent))
    assert result.failure == FAILURE_ERROR
    assert "genErr" in result.error


def test_an_unreadable_interface_table_keeps_the_system_group():
    with Agent(bulk_error=True) as agent:
        result = poll_device("127.0.0.1", options(agent))

    assert result.ok and result.sys_name == "lab-switch"
    assert result.interfaces == ()
    assert result.error.startswith("interfaces not read") and "genErr" in result.error


def test_a_walk_halves_its_batch_when_the_answer_is_too_big():
    with Agent(too_big_above=4) as agent:
        result = poll_device("127.0.0.1", options(agent))
    assert len(result.interfaces) == 3


def test_a_walk_stops_at_its_row_limit():
    columns = [(1, 3, 6, 1, 2, 1, 2, 2, 1, 2)]
    with Agent() as agent, Session("127.0.0.1", port=agent.port, timeout_s=0.5) as session:
        (table,) = bulk_walk(session, columns, max_rows=2, repetitions=1)
    assert sorted(table) == [(1,), (2,)]


def test_many_devices_are_polled_once_each_in_the_order_given():
    with Agent() as agent:
        results = poll_devices(
            ["127.0.0.1", "192.0.2.1", "127.0.0.1"], options(agent, timeout_s=0.3)
        )

    assert [(result.ip, result.ok) for result in results] == [
        ("127.0.0.1", True),
        ("192.0.2.1", False),
    ]
    assert results[1].failure in (FAILURE_TIMEOUT, FAILURE_NETWORK, FAILURE_REFUSED)
    assert poll_devices([]) == []


# ---------------------------------------------------------------- polling v3

AUTH_USERS = {
    "md5": User("MD5", AUTH_KEY),
    "sha": User("SHA", AUTH_KEY),
    "sha224": User("SHA224", AUTH_KEY),
    "sha384": User("SHA384", AUTH_KEY),
    "sha512": User("SHA512", AUTH_KEY),
    "shapriv": User("SHA", AUTH_KEY, PRIV_KEY),
    "sha256priv": User("SHA256", AUTH_KEY, PRIV_KEY),
    "noauth": User(),
}


@pytest.mark.parametrize("name", list(AUTH_USERS))
def test_v3_works_at_every_security_level(name):
    user = AUTH_USERS[name]
    credentials = v3(
        name,
        auth_protocol=user.auth_protocol or "SHA",
        auth_key=user.auth_key,
        priv_key=user.priv_key,
    )
    with Agent(users=AUTH_USERS) as agent:
        result = poll_device("127.0.0.1", options(agent, version="3", credentials=credentials))

    assert result.ok, result.error
    assert result.version == "3" and result.sys_name == "lab-switch"
    assert len(result.interfaces) == 3


def v3_poll(agent, **credentials):
    return poll_device("127.0.0.1", options(agent, version="3", credentials=v3(**credentials)))


@pytest.mark.parametrize(
    "credentials, message",
    [
        (
            {"user": "ghost", "auth_key": AUTH_KEY},
            "does not know this SNMPv3 user",
        ),
        (
            {"user": "sha", "auth_key": WRONG_AUTH_KEY},
            "wrong SNMPv3 authentication key",
        ),
        (
            {"user": "sha", "auth_protocol": "MD5", "auth_key": AUTH_KEY},
            "authentication key",
        ),
        (
            {"user": "shapriv", "auth_key": AUTH_KEY, "priv_key": WRONG_PRIV_KEY},
            "wrong SNMPv3 privacy key",
        ),
        ({"user": "shapriv", "auth_key": AUTH_KEY}, "does not allow this security level"),
    ],
)
def test_v3_rejections_say_what_was_wrong(credentials, message):
    with Agent(users=AUTH_USERS) as agent:
        result = v3_poll(agent, **credentials)

    assert (result.ok, result.failure) == (False, FAILURE_AUTH)
    assert message in result.error
    assert AUTH_KEY not in result.error and WRONG_AUTH_KEY not in result.error


def test_v3_resynchronizes_after_a_time_window_rejection():
    with Agent(users=AUTH_USERS, time_window_rejects=1) as agent:
        assert v3_poll(agent, user="sha", auth_key=AUTH_KEY).ok


def test_v3_gives_up_on_an_agent_that_keeps_rejecting_the_time():
    with Agent(users=AUTH_USERS, time_window_rejects=10) as agent:
        result = v3_poll(agent, user="sha", auth_key=AUTH_KEY)
    assert result.failure == FAILURE_AUTH and "time window" in result.error


def test_v3_rediscovers_an_engine_that_changed():
    with Agent(users=AUTH_USERS, unknown_engine_rejects=1) as agent:
        assert v3_poll(agent, user="shapriv", auth_key=AUTH_KEY, priv_key=PRIV_KEY).ok


def test_v3_refuses_a_reply_with_a_lower_security_level():
    with Agent(users=AUTH_USERS, downgrade=True) as agent:
        result = v3_poll(agent, user="sha", auth_key=AUTH_KEY)
    assert result.failure == FAILURE_AUTH and "lower security level" in result.error


def test_v3_refuses_a_reply_that_fails_authentication():
    with Agent(users=AUTH_USERS, bad_reply_digest=True) as agent:
        result = v3_poll(agent, user="sha", auth_key=AUTH_KEY)
    assert result.failure == FAILURE_AUTH and "failed authentication" in result.error


def test_v3_refuses_an_encrypted_reply_it_did_not_ask_for():
    with Agent(users=AUTH_USERS, encrypt_always=True) as agent:
        result = v3_poll(agent, user="shapriv", auth_key=AUTH_KEY)
    assert result.failure == FAILURE_PROTOCOL and "encrypted" in result.error


def test_v3_context_selects_what_the_agent_serves():
    with Agent(users=AUTH_USERS, context="vrf-blue") as agent:
        assert v3_poll(agent, user="sha", auth_key=AUTH_KEY, context="vrf-blue").ok
        result = v3_poll(agent, user="sha", auth_key=AUTH_KEY, context="vrf-red")

    assert result.failure == FAILURE_TIMEOUT
    assert "context" in result.error


def test_v3_encryption_without_cryptography_is_unsupported(monkeypatch):
    without_cryptography(monkeypatch)
    with Agent(users=AUTH_USERS) as agent:
        result = v3_poll(agent, user="shapriv", auth_key=AUTH_KEY, priv_key=PRIV_KEY)

    assert result.failure == FAILURE_UNSUPPORTED
    assert "ipmg[snmp]" in result.error
