#!/usr/bin/env bash
#
# The installers pin one uv version and carry the SHA256 of what they fetch
# for it. This checks that both installers pin the same version, and that the
# hashes written in them are the ones astral publishes for that release.
set -euo pipefail

cd "$(dirname "$0")/../.."

sh_version="$(sed -n 's/^UV_VERSION="\(.*\)"$/\1/p' install.sh)"
sh_installer_hash="$(sed -n 's/^UV_INSTALLER_SHA256="\([0-9a-f]*\)".*$/\1/p' install.sh)"
ps_version="$(sed -n "s/^\\\$UvVersion = '\\(.*\\)'\$/\\1/p" install.ps1)"

if [ -z "$sh_version" ] || [ -z "$sh_installer_hash" ] || [ -z "$ps_version" ]; then
  echo "::error::could not read the uv pin from install.sh and install.ps1" >&2
  exit 1
fi
if [ "$sh_version" != "$ps_version" ]; then
  echo "::error::install.sh pins uv $sh_version but install.ps1 pins $ps_version" >&2
  exit 1
fi

base="https://github.com/astral-sh/uv/releases/download/$sh_version"
failed=0

actual="$(curl -fsSL "$base/uv-installer.sh" | sha256sum | cut -d' ' -f1)"
if [ "$actual" != "$sh_installer_hash" ]; then
  echo "::error::install.sh has $sh_installer_hash for uv-installer.sh $sh_version, but it is $actual"
  failed=1
fi

published="$(curl -fsSL "$base/sha256.sum")"
while read -r target hash; do
  want="$(printf '%s\n' "$published" | sed -n "s/^\\([0-9a-f]*\\) \\*uv-$target\\.zip\$/\\1/p")"
  if [ "$want" != "$hash" ]; then
    echo "::error::install.ps1 has $hash for uv-$target.zip $sh_version, but astral publishes ${want:-nothing}"
    failed=1
  fi
done < <(sed -n "s/^    '\\([a-z0-9_-]*\\)' *= '\\([0-9a-f]\\{64\\}\\)'.*\$/\\1 \\2/p" install.ps1)

[ "$failed" -eq 0 ] && echo "uv $sh_version: the hashes in both installers match what astral publishes."
exit "$failed"
