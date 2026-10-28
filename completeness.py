"""Completeness check for a snapshot directory or a database backup.

``COMPLETE`` is a JSON object ``{"version", "algorithm": "sha256", "hashes"}``.
It is written last. The directory is then renamed from ``name.partial`` to
``name``. :func:`is_complete` is true only when that marker is present, the
algorithm is ``sha256``, and the set of files matches the marker exactly.
A missing marker means the directory is incomplete.

``-failed`` and ``.partial`` match without regard to case. Hashing reads the
file in chunks. This is the module the backup work can import; it should not
keep a second copy of these checks.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from collections.abc import Mapping
from contextlib import closing
from pathlib import Path

COMPLETE_NAME = "COMPLETE"
BACKUP_COMPLETE_NAME = COMPLETE_NAME
INCOMPLETE_NAME = "INCOMPLETE"
BACKUP_INCOMPLETE_NAME = INCOMPLETE_NAME
BACKUP_FAILED_SUFFIX = "-failed"
PARTIAL_SUFFIX = ".partial"
PARTIAL_LOCK_NAME = ".write-lock"
MARKER_VERSION = 1
HASH_ALGORITHM = "sha256"
_HASH_CHUNK = 1024 * 1024


def is_complete(snapshot_or_backup: Path) -> bool:
    """Return whether a directory is finished and hash-checked.

    Args:
        snapshot_or_backup: Snapshot directory or backup directory. The
            parent path is not part of the check.

    Returns:
        True when ``COMPLETE`` verifies every file. A missing marker, a
        name ending in ``-failed`` or ``.partial`` in any letter case, an
        ``INCOMPLETE`` file, a shortcut, a hash that is not a SHA-256
        digest, or a file set that does not match the marker is false.
    """
    path = Path(snapshot_or_backup)
    try:
        if _rejected(path):
            return False
        marker = path / COMPLETE_NAME
        if not _real_file(marker):
            return False
        return _hashes_match(path)
    except OSError:
        return False


def verify_legacy_backup(backup_dir: Path) -> None:
    """Check an explicitly chosen legacy backup before it is restored.

    :func:`is_complete` stays false for a folder that has ``master.sqlite``
    and no ``COMPLETE`` marker. This copies that database, and a ``-wal``
    file when one is present, into a temporary directory and runs
    ``PRAGMA integrity_check`` there. The backup folder itself is not opened.

    Args:
        backup_dir: Folder the user picked. It must be a legacy backup.

    Raises:
        LibraryError: If the folder is not an unverified legacy backup, the
            database cannot be opened, or the integrity check is not ``ok``.
    """
    import library

    root = _resolved_directory(backup_dir)
    if root is None or not _is_legacy_backup(root):
        raise library.LibraryError("That folder is not an unverified legacy backup.")
    master = _file_inside(root, "master.sqlite")
    if master is None:
        raise library.LibraryError("That folder is not an unverified legacy backup.")
    wal = root / "master.sqlite-wal"
    wal_inside = None
    if wal.exists() or wal.is_symlink():
        wal_inside = _file_inside(root, "master.sqlite-wal")
        if wal_inside is None:
            raise library.LibraryError(
                "That legacy backup could not be checked, so it was not restored."
            )
    try:
        rows = _integrity_rows(master, wal_inside)
    except (sqlite3.Error, OSError) as exc:
        raise library.LibraryError(
            "That legacy backup could not be checked, so it was not restored."
        ) from exc
    if rows != [("ok",)]:
        raise library.LibraryError(
            "That legacy backup did not pass its integrity check, so it was not restored."
        )


def publish_directory(final: Path, files: Mapping[str, bytes]) -> None:
    """Write files, then the JSON ``COMPLETE`` marker, then rename into place.

    Args:
        final: Destination directory. It must not already exist.
        files: File names and bytes. ``COMPLETE`` is written after these.

    Raises:
        FileExistsError: If ``final`` already exists.
        OSError: If a file cannot be written. A leftover ``.partial``
            directory is not complete.
    """
    if final.exists():
        raise FileExistsError(final)
    partial = final.with_name(final.name + PARTIAL_SUFFIX)
    if partial.exists():
        _remove_partial(partial)
    partial.mkdir(parents=True)
    try:
        root = _resolved_directory(partial)
        if root is None:
            raise OSError("The staging directory is not a real directory.")
        for name, data in files.items():
            if name in {COMPLETE_NAME, INCOMPLETE_NAME} or not _single_component(name):
                raise OSError("A published file name is not a single path component.")
            target = _child_inside(root, name, allow_missing=True)
            if target is None:
                raise OSError("A published file leaves the directory.")
            _write_file(target, data)
        write_complete_marker(root)
        os.replace(root, final)
    except Exception:
        _remove_partial(partial)
        raise


def write_complete_marker(folder: Path) -> None:
    """Write the JSON ``COMPLETE`` marker after every other file.

    Args:
        folder: Directory whose files are already in place.

    Raises:
        OSError: If a file cannot be read or the marker cannot be written.
    """
    root = _resolved_directory(folder)
    if root is None:
        raise OSError("The directory is not a real directory.")
    files = _relative_files(root)
    if files is None:
        raise OSError("The directory contains a shortcut.")
    payload = {
        "version": MARKER_VERSION,
        "algorithm": HASH_ALGORITHM,
        "hashes": {rel: _sha256_inside(root, rel) for rel in files},
    }
    marker = _child_inside(root, COMPLETE_NAME, allow_missing=True)
    if marker is None:
        raise OSError("The marker leaves the directory.")
    marker.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _fsync_file(marker)


def _hashes_match(folder: Path) -> bool:
    """Return whether the marker lists exactly the files and their digests.

    Args:
        folder: Directory that contains ``COMPLETE``.

    Returns:
        True when the algorithm is ``sha256`` and every digest matches.
    """
    root = _resolved_directory(folder)
    if root is None:
        return False
    marker = _file_inside(root, COMPLETE_NAME)
    if marker is None:
        return False
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict) or set(payload) != {"version", "algorithm", "hashes"}:
        return False
    if payload.get("version") != MARKER_VERSION or payload.get("algorithm") != HASH_ALGORITHM:
        return False
    hashes = payload.get("hashes")
    if not isinstance(hashes, dict) or not hashes:
        return False
    listed: dict[str, str] = {}
    for rel, digest in hashes.items():
        if not isinstance(rel, str) or not isinstance(digest, str):
            return False
        if not _sha256_digest(digest) or rel in {COMPLETE_NAME, INCOMPLETE_NAME}:
            return False
        if _child_inside(root, rel) is None:
            return False
        if rel in listed:
            return False
        listed[rel] = digest.lower()
    files = _relative_files(root)
    if files is None:
        return False
    names = list(files)
    if names != sorted(listed):
        return False
    try:
        for rel, digest in listed.items():
            if _sha256_inside(root, rel) != digest:
                return False
    except OSError:
        return False
    return True


def _sha256_digest(value: str) -> bool:
    """Return whether a string is a 64-character SHA-256 hex digest.

    Args:
        value: Candidate digest.

    Returns:
        True when the text is 64 hexadecimal characters.
    """
    if len(value) != 64:
        return False
    try:
        bytes.fromhex(value)
    except ValueError:
        return False
    return True


def _resolved_directory(path: Path) -> Path | None:
    """Resolve a directory and reject a shortcut.

    Args:
        path: Candidate directory.

    Returns:
        The resolved directory, or None when it is missing, a shortcut, or
        unreadable.
    """
    try:
        if path.is_symlink() or not path.is_dir():
            return None
        return path.resolve()
    except OSError:
        return None


def _single_component(name: str) -> bool:
    """Return whether a name is one path component.

    Args:
        name: File name from a caller.

    Returns:
        True when the name has no separator, dot-dot, or colon.
    """
    if not name or name in {".", ".."} or "/" in name or "\\" in name or ":" in name:
        return False
    return Path(name).name == name


def _child_inside(root: Path, relative: str, *, allow_missing: bool = False) -> Path | None:
    """Resolve a relative path and keep it inside a directory.

    Args:
        root: Directory that was already resolved.
        relative: POSIX relative path from a marker or a caller.
        allow_missing: When true, a path that does not exist yet is returned
            so a file can be created there.

    Returns:
        The resolved path, or None when it escapes, is a shortcut, or is not
        a file.
    """
    if not relative or "\\" in relative or relative.startswith("/"):
        return None
    parts = relative.split("/")
    if any(part in {"", ".", ".."} or ":" in part for part in parts):
        return None
    try:
        base = root.resolve()
        candidate = base.joinpath(*parts)
        if candidate.is_symlink():
            return None
        if not allow_missing and not candidate.is_file():
            return None
        resolved = candidate.resolve()
    except OSError:
        return None
    if resolved != base and base not in resolved.parents:
        return None
    return resolved


def _file_inside(root: Path, relative: str) -> Path | None:
    """Return a regular file that stays inside a directory.

    Args:
        root: Directory that was already resolved.
        relative: POSIX relative path.

    Returns:
        The resolved file, or None when it is missing, a shortcut, or outside
        the directory.
    """
    return _child_inside(root, relative, allow_missing=False)


def _sha256_inside(root: Path, relative: str) -> str:
    """Hash one file in chunks after checking it stays inside the directory.

    Args:
        root: Directory that was already resolved.
        relative: POSIX relative path.

    Returns:
        The lowercase hex digest.

    Raises:
        OSError: If the file is outside the directory or cannot be read.
    """
    path = _file_inside(root, relative)
    if path is None:
        raise OSError("That file is outside the directory.")
    return _sha256_file(path)


def _sha256_file(path: Path) -> str:
    """Return the SHA-256 hex digest of a file, read in chunks.

    Args:
        path: File to read. The whole file is not loaded at once.

    Returns:
        The lowercase hex digest.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(_HASH_CHUNK)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _relative_files(folder: Path) -> list[str] | None:
    """Return regular files under a folder, excluding the marker and lock.

    Args:
        folder: Directory to walk.

    Returns:
        Relative paths sorted by POSIX name. None when a shortcut is found
        or the walk cannot be read.
    """
    found: list[str] = []
    try:
        base = folder.resolve()
        for path in folder.rglob("*"):
            if path.is_symlink():
                return None
            if not path.is_file():
                continue
            resolved = path.resolve()
            if base not in resolved.parents:
                return None
            if path.name == COMPLETE_NAME and path.parent == folder:
                continue
            if path.name == PARTIAL_LOCK_NAME:
                continue
            found.append(path.relative_to(folder).as_posix())
    except OSError:
        return None
    return sorted(found)


