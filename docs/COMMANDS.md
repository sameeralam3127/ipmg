# Command reference

Every IPMG command and flag, with examples you can copy. To put together a
single scan command interactively — with every flag explained as you pick it —
use the [command builder](https://sameeralam3127.github.io/ipmg/#builder) on the
website. `ipmg --help` (and `ipmg dashboard --help`, `ipmg history --help`,
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
[Automation and exit codes](#automation-and-exit-codes) ·
[Dashboard](#dashboard) ·
[Errors and what they mean](#errors-and-what-they-mean)

---

## Commands at a glance

| Command | What it does |
| --- | --- |
| `ipmg [options]` | Scan targets and save a report (the default command) |
| `ipmg dashboard [options]` | Start the local web dashboard (`ipmg web` is an alias) |
| `ipmg history [options]` | List scans stored in the local history database |
| `ipmg diff [SCAN_ID ...] [options]` | Compare two stored scans |
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
```

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
- **If the input file does not exist, IPMG creates it** with two sample
  addresses (`8.8.8.8` and `1.1.1.1`) and scans those. This is also why plain
  `ipmg`, whose default input is `ip_list.xlsx`, creates a sample
  `ip_list.xlsx` on its first run. Check the file name if a scan shows those two
  hosts unexpectedly.

---

## Names and open ports

```bash
ipmg --input targets.txt --resolve                       # reverse DNS (PTR) name for each host
ipmg --input targets.txt --resolve --dns-cache-ttl 0     # don't cache names (default: 300 seconds)
```

Hosts without a PTR record show `Unresolvable` — that is normal.

```bash
ipmg --input targets.txt --scan-ports                                   # default port list
ipmg --input targets.txt --scan-ports --ports 22,80,443                 # your own list
ipmg --input targets.txt --scan-ports --ports 22,80,443 --port-timeout 0.5
```

Ports are only probed on hosts that answered the ping. The default list is:

| Port | Service | Port | Service |
| --- | --- | --- | --- |
| 21 | FTP | 445 | SMB |
| 22 | SSH | 1433 | Microsoft SQL Server |
| 25 | SMTP | 3306 | MySQL |
| 53 | DNS | 3389 | RDP |
| 80 | HTTP | 5432 | PostgreSQL |
| 443 | HTTPS | | |

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

---

## Reports

Every scan writes a report. Choose one or more formats with `--formats` and
the file name prefix with `--output`:

```bash
ipmg --input targets.txt                                    # results_<timestamp>.xlsx
ipmg --input targets.txt --formats csv                      # results_<timestamp>.csv
ipmg --input targets.txt --formats xlsx csv json md --output audit
```

Files are always named `<prefix>_<YYYYMMDD>_<HHMMSS>.<format>`, so repeated
scans never overwrite each other. The prefix can include a folder
(`--output reports/audit`), but the folder must already exist — otherwise the
scan runs and then fails when it tries to save. The last command above writes, for example:

```text
audit_20260911_232230.xlsx
audit_20260911_232230.csv
audit_20260911_232230.json
audit_20260911_232230.md
```

Each file has one row per host with `IP Address`, `Status`, `Latency`,
`Hostname` (with `--resolve`), `Open Ports` (with `--scan-ports`),
`Batch Timestamp`, and `Scan Duration (s)`. `Status` is one of `Active`,
`Inactive`, `Timeout`, `Unreachable`, `Invalid IP`, or `Error`. The `md` format
adds a status summary, ready to paste into a ticket.

---

## Scan history

Every scan is stored in `~/.ipmg/dashboard.db`, shared by the CLI and the
dashboard.

```bash
ipmg history                          # the 20 most recent scans
ipmg history --limit 50
ipmg history --source targets.txt     # only scans of this input ('auto-discovery' for --discover)

ipmg --input targets.txt --no-history          # scan without storing it
ipmg --input targets.txt --db ./project.db     # use a different database
ipmg history --db ./project.db
```

`--db` works the same way on `ipmg`, `ipmg history`, `ipmg diff`, and
`ipmg dashboard`.

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
| New host, host removed, IP address changed, service changed | warning |
| Host back online, hostname changed, latency changed | info |

---

## Automation and exit codes

| Exit code | Meaning |
| --- | --- |
| `0` | Success |
| `1` | Error, such as an invalid target or a missing column |
| `2` | Changes found by `ipmg diff --fail-on-change` — **or** an invalid command-line option |
| `130` | Interrupted with Ctrl+C |

Because an invalid option also exits `2`, check a scheduled command by hand
once before relying on its exit code.

A scan-then-check job for cron or a systemd timer:

```bash
#!/usr/bin/env bash
cd /opt/ipmg-audit || exit 1
mkdir -p reports    # --output needs the folder to exist
ipmg --input targets.txt --formats csv --output reports/scan || exit 1
ipmg diff --source targets.txt --fail-on-change --diff-formats md --diff-output reports/changes
status=$?
if [ "$status" -eq 2 ]; then
  echo "Network changed — see the latest reports/changes_*.md"
fi
exit "$status"
```

---

## Dashboard

```bash
ipmg dashboard                          # http://127.0.0.1:8080, opens your browser
ipmg dashboard --no-browser             # don't open a browser
ipmg dashboard --port 9000              # another port
ipmg dashboard --db ./project.db        # another history database
ipmg web                                # alias for ipmg dashboard
```

On a server without a browser, keep the default local-only binding and reach it
through an SSH tunnel from your workstation:

```bash
# on the server
ipmg dashboard --no-browser

# on your workstation, then open http://127.0.0.1:8080
ssh -L 8080:127.0.0.1:8080 user@server
```

`--host 0.0.0.0` makes the dashboard reachable from the network. It has no
authentication, so only do that behind a reverse proxy that adds it.

---

## Errors and what they mean

Invalid input is rejected before any host is contacted.

| Command | Message | Exit code |
| --- | --- | --- |
| `ipmg --input 999.999.999.999` | `Input '999.999.999.999' is neither a readable file nor a valid IP/CIDR/range target.` | `1` |
| `ipmg --input 192.168.1.0/99` | `Unsupported target input: 192.168.1.0/99` | `1` |
| `ipmg --input 192.168.1.100-192.168.1.1` | `Invalid IP range: 192.168.1.100-192.168.1.1` | `1` |
| `ipmg --input 10.0.0.0/15` | `CIDR target '10.0.0.0/15' expands to too many hosts. Maximum allowed hosts: 65536.` | `1` |
| `ipmg --input notes.pdf` | `Unsupported input file type '.pdf'. Supported types: .csv, .list, .txt, .xls, .xlsx.` | `1` |
| `ipmg --input empty.txt` | `No valid IP targets were found in 'empty.txt'.` | `1` |
| `ipmg --input hosts.csv` (no `IP Address` column) | `Input file 'hosts.csv' must contain an 'IP Address' column.` | `1` |
| `ipmg --scan-ports --ports 99999` | `argument --ports: port out of range (1-65535): 99999` | `2` |
| `ipmg --formats pdf` | `argument --formats: invalid choice: 'pdf' (choose from xlsx, csv, json, md)` | `2` |
| `ipmg --timeout 0.5` | `argument --timeout: invalid int value: '0.5'` | `2` |

More symptoms and fixes are in [Troubleshooting](TROUBLESHOOTING.md); for
running the test suite, see [CONTRIBUTING.md](../CONTRIBUTING.md#run-the-tests).
