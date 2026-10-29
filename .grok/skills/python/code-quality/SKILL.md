---
name: improving-python-code-quality
description: Improves Python in this repo with pyright (pyrightconfig.json), Google-style docstrings, and ordinary Python idioms. Use when reviewing a change, adding type hints, or refactoring server.py, library.py, tags.py, or the unittest suite. This repo does not use ruff or mypy.
---

# Python code quality

Python in this repo has no linter. Type checking is pyright. Docstrings are Google style. Idioms below are the ones that have hidden bugs in this kind of code: mutable defaults, truthiness, silent fallbacks, and unordered serialization.

## Pyright

`pyrightconfig.json` is the config:

```json
{
  "typeCheckingMode": "strict",
  "pythonVersion": "3.14",
  "include": ["library.py", "tags.py", "server.py", "tests"]
}
```

pyright is not in `requirements.txt`, and CI does not run it. The frontend job typechecks `src/` with `npx tsc --noEmit`. When you change a file in the include list, run `pyright` locally if it is installed.

A file outside `include` is not checked. `files.py`, `snapshots.py`, `desktop.py`, and the other modules are invisible to this config. A new annotation there does not fail the check. Extending `include` is a separate change; do not assume a green pyright run covered a file it does not list.

Do not add ruff or mypy. Do not add a `py.typed` marker or a `src/` package layout. Modules live next to `server.py`.

## Docstrings

Google style, with `Args`, `Returns`, and `Raises`, on functions you add or edit. The `python-docstring-doctor` skill is the format. Match the docstrings already in `server.py` and `tests/fixture.py`: the summary is one imperative sentence, and a test docstring says what the test writes and what it refuses to write.

## Type hints

Annotate new functions. Prefer `list[str]`, `dict[str, int]`, and `str | None` over `Optional` and `List` aliases. Patterns for `Protocol`, `TypeVar`, overloads, and `TypedDict` are in **[TYPE_PATTERNS.md](TYPE_PATTERNS.md)**.

The page's JSON bodies are checked in TypeScript (`src/api-types.ts`), not by a Python model class. A Python `TypedDict` is useful when a handler reads the same keys in more than one place. It does not replace the TypeScript type.

## Idioms

```python
# Mutable default. The list is shared by every call.
def collect(items: list[str] = []) -> list[str]:
    items.append("x")
    return items

# New list each call. `items or []` is fine here because the only
# falsy input is an empty list, which is the same result.
def collect(items: list[str] | None = None) -> list[str]:
    items = items or []
    return items
```

```python
# `0`, `0.0`, `False`, and "" are real values. `or` replaces them.
hour = config.get("start_hour") or 9

hour = config.get("start_hour")
hour = 9 if hour is None else hour
```

`x = x or default` is safe only when no falsy value is meaningful. For a number, a boolean, or a string, use `is None`.

```python
# `is` against a literal depends on interning.
if name is not "":
    ...

if name != "":
    ...
```

```python
try:
    parse(raw)
except ValueError as exc:
    log.error("%s", exc)
```

A bare `except:` or an `except Exception` that returns a normal-looking result hides the failure. Catch the exception you can handle. Let the rest propagate. On a request, `LibraryHandler._report_failure` is the one place that catches everything, and it answers 500 with a fixed sentence rather than the exception text.

```python
for item in items:
    ...
for index, item in enumerate(items):
    ...

value = mapping.get(key, default)

with open(path, encoding="utf-8") as handle:
    text = handle.read()
```

Use a comprehension when it stays a single expression. A loop with a `try` inside is easier to read than a comprehension that hides the error.

## Fail loud

A failure that looks like success is the expensive bug.

- Do not set the success status in the `except` branch.
- Do not replace a failed read with an empty list and return it as the full result.
- Do not substitute sample data when a call fails.
- In a loop over files or tracks, collect the per-item error and return it. A bare `continue` drops the path with no record.
- A subprocess that exits non-zero may still have written the answer to stdout (`ps`, `tasklist`). Return the code together with stdout and stderr, or treat a timeout as the conservative result the caller already documents. `library._unix_process_is_serato` treats a timeout as "Serato is running" so a write stops.

## Deterministic output

Snapshot hashes and committed files change when iteration order changes. A `set` has no stable order across processes. Sort before you serialize.

```python
tags = [render(tag) for tag in sorted(tag_set)]
json.dumps(record, sort_keys=True)
```

`datetime.strptime` with `%b` or `%a` follows the machine locale. Format timestamps with an explicit English label, the way `format_when` does, so a test on a non-English runner matches CI.

## Checklist

```
- [ ] New annotations on files in pyrightconfig.json include pass pyright strict
- [ ] A file outside that include list was not described as typechecked
- [ ] New or edited functions have Google-style docstrings
- [ ] No mutable default argument
- [ ] Guards use `is None` where 0, False, or "" is valid
- [ ] No `is` / `is not` against a literal
- [ ] Exceptions are specific, or the 500 path uses the fixed sentence
- [ ] Sets and dict key order are sorted before hashing or writing
- [ ] No ruff, mypy, or py.typed config added
```
