"""First-run setup: library wording, the completion flag, and a missing library.

The cases use a temporary database and a temporary settings directory.
They do not open a live Serato library.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from html.parser import HTMLParser
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import app_config
import app_log
import library
import server
import setup_flow
import snapshots
import telemetry
from tests.fixture import TempLibrary, build_database


def _request(base: str, path: str, payload: dict | None = None) -> tuple[int, object]:
    """Send one JSON request and return the status and body.

    Args:
        base: ``http://127.0.0.1:<port>`` with no path.
        path: Absolute path, beginning with ``/``.
        payload: JSON object for POST. None sends GET.

    Returns:
        The status code and the decoded JSON value.
    """
    data = None
    headers: dict[str, str] = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(base + path, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            body = response.read()
            status = response.status
    except urllib.error.HTTPError as exc:
        body = exc.read()
        status = exc.code
        exc.close()
    return status, json.loads(body.decode("utf-8"))


class WordingTests(unittest.TestCase):
    """The sentences name a disk and a track count, not a database file."""

    def test_count_phrase(self) -> None:
        """Speak one track and a thousands separator.

        Returns:
            None. The test fails if 1 is plural or 4812 has no comma.
        """
        self.assertEqual(setup_flow.format_track_count(1), "1 track")
        self.assertEqual(setup_flow.format_track_count(4812), "4,812 tracks")
        self.assertEqual(setup_flow.format_track_count(0), "0 tracks")
        self.assertEqual(setup_flow.format_track_count(True), "0 tracks")  # type: ignore[arg-type]

    def test_found_sentence_uses_the_disk_name(self) -> None:
        """Name the disk and the tracks when the fixture library exists.

        Returns:
            None. The test fails if the sentence names a database file.
        """
        with TempLibrary() as library_fx:
            with mock.patch.object(setup_flow, "volume_label", return_value="Macintosh HD"):
                payload = setup_flow.describe_library()
            self.assertTrue(payload["found"])
            self.assertEqual(payload["track_count"], 2)
            self.assertEqual(
                payload["summary"],
                "Found your Serato library on Macintosh HD, 2 tracks.",
            )
            self.assertIsNone(payload["next"])
            self.assertNotIn("master.sqlite", json.dumps(payload))
            self.assertNotIn("database V2", json.dumps(payload))
            self.assertNotIn(str(library_fx.db), json.dumps(payload))

    def test_missing_library_says_what_to_do(self) -> None:
        """Tell the person to open Serato DJ when no library file exists.

        Returns:
            None. The test fails if a path is included.
        """
        missing = Path(tempfile.gettempdir()) / "serato-setup-missing" / "library-file"
        with mock.patch.object(library, "MASTER", missing):
            payload = setup_flow.describe_library()
        self.assertFalse(payload["found"])
        self.assertEqual(payload["summary"], setup_flow.NOT_FOUND_SUMMARY)
        self.assertEqual(payload["next"], setup_flow.NOT_FOUND_NEXT)
        text = json.dumps(payload)
        self.assertNotIn("master.sqlite", text)
        self.assertNotIn("database V2", text)
        self.assertNotIn("space", str(payload["summary"]).lower())
        self.assertNotIn("space", str(payload["next"]).lower())

    def test_chosen_folder_must_be_the_library_folder(self) -> None:
        """Accept the library folder and refuse a different one.

        A shortcut is refused before it is read. The response does not
        repeat the chosen path.

        Returns:
            None. The test fails if another folder counts as the library.
        """
        with TempLibrary() as library_fx:
            with mock.patch.object(setup_flow, "volume_label", return_value="Macintosh HD"):
                chosen = setup_flow.accept_folder(str(library_fx.db.parent))
            self.assertTrue(chosen["found"])
            self.assertNotIn(str(library_fx.db), json.dumps(chosen))
            other = library_fx.root / "other"
            other.mkdir()
            rejected = setup_flow.accept_folder(str(other))
            self.assertFalse(rejected["found"])
            self.assertEqual(rejected["summary"], setup_flow.WRONG_FOLDER_SUMMARY)
            link = library_fx.root / "linked"
            try:
                link.symlink_to(other, target_is_directory=True)
            except OSError:
                link = None
            if link is not None:
                with self.assertRaises(library.LibraryError):
                    setup_flow.accept_folder(str(link))

    def test_browse_lists_folder_names(self) -> None:
        """List child folders and skip a hidden name and a shortcut.

        Returns:
            None. The test fails if a file or a shortcut is listed.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Music").mkdir()
            (root / "notes.txt").write_text("x", encoding="utf-8")
            (root / ".hidden").mkdir()
            try:
                (root / "linked").symlink_to(root / "Music", target_is_directory=True)
            except OSError:
                pass
            payload = setup_flow.browse_folders(str(root))
        self.assertEqual(payload["name"], root.name)
        names = [item["name"] for item in payload["folders"]]
        self.assertEqual(names, ["Music"])


