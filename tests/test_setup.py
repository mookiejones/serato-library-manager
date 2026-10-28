"""First-run setup: library wording, the completion flag, and a missing library.

The cases use a temporary database and a temporary settings directory.
They do not open a live Serato library.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import app_config
import app_log
import library
import server
import setup_flow
from tests.fixture import TempLibrary


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
        config = Path(self._tmp.name) / "config"
        logs = Path(self._tmp.name) / "logs"
        config.mkdir()
        logs.mkdir()
        self._env = mock.patch.dict(
            os.environ,
            {app_config.CONFIG_ENV: str(config), app_config.LOG_ENV: str(logs)},
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
                    self.assertIn("Art placeholder", page)
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
