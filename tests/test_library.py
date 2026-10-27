"""Library reads and writes against a temporary database."""

from __future__ import annotations

import os
import shutil
import unittest
from pathlib import Path
from typing import cast
from unittest import mock

import library
from library import LibraryError, SeratoOpen
from tests.fixture import TempLibrary, open_database


class LibraryTests(unittest.TestCase):
    """Read and write a temporary Serato-shaped database.

    Each case points ``library.MASTER`` at a throwaway file and closes it
    before the directory is removed. The live Serato library is not opened.
    Platform checks patch ``sys.platform`` so macOS and Windows paths are
    covered on either host.
    """
    def test_status_is_writable_without_a_lock(self) -> None:
        """Report a writable library when the lock table is empty.

        Reads the temporary master database. Nothing is written. The file
        manager name follows the host running the test.

        Returns:
            None. The test fails if the status says Serato is open.
        """
        with TempLibrary() as temp:
            info = library.status()
        self.assertTrue(info["writable"])
        self.assertFalse(info["open"])
        self.assertEqual(info["file_manager"], library.file_manager_name())
        self.assertIn(temp.db.name, "master.sqlite")

    def test_status_blocks_a_live_serato_process(self) -> None:
        """Refuse a write while a Serato process holds the lock.

        Inserts a lock row and patches the process check so the pid counts as
        Serato. ``begin_write`` must raise ``SeratoOpen`` before it copies a
        backup or opens a write transaction.

        Returns:
            None. The test fails if the library stays writable.
        """
        with TempLibrary():
            with open_database(library.MASTER) as conn:
                conn.execute(
                    "INSERT INTO lock (owner_process_id, owner_process_name) VALUES (99, 'Serato DJ Pro')"
                )
            with mock.patch.object(library, "_process_is_serato", return_value=True):
                info = library.status()
                with self.assertRaises(SeratoOpen):
                    library.begin_write()
        self.assertFalse(info["writable"])
        self.assertEqual(info["pid"], 99)

    def test_save_track_updates_the_row_and_backs_up(self) -> None:
        """Save a title and BPM, and copy the database once.

        Writes the asset row and creates ``Library/Backups``. The location
        database is absent, so the result carries a warning and the audio file
        is left untouched.

        Returns:
            None. The test fails if the row, the warning, or the backup is missing.
        """
        with TempLibrary() as temp:
            result = library.save_track(1, {"name": "Renamed", "bpm": 126})
            with open_database(temp.db) as conn:
                row = conn.execute("SELECT name, bpm FROM asset WHERE id = 1").fetchone()
            backups = list((temp.db.resolve().parent / "Backups").glob("serato-web-*"))
            self.assertTrue(result["ok"])
            self.assertIsNotNone(result["warning"])
            self.assertEqual(row, ("Renamed", 126))
            self.assertEqual(len(backups), 1)
            self.assertTrue((backups[0] / "master.sqlite").is_file())

    def test_save_rejects_a_bad_bpm_before_writing(self) -> None:
        """Reject a BPM outside Serato's range before any update.

        The asset row must still show the fixture BPM. No backup is required
        because the write is refused first.

        Returns:
            None. The test fails if the database changes.
        """
        with TempLibrary() as temp:
            with self.assertRaises(LibraryError):
                library.save_track(1, {"bpm": 2000})
            with open_database(temp.db) as conn:
                bpm = conn.execute("SELECT bpm FROM asset WHERE id = 1").fetchone()[0]
        self.assertEqual(bpm, 120)

    def test_crate_create_add_export_and_delete(self) -> None:
        """Create a crate, add a track, export it, and delete the crate.

        Writes container and membership rows, reads them back as an extended
        M3U, then removes the crate. The audio file is not moved.

        Returns:
            None. The test fails if the playlist omits the track or the crate remains.
        """
        with TempLibrary() as temp:
            created = library.crate_action({"action": "create", "name": "Warmup"})
            added = library.crate_action({"action": "add", "id": created["id"], "asset": 1})
            playlist = library.export_m3u("Serato Library", cast(int, created["id"]))
            library.crate_action({"action": "delete", "id": created["id"]})
            with open_database(temp.db) as conn:
                left = conn.execute(
                    "SELECT COUNT(*) FROM container WHERE name = 'Warmup'"
                ).fetchone()[0]
        self.assertTrue(added["ok"])
        self.assertIn("#PLAYLIST:Warmup", playlist)
        self.assertIn("same-a.mp3", playlist)
        self.assertIn("#EXTINF:180,", playlist)
        self.assertEqual(left, 0)

    def test_export_names_a_track_with_no_path(self) -> None:
        """Comment a track that has no portable id and keep it out of the playlist.

        Inserts two assets, one without a path. The export reads the space and
        does not write the database. A missing length is written as ``-1``.

        Returns:
            None. The test fails if the pathless track becomes a playlist entry.
        """
        with TempLibrary() as temp:
            with open_database(temp.db) as conn:
                conn.execute(
                    """
                    INSERT INTO asset (id, name, artist, length_ms, portable_id)
                    VALUES
                        (3, 'Ghost', 'Artist', NULL, NULL),
                        (4, 'Quiet', 'Artist', NULL, 'Music/quiet.mp3')
                    """
                )
                conn.execute(
                    """
                    INSERT INTO space_asset (id, asset_id, space_id)
                    VALUES (3, 3, 1), (4, 4, 1)
                    """
                )
            playlist = library.export_m3u("Serato Library", None)
        lines = playlist.splitlines()
        self.assertIn("# omitted, no path: Artist - Ghost", lines)
        self.assertIn("#EXTINF:-1,Artist - Quiet", lines)
        self.assertNotIn("Ghost", [line for line in lines if not line.startswith("#")])

    def test_parent_zero_is_not_the_space_root(self) -> None:
        """Refuse crate parent 0 instead of treating it as the space root.

        Parent 0 is not a container id. The create is rejected and no crate row
        is inserted.

        Returns:
            None. The test fails unless the error status is 404.
        """
        with TempLibrary():
            with self.assertRaises(LibraryError) as caught:
                library.crate_action({"action": "create", "name": "Orphan", "parent": 0})
        self.assertEqual(caught.exception.status, 404)

    def test_unknown_crate_action_rolls_back(self) -> None:
        """Reject an unknown crate action without leaving a write committed.

        The action name is not one ``crate_action`` implements. The temporary
        database must roll back.

        Returns:
            None. The test fails if ``LibraryError`` is not raised.
        """
        with TempLibrary():
            with self.assertRaises(LibraryError):
                library.crate_action({"action": "explode"})

    def test_import_matches_known_paths(self) -> None:
        """Create a crate from an M3U and add only paths the library already has.

        Writes one crate and one membership. ``Music/missing.mp3`` stays in the
        unmatched list. No audio file is created.

        Returns:
            None. The test fails if the known track is not added.
        """
        with TempLibrary() as temp:
            result = library.import_m3u(
                "Serato Library",
                None,
                "From playlist",
                "#EXTM3U\nMusic/same-a.mp3\nMusic/missing.mp3\n",
            )
            with open_database(temp.db) as conn:
                count = conn.execute(
                    "SELECT COUNT(*) FROM container_asset WHERE asset_id = 1"
                ).fetchone()[0]
        self.assertEqual(result["added"], 1)
        self.assertEqual(result["unmatched_count"], 1)
        self.assertEqual(count, 1)

    def test_empty_playlist_is_rejected(self) -> None:
        """Reject a blank playlist and still import a comment-only file.

        A body of whitespace raises before a crate exists. A file that contains
        only comments creates an empty crate and writes no memberships.

        Returns:
            None. The test fails if the comment-only crate is missing.
        """
        with TempLibrary() as temp:
            with self.assertRaises(LibraryError):
                library.import_m3u("Serato Library", None, "Empty", "   \n")
            result = library.import_m3u(
                "Serato Library", None, "Comments", "# comment only\n"
            )
            with open_database(temp.db) as conn:
                count = conn.execute(
                    "SELECT COUNT(*) FROM container WHERE name = 'Comments'"
                ).fetchone()[0]
        self.assertEqual(result["added"], 0)
        self.assertEqual(result["unmatched_count"], 0)
        self.assertEqual(count, 1)

    def test_duplicates_and_history(self) -> None:
        """Group the fixture pair and read its history session.

        Both reads use the temporary master database. Tracks that share a title,
        artist, and whole-second length form one group. Nothing is written.

        Returns:
            None. The test fails if the pair or the Friday session is missing.
        """
        with TempLibrary():
            groups = library.duplicate_groups()
            sessions = library.history_sessions()
            detail = library.history_entries(1)
        self.assertEqual(groups[0]["ids"], [1, 2])
        self.assertEqual(groups[0]["seconds"], 180)
        self.assertEqual(sessions[0]["name"], "Friday")
        self.assertEqual(sessions[0]["played"], 1)
        entries = cast("list[dict[str, object]]", detail["entries"])
        self.assertEqual(entries[0]["name"], "Same")

    def test_missing_history_session(self) -> None:
        """Return 404 for a history session id that is not in the database.

        The read does not create a session.

        Returns:
            None. The test fails unless the error status is 404.
        """
        with TempLibrary():
            with self.assertRaises(LibraryError) as caught:
                library.history_entries(99)
        self.assertEqual(caught.exception.status, 404)

    def test_reveal_missing_file_does_not_open_finder(self) -> None:
        """Skip the file manager when the audio file is not on disk.

        The fixture path does not exist. ``subprocess.run`` must not be called,
        so Finder and File Explorer stay closed.

        Returns:
            None. The test fails if a process is started.
        """
        with TempLibrary():
            with mock.patch("library.subprocess.run") as run:
                with self.assertRaises(LibraryError):
                    library.reveal(1)
        run.assert_not_called()

    def test_default_library_path_follows_the_operating_system(self) -> None:
        """Resolve the live library path for macOS and for Windows.

        Patches ``sys.platform`` and the home or ``LOCALAPPDATA`` location.
        Neither path is opened. The macOS path is under Application Support.
        The Windows path is under ``%LOCALAPPDATA%\\Serato\\Library``.

        Returns:
            None. The test fails if either path misses its platform directory.
        """
        with mock.patch("library.sys.platform", "darwin"), mock.patch(
            "library.Path.home", return_value=Path("/Users/dj")
        ):
            self.assertEqual(
                library.default_library_path(),
                Path("/Users/dj/Library/Application Support/Serato/Library/master.sqlite"),
            )
        with (
            mock.patch("library.sys.platform", "win32"),
            mock.patch.dict("os.environ", {"LOCALAPPDATA": r"C:\Users\dj\AppData\Local"}),
        ):
            self.assertEqual(
                library.default_library_path(),
                Path(r"C:\Users\dj\AppData\Local") / "Serato" / "Library" / "master.sqlite",
            )

    def test_reveal_command_matches_the_file_manager(self) -> None:
        """Build the Finder command on macOS and the Explorer command on Windows.

        Patches ``sys.platform`` only. No process is started. Explorer keeps the
        comma on ``/select,``. Finder uses ``open -R``.

        Returns:
            None. The test fails if the argv or the file-manager label differs.
        """
        with mock.patch("library.sys.platform", "darwin"):
            self.assertEqual(library.reveal_command("/Music/a.mp3"), ["open", "-R", "/Music/a.mp3"])
            self.assertEqual(library.file_manager_name(), "Finder")
        with mock.patch("library.sys.platform", "win32"):
            self.assertEqual(
                library.reveal_command(r"C:\Music\a.mp3"),
                ["explorer", "/select,", r"C:\Music\a.mp3"],
            )
            self.assertEqual(library.file_manager_name(), "File Explorer")

    def test_windows_serato_process_blocks_the_library(self) -> None:
        """Treat a tasklist image named Serato as an open library on Windows.

        Inserts a lock row and patches the platform and ``subprocess.run``.
        The status read must report the library locked and must ask ``tasklist``,
        which is the Windows process check.

        Returns:
            None. The test fails if writes stay allowed.
        """
        completed = mock.Mock(returncode=0, stdout='"Serato DJ Pro.exe","99","Console","1","1 K"')
        with TempLibrary():
            with open_database(library.MASTER) as conn:
                conn.execute(
                    "INSERT INTO lock (owner_process_id, owner_process_name) VALUES (99, 'Serato DJ Pro')"
                )
            with (
                mock.patch("library.sys.platform", "win32"),
                mock.patch("library.subprocess.run", return_value=completed) as run,
            ):
                info = library.status()
        self.assertTrue(info["open"])
        self.assertFalse(info["writable"])
        self.assertEqual(info["file_manager"], "File Explorer")
        self.assertEqual(run.call_args.args[0][0], "tasklist")

    def test_unix_process_check_uses_ps(self) -> None:
        """Ask ``ps`` whether a process is Serato on macOS and other Unix hosts.

        Patches the platform and the command result. No real process is inspected.
        The argv must start with ``ps -p``.

        Returns:
            None. The test fails if the check does not call ``ps``.
        """
        completed = mock.Mock(returncode=0, stdout="Serato DJ Pro\n")
        with (
            mock.patch("library.sys.platform", "darwin"),
            mock.patch("library.subprocess.run", return_value=completed) as run,
        ):
            self.assertTrue(library._process_is_serato(42))
        self.assertEqual(run.call_args.args[0][:2], ["ps", "-p"])

    def test_disallowed_space(self) -> None:
        """Reject a space name the page does not edit.

        ``Streaming`` is not one of the four allowed spaces. The duplicate query
        must raise before it reads tracks for that name.

        Returns:
            None. The test fails if ``LibraryError`` is not raised.
        """
        with TempLibrary():
            with self.assertRaises(LibraryError):
                library.duplicate_groups("Streaming")

    def test_temporary_database_closes_before_cleanup(self) -> None:
        """Close the fixture database before its directory is removed.

        Writes a lock row through the helper that always closes the connection,
        then leaves the ``with`` block. Windows cannot delete a database that
        still has an open handle, so the file must be gone afterwards.

        Returns:
            None. The test fails if the lock row is lost or the file remains.
        """
        with TempLibrary() as temp:
            with open_database(temp.db) as conn:
                conn.execute(
                    "INSERT INTO lock (owner_process_id, owner_process_name) VALUES (7, 'holding')"
                )
            with open_database(temp.db) as conn:
                count = conn.execute("SELECT COUNT(*) FROM lock").fetchone()[0]
            self.assertEqual(count, 1)
            db = temp.db
        self.assertFalse(db.exists())


