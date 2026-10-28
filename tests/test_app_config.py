"""Settings file tests.

The cases use a temporary directory. They do not read the machine's
Serato Library settings, and they do not open a database.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import app_config


class SettingsTests(unittest.TestCase):
    """Check the sharing choice round-trip.

    Each test points ``SERATO_LIBRARY_CONFIG_DIR`` at a fresh directory.
    Nothing is sent over the network.
    """

    def setUp(self) -> None:
        """Create an empty config directory for one test.

        Returns:
            None.
        """
        self._tmp = tempfile.TemporaryDirectory()
        self.config = Path(self._tmp.name) / "config"
        self.config.mkdir()
        self._env = mock.patch.dict(
            os.environ, {app_config.CONFIG_ENV: str(self.config)}
        )
        self._env.start()

    def tearDown(self) -> None:
        """Remove the temporary config directory.

        Returns:
            None.
        """
        self._env.stop()
        self._tmp.cleanup()

    def test_missing_file_means_no_choice(self) -> None:
        """Treat a missing file as an unchosen, off state.

        No file is written. The install id stays empty so nothing has to
        be generated before the person chooses.

        Returns:
            None. The test fails if a file appears or consent is not None.
        """
        settings = app_config.load_settings()
        self.assertIsNone(settings.telemetry_consent)
        self.assertIsNone(settings.install_id)
        self.assertFalse(self.config.joinpath(app_config.SETTINGS_NAME).exists())

    def test_false_is_kept(self) -> None:
        """Keep a saved False instead of treating it as missing.

        Writes the choice, loads it again, and checks the file contains
        both the boolean and an install id.

        Returns:
            None. The test fails if False comes back as None or True.
        """
        saved = app_config.set_telemetry_consent(False)
        self.assertIs(saved.telemetry_consent, False)
        loaded = app_config.load_settings()
        self.assertIs(loaded.telemetry_consent, False)
        self.assertEqual(loaded.install_id, saved.install_id)
        payload = json.loads((self.config / "settings.json").read_text(encoding="utf-8"))
        self.assertIs(payload["telemetry_consent"], False)
        self.assertEqual(set(payload), {"install_id", "telemetry_consent"})

    def test_true_is_kept(self) -> None:
        """Keep a saved True and reuse the install id.

        The second save must not mint a new id.

        Returns:
            None. The test fails if the id changes or consent is not True.
        """
        first = app_config.set_telemetry_consent(True)
        second = app_config.set_telemetry_consent(True)
        self.assertIs(second.telemetry_consent, True)
        self.assertEqual(first.install_id, second.install_id)

    def test_integer_consent_is_rejected(self) -> None:
        """Reject 0 and 1 so a boolean check cannot treat them as flags.

        A JSON integer is the wrong type. The loader ignores it and the
        writer refuses it. No file is replaced by the rejected write.

        Returns:
            None. The test fails if 0 is stored as False or 1 as True.
        """
        path = self.config / "settings.json"
        path.write_text(
            json.dumps({"install_id": "11111111-1111-4111-8111-111111111111", "telemetry_consent": 0}),
            encoding="utf-8",
        )
        with self.assertLogs("serato.library.config", level="WARNING") as caught:
            loaded = app_config.load_settings()
        self.assertIsNone(loaded.telemetry_consent)
        self.assertTrue(any("telemetry_consent" in line for line in caught.output))
        with self.assertRaises(ValueError):
            app_config.set_telemetry_consent(1)  # type: ignore[arg-type]

    def test_unknown_key_is_dropped(self) -> None:
        """Ignore a key the schema does not declare.

        The warning names the key. The next save writes only the known
        fields, so the unknown key does not stick.

        Returns:
            None. The test fails if the extra key survives the save.
        """
        path = self.config / "settings.json"
        path.write_text(
            json.dumps(
                {
                    "install_id": "11111111-1111-4111-8111-111111111111",
                    "telemetry_consent": False,
                    "library_path": "/Users/dj/Music",
                }
            ),
            encoding="utf-8",
        )
        with self.assertLogs("serato.library.config", level="WARNING") as caught:
            loaded = app_config.load_settings()
        self.assertIs(loaded.telemetry_consent, False)
        self.assertTrue(any("library_path" in line for line in caught.output))
        app_config.set_telemetry_consent(False)
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertNotIn("library_path", saved)

    def test_partial_object_is_not_written(self) -> None:
        """Refuse to persist a settings object that omits the choice.

        ``as_json`` is the write boundary. A missing consent must raise
        rather than create a file the loader would treat as final.

        Returns:
            None. The test fails if a partial object serializes.
        """
        partial = app_config.Settings(install_id="11111111-1111-4111-8111-111111111111", telemetry_consent=None)
        with self.assertRaises(ValueError):
            partial.as_json()

    def test_unreadable_file_is_kept_aside(self) -> None:
        """Rename a corrupt file when a new choice is saved.

        The original bytes stay next to the new file. The new file is
        valid JSON with both keys.

        Returns:
            None. The test fails if the corrupt text is deleted.
        """
        path = self.config / "settings.json"
        path.write_text("{", encoding="utf-8")
        app_config.set_telemetry_consent(False)
        retired = path.with_name("settings.json.unreadable")
        self.assertEqual(retired.read_text(encoding="utf-8"), "{")
        self.assertIs(json.loads(path.read_text(encoding="utf-8"))["telemetry_consent"], False)

    def test_relative_override_is_ignored(self) -> None:
        """Ignore a relative config directory override.

        The warning is logged and the default directory is used instead,
        so the file is not created in the working directory.

        Returns:
            None. The test fails if the relative path is accepted.
        """
        with mock.patch.dict(os.environ, {app_config.CONFIG_ENV: "relative-dir"}):
            with self.assertLogs("serato.library.config", level="WARNING"):
                chosen = app_config.config_dir()
        self.assertTrue(chosen.is_absolute())
        self.assertNotEqual(chosen, Path("relative-dir"))


class DirectoryTests(unittest.TestCase):
    """Check the per-system directories.

    The environment overrides are removed for these cases so the platform
    branch is what is asserted. No directory is created.
    """

    def test_macos_paths(self) -> None:
        """Use Application Support and Library Logs on macOS.

        Returns:
            None. The test fails if either path points somewhere else.
        """
        with mock.patch("app_config.sys.platform", "darwin"):
            config = app_config.default_config_dir()
            logs = app_config.default_log_dir()
        self.assertEqual(config, Path.home() / "Library" / "Application Support" / "Serato Library")
        self.assertEqual(logs, Path.home() / "Library" / "Logs" / "Serato Library")

    def test_windows_paths(self) -> None:
        """Use APPDATA for settings and LOCALAPPDATA for logs on Windows.

        Returns:
            None. The test fails if the folders are swapped or renamed.
        """
        environ = {"APPDATA": r"C:\Users\dj\AppData\Roaming", "LOCALAPPDATA": r"C:\Users\dj\AppData\Local"}
        with mock.patch.dict(os.environ, environ), mock.patch("app_config.sys.platform", "win32"):
            config = app_config.default_config_dir()
            logs = app_config.default_log_dir()
        self.assertEqual(config, Path(r"C:\Users\dj\AppData\Roaming") / "Serato Library")
        self.assertEqual(logs, Path(r"C:\Users\dj\AppData\Local") / "Serato Library" / "Logs")

    def test_linux_paths(self) -> None:
        """Use the XDG config and state directories on Linux.

        Returns:
            None. The test fails if the fallback home directories change.
        """
        with mock.patch("app_config.sys.platform", "linux"):
            config = app_config.default_config_dir()
            logs = app_config.default_log_dir()
        self.assertEqual(config, Path.home() / ".config" / "serato-library")
        self.assertEqual(logs, Path.home() / ".local" / "state" / "serato-library" / "logs")


class WindowSettingsTests(unittest.TestCase):
    """Check the desktop window frame stored beside the sharing choice.

    Each test uses a fresh config directory. Nothing is sent over the network.
    """

    def setUp(self) -> None:
        """Create an empty config directory for one test.

        Returns:
            None.
        """
        self._tmp = tempfile.TemporaryDirectory()
        self.config = Path(self._tmp.name) / "config"
        self.config.mkdir()
        self._env = mock.patch.dict(os.environ, {app_config.CONFIG_ENV: str(self.config)})
        self._env.start()

    def tearDown(self) -> None:
        """Remove the temporary config directory.

        Returns:
            None.
        """
        self._env.stop()
        self._tmp.cleanup()

    def test_origin_zero_is_kept_and_consent_is_preserved(self) -> None:
        """Keep x=0 and a saved decline across both writers.

        The window is saved first, then the choice, then the window again.
        Neither write drops the other. ``0`` stays ``0``.

        Returns:
            None. The test fails if a corner at the origin becomes missing.
        """
        frame = app_config.WindowGeometry(0, 0, 640, 480)
        app_config.save_window_geometry(frame)
        saved = app_config.set_telemetry_consent(False)
        self.assertEqual(saved.window, frame)
        self.assertIs(saved.telemetry_consent, False)
        moved = app_config.save_window_geometry(app_config.WindowGeometry(8, 0, 800, 600))
        self.assertIs(moved.telemetry_consent, False)
        self.assertEqual(moved.install_id, saved.install_id)
        assert moved.window is not None
        self.assertEqual(moved.window.x, 8)
        self.assertEqual(moved.window.y, 0)
        payload = json.loads((self.config / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(set(payload), {"install_id", "telemetry_consent", "window"})
        self.assertEqual(set(payload["window"]), set(app_config.WINDOW_FIELDS))

    def test_bool_coordinate_is_rejected(self) -> None:
        """Ignore a boolean coordinate instead of storing it as 1.

        The warning names ``window.x``. The sharing choice is still loaded.
        The constructor also refuses a bool.

        Returns:
            None. The test fails if ``True`` is stored as an origin.
        """
        path = self.config / "settings.json"
        path.write_text(
            json.dumps(
                {
                    "install_id": "11111111-1111-4111-8111-111111111111",
                    "telemetry_consent": False,
                    "window": {"x": True, "y": 0, "width": 800, "height": 600},
                }
            ),
            encoding="utf-8",
        )
        with self.assertLogs("serato.library.config", level="WARNING") as caught:
            loaded = app_config.load_settings()
        self.assertIsNone(loaded.window)
        self.assertIs(loaded.telemetry_consent, False)
        self.assertTrue(any("window.x" in line for line in caught.output))
        with self.assertRaises(ValueError):
            app_config.WindowGeometry(True, 0, 800, 600)  # type: ignore[arg-type]

    def test_partial_window_and_unknown_nested_key_are_dropped(self) -> None:
        """Drop a frame that is missing a field, and warn on an extra key.

        A complete frame with an unknown nested key keeps the four known
        fields. The next save does not write the extra key.

        Returns:
            None. The test fails if a three-field frame is opened later.
        """
        path = self.config / "settings.json"
        path.write_text(
            json.dumps({"window": {"x": 1, "y": 2, "width": 800}}),
            encoding="utf-8",
        )
        with self.assertLogs("serato.library.config", level="WARNING") as caught:
            loaded = app_config.load_settings()
        self.assertIsNone(loaded.window)
        self.assertTrue(any("window.height" in line for line in caught.output))
        path.write_text(
            json.dumps(
                {
                    "window": {
                        "x": 4,
                        "y": 5,
                        "width": 900,
                        "height": 700,
                        "monitor": "left",
                    }
                }
            ),
            encoding="utf-8",
        )
        with self.assertLogs("serato.library.config", level="WARNING") as caught:
            loaded = app_config.load_settings()
        self.assertEqual(loaded.window, app_config.WindowGeometry(4, 5, 900, 700))
        self.assertTrue(any("window.monitor" in line for line in caught.output))
        app_config.save_window_geometry(loaded.window)
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertNotIn("monitor", saved["window"])
        self.assertNotIn("install_id", saved)

    def test_out_of_range_frame_is_ignored(self) -> None:
        """Ignore a width below the minimum the window can open.

        Returns:
            None. The test fails if a 200px frame is returned.
        """
        path = self.config / "settings.json"
        path.write_text(
            json.dumps({"window": {"x": 0, "y": 0, "width": 200, "height": 600}}),
            encoding="utf-8",
        )
        with self.assertLogs("serato.library.config", level="WARNING") as caught:
            loaded = app_config.load_settings()
        self.assertIsNone(loaded.window)
        self.assertTrue(any("window.width" in line for line in caught.output))

    def test_settings_keys_match_a_full_file(self) -> None:
        """Declare every key a full settings file contains.

        Returns:
            None. The test fails if a stored key is missing from the schema.
        """
        app_config.set_telemetry_consent(False)
        app_config.save_window_geometry(app_config.WindowGeometry(1, 2, 640, 480))
        payload = json.loads((self.config / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(set(payload), set(app_config.SETTINGS_KEYS))


class VersionTests(unittest.TestCase):
    """The app version has one definition.

    Sentry's release and PostHog's ``app_version`` import
    ``APP_VERSION``. ``__version__`` must stay that same string.
    """

    def test_version_alias_matches_the_constant(self) -> None:
        """Keep ``__version__`` equal to ``APP_VERSION``.

        Returns:
            None. The test fails when the alias is a second literal.
        """
        self.assertEqual(app_config.__version__, app_config.APP_VERSION)
        self.assertEqual(app_config.APP_VERSION, "1.1.0")

    def test_docs_quote_the_same_version(self) -> None:
        """Keep the privacy and architecture notes on ``APP_VERSION``.

        Returns:
            None. The test fails when either document still names another
            release string.
        """
        root = Path(__file__).resolve().parents[1]
        for relative in ("PRIVACY.md", "docs/architecture.md"):
            text = (root / relative).read_text(encoding="utf-8")
            self.assertIn(app_config.APP_VERSION, text)


if __name__ == "__main__":
    unittest.main()
