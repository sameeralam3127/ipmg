# Security Policy

## Supported Versions

Only the latest release receives security updates.

| Version | Supported          |
| ------- | ------------------ |
| 1.11.x  | :white_check_mark: |
| < 1.11  | :x:                |

## Reporting a Vulnerability

Please report vulnerabilities privately — do not open a public issue.

- Use [GitHub private vulnerability reporting](https://github.com/sameeralam3127/ipmg/security/advisories/new), or
- Email the maintainer: sameeralam3127@gmail.com

Include what you found, steps to reproduce, and the version affected.
You can expect an acknowledgement within a few days; fixes are released
through the normal automated release pipeline as soon as they are ready.

## Scope and Expectations

IPMG sends ICMP ping traffic. Only use it on networks where you have
explicit authorization — unauthorized scanning may violate your
organization's policies or the law.

The web dashboard is designed for local use: it binds to `127.0.0.1` by
default, origin-checks WebSocket connections, caps uploads and target
expansion, and uses parameterized SQL throughout. It intentionally has no
built-in authentication, so exposing it on a non-local interface without a
reverse proxy in front is outside the supported threat model.

## Known Issues

Tracked hardening items — see the linked issues for details:

- Dashboard REST API has no authentication; keep it on `127.0.0.1` and do not
  expose it beyond localhost ([#21](https://github.com/sameeralam3127/ipmg/issues/21))
- Unbounded live-event buffering, only reachable when the dashboard is exposed
  remotely ([#23](https://github.com/sameeralam3127/ipmg/issues/23))

Please do not open a new public issue for anything already listed here. For
anything not listed, report it privately via the
[security advisory](https://github.com/sameeralam3127/ipmg/security/advisories/new)
link above.
