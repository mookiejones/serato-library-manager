# Serato web library

Local browser for the Serato DJ Pro library. `server.py` uses the Python standard library. The desktop window adds `pywebview`. Optional sharing uses `sentry-sdk` and `posthog`, and stays off without a key and without consent. There is no linter. Tests use `unittest`.

## Run

```bash
python3 server.py
```

Serves `http://127.0.0.1:8765`. On macOS the process exits if `~/Library/Application Support/Serato/Library/master.sqlite` is missing. On Windows that file is `%LOCALAPPDATA%\Serato\Library\master.sqlite`. Stop the server with Ctrl-C.

The native window uses a local virtualenv, because Homebrew Python will not take a system-wide install:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python desktop.py
```

Closing the window stops the server. On Windows, use `.venv\Scripts\python` in place of `.venv/bin/python`. `.venv/` stays untracked.

## Tests

```bash
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -t . -v
```

The suite imports `sentry-sdk` and `posthog`. It builds a temporary database. It does not open the live Serato library. Settings and logs for the run stay in a temporary directory.

## Layout

- `server.py` is a `ThreadingHTTPServer` bound to `127.0.0.1:8765`. GET routes are `/api/library`, `/api/status`, `/api/track`, `/api/history`, `/api/duplicates`, `/api/related`, `/api/files`, `/api/export.m3u`, `/api/export.rekordbox.xml`, `/api/settings`, and `/api/logs`. POST routes are `/api/track`, `/api/crate`, `/api/import.m3u`, `/api/reveal`, `/api/related`, `/api/duplicates/merge`, `/api/files`, `/api/settings`, and `/api/logs/open`. Any other path is a file under `static/`. A frozen build reads `static/` from the PyInstaller bundle.
- `rekordbox.py` writes a Rekordbox `DJ_PLAYLISTS` file and a loss report. `python3 rekordbox.py -o rekordbox.xml` prints the report. **Rekordbox** in the page shows the report in a dialog and downloads the XML after confirm. Subcrates become nested playlist folders. Hot cues, loops, and the beatgrid are read with the Markers2 and BeatGrid parsers in `tags.py`. MP3 cue times are shifted from the LAME/Xing header, not by one amount for every file. Device Library Plus and OneLibrary are not written.
- `related.py` stores track links in `related.sqlite` beside `settings.json`, not in `master.sqlite`. `library.update_related_path` points those links at a new path after a file move. The schema is `docs/related-tracks.md`. `GET /api/related?path=` returns saved links and suggestions.
- `desktop.py` starts that server and opens it in a pywebview window. `requirements.txt` pins pywebview, sentry-sdk, and posthog. `requirements-build.txt` repeats those pins and also pins PyInstaller. `static_assets.py` lists the local files `static/index.html` references, and `serato-library.spec` exits when one is missing. The spec builds a windowed app named Serato Library for the OS you build on. `SERATO_LIBRARY_SMOKE` writes `ok\n` and returns before the window opens, and before telemetry starts.
- `telemetry.py` sends anonymous counts and crash reports after consent, and only when a key is present. `app_config.py` stores the choice and a random install id. `app_log.py` writes a rotating log. `_build_config.py` is the empty key file that a release build overwrites. `PRIVACY.md` is the public note.
- `.github/workflows/` runs CI (the suite and a pip-audit of the requirements files), CodeQL, dependency review on pull requests, and a release workflow that builds unsigned macOS and Windows zips. `docs/github.md` is the guide.
- `scripts/release_bundle.py` checks a PyInstaller tree, zips it, and launches the unzipped app with `SERATO_LIBRARY_SMOKE`. The publish job checks the zip and does not launch it.
- `library.py` reads and writes `master.sqlite`. The live path is Application Support on macOS and `%LOCALAPPDATA%\Serato\Library` on Windows. `root.sqlite` beside the master file is updated when it is attached. Writes are refused while a live Serato process holds the lock. The first write in a process copies both databases into `Library/Backups`. Reveal uses Finder on macOS and File Explorer on Windows.
- `files.py` renames, moves, replaces, and trashes audio. It updates path columns in `master.sqlite` and the mirrored location database in one transaction, after a backup, and only while Serato is quit. A journal under `Library/Backups` puts the files back if the database write fails. A successful move also updates related-track paths.
- `tags.py` reads Serato GEOB frames (`Markers2`, `BeatGrid`) and can copy those frames onto a plain ID3v2.3 file or an MP3 that has no tag yet. Other layouts are left unchanged. A full ID3 rewrite from another program can still drop those frames.
- `static/` is `index.html`, `app.js`, and `app.css`. Views are crates, history, missing, duplicates, stems, and files. The Duplicates view can merge a group into the copy you keep. Spaces are Serato Library, Serato Video, Apple Music, and Prepare. The track detail pane lists related tracks. The first launch asks whether to share anonymous stats and crash reports. Settings can change that choice and can open or copy the local log.
- `docs/serato-library-tools.md` is research notes, not runtime config.
- `docs/architecture.md` is the code reference. Update it in the same change as the behavior it describes.
- `tests/` is a `unittest` suite. `tests/fixture.py` points `library.MASTER` at a temporary database.
- `.vscode/launch.json` starts `server.py` on F5. "Python: Debug Tests" runs the suite. The desktop window uses `.venv`. The server launch uses the system Python.

## After a change

1. Update `docs/architecture.md` when behavior, the API, the layout, or the run path changes.
2. Update this file when the run command or the layout summary changes.
3. Update `docs/github.md` when a workflow, a release check, or a GitHub setting changes.
4. Update `PRIVACY.md` and the README when sharing, local logs, or telemetry keys change.
5. Commit the change. Do not push unless asked.

## Library safety

The database lives outside this repo. Quit Serato before a write. Do not commit a copy of `master.sqlite`. Cue points live in the audio file, not in the crate row.
