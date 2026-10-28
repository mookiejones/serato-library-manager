# Serato web library

A local window for the Serato DJ Pro library on macOS and Windows. The user guide is [on GitHub Pages](https://mookiejones.github.io/serato-library-manager/) and [in the repository](docs/index.md).

[![Merge copies dialog. One file is selected to keep, and the plan lists crates and fields.](docs/media/duplicate-merge-poster.jpg)](docs/media/duplicate-merge.mp4)

Select the picture to play the duplicate-merge recording. The steps are in the guide under Duplicates. On the published site the same recording plays in the page.

## Run

1. Quit Serato DJ Pro.
2. From this directory, run `python3 server.py`.
3. Open `http://127.0.0.1:8765`.

The server uses the Python standard library. On macOS it reads `~/Library/Application Support/Serato/Library/master.sqlite`. On Windows it reads `%LOCALAPPDATA%\Serato\Library\master.sqlite`. Writes wait until Serato has quit. Press Ctrl-C to stop the server.

The Duplicates view can merge copies that share a title, artist, and length. Choose the file to keep. The others leave the library, and the copy you keep is added to the crates they were in. Empty fields are filled from the other copies. Play count and rating keep the higher value. Audio files stay on disk unless you move them to the Trash. Cue points stay in the audio file. A merge reads them and does not rewrite them.

**Rekordbox** in the track bar downloads `rekordbox.xml` for the open crate, including subcrates, or for the whole space. The file includes the path, title, artist, album, genre, BPM, key, length, bitrate, comments, hot cues, loops, and beatgrid. In Rekordbox 6 and 7 the import control is at Preferences, Advanced, Database, rekordbox xml. Since Rekordbox 5.6.1 an import does not update a track that is already in the collection. To overwrite it, select the tracks in the rekordbox xml list, right-click, choose Import to Collection, and answer Yes to load information from imported library. That replaces cues, the beatgrid, and tags. `python3 rekordbox.py -o rekordbox.xml` writes the same file and prints what could not be copied. Device Library Plus and OneLibrary USB drives are not written.

The Files view renames, moves, and deletes audio on disk and updates the library path so crates and history stay attached. Replacing a track copies its cue points onto the new file when the tag can take them, and says so when it cannot. Nothing is written until you confirm the preview. A move also points saved related-track links at the new path.

The first launch asks "Share anonymous usage stats and crash reports?" Sharing stays off until you choose it. Settings in the sidebar keeps that switch, and can open or copy the local log. [PRIVACY.md](PRIVACY.md) lists what can leave the machine.

Open a track to save related tracks, with a note and a rating, or to keep a one-way link. Suggestions use musical key, tempo, and shared crates. The links are stored in `related.sqlite` next to the app settings, not in Serato's library, so they can be saved while Serato is open. Copying them into a Serato crate named `Related - ` plus the track title is a library write and waits until Serato has quit. The file layout is [docs/related-tracks.md](docs/related-tracks.md).

In VS Code, press F5. That launch runs `server.py`.

## Desktop window

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python desktop.py
```

The window loads the same page. Closing it stops the server. On Windows, use `.venv\Scripts\python` in place of `.venv/bin/python`.

To build an unsigned app on the current operating system:

```bash
.venv/bin/pip install -r requirements-build.txt
.venv/bin/python -m PyInstaller serato-library.spec
```

On macOS the app is `dist/Serato Library.app`. On Windows it is `dist/Serato Library/`. On Windows, use `.venv\Scripts\python` for both commands. Build on each system you want to ship.

## GitHub

GitHub Actions runs the test suite, audits the pinned requirements, and publishes unsigned desktop zips. The library server stays on `127.0.0.1`. GitHub Pages publishes the user guide only, as a static site. The developer guide is [docs/github.md](docs/github.md). The roadmap is the [Serato Tools Roadmap](https://github.com/users/mookiejones/projects/3) project board. Feature ideas live in [issues labelled feature-gap](https://github.com/mookiejones/serato-library-manager/issues?q=label%3Afeature-gap). Report a vulnerability in private, as [SECURITY.md](SECURITY.md) describes.

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

The user guide is [docs/index.md](docs/index.md). The published copy is [https://mookiejones.github.io/serato-library-manager/](https://mookiejones.github.io/serato-library-manager/). The code reference is [docs/architecture.md](docs/architecture.md). Related-track storage is [docs/related-tracks.md](docs/related-tracks.md). What the app can send is [PRIVACY.md](PRIVACY.md). Functions in `server.py`, `desktop.py`, `library.py`, `files.py`, `related.py`, `rekordbox.py`, `tags.py`, `telemetry.py`, `app_config.py`, and `app_log.py` use Google-style docstrings.
