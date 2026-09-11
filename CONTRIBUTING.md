# Contributing to IPMG

Thanks for helping! This guide takes you from a fresh clone to a passing test
run, and explains the commit rules that drive releases.

By taking part you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
Found a security problem? Please report it privately as described in
[SECURITY.md](SECURITY.md) — not in a public issue.

**Contents**

[Ways to help](#ways-to-help) ·
[Set up](#set-up) ·
[Run the tests](#run-the-tests) ·
[Lint and format](#lint-and-format) ·
[Project layout](#project-layout) ·
[Commit messages](#commit-messages) ·
[Pull requests](#pull-requests) ·
[How releases happen](#how-releases-happen) ·
[Website and dashboard demo](#website-and-dashboard-demo)

---

## Ways to help

- **Report a bug or request a feature** in
  [issues](https://github.com/sameeralam3127/ipmg/issues). For bugs, include
  your OS, `ipmg --version`, the command you ran, and what you expected.
- **Pick up an issue.** Issues labelled
  [`good first issue`](https://github.com/sameeralam3127/ipmg/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22)
  are scoped for newcomers. Comment on one before starting so work isn't
  duplicated.
- **Improve the docs.** The [README](README.md), [FAQ](docs/FAQ.md), and
  [troubleshooting guide](docs/TROUBLESHOOTING.md) all welcome fixes.

---

## Set up

You need **Git** and **Python 3.9 or newer**. IPMG probes hosts with the
system `ping` command; macOS and Windows include it, and on minimal Linux
images you may need to install it (see
[the README](README.md#the-one-thing-ipmg-needs-from-your-system)).

```bash
# 1. Fork the repository on GitHub, then clone your fork
git clone https://github.com/<your-username>/ipmg.git
cd ipmg

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate        # Windows (PowerShell): .venv\Scripts\Activate.ps1

# 3. Install IPMG in editable mode with the development tools
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

Check the install worked:

```bash
ipmg --version
```

Editable mode means your changes to `src/ipmg` take effect immediately — no
reinstall needed.

---

## Run the tests

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q
```

On Windows PowerShell:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"; pytest -q
```

`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` stops pytest plugins installed elsewhere on
your machine from loading, so your run matches CI. The suite needs no network
access and takes a few seconds.

Run one file or one test while you work:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_diff.py -q
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q -k latency
```

CI also runs a quick end-to-end scan against your own machine. It is worth
running before you open a pull request:

```bash
ipmg --input 127.0.0.1 --no-history --formats csv --output smoke
```

CI runs the tests on Python 3.9–3.14 on Ubuntu, plus macOS and Windows, so you
don't need every version locally.

---

## Lint and format

The project uses [Ruff](https://docs.astral.sh/ruff/) for both linting and
formatting:

```bash
ruff check src tests          # lint (add --fix to apply safe fixes)
ruff format src tests         # format
```

To run Ruff and the secret scanner automatically on every commit, install the
pre-commit hooks once:

```bash
pre-commit install
```

The secret scan uses [detect-secrets](https://github.com/Yelp/detect-secrets)
with the committed `.secrets.baseline`. If it flags something that is not a
secret, it is fine to update the baseline in your pull request.

---

## Project layout

```text
src/ipmg/
  cli/             argument parsing and the `ipmg` command
  core/            ping, discovery, port scanning, change detection
  infrastructure/  SQLite history and file input/output
  reporting/       terminal output, live streaming, reports
  services/        scan and history orchestration
  web/             FastAPI dashboard; static/ holds its HTML, CSS, and JS
tests/             pytest suite (one file per module, roughly)
site/              project website published to GitHub Pages
install.sh         one-line installer for Linux and macOS
.github/workflows  CI: tests, security scan, release, Pages deploy
```

---

## Commit messages

Commits follow [Conventional Commits](https://www.conventionalcommits.org/).
This is not just style: the commit type decides whether merging to `main`
publishes a new version.

```text
<type>(<optional scope>): <short summary in the imperative>
```

| Type | Use it for | Release |
| --- | --- | --- |
| `feat` | a new user-facing capability | minor (`1.13.0` → `1.14.0`) |
| `fix` | a bug fix | patch (`1.13.0` → `1.13.1`) |
| `perf` | a performance improvement | patch |
| `docs` | documentation only | none |
| `test` | adding or fixing tests | none |
| `refactor` | code change with no behaviour change | none |
| `ci`, `build`, `chore`, `style` | tooling, dependencies, housekeeping | none |

A breaking change — adding `!` after the type (`feat!: ...`) or a
`BREAKING CHANGE:` footer — publishes a new **major** version. Please discuss
it in an issue first.

Examples:

```text
feat(cli): add --exclude to skip addresses in a range
fix(dashboard): keep the history filter after a page reload
docs: explain --latency-pct in the change detection section
```

---

## Pull requests

1. Create a branch from `main` (for example `fix/dashboard-history-filter`).
2. Keep the change focused; unrelated clean-ups belong in a separate pull
   request.
3. Add or update tests for behaviour you change, and update the README or docs
   if users will notice the change.
4. Make sure tests and `ruff check` pass locally.
5. Open the pull request against `main`, and link the issue it resolves
   (`Closes #123`).

**Use a Conventional Commit as the pull request title.** Pull requests are
squash-merged, so the title becomes the commit message on `main` and decides
the release (see above).

If this is your first contribution, CI will not start until a maintainer
approves the workflow run. That is a safety measure for every outside
contributor — it does not mean anything is wrong with your pull request.

---

## How releases happen

Releases are fully automated; you never bump a version by hand.

1. A pull request is squash-merged into `main`.
2. The **Publish** workflow runs the full test matrix.
3. [python-semantic-release](https://python-semantic-release.readthedocs.io/)
   reads the commits since the last tag. If any of them call for a release, it
   updates the version in `pyproject.toml` and `src/ipmg/__init__.py`, adds an
   entry to [CHANGELOG.md](CHANGELOG.md), and pushes a
   `chore(release): X.Y.Z` commit and a `vX.Y.Z` tag.
4. The package is built, attached to a GitHub release, and published to
   [PyPI](https://pypi.org/project/ipmg/) with trusted publishing — no API
   tokens are stored in the repository.

If none of the new commits are `feat`, `fix`, `perf`, or breaking, the run
ends with "No release will be made".

---

## Website and dashboard demo

The project website at
[sameeralam3127.github.io/ipmg](https://sameeralam3127.github.io/ipmg/) lives
in `site/`: a dependency-free static page with live release data, an install
guide, and an interactive command builder.

The dashboard demo is served beneath it at
[`/demo/`](https://sameeralam3127.github.io/ipmg/demo/). GitHub Pages cannot run
the Python scanner or access a local SQLite database, so the demo transparently
uses realistic seeded network inventory and scan history. Search, filters,
comparison, exports, theme switching, and a manual demo scan all work in the
browser. The local `ipmg dashboard` command always uses the real FastAPI API
and scan engine instead.

The **Deploy site to GitHub Pages** workflow publishes both after changes to
`site/` or `src/ipmg/web/static/` on `main`. No secrets are required; the
repository's Pages source is set to **GitHub Actions**.

To preview locally, assemble the same layout the workflow builds:

```bash
rm -rf _site && mkdir -p _site/demo
cp -R site/. _site/
cp -R src/ipmg/web/static/. _site/demo/
python3 -m http.server 4173 -d _site
# site: http://127.0.0.1:4173/   demo: http://127.0.0.1:4173/demo/?demo=1
```
