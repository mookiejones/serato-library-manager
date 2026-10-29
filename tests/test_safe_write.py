"""Safe-write checks against temporary libraries.

The cases build a database with ``tests.fixture``. They do not open a live
Serato library. Faults stand in for a bad commit, a crash, and a full disk.
"""

from __future__ import annotations

import json
import os
import plistlib
import sqlite3
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import library
import safe_write
import snapshots
from library import LibraryError
from safe_write import Fault, InjectedCrash, VerifyMismatch
from serato_web.completeness import is_complete
from tests.fixture import TempLibrary


def _drive_crate(root: Path) -> Path:
    """Create one external ``_Serato_`` crate under a temporary library.

    Args:
        root: Temporary library directory. On this runner that is under ``/tmp``.

    Returns:
        The crate file.
    """
    crate = root / "drive" / "_Serato_" / "Subcrates" / "House.crate"
    crate.parent.mkdir(parents=True)
    crate.write_bytes(b"house-crate-v1")
    return crate


def _snapshot(*paths: Path) -> dict[str, bytes]:
    """Read the bytes the rollback has to restore.

    Args:
        paths: Files to remember.

    Returns:
        Path text to contents. A missing file is an empty value with a marker.
    """
    found: dict[str, bytes] = {}
    for path in paths:
        found[str(path)] = path.read_bytes() if path.is_file() else b""
    return found


def _wal(db: Path) -> Path:
    """Return the WAL sidecar path.

    Args:
        db: Database file.

    Returns:
        ``db`` plus ``-wal``.
    """
    return Path(str(db) + "-wal")


def _journal(db: Path) -> Path:
    """Return the write journal in the app data folder.

    Args:
        db: Database file. The journal is not stored beside it.

    Returns:
        ``write-journal.json`` under the write-check directory for ``db``.
    """
    return safe_write.store_dir(db) / "write-journal.json"


def _tree(root: Path) -> set[str]:
    """List every relative path in a library folder.

    Args:
        root: Serato library directory.

    Returns:
        POSIX paths of every file and directory under ``root``, plus nothing
        for a missing directory. The names are what a write is allowed to
        leave unchanged.
    """
    if not root.is_dir():
        return set()
    return {path.relative_to(root).as_posix() for path in root.rglob("*")}


@contextmanager
def _serato_version(root: Path, version: str, build: str) -> Iterator[None]:
    """Point version detection at a plist in the temporary library.

    Args:
        root: Directory that receives the plist.
        version: ``CFBundleShortVersionString``.
        build: ``CFBundleVersion``.

    Yields:
        None. The previous environment value is restored afterwards.
    """
    info = root / "Info.plist"
    with info.open("wb") as handle:
        plistlib.dump(
            {"CFBundleShortVersionString": version, "CFBundleVersion": build},
            handle,
        )
    previous = os.environ.get("SERATO_LIBRARY_APP_INFO")
    os.environ["SERATO_LIBRARY_APP_INFO"] = str(info)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("SERATO_LIBRARY_APP_INFO", None)
        else:
            os.environ["SERATO_LIBRARY_APP_INFO"] = previous


