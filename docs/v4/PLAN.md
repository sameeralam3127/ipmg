# IPMG v4 development plan

> **IPMG v4 is under active development on the `v4` branch. Do not switch
> production systems to it.** Use the current stable 3.x release until
> v4.0.0 is published. **Target: v4.0.0 at the end of October 2026.**

IPMG v4 is an **architectural release, not a feature release**. Its identity
stays the same as 3.x: *fast network discovery, historical inventory, change
detection, and reporting.* v4 rebuilds the inside so that identity can grow
through independent, replaceable components instead of an ever-larger scanner
and ever more root-command flags.

**Contents**

[Pillars](#the-five-pillars) ·
[Where 3.x already stands](#where-3x-already-stands) ·
[Architecture](#architecture) ·
[Work areas](#work-areas) ·
[Out of scope](#out-of-scope) ·
[Compatibility contract](#compatibility-contract) ·
[Schedule](#schedule) ·
[Development policy](#development-policy) ·
[Release rule](#release-rule) ·
[Release mechanics](#release-mechanics) ·
[Review notes and risks](#review-notes-and-risks)

---

## The five pillars

1. **SOLID, modular architecture:** components that depend on protocols,
   not on each other's internals.
2. **Plugin architecture:** scanners, exporters, storage, notifiers, and
   discovery methods that can be added without editing the core.
3. **A streaming, bounded-concurrency pipeline:** results flow to storage,
   reports, the web UI, metrics, and notifications as they are produced.
4. **Strong typing as a release gate:** typed domain models, `mypy` in CI.
5. **Contract testing:** every implementation of an interface passes the
   same shared test suite.

---

## Where 3.x already stands

Several items in the original v4 wish list have already shipped. v4 builds
on them rather than redoing them:

| Area | Already in 3.1 | What v4 still adds |
| --- | --- | --- |
| IPv6 | Targets, CIDR/ranges, probing, neighbour discovery (3.0.0) | Domain model built on `ipaddress` objects instead of strings |
| Metrics | Prometheus `/metrics` in IPMG Web (3.1.0) | Scan-pipeline metrics (errors, DNS/port timings) |
| Notifications | Slack, Teams, webhook, email, severity filter | A `Notifier` protocol that makes them plugins |
| Configuration | `ipmg.toml` + `~/.config/ipmg/config.toml`, profiles, strict key validation | Typed config model; `ipmg config show/validate/path` |
| CLI | `ipmg web`, `history`, `diff` (`compare`) subcommands | `scan`, `discover`, `inventory`, `report`, `config`, `plugin` |
| REST API | Versioned `/api/v1` with a committed contract snapshot | Web UI talks only to application services |
| Streaming | `--stream`, `--jsonl`, incremental reports, `--resume` | Streaming as the core pipeline, not an output mode |
| Errors | `IPMGError` with 7 subclasses (`exceptions.py`) | Complete the hierarchy (`InputError`, `StorageError`, `PluginError`, …) |
| Security | Token auth, WebSocket origin check, 5 MB uploads, 65,536-host cap, parameterized SQL; bandit, pip-audit, detect-secrets in CI | Security headers, token lifetime, safe output paths, parser fuzzing |
| Inventory | Inventory view and `/api/v1/assets` | A real host model with tags, first/last seen, CLI access |

---

## Architecture

```text
                    ┌─────────────────────┐
                    │     CLI / Web UI    │
                    └──────────┬──────────┘
                    ┌──────────▼──────────┐
                    │ Application services│
                    └──────────┬──────────┘
             ┌─────────────────┼─────────────────┐
       ┌─────▼─────┐     ┌─────▼─────┐     ┌─────▼─────┐
       │ Discovery │     │  Scanning │     │ Comparison│
       └─────┬─────┘     └─────┬─────┘     └─────┬─────┘
             └─────────────────┼─────────────────┘
                    ┌──────────▼──────────┐
                    │    Domain models    │
                    └──────────┬──────────┘
                 ┌─────────────┼─────────────┐
            ┌────▼────┐   ┌────▼────┐   ┌────▼────┐
            │ Storage │   │ Reports │   │ Plugins │
            └─────────┘   └─────────┘   └─────────┘
```

**CLI, web, storage, exporters, and scanner implementations do not know about
each other's internals.** The CLI and web layers call application services;
services depend on protocols; implementations are wired in at the edge.

Target package layout:

```text
ipmg/
├── core/            domain models, protocols, comparison
├── scanners/        ping, TCP connect, composite
├── discovery/       local subnet, IPv6 neighbours
├── storage/         SQLite (default)
├── exporters/       csv, json, jsonl, md, xlsx
├── notifications/   console, webhook, slack, teams, email
├── plugins/         discovery and loading via entry points
├── services/        application services (scan, history, inventory)
├── cli/
└── web/
```

### SOLID, concretely

- **Single responsibility:** `NetworkDiscovery`, `HostScanner`,
  `DNSResolver`, `PortScanner`, `ScanComparator`, and `ReportGenerator` are
  separate components.
- **Open/closed:** a new report format is a new exporter. The scanner never
  changes for it.

  ```python
  class ReportExporter(Protocol):
      name: str

      def export(self, results: Iterable[ScanResult], destination: Path) -> None: ...
  ```

- **Liskov substitution:** `PingScanner`, `TCPConnectScanner`, and any future
  scanner honour the same `Scanner` contract, which the contract tests
  enforce.
- **Interface segregation:** small protocols (`Scanner`, `Resolver`,
  `Exporter`, `ScanStorage`, `Notifier`, `Comparator`) instead of one class
  with `scan/resolve/save/export/compare/notify`.
- **Dependency inversion:** services receive their collaborators.

  ```python
  class ScanService:
      def __init__(self, scanner: Scanner, storage: ScanStorage, resolver: HostResolver) -> None: ...
  ```

  No `SQLiteDatabase(...)` or `PingScanner(...)` constructed inside the
  business layer.

---

## Work areas

Each area lists what "done" means for v4.0.0. The priority marks what the
release needs (**Must**) and what can follow in 4.x if time runs out
(**Should** / **Could**); see [review notes](#review-notes-and-risks).

### 1. Domain models (Must)

Frozen dataclasses and enums over strings:

```python
@dataclass(frozen=True)
class Target:
    address: IPv4Address | IPv6Address


@dataclass(frozen=True)
class ScanResult:
    target: Target
    status: ScanStatus
    latency_ms: float | None
    hostname: str | None
    open_ports: tuple[int, ...]
```

Use `Enum`, `dataclass`, `Protocol`, `TypeAlias`, `TypedDict`, and `Generic`
where they fit. v4 requires Python 3.10+, so `X | None` syntax is available.

### 2. Scanner abstraction (Must)

```text
Scanner
├── PingScanner          (system ping, today's behaviour)
├── TCPConnectScanner    (for hosts that block ICMP; see #41)
├── PortScanner
└── CompositeScanner
```

Selected with `ipmg scan --method ping|tcp|composite`. No raw-socket
`ICMPScanner` in 4.0: it needs elevated privileges, and "no root required" is
a promise 3.x makes.

### 3. Streaming pipeline with bounded concurrency (Must)

```text
Target generation → work queue → bounded workers → result stream
                                                    ├── storage
                                                    ├── exporters
                                                    ├── WebSocket
                                                    ├── metrics
                                                    └── notifications
```

Bounded concurrency, not "more threads". Each stage can be tuned and tested
on its own. Nothing holds the whole scan in memory to process it afterwards.

### 4. Storage abstraction (Must)

A `ScanStorage` protocol with SQLite as the default implementation. **The
existing `~/.ipmg/dashboard.db` must open and migrate in place.**

### 5. Exporter architecture (Must)

The five 3.x formats (`xlsx`, `csv`, `json`, `jsonl`, `md`) become
`ReportExporter` implementations with byte-compatible output. HTML, PDF, and
others become possible as plugins without touching the scanner.

### 6. Error architecture (Must)

```text
IPMGError
├── ConfigurationError
├── InputError
├── ScanError
├── ResolverError
├── StorageError
├── ExportError
└── PluginError
```

Map the existing 3.x classes onto these, keeping their names as aliases. No
bare `except Exception:` in application code.

### 7. Type checking as a release gate (Must)

```bash
ruff check .
ruff format --check .
mypy src/
pytest
```

Rules: no new untyped public APIs, and no `Any` without a comment explaining
why. Pyright is optional.

### 8. Testing architecture (Must: contract tests; Should: the rest)

```text
tests/
├── unit/
├── integration/
├── contract/      every Scanner, ScanStorage, ReportExporter, and plugin passes the same suite
├── performance/
├── security/
├── e2e/
└── fixtures/
```

Property-based tests (Hypothesis) for IP, CIDR and range parsing, duplicate
removal, config validation, scan diffing, and serialization round-trips.

### 9. Plugin system (Must: the contracts and loading; Could: an installer)

Plugin categories: scanner, exporter, storage, notification, discovery, and
(later) UI. Plugins are ordinary Python packages found through **entry
points**:

```bash
pip install ipmg-postgres   # the user installs plugins like any package
ipmg plugin list            # IPMG lists what it found, and their versions
```

`ipmg plugin install` is not in 4.0; see [review notes](#review-notes-and-risks).

### 10. Configuration system (Should)

A typed configuration model over the **existing TOML files**, which gives
3.x configs a path forward:

```toml
[scan]
timeout = 1.0
concurrency = 100
resolve_dns = true

[ports]
enabled = true
timeout = 0.5
ports = [22, 80, 443]

[reports]
formats = ["json", "csv"]

[storage]
backend = "sqlite"
path = "~/.ipmg/dashboard.db"
```

Commands: `ipmg config show`, `ipmg config validate`, `ipmg config path`, and
`ipmg scan --config ipmg.toml`. Flat 3.x keys keep working.

### 11. CLI redesign (Should)

```bash
ipmg scan | discover | diff | history | inventory | report | config | plugin | web
```

`ipmg --input ...` (scanning from the root command) and every 3.x flag keep
working as aliases for `ipmg scan`.

### 12. Web and API separation (Should)

The web UI talks to application services, never to scanner internals. The
REST API stays versioned under `/api/v1` and only grows (the policy in
`docs/API.md`): new endpoints such as `GET /api/v1/inventory` and
`GET /api/v1/health` are additions. Anything breaking goes to `/api/v2`.

### 13. Reproducible scan metadata (Should)

Each scan records how it was performed:

```json
{
  "scan_id": "…",
  "started_at": "…",
  "finished_at": "…",
  "scanner": "ping",
  "scanner_version": "4.x",
  "configuration_hash": "…",
  "target_count": 256
}
```

This lets a diff show when two scans were not taken the same way.

### 14. Performance engineering (Should)

A benchmark suite at 1,000, 10,000, 50,000, and 65,536 targets, measuring
duration, hosts/s, memory, CPU, DNS throughput, report generation, and
database write throughput. The published table compares 3.x with 4.x.

Benchmarks run against a **fake scanner and loopback**, not real networks,
so they are repeatable and CI-safe. Real-network numbers are reported
separately, with the conditions they were measured under.

### 15. Observability (Should)

`--log-level` and `--log-format json` for structured events:

```json
{"event": "scan_completed", "target_count": 256, "active_hosts": 37, "duration_seconds": 4.21}
```

Pipeline metrics: `hosts_scanned_total`, `hosts_active_total`,
`hosts_inactive_total`, `scan_duration_seconds`, `scan_errors_total`,
`dns_resolution_duration_seconds`, `port_scan_duration_seconds`.

### 16. Notification architecture (Should)

`Notifier` protocol: console, webhook, Slack, Teams, email (all existing), and
`ipmg scan --notify webhook` or configuration-driven notifications. The point
is pluggability, not the number of integrations.

### 17. Security hardening (Should)

Strict IPv4/IPv6 and CIDR validation with expansion limits (present, to be
kept under test), SSRF-resistant web behaviour, safe output paths, secrets
never logged, secure token generation, configurable token lifetime, security
headers, request-size limits, authenticated WebSockets (present), bandit,
pip-audit and detect-secrets (present), Semgrep-style rules, and fuzz tests
for the target parsers.

### 18. Inventory model, tags and groups (Could)

```text
Host: IP addresses, hostnames, MAC (where available; see #42), first seen,
      last seen, last status, open ports, tags, metadata
```

```bash
ipmg inventory list | show 192.168.1.10 | export
ipmg scan --tag production
```

### 19. Documentation (Must: architecture and ADRs; Should: the rest)

Document public APIs and architectural contracts, not every function:

```python
class ScanStorage(Protocol):
    """Persistence abstraction for scan results.

    Implementations must support storing scan metadata and individual host
    results without coupling callers to a specific database.
    """
```

```text
docs/
├── architecture/
│   ├── overview.md  domain.md  scanning.md  storage.md  plugins.md  web.md
│   └── decisions/
│       ├── ADR-001 plugin architecture
│       ├── ADR-002 storage abstraction
│       ├── ADR-003 scanner abstraction
│       ├── ADR-004 concurrency model
│       └── ADR-005 configuration model
├── development/     contributing, testing, performance, release
└── api/
```

`docs/architecture/overview.md` also closes #66.

---

## Out of scope

v4 must not become "add everything". These are not in v4:

- a full nmap replacement, OS fingerprinting, or vulnerability scanning
- packet capture
- distributed scanning clusters
- a cloud dashboard, Kubernetes operator, or mobile app
- a large SIEM integration suite
- SNMP polling (#62)

---

## Compatibility contract

```text
v3 workflows → compatibility layer → v4 core
```

Where it is technically reasonable, 3.x users keep:

- **CLI workflows:** every 3.x command and flag, and the root command
  scanning as before
- **Report formats:** the same five formats, file names, and columns
- **SQLite history:** the existing database opens and migrates in place
- **Configuration:** existing `ipmg.toml` files load unchanged
- **IPMG Web and `/api/v1`:** unchanged or additive
- **Exit codes:** `0`, `1`, `2`, `3`, `130` with the same meanings
- **JSON change types:** such as `service_changed`

**Known breaking change:** Python 3.10 is the minimum (3.9 reached end of
life in October 2025). This is already committed on the `v4` branch.

---

## Schedule

| Dates (2026) | Phase | Work |
| --- | --- | --- |
| Oct 1–7 | Architecture freeze | Architecture, protocols, domain models, plugin contracts, compatibility requirements, ADRs 001–005. No feature creep. |
| Oct 8–14 | Core refactor | Scanner, storage, and exporter abstractions; application services; dependency injection; typed models; error hierarchy |
| Oct 15–21 | Performance and quality | Bounded pipeline, benchmarks, mypy gate, ruff, security checks, test expansion |
| Oct 22–26 | Web/API and plugins | API separation, plugin loading, configuration, CLI subcommands, web integration |
| Oct 27–29 | Release candidate | `v4.0.0-rc1`: full CI, docs review, migration, fresh-install and upgrade testing, benchmark comparison, security review |
| Oct 30–31 | v4.0.0 | Bug fixes, documentation, and packaging only. No new features. |

---

## Development policy

The `v4` branch puts architectural quality and maintainability ahead of new
features. Every significant component introduced or refactored for v4 is
evaluated for:

1. SOLID design
2. separation of concerns
3. testability
4. performance
5. scalability
6. type safety
7. documentation
8. extensibility
9. security
10. backward compatibility where applicable

New functionality is built as independent, reusable components wherever
practical.

---

## Release rule

v4.0.0 is not final until all of these are done:

- [ ] architecture review
- [ ] test-suite validation
- [ ] type checking
- [ ] linting and formatting checks
- [ ] security checks
- [ ] performance benchmarks
- [ ] documentation review
- [ ] migration/compatibility testing
- [ ] clean installation testing
- [ ] release-candidate validation

---

## Release mechanics

Releases are cut by python-semantic-release from `main` only, so the `v4`
branch publishes nothing on its own. That affects the plan in four ways:

1. **v4.0.0 is reserved.** Until `v4` merges, nothing on `main` may use `!`
   or a `BREAKING CHANGE:` footer, or `main` would release 4.0.0 early.
   Breaking changes are committed to `v4`.
2. **CI does not run on `v4` pushes.** The workflows trigger on pushes to
   `main` and pull requests into it. Keep a draft pull request `v4` → `main`
   open so every push is tested.
3. **`v4.0.0-rc1` needs release configuration** that does not exist yet: a
   prerelease branch group for `v4` in `[tool.semantic_release]` and a
   publish trigger for that branch. It is a maintainer decision and should be
   made before Oct 27.
4. **Keep `v4` current:** merge `main` into `v4` after each 3.x release so
   fixes are not lost.

---

## Review notes and risks

These came out of checking this plan against the 3.1 code base:

- **Scope versus time.** Nineteen work areas in 31 days is a lot for one
  maintainer. The **Must** items (the five pillars, the Python floor, and
  the compatibility contract) are the release. **Should** and **Could**
  items move to 4.1+ rather than delaying 4.0.0 or shipping half-built.
- **TOML, not YAML.** 3.x already has a validated TOML config with profiles.
  Adding YAML would mean a second format, a new dependency, and a migration
  for existing users.
- **`ipmg plugin install` is left out.** An installer that runs pip from
  inside IPMG widens the supply-chain surface and fights uv, pipx, Homebrew,
  and Docker installs. Entry-point discovery plus `ipmg plugin list` gives
  pluggability without it.
- **Unversioned `/api/scans` routes would break `/api/v1`'s stability
  promise.** New routes go under `/api/v1`.
- **The biggest compatibility risks are** the root command still scanning
  (`ipmg --input …`), byte-compatible report output, and migrating the
  SQLite history in place. Each needs a test written *before* the refactor.
- **The Windows ping status fix** in 3.1.1 (exit 0 on "Destination host
  unreachable") must carry over into `PingScanner`, with its tests.

Related issues: #41 (TCP-connect probing), #42 (MAC and vendor lookup),
#61 (HTTP checks, a scanner plugin), #64 (GitHub Action), #66 (architecture
overview).
