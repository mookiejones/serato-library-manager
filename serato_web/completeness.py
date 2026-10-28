"""One completeness check for a snapshot directory or a database backup.

A finished copy is a directory. Its last file is ``COMPLETE``, a JSON
object ``{"version": 1, "algorithm": "sha256", "hashes": {relative path:
sha256}}``. The directory is renamed out of ``.partial`` only after that
marker is on disk. A missing ``COMPLETE`` file means the copy is
incomplete. A name ending in ``.partial`` or ``-failed``, in any letter
case, or an ``INCOMPLETE`` file, is also incomplete.

No restore calls these functions yet. The snapshot work in #62 will import
this module and drop its own copy.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

COMPLETE_NAME = "COMPLETE"
INCOMPLETE_NAME = "INCOMPLETE"
FAILED_SUFFIX = "-failed"
PARTIAL_SUFFIX = ".partial"
# Held while a staging directory is being written. Ignored only at the
# top of the backup, not inside a subfolder.
LOCK_NAME = ".write-lock"
LEGACY_STATUS = "legacy, unverified"
MARKER_VERSION = 1
MARKER_ALGORITHM = "sha256"
_HEX = frozenset("0123456789abcdef")
_FAILED_NAME = re.compile(r"-failed(-\d+)?$", re.IGNORECASE)
_MARKER_KEYS = frozenset({"version", "algorithm", "hashes"})


class CompletenessError(Exception):
    """Raised when a backup folder cannot be checked.

    ``library.LibraryError`` subclasses this. Importing this module does
    not import ``library``.

    Attributes:
        message: Text for the caller.
    """

    def __init__(self, message: str) -> None:
        """Store the message.

        Args:
            message: Text for the caller.
        """
        super().__init__(message)
        self.message = message


def is_failed_name(name: str) -> bool:
    """Return whether a directory name is a failed backup.

    Args:
        name: Directory name, not a path.

    Returns:
        True when the name ends with ``-failed`` or ``-failed-`` and one
        or more digits, in any letter case. ``-failed-7``, ``-FAILED-100``,
        and ``-failed-002`` all count.
    """
    return _FAILED_NAME.search(name) is not None


def is_staging_name(name: str) -> bool:
    """Return whether a directory name is an unfinished staging folder.

    Args:
        name: Directory name, not a path.

    Returns:
        True when the name ends with ``.partial``, in any letter case.
    """
    return name.lower().endswith(PARTIAL_SUFFIX)


def _real_dir(path: Path) -> bool:
    """Return whether a path is a directory and not a shortcut.

    Args:
        path: Path to test.

    Returns:
        True for a real directory.
    """
    return path.is_dir() and not path.is_symlink()


def _real_file(path: Path) -> bool:
    """Return whether a path is a file and not a shortcut.

    Args:
        path: Path to test.

    Returns:
        True for a regular file.
    """
    return path.is_file() and not path.is_symlink()


def _bad_relative(rel: str) -> bool:
    """Return whether a marker path is absolute or escapes the directory.

    Args:
        rel: Path text from the marker.

    Returns:
        True when the path must be rejected.
    """
    if not isinstance(rel, str) or not rel or "\\" in rel:
        return True
    if rel.startswith("/") or (len(rel) >= 2 and rel[1] == ":"):
        return True
    return any(part in {"", ".", ".."} for part in rel.split("/"))


def _sha256_file(path: Path) -> str:
    """Return the SHA-256 hex digest of a file.

    Args:
        path: File to read.

    Returns:
        The lowercase hex digest. The file is read in chunks.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _relative_files(folder: Path) -> list[Path] | None:
    """Return regular files under a folder, excluding the marker.

    Args:
        folder: Directory to walk.

    Returns:
        File paths relative to ``folder``, sorted by their POSIX path.
        None when a shortcut is found or the walk cannot be read. A
        ``.write-lock`` file is skipped only when it sits directly in
        ``folder``.
    """
    found: list[Path] = []
    try:
        for path in folder.rglob("*"):
            if path.is_symlink():
                return None
            if not path.is_file():
                continue
            relative = path.relative_to(folder)
            if relative.name == COMPLETE_NAME and relative.parent == Path("."):
                continue
            if relative.name == LOCK_NAME and relative.parent == Path("."):
                continue
            found.append(relative)
    except OSError:
        return None
    return sorted(found, key=lambda item: item.as_posix())


