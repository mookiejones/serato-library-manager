---
name: managing-python-releases
description: Ships this app with semantic version tags and GitHub Releases. Use when cutting a release, writing the release notes, or changing release.yml. There is no PyPI package and no CHANGELOG.
---

# Releases

GitHub Releases is the only download. A tag push builds the macOS disk images, the Windows installer, and the portable zip, attests them, and publishes the release. The workflow does not publish to PyPI, Homebrew, or winget. There is no `CHANGELOG.md` and no deprecation cycle for a library API.

`docs/github.md` is the runbook. This skill is the version and notes contract. If you change `.github/workflows/release.yml` or `scripts/release_bundle.py`, update `docs/github.md` in the same change.

## Semantic versions

`scripts/release_bundle.py check_tag` accepts three shapes. `N` is one or more digits.

| Tag | Published as |
| --- | --- |
| `vMAJOR.MINOR.PATCH` | Latest release (`--latest`) |
| `vMAJOR.MINOR.PATCH-rcN` | Prerelease (`--prerelease --latest=false`) |
| `vMAJOR.MINOR.PATCH-betaN` | Prerelease (`--prerelease --latest=false`) |

`release-flags` prints those `gh` flags. A final tag is the download. A prerelease is not marked latest.

Refused: `v1.2`, `1.2.3`, `v1.2.3-rc.1`, `v1.2.3-rc`, and `refs/tags/v1.2.3`.

Use the numbers the way semver does:

- PATCH: a fix, same behavior aside from the bug.
- MINOR: a feature the current page and library still accept.
- MAJOR: a change that breaks an existing library, a saved `settings.json`, or a snapshot a person already has.

The HTTP banner in `server.py` is `SeratoLibrary/1.0`. A release tag does not change that string. Do not bump a `__version__` in a package, and do not add `pyproject.toml` to carry a version.

## GitHub Releases

Create the tag locally and push that tag. The workflow creates the release. It does not create the tag.

```bash
git tag -a v1.2.3 -m "Release v1.2.3."
git push origin v1.2.3
```

Push the tag only when `main` is the commit you want to ship. Never push a tag or publish a release, including a prerelease, without Charles (@mookiejones)'s explicit OK.

What the workflow does:

- A tag matching `v*.*.*` runs the release jobs. The tag filter is a glob; `check-tag` is the real check. The Windows CI job runs `check-tag` with `RELEASE_TAG=v0.0.0` under bash so that path stays covered. `v0.0.0` is not a published release.
- `workflow_dispatch` builds and attests the files and uploads artifacts. It does not publish, even if the selected ref is a tag.
- A pull request that changes packaging files builds the artifacts and does not publish.
- The publish job runs only on `push` of `refs/tags/v…`. It refuses if the release already exists. It does not launch the apps. It attaches `Serato-Library-macos-arm64.dmg`, `Serato-Library-macos-x64.dmg`, `Serato-Library-windows-setup.exe`, `Serato-Library-windows.zip`, and `SHA256SUMS`.

The publish job's permissions are `contents: write` plus the attestation scopes. The pull-request build job stays `contents: read`.

## Release notes

Notes live on the GitHub Release, not in a changelog file.

The publish step runs `gh release create` with `--generate-notes`, `--title` set to the tag, and `--verify-tag`. It then appends `scripts/release-notes-footer.md` via `scripts/release_bundle.py footer`. The footer is the install table, the unsigned-build warning, the attestation commands, and the reminder that the release does not contain a library. `OWNER/REPO` in the template is replaced with the repository name.

Do not add `CHANGELOG.md` or a Keep a Changelog section as part of a release. Generated notes plus the footer are the notes. Edit the footer template when the install files or the verify commands change, and keep the `OWNER/REPO` placeholder so `footer` can fill it in.

## Checklist

```
Before the tag:
- [ ] python3 -m unittest discover -s tests -t . passes
- [ ] The tag matches vMAJOR.MINOR.PATCH or a -rcN / -betaN prerelease
- [ ] main is the commit being tagged
- [ ] docs/github.md still matches release.yml if the workflow changed

After publish:
- [ ] The release exists and was not replaced
- [ ] A final tag is latest; an rc or beta is a prerelease and is not latest
- [ ] The two disk images, the installer, the zip, and SHA256SUMS are attached
- [ ] gh attestation verify succeeds for each file
```
