"""Keep scan history and report files from growing without bound.

Nothing removes old data on its own: every scan adds a full set of rows to
the history database, and every ``--interval`` pass writes a new report file
per format. An ``--interval 5`` monitor writes 288 files a day until the disk
fills. These helpers let a user, or a monitor's own flags, set a limit.

Retention is opt-in. Nothing is deleted unless a flag or an ``ipmg.toml`` key
asks for it, and history pruning only ever removes whole, finished scans.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ipmg.infrastructure.incremental import REPORT_FORMATS

log = logging.getLogger(__name__)

_AGE = re.compile(r"^\s*(\d+)\s*([smhdw]?)\s*$", re.IGNORECASE)
_AGE_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 7 * 86400, "": 86400}

#: ``<prefix>_<YYYYMMDD_HHMMSS>.<format>``, as every report is named.
_REPORT_FILE = re.compile(r"^(?P<prefix>.+)_(?P<timestamp>\d{8}_\d{6})\.(?P<fmt>[a-z]+)$")


def parse_age(text: str) -> timedelta:
    """``30d``, ``12h``, ``90m``, ``2w``, or a plain number of days.

    ``m`` is minutes, not months: a month has no fixed length.
    """
    match = _AGE.match(str(text))
    if match is None:
        raise ValueError(
            f"invalid age {text!r}: use a number with s, m, h, d, or w, such as 30d or 12h"
        )
    amount, unit = int(match.group(1)), match.group(2).lower()
    return timedelta(seconds=amount * _AGE_UNITS[unit])


# ------------------------------------------------------------------ history


@dataclass(frozen=True)
class PrunePlan:
    """The stored scans a retention policy would remove."""

    scans: list[dict[str, Any]] = field(default_factory=list)

    @property
    def scan_ids(self) -> list[int]:
        return [int(scan["id"]) for scan in self.scans]

    @property
    def result_count(self) -> int:
        return sum(int(scan.get("completed") or 0) for scan in self.scans)

    def by_source(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for scan in self.scans:
            counts[scan["source"]] = counts.get(scan["source"], 0) + 1
        return counts


def plan_prune(
    scans: Sequence[dict[str, Any]],
    keep: int | None = None,
    older_than: timedelta | None = None,
    now: datetime | None = None,
) -> PrunePlan:
    """Which of ``scans`` a policy removes. ``scans`` are rows of the ``scans`` table.

    A scan is kept when any rule covers it: it is one of the ``keep`` newest of
    its source, or it started within ``older_than``. Only scans no rule keeps
    are removed, so ``--keep 10 --older-than 30d`` removes scans that are both
    beyond the newest ten and more than 30 days old. A running scan is never
    removed: its worker is still writing to it.
    """
    if keep is None and older_than is None:
        raise ValueError("a retention policy needs keep, older_than, or both")
    if keep is not None and keep < 0:
        raise ValueError("keep cannot be negative")

    cutoff = None
    if older_than is not None:
        # started_at is stored as local "YYYY-MM-DD HH:MM:SS", which sorts as text.
        cutoff = ((now or datetime.now()) - older_than).isoformat(sep=" ", timespec="seconds")

    seen: dict[str, int] = {}
    doomed: list[dict[str, Any]] = []
    for scan in sorted(scans, key=lambda row: int(row["id"]), reverse=True):
        source = scan["source"]
        rank = seen.get(source, 0)
        seen[source] = rank + 1
        if scan.get("status") == "running":
            continue
        kept_by_count = keep is not None and rank < keep
        kept_by_age = cutoff is not None and str(scan["started_at"]) >= cutoff
        if not (kept_by_count or kept_by_age):
            doomed.append(scan)
    return PrunePlan(doomed)


# ------------------------------------------------------------------ reports


def report_files(base: str, formats: Sequence[str] = REPORT_FORMATS) -> dict[str, list[Path]]:
    """Report files saved under ``base`` (the ``--output`` prefix), oldest first, per format."""
    directory = Path(base).parent
    prefix = Path(base).name
    found: dict[str, list[tuple]] = {}
    try:
        entries = list(directory.iterdir())
    except OSError:
        return {}
    for entry in entries:
        match = _REPORT_FILE.match(entry.name)
        if not match or match["prefix"] != prefix or match["fmt"] not in formats:
            continue
        if not entry.is_file():
            continue
        found.setdefault(match["fmt"], []).append((match["timestamp"], entry))
    return {fmt: [path for _ts, path in sorted(files)] for fmt, files in found.items()}


def prune_reports(
    bases: Sequence[str],
    keep: int,
    formats: Sequence[str] = REPORT_FORMATS,
    protect: str | None = None,
) -> list[str]:
    """Delete all but the ``keep`` newest report files of each format; returns the paths removed.

    Only files named exactly like an IPMG report under one of ``bases`` are
    touched. Files with the ``protect`` timestamp (the pass just written) are
    never removed, whatever ``keep`` says.
    """
    keep = max(keep, 1)
    removed: list[str] = []
    for base in dict.fromkeys(bases):
        for files in report_files(base, formats).values():
            for path in files[: max(len(files) - keep, 0)]:
                if protect and _REPORT_FILE.match(path.name)["timestamp"] == protect:
                    continue
                try:
                    path.unlink()
                except OSError as exc:
                    log.debug("could not remove old report %s: %s", path, exc)
                    continue
                removed.append(str(path))
    return removed
