# How IPMG compares

| | IPMG | nmap | fping | Uptime Kuma |
| --- | --- | --- | --- | --- |
| Primary purpose | Network discovery, scan history, and what changed | Network discovery and security auditing ([nmap.org](https://nmap.org/)) | Fast ICMP reachability for many hosts at once ([man page](https://fping.org/fping.8.html)) | Self-hosted uptime monitoring of individual services ([features](https://github.com/louislam/uptime-kuma#-features)) |
| Ping sweeps of CIDR blocks and ranges | Yes, one system `ping` per host, `--threads` at a time | Yes, `-sn` host discovery ([docs](https://nmap.org/book/man-host-discovery.html)) | Yes, round-robin from one process with `-g`; the fastest here ([man page](https://fping.org/fping.8.html)) | No: one Ping monitor per host ([features](https://github.com/louislam/uptime-kuma#-features)) |
| TCP checks | Connect checks on chosen ports, and `--probe tcp` for hosts that block ping | A full port scanner ([docs](https://nmap.org/book/man-port-scanning-techniques.html)) | No ([man page](https://fping.org/fping.8.html)) | A TCP monitor per host and port ([features](https://github.com/louislam/uptime-kuma#-features)) |
| HTTP checks | `--http-check`: status, time, redirects, TLS, certificate expiry | Through NSE scripts such as `http-title` ([NSE](https://nmap.org/nsedoc/scripts/http-title.html)) | No ([man page](https://fping.org/fping.8.html)) | HTTP(s), keyword, and JSON query monitors ([features](https://github.com/louislam/uptime-kuma#-features)) |
| History and "what changed" | Built in: every scan stored, changes with severities | Save XML, compare two scans with `ndiff` ([ndiff](https://nmap.org/ndiff/)) | No ([man page](https://fping.org/fping.8.html)) | Up/down state and ping charts per monitor ([features](https://github.com/louislam/uptime-kuma#-features)) |
| Alerts | Slack, Teams, webhook, email, filtered by severity | No; it writes output files for other tools ([output](https://nmap.org/book/man-output.html)) | No ([man page](https://fping.org/fping.8.html)) | 90+ notification services ([features](https://github.com/louislam/uptime-kuma#-features)) |
| Exit codes for cron and CI | `3` with `--fail-on-down`, `2` with `diff --fail-on-change` | No; parse its XML output instead ([output](https://nmap.org/book/man-output.html)) | `1` if any host is unreachable ([man page](https://fping.org/fping.8.html)) | Not a command-line tool ([install](https://github.com/louislam/uptime-kuma#-how-to-install)) |
| Reports | Excel, CSV, JSON, JSON Lines, Markdown | Normal, XML, grepable ([output](https://nmap.org/book/man-output.html)) | Plain text, with summaries (`-s`, `-C`) ([man page](https://fping.org/fping.8.html)) | Status pages ([features](https://github.com/louislam/uptime-kuma#-features)) |
| Browser UI | IPMG Web: local, offline, with scheduled scans | No; Zenmap is a desktop app ([Zenmap](https://nmap.org/zenmap/)) | No ([man page](https://fping.org/fping.8.html)) | It is a web app ([features](https://github.com/louislam/uptime-kuma#-features)) |
| Install | `pip`, `uv`, one-line installers, Homebrew, Docker | Packages and installers ([download](https://nmap.org/download.html)) | From source, or Docker ([README](https://github.com/schweikert/fping#installation)) | Docker, or Node.js ([install](https://github.com/louislam/uptime-kuma#-how-to-install)) |

Where the others are better: **nmap** is a real port, service, and OS
scanner, and IPMG does not try to be one. **fping** sends every probe from a
single process, so on large ranges it is much faster than IPMG, which starts
one `ping` per host. **Uptime Kuma** is built for watching a fixed set of
services around the clock, with status pages to share. [Angry IP
Scanner](https://angryip.org/) is a point-and-click desktop scanner with a
plugin system.

Reach for IPMG when you look after a network and need to know what moved since
yesterday, with a report you can hand to someone.

<p align="center">
  <img src="https://raw.githubusercontent.com/sameeralam3127/ipmg/main/docs/assets/ipmg-web.png" alt="IPMG Web dashboard: scan totals, a status donut of 16 active, 1 timeout and 1 inactive host, a latency trend chart, and a list of recent scans" width="820">
</p>
