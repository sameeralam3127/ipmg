#!/usr/bin/env bash
#
# IPMG installer for Linux and macOS.
#
# Installs uv (which brings its own Python, so no system Python is needed)
# and then installs IPMG as an isolated tool. Works the same on Ubuntu,
# Debian, RHEL/Rocky/Alma, Fedora, openSUSE, Arch, Alpine, and macOS.
#
#   curl -sSL https://raw.githubusercontent.com/sameeralam3127/ipmg/main/install.sh | bash
#
# Options (pass them after `| bash -s --`):
#   --with-deps        install missing system packages (curl, tar, gzip, ping) for you
#   --version X.Y.Z    install a specific IPMG release instead of the latest
#   --help             show this help
#
# Environment: IPMG_VERSION, IPMG_WITH_DEPS=1 do the same as the flags.

# busybox sh (Alpine) and dash (Debian's /bin/sh) cannot parse what follows,
# so hand the script to bash when it was started some other way.
if [ -z "${BASH_VERSION:-}" ]; then
  if command -v bash >/dev/null 2>&1 && [ -r "$0" ]; then
    exec bash "$0" "$@"
  fi
  echo "The IPMG installer needs bash. Install it first (e.g. 'apk add bash')," >&2
  echo "then run:  curl -sSL <this script's URL> | bash" >&2
  exit 1
fi

set -Eeuo pipefail

PACKAGE="ipmg"
MAX_RETRIES=3
IPMG_VERSION="${IPMG_VERSION:-}"
WITH_DEPS="${IPMG_WITH_DEPS:-0}"

# -------------------------------------------------------------- output
log()  { printf "\n\033[1;34m[IPMG]\033[0m %s\n" "$1"; }
warn() { printf "\n\033[1;33m[WARN]\033[0m %s\n" "$1" >&2; }
error() { printf "\n\033[1;31m[ERROR]\033[0m %s\n" "$1" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

usage() {
  cat <<'USAGE'
IPMG installer for Linux and macOS.

  curl -sSL https://raw.githubusercontent.com/sameeralam3127/ipmg/main/install.sh | bash

Options (pass them after `| bash -s --`):
  --with-deps        install missing system packages (curl, tar, gzip, ping) for you
  --version X.Y.Z    install a specific IPMG release instead of the latest
  --help             show this help

Environment: IPMG_VERSION, IPMG_WITH_DEPS=1 do the same as the flags.
USAGE
  exit 0
}

# Retries a command a few times with backoff, for the flaky-network case
# (this script is typically run once, unattended, over `curl | bash`).
retry() {
  local attempt=1
  until "$@"; do
    if (( attempt >= MAX_RETRIES )); then
      return 1
    fi
    warn "Command failed (attempt ${attempt}/${MAX_RETRIES}). Retrying in $((attempt * 2))s..."
    sleep $((attempt * 2))
    attempt=$((attempt + 1))
  done
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-deps|--with-ping) WITH_DEPS=1; shift ;;
    --version) IPMG_VERSION="${2:-}"; shift 2 ;;
    --version=*) IPMG_VERSION="${1#*=}"; shift ;;
    -h|--help) usage ;;
    *) error "Unknown option: $1  (try --help)" ;;
  esac
done

# -------------------------------------------------------------- platform
OS="$(uname -s)"
ARCH="$(uname -m)"

case "$OS" in
  Linux|Darwin) ;;
  MINGW*|MSYS*|CYGWIN*)
    error "This installer is for Linux and macOS.
On Windows, run these two commands in PowerShell instead:
  powershell -ExecutionPolicy ByPass -c \"irm https://astral.sh/uv/install.ps1 | iex\"
  uv tool install ${PACKAGE}"
    ;;
  *) error "Unsupported operating system: ${OS}" ;;
esac

DISTRO="$OS"
if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  DISTRO="$(. /etc/os-release && printf '%s' "${PRETTY_NAME:-$NAME}")"
fi
log "Detected ${DISTRO} (${ARCH})"

