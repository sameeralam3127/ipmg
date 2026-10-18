"""What ``--snmp`` asks a device: MIB-II's system group and its interfaces.

- System: sysName, sysDescr, sysObjectID, sysLocation, and sysUpTime, which
  is how a reboot shows (the uptime starts again from zero).
- Interfaces: ifTable and ifXTable, walked side by side with GETBULK: name,
  alias, admin and operational status, speed, and traffic counters (the
  64-bit ones where the agent has them).

A device that does not answer is a result, not an exception: its failure and
the reason are recorded, and the other devices are polled as usual.
"""

from __future__ import annotations

import concurrent.futures
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from ipmg.core.snmp.ber import Oid, VarBind, format_oid
from ipmg.core.snmp.client import TOO_BIG, Credentials, Session, SnmpError

DEFAULT_PORT = 161
DEFAULT_TIMEOUT_S = 2.0
DEFAULT_RETRIES = 1
#: Interfaces read per device at most; a core router can have thousands.
MAX_INTERFACES = 2048

FAILURE_NETWORK = "network"

_SYSTEM = (1, 3, 6, 1, 2, 1, 1)
SYS_DESCR = (*_SYSTEM, 1, 0)
SYS_OBJECT_ID = (*_SYSTEM, 2, 0)
SYS_UPTIME = (*_SYSTEM, 3, 0)
SYS_NAME = (*_SYSTEM, 5, 0)
SYS_LOCATION = (*_SYSTEM, 6, 0)

_IF = (1, 3, 6, 1, 2, 1, 2, 2, 1)
_IFX = (1, 3, 6, 1, 2, 1, 31, 1, 1, 1)
#: The interface columns read, by the name the code uses for them.
IF_COLUMNS: dict[str, Oid] = {
    "descr": (*_IF, 2),
    "speed": (*_IF, 5),
    "admin": (*_IF, 7),
    "oper": (*_IF, 8),
    "in32": (*_IF, 10),
    "out32": (*_IF, 16),
    "name": (*_IFX, 1),
    "in64": (*_IFX, 6),
    "out64": (*_IFX, 10),
    "high_speed": (*_IFX, 15),
    "alias": (*_IFX, 18),
}

ADMIN_STATUS = {1: "up", 2: "down", 3: "testing"}
OPER_STATUS = {
    1: "up",
    2: "down",
    3: "testing",
    4: "unknown",
    5: "dormant",
    6: "notPresent",
    7: "lowerLayerDown",
}
#: Operational states that mean an enabled interface is not passing traffic.
DOWN_STATES = frozenset({"down", "notPresent", "lowerLayerDown"})

_BULK_REPETITIONS = 16
_MAX_WALK_REQUESTS = 512


@dataclass(frozen=True)
class SnmpOptions:
    version: str = "2c"
    port: int = DEFAULT_PORT
    timeout_s: float = DEFAULT_TIMEOUT_S
    retries: int = DEFAULT_RETRIES
    #: Walk the interface tables as well as the system group.
    interfaces: bool = True
    credentials: Credentials = field(default_factory=Credentials)

    def clamped(self) -> SnmpOptions:
        return replace(
            self,
            port=min(max(int(self.port), 1), 65535),
            timeout_s=min(max(float(self.timeout_s), 0.1), 60.0),
            retries=min(max(int(self.retries), 0), 5),
        )


@dataclass(frozen=True)
class SnmpInterface:
    index: int
    #: ifName where the agent has it, else ifDescr.
    name: str
    description: str = ""
    alias: str = ""
    admin_status: str = ""
    oper_status: str = ""
    speed_mbps: int | None = None
    in_octets: int | None = None
    out_octets: int | None = None

    @property
    def down(self) -> bool:
        """Enabled, but not passing traffic: an unplugged cable, a dead uplink."""
        return self.admin_status == "up" and self.oper_status in DOWN_STATES