class SetupApiTests(unittest.TestCase):
    """HTTP coverage for setup and the completion flag."""

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
        app_log.close_files()
        self._tmp.cleanup()
        self.library.__exit__(None, None, None)

    def test_setup_and_completion_flag(self) -> None:
        """Report the fixture library and refuse to finish before a choice.

        The page contains the wizard. Finishing setup requires the
        sharing choice first. An integer flag is rejected.

        Returns:
            None. The test fails if the flag is stored too early.
        """
        status, page = _request_text(self.base, "/")
        self.assertIn("wizard", page)
        self.assertIn("Get started", page)
        self.assertIn("Run setup again", page)
        with mock.patch.object(setup_flow, "volume_label", return_value="Macintosh HD"):
            status, payload = _request(self.base, "/api/setup")
        self.assertEqual(status, 200)
        assert isinstance(payload, dict)
        self.assertTrue(payload["found"])
        self.assertIn("Macintosh HD", payload["summary"])
        self.assertNotIn("master.sqlite", json.dumps(payload))
        status, early = _request(self.base, "/api/settings", {"wizard_complete": True})
        self.assertEqual(status, 400)
        assert isinstance(early, dict)
        self.assertIn("share", early["error"])
        status, rejected = _request(self.base, "/api/settings", {"wizard_complete": 1})
        self.assertEqual(status, 400)
        status, choice = _request(self.base, "/api/settings", {"telemetry_consent": False})
        self.assertEqual(status, 200)
        assert isinstance(choice, dict)
        self.assertIs(choice["wizard_complete"], False)
        status, done = _request(self.base, "/api/settings", {"wizard_complete": True})
        self.assertEqual(status, 200)
        assert isinstance(done, dict)
        self.assertIs(done["wizard_complete"], True)
        self.assertIs(done["telemetry_consent"], False)
        status, both = _request(
            self.base,
            "/api/settings",
            {"telemetry_consent": False, "wizard_complete": True},
        )
        self.assertEqual(status, 400)

    def test_folder_check_and_running_flag(self) -> None:
        """Accept the fixture folder and report whether Serato DJ is running.

        Returns:
            None. The test fails if a running flag is missing or a wrong
            folder is accepted.
        """
        with mock.patch.object(setup_flow.snapshots, "serato_dj_running", return_value=True):
            status, payload = _request(self.base, "/api/setup")
        self.assertEqual(status, 200)
        assert isinstance(payload, dict)
        self.assertIs(payload["serato_running"], True)
        self.assertEqual(payload["status_message"], "Serato DJ is open. Edits stay off until it quits.")
        self.assertIs(payload["status_writable"], False)
        status, chosen = _request(
            self.base,
            "/api/setup",
            {"folder": str(self.library.db.parent)},
        )
        self.assertEqual(status, 200)
        assert isinstance(chosen, dict)
        self.assertTrue(chosen["found"])
        other = self.library.root / "elsewhere"
        other.mkdir()
        status, rejected = _request(self.base, "/api/setup", {"folder": str(other)})
        self.assertEqual(status, 200)
        assert isinstance(rejected, dict)
        self.assertFalse(rejected["found"])
        self.assertNotIn(str(other), json.dumps(rejected))

    def test_settings_rejects_a_non_boolean_and_unknown_keys(self) -> None:
        """Refuse a completion flag that is not a boolean, and any extra key.

        The only accepted completion body is ``{"wizard_complete": bool}``.
        A string, an integer, null, and an unknown field are all 400, and
        none of them creates a settings file.

        Returns:
            None. The test fails if a bad body is stored.
        """
        rejected = (
            {"wizard_complete": "yes"},
            {"wizard_complete": 1},
            {"wizard_complete": None},
            {"theme": "dark"},
            {"wizard_complete": True, "theme": "dark"},
        )
        path = self.config / "settings.json"
        for payload in rejected:
            status, body = _request(self.base, "/api/settings", payload)
            self.assertEqual(status, 400, payload)
            assert isinstance(body, dict)
            self.assertIn("error", body)
            self.assertFalse(path.exists(), payload)

    def test_layout_width_is_saved_and_reset(self) -> None:
        """Save the track list width over HTTP, refuse bad shapes, and reset.

        Returns:
            None. The test fails if a bad body is stored or null keeps a width.
        """
        path = self.config / "settings.json"
        rejected = (
            {"layout": {"track_list_width": "520"}},
            {"layout": {"track_list_width": True}},
            {"layout": {"track_list_width": 520.5}},
            {"layout": {"track_list_width": 12}},
            {"layout": {"track_list_width": 520, "detail": 300}},
            {"layout": {}},
            {"layout": 520},
            {"layout": {"track_list_width": 520}, "wizard_complete": True},
        )
        for payload in rejected:
            status, body = _request(self.base, "/api/settings", payload)
            self.assertEqual(status, 400, payload)
            self.assertFalse(path.exists(), payload)
        status, saved = _request(self.base, "/api/settings", {"layout": {"track_list_width": 520}})
        self.assertEqual(status, 200)
        assert isinstance(saved, dict)
        self.assertEqual(saved["layout"], {"track_list_width": 520})
        self.assertIsNone(saved["telemetry_consent"])
        status, fetched = _request(self.base, "/api/settings")
        assert isinstance(fetched, dict)
        self.assertEqual(fetched["layout"], {"track_list_width": 520})
        status, reset = _request(self.base, "/api/settings", {"layout": {"track_list_width": None}})
        self.assertEqual(status, 200)
        assert isinstance(reset, dict)
        self.assertEqual(reset["layout"], {"track_list_width": None})

    def test_wizard_complete_keeps_the_window_and_a_rerun_keeps_settings(self) -> None:
        """Keep the desktop frame, the install id, and the sharing choice.

        The window is stored first, the way the desktop app saves it
        before setup finishes. Marking setup finished, clearing that flag
        to run setup again, and finishing once more all leave the other
        fields in place.

        Returns:
            None. The test fails if a setup save drops the window.
        """
        frame = app_config.WindowGeometry(-12, 0, 1280, 800)
        app_config.save_window_geometry(frame)
        app_config.set_track_list_width(520)
        status, choice = _request(self.base, "/api/settings", {"telemetry_consent": False})
        self.assertEqual(status, 200)
        assert isinstance(choice, dict)
        self.assertIs(choice["wizard_complete"], False)
        before = json.loads((self.config / "settings.json").read_text(encoding="utf-8"))
        install_id = before["install_id"]
        self.assertEqual(before["window"], {"x": -12, "y": 0, "width": 1280, "height": 800})
        self.assertIs(before["telemetry_consent"], False)

        status, done = _request(self.base, "/api/settings", {"wizard_complete": True})
        self.assertEqual(status, 200)
        assert isinstance(done, dict)
        self.assertIs(done["wizard_complete"], True)
        self.assertIs(done["telemetry_consent"], False)
        finished = json.loads((self.config / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(finished["install_id"], install_id)
        self.assertEqual(finished["window"], before["window"])
        self.assertIs(finished["telemetry_consent"], False)
        self.assertIs(finished["wizard_complete"], True)

        status, again = _request(self.base, "/api/settings", {"wizard_complete": False})
        self.assertEqual(status, 200)
        assert isinstance(again, dict)
        self.assertIs(again["wizard_complete"], False)
        self.assertIs(again["telemetry_consent"], False)
        rerun = json.loads((self.config / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(rerun["install_id"], install_id)
        self.assertEqual(rerun["window"], before["window"])
        self.assertIs(rerun["telemetry_consent"], False)
        self.assertIs(rerun["wizard_complete"], False)

        status, redone = _request(self.base, "/api/settings", {"wizard_complete": True})
        self.assertEqual(status, 200)
        assert isinstance(redone, dict)
        self.assertIs(redone["wizard_complete"], True)
        stored = json.loads((self.config / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(stored["install_id"], install_id)
        self.assertEqual(stored["window"], before["window"])
        self.assertEqual(stored["layout"], {"track_list_width": 520})
        self.assertIs(stored["telemetry_consent"], False)
        self.assertEqual(set(stored), set(app_config.SETTINGS_KEYS))


class MissingLibraryServerTests(unittest.TestCase):
    """The page stays up when Serato has not created a library yet."""

    def test_server_serves_the_page_and_the_next_step(self) -> None:
        """Bind and explain a missing library instead of exiting.

        ``require_library`` stays true. The process used to exit. The
        wizard response names the next step and does not include a path.

        Returns:
            None. The test fails if ``serve`` raises or the page is empty.
        """
        tmp = tempfile.TemporaryDirectory()
        missing = Path(tmp.name) / "missing" / "library"
        config = Path(tmp.name) / "config"
        logs = Path(tmp.name) / "logs"
        config.mkdir()
        logs.mkdir()
        try:
            with mock.patch.object(library, "MASTER", missing), mock.patch.dict(
                os.environ,
                {app_config.CONFIG_ENV: str(config), app_config.LOG_ENV: str(logs)},
            ):
                httpd = server.serve(port=0, require_library=True)
                thread = threading.Thread(target=httpd.serve_forever, daemon=True)
                thread.start()
                host, port = httpd.server_address
                base = f"http://{host}:{port}"
                try:
                    status, page = _request_text(base, "/")
                    self.assertEqual(status, 200)
                    self.assertIn("Get started", page)
                    self.assertNotIn("Art placeholder", page)
                    slots = _art_slots(page)
                    self.assertEqual(
                        list(slots),
                        ["welcome", "library", "snapshot", "consent", "done"],
                    )
                    for name, svg in slots.items():
                        self.assertEqual(svg.get("aria-hidden"), "true", name)
                        self.assertEqual(svg.get("focusable"), "false", name)
                        self.assertNotIn("alt", svg, name)
                    status, payload = _request(base, "/api/setup")
                    self.assertEqual(status, 200)
                    assert isinstance(payload, dict)
                    self.assertFalse(payload["found"])
                    self.assertEqual(payload["summary"], setup_flow.NOT_FOUND_SUMMARY)
                    self.assertIn("Open Serato DJ once", str(payload["next"]))
                    self.assertNotIn("master.sqlite", json.dumps(payload))
                    self.assertNotIn(str(missing), json.dumps(payload))
                    status, library_payload = _request(base, "/api/library")
                    self.assertEqual(status, 404)
                    assert isinstance(library_payload, dict)
                    self.assertEqual(
                        library_payload["error"],
                        "No Serato library was found on this computer.",
                    )
                finally:
                    httpd.shutdown()
                    httpd.server_close()
                    thread.join(3)
                    app_log.close_files()
        finally:
            tmp.cleanup()

    def test_empty_home_serves_the_page_and_reports_the_missing_library(self) -> None:
        """Start ``server.py`` against an empty home and keep serving.

        The home directory has no Serato library. ``require_library`` stays
        at the default ``python server.py`` uses. The page loads, setup
        says the library was not found and offers a folder choice, and the
        process does not create a library file.

        Returns:
            None. The test fails if the process exits or the page is missing.
        """
        home = Path(tempfile.mkdtemp(prefix="serato-empty-home-"))
        config = home / "config"
        logs = home / "logs"
        config.mkdir()
        logs.mkdir()
        env = os.environ.copy()
        env["HOME"] = str(home)
        env["USERPROFILE"] = str(home)
        env["LOCALAPPDATA"] = str(home / "AppData" / "Local")
        env["APPDATA"] = str(home / "AppData" / "Roaming")
        env["XDG_CONFIG_HOME"] = str(home / ".config")
        env["XDG_STATE_HOME"] = str(home / "state")
        env[app_config.CONFIG_ENV] = str(config)
        env[app_config.LOG_ENV] = str(logs)
        env.pop("HOMEDRIVE", None)
        env.pop("HOMEPATH", None)
        env.pop("SERATO_LIBRARY_SMOKE", None)
        script = (
            "import json, sys, threading\n"
            "import library, server\n"
            "master = str(library.MASTER)\n"
            "try:\n"
            "    httpd = server.serve(port=0, require_library=True)\n"
            "except SystemExit as exc:\n"
            "    sys.stdout.write(json.dumps({'error': str(exc)}) + '\\n')\n"
            "    sys.stdout.flush()\n"
            "    raise SystemExit(1)\n"
            "host, port = httpd.server_address\n"
            "if isinstance(host, bytes):\n"
            "    host = host.decode()\n"
            "sys.stdout.write(json.dumps({'host': host, 'port': int(port), 'master': master}) + '\\n')\n"
            "sys.stdout.flush()\n"
            "thread = threading.Thread(target=httpd.serve_forever, daemon=True)\n"
            "thread.start()\n"
            "sys.stdin.readline()\n"
            "httpd.shutdown()\n"
            "httpd.server_close()\n"
            "thread.join(3)\n"
        )
        stderr_path = home / "stderr.txt"
        stderr = stderr_path.open("w", encoding="utf-8")
        proc = subprocess.Popen(
            [sys.executable, "-c", script],
            cwd=str(Path(__file__).resolve().parents[1]),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr,
            text=True,
        )
        line = ""
        code = 1
        try:
            box: dict[str, str] = {}

            def _read() -> None:
                if proc.stdout is not None:
                    box["line"] = proc.stdout.readline()

            reader = threading.Thread(target=_read)
            reader.start()
            reader.join(20)
            if reader.is_alive():
                proc.kill()
                self.fail("The server did not start against an empty home.")
            line = box.get("line", "")
            started = json.loads(line) if line else {}
            self.assertNotIn("error", started, line)
            master = Path(started["master"])
            self.assertTrue(master.is_absolute())
            self.assertEqual(master.name, "master.sqlite")
            self.assertTrue(master.resolve().is_relative_to(home.resolve()))
            self.assertFalse(master.exists())
            base = f"http://{started['host']}:{started['port']}"
            status, page = _request_text(base, "/")
            self.assertEqual(status, 200)
            self.assertIn("Get started", page)
            self.assertIn("Choose a folder", page)
            status, payload = _request(base, "/api/setup")
            self.assertEqual(status, 200)
            assert isinstance(payload, dict)
            self.assertFalse(payload["found"])
            self.assertEqual(payload["summary"], setup_flow.NOT_FOUND_SUMMARY)
            self.assertIn("Open Serato DJ once", str(payload["next"]))
            body = json.dumps(payload)
            self.assertNotIn("master.sqlite", body)
            self.assertNotIn(str(master), body)
            self.assertNotIn(str(home), body)
            status, picked = _request(base, "/api/setup", {"folder": str(home)})
            self.assertEqual(status, 200)
            assert isinstance(picked, dict)
            self.assertFalse(picked["found"])
            self.assertEqual(picked["summary"], setup_flow.NOT_FOUND_SUMMARY)
            self.assertEqual(picked["next"], setup_flow.PICK_FAILED_NEXT)
            self.assertNotIn(str(home), json.dumps(picked))
            status, library_payload = _request(base, "/api/library")
            self.assertEqual(status, 404)
            assert isinstance(library_payload, dict)
            self.assertEqual(
                library_payload["error"],
                "No Serato library was found on this computer.",
            )
            self.assertFalse(master.exists())
            self.assertFalse((config / app_config.LIBRARY_CHOICE_NAME).exists())
            if proc.stdin is not None:
                proc.stdin.write("\n")
                proc.stdin.flush()
            code = proc.wait(timeout=5)
            self.assertEqual(code, 0, stderr_path.read_text(encoding="utf-8", errors="replace")[-2000:])
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)
            stderr.close()
            if proc.stdout is not None:
                proc.stdout.close()
            if proc.stdin is not None:
                proc.stdin.close()


class ChosenLibraryTests(unittest.TestCase):
    """A missing usual library can open a folder that already has one."""

    def setUp(self) -> None:
        """Point the process at a missing file and isolate settings.

        Returns:
            None.
        """
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.config = root / "config"
        self.logs = root / "logs"
        self.config.mkdir()
        self.logs.mkdir()
        self.missing = root / "missing" / "master.sqlite"
        self.folder = root / "crate-library"
        self.folder.mkdir()
        self.db = self.folder / "master.sqlite"
        build_database(self.db)
        self._before = self.db.read_bytes()
        self._old_master = library.MASTER
        self._old_backed = set(library._backed_up)
        library.MASTER = self.missing
        library._backed_up.clear()
        server.invalidate()
        self._env = mock.patch.dict(
            os.environ,
            {
                app_config.CONFIG_ENV: str(self.config),
                app_config.LOG_ENV: str(self.logs),
                "SERATO_LIBRARY_DISABLE_WATCH": "1",
            },
        )
        self._env.start()
        self.httpd = server.serve(port=0, require_library=True)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.httpd.server_address
        self.base = f"http://{host}:{port}"

    def tearDown(self) -> None:
        """Stop the server and restore the process library path.

        Returns:
            None.

        A live WAL writer is closed first. Windows cannot delete the
        database file while that connection is still open.
        """
        writer = getattr(self, "_wal_writer", None)
        if writer is not None:
            writer.close()
            self._wal_writer = None
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=3)
        snapshots.stop_watch()
        telemetry.shutdown()
        self._env.stop()
        app_log.close_files()
        library.MASTER = self._old_master
        library._backed_up.clear()
        library._backed_up.update(self._old_backed)
        setup_flow._set_remembered_missing(False)
        server.invalidate()
        self._tmp.cleanup()

    def test_chosen_folder_opens_the_library_without_writing_it(self) -> None:
        """Open an existing library and leave its bytes unchanged.

        A later title save still copies a backup first. The setup
        response does not include the path. A folder that is not a
        library is refused, and so is a shortcut to the file.

        Returns:
            None. The test fails if the file changes before the save,
            or if no backup is made for that save.
        """
        status, missing = _request(self.base, "/api/setup")
        self.assertEqual(status, 200)
        assert isinstance(missing, dict)
        self.assertFalse(missing["found"])
        status, picked = _request(self.base, "/api/setup", {"folder": str(self.folder)})
        self.assertEqual(status, 200)
        assert isinstance(picked, dict)
        self.assertTrue(picked["found"])
        self.assertEqual(picked["track_count"], 2)
        reported = json.dumps(picked)
        self.assertNotIn(str(self.db), reported)
        self.assertNotIn("master.sqlite", reported)
        self.assertEqual(self.db.read_bytes(), self._before)
        status, library_payload = _request(self.base, "/api/library")
        self.assertEqual(status, 200)
        assert isinstance(library_payload, dict)
        self.assertEqual(len(library_payload["tracks"]), 2)
        self.assertEqual(self.db.read_bytes(), self._before)
        stored = json.loads((self.config / app_config.LIBRARY_CHOICE_NAME).read_text(encoding="utf-8"))
        self.assertEqual(Path(stored["path"]).resolve(), self.db.resolve())
        status, settings = _request(self.base, "/api/settings")
        self.assertEqual(status, 200)
        self.assertNotIn(str(self.db), json.dumps(settings))
        other = self.folder.parent / "other"
        other.mkdir()
        (other / "master.sqlite").write_bytes(b"not a database")
        untouched = (other / "master.sqlite").read_bytes()
        status, rejected = _request(self.base, "/api/setup", {"folder": str(other)})
        self.assertEqual(status, 200)
        assert isinstance(rejected, dict)
        self.assertFalse(rejected["found"])
        self.assertEqual(rejected["summary"], setup_flow.WRONG_FOLDER_SUMMARY)
        self.assertEqual((other / "master.sqlite").read_bytes(), untouched)
        self.assertEqual(Path(library.MASTER).resolve(), self.db.resolve())
        link = self.folder.parent / "linked"
        link.mkdir()
        linked_db = link / "master.sqlite"
        try:
            linked_db.symlink_to(self.db)
        except OSError:
            linked_db = None
        if linked_db is not None:
            library.MASTER = self.missing
            refused = setup_flow.accept_folder(str(link))
            self.assertFalse(refused["found"])
            self.assertEqual(linked_db.read_bytes(), self._before)
            self.assertFalse(Path(library.MASTER).is_file())
            library.MASTER = self.db
        result = library.save_track(1, {"name": "Renamed", "bpm": 126})
        self.assertTrue(result["ok"])
        self.assertFalse((self.db.resolve().parent / "Backups").exists())
        self.assertNotEqual(self.db.read_bytes(), self._before)

    def test_open_library_is_not_switched(self) -> None:
        """Refuse a second library while one is already open.

        Returns:
            None. The test fails if the process path changes.
        """
        library.MASTER = self.db
        elsewhere = self.folder.parent / "elsewhere"
        elsewhere.mkdir()
        build_database(elsewhere / "master.sqlite")
        before = (elsewhere / "master.sqlite").read_bytes()
        chosen = setup_flow.accept_folder(str(elsewhere))
        self.assertFalse(chosen["found"])
        self.assertEqual(chosen["summary"], setup_flow.WRONG_FOLDER_SUMMARY)
        self.assertEqual(Path(library.MASTER).resolve(), self.db.resolve())
        self.assertEqual((elsewhere / "master.sqlite").read_bytes(), before)
        self.assertFalse((self.config / app_config.LIBRARY_CHOICE_NAME).exists())

    def test_remembered_library_is_used_on_the_next_start(self) -> None:
        """Use library.json when the server starts again.

        A relative path, a wrong file name, and a non-library file are
        ignored. A missing remembered file leaves the usual path alone.

        Returns:
            None. The test fails if the next start stays on the missing path.
        """
        setup_flow.accept_folder(str(self.folder))
        self.assertEqual(Path(library.MASTER).resolve(), self.db.resolve())
        library.MASTER = self.missing
        server.invalidate()
        httpd = server.serve(port=0, require_library=True)
        try:
            self.assertEqual(Path(library.MASTER).resolve(), self.db.resolve())
            host, port = httpd.server_address
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                status, payload = _request(f"http://{host}:{port}", "/api/setup")
            finally:
                httpd.shutdown()
                thread.join(timeout=3)
            self.assertEqual(status, 200)
            assert isinstance(payload, dict)
            self.assertTrue(payload["found"])
            self.assertNotIn(str(self.db), json.dumps(payload))
        finally:
            httpd.server_close()
            snapshots.stop_watch()
            telemetry.shutdown()
        choice = self.config / app_config.LIBRARY_CHOICE_NAME
        choice.write_text(json.dumps({"path": "relative/master.sqlite"}), encoding="utf-8")
        library.MASTER = self.missing
        with self.assertLogs("serato.library.config", level="WARNING") as caught:
            self.assertIsNone(app_config.load_remembered_library())
            setup_flow.apply_remembered_library()
        self.assertTrue(any("path" in line for line in caught.output))
        self.assertEqual(library.MASTER, self.missing)
        choice.write_text(
            json.dumps({"path": str(self.folder / "notes.sqlite")}),
            encoding="utf-8",
        )
        with self.assertLogs("serato.library.config", level="WARNING"):
            self.assertIsNone(app_config.load_remembered_library())
        plain = self.folder.parent / "plain"
        plain.mkdir()
        plain_db = plain / "master.sqlite"
        plain_db.write_bytes(b"not a database")
        app_config.remember_library(plain_db)
        library.MASTER = self.missing
        setup_flow.apply_remembered_library()
        self.assertEqual(library.MASTER, self.missing)
        self.assertEqual(plain_db.read_bytes(), b"not a database")
        described = setup_flow.describe_library()
        self.assertNotIn(setup_flow.REMEMBERED_MISSING_NOTE, str(described["summary"]))

    def test_missing_remembered_library_tells_you_the_usual_one_is_in_use(self) -> None:
        """Say so when a remembered library is gone and the usual one is used.

        The setup response is the sentence the library step shows. It does
        not include the missing path.

        Returns:
            None. The test fails if the usual library is hidden or the
            sentence is absent.
        """
        library.MASTER = self.db
        gone = self.folder.parent / "gone" / "master.sqlite"
        app_config.remember_library(gone)
        setup_flow.apply_remembered_library()
        self.assertEqual(Path(library.MASTER).resolve(), self.db.resolve())
        status, payload = _request(self.base, "/api/setup")
        self.assertEqual(status, 200)
        assert isinstance(payload, dict)
        self.assertTrue(payload["found"])
        self.assertIn(setup_flow.REMEMBERED_MISSING_NOTE, str(payload["summary"]))
        self.assertIn("usual place", str(payload["summary"]))
        reported = json.dumps(payload)
        self.assertNotIn(str(gone), reported)
        self.assertNotIn("master.sqlite", reported)

    def test_wal_validation_leaves_the_library_folder_unchanged(self) -> None:
        """Keep a WAL library folder free of wal, shm, and journal files.

        The database is in WAL mode and has already been checkpointed, so
        the folder holds only ``master.sqlite``. Setup's validation, which
        is the table check and the library summary, must leave that
        listing identical.

        Returns:
            None. The test fails if a sidecar appears or the library is
            not recognized.
        """
        folder = self.folder.parent / "Serato" / "Library"
        folder.mkdir(parents=True)
        db = folder / "master.sqlite"
        _write_checkpointed_wal_library(db)
        before = sorted(path.name for path in folder.iterdir())
        self.assertEqual(before, ["master.sqlite"])
        self.assertTrue(library.is_serato_database(db))
        library.MASTER = self.missing
        described = setup_flow.accept_folder(str(folder))
        self.assertTrue(described["found"])
        after = sorted(path.name for path in folder.iterdir())
        self.assertEqual(after, before)
        for name in after:
            self.assertFalse(name.endswith(("-wal", "-shm", "-journal")))

    def test_live_wal_validation_keeps_the_folder_and_the_track_count(self) -> None:
        """Read uncheckpointed WAL rows without touching the library tree.

        A writer stays open with 50 tracks that exist only in ``-wal``.
        The main file already holds 2. The table check, the setup summary,
        both folder picks, and the remembered-library check all run while
        that writer is open. The folder's names, hashes, and mtimes stay
        the same, and the reported count is 52.

        Returns:
            None. The test fails if a sidecar changes or the count is the
            checkpointed 2.
        """
        folder = self.folder.parent / "Serato" / "Library"
        folder.mkdir(parents=True)
        db = folder / "master.sqlite"
        self._wal_writer = _open_live_wal(db)
        try:
            before = _tree_stamp(folder)
            self.assertEqual(set(before), {"master.sqlite", "master.sqlite-shm", "master.sqlite-wal"})
            self.assertTrue(library.is_serato_database(db))
            library.status(db, from_copy=True)
            library.MASTER = db
            summary = setup_flow.describe_library()
            self.assertEqual(summary["track_count"], 52)
            confirmed = setup_flow.accept_folder(str(folder))
            self.assertEqual(confirmed["track_count"], 52)
            library.MASTER = self.missing
            adopted = setup_flow.accept_folder(str(folder))
            self.assertEqual(adopted["track_count"], 52)
            library.MASTER = self.missing
            app_config.remember_library(db)
            setup_flow.apply_remembered_library()
            self.assertEqual(Path(library.MASTER).resolve(), db.resolve())
            remembered = setup_flow.describe_library()
            self.assertEqual(remembered["track_count"], 52)
            status, payload = _request(self.base, "/api/setup")
            self.assertEqual(status, 200)
            assert isinstance(payload, dict)
            self.assertEqual(payload["track_count"], 52)
            self.assertEqual(_tree_stamp(folder), before)
        finally:
            if self._wal_writer is not None:
                self._wal_writer.close()
                self._wal_writer = None


def _tree_stamp(folder: Path) -> dict[str, tuple[str, int]]:
    """Hash and mtime every file under a library folder.

    Args:
        folder: Directory that holds ``master.sqlite``.

    Returns:
        Relative POSIX path to ``(sha256, mtime_ns)``. Shortcuts are skipped.
    """
    stamp: dict[str, tuple[str, int]] = {}
    for path in sorted(folder.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        stamp[path.relative_to(folder).as_posix()] = (digest, path.stat().st_mtime_ns)
    return stamp


def _open_live_wal(db: Path) -> sqlite3.Connection:
    """Open a WAL library with 2 checkpointed tracks and 50 only in ``-wal``.

    Args:
        db: Database file to create. Parent directories must exist.

    Returns:
        The writer connection. It is still open, and it will not checkpoint
        on close. The caller closes it.

    The checkpointed file is what a reader sees when ``-wal`` is ignored.
    The open connection is what keeps those extra rows out of the main file.
    """
    conn = sqlite3.connect(db)
    conn.setconfig(sqlite3.SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE, True)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA wal_autocheckpoint=0")
    conn.executescript(
        """
        CREATE TABLE space (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE asset (id INTEGER PRIMARY KEY);
        CREATE TABLE space_asset (
            id INTEGER PRIMARY KEY,
            asset_id INTEGER,
            space_id INTEGER
        );
        CREATE TABLE container (id INTEGER PRIMARY KEY);
        INSERT INTO space (id, name) VALUES (1, 'Serato Library');
        """
    )
    for asset_id in (1, 2):
        conn.execute("INSERT INTO asset (id) VALUES (?)", (asset_id,))
        conn.execute(
            "INSERT INTO space_asset (id, asset_id, space_id) VALUES (?, ?, 1)",
            (asset_id, asset_id),
        )
    conn.commit()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    for asset_id in range(3, 53):
        conn.execute("INSERT INTO asset (id) VALUES (?)", (asset_id,))
        conn.execute(
            "INSERT INTO space_asset (id, asset_id, space_id) VALUES (?, ?, 1)",
            (asset_id, asset_id),
        )
    conn.commit()
    return conn


def _write_checkpointed_wal_library(db: Path) -> None:
    """Write a WAL-mode library that has no sidecar files.

    Args:
        db: Database to create. Parent directories must exist.

    The journal mode stays WAL. A full checkpoint removes ``-wal`` and
    ``-shm`` before this returns, which is the state that a read-only
    open of the live file would turn back into sidecars.
    """
    conn = sqlite3.connect(db)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(
            """
            CREATE TABLE asset (id INTEGER);
            CREATE TABLE container (id INTEGER);
            CREATE TABLE space (id INTEGER);
            """
        )
        conn.commit()
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = Path(str(db) + suffix)
        if sidecar.exists():
            sidecar.unlink()


class _ArtSlots(HTMLParser):
    """Collect the SVG opening tag inside each setup illustration slot."""

    def __init__(self) -> None:
        """Start with no slot open.

        Returns:
            None.
        """
        super().__init__()
        self.found: dict[str, dict[str, str]] = {}
        self._slot: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Remember a slot, and the SVG that sits inside it.

        Args:
            tag: HTML tag name.
            attrs: Attributes on that tag.
        """
        values = {name: value or "" for name, value in attrs}
        if tag == "div" and "data-art-slot" in values:
            self._slot = values["data-art-slot"]
        elif tag == "svg" and self._slot is not None:
            self.found[self._slot] = values

    def handle_endtag(self, tag: str) -> None:
        """Close the current slot when its div ends.

        Args:
            tag: HTML tag name.
        """
        if tag == "div":
            self._slot = None


def _art_slots(page: str) -> dict[str, dict[str, str]]:
    """Return each setup illustration slot and the SVG attributes on it.

    Args:
        page: HTML of the library page.

    Returns:
        Slot name to the attributes of the SVG in that slot, in page order.
    """
    parser = _ArtSlots()
    parser.feed(page)
    return parser.found


def _request_text(base: str, path: str) -> tuple[int, str]:
    """GET a text response.

    Args:
        base: Server origin.
        path: Absolute path.

    Returns:
        The status and the decoded body.
    """
    with urllib.request.urlopen(base + path, timeout=5) as response:
        return response.status, response.read().decode("utf-8")


if __name__ == "__main__":
    unittest.main()
