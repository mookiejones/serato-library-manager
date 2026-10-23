# Serato web library

Local browser for the Serato DJ Pro library. Python standard library only. There is no package install, test runner, or linter.

## Run

```bash
python3 server.py
```

Serves `http://127.0.0.1:8765`. The process exits if `~/Library/Application Support/Serato/Library/master.sqlite` is missing. Stop it with Ctrl-C.

## Layout

- `server.py` is a `ThreadingHTTPServer` bound to `127.0.0.1:8765`. GET routes are `/api/library`, `/api/status`, `/api/track`, `/api/history`, `/api/duplicates`, and `/api/export.m3u`. POST routes are `/api/track`, `/api/crate`, `/api/import.m3u`, and `/api/reveal`. Any other path is a file under `static/`.
- `library.py` reads and writes `master.sqlite`. `root.sqlite` beside it is updated when it is attached. Writes are refused while a live Serato process holds the lock. The first write in a process copies both databases into `Library/Backups`.
- `tags.py` only reads Serato GEOB frames (`Markers2`, `BeatGrid`) from audio files. Rewriting an ID3 tag can drop those frames.
- `static/` is `index.html`, `app.js`, and `app.css`. Views are crates, history, missing, duplicates, and stems. Spaces are Serato Library, Serato Video, Apple Music, and Prepare.
- `docs/serato-library-tools.md` is research notes, not runtime config.

## Library safety

The database lives outside this repo. Quit Serato before a write. Do not commit a copy of `master.sqlite`. Cue points live in the audio file, not in the crate row.
