# Serato web library

Local browser for the Serato DJ Pro library. Python standard library only. There is no package install or linter. Tests use `unittest`.

## Run

```bash
python3 server.py
```

Serves `http://127.0.0.1:8765`. The process exits if `~/Library/Application Support/Serato/Library/master.sqlite` is missing. Stop it with Ctrl-C.

## Tests

```bash
python3 -m unittest discover -s tests -t . -v
```

The suite builds a temporary database. It does not open the live Serato library.

## Layout

- `server.py` is a `ThreadingHTTPServer` bound to `127.0.0.1:8765`. GET routes are `/api/library`, `/api/status`, `/api/track`, `/api/history`, `/api/duplicates`, and `/api/export.m3u`. POST routes are `/api/track`, `/api/crate`, `/api/import.m3u`, and `/api/reveal`. Any other path is a file under `static/`.
- `library.py` reads and writes `master.sqlite`. `root.sqlite` beside it is updated when it is attached. Writes are refused while a live Serato process holds the lock. The first write in a process copies both databases into `Library/Backups`.
- `tags.py` only reads Serato GEOB frames (`Markers2`, `BeatGrid`) from audio files. Rewriting an ID3 tag can drop those frames.
- `static/` is `index.html`, `app.js`, and `app.css`. Views are crates, history, missing, duplicates, and stems. Spaces are Serato Library, Serato Video, Apple Music, and Prepare.
- `docs/serato-library-tools.md` is research notes, not runtime config.
- `docs/architecture.md` is the code reference. Update it in the same change as the behavior it describes.
- `tests/` is a `unittest` suite. `tests/fixture.py` points `library.MASTER` at a temporary database.
- `.vscode/launch.json` starts `server.py` on F5. "Python: Debug Tests" runs the suite. There is no project virtualenv.

## After a change

1. Update `docs/architecture.md` when behavior, the API, the layout, or the run path changes.
2. Update this file when the run command or the layout summary changes.
3. Commit the change. Do not push unless asked.

## Library safety

The database lives outside this repo. Quit Serato before a write. Do not commit a copy of `master.sqlite`. Cue points live in the audio file, not in the crate row.
