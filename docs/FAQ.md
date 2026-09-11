# Frequently asked questions

Something broken rather than unclear? See
[Troubleshooting](TROUBLESHOOTING.md).

---

### Do I need root or administrator rights?

No. IPMG calls the same `ping` command you would run by hand. The installer
only writes to `~/.local/bin`, unless you run it as root — then it installs
system-wide to `/usr/local/bin` on purpose.

### Do I need a specific Python version installed?

No. The one-line installer brings its own Python, which is why it works on
RHEL 8 (system Python 3.6) and on openSUSE images with no Python at all. If you
install with pip instead, you need Python 3.9 or newer.

### Does it change anything on the hosts it scans?

No. It sends ICMP echo requests, and with `--scan-ports` it opens and
immediately closes TCP connections. Nothing is written, and nothing is logged in
on.

### Where does my scan history live?

In `~/.ipmg/dashboard.db`, on your machine only. Nothing is uploaded anywhere.
Point it elsewhere with `--db`, or skip storing a scan with `--no-history`.

### Can I run it on a schedule?

Yes — `--interval 5` repeats the scan every 5 minutes in the foreground. For
unattended runs, use cron or a systemd timer with `--compare --fail-on-change`
so a change shows up as a non-zero exit code.

### How big a range can I scan?

Up to 65,536 hosts per scan. Anything larger is rejected before the scan starts.

### Does the dashboard need internet access?

No. Everything it serves is bundled with the package.
