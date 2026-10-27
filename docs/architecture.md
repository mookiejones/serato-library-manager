# Serato web library

A local page for the Serato DJ Pro library. The process reads `master.sqlite`. It writes only after Serato has quit. The first write in a process copies the databases into `Library/Backups`.

`docs/serato-library-tools.md` is research about other tools. It is not a description of this program.

## Run

1. Quit Serato DJ Pro.
2. From the repository root, run `python3 server.py`.
3. Open `http://127.0.0.1:8765`.
4. Press Ctrl-C to stop the server.

On macOS the process exits when `~/Library/Application Support/Serato/Library/master.sqlite` is missing. On Windows that file is `%LOCALAPPDATA%\Serato\Library\master.sqlite`. `server.py` uses the Python standard library.

A native window runs the same server:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python desktop.py
```

Closing the window stops the server. On Windows, use `.venv\Scripts\python` in place of `.venv/bin/python`. To build an app for the machine you are on, install `requirements-build.txt` in that environment and run `python -m PyInstaller serato-library.spec`. The result is `dist/Serato Library.app` on macOS, or `dist/Serato Library/` on Windows. The build is unsigned. Release builds, attestations, and the GitHub settings around them are in [docs/github.md](github.md).

The first time the page opens, it asks whether to share anonymous usage stats and crash reports. The choice stays off until you accept. [PRIVACY.md](../PRIVACY.md) lists what can be sent.

## Tests

1. From the repository root, install the pinned packages with `python3 -m pip install -r requirements.txt`. The suite imports `sentry-sdk` and `posthog`.
2. Run `python3 -m unittest discover -s tests -t . -v`.
3. The suite builds a temporary database and points `library.MASTER` at that file. The fixture closes every SQLite connection before it deletes that directory. Windows cannot delete a database file that still has an open handle, and a `sqlite3` connection used as a context manager commits without closing.
4. The suite does not open the live Serato library. `tests/__init__.py` points `SERATO_LIBRARY_CONFIG_DIR` and `SERATO_LIBRARY_LOG_DIR` at a temporary directory for the whole run. A relative value for either variable is ignored.

## Debug in VS Code

1. Open this repository in VS Code.
2. Install the recommended Python extension when VS Code offers it.
3. Press F5.
4. The debugger runs `server.py` in the integrated terminal.

`.vscode/launch.json` names that launch "Python: Run server.py". A second launch, "Python: Current File", debugs the open file. "Python: Debug Tests" runs `unittest` discovery for `tests/`. Those launches use the system Python. The desktop window uses `.venv`. Format on save is on. The explorer hides `__pycache__` and `*.pyc`.

## Containers

```mermaid
C4Container
title Serato web library

Person(dj, "DJ", "Browses and edits the library in a browser")
Container(page, "static/", "HTML, CSS, JavaScript", "Crate tree, track list, and track detail")
Container(server, "server.py", "Python HTTP server", "JSON API on 127.0.0.1 port 8765")
Container(library, "library.py", "Python", "Reads and writes the Serato SQLite schema")
Container(tags, "tags.py", "Python", "Reads cue, loop, flip, and beatgrid frames")
Container(related, "related.py", "Python", "Saved links and key, BPM, and crate suggestions")
ContainerDb(master, "master.sqlite", "SQLite", "Library Serato displays")
ContainerDb(root, "root.sqlite", "SQLite", "On-disk location database")
ContainerDb(sidecar, "related.sqlite", "SQLite", "Links beside settings.json")
Container(audio, "Audio file", "ID3 GEOB", "Markers2 and BeatGrid frames")

