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

## Features

- Fully modular Python package (`src/ipmg`)
- System-wide CLI command: `ipmg`
- Test coverage via `pytest`
- Formatting and linting via `ruff` and `black`
- CI-friendly project structure

---

# Installation

## Option 1 — Install from PyPI (recommended for most users)

Install the latest stable release (**ipmg 1.0.2**) from PyPI:

```bash
pip install ipmg
```

Verify installation:

```bash
ipmg --help
```

---

## Option 2 — Install via uv (recommended for isolated global install)

```bash
uv tool install git+https://github.com/sameeralam3127/ipmg.git
```

Test:

```bash
ipmg --help
```

---

## Option 3 — Install via pip (editable, development mode)

```bash
git clone https://github.com/sameeralam3127/ipmg.git
cd IP_Management
pip install -e .
```

Verify:

```bash
ipmg --help
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
```

---

| Use Case                        | Command                             | Description                                                                  |
| ------------------------------- | ----------------------------------- | ---------------------------------------------------------------------------- |
| Basic Example (Default Input)   | `ipmg`                              | Runs with default config. Creates `ip_list.xlsx` with sample IPs if missing. |
| Scan a Custom Input File        | `ipmg --input network_devices.xlsx` | Scans IPs from the specified Excel file.                                     |
| Auto-discover LAN Subnet        | `ipmg --discover`                   | Automatically detects and scans devices in the local subnet.                 |
| Export Results to CSV + XLSX    | `ipmg --formats csv xlsx`           | Exports scan results in CSV and Excel formats.                               |
| Resolve Hostnames (PTR Records) | `ipmg --resolve`                    | Performs reverse DNS (PTR) lookups for hostnames.                            |
| Run Every 10 Minutes            | `ipmg --interval 10`                | Repeats the scan every 10 minutes.                                           |

If `ip_list.xlsx` does not exist → it will be created with sample IPs.

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
