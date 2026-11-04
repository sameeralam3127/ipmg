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
#
# What it verifies: IPMG's wheel and its hash-pinned dependency list are
# downloaded from a GitHub release and checked against that release's
# SHA256SUMS before anything is installed; uv's installer is pinned to one
# version and checked against a hash written in this script. A mismatch or a
# missing checksum stops the install. See docs/INSTALL.md, "Verify before you run".

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
REPO="sameeralam3127/ipmg"
MAX_RETRIES=3

# The uv this installer fetches when uv is missing, and the SHA256 of its
# uv-installer.sh (which in turn checks the uv archive against hashes written
# inside it). To move to a newer uv, change both together:
#   curl -fsSL https://github.com/astral-sh/uv/releases/download/<version>/uv-installer.sh | sha256sum
# CI fails when the hash no longer matches what astral publishes.
UV_VERSION="0.13.7"
UV_INSTALLER_SHA256="d263ee68314cf5bea36b08e6bd9e2c4563240d7adb73756cf33af5c199b92db4"  # pragma: allowlist secret

# TEST ONLY: a directory or URL holding SHA256SUMS and the release files, in
# place of the GitHub release. CI points it at a deliberately corrupted copy.
IPMG_RELEASE_BASE_URL="${IPMG_RELEASE_BASE_URL:-}"
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

Every download is checked against a published SHA256 before it is installed.
To read and check this script first, see "Verify before you run" in
https://github.com/sameeralam3127/ipmg/blob/main/docs/INSTALL.md
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

# -------------------------------------------------------------- verified downloads
WORK=""
cleanup() { [[ -z "$WORK" ]] || rm -rf "$WORK"; }
trap cleanup EXIT

# download SOURCE DEST. SOURCE is an https URL, or (for the test override) a
# local path or file:// URL.
download() {
  local source="$1" dest="$2"
  case "$source" in
    file://*) cp "${source#file://}" "$dest" ;;
    /*)       cp "$source" "$dest" ;;
    *)
      if have curl; then curl -fsSL -o "$dest" "$source"
      else wget -qO "$dest" "$source"
      fi
      ;;
  esac
}

sha256_of() {
  if have sha256sum; then sha256sum "$1" | cut -d' ' -f1
  elif have shasum;  then shasum -a 256 "$1" | cut -d' ' -f1
  else openssl dgst -sha256 "$1" | sed 's/^.*= *//'
  fi
}

# verify FILE LABEL EXPECTED: stops the install unless FILE hashes to EXPECTED.
verify_sha256() {
  local file="$1" label="$2" expected="$3" actual
  actual="$(sha256_of "$file")"
  if [[ "$actual" != "$expected" ]]; then
    error "Checksum mismatch for ${label}; nothing was installed.
  expected: ${expected}
  actual:   ${actual}
The download is corrupt or has been tampered with. Try again, and if it keeps
failing, report it at https://github.com/${REPO}/issues"
  fi
}

# The hash SHA256SUMS lists for NAME; empty when it has no such entry.
checksum_for() {
  local want="$1" hash name
  while read -r hash name; do
    name="${name#\*}"
    if [[ "$name" == "$want" ]]; then printf '%s' "$hash"; return 0; fi
  done < "${WORK}/SHA256SUMS"
  return 0
}

# fetch_checked NAME: downloads NAME from the release and verifies it against
# SHA256SUMS. A file the checksums do not list is refused, not skipped.
fetch_checked() {
  local name="$1" expected
  expected="$(checksum_for "$name")"
  [[ -n "$expected" ]] || error "SHA256SUMS in ${RELEASE_BASE} has no entry for ${name}; nothing was installed.
Refusing to install a file that has no published checksum."
  retry download "${RELEASE_BASE}/${name}" "${WORK}/${name}" \
    || error "Could not download ${RELEASE_BASE}/${name}"
  verify_sha256 "${WORK}/${name}" "$name" "$expected"
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

IPMG_VERSION="${IPMG_VERSION#v}"

# -------------------------------------------------------------- platform
OS="$(uname -s)"
ARCH="$(uname -m)"

case "$OS" in
  Linux|Darwin) ;;
  MINGW*|MSYS*|CYGWIN*)
    error "This installer is for Linux and macOS.
On Windows, run this in PowerShell instead:
  irm https://raw.githubusercontent.com/sameeralam3127/ipmg/main/install.ps1 | iex"
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

if ! have sha256sum && ! have shasum && ! have openssl; then
  error "Cannot verify downloads: none of sha256sum, shasum, or openssl is installed.
Install coreutils (or openssl), then re-run this installer."
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

# -------------------------------------------------------------- release files
# Fetched and checked before anything is installed, uv included, so a bad
# download leaves nothing behind. SHA256SUMS comes from the release (over
# TLS), and every other file must match the hash it lists.
WORK="$(mktemp -d)"

if [[ -n "$IPMG_VERSION" ]]; then
  RELEASE_BASE="${IPMG_RELEASE_BASE_URL:-https://github.com/${REPO}/releases/download/v${IPMG_VERSION}}"
else
  RELEASE_BASE="${IPMG_RELEASE_BASE_URL:-https://github.com/${REPO}/releases/latest/download}"
fi

log "Fetching the checksums for IPMG ${IPMG_VERSION:-(latest release)}..."
retry download "${RELEASE_BASE}/SHA256SUMS" "${WORK}/SHA256SUMS" \
  || error "Could not download ${RELEASE_BASE}/SHA256SUMS
