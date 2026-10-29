"""Verify a library write and put it back when the check fails.

Every write snapshots the database and the affected files first, using the
content-addressed snapshot in ``snapshots.py`` and a raw preimage marked by
``serato_web.completeness``. The write then commits. The check opens a
temporary copy of the database and any ``-wal`` file. It does not open the
live database. When the rows or file hashes do not match, or the write
raises, the preimage is copied back and those hashes are checked again.

A Serato 5 library is refused before any of that runs. Rollback uses the
same gate and does not replace a file when the gate is closed.

The operation record is one JSON object per write. The page that shows it
is a later change. This module does not build that page.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import secrets
import shutil
import sqlite3
import tempfile
from collections.abc import Callable, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar

import app_log
from serato_web.completeness import is_complete, write_complete_marker

_T = TypeVar("_T")
_STORED_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_JOURNAL_NAME = "write-journal.json"
_LOG_NAME = "operations.jsonl"
_FILES_NAME = "files.json"
_IMAGES = "write-images"
_SKIP_DEPTH = 0
_INSTALLED: Fault | None = None
_CURRENT: Session | None = None
_RESULTS: dict[str, list[WriteResult]] = {}
_RESULT_LIMIT = 200

Check = Callable[[sqlite3.Connection], None]
RollbackHook = Callable[[], None]


class VerifyMismatch(Exception):
    """Raised when a committed write does not match the rows or hashes asked for."""

    def __init__(self, message: str) -> None:
        """Store the mismatch text.

        Args:
            message: Text safe to show. It does not include a file path.
        """
        super().__init__(message)
        self.message = message


class InjectedCrash(BaseException):
    """Simulates a process death after a commit and before the check.

    Tests raise this. A normal error is an ``Exception`` and is rolled back
    in the same call. This one leaves the journal so recovery can run.
    """


@dataclass
class Fault:
    """A test seam for one write.

    Production calls leave this unset. ``disk_full`` fails the preimage
    before the library changes. ``after_commit`` runs after the commit and
    before the check. ``crash`` then leaves the journal in place.
    """

    disk_full: bool = False
    after_commit: Callable[[], None] | None = None
    crash: bool = False


@dataclass
class WriteResult:
    """One structured write record.

    ``files`` and ``hashes`` name the preimage. Paths outside the library
    folder are stored as the file name only. ``result`` is ``verified``,
    ``rolled_back``, ``refused``, or ``rollback_failed``. ``rollback`` is
    ``not_needed``, ``verified``, ``failed``, ``refused``, or ``not_attempted``.
    """

    operation: str
    target: str
    files: tuple[str, ...]
    hashes: dict[str, str]
    result: str
    rollback: str
    snapshot_id: str | None = None
    content_snapshot_id: str | None = None
    time: str = ""

    def to_dict(self) -> dict[str, object]:
        """Return the JSON object stored for this write.

        Returns:
            A dict with the stable field names. ``files`` is a list.
        """
        return {
            "version": 1,
            "time": self.time,
            "operation": self.operation,
            "target": self.target,
            "files": list(self.files),
            "hashes": dict(self.hashes),
            "result": self.result,
            "rollback": self.rollback,
            "snapshot_id": self.snapshot_id,
            "content_snapshot_id": self.content_snapshot_id,
        }


@dataclass
class _FileEntry:
    """One file inside a preimage directory."""

    stored: str
    dest: Path
    sha256: str
    label: str


@dataclass
class _Preimage:
    """A finished raw snapshot of the files a write may replace."""

    snapshot_id: str
    directory: Path
    files: list[_FileEntry] = field(default_factory=list)
    absent: list[Path] = field(default_factory=list)
    labels: dict[str, str] = field(default_factory=dict)
    hashes: dict[str, str] = field(default_factory=dict)


def holding_snapshot() -> bool:
    """Return whether a write session already took the before-write snapshot.

    Returns:
        True while a session is between its snapshot and its finish.
    """
    return _SKIP_DEPTH > 0


def current_session() -> Session | None:
    """Return the write session on this stack, if one is open.

    Returns:
        The active session, or None.
    """
    return _CURRENT


def install_fault(fault: Fault | None) -> None:
    """Install one fault for the next write session.

    Args:
        fault: Fault to consume when the next session starts. None clears it.
    """
    global _INSTALLED
    _INSTALLED = fault


def results(master: Path | None = None) -> list[WriteResult]:
    """Return the write records kept in this process for one library.

    Args:
        master: Database path. None uses the current library.

    Returns:
        Records in the order they were stored, oldest first.
    """
    import library

    key = str(Path(master or library.MASTER).resolve())
    return list(_RESULTS.get(key, ()))


def recover_interrupted_write() -> bool:
    """Put back a write that stopped after its journal was saved.

    Returns:
        True when a journal was found and the preimage was restored.
        False when there is no journal.

    Raises:
        LibraryError: If Serato 5 or a running Serato DJ blocks the
            rollback. No library file is changed. The journal stays.
        LibraryError: If the preimage cannot be restored. The journal stays.
    """
    import library

    path = _journal_path()
    if path is None or not path.is_file() or path.is_symlink():
        return False
    _refuse_rollback()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise library.LibraryError("The unfinished write could not be read.") from exc
    if not isinstance(payload, dict):
        raise library.LibraryError("The unfinished write could not be read.")
    snapshot_id = payload.get("snapshot_id")
    if not isinstance(snapshot_id, str):
        raise library.LibraryError("The unfinished write could not be read.")
    directory = _image_dir(snapshot_id)
    if directory is None:
        raise library.LibraryError("The pre-write snapshot is not in the snapshot store.")
    preimage = _load_preimage(directory, snapshot_id)
    _restore_preimage(preimage)
    _verify_preimage(preimage)
    _clear_journal()
    return True


@contextmanager
def session(
    operation: str,
    target: str,
    extra_files: Sequence[Path] = (),
    fault: Fault | None = None,
    on_rollback: RollbackHook | None = None,
):
    """Snapshot, yield, then verify or roll back.

    Args:
        operation: Short machine name, such as ``rename_crate``.
        target: Human-readable name, such as a crate name.
        extra_files: Files besides the databases to snapshot and restore.
        fault: Test fault. None uses a fault installed for this call, if any.
        on_rollback: Called when a committed write fails its check, before
            the preimage bytes are copied back. An exception from the body
            does not call it. The body already undoes its own file moves.

    Yields:
        The session. The body opens the database with ``connect``.

    Raises:
        LibraryError: If the write is refused, the check fails, or rollback fails.
        SeratoOpen: If Serato holds the library. Nothing is snapshotted.
        InjectedCrash: When a crash fault is set. The journal stays.
    """
    global _CURRENT
    chosen = fault if fault is not None else _take_fault()
    active = Session(operation, target, tuple(Path(path) for path in extra_files), chosen, on_rollback)
    previous = _CURRENT
    _CURRENT = active
    try:
        active.open()
        try:
            yield active
        except InjectedCrash:
            raise
        except Exception:
            active.finish_exception()
            raise
        else:
            active.finish_success()
    finally:
        active.close()
        _CURRENT = previous


def run(
    operation: str,
    target: str,
    apply: Callable[[sqlite3.Connection, Session], _T],
    extra_files: Sequence[Path] = (),
    fault: Fault | None = None,
) -> _T:
    """Run one database write inside a verified session.

    Args:
        operation: Short machine name.
        target: Human-readable name.
        apply: Receives the write connection and the session. It does not
            commit. It registers the row checks for the change it asked for.
        extra_files: Files to snapshot besides the databases.
        fault: Test fault.

    Returns:
        Whatever ``apply`` returns. A failed check raises instead.

    Raises:
        LibraryError: If the write is refused or rolled back.
        SeratoOpen: If Serato holds the library.
        InjectedCrash: When a crash fault is set.
    """
    with session(operation, target, extra_files, fault) as active:
        conn = active.connect()
        try:
            value = apply(conn, active)
            conn.commit()
            active.mark_committed()
            return value
        except Exception:
            try:
                conn.rollback()
            except sqlite3.Error:
                pass
            raise
        finally:
            active.close_connection()


class Session:
    """One library write from snapshot through verify."""

    def __init__(
        self,
        operation: str,
        target: str,
        extra_files: tuple[Path, ...],
        fault: Fault | None,
        on_rollback: RollbackHook | None,
    ) -> None:
        """Store the operation identity and the files to snapshot.

        Args:
            operation: Short machine name.
            target: Human-readable name. ``set_target`` can replace it.
            extra_files: Files besides the databases.
            fault: Test fault, or None.
            on_rollback: Hook for a failed check after commit.
        """
        self.operation = operation
        self.target = target
        self.extra_files = extra_files
        self.fault = fault
        self.on_rollback = on_rollback
        self.committed = False
        self._checks: list[Check] = []
        self._preimage: _Preimage | None = None
        self._content_id: str | None = None
        self._conn: sqlite3.Connection | None = None
        self._held = False
        self._journaled = False

    def set_target(self, target: str) -> None:
        """Replace the human-readable name recorded for this write.

        Args:
            target: Crate name, track name, or file name.
        """
        self.target = target

    def check(self, fn: Check) -> None:
        """Register a row check that runs on the temporary copy.

        Args:
            fn: Called with the copy. Raise ``VerifyMismatch`` when the rows
                are not the ones this write asked for.
        """
        self._checks.append(fn)

    def expect_unchanged(self, path: Path) -> None:
        """Require a snapshotted file to keep its pre-write hash.

        Args:
            path: File included in ``extra_files`` or a database sidecar.
        """
        resolved = path.resolve()

        def check(_conn: sqlite3.Connection, resolved: Path = resolved) -> None:
            preimage = self._preimage
            if preimage is None:
                raise VerifyMismatch("A file changed that this write should have left as it was.")
            wanted = next(
                (entry.sha256 for entry in preimage.files if _same_path(entry.dest, resolved)),
                None,
            )
            if wanted is None or resolved.is_symlink() or not resolved.is_file() or _hash_file(resolved) != wanted:
                raise VerifyMismatch("A file changed that this write should have left as it was.")

        self._checks.append(check)

    def connect(self) -> sqlite3.Connection:
        """Open the write transaction.

        The before-write snapshot and backup already ran.

        Returns:
            A connection inside ``BEGIN IMMEDIATE``.

        Raises:
            LibraryError: If the library cannot be written.
            SeratoOpen: If Serato holds the lock.
        """
        import library

        conn = library.begin_write()
        self._conn = conn
        return conn

    def mark_committed(self) -> None:
        """Record that the body committed the transaction."""
        self.committed = True

    def close_connection(self) -> None:
        """Close the write connection if it is still open."""
        conn = self._conn
        self._conn = None
        if conn is not None:
            conn.close()

    def open(self) -> None:
        """Refuse a blocked library, snapshot, and write the journal.

        Raises:
            LibraryError: If the snapshot cannot be saved. The library is unchanged.
            SeratoOpen: If Serato holds the library. Nothing is snapshotted.
        """
        global _SKIP_DEPTH
        import library

        self._gate()
        try:
            recover_interrupted_write()
        except library.LibraryError:
            self._record("rollback_failed", "failed")
            raise
        try:
            self._preimage = _capture(self.extra_files, self.fault)
        except OSError as exc:
            self._record("refused", "not_attempted")
            if exc.errno == errno.ENOSPC:
                raise library.LibraryError(
                    "The snapshot could not be saved, so nothing was written.",
                    409,
                ) from exc
            raise library.LibraryError(
                "The snapshot could not be saved, so nothing was written.",
                409,
            ) from exc
        try:
            self._content_id = _content_snapshot()
            library.ensure_backup()
        except Exception:
            self._record("refused", "not_attempted")
            raise
        _write_journal(self._preimage, self.operation, self.target)
        self._journaled = True
        _SKIP_DEPTH += 1
        self._held = True

    def finish_success(self) -> None:
        """Verify a committed write, or roll it back.

        Raises:
            LibraryError: If the check fails. The library matches the preimage
                when rollback's hash check passes.
            InjectedCrash: When the crash fault is set. The journal stays.
        """
        import library

        if not self.committed:
            self._restore_and_record("refused", "verified")
            raise library.LibraryError("The write did not finish, so nothing was kept.")
        try:
            if self.fault is not None and self.fault.after_commit is not None:
                self.fault.after_commit()
            if self.fault is not None and self.fault.crash:
                raise InjectedCrash()
            _verify_database(self._checks)
        except InjectedCrash:
            raise
        except Exception as exc:
            self._rollback_committed(exc)
        self._clear_owned_journal()
        self._record("verified", "not_needed")

    def finish_exception(self) -> None:
        """Put the preimage back after the body raised.

        The original error still propagates. A failed restore is recorded
        and raised ahead of that error so it is not reported as success.
        """
        import library

        if not self._journaled or self._preimage is None:
            return
        try:
            _refuse_rollback()
            _restore_preimage(self._preimage)
            _verify_preimage(self._preimage)
        except library.LibraryError as exc:
            if exc.status == 409 and _rollback_blocked():
                self._record("rollback_failed", "refused")
            else:
                self._record("rollback_failed", "failed")
            raise
        except (OSError, VerifyMismatch) as exc:
            self._record("rollback_failed", "failed")
            raise library.LibraryError(
                "The write failed, and putting the library back failed."
            ) from exc
        self._clear_owned_journal()
        outcome = "verified"
        result = "refused" if not self.committed else "rolled_back"
        self._record(result, outcome)

    def close(self) -> None:
        """Drop the snapshot hold and close a leftover connection."""
        global _SKIP_DEPTH
        self.close_connection()
        if self._held:
            _SKIP_DEPTH -= 1
            self._held = False

    def _gate(self) -> None:
        """Refuse Serato and Serato 5 before a snapshot is saved.

        Raises:
            SeratoOpen: If Serato holds the library.
            LibraryError: If the version gate refuses the library.
        """
        import library
        import snapshots

        info = library.status()
        if info["open"]:
            self._record("refused", "not_attempted")
            raise library.SeratoOpen(info)
        blocked = snapshots.write_block_message()
        if blocked:
            self._record("refused", "not_attempted")
            raise library.LibraryError(blocked, 409)

    def _rollback_committed(self, exc: Exception) -> None:
        """Run the file hook, restore the preimage, and raise.

        Args:
            exc: The check or post-commit failure.

        Raises:
            LibraryError: Always. The text says whether the library was put back.
        """
        import library

        if self.on_rollback is not None:
            try:
                self.on_rollback()
            except (OSError, library.LibraryError):
                app_log.logger.exception("The file undo before rollback failed.")
        try:
            self._restore_and_record("rolled_back", "verified")
        except library.LibraryError:
            raise
        message = "The write did not match what was asked, so the library was put back."
        if isinstance(exc, VerifyMismatch):
            message = f"{message} {exc.message}"
        raise library.LibraryError(message) from exc

    def _restore_and_record(self, result: str, rollback: str) -> None:
        """Restore the preimage and record that outcome.

        Args:
            result: Record result to store when the hash check passes.
            rollback: Rollback field to store when the hash check passes.

        Raises:
            LibraryError: If Serato 5 blocks the restore, or the hash check fails.
        """
        import library

        if self._preimage is None:
            raise library.LibraryError("The pre-write snapshot is missing.")
        try:
            _refuse_rollback()
            _restore_preimage(self._preimage)
            _verify_preimage(self._preimage)
        except library.LibraryError as exc:
            if _rollback_blocked():
                self._record("rollback_failed", "refused")
            else:
                self._record("rollback_failed", "failed")
            raise
        except (OSError, VerifyMismatch) as exc:
            self._record("rollback_failed", "failed")
            raise library.LibraryError(
                "The write did not match, and putting the library back failed."
            ) from exc
        self._clear_owned_journal()
        self._record(result, rollback)

    def _clear_owned_journal(self) -> None:
        """Remove the journal after a restore or a verified write."""
        if self._journaled:
            _clear_journal()
            self._journaled = False

    def _record(self, result: str, rollback: str) -> None:
        """Store one operation record.

        Args:
            result: ``verified``, ``rolled_back``, ``refused``, or ``rollback_failed``.
            rollback: What happened when the preimage was or was not applied.
        """
        preimage = self._preimage
        record = WriteResult(
            operation=self.operation,
            target=self.target,
            files=tuple(preimage.labels.values()) if preimage is not None else (),
            hashes=dict(preimage.hashes) if preimage is not None else {},
            result=result,
            rollback=rollback,
            snapshot_id=None if preimage is None else preimage.snapshot_id,
            content_snapshot_id=self._content_id,
            time=_now(),
        )
        _store_result(record, persist=result != "refused" or _store_exists())


def _take_fault() -> Fault | None:
    """Consume the installed fault.

    Returns:
        The fault, or None. A second call does not see the same fault.
    """
    global _INSTALLED
    fault = _INSTALLED
    _INSTALLED = None
    return fault


def _now() -> str:
    """Return the current UTC time as text.

    Returns:
        An ISO-8601 timestamp with a ``Z`` suffix.
    """
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _library_dir() -> Path:
    """Return the directory that holds the open library.

    Returns:
        The parent of ``library.MASTER``.
    """
    import library

    return Path(library.MASTER).resolve().parent


def _store_root() -> Path:
    """Return the snapshot store directory beside the library.

    Returns:
        ``Library/Backups/snapshots``.
    """
    return _library_dir() / "Backups" / "snapshots"


def _store_exists() -> bool:
    """Return whether the snapshot store directory already exists.

    Returns:
        True when that directory is already on disk. A refusal does not create it.
    """
    root = _store_root()
    return root.is_dir() and not root.is_symlink()


def _journal_path() -> Path | None:
    """Return the write journal path when it stays inside the store.

    Returns:
        The journal path, or None when the store path is not a real directory
        and creating it would be the wrong side effect for a missing library.
    """
    root = _store_root()
    path = root / _JOURNAL_NAME
    try:
        if path.is_symlink():
            return None
        resolved = path.resolve()
        base = root.resolve()
        if resolved != base and base not in resolved.parents and resolved.parent != base:
            return None
    except OSError:
        return None
    return path


def _image_dir(snapshot_id: str) -> Path | None:
    """Return one preimage directory inside the store.

    Args:
        snapshot_id: Id stored in the journal.

    Returns:
        The directory, or None when the id leaves the store.
    """
    if not _STORED_NAME.fullmatch(snapshot_id):
        return None
    root = _store_root() / _IMAGES
    path = root / snapshot_id
    try:
        if path.is_symlink():
            return None
        resolved = path.resolve()
        base = root.resolve()
        if base not in resolved.parents:
            return None
    except OSError:
        return None
    return path


def _refuse_rollback() -> None:
    """Refuse to replace library files when the version gate or Serato says no.

    Raises:
        LibraryError: If Serato 5, an unknown version, or a running Serato DJ
            process blocks the write. Nothing has been replaced yet.
    """
    import library
    import snapshots

    if snapshots.serato_dj_running():
        raise library.LibraryError(snapshots.SERATO_RUNNING_MESSAGE, 409)
    blocked = snapshots.write_block_message()
    if blocked:
        raise library.LibraryError(blocked, 409)


def _rollback_blocked() -> bool:
    """Return whether a rollback must not touch the library.

    Returns:
        True when the version gate or a running Serato DJ process refuses it.
    """
    import snapshots

    if snapshots.serato_dj_running():
        return True
    return snapshots.write_block_message() is not None


def _content_snapshot() -> str | None:
    """Save the content-addressed before-write snapshot.

    Returns:
        The new snapshot id, or None when the list does not show it.

    Raises:
        LibraryError: If the snapshot cannot be saved.
    """
    import snapshots

    store = snapshots.current_store()
    before = {str(item["id"]) for item in store.list_snapshots()}
    snapshots.snapshot_before_write()
    for item in store.list_snapshots():
        identity = str(item["id"])
        if identity not in before:
            return identity
    return None


def _capture(extra_files: Sequence[Path], fault: Fault | None) -> _Preimage:
    """Copy the databases and extra files into a completeness-marked directory.

    Args:
        extra_files: Additional files to copy.
        fault: When ``disk_full`` is set, the copy raises ``ENOSPC``.

    Returns:
        The published preimage.

    Raises:
        OSError: If a file cannot be copied or the marker cannot be written.
            A partial directory is removed.
        LibraryError: If a path is a shortcut or leaves the directory it should stay in.
    """
    import library

    library_dir = _library_dir()
    snapshot_id = secrets.token_hex(8)
    root = _store_root() / _IMAGES
    root.mkdir(parents=True, exist_ok=True)
    partial = root / f".{snapshot_id}.partial"
    if partial.exists() or partial.is_symlink():
        _remove_tree(partial)
    partial.mkdir()
    entries: list[_FileEntry] = []
    absent: list[Path] = []
    try:
        if fault is not None and fault.disk_full:
            raise OSError(errno.ENOSPC, "No space left on device")
        for path in _database_paths(library_dir, absent):
            entries.append(_copy_entry(partial, path, library_dir, path.name))
        index = 0
        for extra in extra_files:
            index += 1
            if extra.is_symlink():
                raise library.LibraryError("Refusing to snapshot a shortcut.")
            if not extra.is_file():
                absent.append(extra)
                continue
            stored = f"extra-{index:04d}"
            entries.append(_copy_entry(partial, extra, library_dir, stored))
        _write_files_json(partial, entries, absent)
        write_complete_marker(partial)
        final = root / snapshot_id
        os.replace(partial, final)
    except Exception:
        if partial.exists() or partial.is_symlink():
            _remove_tree(partial)
        raise
    if not is_complete(final):
        raise OSError("The pre-write snapshot was not finished.")
    labels = {entry.stored: entry.label for entry in entries}
    hashes = {entry.label: entry.sha256 for entry in entries}
    return _Preimage(snapshot_id, final, entries, absent, labels, hashes)


def _database_paths(library_dir: Path, absent: list[Path]) -> list[Path]:
    """List database files to copy, and sidecars that are not there yet.

    Args:
        library_dir: Directory that holds ``master.sqlite``.
        absent: Sidecars that do not exist are appended here so rollback
            can delete one a write creates.

    Returns:
        Existing database files and sidecars.

    Raises:
        LibraryError: If the master file is missing or a sidecar is a shortcut.
    """
    import library

    found: list[Path] = []
    master = library_dir / "master.sqlite"
    if master.is_symlink() or not master.is_file():
        raise library.LibraryError("The library database is not a file.")
    bases = [master]
    root = library_dir / "root.sqlite"
    if root.is_symlink():
        raise library.LibraryError("Refusing to snapshot a shortcut.")
    if root.is_file():
        bases.append(root)
    for base in bases:
        found.append(base)
        for suffix in ("-wal", "-shm", "-journal"):
            side = Path(str(base) + suffix)
            if side.is_symlink():
                raise library.LibraryError("Refusing to snapshot a database shortcut.")
            if side.is_file():
                found.append(side)
            else:
                absent.append(side)
    return found


def _copy_entry(partial: Path, source: Path, library_dir: Path, stored: str) -> _FileEntry:
    """Copy one file into the partial preimage.

    Args:
        partial: Directory that is not published yet.
        source: File to copy. A shortcut is refused.
        library_dir: Library directory, used for the record label.
        stored: Single path component inside the preimage.

    Returns:
        The entry, including the SHA-256 of the copied bytes.

    Raises:
        LibraryError: If the stored name or the source is not safe.
        OSError: If the copy cannot be written.
    """
    import library

    if not _STORED_NAME.fullmatch(stored) or stored in {"COMPLETE", "INCOMPLETE", _FILES_NAME}:
        raise library.LibraryError("A snapshot file name is not valid.")
    if source.is_symlink() or not source.is_file():
        raise library.LibraryError("Refusing to snapshot a shortcut.")
    dest = partial / stored
    if partial.resolve() not in dest.resolve().parents:
        raise library.LibraryError("A snapshot path leaves the snapshot store.")
    shutil.copyfile(source, dest)
    _fsync(dest)
    digest = _hash_file(dest)
    if digest != _hash_file(source):
        raise OSError("The snapshot copy does not match the file.")
    return _FileEntry(stored, source.resolve(), digest, _label(source, library_dir))


def _same_path(left: Path, right: Path) -> bool:
    """Return whether two paths are the same file path.

    Args:
        left: First path.
        right: Second path.

    Returns:
        True when the resolved paths match, including on a case-insensitive
        filesystem.
    """
    try:
        return os.path.normcase(str(left.resolve())) == os.path.normcase(str(right.resolve()))
    except OSError:
        return False


def _label(path: Path, library_dir: Path) -> str:
    """Return the name stored in the operation record.

    Args:
        path: File that was snapshotted.
        library_dir: Library directory.

    Returns:
        A path relative to the library directory, or the file name when the
        file lives somewhere else.
    """
    try:
        return path.resolve().relative_to(library_dir.resolve()).as_posix()
    except (OSError, ValueError):
        return path.name


def _write_files_json(partial: Path, entries: Sequence[_FileEntry], absent: Sequence[Path]) -> None:
    """Write the path map that rollback reads.

    Args:
        partial: Unpublished preimage directory.
        entries: Copied files.
        absent: Paths that did not exist and must not exist after rollback.
    """
    payload = {
        "version": 1,
        "files": [
            {"stored": entry.stored, "dest": str(entry.dest), "sha256": entry.sha256, "label": entry.label}
            for entry in entries
        ],
        "absent": [str(path) for path in absent],
    }
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    handle_path = partial / _FILES_NAME
    handle_path.write_text(text, encoding="utf-8")
    _fsync(handle_path)


def _load_preimage(directory: Path, snapshot_id: str) -> _Preimage:
    """Read a published preimage.

    Args:
        directory: Preimage directory.
        snapshot_id: Id that must match the directory name.

    Returns:
        The preimage description.

    Raises:
        LibraryError: If the directory is incomplete or the path map is not valid.
    """
    import library

    if not is_complete(directory):
        raise library.LibraryError("The pre-write snapshot is incomplete.")
    try:
        payload = json.loads((directory / _FILES_NAME).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise library.LibraryError("The pre-write snapshot could not be read.") from exc
    if not isinstance(payload, dict):
        raise library.LibraryError("The pre-write snapshot could not be read.")
    raw_files = payload.get("files")
    raw_absent = payload.get("absent")
    if not isinstance(raw_files, list) or not isinstance(raw_absent, list):
        raise library.LibraryError("The pre-write snapshot could not be read.")
    entries: list[_FileEntry] = []
    labels: dict[str, str] = {}
    hashes: dict[str, str] = {}
    for item in raw_files:
        if not isinstance(item, dict):
            raise library.LibraryError("The pre-write snapshot could not be read.")
        stored = item.get("stored")
        dest = item.get("dest")
        digest = item.get("sha256")
        label = item.get("label")
        if not isinstance(stored, str) or not isinstance(dest, str) or not isinstance(digest, str):
            raise library.LibraryError("The pre-write snapshot could not be read.")
        if not isinstance(label, str):
            label = Path(dest).name
        if not _STORED_NAME.fullmatch(stored):
            raise library.LibraryError("The pre-write snapshot could not be read.")
        stored_path = directory / stored
        if directory.resolve() not in stored_path.resolve().parents:
            raise library.LibraryError("The pre-write snapshot leaves the snapshot store.")
        if _hash_file(stored_path) != digest:
            raise library.LibraryError("The pre-write snapshot does not match its hash.")
        entry = _FileEntry(stored, Path(dest), digest, label)
        entries.append(entry)
        labels[stored] = label
        hashes[label] = digest
    absent = [Path(path) for path in raw_absent if isinstance(path, str)]
    return _Preimage(snapshot_id, directory, entries, absent, labels, hashes)


def _restore_preimage(preimage: _Preimage) -> None:
    """Copy the preimage bytes back over the library files.

    Args:
        preimage: Snapshot whose hashes have been accepted.

    Raises:
        LibraryError: If a destination is a shortcut or is outside the
            library and was not an extra file in this snapshot.
        OSError: If a file cannot be replaced.
    """
    import library

    library_dir = _library_dir()
    live = Path(library.LIVE_MASTER).resolve().parent
    testing = Path(library.MASTER).resolve() != live
    for entry in preimage.files:
        _replace_file(entry, preimage.directory, library_dir, live, testing)
    for path in preimage.absent:
        _remove_absent(path, library_dir, live, testing)


def _replace_file(
    entry: _FileEntry,
    directory: Path,
    library_dir: Path,
    live: Path,
    testing: bool,
) -> None:
    """Replace one destination with the snapshotted bytes.

    Args:
        entry: Preimage entry.
        directory: Preimage directory.
        library_dir: Open library directory.
        live: The real Serato library directory on this computer.
        testing: True when this process is not pointed at that live library.

    Raises:
        LibraryError: If the destination is not safe to replace.
        OSError: If the file cannot be written.
    """
    import library

    dest = entry.dest
    if dest.is_symlink():
        raise library.LibraryError("Refusing to restore a shortcut.")
    if not _destination_allowed(dest, library_dir, live, testing, extra=not entry.stored.startswith("master") and not entry.stored.startswith("root")):
        raise library.LibraryError("Refusing to restore a file outside the library.")
    source = directory / entry.stored
    if _hash_file(source) != entry.sha256:
        raise library.LibraryError("The pre-write snapshot does not match its hash.")
    temporary = dest.parent / f".{dest.name}.{secrets.token_hex(4)}.tmp"
    try:
        shutil.copyfile(source, temporary)
        _fsync(temporary)
        os.replace(temporary, dest)
    finally:
        if temporary.exists():
            temporary.unlink()


def _remove_absent(path: Path, library_dir: Path, live: Path, testing: bool) -> None:
    """Delete a sidecar or extra file that the preimage did not have.

    Args:
        path: Path recorded as absent.
        library_dir: Open library directory.
        live: The real Serato library directory.
        testing: True when this process is not pointed at that live library.

    Raises:
        LibraryError: If the path is a shortcut or is not safe to remove.
    """
    import library

    if not path.exists() and not path.is_symlink():
        return
    if path.is_symlink():
        raise library.LibraryError("Refusing to remove a shortcut.")
    if not _destination_allowed(path, library_dir, live, testing, extra=True):
        raise library.LibraryError("Refusing to remove a file outside the library.")
    if path.is_file():
        path.unlink()


def _destination_allowed(path: Path, library_dir: Path, live: Path, testing: bool, extra: bool) -> bool:
    """Return whether rollback may write this path.

    Args:
        path: Destination. A shortcut is not allowed.
        library_dir: Open library directory.
        live: The real Serato library directory.
        testing: True when the open library is not the live one.
        extra: True for a file that is not ``master.sqlite`` or ``root.sqlite``.

    Returns:
        True when the path is inside the open library, or is an extra file
        that is not inside the snapshot store or the live library while a
        test library is open.
    """
    if path.is_symlink():
        return False
    try:
        resolved = path.resolve()
    except OSError:
        return False
    lib = library_dir.resolve()
    store = (lib / "Backups").resolve()
    if resolved == store or store in resolved.parents:
        return False
    if testing and (resolved == live or live in resolved.parents):
        return False
    if resolved == lib or lib in resolved.parents:
        return True
    return extra


def _verify_preimage(preimage: _Preimage) -> None:
    """Check that the library files match the preimage hashes.

    Args:
        preimage: Snapshot that was just restored.

    Raises:
        VerifyMismatch: If a file hash differs or an absent path still exists.
        LibraryError: If the preimage directory itself is no longer complete.
    """
    import library

    if not is_complete(preimage.directory):
        raise library.LibraryError("The pre-write snapshot is incomplete.")
    for entry in preimage.files:
        if entry.dest.is_symlink() or not entry.dest.is_file():
            raise VerifyMismatch("A restored file is missing.")
        if _hash_file(entry.dest) != entry.sha256:
            raise VerifyMismatch("A restored file does not match the snapshot.")
    for path in preimage.absent:
        if path.exists() or path.is_symlink():
            raise VerifyMismatch("A file created by the write is still there.")


def _verify_database(checks: Sequence[Check]) -> None:
    """Open a temporary copy and run the row checks.

    Args:
        checks: Callables that raise ``VerifyMismatch`` on a bad row.
            File checks may ignore the connection.

    Raises:
        VerifyMismatch: If ``quick_check`` is not ``ok`` or a check fails.
        OSError: If the copy cannot be made.
    """
    import library

    master = Path(library.MASTER)
    _verify_one_database(master, checks)
    root = master.resolve().parent / "root.sqlite"
    if root.is_file() and not root.is_symlink():
        _verify_one_database(root, ())


def _verify_one_database(source: Path, checks: Sequence[Check]) -> None:
    """Copy one database and its ``-wal`` file, then check the copy.

    The live database is not opened. When a ``-wal`` file is copied, the
    copy is opened read-only so SQLite applies those frames. When it is
    not, the copy is opened immutable so a WAL header cannot create a
    sidecar next to the original.

    Args:
        source: ``master.sqlite`` or ``root.sqlite``.
        checks: Row checks. Empty for a location database, which only
            needs ``quick_check``.

    Raises:
        VerifyMismatch: If the check is not exactly ``ok`` or a row check fails.
    """
    if source.is_symlink() or not source.is_file():
        raise VerifyMismatch("The library database is not a file.")
    wal = Path(str(source) + "-wal")
    with tempfile.TemporaryDirectory(prefix="serato-write-verify-") as raw:
        root = Path(raw)
        copied = root / source.name
        shutil.copyfile(source, copied)
        copied_wal = wal.is_file() and not wal.is_symlink()
        if copied_wal:
            shutil.copyfile(wal, root / wal.name)
        import library

        query = "mode=ro" if copied_wal else "mode=ro&immutable=1"
        conn = sqlite3.connect(library._read_only_uri(copied, query), uri=True)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only=ON")
            row = conn.execute("PRAGMA quick_check").fetchone()
            if row is None or row[0] != "ok":
                raise VerifyMismatch("The library failed its check.")
            for check in checks:
                check(conn)
        finally:
            conn.close()


def _write_journal(preimage: _Preimage, operation: str, target: str) -> None:
    """Record the preimage id before the body changes anything.

    Args:
        preimage: Finished snapshot.
        operation: Short machine name.
        target: Human-readable name.

    Raises:
        LibraryError: If the journal would not stay inside the store.
        OSError: If the journal cannot be written.
    """
    import library

    root = _store_root()
    root.mkdir(parents=True, exist_ok=True)
    path = root / _JOURNAL_NAME
    if path.is_symlink() or path.resolve().parent != root.resolve():
        raise library.LibraryError("The write journal is not inside the snapshot store.")
    payload = {
        "version": 1,
        "snapshot_id": preimage.snapshot_id,
        "operation": operation,
        "target": target,
    }
    _atomic_json(path, payload)


def _clear_journal() -> None:
    """Remove the write journal after a finished write or a checked rollback."""
    path = _journal_path()
    if path is None:
        return
    if path.is_symlink():
        return
    if path.is_file():
        path.unlink()


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    """Replace a JSON file by writing a temporary file beside it.

    Args:
        path: Destination.
        payload: Object to store.

    Raises:
        OSError: If the file cannot be written.
    """
    temporary = path.parent / f".{path.name}.{secrets.token_hex(4)}.tmp"
    text = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _store_result(record: WriteResult, persist: bool) -> None:
    """Remember one record and, when the store exists, append it.

    Args:
        record: Result to keep.
        persist: True appends a JSON line. A refusal does not create the
            store directory when it is not already there.
    """
    import library

    key = str(Path(library.MASTER).resolve())
    bucket = _RESULTS.setdefault(key, [])
    bucket.append(record)
    if len(bucket) > _RESULT_LIMIT:
        del bucket[: len(bucket) - _RESULT_LIMIT]
    if not persist:
        return
    root = _store_root()
    if not root.is_dir() or root.is_symlink():
        return
    path = root / _LOG_NAME
    if path.is_symlink():
        return
    line = json.dumps(record.to_dict(), sort_keys=True, separators=(",", ":")) + "\n"
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())


def _hash_file(path: Path) -> str:
    """Return the SHA-256 hex digest of a file.

    Args:
        path: File to read. The caller has already rejected a shortcut.

    Returns:
        The lowercase hex digest.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _fsync(path: Path) -> None:
    """Flush a file through a writable handle.

    Args:
        path: File to flush.

    Raises:
        OSError: If the file cannot be opened or flushed.

    Windows rejects ``fsync`` on a read-only handle, so the handle is opened
    for writing and closed before this returns.
    """
    fd = os.open(path, os.O_RDWR | getattr(os, "O_BINARY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _remove_tree(path: Path) -> None:
    """Remove a partial preimage directory this process created.

    A shortcut is unlinked and its target is left in place. A real directory
    is removed only when every child stays inside it.

    Args:
        path: Directory whose name contains ``.partial`` or a snapshot id
            under ``write-images``.

    Raises:
        OSError: If a child leaves the directory.
    """
    if path.is_symlink():
        path.unlink()
        return
    if not path.exists():
        return
    if not path.is_dir():
        path.unlink()
        return
    root = path.resolve()
    base = (_store_root() / _IMAGES).resolve()
    if root != base and base not in root.parents:
        raise OSError("Refusing to remove a directory outside the snapshot store.")
    for child in sorted(root.rglob("*"), reverse=True):
        parent = child.parent.resolve()
        if parent != root and root not in parent.parents:
            raise OSError("Refusing to remove a file outside the partial snapshot.")
        if child.is_symlink() or not child.is_dir():
            child.unlink()
        else:
            child.rmdir()
    root.rmdir()
