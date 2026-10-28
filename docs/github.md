# GitHub

This repository is a local program. `server.py` binds `127.0.0.1` port `8765` and has no login. GitHub Actions builds and tests that program. It does not host the library server. GitHub Pages hosts the user guide only, as a static site built from `docs/`. Do not publish the port or put the process behind a tunnel.

The HTTP banner in `server.py` is `SeratoLibrary/1.0`. A release tag does not change that string.

## Workflows

| Workflow | When it runs | What it does |
|----------|----------------|--------------|
| CI | Push to `main`, and every pull request | Tests, then audits the requirements files |
| CodeQL | Push to `main`, and every pull request | Analyzes the Python source. There is no autobuild |
| Dependency review | Pull requests only | Reviews dependency changes. It does not comment on the pull request |
| Release | Tag `v*.*.*`, or a manual run | Builds the macOS disk images, the Windows installer, and the portable zip. A tag also publishes a GitHub Release |
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

The Windows test job runs `python scripts/release_bundle.py check-tag` with `shell: bash` and `RELEASE_TAG` set to `v0.0.0`. No tag is passed on the command line. That is the same environment path the release job uses, and it runs on `windows-latest` for every pull request. `v0.0.0` is not a published release.

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

GitHub Releases is the only download. The workflow does not publish a Homebrew formula, a winget package, or a website.

`macos-latest` builds `Serato-Library-macos-arm64.dmg`. That runner is Apple silicon. `macos-15-intel` builds `Serato-Library-macos-x64.dmg`. PyInstaller does not produce a reliable universal binary from one Python install, so the two architectures are separate disk images. `macos-15-intel` is the GitHub-hosted Intel image and is scheduled to remain available through August 2027. `windows-latest` builds `Serato-Library-windows-setup.exe` with Inno Setup 6.7.3 and `Serato-Library-windows.zip`, the portable folder. The builds use Python 3.12, `requirements-build.txt` (`pillow==13.0.0`, `pystray==0.19.5`, `sentry-sdk==2.73.0`, `posthog==7.75.11`, and `pyinstaller==6.22.3`), and, on macOS, `requirements-macos.txt` (`pyobjc-framework-Cocoa==12.2.2` and `pyobjc-framework-Quartz==12.2.2`). Source tests also cover Python 3.14. The frozen app embeds 3.12 only.

Sharing stays off until the person opts in. The first page opens with **Don't share** selected. Closing that dialog, or pressing Esc, saves that decline. A missing key keeps that service off even after opt-in.

On a tag push, and only then, `python scripts/write_build_config.py` writes `_build_config.py` from the `SENTRY_DSN`, `POSTHOG_KEY`, and `POSTHOG_HOST` Actions secrets before PyInstaller runs. The step's condition is `github.event_name == 'push'` and a `refs/tags/v` ref. A `workflow_dispatch` run skips the step, so a manual build keeps the empty file that is committed and embeds no keys. The step prints whether each value was set. It does not print the value. A missing or empty secret writes an empty string, and that service stays off in the build. Forks do not receive these secrets. When a tag build does have keys, they are client keys inside the unsigned build. The copy of `_build_config.py` in git stays empty. A build from source uses that empty file. An environment variable of the same name overrides the baked file when someone runs from source. [PRIVACY.md](../PRIVACY.md) describes what a build with keys can send, and that sending stays off until the person opts in.

The tag filter `v*.*.*` is a glob. `scripts/release_bundle.py check-tag` accepts `vMAJOR.MINOR.PATCH`, `vMAJOR.MINOR.PATCH-rcN`, and `vMAJOR.MINOR.PATCH-betaN`. `N` is one or more digits. `v1.2`, `1.2.3`, `v1.2.3-rc.1`, `v1.2.3-rc`, and `refs/tags/v1.2.3` are refused. The release job passes the tag in `RELEASE_TAG`, set by the Actions `env:` map from `github.ref_name`, and the step sets `shell: bash`. It does not expand `GITHUB_REF_NAME` in the shell. Run 40214779889 failed on Windows because PowerShell expanded that shell form to an empty string. The Windows CI job sets `RELEASE_TAG` and runs `check-tag` with no argument, under bash, so that path is not limited to a tag push.

A final tag is published with `gh release create --latest`. An `-rcN` or `-betaN` tag is published with `--prerelease --latest=false`. `scripts/release_bundle.py release-flags` prints those flags. The publish job runs only when the event is `push` and the ref is a tag. `workflow_dispatch` builds and uploads artifacts and does not publish, including when the selected ref is a tag. A `pull_request` cannot publish either: the publish condition requires `push`.

A pull request runs the three `build` legs when it changes `packaging/`, `serato-library.spec`, `scripts/release_*`, or `.github/workflows/release.yml`. Each leg builds, smoke-tests, and uploads its artifact. The token for that job is `contents: read` only. `actions/upload-artifact` does not need `actions: write`. The job does not attest or publish. A step with no secrets runs `scripts/release_sign.py`, which prints `Signing skipped` and exits 0. The telemetry bake is not in that job, so the build keeps the empty `_build_config.py` from git. Sharing stays off until the person opts in, and a build from a pull request or from source has no keys to send.

Signing is a dormant hook in `scripts/release_sign.py`. The macOS step runs when `runner.os` is `macOS` and receives only `APPLE_CERTIFICATE_P12_BASE64`, `APPLE_CERTIFICATE_PASSWORD`, `APPLE_SIGNING_IDENTITY`, `APPLE_NOTARY_KEY_BASE64`, `APPLE_NOTARY_KEY_ID`, and `APPLE_NOTARY_ISSUER_ID`. The Windows app step runs when `runner.os` is `Windows` and receives only `WINDOWS_CERTIFICATE_PFX_BASE64` and `WINDOWS_CERTIFICATE_PASSWORD`. The installer step on Windows receives those same two Windows secrets. Those secrets are not configured. When every secret for that step is empty, the step prints `Signing skipped` and exits 0. When some are set and some are not, the step fails. The script does not print secret values. The Inno Setup script does not call SignTool.

