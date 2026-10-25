"""Release-key file tests.

The committed ``_build_config.py`` must stay empty. The writer is tested
against a temporary file so the suite does not bake a key into the tree.
"""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import _build_config
import build_config


ROOT = Path(__file__).resolve().parents[1]


def _pins(path: Path) -> dict[str, str]:
    """Return pinned requirement names and specifiers.

    Args:
        path: A requirements file.

    Returns:
        Mapping of package name to the full requirement line, for lines
        that pin with ``==``.
    """
    pins: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "==" not in stripped:
            continue
        name = stripped.split("==", 1)[0].strip().lower()
        pins[name] = stripped
    return pins


class BuildConfigTests(unittest.TestCase):
    """Check the baked key file and the writer.

    No network call is made. Secret-shaped strings exist only in memory
    and in a temporary file that the test deletes.
    """

    def test_committed_file_has_no_keys(self) -> None:
        """Keep the committed telemetry constants empty.

        A release build overwrites the file from secrets. The copy in git
        must not contain a DSN or a project key.

        Returns:
            None. The test fails if any constant is non-empty.
        """
        self.assertEqual(_build_config.SENTRY_DSN, "")
        self.assertEqual(_build_config.POSTHOG_KEY, "")
        self.assertEqual(_build_config.POSTHOG_HOST, "")

    def test_writer_quotes_values_and_hides_them_from_stdout(self) -> None:
        """Write repr-quoted assignments and print only yes or no.

        The DSN is present in the file and absent from the status line.

        Returns:
            None. The test fails if the secret is printed or unquoted.
        """
        secret = "https://public@o0.ingest.sentry.io/0"
        key = "phc_test"
        with mock.patch("tempfile.TemporaryDirectory"):
            pass
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "_build_config.py"
            stdout = io.StringIO()
            with mock.patch.dict(
                "os.environ",
                {"SENTRY_DSN": secret, "POSTHOG_KEY": key, "POSTHOG_HOST": ""},
            ):
                with mock.patch.object(build_config, "BUILD_CONFIG_PATH", path):
                    with redirect_stdout(stdout):
                        build_config.main()
            text = path.read_text(encoding="utf-8")
        self.assertIn(repr(secret), text)
        self.assertIn(repr(key), text)
        self.assertIn("POSTHOG_HOST = ''", text)
        printed = stdout.getvalue()
        self.assertNotIn(secret, printed)
        self.assertNotIn(key, printed)
        self.assertIn("sentry=yes", printed)
        self.assertIn("posthog=yes", printed)
        self.assertIn("host=default", printed)

    def test_control_character_is_refused(self) -> None:
        """Refuse a value that would break out of the assignment.

        Returns:
            None. The test fails if a newline is written into the module.
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "_build_config.py"
            with self.assertRaises(SystemExit):
                build_config.write_build_config(path, {"SENTRY_DSN": "https://example\nKEY = 'x'"})
            self.assertFalse(path.exists())

    def test_telemetry_pins_match(self) -> None:
        """Pin sentry-sdk and posthog to the same versions in both requirement files.

        Returns:
            None. The test fails if a release build would install a
            different telemetry version than the desktop environment.
        """
        runtime = _pins(ROOT / "requirements.txt")
        build = _pins(ROOT / "requirements-build.txt")
        for name in ("sentry-sdk", "posthog", "pywebview"):
            self.assertIn(name, runtime)
            self.assertEqual(runtime[name], build[name])


if __name__ == "__main__":
    unittest.main()
