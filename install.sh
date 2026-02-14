#!/usr/bin/env bash
set -Eeuo pipefail

# -------------------------------
# Configuration
# -------------------------------
REPO_URL="git+https://github.com/sameeralam3127/ipmg.git"
INSTALL_DIR="${HOME}/.local/bin"

# -------------------------------
# Helpers
# -------------------------------
log() {
  printf "\n\033[1;34m[IPMG]\033[0m %s\n" "$1"
}

error() {
  printf "\n\033[1;31m[ERROR]\033[0m %s\n" "$1" >&2
  exit 1
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

log "Detected OS: ${OS}"
log "Detected Architecture: ${ARCH}"

case "$OS" in
  Linux|Darwin) ;;
  *)
    error "Unsupported OS: ${OS}"
    ;;
esac

# -------------------------------
# Install uv if missing
# -------------------------------
if ! command -v uv >/dev/null 2>&1; then
  log "uv not found. Installing uv..."

  curl -LsSf https://astral.sh/uv/install.sh | sh

  # Ensure uv is usable in current session
  export PATH="${INSTALL_DIR}:$PATH"

  if [[ -f "${INSTALL_DIR}/env" ]]; then
    # shellcheck disable=SC1090
    source "${INSTALL_DIR}/env"
  fi

  if ! command -v uv >/dev/null 2>&1; then
    error "uv installation failed. Restart your terminal and try again."
  fi

  log "uv installed successfully."
else
  log "uv already installed."
fi

# -------------------------------
# Install / Upgrade IPMG
# -------------------------------
log "Installing or upgrading IPMG..."

uv tool install --upgrade "${REPO_URL}"

# -------------------------------
# Verify Installation
# -------------------------------
if ! command -v ipmg >/dev/null 2>&1; then
  error "Installation completed but 'ipmg' is not in PATH.
Try restarting your terminal."
fi

VERSION="$(ipmg --version 2>/dev/null || echo "unknown")"

log "Installation successful!"
echo
echo "IPMG version: ${VERSION}"
echo
echo "Run:"
echo "  ipmg --help"
echo
