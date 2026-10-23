# Serato web library

A local page for the Serato DJ Pro library on macOS and Windows.

## Run

1. Quit Serato DJ Pro.
2. From this directory, run `python3 server.py`.
3. Open `http://127.0.0.1:8765`.

The server uses the Python standard library. On macOS it reads `~/Library/Application Support/Serato/Library/master.sqlite`. On Windows it reads `%LOCALAPPDATA%\Serato\Library\master.sqlite`. Writes wait until Serato has quit. Press Ctrl-C to stop the server.

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

GitHub Actions runs the test suite, audits the pinned requirements, and publishes unsigned desktop zips. The server stays on `127.0.0.1`. It is not a website and it is not published to GitHub Pages. The guide is [docs/github.md](docs/github.md). Report a vulnerability in private, as [SECURITY.md](SECURITY.md) describes.

## Tests

From this directory, run:

```bash
python3 -m unittest discover -s tests -t . -v
```

The tests use the Python standard library. They build a temporary database. They do not open the live Serato library.

## Documentation

The code reference is [docs/architecture.md](docs/architecture.md). Functions in `server.py`, `desktop.py`, `library.py`, and `tags.py` use Google-style docstrings.
