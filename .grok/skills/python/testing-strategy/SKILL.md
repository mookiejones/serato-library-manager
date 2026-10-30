---
name: testing-python-libraries
description: Designs unittest suites for this repo, and Vitest tests for the page. Use when adding a test, checking a regression, or deciding whether a green run actually covers the change. The Python suite is unittest, not pytest or Hypothesis.
---

# Testing

Python tests are `unittest`. Page tests are Vitest. There is no pytest config, no Hypothesis, and no coverage fail-under.

```bash
python3 -m unittest discover -s tests -t . -v
python3 -m unittest tests.test_server.FormatTests.test_blank_and_bpm -v

npm test
npm run check
```

CI runs the unittest command on Ubuntu (Python 3.12 and 3.14) and Windows (Python 3.12), and runs `npx tsc --noEmit`, ESLint, `npm test`, and `node scripts/build_frontend.mjs --check` for the page. A local green run uses those commands, not a different runner. `reproducing-ci-locally` covers matching the workflow when the failure is environmental.

## Layout

`tests/fixture.py` inserts the repo root on `sys.path` and builds a temporary Serato-shaped database. `TempLibrary` points `library.MASTER` at that file for one `with` block and restores it on the way out. Tests do not open a person's real library.

```
tests/
├── fixture.py            # TempLibrary, open_database, schema
├── test_server.py
├── test_library.py
└── ...
src/
├── wizard.test.ts        # Vitest, jsdom
└── ...
```

Import the module the code imports. `import server` must resolve to `server.py`. An empty `server/` directory next to it would shadow the module and a smoke import would still succeed.

## Patterns

A test method is the case. `subTest` is how one method holds several inputs. `setUp` and `addCleanup` replace a fixture. `unittest.mock.patch` replaces a monkeypatch.

```python
import unittest

from library import LibraryError
from server import blank, format_bpm, require_space


class FormatTests(unittest.TestCase):
    def test_blank_treats_zero_as_present(self) -> None:
        self.assertTrue(blank(None))
        self.assertFalse(blank(0))

    def test_known_bpm(self) -> None:
        # blank(None) is an em dash, not an empty string.
        cases = [(120, "120"), (None, "—")]
        for bpm, expected in cases:
            with self.subTest(bpm=bpm):
                self.assertEqual(format_bpm(bpm), expected)

    def test_refuses_a_bad_space(self) -> None:
        with self.assertRaisesRegex(LibraryError, "not available"):
            require_space("nope")
```

```python
class LibraryTests(unittest.TestCase):
    def test_reads_the_temp_library(self) -> None:
        with TempLibrary() as temp:
            self.assertTrue(str(temp.db).startswith(tempfile.gettempdir()))
```

`TempLibrary.__exit__` closes the database and deletes the directory. A connection left open fails that cleanup on purpose. Do not catch that `RuntimeError` and continue.

Patch at the boundary the code calls, then assert the result:

```python
def test_ps_failure_counts_as_running(self) -> None:
    failed = subprocess.CompletedProcess(["ps"], 1, stdout="", stderr="ps failed")
    with mock.patch("library.subprocess.run", return_value=failed) as run:
        self.assertTrue(library._unix_process_is_serato(1))
    run.assert_called_once()
```

Patching `library.subprocess.run` is the boundary. Patching a private helper that builds the command, and asserting only the argv you wish it used, stays green after the helper is renamed.

Page behavior goes in `src/*.test.ts` and runs under Vitest. Do not reimplement a DOM test as unittest.

## Principles

| Principle | What it means here |
| --- | --- |
| Independent | `TempLibrary` restores `library.MASTER`. A test does not depend on order. |
| Deterministic | No live Serato process, no network, no wall clock. |
| Focused | Assert the behavior a person or the page sees. |
| Able to fail | A mutation of the fix turns this test red. See below. |

## Tests that stay green when the code is wrong

**A conditional assertion.** If the setup failed, the body never runs and the test passes.

```python
def test_export_lists_the_track(self) -> None:
    text = export()
    self.assertTrue(text)  # fails when export returned nothing
    self.assertIn("same-a.mp3", text)
```

