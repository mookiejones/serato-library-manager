"""Cue-safe move, rename, replace, and delete tests.

The suite uses the temporary Serato-shaped database and temporary audio
files. It does not open a live Serato library or the real Trash.
"""

from __future__ import annotations

import errno
import json
import os
import sqlite3
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib.parse import unquote

import app_config
import files
import library
import related
import server
import telemetry
from tests.fixture import ROOT, TempLibrary, open_database
from tests.test_tags import _id3_file, _markers_payload

import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


ROOT_SCHEMA = """
CREATE TABLE asset (
    id INTEGER PRIMARY KEY,
    portable_id TEXT,
    file_name TEXT,
    video_portable_id TEXT,
    file_path TEXT,
    file_size INTEGER,
    is_missing INTEGER,
    time_modified INTEGER,
    revision INTEGER
);
CREATE TABLE serato (revision INTEGER);
CREATE TABLE container (
    id INTEGER PRIMARY KEY,
    portable_id TEXT
);
"""


class FileManagerTests(unittest.TestCase):
    """Move, rename, replace, and delete against the fixture database."""

    def setUp(self) -> None:
        """Point the library at temporary audio and a sibling location database.

        Asset 1 is in the Warmup crate and in Prepare. Its path columns
        and the mirrored root database start at the same file. Trash is
        redirected to a directory inside the temporary library.

        Returns:
            None.
        """
        self.library = TempLibrary()
        self.library.__enter__()
        self.music = self.library.root / "music"
        self.music.mkdir()
        self.song = self.music / "same-a.mp3"
        self.other = self.music / "same-b.mp3"
        self.song.write_bytes(b"audio-a")
        self.other.write_bytes(b"audio-b")
        self.root_db = self.library.root / "root.sqlite"
        self.trash = self.library.root / "trash-bin"
        self._old_trash = os.environ.get(files._TRASH_ENV)
        os.environ[files._TRASH_ENV] = str(self.trash)
        self._seed()

    def tearDown(self) -> None:
        """Restore the trash override and delete the temporary library.

        Returns:
            None.
        """
        if self._old_trash is None:
            os.environ.pop(files._TRASH_ENV, None)
        else:
            os.environ[files._TRASH_ENV] = self._old_trash
        self.library.__exit__(None, None, None)

    def _seed(self) -> None:
        """Store absolute paths and a location database beside the fixture.

        Returns:
            None.
        """
        song = str(self.song.resolve())
        other = str(self.other.resolve())
        conn = sqlite3.connect(self.root_db)
        try:
            conn.executescript(ROOT_SCHEMA)
            conn.execute("INSERT INTO serato (revision) VALUES (1)")
            conn.execute(
                """
                INSERT INTO asset
                    (id, portable_id, file_name, video_portable_id, file_path, is_missing)
                VALUES (10, ?, 'same-a.mp3', ?, ?, 0)
                """,
                (song, song, song),
            )
            conn.commit()
        finally:
            conn.close()
        with open_database(self.library.db) as conn:
            conn.execute("ALTER TABLE asset ADD COLUMN file_path TEXT")
            conn.execute(
                """
                UPDATE asset
                SET portable_id = ?, file_name = 'same-a.mp3', file_path = ?,
                    video_portable_id = ?, location_id = 3, external_id = 10, is_missing = 0
                WHERE id = 1
                """,
                (song, song, song),
            )
            conn.execute(
                """
                UPDATE asset
                SET portable_id = ?, file_name = 'same-b.mp3', is_missing = 0
                WHERE id = 2
                """,
                (other,),
            )
            conn.execute(
                """
                INSERT INTO container
                    (id, parent_id, name, type, list_order, space_id, time_added, expanded, portable_id)
                VALUES (3, 1, 'Warmup', 1, 1, 1, 2, 0, ?)
                """,
                (song,),
            )
            conn.execute(
                """
                INSERT INTO container_asset (id, asset_id, container_id, list_order)
                VALUES (1, 1, 3, 0)
                """
            )
            conn.execute("INSERT INTO space_asset (id, asset_id, space_id) VALUES (3, 1, 2)")
            conn.execute(
                "INSERT INTO connection (location_id, database_uri) VALUES (3, ?)",
                (self.root_db.resolve().as_uri(),),
            )

    def _master(self, sql: str, params: tuple = ()) -> sqlite3.Row:
        """Read one row from the fixture database.

        Args:
            sql: Query that returns one row.
            params: Bound values.

        Returns:
            The row.
        """
        with open_database(self.library.db) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(sql, params).fetchone()
        self.assertIsNotNone(row)
        assert row is not None
        return row

    def _root(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        """Read one row from the mirrored location database.

        Args:
            sql: Query that returns one row.
            params: Bound values.

        Returns:
            The row, or None when the query matches nothing.
        """
        with open_database(self.root_db) as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute(sql, params).fetchone()

    def _stored_is(self, stored: object, path: Path) -> None:
        """Assert a stored path resolves to a file.

        Args:
            stored: Value from a path column.
            path: Expected file.

        Returns:
            None. The test fails when the paths differ.
        """
        self.assertIsInstance(stored, str)
        assert isinstance(stored, str)
        self.assertEqual(files.resolve_stored(stored), path.resolve())

    def test_rename_updates_every_path_and_keeps_membership(self) -> None:
        """Rename one file and keep its crate, Prepare row, and history.

        Master and the location database both move portable id, file name,
        video path, and file path. History keeps the play and the new
        name. Cue bytes move with the file. The event carries a count and
        a change type, not a path.

        Returns:
            None. The test fails if a path column or a membership row is left behind.
        """
        dest = self.music / "renamed.mp3"
        payload = {
            "action": "rename",
            "path": str(self.song),
            "name": "renamed.mp3",
            "confirm": True,
        }
        with mock.patch("telemetry.capture", wraps=telemetry.capture) as captured:
            result = files.execute(payload)
        self.assertTrue(result["ok"])
        self.assertFalse(result["preview"])
        self.assertTrue(dest.is_file())
        self.assertFalse(self.song.exists())
        self.assertEqual(dest.read_bytes(), b"audio-a")
        asset = self._master("SELECT * FROM asset WHERE id = 1")
        self._stored_is(asset["portable_id"], dest)
        self._stored_is(asset["video_portable_id"], dest)
        self._stored_is(asset["file_path"], dest)
        self.assertEqual(asset["file_name"], "renamed.mp3")
        self.assertEqual(asset["name"], "Same")
        self.assertEqual(asset["is_missing"], 0)
        self.assertEqual(asset["file_size"], dest.stat().st_size)
        self.assertEqual(asset["dj_play_count"], 2)
        history = self._master("SELECT * FROM history_entry WHERE id = 1")
        self.assertEqual(history["asset_id"], 1)
        self.assertEqual(history["name"], "Same")
        self.assertEqual(history["file_name"], "renamed.mp3")
        self.assertIsNotNone(
            self._master("SELECT 1 AS ok FROM container_asset WHERE asset_id = 1 AND container_id = 3")
        )
        self.assertIsNotNone(
            self._master("SELECT 1 AS ok FROM space_asset WHERE asset_id = 1 AND space_id = 2")
        )
        crate = self._master("SELECT portable_id FROM container WHERE id = 3")
        self._stored_is(crate["portable_id"], dest)
        mirrored = self._root("SELECT * FROM asset WHERE id = 10")
        assert mirrored is not None
        self._stored_is(mirrored["portable_id"], dest)
        self._stored_is(mirrored["file_path"], dest)
        self.assertEqual(mirrored["file_name"], "renamed.mp3")
        revision = self._master("SELECT revision FROM serato")
        self.assertGreater(int(revision["revision"]), 1)
        self.assertFalse((self.library.root / "Backups" / "file-ops-journal.json").exists())
        self.assertIn("Warmup", result["changes"][0]["crates"])
        names = [call.args[0] for call in captured.call_args_list]
        self.assertIn(telemetry.EVENT_FILES_CHANGED, names)
        props = next(
            call.args[1]
            for call in captured.call_args_list
            if call.args[0] == telemetry.EVENT_FILES_CHANGED
        )
        self.assertEqual(props["change"], "rename")
        self.assertIsInstance(props["file_count"], int)
        self.assertNotIn("path", props)
        self.assertNotIn("name", props)
        self.assertNotIn("renamed.mp3", json.dumps(props))

    def test_rename_follows_a_related_track_link(self) -> None:
        """Move a saved related-track link when the audio file is renamed.

        The sidecar lives in a temporary settings directory. The link is
        read back from the new path.

        Returns:
            None. The test fails if the link stays on the old path.
        """
        config = self.library.root / "config"
        config.mkdir()
        dest = self.music / "renamed.mp3"
        with mock.patch.dict(os.environ, {app_config.CONFIG_ENV: str(config)}):
            related.add_link(str(self.song.resolve()), str(self.other.resolve()), mutual=False)
            result = files.execute(
                {
                    "action": "rename",
                    "path": str(self.song),
                    "name": "renamed.mp3",
                    "confirm": True,
                }
            )
            moved = related.overview(str(dest.resolve()))
            left = related.overview(str(self.song.resolve()))
        self.assertTrue(result["ok"])
        self.assertEqual(len(moved["saved"]), 1)
        self.assertEqual(left["saved"], [])

    def test_move_several_files(self) -> None:
        """Move two library files into one folder and update both paths.

        Returns:
            None. The test fails if either file or its library row stays put.
        """
        dest = self.music / "sorted"
        dest.mkdir()
        result = files.execute(
            {
                "action": "move",
                "paths": [str(self.song), str(self.other)],
                "destination": str(dest),
                "confirm": True,
            }
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["count"], 2)
        self.assertTrue((dest / "same-a.mp3").is_file())
        self.assertTrue((dest / "same-b.mp3").is_file())
        self._stored_is(self._master("SELECT portable_id FROM asset WHERE id = 1")["portable_id"], dest / "same-a.mp3")
        self._stored_is(self._master("SELECT portable_id FROM asset WHERE id = 2")["portable_id"], dest / "same-b.mp3")
        mirrored = self._root("SELECT portable_id FROM asset WHERE id = 10")
        assert mirrored is not None
        self._stored_is(mirrored["portable_id"], dest / "same-a.mp3")

    def test_move_folder_updates_missing_rows_and_leaves_the_sibling(self) -> None:
        """Move a folder, including a library row whose file is already gone.

        A sibling folder whose name only shares a prefix stays where it
        is. A video path stored under the folder follows the folder.

        Returns:
            None. The test fails if the sibling moves or the missing path stays.
        """
        album = self.music / "album"
        nested = album / "nested"
        nested.mkdir(parents=True)
        track = nested / "song.mp3"
        track.write_bytes(b"nest")
        missing = album / "gone.mp3"
        video = album / "clips" / "video.mov"
        extra = self.music / "album-extra"
        extra.mkdir()
        extra_song = extra / "song.mp3"
        extra_song.write_bytes(b"extra")
        with open_database(self.library.db) as conn:
            conn.execute(
                """
                UPDATE asset
                SET portable_id = ?, file_name = 'song.mp3', file_path = ?, is_missing = 0
                WHERE id = 1
                """,
                (str(track.resolve()), str(track.resolve())),
            )
            conn.execute(
                """
                UPDATE asset
                SET portable_id = ?, file_name = 'gone.mp3', video_portable_id = ?, is_missing = 1
                WHERE id = 2
                """,
                (str(missing.resolve()), str(video.resolve())),
            )
            conn.execute(
                """
                INSERT INTO asset (id, name, artist, portable_id, file_name, is_missing)
                VALUES (3, 'Extra', 'Artist', ?, 'song.mp3', 0)
                """,
                (str(extra_song.resolve()),),
            )
        destination = self.music / "moved"
        destination.mkdir()
        result = files.execute(
            {
                "action": "move_folder",
                "path": str(album),
                "destination": str(destination),
                "confirm": True,
            }
        )
        moved = destination / "album" / "nested" / "song.mp3"
        self.assertTrue(result["ok"])
        self.assertTrue(moved.is_file())
        self.assertEqual(moved.read_bytes(), b"nest")
        self.assertFalse(album.exists())
        self.assertTrue(extra_song.is_file())
        self._stored_is(self._master("SELECT portable_id FROM asset WHERE id = 1")["portable_id"], moved)
        gone = self._master("SELECT portable_id, video_portable_id, is_missing FROM asset WHERE id = 2")
        self._stored_is(gone["portable_id"], destination / "album" / "gone.mp3")
        self._stored_is(gone["video_portable_id"], destination / "album" / "clips" / "video.mov")
        self.assertEqual(gone["is_missing"], 1)
        self._stored_is(self._master("SELECT portable_id FROM asset WHERE id = 3")["portable_id"], extra_song)
        self.assertTrue(any(change["missing"] for change in result["changes"]))

    def test_refusals_leave_the_disk_and_skip_the_backup(self) -> None:
        """Refuse escapes, collisions, shortcuts, and the backup folder.

        A sibling of the backup folder is not the backup folder. A valid
        name that is a shortcut is refused as well. None of the refused
        saves copy the database.

        Returns:
            None. The test fails if a refused path changes or a backup appears.
        """
        outside = self.library.root / "outside.mp3"
        with self.assertRaises(library.LibraryError):
            files.execute(
                {
                    "action": "rename",
                    "path": str(self.song),
                    "name": "../outside.mp3",
                    "confirm": True,
                }
            )
        self.assertFalse(outside.exists())
        self.assertEqual(self.song.read_bytes(), b"audio-a")

        taken = self.music / "taken"
        taken.mkdir()
        (taken / "same-a.mp3").write_bytes(b"there")
        with self.assertRaises(library.LibraryError):
            files.execute(
                {
                    "action": "move",
                    "paths": [str(self.song)],
                    "destination": str(taken),
                    "confirm": True,
                }
            )
        self.assertEqual((taken / "same-a.mp3").read_bytes(), b"there")
        self.assertEqual(self.song.read_bytes(), b"audio-a")

        one = self.music / "one"
        two = self.music / "two"
        one.mkdir()
        two.mkdir()
        (one / "song.mp3").write_bytes(b"1")
        (two / "song.mp3").write_bytes(b"2")
        preview = files.plan(
            {
                "action": "move",
                "paths": [str(one / "song.mp3"), str(two / "song.mp3")],
                "destination": str(self.music),
            }
        )
        self.assertFalse(preview["ok"])
        self.assertTrue((one / "song.mp3").is_file())
        self.assertTrue((two / "song.mp3").is_file())

        secret_dir = self.library.root / "Backups"
        secret_dir.mkdir()
        secret = secret_dir / "secret.mp3"
        secret.write_bytes(b"no")
        protected = files.plan({"action": "rename", "path": str(secret), "name": "nope.mp3"})
        self.assertFalse(protected["ok"])
        self.assertEqual(secret.read_bytes(), b"no")

        backups = self.library.root / "Backups"
        stamped = list(backups.glob("serato-web-*")) if backups.is_dir() else []
        self.assertEqual(stamped, [])

        extra = self.library.root / "Backups-extra"
        extra.mkdir()
        allowed = extra / "song.mp3"
        allowed.write_bytes(b"yes")
        renamed = files.execute(
            {"action": "rename", "path": str(allowed), "name": "song-b.mp3", "confirm": True}
        )
        self.assertTrue(renamed["ok"])
        self.assertEqual((extra / "song-b.mp3").read_bytes(), b"yes")

        self._assert_shortcut_refused()
        missing = self.music / "not-here.mp3"
        with open_database(self.library.db) as conn:
            conn.execute("UPDATE asset SET portable_id = ? WHERE id = 2", (str(missing.resolve()),))
        missing_plan = files.plan({"action": "rename", "path": str(missing), "name": "later.mp3"})
        self.assertFalse(missing_plan["ok"])
        self.assertFalse((self.music / "later.mp3").exists())

        album = self.music / "box"
        inner = album / "inner"
        inner.mkdir(parents=True)
        into_self = files.plan(
            {"action": "move_folder", "path": str(album), "destination": str(inner)}
        )
        self.assertFalse(into_self["ok"])
        self.assertTrue(album.is_dir())
        broad = files.plan(
            {
                "action": "move_folder",
                "path": str(self.library.root),
                "destination": str(self.music),
            }
        )
        self.assertFalse(broad["ok"])
        self.assertTrue(self.library.db.is_file())

    def _assert_shortcut_refused(self) -> None:
        """Refuse a shortcut source and a shortcut destination.

        Returns:
            None. Skipped when shortcuts cannot be created.
        """
        target = self.library.root / "linked-target.mp3"
        target.write_bytes(b"linked")
        link = self.music / "link.mp3"
        outside = self.library.root / "outside-dir"
        outside.mkdir()
        dest_link = self.music / "dest-link"
        try:
            link.symlink_to(target)
            dest_link.symlink_to(outside, target_is_directory=True)
        except OSError:
            return
        source = files.plan({"action": "rename", "path": str(link), "name": "renamed-link.mp3"})
        self.assertFalse(source["ok"])
        self.assertTrue(link.is_symlink())
        self.assertEqual(target.read_bytes(), b"linked")
        destination = files.plan(
            {"action": "move", "paths": [str(self.song)], "destination": str(dest_link)}
        )
        self.assertFalse(destination["ok"])
        self.assertEqual(self.song.read_bytes(), b"audio-a")
        self.assertFalse((outside / self.song.name).exists())

    def test_database_failure_puts_the_file_back(self) -> None:
        """Roll the file back when the database commit fails.

        Returns:
            None. The test fails if the file stays at the new path or the
            journal is left behind.
        """
        dest = self.music / "renamed.mp3"

        def fail(conn: sqlite3.Connection) -> None:
            raise sqlite3.OperationalError("commit failed")

        with mock.patch("files._commit", side_effect=fail):
            with self.assertRaises(library.LibraryError) as caught:
                files.execute(
                    {
                        "action": "rename",
                        "path": str(self.song),
                        "name": "renamed.mp3",
                        "confirm": True,
                    }
                )
        self.assertIn("Nothing was left halfway", str(caught.exception))
        self.assertEqual(self.song.read_bytes(), b"audio-a")
        self.assertFalse(dest.exists())
        self._stored_is(self._master("SELECT portable_id FROM asset WHERE id = 1")["portable_id"], self.song)
        self.assertFalse((self.library.root / "Backups" / "file-ops-journal.json").exists())

    def test_filesystem_failure_puts_the_moved_file_back(self) -> None:
        """Put the first file back when the second move is denied.

        Returns:
            None. The test fails if either file is left in the destination
            or the library path changes.
        """
        dest = self.music / "batch"
        dest.mkdir()
        real = os.rename
        seen = {"count": 0}

        def flaky(src: object, dst: object, *args: object, **kwargs: object) -> None:
            seen["count"] += 1
            if seen["count"] == 2:
                raise OSError(errno.EACCES, "denied")
            real(src, dst)

        with mock.patch("files.os.rename", side_effect=flaky):
            with self.assertRaises(library.LibraryError):
                files.execute(
                    {
                        "action": "move",
                        "paths": [str(self.song), str(self.other)],
                        "destination": str(dest),
                        "confirm": True,
                    }
                )
        self.assertEqual(self.song.read_bytes(), b"audio-a")
        self.assertEqual(self.other.read_bytes(), b"audio-b")
        self.assertFalse((dest / "same-a.mp3").exists())
        self.assertFalse((dest / "same-b.mp3").exists())
        self._stored_is(self._master("SELECT portable_id FROM asset WHERE id = 1")["portable_id"], self.song)

    def test_cross_drive_move_copies_and_a_failed_commit_restores(self) -> None:
        """Copy across a drive, and copy back when the commit fails.

        ``os.rename`` reports a cross-device error. The file bytes still
        arrive. A second run fails the commit and the source is restored.

        Returns:
            None. The test fails if a copy is left at both paths.
        """
        dest_dir = self.music / "other-drive"
        dest_dir.mkdir()

        def cross(src: object, dst: object, *args: object, **kwargs: object) -> None:
            del src, dst, args, kwargs
            raise OSError(errno.EXDEV, "cross-device")

        with mock.patch("files.os.rename", side_effect=cross):
            moved = files.execute(
                {
                    "action": "move",
                    "paths": [str(self.song)],
                    "destination": str(dest_dir),
                    "confirm": True,
                }
            )
        self.assertTrue(moved["ok"])
        self.assertEqual((dest_dir / "same-a.mp3").read_bytes(), b"audio-a")
        self.assertFalse(self.song.exists())

        folder = self.music / "folder-drive"
        folder.mkdir()
        nested = folder / "inside.mp3"
        nested.write_bytes(b"inside")
        parent = self.music / "landed"
        parent.mkdir()

        def fail(conn: sqlite3.Connection) -> None:
            raise sqlite3.OperationalError("commit failed")

        with mock.patch("files.os.rename", side_effect=cross), mock.patch("files._commit", side_effect=fail):
            with self.assertRaises(library.LibraryError):
                files.execute(
                    {
                        "action": "move_folder",
                        "path": str(folder),
                        "destination": str(parent),
                        "confirm": True,
                    }
                )
        self.assertEqual(nested.read_bytes(), b"inside")
        self.assertFalse((parent / "folder-drive" / "inside.mp3").exists())

    def test_delete_requires_confirm_and_keeps_history(self) -> None:
        """Trash a file only after a boolean confirm, and keep the play.

        The asset and its crate row go away. The history row stays, with
        the asset link cleared. A preview and a non-boolean confirm do
        not move the file.

        Returns:
            None. The test fails if the file is trashed early or the play is deleted.
        """
        preview = files.plan({"action": "delete", "paths": [str(self.song)]})
        self.assertTrue(preview["needs_confirm"])
        self.assertTrue(preview["preview"])
        self.assertEqual(self.song.read_bytes(), b"audio-a")
        with self.assertRaises(library.LibraryError):
            files.execute({"action": "delete", "paths": [str(self.song)], "confirm": "yes"})
        self.assertTrue(self.song.is_file())
        result = files.execute({"action": "delete", "paths": [str(self.song)], "confirm": True})
        self.assertTrue(result["ok"])
        self.assertEqual(result["changes"][0]["effect"], "trash")
        self.assertFalse(self.song.exists())
        trashed = list(self.trash.iterdir())
        self.assertEqual(len(trashed), 1)
        self.assertEqual(trashed[0].read_bytes(), b"audio-a")
        self.assertIsNone(self._root("SELECT id FROM asset WHERE id = 10"))
        with open_database(self.library.db) as conn:
            self.assertIsNone(conn.execute("SELECT id FROM asset WHERE id = 1").fetchone())
            self.assertIsNone(conn.execute("SELECT id FROM container_asset WHERE asset_id = 1").fetchone())
            history = conn.execute(
                "SELECT asset_id, name, artist FROM history_entry WHERE id = 1"
            ).fetchone()
        self.assertIsNone(history[0])
        self.assertEqual(history[1], "Same")
        self.assertEqual(history[2], "Artist")

    def test_delete_of_a_missing_file_removes_the_row_only(self) -> None:
        """Remove a library row when the audio is already gone.

        Returns:
            None. The test fails if a trash entry is created.
        """
        missing = self.music / "gone.mp3"
        with open_database(self.library.db) as conn:
            conn.execute(
                "UPDATE asset SET portable_id = ?, is_missing = 1 WHERE id = 2",
                (str(missing.resolve()),),
            )
        result = files.execute({"action": "delete", "paths": [str(missing)], "confirm": True})
        self.assertTrue(result["ok"])
        self.assertTrue(result["changes"][0]["missing"])
        self.assertFalse(self.trash.exists() and any(self.trash.iterdir()))
        with open_database(self.library.db) as conn:
            self.assertIsNone(conn.execute("SELECT id FROM asset WHERE id = 2").fetchone())
            self.assertIsNotNone(conn.execute("SELECT id FROM asset WHERE id = 1").fetchone())

    def test_serato_open_refuses_before_a_backup(self) -> None:
        """Show the refusal in the preview and raise on confirm.

        Returns:
            None. The test fails if the file moves or a backup is copied.
        """
        with open_database(self.library.db) as conn:
            conn.execute(
                "INSERT INTO lock (owner_process_id, owner_process_name) VALUES (?, ?)",
                (os.getpid(), "Serato DJ Pro"),
            )
        payload = {"action": "rename", "path": str(self.song), "name": "renamed.mp3"}
        with mock.patch("library._process_is_serato", return_value=True):
            preview = files.plan(payload)
            self.assertFalse(preview["ok"])
            self.assertFalse(preview["writable"])
            with self.assertRaises(library.SeratoOpen):
                files.execute({**payload, "confirm": True})
        self.assertEqual(self.song.read_bytes(), b"audio-a")
        backups = self.library.root / "Backups"
        stamped = list(backups.glob("serato-web-*")) if backups.is_dir() else []
        self.assertEqual(stamped, [])

    def test_process_check_error_refuses_the_file_change(self) -> None:
        """Refuse a confirmed file change when the lock lookup raises.

        Returns:
            None. The test fails if the file is renamed.
        """
        with open_database(self.library.db) as conn:
            conn.execute(
                "INSERT INTO lock (owner_process_id, owner_process_name) VALUES (?, ?)",
                (os.getpid(), "Serato DJ Pro"),
            )
        payload = {"action": "rename", "path": str(self.song), "name": "renamed.mp3", "confirm": True}
        with mock.patch("library._process_is_serato", side_effect=OSError("ps failed")):
            with self.assertRaises(library.SeratoOpen):
                files.execute(payload)
        self.assertEqual(self.song.read_bytes(), b"audio-a")
        self.assertFalse((self.song.parent / "renamed.mp3").exists())

    def test_preview_does_not_copy_the_database(self) -> None:
        """Check a rename without writing a journal or a backup.

        Returns:
            None. The test fails if the preview writes or moves the file.
        """
        preview = files.plan({"action": "rename", "path": str(self.song), "name": "renamed.mp3"})
        self.assertTrue(preview["ok"])
        self.assertTrue(preview["needs_confirm"])
        self.assertEqual(preview["changes"][0]["from"], str(self.song.resolve()))
        self.assertTrue(self.song.is_file())
        self.assertFalse((self.library.root / "Backups" / "file-ops-journal.json").exists())
        backups = self.library.root / "Backups"
        stamped = list(backups.glob("serato-web-*")) if backups.is_dir() else []
        self.assertEqual(stamped, [])

    def test_replace_copies_cues_and_keeps_the_track(self) -> None:
        """Point the track at a new file and copy its Serato frames.

        The asset id, crate, and title stay. The old file stays on disk.
        The new file keeps its own audio tail.

        Returns:
            None. The test fails if the crate row changes id or the cue is missing.
        """
        _id3_file(_markers_payload(), self.song)
        self.song.write_bytes(self.song.read_bytes() + b"SOURCE-AUDIO")
        replacement = self.music / "better.mp3"
        replacement.write_bytes(_title_tag("Hello") + b"DEST-AUDIO")
        result = files.execute(
            {
                "action": "replace",
                "asset_id": 1,
                "replacement": str(replacement),
                "confirm": True,
            }
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["cues"], "copied")
        self.assertTrue(self.song.is_file())
        copied = replacement.read_bytes()
        self.assertTrue(copied.endswith(b"DEST-AUDIO"))
        self.assertIn(b"Hello", copied)
        from tags import read_serato_tags

        self.assertTrue(read_serato_tags(str(replacement))["found"])
        asset = self._master("SELECT id, name, portable_id FROM asset WHERE id = 1")
        self.assertEqual(asset["name"], "Same")
        self._stored_is(asset["portable_id"], replacement)
        self.assertIsNotNone(
            self._master("SELECT 1 AS ok FROM container_asset WHERE asset_id = 1 AND container_id = 3")
        )
        self.assertEqual(list(self.music.glob(".serato-cue*")), [])
        hold = self.library.root / "Backups" / "cue-hold"
        if hold.exists():
            self.assertEqual(list(hold.iterdir()), [])

    def test_replace_warns_when_the_new_file_cannot_take_cues(self) -> None:
        """Retarget a FLAC file and leave its bytes unchanged.

        Returns:
            None. The test fails if the FLAC file is rewritten.
        """
        _id3_file(_markers_payload(), self.song)
        kept = self.music / "already.mp3"
        _id3_file(_markers_payload(), kept)
        kept.write_bytes(kept.read_bytes() + b"KEEP")
        before = kept.read_bytes()
        kept_result = files.execute(
            {"action": "replace", "asset_id": 1, "replacement": str(kept), "confirm": True}
        )
        self.assertEqual(kept_result["cues"], "kept")
        self.assertEqual(kept.read_bytes(), before)
        flac = self.music / "better.flac"
        payload = b"fLaC" + b"\x00" * 8
        flac.write_bytes(payload)
        result = files.execute(
            {"action": "replace", "path": str(kept), "replacement": str(flac), "confirm": True}
        )
        self.assertEqual(result["cues"], "unsupported")
        self.assertEqual(flac.read_bytes(), payload)
        self.assertTrue(kept.is_file())
        self._stored_is(self._master("SELECT portable_id FROM asset WHERE id = 1")["portable_id"], flac)
        self.assertTrue(result["warning"])

    def test_replace_restores_the_new_file_when_the_copy_fails(self) -> None:
        """Keep the new file's bytes when the cue copy reports failure.

        The library path still moves. The warning says the cues were not copied.

        Returns:
            None. The test fails if the destination bytes change.
        """
        _id3_file(_markers_payload(), self.song)
        replacement = self.music / "better.mp3"
        replacement.write_bytes(_title_tag("Hello") + b"DEST-AUDIO")
        before = replacement.read_bytes()
        with mock.patch(
            "files.copy_serato_geob",
            return_value={"status": "failed", "detail": "Cue points could not be copied. The new file was left unchanged."},
        ):
            result = files.execute(
                {
                    "action": "replace",
                    "asset_id": 1,
                    "replacement": str(replacement),
                    "confirm": True,
                }
            )
        self.assertEqual(result["cues"], "failed")
        self.assertEqual(replacement.read_bytes(), before)
        self._stored_is(self._master("SELECT portable_id FROM asset WHERE id = 1")["portable_id"], replacement)
        self.assertIn("could not be copied", str(result["warning"]))

    def test_recovery_finishes_or_puts_back(self) -> None:
        """Undo a journal the database does not match, and keep one it does.

        A mixed journal is left in place and blocks the next save.

        Returns:
            None. The test fails if recovery moves a file the database already matches.
        """
        dest = self.music / "renamed.mp3"
        self.song.rename(dest)
        journal = {
            "version": 1,
            "action": "rename",
            "moves": [{"src": str(self.song.resolve()), "dst": str(dest.resolve()), "kind": "rename"}],
            "trash": [],
            "cue_backup": None,
            "expect": {
                "paths": [{"id": 1, "portable_id": files.to_portable(dest)}],
                "absent": [],
            },
            "done": False,
            "directories": [],
        }
        path = self.library.root / "Backups" / "file-ops-journal.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(journal), encoding="utf-8")
        self.assertEqual(files.recover_interrupted(), "clear")
        self.assertEqual(self.song.read_bytes(), b"audio-a")
        self.assertFalse(dest.exists())
        self.assertFalse(path.exists())

        self.song.rename(dest)
        with open_database(self.library.db) as conn:
            conn.execute(
                "UPDATE asset SET portable_id = ?, file_name = ? WHERE id = 1",
                (files.to_portable(dest), dest.name),
            )
        path.write_text(json.dumps(journal), encoding="utf-8")
        self.assertEqual(files.recover_interrupted(), "clear")
        self.assertEqual(dest.read_bytes(), b"audio-a")
        self.assertFalse(path.exists())

        mixed = json.loads(json.dumps(journal))
        mixed["expect"]["paths"].append(
            {"id": 2, "portable_id": files.to_portable(self.music / "not-the-file.mp3")}
        )
        path.write_text(json.dumps(mixed), encoding="utf-8")
        self.assertEqual(files.recover_interrupted(), "blocked")
        self.assertTrue(path.is_file())
        self.assertEqual(dest.read_bytes(), b"audio-a")
        with self.assertRaises(library.LibraryError):
            files.execute(
                {"action": "rename", "path": str(self.other), "name": "other-b.mp3", "confirm": True}
            )
        self.assertTrue(self.other.is_file())

    def test_linux_trashinfo_records_the_original_path(self) -> None:
        """Write a FreeDesktop trashinfo document next to the trashed file.

        Returns:
            None. The test fails if the original path is not in the document.
        """
        data = self.library.root / "xdg"
        with mock.patch.dict(os.environ, {"XDG_DATA_HOME": str(data)}, clear=False):
            os.environ.pop(files._TRASH_ENV, None)
            record = files._trash_linux(self.song)
        info = Path(str(record["info"]))
        text = info.read_text(encoding="utf-8")
        line = next(item for item in text.splitlines() if item.startswith("Path="))
        self.assertEqual(unquote(line.removeprefix("Path=")), str(self.song))
        self.assertTrue(Path(str(record["dst"])).is_file())
        self.assertFalse(self.song.exists())
        os.environ[files._TRASH_ENV] = str(self.trash)

    def test_windows_trash_flags_allow_undo(self) -> None:
        """Keep the Recycle Bin undo flag in the Windows delete operation.

        Returns:
            None. The test fails if the undo flag is missing.
        """
        self.assertEqual(files.FO_DELETE, 3)
        self.assertTrue(files.FOF_ALLOWUNDO & 0x0040)
        source = (ROOT / "files.py").read_text(encoding="utf-8")
        self.assertIn("FOF_ALLOWUNDO", source)

    def test_relative_trash_override_is_ignored(self) -> None:
        """Ignore a relative trash override so it cannot redirect a delete.

        Returns:
            None. The test fails if a relative value is accepted.
        """
        with mock.patch.dict(os.environ, {files._TRASH_ENV: "relative-trash"}):
            self.assertIsNone(files._trash_override())

    def test_list_and_http_rename(self) -> None:
        """List a folder over HTTP and rename through the confirm route.

        A preview returns 200 and does not move the file. Confirm moves it.

        Returns:
            None. The test fails if the page route skips the confirm flag.
        """
        listed = files.list_directory(str(self.music))
        names = {entry["name"] for entry in listed["entries"]}
        self.assertIn("same-a.mp3", names)
        match = next(entry for entry in listed["entries"] if entry["name"] == "same-a.mp3")
        self.assertTrue(match["in_library"])
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        host, port = httpd.server_address
        base = f"http://{host}:{port}"
        try:
            status, body = _request(base, f"/api/files?path={urllib.request.quote(str(self.music))}")
            self.assertEqual(status, 200)
            assert isinstance(body, dict)
            self.assertEqual(body["path"], str(self.music.resolve()))
            preview_status, preview = _request(
                base,
                "/api/files",
                {"action": "rename", "path": str(self.song), "name": "from-http.mp3"},
            )
            self.assertEqual(preview_status, 200)
            assert isinstance(preview, dict)
            self.assertTrue(preview["needs_confirm"])
            self.assertTrue(self.song.is_file())
            saved_status, saved = _request(
                base,
                "/api/files",
                {
                    "action": "rename",
                    "path": str(self.song),
                    "name": "from-http.mp3",
                    "confirm": True,
                },
            )
            self.assertEqual(saved_status, 200)
            assert isinstance(saved, dict)
            self.assertTrue(saved["ok"])
            self.assertTrue((self.music / "from-http.mp3").is_file())
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=3)

    def test_page_mentions_the_file_browser(self) -> None:
        """Tie the Files view to the confirm payload.

        The script builds the dialog with text nodes. It does not assign
        ``innerHTML``.

        Returns:
            None. The test fails if the route or the confirm fields are absent.
        """
        page = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn('data-view="files"', page)
        self.assertIn("Files", page)
        self.assertIn('id="files-dialog"', page)
        self.assertIn("/api/files", script)
        self.assertIn("needs_confirm", script)
        self.assertIn("changes", script)
        self.assertIn("Move to Trash", script)
        self.assertNotIn("innerHTML", script)

    def test_empty_browse_lists_music_roots(self) -> None:
        """Open Files on the music folder, not the computer root.

        Returns:
            None. The test fails if the home directory is listed.
        """
        listed = files.list_directory("")
        self.assertEqual(listed["path"], "")
        self.assertIsNone(listed["parent"])
        self.assertFalse(listed["elsewhere"])
        self.assertEqual(listed["entries"], [])
        match = next(item for item in listed["roots"] if item["path"] == str(self.music.resolve()))
        self.assertEqual(match["name"], "music")

    def test_browse_stays_inside_the_music_root(self) -> None:
        """Refuse a parent, a prefixed sibling, and a path that climbs out.

        A child folder is listed. Up is unavailable on the root itself.
        ``elsewhere`` lists the parent.

        Returns:
            None. The test fails if a path outside the music folder is opened.
        """
        with self.assertRaises(library.LibraryError) as outside:
            files.list_directory(str(self.library.root))
        self.assertEqual(outside.exception.status, 403)
        self.assertEqual(outside.exception.message, "That folder is outside the music folders.")
        sibling = self.library.root / "music-extra"
        sibling.mkdir()
        with self.assertRaises(library.LibraryError) as prefixed:
            files.list_directory(str(sibling))
        self.assertEqual(prefixed.exception.status, 403)
        with self.assertRaises(library.LibraryError):
            files.list_directory(str(self.music / ".."))
        opened = files.list_directory(str(self.music))
        self.assertIsNone(opened["parent"])
        self.assertEqual(opened["breadcrumb"][0]["path"], str(self.music.resolve()))
        self.assertEqual(opened["breadcrumb"][0]["name"], "music")
        child = self.music / "Crates"
        child.mkdir()
        inner = files.list_directory(str(child))
        self.assertEqual(inner["parent"], str(self.music.resolve()))
        self.assertEqual(inner["breadcrumb"][1]["name"], "Crates")
        self.assertEqual(inner["breadcrumb"][0]["path"], str(self.music.resolve()))
        wider = files.list_directory(str(self.library.root), elsewhere=True)
        self.assertTrue(wider["elsewhere"])
        self.assertEqual(wider["path"], str(self.library.root.resolve()))

    def test_a_shortcut_cannot_leave_the_music_root(self) -> None:
        """Refuse a shortcut and a folder reached through that shortcut.

        Returns:
            None. The test fails if the target directory is listed.
        """
        secret = self.library.root / "secret"
        secret.mkdir()
        (secret / "nested").mkdir()
        link = self.music / "escape"
        try:
            link.symlink_to(secret, target_is_directory=True)
        except OSError:
            self.skipTest("symlinks are not available")
        with self.assertRaises(library.LibraryError) as caught:
            files.list_directory(str(link))
        self.assertEqual(caught.exception.message, "Shortcuts are left alone.")
        with self.assertRaises(library.LibraryError) as nested:
            files.list_directory(str(link / "nested"))
        self.assertEqual(nested.exception.message, "Shortcuts are left alone.")
        with self.assertRaises(library.LibraryError) as escaped:
            files.list_directory(str(link / "nested"), elsewhere=True)
        self.assertEqual(escaped.exception.message, "Shortcuts are left alone.")

    def test_more_than_5000_entries_are_all_listed_folders_first(self) -> None:
        """Return every name in a large folder, with folders before files.

        Returns:
            None. The test fails if the last file is missing or a file sorts first.
        """
        folder = self.music / "crate"
        folder.mkdir()
        total = 5001
        for index in range(total):
            (folder / f"file-{index:05d}.mp3").write_bytes(b"")
        (folder / "zzz-folder").mkdir()
        listed = files.list_directory(str(folder))
        names = [entry["name"] for entry in listed["entries"]]
        self.assertEqual(len(names), total + 1)
        self.assertFalse(listed["truncated"])
        self.assertEqual(names[0], "zzz-folder")
        self.assertEqual(listed["entries"][0]["kind"], "dir")
        self.assertEqual(names[-1], "file-05000.mp3")
        self.assertLess(names.index("zzz-folder"), names.index("file-00000.mp3"))

    def test_http_browse_refuses_a_path_outside_the_roots(self) -> None:
        """Refuse an outside path over HTTP unless elsewhere is set.

        Returns:
            None. The test fails if the outside path is listed by default.
        """
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        host, port = httpd.server_address
        base = f"http://{host}:{port}"
        outside = urllib.request.quote(str(self.library.root))
        try:
            roots_status, roots = _request(base, "/api/files")
            self.assertEqual(roots_status, 200)
            assert isinstance(roots, dict)
            self.assertEqual(roots["path"], "")
            self.assertTrue(any(str(item["path"]) == str(self.music.resolve()) for item in roots["roots"]))
            denied_status, denied = _request(base, f"/api/files?path={outside}")
            self.assertEqual(denied_status, 403)
            assert isinstance(denied, dict)
            self.assertEqual(denied["error"], "That folder is outside the music folders.")
            allowed_status, allowed = _request(base, f"/api/files?path={outside}&elsewhere=1")
            self.assertEqual(allowed_status, 200)
            assert isinstance(allowed, dict)
            self.assertTrue(allowed["elsewhere"])
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=3)

    def test_blank_query_still_lists_the_folder(self) -> None:
        """Treat a blank q= as a normal folder listing.

        Returns:
            None. The test fails if whitespace starts a name search.
        """
        listed = files.list_directory(str(self.music), query="   ")
        self.assertNotIn("search", listed)
        self.assertFalse(listed["truncated"])
        names = {str(entry["name"]) for entry in listed["entries"]}
        self.assertIn("same-a.mp3", names)
        self.assertIn("same-b.mp3", names)

    def test_name_search_is_fuzzy_ranked_and_read_only(self) -> None:
        """Find a nested name, rank a prefix first, and leave the disk alone.

        ``hs`` is not a substring of House. It is still a match. A file
        whose name only contains the word later ranks below a prefix.
        The music folder's files are unchanged.

        Returns:
            None. The test fails if the search is exact, unranked, or writes.
        """
        nested = self.music / "Deep"
        nested.mkdir()
        house = nested / "House Mix.mp3"
        house.write_bytes(b"nested")
        (self.music / "zz-same.mp3").write_bytes(b"later")
        before = sorted(path.relative_to(self.music).as_posix() for path in self.music.rglob("*"))
        fuzzy = files.list_directory("", query="hs")
        ranked = files.list_directory("", query="same")
        after = sorted(path.relative_to(self.music).as_posix() for path in self.music.rglob("*"))
        self.assertEqual(before, after)
        self.assertNotIn("file-ops-journal.json", after)
        self.assertTrue(fuzzy["search"])
        self.assertEqual(fuzzy["query"], "hs")
        self.assertEqual([str(entry["name"]) for entry in fuzzy["entries"]], ["House Mix.mp3"])
        self.assertFalse(fuzzy["truncated"])
        names = [str(entry["name"]) for entry in ranked["entries"]]
        self.assertLess(names.index("same-a.mp3"), names.index("zz-same.mp3"))
        match = next(entry for entry in ranked["entries"] if entry["name"] == "same-a.mp3")
        self.assertEqual(match["kind"], "file")
        self.assertTrue(match["audio"])
        self.assertTrue(match["in_library"])
        # Windows may spell the same temp folder with an 8.3 short name.
        self.assertTrue(Path(str(match["detail"])).samefile(self.song.parent))
        self.assertTrue(str(match["path"]).endswith("same-a.mp3"))

    def test_search_is_case_insensitive_and_stays_in_the_folder(self) -> None:
        """Match ignoring case, and do not return a sibling of the chosen folder.

        Returns:
            None. The test fails if SAME-A misses, or if a scoped search
            climbs out of Deep.
        """
        nested = self.music / "Deep"
        nested.mkdir()
        (nested / "House Mix.mp3").write_bytes(b"nested")
        wide = files.list_directory("", query="SAME-A")
        self.assertIn("same-a.mp3", [str(entry["name"]) for entry in wide["entries"]])
        scoped = files.list_directory(str(nested), query="same")
        self.assertEqual(scoped["entries"], [])
        housed = files.list_directory(str(nested), query="house")
        self.assertEqual([str(entry["name"]) for entry in housed["entries"]], ["House Mix.mp3"])

    def test_search_skips_shortcuts_missing_roots_and_outside_paths(self) -> None:
        """Do not follow a shortcut, open a missing root, or treat q as a path.

        An empty library search returns no rows. A query that looks like
        a Windows path is text, not a folder to open.

        Returns:
            None. The test fails if a skipped file is returned.
        """
        outside = self.library.root / "outside"
        outside.mkdir()
        secret = outside / "secret-track.mp3"
        secret.write_bytes(b"secret")
        link = self.music / "linked-dir"
        try:
            os.symlink(outside, link, target_is_directory=True)
        except OSError:
            self.skipTest("This user cannot create a shortcut.")
        found = files.list_directory("", query="secret-track")
        self.assertEqual(found["entries"], [])
        sentinel = self.library.root / "unmounted"
        sentinel.mkdir()
        (sentinel / "ghost-track.mp3").write_bytes(b"ghost")
        original = files.music_roots.music_roots

        def with_missing(refresh: bool = False) -> list[dict[str, object]]:
            rows = original(refresh=refresh)
            return [{"name": "Gone", "path": str(sentinel), "kind": "folder", "missing": True}, *rows]

        with mock.patch("files.music_roots.music_roots", with_missing):
            ghosts = files.list_directory("", query="ghost-track")
            kept = files.list_directory("", query="same-a")
        self.assertEqual(ghosts["entries"], [])
        self.assertIn("same-a.mp3", [str(entry["name"]) for entry in kept["entries"]])
        with mock.patch("files.music_roots.music_roots", return_value=[]):
            empty = files.list_directory("", query="same-a")
        self.assertEqual(empty["entries"], [])
        self.assertTrue(empty["search"])
        self.assertFalse(empty["truncated"])
        windows = files.list_directory("", query="C:\\Windows\\System32")
        self.assertEqual(windows["entries"], [])
        with self.assertRaises(library.LibraryError) as outside_path:
            files.list_directory(str(self.library.root), query="same")
        self.assertEqual(outside_path.exception.status, 403)
        with self.assertRaises(library.LibraryError) as elsewhere:
            files.list_directory("", query="same", elsewhere=True)
        self.assertEqual(elsewhere.exception.status, 400)

    def test_search_refuses_a_bad_query_and_caps_the_walk(self) -> None:
        """Refuse a null or a huge query, and stop when the caps are hit.

        Returns:
            None. The test fails if a bad query is searched or a cap is ignored.
        """
        with self.assertRaises(library.LibraryError) as null_query:
            files.list_directory(str(self.music), query="a\x00b")
        self.assertEqual(null_query.exception.status, 400)
        self.assertEqual(null_query.exception.message, "That search is not valid.")
        with self.assertRaises(library.LibraryError) as long_query:
            files.list_directory(str(self.music), query="a" * 201)
        self.assertEqual(long_query.exception.status, 400)
        self.assertEqual(long_query.exception.message, "That search is too long.")
        with mock.patch.object(files, "_SEARCH_SCAN", 1):
            scanned = files.list_directory(str(self.music), query="mp3")
        self.assertTrue(scanned["truncated"])
        self.assertLessEqual(len(scanned["entries"]), 1)
        with mock.patch.object(files, "_SEARCH_HITS", 1):
            capped = files.list_directory(str(self.music), query="mp3")
        self.assertTrue(capped["truncated"])
        self.assertEqual(len(capped["entries"]), 1)

    def test_http_name_search(self) -> None:
        """Search through GET /api/files?q= without writing.

        Returns:
            None. The test fails if the route ignores q or returns a file
            that does not match.
        """
        nested = self.music / "Deep"
        nested.mkdir()
        (nested / "House Mix.mp3").write_bytes(b"nested")
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        host, port = httpd.server_address
        base = f"http://{host}:{port}"
        try:
            status, body = _request(base, "/api/files?q=house")
            self.assertEqual(status, 200)
            assert isinstance(body, dict)
            self.assertTrue(body["search"])
            self.assertEqual(body["query"], "house")
            self.assertIn("House Mix.mp3", [str(entry["name"]) for entry in body["entries"]])
            missing_status, missing = _request(base, "/api/files?q=zzzz-not-a-track")
            self.assertEqual(missing_status, 200)
            assert isinstance(missing, dict)
            self.assertEqual(missing["entries"], [])
            long_status, long_body = _request(base, "/api/files?q=" + ("a" * 201))
            self.assertEqual(long_status, 400)
            assert isinstance(long_body, dict)
            self.assertEqual(long_body["error"], "That search is too long.")
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=3)


def _title_tag(text: str) -> bytes:
    """Build a tiny ID3v2.3 tag whose only frame is a title.

    Args:
        text: Latin-1 title.

    Returns:
        The tag bytes, with no audio after them.
    """
    body = b"\x00" + text.encode("latin-1")
    frame = b"TIT2" + len(body).to_bytes(4, "big") + b"\x00\x00" + body
    size = len(frame)
    synchsafe = bytes(
        (
            (size >> 21) & 0x7F,
            (size >> 14) & 0x7F,
            (size >> 7) & 0x7F,
            size & 0x7F,
        )
    )
    return b"ID3" + bytes([3, 0, 0]) + synchsafe + frame


def _request(base: str, path: str, payload: dict | None = None) -> tuple[int, object]:
    """Send one JSON request to a test server.

    Args:
        base: ``http://host:port`` prefix.
        path: Absolute path.
        payload: JSON body. None sends GET.

    Returns:
        The status and the decoded JSON value.
    """
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(base + path, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request) as response:
            body = response.read()
            status = response.status
    except urllib.error.HTTPError as exc:
        body = exc.read()
        status = exc.code
        exc.close()
    return status, json.loads(body.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