Rel(dj, page, "Uses")
Rel(page, server, "HTTP", "127.0.0.1:8765")
Rel(server, library, "Calls")
Rel(server, related, "Calls")
Rel(server, page, "Serves files")
Rel(library, master, "Reads and writes")
Rel(library, root, "Mirrors a write")
Rel(library, tags, "Reads markers")
Rel(related, sidecar, "Reads and writes")
Rel(related, library, "Reads tracks, writes one crate")
Rel(tags, audio, "Reads the tag header")
```

## Modules

`server.py`, `library.py`, `related.py`, `tags.py`, `desktop.py`, `telemetry.py`, `app_config.py`, `app_log.py`, `build_config.py`, `static_assets.py`, and `scripts/release_bundle.py` document each function with a Google-style docstring. The tests do the same. `static/app.js` documents each function. `static/index.html` and `static/app.css` open with a header comment that states the file's role.

### `server.py`

`serve` binds `ThreadingHTTPServer` to `127.0.0.1` port `8765` and exits when that port is already taken. `main` serves until Ctrl-C. The handler class is `Handler`. It logs each request and answers JSON with `Cache-Control: no-store`.

`app_root` locates `static/`. A PyInstaller build reads it from `sys._MEIPASS`. A source checkout reads the directory beside `server.py`.

`desktop.py` imports `webview` (pywebview 6.2.1), calls `serve`, and opens `http://127.0.0.1:8765` in a native window. The window allows text selection. pywebview uses WKWebView on macOS and WebView2, through the WinForms backend, on Windows. The import stays in `desktop.py`, so the server and the tests do not require the package.

When `SERATO_LIBRARY_SMOKE` is an absolute file path, `smoke_check` runs first and `main` returns. The check confirms the bundled page through `server.app_root()`, writes `ok\n` to that path, and does not import pywebview, bind a port, open the library, or start telemetry. A relative path, a symlink, a directory, or a missing parent directory stops the process. The windowed build has no console, so the marker file is the signal the release check reads.

`static_assets.py` lists local `src` and `href` files in `static/index.html`. Remote URLs, anchors, and data URLs are skipped. `serato-library.spec` exits before it analyzes the program when one of those files is missing. The release zip check compares the same files, byte for byte, with the source tree.

A GET path under `/api/` runs a query. Any other GET path is a file in `static/`. The request is joined to that directory and passed through `os.path.realpath`. It is served only when the result starts with the directory plus a separator and the result is a file. `index.html` answers `/` and an empty path. Anything else returns 404.

`load_library` caches one payload per space. The cache key is the size and modification time of `master.sqlite` and its WAL file. A cache miss can record `library_scanned` with a track-count bucket. A POST takes a process lock, drops that cache, then writes. Settings and log routes are answered before that lock.

The HTTP banner is `SeratoLibrary/1.0`. A release tag does not change that banner. The app version is `app_config.APP_VERSION` (`0.1.1`). `__version__` is that same string. Sentry's release and PostHog's `app_version` read the constant.

`load_track` returns every column listed in `FIELDS`, plus the edit form, crate membership, near-duplicate copies, Prepare membership, the resolved file path, and marker data. Copies share title, artist, and length in whole seconds. The query returns at most 12 copies.

Blank display values use a dash. Dates use English month names, so the label does not follow the machine locale. Colors other than `0xFFFFFF` render as `#RRGGBB`. `third_party_type` maps `0` to Local file, `1` to iTunes, and `6` to Apple Music.

Allowed spaces are `Serato Library`, `Serato Video`, `Apple Music`, and `Prepare`. A missing space name means `Serato Library`.

### `library.py`

`default_library_path` chooses the live database: Application Support on macOS, and `%LOCALAPPDATA%\Serato\Library\master.sqlite` on Windows. `MASTER` starts as that path. Reads use a read-only SQLite URI and `PRAGMA query_only=ON`.

`status` reads the `lock` table. A row counts as open only when the process image contains `serato`. macOS and other Unix systems ask `ps`. Windows asks `tasklist`. A locked database also counts as open. `writable` is false in both cases. The payload includes `file_manager`: `Finder` or `File Explorer`.

`begin_write` refuses the call when Serato is open (`SeratoOpen`, HTTP 409). It then calls `ensure_backup` and opens `BEGIN IMMEDIATE` with a one-second timeout. Foreign keys are off for the write. The backup folder is `Library/Backups/serato-web-<timestamp>/` beside `master.sqlite`. The copy includes `root.sqlite` when that file sits beside the master database. One process backs up a given master path once. After that copy, `backup_made` can be recorded. The backup path is not a property of the event.

`register` installs `serato_str_norm` and `serato_raw_key_string_to_key_type` on a write connection. The key function maps Camelot and traditional names onto Serato's integer key.

Nested crate names in the database use `NAME_SPLIT` (`U+105E8A`). `display_name` keeps the text before that character.

