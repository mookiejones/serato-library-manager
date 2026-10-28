"""Find the Serato library for the first-run wizard.

The sentences in this module are shown to a person who has not used the
app. They name the disk and the track count. They do not name database
files, crate-file formats, or Serato's internal library sections.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

import files
import library
import snapshots

NOT_FOUND_SUMMARY = "No Serato library was found on this computer."
NOT_FOUND_NEXT = (
    "Open Serato DJ once so it can create your library. "
    "Quit Serato DJ, then choose Check again."
)
WRONG_FOLDER_SUMMARY = "That folder is not the Serato library on this computer."
WRONG_FOLDER_NEXT = (
    "Choose Check again to use the library that was found, "
    "or pick the folder Serato uses."
)
_BROWSE_CAP = 500


def format_track_count(count: int) -> str:
    """Return a track count the way the wizard speaks it.

    Args:
        count: Number of tracks in the library. Negative values are
            treated as zero.

    Returns:
        A phrase such as ``1 track`` or ``4,812 tracks``.
    """
    safe = count if isinstance(count, int) and not isinstance(count, bool) and count > 0 else 0
    noun = "track" if safe == 1 else "tracks"
    return f"{safe:,} {noun}"


def volume_label(path: Path) -> str:
    """Return a plain disk name for a library file.

    Args:
        path: File or folder whose disk should be named.

    Returns:
        The volume name on macOS, the volume label or ``drive C`` on
        Windows, and ``this computer`` elsewhere. The result is a short
        name, not a path.
    """
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    if sys.platform == "win32":
        return _windows_volume_label(resolved)
    if sys.platform == "darwin":
        return _mac_volume_label(resolved)
    return "this computer"


def describe_library() -> dict[str, object]:
    """Describe the library the app already knows how to open.

    Returns:
        ``found``, a one-sentence ``summary``, ``next`` when the person
        has to do something, the ``volume`` name, ``track_count`` when it
        could be read, ``places`` for extra disks that hold crates, and
        ``serato_running``. No filesystem path is included.
    """
    running = snapshots.serato_dj_running()
    master = Path(library.MASTER)
    if not master.is_file():
        return {
            "found": False,
            "volume": None,
            "track_count": None,
            "summary": NOT_FOUND_SUMMARY,
            "next": NOT_FOUND_NEXT,
            "places": [],
            "serato_running": running,
        }
    volume = volume_label(master)
    count = _track_count(master)
    places = _extra_places(volume)
    return {
        "found": True,
        "volume": volume,
        "track_count": count,
        "summary": _found_summary(volume, count, places),
        "next": None,
        "places": places,
        "serato_running": running,
    }


def accept_folder(folder: str) -> dict[str, object]:
    """Accept a chosen folder only when it is the library already in use.

    Args:
        folder: Absolute folder from the wizard's folder list.

    Returns:
        The same object as :func:`describe_library` when the folder is
        the one that holds that library. Otherwise a not-found object
        whose ``next`` says what to do. The chosen path is not returned.

    Raises:
        LibraryError: If the folder is missing, not a directory, or a shortcut.
    """
    directory = files._list_root(folder)
    master = Path(library.MASTER)
    try:
        chosen = directory.resolve()
        live = master.resolve() if master.is_file() else None
    except OSError:
        live = None
        chosen = directory
    if live is not None and (chosen == live.parent or _same_file(chosen / "master.sqlite", live)):
        return describe_library()
    running = snapshots.serato_dj_running()
    if master.is_file():
        summary = WRONG_FOLDER_SUMMARY
        nxt = WRONG_FOLDER_NEXT
    else:
        summary = NOT_FOUND_SUMMARY
        nxt = NOT_FOUND_NEXT
    return {
        "found": False,
        "volume": None,
        "track_count": None,
        "summary": summary,
        "next": nxt,
        "places": [],
        "serato_running": running,
    }


def browse_folders(folder: str | None) -> dict[str, object]:
    """List the folders inside one directory for the wizard picker.

    Args:
        folder: Directory to open. None or an empty string opens the
            home directory.

    Returns:
        ``path``, ``parent``, ``name`` (the folder's own name, or
        ``Home``), and ``folders`` of ``name`` and ``path``. Shortcuts
        and hidden names are skipped.

    Raises:
        LibraryError: If the path is not a real folder.
    """
    directory = files._list_root(folder or "")
    folders: list[dict[str, str]] = []
    try:
        with os.scandir(directory) as scanner:
            for entry in scanner:
                if len(folders) >= _BROWSE_CAP:
                    break
                if entry.name.startswith(".") or entry.is_symlink():
                    continue
                try:
                    is_dir = entry.is_dir(follow_symlinks=False)
                except OSError:
                    continue
                if not is_dir:
                    continue
                folders.append({"name": entry.name, "path": entry.path})
    except OSError as exc:
        raise library.LibraryError("That folder could not be read.", 404) from exc
    folders.sort(key=lambda item: item["name"].casefold())
    parent = None if directory.parent == directory else str(directory.parent)
    name = "Home" if directory == Path.home().resolve() else directory.name
    return {
        "path": str(directory),
        "parent": parent,
        "name": name or "Folder",
        "folders": folders,
    }


def _found_summary(volume: str, count: int | None, places: list[str]) -> str:
    """Build the sentence for a library that was found.

    Args:
        volume: Disk name.
        count: Track count, or None when it could not be read.
        places: Extra disk names that hold crates.

    Returns:
        One or two sentences. The track count uses a thousands separator.
    """
    if count is None:
        sentence = f"Found your Serato library on {volume}."
    else:
        sentence = f"Found your Serato library on {volume}, {format_track_count(count)}."
    extra = _extra_sentence(places)
    if extra:
        return f"{sentence} {extra}"
    return sentence


def _extra_sentence(places: list[str]) -> str:
    """Describe extra disks that hold crates.

    Args:
        places: Disk names, already filtered.

    Returns:
        An empty string when there are none. Otherwise one sentence.
    """
    if not places:
        return ""
    if len(places) == 1:
        return f"Crates on {places[0]} are included."
    if len(places) == 2:
        return f"Crates on {places[0]} and {places[1]} are included."
    head = ", ".join(places[:-1])
    return f"Crates on {head}, and {places[-1]} are included."


def _extra_places(volume: str) -> list[str]:
    """Return external disk names that are not the library disk.

    Args:
        volume: Name already used for the library file.

    Returns:
        Unique labels. An error while looking becomes an empty list.
        The relocated test library has none.
    """
    try:
        drives = snapshots.discover_drives()
    except (OSError, RuntimeError):
        return []
    found: list[str] = []
    for drive in drives:
        if drive.role != "external":
            continue
        label = drive.label.strip()
        if not label or label == volume or "/" in label or "\\" in label:
            continue
        if label not in found:
            found.append(label)
    return found


def _track_count(path: Path) -> int | None:
    """Count tracks in the main library.

    Args:
        path: Database file that exists.

    Returns:
        The count, or None when the file cannot be read. The wizard
        still says the library was found.
    """
    try:
        with closing(library.read_conn(path)) as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) FROM asset AS a
                JOIN space_asset AS sa ON sa.asset_id = a.id
                JOIN space AS s ON s.id = sa.space_id
                WHERE s.name = ?
                """,
                (library.LIBRARY_SPACE,),
            ).fetchone()
    except (library.LibraryError, sqlite3.Error, OSError):
        return None
    if row is None or row[0] is None:
        return None
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return None