# The command that installs system packages here, so every hint we print is
# one the user can actually paste. Empty when we do not recognise the distro.
PKG_TOOL=""
if have apt-get;  then PKG_TOOL="apt-get install -y"
elif have dnf;    then PKG_TOOL="dnf install -y"
elif have yum;    then PKG_TOOL="yum install -y"
elif have zypper; then PKG_TOOL="zypper install -y"
elif have pacman; then PKG_TOOL="pacman -S --noconfirm"
elif have apk;    then PKG_TOOL="apk add"
elif have brew;   then PKG_TOOL="brew install"
fi

# Name of the package that provides ping, which differs per distro.
ping_package() {
  if have apt-get;  then printf 'iputils-ping'
  elif have dnf || have yum || have zypper; then printf 'iputils'
  elif have pacman; then printf 'iputils'
  elif have apk;    then printf 'iputils'
  else printf 'iputils'
  fi
}

# Print the command that installs $* on this system, sudo-prefixed if needed.
install_command() {
  local packages="$*"
  if [[ -z "$PKG_TOOL" ]]; then
    printf 'your package manager: install %s' "$packages"
  elif [[ "${EUID}" -eq 0 ]] || have brew; then
    printf '%s %s' "$PKG_TOOL" "$packages"
  else
    printf 'sudo %s %s' "$PKG_TOOL" "$packages"
  fi
}

run_install_command() {
  local packages="$*"
  [[ -n "$PKG_TOOL" ]] || return 1
  if have apt-get && [[ "${EUID}" -eq 0 ]]; then
    apt-get update -qq || true
  elif have apt-get && have sudo; then
    sudo apt-get update -qq || true
  fi
  # shellcheck disable=SC2086
  if [[ "${EUID}" -eq 0 ]] || have brew; then
    $PKG_TOOL $packages
  elif have sudo; then
    sudo $PKG_TOOL $packages
  else
    return 1
  fi
}

# -------------------------------------------------------------- prerequisites
# uv's installer needs a downloader plus tar and gzip to unpack the release.
# A minimal openSUSE image has none of them, and the failure that produced
# ("check your network connection") sent people looking in the wrong place.
MISSING=""
if ! have curl && ! have wget; then MISSING="curl"; fi
if ! have tar; then MISSING="${MISSING:+$MISSING }tar"; fi
if ! have gzip; then MISSING="${MISSING:+$MISSING }gzip"; fi

if [[ -n "$MISSING" ]]; then
  if [[ "$WITH_DEPS" == "1" ]] && run_install_command "$MISSING"; then
    log "Installed missing prerequisite(s): ${MISSING}"
  else
    error "Missing required tool(s): ${MISSING}
Install them first:
  $(install_command "$MISSING")
then re-run this installer (or re-run it with --with-deps to have it do this for you)."
  fi
fi

# -------------------------------------------------------------- install target
if [[ "${EUID}" -eq 0 ]]; then
  # Root usually means a server or a container image build, where a
  # system-wide install is what the user actually wants — /root/.local/bin
  # is on nobody else's PATH.
  BIN_DIR="/usr/local/bin"
  warn "Running as root; installing system-wide into ${BIN_DIR}."
else
  BIN_DIR="${XDG_BIN_HOME:-${HOME}/.local/bin}"
fi

# Remember the inherited PATH: the export below would otherwise make the
# "is the bin directory on PATH?" check further down always answer yes.
INHERITED_PATH="$PATH"

export UV_INSTALL_DIR="$BIN_DIR"
export UV_TOOL_BIN_DIR="$BIN_DIR"
export PATH="${BIN_DIR}:${PATH}"

# -------------------------------------------------------------- uv
if have uv; then
  log "uv is already installed."
