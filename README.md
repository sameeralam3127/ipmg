# IPMG — IP Management & Ping Monitoring Tool

![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Platform](https://img.shields.io/badge/platform-Mac%20%7C%20Linux%20%7C%20Windows-lightgrey)
![CLI](https://img.shields.io/badge/tool-ipmg-orange)
![CI Ready](https://img.shields.io/badge/formatting-ruff%20%7C%20black-yellow)
![Tests](https://img.shields.io/badge/tests-pytest-brightgreen)

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
- **Scheduled recurrent scans**
- **Auto-generated sample Excel input**
- **Colorized CLI output**
- **Modular testable architecture**

---

## ⚠️ Security Disclaimer

> **Do NOT use this tool on networks without explicit authorization.**
> Always obtain written approval from your organization's **Cybersecurity / Network Security team**.
> Unauthorized scanning may violate internal policies or law.

IPMG includes a built-in disclaimer shown at runtime (`security.py`).

---

# Features

### ✔ Modular Python package (`src/ipmg`)

Not a single script anymore — now a clean, testable package.

### ✔ CLI Command: `ipmg`

Installed system-wide or via uv.

### ✔ Auto Subnet Discovery

Scan your `/24` instantly:

```
ipmg --discover
```

### ✔ Multi-threaded high performance

Scans hundreds of hosts in seconds.

### ✔ Auto Sample Excel Generation

If the input file is missing:

```
ip_list.xlsx
```

is created automatically.

### ✔ Supports multiple output formats

```
--formats xlsx csv json
```

### ✔ Hostname resolution

```
--resolve
```

### ✔ Scheduled scanning

```
--interval 5
```

Runs every 5 minutes.

### ✔ Fully tested (pytest) + formatted (ruff/black)

---

# Installation

## Option 1 — Install via uv (recommended)

```
uv tool install git+https://github.com/sameeralam3127/ipmg.git
```

Test:

```
ipmg --help
```

---

## Option 2 — Install via pip (editable, dev mode)

```bash
git clone https://github.com/sameeralam3127/ipmg.git
cd IP_Management

pip install -e .
```

Now:

```
ipmg --help
```

---

## Option 3 — Install using curl installer

```bash
curl -sSL https://raw.githubusercontent.com/sameeralam3127/ipmg/main/install.sh | bash
```

This script:

- Installs uv if missing
- Installs ipmg globally into uv

---

# Usage

### Help

```
ipmg --help
```

---

## Basic Example (using default input)

```
ipmg
```

If `ip_list.xlsx` does not exist → it will be created with sample IPs.

---

## Scan a custom input file

```
ipmg --input network_devices.xlsx
```

---

## Auto-discover LAN subnet

```
ipmg --discover
```

---

## Export results to CSV + XLSX

```
ipmg --formats csv xlsx
```

---

## Resolve hostnames (PTR)

```
ipmg --resolve
```

---

## Run every 10 minutes

```
ipmg --interval 10
```

---

# Testing

Run all tests:

```
uv run pytest
```

---

# Formatting & Linting

### Ruff (lint + autofix)

```
uv run ruff check . --fix
```

### Ruff formatter (PEP-style formatting)

```
uv run ruff format .
```

### Black (formatter)

```
uv run black .
```

---

# Pre-commit Hooks (auto-format on commit)

Install:

```
uv run pre-commit install
```

Run manually:

```
uv run pre-commit run --all-files
```

---

# Sample Output Summary

```
=== IPMG Summary ===
Active: 132
Inactive: 12
Unreachable: 4
Timeout: 2

Success Rate: 88.00%
```

---

# Input File Format (Excel or CSV)

Example:

| IP Address  |
| ----------- |
| 192.168.1.1 |
| 10.0.0.1    |
| 8.8.8.8     |

---

# Output File Format

| IP Address | Status | Latency | Hostname   | Timestamp           |
| ---------- | ------ | ------- | ---------- | ------------------- |
| 8.8.8.8    | Active | 12.5 ms | dns.google | 2025-10-12 18:40:15 |

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
