"""Record the README demo as an asciicast, then render it with agg.

Run from the repository root with IPMG installed in .venv:

    python docs/demo/record.py
    agg --theme monokai --font-size 16 docs/demo/ipmg-demo.cast docs/assets/ipmg-demo.gif

Every command runs for real in a pseudo-terminal; only the typing is
simulated. Targets are public DNS resolvers plus TEST-NET addresses
(RFC 5737) that never answer, so the recording shows timeouts without
exposing a real LAN.
"""

from __future__ import annotations

import fcntl
import json
import os
import pty
import select
import shutil
import struct
import subprocess
import tempfile
import termios
import time
from pathlib import Path

COLS, ROWS = 92, 31
ROOT = Path(__file__).resolve().parents[2]
CAST = ROOT / "docs" / "demo" / "ipmg-demo.cast"
PROMPT = "\x1b[1;32m$\x1b[0m "

COMMANDS = [
    "wc -l targets.txt",
    "ipmg --input targets.txt --resolve --stream-all --no-history --formats md",
]


class Recorder:
    def __init__(self) -> None:
        self.start = time.monotonic()
        self.clock = 0.0
        self.events: list[list] = []

    def emit(self, text: str, delay: float = 0.0) -> None:
        self.clock += delay
        self.events.append([round(self.clock, 3), "o", text])

    def type(self, command: str) -> None:
        self.emit(PROMPT, 0.4)
        for char in command:
            self.emit(char, 0.035)
        self.emit("\r\n", 0.35)

    def run(self, command: str, cwd: str, env: dict[str, str]) -> None:
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", ROWS, COLS, 0, 0))
        proc = subprocess.Popen(
            command,
            shell=True,
            cwd=cwd,
            env=env,
            stdin=slave,
            stdout=slave,
            stderr=slave,
            close_fds=True,
        )
        os.close(slave)
        began = time.monotonic()
        offset = self.clock
        while True:
            ready, _, _ = select.select([master], [], [], 0.05)
            if ready:
                try:
                    chunk = os.read(master, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                self.clock = offset + (time.monotonic() - began)
                self.emit(chunk.decode("utf-8", "replace"))
            elif proc.poll() is not None:
                break
        proc.wait()
        os.close(master)

    def save(self, path: Path) -> None:
        header = {
            "version": 2,
            "width": COLS,
            "height": ROWS,
            "env": {"TERM": "xterm-256color", "SHELL": "/bin/bash"},
        }
        lines = [json.dumps(header)] + [json.dumps(e, ensure_ascii=False) for e in self.events]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    env = dict(os.environ, TERM="xterm-256color", COLUMNS=str(COLS), LINES=str(ROWS))
    env["PATH"] = f"{ROOT / '.venv' / 'bin'}{os.pathsep}{env['PATH']}"
    rec = Recorder()
    with tempfile.TemporaryDirectory() as work:
        shutil.copy(ROOT / "docs" / "demo" / "targets.txt", work)
        for command in COMMANDS:
            rec.type(command)
            rec.run(command, work, env)
        rec.emit(PROMPT, 0.4)
        rec.emit("", 4.0)  # hold the last frame
    rec.save(CAST)
    print(f"wrote {CAST.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
