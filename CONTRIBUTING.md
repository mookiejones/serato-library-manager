# Contributing

This is a local browser for a Serato DJ Pro library. The server binds `127.0.0.1` and has no login. Changes stay in this repository. They do not add a hosted copy of the server.

<picture>
  <source media="(prefers-color-scheme: dark)" type="image/svg+xml" srcset="docs/images/contribution-flow-dark.svg">
  <source media="(prefers-color-scheme: dark)" type="image/png" srcset="docs/images/contribution-flow-dark.png">
  <source type="image/svg+xml" srcset="docs/images/contribution-flow-light.svg">
  <img alt="Branch or fork, pull request, CI green on Ubuntu and Windows, Gatekeeper QA review, Principal Developer review and merge. Docs are updated in the same PR; unmerged work is labelled PREVIEW." src="docs/images/contribution-flow-light.png" width="100%">
</picture>

## Merge flow

1. Branch or fork.
2. Open a pull request. Code and the docs that describe it go in that same pull request.
3. Wait until CI is green, including Windows. The checks live in [`.github/workflows/ci.yml`](.github/workflows/ci.yml), [`.github/workflows/codeql.yml`](.github/workflows/codeql.yml), and [`.github/workflows/dependency-review.yml`](.github/workflows/dependency-review.yml):
   - `tests (ubuntu-latest, Python 3.12)`
   - `tests (ubuntu-latest, Python 3.14)`
   - `tests (windows-latest, Python 3.12)`
   - `dependency audit`
   - `analyze Python`
   - `review dependency changes` (pull requests)
4. Gatekeeper QA reviews the pull request.
5. The Principal Developer reviews and merges. [`.github/CODEOWNERS`](.github/CODEOWNERS) names `@mookiejones` for the whole tree.

Label work that is not merged **PREVIEW**. Do not describe it as shipped.

## Before you start

Quit Serato DJ Pro before a write against a live library. The tests never open that library. Do not commit `master.sqlite`, `root.sqlite`, a backup of either file, or an audio file. Do not attach those files to an issue or a pull request. Cue points live in the audio file.

## Dev setup

Python 3.12 or 3.14. The frozen app embeds 3.12.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python desktop.py
```

`desktop.py` starts the local server, opens the default browser, and shows a menu-bar item on macOS or a tray icon on Windows. It does not embed a web view. On Windows, use `.venv\Scripts\python`. On macOS, also install `requirements-macos.txt`.

`python3 server.py` serves `http://127.0.0.1:8765`. Press F5 in VS Code to run that launch.

Page color and type tokens are in `static/tokens.css`. The page script is plain JavaScript in `static/app.js`. [Issue #59](https://github.com/mookiejones/serato-library-manager/issues/59) is the move to strict TypeScript. It is not merged. Until it lands, keep browser changes in `static/app.js`.

## Checks

From the repository root:

```bash
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -t . -v
```

The install step is required because the suite imports `sentry-sdk` and `posthog`. Sharing stays off without a key and without consent. Do not commit a DSN, a PostHog project key, or a filled-in `_build_config.py`.

GitHub Actions runs the same discovery with `python` on Ubuntu (3.12 and 3.14) and Windows (3.12). The Windows job also runs `python scripts/release_bundle.py check-tag` with `shell: bash` and `RELEASE_TAG` set to `v0.0.0`. [docs/github.md](docs/github.md) lists the workflows.

A desktop build uses `requirements-build.txt` and `python -m PyInstaller serato-library.spec`. On macOS, `requirements-macos.txt` supplies the menu-bar frameworks. Release builds are unsigned. GitHub Releases is the only download. Signing runs only when the Apple or Windows secrets in `scripts/release_sign.py` are all set.

There is no separate linter. The suite is `unittest`.

## What to update in the same pull request

- `docs/architecture.md` when behavior, the API, the layout, or the run path changes.
- `CLAUDE.md` when the run command or the layout summary changes.
- `docs/github.md` when a workflow, a release check, or a GitHub setting changes.
- `docs/index.md` and `docs/guide/` when a DJ can see the change.
- `SECURITY.md` when the threat notes or the attestation commands change.
- `PRIVACY.md` and the README when sharing, local logs, or telemetry keys change.

The pull request template asks for the same list.

## Reports

Use the bug or feature template. For a vulnerability, open a [private advisory](https://github.com/mookiejones/serato-library-manager/security/advisories/new) instead of a public issue. Private vulnerability reporting is enabled for this repository.
