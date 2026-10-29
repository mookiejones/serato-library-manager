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
from html.parser import HTMLParser
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
