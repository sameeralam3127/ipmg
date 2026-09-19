# Security Policy

## Supported Versions

Only the latest release receives security updates.

| Version | Supported          |
| ------- | ------------------ |
| 1.13.x  | :white_check_mark: |
| < 1.13  | :x:                |

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

IPMG Web is designed for local use: it binds to `127.0.0.1` by
default, requires an access token (random per start, or `IPMG_WEB_TOKEN`)
on every API request and WebSocket, origin-checks WebSocket connections,
disconnects live-update clients that stop reading, caps uploads and target
expansion, and uses parameterized SQL throughout. It serves plain HTTP, so
on a non-local interface put a reverse proxy with TLS in front of it.

## Known Issues

There are no known open security issues. Earlier hardening items (API
authentication, [#21](https://github.com/sameeralam3127/ipmg/issues/21); bounded
live-event buffering, [#23](https://github.com/sameeralam3127/ipmg/issues/23))
are fixed.

Please do not open a new public issue for anything already listed here. For
anything not listed, report it privately via the
[security advisory](https://github.com/sameeralam3127/ipmg/security/advisories/new)
link above.