def _same_file(left: Path, right: Path) -> bool:
    """Return whether two paths are the same file.

    Args:
        left: Candidate.
        right: Known file.

    Returns:
        True when both exist and resolve to the same path.
    """
    try:
        return left.is_file() and left.resolve() == right.resolve()
    except OSError:
        return False


def _mac_volume_label(path: Path) -> str:
    """Return the macOS volume name for a path.

    Args:
        path: File on a mounted volume.

    Returns:
        The ``/Volumes`` name that shares the path's device. A name
        ending in `` - Data`` loses to the shorter name on the same
        device. ``this Mac`` when none match.
    """
    volumes = Path("/Volumes")
    if not volumes.is_dir():
        return "this Mac"
    try:
        device = path.stat().st_dev
    except OSError:
        return "this Mac"
    names: list[str] = []
    try:
        entries = list(volumes.iterdir())
    except OSError:
        return "this Mac"
    for entry in entries:
        if entry.name.startswith("."):
            continue
        try:
            if entry.is_symlink() or not entry.is_dir():
                continue
            if entry.stat().st_dev == device:
                names.append(entry.name)
        except OSError:
            continue
    plain = [name for name in names if not name.endswith(" - Data")]
    if plain:
        return sorted(plain)[0]
    if names:
        return sorted(names)[0]
    return "this Mac"


def _windows_volume_label(path: Path) -> str:
    """Return the Windows volume label, or a drive letter name.

    Args:
        path: File on a drive.

    Returns:
        The volume label when Windows reports one. Otherwise ``drive C``
        using the drive letter. ``this PC`` when there is no drive.
    """
    drive = os.path.splitdrive(str(path))[0]
    if not drive:
        return "this PC"
    letter = drive.rstrip(":\\")
    label = _windows_label(f"{letter}:\\")
    if label:
        return label
    return f"drive {letter}"


def _windows_label(root: str) -> str:
    """Read a Windows volume label.

    Args:
        root: A drive root such as ``C:\\``.

    Returns:
        The label, or an empty string when it cannot be read. This is
        only called on Windows.
    """
    if sys.platform != "win32":
        return ""
    try:
        import ctypes

        buffer = ctypes.create_unicode_buffer(261)
        ok = ctypes.windll.kernel32.GetVolumeInformationW(
            root,
            buffer,
            len(buffer),
            None,
            None,
            None,
            None,
            0,
        )
    except (AttributeError, OSError):
        return ""
    if not ok:
        return ""
    return buffer.value.strip()
