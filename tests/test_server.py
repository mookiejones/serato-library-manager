"""HTTP API tests against a temporary library."""

from __future__ import annotations

import errno
import http.client
import json
import threading
import unittest
import unittest.mock
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from http.server import ThreadingHTTPServer
from xml.etree import ElementTree

import server
from server import (
    blank,
    display_beatgrid,
    encode_json,
    format_beat_position,
    format_bpm,
    format_bool,
    format_color,
    format_when,
    require_space,
)
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

    def test_beat_position_rounds_for_display(self) -> None:
        """Show a beatgrid position to the millisecond and hide binary noise.

        ``1.2300000190734863`` is the float32 value of 1.23 seconds. The
        panel string is ``1.230``. A non-finite value is blank. Nothing
        is written, and this string is not the export.

        Returns:
            None. The test fails if the long float is shown or a NaN becomes 0.
        """
        self.assertEqual(format_beat_position(1.2300000190734863), "1.230")
        self.assertEqual(format_beat_position(float("nan")), "")
        self.assertEqual(format_beat_position(float("inf")), "")
        script = Path(__file__).resolve().parents[1].joinpath("static", "app.js").read_text(encoding="utf-8")
        self.assertIn("beatSeconds(mark.position)", script)
        self.assertIn("toFixed(3)", script)
        self.assertIn("Number.isFinite(bpmNumber)", script)

    def test_nonfinite_bpm_is_null_in_json(self) -> None:
        """Send a non-finite beatgrid BPM as null, never as the token NaN.

        ``display_beatgrid`` clears the BPM. ``encode_json`` also replaces
        a non-finite float anywhere in a payload and refuses ``allow_nan``.
        A finite BPM and a marker that has no BPM are left alone. Nothing
        is written.

        Returns:
            None. The test fails if the JSON contains NaN or Infinity.
        """
        shown = display_beatgrid(
            [
                {"position": 1.2300000190734863, "bpm": float("nan")},
                {"position": 2.0, "bpm": float("inf")},
                {"position": 3.0, "bpm": float("-inf")},
                {"position": 4.0, "bpm": 128.0},
                {"position": 0.0, "beats": 4},
            ]
        )
        self.assertIsNone(shown[0]["bpm"])
        self.assertIsNone(shown[1]["bpm"])
        self.assertIsNone(shown[2]["bpm"])
        self.assertEqual(shown[3]["bpm"], 128.0)
        self.assertNotIn("bpm", shown[4])
        self.assertEqual(shown[0]["position"], "1.230")
        body = encode_json({"beatgrid": shown, "raw": float("nan"), "huge": float("inf")})
        text = body.decode("utf-8")
        self.assertNotIn("NaN", text)
        self.assertNotIn("Infinity", text)
        parsed = json.loads(text)
        self.assertIsNone(parsed["beatgrid"][0]["bpm"])
        self.assertIsNone(parsed["raw"])
        self.assertIsNone(parsed["huge"])
        self.assertEqual(parsed["beatgrid"][3]["bpm"], 128.0)

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

    def test_export_option_warns_on_an_unknown_value(self) -> None:
        """Log a warning and keep the default when the query word is unknown.

        ``yes`` is on and ``no`` is off. ``banana`` and ``nope`` are not
        switches, so the warning names the parameter and the default.

        Returns:
            None. The test fails if the warning is missing or the default changes.
        """
        self.assertTrue(server.export_option("yes", default=False, name="memory"))
        self.assertFalse(server.export_option("no", default=True, name="memory"))
        with self.assertLogs("serato", level="WARNING") as caught:
            self.assertTrue(server.export_option("banana", default=True, name="memory"))
            self.assertFalse(server.export_option("nope", default=False, name="hot_loops"))
        text = " ".join(caught.output)
        self.assertIn("memory='banana'", text)
        self.assertIn("Using on", text)
        self.assertIn("hot_loops='nope'", text)
        self.assertIn("Using off", text)


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
        if route.endswith(".m3u") or route.endswith(".xml") or route == "/":
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
        self.assertIn("<title>Serato Library</title>", page)
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

    def test_tokens_css_is_a_stylesheet(self) -> None:
        """Serve /tokens.css as text/css from static/.

        The page links this file before app.css. The body is the walnut
        and manila sheet, not the dark reference under design/.

        Returns:
            None. The test fails if the status, media type, or palette differs.
        """
        host, port = self.httpd.server_address
        connection = http.client.HTTPConnection(host, port, timeout=5)
        connection.putrequest("GET", "/tokens.css")
        connection.endheaders()
        response = connection.getresponse()
        body = response.read()
        content_type = response.getheader("Content-Type")
        connection.close()
        self.assertEqual(response.status, 200)
        self.assertEqual(content_type, "text/css; charset=utf-8")
        self.assertIn(b"--color-bg: #231910", body)
        self.assertNotIn(b"#0d0f14", body)

    def test_wizard_svg_is_an_image(self) -> None:
        """Serve a setup illustration as an SVG image.

        An ``img`` will not paint the file when the type is a generic
        byte stream.

        Returns:
            None. The test fails if the media type is not ``image/svg+xml``.
        """
        host, port = self.httpd.server_address
        connection = http.client.HTTPConnection(host, port, timeout=5)
        connection.putrequest("GET", "/img/wizard/wizard-welcome.svg")
        connection.endheaders()
        response = connection.getresponse()
        body = response.read()
        content_type = response.getheader("Content-Type")
        connection.close()
        self.assertEqual(response.status, 200)
        self.assertEqual(content_type, "image/svg+xml")
        self.assertIn(b"--illus-primary", body)
        self.assertNotIn(b"#", body)

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
        request = urllib.request.Request(self.base + "/api/export.rekordbox.xml?crate=all")
        with urllib.request.urlopen(request) as response:
            body = response.read()
            self.assertEqual(response.status, 200)
            self.assertIn("application/xml", response.headers.get("Content-Type", ""))
            self.assertIn("rekordbox.xml", response.headers.get("Content-Disposition", ""))
        root = ElementTree.fromstring(body)
        self.assertEqual(root.tag, "DJ_PLAYLISTS")
        names = {track.get("Name") for track in root.find("COLLECTION").findall("TRACK")}
        self.assertIn("Same", names)
        status, reported = self.request("/api/export.rekordbox.xml?crate=all&report=1")
        self.assertEqual(status, 200)
        summary = json.loads(reported)
        self.assertIn("Import to Collection", " ".join(summary["report"]))
        self.assertTrue(summary["xml"].startswith("<?xml"))
        self.assertIn("Colour", " ".join(summary["report"]))
        self.assertIn("smart crate", " ".join(summary["report"]).lower())
        status, bad_crate = self.request("/api/export.rekordbox.xml?crate=nope")
        self.assertEqual(status, 400)
        self.assertIn("not valid", bad_crate)
        refused = urllib.request.Request(self.base + "/api/export.rekordbox.xml?crate=nope")
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(refused)
        self.assertEqual(caught.exception.code, 400)
        self.assertNotIn("rekordbox.xml", caught.exception.headers.get("Content-Disposition", ""))
        caught.exception.close()
        for raw in ("+1", "1_2", "١"):
            status, _body = self.request("/api/export.rekordbox.xml?crate=" + urllib.parse.quote(raw))
            self.assertEqual(status, 400, raw)
        status, huge = self.request("/api/export.rekordbox.xml?crate=" + ("9" * 40))
        self.assertEqual(status, 400)
        status, missing = self.request("/api/export.rekordbox.xml?crate=999")
        self.assertEqual(status, 404)
        self.assertIn("not in this space", missing)
        with unittest.mock.patch.object(server.app_log.logger, "warning") as warning:
            status, known = self.request("/api/export.rekordbox.xml?crate=all&report=1&memory=0&hot_loops=yes")
            self.assertEqual(status, 200)
            self.assertEqual(warning.call_count, 0)
            status, defaults = self.request("/api/export.rekordbox.xml?crate=all&report=1")
            status, weird = self.request(
                "/api/export.rekordbox.xml?crate=all&report=1&memory=banana&hot_loops=nope"
            )
            self.assertEqual(status, 200)
            rendered = [call.args[0] % call.args[1:] for call in warning.call_args_list]
        self.assertEqual(len(rendered), 2)
        self.assertTrue(any("memory='banana'" in line and "Using on" in line for line in rendered))
        self.assertTrue(any("hot_loops='nope'" in line and "Using off" in line for line in rendered))
        self.assertTrue(json.loads(known)["xml"].startswith("<?xml"))
        self.assertEqual(json.loads(weird)["xml"], json.loads(defaults)["xml"])

    def test_hot_loops_reaches_the_export(self) -> None:
        """Pass hot loops through to the export for on, off, and omitted.

        ``true`` and ``1`` are on. ``false`` and ``0`` are off. A request
        that omits ``hot_loops`` is off. The export function is replaced,
        so the fixture audio is not read.

        Returns:
            None. The test fails if the boolean passed to the export differs.
        """
        sentinel = ('<?xml version="1.0" encoding="UTF-8"?>\n<DJ_PLAYLISTS/>', [])
        cases = (
            ("&hot_loops=true", True),
            ("&hot_loops=false", False),
            ("&hot_loops=1", True),
            ("&hot_loops=0", False),
            ("", False),
        )
        with unittest.mock.patch.object(server.rekordbox, "export_rekordbox", return_value=sentinel) as export:
            for query, expected in cases:
                with self.subTest(query=query or "missing"):
                    status, body = self.request(
                        "/api/export.rekordbox.xml?crate=all&report=1" + query
                    )
                    self.assertEqual(status, 200)
                    self.assertTrue(str(body).startswith('{"'))
                    self.assertIs(export.call_args.kwargs["hot_loops"], expected)
                    self.assertIs(export.call_args.kwargs["memory_cues"], True)

    def test_served_page_renders_hot_loops(self) -> None:
        """Serve the Hot loops control with its label and help line.

        GET ``/`` is the page file. The checkbox is present and unchecked.

        Returns:
            None. The test fails if the served page omits the control.
        """
        status, page = self.request("/")
        self.assertEqual(status, 200)
        self.assertIsInstance(page, str)
        assert isinstance(page, str)
        self.assertIn("Hot loops", page)
        self.assertIn("Uses a free hot-cue pad", page)
        self.assertRegex(page, r'id="rekordbox-hot-loops"[^>]*type="checkbox"')
        self.assertNotRegex(page, r'id="rekordbox-hot-loops"[^>]*\bchecked\b')

    def test_merge_preview_and_confirm(self) -> None:
        """Preview a duplicate merge, then confirm it over HTTP.

        The preview leaves both fixture rows in place. A body without
        ``confirm`` returns 400. The confirmed merge removes asset 2.
        The page script reads the plan fields this route returns.

        Returns:
            None. The test fails if the preview writes or the merge keeps the duplicate.
        """
        status, preview = self.request(
            "/api/duplicates/merge",
            {"keep_id": 1, "space": "Serato Library", "preview": True},
        )
        self.assertEqual(status, 200)
        self.assertTrue(preview["preview"])
        self.assertEqual(preview["remove_ids"], [2])
        with open_database(library.MASTER) as conn:
            before = conn.execute("SELECT COUNT(*) FROM asset WHERE id = 2").fetchone()[0]
        status, rejected = self.request(
            "/api/duplicates/merge",
            {"keep_id": 1, "delete_files": True},
        )
        self.assertEqual(status, 400)
        self.assertIn("error", rejected)
        status, merged = self.request(
            "/api/duplicates/merge",
            {"keep_id": 1, "confirm": True, "delete_files": False, "confirm_delete_files": False},
        )
        self.assertEqual(status, 200)
        self.assertTrue(merged["ok"])
        self.assertFalse(merged["preview"])
        with open_database(library.MASTER) as conn:
            after = conn.execute("SELECT COUNT(*) FROM asset WHERE id = 2").fetchone()[0]
        self.assertEqual(before, 1)
        self.assertEqual(after, 0)
        script = Path(__file__).resolve().parents[1].joinpath("static", "app.js").read_text(encoding="utf-8")
        page = Path(__file__).resolve().parents[1].joinpath("static", "index.html").read_text(encoding="utf-8")
        for field in ("/api/duplicates/merge", "confirm_delete_files", "cue_warning", "crates_added", "history_entries"):
            self.assertIn(field, script)
        self.assertIn("merge-dialog", page)
        self.assertIn("Merge copies", page)

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

    def test_health_does_not_read_the_library(self) -> None:
        """Answer ``/api/health`` when the master database is missing.

        ``serve`` is called with ``require_library`` false and a free port.
        The body is ``{"ok": true}``. Shutdown without a token is 404.

        Returns:
            None. The test fails if health touches the database or stays bound.
        """
        missing = Path("/tmp/serato-library-missing-master.sqlite")
        with unittest.mock.patch.object(server, "db_path", return_value=missing):
            httpd = server.serve(port=0, require_library=False)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        host, port = httpd.server_address
        try:
            with urllib.request.urlopen(f"http://{host}:{port}/api/health", timeout=5) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(json.loads(response.read().decode("utf-8")), {"ok": True})
            request = urllib.request.Request(
                f"http://{host}:{port}/api/shutdown",
                data=b"{}",
                method="POST",
            )
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(request, timeout=5)
            self.assertEqual(caught.exception.code, 404)
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(3)

    def test_shutdown_requires_the_token(self) -> None:
        """Accept shutdown only with the token stored on the server.

        A wrong token returns 403 and leaves the server running. The
        matching token returns 200 and stops ``serve_forever``.

        Returns:
            None. The test fails if a wrong token stops the server.
        """
        httpd = server.serve(port=0, require_library=False)
        httpd.shutdown_token = "token-value"
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        host, port = httpd.server_address
        base = f"http://{host}:{port}/api/shutdown"
        try:
            wrong = urllib.request.Request(
                base,
                data=b"{}",
                headers={server.SHUTDOWN_HEADER: "nope"},
                method="POST",
            )
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(wrong, timeout=5)
            self.assertEqual(caught.exception.code, 403)
            self.assertTrue(thread.is_alive())
            right = urllib.request.Request(
                base,
                data=b"{}",
                headers={server.SHUTDOWN_HEADER: "token-value"},
                method="POST",
            )
            with urllib.request.urlopen(right, timeout=5) as response:
                self.assertEqual(response.status, 200)
            thread.join(5)
            self.assertFalse(thread.is_alive())
        finally:
            if thread.is_alive():
                httpd.shutdown()
                thread.join(3)
            httpd.server_close()

    def test_focus_requires_the_token(self) -> None:
        """Bring the window forward only with the desktop focus token.

        A missing token returns 404. A wrong token returns 403 and does
        not call the callback. The matching token returns 200 and calls
        it. The server keeps running.

        Returns:
            None. The test fails if a wrong token focuses the window.
        """
        httpd = server.serve(port=0, require_library=False)
        focused: list[str] = []
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        host, port = httpd.server_address
        base = f"http://{host}:{port}/api/focus"
        try:
            missing = urllib.request.Request(base, data=b"{}", method="POST")
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(missing, timeout=5)
            self.assertEqual(caught.exception.code, 404)
            httpd.focus_token = "focus-token"
            httpd.focus_window = lambda: focused.append("focused")
            wrong = urllib.request.Request(
                base,
                data=b"{}",
                headers={server.FOCUS_HEADER: "nope"},
                method="POST",
            )
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(wrong, timeout=5)
            self.assertEqual(caught.exception.code, 403)
            self.assertEqual(focused, [])
            right = urllib.request.Request(
                base,
                data=b"{}",
                headers={server.FOCUS_HEADER: "focus-token"},
                method="POST",
            )
            with urllib.request.urlopen(right, timeout=5) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(json.loads(response.read().decode("utf-8")), {"ok": True})
            self.assertEqual(focused, ["focused"])
            self.assertTrue(thread.is_alive())
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(3)

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
