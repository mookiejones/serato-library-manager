"""Range streaming for tracks that are already in the library.

The temporary database is the fixture library. Audio bytes live beside it
only for these tests. Nothing here reads a person's Serato folder, and the
route does not write one.
"""

from __future__ import annotations

import hashlib
import http.client
import os
import threading
import unittest
import urllib.parse
from http.server import ThreadingHTTPServer
from pathlib import Path

import audio_stream
import server
from tests.fixture import TempLibrary, open_database

BODY = b"abcdefghijklmnopqrstuvwxyz"
SECRET = b"NOT-IN-LIBRARY-SECRET"


class RangeParseTests(unittest.TestCase):
    """Check Range parsing without opening a file or a database."""

    def test_open_ended_and_unsatisfiable_ranges(self) -> None:
        """Cover a whole file, an open end, a backwards range, and a suffix.

        No file is opened. An end past the size is clamped. A start past
        the size is 416.

        Returns:
            None. The test fails if a span disagrees.
        """
        whole = audio_stream.parse_range(None, 26)
        self.assertEqual((whole.status, whole.start, whole.end), (200, 0, 25))
        opened = audio_stream.parse_range("bytes=20-", 26)
        self.assertEqual((opened.status, opened.start, opened.end), (206, 20, 25))
        exact = audio_stream.parse_range("bytes=4-7", 26)
        self.assertEqual((exact.status, exact.start, exact.end), (206, 4, 7))
        backwards = audio_stream.parse_range("bytes=10-4", 26)
        self.assertEqual(backwards.status, 416)
        past = audio_stream.parse_range("bytes=1000-1001", 26)
        self.assertEqual(past.status, 416)
        suffix = audio_stream.parse_range("bytes=-4", 26)
        self.assertEqual((suffix.status, suffix.start, suffix.end), (206, 22, 25))
        self.assertEqual(audio_stream.parse_range("bytes=0-1,2-3", 26).status, 416)

    def test_chunks_stay_smaller_than_the_file(self) -> None:
        """Read a slice in pieces and never return it as one buffer.

        The file is a temporary file, not a Serato library. Each chunk is
        at most eight bytes, and joining them is the slice.

        Returns:
            None. The test fails if one read returns the whole slice.
        """
        import tempfile

        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "clip.bin"
            path.write_bytes(BODY)
            chunks = list(audio_stream.iter_bytes(path, 2, 21, chunk_size=8))
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 8 for chunk in chunks))
        self.assertEqual(b"".join(chunks), BODY[2:22])

    def test_content_types(self) -> None:
        """Name the media type for each suffix the player is asked to stream.

        No file is opened. The suffix is enough.

        Returns:
            None. The test fails if a suffix maps to the wrong type.
        """
        expected = {
            ".mp3": "audio/mpeg",
            ".m4a": "audio/mp4",
            ".aac": "audio/aac",
            ".flac": "audio/flac",
            ".wav": "audio/wav",
            ".aiff": "audio/aiff",
            ".aif": "audio/aiff",
            ".ogg": "audio/ogg",
        }
        for suffix, media in expected.items():
            with self.subTest(suffix=suffix):
                self.assertEqual(audio_stream.content_type_for(Path(f"tune{suffix}")), media)


