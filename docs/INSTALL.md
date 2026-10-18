# Installing IPMG

**Contents**

[Requirements](#requirements-and-platform-support) ·
[Python 3.10 or newer](#python-310-or-newer) ·
[One-line installers](#one-line-installers) ·
[Docker](#running-in-docker) ·
[pip](#installing-with-pip) ·
[What gets installed](#what-gets-installed) ·
[Tab completion](#tab-completion) ·
[ping](#the-one-thing-ipmg-needs-from-your-system) ·
[Verified environments](#verified-environments) ·
[Other ways](#other-ways-to-install) ·
[Upgrading from 3.x](#upgrading-from-3x)

---

## Requirements and platform support

IPMG does not craft packets. It runs your operating system's `ping` command
once per host, as a direct process call with no shell, and reads its output.
That means:

- **Python 3.10 or newer**, unless you use the one-line installers, which
  bring their own.
- **The system `ping` command.** macOS and Windows include it; minimal Linux
  and container images may not ([how to install it](#the-one-thing-ipmg-needs-from-your-system)).
- **No root or administrator rights.** IPMG has exactly the privileges your
  `ping` has: if `ping 8.8.8.8` works for your user, a scan works too. Port
  checks (`--scan-ports`) are ordinary TCP connections.

| Platform | What IPMG runs | Status |
| --- | --- | --- |
| Linux (iputils or busybox `ping`) | `ping -c COUNT -W SECONDS` | Supported. CI runs the tests and a scan on Ubuntu; see [verified environments](#verified-environments) |
| macOS | `ping -c COUNT -W MILLISECONDS`; `ping6` for IPv6 | Supported. CI runs the tests and a scan on macOS |
| Windows | `ping -n COUNT -w MILLISECONDS` | Supported. CI runs the tests and a scan of `127.0.0.1` on `windows-latest`; not yet verified against a real LAN |
| FreeBSD | `ping -c COUNT -W MILLISECONDS`; `ping6` for IPv6 | Probed in a FreeBSD VM in CI when the ping code changes |
| OpenBSD | `ping -c COUNT -w SECONDS`; `ping6` for IPv6 | Probed in an OpenBSD VM in CI when the ping code changes |
| NetBSD | `ping -c COUNT -w DEADLINE`; `ping6 -x MILLISECONDS` for IPv6 | Probed in a NetBSD VM in CI when the ping code changes |

`--discover ipv6` reads the neighbour table with `ip -6 neigh` on Linux (the
`iproute2` package), `ndp -an` on macOS, and `netsh` on Windows.

---

## Python 3.10 or newer

IPMG 4 needs Python 3.10 or newer. The one-line installers, Homebrew, and the
Docker image bring their own, so this only matters if you install with `pip`
or `uv`/`pipx` yourself. Some long-term-support systems still default to an
older Python:

| System | Default `python3` | What to do |
| --- | --- | --- |
| RHEL, Rocky, Alma, CentOS Stream 9 | 3.9 | `sudo dnf install -y python3.12`, then use `python3.12 -m venv` |
| RHEL, Rocky 8 | 3.6 | `sudo dnf install -y python3.11`, then use `python3.11 -m venv` |
| openSUSE Leap 15, SLES 15 | 3.6 | `sudo zypper install -y python311`, then use `python3.11 -m venv` |
| Ubuntu 20.04 | 3.8 | use the one-line installer or uv |
| Debian 11 | 3.9 | use the one-line installer or uv |

With an older Python, `pip install ipmg` does not fail: it quietly installs
3.2.0, the last release that supports it. Check with `ipmg --version`. uv picks
or downloads a suitable Python by itself when asked:

```bash
uv tool install --python ">=3.10" "ipmg[web]"
```

---

## One-line installers

**Linux and macOS — one command, works on every distribution:**

```bash
curl -sSL https://raw.githubusercontent.com/sameeralam3127/ipmg/main/install.sh | bash
```

It installs [uv](https://docs.astral.sh/uv/) (which brings its own Python, so
your system Python does not matter), then installs IPMG as an isolated tool.
Nothing is installed system-wide unless you run it as root.

On a minimal server or container image, add `--with-deps` and it will install
the handful of system packages it needs (`curl`, `tar`, `gzip`, `ping`) for you:

```bash
curl -sSL https://raw.githubusercontent.com/sameeralam3127/ipmg/main/install.sh | bash -s -- --with-deps
```

**macOS and Linux with Homebrew:**

```bash
brew install sameeralam3127/tap/ipmg
```

The formula lives in
[sameeralam3127/homebrew-tap](https://github.com/sameeralam3127/homebrew-tap)
and is updated with every release. Upgrade with `brew upgrade ipmg`, remove
with `brew uninstall ipmg`.

**Windows — one command in PowerShell:**

```powershell
irm https://raw.githubusercontent.com/sameeralam3127/ipmg/main/install.ps1 | iex
```

It works in Windows PowerShell 5.1 and PowerShell 7 and needs no
administrator rights: it installs uv if it is missing, installs IPMG, adds it
to your user `PATH`, and checks that `ipmg --version` runs. To pin a release,
replace `X.Y.Z` with any version listed on
[PyPI](https://pypi.org/project/ipmg/#history):

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/sameeralam3127/ipmg/main/install.ps1))) -Version X.Y.Z
```

**Docker (amd64 and arm64):**

```bash
docker run --rm ghcr.io/sameeralam3127/ipmg --input 10.0.0.0/24
```

Then check it works, on any platform:

```bash
ipmg --version
```

## Running in Docker

The image carries `ping`, runs as an unprivileged user (uid 10001), and keeps
everything a scan writes (reports and the history database) in `/data`. Mount
a volume there to keep it between runs:

```bash
docker run --rm -v ipmg-data:/data ghcr.io/sameeralam3127/ipmg --input 10.0.0.0/24 --compare
```

Ping needs no added capability: it uses the unprivileged ICMP sockets that
Docker and containerd enable by default, so it also works with
`--cap-drop ALL` and under Kubernetes' restricted pod security profile. To
scan your LAN rather than the container's network, add `--network host`
(Linux).

For IPMG Web, use the [`compose.yaml`](https://github.com/sameeralam3127/ipmg/blob/main/compose.yaml)
in this repository. Inside a container IPMG Web must listen on `0.0.0.0` or
nothing outside the container could reach it, so the compose file starts it
with `web --host 0.0.0.0` and publishes the port on the host's `127.0.0.1`
only. Set a fixed `IPMG_WEB_TOKEN` in `.env`, then:

```bash
docker compose up -d                                      # http://127.0.0.1:8080/#token=<your token>
docker compose run --rm scan --input 10.0.0.0/24          # CLI scans land in the same history
```

Publishing the port more widely (`8080:8080`) exposes IPMG Web on your
network over plain HTTP; put a reverse proxy with TLS in front first. Images
are tagged with the release version (`X.Y.Z`), the minor line (`X.Y`), and
`latest`.

## Installing with pip

`pip install ipmg` works inside a virtual environment, and inside one only.
On Ubuntu 23.04+, Debian 12+, Fedora 38+, and recent openSUSE, installing into
the system Python is blocked by the distribution itself:

```
error: externally-managed-environment
× This environment is externally managed
```

That is [PEP 668](https://peps.python.org/pep-0668/), and it is not an IPMG
bug — the distro is protecting its own Python. Any of these get you around it:

```bash
# 1. uv — no system Python needed at all (what the installer above uses)
uv tool install ipmg

# 2. pipx — the standard way to install Python applications
pipx install ipmg

# 3. a virtual environment you manage yourself
python3 -m venv ~/.venvs/ipmg
~/.venvs/ipmg/bin/pip install ipmg
~/.venvs/ipmg/bin/ipmg --version
```

Please do not reach for `--break-system-packages`. It does what it says.

## What gets installed

`pip install ipmg` is the lean core: scanning, every report format
(Excel included), history, change detection, notifications, and exit codes.
It is about 9 MB and 7 packages. IPMG Web, the browser UI with its REST API
and Prometheus `/metrics`, is the optional `web` extra, because its server
stack is most of the weight:

```bash
pip install "ipmg[web]"             # or: uv tool install "ipmg[web]", pipx install "ipmg[web]"
```

The one-line installers, Homebrew, and the Docker image install it with the
`web` extra already. Run `ipmg web` without it and IPMG tells you the command
that adds it.

## Tab completion

`ipmg completion SHELL` prints a completion script for commands, flags, their
choices, and file names. It is generated from IPMG's own flag definitions, so
it never falls behind; run it again after an upgrade.

| Shell | Add this |
| --- | --- |
| bash | `eval "$(ipmg completion bash)"` in `~/.bashrc` (bash 3.2 and later; no bash-completion package needed) |
| zsh | `eval "$(ipmg completion zsh)"` in `~/.zshrc`, after `compinit`; or save it as `_ipmg` in a directory on your `$fpath` |
| fish | `ipmg completion fish > ~/.config/fish/completions/ipmg.fish` |
| PowerShell | `ipmg completion powershell \| Out-String \| Invoke-Expression` in your `$PROFILE` |

## The one thing IPMG needs from your system

IPMG probes hosts with your operating system's `ping` command, and minimal
Ubuntu, RHEL, SUSE, and container images ship without it. If a scan reports
`The system 'ping' command is not available`, install it:

| System | Command |
| --- | --- |
| Ubuntu, Debian | `sudo apt-get install -y iputils-ping` |
| RHEL, Rocky, Alma, Fedora | `sudo dnf install -y iputils` |
| openSUSE, SLES | `sudo zypper install -y iputils` |
| Arch | `sudo pacman -S iputils` |
| Alpine | `sudo apk add iputils` |
| macOS, Windows | already included |

You do **not** need root, administrator rights, or a raw-socket capability —
IPMG runs the same `ping` you would run by hand.

## Verified environments

The installer is tested in each of these whenever `install.sh` changes, and
weekly: a fresh install as root with `--with-deps`, then a scan
([workflow](https://github.com/sameeralam3127/ipmg/actions/workflows/install-sh.yml)).
macOS and Ubuntu are also tested as a normal user, as are a pinned
`--version` and an upgrade over an existing install.

| Environment | Notes |
| --- | --- |
| Ubuntu 22.04 / 24.04 | 24.04 blocks `pip install`; the installer is unaffected |
| Debian 12 | same PEP 668 situation as Ubuntu |
| RHEL 8 / RHEL 9 (UBI), Rocky 9 | RHEL 8's system Python is 3.6; uv supplies its own |
| Fedora 41 | |
| openSUSE Leap 15.6 | image has no Python at all; installer supplies everything |
| Alpine 3.20 | run the installer with `bash`, not `sh` |
| macOS | verified on Apple silicon |

Windows is not in that list because it cannot be tested in a container: it is
covered instead by the CI matrix, which runs the full test suite and a live
scan on `windows-latest` for every change.

Python 3.10 through 3.14 are supported, and CI runs the test suite against every
one of them.

---

## Other ways to install

**uv (isolated global install):**

```bash
uv tool install ipmg
```

**Pin a specific version** (any release listed on
[PyPI](https://pypi.org/project/ipmg/#history)):

```bash
curl -sSL https://raw.githubusercontent.com/sameeralam3127/ipmg/main/install.sh | bash -s -- --version X.Y.Z
```

**From source (development):**

```bash
git clone https://github.com/sameeralam3127/ipmg.git
cd ipmg
pip install -e ".[dev]"
```

**Upgrade or remove:**

```bash
uv tool upgrade ipmg
uv tool uninstall ipmg
```

---

## Upgrading from 3.x

IPMG 4 opens what 3.x wrote. Your scan history (`~/.ipmg/dashboard.db`) is
upgraded in place the first time IPMG 4 opens it, `ipmg.toml` files keep
working, and every 3.x command, flag, report format, exit code, and `/api/v1`
endpoint behaves as before. The one hard requirement is
[Python 3.10 or newer](#python-310-or-newer); the one-line installers and
uv take care of it.

```bash
# Re-running the installer upgrades in place (it asks uv for Python 3.10+):
curl -sSL https://raw.githubusercontent.com/sameeralam3127/ipmg/main/install.sh | bash

# Or by hand. --python matters: an upgrade otherwise keeps the Python the tool
# was installed with, and on 3.9 that means staying on IPMG 3.2.0.
uv tool install --force --python ">=3.10" "ipmg[web]"
pipx reinstall --python python3.12 ipmg
brew upgrade ipmg

ipmg --version                       # 4.x
ipmg history                         # your 3.x scans are still there
```