@dataclass(frozen=True)
class SnmpResult:
    """One device's poll."""

    ip: str
    ok: bool
    version: str = "2c"
    sys_name: str = ""
    sys_descr: str = ""
    sys_object_id: str = ""
    sys_location: str = ""
    #: Seconds since the agent (re)started, from sysUpTime.
    uptime_s: float | None = None
    interfaces: tuple[SnmpInterface, ...] = ()
    response_ms: float | None = None
    #: ``timeout``, ``refused``, ``auth``, ...; "" when the device answered.
    failure: str = ""
    #: Why it failed, or a note about a partial answer (an unreadable interface table).
    error: str = ""

    @property
    def outcome(self) -> str:
        return "OK" if self.ok else "Failed"

    @property
    def interfaces_up(self) -> int:
        return sum(1 for interface in self.interfaces if interface.oper_status == "up")

    @property
    def interfaces_down(self) -> tuple[SnmpInterface, ...]:
        return tuple(interface for interface in self.interfaces if interface.down)


# ------------------------------------------------------------------ helpers


def _text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").replace("\x00", "").strip()
    return "" if value is None else str(value).strip()


def _number(varbind: VarBind | None) -> int | None:
    if varbind is None or varbind.missing or not isinstance(varbind.value, int):
        return None
    return varbind.value


def _values(varbinds: Iterable[VarBind]) -> dict[Oid, VarBind]:
    return {varbind.oid: varbind for varbind in varbinds if not varbind.missing}


def bulk_walk(
    session: Session,
    columns: Sequence[Oid],
    max_rows: int = MAX_INTERFACES,
    repetitions: int = _BULK_REPETITIONS,
) -> list[dict[Oid, VarBind]]:
    """Walk table columns side by side; for each column, {row index: varbind}."""
    tables: list[dict[Oid, VarBind]] = [{} for _ in columns]
    last = list(columns)
    active = list(range(len(columns)))
    for _request in range(_MAX_WALK_REQUESTS):
        if not active:
            break
        try:
            varbinds = session.get_bulk([last[column] for column in active], repetitions)
        except SnmpError as exc:
            if exc.status != TOO_BIG or repetitions == 1:
                raise
            repetitions //= 2
            continue
        if not varbinds:
            break
        active = _absorb(varbinds, active, columns, last, tables, max_rows)
    return tables


def _absorb(
    varbinds: Sequence[VarBind],
    active: list[int],
    columns: Sequence[Oid],
    last: list[Oid],
    tables: list[dict[Oid, VarBind]],
    max_rows: int,
) -> list[int]:
    """File one GETBULK answer under its columns; return the columns still going.

    The answer repeats the requested columns in order, so position modulo
    their count says which column a varbind belongs to. A column is finished
    when its walk leaves the column, ends, stops moving forward, or is full.
    """
    finished: set[int] = set()
    for position, varbind in enumerate(varbinds):
        column = active[position % len(active)]
        if column in finished:
            continue
        prefix = columns[column]
        if varbind.missing or varbind.oid[: len(prefix)] != prefix or varbind.oid <= last[column]:
            finished.add(column)
            continue
        tables[column][varbind.oid[len(prefix) :]] = varbind
        last[column] = varbind.oid
        if len(tables[column]) >= max_rows:
            finished.add(column)
    return [column for column in active if column not in finished]


def _system(session: Session) -> dict[str, Any]:
    found = _values(session.get([SYS_NAME, SYS_DESCR, SYS_OBJECT_ID, SYS_LOCATION, SYS_UPTIME]))
    uptime = _number(found.get(SYS_UPTIME))
    object_id = found.get(SYS_OBJECT_ID)
    return {
        "sys_name": _text(found[SYS_NAME].value) if SYS_NAME in found else "",
        "sys_descr": _text(found[SYS_DESCR].value) if SYS_DESCR in found else "",
        "sys_object_id": format_oid(object_id.value)
        if object_id is not None and isinstance(object_id.value, tuple)
        else "",
        "sys_location": _text(found[SYS_LOCATION].value) if SYS_LOCATION in found else "",
        # TimeTicks are hundredths of a second.
        "uptime_s": uptime / 100 if uptime is not None else None,
    }