class AudioRouteTests(unittest.TestCase):
    """Stream fixture audio through GET /api/audio and refuse every other path."""

    def setUp(self) -> None:
        """Start a temporary library and an HTTP server on a free port.

        The fixture database is the only library this process reads. The
        live Serato file is not opened.

        Returns:
            None.
        """
        self.library = TempLibrary()
        self.library.__enter__()
        self._next_id = 100
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        """Stop the server and delete the temporary library.

        Returns:
            None.
        """
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=3)
        self.library.__exit__(None, None, None)

    def exchange(
        self, method: str, path: str, headers: dict[str, str] | None = None
    ) -> tuple[int, dict[str, str], bytes]:
        """Send one request and return the status, headers, and body.

        Args:
            method: HTTP method, such as GET or HEAD.
            path: Absolute path and query.
            headers: Extra request headers. None sends none.

        Returns:
            Status code, lower-cased header names, and the raw body.
        """
        host, port = self.httpd.server_address
        if isinstance(port, str):
            raise AssertionError("The test server did not bind a TCP port.")
        conn = http.client.HTTPConnection(str(host), port, timeout=5)
        try:
            conn.request(method, path, headers=headers or {})
            response = conn.getresponse()
            body = response.read()
            found = {key.lower(): value for key, value in response.getheaders()}
            return response.status, found, body
        finally:
            conn.close()

    def add_track(self, relative: str, data: bytes, *, suffix: str | None = None) -> tuple[int, Path]:
        """Write an audio file and insert it as a Serato Library asset.

        Args:
            relative: Path under the temporary library directory.
            data: File bytes. The file is not a copy of anyone's music.
            suffix: Replacement suffix. None keeps the name that was given.

        Returns:
            The new asset id and the file path.
        """
        path = self.library.root / relative
        if suffix is not None:
            path = path.with_suffix(suffix)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        asset_id = self._next_id
        self._next_id += 1
        with open_database(self.library.db) as conn:
            conn.execute(
                """
                INSERT INTO asset
                    (id, name, artist, portable_id, file_name, is_missing, length_ms)
                VALUES (?, ?, ?, ?, ?, 0, 1000)
                """,
                (asset_id, "Tune", "DJ", str(path), path.name),
            )
            conn.execute(
                "INSERT INTO space_asset (id, asset_id, space_id) VALUES (?, ?, 1)",
                (asset_id, asset_id),
            )
        audio_stream.invalidate_index()
        return asset_id, path

    def tree(self) -> list[tuple[str, int, int, str]]:
        """Fingerprint the temporary library directory.

        Symlinks are recorded as links and are not followed. Regular files
        contribute size, mtime, and a sha256 of their bytes.

        Returns:
            One row per file, sorted by relative path.
        """
        rows: list[tuple[str, int, int, str]] = []
        root = self.library.root
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            dirnames.sort()
            for name in sorted(filenames):
                file = Path(dirpath) / name
                relative = file.relative_to(root).as_posix()
                if file.is_symlink():
                    rows.append((relative, -1, -1, f"link:{os.readlink(file)}"))
                    continue
                info = file.stat()
                digest = hashlib.sha256(file.read_bytes()).hexdigest()
                rows.append((relative, info.st_size, info.st_mtime_ns, digest))
        return rows

    def test_full_file_is_200(self) -> None:
        """Return the whole file for an asset id, with the mp3 media type.

        The body is the file on disk. Accept-Ranges says bytes. Nothing
        is written.

        Returns:
            None. The test fails if the body or the type differs.
        """
        asset_id, _path = self.add_track("music/song.mp3", BODY)
        status, headers, body = self.exchange("GET", f"/api/audio?id={asset_id}")
        self.assertEqual(status, 200)
        self.assertEqual(body, BODY)
        self.assertEqual(headers["content-type"], "audio/mpeg")
        self.assertEqual(headers["accept-ranges"], "bytes")
        self.assertEqual(headers["content-length"], str(len(BODY)))
        self.assertNotIn("content-range", headers)

    def test_range_is_206_with_the_exact_bytes(self) -> None:
        """Return only the requested slice, with a Content-Range header.

        bytes=4-7 is four bytes, not the rest of the file. The library
        file is not rewritten.

        Returns:
            None. The test fails if the slice or the header is wrong.
        """
        asset_id, _path = self.add_track("music/song.mp3", BODY)
        status, headers, body = self.exchange(
            "GET",
            f"/api/audio?id={asset_id}",
            {"Range": "bytes=4-7"},
        )
        self.assertEqual(status, 206)
        self.assertEqual(body, BODY[4:8])
        self.assertEqual(headers["content-range"], f"bytes 4-7/{len(BODY)}")
        self.assertEqual(headers["content-length"], "4")
        self.assertEqual(headers["accept-ranges"], "bytes")
        self.assertEqual(headers["content-type"], "audio/mpeg")

    def test_open_ended_range(self) -> None:
        """Return from the start byte through the end of the file.

        bytes=20- has no end. The body is the tail, and Content-Range
        names the last byte.

        Returns:
            None. The test fails if the tail is short or the header is closed.
        """
        asset_id, _path = self.add_track("music/song.mp3", BODY)
        status, headers, body = self.exchange(
            "GET",
            f"/api/audio?id={asset_id}",
            {"Range": "bytes=20-"},
        )
        self.assertEqual(status, 206)
        self.assertEqual(body, BODY[20:])
        self.assertEqual(headers["content-range"], f"bytes 20-{len(BODY) - 1}/{len(BODY)}")
        self.assertEqual(headers["content-length"], str(len(BODY) - 20))

    def test_bad_range_is_416(self) -> None:
        """Refuse a range that starts past the end of the file.

        The body is empty. Content-Range tells the client the size.
        The file is not opened for writing.

        Returns:
            None. The test fails if audio bytes are returned.
        """
        asset_id, _path = self.add_track("music/song.mp3", BODY)
        status, headers, body = self.exchange(
            "GET",
            f"/api/audio?id={asset_id}",
            {"Range": "bytes=1000-1001"},
        )
        self.assertEqual(status, 416)
        self.assertEqual(body, b"")
        self.assertEqual(headers["content-range"], f"bytes */{len(BODY)}")
        self.assertEqual(headers["accept-ranges"], "bytes")

    def test_head(self) -> None:
        """Send the media headers and an empty body for HEAD.

        Content-Length is the whole file. The body is empty, so a client
        can learn the size without a download.

        Returns:
            None. The test fails if HEAD returns bytes or omits the length.
        """
        asset_id, _path = self.add_track("music/song.mp3", BODY)
        status, headers, body = self.exchange("HEAD", f"/api/audio?id={asset_id}")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"")
        self.assertEqual(headers["content-length"], str(len(BODY)))
        self.assertEqual(headers["content-type"], "audio/mpeg")
        self.assertEqual(headers["accept-ranges"], "bytes")

    def test_path_outside_the_library_is_refused(self) -> None:
        """Refuse a real file that is not an asset.

        The file exists, is not a symlink, and has no ``..`` segment.
        ``indexed_path`` is the check that refuses it. Returning that
        real path from ``indexed_path`` without the index lookup would
        serve ``SECRET`` and fail this test.

        Returns:
            None. The test fails if the status is not 403 or the secret
            bytes are in the body.
        """
        secret = self.library.root / "secret.mp3"
        secret.write_bytes(SECRET)
        status, _headers, body = self.exchange(
            "GET",
            "/api/audio?" + urllib.parse.urlencode({"path": str(secret)}),
        )
        self.assertEqual(status, 403)
        self.assertNotIn(SECRET, body)
        self.assertNotIn(str(secret).encode(), body)

    def test_traversal_is_refused(self) -> None:
        """Refuse a ``..`` path even when it normalizes onto a library file.

        The normalized file is the asset that would otherwise stream.
        A realpath membership check alone would allow it. The ``..``
        refusal runs first.

        Returns:
            None. The test fails if the library bytes are returned.
        """
        _asset_id, song = self.add_track("music/song.mp3", BODY)
        nested = song.parent / "nested"
        nested.mkdir()
        climbed = nested / ".." / song.name
        self.assertIn("..", climbed.parts)
        status, _headers, body = self.exchange(
            "GET",
            "/api/audio?" + urllib.parse.urlencode({"path": str(climbed)}),
        )
        self.assertEqual(status, 403)
        self.assertNotEqual(body, BODY)

    def test_symlink_escape_is_refused(self) -> None:
        """Refuse a symlink whose target is outside the library index.

        The link itself is not an asset. Its target is a real file that
        is also not an asset. The response does not contain that file.

        Returns:
            None. The test fails if the secret bytes are streamed.
        """
        secret = self.library.root / "secret.mp3"
        secret.write_bytes(SECRET)
        link = self.library.root / "music" / "escape.mp3"
        link.parent.mkdir(parents=True, exist_ok=True)
        try:
            link.symlink_to(secret)
        except OSError:
            self.skipTest("symlinks are not available")
        status, _headers, body = self.exchange(
            "GET",
            "/api/audio?" + urllib.parse.urlencode({"path": str(link)}),
        )
        self.assertEqual(status, 403)
        self.assertNotIn(SECRET, body)

    def test_symlink_to_a_library_file_is_refused(self) -> None:
        """Refuse a symlink even when its target is the indexed file.

        realpath of the link is the library file, so the index would
        allow it. The symlink check refuses it first.

        Returns:
            None. The test fails if the link is followed.
        """
        _asset_id, song = self.add_track("music/song.mp3", BODY)
        link = song.parent / "alias.mp3"
        try:
            link.symlink_to(song)
        except OSError:
            self.skipTest("symlinks are not available")
        status, _headers, body = self.exchange(
            "GET",
            "/api/audio?" + urllib.parse.urlencode({"path": str(link)}),
        )
        self.assertEqual(status, 403)
        self.assertNotEqual(body, BODY)

    def test_sibling_directory_is_refused(self) -> None:
        """Refuse a file whose folder name only starts with a library folder.

        ``music-backup`` is not ``music``. A string prefix check would
        confuse them. The index does not.

        Returns:
            None. The test fails if the sibling bytes are streamed.
        """
        self.add_track("music/a.mp3", BODY)
        sibling = self.library.root / "music-backup" / "a.mp3"
        sibling.parent.mkdir()
        sibling.write_bytes(SECRET)
        status, _headers, body = self.exchange(
            "GET",
            "/api/audio?" + urllib.parse.urlencode({"path": str(sibling)}),
        )
        self.assertEqual(status, 403)
        self.assertNotIn(SECRET, body)

    def test_library_path_is_streamed(self) -> None:
        """Stream a path that is the real path of an asset.

        The same bytes come back as a request by id. A path query is
        still only a lookup.

        Returns:
            None. The test fails if an indexed path is refused.
        """
        _asset_id, song = self.add_track("music/song.mp3", BODY)
        status, headers, body = self.exchange(
            "GET",
            "/api/audio?" + urllib.parse.urlencode({"path": str(song)}),
        )
        self.assertEqual(status, 200)
        self.assertEqual(body, BODY)
        self.assertEqual(headers["content-type"], "audio/mpeg")

    def test_streaming_leaves_the_library_tree_unchanged(self) -> None:
        """Leave the temporary Serato folder byte-for-byte after a play.

        A full GET and a range GET run between two fingerprints. The
        database, the audio file, and the directory listing must match,
        including mtimes. No Backups directory is created.

        Returns:
            None. The test fails if any file is added, removed, or rewritten.
        """
        asset_id, _path = self.add_track("music/song.mp3", BODY)
        before = self.tree()
        full = self.exchange("GET", f"/api/audio?id={asset_id}")
        part = self.exchange("GET", f"/api/audio?id={asset_id}", {"Range": "bytes=0-3"})
        self.assertEqual(full[0], 200)
        self.assertEqual(part[0], 206)
        self.assertEqual(part[2], BODY[:4])
        self.assertEqual(self.tree(), before)
        names = [row[0] for row in before]
        self.assertNotIn("Backups", names)
        self.assertFalse(any(name.startswith("Backups/") for name in names))

    def test_content_types_on_the_wire(self) -> None:
        """Send the media type for each suffix the route knows.

        HEAD is enough. The body is empty. Each file is a few marker
        bytes, not a real encode, because the type comes from the name.

        Returns:
            None. The test fails if a suffix is served as the wrong type.
        """
        suffixes = {
            ".mp3": "audio/mpeg",
            ".m4a": "audio/mp4",
            ".aac": "audio/aac",
            ".flac": "audio/flac",
            ".wav": "audio/wav",
            ".aiff": "audio/aiff",
            ".ogg": "audio/ogg",
        }
        for suffix, media in suffixes.items():
            with self.subTest(suffix=suffix):
                asset_id, _path = self.add_track(f"music/tune{suffix}", b"tone", suffix=suffix)
                status, headers, body = self.exchange("HEAD", f"/api/audio?id={asset_id}")
                self.assertEqual(status, 200)
                self.assertEqual(body, b"")
                self.assertEqual(headers["content-type"], media)

    def test_relative_path_is_refused(self) -> None:
        """Refuse a relative path instead of joining it onto a directory.

        The name matches the file on disk. It is still not absolute, so
        it is not a lookup key.

        Returns:
            None. The test fails if the relative name streams the file.
        """
        _asset_id, song = self.add_track("music/song.mp3", BODY)
        status, _headers, body = self.exchange(
            "GET",
            "/api/audio?" + urllib.parse.urlencode({"path": song.name}),
        )
        self.assertEqual(status, 403)
        self.assertNotEqual(body, BODY)

    def test_unknown_id_is_404(self) -> None:
        """Refuse an asset id that is not in the database.

        Returns:
            None. The test fails if a missing id is streamed.
        """
        status, _headers, body = self.exchange("GET", "/api/audio?id=99999")
        self.assertEqual(status, 404)
        self.assertNotIn(BODY, body)
