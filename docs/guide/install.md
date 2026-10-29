# Install

Download a release build. You do not need Python, and you do not need to build the app. The open steps, the unsigned-app warnings, and the Mac external-drive permission are in [First install](../first-install.md).

Open the [releases page](https://github.com/mookiejones/serato-library-manager/releases).

| Computer | File |
| --- | --- |
| Mac with Apple silicon | `Serato-Library-macos-arm64.dmg` |
| Mac with an Intel processor | `Serato-Library-macos-x64.dmg` |
| Windows installer | `Serato-Library-windows-setup.exe` |
| Windows, if you cannot run an installer | `Serato-Library-windows.zip` |

`SHA256SUMS` on that release lists the SHA-256 of each file. GitHub Releases is the only download.

The builds are unsigned. macOS Gatekeeper and Windows SmartScreen warn before the app opens. That warning is expected. On a Mac, reading an external drive needs **Removable Volumes** under **System Settings › Privacy & Security › Files and Folders**. That is not Full Disk Access. An unsigned update can ask again. [First install](../first-install.md#mac-external-drives) has the steps.

!!! note "What version 0.1.1 includes"
    The GitHub Release marked Latest is v0.1.1. It was built before Duplicate Merge, Related Tracks, and Files. The pre-release v1.1.0-rc2 includes those parts. It does not include the first-run setup or **Hot loops**. This guide describes the app in the repository now. Crates, track details, History, Missing, the Duplicates list, Stems, Prepare, playlists, and Settings are in v0.1.1.

## The first page

Quit Serato DJ Pro if it is open and you plan to edit the library. Then open the app the way [First install](../first-install.md) describes.

A window titled **Serato Library** opens. The page is served on `127.0.0.1`. The first time, setup runs before the library is yours to browse.

1. **Welcome.** Read the one sentence. Choose **Get started**.
2. **Find your library.** The page names the disk and how many tracks it found. Choose **Use this library**. If it found nothing, open Serato DJ once, quit it, and choose **Check again**. **Choose a folder** lets you point at that folder yourself. The app still opens the library Serato keeps on this computer.
3. **Safety snapshot.** Choose **Take a safety snapshot**. If Serato DJ is open, the page says **Close Serato DJ to continue** and checks again on its own. When the copy is saved, choose **Continue**.
4. **Sharing,** if you have not chosen yet. **No, don't share** and **Yes, share** are the same kind of button. **No, don't share** is first.
5. **Done.** The page says **Library ready. Snapshot saved.** Choose **Open my library**.

**Back** is on every step except Welcome. **Cancel** closes setup and does not change the library. Setup shows again the next time you open the app until you choose **Open my library**. Pressing Esc cancels setup. It does not answer the sharing question.

After that, the left side says **Library**. The status line starts as **Checking Serato**, then changes to one of these:

- **Serato is quit. Edits save to the library.**
- **Serato DJ Pro is open. Edits stay off until it quits.** The process name in the sentence matches the program that has the library open.

Close the window to quit. A second double-click focuses the same window. The page is served on `127.0.0.1` only. Nothing in the release is your library. The app reads the library Serato already keeps on this computer.

Read [Settings and privacy](settings.md) before you choose **Yes, share**. **No, don't share** leaves sharing off. Esc on that step cancels setup and does not save a sharing choice.

## Where Serato keeps the library

Serato DJ Pro stores the library in a database named `master.sqlite`. A second file, `root.sqlite`, often sits in the same folder. Serato Library reads both. It updates `root.sqlite` when that file is present.

| System | Folder |
| --- | --- |
| macOS | `~/Library/Application Support/Serato/Library/` |
| Windows | `%LOCALAPPDATA%\Serato\Library\` |

On a Mac, the file is `~/Library/Application Support/Serato/Library/master.sqlite`.

On Windows, the file is `%LOCALAPPDATA%\Serato\Library\master.sqlite`.

### Open the folder on a Mac

1. Open Finder.
2. Choose Go, then Go to Folder.
3. Paste `~/Library/Application Support/Serato/Library`.
4. Press Return.

### Open the folder on Windows

1. Press the Windows key and R together.
2. Paste `%LOCALAPPDATA%\Serato\Library`.
3. Press Enter.

If that file is missing, the app stays open. Setup says **No Serato library was found on this computer.** Install Serato DJ Pro and open it once so it can create the library. Quit Serato DJ. Then choose **Check again**.

## If the window does not open

Another copy may already be running. Its window should come forward. If it does not, close the Serato Library window and try again. If you started `server.py` from a terminal, the message is **http://127.0.0.1:8765 is already in use. Quit the other Serato library server (server.py or the desktop app) and try again.**

Gatekeeper, SmartScreen, and Removable Volumes steps are in [First install](../first-install.md) and [Troubleshooting](troubleshooting.md).