def _seed_merge_group(conn: object) -> None:
    """Add a third duplicate, a bystander track, and crate positions.

    Asset 1 is the copy tests keep. Assets 2 and 3 share its title, artist,
    and whole-second length and carry the metadata the merge should fold in.
    Asset 4 sits in a crate so its position can be checked afterwards.

    Args:
        conn: Open connection for the fixture database.

    The connection is left uncommitted. The caller commits by closing the
    ``open_database`` block.
    """
    connection = cast("library.sqlite3.Connection", conn)
    connection.execute(
        """
        UPDATE asset SET
            album = '', genre = NULL, comments = NULL, key = NULL, bpm = NULL,
            color = ?, rating = 0.2, dj_play_count = 2, is_beatgrid_locked = 0,
            dj_recently_played = 0, file_bit_rate = NULL, time_added = 10
        WHERE id = 1
        """,
        (0xFFFFFF,),
    )
    connection.execute(
        """
        UPDATE asset SET
            album = 'Live', genre = 'House', comments = 'night', key = '8A',
            bpm = NULL, color = ?, rating = 0.8, dj_play_count = 9,
            is_beatgrid_locked = 1, dj_recently_played = 1, file_bit_rate = 320000,
            time_added = 11
        WHERE id = 2
        """,
        (0xFFFFFF,),
    )
    connection.execute(
        """
        INSERT INTO asset
            (id, name, artist, album, genre, comments, key, bpm, color, rating,
             dj_play_count, is_beatgrid_locked, length_ms, file_name, portable_id,
             location_id, time_added, file_bit_rate, dj_recently_played)
        VALUES
            (3, 'Same', 'Artist', 'Other', 'Disco', 'later', '1A', 140, ?, 0.4,
             4, 0, 180200, 'same-c.mp3', 'Music/same-c.mp3', 1, 5, 96000, 0),
            (4, 'Other', 'Artist', 'Album', NULL, NULL, NULL, 100, ?, NULL,
             1, 0, 90000, 'other.mp3', 'Music/other.mp3', 1, 12, NULL, 0)
        """,
        (0xCC0000, 0xFFFFFF),
    )
    connection.execute(
        "INSERT INTO space_asset (id, asset_id, space_id) VALUES (3, 3, 1), (4, 4, 1), (5, 3, 2)"
    )
    connection.execute(
        """
        INSERT INTO container
            (id, parent_id, name, type, list_order, space_id, time_added, expanded, portable_id)
        VALUES
            (10, 1, 'Warmup', 1, 1, 1, 1, 0, ''),
            (11, 1, 'Closing', 1, 2, 1, 1, 0, '')
        """
    )
    connection.execute(
        """
        INSERT INTO location_container (id, container_id, location_id, external_container_id)
        VALUES (10, 10, 1, NULL), (11, 11, 1, NULL), (12, 2, 1, NULL)
        """
    )
    connection.execute(
        """
        INSERT INTO container_asset
            (id, asset_id, location_container_id, space_asset_id, list_order, time_added)
        VALUES
            (1, 4, 10, 4, 1, 1),
            (2, 2, 10, 2, 3, 1),
            (3, 3, 10, 3, 5, 1),
            (4, 2, 11, 2, 1, 1),
            (5, 1, 11, 1, 2, 1),
            (6, 3, 12, 5, 7, 1)
        """
    )
    connection.execute(
        """
        INSERT INTO history_entry
            (id, session_id, asset_id, name, artist, played, start_time, file_name, is_missing)
        VALUES
            (2, 1, 2, 'Same', 'Artist', 1, 110, 'same-b.mp3', 0),
            (3, 1, 3, 'Same', 'Artist', 1, 120, 'same-c.mp3', 0)
        """
    )


