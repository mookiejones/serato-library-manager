## Install

These builds are unsigned. macOS Gatekeeper and Windows SmartScreen warn before the app opens. On macOS, right-click the app and choose Open. On Windows, open `Serato Library.exe` from the unzipped folder.

The macOS download is an Apple Silicon (arm64) app. The Windows download is 64-bit.

Quit Serato DJ Pro before you edit the library. The window serves `127.0.0.1` only. This is not a website, and the release does not contain your library.

Confirm a download was built by this repository:

```bash
gh attestation verify Serato-Library-macos.zip --repo OWNER/REPO
gh attestation verify Serato-Library-windows.zip --repo OWNER/REPO
```
