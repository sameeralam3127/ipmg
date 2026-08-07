# IPMG — IP Management & Ping Monitoring Tool

[![PyPI](https://img.shields.io/pypi/v/ipmg)](https://pypi.org/project/ipmg/)
![Python Version](https://img.shields.io/badge/python-3.9%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
[![Publish](https://github.com/sameeralam3127/ipmg/actions/workflows/publish.yml/badge.svg)](https://github.com/sameeralam3127/ipmg/actions/workflows/publish.yml)

Scan and monitor IP networks from the command line — or from a local web
dashboard. IPMG pings hosts in parallel, resolves hostnames, and exports
results as Excel, CSV, JSON, or Markdown reports.

> **Security note:** only scan networks you are authorized to scan.
> Unauthorized scanning may violate your organization's policies or the law.

---

## Install

```bash
pip install ipmg
```

Check that it works:

```bash
ipmg --version
```

<details>
<summary>Other install methods</summary>

**uv (isolated global install):**

```bash
uv tool install git+https://github.com/sameeralam3127/ipmg.git
```

**curl installer (installs uv if missing):**

```bash
curl -sSL https://raw.githubusercontent.com/sameeralam3127/ipmg/main/install.sh | bash
```

**From source (development):**

```bash
git clone https://github.com/sameeralam3127/ipmg.git
cd ipmg
pip install -e .
```

</details>

---

## Quick start

```bash
# Scan your local subnet automatically
ipmg --discover

# Scan a single host
ipmg --input 8.8.8.8

# Scan a CIDR range
ipmg --input 192.168.1.0/24

# Scan an IP range
ipmg --input 10.0.0.1-10.0.0.50

# Scan targets from a file (xlsx, csv, txt, or list)
ipmg --input targets.txt

# Resolve hostnames and export CSV + a readable Markdown report
ipmg --input targets.txt --resolve --formats md csv

# Scan and report what changed since the previous scan
ipmg --input targets.txt --compare

# List stored scans, then compare any two of them
ipmg history
ipmg diff 12 14

# Open the local web dashboard
ipmg dashboard
```

Running plain `ipmg` uses `ip_list.xlsx` as input and creates a sample file
if it does not exist.

---

## Change detection

Every scan is stored in a local SQLite history (`~/.ipmg/dashboard.db`),
shared by the CLI and the dashboard. IPMG can then tell you what moved
between any two scans.

```bash
ipmg --input targets.txt --compare                   # compare with the previous scan
ipmg diff                                            # compare the two latest scans
ipmg diff 14                                         # compare scan 14 with the one before it
ipmg diff 12 14                                      # compare two specific scans
ipmg diff --diff-formats md json                     # export the change summary
ipmg diff --fail-on-change                           # exit 2 when anything changed (CI)
ipmg history --limit 10                              # list stored scans
```

Detected changes:

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

By default a scan is compared against the previous scan **of the same target
source**, so file-based and `--discover` runs do not get mixed up.

---

## Web dashboard

```bash
ipmg dashboard          # starts http://127.0.0.1:8080 and opens your browser
```

A modern browser UI that shares the CLI's scanning engine and runs fully
offline — every stylesheet and script is bundled with the package, nothing
is loaded from a CDN. It gives you:

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

---

## Options

| Flag | Default | Description |
| --- | --- | --- |
| `--input` | `ip_list.xlsx` | Targets: a file (`.xlsx`, `.xls`, `.csv`, `.txt`, `.list`), a single IP, a CIDR block, or an IP range (`10.0.0.1-10.0.0.50`) |
| `--output` | `results` | Output file name prefix |
| `--formats` | `xlsx` | One or more of `xlsx`, `csv`, `json`, `md` |
| `--discover` | off | Auto-detect and scan the local subnet |
| `--resolve` | off | Reverse DNS (PTR) lookup for each host |
| `--dns-cache-ttl` | `300` | Cache DNS results for this many seconds (`0` disables caching) |
| `--timeout` | `2` | Ping timeout in seconds |
| `--count` | `1` | Pings per host |
| `--threads` | `50` | Parallel workers |
| `--interval` | off | Repeat the scan every N minutes |
| `--compare` | off | Report what changed since the previous scan |
| `--no-history` | off | Do not store the scan in the history database |
| `--verbose` | off | Debug logging |

Exit codes: `0` success, `1` error, `2` changes detected
(`ipmg diff --fail-on-change`), `130` interrupted.

---

## Input formats

- **Excel / CSV** — must contain an `IP Address` column:

  | IP Address  |
  | ----------- |
  | 192.168.1.1 |
  | 10.0.1.0/30 |

- **Text file** — one IP or CIDR per line; blank lines and `#` comments are ignored:

  ```text
  # Production DNS
  8.8.8.8
  192.168.1.0/30
  ```

- **Command line** — a literal IP (`8.8.8.8`), CIDR block (`10.0.0.0/24`),
  or IP range (`10.0.0.1-10.0.0.200`)

Duplicate targets are removed automatically, and one scan expands to at most
65,536 hosts — larger CIDR blocks or ranges are rejected up front.

---

## Output

```text
  ipmg 1.8.1  ·  scan
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

Colors follow `NO_COLOR`, the progress bar is hidden when output is piped,
and the symbols fall back to ASCII on terminals that cannot render them.

Result files (e.g. `results_20260628_120000.xlsx`) contain one row per host:

| IP Address | Status | Latency | Hostname   | Batch Timestamp     | Scan Duration (s) |
| ---------- | ------ | ------- | ---------- | ------------------- | ----------------- |
| 8.8.8.8    | Active | 12.5    | dns.google | 2026-04-09 11:42:13 | 6.24              |

Status values: `Active`, `Inactive`, `Timeout`, `Unreachable`, `Invalid IP`, `Error`.

The `md` format produces a shareable Markdown report with a status summary
table — handy for tickets, handoffs, and incident timelines.

---

## Security

IPMG is built for scanning networks you are authorized to scan, and the
tool itself is hardened accordingly:

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

## Troubleshooting

- **`command not found: ipmg`** — make sure pip's script directory is on your
  `PATH`, or reinstall with `pip install ipmg`.
- **Hostname shows `Unresolvable`** — the host has no DNS PTR record.
- **Input file rejected** — check the extension is supported and that
  spreadsheets/CSVs include an `IP Address` column.

---

## Development

```bash
pip install -e ".[dev]"
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q
```

Releases are automated: merging a conventional commit (`feat: ...`,
`fix: ...`) to `main` triggers GitHub Actions to run tests, create a
semantic-release tag, and publish to [PyPI](https://pypi.org/project/ipmg/).

### GitHub Pages demo

The dashboard also has a static, interactive demonstration at
[sameeralam3127.github.io/ipmg](https://sameeralam3127.github.io/ipmg/).
GitHub Pages cannot run the Python scanner or access a local SQLite database,
so this version transparently uses realistic seeded network inventory and scan
history. Search, filters, comparison, exports, theme switching, and a manual
demo scan all work in the browser. The local `ipmg dashboard` command always
uses the real FastAPI API and scan engine instead.

The `Deploy dashboard demo to GitHub Pages` workflow publishes
`src/ipmg/web/static` after changes to `main`. In repository settings, select
**GitHub Actions** as the GitHub Pages source once; no secrets are required.

To review the static experience locally, run any static web server from
`src/ipmg/web/static` and open it with `?demo=1`:

```bash
cd src/ipmg/web/static
python3 -m http.server 4173
# http://127.0.0.1:4173/?demo=1
```

---

## License

MIT — free for commercial and personal use.
