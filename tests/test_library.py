"""Library reads and writes against a temporary database."""

from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()