On a tag push, each build job checks the tag, installs the build file, bakes `_build_config.py`, runs `python -m PyInstaller serato-library.spec`, checks the frozen architecture, runs the signing step for that OS, then packs. A manual run does the same work and skips the bake, so the frozen app has no telemetry keys. A macOS job runs `pack-dmg`, which writes a UDZO disk image containing `Serato Library.app` and an Applications link, mounts that image, copies the app outside the repository, and launches it with `SERATO_LIBRARY_SMOKE`. A Windows job runs `pack` for the portable zip, installs Inno Setup 6.7.3 after checking its SHA-256, compiles the installer, runs the signing hook on the installer, then installs it into a temporary directory and launches that copy. The smoke path binds `127.0.0.1` on a free port, writes the URL and a shutdown token to the marker, and does not open the library, a browser, a menu icon, or telemetry. The harness GET `/api/health` and POST `/api/shutdown` with the token. The launch environment keeps `PATH` and the operating-system variables the process needs. `HOME`, `USERPROFILE`, `LOCALAPPDATA`, and `APPDATA` are empty. `PYTHONPATH` is not passed through. A failure deletes the file the command was writing.

The pull-request `build` job only has `contents: read`. It builds, smoke-tests, and uploads the disk images, the portable zip, and the Windows installer. `release-build` runs on a tag push or a manual run and uploads the same files for the later jobs. `attest build provenance` downloads those artifacts and runs only on a tag push or a manual run. Its permissions are `contents: read`, `actions: read`, `id-token: write`, and `attestations: write`. A pull request never starts `release-build`, `attest`, or `publish`.

`publish GitHub release` runs only when the ref is `refs/tags/v…`. It downloads the four files, runs `check-binaries`, and runs `gh attestation verify` for each file against this repository. It does not launch any app. A Linux runner cannot mount the disk image or start the Windows executable. `check-binaries` checks the zip contents, the UDIF trailer, and the installer PE header. The job then writes `SHA256SUMS`, checks it, attests it, and verifies that attestation. It refuses to continue if that release already exists. Otherwise it creates the release with `gh release create --generate-notes --verify-tag` and appends `scripts/release-notes-footer.md`. The attached files are the two disk images, the installer, the portable zip, and `SHA256SUMS`. Its permissions are `contents: write`, `id-token: write`, and `attestations: write`.

A manual run of the Release workflow (`workflow_dispatch`) builds and attests the files and uploads them as artifacts. It does not publish a release. The publish job's condition requires `github.event_name == 'push'` as well as a `refs/tags/v` ref, so choosing a tag in the manual run still does not publish.

The size checks refuse a bundle under 8 MiB or over 250 MiB, and a zip, disk image, or installer under 4 MiB or over 180 MiB. The floor exists to catch a bundle that never collected the Python runtime. It is not a measurement of a healthy build. Page files are compared by content, which is the check that catches a missing stylesheet or script. After a real build, raise the floor so a healthy bundle is several times that number.

`pack` also refuses a zip that would overwrite an existing file, a symlink that leaves the bundle, an absolute link, a `..` entry, a zip-slip path, and an empty, newline, or NUL name. The macOS executable must be marked executable. The release names are `Serato-Library-macos-arm64.dmg`, `Serato-Library-macos-x64.dmg`, `Serato-Library-windows-setup.exe`, `Serato-Library-windows.zip`, and `SHA256SUMS`.

## What a download is

The builds are unsigned. macOS Gatekeeper and Windows SmartScreen warn before the app opens. The steps, including Removable Volumes on a Mac, are in [First install](first-install.md).

Confirm a download before you open it:

```bash
gh attestation verify Serato-Library-macos-arm64.dmg --repo mookiejones/serato-library-manager
gh attestation verify Serato-Library-macos-x64.dmg --repo mookiejones/serato-library-manager
gh attestation verify Serato-Library-windows-setup.exe --repo mookiejones/serato-library-manager
gh attestation verify Serato-Library-windows.zip --repo mookiejones/serato-library-manager
gh attestation verify SHA256SUMS --repo mookiejones/serato-library-manager
```

Quit Serato DJ Pro before you edit the library. The page is served on `127.0.0.1` only. The release does not contain a library.

## Cut a release

Create the tag locally and push that tag. The workflow creates the GitHub Release. It does not create the tag.

```bash
git tag -a v1.0.0 -m "Release v1.0.0."
git push origin v1.0.0
```

Use the next `vMAJOR.MINOR.PATCH` tag. Push the tag only when `main` is the commit you want to ship.

To build without publishing, open Actions, choose Release, and run the workflow. Download the artifacts from that run. Those files are the same shape as a release, and they carry attestations, but they are not attached to a GitHub Release. `SHA256SUMS` is written by the publish job, so a manual run has the disk images, the installer, and the zip, and does not have the checksum file.

## User guide

The guide source is `docs/index.md`, `docs/first-install.md`, `docs/guide/`, `docs/coming-from-rekordbox.md`, and `docs/media/`. `docs/mkdocs.yml` is the site config. `docs/requirements-docs.txt` pins MkDocs. Developer pages (`architecture.md`, `github.md`, `related-tracks.md`, `serato-library-tools.md`) stay in `docs/` and are excluded from the site build. The site nav links to them on GitHub under **For developers**.

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