def _rejected(path: Path) -> bool:
    """Return whether a directory can never be complete.

    Args:
        path: Candidate directory.

    Returns:
        True for a shortcut, a missing path, a failed name, a staging name,
        a folder that contains ``INCOMPLETE``, or an unreadable path.
    """
    root = _resolved_directory(path)
    if root is None:
        return True
    if _is_failed_name(root.name) or _is_partial_name(root.name):
        return True
    marker = _child_inside(root, INCOMPLETE_NAME, allow_missing=True)
    if marker is None:
        return True
    return marker.exists()


def _is_failed_name(name: str) -> bool:
    """Return whether a directory name is a failed copy.

    Args:
        name: Directory name, not a path.

    Returns:
        True when the name ends with ``-failed`` or ``-failed-NN``, in any
        letter case.
    """
    lowered = name.lower()
    if lowered.endswith("-failed"):
        return True
    tail = lowered.rsplit("-failed-", 1)
    return len(tail) == 2 and len(tail[1]) == 2 and tail[1].isdigit()


def _is_partial_name(name: str) -> bool:
    """Return whether a directory name is an unfinished staging folder.

    Args:
        name: Directory name, not a path.

    Returns:
        True when the name ends with ``.partial``, in any letter case.
    """
    return name.lower().endswith(".partial")


