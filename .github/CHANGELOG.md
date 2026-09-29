# CHANGELOG

<!-- version list -->

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
