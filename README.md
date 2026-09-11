# IPMG — IP Management & Ping Monitoring Tool

[![PyPI](https://img.shields.io/pypi/v/ipmg)](https://pypi.org/project/ipmg/)
![Python Version](https://img.shields.io/badge/python-3.9%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
[![Publish](https://github.com/sameeralam3127/ipmg/actions/workflows/publish.yml/badge.svg)](https://github.com/sameeralam3127/ipmg/actions/workflows/publish.yml)

**Find out which hosts on your network are up — and what changed since last time.**

IPMG pings hosts in parallel, resolves their names, and hands you a report you
can send to someone: Excel, CSV, JSON, or Markdown. It works from the command
line or from a local web dashboard, and it remembers every scan so it can tell
you what moved.

**Website:** [sameeralam3127.github.io/ipmg](https://sameeralam3127.github.io/ipmg/) ·
**Live demo:** [dashboard with sample data](https://sameeralam3127.github.io/ipmg/demo/)

```bash
pip install ipmg
ipmg --discover        # scan the network you are on, right now
```

> **Please read:** only scan networks you are authorized to scan. Unauthorized
> scanning may violate your organization's policies or the law.

**Contents**

[Install](#install) ·
[Your first scan](#your-first-scan) ·
[Common tasks](#common-tasks) ·
[Live results](#live-results) ·
[Change detection](#change-detection) ·
[Web dashboard](#web-dashboard) ·
[What you can scan](#what-you-can-scan) ·
[Reports](#reports) ·
[All options](#all-options) ·
[Security](#security) ·
[More help](#more-help) ·
[Contributing](#contributing)

---

## Install

**Linux and macOS — one command, works on every distribution:**

```bash
curl -sSL https://raw.githubusercontent.com/sameeralam3127/ipmg/main/install.sh | bash
```

It installs [uv](https://docs.astral.sh/uv/) (which brings its own Python, so
your system Python does not matter), then installs IPMG as an isolated tool.
Nothing is installed system-wide unless you run it as root.

On a minimal server or container image, add `--with-deps` and it will install
the handful of system packages it needs (`curl`, `tar`, `gzip`, `ping`) for you:

```bash
curl -sSL https://raw.githubusercontent.com/sameeralam3127/ipmg/main/install.sh | bash -s -- --with-deps
```

**Windows — two commands in PowerShell:**

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
uv tool install ipmg
```

Then check it works, on any platform:

```bash
ipmg --version
```

### Installing with pip

`pip install ipmg` works inside a virtual environment, and inside one only.
On Ubuntu 23.04+, Debian 12+, Fedora 38+, and recent openSUSE, installing into
the system Python is blocked by the distribution itself:

```
error: externally-managed-environment
× This environment is externally managed
```

That is [PEP 668](https://peps.python.org/pep-0668/), and it is not an IPMG
bug — the distro is protecting its own Python. Any of these get you around it:

```bash
# 1. uv — no system Python needed at all (what the installer above uses)
uv tool install ipmg

# 2. pipx — the standard way to install Python applications
pipx install ipmg

# 3. a virtual environment you manage yourself
python3 -m venv ~/.venvs/ipmg
~/.venvs/ipmg/bin/pip install ipmg
~/.venvs/ipmg/bin/ipmg --version
```

Please do not reach for `--break-system-packages`. It does what it says.

### The one thing IPMG needs from your system

IPMG probes hosts with your operating system's `ping` command, and minimal
Ubuntu, RHEL, SUSE, and container images ship without it. If a scan reports
`The system 'ping' command is not available`, install it:

| System | Command |
| --- | --- |
| Ubuntu, Debian | `sudo apt-get install -y iputils-ping` |
| RHEL, Rocky, Alma, Fedora | `sudo dnf install -y iputils` |
| openSUSE, SLES | `sudo zypper install -y iputils` |
| Arch | `sudo pacman -S iputils` |
| Alpine | `sudo apk add iputils` |
| macOS, Windows | already included |

You do **not** need root, administrator rights, or a raw-socket capability —
IPMG runs the same `ping` you would run by hand.

### Verified environments

Each of these was installed from scratch and run against a live target:

| Environment | Notes |
| --- | --- |
| Ubuntu 22.04 / 24.04 | 24.04 blocks `pip install`; the installer is unaffected |
| Debian 12 | same PEP 668 situation as Ubuntu |
| RHEL 8 / RHEL 9 (UBI), Rocky 9 | RHEL 8's system Python is 3.6 — uv supplies its own |
| Fedora 41 | |
| openSUSE Leap 15.6 | image has no Python at all; installer supplies everything |
| Alpine 3.20 | run the installer with `bash`, not `sh` |
| macOS | verified on Apple silicon |

Windows is not in that list because it cannot be tested in a container: it is
covered instead by the CI matrix, which runs the full test suite and a live
scan on `windows-latest` for every change.

Python 3.9 through 3.14 are supported, and CI runs the test suite against every
one of them.

<details>
<summary>Other ways to install</summary>

**uv (isolated global install):**

```bash
uv tool install ipmg
```

**Pin a specific version:**

```bash
curl -sSL https://raw.githubusercontent.com/sameeralam3127/ipmg/main/install.sh | bash -s -- --version 1.13.0
```

**From source (development):**

```bash
git clone https://github.com/sameeralam3127/ipmg.git
cd ipmg
pip install -e ".[dev]"
```

**Upgrade or remove:**

```bash
uv tool upgrade ipmg
uv tool uninstall ipmg
```

</details>

---

## Your first scan

The fastest way to see IPMG work is to point it at the network you are already
on. `--discover` finds your machine's address and scans the /24 around it:

```bash
ipmg --discover
```

Prefer to be specific? Any of these work as a target:

```bash
ipmg --input 8.8.8.8                  # one host
ipmg --input 192.168.1.0/24           # a CIDR block
ipmg --input 10.0.0.1-10.0.0.50       # a range
ipmg --input targets.txt              # a file of hosts
```

Here is what a finished scan looks like:

```text
  ipmg 1.13.0  ·  scan
  ICMP probes only — scan only networks you are authorized to scan.

  Source   targets.txt
  Targets  3 hosts
  Config   50 threads · 2s timeout · 1 ping · reverse DNS

  Results
  ● Active   2  ━━━━━━━━━━━━━━━───────  66.7%
  ● Timeout  1  ━━━━━━━───────────────  33.3%

  3 hosts · 66.7% active · 5.8 ms avg · 3.08s · 2026-07-26 23:13:25

  Saved    results_20260726_231328.csv
```

Reading it top to bottom: where the targets came from, how the scan was
configured, how the hosts answered, a one-line scorecard, and the report file
IPMG wrote for you.

Running plain `ipmg` with no arguments uses `ip_list.xlsx` as its input, and
creates it with two sample targets (`8.8.8.8` and `1.1.1.1`) if it does not
exist yet. A file you name with `--input` must already exist.

---

## Common tasks

| I want to… | Command |
| --- | --- |
| Scan the network I am on | `ipmg --discover` |
| Scan hosts listed in a file | `ipmg --input targets.txt` |
| Get names, not just IP addresses | `ipmg --input targets.txt --resolve` |
| Get a report I can send to someone | `ipmg --input targets.txt --formats md csv` |
| See hosts appear as they answer | `ipmg --input 192.168.1.0/24 --stream` |
| See what changed since last time | `ipmg --input targets.txt --compare` |
| Check which services are listening | `ipmg --input targets.txt --scan-ports` |
| Keep scanning every 5 minutes | `ipmg --input targets.txt --interval 5` |
| Look back at earlier scans | `ipmg history` |
| Compare two specific scans | `ipmg diff 12 14` |
| Use the web dashboard instead | `ipmg dashboard` |
| See every available flag | `ipmg --help` |

---

## Live results

By default a scan prints its results once every host has been probed. On a
large range that is a long wait with nothing to look at, so `--stream` prints
each host the moment its probe finishes, above a progress bar that also carries
a running count of the hosts that answered:

```bash
ipmg --input 192.168.1.0/24 --stream
```

```text
  Live
  Status        Host                Latency
  ● Active      192.168.1.1          0.9 ms
  ● Active      192.168.1.24         3.1 ms
   ⠹ Scanning ━━━━━━━━━━━───────────  48% 122/254 0:00:09 2 up
```

`--stream` shows only the hosts that answer, which is what makes a sparse range
readable. Add `--stream-all` to see every result, including timeouts and
unreachable hosts. The rows gain a `Name` column under `--resolve` and an
`Open ports` column under `--scan-ports`.

Streaming costs nothing in scan time: rows are printed by the thread that
collects results, so the workers never wait on the terminal. When output is
piped or redirected the progress bar is dropped and the rows are written as
plain lines, which makes `ipmg --stream-all >> scan.log` a usable live log.

---

## Change detection

Every scan is stored in a local SQLite history (`~/.ipmg/dashboard.db`), shared
by the CLI and the dashboard. IPMG can then tell you what moved between any two
scans — which is usually the question you actually have.

```bash
ipmg --input targets.txt --compare    # compare with the previous scan
ipmg diff                             # compare the two latest scans
ipmg diff 14                          # compare scan 14 with the one before it
ipmg diff 12 14                       # compare two specific scans
ipmg diff --diff-formats md json      # export the change summary
ipmg diff --fail-on-change            # exit 2 when anything changed (CI)
ipmg history --limit 10               # list stored scans
```

What counts as a change:

| Change | Severity | Meaning |
| --- | --- | --- |
| Host offline | critical | Reachable in the baseline, not reachable now |
| New host | warning | An IP that the baseline never saw |
| Host removed | warning | An IP the current scan no longer covers |
| IP address changed | warning | A known hostname moved to a different IP |
| Service changed | warning | Status moved between failure modes (e.g. `Timeout` → `Unreachable`) |
| Host back online | info | Recovered since the baseline |
| Hostname changed | info | Same IP, different PTR record |
| Latency changed | info | Latency moved past both thresholds |

A latency change is only reported when it clears **both** `--latency-threshold`
(default 5 ms) and `--latency-pct` (default 25%), which keeps normal jitter out
of the report.

By default a scan is compared against the previous scan **of the same target
source**, so file-based and `--discover` runs do not get mixed up. Pass
`--compare-any-source` if you want the previous scan whatever its source.

| Flag | Default | Description |
| --- | --- | --- |
| `--compare` | off | Print a change report after the scan |
| `--compare-any-source` | off | Allow a baseline from a different target source |
| `--no-history` | off | Do not store the scan |
| `--db` | `~/.ipmg/dashboard.db` | History database location |
| `--diff-formats` | none | Export the change summary as `md`, `json`, `csv` |
| `--diff-output` | `changes` | Base filename for exported change summaries |
| `--latency-threshold` | `5` | Minimum latency delta in ms |
| `--latency-pct` | `25` | Minimum relative latency change |
| `--fail-on-change` | off | `ipmg diff` exits 2 when changes are found |

---

## Web dashboard

Prefer clicking to typing? The dashboard runs locally and shares the CLI's
scanning engine:

```bash
ipmg dashboard          # starts http://127.0.0.1:8080 and opens your browser
```

It runs fully offline — every stylesheet and script is bundled with the
package, nothing is loaded from a CDN. It gives you:

- **Dashboard** — status donut, latency trend, and recent scan overview
- **New Scan** — upload Excel/CSV/text/JSON target files or type IPs,
  CIDR blocks, and ranges; configure threads, timeout, and DNS options
- **Live Monitor** — real-time progress and results over WebSockets
- **History** — every scan stored locally in SQLite (`~/.ipmg/dashboard.db`),
  searchable and downloadable as XLSX/CSV/JSON/Markdown
- **Changes** — pick any two scans and see new/offline hosts, IP and hostname
  moves, and latency shifts; export the summary as Markdown/JSON/CSV
- **Inventory** — every host seen across scans, with last status and export

| Flag | Default | Description |
| --- | --- | --- |
| `--port` | `8080` | Port to listen on |
| `--host` | `127.0.0.1` | Bind address (local-only by default) |
| `--no-browser` | off | Don't open the browser automatically |
| `--db` | `~/.ipmg/dashboard.db` | History database location |

`ipmg web` is an alias for `ipmg dashboard`.

### On a server with no browser

On a Linux server with no display (e.g. accessed over plain SSH), IPMG detects
that no browser can be opened, skips the attempt, and prints a hint instead of
failing silently. The dashboard still binds to `127.0.0.1` by default, so reach
it from your workstation with an SSH tunnel:

```bash
ssh -L 8080:127.0.0.1:8080 user@server
# then open http://127.0.0.1:8080 locally
```

Alternatively, bind to all interfaces with `--host 0.0.0.0` — this exposes an
unauthenticated API on the network, so only do this on a trusted network or
behind a reverse proxy with authentication (see [Security](#security)).

---

## What you can scan

Anywhere IPMG takes `--input`, you can give it any of these:

- **A single IP** — `8.8.8.8`
- **A CIDR block** — `10.0.0.0/24`
- **A range** — `10.0.0.1-10.0.0.200`
- **A text file** — one IP or CIDR per line. Blank lines and `#` comments are
  ignored, so you can annotate it:

  ```text
  # Production DNS
  8.8.8.8
  192.168.1.0/30
  ```

- **An Excel or CSV file** (`.xlsx`, `.xls`, `.csv`) — must contain a column
  named `IP Address`. Cells can hold single addresses or CIDR blocks:

  | IP Address  |
  | ----------- |
  | 192.168.1.1 |
  | 10.0.1.0/30 |

Duplicate targets are removed automatically, and one scan expands to at most
65,536 hosts — larger CIDR blocks or ranges are rejected up front, before the
scan starts.

---

## Reports

Every scan writes a report file named after the time it ran, e.g.
`results_20260628_120000.xlsx`. Choose the format with `--formats` (you can ask
for several at once) and the name prefix with `--output`:

```bash
ipmg --input targets.txt --formats md csv --output monday-audit
```

Each file has one row per host:

| IP Address | Status | Latency | Hostname   | Open Ports | Batch Timestamp     | Scan Duration (s) |
| ---------- | ------ | ------- | ---------- | ---------- | ------------------- | ----------------- |
| 8.8.8.8    | Active | 12.5    | dns.google | 443        | 2026-04-09 11:42:13 | 6.24               |

Status is one of `Active`, `Inactive`, `Timeout`, `Unreachable`, `Invalid IP`,
or `Error`. `Hostname` is filled in when you pass `--resolve`.

The `md` format produces a shareable Markdown report with a status summary
table — handy for tickets, handoffs, and incident timelines.

**Open ports.** `Open Ports` is only populated when `--scan-ports` is set: for
each host that answers, IPMG probes a list of common TCP ports (SSH, HTTP,
HTTPS, RDP, SMB, FTP, SMTP, DNS, MSSQL, MySQL, PostgreSQL by default)
concurrently and records which ones accepted a connection.

```bash
ipmg --input targets.txt --scan-ports
ipmg --input targets.txt --scan-ports --ports 22,80,443 --port-timeout 0.5
```

In the terminal, colors follow `NO_COLOR`, the progress bar is hidden when
output is piped, and symbols fall back to ASCII on terminals that cannot render
them — so piping IPMG into a file or a log gives you clean text.

---

## All options

`ipmg --help` always lists the current set. Grouped for reading:

**Targets and reports**

| Flag | Default | Description |
| --- | --- | --- |
| `--input` | `ip_list.xlsx` | What to scan: a file (`.xlsx`, `.xls`, `.csv`, `.txt`, `.list`), a single IP, a CIDR block, or a range (`10.0.0.1-10.0.0.50`) |
| `--discover` | off | Auto-detect and scan the local subnet instead |
| `--output` | `results` | Report file name prefix |
| `--formats` | `xlsx` | One or more of `xlsx`, `csv`, `json`, `md` |

**Speed and accuracy**

| Flag | Default | Description |
| --- | --- | --- |
| `--threads` | `50` | How many hosts to probe at once |
| `--timeout` | `2` | Seconds to wait for a reply |
| `--count` | `1` | Pings per host (raise it on a lossy link) |
| `--interval` | off | Repeat the whole scan every N minutes |

**Names and services**

| Flag | Default | Description |
| --- | --- | --- |
| `--resolve` | off | Reverse DNS (PTR) lookup for each host |
| `--dns-cache-ttl` | `300` | Cache DNS results for this many seconds (`0` disables caching) |
| `--scan-ports` | off | Probe common TCP ports on hosts that answer |
| `--ports` | `21,22,25,53,80,443,445,1433,3306,3389,5432` | Which TCP ports to probe when `--scan-ports` is set |
| `--port-timeout` | `1` | Connect timeout per port in seconds |

**Live output**

| Flag | Default | Description |
| --- | --- | --- |
| `--stream` | off | Print each host that answers as soon as its probe finishes |
| `--stream-all` | off | Stream every result, including hosts that did not answer (implies `--stream`) |
| `--stream-refresh` | `0.25` | Seconds between progress-bar redraws while streaming (0.05-5) |
| `--verbose` | off | Debug logging |

**History and changes** — see [Change detection](#change-detection) for
`--compare`, `--no-history`, `--db`, `--diff-formats`, `--diff-output`,
`--latency-threshold`, `--latency-pct`, and `--fail-on-change`.

Exit codes: `0` success, `1` error, `2` changes detected
(`ipmg diff --fail-on-change`), `130` interrupted.

---

## Security

IPMG is built for scanning networks you are authorized to scan, and the tool
itself is hardened accordingly:

- Pings run as a direct process call (no shell), and every target is
  validated as an IP address first
- The dashboard binds to `127.0.0.1` by default and serves everything
  locally — no CDN assets, no outbound requests
- WebSocket connections are origin-checked, so a web page you happen to
  visit cannot connect to the local dashboard and read your scan results
- Uploads are capped at 5 MB and one scan expands to at most 65,536 hosts,
  so a bad input file cannot exhaust memory
- All database access uses parameterized SQL

If you bind to a non-local address with `--host`, anyone who can reach that
interface can start scans and read results — put a reverse proxy with
authentication in front of it.

Found a vulnerability? See [SECURITY.md](SECURITY.md) for how to report it.

---

## More help

- **[Command reference](https://github.com/sameeralam3127/ipmg/blob/main/docs/COMMANDS.md)** —
  every command and flag with copy-paste examples, a safe session that tries
  everything on your own machine, exit codes, and error messages
- **[Troubleshooting](https://github.com/sameeralam3127/ipmg/blob/main/docs/TROUBLESHOOTING.md)** —
  install errors, `command not found`, every host timing out, slow scans,
  rejected input files
- **[FAQ](https://github.com/sameeralam3127/ipmg/blob/main/docs/FAQ.md)** —
  root rights, Python versions, where history lives, running on a schedule
- **[Issues](https://github.com/sameeralam3127/ipmg/issues)** — report a bug or
  request a feature

---

## Contributing

Contributions are welcome.
[CONTRIBUTING.md](https://github.com/sameeralam3127/ipmg/blob/main/CONTRIBUTING.md)
covers setting up a development environment, running the tests, the commit
message format that drives automated releases, and how the project website and
dashboard demo are built. Everyone taking part is expected to follow the
[Code of Conduct](https://github.com/sameeralam3127/ipmg/blob/main/CODE_OF_CONDUCT.md).

---

## License

MIT — free for commercial and personal use.
