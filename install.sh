#!/usr/bin/env bash
set -Eeuo pipefail

# -------------------------------
# Configuration
# -------------------------------
PACKAGE="ipmg"
INSTALL_DIR="${HOME}/.local/bin"
MAX_RETRIES=3

# -------------------------------
# Helpers
# -------------------------------
log() {
  printf "\n\033[1;34m[IPMG]\033[0m %s\n" "$1"
}

warn() {
  printf "\n\033[1;33m[WARN]\033[0m %s\n" "$1" >&2
}

error() {
  printf "\n\033[1;31m[ERROR]\033[0m %s\n" "$1" >&2
  exit 1
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

# -------------------------------
# Safety Checks
# -------------------------------
if [[ "${EUID}" -eq 0 ]]; then
  error "Do NOT run this installer as root.
Run it as a normal user:
  curl -sSL https://raw.githubusercontent.com/sameeralam3127/ipmg/main/install.sh | bash"
fi

if ! command -v curl >/dev/null 2>&1; then
  error "curl is required but not installed."
fi

# -------------------------------
# Detect OS
# -------------------------------
OS="$(uname -s)"
ARCH="$(uname -m)"

log "Detected OS: ${OS} (${ARCH})"

case "$OS" in
  Linux|Darwin) ;;
  MINGW*|MSYS*|CYGWIN*)
    error "Unsupported OS: ${OS}.
On Windows, use 'pip install ${PACKAGE}' or run this installer inside WSL instead."
    ;;
  *)
    error "Unsupported OS: ${OS}"
    ;;
esac

# -------------------------------
# Install uv if missing
# -------------------------------
if ! command -v uv >/dev/null 2>&1; then
  log "uv not found. Installing uv..."

  if ! retry bash -c 'curl -LsSf https://astral.sh/uv/install.sh | sh'; then
    error "Failed to download or run the uv installer after ${MAX_RETRIES} attempts.
Check your network connection, or install uv manually: https://docs.astral.sh/uv/"
  fi

  log "uv installed successfully."
else
  log "uv already installed."
fi

# Make the freshly installed (or pre-existing) uv, and any tool it installs,
# visible in this session regardless of which branch above ran.
export PATH="${INSTALL_DIR}:${PATH}"
if [[ -f "${INSTALL_DIR}/env" ]]; then
  # shellcheck disable=SC1090,SC1091
  source "${INSTALL_DIR}/env"
fi

if ! command -v uv >/dev/null 2>&1; then
  error "uv installation finished but 'uv' is still not on PATH.
Open a new terminal and re-run this installer."
fi

# -------------------------------
# Install / Upgrade IPMG
# -------------------------------
# Always resolved against PyPI, so this reliably lands on the latest
# published release rather than risking a stale cached Git checkout.
log "Installing or upgrading ${PACKAGE} from PyPI..."

if ! retry uv tool install --upgrade "${PACKAGE}"; then
  warn "Upgrade failed; retrying with a clean reinstall (this recovers from a previous
install of '${PACKAGE}' from a different source, e.g. an older Git-based install)."
  if ! retry uv tool install --force "${PACKAGE}"; then
    error "Failed to install '${PACKAGE}' via uv after ${MAX_RETRIES} attempts.
Try manually: uv tool install --force ${PACKAGE}"
  fi
fi

# -------------------------------
# Verify Installation
# -------------------------------
if ! command -v ipmg >/dev/null 2>&1; then
  error "Installation completed but 'ipmg' is not in PATH ('${INSTALL_DIR}').
Add it to your shell profile, then restart your terminal:
  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc"
fi

VERSION="$(ipmg --version 2>/dev/null || echo "unknown")"

log "Installation successful!"
echo
echo "IPMG version: ${VERSION}"
echo
echo "Run:"
echo "  ipmg --help"
echo
