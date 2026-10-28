# GitHub

This repository is a local program. `server.py` binds `127.0.0.1` port `8765` and has no login. GitHub Actions builds and tests that program. It does not host the library server. GitHub Pages hosts the user guide only, as a static site built from `docs/`. Do not publish the port or put the process behind a tunnel.

The HTTP banner in `server.py` is `SeratoLibrary/1.0`. A release tag does not change that string.

## Workflows

| Workflow | When it runs | What it does |
|----------|----------------|--------------|
| CI | Push to `main`, and every pull request | Tests, then audits the requirements files |
| CodeQL | Push to `main`, and every pull request | Analyzes the Python source. There is no autobuild |
| Dependency review | Pull requests only | Reviews dependency changes. It does not comment on the pull request |
| Release | Tag `v*.*.*`, or a manual run | Builds the desktop zips. A tag also publishes a GitHub Release |
| Pages | Push to `main` when `docs/` or `.github/workflows/pages.yml` changes, a pull request that changes those paths, or a manual run | Builds the user guide with MkDocs. A push to `main` also publishes it. A pull request builds the site and does not publish it |

A push to `main` runs CI and CodeQL once. When that push also changes `docs/` or the Pages workflow, Pages runs too. A pull request runs CI, CodeQL, and dependency review. A pull request that changes the guide also builds the site. The two events do not both fire for the same commit on a feature branch, because CI, CodeQL, and Pages listen to `push` only on `main`.

Each workflow sets `permissions: contents: read` and a `timeout-minutes` value. A job that needs more access sets its own permissions, which replace the workflow floor. CI, CodeQL, and dependency review cancel an older run on the same ref. The release workflow does not. The Pages workflow does not cancel an in-progress run, because a publish should finish. The Pages deploy job sets `contents: read`, `pages: write`, and `id-token: write`.

Actions are pinned to a commit SHA. The trailing comment is the version Dependabot matches. Dependabot opens a weekly Monday pull request for Python dependencies and another for GitHub Actions. Each group is one pull request, with a `deps` commit prefix, and at most five Python pull requests stay open.

### CI

The test job is a matrix:

- `tests (ubuntu-latest, Python 3.12)`
- `tests (ubuntu-latest, Python 3.14)`
- `tests (windows-latest, Python 3.12)`

There is no macOS test job. The suite mocks platform paths, and a macOS runner costs ten times a Linux minute. Windows stays in the matrix because the app ships a Windows build.

The test job installs `requirements.txt`, then runs the suite. The suite imports `sentry-sdk` and `posthog`. On your machine the commands are:

```bash
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -t . -v
```

Runners use `python -m pip install -r requirements.txt` and then `python` with the same unittest arguments. The suite builds a temporary database. It does not open the live Serato library. Settings and logs for the run stay in a temporary directory.

The `dependency audit` job installs `pip-audit==2.10.1` on Ubuntu with Python 3.12 and runs:

```bash
pip-audit --requirement requirements.txt --requirement requirements-build.txt --vulnerability-service osv
```

That audits the pinned files. It does not audit whatever else is installed on the runner.

### CodeQL

The job name is `analyze Python`. It runs on Ubuntu. The job permission is `contents: read` plus `security-events: write`. Code scanning uses this workflow. Do not also turn on the repository's default CodeQL setup, or the same code is scanned twice.

### Dependency review

The job name is `review dependency changes`. It needs only `contents: read`. A pull request from a fork can run this job, the test matrix, the dependency audit, and CodeQL. Fork pull requests do not run the release workflow, so they do not mint attestations or publish a release.

### Release

`macos-latest` builds `Serato-Library-macos.zip`. That runner is Apple Silicon, so the app is arm64. `windows-latest` builds `Serato-Library-windows.zip` for 64-bit Windows. The two builds use Python 3.12 and `requirements-build.txt` (`pywebview==6.2.1`, `sentry-sdk==2.73.0`, `posthog==7.75.11`, and `pyinstaller==6.22.3`). Source tests also cover Python 3.14. The frozen app embeds 3.12 only.

After the build tools are installed, and before PyInstaller runs, `python scripts/write_build_config.py` writes `_build_config.py` from the `SENTRY_DSN`, `POSTHOG_KEY`, and `POSTHOG_HOST` Actions secrets. The step prints whether each value was set. It does not print the value. A missing or empty secret writes an empty string, and that service stays off in the zip. Forks do not receive these secrets. The values are client keys and are inside the unsigned zip. The copy of `_build_config.py` in git stays empty. An environment variable of the same name overrides the baked file when someone runs from source. [PRIVACY.md](../PRIVACY.md) describes what a build with keys can send, and that sending stays off until the person opts in.

The tag filter `v*.*.*` is a glob. `scripts/release_bundle.py check-tag` accepts only `vMAJOR.MINOR.PATCH`. `v1.2`, `1.2.3`, and `v1.2.3-rc.1` are refused.

Windows runners default to PowerShell, which does not expand `${GITHUB_REF_NAME}`. Every `run` step that expands `${GITHUB_REF_NAME}` or `${GITHUB_REPOSITORY}`, and the publish script that redirects and globs, sets `shell: bash`. `pack` and `check-zips` are plain `python` commands. The archive is written with Python's `zipfile`, not a shell zip tool, so those steps stay on the runner's default shell.

