<p align="center">
  <img src="https://raw.githubusercontent.com/sameeralam3127/ipmg/main/docs/assets/ipmg-logo.svg" alt="" width="88">
</p>

<h1 align="center">IPMG</h1>

<p align="center">
  <b>IP Management &amp; Ping Monitoring Tool</b><br>
  Know what changed on your network since the last scan.
</p>

<p align="center">
  <a href="https://pypi.org/project/ipmg/"><img src="https://img.shields.io/pypi/v/ipmg" alt="PyPI"></a>
  <a href="https://pypi.org/project/ipmg/"><img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python Version"></a>
  <a href="https://github.com/sameeralam3127/ipmg/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="License"></a>
  <a href="https://github.com/sameeralam3127/ipmg/actions/workflows/publish.yml"><img src="https://github.com/sameeralam3127/ipmg/actions/workflows/publish.yml/badge.svg" alt="Publish"></a>
</p>

<p align="center">
  🌐 <a href="https://sameeralam3127.github.io/ipmg/"><b>Website</b></a>
  &nbsp;·&nbsp;
  🖥️ <a href="https://sameeralam3127.github.io/ipmg/demo/"><b>Live demo</b></a>
  &nbsp;·&nbsp;
  🧰 <a href="https://sameeralam3127.github.io/ipmg/#builder"><b>Command builder</b></a>
  &nbsp;·&nbsp;
  📚 <a href="https://github.com/sameeralam3127/ipmg#-documentation"><b>Docs</b></a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/sameeralam3127/ipmg/main/docs/assets/ipmg-compare.gif" alt="ipmg scans 13 hosts with --stream, printing each one as it answers; a new address is added to the target file; a second scan with --compare reports it as a new host (warning) against the first" width="820">
</p>

IPMG sweeps IPs, CIDR blocks, and ranges in parallel, remembers every scan, and
tells you what changed since the last one: hosts that went down or appeared, a
new MAC address or hostname behind an address, slower replies, a web service
that started failing. Only the changes that matter reach Slack, Teams, a
webhook, or email, or fail your cron job or CI step.

## ✨ Features

- ⚡ **Fast, without root.** IPv4 and IPv6, CIDR blocks, ranges, and target
  files (text, CSV, Excel, JSON), many hosts at a time, using your system's own
  `ping`.
- 🔍 **Finds hosts that block ping** with TCP probes (`--probe icmp,tcp`), and
  checks web services (`--http-check`: status, response time, TLS, certificate
  expiry).
- 🏷️ **Names every device** by reverse DNS and, on your LAN, by MAC address
  and vendor (`--mac`). Wakes them with Wake-on-LAN (`ipmg wake`).
- 🔔 **Tells you what changed** since the last scan, with a severity for each
  change, and alerts Slack, Teams, webhooks, or email.
- 🤖 **Made for automation:** exit codes for cron and CI, a GitHub Action,
  `--json` for scripts, systemd and launchd templates, Prometheus metrics.
- 🖥️ **IPMG Web**, a local dashboard: live scans, history, changes, inventory,
  and scheduled scans.
- 📊 **Reports** in Excel, CSV, JSON, JSON Lines, and Markdown, written as the
  scan runs, so an interrupted scan keeps its results.

