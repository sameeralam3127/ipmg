"""``--snmp`` against real agents: net-snmp's snmpd and snmpsim (pysnmp).

The other SNMP tests use an agent built on IPMG's own encoding, which cannot
show that IPMG speaks SNMP the way everyone else does. These start two
independent implementations on loopback and poll them at every security
level IPMG offers.

They are skipped where an agent is not installed. The SNMP job in CI sets
``IPMG_SNMP_AGENT_TESTS=require``, which turns a missing agent into a
failure, so the job cannot pass by skipping everything.
"""

import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest

from ipmg.core.snmp import FAILURE_AUTH, FAILURE_TIMEOUT, Credentials, SnmpOptions, poll_device

REQUIRED = os.environ.get("IPMG_SNMP_AGENT_TESTS") == "require"
AUTH_KEY = "authpass123"  # pragma: allowlist secret
PRIV_KEY = "privpass123"  # pragma: allowlist secret
WRONG_KEY = "wrongpass99"  # pragma: allowlist secret


def unavailable(reason):
    if REQUIRED:
        pytest.fail(f"{reason}, and IPMG_SNMP_AGENT_TESTS=require")
    pytest.skip(reason)


def free_udp_port():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def wait_until_answering(port, community, process, log):
    # snmpsim indexes its data files before it listens, which can take a while.
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            break
        result = poll_device(
            "127.0.0.1",
            SnmpOptions(
                port=port,
                timeout_s=0.5,
                retries=0,
                interfaces=False,
                credentials=Credentials(community=community),
            ),
        )
        if result.ok:
            return
        time.sleep(0.2)
    process.kill()
    unavailable(f"the agent did not start: {log.read_text()[-1500:] if log.exists() else ''}")


def stop(process):
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


# ------------------------------------------------------------------- agents

NET_SNMP_CONFIG = """\
agentAddress udp:127.0.0.1:{port}
rocommunity ipmgtest 127.0.0.1
createUser noauthuser
createUser authuser SHA "{auth}"
createUser privuser SHA "{auth}" AES "{priv}"
createUser md5priv MD5 "{auth}" AES "{priv}"
rouser noauthuser noauth
rouser authuser auth
rouser privuser priv
rouser md5priv priv
sysName ipmg-net-snmp
sysLocation ipmg lab
"""


