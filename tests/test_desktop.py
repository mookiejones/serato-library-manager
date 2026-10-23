"""Smoke check for the frozen desktop app."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import desktop


class SmokeTests(unittest.TestCase):
    def test_smoke_check_writes_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "marker.txt"
            desktop.smoke_check(marker)
            self.assertEqual(marker.read_text(encoding="utf-8"), "ok\n")

    def test_smoke_check_rejects_a_relative_path(self) -> None:
        with self.assertRaises(SystemExit):
            desktop.smoke_check(Path("marker.txt"))

    def test_main_smoke_does_not_import_webview(self) -> None:
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
