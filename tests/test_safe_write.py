"""Safe-write checks against temporary libraries.

The cases build a database with ``tests.fixture``. They do not open a live
Serato library. Faults stand in for a bad commit, a crash, and a full disk.
"""

from __future__ import annotations

import json
import os
import plistlib
import sqlite3
import tempfile
import unittest
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from unittest import mock

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
def _serato_version(
    root: Path, version: str, build: str, *, protect: str | None = None
) -> Iterator[None]:
    """Point version detection at a plist in the temporary library.

    Args:
        root: Directory that receives the plist.
        version: ``CFBundleShortVersionString``.
        build: ``CFBundleVersion``.
        protect: ``on`` or ``off`` writes ``library_protect``. None leaves
            Protect Library unread.

    Yields:
        None. The previous environment value is restored afterwards.
    """
    info = root / "Info.plist"
    with info.open("wb") as handle:
        plistlib.dump(
            {"CFBundleShortVersionString": version, "CFBundleVersion": build},
            handle,
        )
    previous_info = os.environ.get("CRATECRAFT_APP_INFO")
    previous_prefs = os.environ.get("CRATECRAFT_PREFERENCES")
    os.environ["CRATECRAFT_APP_INFO"] = str(info)
    if protect is not None:
        prefs = root / "com.serato.seratodj.plist"
        with prefs.open("wb") as handle:
            plistlib.dump({"library_protect": 1 if protect == "on" else 0}, handle)
        os.environ["CRATECRAFT_PREFERENCES"] = str(prefs)
    try:
        yield
    finally:
        if previous_info is None:
            os.environ.pop("CRATECRAFT_APP_INFO", None)
        else:
            os.environ["CRATECRAFT_APP_INFO"] = previous_info
        if previous_prefs is None:
            os.environ.pop("CRATECRAFT_PREFERENCES", None)
        else:
            os.environ["CRATECRAFT_PREFERENCES"] = previous_prefs


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
            lines = safe_write.read_log(temp.db)
            self.assertEqual(len(lines), 1)
            self.assertIs(lines[0]["verified"], True)
            self.assertIs(lines[0]["rolled_back"], False)
            self.assertEqual(lines[0]["action"], "crate_create")
            self.assertEqual(lines[0]["snapshot_before"], record.snapshot_id)
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
            self.assertEqual(_hash_file(temp.db), record.hashes["master.sqlite"])
            entry = safe_write.read_log(temp.db)[-1]
            self.assertIs(entry["verified"], False)
            self.assertIs(entry["rolled_back"], True)
            self.assertEqual(entry["result"], "rolled_back")
            self.assertEqual(record.target, "Renamed")
            self.assertIn("drive/_Serato_/Subcrates/House.crate", record.files)
            self.assertFalse(_journal(temp.db).exists())

    def test_rollback_restores_when_master_is_the_live_file(self) -> None:
        """Put the live library back when MASTER and LIVE_MASTER are the same file.

        Tests usually point MASTER at a temp file while LIVE_MASTER stays
        the real Serato path, so dests never sit inside the live folder.
        On a real launch both names are that live file. Rollback must
        compare file to file, or dests inside the live folder are refused.

        Returns:
            None. The test fails if restore is refused or the bytes differ.
        """
        with TempLibrary() as temp:
            crate = _drive_crate(temp.root)
            before = _snapshot(temp.db, crate)

            def apply(conn: sqlite3.Connection, session: safe_write.Session) -> None:
                _rename(conn, session, crate)

            with mock.patch("library.LIVE_MASTER", str(temp.db)):
                with mock.patch("snapshots.write_block_message", return_value=None):
                    with self.assertRaises(LibraryError) as caught:
                        safe_write.run(
                            "rename_track",
                            "Renamed",
                            apply,
                            extra_files=(crate,),
                            fault=Fault(after_commit=lambda: _corrupt(temp.db, crate)),
                        )
            after = _snapshot(temp.db, crate)
            self.assertEqual(after, before)
            self.assertIn("put back", caught.exception.message)
            self.assertNotIn("outside the library", caught.exception.message)
            self.assertFalse(_journal(temp.db).exists())

    def test_recovery_clears_a_leftover_journal_when_master_is_the_live_file(self) -> None:
        """Recover a leftover journal on the live library, then write again.

        A refused restore used to leave write-journal.json. The next write
        then hit recover first and raised the same refuse. After the
        file-to-file comparison, recover restores and later writes run.

        Returns:
            None. The test fails if recover refuses or the later write is blocked.
        """
        with TempLibrary() as temp:
            crate = _drive_crate(temp.root)
            before = _snapshot(temp.db, crate, _wal(temp.db))

            def apply(conn: sqlite3.Connection, session: safe_write.Session) -> None:
                _rename(conn, session, crate)

            with mock.patch("library.LIVE_MASTER", str(temp.db)):
                with mock.patch("snapshots.write_block_message", return_value=None):
                    with self.assertRaises(InjectedCrash):
                        safe_write.run(
                            "rename_track",
                            "Renamed",
                            apply,
                            extra_files=(crate,),
                            fault=Fault(crash=True),
                        )
                    self.assertTrue(_journal(temp.db).is_file())
                    self.assertTrue(safe_write.recover_interrupted_write())
                    self.assertEqual(_snapshot(temp.db, crate, _wal(temp.db)), before)
                    self.assertFalse(_journal(temp.db).exists())
                    created = library.crate_action({"action": "create", "name": "Warmup"})
            self.assertEqual(created["name"], "Warmup")
            self.assertFalse(_journal(temp.db).exists())

    def test_testing_refuses_to_restore_a_file_under_the_live_library_folder(self) -> None:
        """Keep dests inside the real live folder off-limits while tests run.

        MASTER is the temp library. LIVE_MASTER is a different file. A
        crate that happens to sit under that live folder must not be
        overwritten on rollback.

        Returns:
            None. The test fails if the live-folder dest is rewritten.
        """
        with TempLibrary() as temp:
            crate = _drive_crate(temp.root)
            with tempfile.TemporaryDirectory() as live_root:
                live_dir = Path(live_root)
                live_master = live_dir / "master.sqlite"
                live_master.write_bytes(b"live-master")
                victim = live_dir / "Keep.crate"
                victim.write_bytes(b"do-not-touch")

                def apply(conn: sqlite3.Connection, session: safe_write.Session) -> None:
                    _rename(conn, session, crate)

                def dirty() -> None:
                    _corrupt(temp.db, crate)
                    victim.write_bytes(b"changed")

                with mock.patch("library.LIVE_MASTER", str(live_master)):
                    with self.assertLogs("serato", level="ERROR") as logged:
                        with self.assertRaises(LibraryError) as caught:
                            safe_write.run(
                                "rename_track",
                                "Renamed",
                                apply,
                                extra_files=(crate, victim),
                                fault=Fault(after_commit=dirty),
                            )
                self.assertEqual(caught.exception.code, "restore_outside")
                self.assertEqual(caught.exception.params, {"name": "Keep.crate"})
                self.assertIn("Keep.crate", caught.exception.message)
                self.assertIn("local log", caught.exception.message)
                self.assertIn("Backups", caught.exception.message)
                self.assertNotIn(str(live_dir), caught.exception.message)
                self.assertTrue(any(str(victim) in line for line in logged.output))
                self.assertEqual(victim.read_bytes(), b"changed")
                self.assertTrue(_journal(temp.db).is_file())

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

    def test_recovery_leaves_a_library_changed_after_the_crash(self) -> None:
        """Do not roll back over changes made after the interrupted write.

        The app stops mid-write. Serato DJ then runs a session (it renames
        the track and writes a new crate file) and quits. When the app
        starts again, putting the pre-write bytes back would erase that
        session. Recovery must leave the library and the new crate alone,
        clear the journal so later writes are not blocked, and record that
        the rollback was refused.

        Returns:
            None. The test fails if Serato's later changes are overwritten.
        """
        with TempLibrary() as temp:
            crate = _drive_crate(temp.root)

            def apply(conn: sqlite3.Connection, session: safe_write.Session) -> None:
                _rename(conn, session, crate)

            with self.assertRaises(InjectedCrash):
                safe_write.run(
                    "rename_track",
                    "Renamed",
                    apply,
                    extra_files=(crate,),
                    fault=Fault(crash=True),
                )
            self.assertTrue(_journal(temp.db).is_file())
            gig = sqlite3.connect(temp.db)
            try:
                gig.execute("UPDATE asset SET name = ? WHERE id = 1", ("Played at the gig",))
                gig.commit()
            finally:
                gig.close()
            data = bytearray(crate.read_bytes())
            data[-1] ^= 0xFF
            crate.write_bytes(bytes(data))
            after_gig = _snapshot(temp.db, crate, _wal(temp.db))

            self.assertFalse(safe_write.recover_interrupted_write())

            self.assertEqual(_snapshot(temp.db, crate, _wal(temp.db)), after_gig)
            self.assertFalse(_journal(temp.db).exists())
            last = safe_write.read_log(temp.db)[-1]
            self.assertEqual(last["result"], "rollback_failed")
            self.assertEqual(last["rollback"], "refused")

    def test_recovery_restores_when_only_this_write_changed_the_library(self) -> None:
        """Roll back after a crash when nothing else touched the files.

        The write committed and the process stopped before its check. No
        other program changed the library, so recovery puts the pre-write
        bytes back as before.

        Returns:
            None. The test fails if the rollback is skipped.
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
                    fault=Fault(crash=True),
                )
            self.assertNotEqual(_snapshot(temp.db, crate, _wal(temp.db)), before)
            self.assertTrue(safe_write.recover_interrupted_write())
            self.assertEqual(_snapshot(temp.db, crate, _wal(temp.db)), before)
            self.assertFalse(_journal(temp.db).exists())

    def test_recovery_ignores_a_shm_index_rewritten_by_a_read(self) -> None:
        """Roll back in WAL mode after the app's own status read.

        Serato's library runs in WAL mode. On the next launch the app reads
        ``status()`` before the snapshot store recovers, and that read
        rewrites ``master.sqlite-shm``. That index holds no library data, so
        it must not make recovery think another program changed the library.

        Returns:
            None. The test fails if the rollback is skipped.
        """
        with TempLibrary() as temp:
            with closing(sqlite3.connect(temp.db)) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
            crate = _drive_crate(temp.root)
            shm = Path(str(temp.db) + "-shm")
            before = _snapshot(temp.db, crate)
            name_before = _names_with_wal(temp.db)[1]

            def apply(conn: sqlite3.Connection, session: safe_write.Session) -> None:
                _rename(conn, session, crate)

            with self.assertRaises(InjectedCrash):
                safe_write.run(
                    "rename_track",
                    "Renamed",
                    apply,
                    extra_files=(crate,),
                    fault=Fault(crash=True),
                )
            shm_after_crash = shm.read_bytes()
            with mock.patch("snapshots.serato_dj_running", return_value=False):
                library.status()
            self.assertNotEqual(shm.read_bytes(), shm_after_crash)
            self.assertEqual(_names_with_wal(temp.db)[1], "Renamed")
            self.assertTrue(safe_write.recover_interrupted_write())
            self.assertEqual(_names_with_wal(temp.db)[1], name_before)
            self.assertEqual(_snapshot(temp.db, crate), before)

    def test_read_only_store_open_leaves_an_unfinished_write(self) -> None:
        """Do not roll back a write when the store is opened read-only.

        The gig check opens ``SnapshotStore(master, recover=False)`` and
        promises not to write. An unfinished write's journal must survive
        that open, and the library must keep the committed bytes. A normal
        open still recovers.

        Returns:
            None. The test fails if a read-only open changes the library.
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
                    fault=Fault(crash=True),
                )
            committed = _snapshot(temp.db, crate, _wal(temp.db))
            with mock.patch("snapshots.serato_dj_running", return_value=False):
                snapshots.SnapshotStore(temp.db, recover=False)
            self.assertEqual(_snapshot(temp.db, crate, _wal(temp.db)), committed)
            self.assertTrue(_journal(temp.db).is_file())
            with mock.patch("snapshots.serato_dj_running", return_value=False):
                snapshots.SnapshotStore(temp.db)
            self.assertEqual(_snapshot(temp.db, crate, _wal(temp.db)), before)
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

        Protect Library unread is unknown, so the write stays off.

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
            self.assertIn("Protect Library is unknown", caught.exception.message)
            self.assertEqual(_snapshot(temp.db, crate), before)
            self.assertFalse(_journal(temp.db).exists())
            self.assertFalse((temp.db.parent / "Backups").exists())
            self.assertEqual(record.result, "refused")
            self.assertEqual(record.rollback, "not_attempted")

    def test_serato_5_write_is_verified_when_protect_is_off(self) -> None:
        """Save a crate and a drive crate on Serato 5 when Protect is off.

        Returns:
            None. The test fails if the crate is missing or the record is not
            verified.
        """
        with TempLibrary() as temp:
            crate = _drive_crate(temp.root)
            with _serato_version(temp.root, "5.0.0", "5.0.0.1251", protect="off"):
                created = library.crate_action({"action": "create", "name": "Warmup"})

                def apply(conn: sqlite3.Connection, session: safe_write.Session) -> None:
                    conn.execute("UPDATE asset SET name = ? WHERE id = 1", ("Renamed",))

                    def check(copied: sqlite3.Connection) -> None:
                        row = copied.execute("SELECT name FROM asset WHERE id = 1").fetchone()
                        if row is None or row[0] != "Renamed":
                            raise VerifyMismatch("The track name does not match.")

                    session.check(check)
                    crate.write_bytes(b"house-crate-v2")

                safe_write.run("rename_track", "Renamed", apply, extra_files=(crate,))
            records = safe_write.results(temp.db)
            self.assertEqual(created["name"], "Warmup")
            self.assertEqual(records[0].result, "verified")
            self.assertEqual(records[1].result, "verified")
            self.assertEqual(records[1].rollback, "not_needed")
            self.assertEqual(crate.read_bytes(), b"house-crate-v2")
            with closing(sqlite3.connect(temp.db)) as conn:
                name = conn.execute("SELECT name FROM asset WHERE id = 1").fetchone()
            self.assertEqual(name[0], "Renamed")
            self.assertFalse(_journal(temp.db).exists())

    def test_serato_5_mismatch_rolls_back_when_protect_is_off(self) -> None:
        """Put the Serato 5 library back when the post-write check fails.

        Returns:
            None. The test fails if the database or crate stays corrupted.
        """
        with TempLibrary() as temp:
            crate = _drive_crate(temp.root)
            before = _snapshot(temp.db, crate)

            def apply(conn: sqlite3.Connection, session: safe_write.Session) -> None:
                _rename(conn, session, crate)

            with _serato_version(temp.root, "5.0.0", "5.0.0.1251", protect="off"):
                with self.assertRaises(LibraryError) as caught:
                    safe_write.run(
                        "rename_track",
                        "Renamed",
                        apply,
                        extra_files=(crate,),
                        fault=Fault(after_commit=lambda: _corrupt(temp.db, crate)),
                    )
            record = safe_write.results(temp.db)[-1]
            self.assertIn("put back", caught.exception.message)
            self.assertEqual(_snapshot(temp.db, crate), before)
            self.assertEqual(record.result, "rolled_back")
            self.assertEqual(record.rollback, "verified")
            self.assertFalse(_journal(temp.db).exists())

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
            self.assertIn("Protect Library is unknown", caught.exception.message)
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

    def test_crate_rename_corruption_matches_the_preimage(self) -> None:
        """Roll a renamed crate back when the committed row is changed.

        The bytes after the failure match the pre-write snapshot, including
        the database hash stored for that snapshot.

        Returns:
            None. The test fails if the new name remains or the hash differs.
        """
        with TempLibrary() as temp:
            created = library.crate_action({"action": "create", "name": "Warmup"})
            crate_id = int(created["id"])
            before = _snapshot(temp.db, _wal(temp.db))

            def corrupt() -> None:
                conn = sqlite3.connect(temp.db)
                try:
                    flag = getattr(sqlite3, "SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE", None)
                    if flag is not None:
                        conn.setconfig(flag, True)
                    conn.execute("PRAGMA wal_autocheckpoint=0")
                    conn.execute("UPDATE container SET name = ? WHERE id = ?", ("Corrupt", crate_id))
                    conn.commit()
                finally:
                    conn.close()

            safe_write.install_fault(Fault(after_commit=corrupt))
            with self.assertRaises(LibraryError) as caught:
                library.crate_action({"action": "rename", "id": crate_id, "name": "Evening"})
            record = safe_write.results(temp.db)[-1]
            self.assertIn("put back", caught.exception.message)
            self.assertEqual(_snapshot(temp.db, _wal(temp.db)), before)
            self.assertEqual(_hash_file(temp.db), record.hashes["master.sqlite"])
            self.assertEqual(record.result, "rolled_back")
            self.assertFalse(_journal(temp.db).exists())
            conn = library.read_conn()
            try:
                row = conn.execute("SELECT name FROM container WHERE id = ?", (crate_id,)).fetchone()
            finally:
                conn.close()
            self.assertIsNotNone(row)
            assert row is not None
            self.assertNotEqual(row[0], "Evening")
            self.assertNotEqual(row[0], "Corrupt")

    def test_crate_color_corruption_rolls_back(self) -> None:
        """Roll a crate color back when the committed color is changed.

        Returns:
            None. The test fails if the color check is skipped and the
            corrupted color remains.
        """
        with TempLibrary() as temp:
            created = library.crate_action({"action": "create", "name": "Warmup"})
            crate_id = int(created["id"])

            def corrupt() -> None:
                conn = sqlite3.connect(temp.db)
                try:
                    flag = getattr(sqlite3, "SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE", None)
                    if flag is not None:
                        conn.setconfig(flag, True)
                    conn.execute("PRAGMA wal_autocheckpoint=0")
                    conn.execute("UPDATE container SET color = 1 WHERE id = ?", (crate_id,))
                    conn.commit()
                finally:
                    conn.close()

            safe_write.install_fault(Fault(after_commit=corrupt))
            with self.assertRaises(LibraryError):
                library.crate_action({"action": "color", "id": crate_id, "color": 255})
            conn = library.read_conn()
            try:
                row = conn.execute("SELECT color FROM container WHERE id = ?", (crate_id,)).fetchone()
            finally:
                conn.close()
            self.assertIsNotNone(row)
            assert row is not None
            self.assertIsNone(row[0])
            entry = safe_write.read_log(temp.db)[-1]
            self.assertEqual(entry["action"], "crate_color")
            self.assertIs(entry["verified"], False)
            self.assertIs(entry["rolled_back"], True)
            self.assertFalse(_journal(temp.db).exists())

    def test_crate_expanded_corruption_rolls_back(self) -> None:
        """Roll an expanded flag back when the committed value is changed.

        Returns:
            None. The test fails if the expanded check is skipped.
        """
        with TempLibrary() as temp:
            created = library.crate_action({"action": "create", "name": "Warmup"})
            crate_id = int(created["id"])

            def corrupt() -> None:
                conn = sqlite3.connect(temp.db)
                try:
                    flag = getattr(sqlite3, "SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE", None)
                    if flag is not None:
                        conn.setconfig(flag, True)
                    conn.execute("PRAGMA wal_autocheckpoint=0")
                    conn.execute("UPDATE container SET expanded = 2 WHERE id = ?", (crate_id,))
                    conn.commit()
                finally:
                    conn.close()

            safe_write.install_fault(Fault(after_commit=corrupt))
            with self.assertRaises(LibraryError):
                library.crate_action({"action": "expanded", "id": crate_id, "expanded": True})
            conn = library.read_conn()
            try:
                row = conn.execute("SELECT expanded FROM container WHERE id = ?", (crate_id,)).fetchone()
            finally:
                conn.close()
            self.assertIsNotNone(row)
            assert row is not None
            self.assertEqual(int(row[0]), 0)
            entry = safe_write.read_log(temp.db)[-1]
            self.assertEqual(entry["action"], "crate_expanded")
            self.assertIs(entry["rolled_back"], True)
            self.assertIs(entry["verified"], False)

    def test_smart_crate_rules_corruption_rolls_back(self) -> None:
        """Roll smart-crate rules back when the committed JSON is changed.

        Returns:
            None. The test fails if the rules check is skipped.
        """
        with TempLibrary() as temp:
            rules = {"conjunction": "AND", "live_updates": True, "rules": [], "spaces": ["Serato Library"]}
            created = library.crate_action({"action": "create", "name": "Smart", "smart": True, "rules": rules})
            crate_id = int(created["id"])
            conn = library.read_conn()
            try:
                before = conn.execute(
                    "SELECT rules FROM smart_crate_rules WHERE container_id = ?",
                    (crate_id,),
                ).fetchone()
            finally:
                conn.close()
            self.assertIsNotNone(before)
            assert before is not None
            original = str(before[0])

            def corrupt() -> None:
                conn = sqlite3.connect(temp.db)
                try:
                    flag = getattr(sqlite3, "SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE", None)
                    if flag is not None:
                        conn.setconfig(flag, True)
                    conn.execute("PRAGMA wal_autocheckpoint=0")
                    conn.execute(
                        "UPDATE smart_crate_rules SET rules = ? WHERE container_id = ?",
                        ('{"rules":["corrupt"]}', crate_id),
                    )
                    conn.commit()
                finally:
                    conn.close()

            replacement = {"conjunction": "OR", "live_update": True, "rules": [], "spaces": ["Serato Library"]}
            safe_write.install_fault(Fault(after_commit=corrupt))
            with self.assertRaises(LibraryError):
                library.crate_action({"action": "rules", "id": crate_id, "rules": replacement})
            conn = library.read_conn()
            try:
                row = conn.execute(
                    "SELECT rules FROM smart_crate_rules WHERE container_id = ?",
                    (crate_id,),
                ).fetchone()
            finally:
                conn.close()
            self.assertIsNotNone(row)
            assert row is not None
            self.assertEqual(str(row[0]), original)
            entry = safe_write.read_log(temp.db)[-1]
            self.assertEqual(entry["action"], "crate_rules")
            self.assertIs(entry["verified"], False)
            self.assertIs(entry["rolled_back"], True)

    def test_failed_rollback_is_logged_and_not_success(self) -> None:
        """Keep the journal and the failure when the preimage cannot be restored.

        Returns:
            None. The test fails if the failure is recorded as verified or
            the journal is removed.
        """
        with TempLibrary() as temp:
            def break_preimage() -> None:
                images = safe_write.store_dir(temp.db) / "write-images"
                copies = [path for path in images.glob("*/master.sqlite") if path.is_file()]
                self.assertTrue(copies)
                copies[0].write_bytes(b"broken-preimage")
                conn = sqlite3.connect(temp.db)
                try:
                    flag = getattr(sqlite3, "SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE", None)
                    if flag is not None:
                        conn.setconfig(flag, True)
                    conn.execute("PRAGMA wal_autocheckpoint=0")
                    conn.execute("UPDATE container SET name = 'Corrupt' WHERE type = 1")
                    conn.commit()
                finally:
                    conn.close()

            safe_write.install_fault(Fault(after_commit=break_preimage))
            with self.assertRaises(LibraryError) as caught:
                library.crate_action({"action": "create", "name": "Warmup"})
            self.assertIn("does not match its hash", caught.exception.message)
            self.assertNotIn("verified", caught.exception.message)
            entry = safe_write.read_log(temp.db)[-1]
            self.assertEqual(entry["result"], "rollback_failed")
            self.assertIs(entry["verified"], False)
            self.assertIs(entry["rolled_back"], False)
            self.assertTrue(_journal(temp.db).is_file())


def _hash_file(path: Path) -> str:
    """Return the SHA-256 hex digest of one file.

    Args:
        path: File to read.

    Returns:
        The lowercase hex digest.
    """
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


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