Container type `0` is the space root and stays out of the crate list. Type `2` is a smart crate. Smart-crate rules are JSON in `smart_crate_rules`.

A write to a track or crate updates `master.sqlite`, then mirrors the change into the location database from the `connection` table. Location id `3` falls back to `root.sqlite` beside the master file. A test database whose path is not the live master mirrors only files in the same directory, or under `/tmp/`. A missing drive, or a database or filesystem error while mirroring, produces a warning and leaves the audio file in place. Any other mirror error propagates.

`save_track` accepts `name`, `artist`, `album`, `genre`, `year`, `composer`, `remixer`, `label`, `grouping`, `comments`, `key`, `emoji`, `bpm`, `color`, `rating`, `is_beatgrid_locked`, and `portable_id`. A new `portable_id` also sets `file_name`, clears `is_missing`, and records `file_size`. If that file's size cannot be read, the save is refused. Every save sets `time_modified`.

`crate_action` accepts `create`, `rename`, `delete`, `color`, `expanded`, `rules`, `add`, `remove`, `prepare`, and `remove_library`. Delete removes the crate and its descendants. `remove_library` removes the track from the space and its crates. It does not delete the audio file. `prepare` adds or removes the track in the Prepare space.

`history_sessions` and `history_entries` read `history_session` and `history_entry`. `duplicate_groups` groups tracks in one space by title, artist, and length in whole seconds. Rows with an empty title, an empty artist, or no length are skipped. Asset ids in a group are sorted.

`merge_duplicates` folds one of those groups into the copy you keep. `preview` true returns the plan and does not write. A merge requires `confirm` true. The master changes run in the `begin_write` transaction. Each location database is mirrored afterwards, in its own transaction, the same way other writes are. Serato open returns 409 before the backup. A preview still returns the plan when Serato is open, with `writable` false. That gap is intentional: the plan is readable, and the write path refuses before it copies a backup.

The kept track is added to every normal crate any duplicate was in, in any space, so a Prepare crate is included. Smart crates and the space root are left alone. If the kept track is already in a crate, it stays at its current position. Otherwise it takes the earliest duplicate's `list_order` in that crate. The location database receives the new membership with that same position when the column exists. A track that is already in the drive crate is not moved.

Empty text (album, genre, year, composer, remixer, label, grouping, comments, key, emoji, disc, track number, and the comment language fields) and an empty BPM are filled from the first duplicate, in asset-id order, that has a value. Text longer than the field limit is skipped. Play count and rating keep the highest number, treating a missing value as lower than a real one. White (`0xFFFFFF`) or a missing color is filled from the first real color. Date added keeps the earliest timestamp. Recently played is set when any copy was recently played. Filling the key also sets `key_value`. `is_beatgrid_locked` is not copied, because the lock belongs to that file's beatgrid. Path, file name, file size, bitrate, sample rate, length, and the missing flag stay with the file you keep.

`history_entry.asset_id` is repointed when that column exists. The played name and file name on the history row stay as a snapshot of what was played. The same repoint is applied in a location database that has the column, using that database's asset ids. Duplicate rows are then removed from space membership, crate membership, and the asset table. The location database removes the same memberships and deletes the location asset row, so Serato does not recreate the duplicate from the drive. A duplicate that shares the kept track's location asset id is left in the drive database. A track whose location is not the main drive (`location_id` 3) is removed from the master library, and that other drive is left unchanged, matching `remove_library`. When several of those mirrors are skipped, `warning` says so once. A shared drive record, or a file that could not be moved to the Trash, is reported in addition to that sentence.

Cue points are read with `tags.read_serato_tags`. They are not written back. When the kept file has no cues, loops, flips, or beatgrid and a duplicate file does, the plan includes `cue_warning`. The markers stay in the other audio file. Rewriting the ID3 tag can drop Serato's frames, so there is no copy step.

`delete_files` defaults off. Turning it on also requires `confirm_delete_files` true. The move is refused, before `begin_write`, when a duplicate path is a symlink, a directory, the same file as the kept copy (including a hard link), named `master.sqlite` or `root.sqlite`, or inside the library database folder. A sibling folder whose name only starts with the library folder's name is not treated as inside it. Files that pass are moved to the Trash after the database commit: Finder on macOS, the Recycle Bin on Windows, and the FreeDesktop trash specification elsewhere. A failed move leaves the file on disk and returns a warning. The library change is already committed. A missing file is skipped. The response lists file names, not paths.

