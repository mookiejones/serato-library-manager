# Security

The library browser is a local program. `server.py` binds `127.0.0.1` port `8765` and has no login. The desktop app binds `127.0.0.1` on a free port. Do not publish that port, put the process behind a tunnel, or deploy it as a website. Anyone who can reach it can read and edit the Serato library on that machine. `POST /api/shutdown` is enabled only for the desktop process, and only with a token that is not in the page.

Do not send `master.sqlite`, `root.sqlite`, or audio files with a report. Cue data lives in the audio file. The database lives outside this repository.

Anonymous usage counts and crash reports are off until the person opts in from the page. They never include track titles, crate names, file paths, or library rows. A missing `SENTRY_DSN` or `POSTHOG_KEY` disables that service. Release builds bake those client keys from Actions secrets of the same names. Do not commit a DSN or a project key. The copy of `_build_config.py` in git stays empty. [PRIVACY.md](PRIVACY.md) is the full note.

Release builds are unsigned. Check the attestation before you open a download:

```bash
gh attestation verify Serato-Library-macos-arm64.dmg --repo mookiejones/serato-library-manager
gh attestation verify Serato-Library-macos-x64.dmg --repo mookiejones/serato-library-manager
gh attestation verify Serato-Library-windows-setup.exe --repo mookiejones/serato-library-manager
gh attestation verify Serato-Library-windows.zip --repo mookiejones/serato-library-manager
gh attestation verify SHA256SUMS --repo mookiejones/serato-library-manager
```

## Reporting

Report a vulnerability privately: [Open a security advisory](https://github.com/mookiejones/serato-library-manager/security/advisories/new).

GitHub secret scanning, push protection, vulnerability alerts, and Dependabot security updates are on for this repository. Private vulnerability reporting is on.
