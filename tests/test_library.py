"""Library reads and writes against a temporary database."""

from __future__ import annotations

import sqlite3
import unittest
from unittest import mock

import library
from library import LibraryError, SeratoOpen
from tests.fixture import TempLibrary


class LibraryTests(unittest.TestCase):
    def test_status_is_writable_without_a_lock(self) -> None:
        with TempLibrary() as temp:
            info = library.status()
        self.assertTrue(info["writable"])
        self.assertFalse(info["open"])
        self.assertIn(temp.db.name, "master.sqlite")

    def test_status_blocks_a_live_serato_process(self) -> None:
        with TempLibrary():
            with sqlite3.connect(library.MASTER) as conn:
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
        with TempLibrary() as temp:
            result = library.save_track(1, {"name": "Renamed", "bpm": 126})
            with sqlite3.connect(temp.db) as conn:
                row = conn.execute("SELECT name, bpm FROM asset WHERE id = 1").fetchone()
            backups = list((temp.db.resolve().parent / "Backups").glob("serato-web-*"))
            self.assertTrue(result["ok"])
            self.assertIsNotNone(result["warning"])
            self.assertEqual(row, ("Renamed", 126))
            self.assertEqual(len(backups), 1)
            self.assertTrue((backups[0] / "master.sqlite").is_file())

    def test_save_rejects_a_bad_bpm_before_writing(self) -> None:
        with TempLibrary() as temp:
            with self.assertRaises(LibraryError):
                library.save_track(1, {"bpm": 2000})
            with sqlite3.connect(temp.db) as conn:
                bpm = conn.execute("SELECT bpm FROM asset WHERE id = 1").fetchone()[0]
        self.assertEqual(bpm, 120)

    def test_crate_create_add_export_and_delete(self) -> None:
        with TempLibrary() as temp:
            created = library.crate_action({"action": "create", "name": "Warmup"})
            added = library.crate_action({"action": "add", "id": created["id"], "asset": 1})
            playlist = library.export_m3u("Serato Library", created["id"])
            library.crate_action({"action": "delete", "id": created["id"]})
            with sqlite3.connect(temp.db) as conn:
                left = conn.execute(
                    "SELECT COUNT(*) FROM container WHERE name = 'Warmup'"
                ).fetchone()[0]
        self.assertTrue(added["ok"])
        self.assertIn("#PLAYLIST:Warmup", playlist)
        self.assertIn("same-a.mp3", playlist)
        self.assertEqual(left, 0)

    def test_unknown_crate_action_rolls_back(self) -> None:
        with TempLibrary():
            with self.assertRaises(LibraryError):
                library.crate_action({"action": "explode"})

    def test_import_matches_known_paths(self) -> None:
        with TempLibrary() as temp:
            result = library.import_m3u(
                "Serato Library",
                None,
                "From playlist",
                "#EXTM3U\nMusic/same-a.mp3\nMusic/missing.mp3\n",
            )
            with sqlite3.connect(temp.db) as conn:
                count = conn.execute(
                    "SELECT COUNT(*) FROM container_asset WHERE asset_id = 1"
                ).fetchone()[0]
        self.assertEqual(result["added"], 1)
        self.assertEqual(result["unmatched_count"], 1)
        self.assertEqual(count, 1)

    def test_empty_playlist_is_rejected(self) -> None:
        with TempLibrary() as temp:
            with self.assertRaises(LibraryError):
                library.import_m3u("Serato Library", None, "Empty", "   \n")
            result = library.import_m3u(
                "Serato Library", None, "Comments", "# comment only\n"
            )
            with sqlite3.connect(temp.db) as conn:
                count = conn.execute(
                    "SELECT COUNT(*) FROM container WHERE name = 'Comments'"
                ).fetchone()[0]
        self.assertEqual(result["added"], 0)
        self.assertEqual(result["unmatched_count"], 0)
        self.assertEqual(count, 1)

    def test_duplicates_and_history(self) -> None:
        with TempLibrary():
            groups = library.duplicate_groups()
            sessions = library.history_sessions()
            detail = library.history_entries(1)
        self.assertEqual(groups[0]["ids"], [1, 2])
        self.assertEqual(groups[0]["seconds"], 180)
        self.assertEqual(sessions[0]["name"], "Friday")
        self.assertEqual(sessions[0]["played"], 1)
        self.assertEqual(detail["entries"][0]["name"], "Same")

    def test_missing_history_session(self) -> None:
        with TempLibrary():
            with self.assertRaises(LibraryError) as caught:
                library.history_entries(99)
        self.assertEqual(caught.exception.status, 404)

    def test_reveal_missing_file_does_not_open_finder(self) -> None:
        with TempLibrary():
            with mock.patch("library.subprocess.run") as run:
                with self.assertRaises(LibraryError):
                    library.reveal(1)
        run.assert_not_called()

    def test_disallowed_space(self) -> None:
        with TempLibrary():
            with self.assertRaises(LibraryError):
                library.duplicate_groups("Streaming")


if __name__ == "__main__":
    unittest.main()
