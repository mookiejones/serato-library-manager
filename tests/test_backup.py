"""Backup folder names and a restore that matches the source."""

from __future__ import annotations

import hashlib
import sqlite3
import unittest
from pathlib import Path
from typing import cast
from unittest import mock

import library
from tests.fixture import TempLibrary, open_database

STAMP = "20261028-153045"
TABLES = ("asset", "container", "container_asset")


def _sha256(path: Path) -> str:
    """Return the SHA-256 hex digest of a file.

    Args:
        path: File to read.

    Returns:
        The digest of the file bytes.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rows(path: Path, table: str) -> list[tuple[object, ...]]:
    """Return every row of one table, ordered by id.

    Args:
        path: SQLite database file.
        table: ``asset``, ``container``, or ``container_asset``.

    Returns:
        The rows. The connection is closed before this returns.
    """
    with open_database(path) as conn:
        return list(conn.execute(f"SELECT * FROM {table} ORDER BY id"))


def _change_counter(path: Path) -> int:
    """Return the SQLite file change counter at header offset 24.

    Args:
        path: Database file.

    Returns:
        The big-endian counter.
    """
    return int.from_bytes(path.read_bytes()[24:28], "big")


def _freeze_clock():
    """Patch the backup clock to one second.

    Returns:
        A patch of ``library.time.strftime`` that always reports ``STAMP``.
    """
    return mock.patch("library.time.strftime", return_value=STAMP)


class BackupTests(unittest.TestCase):
    """Claim a unique backup folder and check the copied databases."""

    def test_two_backups_in_the_same_second(self) -> None:
        """Take two backups while the clock stays on one second.

        The stamp is patched, so the result does not depend on the host
        clock. The second folder uses the ``-02`` suffix.

        Returns:
            None. The test fails if the second call raises or reuses the folder.
        """
        with TempLibrary() as temp:
            with _freeze_clock():
                first = library.ensure_backup()
                library._backed_up.clear()
                second = library.ensure_backup()
            self.assertIsInstance(first, Path)
            self.assertIsInstance(second, Path)
            first_folder = cast(Path, first)
            second_folder = cast(Path, second)
            self.assertNotEqual(first_folder, second_folder)
            self.assertTrue((first_folder / "master.sqlite").is_file())
            self.assertTrue((second_folder / "master.sqlite").is_file())
            self.assertEqual(first_folder.name, f"serato-web-{STAMP}")
            self.assertEqual(second_folder.name, f"serato-web-{STAMP}-02")
            parent = temp.db.resolve().parent / "Backups"
            self.assertEqual(
                sorted(path.name for path in parent.iterdir()),
                [first_folder.name, second_folder.name],
            )

    def test_backup_matches_source_rows_and_bytes(self) -> None:
        """Restore the copied databases and compare them to the source.

        The master fixture gains one container-asset row. ``root.sqlite``
        is a sibling database with different rows in the same three tables.
        Each copied file must match its source by SHA-256, and the asset,
        container, and container-asset tables must match row for row.

        Returns:
            None. The test fails if a table or a file digest differs.
        """
        with TempLibrary() as temp:
            with open_database(temp.db) as conn:
                conn.execute(
                    """
                    INSERT INTO container_asset
                        (id, asset_id, container_id, list_order)
                    VALUES (9, 1, 1, 42)
                    """
                )
            root = temp.db.parent / "root.sqlite"
            with open_database(root) as conn:
                conn.executescript(
                    """
                    CREATE TABLE asset (id INTEGER PRIMARY KEY, name TEXT);
                    CREATE TABLE container (id INTEGER PRIMARY KEY, name TEXT);
                    CREATE TABLE container_asset (
                        id INTEGER PRIMARY KEY,
                        asset_id INTEGER,
                        list_order INTEGER
                    );
                    INSERT INTO asset (id, name) VALUES (5, 'Location track');
                    INSERT INTO container (id, name) VALUES (6, 'Drive crate');
                    INSERT INTO container_asset (id, asset_id, list_order)
                    VALUES (7, 5, 3);
                    """
                )
            sources = {"master.sqlite": temp.db, "root.sqlite": root}
            for path in sources.values():
                for table in TABLES:
                    self.assertGreater(len(_rows(path, table)), 0)
            self.assertNotEqual(_rows(temp.db, "asset"), _rows(root, "asset"))
            digests = {name: _sha256(path) for name, path in sources.items()}
            folder = library.ensure_backup()
            self.assertIsInstance(folder, Path)
            backup = cast(Path, folder)
            copied = sorted(path.name for path in backup.iterdir() if path.is_file())
            self.assertEqual(copied, ["master.sqlite", "root.sqlite"])
            for name, source in sources.items():
                self.assertEqual(_sha256(backup / name), digests[name])
                self.assertEqual(_sha256(source), digests[name])
                for table in TABLES:
                    self.assertEqual(_rows(backup / name, table), _rows(source, table))

    def test_suffixes_sort_in_creation_order(self) -> None:
        """Fill suffixes through ``-09`` and check that ``-10`` sorts after it.

        Ten backups share one patched second. A plain ``sorted`` of the
        folder paths and of their names follows the order they were created.

        Returns:
            None. The test fails if ``-10`` is created before ``-09`` or
            sorts ahead of it.
        """
        with TempLibrary():
            created: list[Path] = []
            with _freeze_clock():
                for _ in range(10):
                    library._backed_up.clear()
                    folder = library.ensure_backup()
                    self.assertIsInstance(folder, Path)
                    created.append(cast(Path, folder))
            names = [path.name for path in created]
            self.assertEqual(
                names,
                [f"serato-web-{STAMP}"]
                + [f"serato-web-{STAMP}-{suffix:02d}" for suffix in range(2, 11)],
            )
            self.assertEqual(names[-2], f"serato-web-{STAMP}-09")
            self.assertEqual(names[-1], f"serato-web-{STAMP}-10")
            self.assertEqual(sorted(names), names)
            self.assertEqual(sorted(created), created)

    def test_exhausted_suffixes_copy_nothing(self) -> None:
        """Raise a clear error when ``-02`` through ``-99`` are already taken.

        Every candidate folder is created empty before the call. The error
        is raised before a database file is copied, and the source file is
        left unchanged.

        Returns:
            None. The test fails if a copy appears or the error text is vague.
        """
        with TempLibrary() as temp:
            parent = temp.db.resolve().parent / "Backups"
            names = [f"serato-web-{STAMP}"]
            names.extend(
                f"serato-web-{STAMP}-{suffix:02d}" for suffix in range(2, 100)
            )
            for name in names:
                (parent / name).mkdir(parents=True)
            digest = _sha256(temp.db)
            with _freeze_clock():
                with self.assertRaises(FileExistsError) as caught:
                    library.ensure_backup()
            message = str(caught.exception)
            self.assertIn("Nothing was copied", message)
            self.assertIn(f"{STAMP}-99", message)
            self.assertEqual(
                sorted(path.name for path in parent.iterdir()),
                sorted(names),
            )
            for name in names:
                self.assertEqual(list((parent / name).iterdir()), [])
            self.assertEqual(_sha256(temp.db), digest)
            self.assertNotIn(str(temp.db.resolve()), library._backed_up)

    def test_failed_root_copy_removes_the_folder(self) -> None:
        """Remove the claimed folder when the location database copy fails.

        The master copy runs. The root copy raises ``OSError`` 28. No
        ``serato-web-`` folder remains. A sibling of ``Backups`` is left
        in place, and neither source file is deleted.

        Returns:
            None. The test fails if the error is swallowed or a backup folder remains.
        """
        with TempLibrary() as temp:
            library_dir = temp.db.resolve().parent
            root = library_dir / "root.sqlite"
            root.write_bytes(b"location")
            extra = library_dir / "Backups-extra"
            extra.mkdir()
            (extra / "keep.txt").write_text("keep")
            digest = _sha256(temp.db)
            real = library._backup_database

            def copy_master_only(source: Path, dest: Path) -> None:
                if Path(source).name == "root.sqlite":
                    raise OSError(28, "No space left on device")
                real(source, dest)

            with mock.patch.object(library, "_backup_database", side_effect=copy_master_only):
                with self.assertRaises(OSError) as caught:
                    library.ensure_backup()
            self.assertEqual(caught.exception.errno, 28)
            self.assertEqual(list(library_dir.glob("Backups/serato-web-*")), [])
            self.assertEqual((extra / "keep.txt").read_text(), "keep")
            self.assertEqual(root.read_bytes(), b"location")
            self.assertEqual(_sha256(temp.db), digest)
            self.assertTrue(temp.db.is_file())
            self.assertNotIn(str(temp.db.resolve()), library._backed_up)

    def test_failed_backup_cleanup_leaves_a_symlink(self) -> None:
        """Do not follow a backup-shaped symlink out of ``Backups``.

        Returns:
            None. The test fails if the link target is removed. Skipped when
            this host cannot create a directory symlink.
        """
        with TempLibrary() as temp:
            library_dir = temp.db.resolve().parent
            backups = library_dir / "Backups"
            backups.mkdir()
            outside = library_dir / "outside"
            outside.mkdir()
            (outside / "keep.txt").write_text("keep")
            link = backups / "serato-web-link"
            try:
                link.symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest("symlinks are not available")
            library._discard_failed_backup(link, backups)
            self.assertTrue(link.is_symlink())
            self.assertEqual((outside / "keep.txt").read_text(), "keep")

    def test_wal_snapshot_keeps_uncheckpointed_rows(self) -> None:
        """Include a location-database row that exists only in the WAL.

        Auto-checkpoint is off and the writer stays open, so the main file
        does not contain the second asset. The backup must. The backup API
        resets the file change counter; that counter stays reset while the
        WAL sidecar exists.

        Returns:
            None. The test fails if the uncheckpointed row is missing.
        """
        with TempLibrary() as temp:
            root = temp.db.resolve().parent / "root.sqlite"
            conn = sqlite3.connect(root)
            try:
                mode = conn.execute("PRAGMA journal_mode=WAL").fetchone()
                self.assertIsNotNone(mode)
                self.assertEqual(mode[0], "wal")
                conn.execute("PRAGMA wal_autocheckpoint=0").fetchone()
                conn.executescript(
                    """
                    CREATE TABLE asset (id INTEGER PRIMARY KEY, name TEXT);
                    CREATE TABLE container (id INTEGER PRIMARY KEY, name TEXT);
                    CREATE TABLE container_asset (
                        id INTEGER PRIMARY KEY,
                        asset_id INTEGER
                    );
                    INSERT INTO asset (id, name) VALUES (1, 'checkpointed');
                    INSERT INTO container (id, name) VALUES (1, 'crate');
                    INSERT INTO container_asset (id, asset_id) VALUES (1, 1);
                    """
                )
                conn.commit()
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
                conn.execute(
                    "INSERT INTO asset (id, name) VALUES (2, 'only-in-wal')"
                )
                conn.commit()
                wal = Path(str(root) + "-wal")
                self.assertTrue(wal.is_file())
                self.assertGreater(wal.stat().st_size, 0)
                self.assertGreater(_change_counter(root), 1)
                folder = library.ensure_backup()
                self.assertIsInstance(folder, Path)
                backup = cast(Path, folder)
                with open_database(backup / "root.sqlite") as copied:
                    names = [
                        row[0]
                        for row in copied.execute("SELECT name FROM asset ORDER BY id")
                    ]
                self.assertNotEqual(
                    _change_counter(backup / "root.sqlite"),
                    _change_counter(root),
                )
            finally:
                conn.close()
        self.assertEqual(names, ["checkpointed", "only-in-wal"])
