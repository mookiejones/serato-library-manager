# Serato web library

Local browser for the Serato DJ Pro library. `server.py` uses the Python standard library. `desktop.py` opens that page in a native window and shuts the server down when the window closes. Optional sharing uses `sentry-sdk` and `posthog`, and stays off without a key and without consent. Python has no linter. The page uses ESLint. Tests use `unittest` and Vitest.

## Run

```bash
python3 server.py
```

Serves `http://127.0.0.1:8765`. A missing library still serves the page so setup can explain the next step. On macOS the usual library file is `~/Library/Application Support/Serato/Library/master.sqlite`. On Windows that file is `%LOCALAPPDATA%\Serato\Library\master.sqlite`. Stop the server with Ctrl-C.

The desktop app uses a local virtualenv, because Homebrew Python will not take a system-wide install:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python desktop.py
```

It binds `127.0.0.1` on a free port and opens a window titled Serato Library. Close the window to quit. A second launch focuses that window. On Windows, use `.venv\Scripts\python` in place of `.venv/bin/python`. On macOS, also install `requirements-macos.txt` so WKWebView can load. On Linux, install WebKitGTK (GTK 3 and WebKit2) or Qt WebKit. `.venv/` stays untracked. `SERATO_LIBRARY_NO_WINDOW=1` or `--no-window` skips the window.

## Tests

```bash
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -t . -v
```

The suite imports `sentry-sdk` and `posthog`. It builds a temporary database. It does not open the live Serato library. Settings and logs for the run stay in a temporary directory.

The page tests, including the setup wizard, need Node 22 or newer:

```bash
npm ci
npm test
npm run typecheck
npm run build
```

## Layout

- `server.py` is a `ThreadingHTTPServer` bound to `127.0.0.1:8765` when you run it directly. The desktop app asks for a free port instead. GET routes are `/api/health`, `/api/library`, `/api/status`, `/api/track`, `/api/history`, `/api/duplicates`, `/api/related`, `/api/files`, `/api/export.m3u`, `/api/export.rekordbox.xml`, `/api/settings`, `/api/setup`, `/api/logs`, and `/api/snapshots`. POST routes are `/api/shutdown`, `/api/focus`, `/api/track`, `/api/crate`, `/api/import.m3u`, `/api/reveal`, `/api/related`, `/api/duplicates/merge`, `/api/files`, `/api/settings`, `/api/setup`, `/api/logs/open`, and `/api/snapshots`. Any other path is a file under `static/`. A frozen build reads `static/` from the PyInstaller bundle. `/api/health` does not open the library. `/api/shutdown` answers only when the desktop process set a token. When the library file exists, `serve` starts a poll of the Serato files that snapshots after an outside change. A missing library file still serves the page.
- `rekordbox.py` writes a Rekordbox `DJ_PLAYLISTS` file and a loss report. `python3 rekordbox.py -o rekordbox.xml` prints the report. **Rekordbox** in the page shows the report in a dialog and downloads the XML after confirm. **Hot loops** sits beside **Memory cues**, starts off, and is remembered with Memory cues and the key notation in `settings.json`. The help line reads Uses a free hot-cue pad. Subcrates become nested playlist folders. Hot cues, loops, and the beatgrid are read with the Markers2 and BeatGrid parsers in `tags.py`. MP3 cue times are shifted from the LAME/Xing header, not by one amount for every file. Device Library Plus and OneLibrary are not written.
- `snapshots.py` stores content-addressed, hash-checked snapshots of the database, per-drive `_Serato_` crates (including `database V2`), and Serato frames inside audio files. Frame bytes are read and written by `snapshot_frames.py`. `Export Backups` and `Lexicon` are never read or restored, including a Windows name with a trailing dot, a trailing space, or an alternate data stream. Restore saves a snapshot first, writes a journal before the first replace, can be previewed without writing, and refuses while Serato DJ is running or while the Serato version, Protect Library, or Lucid/Flexible beatgrid storage is not safe to write. An unfinished restore is rolled back when the store opens. `SnapshotReader` exposes `list_snapshots` and `load`. `serato_web.completeness.is_complete` is the shared check for a finished snapshot or backup. `restore` calls `verify_legacy_backup` when `backup_status` is `legacy, unverified`, before the pre-restore snapshot.
- `related.py` stores track links in `related.sqlite` beside `settings.json`, not in `master.sqlite`. `library.update_related_path` points those links at a new path after a file move. The schema is `docs/related-tracks.md`. `GET /api/related?path=` returns saved links and suggestions.
- `desktop.py` starts that server on a free port and opens a pywebview window titled Serato Library. The window uses the system web view: WebView2 on Windows, WKWebView on macOS, and WebKitGTK or Qt WebKit on Linux. Chromium is not bundled. Closing the window POSTs `/api/shutdown` with the desktop token. A second launch POSTs `/api/focus` and the running process brings the window forward. `requirements.txt` pins pywebview, sentry-sdk, and posthog, and pins pythonnet on Windows. `requirements-build.txt` repeats those pins and also pins PyInstaller. `requirements-macos.txt` pins the PyObjC frameworks WKWebView needs. `static_assets.py` lists the local files `static/index.html` references, and `serato-library.spec` exits when one is missing or pywebview is missing. The spec builds a windowed app named Serato Library for the OS you build on. `SERATO_LIBRARY_SMOKE` is an absolute marker path. The process writes the URL and a shutdown token there, serves `/api/health` without opening the library, a window, or telemetry, and exits when the harness posts that token. `SERATO_LIBRARY_NO_WINDOW=1` or `--no-window` skips the window on a normal launch. The window size and position are stored in `settings.json`. A saved position is restored when a 100 by 40 pixel strip of the title bar is on a screen, including a monitor with a negative origin. Otherwise the window is centered on the primary screen. A crash leaves the lock free; the next launch deletes the leftover `instance.port`.
- `telemetry.py` sends anonymous counts and crash reports after consent, and only when a key is present. `app_config.py` stores the choice, a random install id, `wizard_complete`, the window frame, and the track list width. `setup_flow.py` describes the library in plain words for the first-run wizard. `app_log.py` writes a rotating log. `_build_config.py` is the empty key file that a release build overwrites. `PRIVACY.md` is the public note.
- `.github/workflows/` runs CI (the suite, a TypeScript check of `src/`, Vitest in jsdom, a freshness check of the committed `static/app.js` and `static/wizard.js` bundles, and a pip-audit of the requirements files), CodeQL, dependency review on pull requests, and a release workflow that builds the page bundle before PyInstaller and then builds unsigned macOS disk images and a Windows installer plus portable zip. Dependabot also updates the Node toolchain. A pull request that changes the packaging files runs those builds and uploads the artifacts. Only a tag push publishes a GitHub Release. That is the only download. `docs/github.md` is the guide.
- `scripts/release_bundle.py` checks a PyInstaller tree, writes the macOS disk image or the Windows zip and installer, and launches the unpacked app with `SERATO_LIBRARY_SMOKE`. The harness hits `/api/health` and shuts the app down. The publish job checks the files and `SHA256SUMS` and does not launch them. `scripts/release_sign.py` signs only when the Apple or Windows secrets are all set. When they are absent it skips and exits 0.
- `library.py` reads and writes `master.sqlite`. The live path is Application Support on macOS and `%LOCALAPPDATA%\Serato\Library` on Windows. `root.sqlite` beside the master file is updated when it is attached. Writes are refused while a live Serato process holds the lock. The first write in a process copies both databases into `Library/Backups`. `serato_web/completeness.py` is the shared check for a finished backup or snapshot directory (`is_complete`, `verify_legacy_backup`). Reveal uses Finder on macOS and File Explorer on Windows.
- `files.py` renames, moves, replaces, and trashes audio. It updates path columns in `master.sqlite` and the mirrored location database in one transaction, after a backup, and only while Serato is quit. A journal under `Library/Backups` puts the files back if the database write fails. A successful move also updates related-track paths.
- `tags.py` reads Serato markers from ID3 GEOB frames (`Markers2`, `BeatGrid`), from FLAC Vorbis comments (`SERATO_MARKERS_V2`, `SERATO_BEATGRID`), and from M4A/MP4 freeform atoms (`----:com.serato.dj:markersv2` and `beatgrid`). It can copy GEOB frames onto a plain ID3v2.3 file or an MP3 that has no tag yet. FLAC, M4A, and other layouts are left unchanged by that copy. `snapshot_frames.py` is what puts a snapshot's exact Markers2, BeatGrid, and Autotags bytes back. A full ID3 rewrite from another program can still drop those frames.
- `src/` is the page in strict TypeScript. `app.ts` wires the screen. `views.ts` paints crates, history, missing tracks, duplicates, stems, and files. `dialogs.ts` is the Rekordbox, merge, sharing, and file dialogs. `wizard.ts` and `wizard-view.ts` are the first-run setup. `virtual-scroll.ts` paints the track rows. `restore.ts` is snapshots. `splitter.ts` is the draggable list/details divider, and `layout.ts` mounts it on the track sheet and saves its width in `settings.json`. `format.ts`, `api.ts`, `api-types.ts`, `state.ts`, `dom.ts`, and `bridge.ts` are the rest. `package.json` requires Node `>=22`. `npm run build` bundles `src/app.ts` to `static/app.js` and `src/wizard-view.ts` to `static/wizard.js`, both IIFEs. Those files are committed, so the server does not need Node. `static/` is `index.html`, `tokens.css`, `app.css`, `app.js`, `app.js.map`, `wizard.js`, `wizard.js.map`, and the setup illustrations in `img/wizard/`. Views are crates, history, missing, duplicates, stems, files, and snapshots. The Duplicates view can merge a group into the copy you keep. The Snapshots view lists hash-checked snapshots, previews a restore, and can undo an outside change. Spaces are Serato Library, Serato Video, Apple Music, and Prepare. The track detail pane lists related tracks. The first launch runs setup until `wizard_complete` is true: confirm the library, save a safety snapshot, and choose whether to share anonymous stats. Cancel does not finish setup. Settings can change the sharing choice, run setup again, and open or copy the local log.
- `docs/wiki/` is the GitHub wiki draft: `Home.md`, `Quick-Start.md`, `Install-macOS.md`, `Install-Windows.md`, the feature pages, `_Sidebar.md`, and `docs/wiki/images/`. Copy those pages into the wiki by hand. Do not push the wiki from this repository. `docs/quick-start.md` is the same Quick Start in the user guide, with light and dark pictures. The wiki page uses the light PNG. `docs/mkdocs.yml` excludes `wiki/*.md` from the site build.
- `docs/serato-library-tools.md` is research notes, not runtime config.
- `docs/architecture.md` is the code reference. Update it in the same change as the behavior it describes.
- `tests/` is a `unittest` suite. `tests/fixture.py` points `library.MASTER` at a temporary database. `src/wizard.test.ts` is the Vitest suite for the setup steps.
- `.vscode/launch.json` starts `server.py` on F5. "Python: Debug Tests" runs the suite. The desktop app uses `.venv`. The server launch uses the system Python.

## Strict TypeScript

`src/` is the page in strict TypeScript.

## After a change

1. Update `docs/architecture.md` when behavior, the API, the layout, or the run path changes.
2. Update `CLAUDE.md` and `AGENTS.md` together. They are copies of the same text. Update them when the run command or the layout summary changes.
3. Update `docs/github.md` when a workflow, a release check, or a GitHub setting changes.
4. Update `PRIVACY.md` and the README when sharing, local logs, or telemetry keys change.
5. Commit the change. Do not push unless asked.

## Merge rules

- `main` is protected. Changes go in only through a pull request.
- If a new push dismisses the `mookiejones-qa` approval, re-request review.
- These checks must pass:
  - `tests (ubuntu-latest, Python 3.12)`
  - `tests (ubuntu-latest, Python 3.14)`
  - `tests (windows-latest, Python 3.12)`
  - `frontend (ubuntu-latest)`
  - `frontend (windows-latest)`
  - `analyze Python` (CodeQL)
- Do not force-push to `main`.
- Admins can bypass these rules, but should not.
- The team (including agents) may merge a PR once `mookiejones-qa` has approved its latest commit and all required checks are green (the six listed: Ubuntu + Windows tests, frontend, and `analyze Python` (CodeQL)). Agents never tag or publish a release (including pre-releases) without Charles (@mookiejones)'s explicit OK.
- QA reviews every pull request and blocks any pull request lacking tests for its changes.
- Follow [Library safety](#library-safety) and [strict TypeScript](#strict-typescript).

## Library safety

The database lives outside this repo. Quit Serato before a write. Do not commit a copy of `master.sqlite`. Cue points live in the audio file, not in the crate row.
