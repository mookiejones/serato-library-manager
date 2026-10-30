"""Read an older Serato library that has ``database V2`` but no ``master.sqlite``.

Serato DJ before version 4 kept its library in ``_Serato_/database V2`` and
per-drive ``.crate`` files. This module reads those files and never writes
them. It answers three questions: which tracks are in the library (browse),
which of them are not on disk (missing), and which file names appear more
than once (duplicates).

Every function here is read-only. Files are opened with ``"rb"`` only, and
nothing is created inside the ``_Serato_`` folder. Writes for an older
library are refused with :data:`WRITE_BLOCKED` until snapshot and restore are
verified on a real older install (issue #126).
"""

from __future__ import annotations

import os
from pathlib import Path, PurePath
from typing import Callable

import snapshots

DATABASE_NAME = "database V2"
SUBCRATES = "Subcrates"
CRATE_SEPARATOR = "%%"
CRATE_SUFFIX = ".crate"
_READ_CAP = 256 * 1024 * 1024

LEGACY_SUMMARY = "Found an older Serato library on {volume}, {count}."
LEGACY_SUMMARY_NO_COUNT = "Found an older Serato library on {volume}."
LEGACY_NEXT = (
    "This library was made by an older Serato DJ. "
    "You can look at your tracks, missing files, and duplicates, "
    "but this app will not change anything in it yet."
)
WRITE_BLOCKED = (
    "This library was made by an older Serato DJ. "
    "This app can show it but cannot change it yet."
)

TrackStatus = str
"""``ok``, ``missing``, ``offline`` (the drive is not connected), or ``invalid``."""


class LegacyLibraryError(Exception):
    """An older library could not be read, with a plain-words message."""

    def __init__(self, message: str, status: int = 404):
        """Store the message and HTTP status.

        Args:
            message: Sentence safe to show to the person.
            status: HTTP status for the API.
        """
        super().__init__(message)
        self.message = message
        self.status = status


def home_serato_folder() -> Path:
    """Return the usual ``_Serato_`` folder for an older library.

    Returns:
        ``~/Music/_Serato_`` on macOS and ``%USERPROFILE%\\Music\\_Serato_``
        on Windows. The folder may not exist.
    """
    return Path.home() / "Music" / "_Serato_"


def is_legacy_folder(folder: Path) -> bool:
    """Return whether ``folder`` is a ``_Serato_`` folder with only ``database V2``.

    Args:
        folder: Candidate ``_Serato_`` folder, or a folder that contains one.

    Returns:
        True when ``database V2`` is a regular file (not a shortcut) and
        the folder itself is not a shortcut. Errors while looking count as
        False.
    """
    serato = _serato_dir(folder)
    if serato is None:
        return False
    try:
        if serato.is_symlink() or not serato.is_dir():
            return False
        database = serato / DATABASE_NAME
        if database.is_symlink() or not database.is_file():
            return False
        return True
    except OSError:
        return False


def find_legacy_library(master: Path, candidates: list[Path] | None = None) -> Path | None:
    """Find an older library when the newer library file is missing.

    Args:
        master: Path the app uses for ``master.sqlite``. When that file
            exists the newer library wins and None is returned.
        candidates: Folders to check, in order. Defaults to
            :func:`home_serato_folder`.

    Returns:
        The ``_Serato_`` folder, or None.
    """
    try:
        if master.is_file():
            return None
    except OSError:
        return None
    for candidate in candidates if candidates is not None else [home_serato_folder()]:
        if is_legacy_folder(candidate):
            return _serato_dir(candidate)
    return None


def drive_base(serato: PurePath) -> PurePath:
    """Return the folder that ``database V2`` paths are relative to.

    Serato stores paths without the drive. On the system disk that is the
    disk root (``/`` or ``C:\\``). A ``_Serato_`` folder at the top of an
    external drive (``/Volumes/USB/_Serato_`` or ``E:\\_Serato_``) is
    relative to that drive.

    Args:
        serato: The ``_Serato_`` folder.

    Returns:
        The base folder. Works on both path flavours, whatever the host OS.
    """
    parent = serato.parent
    if str(parent) == serato.anchor:
        return parent
    parts = serato.parts
    if serato.anchor == "/" and len(parts) == 4 and parts[1] == "Volumes":
        return parent
    return type(serato)(serato.anchor) if serato.anchor else parent


def track_location(stored: str, base: PurePath) -> PurePath | None:
    """Join a path stored in ``database V2`` or a crate onto its drive.

    Args:
        stored: Path as Serato wrote it. ``/`` and ``\\`` both separate.
        base: Result of :func:`drive_base`.

    Returns:
        The joined path, or None when the stored path is empty, climbs
        with ``..``, or carries its own drive letter or stream (``:``).
    """
    raw = stored.replace("\\", "/")
    parts = [part for part in raw.split("/") if part not in ("", ".")]
    if not parts or any(part == ".." or ":" in part for part in parts):
        return None
    return base.joinpath(*parts)


def track_status(location: PurePath | None, base: PurePath, *, exists: Callable[[str], bool] | None = None) -> TrackStatus:
    """Classify one track.

    Args:
        location: Result of :func:`track_location`.
        base: Drive base. When it is not there, the drive is unplugged.
        exists: ``os.path.isdir``-like check, for tests. The same check is
            used for the base (as a folder) and the file.

    Returns:
        ``invalid``, ``offline``, ``ok``, or ``missing``. An unplugged
        drive is ``offline``, not ``missing``.
    """
    if location is None:
        return "invalid"
    if exists is not None:
        if not exists(str(base)):
            return "offline"
        return "ok" if exists(str(location)) else "missing"
    if not os.path.isdir(str(base)):
        return "offline"
    return "ok" if os.path.isfile(str(location)) else "missing"


