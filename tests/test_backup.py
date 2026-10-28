"""Backup folder names and a restore that matches the source."""

from __future__ import annotations

import ctypes
import hashlib
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import cast
from unittest import mock

import app_log
import files
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
            self.assertEqual(copied, [library.BACKUP_COMPLETE_NAME, "master.sqlite", "root.sqlite"])
            self.assertTrue(library.is_complete(backup))
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

    def test_cleanup_lock_keeps_the_original_error(self) -> None:
        """Keep the copy error when removing the folder is itself locked.

        The copy raises ``OSError`` 28. Removing the folder raises
        ``PermissionError``. ``ensure_backup`` must raise that same
        ``OSError`` 28, and the log must name the folder that could not
        be removed.

        Returns:
            None. The test fails if the lock error replaces the copy error
            or the warning omits the folder path.
        """
        with TempLibrary() as temp:
            disk_full = OSError(28, "No space left on device")
            folder = temp.db.resolve().parent / "Backups" / f"serato-web-{STAMP}"
            with _freeze_clock():
                with mock.patch.object(library, "_backup_database", side_effect=disk_full):
                    with mock.patch(
                        "library.shutil.rmtree",
                        side_effect=PermissionError(13, "Access is denied"),
                    ):
                        with self.assertLogs(app_log.LOGGER_NAME, level="WARNING") as recorded:
                            with self.assertRaises(OSError) as caught:
                                library.ensure_backup()
            self.assertIs(caught.exception, disk_full)
            self.assertEqual(caught.exception.errno, 28)
            self.assertIsNone(caught.exception.__cause__)
            self.assertIsNone(caught.exception.__context__)
            self.assertNotIsInstance(caught.exception, PermissionError)
            logged = "\n".join(recorded.output)
            self.assertIn(STAMP, logged)
            self.assertIn(".partial", logged)

    def test_double_failure_leaves_only_a_hidden_partial(self) -> None:
        """Keep a failed copy out of the restore list when cleanup also fails.

        The root copy raises ``OSError`` 28 after ``master.sqlite`` is in
        the staging directory. Renaming that directory fails, and writing
        ``INCOMPLETE`` fails too. The leftover keeps the ``.partial`` name.
        It is not complete and no listing offers it.

        Returns:
            None. The test fails if a ``serato-web-`` folder is offered.
        """
        with TempLibrary() as temp:
            parent = temp.db.resolve().parent / "Backups"
            good = parent / "serato-web-20200101-000000"
            good.mkdir(parents=True)
            (good / "master.sqlite").write_bytes(b"complete")
            library._write_complete_marker(good)
            root = temp.db.resolve().parent / "root.sqlite"
            root.write_bytes(b"location")
            real = library._backup_database
            real_rename = Path.rename
            real_write = Path.write_text

            def copy_master_only(source: Path, dest: Path) -> None:
                if Path(source).name == "root.sqlite":
                    raise OSError(28, "No space left on device")
                real(source, dest)

            def refuse_rename(self: Path, target: Path) -> Path:
                if "serato-web-" in self.name.lower():
                    raise OSError(13, "Access is denied")
                return real_rename(self, target)

            def refuse_marker(self: Path, data: str, *args: object, **kwargs: object) -> int:
                if self.name == library.BACKUP_INCOMPLETE_NAME:
                    raise OSError(13, "Access is denied")
                return real_write(self, data, *args, **kwargs)

            with mock.patch.object(library, "_backup_database", side_effect=copy_master_only):
                with mock.patch.object(Path, "rename", refuse_rename):
                    with mock.patch.object(Path, "write_text", refuse_marker):
                        with self.assertRaises(OSError) as caught:
                            library.ensure_backup()
            self.assertEqual(caught.exception.errno, 28)
            self.assertNotIsInstance(caught.exception, PermissionError)
            leftovers = [path for path in parent.iterdir() if path.is_dir() and path != good]
            self.assertEqual(len(leftovers), 1)
            leftover = leftovers[0]
            self.assertTrue(library._is_staging_name(leftover.name))
            self.assertTrue((leftover / "master.sqlite").is_file())
            self.assertFalse((leftover / "root.sqlite").exists())
            self.assertFalse((leftover / library.BACKUP_COMPLETE_NAME).exists())
            self.assertFalse((leftover / library.BACKUP_INCOMPLETE_NAME).exists())
            self.assertFalse(library.is_complete(leftover))
            self.assertEqual(library.backup_status(leftover), "incomplete")
            self.assertEqual(library.list_backups(parent), [good])
            names = [item["name"] for item in files.list_directory(str(parent))["entries"]]
            self.assertNotIn(leftover.name, names)
            self.assertIn(good.name, names)

    def test_partial_leftover_is_removed_on_the_next_run(self) -> None:
        """Ignore a crash before publish, and remove it once it is stale.

        A ``.partial`` directory left before ``os.replace`` is not listed.
        A fresh one survives the next backup. One whose newest mtime is
        older than an hour, and whose lock is free, is removed.

        Returns:
            None. The test fails if a fresh staging directory is deleted
            or a stale one is kept.
        """
        with TempLibrary() as temp:
            parent = temp.db.resolve().parent / "Backups"
            parent.mkdir()
            fresh = parent / ".serato-web-29990101-000000.partial"
            fresh.mkdir()
            (fresh / "master.sqlite").write_bytes(b"live")
            stale = parent / ".serato-web-crash.partial"
            stale.mkdir()
            (stale / "master.sqlite").write_bytes(b"half")
            old = time.time() - library.PARTIAL_STALE_SECONDS - 5
            os.utime(stale, (old, old))
            os.utime(stale / "master.sqlite", (old, old))
            self.assertFalse(library.is_complete(fresh))
            self.assertFalse(library.is_complete(stale))
            self.assertEqual(library.list_backups(parent), [])
            names = [item["name"] for item in files.list_directory(str(parent))["entries"]]
            self.assertNotIn(fresh.name, names)
            self.assertNotIn(stale.name, names)
            library.MASTER = temp.db
            library._backed_up.clear()
            folder = library.ensure_backup()
            self.assertIsInstance(folder, Path)
            self.assertTrue(fresh.is_dir())
            self.assertEqual((fresh / "master.sqlite").read_bytes(), b"live")
            self.assertFalse(stale.exists())
            self.assertTrue(library.is_complete(cast(Path, folder)))

    def test_locked_partial_survives_another_backup(self) -> None:
        """Leave a staging directory alone while another process holds its lock.

        The directory is old enough to be stale. The lock is what keeps it.

        Returns:
            None. The test fails if the locked directory is removed.
        """
        with TempLibrary() as temp:
            parent = temp.db.resolve().parent / "Backups"
            parent.mkdir()
            live = parent / ".serato-web-locked.partial"
            live.mkdir()
            (live / "master.sqlite").write_bytes(b"live")
            lock_path = live / library.PARTIAL_LOCK_NAME
            script = (
                "import os, sys, time\n"
                "fd = os.open(sys.argv[1], os.O_CREAT | os.O_RDWR, 0o644)\n"
                "if os.name == 'nt':\n"
                "    import msvcrt\n"
                "    os.write(fd, b'\\0')\n"
                "    os.lseek(fd, 0, os.SEEK_SET)\n"
                "    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)\n"
                "else:\n"
                "    import fcntl\n"
                "    fcntl.flock(fd, fcntl.LOCK_EX)\n"
                "sys.stdout.write('ready\\n')\n"
                "sys.stdout.flush()\n"
                "time.sleep(30)\n"
            )
            proc = subprocess.Popen(
                [sys.executable, "-c", script, str(lock_path)],
                stdout=subprocess.PIPE,
                text=True,
            )
            try:
                ready = proc.stdout.readline() if proc.stdout is not None else ""
                self.assertEqual(ready.strip(), "ready")
                old = time.time() - library.PARTIAL_STALE_SECONDS - 5
                os.utime(live, (old, old))
                os.utime(live / "master.sqlite", (old, old))
                os.utime(lock_path, (old, old))
                library.MASTER = temp.db
                library._backed_up.clear()
                library.ensure_backup()
                self.assertEqual((live / "master.sqlite").read_bytes(), b"live")
            finally:
                proc.kill()
                proc.wait(timeout=5)
                if proc.stdout is not None:
                    proc.stdout.close()

    def test_complete_marker_rejects_bad_contents(self) -> None:
        """Reject an extra file, a missing file, a bad marker, and a path escape.

        Returns:
            None. The test fails if any of those folders is complete.
        """
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)

            extra = root / "extra"
            extra.mkdir()
            (extra / "master.sqlite").write_bytes(b"db")
            library._write_complete_marker(extra)
            (extra / "notes.txt").write_bytes(b"more")
            self.assertFalse(library.is_complete(extra))

            missing = root / "missing"
            missing.mkdir()
            (missing / "master.sqlite").write_bytes(b"db")
            (missing / "root.sqlite").write_bytes(b"root")
            library._write_complete_marker(missing)
            (missing / "root.sqlite").unlink()
            self.assertFalse(library.is_complete(missing))

            malformed = root / "malformed"
            malformed.mkdir()
            (malformed / "master.sqlite").write_bytes(b"db")
            (malformed / library.BACKUP_COMPLETE_NAME).write_text("not-a-hash\n", encoding="utf-8")
            self.assertFalse(library.is_complete(malformed))

            escape = root / "escape"
            escape.mkdir()
            (escape / "master.sqlite").write_bytes(b"db")
            digest = hashlib.sha256(b"db").hexdigest()
            (escape / library.BACKUP_COMPLETE_NAME).write_text(
                f"{digest}  ../master.sqlite\n",
                encoding="utf-8",
            )
            self.assertFalse(library.is_complete(escape))

    def test_wal_legacy_backup_is_left_unchanged(self) -> None:
        """Check a WAL legacy backup without writing ``-shm`` beside it.

        Returns:
            None. The test fails if the backup bytes change or ``-shm`` appears.
        """
        from contextlib import closing

        with TempLibrary() as temp:
            parent = temp.db.resolve().parent / "Backups"
            parent.mkdir()
            legacy = parent / "serato-web-20180101-000000"
            legacy.mkdir()
            source = parent / "wal-source.sqlite"
            with closing(sqlite3.connect(source)) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA wal_autocheckpoint=0")
                conn.execute("CREATE TABLE asset (id INTEGER PRIMARY KEY)")
                conn.execute("INSERT INTO asset VALUES (1)")
                conn.commit()
                (legacy / "master.sqlite").write_bytes(source.read_bytes())
                wal = Path(str(source) + "-wal")
                self.assertGreater(wal.stat().st_size, 0)
                (legacy / "master.sqlite-wal").write_bytes(wal.read_bytes())
            source.unlink()
            before = {
                path.name: path.read_bytes()
                for path in legacy.iterdir()
                if path.is_file()
            }
            self.assertNotIn("master.sqlite-shm", before)
            self.assertEqual(library.backup_status(legacy), library.LEGACY_BACKUP_STATUS)
            library.verify_legacy_backup(legacy)
            after = {
                path.name: path.read_bytes()
                for path in legacy.iterdir()
                if path.is_file()
            }
            self.assertEqual(after, before)
            self.assertFalse((legacy / "master.sqlite-shm").exists())
            self.assertFalse(library.is_complete(legacy))

    def test_tampered_backup_fails_hash_verification(self) -> None:
        """Reject a backup whose file no longer matches COMPLETE.

        Returns:
            None. The test fails if the tampered folder is still complete.
        """
        with TempLibrary() as temp:
            folder = library.ensure_backup()
            self.assertIsInstance(folder, Path)
            backup = cast(Path, folder)
            self.assertTrue(library.is_complete(backup))
            master = backup / "master.sqlite"
            data = bytearray(master.read_bytes())
            data[-1] ^= 0xFF
            master.write_bytes(data)
            self.assertFalse(library.is_complete(backup))
            self.assertEqual(library.list_backups(backup.parent), [])

    def test_legacy_backup_is_unverified_until_checked(self) -> None:
        """Leave an unmarked backup off the restore list until it is checked.

        A folder with ``master.sqlite`` and no COMPLETE marker is
        ``legacy, unverified``. A corrupt database is refused.
        ``PRAGMA integrity_check`` must be exactly ``ok`` before a healthy
        one can be restored. Neither one is :func:`library.is_complete`.

        Returns:
            None. The test fails if a legacy folder is listed as complete
            or a corrupt database is accepted.
        """
        with TempLibrary() as temp:
            parent = temp.db.resolve().parent / "Backups"
            parent.mkdir()
            legacy = parent / "serato-web-20190101-000000"
            legacy.mkdir()
            healthy = legacy / "master.sqlite"
            with open_database(healthy) as conn:
                conn.execute("CREATE TABLE asset (id INTEGER PRIMARY KEY, name TEXT)")
                conn.execute("INSERT INTO asset VALUES (1, 'kept')")
            corrupt = parent / "serato-web-20190101-000001"
            corrupt.mkdir()
            broken = corrupt / "master.sqlite"
            broken.write_bytes(healthy.read_bytes())
            data = bytearray(broken.read_bytes())
            data[100] ^= 0xFF
            broken.write_bytes(data)
            self.assertEqual(library.backup_status(legacy), library.LEGACY_BACKUP_STATUS)
            self.assertEqual(library.backup_status(corrupt), library.LEGACY_BACKUP_STATUS)
            self.assertFalse(library.is_complete(legacy))
            self.assertFalse(library.is_complete(corrupt))
            self.assertEqual(library.list_backups(parent), [])
            library.verify_legacy_backup(legacy)
            with self.assertRaises(library.LibraryError) as caught:
                library.verify_legacy_backup(corrupt)
            self.assertIn("not restored", str(caught.exception))

    def test_failed_rename_uses_the_next_suffix(self) -> None:
        """Use ``-failed-02`` when ``-failed`` is already taken.

        Returns:
            None. The test fails if the collision overwrites the first name
            or the second name is offered as a restore.
        """
        with TempLibrary() as temp:
            parent = temp.db.resolve().parent / "Backups"
            taken = parent / f".serato-web-{STAMP}.partial-failed"
            taken.mkdir(parents=True)
            (taken / "keep.txt").write_text("keep", encoding="utf-8")
            root = temp.db.resolve().parent / "root.sqlite"
            root.write_bytes(b"location")
            real = library._backup_database

            def copy_master_only(source: Path, dest: Path) -> None:
                if Path(source).name == "root.sqlite":
                    raise OSError(28, "No space left on device")
                real(source, dest)

            with _freeze_clock():
                with mock.patch.object(library, "_backup_database", side_effect=copy_master_only):
                    with mock.patch(
                        "library.shutil.rmtree",
                        side_effect=PermissionError(13, "Access is denied"),
                    ):
                        with self.assertRaises(OSError):
                            library.ensure_backup()
            second = parent / f".serato-web-{STAMP}.partial-failed-02"
            self.assertTrue(second.is_dir())
            self.assertEqual((taken / "keep.txt").read_text(encoding="utf-8"), "keep")
            self.assertFalse(library.is_complete(taken))
            self.assertFalse(library.is_complete(second))
            self.assertEqual(library.list_backups(parent), [])
            uppercase = parent / "serato-web-old-FAILED"
            uppercase.mkdir()
            (uppercase / "master.sqlite").write_bytes(b"old")
            library._write_complete_marker(uppercase)
            self.assertFalse(library.is_complete(uppercase))
            mixed = parent / "serato-web-old-Failed"
            mixed.mkdir()
            (mixed / "master.sqlite").write_bytes(b"old")
            library._write_complete_marker(mixed)
            self.assertFalse(library.is_complete(mixed))

    def test_is_complete_verifies_a_snapshot_store_anywhere(self) -> None:
        """Require a verified COMPLETE marker in any directory.

        A snapshot store outside ``Library/Backups`` is complete only after
        its COMPLETE marker matches every file. A missing marker, a
        ``-failed`` name, and ``INCOMPLETE`` are not complete.

        Returns:
            None. The test fails if the parent path decides the result.
        """
        with tempfile.TemporaryDirectory() as raw:
            app_data = Path(raw) / "Serato Library"
            store = app_data / "snapshots"
            (store / "manifests").mkdir(parents=True)
            (store / "objects").mkdir()
            (store / "manifests" / "one.json").write_text("{}\n", encoding="utf-8")
            half = app_data / "half-store"
            (half / "objects").mkdir(parents=True)
            (half / "objects" / "blob").write_bytes(b"blob")
            failed = app_data / "snapshots-FAILED"
            (failed / "manifests").mkdir(parents=True)
            (failed / "objects").mkdir()
            (failed / "manifests" / "one.json").write_text("{}\n", encoding="utf-8")
            library._write_complete_marker(failed)
            marked = app_data / "marked-store"
            (marked / "manifests").mkdir(parents=True)
            (marked / "objects").mkdir()
            (marked / "manifests" / "one.json").write_text("{}\n", encoding="utf-8")
            library._write_complete_marker(marked)
            (marked / library.BACKUP_INCOMPLETE_NAME).write_text("incomplete\n", encoding="utf-8")
            self.assertFalse(library.is_complete(store))
            library._write_complete_marker(store)
            self.assertTrue(library.is_complete(store))
            self.assertFalse(library.is_complete(half))
            self.assertFalse(library.is_complete(failed))
            self.assertFalse(library.is_complete(marked))
        with TempLibrary() as temp:
            parent = temp.db.resolve().parent / "Backups"
            good = parent / "serato-web-20200101-000000"
            good.mkdir(parents=True)
            (good / "master.sqlite").write_bytes(b"complete")
            library._write_complete_marker(good)
            snapshots = parent / "snapshots"
            (snapshots / "manifests").mkdir(parents=True)
            (snapshots / "objects").mkdir()
            (snapshots / "manifests" / "one.json").write_text("{}\n", encoding="utf-8")
            library._write_complete_marker(snapshots)
            self.assertTrue(library.is_complete(snapshots))
            self.assertEqual(library.list_backups(parent), [good, snapshots])
            names = [item["name"] for item in files.list_directory(str(parent))["entries"]]
            self.assertIn(good.name, names)
            self.assertIn(snapshots.name, names)

    def test_partial_delete_is_not_offered(self) -> None:
        """Leave a locked delete under a name restore will not offer.

        The master database is copied, so the folder would look finished.
        Deleting it raises ``PermissionError`` after the rename. The
        leftover name ends with ``-failed``. ``list_backups`` and the file
        browser omit it, and a finished folder beside it is still listed.

        Returns:
            None. The test fails if the copy error changes or the leftover
            is offered as a restore.
        """
        with TempLibrary() as temp:
            parent = temp.db.resolve().parent / "Backups"
            good = parent / "serato-web-20200101-000000"
            good.mkdir(parents=True)
            (good / "master.sqlite").write_bytes(b"complete")
            library._write_complete_marker(good)
            root = temp.db.resolve().parent / "root.sqlite"
            root.write_bytes(b"location")
            digest = _sha256(temp.db)
            real = library._backup_database

            def copy_master_only(source: Path, dest: Path) -> None:
                if Path(source).name == "root.sqlite":
                    raise OSError(28, "No space left on device")
                real(source, dest)

            journal = parent / "file-ops-journal.json"
            journal.write_text("{}", encoding="utf-8")
            with mock.patch.object(library, "_backup_database", side_effect=copy_master_only):
                with mock.patch(
                    "library.shutil.rmtree",
                    side_effect=PermissionError(13, "Access is denied"),
                ):
                    with self.assertLogs(app_log.LOGGER_NAME, level="WARNING") as recorded:
                        with self.assertRaises(OSError) as caught:
                            library.ensure_backup()
            self.assertEqual(caught.exception.errno, 28)
            self.assertNotIsInstance(caught.exception, PermissionError)
            renamed = [
                path for path in parent.iterdir() if path.name.endswith(library.BACKUP_FAILED_SUFFIX)
            ]
            self.assertEqual(len(renamed), 1)
            leftover = renamed[0]
            self.assertTrue((leftover / "master.sqlite").is_file())
            self.assertFalse(library.is_complete(leftover))
            self.assertTrue(library.is_complete(good))
            self.assertEqual(library.list_backups(parent), [good])
            names = [item["name"] for item in files.list_directory(str(parent))["entries"]]
            self.assertIn(good.name, names)
            self.assertNotIn(leftover.name, names)
            self.assertIn(journal.name, names)
            self.assertIn(str(leftover), "\n".join(recorded.output))
            self.assertEqual(_sha256(temp.db), digest)
            self.assertEqual(root.read_bytes(), b"location")

    def test_rename_failure_writes_incomplete_marker(self) -> None:
        """Write ``INCOMPLETE`` when the failed folder cannot be renamed.

        The copied ``master.sqlite`` would otherwise look safe to restore.
        The marker makes :func:`library.is_complete` false, and listings
        omit the folder. The copy error is still ``OSError`` 28.

        Returns:
            None. The test fails if the marker is missing or the folder is offered.
        """
        with TempLibrary() as temp:
            parent = temp.db.resolve().parent / "Backups"
            good = parent / "serato-web-20200101-000000"
            good.mkdir(parents=True)
            (good / "master.sqlite").write_bytes(b"complete")
            library._write_complete_marker(good)
            root = temp.db.resolve().parent / "root.sqlite"
            root.write_bytes(b"location")
            real = library._backup_database
            real_rename = Path.rename

            def copy_master_only(source: Path, dest: Path) -> None:
                if Path(source).name == "root.sqlite":
                    raise OSError(28, "No space left on device")
                real(source, dest)

            def refuse_failed_rename(self: Path, target: Path) -> Path:
                if "serato-web-" in self.name.lower():
                    raise OSError(13, "Access is denied")
                return real_rename(self, target)

            with mock.patch.object(library, "_backup_database", side_effect=copy_master_only):
                with mock.patch.object(Path, "rename", refuse_failed_rename):
                    with self.assertLogs(app_log.LOGGER_NAME, level="WARNING") as recorded:
                        with self.assertRaises(OSError) as caught:
                            library.ensure_backup()
            self.assertEqual(caught.exception.errno, 28)
            self.assertNotIsInstance(caught.exception, PermissionError)
            folders = [path for path in parent.iterdir() if path.is_dir() and path != good]
            self.assertEqual(len(folders), 1)
            leftover = folders[0]
            self.assertFalse(leftover.name.endswith(library.BACKUP_FAILED_SUFFIX))
            self.assertTrue((leftover / library.BACKUP_INCOMPLETE_NAME).is_file())
            self.assertTrue((leftover / "master.sqlite").is_file())
            self.assertFalse(library.is_complete(leftover))
            self.assertEqual(library.list_backups(parent), [good])
            names = [item["name"] for item in files.list_directory(str(parent))["entries"]]
            self.assertIn(good.name, names)
            self.assertNotIn(leftover.name, names)
            self.assertIn(str(leftover), "\n".join(recorded.output))

    @unittest.skipUnless(sys.platform == "win32", "needs a Windows file lock")
    def test_windows_lock_is_not_a_complete_backup(self) -> None:
        """Hold the copied database open so Windows refuses the cleanup.

        The leftover must not be offered. It is either renamed to end with
        ``-failed`` or marked ``INCOMPLETE``. The copy error stays
        ``OSError`` 28.

        Returns:
            None. The test fails if a locked folder is listed as complete.
        """
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateFileW.restype = ctypes.c_void_p
        kernel32.CreateFileW.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
        ]
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        invalid = ctypes.c_void_p(-1).value
        handle: int | None = None
        with TempLibrary() as temp:
            root = temp.db.resolve().parent / "root.sqlite"
            root.write_bytes(b"location")
            real = library._backup_database

            def lock_master(source: Path, dest: Path) -> None:
                nonlocal handle
                if Path(source).name == "root.sqlite":
                    master = Path(dest).parent / "master.sqlite"
                    handle = kernel32.CreateFileW(
                        str(master),
                        0x80000000,
                        0,
                        None,
                        3,
                        0x80,
                        None,
                    )
                    if handle in (None, 0, invalid):
                        raise OSError(ctypes.get_last_error(), "CreateFileW")
                    raise OSError(28, "No space left on device")
                real(source, dest)

            try:
                with mock.patch.object(library, "_backup_database", side_effect=lock_master):
                    with self.assertRaises(OSError) as caught:
                        library.ensure_backup()
                self.assertEqual(caught.exception.errno, 28)
                parent = temp.db.resolve().parent / "Backups"
                leftovers = [path for path in parent.iterdir() if path.is_dir()]
                self.assertTrue(leftovers)
                for item in leftovers:
                    marked = (
                        library._is_failed_name(item.name)
                        or library._is_staging_name(item.name)
                        or (item / library.BACKUP_INCOMPLETE_NAME).exists()
                    )
                    self.assertTrue(marked)
                    self.assertFalse(library.is_complete(item))
                self.assertEqual(library.list_backups(parent), [])
            finally:
                if handle not in (None, 0, invalid):
                    kernel32.CloseHandle(handle)

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
