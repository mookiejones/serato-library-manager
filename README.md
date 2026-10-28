# Serato Library

A local window for the Serato DJ Pro library on macOS and Windows. Browse crates, edit track details, clean up duplicate copies, move files, and export `rekordbox.xml`. The app talks only to this computer. Your tracks, crate names, and file paths stay here.

GitHub is the only place to get it. Install a [release](https://github.com/mookiejones/serato-library-manager/releases), or run this repository from source. Both are below.

## Release

The latest release is [v0.1.1](https://github.com/mookiejones/serato-library-manager/releases/tag/v0.1.1). The zips are unsigned.

| Computer | File | What is inside |
| --- | --- | --- |
| Mac with Apple silicon | `Serato-Library-macos.zip` | `Serato Library.app` |
| 64-bit Windows | `Serato-Library-windows.zip` | A folder named `Serato Library`, with `Serato Library.exe` inside |

The Mac zip is for Apple silicon. An Intel Mac is not in that zip.

v0.1.1 includes crates, track details, History, Missing, the Duplicates list, Stems, Prepare, playlists, and Settings. Duplicate merge, related tracks, the Files view, and the Rekordbox export were added after that tag. They are in this repository. They are not in the v0.1.1 zip.

### macOS

1. Open the [v0.1.1 release](https://github.com/mookiejones/serato-library-manager/releases/tag/v0.1.1) and download `Serato-Library-macos.zip`.
2. Double-click the zip. Finder unpacks `Serato Library.app`.
3. Quit Serato DJ Pro if you plan to edit the library.
4. Right-click `Serato Library.app` and choose Open.
5. Choose Open again in the Gatekeeper dialog.

The next launch can be a normal double-click. Closing the window stops the app.

### Windows

1. Open the [v0.1.1 release](https://github.com/mookiejones/serato-library-manager/releases/tag/v0.1.1) and download `Serato-Library-windows.zip`.
2. Right-click the zip, choose Extract All, and finish the extract.
3. Open the extracted `Serato Library` folder.
4. Quit Serato DJ Pro if you plan to edit the library.
5. Double-click `Serato Library.exe`.
6. If SmartScreen appears, choose More info, then Run anyway.

Run the exe from the extracted folder. Closing the window stops the app.

## Run from source

A checkout of this repository includes every merged feature, including the Rekordbox export.

Quit Serato DJ Pro before you edit the library. Writes wait until Serato has quit.

1. From this directory, run `python3 server.py`.
2. Open `http://127.0.0.1:8765`.

The server uses the Python standard library. Press Ctrl-C to stop it. If `master.sqlite` is missing, the process exits.

| System | Library file |
| --- | --- |
| macOS | `~/Library/Application Support/Serato/Library/master.sqlite` |
| Windows | `%LOCALAPPDATA%\Serato\Library\master.sqlite` |

The same page can open in a desktop window. Use a virtualenv, because a system Python may refuse a system-wide install.

### macOS

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python desktop.py
```

Closing the window stops the server.

To build an unsigned app on this Mac:

```bash
.venv/bin/pip install -r requirements-build.txt
.venv/bin/python -m PyInstaller serato-library.spec
```

The app is `dist/Serato Library.app`.

### Windows

```bat
python3 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python desktop.py
```

Closing the window stops the server.

To build an unsigned app on this PC, use `.venv\Scripts\python` for both of the commands below:

```bat
.venv\Scripts\python -m pip install -r requirements-build.txt
.venv\Scripts\python -m PyInstaller serato-library.spec
```

The app is `dist\Serato Library\`. Build on each system you want to ship. GitHub Actions publishes the unsigned release zips. The developer guide is [docs/github.md](docs/github.md).

In VS Code, press F5. That launch runs `server.py`.

## Rekordbox export

This is shipped in this repository. It is not in the v0.1.1 zip.

**Rekordbox** in the track bar reads the open crate, including subcrates, or the whole space. It does not change the Serato library or the audio files. A dialog lists what could not be copied. The `rekordbox.xml` download starts after you confirm, and it is the same XML as that check.

The bar has **Memory cues** (on until you clear it) and a key choice: **Key as stored**, **Camelot key**, or **Classical key**. Saved loops stay memory loops in that download. `python3 rekordbox.py -o rekordbox.xml` writes the same file and prints the same report. `--hot-loops` can place a saved loop on a free hot cue pad. The page does not send that option.

The file includes the path, title, artist, album, genre, BPM, key, length, bitrate, comments, hot cues, loops, and beatgrid. A flexible grid uses the marker times stored in the file. Those times are not rounded to three decimals before the BPM calculation. The written BPM is two decimal places, so the grid can drift.

In Rekordbox 6 and 7 the import control is at Preferences, Advanced, Database, rekordbox xml. Since Rekordbox 5.6.1 an import does not update a track that is already in the collection. To overwrite it, select the tracks in the rekordbox xml list, right-click, choose Import to Collection, and answer Yes to load information from imported library. That replaces cues, the beatgrid, and tags. A cue that exists only in Rekordbox is removed. Device Library Plus, OneLibrary, and `master.db` are not written.

What the file keeps is [docs/coming-from-rekordbox.md](docs/coming-from-rekordbox.md). The steps in the app are in [docs/guide/playlists.md](docs/guide/playlists.md).

## Guides

- [Panic page](docs/panic.md). Red tracks, missing crates, a drive that will not mount, or a library that looks wrong after a Serato update. The steps use Serato's own tools.
- [Is my library safe?](docs/is-my-library-safe.md). Restore, undo, snapshots, the outside-change watcher, and the gig check. Those are PREVIEW. The pictures are example data.
- [Moving between Serato and Rekordbox](docs/coming-from-rekordbox.md). What the shipped export keeps.
- [User guide](docs/index.md). The rest of the app.

## PREVIEW

One-click restore, undo, snapshots, the outside-change watcher, and the gig check are **PREVIEW** until [#35](https://github.com/mookiejones/serato-library-manager/issues/35) and [#41](https://github.com/mookiejones/serato-library-manager/issues/41) merge. They are not in the app. The screens on the safety page are example data.

What is in the app today is a database copy, not that restore. The first save after you open the app copies `master.sqlite` (and `root.sqlite` when it is present) into `Library/Backups`. Putting a copy back is a manual file swap. The steps are in [docs/guide/safety.md](docs/guide/safety.md).

## In this repository

These are merged. They are not in the v0.1.1 zip.

The Duplicates view can merge copies that share a title, artist, and length. Choose the file to keep. The others leave the library, and the copy you keep is added to the crates they were in. Empty fields are filled from the other copies. Play count and rating keep the higher value. Audio files stay on disk unless you move them to the Trash. Cue points stay in the audio file. A merge reads them and does not rewrite them.

[![Merge copies dialog. One file is selected to keep, and the plan lists crates and fields.](docs/media/duplicate-merge-poster.jpg)](docs/media/duplicate-merge.mp4)

Select the picture to play the duplicate-merge recording.

The Files view renames, moves, and deletes audio on disk and updates the library path so crates and history stay attached. Replacing a track copies its cue points onto the new file when the tag can take them, and says so when it cannot. Nothing is written until you confirm the review.

Open a track to save related tracks, with a note and a rating, or to keep a one-way link. Suggestions use musical key, tempo, and shared crates. The links are stored in `related.sqlite` next to the app settings, not in Serato's library, so they can be saved while Serato is open. Copying them into a Serato crate named `Related - ` plus the track title is a library write and waits until Serato has quit. The file layout is [docs/related-tracks.md](docs/related-tracks.md).

The first launch asks "Share anonymous usage stats and crash reports?" Sharing stays off until you choose it. Settings in the sidebar keeps that switch, and can open or copy the local log. [PRIVACY.md](PRIVACY.md) lists what can leave the machine.

## Sharing

Crash reports use `sentry-sdk`. Usage counts use the `posthog` package. Both stay off when their key is missing, and both stay off until you opt in. The variables are `SENTRY_DSN`, `POSTHOG_KEY`, and `POSTHOG_HOST` (the host defaults to `https://us.i.posthog.com`). A release build reads those names from GitHub Actions secrets. The guide is [docs/github.md](docs/github.md). The server still starts when the packages are not installed. Sharing is then a no-op.

## Tests

Install the pinned packages, then run the suite from this directory. The suite imports `sentry-sdk` and `posthog`.

```bash
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -t . -v
```

The tests build a temporary database. They do not open the live Serato library. Settings and logs for the run stay in a temporary directory.

## Documentation

The user guide is [docs/index.md](docs/index.md). The code reference is [docs/architecture.md](docs/architecture.md). Related-track storage is [docs/related-tracks.md](docs/related-tracks.md). What the app can send is [PRIVACY.md](PRIVACY.md). Functions in `server.py`, `desktop.py`, `library.py`, `files.py`, `related.py`, `rekordbox.py`, `tags.py`, `telemetry.py`, `app_config.py`, and `app_log.py` use Google-style docstrings.