def _is_legacy_backup(backup_dir: Path) -> bool:
    """Return whether a folder is an old backup with no COMPLETE marker.

    Args:
        backup_dir: Candidate directory.

    Returns:
        True when ``master.sqlite`` is a regular file, the folder has no
        marker, and it is not a failed or staging name.
    """
    try:
        if _rejected(backup_dir):
            return False
        if (backup_dir / COMPLETE_NAME).exists():
            return False
        return _real_file(backup_dir / "master.sqlite")
    except OSError:
        return False


def _integrity_rows(master: Path, wal: Path | None) -> list[tuple[object, ...]]:
    """Run ``PRAGMA integrity_check`` on a copy of a legacy database.

    Args:
        master: Resolved ``master.sqlite`` inside the legacy folder. It is
            not opened in place.
        wal: Resolved ``-wal`` file inside that same folder, or None.

    Returns:
        Rows from the check on the temporary copy.

    Raises:
        sqlite3.Error: If the copy cannot be opened.
        OSError: If the copy cannot be made.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as raw:
        copied = Path(raw) / "master.sqlite"
        shutil.copyfile(master, copied)
        if wal is not None:
            shutil.copyfile(wal, Path(raw) / "master.sqlite-wal")
        uri = f"file:{copied.resolve()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        try:
            with closing(connection.cursor()) as cursor:
                cursor.execute("PRAGMA integrity_check")
                return list(cursor.fetchall())
        finally:
            connection.close()


def _real_file(path: Path) -> bool:
    """Return whether a path is a regular file.

    Args:
        path: Path to test.

    Returns:
        True when the path is a file and not a shortcut.
    """
    return path.is_file() and not path.is_symlink()


def _write_file(path: Path, data: bytes) -> None:
    """Write one file and flush it.

    Args:
        path: Destination. The parent must exist.
        data: Bytes to store.
    """
    with path.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _fsync_file(path: Path) -> None:
    """Flush a file that was written as text.

    Args:
        path: File to flush.
    """
    with path.open("rb+") as handle:
        handle.flush()
        os.fsync(handle.fileno())


def _remove_partial(path: Path) -> None:
    """Remove a ``.partial`` directory this process created.

    Args:
        path: Directory whose name ends in ``.partial``.
    """
    root = _resolved_directory(path)
    if root is None or not _is_partial_name(root.name):
        return
    for child in sorted(root.rglob("*"), reverse=True):
        parent = child.parent.resolve()
        if parent != root and root not in parent.parents:
            raise OSError("Refusing to remove a file outside the partial directory.")
        if child.is_symlink() or child.is_file():
            child.unlink()
        elif child.is_dir():
            child.rmdir()
    root.rmdir()
