# CHANGELOG

<!-- version list -->

## v1.8.0 (2026-07-26)

### Features

- **cli**: Flat, modern terminal interface ([#18](https://github.com/sameeralam3127/ipmg/pull/18),
  [`7c247c2`](https://github.com/sameeralam3127/ipmg/commit/7c247c2b0d32d856fcffa335596b131d6212aa50))


## v1.7.0 (2026-07-26)

### Bug Fixes

- **discover**: Detect the outbound interface instead of the hostname address
  ([#17](https://github.com/sameeralam3127/ipmg/pull/17),
  [`f4fb55c`](https://github.com/sameeralam3127/ipmg/commit/f4fb55c4131d6e6f929426ae17a02d484fa0456b))

- **ping**: Use milliseconds for the ping timeout on macOS and BSD
  ([#17](https://github.com/sameeralam3127/ipmg/pull/17),
  [`f4fb55c`](https://github.com/sameeralam3127/ipmg/commit/f4fb55c4131d6e6f929426ae17a02d484fa0456b))

### Features

- Compare scan history and detect changes ([#17](https://github.com/sameeralam3127/ipmg/pull/17),
  [`f4fb55c`](https://github.com/sameeralam3127/ipmg/commit/f4fb55c4131d6e6f929426ae17a02d484fa0456b))

- Compare scan history and detect changes (closes #11)
  ([#17](https://github.com/sameeralam3127/ipmg/pull/17),
  [`f4fb55c`](https://github.com/sameeralam3127/ipmg/commit/f4fb55c4131d6e6f929426ae17a02d484fa0456b))


## v1.6.1 (2026-07-13)

### Bug Fixes

- Add websockets dependency for dashboard live updates
  ([#16](https://github.com/sameeralam3127/ipmg/pull/16),
  [`87451a7`](https://github.com/sameeralam3127/ipmg/commit/87451a734aaaed8b7d6679f941fff1f5df364c1b))


## v1.6.0 (2026-07-13)

### Continuous Integration

- Add security scanning workflow and secret detection
  ([#14](https://github.com/sameeralam3127/ipmg/pull/14),
  [`9ff9f56`](https://github.com/sameeralam3127/ipmg/commit/9ff9f56c1c0ed766280063a11d1d7d597ee56e2f))

### Features

- Add local web dashboard with shared scan engine
  ([#15](https://github.com/sameeralam3127/ipmg/pull/15),
  [`f0347f9`](https://github.com/sameeralam3127/ipmg/commit/f0347f9a292d4208c03ecbc83debab087446a000))


## v1.5.0 (2026-07-13)

### Features

- Add security workflow for code analysis
  ([`73aa92e`](https://github.com/sameeralam3127/ipmg/commit/73aa92ee4715206eb18e42620b782a2267208b32))


## v1.4.0 (2026-07-13)

### Documentation

- Simplify README ([#13](https://github.com/sameeralam3127/ipmg/pull/13),
  [`f2df9cd`](https://github.com/sameeralam3127/ipmg/commit/f2df9cd6f76aa674529546e024cd282416e719d2))

### Features

- Cache reverse DNS lookups ([#13](https://github.com/sameeralam3127/ipmg/pull/13),
  [`f2df9cd`](https://github.com/sameeralam3127/ipmg/commit/f2df9cd6f76aa674529546e024cd282416e719d2))


## v1.3.0 (2026-06-28)

### Features

- Add markdown scan reports
  ([`2093a34`](https://github.com/sameeralam3127/ipmg/commit/2093a342aa4bc3c09da50414f6953bf679506397))


## v1.2.0 (2026-06-04)

### Features

- Add CLI version flag and release docs
  ([`1ccbbbe`](https://github.com/sameeralam3127/ipmg/commit/1ccbbbe92efd854e173302582147c053c7fa8e96))


## v1.1.2 (2026-04-25)

### Bug Fixes

- Harden scan resource limits
  ([`e10118d`](https://github.com/sameeralam3127/ipmg/commit/e10118d763d2090f7c6f9ee0e785c5c7ccf55652))

### Chores

- Enrich PyPI project metadata
  ([`54e79d4`](https://github.com/sameeralam3127/ipmg/commit/54e79d4f4e511d62683af0543d506c7b28bf0fa8))


## v1.1.1 (2026-04-08)

### Bug Fixes

- Use pypi environment for trusted publishing
  ([`6e0507d`](https://github.com/sameeralam3127/ipmg/commit/6e0507d059b70fcd8cfdcf220033dca17561d001))


## v1.1.0 (2026-04-08)

### Bug Fixes

- Build releases outside semantic-release container
  ([`ed49a04`](https://github.com/sameeralam3127/ipmg/commit/ed49a04c8a792b80dd56987181925aad4e8db523))

- Release to PyPI from semantic release outputs
  ([`4524fa0`](https://github.com/sameeralam3127/ipmg/commit/4524fa032c05ee1876428fc5e7f2bd9fa599b07f))

- Test release pipeline
  ([`c57641f`](https://github.com/sameeralam3127/ipmg/commit/c57641f8b3fea72171db136c687dc51b4b1151eb))

### Chores

- Initialize semantic release
  ([`ffa82c2`](https://github.com/sameeralam3127/ipmg/commit/ffa82c29e01650ae3f53b2f648d0565a50b82d0a))

- Prepare next PyPI release
  ([`69633be`](https://github.com/sameeralam3127/ipmg/commit/69633bea12e8203395cb9fd35950b269fdb7a3ba))

### Features

- Add subnet scanner
  ([`0b5f3b5`](https://github.com/sameeralam3127/ipmg/commit/0b5f3b56ece22a73bdd033b5f037e318599bbb8d))

- Improve CLI UX and release workflow
  ([`28d74ad`](https://github.com/sameeralam3127/ipmg/commit/28d74ad6d5c8d5c4cbef03eedab4f1588548fdb8))

### Refactoring

- **installer**: Harden install.sh with strict mode, PATH fix, and verification
  ([`f9b404d`](https://github.com/sameeralam3127/ipmg/commit/f9b404d9250358a63472d8c8e79abb9a7c2a8874))


## v1.0.3 (2026-02-14)

- Initial Release
