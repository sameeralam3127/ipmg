#!/usr/bin/env bash
# Smoke-test an IPMG image: docker-smoke.sh IMAGE
# Checks what #44 promises: it runs as non-root, ping works, a scan writes its
# report and history to /data, and IPMG Web answers with its token.
set -euo pipefail

image="${1:?usage: docker-smoke.sh IMAGE}"
# A fresh throwaway token per run (IPMG_WEB_TOKEN needs 16+ characters).
token="smoke-$RANDOM$RANDOM$RANDOM$RANDOM$RANDOM"
volume="ipmg-smoke-$$"
web="ipmg-smoke-web-$$"

cleanup() {
  docker rm -f "$web" >/dev/null 2>&1 || true
  docker volume rm -f "$volume" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "== version"
docker run --rm "$image" --version

echo "== runs as a non-root user"
uid=$(docker run --rm --entrypoint id "$image" -u)
[ "$uid" != "0" ] || { echo "image runs as root"; exit 1; }
echo "uid $uid"

echo "== a scan answers from inside the container and keeps its results"
docker run --rm -v "$volume:/data" "$image" \
  --input 127.0.0.1 --formats csv --output smoke --fail-on-down
docker run --rm -v "$volume:/data" --entrypoint sh "$image" -c \
  'ls smoke_*.csv && test -s .ipmg/dashboard.db && grep -q Active smoke_*.csv'

echo "== ping needs no capability, so it survives --cap-drop ALL (Kubernetes restricted)"
docker run --rm --cap-drop ALL "$image" --input 127.0.0.1 --no-history --formats csv --fail-on-down \
  >/dev/null

echo "== IPMG Web answers with its token, and refuses without it"
docker run -d --name "$web" -e IPMG_WEB_TOKEN="$token" -p 127.0.0.1:18080:8080 \
  -v "$volume:/data" "$image" web --host 0.0.0.0 --no-browser >/dev/null
for _ in $(seq 1 30); do
  curl -fsS -o /dev/null http://127.0.0.1:18080/ 2>/dev/null && break
  sleep 1
done
anonymous=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18080/api/v1/stats)
[ "$anonymous" = "401" ] || { echo "expected 401 without a token, got $anonymous"; exit 1; }
curl -fsS -H "Authorization: Bearer $token" http://127.0.0.1:18080/api/v1/stats | grep -q scan_count \
  || { echo "stats did not answer"; docker logs "$web"; exit 1; }

echo "smoke test passed"
