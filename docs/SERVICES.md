# Running IPMG as a service

`ipmg --interval N` repeats a scan, but only while its terminal is open, and
`ipmg web` stops when you log out. To keep either running across logouts and
reboots, run it as a service. The templates in
[`contrib/`](https://github.com/sameeralam3127/ipmg/tree/main/contrib) do that
the careful way: as a dedicated non-root user, with the history database and
reports in one known place, and IPMG Web bound to `127.0.0.1` only.

| Template | What it runs |
| --- | --- |
| [`systemd/ipmg-scan.service`](../contrib/systemd/ipmg-scan.service) | A long-running monitor: `ipmg --interval 15 --compare`, restarted if it ever exits |
| [`systemd/ipmg-check.service`](../contrib/systemd/ipmg-check.service) + [`ipmg-check.timer`](../contrib/systemd/ipmg-check.timer) | One scan every 15 minutes, then `ipmg diff --fail-on-change`: a change makes the unit fail |
| [`systemd/ipmg-web.service`](../contrib/systemd/ipmg-web.service) | IPMG Web on `127.0.0.1:8080` |
| [`launchd/io.github.sameeralam3127.ipmg.scan.plist`](../contrib/launchd/io.github.sameeralam3127.ipmg.scan.plist) | The monitor on macOS, as your own user |

Pick the monitor *or* the check timer, not both: they would scan the same
targets twice. The monitor alerts through `--notify-*`; the timer turns a
change into a failed unit, which suits hosts already watched for failed units.

When output is not a terminal, IPMG prints plain lines instead of a progress
bar, so the journal and log files stay readable. Nothing is deleted unless you
ask, so the templates keep the newest 96 reports per format and 2,000 scans
(`--keep-reports`, `--keep-scans`); change or drop those to suit.

**Contents**

[Placeholders](#placeholders) ·
[systemd (Linux)](#systemd-linux) ·
[launchd (macOS)](#launchd-macos) ·
[Uninstalling](#uninstalling)

---

## Placeholders

Lines marked `CHANGE` in the templates hold paths you will want to adjust:

| Placeholder | Meaning | Find yours with |
| --- | --- | --- |
| `/usr/local/bin/ipmg`, `/Users/YOU/.local/bin/ipmg` | The `ipmg` executable | `command -v ipmg` |
| `/etc/ipmg/targets.txt`, `/Users/YOU/ipmg/targets.txt` | What to scan: a file of IPs, CIDR blocks, and ranges ([format](COMMANDS.md#choosing-targets)) | |
| `/var/lib/ipmg/history.db` (`--db`) | Scan history: what change detection compares against | |
| `/var/lib/ipmg/reports/scan` (`--output`) | Report folder and file prefix; the folder is created if missing | |

The systemd units keep everything they write under `/var/lib/ipmg`, the
service's own `StateDirectory`, which systemd creates and gives to the `ipmg`
user. Everything else on the system is read-only to them (`ProtectSystem=strict`).

---

## systemd (Linux)

**1. Install IPMG where the service user can run it**, for example in its own
virtual environment (or use any install where `ipmg` is on a system path):

```bash
sudo python3 -m venv /opt/ipmg
sudo /opt/ipmg/bin/pip install "ipmg[web]"
sudo ln -s /opt/ipmg/bin/ipmg /usr/local/bin/ipmg
```

**2. Create the service user and the configuration:**

```bash
sudo useradd --system --home-dir /var/lib/ipmg --shell /usr/sbin/nologin ipmg
sudo mkdir -p /etc/ipmg
printf '192.168.1.0/24\n' | sudo tee /etc/ipmg/targets.txt
```

Optional, for notifications: put the settings in `/etc/ipmg/notify.env`,
readable only by root (systemd reads it before dropping to the `ipmg` user):

```bash
sudo install -m 600 /dev/null /etc/ipmg/notify.env
sudoedit /etc/ipmg/notify.env      # e.g. IPMG_NOTIFY_SLACK=https://hooks.slack.com/services/...
```

and add the matching flag, such as `--notify-slack`, to `ExecStart`. Each
`--notify-*` flag given without a URL reads it from its environment variable
([details](COMMANDS.md#notifications)).

**3. Install and start the units you want:**

```bash
sudo cp contrib/systemd/ipmg-scan.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ipmg-scan.service
```

For the check timer instead, run one scan by hand first, so the first timed
check has a scan to compare with (otherwise it fails once):

```bash
sudo cp contrib/systemd/ipmg-check.service contrib/systemd/ipmg-check.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start ipmg-check.service       # the baseline
sudo systemctl enable --now ipmg-check.timer
```

For IPMG Web, set a fixed token so its link survives restarts, then enable it:

```bash
echo "IPMG_WEB_TOKEN=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')" \
  | sudo tee /etc/ipmg/web.env >/dev/null && sudo chmod 600 /etc/ipmg/web.env
sudo cp contrib/systemd/ipmg-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ipmg-web.service
```

Reach it from your workstation through an SSH tunnel
(`ssh -L 8080:127.0.0.1:8080 you@server`), then open
`http://127.0.0.1:8080/#token=<the token>`. To serve it more widely, put a
reverse proxy with TLS in front; do not change `--host`.

**Logs and status:**

```bash
systemctl status ipmg-scan.service
journalctl -u ipmg-scan.service -f                 # follow the monitor
journalctl -u ipmg-check.service --since today     # what the checks found
systemctl list-timers ipmg-check.timer             # when the next check runs
systemctl --failed                                 # a check that found changes
ls /var/lib/ipmg/reports/                          # the reports
sudo -u ipmg ipmg history --db /var/lib/ipmg/history.db
```

`systemd-analyze verify /etc/systemd/system/ipmg-*.service` checks your edited
copies. The templates in this repository are verified in CI.

**ping and service hardening.** The units do not set `NoNewPrivileges=`, on
purpose: on systems where `ping` is setuid or carries the `cap_net_raw` file
capability, it would make every probe fail with "Operation not permitted". If
your system uses unprivileged ICMP sockets (`sysctl net.ipv4.ping_group_range`
covers the `ipmg` user's group, as systemd's defaults do), you can add it.

---

## launchd (macOS)

The agent runs as your own user, starts at login, and is restarted if it ever
exits.

```bash
mkdir -p ~/ipmg/reports ~/Library/Logs/ipmg
printf '192.168.1.0/24\n' > ~/ipmg/targets.txt
cp contrib/launchd/io.github.sameeralam3127.ipmg.scan.plist ~/Library/LaunchAgents/
```

Edit the copy: replace every `/Users/YOU` with your home folder and the
`ipmg` path with the output of `command -v ipmg`. Add notification settings
under `EnvironmentVariables` and the matching `--notify-*` flags to
`ProgramArguments`. Check and load it:

```bash
plutil -lint ~/Library/LaunchAgents/io.github.sameeralam3127.ipmg.scan.plist
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/io.github.sameeralam3127.ipmg.scan.plist
```

**Logs and status:**

```bash
launchctl print "gui/$(id -u)/io.github.sameeralam3127.ipmg.scan" | head -20
tail -f ~/Library/Logs/ipmg/scan.log
log show --last 1h --predicate 'process == "launchd"' | grep ipmg   # launchd's own messages
```

On macOS 15 and later, `--mac` needs **Local Network** permission for the
program that runs IPMG ([troubleshooting](TROUBLESHOOTING.md)).

---

## Uninstalling

systemd:

```bash
sudo systemctl disable --now ipmg-scan.service ipmg-check.timer ipmg-web.service
sudo rm /etc/systemd/system/ipmg-{scan,check,web}.service /etc/systemd/system/ipmg-check.timer
sudo systemctl daemon-reload
sudo rm -r /var/lib/ipmg /etc/ipmg      # the history, reports, and settings
sudo userdel ipmg
```

launchd:

```bash
launchctl bootout "gui/$(id -u)/io.github.sameeralam3127.ipmg.scan"
rm ~/Library/LaunchAgents/io.github.sameeralam3127.ipmg.scan.plist
rm -r ~/ipmg ~/Library/Logs/ipmg        # the history, reports, and logs
```
