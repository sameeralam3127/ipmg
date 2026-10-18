"""Regenerate src/ipmg/data/oui.tsv.gz, the bundled MAC vendor database.

Run from the repository root:

    python .github/scripts/update-oui.py

It downloads the IEEE Registration Authority's public assignment lists for
all three block sizes (MA-L: 24-bit prefixes, MA-M: 28-bit, MA-S: 36-bit)
and writes one ``PREFIX<TAB>Organization`` line per assignment, sorted, in a
gzip file. Vendor lookup needs no network access at scan time.

Pass already downloaded CSV files to skip the download:

    python .github/scripts/update-oui.py oui.csv mam.csv oui36.csv
"""

from __future__ import annotations

import csv
import gzip
import io
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

REGISTRIES = (
    "https://standards-oui.ieee.org/oui/oui.csv",
    "https://standards-oui.ieee.org/oui28/mam.csv",
    "https://standards-oui.ieee.org/oui36/oui36.csv",
)
OUTPUT = Path(__file__).resolve().parents[2] / "src" / "ipmg" / "data" / "oui.tsv.gz"
_HEX = re.compile(r"^[0-9A-F]{6}(?:[0-9A-F]|[0-9A-F]{3})?$")


def _download(url: str) -> str:
    # The registry refuses requests without a browser-like user agent.
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (ipmg update-oui)"})
    with urllib.request.urlopen(request, timeout=60) as response:  # nosec B310 - fixed https URLs
        return response.read().decode("utf-8")


def _entries(text: str):
    for row in csv.DictReader(io.StringIO(text)):
        prefix = (row.get("Assignment") or "").strip().upper()
        name = " ".join((row.get("Organization Name") or "").split())
        if _HEX.match(prefix) and name:
            yield prefix, name


def main(paths) -> int:
    texts = [Path(path).read_text(encoding="utf-8") for path in paths] or [
        _download(url) for url in REGISTRIES
    ]
    entries = {}
    for text in texts:
        entries.update(_entries(text))
    if len(entries) < 10_000:
        print(f"only {len(entries)} assignments found; refusing to write", file=sys.stderr)
        return 1

    lines = [f"# IEEE Registration Authority MA-L, MA-M, MA-S, retrieved {date.today()}"]
    lines += [f"{prefix}\t{name}" for prefix, name in sorted(entries.items())]
    data = ("\n".join(lines) + "\n").encode("utf-8")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    # mtime=0: the same registry contents always produce the same bytes.
    OUTPUT.write_bytes(gzip.compress(data, compresslevel=9, mtime=0))
    print(f"wrote {len(entries)} assignments to {OUTPUT} ({OUTPUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
