"""Backup, undo, and cue-copy safety against the format fixtures.

The undo journal already restores a move, a trash, and a cue file on
main. ``ensure_backup`` restores the crate rows. FLAC and M4A destinations
are left untouched because the copier only rewrites a plain ID3 tag.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import unittest
from pathlib import Path
from unittest import mock

import tempfile

import files
import library
import server
from tags import copy_serato_geob, plan_serato_geob
from tests.fixture import TempLibrary, open_database
from tests.test_tags import _id3_file, _markers_payload


FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "serato4" / "audio"


def _hash(path: Path) -> str:
    """Hash one file.

    Args:
        path: File to read.

    Returns:
        The SHA-256 hex digest.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


class MissingDriveTests(unittest.TestCase):
    """A crate row on an unmounted volume stays, and its markers are unavailable."""

    def test_unmounted_track_stays_in_the_crate(self) -> None:
        """Keep the membership and report markers unavailable.

        The path points at a volume directory that is never created. The
        asset row and the crate membership are still there after the read.

        Returns:
            None. The test fails if the track is removed or markers are
            reported as found.
        """
        with TempLibrary() as temp:
            volume = temp.root / "Volumes" / "UNMOUNTED"
            track = volume / "Music" / "gig.mp3"
            self.assertFalse(volume.exists())
            with open_database(temp.db) as conn:
                conn.execute(
                    "UPDATE asset SET portable_id = ?, file_name = ? WHERE id = 1",
                    (str(track), track.name),
                )
            created = library.crate_action({"action": "create", "name": "Gig"})
            library.crate_action({"action": "add", "id": created["id"], "asset": 1})
            payload = server.load_library("Serato Library")
            crates = payload["crates"]
            self.assertIsInstance(crates, list)
            assert isinstance(crates, list)
            gig = next(crate for crate in crates if crate["name"] == "Gig")
            self.assertIn(1, gig["tracks"])
            detail = server.load_track(1, "Serato Library")
            self.assertIsNotNone(detail)
            assert detail is not None
            self.assertFalse(detail["file_on_disk"])
            self.assertTrue(detail["markers_unavailable"])
            self.assertFalse(detail["markers_found"])
            self.assertEqual(detail["cues"], [])
            with open_database(temp.db) as conn:
                row = conn.execute("SELECT id, portable_id FROM asset WHERE id = 1").fetchone()
                member = conn.execute(
                    """
                    SELECT 1
                    FROM container_asset ca
                    JOIN location_container lc ON lc.id = ca.location_container_id
                    WHERE ca.asset_id = 1 AND lc.container_id = ?
                    """,
                    (created["id"],),
                ).fetchone()
            self.assertIsNotNone(row)
            self.assertIsNotNone(member)
            assert row is not None
            self.assertEqual(row[1], str(track))


