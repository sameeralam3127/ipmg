# IPMG Web

IPMG Web is IPMG in the browser: the same scanning engine, history, and change
detection as the command line, on a page you can share with your team. It runs
on your own machine, fully offline: every script and stylesheet is bundled,
nothing is loaded from a CDN.

<p align="center">
  <img src="https://raw.githubusercontent.com/sameeralam3127/ipmg/main/docs/assets/ipmg-web.png" alt="IPMG Web dashboard: scan totals, a status donut of 16 active, 1 timeout and 1 inactive host, a latency trend chart, and a list of recent scans" width="820">
</p>

- **Dashboard**: status donut, latency trend, and recent scans
- **New Scan**: type IPs, CIDR blocks, and ranges or upload an Excel, CSV,
  text, or JSON file; choose the probe (ICMP, TCP, or both), reverse DNS, and
  MAC lookup
- **Live Monitor**: progress and results as they arrive, over a WebSocket
- **Schedules**: scans that run on their own, every N minutes or on a cron
  schedule ([details](#scheduled-scans))
- **History**: every scan, searchable, downloadable as XLSX, CSV, JSON, or
  Markdown, with its HTTP checks and, for `ipmg --snmp` scans, each polled
  device's uptime and interfaces ([SNMP](SNMP.md))
- **Changes**: compare any two scans (new and offline hosts, IP, hostname, and
  MAC changes, latency shifts, reboots and interfaces going down) and export
  the summary
- **Inventory**: every host ever seen, with its last status, SNMP name, MAC
  address, and vendor, and a **Wake** button for hosts with a known MAC

IPMG Web is the optional `web` extra. The one-line installers, Homebrew, and
the Docker image include it; after a plain `pip install ipmg`, add it with
`pip install "ipmg[web]"`.

**Contents**

[Starting it](#starting-it) ·
[Opening it from other machines](#opening-it-from-other-machines) ·
[Scheduled scans](#scheduled-scans) ·
[Limits](#limits) ·
[Scripting IPMG Web](#scripting-ipmg-web) ·
[Prometheus metrics](#prometheus-metrics) ·
[In Docker](#in-docker)

---

## Starting it

```bash
ipmg web                         # http://127.0.0.1:8080, opens your browser
ipmg web --lan                   # let other machines open it (see below)
ipmg web --no-browser            # on a server, or over SSH
ipmg web --port 9000             # another port
ipmg web --db ./project.db       # another history database
ipmg web --max-scans 4           # run up to 4 scans at once (default: 2)
ipmg web --metrics               # also serve Prometheus metrics at /metrics
ipmg --web                       # same as ipmg web
```

| Flag | Default | Description |
| --- | --- | --- |
| `--lan` | off | Listen on every interface and print the link with this machine's address |
| `--host` | `127.0.0.1` | Listen on this address instead (this machine only, by default) |
| `--port` | `8080` | Port to listen on |
| `--open-firewall` | off | Open the port in firewalld or ufw while IPMG Web runs, then close it (needs root; implies `--lan`) |
| `--no-browser` | off | Do not open a browser |
| `--db` | `~/.ipmg/dashboard.db` | History database, shared with the command line |
| `--max-scans` | `2` | Scans that may run at once |
| `--metrics` | off | Serve Prometheus metrics at `/metrics` |
| `--metrics-sources` | `20` | Export only the N most recently scanned sources |

**The access token.** Every start creates a new token. The browser opens with
it in the link, and IPMG Web prints that link (`http://…:8080/#token=…`); the
API refuses every request without it. Opening IPMG Web in another browser, or
after a restart, takes the printed link. To keep one token across restarts,
for a bookmark, a reverse proxy, or Prometheus, set `IPMG_WEB_TOKEN`:

```bash
export IPMG_WEB_TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
ipmg web --lan
```

---

## Opening it from other machines

By default IPMG Web listens on `127.0.0.1`, so only the machine it runs on can
open it. To open it from your laptop, phone, or anywhere else on the network:

```bash
ipmg web --lan
```

It then prints the link to use, with this machine's network address and the
token, and checks the firewall:

```text
  Open     http://192.168.0.201:8080/#token=…  (from other machines)
           http://127.0.0.1:8080/#token=…      (on this machine)
  History  /root/.ipmg/dashboard.db
  Firewall firewalld blocks 8080/tcp, so other machines cannot connect yet.
           Allow it with:
             sudo firewall-cmd --add-port=8080/tcp
             sudo firewall-cmd --permanent --add-port=8080/tcp   # keep it after a reboot
           or restart with --open-firewall to open it only while IPMG Web runs.
```

**The firewall.** IPMG Web tells you which firewall is in the way and the
command that opens the port. It never changes the firewall unless you ask:

| System | Firewall | To let others in |
| --- | --- | --- |
| RHEL, Rocky, Alma, CentOS, Fedora, openSUSE, SLES | firewalld | `sudo firewall-cmd --add-port=8080/tcp`, and again with `--permanent` to keep it after a reboot |
| Ubuntu | ufw (if enabled) | `sudo ufw allow 8080/tcp` |
| Debian, Alpine, Arch | usually none | nothing to do |
| Windows | Windows Defender Firewall | allow Python when Windows asks (Private networks), or as Administrator: `netsh advfirewall firewall add rule name="IPMG Web" dir=in action=allow protocol=TCP localport=8080` |
| macOS | Application firewall (if on) | click **Allow** when macOS asks about incoming connections |

`sudo ipmg web --open-firewall` does it for you on Linux: it opens the port in
firewalld or ufw while IPMG Web runs and removes the rule when it stops (with
firewalld it is a runtime rule, so even a killed process leaves nothing behind
after a reload). A port that was already open is left alone. To close a port
you opened by hand: `sudo firewall-cmd --remove-port=8080/tcp` (and with
`--permanent`), or `sudo ufw delete allow 8080/tcp`.

**Is it safe?** Every request still needs the token, but IPMG Web speaks plain
HTTP, so anyone who can watch the network traffic could read the token. On a
network you trust, `--lan` is fine. Anywhere else, keep the default and use an
SSH tunnel, or put a reverse proxy with TLS in front
([SECURITY.md](https://github.com/sameeralam3127/ipmg/blob/main/.github/SECURITY.md)):

```bash
# on the server
ipmg web --no-browser
# on your laptop, then open the printed link
ssh -L 8080:127.0.0.1:8080 user@server
```

On a Linux server without a display, IPMG Web notices that no browser can be
opened and just prints the link.

---

## Scheduled scans

IPMG Web can run scans on its own, so continuous monitoring from the browser no
longer means leaving a terminal open. On the **Schedules** page, give a
schedule a name, its targets, and either **every N minutes** or a five-field
**cron expression** in the server's local time (`*/15 * * * *`,
`0 7 * * mon-fri`, `@daily`), plus the usual scan settings. Each schedule can
be paused, resumed, run now, or deleted (its scans stay in the history).

- Schedules are stored in the history database, so they survive a restart; a
  run that fell due while IPMG Web was stopped happens once, when it starts.
- Every run is a normal scan under the source `schedule:<name>`, so it appears
  in History, and the Changes view compares it with that schedule's previous
  run by default.
- A run is skipped, not stacked, while the schedule's previous run is still
  going or `--max-scans` scans are running. The page shows the last skip and
  why.
- An every-N-minutes schedule runs once when created or resumed and then keeps
  a fixed cadence; a cron schedule waits for its next match.

The same is available over the API under `/api/v1/schedules`
([API reference](API.md)). For scheduled scans without IPMG Web, use `--interval`
or the [service templates](SERVICES.md).

---

## Limits

Each scan may use up to 500 threads, each running a `ping` process, so IPMG
Web runs at most `--max-scans` scans at once (default 2). Starting another,
from a second tab, a double click, a script, or a schedule, is refused with
"a scan is already running" (HTTP `429`) until one finishes or is cancelled.

---

## Scripting IPMG Web

Everything the dashboard does goes through a documented, versioned REST API
under `/api/v1`, so you can start scans, fetch results, and compare scans from
your own scripts. The [API guide](https://github.com/sameeralam3127/ipmg/blob/main/docs/API.md)
covers authentication, errors, and worked `curl` examples; the running server
also serves interactive docs at `http://127.0.0.1:8080/docs`.

---

## Prometheus metrics

`ipmg web --metrics` serves `/metrics` in the Prometheus text format, so the
results of every scan, whether run from cron with the CLI or from the browser,
land in the dashboards and alerts you already have. It reports the latest
completed scan of each source, and it is off unless you pass the flag:

```bash
IPMG_WEB_TOKEN=$(cat /etc/ipmg/token) ipmg web --metrics --no-browser
```

```yaml
# prometheus.yml: the token is the same one the web UI uses
scrape_configs:
  - job_name: ipmg
    authorization:
      credentials_file: /etc/prometheus/ipmg-token
    static_configs:
      - targets: ["127.0.0.1:8080"]

# an alert rule: a host that stopped answering
groups:
  - name: ipmg
    rules:
      - alert: HostDown
        expr: ipmg_host_up == 0
        for: 10m
        annotations:
          summary: "{{ $labels.ip }} ({{ $labels.source }}) is not answering ping"
```

| Metric | Labels | Meaning |
| --- | --- | --- |
| `ipmg_host_up` | `source`, `ip` | 1 if the host answered, else 0 |
| `ipmg_host_latency_seconds` | `source`, `ip` | Round-trip time, for hosts that answered |
| `ipmg_host_open_ports` | `source`, `ip` | Open TCP ports, for scans run with `--scan-ports` |
| `ipmg_host_info` | `source`, `ip`, `hostname` | Always 1; carries the reverse DNS name |
| `ipmg_scan_hosts` | `source`, `status` | Hosts in the latest scan, by status |
| `ipmg_scan_duration_seconds` | `source` | How long the latest scan took |
| `ipmg_scan_timestamp_seconds` | `source` | When the latest scan finished; alert on `time() - this` to catch a stalled cron job |
| `ipmg_scans_total` | `source` | Completed scans stored for the source |
| `ipmg_metrics_sources_omitted` | | Sources left out by `--metrics-sources` |
| `ipmg_build_info` | `version` | Always 1 |

**Cardinality is bounded.** Host series carry only `source` and `ip`, never
the hostname or status, which change, so a rename does not start a new series.
Only the `--metrics-sources` most recently scanned sources are exported
(default 20), and a scan holds at most 65,536 hosts, so the page stays at
about `sources × hosts × 4` series at most. Give recurring scans a stable
input (the same file) so each one updates its source rather than adding one.

---

## In Docker

Inside a container IPMG Web must listen on `0.0.0.0`, or nothing outside the
container could reach it. The [`compose.yaml`](https://github.com/sameeralam3127/ipmg/blob/main/compose.yaml) in this
repository does that and publishes the port on the host's `127.0.0.1` only.
Set a fixed `IPMG_WEB_TOKEN` in `.env`, then:

```bash
docker compose up -d                                  # http://127.0.0.1:8080/#token=<your token>
docker compose run --rm scan --input 10.0.0.0/24      # CLI scans land in the same history
```

To open it from other machines, publish the port on every interface
(`"8080:8080"` in `compose.yaml`) and allow it in the host's firewall as above.