def _asset_count(path: Path, asset_id: int) -> int:
    """Return 1 when an asset row exists.

    Args:
        path: Fixture database.
        asset_id: Asset id.

    Returns:
        The number of matching rows.
    """
    with open_database(path) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM asset WHERE id = ?", (asset_id,)).fetchone()[0])


class MergeTests(unittest.TestCase):
    """Merge duplicate tracks in the temporary library.

    Each case points ``library.MASTER`` at the fixture and closes it before
    the directory is removed. Audio files created for the trash checks live
    beside that directory and are removed in the test. The live Serato
    library is not opened.
    """

    def test_merge_folds_crates_metadata_and_history(self) -> None:
        """Keep one copy and fold crates, metadata, and history into it.

        Writes the fixture, then merges assets 2 and 3 into asset 1. The
        kept row gains the earliest crate position, the filled fields, and
        the higher play count and rating. History rows point at asset 1 and
        keep the file name they were played with. The beatgrid lock and the
        bitrate stay with the file that was kept. The other asset rows are
        removed. The audio paths in the fixture are not files, so nothing is
        moved on disk.

        Returns:
            None. The test fails if a crate position, a field, or a history
            snapshot is wrong.
        """
        with TempLibrary() as temp:
            with open_database(temp.db) as conn:
                _seed_merge_group(conn)
            result = library.merge_duplicates(
                {"keep_id": 1, "space": "Serato Library", "confirm": True}
            )
            with open_database(temp.db) as conn:
                kept = conn.execute(
                    """
                    SELECT album, genre, comments, key, key_value, bpm, color, rating,
                           dj_play_count, is_beatgrid_locked, dj_recently_played,
                           file_bit_rate, portable_id, time_added
                    FROM asset WHERE id = 1
                    """
                ).fetchone()
                warmup = conn.execute(
                    """
                    SELECT asset_id, list_order FROM container_asset
                    WHERE location_container_id = 10
                    ORDER BY list_order, asset_id
                    """
                ).fetchall()
                closing = conn.execute(
                    """
                    SELECT asset_id, list_order FROM container_asset
                    WHERE location_container_id = 11
                    ORDER BY list_order
                    """
                ).fetchall()
                prepare = conn.execute(
                    """
                    SELECT asset_id, list_order FROM container_asset
                    WHERE location_container_id = 12
                    """
                ).fetchall()
                history = conn.execute(
                    "SELECT asset_id, file_name FROM history_entry ORDER BY id"
                ).fetchall()
                removed = conn.execute(
                    "SELECT COUNT(*) FROM asset WHERE id IN (2, 3)"
                ).fetchone()[0]
                bystander = conn.execute("SELECT COUNT(*) FROM asset WHERE id = 4").fetchone()[0]
            backups = list((temp.db.resolve().parent / "Backups").glob("serato-web-*"))
        changes = {item["field"]: item["after"] for item in cast(list[dict[str, object]], result["fields"])}
        self.assertTrue(result["ok"])
        self.assertFalse(result["preview"])
        self.assertEqual(result["remove_ids"], [2, 3])
        self.assertEqual(changes["album"], "Live")
        self.assertEqual(changes["genre"], "House")
        self.assertEqual(changes["comments"], "night")
        self.assertEqual(changes["key"], "8A")
        self.assertEqual(changes["bpm"], 140)
        self.assertEqual(changes["rating"], 0.8)
        self.assertEqual(changes["dj_play_count"], 9)
        self.assertEqual(changes["color"], "#CC0000")
        self.assertEqual(changes["time_added"], 5)
        self.assertEqual(changes["dj_recently_played"], 1)
        self.assertNotIn("is_beatgrid_locked", changes)
        self.assertEqual(kept[0], "Live")
        self.assertEqual(kept[1], "House")
        self.assertEqual(kept[2], "night")
        self.assertEqual(kept[3], "8A")
        self.assertEqual(kept[4], library.serato_key_type("8A"))
        self.assertEqual(kept[5], 140)
        self.assertEqual(kept[6], 0xCC0000)
        self.assertEqual(kept[7], 0.8)
        self.assertEqual(kept[8], 9)
        self.assertEqual(kept[9], 0)
        self.assertEqual(kept[10], 1)
        self.assertIsNone(kept[11])
        self.assertEqual(kept[12], "Music/same-a.mp3")
        self.assertEqual(kept[13], 5)
        self.assertEqual(warmup, [(4, 1), (1, 3)])
        self.assertEqual(closing, [(1, 2)])
        self.assertEqual(prepare, [(1, 7)])
        self.assertEqual(history, [(1, "same-a.mp3"), (1, "same-b.mp3"), (1, "same-c.mp3")])
        self.assertEqual(removed, 0)
        self.assertEqual(bystander, 1)
        self.assertEqual(result["history_entries"], 2)
        self.assertTrue(result["history_repointed"])
        self.assertEqual(len(backups), 1)
        names = {item["name"] for item in cast(list[dict[str, object]], result["crates_added"])}
        self.assertEqual(names, {"Warmup", "Prepare"})
        warning = str(result["warning"])
        self.assertEqual(warning.count("Saved in the main library"), 1)
        self.assertIn("was not changed", warning)

    def test_preview_does_not_write(self) -> None:
        """Return the plan and leave the database and the file alone.

        ``preview`` true is set together with the file-move flags. The
        response says the move did not run. No backup directory is created.

        Returns:
            None. The test fails if a row changes or the file is moved.
        """
        with TempLibrary() as temp:
            with open_database(temp.db) as conn:
                _seed_merge_group(conn)
            audio = temp.db.parent / "same-b.mp3"
            audio.write_bytes(b"duplicate")
            with open_database(temp.db) as conn:
                conn.execute(
                    "UPDATE asset SET portable_id = ? WHERE id = 2",
                    (str(audio),),
                )
            result = library.merge_duplicates(
                {
                    "keep_id": 1,
                    "preview": True,
                    "confirm": True,
                    "delete_files": True,
                    "confirm_delete_files": True,
                }
            )
            left = _asset_count(temp.db, 2)
            backups = temp.db.parent / "Backups"
            self.assertTrue(audio.is_file())
            self.assertEqual(audio.read_bytes(), b"duplicate")
            self.assertFalse(backups.exists())
        self.assertTrue(result["preview"])
        self.assertFalse(result["delete_files"])
        self.assertIn("Warmup", [item["name"] for item in cast(list[dict[str, object]], result["crates_added"])])
        self.assertEqual(left, 1)

    def test_merge_requires_confirm_and_a_real_group(self) -> None:
        """Refuse a merge that is not confirmed or is not a duplicate group.

        A missing confirmation, a file move without its own confirmation, a
        boolean id, and a track whose partner no longer matches are each
        rejected. The asset rows stay, and no backup is taken.

        Returns:
            None. The test fails if a refusal still changes the library.
        """
        with TempLibrary() as temp:
            before = _asset_count(temp.db, 2)
            with self.assertRaises(LibraryError):
                library.merge_duplicates({"keep_id": 1, "delete_files": False})
            with self.assertRaises(LibraryError):
                library.merge_duplicates(
                    {"keep_id": 1, "confirm": True, "delete_files": True}
                )
            with self.assertRaises(LibraryError):
                library.merge_duplicates({"keep_id": True, "confirm": True})
            with open_database(temp.db) as conn:
                conn.execute("UPDATE asset SET artist = 'Other' WHERE id = 2")
            with self.assertRaises(LibraryError):
                library.merge_duplicates({"keep_id": 1, "confirm": True})
            after = _asset_count(temp.db, 2)
            self.assertFalse((temp.db.parent / "Backups").exists())
        self.assertEqual(before, 1)
        self.assertEqual(after, 1)

    def test_merge_refuses_while_serato_is_open(self) -> None:
        """Refuse the merge before a backup when Serato holds the lock.

        Inserts a lock row and patches the process check. The duplicate row
        must still be present.

        Returns:
            None. The test fails if ``SeratoOpen`` is not raised.
        """
        with TempLibrary() as temp:
            with open_database(temp.db) as conn:
                conn.execute(
                    "INSERT INTO lock (owner_process_id, owner_process_name) VALUES (99, 'Serato DJ Pro')"
                )
            with mock.patch.object(library, "_process_is_serato", return_value=True):
                with self.assertRaises(SeratoOpen):
                    library.merge_duplicates({"keep_id": 1, "confirm": True})
            left = _asset_count(temp.db, 2)
            self.assertFalse((temp.db.parent / "Backups").exists())
        self.assertEqual(left, 1)

    def test_failed_mirror_rolls_the_master_back(self) -> None:
        """Leave the master database unchanged when a later step raises.

        The crate add is mirrored after the master rows are updated and
        before commit. The mirror is forced to raise. The duplicate asset
        and its crate row must remain.

        Returns:
            None. The test fails if the duplicate row is gone.
        """
        with TempLibrary() as temp:
            with open_database(temp.db) as conn:
                _seed_merge_group(conn)
            with mock.patch.object(library, "_mirror_placed_membership", side_effect=RuntimeError("boom")):
                with self.assertRaises(RuntimeError):
                    library.merge_duplicates({"keep_id": 1, "confirm": True})
            with open_database(temp.db) as conn:
                left = conn.execute("SELECT COUNT(*) FROM asset WHERE id = 2").fetchone()[0]
                crate = conn.execute(
                    "SELECT COUNT(*) FROM container_asset WHERE asset_id = 2"
                ).fetchone()[0]
        self.assertEqual(left, 1)
        self.assertEqual(crate, 2)

    def test_merge_mirrors_the_location_database(self) -> None:
        """Update root.sqlite in the same way the master merge changes crates.

        Both copies live on location 3. The duplicate's crate position is
        given to the kept track in the location database, the duplicate
        asset row is removed there, and the filled album is copied onto the
        kept location row.

        Returns:
            None. The test fails if the drive database still has the duplicate.
        """
        with TempLibrary() as temp:
            root = temp.db.parent / "root.sqlite"
            with open_database(root) as conn:
                conn.executescript(
                    """
                    CREATE TABLE serato (revision INTEGER);
                    CREATE TABLE space (id INTEGER PRIMARY KEY, name TEXT);
                    CREATE TABLE asset (
                        id INTEGER PRIMARY KEY,
                        album TEXT,
                        rating REAL,
                        dj_play_count INTEGER,
                        time_modified INTEGER,
                        revision INTEGER
                    );
                    CREATE TABLE space_asset (
                        id INTEGER PRIMARY KEY,
                        asset_id INTEGER,
                        space_id INTEGER,
                        revision INTEGER
                    );
                    CREATE TABLE container (
                        id INTEGER PRIMARY KEY,
                        name TEXT,
                        type INTEGER,
                        space_id INTEGER
                    );
                    CREATE TABLE container_asset (
                        id INTEGER PRIMARY KEY,
                        revision INTEGER,
                        container_id INTEGER,
                        space_asset_id INTEGER,
                        list_order INTEGER,
                        time_added INTEGER
                    );
                    INSERT INTO serato (revision) VALUES (1);
                    INSERT INTO space (id, name) VALUES (1, 'Serato Library');
                    INSERT INTO asset (id, album, rating, dj_play_count) VALUES
                        (101, '', 0.2, 2),
                        (102, 'Live', 0.8, 9);
                    INSERT INTO space_asset (id, asset_id, space_id) VALUES (1, 101, 1), (2, 102, 1);
                    INSERT INTO container (id, name, type, space_id) VALUES (50, 'Warmup', 1, 1);
                    INSERT INTO container_asset (id, container_id, space_asset_id, list_order, time_added)
                    VALUES (1, 50, 2, 4, 1);
                    """
                )
            with open_database(temp.db) as conn:
                conn.execute(
                    """
                    UPDATE asset SET
                        location_id = 3, external_id = 101, album = '', rating = 0.2,
                        dj_play_count = 2
                    WHERE id = 1
                    """
                )
                conn.execute(
                    """
                    UPDATE asset SET
                        location_id = 3, external_id = 102, album = 'Live', rating = 0.8,
                        dj_play_count = 9
                    WHERE id = 2
                    """
                )
                conn.execute(
                    """
                    INSERT INTO container
                        (id, parent_id, name, type, list_order, space_id, time_added, expanded, portable_id)
                    VALUES (10, 1, 'Warmup', 1, 1, 1, 1, 0, '')
                    """
                )
                conn.execute(
                    """
                    INSERT INTO location_container (id, container_id, location_id, external_container_id)
                    VALUES (10, 10, 3, 50)
                    """
                )
                conn.execute(
                    """
                    INSERT INTO container_asset
                        (id, asset_id, location_container_id, space_asset_id, list_order, time_added)
                    VALUES (1, 2, 10, 2, 4, 1)
                    """
                )
                conn.execute(
                    "INSERT INTO connection (location_id, database_uri) VALUES (3, ?)",
                    (root.resolve().as_uri(),),
                )
            result = library.merge_duplicates({"keep_id": 1, "confirm": True})
            with open_database(root) as conn:
                albums = conn.execute("SELECT id, album, dj_play_count FROM asset ORDER BY id").fetchall()
                members = conn.execute(
                    "SELECT space_asset_id, list_order FROM container_asset ORDER BY space_asset_id"
                ).fetchall()
            master_left = _asset_count(temp.db, 2)
        self.assertIsNone(result["warning"])
        self.assertEqual(master_left, 0)
        self.assertEqual(albums, [(101, "Live", 9)])
        self.assertEqual(members, [(1, 4)])

    def test_unsafe_file_moves_are_refused_before_a_write(self) -> None:
        """Refuse to trash a symlink, a library file, or the kept audio.

        Each refusal happens before ``begin_write``. The duplicate asset and
        the target file stay where they are. A hard link to the kept file is
        treated as the same file.

        Returns:
            None. The test fails if a refusal deletes a file or a row.
        """
        with TempLibrary() as temp:
            library_dir = temp.db.parent
            sibling = library_dir.parent / f"{library_dir.name}-backup"
            sibling.mkdir()
            try:
                target = sibling / "real.mp3"
                link = sibling / "link.mp3"
                target.write_bytes(b"target")
                try:
                    link.symlink_to(target)
                except OSError:
                    self.skipTest("symlinks are not available")
                with open_database(temp.db) as conn:
                    conn.execute("UPDATE asset SET portable_id = ? WHERE id = 2", (str(link),))
                with self.assertRaises(LibraryError):
                    library.merge_duplicates(
                        {"keep_id": 1, "confirm": True, "delete_files": True, "confirm_delete_files": True}
                    )
                self.assertTrue(link.is_symlink())
                self.assertEqual(target.read_bytes(), b"target")
                self.assertEqual(_asset_count(temp.db, 2), 1)
                self.assertFalse((library_dir / "Backups").exists())

                decoy = sibling / "master.sqlite"
                decoy.write_bytes(b"not-the-library")
                with open_database(temp.db) as conn:
                    conn.execute("UPDATE asset SET portable_id = ? WHERE id = 2", (str(decoy),))
                with self.assertRaises(LibraryError):
                    library.merge_duplicates(
                        {"keep_id": 1, "confirm": True, "delete_files": True, "confirm_delete_files": True}
                    )
                self.assertEqual(decoy.read_bytes(), b"not-the-library")
                self.assertTrue(temp.db.is_file())

                inside = library_dir / "song.mp3"
                inside.write_bytes(b"inside")
                with open_database(temp.db) as conn:
                    conn.execute("UPDATE asset SET portable_id = ? WHERE id = 2", (str(inside),))
                with self.assertRaises(LibraryError):
                    library.merge_duplicates(
                        {"keep_id": 1, "confirm": True, "delete_files": True, "confirm_delete_files": True}
                    )
                self.assertEqual(inside.read_bytes(), b"inside")

                kept = sibling / "keep.mp3"
                same = sibling / "same.mp3"
                kept.write_bytes(b"audio")
                try:
                    os.link(kept, same)
                except OSError:
                    linked = False
                else:
                    linked = True
                if linked:
                    with open_database(temp.db) as conn:
                        conn.execute(
                            "UPDATE asset SET portable_id = ? WHERE id = 1",
                            (str(kept),),
                        )
                        conn.execute(
                            "UPDATE asset SET portable_id = ? WHERE id = 2",
                            (str(same),),
                        )
                    with self.assertRaises(LibraryError):
                        library.merge_duplicates(
                            {
                                "keep_id": 1,
                                "confirm": True,
                                "delete_files": True,
                                "confirm_delete_files": True,
                            }
                        )
                    self.assertEqual(kept.read_bytes(), b"audio")
                    self.assertEqual(same.read_bytes(), b"audio")
                    self.assertEqual(_asset_count(temp.db, 2), 1)
            finally:
                shutil.rmtree(sibling, ignore_errors=True)
                inside = library_dir / "song.mp3"
                if inside.exists():
                    inside.unlink()

    def test_trash_moves_a_sibling_file_and_not_a_prefix_match(self) -> None:
        """Move the duplicate into the FreeDesktop trash and leave the kept file.

        The audio lives in a directory whose name starts with the library
        folder name and then ``-backup``. A string prefix would treat that
        directory as inside the library and refuse the move. The file must
        land in the trash files directory with a ``.trashinfo`` record, and
        the kept file must stay. ``os.unlink`` is not used on the audio.

        Returns:
            None. The test fails if the file is unlinked or left in place.
        """
        with TempLibrary() as temp:
            library_dir = temp.db.parent
            sibling = library_dir.parent / f"{library_dir.name}-backup"
            sibling.mkdir()
            xdg = sibling / "xdg"
            try:
                self.assertTrue(str(sibling).startswith(str(library_dir)))
                kept = sibling / "keep.mp3"
                audio = sibling / "song.mp3"
                kept.write_bytes(b"keep")
                audio.write_bytes(b"duplicate")
                with open_database(temp.db) as conn:
                    conn.execute("UPDATE asset SET portable_id = ?, file_name = 'keep.mp3' WHERE id = 1", (str(kept),))
                    conn.execute("UPDATE asset SET portable_id = ?, file_name = 'song.mp3' WHERE id = 2", (str(audio),))
                real_unlink = os.unlink

                def guard(path: object, *args: object, **kwargs: object) -> None:
                    """Refuse an unlink of the duplicate audio and pass other paths through.

                    Args:
                        path: Path ``os.unlink`` was asked to remove.
                        *args: Extra positional arguments.
                        **kwargs: Extra keyword arguments.
                    """
                    if Path(str(path)) == audio:
                        raise AssertionError("hard delete")
                    real_unlink(path, *args, **kwargs)  # type: ignore[arg-type]

                with (
                    mock.patch("library.sys.platform", "linux"),
                    mock.patch.dict(os.environ, {"XDG_DATA_HOME": str(xdg)}),
                    mock.patch("os.unlink", guard),
                ):
                    result = library.merge_duplicates(
                        {
                            "keep_id": 1,
                            "confirm": True,
                            "delete_files": True,
                            "confirm_delete_files": True,
                        }
                    )
                files = xdg / "Trash" / "files"
                moved = [path for path in files.iterdir() if path.name == "song.mp3" or path.name.startswith("song.mp3_")]
                info = xdg / "Trash" / "info" / f"{moved[0].name}.trashinfo"
                self.assertEqual(result["trashed"], ["song.mp3"])
                self.assertFalse(audio.exists())
                self.assertEqual(kept.read_bytes(), b"keep")
                self.assertEqual(moved[0].read_bytes(), b"duplicate")
                self.assertIn("[Trash Info]", info.read_text(encoding="utf-8"))
                self.assertIn("song.mp3", info.read_text(encoding="utf-8"))
                self.assertEqual(_asset_count(temp.db, 2), 0)
            finally:
                shutil.rmtree(sibling, ignore_errors=True)

    def test_trash_failure_keeps_the_library_change_and_the_file(self) -> None:
        """Report a trash failure after the library rows have been merged.

        The move raises after commit. The duplicate asset is gone and the
        audio file is still on disk. The warning names the file, not a path
        outside the file name.

        Returns:
            None. The test fails if the file is gone or the row remains.
        """
        with TempLibrary() as temp:
            audio = temp.db.parent.parent / f"{temp.db.parent.name}-backup-file.mp3"
            audio.write_bytes(b"still")
            try:
                with open_database(temp.db) as conn:
                    conn.execute(
                        "UPDATE asset SET portable_id = ?, file_name = 'song.mp3' WHERE id = 2",
                        (str(audio),),
                    )
                with mock.patch.object(
                    library,
                    "_move_to_trash",
                    side_effect=LibraryError("The file could not be moved to the Trash."),
                ):
                    result = library.merge_duplicates(
                        {
                            "keep_id": 1,
                            "confirm": True,
                            "delete_files": True,
                            "confirm_delete_files": True,
                        }
                    )
                warning = str(result["warning"])
                self.assertIn("song.mp3", warning)
                self.assertNotIn(str(audio.parent), warning)
                self.assertEqual(audio.read_bytes(), b"still")
                self.assertEqual(_asset_count(temp.db, 2), 0)
            finally:
                if audio.exists():
                    audio.unlink()

    def test_cue_warning_does_not_rewrite_the_audio_file(self) -> None:
        """Warn when the kept file has no cues and a duplicate file does.

        The tag reader is patched so the duplicate reports one cue. Both
        files are written with fixed bytes first. After a preview and a
        merge, those bytes are unchanged. The warning says the app does
        not copy the frames.

        Returns:
            None. The test fails if the warning is missing or a file changes.
        """
        with TempLibrary() as temp:
            sibling = temp.db.parent.parent / f"{temp.db.parent.name}-backup"
            sibling.mkdir()
            try:
                kept = sibling / "keep.mp3"
                dup = sibling / "dup.mp3"
                kept.write_bytes(b"KEEP")
                dup.write_bytes(b"DUP")
                with open_database(temp.db) as conn:
                    conn.execute(
                        "UPDATE asset SET portable_id = ?, file_name = 'keep.mp3' WHERE id = 1",
                        (str(kept),),
                    )
                    conn.execute(
                        "UPDATE asset SET portable_id = ?, file_name = 'dup.mp3' WHERE id = 2",
                        (str(dup),),
                    )
                marked = {
                    "cues": [{"index": 0, "start_ms": 1, "color": None, "name": "Drop"}],
                    "loops": [],
                    "flips": [],
                    "beatgrid": [],
                    "found": True,
                }
                empty = {"cues": [], "loops": [], "flips": [], "beatgrid": [], "found": False}

                def fake(path: str | None) -> dict[str, object]:
                    """Return one cue for the duplicate and nothing for the kept file.

                    Args:
                        path: Audio path passed to the tag reader.

                    Returns:
                        A marker dict.
                    """
                    if path and path.endswith("dup.mp3"):
                        return marked
                    return empty

                with mock.patch("library.read_serato_tags", side_effect=fake):
                    preview = library.merge_duplicates({"keep_id": 1, "preview": True})
                    result = library.merge_duplicates({"keep_id": 1, "confirm": True})
                self.assertIn("does not copy them", str(preview["cue_warning"]))
                self.assertIn("dup.mp3", str(preview["cue_warning"]))
                self.assertIn("does not copy them", str(result["cue_warning"]))
                self.assertEqual(kept.read_bytes(), b"KEEP")
                self.assertEqual(dup.read_bytes(), b"DUP")
            finally:
                shutil.rmtree(sibling, ignore_errors=True)

    def test_windows_trash_keeps_the_path_out_of_the_script(self) -> None:
        """Pass a Windows trash path in the environment, not in the script.

        Patches the platform and ``subprocess.run``. The script asks for the
        Recycle Bin. The path is only ``SERATO_TRASH_PATH``. The file is not
        unlinked by this process.

        Returns:
            None. The test fails if the script contains the path.
        """
        with TempLibrary() as temp:
            sibling = temp.db.parent.parent / f"{temp.db.parent.name}-backup"
            sibling.mkdir()
            try:
                audio = sibling / "song.mp3"
                audio.write_bytes(b"x")
                with mock.patch("library.sys.platform", "win32"), mock.patch(
                    "library.subprocess.run",
                    return_value=mock.Mock(returncode=0),
                ) as run, mock.patch.object(Path, "exists", return_value=False):
                    library._move_to_trash(audio)
                script = run.call_args.args[0][-1]
                self.assertIn("SendToRecycleBin", script)
                self.assertNotIn(str(audio), script)
                self.assertEqual(run.call_args.kwargs["env"]["SERATO_TRASH_PATH"], str(audio))
                self.assertTrue(audio.is_file())
            finally:
                shutil.rmtree(sibling, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
