"""Page language: the saved choice, the settings API, and the error codes.

The cases use a temporary settings directory and a fixture library. They
do not open the live Serato library.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import app_config
import error_codes
import legacy_library
import server
import snapshots
import telemetry
from tests.fixture import TempLibrary
from tests.test_setup import _request

ROOT = Path(__file__).resolve().parent.parent
LOCALES = ROOT / "locales"


def _catalog(code: str) -> dict[str, object]:
    """Read one locale file.

    Args:
        code: Language code, such as ``en``.

    Returns:
        The decoded catalog.
    """
    return json.loads((LOCALES / f"{code}.json").read_text(encoding="utf-8"))


class LanguageSettingTests(unittest.TestCase):
    """Store and read the language beside the other settings."""

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

    def _stored(self) -> dict[str, object]:
        return json.loads((self.config / "settings.json").read_text(encoding="utf-8"))

    def test_default_follows_the_system(self) -> None:
        """No file and no key both mean follow the OS.

        Returns:
            None.
        """
        self.assertIsNone(app_config.load_settings().language)
        app_config.set_track_list_width(500)
        self.assertNotIn("language", self._stored())
        self.assertIsNone(telemetry.public_settings()["language"])

    def test_set_and_clear_language(self) -> None:
        """A saved code reads back. None removes the key.

        Returns:
            None.
        """
        written = app_config.set_language("es")
        self.assertEqual(written.language, "es")
        self.assertEqual(self._stored()["language"], "es")
        self.assertEqual(app_config.load_settings().language, "es")
        self.assertEqual(telemetry.public_settings()["language"], "es")
        app_config.set_language(None)
        self.assertNotIn("language", self._stored())
        self.assertIsNone(app_config.load_settings().language)

    def test_rejects_unknown_language(self) -> None:
        """Only the shipped codes are stored.

        Returns:
            None.
        """
        for bad in ("fr", "ES", "", "es-MX", 1, True):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                app_config.set_language(bad)  # type: ignore[arg-type]
        self.assertFalse((self.config / "settings.json").exists())

    def test_bad_value_in_file_is_ignored(self) -> None:
        """An unknown or wrong-typed value falls back to the OS language.

        Returns:
            None.
        """
        for raw in ("fr", 3, ["es"]):
            with self.subTest(raw=raw):
                (self.config / "settings.json").write_text(json.dumps({"language": raw}), encoding="utf-8")
                with self.assertLogs("serato.library.config", level="WARNING"):
                    self.assertIsNone(app_config.load_settings().language)
        (self.config / "settings.json").write_text(json.dumps({"language": None}), encoding="utf-8")
        self.assertIsNone(app_config.load_settings().language)

    def test_every_other_save_keeps_the_language(self) -> None:
        """Each settings writer carries the language through.

        Returns:
            None.
        """
        app_config.set_language("es")
        writers = (
            lambda: app_config.set_telemetry_consent(True),
            lambda: app_config.save_window_geometry(app_config.WindowGeometry(1, 2, 800, 600)),
            lambda: app_config.set_wizard_complete(True),
            lambda: app_config.update_rekordbox(hot_loops=True),
            lambda: app_config.set_track_list_width(480),
            lambda: app_config.set_wizard_complete(False),
            lambda: app_config.set_telemetry_consent(False),
        )
        for index, write in enumerate(writers):
            with self.subTest(writer=index):
                write()
                self.assertEqual(app_config.load_settings().language, "es")
                self.assertEqual(self._stored()["language"], "es")

    def test_language_save_keeps_every_other_field(self) -> None:
        """Changing the language leaves the rest of the file alone.

        Returns:
            None.
        """
        app_config.set_telemetry_consent(True)
        app_config.save_window_geometry(app_config.WindowGeometry(1, 2, 800, 600))
        app_config.set_wizard_complete(True)
        app_config.update_rekordbox(key_notation="camelot")
        app_config.set_track_list_width(480)
        before = self._stored()
        app_config.set_language("es")
        after = self._stored()
        self.assertEqual({key: value for key, value in after.items() if key != "language"}, before)

    def test_unfinished_wizard_rerun_keeps_the_language(self) -> None:
        """Clearing setup before a sharing choice still keeps the language.

        Returns:
            None.
        """
        app_config.set_language("es")
        self.assertEqual(app_config.set_wizard_complete(False).language, "es")

    def test_languages_match_the_page(self) -> None:
        """app_config, src/i18n.ts, the locale files, and the picker agree.

        Returns:
            None.
        """
        source = (ROOT / "src" / "i18n.ts").read_text(encoding="utf-8")
        match = re.search(r"export const LANGUAGES = \[([^\]]*)\] as const;", source)
        assert match is not None
        page = tuple(re.findall(r'"([a-z]{2})"', match.group(1)))
        self.assertEqual(page, app_config.LANGUAGES)
        files = tuple(sorted(path.stem for path in LOCALES.glob("*.json")))
        self.assertEqual(files, tuple(sorted(app_config.LANGUAGES)))
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        picker = re.search(r'<select id="language-select">(.*?)</select>', html, re.S)
        assert picker is not None
        values = tuple(re.findall(r'<option value="([^"]*)"', picker.group(1)))
        self.assertEqual(values, ("", *app_config.LANGUAGES))


class LanguageApiTests(unittest.TestCase):
    """POST and GET /api/settings carry the language."""

    def setUp(self) -> None:
        """Start a fixture library and isolate settings.

        Returns:
            None.
        """
        self.library = TempLibrary()
        self.library.__enter__()
        self._tmp = tempfile.TemporaryDirectory()
        self.config = Path(self._tmp.name) / "config"
        logs = Path(self._tmp.name) / "logs"
        self.config.mkdir()
        logs.mkdir()
        self._env = mock.patch.dict(
            os.environ,
            {app_config.CONFIG_ENV: str(self.config), app_config.LOG_ENV: str(logs)},
        )
        self._env.start()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.httpd.server_address
        self.base = f"http://{host}:{port}"

    def tearDown(self) -> None:
        """Stop the server and remove the temporary files.

        Returns:
            None.
        """
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=3)
        self._env.stop()
        self._tmp.cleanup()
        self.library.__exit__(None, None, None)

    def test_post_and_get_language(self) -> None:
        """A saved language comes back from GET, and null clears it.

        Returns:
            None.
        """
        status, body = _request(self.base, "/api/settings", {"language": "es"})
        self.assertEqual(status, 200)
        assert isinstance(body, dict)
        self.assertEqual(body["language"], "es")
        status, fetched = _request(self.base, "/api/settings")
        self.assertEqual(status, 200)
        assert isinstance(fetched, dict)
        self.assertEqual(fetched["language"], "es")
        status, cleared = _request(self.base, "/api/settings", {"language": None})
        self.assertEqual(status, 200)
        assert isinstance(cleared, dict)
        self.assertIsNone(cleared["language"])
        self.assertIsNone(app_config.load_settings().language)

    def test_bad_language_is_refused_with_a_code(self) -> None:
        """Unknown codes, wrong types, and extra keys are 400.

        Returns:
            None.
        """
        app_config.set_language("es")
        for payload in ({"language": "fr"}, {"language": 2}, {"language": ["es"]}, {"language": "es", "layout": {}}):
            with self.subTest(payload=payload):
                status, body = _request(self.base, "/api/settings", payload)
                self.assertEqual(status, 400)
                self.assertEqual(body, {"error": "That request is not valid.", "code": "invalid_request"})
        self.assertEqual(app_config.load_settings().language, "es")

    def test_failed_write_says_so(self) -> None:
        """A disk error is a 500 with its own code.

        Returns:
            None.
        """
        with mock.patch.object(app_config, "save_settings", side_effect=OSError("disk full")):
            status, body = _request(self.base, "/api/settings", {"language": "es"})
        self.assertEqual(status, 500)
        self.assertEqual(body, {"error": "The language could not be saved.", "code": "language_not_saved"})

    def test_unknown_serato_version_is_coded_on_status_and_snapshots(self) -> None:
        """The status line and the snapshot list name the build for translation.

        A known Serato 4 install has no code. An unreadable version file
        does. Nothing is written to the library.

        Returns:
            None.
        """
        status, plain = _request(self.base, "/api/status")
        self.assertEqual(status, 200)
        assert isinstance(plain, dict)
        self.assertNotIn("code", plain)
        self.assertTrue(plain["writable"])
        bad = self.config / "not-a-plist"
        bad.write_bytes(b"nope")
        with mock.patch.dict(os.environ, {"SERATO_LIBRARY_APP_INFO": str(bad)}):
            status, body = _request(self.base, "/api/status")
            self.assertEqual(status, 200)
            assert isinstance(body, dict)
            self.assertEqual(body["code"], "serato_version_unknown")
            self.assertEqual(body["params"], {"build": "unknown"})
            self.assertIn("(build unknown)", body["message"])
            self.assertFalse(body["writable"])
            status, listed = _request(self.base, "/api/snapshots")
            self.assertEqual(status, 200)
            assert isinstance(listed, dict)
            self.assertEqual(listed["write_block_code"], "serato_version_unknown")
            self.assertEqual(listed["write_block_params"], {"build": "unknown"})
            self.assertEqual(listed["write_block"], body["message"])
            created_status, created = _request(self.base, "/api/snapshots", {"action": "create"})
            self.assertEqual(created_status, 200)
            assert isinstance(created, dict)
            snapshot = created["snapshot"]
            assert isinstance(snapshot, dict)
            plan_status, plan = _request(self.base, "/api/snapshots", {"action": "plan", "id": snapshot["id"]})
            self.assertEqual(plan_status, 200)
            assert isinstance(plan, dict)
            self.assertEqual(plan["restore_blocked_code"], "serato_version_unknown")
            self.assertEqual(plan["restore_blocked_params"], {"build": "unknown"})
            self.assertEqual(plan["restore_blocked"], body["message"])
            self.assertTrue(plan["dry_run"])


class ErrorCodeTests(unittest.TestCase):
    """Codes for the server's fixed error sentences."""

    def test_codes_are_unique_and_stable_words(self) -> None:
        """Every code is lowercase words joined by underscores, used once.

        Returns:
            None.
        """
        codes = list(error_codes.ERROR_CODES.values())
        self.assertEqual(len(codes), len(set(codes)))
        for code in codes:
            self.assertRegex(code, r"^[a-z]+(_[a-z]+)*$")

    def test_every_code_is_in_every_locale(self) -> None:
        """English repeats the server sentence. Other languages translate it.

        Returns:
            None.
        """
        english = _catalog("en")
        for message, code in error_codes.ERROR_CODES.items():
            with self.subTest(code=code):
                self.assertEqual(english.get(f"error.{code}"), message)
        for language in app_config.LANGUAGES:
            catalog = _catalog(language)
            for code in error_codes.ERROR_CODES.values():
                with self.subTest(language=language, code=code):
                    self.assertIn(f"error.{code}", catalog)
            for code, template in error_codes.PARAM_CODES.items():
                with self.subTest(language=language, code=code):
                    self.assertEqual(catalog[f"error.{code}"].count("{build}"), template.count("{build}"))
                    self.assertIn("{build}", catalog[f"error.{code}"])
        for code, template in error_codes.PARAM_CODES.items():
            self.assertEqual(english[f"error.{code}"], template)
            self.assertNotIn(code, error_codes.ERROR_CODES.values())

    def test_with_code_adds_only_for_a_known_sentence(self) -> None:
        """Known sentences get a code. Others, and non-errors, stay as they are.

        Returns:
            None.
        """
        self.assertEqual(
            error_codes.with_code({"error": "That request is not valid.", "serato": None}),
            {"error": "That request is not valid.", "serato": None, "code": "invalid_request"},
        )
        self.assertEqual(
            error_codes.with_code({"error": legacy_library.WRITE_BLOCKED, "read_only": True})["code"],  # type: ignore[index]
            "legacy_read_only",
        )
        unknown = {"error": "Could not open /Users/me/Music/a.mp3."}
        self.assertIs(error_codes.with_code(unknown), unknown)
        kept = {"error": "That request is not valid.", "code": "custom"}
        self.assertIs(error_codes.with_code(kept), kept)
        success = {"ok": True}
        self.assertIs(error_codes.with_code(success), success)
        listing = [{"error": "That request is not valid."}]
        self.assertIs(error_codes.with_code(listing), listing)
        self.assertIsNone(error_codes.code_for(None))
        self.assertIsNone(error_codes.code_for(3))

    def test_with_code_does_not_change_its_input(self) -> None:
        """The payload passed in is not modified.

        Returns:
            None.
        """
        payload = {"error": "That request is not valid."}
        error_codes.with_code(payload)
        self.assertEqual(payload, {"error": "That request is not valid."})

    def test_unknown_version_notice_carries_a_code_and_the_build(self) -> None:
        """The unknown-version sentence is a template, not a fixed code.

        Returns:
            None.
        """
        install = snapshots.SeratoInstall("v5.0", "9.9", "on")
        notice = snapshots.write_block_notice(install)
        assert notice is not None
        self.assertEqual(notice.code, "serato_version_unknown")
        self.assertEqual(notice.params, {"build": "9.9"})
        template = _catalog("en")["error.serato_version_unknown"]
        assert isinstance(template, str)
        self.assertEqual(notice.text, template.format(build="9.9"))
        self.assertIsNone(snapshots.write_block_notice(snapshots.SeratoInstall("4.1.0", "4.1.0.1", "off")))

    def test_history_column_and_search_fit_a_longer_language(self) -> None:
        """Spanish history and Reload stay on one row at the default split.

        The played column is 8.5rem so “Reproducida” is not clipped. Export,
        Import, and Reload stay in one row; the Rekordbox options wrap under them.

        Returns:
            None.
        """
        css = (ROOT / "static" / "app.css").read_text(encoding="utf-8")
        self.assertRegex(
            css,
            r"\.columns\.for-history,\s*\.list\.for-history \.row \{\s*grid-template-columns:[^}]*8\.5rem",
        )
        self.assertRegex(css, r"\.browser-actions \{[^}]*flex-wrap: nowrap")


if __name__ == "__main__":
    unittest.main()