def _immutable_name(db: Path, asset_id: int) -> str | None:
    """Read one asset name without the WAL file.

    Args:
        db: Database file. It is not opened except as an immutable copy URI.
        asset_id: Asset id.

    Returns:
        The name, or None when that id is not in the main file.
    """
    conn = sqlite3.connect(library._read_only_uri(db, "mode=ro&immutable=1"), uri=True)
    try:
        row = conn.execute("SELECT name FROM asset WHERE id = ?", (asset_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return str(row[0])


def _rename(conn: sqlite3.Connection, session: safe_write.Session, crate: Path) -> None:
    """Rename one track and require the crate file to stay as it was.

    Args:
        conn: Open write connection.
        session: Session that records the check.
        crate: Crate file that this write does not edit.
    """
    conn.execute("UPDATE asset SET name = ? WHERE id = 1", ("Renamed",))

    def check(copied: sqlite3.Connection) -> None:
        """Fail when the copied row is not the name this write asked for.

        Args:
            copied: Read-only connection to the temporary database copy.

        Raises:
            VerifyMismatch: If the name is not ``Renamed``.
        """
        row = copied.execute("SELECT name FROM asset WHERE id = 1").fetchone()
        if row is None or row[0] != "Renamed":
            raise VerifyMismatch("The track name does not match.")

    session.check(check)
    session.expect_unchanged(crate)
    session.set_target("Renamed")


def _corrupt(db: Path, crate: Path) -> None:
    """Change the committed row and the crate file.

    Args:
        db: Database to rewrite. The connection is closed before return.
        crate: Crate file to flip.
    """
    conn = sqlite3.connect(db)
    try:
        flag = getattr(sqlite3, "SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE", None)
        if flag is not None:
            conn.setconfig(flag, True)
        conn.execute("PRAGMA wal_autocheckpoint=0")
        conn.execute("UPDATE asset SET name = ? WHERE id = 1", ("Corrupt",))
        conn.commit()
    finally:
        conn.close()
    data = bytearray(crate.read_bytes())
    data[-1] ^= 0xFF
    crate.write_bytes(bytes(data))


class SafeWriteTests(unittest.TestCase):
    """Verify, roll back, and refuse library writes on temporary databases."""

    def test_verified_write_records_the_crate_name(self) -> None:
        """Save a crate and record one verified result.

        Returns:
            None. The test fails if the crate is missing or the record is not verified.
        """
        with TempLibrary() as temp:
            crate = _drive_crate(temp.root)
            created = library.crate_action({"action": "create", "name": "Warmup"})
            record = safe_write.results(temp.db)[-1]
            blob = json.dumps(record.to_dict())
            images = safe_write.store_dir(temp.db) / "write-images"
            finished = [path for path in images.iterdir() if path.is_dir() and is_complete(path)]
            self.assertEqual(created["name"], "Warmup")
            self.assertEqual(record.operation, "crate_create")
            self.assertEqual(record.target, "Warmup")
            self.assertEqual(record.result, "verified")
            self.assertEqual(record.rollback, "not_needed")
            self.assertIsNotNone(record.snapshot_id)
            self.assertIn("master.sqlite", record.files)
            self.assertNotIn(str(temp.root), blob)
            self.assertTrue(finished)
            self.assertFalse(str(images.resolve()).startswith(str(temp.db.resolve().parent)))
            self.assertEqual(crate.read_bytes(), b"house-crate-v1")
            self.assertFalse(_journal(temp.db).exists())
            self.assertFalse((temp.db.parent / "Backups").exists())

    def test_successful_write_adds_nothing_in_the_serato_folder(self) -> None:
        """Leave the library folder's names unchanged after a crate is saved.

        The preimage, journal, and operation log are in the app data folder.
        They must not show up beside ``master.sqlite``.

        Returns:
            None. The test fails if ``Backups``, a snapshot directory, a
            journal, or ``operations.jsonl`` appears.
        """
        with TempLibrary() as temp:
            before = _tree(temp.root)
            library.crate_action({"action": "create", "name": "Warmup"})
            after = _tree(temp.root)
            self.assertEqual(after, before)
            self.assertFalse((temp.root / "Backups").exists())
            self.assertNotIn("operations.jsonl", after)
            self.assertNotIn("write-journal.json", after)
            self.assertTrue((safe_write.store_dir(temp.db) / "operations.jsonl").is_file())
            self.assertFalse(str(safe_write.store_dir(temp.db)).startswith(str(temp.root.resolve())))

    def test_rollback_adds_nothing_in_the_serato_folder(self) -> None:
        """Leave the library folder's names unchanged when a write is put back.

        Returns:
            None. The test fails if a new file remains beside the database
            or the crate bytes are not the pre-write bytes.
        """
        with TempLibrary() as temp:
            crate = _drive_crate(temp.root)
            before_names = _tree(temp.root)
            before_bytes = _snapshot(temp.db, crate)

            def apply(conn: sqlite3.Connection, session: safe_write.Session) -> None:
                _rename(conn, session, crate)

            with self.assertRaises(LibraryError):
                safe_write.run(
                    "rename_track",
                    "Renamed",
                    apply,
                    extra_files=(crate,),
                    fault=Fault(after_commit=lambda: _corrupt(temp.db, crate)),
                )
            self.assertEqual(_tree(temp.root), before_names)
            self.assertEqual(_snapshot(temp.db, crate), before_bytes)
            self.assertFalse((temp.root / "Backups").exists())
            self.assertFalse(any(name.endswith("operations.jsonl") or name.endswith("write-journal.json") for name in before_names))
            self.assertTrue((safe_write.store_dir(temp.db) / "operations.jsonl").is_file())

    def test_mismatched_write_restores_the_database_and_crate(self) -> None:
        """Roll a corrupt commit back to the pre-write bytes.

        Returns:
            None. The test fails if the database or the crate file differs.
        """
        with TempLibrary() as temp:
            crate = _drive_crate(temp.root)
            before = _snapshot(temp.db, crate)

            def apply(conn: sqlite3.Connection, session: safe_write.Session) -> None:
                _rename(conn, session, crate)

            with self.assertRaises(LibraryError) as caught:
                safe_write.run(
                    "rename_track",
                    "Renamed",
                    apply,
                    extra_files=(crate,),
                    fault=Fault(after_commit=lambda: _corrupt(temp.db, crate)),
                )
            after = _snapshot(temp.db, crate)
            record = safe_write.results(temp.db)[-1]
            self.assertEqual(after, before)
            self.assertIn("put back", caught.exception.message)
            self.assertEqual(record.result, "rolled_back")
            self.assertEqual(record.rollback, "verified")
            self.assertEqual(record.target, "Renamed")
            self.assertIn("drive/_Serato_/Subcrates/House.crate", record.files)
            self.assertFalse(_journal(temp.db).exists())

    def test_crash_recovers_from_the_journal(self) -> None:
        """Leave the journal when the process dies, then put the bytes back.

        Returns:
            None. The test fails if recovery does not match the pre-write files.
        """
        with TempLibrary() as temp:
            crate = _drive_crate(temp.root)
            before = _snapshot(temp.db, crate, _wal(temp.db))

            def apply(conn: sqlite3.Connection, session: safe_write.Session) -> None:
                _rename(conn, session, crate)

            with self.assertRaises(InjectedCrash):
                safe_write.run(
                    "rename_track",
                    "Renamed",
                    apply,
                    extra_files=(crate,),
                    fault=Fault(after_commit=lambda: _corrupt(temp.db, crate), crash=True),
                )
            self.assertTrue(_journal(temp.db).is_file())
            self.assertNotEqual(_snapshot(temp.db, crate), before)
            self.assertTrue(safe_write.recover_interrupted_write())
            restored = _snapshot(temp.db, crate, _wal(temp.db))
            self.assertEqual(restored, before)
            self.assertFalse(_journal(temp.db).exists())

    def test_disk_full_refuses_the_write(self) -> None:
        """Refuse the write when the preimage cannot be stored.

        Returns:
            None. The test fails if the database changes or a journal is left.
        """
        with TempLibrary() as temp:
            crate = _drive_crate(temp.root)
            before = _snapshot(temp.db, crate)
            called = {"apply": False}

            def apply(conn: sqlite3.Connection, session: safe_write.Session) -> None:
                called["apply"] = True
                _rename(conn, session, crate)

            with self.assertRaises(LibraryError) as caught:
                safe_write.run(
                    "rename_track",
                    "Renamed",
                    apply,
                    extra_files=(crate,),
                    fault=Fault(disk_full=True),
                )
            partials = list(safe_write.store_dir(temp.db).rglob("*.partial")) if safe_write.store_dir(temp.db).exists() else []
            record = safe_write.results(temp.db)[-1]
            self.assertIn("nothing was written", caught.exception.message)
            self.assertFalse(called["apply"])
            self.assertEqual(_snapshot(temp.db, crate), before)
            self.assertEqual(partials, [])
            self.assertFalse(_journal(temp.db).exists())
            self.assertEqual(record.result, "refused")
            self.assertEqual(record.rollback, "not_attempted")

    def test_serato_5_write_is_refused_and_untouched(self) -> None:
        """Refuse a Serato 5 library before a snapshot or a journal.

        Returns:
            None. The test fails if the database or the crate file changes.
        """
        with TempLibrary() as temp:
            crate = _drive_crate(temp.root)
            before = _snapshot(temp.db, crate)
            with _serato_version(temp.root, "5.0.0", "5.0.0.1251"):
                with self.assertRaises(LibraryError) as caught:
                    library.crate_action({"action": "create", "name": "Warmup"})
            record = safe_write.results(temp.db)[-1]
            self.assertIn("read-only", caught.exception.message)
            self.assertEqual(_snapshot(temp.db, crate), before)
            self.assertFalse(_journal(temp.db).exists())
            self.assertFalse((temp.db.parent / "Backups").exists())
            self.assertEqual(record.result, "refused")
            self.assertEqual(record.rollback, "not_attempted")

    def test_serato_5_rollback_does_not_touch_the_library(self) -> None:
        """Leave a crashed Serato 5 library as it is.

        The crash happens on Serato 4, which is allowed to journal. The
        version is then Serato 5. Recovery must not replace a file.

        Returns:
            None. The test fails if recovery writes the database or the crate.
        """
        with TempLibrary() as temp:
            crate = _drive_crate(temp.root)
            before = _snapshot(temp.db, crate)

            def apply(conn: sqlite3.Connection, session: safe_write.Session) -> None:
                _rename(conn, session, crate)

            with self.assertRaises(InjectedCrash):
                safe_write.run(
                    "rename_track",
                    "Renamed",
                    apply,
                    extra_files=(crate,),
                    fault=Fault(after_commit=lambda: _corrupt(temp.db, crate), crash=True),
                )
            dirty = _snapshot(temp.db, crate)
            with _serato_version(temp.root, "5.0.0", "5.0.0.1251"):
                with self.assertRaises(LibraryError) as caught:
                    safe_write.recover_interrupted_write()
                during = _snapshot(temp.db, crate)
                self.assertTrue(_journal(temp.db).is_file())
            self.assertIn("read-only", caught.exception.message)
            self.assertEqual(during, dirty)
            self.assertTrue(safe_write.recover_interrupted_write())
            self.assertEqual(_snapshot(temp.db, crate), before)
            self.assertFalse(_journal(temp.db).exists())

    def test_wal_only_row_is_read_from_the_copied_sidecar(self) -> None:
        """See a row that exists only in ``-wal`` when the write is checked.

        Auto-checkpoint is off. The main file does not contain the extra
        track. The check has to copy ``-wal`` or it will not see that row,
        and it will roll the rename back.

        Returns:
            None. The test fails if the rename is undone or the WAL row disappears.
        """
        with TempLibrary() as temp:
            conn = sqlite3.connect(temp.db)
            try:
                flag = getattr(sqlite3, "SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE", None)
                if flag is None:
                    self.skipTest("This Python cannot keep a WAL file on close.")
                conn.setconfig(flag, True)
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA wal_autocheckpoint=0")
                conn.execute(
                    """
                    INSERT INTO asset (id, name, artist, length_ms, file_name, portable_id)
                    VALUES (50, 'OnlyWal', 'Artist', 1000, 'wal.mp3', 'Music/wal.mp3')
                    """
                )
                conn.execute("INSERT INTO space_asset (id, asset_id, space_id) VALUES (50, 50, 1)")
                conn.commit()
            finally:
                conn.close()
            self.assertTrue(_wal(temp.db).is_file())
            self.assertIsNone(_immutable_name(temp.db, 50))
            snapshots.snapshot_before_write()
            self.assertIsNone(_immutable_name(temp.db, 50), "the content snapshot checkpointed the WAL")

            def apply(conn: sqlite3.Connection, session: safe_write.Session) -> None:
                conn.execute("UPDATE asset SET name = ? WHERE id = 1", ("Renamed",))

                def check(copied: sqlite3.Connection) -> None:
                    """Fail when the copy is missing the rename or the WAL-only row.

                    Args:
                        copied: Read-only connection to the temporary database copy.

                    Raises:
                        VerifyMismatch: If either row is wrong. Skipping the
                            ``-wal`` copy makes this fail.
                    """
                    renamed = copied.execute("SELECT name FROM asset WHERE id = 1").fetchone()
                    only = copied.execute("SELECT name FROM asset WHERE id = 50").fetchone()
                    if renamed is None or renamed[0] != "Renamed" or only is None or only[0] != "OnlyWal":
                        raise VerifyMismatch("The copied database is missing a WAL row.")

                session.check(check)
                session.set_target("Renamed")

            safe_write.run("rename_track", "Renamed", apply)
            record = safe_write.results(temp.db)[-1]
            self.assertEqual(record.result, "verified")
            self.assertEqual(_immutable_name(temp.db, 1), "Same")
            seen = _names_with_wal(temp.db)
            self.assertEqual(seen[1], "Renamed")
            self.assertEqual(seen[50], "OnlyWal")


def _names_with_wal(db: Path) -> dict[int, str]:
    """Read asset names from a temporary copy that includes ``-wal``.

    Args:
        db: Database file. The live file is not opened.

    Returns:
        Asset id to name.
    """
    import shutil
    import tempfile

    wal = _wal(db)
    with tempfile.TemporaryDirectory(prefix="serato-wal-read-") as raw:
        root = Path(raw)
        copied = root / "master.sqlite"
        shutil.copyfile(db, copied)
        if wal.is_file() and not wal.is_symlink():
            shutil.copyfile(wal, root / "master.sqlite-wal")
        conn = sqlite3.connect(library._read_only_uri(copied, "mode=ro"), uri=True)
        try:
            rows = conn.execute("SELECT id, name FROM asset").fetchall()
        finally:
            conn.close()
    return {int(row[0]): str(row[1]) for row in rows}


if __name__ == "__main__":
    unittest.main()
