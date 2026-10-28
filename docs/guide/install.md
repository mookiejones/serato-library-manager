# Install

Download a release build. You do not need Python, and you do not need to build the app.

Open the [releases page](https://github.com/mookiejones/serato-library-manager/releases). Download the zip for your computer.

| Computer | File | What is inside |
| --- | --- | --- |
| Mac with Apple silicon | `Serato-Library-macos.zip` | `Serato Library.app` |
| 64-bit Windows | `Serato-Library-windows.zip` | A folder named `Serato Library`, with `Serato Library.exe` inside |

The Mac download is for Apple silicon. An Intel Mac is not in that zip.

The builds are unsigned. macOS Gatekeeper and Windows SmartScreen warn before the app opens. That warning is expected.

!!! note "What version 0.1.1 includes"
    The GitHub Release named v0.1.1 was built before Duplicate Merge, Related Tracks, Files, and the Rekordbox export. This guide describes the app in the repository now. Those parts are not in the v0.1.1 zip. Crates, track details, History, Missing, the Duplicates list, Stems, Prepare, playlists, and Settings are in v0.1.1.

## macOS

1. Download `Serato-Library-macos.zip`.
2. Double-click the zip. Finder unpacks `Serato Library.app`.
3. Quit Serato DJ Pro if it is open and you plan to edit the library.
4. Right-click `Serato Library.app`.
5. Choose Open.
6. Choose Open again in the Gatekeeper dialog.

The next launch can be a normal double-click.

## Windows

1. Download `Serato-Library-windows.zip`.
2. Right-click the zip.
3. Choose Extract All, and finish the extract.
4. Open the `Serato Library` folder that was extracted.
5. Quit Serato DJ Pro if it is open and you plan to edit the library.
6. Double-click `Serato Library.exe`.
7. If SmartScreen appears, choose More info, then Run anyway.

Leave the extracted folder where it is. The app runs from that folder.

## The first window

The window title is **Serato library**. The left side says **Library**. The status line starts as **Checking Serato**, then changes to one of these:

- **Serato is quit. Edits save to the library.**
- **Serato DJ Pro is open. Edits stay off until it quits.** The process name in the sentence matches the program that has the library open.

Closing the window stops the app. The window serves `127.0.0.1` only. Nothing in the release is your library. The app reads the library Serato already keeps on this computer.

The first launch asks **Share anonymous usage stats and crash reports?** **Don't share** is selected. Read [Settings and privacy](settings.md) before you choose Share. Closing the dialog, or pressing Esc, saves **Don't share**.

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

If `master.sqlite` is missing, the app closes. The message is **Serato library not found at** followed by the path above. Install Serato DJ Pro and open it once so it can create the library. Then open Serato Library again.

## If the window does not open

Another copy may already be running. Quit that window and try again. The message is **http://127.0.0.1:8765 is already in use. Quit the other Serato library server (server.py or the desktop window) and try again.**

Gatekeeper and SmartScreen steps are also in [Troubleshooting](troubleshooting.md).
