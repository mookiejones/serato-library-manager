# Vulnerability pairs

The pairs below are the ones Bandit and a path review are for in this app. pip-audit covers dependency pins and is not a source pattern.

## SQL injection

Bandit B608. The sqlite3 driver binds values. It does not bind table or column names.

```python
# Vulnerable — request text becomes SQL
conn.execute(f"SELECT * FROM asset WHERE name = '{name}'")
```

```python
# Fixed — the value is a parameter
conn.execute("SELECT id FROM space WHERE name = ?", (space,))
```

```python
# Vulnerable — PRAGMA cannot take a placeholder, and the name came from the request
conn.execute(f"PRAGMA table_info({table_from_query})")
```

```python
# Fixed — the name is one the program already allows
if table not in {"asset", "container"}:
    raise ValueError(table)
conn.execute(f"PRAGMA table_info({table})")
```

## Command injection

Bandit B602 and B605. `shell=True` and `os.system` let a track title or a path change the command.

```python
# Vulnerable
subprocess.run(f"open {path}", shell=True)
```

```python
# Fixed — argument list. The process id is an int before it is interpolated
# into a single argv element, as library._unix_process_is_serato does.
subprocess.run(
    ["ps", "-p", str(int(pid)), "-o", "comm="],
    capture_output=True,
    text=True,
    timeout=2,
    check=False,
)
```

## Path traversal

A join is not a containment check. `files._contained` and `LibraryHandler.send_file` each do both steps.

```python
# Vulnerable — "../" climbs out, and a sibling directory shares the prefix
path = os.path.join(base_dir, filename)
open(path).read()
```

```python
# Fixed — reject a separator in the name, refuse a symlink, then compare
# the resolved parent to the resolved base.
if "/" in name or "\\" in name or "\x00" in name:
    raise ValueError(name)
base = directory.resolve()
candidate = base / name
if candidate.is_symlink() or directory.is_symlink():
    raise ValueError(name)
resolved = candidate.resolve(strict=False)
if resolved.parent != base:
    raise ValueError(name)
```

For a URL path mapped onto `static/`, realpath both sides and require the candidate to start with `root + os.sep`. A check of `startswith(root)` alone accepts `static-evil`.

Test the name check and the resolve check with different inputs. A `../` payload does not prove the symlink case, and a symlink case does not prove the name check.

## Secrets

Bandit B105 and B106. A string assigned to a name like `API_KEY` or `password` is the finding. The git copy of `_build_config.py` stays empty; release builds fill a different copy from Actions secrets.

```python
# Vulnerable — the key is in the commit, and the error body quotes a path
SENTRY_DSN = "https://example@o0.ingest.sentry.io/0"

def read_track(path: str) -> dict:
    try:
        return parse(path)
    except OSError as exc:
        return {"error": str(exc)}
```

```python
# Fixed — empty in git, and the response does not echo the exception
# _build_config.py
SENTRY_DSN = ""

def read_track(path: str) -> dict:
    try:
        return parse(path)
    except OSError:
        log.exception("Request failed")
        return {"error": "Something went wrong. The details are in the local log."}
```

Deleting a committed secret does not rotate it. The log line and the JSON body are different channels. The local log may keep the traceback. The JSON body may not.
