# unittest fixtures

Shared setup lives in `tests/fixture.py`. A test gets a database by entering `TempLibrary`. There is no `conftest.py` and no pytest fixture scope. Snippets assume `import os`, `import tempfile`, `import unittest`, `import library`, and `from server import require_space`.

## Temporary library

```python
from tests.fixture import TempLibrary

class CrateTests(unittest.TestCase):
    def test_lists_the_seeded_track(self) -> None:
        with TempLibrary() as temp:
            self.assertEqual(temp.db.name, "master.sqlite")
```

`TempLibrary` builds `master.sqlite` with the Serato-shaped schema, points `library.MASTER` at it, and clears the server cache. On exit it restores `library.MASTER`, drops the cache, and deletes the directory. An open SQLite handle fails that cleanup with `RuntimeError`. Close every connection the test opened.

Importing `tests.fixture` does not redirect `library.MASTER`. The switch happens in `__enter__`.

`open_database` is the context manager for a connection. Use it when the test needs a handle. Do not leave the connection open across the end of the `with TempLibrary()` block.

## setUp and addCleanup

Use `setUp` when several methods share a value that is not the library file. Register the undo with `addCleanup` so it runs when the test fails, not only when it passes.

```python
class PathTests(unittest.TestCase):
    def setUp(self) -> None:
        self._previous = os.getcwd()
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.addCleanup(os.chdir, self._previous)
        os.chdir(self.tmpdir.name)
```

`addCleanup` runs in reverse order, after `tearDown`.

## Patches

```python
def test_reveal_command_is_an_argument_list(self) -> None:
    command = library.reveal_command("/tmp/track.mp3")
    self.assertIsInstance(command, list)
    self.assertGreaterEqual(len(command), 2)
```

`reveal` itself takes an asset id and calls `subprocess.run(reveal_command(path), check=False)` with no `shell`. Patch `library.subprocess.run` where the code looks the name up, not only the `subprocess` module. `reset_mock()` alone keeps `return_value` and `side_effect`.

## Several inputs

```python
def test_spaces(self) -> None:
    for name in ("Serato Library", "Prepare"):
        with self.subTest(name=name):
            self.assertIsNotNone(require_space(name))
```

`subTest` reports the failing value. It is the replacement for a parameter list. The method still counts as one test.

## What this file does not cover

Property tests, fixture scopes (`session`, `module`), and `pytest.fixture` factories are not used. A generated case belongs as an explicit `subTest` row whose expected value you computed, or as its own method.
