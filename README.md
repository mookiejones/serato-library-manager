# Serato web library

A local page for the Serato DJ Pro library on macOS and Windows.

## Run

1. Quit Serato DJ Pro.
2. From this directory, run `python3 server.py`.
3. Open `http://127.0.0.1:8765`.

The server uses the Python standard library. On macOS it reads `~/Library/Application Support/Serato/Library/master.sqlite`. On Windows it reads `%LOCALAPPDATA%\Serato\Library\master.sqlite`. Writes wait until Serato has quit. Press Ctrl-C to stop the server.

The first launch asks "Share anonymous usage stats and crash reports?" Sharing stays off until you choose it. Settings in the sidebar keeps that switch, and can open or copy the local log. [PRIVACY.md](PRIVACY.md) lists what can leave the machine.

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

The code reference is [docs/architecture.md](docs/architecture.md). What the app can send is [PRIVACY.md](PRIVACY.md). Functions in `server.py`, `desktop.py`, `library.py`, `tags.py`, `telemetry.py`, `app_config.py`, and `app_log.py` use Google-style docstrings.
