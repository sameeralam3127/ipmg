"""SNMPv3 user-based security (USM): keys, authentication, and privacy.

- Keys: RFC 3414 A.2. A password is stretched to a key by hashing a megabyte
  of it, then localized to one agent by hashing it with that agent's engine ID.
- Authentication: HMAC-MD5-96 and HMAC-SHA-96 (RFC 3414), and the SHA-2
  variants of RFC 7860, each truncated to the length the RFCs give.
- Privacy: AES-128 in CFB mode (RFC 3826). DES is not offered: it has been
  broken for decades, and agents that support only DES should be upgraded.

Encryption comes from the ``cryptography`` package, the ``snmp`` extra. It is
imported only when a message is actually encrypted or decrypted, so v2c and
authentication-only v3 work without it.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from functools import lru_cache

#: Authentication protocol: (hashlib name, bytes of the HMAC that are sent).
AUTH_PROTOCOLS: dict[str, tuple[str, int]] = {
    "MD5": ("md5", 12),
    "SHA": ("sha1", 12),
    "SHA224": ("sha224", 16),
    "SHA256": ("sha256", 24),
    "SHA384": ("sha384", 32),
    "SHA512": ("sha512", 48),
}
PRIV_PROTOCOLS = ("AES",)

#: How much of the repeated password is hashed into a key (RFC 3414 A.2).
_STRETCH_BYTES = 1_048_576
#: AES-128 keys and the AES block, which the IV fills.
_AES_KEY_BYTES = 16

PRIVACY_EXTRA_MISSING = (
    "SNMPv3 encryption needs the 'cryptography' package, which this install does not "
    "have. Install IPMG with the snmp extra, as in pip install 'ipmg[snmp]' or "
    "uv tool install --force 'ipmg[web,snmp]'."
)


class PrivacyUnavailable(RuntimeError):
    """``cryptography`` is not installed, so messages cannot be encrypted."""


@lru_cache(maxsize=8)
def password_to_key(password: str, protocol: str) -> bytes:
    """RFC 3414 A.2.1: the user's key, before it is localized to an engine.

    Hashing a megabyte takes a few milliseconds, and every device in a scan
    uses the same password, so the result is kept.
    """
    data = password.encode("utf-8")
    if not data:
        raise ValueError("an SNMPv3 password cannot be empty")
    repeated = data * (_STRETCH_BYTES // len(data) + 1)
    # A key derivation the RFC fixes, not a choice of hash for new security.
    return hashlib.new(_hash(protocol), repeated[:_STRETCH_BYTES]).digest()


def localize_key(key: bytes, engine_id: bytes, protocol: str) -> bytes:
    """RFC 3414 A.2.2: a key that is only valid for one agent's engine ID."""
    return hashlib.new(_hash(protocol), key + engine_id + key).digest()


def _hash(protocol: str) -> str:
    try:
        return AUTH_PROTOCOLS[protocol][0]
    except KeyError:
        raise ValueError(f"unknown SNMPv3 authentication protocol {protocol!r}") from None


def digest_length(protocol: str) -> int:
    return AUTH_PROTOCOLS[protocol][1]


def sign(message: bytes, key: bytes, protocol: str) -> bytes:
    """The truncated HMAC that goes in msgAuthenticationParameters."""
    mac = hmac.new(key, message, _hash(protocol)).digest()
    return mac[: digest_length(protocol)]


def verify(message: bytes, key: bytes, protocol: str, received: bytes) -> bool:
    return hmac.compare_digest(sign(message, key, protocol), received)


@dataclass(frozen=True)
class LocalKeys:
    """One user's keys, localized to one agent."""

    auth_protocol: str
    auth_key: bytes
    priv_key: bytes = b""


def local_keys(
    engine_id: bytes,
    auth_protocol: str,
    auth_password: str,
    priv_password: str | None = None,
) -> LocalKeys:
    """The keys to talk to one engine. The privacy key uses the auth hash (RFC 3826 1.2)."""
    auth_key = localize_key(password_to_key(auth_password, auth_protocol), engine_id, auth_protocol)
    priv_key = b""
    if priv_password:
        localized = localize_key(
            password_to_key(priv_password, auth_protocol), engine_id, auth_protocol
        )
        priv_key = localized[:_AES_KEY_BYTES]
    return LocalKeys(auth_protocol, auth_key, priv_key)


def _aes_iv(boots: int, engine_time: int, salt: bytes) -> bytes:
    """RFC 3826 3.1.2.1: the engine's boots and time, then the 64-bit salt."""
    return boots.to_bytes(4, "big") + engine_time.to_bytes(4, "big") + salt


def _cfb_mode(iv: bytes):
    """AES-CFB, which newer ``cryptography`` releases keep under ``decrepit``.

    CFB is only "decrepit" for new designs; RFC 3826 fixes it for SNMPv3.
    """
    try:
        from cryptography.hazmat.decrepit.ciphers.modes import CFB
    except ImportError:
        from cryptography.hazmat.primitives.ciphers.modes import CFB
    return CFB(iv)


def _cfb(key: bytes, iv: bytes, data: bytes, encrypt: bool) -> bytes:
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms

        mode = _cfb_mode(iv)
    except ImportError as exc:
        raise PrivacyUnavailable(PRIVACY_EXTRA_MISSING) from exc
    cipher = Cipher(algorithms.AES(key), mode)
    worker = cipher.encryptor() if encrypt else cipher.decryptor()
    return worker.update(data) + worker.finalize()


def encrypt(plain: bytes, key: bytes, boots: int, engine_time: int, salt: bytes) -> bytes:
    return _cfb(key, _aes_iv(boots, engine_time, salt), plain, encrypt=True)


def decrypt(cipher_text: bytes, key: bytes, boots: int, engine_time: int, salt: bytes) -> bytes:
    if len(salt) != 8:
        raise ValueError("the privacy parameters of an AES message are 8 bytes")
    return _cfb(key, _aes_iv(boots, engine_time, salt), cipher_text, encrypt=False)
