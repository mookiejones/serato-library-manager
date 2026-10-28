"""One completeness check for a snapshot or a database backup.

A finished copy is a directory. Its last file is ``COMPLETE``, a JSON object
whose ``hashes`` map names the files in that directory and the SHA-256 of
each. The directory is renamed from ``name.partial`` to ``name`` only after
that marker is on disk. A missing ``COMPLETE`` file means the copy is
incomplete. A name ending in ``.partial`` or ``-failed``, or an
``INCOMPLETE`` file, is also incomplete.

Backup folders can use the same marker. Until they do, a backup directory
without ``COMPLETE`` is not complete. The backup work can call
``is_complete`` instead of defining another check.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path

COMPLETE_NAME = "COMPLETE"
PARTIAL_SUFFIX = ".partial"


def is_complete(snapshot_or_backup: Path | Mapping[str, object]) -> bool:
    """Return whether a snapshot or backup is finished and hash-checked.

    Args:
        snapshot_or_backup: A directory, or a mapping that already has a
            ``complete`` flag and a ``sha256``. A directory is complete only
            when ``COMPLETE`` is present and every hash in it matches.

    Returns:
        True when the copy may be listed or restored.
    """
    if isinstance(snapshot_or_backup, Mapping):
        return snapshot_or_backup.get("complete") is True and isinstance(
            snapshot_or_backup.get("sha256"), str
        )
    path = Path(snapshot_or_backup)
    name = path.name
    if name.endswith(PARTIAL_SUFFIX) or name.endswith("-failed"):
        return False
    try:
        if path.is_symlink() or not path.is_dir():
            return False
        if (path / "INCOMPLETE").exists():
            return False
        marker_path = path / COMPLETE_NAME
        if not marker_path.is_file() or marker_path.is_symlink():
            return False
        payload = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return False
    if not isinstance(payload, dict):
        return False
    hashes = payload.get("hashes")
    if not isinstance(hashes, dict) or not hashes:
        return False
    for rel, digest in hashes.items():
        if not isinstance(rel, str) or not isinstance(digest, str):
            return False
        relative = Path(rel)
        if relative.is_absolute() or ".." in relative.parts:
            return False
        target = path / relative
        try:
            if not target.is_file() or target.is_symlink():
                return False
            if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                return False
            if path.resolve() not in target.resolve().parents:
                return False
        except OSError:
            return False
    return "manifest.json" in hashes or "master.sqlite" in hashes


def publish_directory(final: Path, files: Mapping[str, bytes]) -> None:
    """Write a directory, then ``COMPLETE``, then rename it into place.

    Args:
        final: Destination directory. It must not already exist.
        files: File names and bytes stored inside the directory. ``COMPLETE``
            is not one of these names. It is written after every other file.

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
    hashes: dict[str, str] = {}
    try:
        for name, data in files.items():
            if name == COMPLETE_NAME or Path(name).name != name:
                raise OSError("A published file name is not a single path component.")
            target = partial / name
            _write_file(target, data)
            hashes[name] = hashlib.sha256(data).hexdigest()
        marker = (json.dumps({"hashes": hashes}, indent=2, sort_keys=True) + "\n").encode("utf-8")
        _write_file(partial / COMPLETE_NAME, marker)
        os.replace(partial, final)
    except Exception:
        _remove_partial(partial)
        raise


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


def _remove_partial(path: Path) -> None:
    """Remove a ``.partial`` directory this process created.

    Args:
        path: Directory whose name ends in ``.partial``.
    """
    if not path.exists():
        return
    if path.name.endswith(PARTIAL_SUFFIX) and path.is_dir() and not path.is_symlink():
        for child in sorted(path.rglob("*"), reverse=True):
            if child.is_file() or child.is_symlink():
                child.unlink()
            elif child.is_dir():
                child.rmdir()
        path.rmdir()
