"""A scan's SNMP settings: the flags, the environment, and the config file.

The flags say how to poll (``--snmp-version``, ``--snmp-timeout``...). The
credentials come only from environment variables or the ``[snmp-credentials]``
table of a config file, never from a flag, so they never reach a process
listing, shell history, or the scan settings stored with each scan. The
environment wins over the file.

This module is apart from :mod:`ipmg.core.snmp` so the parser can show these
defaults without loading the SNMP code, which only ``--snmp`` imports.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from ipmg.exceptions import ConfigError

if TYPE_CHECKING:
    from ipmg.core.snmp import SnmpOptions

VERSIONS = ("2c", "3")
DEFAULT_PORT = 161
DEFAULT_TIMEOUT_S = 2.0
DEFAULT_RETRIES = 1
MAX_RETRIES = 5
#: Used when no community string is configured, as most tools do.
DEFAULT_COMMUNITY = "public"

#: The config-file table that holds the credentials.
CREDENTIALS_TABLE = "snmp-credentials"

ENV_COMMUNITY = "IPMG_SNMP_COMMUNITY"
ENV_USER = "IPMG_SNMP_USER"
ENV_AUTH_PROTOCOL = "IPMG_SNMP_AUTH_PROTOCOL"
ENV_AUTH_KEY = "IPMG_SNMP_AUTH_KEY"  # pragma: allowlist secret
ENV_PRIV_PROTOCOL = "IPMG_SNMP_PRIV_PROTOCOL"
ENV_PRIV_KEY = "IPMG_SNMP_PRIV_KEY"  # pragma: allowlist secret
ENV_CONTEXT = "IPMG_SNMP_CONTEXT"

#: Config key -> (Credentials field, environment variable).
FIELDS: dict[str, tuple[str, str]] = {
    "community": ("community", ENV_COMMUNITY),
    "user": ("user", ENV_USER),
    "auth-protocol": ("auth_protocol", ENV_AUTH_PROTOCOL),
    "auth-key": ("auth_key", ENV_AUTH_KEY),
    "priv-protocol": ("priv_protocol", ENV_PRIV_PROTOCOL),
    "priv-key": ("priv_key", ENV_PRIV_KEY),
    "context": ("context", ENV_CONTEXT),
}

#: Other spellings people use for the protocols, as RFCs and vendors write them.
_PROTOCOL_ALIASES = {
    "SHA1": "SHA",
    "SHA-1": "SHA",
    "SHA-224": "SHA224",
    "SHA-256": "SHA256",
    "SHA-384": "SHA384",
    "SHA-512": "SHA512",
    "AES128": "AES",
    "AES-128": "AES",
}


def _protocol(value: str) -> str:
    text = value.strip().upper()
    return _PROTOCOL_ALIASES.get(text, text)


def credential_values(
    table: Mapping[str, Any], environ: Mapping[str, str]
) -> tuple[dict[str, str], dict[str, str]]:
    """The credentials, and where each came from (``environment`` or ``config file``)."""
    unknown = sorted(set(table) - set(FIELDS))
    if unknown:
        raise ConfigError(
            f"Unknown key in [{CREDENTIALS_TABLE}]: {', '.join(unknown)}. "
            f"The keys are {', '.join(FIELDS)}."
        )
    values: dict[str, str] = {}
    origins: dict[str, str] = {}
    for key, (name, env) in FIELDS.items():
        from_env = environ.get(env, "").strip()
        from_file = table.get(key, "")
        if not isinstance(from_file, str):
            raise ConfigError(f"'{key}' in [{CREDENTIALS_TABLE}] must be a string.")
        value = from_env or from_file.strip()
        if not value:
            continue
        values[name] = _protocol(value) if name.endswith("_protocol") else value
        origins[name] = "environment" if from_env else "config file"
    return values, origins


def snmp_options(args, environ: Mapping[str, str] | None = None) -> SnmpOptions | None:
    """The scan's SNMP options, or None without ``--snmp``.

    The SNMP code is imported here, and only for a scan that asked for it.
    """
    if not getattr(args, "snmp", False):
        return None
    from ipmg.core.snmp import Credentials, SnmpOptions

    values, _origins = credential_values(
        getattr(args, "snmp_credentials", None) or {},
        os.environ if environ is None else environ,
    )
    credentials = Credentials(**values)
    version = getattr(args, "snmp_version", None) or "2c"
    problems = credentials.problems(version)
    if problems:
        raise ConfigError(
            f"--snmp-version {version}: {'; '.join(problems)}. Set the credentials with "
            f"the {ENV_USER}, {ENV_AUTH_KEY}, and {ENV_PRIV_KEY} environment variables, "
            f"or in the [{CREDENTIALS_TABLE}] table of your config file."
        )
    return SnmpOptions(
        version=version,
        port=getattr(args, "snmp_port", DEFAULT_PORT),
        timeout_s=float(getattr(args, "snmp_timeout", DEFAULT_TIMEOUT_S)),
        retries=int(getattr(args, "snmp_retries", DEFAULT_RETRIES)),
        interfaces=not bool(getattr(args, "snmp_no_interfaces", False)),
        credentials=credentials,
    ).clamped()


def describe_credentials(args, environ: Mapping[str, str] | None = None) -> str:
    """Which credentials a scan uses, for the Config line, without any secret."""
    values, origins = credential_values(
        getattr(args, "snmp_credentials", None) or {},
        os.environ if environ is None else environ,
    )
    if (getattr(args, "snmp_version", None) or "2c") != "3":
        origin = origins.get("community")
        return f"community from the {origin}" if origin else f"community {DEFAULT_COMMUNITY}"
    level = "noAuthNoPriv"
    if values.get("auth_key"):
        protocols = values.get("auth_protocol", "SHA")
        level = "authNoPriv"
        if values.get("priv_key"):
            level = "authPriv"
            protocols += f", {values.get('priv_protocol', 'AES')}"
        level += f" ({protocols})"
    context = values.get("context")
    return f"user {values.get('user', '?')}, {level}" + (f", context {context}" if context else "")