def _fsync_file(path: Path) -> None:
    """Flush a file through a writable handle.

    Args:
        path: File to flush.

    Raises:
        OSError: If the file cannot be opened or flushed.

    Windows rejects ``fsync`` on a read-only handle.
    """
    fd = os.open(path, os.O_RDWR | getattr(os, "O_BINARY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_complete_marker(folder: Path) -> None:
    """Write the COMPLETE marker after every other file.

    Args:
        folder: Directory whose files are already in place.

    Raises:
        OSError: If a file cannot be read or the marker cannot be written.
    """
    files = _relative_files(folder)
    if files is None:
        raise OSError("The backup contains a shortcut.")
    if not files:
        raise OSError("The backup has no files to record.")
    hashes = {rel.as_posix(): _sha256_file(folder / rel) for rel in files}
    payload = {
        "version": MARKER_VERSION,
        "algorithm": MARKER_ALGORITHM,
        "hashes": hashes,
    }
    marker = folder / COMPLETE_NAME
    marker.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _fsync_file(marker)


def _valid_digest(digest: object) -> bool:
    """Return whether a marker value is a lowercase SHA-256 hex string.

    Args:
        digest: Value from the ``hashes`` object.

    Returns:
        True for 64 lowercase hexadecimal characters.
    """
    return (
        isinstance(digest, str)
        and len(digest) == 64
        and digest == digest.lower()
        and all(character in _HEX for character in digest)
    )


def _hashes_match(folder: Path, payload: object) -> bool:
    """Return whether a COMPLETE payload matches the directory exactly.

    Args:
        folder: Directory that contains the marker.
        payload: Parsed JSON value.

    Returns:
        True when version, algorithm, and every file hash agree, with no
        extra or missing files.
    """
    if not isinstance(payload, dict) or set(payload) != _MARKER_KEYS:
        return False
    if payload.get("version") != MARKER_VERSION or payload.get("algorithm") != MARKER_ALGORITHM:
        return False
    hashes = payload.get("hashes")
    if not isinstance(hashes, dict) or not hashes:
        return False
    for rel, digest in hashes.items():
        if _bad_relative(rel) or not _valid_digest(digest):
            return False
        target = folder / rel
        try:
            if not target.is_file() or target.is_symlink():
                return False
            if folder.resolve() not in target.resolve().parents:
                return False
            if _sha256_file(target) != digest:
                return False
        except OSError:
            return False
    files = _relative_files(folder)
    if files is None:
        return False
    return {path.as_posix() for path in files} == set(hashes)


def _rejected(path: Path) -> bool:
    """Return whether a directory can never be a finished copy.

    Args:
        path: Candidate directory.

    Returns:
        True for a shortcut, a missing path, a failed name, a staging
        name, a folder that contains ``INCOMPLETE``, or an unreadable path.
    """
    if path.is_symlink() or not path.is_dir():
        return True
    if is_failed_name(path.name) or is_staging_name(path.name):
        return True
    return (path / INCOMPLETE_NAME).exists()


def is_complete(snapshot_or_backup: Path) -> bool:
    """Return whether a snapshot or backup directory is finished.

    The check always reads the directory. No restore calls this yet.
    The snapshot work in #62 will.

    Args:
        snapshot_or_backup: Directory to check.

    Returns:
        True only when ``COMPLETE`` exists and every listed hash matches
        the file set exactly. A missing marker, a text-line marker, an
        extra key, a ``.partial`` name, a ``-failed`` name, traversal, an
        absolute path, or a hash that is not 64 lowercase hex characters
        is false.
    """
    path = Path(snapshot_or_backup)
    try:
        if _rejected(path):
            return False
        marker = path / COMPLETE_NAME
        if not _real_file(marker):
            return False
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return False
    return _hashes_match(path, payload)


def backup_status(backup_dir: Path) -> str:
    """Describe a backup directory for a list.

    Args:
        backup_dir: Candidate directory.

    Returns:
        ``complete`` when :func:`is_complete` is true.
        :data:`LEGACY_STATUS` (``legacy, unverified``) when the folder is
        an old backup with ``master.sqlite`` and no COMPLETE marker.
        ``incomplete`` for everything else.
    """
    if is_complete(backup_dir):
        return "complete"
    if _is_legacy_backup(backup_dir):
        return LEGACY_STATUS
    return "incomplete"


def _is_legacy_backup(backup_dir: Path) -> bool:
    """Return whether a folder is an old backup with no COMPLETE marker.

    Args:
        backup_dir: Candidate directory.

    Returns:
        True when ``master.sqlite`` is a regular file and the folder has
        neither marker, and it is not a failed or staging name.
    """
    try:
        if _rejected(backup_dir):
            return False
        if (backup_dir / COMPLETE_NAME).exists():
            return False
        return _real_file(backup_dir / "master.sqlite")
    except OSError:
        return False


def verify_legacy_backup(backup_dir: Path) -> None:
    """Check an explicitly chosen legacy backup.

    Call this only when the user picked an unmarked folder.
    :func:`is_complete` stays false for that folder. No restore calls this
    yet. The snapshot work in #62 will call it before its pre-restore
    snapshot when the chosen folder is legacy. The check copies
    ``master.sqlite`` and any ``-wal`` file into a temporary directory and
    runs ``PRAGMA integrity_check`` there. The backup folder is not opened,
    so no ``-shm`` file is created beside it. The result must be exactly
    ``ok``.

    Args:
        backup_dir: Folder the user picked. It must be a legacy backup.

    Raises:
        CompletenessError: If the folder is not an unverified legacy backup,
            the copy cannot be checked, or the integrity check is not
            exactly ``ok``.
    """
    if not _is_legacy_backup(backup_dir):
        raise CompletenessError("That folder is not an unverified legacy backup.")
    master = backup_dir / "master.sqlite"
    try:
        rows = _integrity_rows(master)
    except sqlite3.Error as exc:
        raise CompletenessError(
            "That legacy backup could not be checked, so it was not restored."
        ) from exc
    if rows != [("ok",)]:
        raise CompletenessError(
            "That legacy backup did not pass its integrity check, so it was not restored."
        )


def _integrity_rows(master: Path) -> list[tuple[object, ...]]:
    """Run ``PRAGMA integrity_check`` on a copy of a legacy database.

    Args:
        master: ``master.sqlite`` inside the legacy folder. It is not opened.

    Returns:
        Rows from the check on the temporary copy.

    Raises:
        sqlite3.Error: If the copy cannot be opened.
        OSError: If the copy cannot be made.
    """
    wal = Path(str(master) + "-wal")
    with tempfile.TemporaryDirectory() as raw:
        copied = Path(raw) / "master.sqlite"
        shutil.copyfile(master, copied)
        if _real_file(wal):
            shutil.copyfile(wal, Path(raw) / "master.sqlite-wal")
        uri = f"file:{copied.resolve()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        try:
            with closing(conn.cursor()) as cursor:
                cursor.execute("PRAGMA integrity_check")
                return list(cursor.fetchall())
        finally:
            conn.close()