**An `or` that cannot fail, or a substring that matches the wrong token.** `self.assertIn("ui", tags)` also matches `"build"`. Assert the whole value.

**Presence is not count.** `self.assertIn("canonical", html)` passes with two conflicting tags. Extract every match and compare the list.

```python
canonicals = re.findall(r'<link rel="canonical" href="([^"]*)"', html)
self.assertEqual(canonicals, ["https://example.com/guide/"])
```

**A fake that ignores the argument under test.** If the fake returns every row no matter what `space` or `after` is, the filter is untested. Honor the parameter.

**A smoke import.** `python -c "import server"` can import the wrong file. Call a symbol: the test module imports `serve` or a handler and asserts a value.

**A forgotten patch that hits the machine.** `library.py` shells out to `ps` or `tasklist` to see if Serato is running. Patch `subprocess.run` in that test. An unpatched call reads the real process table and the result depends on the runner.

**A filter that matches nothing.** If the code treats "no rules selected" as "nothing wrong", the test needs a subject that would fail when a rule actually runs, and an assertion that at least one check ran. An empty list is not a pass.

**A test written around the bug.** `try` / `except` that swallows the error documents the bug as allowed. Assert the behavior you want. `@unittest.expectedFailure` tracks a known failure; an unexpected pass is an unexpected success and fails `wasSuccessful()`.

## Prove the test can fail

Revert the fix, run that one test, and confirm it fails for the reason you think. Restore the fix and confirm it passes.

```bash
# One method, not the whole suite. Name the test you just added.
python3 -m unittest tests.test_files.FileManagerTests.test_refusals_leave_the_disk_and_skip_the_backup -v
```

When the guard is two checks, revert each one on its own. For `files._contained`, a `..` name and a symlink inside the directory are different mutations. If reverting one half leaves the suite green, that half is untested.

Also test a plausible wrong fix, not only the original bug. Two identical labels catch a map that overwrites. A label that already contains the generated suffix catches a counter that does not look at keys it already issued.

Know what red looks like for the mutation you picked:

- Removing a timeout can hang. Run under `timeout 60` and treat silence as the failure.
- A mutation that breaks collection means no test ran.
- `git diff --stat` should show the mutation before you read the result. BSD `sed -i` can take the next argument as a backup suffix and edit nothing.

A fixture you typed by hand can share the bug's assumption. Keep one fixture taken from a real file when the parser is what you are testing, and point the test at that.

## A surviving mutation

If you delete a branch and the suite stays green, try to find an input where the results differ. If you cannot, the branch is inert. Delete it or leave it, and do not name a test as if it guards it.

Some branches only matter for one construction path. A fixture that went through the normal loader will not hit a guard that exists for a hand-built object. Build the object the way the failing path does.

Say so when you report it: the branch does not change behavior, and no input distinguishes it.

## Both directions

A new conditional can fail two ways: it never fires, or it always fires. Write the test for each.

| Mutation | Test that goes red |
| --- | --- |
| Condition removed, warning never happens | The case that should warn |
| Condition inverted or dropped, warning always happens | The healthy case that must stay quiet |

The healthy-case test looks vacuous because it passed before the fix too. It is the one that catches the over-broad mutation. Keep it.

`if not value` fires for `None` and also for `[]`, `0`, and `""`. Use `is None` when only the missing value is the signal. A new warning that lights up existing empty-list fixtures is the over-broad mutation, not a fixture to update.

Revert one part of a fix at a time and record which test fails. A part whose removal stays green is a gap.

## Edge cases that pass on the unfixed code

"Empty input returns 0" often passed before the fix, because `sum([])` or a count of `""` was already 0. Run the new test against the pre-fix code. Only the tests that go red are regression tests. Name the others as edge behavior.

The bug and the wrong fix need different data. A phrase whose words appear only apart catches an "all words present" rewrite. A text that contains only the first word catches first-token matching. One fixture rarely covers both.

## Pick values that separate the bug from the fix

If the buggy code and the fixed code return the same number on your fixture, change the fixture.