👉 [How IPMG compares](https://github.com/sameeralam3127/ipmg/blob/main/docs/COMPARISON.md)
with nmap, fping, and Uptime Kuma.

## 📦 Install

```bash
# Linux and macOS, no Python needed
curl -sSL https://raw.githubusercontent.com/sameeralam3127/ipmg/main/install.sh | bash
```

```powershell
# Windows, no administrator rights
irm https://raw.githubusercontent.com/sameeralam3127/ipmg/main/install.ps1 | iex
```

Or from PyPI, with Python 3.10 or newer:

```bash
# With pip, in a virtual environment
pip install "ipmg[web]"
```

```bash
# With pipx
pipx install "ipmg[web]"
```

```bash
# With uv, which fetches Python 3.10+ if you need it
uv tool install --python ">=3.10" "ipmg[web]"
```

Also on **Homebrew** (`brew install sameeralam3127/tap/ipmg`) and **Docker**
(`docker run --rm ghcr.io/sameeralam3127/ipmg --input 10.0.0.0/24`).

> 💡 `[web]` adds IPMG Web; `pip install ipmg` alone is the command line only.
> Where the system Python is older than 3.10 (RHEL 9, Ubuntu 20.04, SLES 15),
> pip and pipx quietly install an older IPMG: use the installer or uv there. The
> [install guide](https://github.com/sameeralam3127/ipmg/blob/main/docs/INSTALL.md)
> covers version pinning, upgrading from 3.x, and tab completion.

## 🚀 Quick start

```bash
ipmg --discover             # scan the network you are on, right now
ipmg --discover --compare   # later: scan again and see what changed
ipmg web --lan              # open the dashboard from any machine on your network
```

Every scan is saved to a local history (`~/.ipmg/dashboard.db`), so
`--compare` always has the previous scan to compare with.

<details>
<summary>What a scan prints</summary>

```text
  ipmg X.Y.Z  ·  scan
  ICMP probes only — scan only networks you are authorized to scan.

  Source   192.168.1.0/24
  Targets  254 hosts
  Config   50 threads · 2s timeout · 1 ping

  Results
  ● Active    12  ━───────────────────────   4.7%
  ● Timeout  242  ━━━━━━━━━━━━━━━━━━━━━━━━  95.3%

  254 hosts · 4.7% active · 3.1 ms avg · 5.21s · 2026-10-18 09:15:02

  Saved    results_20261018_091502.xlsx
```

</details>

> ⚠️ **Only scan networks you are authorized to scan.** Unauthorized scanning
> may violate your organization's policies or the law.

## 🧭 Common tasks

| I want to… | Command |
| --- | --- |
| Scan the network I am on | `ipmg --discover` |
| Scan hosts listed in a file, plus a few more | `ipmg --input targets.txt 10.0.0.5` |
| See what changed since last time | `ipmg --input targets.txt --compare` |
| Get alerted when something changes | `ipmg --input targets.txt --interval 15 --notify-slack` |
| Find hosts that block ping | `ipmg --input 10.0.0.0/24 --probe icmp,tcp` |
| Know which device each address is | `ipmg --discover --resolve --mac` |
| Check that a web service works | `ipmg --http-check https://intranet.example.com/` |
| See which services are listening | `ipmg --input targets.txt --scan-ports` |
| Get a report I can send to someone | `ipmg --input targets.txt --formats md csv` |
| Pipe the results into a script | `ipmg --input targets.txt --json \| jq .` |
| Fail a cron job or CI step when hosts are down | `ipmg --input servers.txt --fail-on-down` |
| Wake a machine | `ipmg wake AA:BB:CC:DD:EE:FF` |
| Use the dashboard from another machine | `ipmg web --lan` |
| Keep it running after logout and reboots | [systemd and launchd templates](https://github.com/sameeralam3127/ipmg/blob/main/docs/SERVICES.md) |
| See every option | `ipmg --help`, or the [command reference](https://github.com/sameeralam3127/ipmg/blob/main/docs/COMMANDS.md) |

## 🖥️ IPMG Web

```bash
ipmg web          # this machine: opens http://127.0.0.1:8080 in your browser
ipmg web --lan    # any machine on your network: prints the link to open
```

With `--lan`, IPMG Web prints the link with this machine's address and access
token, checks the firewall, and tells you the exact command that opens the
port if it is blocked (`sudo ipmg web --open-firewall` opens it only while
IPMG Web runs). Every request needs the token in that link.

<p align="center">
  <img src="https://raw.githubusercontent.com/sameeralam3127/ipmg/main/docs/assets/ipmg-web.png" alt="IPMG Web dashboard: scan totals, a status donut of 16 active, 1 timeout and 1 inactive host, a latency trend chart, and a list of recent scans" width="820">
</p>

Dashboard, live monitor, history, changes, inventory with Wake-on-LAN, and
scheduled scans; see the
[IPMG Web guide](https://github.com/sameeralam3127/ipmg/blob/main/docs/WEB.md),
or try it first in the [live demo](https://sameeralam3127.github.io/ipmg/demo/).

## 📚 Documentation

| Guide | What is in it |
| --- | --- |
| [Install](https://github.com/sameeralam3127/ipmg/blob/main/docs/INSTALL.md) | Installers, Docker, pip, Python versions, upgrading from 3.x, tab completion, verified systems |
| [Command reference](https://github.com/sameeralam3127/ipmg/blob/main/docs/COMMANDS.md) | Every command and flag with examples: targets, probes, HTTP checks, reports, history, change detection, notifications, `ipmg.toml`, exit codes |
| [IPMG Web](https://github.com/sameeralam3127/ipmg/blob/main/docs/WEB.md) | The dashboard, opening it from other machines, the firewall, scheduled scans, Prometheus metrics |
| [Web API](https://github.com/sameeralam3127/ipmg/blob/main/docs/API.md) | Scripting IPMG Web over HTTP and WebSocket |
| [Running as a service](https://github.com/sameeralam3127/ipmg/blob/main/docs/SERVICES.md) | systemd and launchd templates for scheduled scans and IPMG Web |
| [GitHub Action](https://github.com/sameeralam3127/ipmg/blob/main/docs/GITHUB-ACTION.md) | Reachability checks in CI, before a deploy or on a schedule |
| [How it compares](https://github.com/sameeralam3127/ipmg/blob/main/docs/COMPARISON.md) | IPMG next to nmap, fping, and Uptime Kuma |
| [Troubleshooting](https://github.com/sameeralam3127/ipmg/blob/main/docs/TROUBLESHOOTING.md) and [FAQ](https://github.com/sameeralam3127/ipmg/blob/main/docs/FAQ.md) | Install errors, timeouts, slow scans, empty MAC addresses, common questions |
| [Architecture](https://github.com/sameeralam3127/ipmg/blob/main/docs/ARCHITECTURE.md) | How the code fits together, for contributors |

## 🔒 Security

IPMG runs `ping` as a direct process call with no shell, validates every
target first, and needs no root. IPMG Web listens on `127.0.0.1` unless you
pass `--lan`, serves everything locally, and requires its access token on
every request, behind a strict Content-Security-Policy. The only outbound
requests IPMG makes are the notifications and HTTP checks you ask for. Found a
vulnerability? See
[SECURITY.md](https://github.com/sameeralam3127/ipmg/blob/main/.github/SECURITY.md).

## 🤝 Contributing

Contributions are welcome.
[CONTRIBUTING.md](https://github.com/sameeralam3127/ipmg/blob/main/.github/CONTRIBUTING.md)
covers the development setup, the tests, and the commit format that drives
releases, and
[ARCHITECTURE.md](https://github.com/sameeralam3127/ipmg/blob/main/docs/ARCHITECTURE.md)
explains the code. Everyone taking part is expected to follow the
[Code of Conduct](https://github.com/sameeralam3127/ipmg/blob/main/.github/CODE_OF_CONDUCT.md).

If IPMG saves you time, a ⭐ on
[GitHub](https://github.com/sameeralam3127/ipmg) helps other people find it.

## 📄 License

MIT — free for commercial and personal use.
