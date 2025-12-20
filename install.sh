#!/usr/bin/env bash
set -e

echo "Installing IPMG (IP Management & Ping Monitoring Tool)..."

# Check if uv exists, install if missing
if ! command -v uv >/dev/null 2>&1; then
  echo "uv not found. Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # Reload shell profile if uv alters PATH
  if [ -n "$ZSH_VERSION" ]; then
    source ~/.zshrc
  elif [ -n "$BASH_VERSION" ]; then
    source ~/.bashrc
  fi
fi

echo "Installing ipmg from GitHub..."
uv tool install git+https://github.com/sameeralam3127/ipmg.git

echo "✅ Installation complete!"
echo "You can now run: ipmg --help"
