"""SNMP polling of switches, routers, and other network devices (``--snmp``).

A small SNMP implementation of its own (v2c, and v3 with USM authentication
and AES privacy), so the default install needs nothing more. Only SNMPv3
encryption needs the ``cryptography`` package, from the ``snmp`` extra.

Nothing imports this package unless a scan asks for SNMP.
"""

from ipmg.core.snmp.client import (
    FAILURE_AUTH,
    FAILURE_ERROR,
    FAILURE_PROTOCOL,
    FAILURE_REFUSED,
    FAILURE_TIMEOUT,
    FAILURE_UNSUPPORTED,
    VERSIONS,
    Credentials,
    Session,
    SnmpError,
)
from ipmg.core.snmp.poller import (
    DEFAULT_PORT,
    DEFAULT_RETRIES,
    DEFAULT_TIMEOUT_S,
    FAILURE_NETWORK,
    SnmpInterface,
    SnmpOptions,
    SnmpResult,
    poll_device,
    poll_devices,
)
from ipmg.core.snmp.usm import AUTH_PROTOCOLS, PRIV_PROTOCOLS

__all__ = [
    "AUTH_PROTOCOLS",
    "DEFAULT_PORT",
    "DEFAULT_RETRIES",
    "DEFAULT_TIMEOUT_S",
    "FAILURE_AUTH",
    "FAILURE_ERROR",
    "FAILURE_NETWORK",
    "FAILURE_PROTOCOL",
    "FAILURE_REFUSED",
    "FAILURE_TIMEOUT",
    "FAILURE_UNSUPPORTED",
    "PRIV_PROTOCOLS",
    "VERSIONS",
    "Credentials",
    "Session",
    "SnmpError",
    "SnmpInterface",
    "SnmpOptions",
    "SnmpResult",
    "poll_device",
    "poll_devices",
]