`export_m3u` writes an extended M3U for one crate or for the whole space. A track with no path is named in a `# omitted, no path` comment and left out of the playlist. A missing length is written as `-1`. `import_m3u` creates a normal crate and adds tracks whose `portable_id` matches a playlist path. Unmatched paths stay out of the crate. The result lists at most 50 of them.

`reveal` shows the resolved audio file in the host file manager. macOS runs `open -R`. Windows runs `explorer /select,`. `markers_for` calls `tags.read_serato_tags` when the file is on disk. A successful read can record `tags_read`. The audio path is not a property of the event. A duplicate merge reads markers through `read_serato_tags` directly and does not record `tags_read`.

`update_related_path` rewrites a path in the related-tracks sidecar after a file move. It does not open `master.sqlite`. The implementation is `related.update_path`.

### `related.py`

`related_db_path` is `related.sqlite` beside `settings.json`. The schema is version 1 (`PRAGMA user_version`) and is documented in [related-tracks.md](related-tracks.md). Reads and writes of that file do not take the Serato lock.

A track key is a normalized absolute path. `~` is expanded and `.` and `..` are collapsed. Symlinks are not followed, and the request path is not used to test whether a file exists. A track in the open library uses the path the library already resolved. Title, artist, and length in whole seconds are a fallback when exactly one stored row matches and that path is not still a different track in the library. `update_path` is what a file move calls. `add_link` stores a one-way or two-way link with an optional note and a rating from 1 to 5. `remove_link` deletes the link and keeps the identity rows. `overview` returns saved links and suggestions. `refresh_crate` creates or replaces a normal Serato crate named `Related - ` plus the track title. That call writes `master.sqlite` through `crate_action`, so Serato must be quit and the backup rules apply.

Suggestions rank other tracks in the space by Camelot key (same, relative, or one step on the wheel), BPM within 6 percent including half time and double time, and shared normal crates. Crates whose names start with `Related - ` are not counted. At most 12 suggestions are returned. They are not stored.

### `tags.py`

`read_serato_tags` reads. It does not write audio. It scans the first 2,000,000 bytes and, for a longer file, the last 512,000 bytes. It collects ID3 GEOB frames named `Serato Markers2` and `Serato BeatGrid`.

Markers2 is base64 after a `01 01` header. Each entry is `CUE`, `LOOP`, or `FLIP`. A cue has index, start in milliseconds, color, and name. A loop adds end time and a locked flag. A flip has index, enabled, and name. Duplicate merge uses this read to decide whether to warn. It does not write a GEOB frame.

BeatGrid version byte `1` yields markers. Each marker has a position in seconds. The last marker stores BPM. Earlier markers store a beat count. More than 4096 markers, or a payload shorter than the declared marker count, returns an empty list.

### `static/`

`index.html` is one screen. The rail holds the status line, the space menu, and five views: Crates, History, Missing, Duplicates, and Stems. Crate tools search, sort, create, and import an M3U. The sheet holds the track search, the virtualized list, and the detail pane.

`app.js` keeps library state in `state`. The list paints only the rows inside the scroll window. Row height is 36 pixels. Track sort keys include name, artist, album, BPM, key, and the other columns the header exposes. Crate sort is custom order, name, or date added.

The detail pane edits the fields `save_track` accepts, shows marker sections, lists near-duplicate copies, and offers crate membership, Prepare, reveal in the host file manager, and remove from the library. In the Duplicates view it also offers Merge copies. It also lists saved related tracks, searches the loaded tracks to add a link, removes a link, and can write the `Related - ` crate. A successful crate write reloads the library so the new crate appears in the tree. Suggestions show the reason text from `GET /api/related` and save with one click. Notes and titles are set with `textContent`. The reveal label uses `file_manager` from the track status. Writes stay disabled while `writable` is false. Color choices are None, Red, Orange, Yellow, Green, Blue, Purple, and Pink.

