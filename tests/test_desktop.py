"""Smoke check for the frozen desktop app."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import desktop


class SmokeTests(unittest.TestCase):
    """Check the frozen-app smoke path without opening a window.

    The cases call ``desktop.smoke_check`` and ``desktop.main`` against a
    temporary marker file. They do not bind a port or open the Serato database.
    """
    def test_smoke_check_writes_ok(self) -> None:
        """Write ``ok`` when the bundled page files can be read.

        Confirms the release marker. The check reads ``static/`` and overwrites
        the marker file. It does not bind a port or open Serato.

        Returns:
            None. The test fails if the marker text is not ``ok\n``.
        """
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "marker.txt"
            desktop.smoke_check(marker)
            self.assertEqual(marker.read_text(encoding="utf-8"), "ok\n")

    def test_smoke_check_rejects_a_relative_path(self) -> None:
        """Refuse a relative smoke-marker path.

        A relative path could write the marker inside the repository. The
        function raises ``SystemExit`` and does not create a file.

        Returns:
            None. The test fails if ``SystemExit`` is not raised.
        """
        with self.assertRaises(SystemExit):
            desktop.smoke_check(Path("marker.txt"))

    def test_main_smoke_does_not_import_webview(self) -> None:
        """Return from ``main`` after the smoke check, without pywebview.

        Sets ``SERATO_LIBRARY_SMOKE`` and drops any cached ``webview`` module.
        The marker file is written. The desktop window is not opened and the
        Serato database is not read.

        Returns:
            None. The test fails if ``webview`` is imported or the marker differs.
        """
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "marker.txt"
            with mock.patch.dict(os.environ, {desktop.SMOKE_ENV: str(marker)}):
                with mock.patch.dict("sys.modules"):
                    import sys

                    sys.modules.pop("webview", None)
                    desktop.main()
                    self.assertNotIn("webview", sys.modules)
            self.assertEqual(marker.read_text(encoding="utf-8"), "ok\n")


if __name__ == "__main__":
    unittest.main()