- Order-sensitive reads need ends that differ. A one-row fixture makes "first" and "last" agree.
- A per-group gap and a global gap agree on most rows unless the groups are interleaved so every row differs. Assert the numbers and the blank count.
- A fixture that omits a header does not catch a redundant 60 second wait when the legitimate fallback is also 60 seconds. Supply a header that makes the legitimate wait different.
- Record the call sequence. A stub that returns `None` answers "did it get called?" and misses an extra call. Append the arguments and assert the list.

## Changing a value an existing test pins

Read the assertion before changing the output.

1. The assertion only checks a type or a substring. It is not coverage. Tighten it or leave it.
2. The assertion pins the correct value. Your change is the regression. Stop.
3. The assertion pins the bug. Update it, and search the suite for the old text, not only the test named in the issue.

```bash
rg -n 'HeadingBody text' tests src
```

Prefer a relationship over a magic constant when the number comes from another program. If you pin a number, compute it and paste it. Do not estimate. Size a tolerance to the gap between the bug and the fix.

`unittest` has no `pytest.approx`. For a tiny non-zero result, a fixed absolute tolerance treats `0.0` as close to `1e-200`. Use a relative check and reject a non-finite result:

```python
def test_scale_preserves_a_tiny_value(self) -> None:
    result = scale(1e-200)
    self.assertTrue(math.isfinite(result))
    self.assertTrue(math.isclose(result, 1e-200, rel_tol=1e-12, abs_tol=0.0))
```

Keep a separate exact-zero case. Relative error is undefined at zero.

To see the old number without checking out the old tree:

```bash
git show main:server.py > /tmp/old_server.py
```

Load that file with `importlib` only in a throwaway probe. Do not leave it imported from a test.

## Where output goes

Build the redirect in the test body, around the call that configures the logger. A redirect installed earlier is easy to undo before the call runs, and the test then looks empty unless `-s` is passed (that flag is pytest; under unittest the symptom is an empty buffer and the text on the real stderr).

```python
def test_log_line_goes_to_stderr(self) -> None:
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        configure_logging()
        logging.getLogger("app").info("hello")
    self.assertIn("hello", err.getvalue())
```

Restore the root logger's handlers in `addCleanup` when the code calls `basicConfig`. Later tests inherit the handlers you left behind.

## Ambient state

Pin every input the code reads.

- `HOME` is not enough on Linux. Set `XDG_CONFIG_HOME` as well when the code resolves a config directory. macOS ignoring XDG is why the incomplete test passes on a laptop.
- A settings object built at import time runs before `setUp`. Construct it inside the test, or set the environment before the import. `tests/fixture.py` delays the database build until `TempLibrary.__enter__` so importing the fixture does not redirect `library.MASTER`.
- Clear a module-global cache at the start and in `addCleanup`. `mock.Mock.reset_mock()` clears calls and keeps `return_value` and `side_effect`. Pass `return_value=True, side_effect=True` to clear those too.
- Code that shells out inherits the working directory. `os.chdir` to an empty temporary directory first, and `addCleanup` the original directory, so a missing path argument cannot silently use the repo.
- Do not sleep to reach a time of day. Pass the clock in, or patch the function that reads it. Restoring the real clock mid-test makes a later assertion follow the runner's timezone.

## Threads

The server tests start a real `ThreadingHTTPServer`. "The thread was started" is not "the request finished". Wait until the server is bound, send the request, and assert the status and the body. On teardown, shut the server down and join the thread. A test that returns while the thread is still in `serve_forever` leaks into the next test.

## Checklist

```
- [ ] Python behavior is a unittest method; page behavior is a Vitest test
- [ ] The test uses TempLibrary or another temp path, never a real Serato library
- [ ] Edge cases include empty input, a boundary, and the error status
- [ ] subprocess, the clock, and the working directory are pinned when the code reads them
- [ ] Each regression test was red against the reverted fix
- [ ] A two-part guard was mutated one part at a time
- [ ] A surviving mutation was classified before a test was named for it
- [ ] A new conditional has a test for never-fires and a test for always-fires
- [ ] Absence is `is None`, not truthiness, where [] / 0 / "" are real
- [ ] Fixture values make the buggy and correct results differ
- [ ] Assertions that pin the old output were found with a search, not by test name
- [ ] The discover command and, for a page change, npm test were run
```