Merge copies opens a dialog. The radios choose the file to keep. The dialog then shows the plan: crates, spaces, fields, history rows, and a cue warning when the kept file has no markers and another copy does. Date added in that list includes the year and the seconds. Cancel closes the dialog. Merge copies sends `confirm` true. Move the other audio files to the Trash is off until checked, and the confirm button then reads Merge and move files to Trash. The checkbox stays disabled when a file cannot be moved safely or is not on disk. The Merge copies button stays disabled while Serato has the library open. A preview request still returns the plan in that state, with `writable` false, and the confirm button stays disabled when that flag is false.

The rail ends with Settings. The first launch opens a dialog whose heading is "Share anonymous usage stats and crash reports?" **Don't share** is focused. Esc or closing the dialog saves a decline. Settings holds the same choice as a checkbox, plus **Open logs folder** and **Copy logs**. The page does not load a third-party analytics script, and it does not insert log text with `innerHTML`.

`app.css` is the layout and color for that screen.

## Sharing and logs

`telemetry.py` is the gate. `capture` returns false, and does not queue the event, unless the saved choice is the boolean `True` and `POSTHOG_KEY` is non-empty. `capture_exception` returns without sending unless the choice is `True` and `SENTRY_DSN` is non-empty. A missing package is the same as a missing key: that service stays off. Clients start in `activate`, which `serve` calls after the port is bound, and which `set_consent(True)` calls when the person opts in. `shutdown` runs when the server or the desktop window stops. The smoke path returns before `serve`, so it does not start a client.

Keys are read from the environment first, then from `_build_config.py`. The committed file sets `SENTRY_DSN`, `POSTHOG_KEY`, and `POSTHOG_HOST` to empty strings. `scripts/write_build_config.py` overwrites that file for a release build. `POSTHOG_HOST` falls back to `https://us.i.posthog.com`. The script prints `yes` or `no`. It does not print the value.

The events are `app_opened` (once per process after consent), `library_scanned`, `crate_created` (a created crate, or a crate created by an M3U import), `backup_made`, `tags_read`, `related_link_saved`, `related_link_removed`, `related_crate_written`, and `duplicates_merged` (a confirmed merge, not a preview). Properties this process adds are `app` (`serato-library-manager`), `app_version` (the same `app_config.APP_VERSION` string Sentry uses as its release), `os`, for a scan, `track_count_bucket`, and for `related_link_saved`, `link_direction` (`one_way` or `two_way`). Buckets are `0`, `1-9`, `10-49`, `50-99`, `100-499`, `500-999`, `1000-4999`, `5000-9999`, and `10000+`. The exact count is not sent. `duplicates_merged` has no extra properties: no kept id, no removed count, no title, and no path. The PostHog client may also attach its Python and library version fields. A before-send hook drops any other property, including a title or a path, and drops the event if consent is no longer granted. GeoIP is disabled. Feature-flag polling and exception autocapture are off.

Sentry uses `server_name` `local`, environment `local`, release `app_config.APP_VERSION` (`0.1.1`), and the tag `app=serato-library-manager`. `send_default_pii` is false. Local variables, source context, and request bodies are off. Argv and logging integrations are disabled. Framework auto-enabling is off. `before_send` returns `None` when consent is off. Otherwise it removes request data, frame variables, and absolute paths. A path becomes `[path]`. A final component ending in `.py` is kept as the file name.

`app_config.py` stores `settings.json` with `install_id` and `telemetry_consent`. The id is a random UUID, created when the choice is saved, not before. `None` means the prompt is still due. `False` is a saved decline. The file is written only when both fields are set. A corrupt file is renamed to `settings.json.unreadable`. The directory is `~/Library/Application Support/Serato Library` on macOS, `%APPDATA%\Serato Library` on Windows, and `$XDG_CONFIG_HOME/serato-library` (or `~/.config/serato-library`) elsewhere. `SERATO_LIBRARY_CONFIG_DIR` overrides it when the value is absolute. `related.sqlite` is in that same directory. Its schema is in [related-tracks.md](related-tracks.md).

