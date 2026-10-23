# Contributing

This is a local browser for a Serato DJ Pro library. The server binds `127.0.0.1` and has no login. Changes stay in this repository. They do not add a hosted copy of the server.

## Before you start

Quit Serato DJ Pro before a write against a live library. The tests never open that library. Do not commit `master.sqlite`, `root.sqlite`, a backup of either file, or an audio file. Do not attach those files to an issue or a pull request. Cue points live in the audio file.

## Checks

From the repository root:

```bash
python3 -m unittest discover -s tests -t . -v
```

GitHub Actions runs the same discovery with `python` on Ubuntu (3.12 and 3.14) and Windows (3.12). [docs/github.md](docs/github.md) lists the workflows, the release tags, and the checks to require after they have gone green once.

A desktop build uses `requirements-build.txt` and `python -m PyInstaller serato-library.spec`. Release builds are unsigned.

## What to update

- `docs/architecture.md` when behavior, the API, the layout, or the run path changes.
- `CLAUDE.md` when the run command or the layout summary changes.
- `docs/github.md` when a workflow, a release check, or a GitHub setting changes.
- `SECURITY.md` when the threat notes or the attestation commands change.

The pull request template asks for the same list. There is no separate linter. The suite is `unittest`.

## Reports

Use the bug or feature template. For a vulnerability, open a [private advisory](https://github.com/mookiejones/serato-library-manager/security/advisories/new) instead of a public issue.