Releases before 4.2.1 have no checksums, so this installer will not install them.
For those, install by hand: uv tool install '${PACKAGE}[web]==${IPMG_VERSION:-X.Y.Z}'"

# The wheel is the one file named ipmg-<version>-py3-none-any.whl.
WHEEL_NAME=""
WHEEL_COUNT=0
while read -r _hash _name; do
  _name="${_name#\*}"
  case "$_name" in
    "${PACKAGE}"-*-py3-none-any.whl) WHEEL_NAME="$_name"; WHEEL_COUNT=$((WHEEL_COUNT + 1)) ;;
  esac
done < "${WORK}/SHA256SUMS"
[[ "$WHEEL_COUNT" -eq 1 ]] \
  || error "Expected one ${PACKAGE} wheel in SHA256SUMS, found ${WHEEL_COUNT}; nothing was installed."

if [[ -n "$IPMG_VERSION" && "$WHEEL_NAME" != "${PACKAGE}-${IPMG_VERSION}-py3-none-any.whl" ]]; then
  error "SHA256SUMS lists ${WHEEL_NAME}, not IPMG ${IPMG_VERSION}; nothing was installed.
--version takes a release number such as 4.2.1."
fi

if [[ -z "$IPMG_VERSION" ]]; then
  # "Latest" was only used to find the version. Everything else comes from
  # that release's own tag, so a release cut in between cannot mix files.
  IPMG_VERSION="${WHEEL_NAME#"${PACKAGE}"-}"
  IPMG_VERSION="${IPMG_VERSION%%-*}"
  if [[ -z "$IPMG_RELEASE_BASE_URL" ]]; then
    RELEASE_BASE="https://github.com/${REPO}/releases/download/v${IPMG_VERSION}"
  fi
fi

REQUIREMENTS_NAME="requirements-web.txt"
fetch_checked "$WHEEL_NAME"
fetch_checked "$REQUIREMENTS_NAME"
log "Verified ${WHEEL_NAME} and ${REQUIREMENTS_NAME} against SHA256SUMS."

# -------------------------------------------------------------- uv
if have uv; then
  log "uv is already installed."
else
  log "Installing uv ${UV_VERSION} (it brings its own Python, so no system Python is needed)..."
  UV_INSTALLER_URL="https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-installer.sh"
  retry download "$UV_INSTALLER_URL" "${WORK}/uv-installer.sh" \
    || error "Could not download ${UV_INSTALLER_URL}
Check that this machine can reach https://github.com, or install uv by hand:
  https://docs.astral.sh/uv/getting-started/installation/"
  verify_sha256 "${WORK}/uv-installer.sh" "uv-installer.sh (uv ${UV_VERSION})" "$UV_INSTALLER_SHA256"

  # uv's installer then checks the uv archive against hashes written inside it.
  retry sh "${WORK}/uv-installer.sh" \
    || error "The uv installer failed.
Install uv by hand, then re-run this installer:
  https://docs.astral.sh/uv/getting-started/installation/"

  if [[ -f "${BIN_DIR}/env" ]]; then
    # shellcheck disable=SC1090,SC1091
    source "${BIN_DIR}/env"
  fi
  have uv || error "uv installed but is not on PATH. Open a new terminal and re-run this installer."
  log "uv installed."
fi

# -------------------------------------------------------------- ipmg
# The web extra too: someone running the one-liner expects `ipmg web` to work.
TARGET="${PACKAGE}[web] @ file://${WORK}/${WHEEL_NAME}"
REQUIREMENTS="${WORK}/${REQUIREMENTS_NAME}"

# IPMG 4 needs Python 3.10 or newer. Asked for explicitly, uv uses a system
# Python that new enough or downloads one; left to itself on RHEL 9 or
# Ubuntu 20.04 it would pick the system's 3.9 or 3.8 and quietly resolve an
# older IPMG release that still supports it.
PYTHON_REQUEST=">=3.10"

# uv tool install does not check hashes (a wrong one in a constraints file is
# ignored), so it only places the verified wheel and the pinned versions;
# the dependencies are then reinstalled with --require-hashes below.
# --no-build: a source distribution would run code no hash has vouched for.
log "Installing ${PACKAGE} ${IPMG_VERSION} from the verified wheel..."
if ! retry uv tool install --python "$PYTHON_REQUEST" --no-build --constraints "$REQUIREMENTS" --upgrade "$TARGET"; then
  warn "Upgrade failed; retrying with a clean reinstall (this recovers from a previous
install of '${PACKAGE}' from a different source, e.g. an older Git-based install)."
  if ! retry uv tool install --python "$PYTHON_REQUEST" --no-build --constraints "$REQUIREMENTS" --force "$TARGET"; then
    error "Could not install '${PACKAGE}' ${IPMG_VERSION} from ${WHEEL_NAME}.
Try it by hand to see the full error:
  uv tool install --python '${PYTHON_REQUEST}' --no-build --force '${TARGET}'"
  fi
fi

log "Checking every dependency against its pinned hash..."
TOOL_PYTHON="$(uv tool dir)/${PACKAGE}/bin/python"
if ! uv pip install --python "$TOOL_PYTHON" --reinstall --require-hashes --no-build --requirement "$REQUIREMENTS"; then
  uv tool uninstall "$PACKAGE" >/dev/null 2>&1 || true
  error "A dependency did not match its pinned hash in ${REQUIREMENTS_NAME}; IPMG was removed again.
See the uv error above for the package. Nothing unverified was left installed."
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