class UndoAndBackupTests(unittest.TestCase):
    """Restore crates from the backup and files from the undo journal."""

    def setUp(self) -> None:
        """Point the library at fixture audio and a private trash directory.

        Returns:
            None.
        """
        self.library = TempLibrary()
        self.library.__enter__()
        self.music = self.library.root / "music"
        self.music.mkdir()
        self.song = self.music / "one-grid.mp3"
        self.other = self.music / "several-grid.aiff"
        self.song.write_bytes((FIXTURES / "one-grid.mp3").read_bytes())
        self.other.write_bytes((FIXTURES / "several-grid.aiff").read_bytes())
        self._old_trash = os.environ.get(files._TRASH_ENV)
        os.environ[files._TRASH_ENV] = str(self.library.root / "trash-bin")
        with open_database(self.library.db) as conn:
            conn.execute(
                "UPDATE asset SET portable_id = ?, file_name = ?, is_missing = 0 WHERE id = 1",
                (str(self.song.resolve()), self.song.name),
            )
            conn.execute(
                "UPDATE asset SET portable_id = ?, file_name = ?, is_missing = 0 WHERE id = 2",
                (str(self.other.resolve()), self.other.name),
            )

    def tearDown(self) -> None:
        """Restore the trash override and remove the temporary library.

        Returns:
            None.
        """
        if self._old_trash is None:
            os.environ.pop(files._TRASH_ENV, None)
        else:
            os.environ[files._TRASH_ENV] = self._old_trash
        self.library.__exit__(None, None, None)

    def test_backup_and_undo_keep_crates_cues_and_grids(self) -> None:
        """Put crates, cue points, and beatgrids back after a bad edit.

        The snapshot is ``library.ensure_backup``. The file half is
        ``files._undo_journal``, which moves a renamed file back, restores
        a trashed file, and calls ``_restore_cue`` for the clobbered tag.
        QA confirmed this journal round-trip already passes on main.

        Returns:
            None. The test fails if a crate, cue, grid, or audio byte differs.
        """
        created = library.crate_action({"action": "create", "name": "House"})
        library.crate_action({"action": "add", "id": created["id"], "asset": 1})
        library.crate_action({"action": "add", "id": created["id"], "asset": 2})
        self._drop_backups()
        folder = library.ensure_backup()
        self.assertIsNotNone(folder)
        assert folder is not None
        before_song = _hash(self.song)
        before_other = _hash(self.other)
        before_detail = server.load_track(1, "Serato Library")
        self.assertIsNotNone(before_detail)
        assert before_detail is not None
        self.assertTrue(before_detail["markers_found"])
        self.assertGreaterEqual(len(before_detail["cues"]), 1)
        self.assertGreaterEqual(len(before_detail["beatgrid"]), 1)
        library.crate_action({"action": "rename", "id": created["id"], "name": "Changed"})
        renamed = server.load_library("Serato Library")
        crates = renamed["crates"]
        self.assertIsInstance(crates, list)
        assert isinstance(crates, list)
        self.assertTrue(any(crate["name"] == "Changed" for crate in crates))
        extra = self.music / "extra.mp3"
        extra.write_bytes(b"extra-bytes")
        moved = self.music / "extra-moved.mp3"
        os.rename(extra, moved)
        trash_record = files.trash_file(self.other)
        cue_backup = self.library.root / "cue-hold.mp3"
        shutil.copy2(self.song, cue_backup)
        self.song.write_bytes(b"clobbered-tags")
        journal = {
            "moves": [{"src": str(extra), "dst": str(moved), "kind": "rename"}],
            "trash": [trash_record],
            "cue_backup": {"file": str(self.song), "backup": str(cue_backup)},
        }
        for suffix in ("-wal", "-shm", "-journal"):
            Path(str(self.library.db) + suffix).unlink(missing_ok=True)
        shutil.copyfile(folder / "master.sqlite", self.library.db)
        server.invalidate()
        files._undo_journal(journal)
        self.assertEqual(_hash(self.song), before_song)
        self.assertEqual(_hash(self.other), before_other)
        self.assertEqual(extra.read_bytes(), b"extra-bytes")
        self.assertFalse(moved.exists())
        self.assertFalse(cue_backup.exists())
        self.assertTrue(self.other.is_file())
        restored = server.load_library("Serato Library")
        restored_crates = restored["crates"]
        self.assertIsInstance(restored_crates, list)
        assert isinstance(restored_crates, list)
        house = next(crate for crate in restored_crates if crate["name"] == "House")
        self.assertIn(1, house["tracks"])
        self.assertIn(2, house["tracks"])
        self.assertFalse(any(crate["name"] == "Changed" for crate in restored_crates))
        detail = server.load_track(1, "Serato Library")
        other = server.load_track(2, "Serato Library")
        self.assertIsNotNone(detail)
        self.assertIsNotNone(other)
        assert detail is not None and other is not None
        self.assertEqual(detail["cues"], before_detail["cues"])
        self.assertEqual(detail["loops"], before_detail["loops"])
        self.assertEqual(detail["flips"], before_detail["flips"])
        self.assertEqual(detail["beatgrid"], before_detail["beatgrid"])
        self.assertTrue(other["markers_found"])
        self.assertGreaterEqual(len(other["beatgrid"]), 2)
        self.assertFalse(detail["markers_unavailable"])

    def test_same_second_backup_collision_keeps_the_first_copy(self) -> None:
        """Raise ``FileExistsError`` when the timestamped folder already exists.

        ``ensure_backup`` names the folder with a one-second timestamp and
        refuses to reuse it. The first copy stays readable.

        Returns:
            None. The test fails if the second call overwrites the snapshot
            or does not raise.
        """
        with mock.patch("library.time.strftime", return_value="20261028-120000"):
            folder = library.ensure_backup()
            self.assertIsNotNone(folder)
            assert folder is not None
            digest = (folder / "master.sqlite").read_bytes()
            library._backed_up.clear()
            with self.assertRaises(FileExistsError):
                library.ensure_backup()
            self.assertEqual((folder / "master.sqlite").read_bytes(), digest)
        with open_database(folder / "master.sqlite") as conn:
            row = conn.execute("SELECT id FROM asset WHERE id = 1").fetchone()
        self.assertIsNotNone(row)

    def _drop_backups(self) -> None:
        """Remove snapshot folders so the next call writes a fresh one.

        Returns:
            None.
        """
        backup_root = self.library.root / "Backups"
        if backup_root.exists():
            shutil.rmtree(backup_root)
        library._backed_up.clear()


class CueCopyCarrierTests(unittest.TestCase):
    """``plan_serato_geob`` and ``copy_serato_geob`` leave FLAC and M4A alone."""

    def test_flac_and_m4a_are_not_rewritten(self) -> None:
        """Refuse a FLAC or M4A destination and keep every byte.

        The source is a plain ID3v2.3 file the copier would accept for an
        MP3. The fixture files are the destinations.

        Returns:
            None. The test fails if a destination byte changes or the status
            is anything other than unsupported.
        """
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.mp3"
            _id3_file(_markers_payload(), source)
            for name in ("one-grid.flac", "several-grid.m4a"):
                dest = root / name
                dest.write_bytes((FIXTURES / name).read_bytes())
                before = dest.read_bytes()
                planned = plan_serato_geob(source, dest)
                copied = copy_serato_geob(source, dest)
                self.assertEqual(planned["status"], "unsupported")
                self.assertEqual(copied["status"], "unsupported")
                self.assertEqual(dest.read_bytes(), before)
                flipped = plan_serato_geob(dest, source)
                self.assertEqual(flipped["status"], "unsupported")
                self.assertEqual(dest.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