else
  log "Installing uv (it brings its own Python, so no system Python is needed)..."
  if have curl; then
    fetch_uv() { curl -LsSf https://astral.sh/uv/install.sh | sh; }
  else
    fetch_uv() { wget -qO- https://astral.sh/uv/install.sh | sh; }
  fi

  if ! retry fetch_uv; then
    error "Could not download and run the uv installer.
Check that this machine can reach https://astral.sh, or install uv by hand:
  https://docs.astral.sh/uv/getting-started/installation/"
  fi

  if [[ -f "${BIN_DIR}/env" ]]; then
    # shellcheck disable=SC1090,SC1091
    source "${BIN_DIR}/env"
  fi
  have uv || error "uv installed but is not on PATH. Open a new terminal and re-run this installer."
  log "uv installed."
fi

# -------------------------------------------------------------- ipmg
TARGET="$PACKAGE"
if [[ -n "$IPMG_VERSION" ]]; then
  TARGET="${PACKAGE}==${IPMG_VERSION}"
fi

log "Installing ${TARGET} from PyPI..."
if ! retry uv tool install --upgrade "$TARGET"; then
  warn "Upgrade failed; retrying with a clean reinstall (this recovers from a previous
install of '${PACKAGE}' from a different source, e.g. an older Git-based install)."
  if ! retry uv tool install --force "$TARGET"; then
    error "Could not install '${TARGET}'.
Try it by hand to see the full error:
  uv tool install --force ${TARGET}"
  fi
fi

# -------------------------------------------------------------- PATH
# uv writes its own shell hook, but a tool bin directory that is not on PATH
# is the single most common "installed fine, command not found" report.
add_to_profile() {
  local profile="$1"
  local line="export PATH=\"${BIN_DIR}:\$PATH\""
  [[ -f "$profile" ]] || return 0
  if grep -qsF "$BIN_DIR" "$profile"; then
    return 0
  fi
  printf '\n# Added by the IPMG installer\n%s\n' "$line" >> "$profile"
  log "Added ${BIN_DIR} to PATH in ${profile}"
}

case ":${INHERITED_PATH}:" in
  *":${BIN_DIR}:"*) ;;
  *)
    for profile in "${HOME}/.bashrc" "${HOME}/.zshrc" "${HOME}/.profile"; do
      add_to_profile "$profile"
    done
    ;;
esac

# -------------------------------------------------------------- ping
# IPMG shells out to the system ping, which minimal Ubuntu, RHEL, and SUSE
# images do not ship. Without this check the install "succeeds" and then
# every single scan fails.
if ! have ping; then
  PING_PKG="$(ping_package)"
  if [[ "$WITH_DEPS" == "1" ]]; then
    log "Installing the ping command (${PING_PKG})..."
    if ! run_install_command "$PING_PKG"; then
      warn "Could not install ${PING_PKG} automatically. Run:
  $(install_command "$PING_PKG")"
    fi
  else
    warn "The 'ping' command is not installed, and IPMG needs it to probe hosts.
Install it with:
  $(install_command "$PING_PKG")
or re-run this installer with --with-deps."
  fi
fi

# -------------------------------------------------------------- verify
IPMG_BIN="${BIN_DIR}/${PACKAGE}"
if [[ ! -x "$IPMG_BIN" ]] && have "$PACKAGE"; then
  IPMG_BIN="$(command -v "$PACKAGE")"
fi

if [[ ! -x "$IPMG_BIN" ]]; then
  error "Installation finished but '${PACKAGE}' was not found in ${BIN_DIR}.
Try: uv tool install --force ${PACKAGE}"
fi

VERSION="$("$IPMG_BIN" --version 2>/dev/null || echo "unknown")"

log "Installed: ${VERSION}"
echo
echo "Next steps:"
echo "  ipmg --help          # every option"
echo "  ipmg --discover      # scan the network this machine is on"
echo
case ":${INHERITED_PATH}:" in
  *":${BIN_DIR}:"*) ;;
  *) echo "Open a new terminal first, so ${BIN_DIR} is on your PATH."; echo ;;
esac
