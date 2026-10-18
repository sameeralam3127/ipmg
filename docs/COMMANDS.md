# Command reference

Every IPMG command and flag, with examples you can copy. To put together a
single scan command interactively — with every flag explained as you pick it —
use the [command builder](https://sameeralam3127.github.io/ipmg/#builder) on the
website. `ipmg --help` (and `ipmg web --help`, `ipmg history --help`,
`ipmg diff --help`) always shows the options of the version you have installed;
[All scan options](#all-scan-options) lists them here.

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
[HTTP checks](#http-checks) ·
[Live output and logs](#live-output-and-logs) ·
[Speed and accuracy](#speed-and-accuracy) ·
[Reports](#reports) ·
[Scan history](#scan-history) ·
[Change detection](#change-detection) ·
[Notifications](#notifications) ·
[Default options in a file](#default-options-in-a-file) ·
[Automation and exit codes](#automation-and-exit-codes) ·
[Wake-on-LAN](#wake-on-lan) ·
[IPMG Web](#ipmg-web) ·
[All scan options](#all-scan-options) ·
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
| `ipmg completion bash\|zsh\|fish\|powershell` | Print a tab-completion script ([install it](INSTALL.md#tab-completion)) |
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

Anywhere IPMG takes `--input`, you can give it any of these:

- **A single IP** — `8.8.8.8`, or IPv6 such as `2001:db8::1` or a link-local
  `fe80::1%eth0`
- **A CIDR block** — `10.0.0.0/24`, or an IPv6 prefix up to 65,536 hosts
  (`2001:db8::/112`)
- **A range** — `10.0.0.1-10.0.0.200` or `2001:db8::10-2001:db8::20`
- **A text file** — one IP or CIDR per line. Blank lines and `#` comments are
  ignored, so you can annotate it:

  ```text
  # Production DNS
  8.8.8.8
  192.168.1.0/30
  ```

- **An Excel or CSV file** (`.xlsx`, `.csv`) — must contain a column
  named `IP Address`. Cells can hold single addresses or CIDR blocks:

  | IP Address  |
  | ----------- |
  | 192.168.1.1 |
  | 10.0.1.0/30 |

- **A JSON file** (`.json`) — a list of addresses, a list of objects keyed by
  `IP Address`, `ip`, or `target`, or an object with a `targets` or `ips` array:

  ```json
  ["192.168.1.1", "10.0.1.0/30"]
  ```

  Because `IP Address` is one of the keys it accepts, a report IPMG wrote with
  `--formats json` can be fed straight back in:

  ```bash
  ipmg --input results_20260628_120000.json
  ```

`--input` takes as many of these as you like, in any mix, and may also be
repeated:

```bash
ipmg --input targets.txt 10.0.0.0/30 10.0.0.5
ipmg --input targets.txt --input 10.0.0.5     # the same thing
```

IPv4 and IPv6 targets mix freely in one scan, and reports, history, and change
detection handle both. An IPv6 `/64` holds 2^64 addresses, far too many to
sweep one by one, so it is rejected with a pointer to `--discover ipv6`, which
finds the hosts on your local links through neighbour discovery instead:

```bash
ipmg --discover ipv6      # IPv6 neighbours on the local links
ipmg --discover all       # the IPv4 /24 and the IPv6 neighbours together
```

Duplicate targets are removed automatically — across sources too, so a host
that is both in the file and on the command line is scanned once — and one scan
expands to at most 65,536 hosts in total. Larger CIDR blocks, ranges, or
combinations are rejected up front, before the scan starts.

### Rules worth knowing

- **A range must go upwards:** `192.168.1.100-192.168.1.1` is rejected.
- **In files, a line that is not an IP, CIDR block, or range** (a hostname, for
  example) is skipped.
- **A file named with `--input` must exist.** A missing file is reported as
  `Input file '<name>' was not found.` before anything is scanned. Only plain
  `ipmg`, run without `--input`, creates its default `ip_list.xlsx`, with two
  sample targets (`8.8.8.8` and `1.1.1.1`), if it does not exist yet.

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

<p align="center">
  <img src="https://raw.githubusercontent.com/sameeralam3127/ipmg/main/docs/assets/ipmg-demo.gif" alt="ipmg scanning 13 hosts in parallel: live results with reverse DNS names and latency, then a summary of 10 active and 3 timed out" width="820">
</p>

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

### Piping results into a script

`--json` prints the finished scan to stdout as
a JSON array, and `--jsonl` prints one object per host the moment its probe
finishes. The human output moves to stderr, so stdout is nothing but data and no
temp file or glob is needed:

```bash
ipmg --input 10.0.0.0/24 --json | jq '.[] | select(.Status == "Active")'
ipmg --input 10.0.0.0/24 --jsonl | while read -r host; do notify "$host"; done
ipmg --input 10.0.0.0/24 --json 2>/dev/null > hosts.json   # data only
```

The field names are the report columns above, and both flags print a host
identically — `--json` is what `--jsonl` prints, gathered into an array. Unless
you ask for `--formats` explicitly, a piped scan writes no report file at all.
Exit codes are unchanged.

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

| Change | Severity | Meaning |
| --- | --- | --- |
| Host offline | critical | Reachable in the baseline, not reachable now |
| HTTP check failing | critical | An `--http-check` URL that passed now fails |
| New host | warning | An IP that the baseline never saw |
| Host removed | warning | An IP the current scan no longer covers |
| IP address changed | warning | A known hostname, or with `--mac` a known MAC, moved to a different IP |
| Status changed | warning | Status moved between failure modes (e.g. `Timeout` → `Unreachable`) |
| MAC address changed | warning | With `--mac`: a different device answers at the same IP |
| HTTP status changed | warning | An HTTP check's status or failure reason changed |
| Host back online | info | Recovered since the baseline |
| Hostname changed | info | Same IP, different PTR record |
| Latency changed | info | Latency moved past both thresholds |
| HTTP check recovered | info | A failing HTTP check passes again |

By default a scan is compared with the previous scan **of the same target
source**, so file-based and `--discover` runs do not get mixed up;
`--compare-any-source` takes the previous scan whatever its source.

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

## Default options in a file

If every run repeats the same flags, put them in **`ipmg.toml`** next to your
work instead:

```toml
threads = 200
timeout = 1
resolve = true
formats = ["md", "csv"]

[profile.datacenter]
threads = 400
scan-ports = true
ports = "22,80,443"
```

```bash
ipmg --input targets.txt                        # uses the file's defaults
ipmg --input targets.txt --profile datacenter   # and the profile on top
ipmg --input targets.txt --threads 20           # a flag always wins
```

Any long flag can be a key, written as the flag is (`scan-ports`) or with
underscores (`scan_ports`). A switch takes `true` to mean "as if the flag were
passed" — `no-history = true` is `--no-history`. Files are read from
`~/.config/ipmg/config.toml` first (or `$XDG_CONFIG_HOME`), then `./ipmg.toml`
on top, so a project can override your global defaults:

| Flag | What it does |
| --- | --- |
| `--config PATH` | Read that file instead of searching |
| `--no-config` | Ignore every file and use the built-in defaults |
| `--profile NAME` | Apply the `[profile.NAME]` section as well |

**The command line always wins.** A flag that appears on it ignores the file
entirely for that flag — including `--input`, which merges several sources on
one command line but replaces the file's list rather than adding to it.

A key that is not a flag, a value of the wrong type, or a value outside a
flag's choices is an error naming the key and the file it came from:

```text
✗ Unknown option 'thredas' in ipmg.toml. Did you mean 'threads'?
✗ 'formats' in ipmg.toml: 'pdf' is not one of xlsx, csv, json, jsonl, md.
```

A project's `./ipmg.toml` comes with whatever directory you scan from,
including a repository you just cloned, so it cannot say where results are
sent: the `--notify-*` destinations and `--smtp-*` settings are only read from
`~/.config/ipmg/config.toml` or a file you pass with `--config`. A file also
cannot combine flags that exclude each other, such as `json` and `jsonl`.

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

```bash
ipmg web            # this machine only
ipmg web --lan      # other machines too: prints the link and any firewall step
```

Everything about IPMG Web, including opening it from other machines, the
firewall, scheduled scans, the access token, and Prometheus metrics, is in
[WEB.md](WEB.md).

---

## All scan options

Generated from `ipmg --help`, which always has the current set. The other
commands list theirs with `ipmg web --help`, `ipmg history --help`,
`ipmg history prune --help`, `ipmg diff --help`, `ipmg wake --help`, and
`ipmg completion --help`.

**General**

| Flag | Default | Description |
| --- | --- | --- |
| `--input TARGETS` | none | One or more IPs, CIDR blocks, ranges, or target files (.txt, .list, .csv, .json, .xls, .xlsx). Every source is merged and de-duplicated, and the flag may be repeated. Without --input or --discover, ip_list.xlsx is used and created with sample targets if it does not exist. |
| `--output PREFIX` | `results` | Report file name prefix; the timestamp is appended (default: results). |
| `--timeout SECONDS` | `2` | Seconds to wait for a reply from each host (default: 2). |
| `--count N` | `1` | Pings per host; raise it on a lossy link (default: 1). |
| `--threads N` | `50` | How many hosts to probe at once (default: 50). |
| `--formats FORMAT` | none | One or more report formats: xlsx, csv, json, jsonl, md (default: xlsx, or no report file at all with --json or --jsonl). Choices: `xlsx`, `csv`, `json`, `jsonl`, `md`. |
| `--discover FAMILY` | none | Scan this machine's networks instead of --input: ipv4 (the default) sweeps the local /24, ipv6 finds hosts on the local links through neighbour discovery, all does both. Choices: `ipv4`, `ipv6`, `all`. |
| `--resolve` | off | Look up each host's name with a reverse DNS (PTR) query. |
| `--mac` | off | Add each responding host's MAC address and its vendor, read from this machine's ARP/neighbour table (hosts on the local network only). |
| `--dns-cache-ttl SECONDS` | `300` | Cache reverse DNS results for this many seconds (default: 300). |
| `--dns-timeout SECONDS` | `2.0` | Record a host as Unresolvable when its reverse DNS lookup takes longer (default: 2, range 0.1-60). |
| `--resolve-active-only` | off | With --resolve, only look up hosts that answered the probe. |
| `--interval MINUTES` | none | Repeat the whole scan every N minutes until interrupted. |
| `--verbose` | off | Debug logging. |
| `--web` | off | Start IPMG Web, the local browser UI (same as 'ipmg web'). |

**Exit status (for cron and monitoring)**

| Flag | Default | Description |
| --- | --- | --- |
| `--fail-on-down` | off | Exit with status 3 if any target is not Active. Reports are still written. |
| `--min-active PERCENT` | none | Exit with status 3 if fewer than PERCENT of the targets are Active (0-100). |

**TCP checks**

| Flag | Default | Description |
| --- | --- | --- |
| `--probe` | `icmp` | How to tell a host is up: icmp (ping, the default), tcp (a connection to any of --ports, accepted or refused), or icmp,tcp (TCP only for hosts that did not answer the ping, for hosts that block ICMP). Choices: `icmp`, `tcp`, `icmp,tcp`. |
| `--scan-ports` | off | List which of --ports are open on every host that is up (off by default). |
| `--ports PORTS` | `21,22,25,53,80,443,445,1433,3306,3389,5432` | Comma-separated TCP ports for --scan-ports and --probe tcp (default: 21,22,25,53,80,443,445,1433,3306,3389,5432). |
| `--port-timeout SECONDS` | `1.0` | Connect timeout per port, for --scan-ports and --probe tcp (default: 1). |

**HTTP checks**

| Flag | Default | Description |
| --- | --- | --- |
| `--http-check URL` | none | Request each URL and record its status, response time, and why it failed. |
| `--http-timeout SECONDS` | `5.0` | Seconds per check, redirects included (default: 5). |
| `--http-expect CODES` | `200-399` | Status codes that pass, such as 200-299,401 (default: 200-399). |
| `--http-method` | `GET` | Request method (default: GET). Choices: `GET`, `HEAD`. |
| `--http-no-redirects` | off | Do not follow redirects; the redirect's own status is checked. |
| `--http-insecure` | off | Do not verify TLS certificates (for self-signed lab hosts; not recommended). |

**Report writing**

| Flag | Default | Description |
| --- | --- | --- |
| `--no-incremental` | off | Only write the report once the scan has finished. |
| `--autosave SECONDS` | `30.0` | How often a running scan re-saves the xlsx, json, and md reports (default: 30, range: 1-3600). csv and jsonl are written per host regardless. |
| `--keep-reports N` | none | After writing this scan's reports, delete all but the N newest report files of each format named after --output (off by default). |
| `--resume REPORT` | none | Finish an interrupted scan: skip the hosts its report already holds and complete that report. REPORT is its jsonl, csv, json, or xlsx file (default: the newest report named after --output). |

**Machine-readable output**

| Flag | Default | Description |
| --- | --- | --- |
| `--json` | off | Print the finished scan to stdout as a JSON array, with the human output on stderr, for piping into jq or a script. |
| `--jsonl` | off | Stream one JSON object per host to stdout as each probe finishes, with the human output on stderr. |

**Live output**

| Flag | Default | Description |
| --- | --- | --- |
| `--stream` | off | Print each host that answers as soon as its probe finishes. |
| `--stream-all` | off | Stream every result, including hosts that did not answer (implies --stream). |
| `--stream-refresh SECONDS` | `0.25` | Seconds between progress-bar redraws while streaming (default: 0.25, range 0.05-5.0). |

**Scan history**

| Flag | Default | Description |
| --- | --- | --- |
| `--no-history` | off | Do not store this scan in the local history database. |
| `--compare` | off | Compare this scan against the previous one and print a change report (implied by any --notify-* flag). |
| `--compare-any-source` | off | Compare against the previous scan even if it used a different target source. |
| `--keep-scans N` | none | After storing this scan, delete all but the N newest stored scans of its source (off by default). |
| `--db PATH` | none | Scan history database file (default: ~/.ipmg/dashboard.db). |
| `--diff-formats FORMAT` | `` | Export the change summary as md, json, csv. Choices: `md`, `json`, `csv`. |
| `--diff-output BASENAME` | `changes` | Base filename for exported change summaries (default: changes). |

**Change detection thresholds**

| Flag | Default | Description |
| --- | --- | --- |
| `--latency-threshold MS` | `5.0` | Minimum latency delta in milliseconds before it is reported (default: 5). |
| `--latency-pct PERCENT` | `25.0` | Minimum relative latency change before it is reported (default: 25). |

**Configuration file**

| Flag | Default | Description |
| --- | --- | --- |
| `--config PATH` | none | Read default options from this file instead of searching for ipmg.toml. |
| `--no-config` | off | Ignore every configuration file and use the built-in defaults. |
| `--profile NAME` | none | Apply the [profile.NAME] section of the configuration file. |

**Change notifications**

| Flag | Default | Description |
| --- | --- | --- |
| `--notify-webhook URL` | none | POST the change report as JSON to URL (or $IPMG_NOTIFY_WEBHOOK). |
| `--notify-slack URL` | none | Post the changes to a Slack incoming webhook (or $IPMG_NOTIFY_SLACK). |
| `--notify-teams URL` | none | Post the changes to a Microsoft Teams Workflows webhook (or $IPMG_NOTIFY_TEAMS). |
| `--notify-email ADDRESS` | none | Email the Markdown change report to these addresses (or the comma-separated $IPMG_NOTIFY_EMAIL). Needs --smtp-host. |
| `--notify-severity` | `warning` | Only notify when a change is at least this severe (default: warning). Choices: `critical`, `warning`, `info`. |
| `--smtp-host HOST` | none | Mail server for --notify-email (or $IPMG_SMTP_HOST). |
| `--smtp-port PORT` | none | Mail server port (or $IPMG_SMTP_PORT; default: 587, 465 with ssl, 25 with none). |
| `--smtp-security` | none | How to encrypt the mail connection (or $IPMG_SMTP_SECURITY; default: starttls). Choices: `starttls`, `ssl`, `none`. |
| `--smtp-user USER` | none | Mail server login (or $IPMG_SMTP_USER). The password is read from $IPMG_SMTP_PASSWORD. |
| `--smtp-from ADDRESS` | none | Sender address (or $IPMG_SMTP_FROM; default: the login, else ipmg@<this host>). |

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