`app_log.py` writes `serato-library.log` with `RotatingFileHandler`: 1 MiB and three backups. The directory is `~/Library/Logs/Serato Library` on macOS, `%LOCALAPPDATA%\Serato Library\Logs` on Windows, and `$XDG_STATE_HOME/serato-library/logs` (or `~/.local/state/serato-library/logs`) elsewhere. `SERATO_LIBRARY_LOG_DIR` overrides it when the value is absolute. The startup line can include the database path. That file is not uploaded. Copying the log skips a symlink and skips a file that is not inside the log directory, and it keeps the newest 200,000 characters. Opening the folder runs `open` on macOS, `xdg-open` elsewhere, and `os.startfile` on Windows. The response does not include the path.

## HTTP API

The server accepts JSON objects up to 2,000,000 bytes. A larger body returns 413. Invalid JSON returns 400. Serato open or a database lock returns 409 with a `serato` object: `open`, `writable`, `pid`, `process`, `message`, and `file_manager`.

| Method | Path | Query or body | Result |
|--------|------|---------------|--------|
| GET | `/api/status` | none | Lock status |
| GET | `/api/library` | `space` | Tracks, crates, rules, counts |
| GET | `/api/track` | `id`, `space` | One track, or 404 |
| GET | `/api/history` | none | `{ "sessions": [...] }` |
| GET | `/api/history` | `session` | One session and its entries |
| GET | `/api/duplicates` | `space` | Groups, plus `count` |
| GET | `/api/related` | `path`, optional `space`, `title`, `artist`, `length_ms` | Saved links and suggestions. See [related-tracks.md](related-tracks.md) |
| POST | `/api/duplicates/merge` | `keep_id`, `space`, `preview`, `confirm`, `delete_files`, `confirm_delete_files` | Plan. `preview` true does not write. A merge needs `confirm` true. Moving files also needs `confirm_delete_files` true |
| GET | `/api/export.m3u` | `space`, `crate` | M3U file `crate.m3u`. `crate=all` exports the space |
| POST | `/api/track` | `id`, `space`, `fields` | Saves track fields |
| POST | `/api/crate` | `action` plus ids and fields | Crate or membership change |
| POST | `/api/import.m3u` | `space`, `parent`, `name`, `text` | New crate from playlist text |
| POST | `/api/reveal` | `id` | Reveals the file in Finder or File Explorer |
| POST | `/api/related` | `action` `add`, `remove`, or `crate` | Saves or removes a sidecar link, or writes the `Related - ` crate |
| GET | `/api/settings` | none | `telemetry_consent` (`true`, `false`, or `null`), `needs_consent_prompt`, `telemetry_configured`, `app_version`. The install id and the keys are omitted |
| POST | `/api/settings` | `telemetry_consent` | Saves the boolean choice. Any other field, or a non-boolean, returns 400 |
| GET | `/api/logs` | none | `{ "text", "truncated" }` from the local log. The text can contain a path. It is not a report |
| POST | `/api/logs/open` | none | Opens the logs folder. `{ "ok": true }`. The path is not in the body |

`GET /api/settings` and `GET /api/logs` do not take the library write lock. `POST /api/settings` and `POST /api/logs/open` are handled before that lock. `GET /api/related` and `POST /api/related` with `add` or `remove` write only the sidecar file and do not take that lock. `action` `crate` takes the lock, then `library.crate_action`. An unexpected handler error returns 500 with "Something went wrong. The details are in the local log." A `LibraryError` is still returned as its own JSON and is not sent as a crash report.

`GET /api/library` crate objects use `id`, `parent`, `name`, `smart`, `order`, `color`, `expanded`, `added`, `tracks`, and `rules` on smart crates. The space root crate is omitted. `root_id` is returned separately.

## Write path

```mermaid
sequenceDiagram
participant Page
participant Server
participant Library
participant Backup
participant Master

Page->>Server: POST /api/track, /api/crate, or /api/duplicates/merge
Server->>Library: status()
alt Serato holds the lock
Library-->>Page: 409
else Serato is quit
Library->>Backup: Copy master.sqlite on the first write
Library->>Master: BEGIN IMMEDIATE
Library->>Master: Update the row
Library->>Master: Mirror into the location database
Library-->>Page: ok, plus a warning when the mirror is skipped
end
```

1. Quit Serato DJ Pro.
2. Edit a field, a crate, or a duplicate merge in the page.
3. Confirm the status line says edits save to the library.
4. Leave the audio file in place. Cue data stays in the file.

A full ID3 rewrite from another program can drop Markers2 and BeatGrid. This program does not rewrite those frames.
