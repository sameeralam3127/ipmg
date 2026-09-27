# IPMG Web API

IPMG Web is built on an HTTP API under `/api/v1`. The dashboard uses it, and
you can use it too: to start scans from a script, pull results into another
tool, or react to changes between scans.

- [Before you start](#before-you-start)
- [Authentication](#authentication)
- [Versioning and stability](#versioning-and-stability)
- [Errors](#errors)
- [Endpoints](#endpoints)
- [Examples](#examples)
- [Live events (WebSocket)](#live-events-websocket)
- [Interactive docs and the schema](#interactive-docs-and-the-schema)

## Before you start

Start IPMG Web and set the token it uses, so your scripts know it:

```bash
export IPMG_WEB_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
ipmg web --no-browser
```

The examples below assume that shell, plus:

```bash
API=http://127.0.0.1:8080/api/v1
AUTH="Authorization: Bearer $IPMG_WEB_TOKEN"
```

Without `IPMG_WEB_TOKEN`, IPMG Web makes a new token on every start. It is
the part after `#token=` in the link it prints.

## Authentication

Every request to `/api/v1` needs the access token in an `Authorization`
header:

```
Authorization: Bearer <token>
```

A missing or wrong token gets `401 Unauthorized`. The token is never
accepted in the URL, because query strings end up in logs and browser
history.

The API binds to `127.0.0.1` by default. The token keeps other users on
the machine and web pages you visit from driving it, but it travels over
plain HTTP. To reach the API from another machine, use an SSH tunnel or a
reverse proxy with TLS rather than exposing the port directly (see
[Security](../README.md#security)).

The token is a single shared secret for the whole API. There are no
per-user accounts or permissions yet.

## Versioning and stability

- **`/api/v1` only grows.** New endpoints, new optional request fields, and
  new response fields can be added at any time. Clients should ignore
  response fields they don't know.
- **Breaking changes go to a new version.** Removing or renaming a field,
  changing a type, or tightening validation happens under `/api/v2`, with
  `/api/v1` kept alongside it for a deprecation period.
- **Deprecations are announced** in the
  [changelog](../.github/CHANGELOG.md) before anything is removed.

Every pull request is checked against a committed snapshot of the API contract
(`tests/snapshots/api_v1_contract.json`), so a change to `/api/v1` can't
ship by accident.

## Errors

Every error response has the same JSON body:

```json
{ "detail": "Scan not found" }
```

`detail` is always a human-readable string. Validation errors (422) also
list each problem in `errors`:

```json
{
  "detail": "Invalid request: body.threads: Input should be a valid integer, unable to parse string as an integer",
  "errors": [
    { "loc": ["body", "threads"], "msg": "Input should be a valid integer, unable to parse string as an integer", "type": "int_parsing" }
  ]
}
```

| Status | Meaning |
| --- | --- |
| `400` | The request is well-formed but can't be used, e.g. no valid targets or an unsupported report format |
| `401` | Missing or invalid access token |
| `404` | No scan with that ID, or no earlier scan to compare with |
| `409` | Cancelling a scan that isn't running |
| `413` | Upload larger than 5 MB |
| `422` | A field has the wrong type, e.g. `"threads": "many"` |

## Endpoints

| Method | Path | Returns |
| --- | --- | --- |
| `GET` | `/stats` | Dashboard overview: counts, latest scan, running scans, trend |
| `GET` | `/assets` | Every host ever scanned, with its latest status |
| `GET` | `/scans?limit=50` | Recent scans, newest first (`limit` 1-500) |
| `POST` | `/scans` | Start a scan; returns `201` with `{"id", "total"}` |
| `GET` | `/scans/{id}` | One scan, with status counts and average latency |
| `GET` | `/scans/{id}/results?status=&search=` | Per-host results, optionally filtered by status (`Active`, `Inactive`, `Timeout`, `Error`) or IP/hostname substring |
| `POST` | `/scans/{id}/cancel` | Stop a running scan |
| `DELETE` | `/scans/{id}` | Delete a scan and its results; returns `204` |
| `GET` | `/scans/{id}/report?fmt=csv` | Download results as `xlsx`, `csv`, `json`, or `md` |
| `GET` | `/scans/{id}/diff?baseline=` | Changes since `baseline` (default: the previous scan) |
| `GET` | `/scans/{id}/diff/report?fmt=md` | Download the changes as `md`, `json`, or `csv` |
| `POST` | `/upload` | Parse targets from an uploaded file (multipart field `file`) |
| WebSocket | `/ws` | Live scan events |

The exact fields of every request and response are in the
[schema](#interactive-docs-and-the-schema).

### Starting a scan

`POST /scans` takes a JSON body. Give either `targets` (free text: IPs, CIDR
blocks, ranges, and hostnames separated by newlines, commas, or spaces) or
`ips` (a list). Everything else is optional:

| Field | Default | Notes |
| --- | --- | --- |
| `targets` | — | e.g. `"192.168.1.0/24, 10.0.0.5"` |
| `ips` | — | e.g. `["10.0.0.1", "10.0.0.2"]`; used instead of `targets` if both are set |
| `source` | `"manual"` | A label stored with the scan |
| `timeout` | `2` | Seconds per ping, clamped to 1-60 |
| `count` | `1` | Pings per host, clamped to 1-10 |
| `threads` | `50` | Concurrent workers, clamped to 1-500 |
| `resolve` | `false` | Reverse-resolve hostnames |
| `dns_cache_ttl` | `300` | Seconds, clamped to 0-86400 |

A scan's `status` is `running`, then `complete`, `cancelled`, or `failed`.

## Examples

### 1. Start a scan

```bash
curl -s -X POST "$API/scans" -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"targets": "192.168.1.0/28", "resolve": true, "source": "nightly"}'
```

```json
{ "id": 42, "total": 16 }
```

### 2. Wait for it to finish

```bash
while [ "$(curl -s "$API/scans/42" -H "$AUTH" | jq -r .status)" = running ]; do
  sleep 2
done
curl -s "$API/scans/42" -H "$AUTH" | jq '{status, completed, total, status_counts, avg_latency}'
```

```json
{ "status": "complete", "completed": 16, "total": 16, "status_counts": { "Active": 12, "Timeout": 4 }, "avg_latency": 3.41 }
```

For progress as it happens instead of polling, use the
[WebSocket](#live-events-websocket).

### 3. Fetch the results

```bash
# every host
curl -s "$API/scans/42/results" -H "$AUTH"

# only hosts that replied, as "ip hostname latency"
curl -s "$API/scans/42/results?status=Active" -H "$AUTH" \
  | jq -r '.[] | "\(.ip) \(.hostname) \(.latency)"'
```

Each result looks like:

```json
{ "ip": "192.168.1.1", "status": "Active", "latency": 0.84, "hostname": "router.lan", "open_ports": "", "checked_at": "2026-09-27 14:03:11" }
```

### 4. Download a report

```bash
curl -s -OJ "$API/scans/42/report?fmt=xlsx" -H "$AUTH"
# saves ipmg_scan_42_<timestamp>.xlsx
```

### 5. Compare two scans

```bash
# what changed since the previous scan
curl -s "$API/scans/42/diff" -H "$AUTH" | jq '.summary'

# against a specific scan, reporting latency shifts of 20 ms and 50% or more
curl -s "$API/scans/42/diff?baseline=37&latency_threshold=20&latency_pct=50" -H "$AUTH" \
  | jq -r '.changes[] | "\(.severity)\t\(.ip)\t\(.description)"'

# or as a Markdown report
curl -s -OJ "$API/scans/42/diff/report?fmt=md" -H "$AUTH"
```

### 6. Scan the targets in a file

```bash
TARGETS=$(curl -s -X POST "$API/upload" -H "$AUTH" -F "file=@hosts.xlsx" | jq -c .targets)
curl -s -X POST "$API/scans" -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"ips\": $TARGETS, \"source\": \"hosts.xlsx\"}"
```

### 7. Cancel or delete a scan

```bash
curl -s -X POST "$API/scans/42/cancel" -H "$AUTH"   # {"id": 42, "cancelling": true}
curl -s -X DELETE "$API/scans/42" -H "$AUTH" -o /dev/null -w '%{http_code}\n'   # 204
```

### From Python

With [requests](https://pypi.org/project/requests/) installed:

```python
import os
import time

import requests

api = "http://127.0.0.1:8080/api/v1"
session = requests.Session()
session.headers["Authorization"] = f"Bearer {os.environ['IPMG_WEB_TOKEN']}"

scan = session.post(f"{api}/scans", json={"targets": "10.0.0.0/29"}).json()
while session.get(f"{api}/scans/{scan['id']}").json()["status"] == "running":
    time.sleep(1)

for host in session.get(f"{api}/scans/{scan['id']}/results").json():
    print(host["ip"], host["status"], host["latency"])
```

## Live events (WebSocket)

Connect to `ws://127.0.0.1:8080/api/v1/ws` to receive every scan's progress
as JSON messages. Scripts send the token in an `Authorization: Bearer`
header. Browsers can't set headers on a WebSocket, so they offer the
subprotocols `ipmg` and `ipmg.token.<token>` instead.

```bash
websocat -H "Authorization: Bearer $IPMG_WEB_TOKEN" ws://127.0.0.1:8080/api/v1/ws
```

Each message has a `type`:

```json
{ "type": "scan_started", "scan_id": 42, "total": 16 }
{ "type": "result", "scan_id": 42, "completed": 1, "total": 16,
  "result": { "ip": "192.168.1.1", "status": "Active", "latency": 0.84, "hostname": "router.lan", "open_ports": [] } }
{ "type": "scan_finished", "scan_id": 42, "status": "complete", "duration_s": 4.127 }
```

Events are for every scan, not just the ones you started; filter on
`scan_id`. The server never expects messages from the client.

A client that falls more than 1,000 events behind is disconnected with
close code `1013`. Reconnect and reload the scan from `GET /scans/{id}`.
A connection with a missing or wrong token, or from another website's
page, is closed with code `1008`.

## Interactive docs and the schema

While IPMG Web is running:

- **<http://127.0.0.1:8080/docs>** — interactive docs. Click
  **Authorize**, paste the token, and try any endpoint from the browser.
- **<http://127.0.0.1:8080/openapi.json>** — the OpenAPI 3.1 schema, for
  generating a client. WebSocket messages are described by the
  `WebSocketEvent` schema under `components.schemas`.

Neither needs the token; they describe the API and contain no scan data.
