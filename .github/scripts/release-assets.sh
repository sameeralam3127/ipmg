#!/usr/bin/env bash
#
# Collects everything a GitHub release carries into one directory and writes
# the SHA256SUMS that covers it: the wheel and sdist, both installers, and a
# hash-pinned list of the web install's dependencies.
#
#   .github/scripts/release-assets.sh DIST_DIR OUT_DIR
#
# DIST_DIR holds the output of `python -m build`. The release job runs this,
# and the installer workflows run it to build the release they test against,
# so the checksum format the installers read is the one that ships.
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "usage: $0 DIST_DIR OUT_DIR" >&2
  exit 2
fi
dist="$1"
out="$2"
root="$(cd "$(dirname "$0")/../.." && pwd)"

wheels=("$dist"/*.whl)
sdists=("$dist"/*.tar.gz)
if [ "${#wheels[@]}" -ne 1 ] || [ ! -f "${wheels[0]}" ] || [ "${#sdists[@]}" -ne 1 ] || [ ! -f "${sdists[0]}" ]; then
  echo "::error::$dist must hold exactly one wheel and one sdist" >&2
  exit 1
fi

rm -rf "$out"
mkdir -p "$out"
cp "${wheels[0]}" "${sdists[0]}" "$out/"
cp "$root/install.sh" "$root/install.ps1" "$out/"

# Every dependency of `ipmg[web]` at the version and hash it had when this
# release was cut. --universal covers every platform and Python in one file.
(cd "$root" && uv pip compile pyproject.toml --extra web \
  --generate-hashes --universal --python-version 3.10 --quiet --no-header \
  --output-file "$out/requirements-web.txt")

sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1
  else shasum -a 256 "$1" | cut -d' ' -f1
  fi
}

(
  cd "$out"
  : > SHA256SUMS
  # The glob sorts by the C locale's byte order, the same on every runner.
  export LC_ALL=C
  for file in *; do
    [ "$file" = SHA256SUMS ] && continue
    # Two spaces, the format `sha256sum -c` and `shasum -a 256 -c` read.
    printf '%s  %s\n' "$(sha256_of "$file")" "$file" >> SHA256SUMS
  done
  cat SHA256SUMS
)
