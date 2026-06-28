# IPMG — IP Management & Ping Monitoring Tool

![PyPI](https://img.shields.io/pypi/v/ipmg)
![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Platform](https://img.shields.io/badge/platform-Mac%20%7C%20Linux%20%7C%20Windows-lightgrey)
![CLI](https://img.shields.io/badge/tool-ipmg-orange)
![CI Ready](https://img.shields.io/badge/formatting-ruff%20%7C%20black-yellow)
[![Publish](https://github.com/sameeralam3127/ipmg/actions/workflows/publish.yml/badge.svg)](https://github.com/sameeralam3127/ipmg/actions/workflows/publish.yml)

---

**IPMG (IP Management Tool)** is a modern, modular, enterprise-ready network scanner and monitoring utility.
It replaces the legacy `ip_pinger.py` script with a **clean package architecture**, CLI tooling, and automated workflows.

Designed for:

- Network administrators
- Systems engineers
- Cybersecurity teams
- DevOps and SREs

IPMG supports:

- **Subnet auto-discovery**
- **Parallel pinging with thread pools**
- **Hostname resolution**
- **Multi-format reporting (XLSX/CSV/JSON)**
- **Human-readable Markdown scan reports**
- **Flexible target input (XLSX/CSV/text/single IP/CIDR)**
- **Scheduled recurrent scans**
- **Auto-generated sample input files**
- **Colorized CLI output**
- **Rich console panels, progress bars, and color-coded summaries**
- **Modular testable architecture**
- **Batch-level scan timestamps and duration tracking**

---

## ⚠️ Security Disclaimer

> **Do NOT use this tool on networks without explicit authorization.**
> Always obtain written approval from your organization's **Cybersecurity / Network Security team**.
> Unauthorized scanning may violate internal policies or law.

IPMG includes a built-in disclaimer shown at runtime (`security.py`).

---

## Features

- Fully modular Python package (`src/ipmg`)
- System-wide CLI command: `ipmg`
- Accepts targets from `.xlsx`, `.csv`, `.txt`, `.list`, literal IPs, and CIDR blocks
- Exports machine-readable files and shareable Markdown reports from the same scan
- Test coverage via `pytest`
- Formatting and linting via `ruff` and `black`
- CI-friendly project structure

> [!NOTE]
> Modern network utility users usually need both automation-friendly exports and a quick report they can paste into tickets, handoff notes, or incident timelines. IPMG now supports `md` output so one scan can produce spreadsheet data for analysis and a readable operational summary for humans.

---

# Installation

## Option 1 — Install from PyPI (recommended for most users)

Install the latest stable release from PyPI:

```bash
pip install ipmg
```

Verify installation:

```bash
ipmg --help
ipmg --version
```

You can always check the current published version on [PyPI](https://pypi.org/project/ipmg/).

---

## Option 2 — Install via uv (recommended for isolated global install)

```bash
uv tool install git+https://github.com/sameeralam3127/ipmg.git
```

Test:

```bash
ipmg --help
ipmg --version
```

---

## Option 3 — Install via pip (editable, development mode)

```bash
git clone https://github.com/sameeralam3127/ipmg.git
cd ipmg
pip install -e .
```

Verify:

```bash
ipmg --help
ipmg --version
```

---

## Option 4 — Install using curl installer

```bash
curl -sSL https://raw.githubusercontent.com/sameeralam3127/ipmg/main/install.sh | bash
```

This script:

- Installs **uv** if missing
- Installs **ipmg** globally using uv

Verify:

```bash
ipmg --help
ipmg --version
```

---

| Use Case                        | Command                             | Description                                                                   |
| ------------------------------- | ----------------------------------- | ----------------------------------------------------------------------------- |
| Basic Example (Default Input)   | `ipmg`                              | Runs with default config. Creates `ip_list.xlsx` with sample IPs if missing.  |
| Scan a Custom Excel File        | `ipmg --input network_devices.xlsx` | Scans IPs from an Excel file with an `IP Address` column.                     |
| Scan a CSV File                 | `ipmg --input network_devices.csv`  | Scans IPs from a CSV file with an `IP Address` column.                        |
| Scan a Text File                | `ipmg --input targets.txt`          | Scans one target per line. Blank lines and `#` comments are ignored.          |
| Scan a Single Host              | `ipmg --input 8.8.8.8`              | Scans a literal IP passed directly on the CLI.                                |
| Scan a CIDR Range               | `ipmg --input 192.168.1.0/24`       | Expands the CIDR block into host IPs and scans them.                          |
| Auto-discover LAN Subnet        | `ipmg --discover`                   | Automatically detects and scans devices in the local subnet.                  |
| Export Results to CSV + XLSX    | `ipmg --formats csv xlsx`           | Exports scan results in CSV and Excel formats.                                |
| Create a Markdown Report        | `ipmg --formats md csv`             | Saves a readable scan report plus CSV data for tickets, handoffs, and audits. |
| Resolve Hostnames (PTR Records) | `ipmg --resolve`                    | Performs reverse DNS (PTR) lookups for hostnames.                             |
| Run Every 10 Minutes            | `ipmg --interval 10`                | Repeats the scan every 10 minutes.                                            |

If the default input file does not exist, IPMG creates a sample file based on the requested extension such as `.xlsx`, `.csv`, or `.txt`.

---

# Sample Output Summary

```
IPMG Summary

Status        Count
Active        132
Inactive      12
Unreachable   4
Timeout       2

Batch Timestamp: 2026-04-09 11:42:13
Total Hosts: 150
Active Rate: 88.00%
Completion Rate: 90.67%
Scan Duration: 6.24s
```

---

# Input Formats

IPMG accepts targets from:

- Excel files: `.xlsx`, `.xls`
- CSV files: `.csv`
- Plain text files: `.txt`, `.list`
- Literal IPs such as `8.8.8.8`
- CIDR blocks such as `10.0.0.0/24`

For Excel and CSV inputs, the file must contain an `IP Address` column.

Example spreadsheet/CSV:

| IP Address  |
| ----------- |
| 192.168.1.1 |
| 10.0.0.1    |
| 10.0.1.0/30 |

Example text file:

```text
# Production DNS
8.8.8.8
1.1.1.1
192.168.1.0/30
```

---

# Output File Format

Each exported row includes batch-level metadata so a single run can be grouped reliably in downstream tools.

| IP Address | Status | Latency | Hostname   | Batch Timestamp     | Scan Duration (s) |
| ---------- | ------ | ------- | ---------- | ------------------- | ----------------- |
| 8.8.8.8    | Active | 12.5    | dns.google | 2026-04-09 11:42:13 | 6.24              |

Possible status values include `Active`, `Inactive`, `Timeout`, `Unreachable`, `Invalid IP`, and `Error`.

## Markdown Reports

Use `md` in `--formats` when you want an easy-to-share report:

```bash
ipmg --input targets.txt --formats md csv --resolve
```

The Markdown report includes:

- Batch timestamp
- Total host count
- Active host count and active rate
- Scan duration
- Status summary table
- Preview of the first 25 scanned hosts

Example generated files:

```text
results_20260628_120000.md
results_20260628_120000.csv
```

---

# Troubleshooting

### **Command not found: ipmg**

Solution:

```
pip install -e .
```

### **Permission denied output folder**

Run inside a writeable directory or use:

```
sudo ipmg ...
```

### **Hostname Unresolvable**

Likely missing DNS PTR records.

### **Input file is rejected**

Check that:

- The file extension is one of `.xlsx`, `.xls`, `.csv`, `.txt`, or `.list`
- Spreadsheet and CSV files include an `IP Address` column
- Plain text files contain one IP or CIDR target per line

### **One host crashes the scan**

IPMG now records unexpected per-host failures as `Error` and continues scanning the remaining targets.

---

# Development and Release

Set up a local development environment:

```bash
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

Run the test suite and build the package before opening a release PR:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q
python -m build
```

Releases are managed from the `main` branch by GitHub Actions. After a PR with a conventional commit such as `feat: ...` or `fix: ...` is merged, the publish workflow runs tests, creates the semantic-release version tag, builds source/wheel distributions, attaches release assets, and publishes the package to [PyPI](https://pypi.org/project/ipmg/) using the `pypi` trusted publishing environment.

Use `ipmg --version` after installation to confirm the installed package version matches the latest PyPI release.

---

# macOS GUI (PingMonitorApp – Beta)

A native macOS interface for IPMG is under active development.

Download Beta:

👉 [https://github.com/sameeralam3127/IP_Management/releases/tag/macOS](https://github.com/sameeralam3127/IP_Management/releases/tag/macOS)

---

# License

MIT License — free for commercial and personal use.

---

Made with ❤️ using Python & uv.
