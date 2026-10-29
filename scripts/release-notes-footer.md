## Install

These builds are unsigned. macOS Gatekeeper and Windows SmartScreen warn before the app opens. The steps, including Removable Volumes on a Mac, are in the guide under First install.

| Computer | File |
| --- | --- |
| Mac with Apple silicon | `Serato-Library-macos-arm64.dmg` |
| Mac with an Intel processor | `Serato-Library-macos-x64.dmg` |
| Windows installer | `Serato-Library-windows-setup.exe` |
| Windows portable zip | `Serato-Library-windows.zip` |

`SHA256SUMS` lists the SHA-256 of each file. GitHub Releases is the only download.

Quit Serato DJ Pro before you edit the library. The page is served on `127.0.0.1` only. This is not a website, and the release does not contain your library.

Sharing of anonymous usage stats and crash reports stays off until you turn it on in the app. Logs stay on your machine.

Confirm a download was built by this repository:

```bash
gh attestation verify Serato-Library-macos-arm64.dmg --repo OWNER/REPO
gh attestation verify Serato-Library-macos-x64.dmg --repo OWNER/REPO
gh attestation verify Serato-Library-windows-setup.exe --repo OWNER/REPO
gh attestation verify Serato-Library-windows.zip --repo OWNER/REPO
gh attestation verify SHA256SUMS --repo OWNER/REPO
```
