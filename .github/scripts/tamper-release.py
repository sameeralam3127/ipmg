#!/usr/bin/env python3
"""Copy a release directory and break one thing in it, for the installer tests.

    tamper-release.py MODE RELEASE_DIR OUT_DIR

Modes, each of which the installers must refuse:

  wheel              append a byte to the wheel; SHA256SUMS still lists the old hash
  requirements       append a line to requirements-web.txt, the same way
  drop-wheel         remove the wheel's line from SHA256SUMS
  drop-requirements  remove the requirements file's line from SHA256SUMS
  dependency-hash    change one dependency's hash in requirements-web.txt and
                     update SHA256SUMS to match, so only --require-hashes can
                     catch it

The result is meant to be passed to an installer as IPMG_RELEASE_BASE_URL.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import sys
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rewrite_sums(out: Path, keep) -> None:
    lines = []
    for line in (out / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split(None, 1)
        if keep(name):
            lines.append(f"{digest}  {name}\n")
    (out / "SHA256SUMS").write_text("".join(lines), newline="\n")


def break_dependency_hash(dest: Path, requirements: Path) -> int:
    text = requirements.read_text()
    # The first pinned package keeps only two hashes that match nothing.
    pattern = re.compile(r"^(\S+==\S+ \\\n)((?:    --hash=sha256:[0-9a-f]{64} ?\\?\n)+)", re.M)
    fake = "".join(f"    --hash=sha256:{digit * 64} \\\n" for digit in "01")
    text, count = pattern.subn(lambda m: m.group(1) + fake, text, count=1)
    if count != 1:
        print("could not find a hashed requirement to change", file=sys.stderr)
        return 1
    requirements.write_text(text, newline="\n")
    lines = []
    for line in (dest / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split(None, 1)
        if name == "requirements-web.txt":
            digest = sha256(requirements)
        lines.append(f"{digest}  {name}\n")
    (dest / "SHA256SUMS").write_text("".join(lines), newline="\n")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(__doc__, file=sys.stderr)
        return 2
    mode, source, dest = argv[1], Path(argv[2]), Path(argv[3])
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(source, dest)

    wheel = next(dest.glob("*.whl"))
    requirements = dest / "requirements-web.txt"

    if mode == "wheel":
        with wheel.open("ab") as handle:
            handle.write(b"\0")
    elif mode == "requirements":
        with requirements.open("ab") as handle:
            handle.write(b"evil==1.0\n")
    elif mode == "drop-wheel":
        rewrite_sums(dest, lambda name: not name.endswith(".whl"))
    elif mode == "drop-requirements":
        rewrite_sums(dest, lambda name: name != "requirements-web.txt")
    elif mode == "dependency-hash":
        return break_dependency_hash(dest, requirements)
    else:
        print(f"unknown mode: {mode}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
