"""HTTP API tests against a temporary library."""

from __future__ import annotations

import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import server
from server import blank, format_bpm, format_bool, format_color, require_space
from tests.fixture import TempLibrary
import library
from library import LibraryError


class FormatTests(unittest.TestCase):
    def test_blank_and_bpm(self) -> None:
        self.assertTrue(blank(None))
        self.assertFalse(blank(0))
        self.assertEqual(format_bpm(120), "120")
        self.assertEqual(format_bool(1), "Yes")
        self.assertEqual(format_color(0xFFFFFF), "None")
        self.assertEqual(format_color(0xCC0000), "#CC0000")

    def test_require_space(self) -> None:
        self.assertEqual(require_space(None), "Serato Library")
        with self.assertRaises(LibraryError):
            require_space("Streaming")


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.library = TempLibrary()
        self.library.__enter__()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.httpd.server_address
        self.base = f"http://{host}:{port}"

    def tearDown(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=3)
        self.library.__exit__(None, None, None)

    def request(self, path: str, payload: dict | None = None) -> tuple[int, object]:
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.base + path, data=data, headers=headers)
        try:
            with urllib.request.urlopen(request) as response:
                body = response.read()
                status = response.status
        except urllib.error.HTTPError as exc:
            body = exc.read()
            status = exc.code
            exc.close()
        route = path.split("?", 1)[0]
        if route.endswith(".m3u") or route == "/":
            return status, body.decode("utf-8")
        return status, json.loads(body.decode("utf-8"))

    def test_library_and_page(self) -> None:
        status, page = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn("Serato library", page)
        status, payload = self.request("/api/library")
        self.assertEqual(status, 200)
        self.assertEqual(payload["track_count"], 2)
        self.assertTrue(payload["writable"])
        self.assertEqual(payload["tracks"][0]["name"], "Same")

    def test_save_and_read_track(self) -> None:
        status, saved = self.request(
            "/api/track",
            {"id": 1, "space": "Serato Library", "fields": {"comments": "peak time"}},
        )
        self.assertEqual(status, 200)
        self.assertTrue(saved["ok"])
        status, track = self.request("/api/track?id=1")
        self.assertEqual(status, 200)
        self.assertEqual(track["edit"]["comments"], "peak time")

    def test_bad_json_and_missing_track(self) -> None:
        request = urllib.request.Request(
            self.base + "/api/track",
            data=b"not-json",
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request)
        self.assertEqual(caught.exception.code, 400)
        caught.exception.close()
        status, missing = self.request("/api/track?id=99")
        self.assertEqual(status, 404)
        self.assertIn("error", missing)

    def test_duplicates_history_and_export(self) -> None:
        status, groups = self.request("/api/duplicates")
        self.assertEqual(status, 200)
        self.assertEqual(groups["count"], 1)
        status, history = self.request("/api/history")
        self.assertEqual(history["sessions"][0]["name"], "Friday")
        status, playlist = self.request("/api/export.m3u?crate=all")
        self.assertEqual(status, 200)
        self.assertIn("#EXTM3U", playlist)
        self.assertIn("same-a.mp3", playlist)

    def test_locked_library_returns_409(self) -> None:
        import sqlite3

        with sqlite3.connect(library.MASTER) as conn:
            conn.execute(
                "INSERT INTO lock (owner_process_id, owner_process_name) VALUES (99, 'Serato DJ Pro')"
            )
        with unittest.mock.patch.object(library, "_process_is_serato", return_value=True):
            status, payload = self.request(
                "/api/track",
                {"id": 1, "fields": {"name": "Blocked"}},
            )
        self.assertEqual(status, 409)
        self.assertFalse(payload["serato"]["writable"])


if __name__ == "__main__":
    unittest.main()
