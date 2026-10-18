"""Five-field cron expressions, for scheduled scans in IPMG Web.

``minute hour day-of-month month day-of-week``, as in crontab(5):

* ``*``, a number, a range ``a-b``, a step ``*/n`` or ``a-b/n``, and lists
  of those separated by commas;
* month and weekday names (``jan``, ``mon``); weekday 0 and 7 are Sunday;
* ``@hourly``, ``@daily``, ``@weekly``, ``@monthly``, ``@yearly``.

As in Vixie cron, when both day-of-month and day-of-week are restricted, a
day matching either one matches. Times are local, like every other time
IPMG stores.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import FrozenSet, Optional, Tuple

_MACROS = {
    "@hourly": "0 * * * *",
    "@daily": "0 0 * * *",
    "@midnight": "0 0 * * *",
    "@weekly": "0 0 * * 0",
    "@monthly": "0 0 1 * *",
    "@yearly": "0 0 1 1 *",
    "@annually": "0 0 1 1 *",
}
_MONTHS = {
    name: number
    for number, name in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"],
        start=1,
    )
}
_WEEKDAYS = {
    name: number for number, name in enumerate(["sun", "mon", "tue", "wed", "thu", "fri", "sat"])
}

#: How far ahead to look for a match before calling an expression impossible
#: (``0 0 30 2 *``, February 30th, never comes).
_SEARCH_YEARS = 5


def _value(text: str, names: dict, low: int, high: int, field: str) -> int:
    text = text.strip().lower()
    if text in names:
        return names[text]
    try:
        number = int(text)
    except ValueError:
        raise ValueError(f"invalid {field} {text!r}") from None
    if not low <= number <= high:
        raise ValueError(f"{field} {number} is outside {low}-{high}")
    return number


def _field(
    text: str, low: int, high: int, field: str, names: Optional[dict] = None
) -> FrozenSet[int]:
    names = names or {}
    values = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            raise ValueError(f"empty item in {field} {text!r}")
        base, _, step_text = part.partition("/")
        step = 1
        if step_text:
            try:
                step = int(step_text)
            except ValueError:
                raise ValueError(f"invalid step {step_text!r} in {field}") from None
            if step < 1:
                raise ValueError(f"the step in {field} must be at least 1")
        if base == "*":
            start, end = low, high
        elif "-" in base:
            first, _, last = base.partition("-")
            start = _value(first, names, low, high, field)
            end = _value(last, names, low, high, field)
            if start > end:
                raise ValueError(f"{field} range {base!r} runs backwards")
        else:
            start = _value(base, names, low, high, field)
            # "5/15" means from 5 to the end, every 15.
            end = high if step_text else start
        values.update(range(start, end + 1, step))
    return frozenset(values)


@dataclass(frozen=True)
class CronSchedule:
    expression: str
    minutes: FrozenSet[int]
    hours: FrozenSet[int]
    days: FrozenSet[int]
    months: FrozenSet[int]
    weekdays: FrozenSet[int]
    #: Whether day-of-month and day-of-week were restricted (not ``*``).
    day_restricted: bool
    weekday_restricted: bool

    def _day_matches(self, moment: datetime) -> bool:
        weekday = (moment.weekday() + 1) % 7  # cron counts from Sunday = 0
        day_ok = moment.day in self.days
        weekday_ok = weekday in self.weekdays
        if self.day_restricted and self.weekday_restricted:
            return day_ok or weekday_ok
        return day_ok and weekday_ok

    def matches(self, moment: datetime) -> bool:
        return (
            moment.minute in self.minutes
            and moment.hour in self.hours
            and moment.month in self.months
            and self._day_matches(moment)
        )

    def next_after(self, moment: datetime) -> datetime:
        """The first matching minute strictly after ``moment``."""
        candidate = moment.replace(second=0, microsecond=0) + timedelta(minutes=1)
        limit = candidate + timedelta(days=366 * _SEARCH_YEARS)
        while candidate < limit:
            if candidate.month not in self.months:
                year = candidate.year + candidate.month // 12
                candidate = candidate.replace(
                    year=year, month=candidate.month % 12 + 1, day=1, hour=0, minute=0
                )
                continue
            if not self._day_matches(candidate):
                candidate = (candidate + timedelta(days=1)).replace(hour=0, minute=0)
                continue
            if candidate.hour not in self.hours:
                candidate = (candidate + timedelta(hours=1)).replace(minute=0)
                continue
            if candidate.minute not in self.minutes:
                candidate += timedelta(minutes=1)
                continue
            return candidate
        raise ValueError(f"{self.expression!r} never matches a date")


def parse_cron(expression: str) -> CronSchedule:
    """Parse a cron expression; raises ValueError naming what is wrong."""
    text = " ".join(str(expression).split())
    fields = _MACROS.get(text.lower(), text).split(" ")
    if len(fields) != 5:
        raise ValueError(
            "a cron expression has five fields: minute hour day-of-month month day-of-week, "
            "as in '*/15 * * * *'"
        )
    minute, hour, day, month, weekday = fields
    weekdays = _field(weekday, 0, 7, "day of week", _WEEKDAYS)
    schedule = CronSchedule(
        expression=text,
        minutes=_field(minute, 0, 59, "minute"),
        hours=_field(hour, 0, 23, "hour"),
        days=_field(day, 1, 31, "day of month"),
        months=_field(month, 1, 12, "month", _MONTHS),
        # 7 is Sunday too.
        weekdays=frozenset(value % 7 for value in weekdays),
        day_restricted=not day.startswith("*"),
        weekday_restricted=not weekday.startswith("*"),
    )
    schedule.next_after(datetime(2000, 1, 1))  # an impossible date is an error now
    return schedule


def next_interval_run(
    previous: datetime, interval: timedelta, now: datetime
) -> Tuple[datetime, int]:
    """The next slot on a fixed cadence after ``now``, and how many slots were missed.

    Runs stay on ``previous + n * interval``, so a run that started late does
    not push every later one back.
    """
    if previous > now:
        return previous, 0
    missed = int((now - previous) / interval)
    return previous + (missed + 1) * interval, missed