@pytest.fixture(scope="module")
def net_snmp(tmp_path_factory):
    snmpd = shutil.which("snmpd") or next(
        (path for path in ("/usr/sbin/snmpd", "/usr/local/sbin/snmpd") if Path(path).exists()),
        None,
    )
    if snmpd is None:
        unavailable("net-snmp's snmpd is not installed")
    folder = tmp_path_factory.mktemp("net-snmp")
    port = free_udp_port()
    conf = folder / "snmpd.conf"
    conf.write_text(NET_SNMP_CONFIG.format(port=port, auth=AUTH_KEY, priv=PRIV_KEY))
    (folder / "persist").mkdir()
    log = folder / "snmpd.log"
    process = subprocess.Popen(
        # The address is in the config; giving it here as well binds it twice.
        [snmpd, "-f", "-r", "-C", "-c", str(conf), "-Lf", str(log)],
        env={**os.environ, "SNMP_PERSISTENT_DIR": str(folder / "persist")},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    wait_until_answering(port, "ipmgtest", process, log)
    yield {"port": port, "community": "ipmgtest", "name": "ipmg-net-snmp", "context": ""}
    stop(process)


SIM_RECORDS = """\
1.3.6.1.2.1.1.1.0|4|Simulated switch
1.3.6.1.2.1.1.3.0|67|123456789
1.3.6.1.2.1.1.5.0|4|ipmg-snmpsim
1.3.6.1.2.1.2.2.1.2.1|4|GigabitEthernet1/0/1
1.3.6.1.2.1.2.2.1.2.2|4|GigabitEthernet1/0/2
1.3.6.1.2.1.2.2.1.7.1|2|1
1.3.6.1.2.1.2.2.1.7.2|2|1
1.3.6.1.2.1.2.2.1.8.1|2|1
1.3.6.1.2.1.2.2.1.8.2|2|2
1.3.6.1.2.1.31.1.1.1.1.1|4|Gi1/0/1
1.3.6.1.2.1.31.1.1.1.1.2|4|Gi1/0/2
1.3.6.1.2.1.31.1.1.1.6.1|70|98765432109876
1.3.6.1.2.1.31.1.1.1.15.1|66|1000
1.3.6.1.2.1.31.1.1.1.18.1|4|Uplink to core
"""


@pytest.fixture(scope="module")
def snmpsim(tmp_path_factory):
    responder = shutil.which("snmpsim-command-responder")
    if responder is None:
        unavailable("snmpsim is not installed")
    folder = tmp_path_factory.mktemp("snmpsim")
    (folder / "data").mkdir()
    # snmpsim serves a data file per community, and per v3 context.
    (folder / "data" / "ipmgsim.snmprec").write_text(SIM_RECORDS)
    port = free_udp_port()
    users = [
        ("simmd5", "MD5", None),
        ("simsha512", "SHA512", None),
        ("simsha", "SHA", "AES"),
        ("simsha256", "SHA256", "AES"),
    ]
    command = [
        responder,
        "--v3-engine-id=auto",
        f"--data-dir={folder / 'data'}",
        f"--agent-udpv4-endpoint=127.0.0.1:{port}",
    ]
    for name, auth, priv in users:
        command += [f"--v3-user={name}", f"--v3-auth-key={AUTH_KEY}", f"--v3-auth-proto={auth}"]
        if priv:
            command += [f"--v3-priv-key={PRIV_KEY}", f"--v3-priv-proto={priv}"]
    log = folder / "snmpsim.log"
    with log.open("w") as handle:
        process = subprocess.Popen(command, stdout=handle, stderr=subprocess.STDOUT)
    wait_until_answering(port, "ipmgsim", process, log)
    yield {"port": port, "community": "ipmgsim", "name": "ipmg-snmpsim", "context": "ipmgsim"}
    stop(process)


AGENTS = ["net_snmp", "snmpsim"]

#: Users each agent has, by security level: (user, auth protocol, privacy?).
USERS = {
    "net_snmp": [
        ("noauthuser", None, False),
        ("authuser", "SHA", False),
        ("privuser", "SHA", True),
        ("md5priv", "MD5", True),
    ],
    "snmpsim": [
        ("simmd5", "MD5", False),
        ("simsha512", "SHA512", False),
        ("simsha", "SHA", True),
        ("simsha256", "SHA256", True),
    ],
}


def poll(agent, version="2c", **credentials):
    credentials.setdefault("community", agent["community"])
    if version == "3":
        credentials.setdefault("context", agent["context"])
    return poll_device(
        "127.0.0.1",
        SnmpOptions(
            version=version,
            port=agent["port"],
            timeout_s=2,
            retries=1,
            credentials=Credentials(**credentials),
        ),
    )


# -------------------------------------------------------------------- tests


@pytest.mark.parametrize("name", AGENTS)
def test_v2c_reads_the_system_group_and_interfaces(request, name):
    agent = request.getfixturevalue(name)
    result = poll(agent)

    assert result.ok, result.error
    assert result.sys_name == agent["name"]
    assert result.uptime_s is not None and result.uptime_s >= 0
    assert result.interfaces
    assert all(interface.name for interface in result.interfaces)


def test_snmpsim_interfaces_come_through_intact(snmpsim):
    result = poll(snmpsim)

    uplink, printer = result.interfaces
    assert (uplink.name, uplink.alias, uplink.speed_mbps) == ("Gi1/0/1", "Uplink to core", 1000)
    assert uplink.in_octets == 98765432109876
    assert printer.down and result.interfaces_down == (printer,)
    assert result.uptime_s == pytest.approx(1234567.89)


@pytest.mark.parametrize("name", AGENTS)
def test_a_wrong_community_gets_no_answer(request, name):
    agent = request.getfixturevalue(name)
    result = poll(agent, community="not-the-community")

    if result.ok and name == "net_snmp" and not REQUIRED:
        pytest.skip("this snmpd runs without access control (an unprivileged macOS build)")
    assert result.failure == FAILURE_TIMEOUT


@pytest.mark.parametrize(
    "name, user, auth, private",
    [(name, *user) for name in AGENTS for user in USERS[name]],
)
def test_v3_at_every_security_level(request, name, user, auth, private):
    agent = request.getfixturevalue(name)
    credentials = {"user": user}
    if auth:
        credentials.update(auth_protocol=auth, auth_key=AUTH_KEY)
    if private:
        credentials.update(priv_key=PRIV_KEY)

    result = poll(agent, version="3", **credentials)

    assert result.ok, result.error
    assert result.sys_name == agent["name"] and result.interfaces


@pytest.mark.parametrize("name", AGENTS)
def test_v3_refuses_a_wrong_authentication_key(request, name):
    agent = request.getfixturevalue(name)
    user, auth, _private = USERS[name][1]

    result = poll(agent, version="3", user=user, auth_protocol=auth, auth_key=WRONG_KEY)
    assert result.failure == FAILURE_AUTH
    assert "authentication key" in result.error


@pytest.mark.parametrize("name", AGENTS)
def test_v3_refuses_an_unknown_user(request, name):
    agent = request.getfixturevalue(name)

    result = poll(agent, version="3", user="nobody-here", auth_key=AUTH_KEY)
    assert result.failure == FAILURE_AUTH
    assert "does not know this SNMPv3 user" in result.error


@pytest.mark.parametrize("name", AGENTS)
def test_v3_refuses_a_wrong_privacy_key(request, name):
    agent = request.getfixturevalue(name)
    user, auth, _private = USERS[name][2]

    result = poll(
        agent,
        version="3",
        user=user,
        auth_protocol=auth,
        auth_key=AUTH_KEY,
        priv_key=WRONG_KEY,
    )
    # snmpsim reports a decryption error; net-snmp drops what it cannot decrypt.
    assert result.failure in (FAILURE_AUTH, FAILURE_TIMEOUT)
    assert not result.ok
