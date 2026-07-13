# IPMG — IP Management & Ping Monitoring Tool

[![PyPI](https://img.shields.io/pypi/v/ipmg)](https://pypi.org/project/ipmg/)
![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)
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

# Open the local web dashboard
ipmg dashboard
```

Running plain `ipmg` uses `ip_list.xlsx` as input and creates a sample file
if it does not exist.

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
| `--verbose` | off | Debug logging |

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

---

## Output

Every scan prints a color-coded summary and writes result files
(e.g. `results_20260628_120000.xlsx`). Each row includes:

| IP Address | Status | Latency | Hostname   | Batch Timestamp     | Scan Duration (s) |
| ---------- | ------ | ------- | ---------- | ------------------- | ----------------- |
| 8.8.8.8    | Active | 12.5    | dns.google | 2026-04-09 11:42:13 | 6.24              |

Status values: `Active`, `Inactive`, `Timeout`, `Unreachable`, `Invalid IP`, `Error`.

The `md` format produces a shareable Markdown report with a status summary
table — handy for tickets, handoffs, and incident timelines.

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

---

## License

MIT — free for commercial and personal use.
