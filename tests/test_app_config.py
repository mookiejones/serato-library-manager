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
        self.assertFalse(settings.rekordbox.hot_loops)
        self.assertTrue(settings.rekordbox.memory_cues)
        self.assertEqual(settings.rekordbox.key_notation, "asis")
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
        self.assertEqual(set(payload), {"install_id", "telemetry_consent", "rekordbox"})
        self.assertEqual(
            payload["rekordbox"],
            {"hot_loops": False, "memory_cues": True, "key_notation": "asis"},
        )

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
        self.assertIn("rekordbox", saved)

    def test_missing_consent_is_not_written_as_a_choice(self) -> None:
        """Omit a sharing choice that has not been made.

        The export bar can be stored on its own. The next load still has
        no consent, so the prompt is still due.

        Returns:
            None. The test fails if consent is written as false or null.
        """
        partial = app_config.Settings(
            install_id="11111111-1111-4111-8111-111111111111",
            telemetry_consent=None,
        )
        body = partial.as_json()
        self.assertNotIn("telemetry_consent", body)
        self.assertIn("rekordbox", body)
        saved = app_config.update_rekordbox(hot_loops=True)
        self.assertIsNone(saved.telemetry_consent)
        self.assertIsNone(saved.install_id)
        loaded = app_config.load_settings()
        self.assertIsNone(loaded.telemetry_consent)
        self.assertTrue(loaded.rekordbox.hot_loops)
        payload = json.loads((self.config / "settings.json").read_text(encoding="utf-8"))
        self.assertNotIn("telemetry_consent", payload)

    def test_rekordbox_defaults_round_trip_and_reject_bad_types(self) -> None:
        """Keep false, merge one field, and refuse integers and bad keys.

        A saved memory-cues false stays false when only hot loops is
        updated. A sharing choice saved afterwards keeps the export bar.
        An integer, an unknown field, and a notation outside the three
        words raise before the file changes.

        Returns:
            None. The test fails if false becomes the default or a bad
            value is stored.
        """
        import rekordbox

        self.assertEqual(app_config.REKORDBOX_KEY_NOTATIONS, rekordbox._KEY_NOTATIONS)
        saved = app_config.update_rekordbox(
            hot_loops=True,
            memory_cues=False,
            key_notation="camelot",
        )
        self.assertTrue(saved.rekordbox.hot_loops)
        self.assertFalse(saved.rekordbox.memory_cues)
        self.assertEqual(saved.rekordbox.key_notation, "camelot")
        app_config.update_rekordbox(hot_loops=False)
        loaded = app_config.load_settings()
        self.assertFalse(loaded.rekordbox.hot_loops)
        self.assertFalse(loaded.rekordbox.memory_cues)
        self.assertEqual(loaded.rekordbox.key_notation, "camelot")
        path = self.config / "settings.json"
        before = path.read_text(encoding="utf-8")
        with self.assertRaises(ValueError):
            app_config.update_rekordbox(hot_loops=1)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            app_config.update_rekordbox(memory_cues=0)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            app_config.update_rekordbox(key_notation="open")
        with self.assertRaises(ValueError):
            app_config.rekordbox_changes({"nope": True})
        with self.assertRaises(ValueError):
            app_config.rekordbox_changes({})
        with self.assertRaises(ValueError):
            app_config.rekordbox_changes("yes")
        self.assertEqual(path.read_text(encoding="utf-8"), before)
        path.write_text(
            json.dumps(
                {
                    "rekordbox": {
                        "hot_loops": 1,
                        "memory_cues": False,
                        "key_notation": "classical",
                        "library_path": "/tmp",
                    }
                }
            ),
            encoding="utf-8",
        )
        with self.assertLogs("serato.library.config", level="WARNING") as caught:
            repaired = app_config.load_settings()
        self.assertFalse(repaired.rekordbox.hot_loops)
        self.assertFalse(repaired.rekordbox.memory_cues)
        self.assertEqual(repaired.rekordbox.key_notation, "classical")
        text = " ".join(caught.output)
        self.assertIn("rekordbox.hot_loops", text)
        self.assertIn("rekordbox.library_path", text)
        app_config.set_telemetry_consent(False)
        kept = app_config.load_settings()
        self.assertIs(kept.telemetry_consent, False)
        self.assertFalse(kept.rekordbox.memory_cues)
        self.assertEqual(kept.rekordbox.key_notation, "classical")
        written = json.loads(path.read_text(encoding="utf-8"))
        self.assertNotIn("library_path", written["rekordbox"])

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
