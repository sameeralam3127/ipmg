# Troubleshooting

Something not working? Find the symptom below. If it is not listed, search
the [issues](https://github.com/sameeralam3127/ipmg/issues) or open a new one.
See also the [FAQ](FAQ.md).

**Contents**

[Installing](#installing) ·
[Scanning](#scanning) ·
[Input files](#input-files) ·
[Dashboard](#dashboard)

---

## Installing

### `error: externally-managed-environment` when running `pip install ipmg`

Your distribution blocks installs into the system Python (Ubuntu 23.04+,
Debian 12+, Fedora 38+). Use the one-line installer, `uv tool install ipmg`, or
`pipx install ipmg` — see
[Installing with pip](../README.md#installing-with-pip).

### `command not found: ipmg` right after installing

The install directory is not on your `PATH` yet. Open a new terminal first —
the installer adds it to your shell profile. Still missing? Run it directly
from `~/.local/bin/ipmg`, or `python -m ipmg` if you installed with pip.

### The installer fails on a minimal image

Bare container and cloud images often lack `curl`, `tar`, or `gzip`. The
installer names exactly what is missing and the command that installs it, or
you can let it do the work: add `--with-deps`. On Alpine, run it with `bash`
(`apk add bash`) — the script needs more than busybox `sh` provides.

### `The system 'ping' command is not available`

IPMG installed fine, but your image has no ping. Install it with the command
for your distribution — see
[The one thing IPMG needs](../README.md#the-one-thing-ipmg-needs-from-your-system).

---

## Scanning

### Every host comes back `Timeout`

Something is dropping ICMP — a host firewall, a VPN, or a cloud security group.
Confirm by running `ping` by hand against one of the addresses: if that fails
too, it is the network and not IPMG. Note that `--scan-ports` will not help
here — ports are only probed on hosts that already answered a ping.

### The scan is slower than I expected

Unreachable hosts cost you the full `--timeout` each. On a big range, raise
`--threads` and lower `--timeout`:

```bash
ipmg --input 10.0.0.0/16 --threads 200 --timeout 1
```

### `--discover` scanned the wrong network

It uses the interface your machine routes out of, which on a VPN is the VPN.
Pass the network you meant explicitly: `ipmg --input 192.168.1.0/24`.

### Hostname shows `Unresolvable`

That host has no DNS PTR record. Nothing is broken — there is simply no name to
look up.

---

## Input files

### `Input file 'targets.txt' was not found`

IPMG could not find the file you passed to `--input`. Check the spelling and
the folder you are running from — a relative path is looked up from your
current directory. Only plain `ipmg`, run without `--input`, creates a sample
file (`ip_list.xlsx`) for you.

### My input file was rejected

Check the extension is one IPMG reads (`.xlsx`, `.xls`, `.csv`, `.txt`,
`.list`), and that spreadsheets and CSVs have a column named exactly
`IP Address`.

---

## Dashboard

### The dashboard port is already in use

Pick another port: `ipmg dashboard --port 9000`.