def _interface(index: int, row: dict[str, VarBind]) -> SnmpInterface:
    def value(column: str) -> Any:
        varbind = row.get(column)
        return None if varbind is None or varbind.missing else varbind.value

    high_speed = _number(row.get("high_speed"))
    speed = _number(row.get("speed"))
    in_octets = _number(row.get("in64"))
    out_octets = _number(row.get("out64"))
    description = _text(value("descr"))
    return SnmpInterface(
        index=index,
        name=_text(value("name")) or description or f"ifIndex {index}",
        description=description,
        alias=_text(value("alias")),
        admin_status=ADMIN_STATUS.get(_number(row.get("admin")) or 0, ""),
        oper_status=OPER_STATUS.get(_number(row.get("oper")) or 0, ""),
        # ifSpeed tops out at 4.29 Gbit/s; ifHighSpeed is already in Mbit/s.
        speed_mbps=high_speed if high_speed else (round(speed / 1e6) if speed else None),
        in_octets=in_octets if in_octets is not None else _number(row.get("in32")),
        out_octets=out_octets if out_octets is not None else _number(row.get("out32")),
    )


def _interfaces(session: Session) -> tuple[SnmpInterface, ...]:
    names = list(IF_COLUMNS)
    tables = bulk_walk(session, [IF_COLUMNS[name] for name in names])
    rows: dict[int, dict[str, VarBind]] = {}
    for name, table in zip(names, tables):
        for index, varbind in table.items():
            if len(index) == 1:
                rows.setdefault(index[0], {})[name] = varbind
    return tuple(_interface(index, rows[index]) for index in sorted(rows))


# ------------------------------------------------------------------ polling


def _failed(ip: str, options: SnmpOptions, failure: str, error: str) -> SnmpResult:
    return SnmpResult(ip=ip, ok=False, version=options.version, failure=failure, error=error)


def poll_device(ip: str, options: SnmpOptions | None = None) -> SnmpResult:
    """Poll one device. Never raises: a device that does not answer is a result."""
    options = (options or SnmpOptions()).clamped()
    started = time.perf_counter()
    try:
        session = Session(
            ip,
            port=options.port,
            version=options.version,
            credentials=options.credentials,
            timeout_s=options.timeout_s,
            retries=options.retries,
        )
    except OSError as exc:
        return _failed(ip, options, FAILURE_NETWORK, str(exc) or type(exc).__name__)
    with session:
        try:
            system = _system(session)
        except SnmpError as exc:
            return _failed(ip, options, exc.failure, str(exc))
        except OSError as exc:
            # Unreachable networks and hosts, refused sends the OS will not route.
            return _failed(ip, options, FAILURE_NETWORK, str(exc) or type(exc).__name__)
        response_ms = round((time.perf_counter() - started) * 1000, 3)
        interfaces: tuple[SnmpInterface, ...] = ()
        note = ""
        if options.interfaces:
            try:
                interfaces = _interfaces(session)
            except (SnmpError, OSError) as exc:
                note = f"interfaces not read: {exc}"
    return SnmpResult(
        ip=ip,
        ok=True,
        version=options.version,
        interfaces=interfaces,
        response_ms=response_ms,
        error=note,
        **system,
    )


def poll_devices(
    ips: Iterable[str],
    options: SnmpOptions | None = None,
    max_workers: int = 50,
) -> list[SnmpResult]:
    """Poll every device concurrently (at most ``max_workers`` at once), in the order given."""
    ips = list(dict.fromkeys(ips))
    if not ips:
        return []
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=max(1, min(max_workers, len(ips))), thread_name_prefix="ipmg-snmp"
    ) as pool:
        return list(pool.map(lambda ip: poll_device(ip, options), ips))
