"""A library file that exists but does not open counts as Serato running.

Issue #90, part 2. Every case uses the temporary Serato-shaped database
from ``tests.fixture``. The live Serato library is not opened, and nothing
is written inside a Serato folder.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import app_config
import files
import library
import server
import setup_flow
import snapshots
from library import LibraryError, SeratoOpen
from snapshots import DriveSpec, SnapshotBlocked, SnapshotStore
from tests.fixture import TempLibrary, open_database

OPEN_ERRORS = ("disk I/O error", "unable to open database file")


def _failing_open(text: str) -> Callable[..., sqlite3.Connection]:
    """Return a ``read_conn`` stand-in that raises one SQLite open error.

    Args:
        text: The ``OperationalError`` text.

    Returns:
        A function with the ``read_conn`` signature that always raises.
    """

    def opener(path: Path | None = None) -> sqlite3.Connection:
        raise sqlite3.OperationalError(text)

    return opener


@contextmanager
def _open_fails(text: str) -> Iterator[None]:
    """Make every read-only open of the library raise ``text``.

    Args:
        text: The ``OperationalError`` text.

    Yields:
        None while ``library.read_conn`` and ``library.copied_read_conn`` raise.
    """
    with mock.patch.object(library, "read_conn", _failing_open(text)), mock.patch.object(
        library, "copied_read_conn", _failing_open(text)
    ), mock.patch("snapshots.serato_dj_running", return_value=False):
        yield


def _backups(temp: TempLibrary) -> list[Path]:
    """Return the database copies and saved snapshots beside the fixture.

    The snapshot store's ``state.json`` bookkeeping file is not a copy of
    the library and is not counted.

    Args:
        temp: Fixture library.

    Returns:
        ``serato-web-*`` backup folders and snapshot directories, or an
        empty list.
    """
    folder = temp.db.resolve().parent / "Backups"
    if not folder.is_dir():
        return []
    found = sorted(folder.glob("serato-web-*"))
    store = folder / "snapshots"
    if store.is_dir():
        found.extend(sorted(item for item in store.iterdir() if item.is_dir()))
    return found


class OpenErrorStatusTests(unittest.TestCase):
    """``status`` and the write paths that read it."""

    def test_non_locked_open_error_reports_open_with_the_sqlite_text(self) -> None:
        """Report open and not writable, and keep the SQLite text.

        Both the live read and the setup copy are covered.

        Returns:
            None. The test fails if status raises, reports writable, or
            hides the SQLite error behind a plain Serato message.
        """
        for text in OPEN_ERRORS:
            for from_copy in (False, True):
                with self.subTest(text=text, from_copy=from_copy), TempLibrary():
                    with _open_fails(text):
                        info = library.status(from_copy=from_copy)
                    self.assertIs(info["open"], True)
                    self.assertIs(info["writable"], False)
                    self.assertIn(text, str(info["message"]))
                    self.assertEqual(info["open_error"], text)
                    self.assertNotEqual(info["message"], library.LOCKED_MESSAGE)
                    self.assertFalse(info["serato_running"])
                    self.assertEqual(info["file_manager"], library.file_manager_name())

    def test_first_query_error_reports_open(self) -> None:
        """Treat a real failure of the first query as busy, without a mock.

        The fixture's ``lock`` table is replaced by a view that calls a
        function SQLite does not have, so reading it raises an
        ``OperationalError`` that is neither "locked" nor "no such table".

        Returns:
            None. The test fails if status raises or allows edits.
        """
        with TempLibrary() as temp:
            with open_database(temp.db) as conn:
                conn.execute("DROP TABLE lock")
                conn.execute(
                    "CREATE VIEW lock AS SELECT serato_missing_fn() AS owner_process_id, "
                    "'x' AS owner_process_name"
                )
            with mock.patch("snapshots.serato_dj_running", return_value=False):
                info = library.status()
                with self.assertRaises(SeratoOpen) as caught:
                    library.begin_write()
            backups = _backups(temp)
        self.assertTrue(info["open"])
        self.assertFalse(info["writable"])
        self.assertIn("serato_missing_fn", str(info["message"]))
        self.assertIn("serato_missing_fn", caught.exception.message)
        self.assertEqual(caught.exception.status, 409)
        self.assertEqual(backups, [])

    def test_every_library_write_refuses_before_a_backup(self) -> None:
        """Refuse track, crate, and M3U writes, and copy nothing.

        A merge reads the library before it writes, so it is covered over
        HTTP, where that failed read must also answer 409.

        Returns:
            None. The test fails if a write is allowed, raises something
            other than ``SeratoOpen``, loses the SQLite text, or makes a backup.
        """
        writes: dict[str, Callable[[], object]] = {
            "begin_write": library.begin_write,
            "save_track": lambda: library.save_track(1, {"name": "Renamed"}),
            "crate_create": lambda: library.crate_action(
                {"action": "create", "space": library.LIBRARY_SPACE, "name": "New"}
            ),
            "crate_add": lambda: library.crate_action(
                {"action": "add", "space": library.LIBRARY_SPACE, "id": 1, "asset": 1}
            ),
            "import_m3u": lambda: library.import_m3u(
                library.LIBRARY_SPACE, None, "Imported", "#EXTM3U\n"
            ),
        }
        for text in OPEN_ERRORS:
            for name, write in writes.items():
                with self.subTest(text=text, write=name), TempLibrary() as temp:
                    before = temp.db.read_bytes()
                    with _open_fails(text):
                        with self.assertRaises(SeratoOpen) as caught:
                            write()
                    self.assertIn(text, caught.exception.message)
                    self.assertEqual(caught.exception.status, 409)
                    self.assertEqual(caught.exception.info["open_error"], text)
                    self.assertFalse(caught.exception.info["writable"])
                    self.assertEqual(temp.db.read_bytes(), before)
                    self.assertEqual(_backups(temp), [])

    def test_write_transaction_open_error_is_serato_open(self) -> None:
        """Refuse with ``SeratoOpen`` when the write connection fails to open.

        The status read succeeds. Opening the write connection then raises
        a non-locked error. That used to escape as a bare ``OperationalError``.

        Returns:
            None. The test fails unless the refusal is a 409 with the text.
        """
        real = sqlite3.connect

        def connect(*args: object, **kwargs: object) -> sqlite3.Connection:
            if kwargs.get("timeout") == 1:
                raise sqlite3.OperationalError("disk I/O error")
            return real(*args, **kwargs)  # type: ignore[arg-type]

        with TempLibrary() as temp:
            before = temp.db.read_bytes()
            with mock.patch("snapshots.serato_dj_running", return_value=False), mock.patch.object(
                library.sqlite3, "connect", connect
            ):
                with self.assertRaises(SeratoOpen) as caught:
                    library.begin_write()
            after = temp.db.read_bytes()
        self.assertIn("disk I/O error", caught.exception.message)
        self.assertFalse(caught.exception.info["writable"])
        self.assertTrue(caught.exception.info["open"])
        self.assertEqual(after, before)

    def test_locked_error_keeps_the_serato_message(self) -> None:
        """Keep today's message and refusal for a locked database.

        Returns:
            None. The test fails if a lock gains SQLite text or stops refusing.
        """
        with TempLibrary() as temp:
            with _open_fails("database is locked"):
                info = library.status()
                with self.assertRaises(SeratoOpen) as caught:
                    library.save_track(1, {"name": "Renamed"})
            backups = _backups(temp)
        self.assertTrue(info["open"])
        self.assertFalse(info["writable"])
        self.assertEqual(info["process"], "Serato DJ Pro")
        self.assertEqual(info["message"], library.LOCKED_MESSAGE)
        self.assertIsNone(info["open_error"])
        self.assertEqual(caught.exception.message, library.LOCKED_MESSAGE)
        self.assertEqual(backups, [])

    def test_open_library_reports_no_open_error(self) -> None:
        """Report ``open_error`` as null when the library opens normally.

        Returns:
            None. The test fails if a healthy library carries an open error.
        """
        with TempLibrary():
            with mock.patch("snapshots.serato_dj_running", return_value=False):
                info = library.status()
        self.assertIn("open_error", info)
        self.assertIsNone(info["open_error"])
        self.assertTrue(info["writable"])

    def test_missing_library_is_not_reported_as_running(self) -> None:
        """Keep the not-found error for a missing file, even if the open raises.

        The setup wizard still sees no library and no running Serato.

        Returns:
            None. The test fails if a missing file reads as Serato open.
        """
        with TempLibrary() as temp:
            missing = temp.root / "elsewhere" / "master.sqlite"
            with mock.patch("snapshots.serato_dj_running", return_value=False):
                with self.assertRaises(LibraryError) as plain:
                    library.status(missing)
                with self.assertRaises(LibraryError) as copied:
                    library.status(missing, from_copy=True)
                # A file removed between the exists check and the open.
                with mock.patch.object(library, "read_conn", _failing_open("unable to open database file")):
                    with self.assertRaises(LibraryError) as raced:
                        library.status(missing)
                old = library.MASTER
                library.MASTER = missing
                try:
                    described = setup_flow.describe_library()
                    with self.assertRaises(LibraryError) as write:
                        library.begin_write()
                finally:
                    library.MASTER = old
        self.assertNotIsInstance(plain.exception, SeratoOpen)
        self.assertEqual(plain.exception.status, 404)
        self.assertNotIsInstance(copied.exception, SeratoOpen)
        self.assertNotIsInstance(raced.exception, SeratoOpen)
        self.assertEqual(raced.exception.status, 404)
        self.assertNotIsInstance(write.exception, SeratoOpen)
        self.assertFalse(described["found"])
        self.assertFalse(described["serato_running"])

    def test_wizard_shows_the_open_error(self) -> None:
        """Show the SQLite text in setup instead of "Serato is quit".

        Returns:
            None. The test fails if setup says the library is writable.
        """
        with TempLibrary():
            with _open_fails("disk I/O error"):
                described = setup_flow.describe_library()
        self.assertTrue(described["found"])
        self.assertFalse(described["status_writable"])
        self.assertIn("disk I/O error", str(described["status_message"]))
        self.assertFalse(described["serato_running"])


class OpenErrorFileTests(unittest.TestCase):
    """``files.plan`` and ``files.execute`` against a library that will not open."""

    def test_file_change_refuses_and_leaves_the_file(self) -> None:
        """Refuse a confirmed rename before the file is touched.

        ``execute`` checks the status before it reads the library, so it
        refuses with ``SeratoOpen``. The preview is covered over HTTP.

        Returns:
            None. The test fails if the file moves or a backup is made.
        """
        for text in OPEN_ERRORS:
            with self.subTest(text=text), TempLibrary() as temp:
                song = temp.root / "music" / "same-a.mp3"
                song.parent.mkdir()
                song.write_bytes(b"audio-a")
                with open_database(temp.db) as conn:
                    conn.execute("UPDATE asset SET portable_id = ? WHERE id = 1", (str(song),))
                payload = {"action": "rename", "path": str(song), "name": "renamed.mp3"}
                with _open_fails(text):
                    with self.assertRaises(SeratoOpen) as caught:
                        files.execute({**payload, "confirm": True})
                self.assertIn(text, caught.exception.message)
                self.assertFalse(caught.exception.info["writable"])
                self.assertTrue(song.is_file())
                self.assertFalse((song.parent / "renamed.mp3").exists())
                self.assertEqual(_backups(temp), [])


class OpenErrorRestoreTests(unittest.TestCase):
    """Snapshot restore refuses while the library will not open."""

    def test_restore_refuses_and_dry_run_says_why(self) -> None:
        """Refuse a restore and report the SQLite text in the dry run.

        Returns:
            None. The test fails if the restore runs or a file changes.
        """
        with TempLibrary() as temp:
            music = temp.root / "music"
            serato = music / "_Serato_"
            (serato / "Subcrates").mkdir(parents=True)
            crate = serato / "Subcrates" / "House.crate"
            crate.write_bytes(b"before")
            store = SnapshotStore(temp.db, [DriveSpec(
                drive_id="tour",
                label="Tour",
                serato_root=serato,
                music_root=music,
                role="external",
                present=True,
            )])
            store.serato_running = lambda: False
            store.process_names = lambda: []
            saved = store.take("manual", "While Serato is quit.")
            crate.write_bytes(b"after")
            database = temp.db.read_bytes()
            count = len(store.list_snapshots())
            with _open_fails("disk I/O error"):
                with self.assertRaises(SnapshotBlocked) as caught:
                    store.restore(saved["id"])
                preview = store.plan(saved["id"])
            self.assertIn("disk I/O error", caught.exception.message)
            self.assertIn("disk I/O error", str(preview["restore_blocked"]))
            self.assertEqual(crate.read_bytes(), b"after")
            self.assertEqual(temp.db.read_bytes(), database)
            self.assertEqual(len(store.list_snapshots()), count)


class OpenErrorHttpTests(unittest.TestCase):
    """The server's 409 ``serato`` object for an open error."""

    def setUp(self) -> None:
        """Start the fixture library, a config directory, and the server.

        Returns:
            None.
        """
        self._dir = tempfile.TemporaryDirectory()
        config = Path(self._dir.name) / "config"
        config.mkdir()
        self._env = mock.patch.dict(os.environ, {app_config.CONFIG_ENV: str(config)})
        self._env.start()
        self.library = TempLibrary()
        self.library.__enter__()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.httpd.server_address[:2]
        self.base = f"http://{host}:{port}"

    def tearDown(self) -> None:
        """Stop the server and delete the temporary files.

        Returns:
            None.
        """
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=3)
        self.library.__exit__(None, None, None)
        self._env.stop()
        self._dir.cleanup()

    def request(self, path: str, payload: dict | None = None) -> tuple[int, dict]:
        """Send one JSON request.

        Args:
            path: Absolute path and query.
            payload: JSON body for POST. None sends GET.

        Returns:
            The status code and the decoded JSON object.
        """
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {} if payload is None else {"Content-Type": "application/json"}
        request = urllib.request.Request(self.base + path, data=data, headers=headers)
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read()
            exc.close()
            return exc.code, json.loads(body.decode("utf-8"))

    def test_writes_return_409_with_the_sqlite_text(self) -> None:
        """Answer 409 with a ``serato`` object for every write route.

        The related-crate write, the merge, and the file preview read the
        library before they write, so that read fails too. They must still
        answer 409, not 500.

        Returns:
            None. The test fails if a write is allowed or the text is lost.
        """
        before = self.library.db.read_bytes()
        song = self.library.root / "music" / "same-a.mp3"
        song.parent.mkdir()
        song.write_bytes(b"audio-a")
        rename = {"action": "rename", "path": str(song), "name": "renamed.mp3"}
        with _open_fails("disk I/O error"):
            status_code, info = self.request("/api/status")
            posts = {
                "crate": self.request(
                    "/api/crate", {"action": "create", "space": library.LIBRARY_SPACE, "name": "New"}
                ),
                "track": self.request("/api/track", {"id": 1, "fields": {"name": "Renamed"}}),
                "related": self.request("/api/related", {"action": "crate", "asset": 1}),
                "merge": self.request("/api/duplicates/merge", {"keep_id": 1, "confirm": True}),
                "m3u": self.request(
                    "/api/import.m3u",
                    {"space": library.LIBRARY_SPACE, "name": "Imported", "text": "#EXTM3U\n"},
                ),
                "files_plan": self.request("/api/files", rename),
                "files_execute": self.request("/api/files", {**rename, "confirm": True}),
            }
        self.assertEqual(status_code, 200)
        self.assertTrue(info["open"])
        self.assertFalse(info["writable"])
        self.assertEqual(info["open_error"], "disk I/O error")
        for name, (code, body) in posts.items():
            with self.subTest(write=name):
                self.assertEqual(code, 409, body)
                self.assertIn("disk I/O error", body["error"])
                self.assertTrue(body["serato"]["open"])
                self.assertFalse(body["serato"]["writable"])
                self.assertIn("disk I/O error", body["serato"]["message"])
        self.assertEqual(self.library.db.read_bytes(), before)
        self.assertEqual(_backups(self.library), [])
        self.assertTrue(song.is_file())


if __name__ == "__main__":
    unittest.main()