On a tag push, each build job checks the tag, installs the build file, bakes `_build_config.py`, runs `python -m PyInstaller serato-library.spec`, then `python scripts/release_bundle.py pack`. `pack` checks the tree, zips it, unpacks that zip outside the repository, and launches the frozen executable with `SERATO_LIBRARY_SMOKE`. The smoke path writes `ok\n` and returns before a window, a port, the library, or telemetry. The launch environment keeps `PATH` and the operating-system variables the process needs. `HOME`, `USERPROFILE`, `LOCALAPPDATA`, and `APPDATA` are empty. `PYTHONPATH` is not passed through. A failure deletes the zip the command was writing.

The build job then attests the zip with `actions/attest` and uploads it. That job's permissions are `contents: read`, `id-token: write`, and `attestations: write`.

`publish GitHub release` runs only when the ref is `refs/tags/v…`. It downloads both zips, runs `check-zips`, and runs `gh attestation verify` for each zip against this repository. It does not launch either app. A Linux runner cannot start the macOS bundle, and it does not start the Windows executable either. The job then refuses to continue if that release already exists. Otherwise it creates the release with `gh release create --generate-notes --verify-tag` and appends `scripts/release-notes-footer.md`. Its permissions are `contents: write` and `attestations: read`.

A manual run of the Release workflow (`workflow_dispatch`) builds and attests the zips and uploads them as artifacts. It does not publish a release.

The size checks refuse a bundle under 8 MiB or over 250 MiB, and a zip under 4 MiB or over 180 MiB. The floor exists to catch a bundle that never collected the Python runtime. It is not a measurement of a healthy build. Page files are compared by content, which is the check that catches a missing stylesheet or script. After a real build, raise the floor so a healthy bundle is several times that number.

`pack` also refuses a zip that would overwrite an existing file, a symlink that leaves the bundle, an absolute link, a `..` entry, a zip-slip path, and an empty, newline, or NUL name. The macOS executable must be marked executable. The two expected names are `Serato-Library-macos.zip` and `Serato-Library-windows.zip`.

## What a download is

The builds are unsigned. macOS Gatekeeper and Windows SmartScreen warn before the app opens. On macOS, right-click the app and choose Open. On Windows, open `Serato Library.exe` from the unzipped folder.

Confirm a download before you open it:

```bash
gh attestation verify Serato-Library-macos.zip --repo mookiejones/serato-library-manager
gh attestation verify Serato-Library-windows.zip --repo mookiejones/serato-library-manager
```

Quit Serato DJ Pro before you edit the library. The window serves `127.0.0.1` only. The release does not contain a library.

## Cut a release

Create the tag locally and push that tag. The workflow creates the GitHub Release. It does not create the tag.

```bash
git tag -a v1.0.0 -m "Release v1.0.0."
git push origin v1.0.0
```

Use the next `vMAJOR.MINOR.PATCH` tag. Push the tag only when `main` is the commit you want to ship.

To build without publishing, open Actions, choose Release, and run the workflow. Download the artifacts from that run. Those zips are the same shape as a release, and they carry attestations, but they are not attached to a GitHub Release.

## User guide

The guide source is `docs/index.md`, `docs/guide/`, `docs/coming-from-rekordbox.md`, and `docs/media/`. `docs/mkdocs.yml` is the site config. `docs/requirements-docs.txt` pins MkDocs. Developer pages (`architecture.md`, `github.md`, `related-tracks.md`, `serato-library-tools.md`) stay in `docs/` and are excluded from the site build. The site nav links to them on GitHub under **For developers**.

The published URL is `https://mookiejones.github.io/serato-library-manager/`.

One repository setting is required before the first publish. Open Settings, then Pages, then Build and deployment. Set Source to **GitHub Actions**. A push to `main` that changes the guide then deploys the site. The workflow does not change that setting by itself.

The library server is still not on Pages. The site is the static guide.

## Repository settings

Secret scanning and push protection are on. Vulnerability alerts, Dependabot security updates, and private vulnerability reporting are on. Dependabot version updates are in `.github/dependabot.yml`. Private reports go to [the advisory form](https://github.com/mookiejones/serato-library-manager/security/advisories/new). Do not attach `master.sqlite`, `root.sqlite`, or audio.

The wiki stays as it is. Discussions stay off. Issues use the templates in `.github/ISSUE_TEMPLATE/`. Blank issues are closed off. `.github/CODEOWNERS` names `@mookiejones` for the whole tree.

## Branch protection

Wait until CI, CodeQL, and a pull-request dependency review have each completed once. Then require these checks on `main`:

- `tests (ubuntu-latest, Python 3.12)`
- `tests (ubuntu-latest, Python 3.14)`
- `tests (windows-latest, Python 3.12)`
- `dependency audit`
- `analyze Python`

Require `review dependency changes` on pull requests. That check does not run on a direct push, so it cannot be a required status for every update of `main`.

## Where a change has to land

A workflow, release, or GitHub setting change updates this file in the same commit. A change a DJ can see also updates the user guide under `docs/index.md` and `docs/guide/` in the same commit. Behavior, the API, the layout, or the run path also updates [architecture.md](architecture.md). The run command or the layout summary also updates `CLAUDE.md`. The README keeps the local test command and points here for Actions. `SECURITY.md` keeps the attestation commands and the rule that the server stays on `127.0.0.1`. `PRIVACY.md` keeps what sharing can send. The release footer in `scripts/release-notes-footer.md` is what GitHub appends to the generated notes.
