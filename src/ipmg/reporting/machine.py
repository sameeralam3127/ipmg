"""Machine-readable scan output on stdout, for piping into jq or a script.

``--formats json`` writes a timestamped file, so a script that wants the
results has to glob for it. These two flags put the same rows on stdout
instead:

* ``--json`` prints the finished scan as one JSON array.
* ``--jsonl`` prints one object per host, the moment its probe finishes.

Both render rows through :mod:`ipmg.infrastructure.incremental`, the code the
report files go through, so a host looks the same in all of them: ``--json``
prints exactly what ``--jsonl`` would, gathered into an array, and either one
matches a line of the ``jsonl`` report. Field names are the report's column
names.

While either flag is set the human UI moves to stderr, so stdout carries
nothing but the data and the two can be redirected apart.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from typing import Dict, Optional, Sequence

from ipmg.core.engine import HostResult
from ipmg.infrastructure.incremental import jsonl_record, result_row
from ipmg.reporting.frames import ReportTable


@dataclass(frozen=True)
class MachineOutput:
    """Which machine-readable stream, if any, a scan should write to stdout."""

    #: ``--json``: the whole scan as one array, once it has finished.
    array: bool = False
    #: ``--jsonl``: one object per host, as each probe finishes.
    stream: bool = False

    @property
    def enabled(self) -> bool:
        return self.array or self.stream


class MachineStream:
    """Print one JSON object per host to stdout as its probe finishes.

    Takes the same ``record(result)`` call as
    :class:`~ipmg.infrastructure.incremental.IncrementalReport`, so a scan can
    feed both from one callback. Resumed hosts are replayed first, which keeps
    the stream a complete account of the scan rather than of this pass only.
    """

    def __init__(
        self,
        batch_timestamp: object,
        previous: Optional[Sequence[HostResult]] = None,
        previous_elapsed_s: float = 0.0,
    ) -> None:
        self._batch_timestamp = batch_timestamp
        self._started_at = time.monotonic() - previous_elapsed_s
        for result in previous or ():
            self._write(result_row(result, batch_timestamp, previous_elapsed_s))

    def record(self, result: HostResult) -> None:
        elapsed_s = time.monotonic() - self._started_at
        self._write(result_row(result, self._batch_timestamp, elapsed_s))

    @staticmethod
    def _write(row: Dict[str, object]) -> None:
        # Flushed per host: whoever is reading the pipe should see a result as
        # soon as it lands, not when the buffer happens to fill.
        sys.stdout.write(jsonl_record(row))
        sys.stdout.flush()


def write_array(table: ReportTable) -> None:
    """Print a finished scan to stdout as one JSON array.

    ``default=str`` for the same reason :func:`jsonl_record` uses it: a
    timestamp should read as the text it prints as, not as epoch milliseconds.
    """
    sys.stdout.write(json.dumps(table.rows, default=str) + "\n")
    sys.stdout.flush()
