# CHANGELOG

<!-- version list -->

## v4.0.0-beta.1 (2026-10-18)

### Bug Fixes

- Removed unnecessary vulnerability ignore flag. Fixes #48
  ([#125](https://github.com/sameeralam3127/ipmg/pull/125),
  [`2ae2723`](https://github.com/sameeralam3127/ipmg/commit/2ae2723199001691b1b6db61c0e5214cdb21fcc6))

- TCP refusals and MAC lookups on Windows ([#125](https://github.com/sameeralam3127/ipmg/pull/125),
  [`2ae2723`](https://github.com/sameeralam3127/ipmg/commit/2ae2723199001691b1b6db61c0e5214cdb21fcc6))

- Windows TCP refusals and MAC lookups, and link the architecture overview
  ([#125](https://github.com/sameeralam3127/ipmg/pull/125),
  [`2ae2723`](https://github.com/sameeralam3127/ipmg/commit/2ae2723199001691b1b6db61c0e5214cdb21fcc6))

- Windows unreachable hosts, "Status changed" label, and README presentation
  ([#125](https://github.com/sameeralam3127/ipmg/pull/125),
  [`2ae2723`](https://github.com/sameeralam3127/ipmg/commit/2ae2723199001691b1b6db61c0e5214cdb21fcc6))

- **diff**: Label failure-mode moves "Status changed"
  ([#125](https://github.com/sameeralam3127/ipmg/pull/125),
  [`2ae2723`](https://github.com/sameeralam3127/ipmg/commit/2ae2723199001691b1b6db61c0e5214cdb21fcc6))

- **notify**: Refuse cleartext SMTP auth with --smtp-security none on remote hosts
  ([#125](https://github.com/sameeralam3127/ipmg/pull/125),
  [`2ae2723`](https://github.com/sameeralam3127/ipmg/commit/2ae2723199001691b1b6db61c0e5214cdb21fcc6))

- **ping**: Stop reporting Windows "Destination host unreachable" as Active
  ([#125](https://github.com/sameeralam3127/ipmg/pull/125),
  [`2ae2723`](https://github.com/sameeralam3127/ipmg/commit/2ae2723199001691b1b6db61c0e5214cdb21fcc6))

- **ping**: Use each BSD's own reply-timeout flag
  ([#125](https://github.com/sameeralam3127/ipmg/pull/125),
  [`2ae2723`](https://github.com/sameeralam3127/ipmg/commit/2ae2723199001691b1b6db61c0e5214cdb21fcc6))

- **report**: Write XLSX in write-only mode so large scans save in linear time
  ([#125](https://github.com/sameeralam3127/ipmg/pull/125),
  [`2ae2723`](https://github.com/sameeralam3127/ipmg/commit/2ae2723199001691b1b6db61c0e5214cdb21fcc6))

- **scan**: Keep an --interval monitor running through a failed pass
  ([#125](https://github.com/sameeralam3127/ipmg/pull/125),
  [`2ae2723`](https://github.com/sameeralam3127/ipmg/commit/2ae2723199001691b1b6db61c0e5214cdb21fcc6))

- **web**: Give the IPMG Web demo the real change types
  ([#125](https://github.com/sameeralam3127/ipmg/pull/125),
  [`2ae2723`](https://github.com/sameeralam3127/ipmg/commit/2ae2723199001691b1b6db61c0e5214cdb21fcc6))

- **web**: Limit concurrent scans with --max-scans
  ([#125](https://github.com/sameeralam3127/ipmg/pull/125),
  [`2ae2723`](https://github.com/sameeralam3127/ipmg/commit/2ae2723199001691b1b6db61c0e5214cdb21fcc6))

- **web**: Recover scans left running by a stopped IPMG Web
  ([#125](https://github.com/sameeralam3127/ipmg/pull/125),
  [`2ae2723`](https://github.com/sameeralam3127/ipmg/commit/2ae2723199001691b1b6db61c0e5214cdb21fcc6))

- **web**: Refuse to delete a scan while it is still running
  ([#125](https://github.com/sameeralam3127/ipmg/pull/125),
  [`2ae2723`](https://github.com/sameeralam3127/ipmg/commit/2ae2723199001691b1b6db61c0e5214cdb21fcc6))

- **web**: Send security headers against clickjacking and content sniffing
  ([#125](https://github.com/sameeralam3127/ipmg/pull/125),
  [`2ae2723`](https://github.com/sameeralam3127/ipmg/commit/2ae2723199001691b1b6db61c0e5214cdb21fcc6))

### Build System

- Require Python 3.10 or newer
  ([`302f4b4`](https://github.com/sameeralam3127/ipmg/commit/302f4b4a66c7187f16df652f54f50481ff4cabd6))

- **deps**: Update tomli requirement ([#125](https://github.com/sameeralam3127/ipmg/pull/125),
  [`2ae2723`](https://github.com/sameeralam3127/ipmg/commit/2ae2723199001691b1b6db61c0e5214cdb21fcc6))

### Chores

- Issue forms and a pull request template ([#125](https://github.com/sameeralam3127/ipmg/pull/125),
  [`2ae2723`](https://github.com/sameeralam3127/ipmg/commit/2ae2723199001691b1b6db61c0e5214cdb21fcc6))

- Merge 3.2.0 into v4 and release 4.0.0 betas from v4
  ([#125](https://github.com/sameeralam3127/ipmg/pull/125),
  [`2ae2723`](https://github.com/sameeralam3127/ipmg/commit/2ae2723199001691b1b6db61c0e5214cdb21fcc6))

- **release**: Drop the orphaned 3.1.3 changelog entry
  ([#125](https://github.com/sameeralam3127/ipmg/pull/125),
  [`2ae2723`](https://github.com/sameeralam3127/ipmg/commit/2ae2723199001691b1b6db61c0e5214cdb21fcc6))

### Code Style

- **tests**: Apply black to test_notify.py ([#125](https://github.com/sameeralam3127/ipmg/pull/125),
  [`2ae2723`](https://github.com/sameeralam3127/ipmg/commit/2ae2723199001691b1b6db61c0e5214cdb21fcc6))

### Continuous Integration

- Dependabot and Security workflow improvements. Fixes #48.
  ([#125](https://github.com/sameeralam3127/ipmg/pull/125),
  [`2ae2723`](https://github.com/sameeralam3127/ipmg/commit/2ae2723199001691b1b6db61c0e5214cdb21fcc6))

- Native arm64 Docker builds, a build cache, uv installs, and a real dependency audit
  ([#125](https://github.com/sameeralam3127/ipmg/pull/125),
  [`2ae2723`](https://github.com/sameeralam3127/ipmg/commit/2ae2723199001691b1b6db61c0e5214cdb21fcc6))

- Queue main runs instead of cancelling an in-flight release
  ([#125](https://github.com/sameeralam3127/ipmg/pull/125),
  [`2ae2723`](https://github.com/sameeralam3127/ipmg/commit/2ae2723199001691b1b6db61c0e5214cdb21fcc6))

- Revised dependabot and security workflows according to code review. Fixes #48
  ([#125](https://github.com/sameeralam3127/ipmg/pull/125),
  [`2ae2723`](https://github.com/sameeralam3127/ipmg/commit/2ae2723199001691b1b6db61c0e5214cdb21fcc6))

- Test install.sh on every distribution it claims to support
  ([#125](https://github.com/sameeralam3127/ipmg/pull/125),
  [`2ae2723`](https://github.com/sameeralam3127/ipmg/commit/2ae2723199001691b1b6db61c0e5214cdb21fcc6))

### Documentation

- Add comprehensive architecture overview for contributors
  ([#125](https://github.com/sameeralam3127/ipmg/pull/125),
  [`2ae2723`](https://github.com/sameeralam3127/ipmg/commit/2ae2723199001691b1b6db61c0e5214cdb21fcc6))

- Architecture overview for contributors ([#125](https://github.com/sameeralam3127/ipmg/pull/125),
  [`2ae2723`](https://github.com/sameeralam3127/ipmg/commit/2ae2723199001691b1b6db61c0e5214cdb21fcc6))

- Compare IPMG with nmap, fping, and Uptime Kuma, with sources
  ([#125](https://github.com/sameeralam3127/ipmg/pull/125),
  [`2ae2723`](https://github.com/sameeralam3127/ipmg/commit/2ae2723199001691b1b6db61c0e5214cdb21fcc6))

- Replace pinned example versions with X.Y.Z and update the PyPI summary
  ([#125](https://github.com/sameeralam3127/ipmg/pull/125),
  [`2ae2723`](https://github.com/sameeralam3127/ipmg/commit/2ae2723199001691b1b6db61c0e5214cdb21fcc6))

- Show change detection in the README visuals
  ([#125](https://github.com/sameeralam3127/ipmg/pull/125),
  [`2ae2723`](https://github.com/sameeralam3127/ipmg/commit/2ae2723199001691b1b6db61c0e5214cdb21fcc6))

- **readme**: Add requirements and platform support
  ([#125](https://github.com/sameeralam3127/ipmg/pull/125),
  [`2ae2723`](https://github.com/sameeralam3127/ipmg/commit/2ae2723199001691b1b6db61c0e5214cdb21fcc6))

- **readme**: Lead with change detection ([#125](https://github.com/sameeralam3127/ipmg/pull/125),
  [`2ae2723`](https://github.com/sameeralam3127/ipmg/commit/2ae2723199001691b1b6db61c0e5214cdb21fcc6))

- **v4**: Add the v4 development plan and notice
  ([`c50cb5b`](https://github.com/sameeralam3127/ipmg/commit/c50cb5b2b61a9ea5559c29d76c1cae0e70b570bb))

### Features

- GitHub Action to run an IPMG scan in CI ([#125](https://github.com/sameeralam3127/ipmg/pull/125),
  [`2ae2723`](https://github.com/sameeralam3127/ipmg/commit/2ae2723199001691b1b6db61c0e5214cdb21fcc6))

- Systemd and launchd service templates for scheduled scans
  ([#125](https://github.com/sameeralam3127/ipmg/pull/125),
  [`2ae2723`](https://github.com/sameeralam3127/ipmg/commit/2ae2723199001691b1b6db61c0e5214cdb21fcc6))

- Wake-on-LAN with ipmg wake and an inventory Wake button
  ([#125](https://github.com/sameeralam3127/ipmg/pull/125),
  [`2ae2723`](https://github.com/sameeralam3127/ipmg/commit/2ae2723199001691b1b6db61c0e5214cdb21fcc6))

- **cli**: Shell completion for bash, zsh, fish, and PowerShell
  ([#125](https://github.com/sameeralam3127/ipmg/pull/125),
  [`2ae2723`](https://github.com/sameeralam3127/ipmg/commit/2ae2723199001691b1b6db61c0e5214cdb21fcc6))

- **history**: Retention for scan history and report files
  ([#125](https://github.com/sameeralam3127/ipmg/pull/125),
  [`2ae2723`](https://github.com/sameeralam3127/ipmg/commit/2ae2723199001691b1b6db61c0e5214cdb21fcc6))

- **scan**: Bound reverse DNS lookups with --dns-timeout
  ([#125](https://github.com/sameeralam3127/ipmg/pull/125),
  [`2ae2723`](https://github.com/sameeralam3127/ipmg/commit/2ae2723199001691b1b6db61c0e5214cdb21fcc6))

- **scan**: HTTP(S) checks with status code and response time
  ([#125](https://github.com/sameeralam3127/ipmg/pull/125),
  [`2ae2723`](https://github.com/sameeralam3127/ipmg/commit/2ae2723199001691b1b6db61c0e5214cdb21fcc6))

- **scan**: MAC address and vendor lookup with --mac
  ([#125](https://github.com/sameeralam3127/ipmg/pull/125),
  [`2ae2723`](https://github.com/sameeralam3127/ipmg/commit/2ae2723199001691b1b6db61c0e5214cdb21fcc6))

- **scan**: TCP-connect probing for hosts that block ICMP
  ([#125](https://github.com/sameeralam3127/ipmg/pull/125),
  [`2ae2723`](https://github.com/sameeralam3127/ipmg/commit/2ae2723199001691b1b6db61c0e5214cdb21fcc6))

- **web**: Scheduled recurring scans in IPMG Web
  ([#125](https://github.com/sameeralam3127/ipmg/pull/125),
  [`2ae2723`](https://github.com/sameeralam3127/ipmg/commit/2ae2723199001691b1b6db61c0e5214cdb21fcc6))

### Performance Improvements

- **web**: Batch scan result writes and run SQLite in WAL mode
  ([#125](https://github.com/sameeralam3127/ipmg/pull/125),
  [`2ae2723`](https://github.com/sameeralam3127/ipmg/commit/2ae2723199001691b1b6db61c0e5214cdb21fcc6))

### Testing

- Check XLSX write scaling by ratio, not a wall-clock limit
  ([#125](https://github.com/sameeralam3127/ipmg/pull/125),
  [`2ae2723`](https://github.com/sameeralam3127/ipmg/commit/2ae2723199001691b1b6db61c0e5214cdb21fcc6))

- Use httpx2 for the TestClient and fail on first-party deprecations
  ([#125](https://github.com/sameeralam3127/ipmg/pull/125),
  [`2ae2723`](https://github.com/sameeralam3127/ipmg/commit/2ae2723199001691b1b6db61c0e5214cdb21fcc6))


## v3.2.0 (2026-10-18)

### Bug Fixes

- TCP refusals and MAC lookups on Windows ([#124](https://github.com/sameeralam3127/ipmg/pull/124),
  [`bc4f612`](https://github.com/sameeralam3127/ipmg/commit/bc4f6123e0750bc06ac115c0f6bd0d98aa875fbf))

- Windows TCP refusals and MAC lookups, and link the architecture overview
  ([#124](https://github.com/sameeralam3127/ipmg/pull/124),
  [`bc4f612`](https://github.com/sameeralam3127/ipmg/commit/bc4f6123e0750bc06ac115c0f6bd0d98aa875fbf))

- **ping**: Use each BSD's own reply-timeout flag
  ([`c543089`](https://github.com/sameeralam3127/ipmg/commit/c543089b7b62a11f32b28c8369ea3739529e5895))

- **scan**: Keep an --interval monitor running through a failed pass
  ([`59b63ef`](https://github.com/sameeralam3127/ipmg/commit/59b63efaa0a70a3ef3ec303c27ab78088f87fd57))

- **web**: Limit concurrent scans with --max-scans
  ([`2aaf34b`](https://github.com/sameeralam3127/ipmg/commit/2aaf34b64dd1ccbb2cec1d45e5ca4c0694ea7438))

- **web**: Recover scans left running by a stopped IPMG Web
  ([`475772d`](https://github.com/sameeralam3127/ipmg/commit/475772d90cc9aae5824c16ea55cc763cb2c5e757))

- **web**: Refuse to delete a scan while it is still running
  ([`d51a3de`](https://github.com/sameeralam3127/ipmg/commit/d51a3de3df663867b914e79cd73a9eb119bb3eb3))

- **web**: Send security headers against clickjacking and content sniffing
  ([`ff8c514`](https://github.com/sameeralam3127/ipmg/commit/ff8c5140f1be61bb3706d7db649d597519769f3b))

### Chores

- Issue forms and a pull request template
  ([`51b2433`](https://github.com/sameeralam3127/ipmg/commit/51b2433b6cf4ca8b495de219247f963976944a58))

### Continuous Integration

- Native arm64 Docker builds, a build cache, uv installs, and a real dependency audit
  ([`018e9b6`](https://github.com/sameeralam3127/ipmg/commit/018e9b622e022eb45d6e244b313690f4e444df8b))

- Queue main runs instead of cancelling an in-flight release
  ([#121](https://github.com/sameeralam3127/ipmg/pull/121),
  [`1cadfbf`](https://github.com/sameeralam3127/ipmg/commit/1cadfbf1987d87c47e99b77b725694297ac1bcd3))

- Test install.sh on every distribution it claims to support
  ([`de5a75b`](https://github.com/sameeralam3127/ipmg/commit/de5a75b71e8fbc4a0874312ea3115969d4937231))

### Documentation

- Add comprehensive architecture overview for contributors
  ([`0595daf`](https://github.com/sameeralam3127/ipmg/commit/0595daf0d7ffc7ad34566f13fbb21b0323ece24b))

- Architecture overview for contributors ([#124](https://github.com/sameeralam3127/ipmg/pull/124),
  [`bc4f612`](https://github.com/sameeralam3127/ipmg/commit/bc4f6123e0750bc06ac115c0f6bd0d98aa875fbf))

- Compare IPMG with nmap, fping, and Uptime Kuma, with sources
  ([`1ce1877`](https://github.com/sameeralam3127/ipmg/commit/1ce18777be800ee0d49b4ca8515ac285d0ce81e5))

- Replace pinned example versions with X.Y.Z and update the PyPI summary
  ([`160acbf`](https://github.com/sameeralam3127/ipmg/commit/160acbf97bd982c02e4226b633736d0c4577a022))

### Features

- GitHub Action to run an IPMG scan in CI
  ([`d2c3f2e`](https://github.com/sameeralam3127/ipmg/commit/d2c3f2e7775730ac059d24a88e9accc2b9f6910f))

- Systemd and launchd service templates for scheduled scans
  ([`2555756`](https://github.com/sameeralam3127/ipmg/commit/2555756be86effc4b516c7e39199b97cbf20130c))

- Wake-on-LAN with ipmg wake and an inventory Wake button
  ([`8674866`](https://github.com/sameeralam3127/ipmg/commit/86748665a6251fa6352fc9a5c968d07b93744c8d))

- **cli**: Shell completion for bash, zsh, fish, and PowerShell
  ([`be7e00a`](https://github.com/sameeralam3127/ipmg/commit/be7e00aebb00919a4b2aed271e9311fddcb55cca))

- **history**: Retention for scan history and report files
  ([`8ce89ac`](https://github.com/sameeralam3127/ipmg/commit/8ce89ac0ee6a2eebc75d08ad35d487497b352cad))

- **scan**: Bound reverse DNS lookups with --dns-timeout
  ([`0d9c90a`](https://github.com/sameeralam3127/ipmg/commit/0d9c90a13c59b99b1d77a7107ce98d328f5f9401))

- **scan**: HTTP(S) checks with status code and response time
  ([`3f563a8`](https://github.com/sameeralam3127/ipmg/commit/3f563a86967862271cd261d5c3d3840cca74e8b5))

- **scan**: MAC address and vendor lookup with --mac
  ([`f00ccb0`](https://github.com/sameeralam3127/ipmg/commit/f00ccb02e9081b8ac8fbd82bfad5a4babaeeeda9))

- **scan**: TCP-connect probing for hosts that block ICMP
  ([`9a83336`](https://github.com/sameeralam3127/ipmg/commit/9a833367e31cc717576ebb255778626e5393c072))

- **web**: Scheduled recurring scans in IPMG Web
  ([`d07e0e0`](https://github.com/sameeralam3127/ipmg/commit/d07e0e0a39262e2a593a019a7b9486dda9b73e4d))

### Performance Improvements

- **web**: Batch scan result writes and run SQLite in WAL mode
  ([`9dd3872`](https://github.com/sameeralam3127/ipmg/commit/9dd38721891667d6d54c696419c2042d17ba4746))

### Testing

- Use httpx2 for the TestClient and fail on first-party deprecations
  ([`ff9c457`](https://github.com/sameeralam3127/ipmg/commit/ff9c457618078d12dff76d574cf2fe0e7269129e))


## v3.1.4 (2026-10-08)

### Bug Fixes

- **report**: Write XLSX in write-only mode so large scans save in linear time
  ([#120](https://github.com/sameeralam3127/ipmg/pull/120),
  [`89cffbd`](https://github.com/sameeralam3127/ipmg/commit/89cffbdc86985eb1a924f65e37cbc9cdeeec415a))

### Testing

- Check XLSX write scaling by ratio, not a wall-clock limit
  ([#120](https://github.com/sameeralam3127/ipmg/pull/120),
  [`89cffbd`](https://github.com/sameeralam3127/ipmg/commit/89cffbdc86985eb1a924f65e37cbc9cdeeec415a))


## v3.1.3 (2026-10-04)

### Bug Fixes

- Removed unnecessary vulnerability ignore flag. Fixes #48
  ([#117](https://github.com/sameeralam3127/ipmg/pull/117),
  [`5cb56aa`](https://github.com/sameeralam3127/ipmg/commit/5cb56aaaf05059506c414546e21c2e789827b67a))

### Build System

- **deps**: Update tomli requirement ([#116](https://github.com/sameeralam3127/ipmg/pull/116),
  [`5b51bd6`](https://github.com/sameeralam3127/ipmg/commit/5b51bd6c32913cbbdac3ed0790f797028fdd21a1))

### Chores

- **release**: Drop the orphaned 3.1.3 changelog entry
  ([#119](https://github.com/sameeralam3127/ipmg/pull/119),
  [`e860cee`](https://github.com/sameeralam3127/ipmg/commit/e860cee15b97ce61d34d659ebb76540c7fe6d7e7))

### Code Style

- **tests**: Apply black to test_notify.py ([#118](https://github.com/sameeralam3127/ipmg/pull/118),
  [`577bd11`](https://github.com/sameeralam3127/ipmg/commit/577bd1142a50de4228f1dc3ebfbb4b79bf2ff8d7))

### Continuous Integration

- Dependabot and Security workflow improvements. Fixes #48.
  ([#117](https://github.com/sameeralam3127/ipmg/pull/117),
  [`5cb56aa`](https://github.com/sameeralam3127/ipmg/commit/5cb56aaaf05059506c414546e21c2e789827b67a))

- Revised dependabot and security workflows according to code review. Fixes #48
  ([#117](https://github.com/sameeralam3127/ipmg/pull/117),
  [`5cb56aa`](https://github.com/sameeralam3127/ipmg/commit/5cb56aaaf05059506c414546e21c2e789827b67a))


## v3.1.2 (2026-09-30)

### Bug Fixes

- **notify**: Refuse cleartext SMTP auth with --smtp-security none on remote hosts
  ([#115](https://github.com/sameeralam3127/ipmg/pull/115),
  [`019a0a9`](https://github.com/sameeralam3127/ipmg/commit/019a0a971b75e025262f348f003018df3cc73486))


## v3.1.1 (2026-09-29)

### Bug Fixes

- Windows unreachable hosts, "Status changed" label, and README presentation
  ([#96](https://github.com/sameeralam3127/ipmg/pull/96),
  [`cf9a6c5`](https://github.com/sameeralam3127/ipmg/commit/cf9a6c51adf07fb3ad675cddcaa261660d51d6bb))

- **diff**: Label failure-mode moves "Status changed"
  ([#96](https://github.com/sameeralam3127/ipmg/pull/96),
  [`cf9a6c5`](https://github.com/sameeralam3127/ipmg/commit/cf9a6c51adf07fb3ad675cddcaa261660d51d6bb))

- **ping**: Stop reporting Windows "Destination host unreachable" as Active
  ([#96](https://github.com/sameeralam3127/ipmg/pull/96),
  [`cf9a6c5`](https://github.com/sameeralam3127/ipmg/commit/cf9a6c51adf07fb3ad675cddcaa261660d51d6bb))

- **web**: Give the IPMG Web demo the real change types
  ([#96](https://github.com/sameeralam3127/ipmg/pull/96),
  [`cf9a6c5`](https://github.com/sameeralam3127/ipmg/commit/cf9a6c51adf07fb3ad675cddcaa261660d51d6bb))

### Documentation

- Show change detection in the README visuals
  ([#96](https://github.com/sameeralam3127/ipmg/pull/96),
  [`cf9a6c5`](https://github.com/sameeralam3127/ipmg/commit/cf9a6c51adf07fb3ad675cddcaa261660d51d6bb))

- **readme**: Add requirements and platform support
  ([#96](https://github.com/sameeralam3127/ipmg/pull/96),
  [`cf9a6c5`](https://github.com/sameeralam3127/ipmg/commit/cf9a6c51adf07fb3ad675cddcaa261660d51d6bb))

- **readme**: Lead with change detection ([#96](https://github.com/sameeralam3127/ipmg/pull/96),
  [`cf9a6c5`](https://github.com/sameeralam3127/ipmg/commit/cf9a6c51adf07fb3ad675cddcaa261660d51d6bb))


## v3.1.0 (2026-09-27)

### Features

- **web**: Prometheus /metrics endpoint for scan results
  ([#91](https://github.com/sameeralam3127/ipmg/pull/91),
  [`c4bfb97`](https://github.com/sameeralam3127/ipmg/commit/c4bfb977b0bc1b4691f1cf0e6c363726fdf5049d))

### Refactoring

- **web**: Import the metrics renderer only when /metrics is enabled
  ([#91](https://github.com/sameeralam3127/ipmg/pull/91),
  [`c4bfb97`](https://github.com/sameeralam3127/ipmg/commit/c4bfb977b0bc1b4691f1cf0e6c363726fdf5049d))


## v3.0.0 (2026-09-27)

### Build System

- **docker**: Install the web extra, so the image keeps IPMG Web after the lean-core split
  ([#92](https://github.com/sameeralam3127/ipmg/pull/92),
  [`2f97eb0`](https://github.com/sameeralam3127/ipmg/commit/2f97eb0358b0addb160298a4cd5a280ab0e8f3e4))

### Continuous Integration

- **docker**: Use a random token per smoke-test run
  ([#92](https://github.com/sameeralam3127/ipmg/pull/92),
  [`2f97eb0`](https://github.com/sameeralam3127/ipmg/commit/2f97eb0358b0addb160298a4cd5a280ab0e8f3e4))

### Documentation

- Place the extras section after Installing with pip
  ([#95](https://github.com/sameeralam3127/ipmg/pull/95),
  [`b0f2072`](https://github.com/sameeralam3127/ipmg/commit/b0f2072daea374745e72c7777a678da3bb42743f))

### Features

- **docker**: Official multi-arch image on GHCR
  ([#92](https://github.com/sameeralam3127/ipmg/pull/92),
  [`2f97eb0`](https://github.com/sameeralam3127/ipmg/commit/2f97eb0358b0addb160298a4cd5a280ab0e8f3e4))

- **install**: Install.ps1 installs the web extra, like install.sh
  ([#93](https://github.com/sameeralam3127/ipmg/pull/93),
  [`5c7d2ca`](https://github.com/sameeralam3127/ipmg/commit/5c7d2cae767d6e84f5c3d781812072da7d644ad5))

- **install**: PowerShell installer for Windows (install.ps1)
  ([#93](https://github.com/sameeralam3127/ipmg/pull/93),
  [`5c7d2ca`](https://github.com/sameeralam3127/ipmg/commit/5c7d2cae767d6e84f5c3d781812072da7d644ad5))

- **packaging**: Lean core install without pandas; IPMG Web becomes the `web` extra
  ([#95](https://github.com/sameeralam3127/ipmg/pull/95),
  [`b0f2072`](https://github.com/sameeralam3127/ipmg/commit/b0f2072daea374745e72c7777a678da3bb42743f))

- **packaging**: Lean core install without pandas; IPMG Web becomes the web extra
  ([#95](https://github.com/sameeralam3127/ipmg/pull/95),
  [`b0f2072`](https://github.com/sameeralam3127/ipmg/commit/b0f2072daea374745e72c7777a678da3bb42743f))

- **scan**: IPv6 targets, probing, and neighbour discovery
  ([#90](https://github.com/sameeralam3127/ipmg/pull/90),
  [`64e84a5`](https://github.com/sameeralam3127/ipmg/commit/64e84a52a1432d66b84072fb1bc8eb8d9c595e28))


## v2.4.0 (2026-09-27)

### Bug Fixes

- Address CodeRabbit review on config files and JSON targets
  ([#84](https://github.com/sameeralam3127/ipmg/pull/84),
  [`3f33acc`](https://github.com/sameeralam3127/ipmg/commit/3f33acccd07eeacdd4e168aa4900bb75525b52e6))

### Features

- **cli**: Accept a file and extra targets together in one scan
  ([#84](https://github.com/sameeralam3127/ipmg/pull/84),
  [`3f33acc`](https://github.com/sameeralam3127/ipmg/commit/3f33acccd07eeacdd4e168aa4900bb75525b52e6))

- **cli**: Accept JSON target files with --input
  ([#84](https://github.com/sameeralam3127/ipmg/pull/84),
  [`3f33acc`](https://github.com/sameeralam3127/ipmg/commit/3f33acccd07eeacdd4e168aa4900bb75525b52e6))

### Testing

- **json**: Compare the error text with rich's line wrapping undone
  ([#84](https://github.com/sameeralam3127/ipmg/pull/84),
  [`3f33acc`](https://github.com/sameeralam3127/ipmg/commit/3f33acccd07eeacdd4e168aa4900bb75525b52e6))


## v2.3.0 (2026-09-27)

### Bug Fixes

- **notify**: Pass lint, and catch errors building a message
  ([#85](https://github.com/sameeralam3127/ipmg/pull/85),
  [`da87756`](https://github.com/sameeralam3127/ipmg/commit/da87756e226e960ccd375f52a696f398bcef24d3))

- **notify**: Refuse non-http URLs in post_json and pass bandit
  ([#85](https://github.com/sameeralam3127/ipmg/pull/85),
  [`da87756`](https://github.com/sameeralam3127/ipmg/commit/da87756e226e960ccd375f52a696f398bcef24d3))

### Continuous Integration

- Bump the actions group with 3 updates ([#81](https://github.com/sameeralam3127/ipmg/pull/81),
  [`137a504`](https://github.com/sameeralam3127/ipmg/commit/137a504f98895e295909f60e0c9b84566f223092))

### Documentation

- Move community health files into .github ([#83](https://github.com/sameeralam3127/ipmg/pull/83),
  [`4b5e9b6`](https://github.com/sameeralam3127/ipmg/commit/4b5e9b65a8ae5232bd128e1ece58519d28395ab2))

### Features

- **notify**: Send change reports to a webhook, Slack, Teams, and email
  ([#85](https://github.com/sameeralam3127/ipmg/pull/85),
  [`da87756`](https://github.com/sameeralam3127/ipmg/commit/da87756e226e960ccd375f52a696f398bcef24d3))

- **scan**: Exit non-zero when hosts are down, for cron and monitoring
  ([#82](https://github.com/sameeralam3127/ipmg/pull/82),
  [`1cf21dc`](https://github.com/sameeralam3127/ipmg/commit/1cf21dc482877fc688822e66b3898cc97c436a4e))

- **web**: Stabilize and document the /api/v1 REST API
  ([#87](https://github.com/sameeralam3127/ipmg/pull/87),
  [`f861b2c`](https://github.com/sameeralam3127/ipmg/commit/f861b2c7cad0a1e4ecc4fef9da8734b482c393db))

### Refactoring

- **scan**: Define HostsDownError next to the health check
  ([#82](https://github.com/sameeralam3127/ipmg/pull/82),
  [`1cf21dc`](https://github.com/sameeralam3127/ipmg/commit/1cf21dc482877fc688822e66b3898cc97c436a4e))

- **scan**: Report hosts down with an exception, keeping run_scan's signature
  ([#82](https://github.com/sameeralam3127/ipmg/pull/82),
  [`1cf21dc`](https://github.com/sameeralam3127/ipmg/commit/1cf21dc482877fc688822e66b3898cc97c436a4e))

- **scan**: Sort down hosts with the shared ip_sort_key
  ([#82](https://github.com/sameeralam3127/ipmg/pull/82),
  [`1cf21dc`](https://github.com/sameeralam3127/ipmg/commit/1cf21dc482877fc688822e66b3898cc97c436a4e))


## v2.2.0 (2026-09-23)

### Features

- **reports**: Resume an interrupted scan from its partial report
  ([#80](https://github.com/sameeralam3127/ipmg/pull/80),
  [`2442ac0`](https://github.com/sameeralam3127/ipmg/commit/2442ac0fe5149961efe869baae5d21c2321d7c09))


## v2.1.1 (2026-09-19)

### Bug Fixes

- **web**: Keep the access token out of URLs, and bound port-probe threads
  ([#78](https://github.com/sameeralam3127/ipmg/pull/78),
  [`4dc1347`](https://github.com/sameeralam3127/ipmg/commit/4dc134739efc20e530366c92f531dedb16273929))

- **web**: Rename the WebSocket auth prefix constant to satisfy bandit B105
  ([#78](https://github.com/sameeralam3127/ipmg/pull/78),
  [`4dc1347`](https://github.com/sameeralam3127/ipmg/commit/4dc134739efc20e530366c92f531dedb16273929))

- **web**: Require an access token for IPMG Web, bound live-update buffers, and parallelize reverse
  DNS ([#78](https://github.com/sameeralam3127/ipmg/pull/78),
  [`4dc1347`](https://github.com/sameeralam3127/ipmg/commit/4dc134739efc20e530366c92f531dedb16273929))

- **web**: Require an access token, bound live-update buffers, and parallelize reverse DNS
  ([#78](https://github.com/sameeralam3127/ipmg/pull/78),
  [`4dc1347`](https://github.com/sameeralam3127/ipmg/commit/4dc134739efc20e530366c92f531dedb16273929))

### Continuous Integration

- Add tox for running the CI checks locally, drop the Codecov upload
  ([#77](https://github.com/sameeralam3127/ipmg/pull/77),
  [`095785f`](https://github.com/sameeralam3127/ipmg/commit/095785f656d97f8abf8bea18c786a33491f0ff2d))


## v2.1.0 (2026-09-19)

### Bug Fixes

- Restore Python 3.9 support and add lint, lowest-deps, coverage, and PR-title checks
  ([#76](https://github.com/sameeralam3127/ipmg/pull/76),
  [`aa09162`](https://github.com/sameeralam3127/ipmg/commit/aa091623b0b1b711e23c695ba5311fcb19263f05))

### Documentation

- **readme**: Open with a demo GIF and a comparison to nmap, fping, and Angry IP Scanner
  ([#74](https://github.com/sameeralam3127/ipmg/pull/74),
  [`b8232f0`](https://github.com/sameeralam3127/ipmg/commit/b8232f06bb85e72254a81cab6f6ec1f8a1bbb9bd))

- **readme**: Point to the command builder, with a screenshot
  ([#75](https://github.com/sameeralam3127/ipmg/pull/75),
  [`1c76265`](https://github.com/sameeralam3127/ipmg/commit/1c76265feeb124d4ae494069d4cb1b5e85ef8014))

### Features

- **reports**: Write scan reports while the scan runs
  ([#71](https://github.com/sameeralam3127/ipmg/pull/71),
  [`19629de`](https://github.com/sameeralam3127/ipmg/commit/19629de9913e7f1e8b31a490a9f901927738a3ac))


## v2.0.0 (2026-09-17)

### Documentation

- Document the Homebrew tap install ([#69](https://github.com/sameeralam3127/ipmg/pull/69),
  [`fd21a04`](https://github.com/sameeralam3127/ipmg/commit/fd21a04d382c753d704fe312dfebf8a8baa883e1))

- **site**: Always show the latest version, with calendar-day dates
  ([#58](https://github.com/sameeralam3127/ipmg/pull/58),
  [`228de1f`](https://github.com/sameeralam3127/ipmg/commit/228de1fc4f8be661ce66ded0b1332055b0bc1175))

### Features

- **cli**: Rename the dashboard to IPMG Web ([#70](https://github.com/sameeralam3127/ipmg/pull/70),
  [`f6d73cd`](https://github.com/sameeralam3127/ipmg/commit/f6d73cde5bea3c562e3169787a48b63cb25abb8c))

### Breaking Changes

- **cli**: `ipmg dashboard` no longer exists; use `ipmg web`.


## v1.13.2 (2026-09-11)

### Bug Fixes

- **cli**: Report a missing input file instead of scanning sample hosts
  ([#57](https://github.com/sameeralam3127/ipmg/pull/57),
  [`717f0d4`](https://github.com/sameeralam3127/ipmg/commit/717f0d4f49da5a8be4c976ceef898eeab1cdc0f6))

### Chores

- Remove redundant tooling config and legacy import shims
  ([#54](https://github.com/sameeralam3127/ipmg/pull/54),
  [`26763fa`](https://github.com/sameeralam3127/ipmg/commit/26763fa3fd4606e4e6a6bc88d6220ad27c4a1032))

### Continuous Integration

- Bump the actions group across 1 directory with 7 updates
  ([#53](https://github.com/sameeralam3127/ipmg/pull/53),
  [`3cb98da`](https://github.com/sameeralam3127/ipmg/commit/3cb98da641f59221a16064eb7ba150ef95f28969))

- Harden workflows for a public repository ([#52](https://github.com/sameeralam3127/ipmg/pull/52),
  [`9419bee`](https://github.com/sameeralam3127/ipmg/commit/9419beea41b5f68e6cd4acbe0c8722c0abcf20c6))

### Documentation

- Add a command reference and cover every command in the site builder
  ([#56](https://github.com/sameeralam3127/ipmg/pull/56),
  [`0e39bfd`](https://github.com/sameeralam3127/ipmg/commit/0e39bfd5c0d31c2ffdff80cf5074a670e1abdbb6))

- Add contributing guide and code of conduct, split README help docs
  ([#55](https://github.com/sameeralam3127/ipmg/pull/55),
  [`279c6e0`](https://github.com/sameeralam3127/ipmg/commit/279c6e003909091e38706c8b39af749f05b5442d))

- Describe the missing-input-file fix and correct a builder warning
  ([#56](https://github.com/sameeralam3127/ipmg/pull/56),
  [`0e39bfd`](https://github.com/sameeralam3127/ipmg/commit/0e39bfd5c0d31c2ffdff80cf5074a670e1abdbb6))

- **site**: Add a project website and serve the dashboard demo at /demo
  ([#54](https://github.com/sameeralam3127/ipmg/pull/54),
  [`26763fa`](https://github.com/sameeralam3127/ipmg/commit/26763fa3fd4606e4e6a6bc88d6220ad27c4a1032))

- **site**: Project website, dashboard demo at /demo, and cleanup
  ([#54](https://github.com/sameeralam3127/ipmg/pull/54),
  [`26763fa`](https://github.com/sameeralam3127/ipmg/commit/26763fa3fd4606e4e6a6bc88d6220ad27c4a1032))


## v1.13.1 (2026-09-10)

### Bug Fixes

- **install**: Make installation work on every supported OS and Python
  ([#30](https://github.com/sameeralam3127/ipmg/pull/30),
  [`1c653fc`](https://github.com/sameeralam3127/ipmg/commit/1c653fc21a1eeb318b0b1cb879c4700a0f2ed7d6))


## v1.13.0 (2026-09-10)

### Features

- **cli**: Stream scan results as each host finishes
  ([#29](https://github.com/sameeralam3127/ipmg/pull/29),
  [`0f57dfa`](https://github.com/sameeralam3127/ipmg/commit/0f57dfaa189b5317e40c49bacf25ccbd4e3137be))


## v1.12.2 (2026-09-09)

### Bug Fixes

- **security**: Neutralize spreadsheet formulas in exported reports
  ([#28](https://github.com/sameeralam3127/ipmg/pull/28),
  [`578553a`](https://github.com/sameeralam3127/ipmg/commit/578553ad89e06d076640d12b642450a34d6db785))


## v1.12.1 (2026-08-22)

### Bug Fixes

- **dashboard**: Open local dashboard on New Scan, not the marketing landing page
  ([#27](https://github.com/sameeralam3127/ipmg/pull/27),
  [`0734d6c`](https://github.com/sameeralam3127/ipmg/commit/0734d6c2d0a4a40dfe3c87f62bb283e259335709))


## v1.12.0 (2026-08-22)

### Bug Fixes

- **dashboard**: Skip browser launch and hint remote access on headless servers
  ([#26](https://github.com/sameeralam3127/ipmg/pull/26),
  [`5fa24f7`](https://github.com/sameeralam3127/ipmg/commit/5fa24f714d94947b318af22604743b6968702253))

- **install**: Always install from PyPI and harden edge cases
  ([#26](https://github.com/sameeralam3127/ipmg/pull/26),
  [`5fa24f7`](https://github.com/sameeralam3127/ipmg/commit/5fa24f714d94947b318af22604743b6968702253))

### Documentation

- **security**: Update supported version and note known issues
  ([`8f503f6`](https://github.com/sameeralam3127/ipmg/commit/8f503f61139b04c92fa8daa78d513a49ec566d9d))

### Features

- Add optional TCP service discovery after ICMP
  ([#26](https://github.com/sameeralam3127/ipmg/pull/26),
  [`5fa24f7`](https://github.com/sameeralam3127/ipmg/commit/5fa24f714d94947b318af22604743b6968702253))


## v1.11.0 (2026-08-07)

### Features

- Add public IPMG landing page
  ([`68e9a1c`](https://github.com/sameeralam3127/ipmg/commit/68e9a1ce98749889e264996ed635b64ed2c9fec2))


## v1.10.0 (2026-08-07)

### Bug Fixes

- Version dashboard assets for Pages
  ([`2615fb9`](https://github.com/sameeralam3127/ipmg/commit/2615fb927dcebcf054155fdb9503a40ae0c09ad2))

### Features

- Add project details page
  ([`8880733`](https://github.com/sameeralam3127/ipmg/commit/88807334950ffb2b6b0816d4d1c2f5327661827a))


## v1.9.0 (2026-08-07)

### Bug Fixes

- Enable GitHub Pages deployment
  ([`5de52ca`](https://github.com/sameeralam3127/ipmg/commit/5de52cabad5ca8a7bd14d86d95b9b5fb5c8de2ae))

### Features

- Add GitHub Pages dashboard demo
  ([`cf7fd21`](https://github.com/sameeralam3127/ipmg/commit/cf7fd21074fe437737a6e0d336fca136d27f4cc9))


## v1.8.1 (2026-07-29)

### Bug Fixes

- **security**: Harden dashboard and target parsing, remove dead code
  ([`e6d36f2`](https://github.com/sameeralam3127/ipmg/commit/e6d36f20c1c4c78f5c7b59a8e8d980794436298e))

### Documentation

- Add security section to README and fill in SECURITY.md
  ([`78a689b`](https://github.com/sameeralam3127/ipmg/commit/78a689b68ecbf52980684c37e38032e482f1b87c))


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