def crate_name(file_name: str) -> tuple[str, list[str]]:
    """Split a crate file name into its name and parent crates.

    Args:
        file_name: Such as ``House%%Deep.crate``.

    Returns:
        ``("Deep", ["House"])``. A name with no separator has no parents.
    """
    stem = file_name[: -len(CRATE_SUFFIX)] if file_name.endswith(CRATE_SUFFIX) else file_name
    pieces = [piece for piece in stem.split(CRATE_SEPARATOR) if piece]
    if not pieces:
        return stem, []
    return pieces[-1], pieces[:-1]


def read_library(serato: Path, *, base: PurePath | None = None, exists: Callable[[str], bool] | None = None) -> dict[str, object]:
    """Read an older library for browse, missing files, and duplicates.

    Args:
        serato: The ``_Serato_`` folder.
        base: Drive base for track paths. Defaults to :func:`drive_base`.
        exists: Optional existence check, for tests.

    Returns:
        ``read_only`` (always True), ``tracks``, ``crates``, ``missing``,
        ``offline``, ``duplicates``, and ``write_blocked``. Track rows have
        ``path`` (as stored), ``location``, ``status``, and the text fields.

    Raises:
        LegacyLibraryError: When the folder is not an older library.
    """
    if not is_legacy_folder(serato):
        raise LegacyLibraryError("No older Serato library was found there.")
    folder = _serato_dir(serato)
    assert folder is not None
    root = base if base is not None else drive_base(folder)
    rows = snapshots.parse_database_v2(_read_bytes(folder / DATABASE_NAME))
    tracks: list[dict[str, object]] = []
    for row in rows:
        stored = str(row.get("path", ""))
        location = track_location(stored, root)
        status = track_status(location, root, exists=exists)
        tracks.append({
            **row,
            "path": stored,
            "location": None if location is None else str(location),
            "status": status,
        })
    crates = _read_crates(folder)
    return {
        "read_only": True,
        "write_blocked": WRITE_BLOCKED,
        "tracks": tracks,
        "crates": crates,
        "missing": [t for t in tracks if t["status"] == "missing"],
        "offline": [t for t in tracks if t["status"] == "offline"],
        "duplicates": duplicate_groups(tracks),
    }


def duplicate_groups(tracks: list[dict[str, object]]) -> list[dict[str, object]]:
    """Group tracks whose file names match, ignoring case.

    Args:
        tracks: Rows from :func:`read_library`. Rows with no location
            are skipped.

    Returns:
        Groups of two or more rows, as ``{"name", "tracks"}``, sorted by
        name. The same stored path listed twice is also a group.
    """
    groups: dict[str, list[dict[str, object]]] = {}
    for track in tracks:
        location = track.get("location")
        if not isinstance(location, str):
            continue
        name = str(track.get("path", "")).replace("\\", "/").rsplit("/", 1)[-1]
        groups.setdefault(name.casefold(), []).append(track)
    return [
        {"name": key, "tracks": rows}
        for key, rows in sorted(groups.items())
        if len(rows) > 1
    ]


def refuse_write() -> None:
    """Refuse a change to an older library.

    Raises:
        LegacyLibraryError: Always, with status 409.
    """
    raise LegacyLibraryError(WRITE_BLOCKED, status=409)


def _read_crates(folder: Path) -> list[dict[str, object]]:
    """Read every ``.crate`` under ``Subcrates``.

    Args:
        folder: The ``_Serato_`` folder.

    Returns:
        ``{"name", "parents", "tracks"}`` rows sorted by file name.
        Shortcuts and unreadable files are skipped.
    """
    subcrates = folder / SUBCRATES
    try:
        if subcrates.is_symlink() or not subcrates.is_dir():
            return []
        entries = sorted(subcrates.iterdir(), key=lambda p: p.name)
    except OSError:
        return []
    crates: list[dict[str, object]] = []
    for entry in entries:
        if not entry.name.endswith(CRATE_SUFFIX):
            continue
        try:
            if entry.is_symlink() or not entry.is_file():
                continue
            data = _read_bytes(entry)
        except (OSError, LegacyLibraryError):
            continue
        name, parents = crate_name(entry.name)
        crates.append({"name": name, "parents": parents, "tracks": snapshots.parse_serato_bytes(data)})
    return crates


def _read_bytes(path: Path) -> bytes:
    """Read a Serato file without changing it.

    Args:
        path: File to read.

    Returns:
        Its bytes.

    Raises:
        LegacyLibraryError: When it is too large or cannot be read.
    """
    try:
        with open(path, "rb") as handle:
            data = handle.read(_READ_CAP + 1)
    except OSError as exc:
        raise LegacyLibraryError("The older Serato library could not be read.", status=500) from exc
    if len(data) > _READ_CAP:
        raise LegacyLibraryError("The older Serato library is too large to read.", status=413)
    return data


def _serato_dir(folder: Path) -> Path | None:
    """Return ``folder`` when it is ``_Serato_``, or its ``_Serato_`` child.

    Args:
        folder: Folder the person chose, or a ``_Serato_`` folder.

    Returns:
        The ``_Serato_`` path, or None when neither applies.
    """
    if folder.name == "_Serato_":
        return folder
    child = folder / "_Serato_"
    try:
        if child.is_dir():
            return child
    except OSError:
        return None
    return None
