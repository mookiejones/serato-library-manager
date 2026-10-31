"""Settings file tests.

The cases use a temporary directory. They do not read the machine's
Serato Library settings, and they do not open a database.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import _version
import app_config
import version_info


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
        the boolean, an install id, and an unfinished setup flag.

        Returns:
            None. The test fails if False comes back as None or True.
        """
        saved = app_config.set_telemetry_consent(False)
        self.assertIs(saved.telemetry_consent, False)
        loaded = app_config.load_settings()
        self.assertIs(loaded.telemetry_consent, False)
        self.assertIs(loaded.wizard_complete, False)
        self.assertEqual(loaded.install_id, saved.install_id)
        payload = json.loads((self.config / "settings.json").read_text(encoding="utf-8"))
        self.assertIs(payload["telemetry_consent"], False)
        self.assertIs(payload["wizard_complete"], False)
        self.assertEqual(
            set(payload),
            {"install_id", "telemetry_consent", "wizard_complete", "rekordbox"},
        )
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
        with self.assertRaises(ValueError):
            app_config.Settings(
                install_id="11111111-1111-4111-8111-111111111111",
                telemetry_consent=None,
            ).as_json()
        body = app_config.Settings(install_id=None, telemetry_consent=None).as_json()
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
        self.assertEqual(
            set(payload),
            {"install_id", "telemetry_consent", "window", "wizard_complete", "rekordbox"},
        )
        self.assertIs(payload["wizard_complete"], False)
        self.assertEqual(set(payload["window"]), set(app_config.WINDOW_FIELDS))

    def test_wizard_complete_keeps_the_window_and_a_rerun_keeps_the_choice(self) -> None:
        """Keep a negative origin when setup is finished and run again.

        False before a sharing choice does not write a file. After the
        choice and the frame exist, True and False both keep them.

        Returns:
            None. The test fails if setup drops the window or the choice.
        """
        untouched = app_config.set_wizard_complete(False)
        self.assertIsNone(untouched.window)
        self.assertFalse((self.config / "settings.json").exists())
        frame = app_config.WindowGeometry(-40, 0, 1280, 800)
        app_config.save_window_geometry(frame)
        saved = app_config.set_telemetry_consent(True)
        done = app_config.set_wizard_complete(True)
        self.assertEqual(done.window, frame)
        self.assertIs(done.telemetry_consent, True)
        self.assertEqual(done.install_id, saved.install_id)
        again = app_config.set_wizard_complete(False)
        self.assertIs(again.wizard_complete, False)
        self.assertEqual(again.window, frame)
        self.assertIs(again.telemetry_consent, True)
        self.assertEqual(again.install_id, saved.install_id)
        finished = app_config.set_wizard_complete(True)
        self.assertEqual(finished.window, frame)
        payload = json.loads((self.config / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["window"]["x"], -40)
        self.assertIs(payload["telemetry_consent"], True)
        self.assertEqual(payload["install_id"], saved.install_id)

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
        app_config.set_track_list_width(520)
        app_config.set_language("es")
        payload = json.loads((self.config / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(set(payload), set(app_config.SETTINGS_KEYS))


class LayoutSettingsTests(unittest.TestCase):
    """Check the track list width stored beside the other settings.

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

    def test_width_round_trips_and_keeps_the_other_fields(self) -> None:
        """Save a width after the sharing choice and the window.

        Returns:
            None. The test fails if a later save drops a field.
        """
        app_config.set_telemetry_consent(False)
        frame = app_config.WindowGeometry(0, 0, 1280, 800)
        app_config.save_window_geometry(frame)
        app_config.set_track_list_width(520)
        loaded = app_config.load_settings()
        self.assertEqual(loaded.track_list_width, 520)
        self.assertIs(loaded.telemetry_consent, False)
        self.assertEqual(loaded.window, frame)
        app_config.set_wizard_complete(True)
        app_config.save_window_geometry(frame)
        app_config.set_telemetry_consent(True)
        self.assertEqual(app_config.load_settings().track_list_width, 520)
        stored = json.loads((self.config / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(stored["layout"], {"track_list_width": 520})

    def test_width_before_a_choice_does_not_invent_one(self) -> None:
        """Store a width on a first launch, then clear it.

        Returns:
            None. The test fails if a consent appears or the layout stays.
        """
        app_config.update_rekordbox(hot_loops=True)
        app_config.set_track_list_width(400)
        path = self.config / "settings.json"
        stored = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(set(stored), {"rekordbox", "layout"})
        self.assertEqual(stored["layout"], {"track_list_width": 400})
        self.assertIs(stored["rekordbox"]["hot_loops"], True)
        self.assertIsNone(app_config.load_settings().telemetry_consent)
        app_config.set_track_list_width(None)
        stored = json.loads(path.read_text(encoding="utf-8"))
        self.assertNotIn("layout", stored)
        self.assertIs(stored["rekordbox"]["hot_loops"], True)
        self.assertIsNone(app_config.load_settings().track_list_width)
        app_config.update_rekordbox(memory_cues=False)
        app_config.set_track_list_width(500)
        app_config.update_rekordbox(key_notation="camelot")
        loaded = app_config.load_settings()
        self.assertEqual(loaded.track_list_width, 500)
        self.assertIs(loaded.rekordbox.memory_cues, False)

    def test_reset_keeps_the_window(self) -> None:
        """Clear the width while a window frame is stored.

        Returns:
            None. The test fails if the reset drops the frame.
        """
        frame = app_config.WindowGeometry(4, 5, 900, 700)
        app_config.save_window_geometry(frame)
        app_config.set_track_list_width(600)
        app_config.set_track_list_width(None)
        stored = json.loads((self.config / "settings.json").read_text(encoding="utf-8"))
        self.assertNotIn("layout", stored)
        self.assertEqual(app_config.load_settings().window, frame)

    def test_bad_widths_are_rejected(self) -> None:
        """Refuse a bool, a float, and widths out of range.

        Returns:
            None. The test fails if one is written.
        """
        for value in (True, 512.0, "512", app_config.TRACK_LIST_MIN_WIDTH - 1,
                      app_config.TRACK_LIST_MAX_WIDTH + 1):
            with self.assertRaises(ValueError, msg=repr(value)):
                app_config.set_track_list_width(value)  # type: ignore[arg-type]
        self.assertFalse((self.config / "settings.json").exists())

    def test_bad_stored_width_is_ignored(self) -> None:
        """Drop a hand-edited width that is not an integer in range.

        Returns:
            None. The test fails if the loader keeps it.
        """
        path = self.config / "settings.json"
        for layout in ({"track_list_width": True}, {"track_list_width": 10},
                       {"track_list_width": "wide"}, [], {"other": 1}):
            path.write_text(json.dumps({"layout": layout}), encoding="utf-8")
            with self.assertLogs("serato.library.config", level="WARNING"):
                loaded = app_config.load_settings()
            self.assertIsNone(loaded.track_list_width, layout)


class SettingsIntegrityTests(unittest.TestCase):
    """Gaps that let a settings save drop or tear another field.

    Each test uses a fresh directory via ``SERATO_LIBRARY_CONFIG_DIR``.
    Nothing here opens a Serato database or the machine's settings file.
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

    def test_update_rekordbox_keeps_the_window(self) -> None:
        """Keep a saved frame when the export bar is written.

        The frame includes a negative origin. The export-bar save has to
        write that object back, not only the ``rekordbox`` section.

        Returns:
            None. The test fails if the frame is missing after the save.
        """
        frame = app_config.WindowGeometry(12, -8, 1024, 768)
        app_config.save_window_geometry(frame)
        saved = app_config.update_rekordbox(hot_loops=True)
        self.assertEqual(saved.window, frame)
        self.assertTrue(saved.rekordbox.hot_loops)
        loaded = app_config.load_settings()
        self.assertEqual(loaded.window, frame)
        payload = json.loads((self.config / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(
            payload["window"],
            {"x": 12, "y": -8, "width": 1024, "height": 768},
        )

    def test_update_rekordbox_keeps_wizard_complete(self) -> None:
        """Keep a finished setup flag when the export bar is written.

        The flag starts True. A save that reset it to False would hide
        that the wizard had already finished.

        Returns:
            None. The test fails if the flag comes back False.
        """
        app_config.set_telemetry_consent(False)
        done = app_config.set_wizard_complete(True)
        self.assertIs(done.wizard_complete, True)
        saved = app_config.update_rekordbox(memory_cues=False)
        self.assertIs(saved.wizard_complete, True)
        self.assertIs(saved.telemetry_consent, False)
        self.assertFalse(saved.rekordbox.memory_cues)
        loaded = app_config.load_settings()
        self.assertIs(loaded.wizard_complete, True)
        self.assertIs(loaded.telemetry_consent, False)
        payload = json.loads((self.config / "settings.json").read_text(encoding="utf-8"))
        self.assertIs(payload["wizard_complete"], True)

    def test_overlapping_saves_keep_every_settings_key(self) -> None:
        """Keep every settings key when three saves overlap.

        One thread stores a new window frame and another stores a sharing
        choice while an export-bar save is inside its write. Those writes
        share the settings lock, so each one reads the file the previous
        one published. The file still has every ``SETTINGS_KEYS`` entry,
        the new frame, the new choice, and the export-bar change.

        Returns:
            None. The test fails if a stale export-bar write puts the old
            frame or the old choice back, or if a key disappears.
        """
        consented = app_config.set_telemetry_consent(False)
        app_config.set_wizard_complete(True)
        old_frame = app_config.WindowGeometry(1, 2, 800, 600)
        app_config.save_window_geometry(old_frame)
        app_config.set_track_list_width(480)
        app_config.set_language("es")
        app_config.update_rekordbox(memory_cues=False, key_notation="camelot")
        new_frame = app_config.WindowGeometry(30, 40, 1100, 700)
        original_save = app_config.save_settings
        armed = True
        errors: list[BaseException] = []
        window_ready = threading.Event()
        consent_ready = threading.Event()

        def save_frame() -> None:
            try:
                acquired = app_config._settings_lock.acquire(blocking=False)
                if acquired:
                    try:
                        app_config.save_window_geometry(new_frame)
                    finally:
                        app_config._settings_lock.release()
                        window_ready.set()
                else:
                    window_ready.set()
                    app_config.save_window_geometry(new_frame)
            except BaseException as exc:
                errors.append(exc)
                window_ready.set()

        def save_choice() -> None:
            try:
                if not window_ready.wait(timeout=5):
                    raise TimeoutError("window save did not reach the settings lock")
                acquired = app_config._settings_lock.acquire(blocking=False)
                if acquired:
                    try:
                        app_config.set_telemetry_consent(True)
                    finally:
                        app_config._settings_lock.release()
                        consent_ready.set()
                else:
                    consent_ready.set()
                    app_config.set_telemetry_consent(True)
            except BaseException as exc:
                errors.append(exc)
                consent_ready.set()

        frame_thread = threading.Thread(target=save_frame, name="window-save", daemon=True)
        choice_thread = threading.Thread(target=save_choice, name="consent-save", daemon=True)

        def wrapped_save(settings: app_config.Settings) -> None:
            nonlocal armed
            if armed and settings.rekordbox.hot_loops is True and settings.window == old_frame:
                armed = False
                frame_thread.start()
                choice_thread.start()
                if not window_ready.wait(timeout=5) or not consent_ready.wait(timeout=5):
                    raise AssertionError("overlapping saves did not reach the settings lock")
            original_save(settings)

        try:
            with mock.patch.object(app_config, "save_settings", wrapped_save):
                app_config.update_rekordbox(hot_loops=True)
        finally:
            # Join even when the save raises, so a writer is not still
            # holding settings.json when the temp directory is removed.
            # Windows cannot delete a file that is still open.
            for thread in (frame_thread, choice_thread):
                if thread.ident is not None:
                    thread.join(timeout=5)
        self.assertFalse(frame_thread.is_alive())
        self.assertFalse(choice_thread.is_alive())
        self.assertEqual(errors, [])
        loaded = app_config.load_settings()
        self.assertEqual(loaded.window, new_frame)
        self.assertIs(loaded.telemetry_consent, True)
        self.assertEqual(loaded.install_id, consented.install_id)
        self.assertIs(loaded.wizard_complete, True)
        self.assertTrue(loaded.rekordbox.hot_loops)
        self.assertFalse(loaded.rekordbox.memory_cues)
        self.assertEqual(loaded.rekordbox.key_notation, "camelot")
        self.assertEqual(loaded.track_list_width, 480)
        self.assertEqual(loaded.language, "es")
        payload = json.loads((self.config / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(set(payload), set(app_config.SETTINGS_KEYS))

    def test_rekordbox_changes_rejects_integers(self) -> None:
        """Reject an integer where the export bar wants a boolean.

        ``1`` is not true and ``0`` is not false. A real boolean still
        passes, including a saved false.

        Returns:
            None. The test fails if an integer is returned as a change.
        """
        accepted = app_config.rekordbox_changes(
            {"hot_loops": False, "memory_cues": True, "key_notation": "classical"}
        )
        self.assertIs(accepted["hot_loops"], False)
        self.assertIs(accepted["memory_cues"], True)
        self.assertEqual(accepted["key_notation"], "classical")
        for field in ("hot_loops", "memory_cues"):
            for value in (1, 0, 2):
                with self.assertRaises(ValueError, msg=f"{field}={value!r}"):
                    app_config.rekordbox_changes({field: value})
        with self.assertRaises(ValueError):
            app_config.rekordbox_changes({"key_notation": 1})

    def test_interrupted_write_keeps_the_original_file(self) -> None:
        """Leave the previous settings file in place when a write stops halfway.

        The new bytes go to a temp file in the same directory. A crash
        during that write must not replace ``settings.json``.

        Returns:
            None. The test fails if the original file is truncated or replaced.
        """
        app_config.set_telemetry_consent(False)
        path = self.config / "settings.json"
        original = path.read_bytes()

        def crash_mid_write(target: Path, data: str, *args: object, **kwargs: object) -> None:
            encoding = kwargs.get("encoding")
            if not isinstance(encoding, str):
                encoding = args[0] if args and isinstance(args[0], str) else "utf-8"
            # Close the handle before raising. Windows cannot remove the
            # temp directory while this file is still open.
            with target.open("w", encoding=encoding) as handle:
                handle.write(data[:8])
            raise OSError("crash mid-write")

        with mock.patch.object(Path, "write_text", crash_mid_write):
            with self.assertRaises(OSError):
                app_config.update_rekordbox(hot_loops=True)
        self.assertEqual(path.read_bytes(), original)
        temp = path.with_suffix(".json.tmp")
        leftover = temp.read_text(encoding="utf-8")
        self.assertEqual(len(leftover), 8)
        self.assertTrue(leftover.startswith("{\n"))
        loaded = app_config.load_settings()
        self.assertIs(loaded.telemetry_consent, False)
        self.assertFalse(loaded.rekordbox.hot_loops)

    def test_failed_replace_keeps_the_original_file(self) -> None:
        """Keep the previous file when the temp file cannot be renamed into place.

        The new JSON is in the temp file. ``settings.json`` is the file
        that was already there.

        Returns:
            None. The test fails if the destination changes before the
            rename, or if the rename is not attempted.
        """
        app_config.set_telemetry_consent(False)
        path = self.config / "settings.json"
        original = path.read_bytes()
        seen: list[tuple[str, str]] = []

        def fail_replace(src: object, dst: object, *args: object, **kwargs: object) -> None:
            seen.append((Path(str(src)).name, Path(str(dst)).name))
            raise OSError("replace failed")

        with mock.patch("os.replace", side_effect=fail_replace):
            with self.assertRaises(OSError):
                app_config.update_rekordbox(key_notation="classical")
        self.assertEqual(seen, [("settings.json.tmp", "settings.json")])
        self.assertEqual(path.read_bytes(), original)
        temp = path.with_suffix(".json.tmp")
        self.assertIn("classical", temp.read_text(encoding="utf-8"))
        loaded = app_config.load_settings()
        self.assertEqual(loaded.rekordbox.key_notation, "asis")
        self.assertIs(loaded.telemetry_consent, False)


class VersionTests(unittest.TestCase):
    """The app version has one definition.

    Sentry's release, PostHog's ``app_version``, ``__version__``, and
    ``GET /api/settings`` all read the string ``GET /api/version`` returns.
    """

    def test_version_alias_matches_the_resolver(self) -> None:
        """Keep ``__version__`` and ``APP_VERSION`` on the version endpoint.

        Nothing is written. A stamped tag must replace both attributes
        together, so a hard-coded package version cannot linger.

        Returns:
            None. The test fails when either attribute is a second string.
        """
        resolved = version_info.resolve().version
        self.assertEqual(app_config.__version__, resolved)
        self.assertEqual(app_config.APP_VERSION, resolved)
        self.assertIsInstance(app_config.APP_VERSION, str)
        with (
            mock.patch.object(_version, "VERSION", "v2.0.0"),
            mock.patch.object(_version, "COMMIT", "abcdef012345"),
            mock.patch.object(_version, "SOURCE", "release"),
        ):
            self.assertEqual(app_config.APP_VERSION, "v2.0.0")
            self.assertEqual(app_config.__version__, "v2.0.0")
            self.assertEqual(version_info.payload()["version"], "v2.0.0")

    def test_docs_name_the_shared_version(self) -> None:
        """Point the privacy and architecture notes at ``GET /api/version``.

        The live version changes with the checkout, so the notes name the
        source instead of copying one release string.

        Returns:
            None. The test fails when either document still treats
            ``1.1.0`` as the only app version.
        """
        root = Path(__file__).resolve().parents[1]
        architecture = (root / "docs" / "architecture.md").read_text(encoding="utf-8")
        privacy = (root / "PRIVACY.md").read_text(encoding="utf-8")
        self.assertIn("the same string `GET /api/version` returns", architecture)
        self.assertIn("`app_version` is the `version` field from `GET /api/version`", architecture)
        self.assertNotIn("not the release tag", architecture)
        self.assertIn("GET /api/version", privacy)
        self.assertNotIn("(`1.1.0`)", privacy)


if __name__ == "__main__":
    unittest.main()
