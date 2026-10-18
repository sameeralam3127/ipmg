# Command reference

Every IPMG command and flag, with examples you can copy. To put together a
single scan command interactively — with every flag explained as you pick it —
use the [command builder](https://sameeralam3127.github.io/ipmg/#builder) on the
website. `ipmg --help` (and `ipmg web --help`, `ipmg history --help`,
`ipmg diff --help`) always shows the options of the version you have installed.

> Only scan networks you are authorized to scan. Examples below that use
> `192.168.1.0/24` or similar are placeholders: replace them with a network you
> are allowed to scan. For a risk-free first look, start with
> [Try everything safely](#try-everything-safely), which only touches your own
> machine.

**Contents**

[Commands at a glance](#commands-at-a-glance) ·
[Try everything safely](#try-everything-safely) ·
[Choosing targets](#choosing-targets) ·
[Names and open ports](#names-and-open-ports) ·
[Live output and logs](#live-output-and-logs) ·
[Speed and accuracy](#speed-and-accuracy) ·
[Reports](#reports) ·
[Scan history](#scan-history) ·
[Change detection](#change-detection) ·
[Notifications](#notifications) ·
[Automation and exit codes](#automation-and-exit-codes) ·
[IPMG Web](#ipmg-web) ·
[Errors and what they mean](#errors-and-what-they-mean)

---

## Commands at a glance

| Command | What it does |
| --- | --- |
| `ipmg [options]` | Scan targets and save a report (the default command) |
| `ipmg web [options]` | Start IPMG Web, the local browser UI (`ipmg --web` also works) |
| `ipmg history [options]` | List scans stored in the local history database |
| `ipmg history prune [options]` | Delete old scans from the history ([retention](#keeping-history-and-reports-bounded)) |
| `ipmg diff [SCAN_ID ...] [options]` | Compare two stored scans |
| `ipmg wake MAC [MAC ...] [options]` | Wake hosts with a Wake-on-LAN magic packet ([details](#wake-on-lan)) |
| `ipmg completion bash\|zsh\|fish\|powershell` | Print a tab-completion script ([install it](../README.md#tab-completion)) |
| `ipmg --version` | Print the installed version |
| `python -m ipmg ...` | Same as `ipmg ...`, useful when the script is not on your `PATH` |

---

## Try everything safely

This session exercises scanning, target files, DNS, port probing, streaming,
every report format, history, and change detection — using only your own
machine and a throwaway folder and database, so your real scan history is not
touched.

<!-- tryout:start -->
```bash
# Work in a throwaway folder with a throwaway history database
mkdir -p ~/ipmg-tryout && cd ~/ipmg-tryout
export DB="$PWD/tryout.db"

# 1. Scan this machine
ipmg --input 127.0.0.1 --db "$DB"

# 2. Scan from a target file, with names and every result streamed live
printf '# this machine\n127.0.0.1\n' > targets.txt
ipmg --input targets.txt --resolve --stream-all --db "$DB"

# 3. Write every report format under a custom name
ipmg --input targets.txt --formats xlsx csv json md --output tryout --db "$DB"
ls tryout_*

# 4. Check a few TCP ports on this machine
ipmg --input targets.txt --scan-ports --ports 22,80,443 --port-timeout 0.5 --db "$DB"

# 5. Add a host to the file, scan again, and compare with the previous scan
printf '127.0.0.1\n127.0.0.2\n' > targets.txt
ipmg --input targets.txt --timeout 1 --compare --db "$DB"

# 6. Browse the history and the differences
ipmg history --db "$DB"
ipmg diff --db "$DB"
ipmg diff --db "$DB" --diff-formats md json --diff-output tryout-changes
ipmg diff --db "$DB" --fail-on-change; echo "exit code: $?"

# 7. Clean up
cd ~ && rm -rf ~/ipmg-tryout
```
<!-- tryout:end -->

Step 6 prints `exit code: 2`, because step 5 added a host: that is how scripts
detect change (see [Automation and exit codes](#automation-and-exit-codes)).

---

## Choosing targets

`--input` takes one target: an address, a network, a range, or a file.

```bash
ipmg --input 8.8.8.8                    # a single IP address
ipmg --input 192.168.1.0/24             # a CIDR block (network and broadcast addresses are skipped)
ipmg --input 192.168.1.1-192.168.1.50   # an inclusive range
ipmg --input targets.txt                # a file (see below)
ipmg --discover                         # the /24 around the interface your machine routes through
ipmg --input 2001:db8::/120             # IPv6 works too, mixed with IPv4 if you like
ipmg --discover ipv6                    # IPv6 hosts on the local links (neighbour discovery)
ipmg --discover all                     # both of the above
```

IPv6 probing uses `ping` on Linux and Windows and `ping6` on macOS and the
BSDs. `--discover ipv6` pings the all-nodes group (`ff02::1`) on every
interface and scans the neighbours that answer; link-local addresses keep their
interface, as in `fe80::1%eth0`. Its scans are stored in history as
`auto-discovery-ipv6`, separately from the IPv4 `auto-discovery` scans.

To scan several unrelated targets, put them in a file — `--input` does not
accept a comma-separated list.

### Target files

| Extension | Format |
| --- | --- |
| `.txt`, `.list` | One IP, CIDR block, or range per line. Blank lines and lines starting with `#` are ignored. |
| `.csv`, `.xlsx`, `.xls` | A column named exactly `IP Address`; each cell holds an IP, CIDR block, or range. Other columns are ignored. |

```bash
cat > targets.txt <<'EOF'
# Gateways
192.168.1.1

# Public DNS
8.8.8.8
1.1.1.1

# A small block and a range
10.0.0.0/30
10.0.1.10-10.0.1.20
EOF

ipmg --input targets.txt
```

```bash
printf 'IP Address\n8.8.8.8\n1.1.1.1\n' > targets.csv
ipmg --input targets.csv
```

In files, lines that are not an IP, CIDR block, or range (for example a
hostname) are skipped.

### Rules worth knowing

- **Duplicates are removed** before scanning.
- **One scan covers at most 65,536 hosts.** `10.0.0.0/16` (65,534 hosts) is
  accepted; `10.0.0.0/15` is rejected before anything is sent.
- **A range must go upwards:** `192.168.1.100-192.168.1.1` is rejected.
- **A file named with `--input` must exist.** A missing file is reported as
  `Input file '<name>' was not found.` before anything is scanned (since
  1.13.2; earlier versions created the file with sample addresses and scanned
  those). Only plain `ipmg`, run without `--input`, creates its default
  `ip_list.xlsx` — with two sample targets, `8.8.8.8` and `1.1.1.1` — if it
  does not exist yet.

---

## Names and open ports

```bash
ipmg --input targets.txt --resolve                       # reverse DNS (PTR) name for each host
ipmg --input targets.txt --resolve --dns-cache-ttl 0     # don't cache names (default: 300 seconds)
ipmg --input 10.0.0.0/16 --resolve --resolve-active-only # only look up hosts that answered
ipmg --input targets.txt --resolve --dns-timeout 5       # wait longer for a slow resolver
```

Hosts without a PTR record show `Unresolvable` — that is normal. So do hosts
whose lookup takes longer than `--dns-timeout` (default 2 seconds, range
0.1–60): a resolver that has stopped answering costs each host that long, not
the system resolver's own retry period of up to 30 seconds, and Ctrl+C never
waits on it. On a large, sparse range, `--resolve-active-only` skips the PTR
query for every address that did not answer, which is usually most of them.

```bash
ipmg --input targets.txt --scan-ports                                   # default port list
ipmg --input targets.txt --scan-ports --ports 22,80,443                 # your own list
ipmg --input targets.txt --scan-ports --ports 22,80,443 --port-timeout 0.5
```

Ports are only probed on hosts that are up. The default list is:

| Port | Service | Port | Service |
| --- | --- | --- | --- |
| 21 | FTP | 445 | SMB |
| 22 | SSH | 1433 | Microsoft SQL Server |
| 25 | SMTP | 3306 | MySQL |
| 53 | DNS | 3389 | RDP |
| 80 | HTTP | 5432 | PostgreSQL |
| 443 | HTTPS | | |

### MAC addresses and vendors

```bash
ipmg --discover --mac                          # every host on this network, with its MAC and vendor
ipmg --input 192.168.1.0/24 --mac --resolve    # names too
```

On a local network the IP alone rarely identifies a device; its MAC address
and vendor (Apple, Cisco, Raspberry Pi…) usually do, and they stay put when
DHCP moves the device. `--mac` reads both from this machine's ARP/neighbour
table after each host answers (`ip neigh` on Linux, `arp -an` and `ndp -an` on
macOS and the BSDs, `arp -a` and `netsh` on Windows), so it needs no raw
sockets or extra privileges. Vendors come from the IEEE's MA-L, MA-M, and MA-S
assignment lists, bundled with IPMG, so nothing is looked up online.

Only hosts on the same network segment have a MAC to report: traffic to
anything beyond a router goes to the router's MAC, so those hosts show an
empty MAC rather than the router's. A MAC with the "locally administered" bit
set (phones and laptops that randomise their MAC per network, VMs, containers)
has no registered vendor and is labelled `Locally administered`. In Docker,
add `--network host` (Linux) so the container sees your LAN's neighbour table.

Reports gain `MAC Address` and `Vendor` columns, and IPMG Web's inventory lists
the last MAC seen for every host. With MACs in the history, change detection
also recognises a device that DHCP moved to another IP (one `IP address
changed`, not a new host plus a removed one) and reports a different device
answering at an IP as `MAC address changed` (warning).

### Hosts that block ping

Firewalled servers, cloud instances with default security groups, and Windows
machines often drop ICMP while serving traffic, so a ping sweep reports them
as down. `--probe` changes how IPMG decides a host is up:

```bash
ipmg --input 10.0.0.0/24 --probe icmp,tcp                # ping first, TCP for hosts that did not answer
ipmg --input servers.txt --probe tcp --ports 22,443      # TCP connections only, no ping
ipmg --input servers.txt --probe tcp --port-timeout 0.5
```

| `--probe` | A host is up when |
| --- | --- |
| `icmp` (default) | it answers a ping |
| `tcp` | any of `--ports` accepts a connection or refuses it (a TCP reset) |
| `icmp,tcp` | it answers a ping, or, if not, a TCP connection as above |

Its latency is then the connect time. With `tcp` or `icmp,tcp`, reports gain a
`Probe` column (after `Open Ports`) that says which method found each host:
`icmp`, `tcp`, or empty for a host that is down. TCP probes are ordinary
connections, so they need no extra privileges, and they share the bounded
connection pool `--scan-ports` uses.

On Windows, a refused connection is only reported after about two seconds:
Windows tries a connection the other end reset twice more before giving up.
To count hosts that refuse every probed port as up there, give
`--port-timeout 3`. A port that accepts the connection is found at once on
every system.

---

## HTTP checks

A host can answer ping while the service on it is broken: a web server
returning 502s, an expired certificate, a login page that times out.
`--http-check` requests URLs and records what came back:

```bash
ipmg --http-check https://intranet.example.com/ https://grafana.example.com/login
ipmg --input servers.txt --http-check https://app.example.com/health    # hosts and URLs together
ipmg --http-check https://api.example.com/ --http-expect 200-299,401    # what counts as a pass
ipmg --http-check https://lab.local/ --http-insecure                    # self-signed certificate
ipmg --http-check https://app.example.com/ --interval 5 --compare --notify-slack
```

| Flag | Default | Meaning |
| --- | --- | --- |
| `--http-check URL ...` | none | URLs to check; repeat the flag or list several |
| `--http-timeout SECONDS` | `5` | Time allowed per check, redirects included |
| `--http-expect CODES` | `200-399` | Status codes that pass: ranges and single codes, comma-separated |
| `--http-method GET\|HEAD` | `GET` | Request method; the body is never downloaded either way |
| `--http-no-redirects` | follow | Check the redirect's own status instead of where it leads |
| `--http-insecure` | verify | Skip TLS certificate verification |

Each check records the status code, the time to the response, the URL that
redirects ended on, the expiry date of the server's certificate (verified
HTTPS only), and, if it failed, why: `dns`, `connect`, `tls`, `timeout`,
`status` (an unexpected code), `protocol`, `redirects` (more than 10), or
`invalid`. A failure is a result, never a failed scan. Checks run
concurrently, at most `--threads` at a time.

Without `--input` or `--discover`, only the URLs are checked, and history
records the run under the source `http-checks`. Results print as their own
table and are saved beside the host reports as
`<prefix>_http_<timestamp>.<format>` in every `--formats` format (they are not
part of `--json` or `--jsonl` on stdout). They are stored in the history, shown
on the scan's page in IPMG Web, and compared like hosts:

| Change | Severity | When |
| --- | --- | --- |
| `http_failing` | critical | a check that passed now fails |
| `http_status_changed` | warning | the status or failure reason changed, but not pass/fail |
| `http_recovered` | info | a failing check passes again |

The change's `ip` field holds the URL. `--fail-on-down` also fails the run
(exit status `3`) when any HTTP check failed.

---

## Live output and logs

```bash
ipmg --input 192.168.1.0/24 --stream          # print each host that answers, as it answers
ipmg --input 192.168.1.0/24 --stream-all      # print every result, including timeouts
ipmg --input 192.168.1.0/24 --stream --stream-refresh 1   # redraw the progress bar once a second
```

`--stream-refresh` takes seconds between progress-bar redraws (default `0.25`);
values outside `0.05`–`5` are clamped to that range.

When output is piped or redirected, the progress bar and colors are dropped and
each result is a plain line, so logging just works:

```bash
ipmg --input targets.txt --stream-all >> scan.log
ipmg --input targets.txt --stream-all --verbose > ipmg-debug.log 2>&1   # include debug logging
```

Colors follow the usual conventions: `NO_COLOR=1` turns them off in a
terminal, and `FORCE_COLOR=1` keeps them when piping.

---

## Speed and accuracy

| Flag | Default | Meaning |
| --- | --- | --- |
| `--threads N` | `50` | Hosts probed at the same time |
| `--timeout N` | `2` | Whole seconds to wait for each reply |
| `--count N` | `1` | Pings per host (raise it on a lossy link) |
| `--interval N` | off | Repeat the whole scan every N minutes, until you press Ctrl+C |

Unreachable hosts cost the full timeout each, so large, sparse ranges scan
faster with more threads and a shorter timeout:

```bash
ipmg --input 10.0.0.0/16 --threads 200 --timeout 1
ipmg --input targets.txt --count 3                  # more reliable on flaky links
ipmg --input targets.txt --interval 5 --compare     # rescan every 5 minutes and report changes
```

### Monitoring with `--interval`

Passes keep a fixed cadence: `--interval 5` starts a pass every five minutes
however long each scan takes, rather than sleeping five minutes after it. A
pass that overruns its slot skips to the next free one instead of starting
the next pass at once.

A monitor rides out a pass that cannot scan: the target file missing while a
tool rewrites it, `--discover` failing during a network blip, a full disk. It
prints a warning, sends a "could not scan" alert to every configured
`--notify-*` destination (whatever `--notify-severity` is set to), and tries
again at the next interval. Only the first pass is fatal, so a typo in
`--input` still ends the command at once with exit status `1`.

---

## Reports

Every scan writes a report. Choose one or more formats with `--formats` and
the file name prefix with `--output`:

```bash
ipmg --input targets.txt                                    # results_<timestamp>.xlsx
ipmg --input targets.txt --formats csv                      # results_<timestamp>.csv
ipmg --input targets.txt --formats xlsx csv json jsonl md --output audit
```

Files are always named `<prefix>_<YYYYMMDD>_<HHMMSS>.<format>`, so repeated
scans never overwrite each other. The prefix can include a folder
(`--output reports/audit`), which is created before the scan starts if it does
not exist. The last command above writes, for example:

```text
audit_20260911_232230.xlsx
audit_20260911_232230.csv
audit_20260911_232230.json
audit_20260911_232230.md
```

Each file has one row per host with `IP Address`, `Status`, `Latency`,
`Hostname` (with `--resolve`), `Open Ports` (with `--scan-ports`),
`Batch Timestamp`, and `Scan Duration (s)`. A scan that asks for more adds a
column for it after `Open Ports`: `Probe` with `--probe tcp` or
`--probe icmp,tcp`, and `MAC Address` and `Vendor` with `--mac`. `Status` is
one of `Active`,
`Inactive`, `Timeout`, `Unreachable`, `Invalid IP`, or `Error`. The `md` format
adds a status summary, ready to paste into a ticket, and `jsonl` writes one
JSON object per line for `jq` and log pipelines.

### Interrupted scans

Reports are written while the scan runs, so an interrupted pass still leaves a
valid report of the hosts it reached:

| Format | Written | After a Ctrl+C |
| --- | --- | --- |
| `csv`, `jsonl` | One row per host, as it answers | Every host scanned so far |
| `xlsx`, `json`, `md` | Re-saved every `--autosave` seconds | Everything up to the last save, plus a final save on the way out |

```bash
ipmg --input 10.0.0.0/16 --formats csv          # a row lands per host
ipmg --input 10.0.0.0/16 --autosave 10          # re-save xlsx/json/md every 10s
ipmg --input 10.0.0.0/16 --no-incremental       # only write once the scan ends
```

Each row of an unfinished report carries the time that host answered in
`Scan Duration (s)`; when the scan finishes, the file is replaced by the
complete report, in which that column is the duration of the whole pass. The
file name never changes, so a finished scan produces exactly what it always
did.

---

## Scan history

Every scan is stored in `~/.ipmg/dashboard.db`, shared by the CLI and IPMG
Web.

```bash
ipmg history                          # the 20 most recent scans
ipmg history --limit 50
ipmg history --source targets.txt     # only scans of this input ('auto-discovery' for --discover)

ipmg --input targets.txt --no-history          # scan without storing it
ipmg --input targets.txt --db ./project.db     # use a different database
ipmg history --db ./project.db
```

`--db` works the same way on `ipmg`, `ipmg history`, `ipmg diff`, and
`ipmg web`.

### Keeping history and reports bounded

Nothing is deleted unless you ask. Every scan adds a full set of rows to the
database and every pass writes a new report file per format, so an
`--interval 5` monitor writes 288 of each a day until the disk fills. Prune
the history by hand, or let each scan do it:

```bash
ipmg history prune --keep 100                   # the 100 newest scans of each source
ipmg history prune --older-than 30d             # scans older than 30 days (s, m, h, d, w)
ipmg history prune --keep 10 --older-than 30d   # only scans neither rule keeps
ipmg history prune --keep 100 --dry-run         # list what would go, delete nothing
ipmg history prune --keep 100 --vacuum          # then give the space back to the disk
ipmg history prune --keep 1 --source targets.txt

ipmg --input targets.txt --interval 5 --compare --keep-scans 2000 --keep-reports 24
```

Each source keeps its own history, and a scan is kept when any rule covers
it: one of the `--keep` newest of its source, or newer than `--older-than`.
Running scans are never deleted. `--keep-scans N` prunes the scan's own
source to N after storing and comparing it, and `--keep-reports N` deletes all
but the N newest report files of each format named after `--output` (only
files named exactly like an IPMG report). Both can live in `ipmg.toml`, so a
long-running monitor is bounded by default:

```toml
keep-scans = 2000
keep-reports = 24
```

---

## Change detection

Compare a new scan with the previous scan of the same input:

```bash
ipmg --input targets.txt --compare
ipmg --input targets.txt --compare --compare-any-source   # previous scan of any input
```

Compare stored scans (ids come from `ipmg history`):

```bash
ipmg diff                            # the two most recent scans
ipmg diff 14                         # scan 14 against the scan before it
ipmg diff 12 14                      # scan 12 (baseline) against scan 14
ipmg diff --source targets.txt       # the two most recent scans of this input
ipmg diff --limit 20                 # print at most 20 changes (exports keep all)
```

Export the change summary — files are named `<prefix>_<timestamp>.<format>`:

```bash
ipmg diff --diff-formats md json csv
ipmg diff --diff-formats md --diff-output weekly-changes
ipmg --input targets.txt --compare --diff-formats md     # export straight after a scan
```

Latency changes are only reported when they clear **both** thresholds, which
keeps normal jitter out of the report:

```bash
ipmg diff --latency-threshold 10 --latency-pct 50   # defaults: 5 ms and 25%
```

| Change | Severity |
| --- | --- |
| Host offline | critical |
| New host, host removed, IP address changed, status changed | warning |
| Host back online, hostname changed, latency changed | info |

---

## Notifications

`--compare` prints what changed. The `--notify-*` flags send it somewhere, so
someone hears about it without watching a terminal. They work on a scan and on
`ipmg diff`, and any of them turns on `--compare` for a scan.

```bash
ipmg --input servers.txt --notify-slack https://hooks.slack.com/services/…
ipmg --input servers.txt --notify-teams https://prod-00.westus.logic.azure.com/…
ipmg --input servers.txt --notify-webhook https://ops.example.com/ipmg
ipmg --input servers.txt --notify-email ops@example.com --smtp-host smtp.example.com
ipmg diff --notify-slack                  # URL from $IPMG_NOTIFY_SLACK
```

| Flag | Sends |
| --- | --- |
| `--notify-webhook [URL]` | The change report as JSON: `ipmg diff --diff-formats json` plus `event`, `headline`, `min_severity`, and `ipmg_version` |
| `--notify-slack [URL]` | A Slack message listing up to 20 changes, most severe first, to an [incoming webhook](https://api.slack.com/messaging/webhooks) |
| `--notify-teams [URL]` | The same list as an Adaptive Card, to a Teams **Workflows** webhook ("Post to a channel when a webhook request is received") |
| `--notify-email [ADDRESS ...]` | An email whose body is the Markdown change report |
| `--notify-severity LEVEL` | Only notify when a change is at least `critical`, `warning` (default), or `info` — see [severities](#change-detection) |

A notification is sent only when at least one change reaches
`--notify-severity`, and then it carries every change, so you see the context.
With `--interval`, each pass is compared with the one before it, so you hear
about a host going offline once, when it happens, and again only when
something else changes.

A monitor pass that could not scan at all sends an alert of its own, whatever
`--notify-severity` says ([details](#monitoring-with---interval)). The webhook
receives `{"event": "ipmg.scan_failed", "headline": …, "severity": "critical",
"error": …, "ipmg_version": …}` instead of a change report.

### Secrets and the environment

Webhook URLs contain their access token. Give a URL flag without a value and
IPMG reads the URL from the environment instead. That keeps the token out of
`ps`, your shell history, and your crontab:

| Setting | Environment variable |
| --- | --- |
| `--notify-webhook` | `IPMG_NOTIFY_WEBHOOK` |
| `--notify-slack` | `IPMG_NOTIFY_SLACK` |
| `--notify-teams` | `IPMG_NOTIFY_TEAMS` |
| `--notify-email` | `IPMG_NOTIFY_EMAIL` (comma-separated) |
| `--smtp-host` | `IPMG_SMTP_HOST` |
| `--smtp-port` | `IPMG_SMTP_PORT` (default 587; 465 with `ssl`, 25 with `none`) |
| `--smtp-security` | `IPMG_SMTP_SECURITY`: `starttls` (default), `ssl`, or `none` |
| `--smtp-user` | `IPMG_SMTP_USER` |
| `--smtp-from` | `IPMG_SMTP_FROM` (default: the login, else `ipmg@<this host>`) |
| — | `IPMG_SMTP_PASSWORD`, the only way to give the mail password |

A flag with a value wins over its variable. A variable on its own never turns
notifications on: you still pass the flag.

```bash
# /etc/ipmg/notify.env, readable only by the account that runs the scan
IPMG_NOTIFY_SLACK=https://hooks.slack.com/services/…
IPMG_SMTP_HOST=smtp.example.com
IPMG_SMTP_USER=ipmg@example.com
IPMG_SMTP_PASSWORD=…

# crontab: scan every 15 minutes, alert Slack and email on warnings or worse
*/15 * * * * set -a; . /etc/ipmg/notify.env; ipmg --input /opt/ipmg/targets.txt --formats csv --output /var/lib/ipmg/scan --notify-slack --notify-email ops@example.com
```

### When a notification fails

A setting that cannot work, like `--notify-email` with no mail server or a
URL that is not `http(s)://`, is an error before any host is probed (exit
`1`). Delivery is different: if Slack is down or the mail server refuses the
login, IPMG prints a warning and carries on. The scan, its reports, its
history entry, the other notifications, and the exit code are unaffected.
Error messages never include a webhook URL or the password.

---

## Automation and exit codes

| Exit code | Meaning |
| --- | --- |
| `0` | Success |
| `1` | Error, such as an invalid target or a missing column |
| `2` | Changes found by `ipmg diff --fail-on-change` — **or** an invalid command-line option |
| `3` | Hosts down: the scan failed `--fail-on-down` or `--min-active` |
| `130` | Interrupted with Ctrl+C |

Because an invalid option also exits `2`, check a scheduled command by hand
once before relying on its exit code.

A scan exits `0` however many hosts are down, unless you ask it to check:

```bash
ipmg --input servers.txt --fail-on-down      # exit 3 if any target is not Active
ipmg --input 10.0.0.0/24 --min-active 80     # exit 3 if fewer than 80% are Active
```

The reports and the history entry are written before the scan exits, so a
failed check still leaves the evidence behind. With `--interval` the checks
print a warning after every pass that fails them, and the scan keeps running.

Ready-made systemd units (a monitor, a check timer, IPMG Web) and a macOS
launchd agent are in [`contrib/`](../contrib), with a guide in
[SERVICES.md](SERVICES.md). A scan-then-check job for cron:

```bash
#!/usr/bin/env bash
cd /opt/ipmg-audit || exit 1
ipmg --input targets.txt --formats csv --output reports/scan --fail-on-down
scan_status=$?
if [ "$scan_status" -eq 3 ]; then
  echo "Hosts are down — see the latest reports/scan_*.csv"
elif [ "$scan_status" -ne 0 ]; then
  exit "$scan_status"
fi
ipmg diff --source targets.txt --fail-on-change --diff-formats md --diff-output reports/changes
status=$?
if [ "$status" -eq 2 ]; then
  echo "Network changed — see the latest reports/changes_*.md"
fi
[ "$status" -eq 0 ] && status=$scan_status
exit "$status"
```

---

## Wake-on-LAN

When a scan shows a workstation or server as down, wake it:

```bash
ipmg wake AA:BB:CC:DD:EE:FF                            # broadcast on this network segment
ipmg wake aa-bb-cc-dd-ee-ff AABBCCDDEE01               # several hosts; any common spelling
ipmg wake AA:BB:CC:DD:EE:FF --broadcast 192.168.2.255  # a directed broadcast to another subnet
ipmg wake AA:BB:CC:DD:EE:FF --port 7                   # some cards listen on 7 instead of 9
```

The magic packet (six `0xFF` bytes, then the MAC 16 times) goes out as an
ordinary UDP broadcast, with no raw sockets or administrator rights. It only
works when:

- the target has Wake-on-LAN enabled, in its firmware and its operating system;
- the broadcast reaches it: the target is on this network segment, or
  `--broadcast` names its subnet's directed broadcast address and the router
  between you forwards directed broadcasts (most do not by default).

Every MAC is checked before any packet is sent; an invalid one is an error
with exit status `1`. A scan with [`--mac`](#mac-addresses-and-vendors)
records each host's MAC, and IPMG Web's inventory then offers a **Wake**
button for it (`POST /api/v1/wake`, behind the same access token).

---

## IPMG Web

IPMG Web is the optional `web` extra. The one-line installers, Homebrew, and
the Docker image include it; after a plain `pip install ipmg`, add it with
`pip install "ipmg[web]"`.

```bash
ipmg web                                # http://127.0.0.1:8080, opens your browser
ipmg web --no-browser                   # don't open a browser
ipmg web --port 9000                    # another port
ipmg web --db ./project.db              # another history database
ipmg web --metrics --no-browser         # also serve Prometheus metrics at /metrics
ipmg web --max-scans 4                  # run up to 4 scans at once (default: 2)
ipmg --web                              # same as ipmg web
```

On a server without a browser, keep the default local-only binding and reach it
through an SSH tunnel from your workstation:

```bash
# on the server
ipmg web --no-browser

# on your workstation, then open the link the server printed
# (http://127.0.0.1:8080/#token=…)
ssh -L 8080:127.0.0.1:8080 user@server
```

Every API request needs the access token in that link. A new token is made
each time IPMG Web starts; set `IPMG_WEB_TOKEN` to keep one fixed.

### Scheduled scans

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

Each scan may use up to 500 threads, each running a `ping` process, so IPMG
Web runs at most `--max-scans` scans at once (default 2). Starting another,
from a second tab, a double click, a script, or a schedule, is refused with
"a scan is already running" (HTTP `429`) until one finishes or is cancelled.

`--metrics` adds `/metrics` for Prometheus, behind the same token, sent as a
Bearer credential (`authorization.credentials_file` in a scrape config). Pin
the token with `IPMG_WEB_TOKEN` so a restart does not break the scrape.
`--metrics-sources N` (default 20) limits it to the N most recently scanned
sources. The metrics and a sample alert rule are listed in the
[README](../README.md#prometheus-metrics).

`--host 0.0.0.0` makes IPMG Web reachable from the network. The token still
guards it, but it travels over plain HTTP, so use a reverse proxy with TLS on
any network you don't trust.

---

## Errors and what they mean

Invalid input is rejected before any host is contacted.

| Command | Message | Exit code |
| --- | --- | --- |
| `ipmg --input 999.999.999.999` | `Input '999.999.999.999' is neither a readable file nor a valid IP/CIDR/range target.` | `1` |
| `ipmg --input 192.168.1.0/99` | `Unsupported target input: 192.168.1.0/99` | `1` |
| `ipmg --input 192.168.1.100-192.168.1.1` | `Invalid IP range: 192.168.1.100-192.168.1.1` | `1` |
| `ipmg --input 10.0.0.0/15` | `CIDR target '10.0.0.0/15' expands to too many hosts. Maximum allowed hosts: 65536.` | `1` |
| `ipmg --input targts.txt` (no such file) | `Input file 'targts.txt' was not found.` | `1` |
| `ipmg --input notes.pdf` | `Unsupported input file type '.pdf'. Supported types: .csv, .list, .txt, .xls, .xlsx.` | `1` |
| `ipmg --input empty.txt` | `No valid IP targets were found in 'empty.txt'.` | `1` |
| `ipmg --input hosts.csv` (no `IP Address` column) | `Input file 'hosts.csv' must contain an 'IP Address' column.` | `1` |
| `ipmg --scan-ports --ports 99999` | `argument --ports: port out of range (1-65535): 99999` | `2` |
| `ipmg --formats pdf` | `argument --formats: invalid choice: 'pdf' (choose from xlsx, csv, json, md)` | `2` |
| `ipmg --timeout 0.5` | `argument --timeout: invalid int value: '0.5'` | `2` |

More symptoms and fixes are in [Troubleshooting](TROUBLESHOOTING.md); for
running the test suite, see [CONTRIBUTING.md](../.github/CONTRIBUTING.md#run-the-tests).
