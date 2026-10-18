# Troubleshooting

Something not working? Find the symptom below. If it is not listed, search
the [issues](https://github.com/sameeralam3127/ipmg/issues) or open a new one.
See also the [FAQ](FAQ.md).

**Contents**

[Installing](#installing) ·
[Scanning](#scanning) ·
[Input files](#input-files) ·
[IPMG Web](#ipmg-web)

---

## Installing

### `error: externally-managed-environment` when running `pip install ipmg`

Your distribution blocks installs into the system Python (Ubuntu 23.04+,
Debian 12+, Fedora 38+). Use the one-line installer, `uv tool install ipmg`, or
`pipx install ipmg` — see
[Installing with pip](INSTALL.md#installing-with-pip).

### `command not found: ipmg` right after installing

The install directory is not on your `PATH` yet. Open a new terminal first —
the installer adds it to your shell profile. Still missing? Run it directly
from `~/.local/bin/ipmg`, or `python -m ipmg` if you installed with pip.

### `IPMG Web needs the optional 'web' packages`

`pip install ipmg` installs the lean core, which scans and writes every report
but does not include IPMG Web's server. Add it with the tool that installed
IPMG: `uv tool install --force "ipmg[web]"`, `pipx install --force "ipmg[web]"`,
or `pip install "ipmg[web]"`.

### An Excel 97-2003 (`.xls`) file is rejected

IPMG reads `.xlsx` workbooks. Open the `.xls` file in Excel or LibreOffice and
save it as `.xlsx` or `.csv`.

### The installer fails on a minimal image

Bare container and cloud images often lack `curl`, `tar`, or `gzip`. The
installer names exactly what is missing and the command that installs it, or
you can let it do the work: add `--with-deps`. On Alpine, run it with `bash`
(`apk add bash`) — the script needs more than busybox `sh` provides.

### `The system 'ping' command is not available`

IPMG installed fine, but your image has no ping. Install it with the command
for your distribution — see
[The one thing IPMG needs](INSTALL.md#the-one-thing-ipmg-needs-from-your-system).

---

## Scanning

### Every host comes back `Timeout`

Something is dropping ICMP — a host firewall, a VPN, or a cloud security group.
Confirm by running `ping` by hand against one of the addresses: if that fails
too, it is the network and not IPMG.

Hosts that drop ping usually still serve traffic, so probe them with TCP
instead:

```bash
ipmg --input targets.txt --probe icmp,tcp                 # TCP only for hosts that did not answer the ping
ipmg --input targets.txt --probe tcp --ports 22,443,3389  # TCP only, on the ports your hosts serve
```

A host counts as up when any of `--ports` accepts the connection, or refuses
it: a refusal is a TCP reset, which only a live host sends. The `Probe`
column then says which method found each host.

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
look up. A lookup that takes longer than `--dns-timeout` (default 2 seconds)
also shows `Unresolvable`; raise it if your resolver is slow.

### `MAC Address` is empty with `--mac`

A host beyond a router never has one: only hosts on your own network segment
are in the neighbour table. For a host on the same segment, check that the
table lists it (`arp -an` on macOS and the BSDs, `ip neigh` on Linux,
`arp -a` on Windows). Inside Docker, the container has its own network unless
you run it with `--network host`.

On macOS 15 and later, a program needs **Local Network** permission to see
devices on your network. Without it the neighbour table reads back empty for
that program and everything it starts, even though `arp -an` works in your
terminal. Allow your terminal app (or the Python that runs IPMG) under
System Settings → Privacy & Security → Local Network.

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

## IPMG Web

### The IPMG Web port is already in use

Pick another port: `ipmg web --port 9000`.

### Another machine cannot open IPMG Web

By default IPMG Web listens on `127.0.0.1`, which only the machine it runs on
can reach. Start it with `--lan`:

```bash
ipmg web --lan
```

and open the link it prints next to "from other machines", which has this
machine's address and the access token. If the page still does not load, the
firewall is in the way: IPMG Web names it and prints the command that opens
the port, such as `sudo firewall-cmd --add-port=8080/tcp` on RHEL or
`sudo ufw allow 8080/tcp` on Ubuntu, or run `sudo ipmg web --open-firewall` to
open it only while IPMG Web runs. Check what it listens on with
`ss -ltnp | grep 8080`: `0.0.0.0:8080` means every interface. More in the
[IPMG Web guide](WEB.md#opening-it-from-other-machines).

### The page says the access token is missing or wrong

The token changes every time IPMG Web starts, so a link or bookmark from an
earlier run stops working. Use the link it printed this time, or pin a token
with `export IPMG_WEB_TOKEN=...` before starting it.

### `pip install ipmg` installed 3.2.0, not 4.x

IPMG 4 needs Python 3.10 or newer, and on an older Python pip quietly picks
the last release that supports it. RHEL 9 (3.9), RHEL 8 and SLES 15 (3.6), and
Ubuntu 20.04 (3.8) are the usual cases. Use the one-line installer, or
`uv tool install --python ">=3.10" "ipmg[web]"`, or a newer Python from your
distribution ([details](INSTALL.md#python-310-or-newer)).
