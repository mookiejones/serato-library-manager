# First install (GitHub Releases)

> **Back up first.** Close Serato and copy your `_Serato_` folder (one per drive) somewhere safe. If anything looks wrong, see [Troubleshooting](guide/troubleshooting.md).

1. Go to the repo's **Releases** page on GitHub and download the file for your computer.

    | Computer | File |
    | --- | --- |
    | Mac with Apple silicon | `Serato-Library-macos-arm64.dmg` |
    | Mac with an Intel processor | `Serato-Library-macos-x64.dmg` |
    | Windows | `Serato-Library-windows-setup.exe` |

    Windows also has a portable copy, `Serato-Library-windows.zip`, for when you cannot run an installer. Unzip it, leave the folder where it is, and open `Serato Library.exe` inside it.

    You do not need Python, and you do not need a terminal.

2. Optional: check the download against `SHA256SUMS` on the same release.

On a Mac, double-click the disk image, drag **Serato Library** onto **Applications**, then open it from Applications. On Windows, double-click the installer and leave **Open Serato Library** checked at the end.

A window titled **Serato Library** opens. The page is served on this computer at an address starting with `127.0.0.1`. Nothing is uploaded. On Windows the window uses the installed WebView2 runtime. On a Mac it uses the system web view. A second double-click focuses that window. Close the window to quit.

## Why you'll see a warning

This release isn't code-signed yet, so your computer will warn you the first time you open it. That's expected.

### Mac: macOS 15 (Sequoia) and later

1. Open the app once. macOS blocks it.
2. Go to **System Settings › Privacy & Security**.
3. Scroll down and click **Open Anyway** next to the app's name.
4. Confirm, and enter your password if asked.

### Mac: macOS 14 and earlier

Right-click (or Control-click) the app, choose **Open**, then click **Open** again.

### Mac: external drives

Reading music on an external drive needs **Removable Volumes**. That is not Full Disk Access. Do not turn on Full Disk Access for this app.

The first time the app reads a drive, macOS may ask. Choose Allow. If it does not ask, or the drive stays empty:

1. Open **System Settings**.
2. Go to **Privacy & Security**.
3. Go to **Files and Folders**.
4. Select **Serato Library**.
5. Turn on **Removable Volumes**.

These builds are unsigned, so macOS treats each update as a different app. It may ask again after an update, or the switch may be off. Turn **Removable Volumes** back on for the new copy.

### Windows

SmartScreen shows "Windows protected your PC." Click **More info**, then **Run anyway**. The warning fades as more people download the app.
