## What and why

<!-- What this changes, and the problem it solves. -->

Closes #

## How it was tested

<!-- Commands run, and anything checked by hand (a scan, IPMG Web in a browser). -->

## Checklist

- [ ] The title is a [Conventional Commit](https://github.com/sameeralam3127/ipmg/blob/main/.github/CONTRIBUTING.md#commit-messages) (`feat:`, `fix:`, `docs:`, ...); it decides the release.
- [ ] Nothing here is a breaking change (`!` or `BREAKING CHANGE`): those go to the `v4` branch until v4.0.0 ships.
- [ ] Tests cover the change, and `pytest` passes.
- [ ] `pre-commit run --all-files` passes.
- [ ] User-facing changes are documented (README, docs/COMMANDS.md, docs/API.md).
- [ ] An `/api/v1` change is additive, and `tests/snapshots/api_v1_contract.json` is updated.
