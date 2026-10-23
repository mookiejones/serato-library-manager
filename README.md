# Serato web library

A local page for the Serato DJ Pro library on this Mac.

## Run

1. Quit Serato DJ Pro.
2. From this directory, run `python3 server.py`.
3. Open `http://127.0.0.1:8765`.

The program uses the Python standard library. It reads `~/Library/Application Support/Serato/Library/master.sqlite`. Writes wait until Serato has quit. Press Ctrl-C to stop the server.

In VS Code, press F5. That launch runs `server.py`.

## Tests

From this directory, run:

```bash
python3 -m unittest discover -s tests -t . -v
```

The tests use the Python standard library. They build a temporary database. They do not open the live Serato library.

## Documentation

The code reference is [docs/architecture.md](docs/architecture.md). Functions in `server.py`, `library.py`, and `tags.py` use Google-style docstrings.
