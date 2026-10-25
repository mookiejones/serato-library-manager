"""HTTP API tests against a temporary library."""

from __future__ import annotations

import errno
import http.client
import json
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from http.server import ThreadingHTTPServer

import server
from server import blank, format_bpm, format_bool, format_color, format_when, require_space
from tests.fixture import TempLibrary, open_database
import library
from library import LibraryError


class FormatTests(unittest.TestCase):
    """Check display formatting without opening a database.

    Dates, colors, BPM, and blank values are rendered the way the detail
    pane shows them. No HTTP server is started.
    """
    def test_blank_and_bpm(self) -> None:
        """Format empty values, BPM, booleans, colors, and timestamps.

        ``0`` is a real value and must not look blank. White is the Serato
        "no color" value. Timestamps use English month names so the label
        does not follow the machine locale. Nothing is written.

        Returns:
            None. The test fails if a formatted label differs.
        """
        self.assertTrue(blank(None))
        self.assertFalse(blank(0))
        self.assertEqual(format_bpm(120), "120")
        self.assertEqual(format_bool(1), "Yes")
        self.assertEqual(format_color(0xFFFFFF), "None")
        self.assertEqual(format_color(0xCC0000), "#CC0000")
        when = datetime(2026, 1, 15, 15, 5)
        self.assertEqual(format_when(int(when.timestamp())), "Jan 15, 2026 3:05 PM")
        self.assertEqual(format_when(when.timestamp()), "Jan 15, 2026 3:05 PM")
        self.assertEqual(format_when(0), "—")
        self.assertEqual(format_when(False), "—")

    def test_require_space(self) -> None:
        """Default a missing space to Serato Library and reject an unknown one.

        No database is opened. ``Streaming`` is outside the four spaces this
        page edits.

        Returns:
            None. The test fails if the default or the rejection changes.
        """
        self.assertEqual(require_space(None), "Serato Library")
        with self.assertRaises(LibraryError):
            require_space("Streaming")


class ApiTests(unittest.TestCase):
    """Exercise the HTTP routes against a temporary library.

    ``setUp`` starts ``Handler`` on an ephemeral port and points the library
    at the fixture database. ``tearDown`` stops the server and closes that
    database. The live Serato file is not used.
    """
    def setUp(self) -> None:
        """Start a temporary library and an HTTP server on a free port.

        Writes the fixture database, binds ``127.0.0.1`` with port 0, and serves
        ``Handler`` on a daemon thread.

        Returns:
            None.
        """
        self.library = TempLibrary()
        self.library.__enter__()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.httpd.server_address
        self.base = f"http://{host}:{port}"

    def tearDown(self) -> None:
        """Stop the test server and delete the temporary library.

        Shuts the listening socket down and closes the fixture SQLite file so
        Windows can remove the directory.

        Returns:
            None.
        """
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=3)
        self.library.__exit__(None, None, None)

    def request(self, path: str, payload: dict | None = None) -> tuple[int, object]:
        """Send one request to the test server and decode the body.

        JSON routes are parsed. The page and the M3U route stay text. HTTP
        errors are returned as status-and-body pairs instead of raising, except
        where a test calls ``urlopen`` itself.

        Args:
            path: Absolute path and query, beginning with ``/``.
            payload: JSON object to POST. None sends a GET.

        Returns:
            The HTTP status and either a decoded JSON value or a text body.
        """
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
        """Serve the page and the crate payload for the default space.

        GET ``/`` reads ``static/index.html``. GET ``/api/library`` reads the
        fixture database and returns two tracks. Nothing is written.

        Returns:
            None. The test fails if the page or the track count is wrong.
        """
        status, page = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn("Serato library", page)
        status, payload = self.request("/api/library")
        self.assertEqual(status, 200)
        self.assertEqual(payload["track_count"], 2)
        self.assertTrue(payload["writable"])
        self.assertEqual(payload["serato"]["file_manager"], library.file_manager_name())
        self.assertEqual(payload["tracks"][0]["name"], "Same")

    def test_static_path_stays_in_the_directory(self) -> None:
        """Refuse a request that climbs out of static/.

        The client sends the path unchanged, so ``..`` reaches the handler.
        The response is 404 and does not include the server source. A file
        inside static/ is still served.

        Returns:
            None. The test fails if the parent file is returned.
        """
        host, port = self.httpd.server_address
        connection = http.client.HTTPConnection(host, port, timeout=5)
        connection.putrequest("GET", "/../server.py")
        connection.endheaders()
        response = connection.getresponse()
        body = response.read()
        connection.close()
        self.assertEqual(response.status, 404)
        self.assertNotIn(b"def serve", body)
        connection = http.client.HTTPConnection(host, port, timeout=5)
        connection.putrequest("GET", "/app.css")
        connection.endheaders()
        response = connection.getresponse()
        body = response.read()
        connection.close()
        self.assertEqual(response.status, 200)
        self.assertIn(b"--walnut", body)

    def test_save_and_read_track(self) -> None:
        """Save a comment through POST ``/api/track`` and read it back.

        The write updates the fixture database and may record a backup beside
        it. The following GET must show the comment in the edit form.

        Returns:
            None. The test fails if the saved comment does not round-trip.
        """
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
        """Reject a body that is not JSON and a track id that is absent.

        The bad POST must return 400 before a write. The missing id must return
        404. The fixture row is left unchanged by the bad body.

        Returns:
            None. The test fails if either status differs.
        """
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
        """Read duplicate groups, history, and an extended M3U over HTTP.

        All three are GET routes against the fixture. The playlist must name
        the fixture file. Nothing is written.

        Returns:
            None. The test fails if a route omits the fixture data.
        """
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
        """Return 409 when a write finds Serato holding the lock.

        Inserts a lock row and patches the process check. POST ``/api/track``
        must answer with the lock payload and must not rename the track.

        Returns:
            None. The test fails unless the status is 409 and writes are refused.
        """
        with open_database(library.MASTER) as conn:
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

    def test_frozen_app_reads_static_from_the_bundle(self) -> None:
        """Read ``static/`` from the PyInstaller extract directory when frozen.

        Patches ``sys.frozen`` and ``sys._MEIPASS``. No bundle is built and no
        file is opened. A source checkout uses the directory beside ``server.py``
        only when those flags are absent.

        Returns:
            None. The test fails if ``app_root`` ignores the frozen path.
        """
        with unittest.mock.patch.object(server.sys, "frozen", True, create=True), unittest.mock.patch.object(
            server.sys, "_MEIPASS", "/bundle", create=True
        ):
            self.assertEqual(server.app_root(), Path("/bundle"))

    def test_taken_port_names_the_other_server(self) -> None:
        """Name the other server when port 8765 is already bound.

        Patches the listening socket so it raises ``EADDRINUSE``. ``serve`` must
        raise ``SystemExit`` and mention ``server.py``. No second socket is kept.

        Returns:
            None. The test fails if the exit message hides the conflict.
        """
        with unittest.mock.patch(
            "server.ThreadingHTTPServer",
            side_effect=OSError(errno.EADDRINUSE, "Address already in use"),
        ):
            with self.assertRaises(SystemExit) as caught:
                server.serve()
        self.assertIn("server.py", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
