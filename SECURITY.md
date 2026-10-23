# Security

The library browser is a local program. `server.py` binds `127.0.0.1` port `8765` and has no login. Do not publish that port, put the process behind a tunnel, or deploy it as a website. Anyone who can reach it can read and edit the Serato library on that machine.

Do not send `master.sqlite`, `root.sqlite`, or audio files with a report. Cue data lives in the audio file. The database lives outside this repository.

Release builds are unsigned. Check the attestation before you open a download:

```bash
gh attestation verify Serato-Library-macos.zip --repo mookiejones/serato-library-manager
gh attestation verify Serato-Library-windows.zip --repo mookiejones/serato-library-manager
```

## Reporting

Report a vulnerability privately: [Open a security advisory](https://github.com/mookiejones/serato-library-manager/security/advisories/new).

GitHub secret scanning, push protection, vulnerability alerts, and Dependabot security updates are on for this repository. Private vulnerability reporting is on.
