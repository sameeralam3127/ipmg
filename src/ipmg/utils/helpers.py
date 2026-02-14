import logging
import socket
from datetime import datetime
from typing import Optional


def configure_logging(verbose: bool) -> None:
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO)


def resolve_hostname(ip: str) -> str:
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return "Unresolvable"


def current_timestamp() -> datetime:
    return datetime.now()


def clamp_int(value: int, minimum: Optional[int], maximum: Optional[int]) -> int:
    if minimum is not None:
        value = max(value, minimum)

    if maximum is not None:
        value = min(value, maximum)

    return value
