"""Music folders the Files page opens on.

Track folders in ``master.sqlite`` collapse to the shared music folder
(album folders under ``Music`` become ``Music``). Each mounted drive that
contains a ``_Serato_`` folder is added as well. macOS looks in
``/Volumes``. Windows checks drive letters. The browse guard lives in
``files.py`` and uses the paths this module returns.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from collections.abc import Callable, Sequence
from contextlib import closing
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath

_LETTERS = tuple("ABCDEFGHIJKLMNOPQRSTUVWXYZ")


class _Node:
    """One directory in the track-folder trie."""

    def __init__(self) -> None:
        """Start an empty directory node."""
        self.children: dict[str, _Node] = {}
        self.terminal = False


def collapse_track_folders(directories: Sequence[PurePath]) -> list[PurePath]:
    """Collapse album folders to the shared music folder on each volume.

    Paths on different drives, and macOS paths under different
    ``/Volumes`` names, stay separate. A branch at the volume root becomes
    one folder per child, so the result is not the computer root.

    Args:
        directories: Parent folders of tracks. Missing folders are kept
            here; the caller drops a folder that is not on disk.

    Returns:
        One path per collapsed music folder, sorted by the path text.
    """
    groups: dict[str, list[PurePath]] = {}
    for directory in directories:
        prefix = _volume_prefix(directory)
        groups.setdefault(str(prefix), []).append(directory)
    found: list[PurePath] = []
    for members in groups.values():
        if not members:
            continue
        prefix = _volume_prefix(members[0])
        root = _Node()
        for directory in members:
            _insert(root, _relative_parts(directory, prefix))
        found.extend(_emit(root, prefix, at_anchor=True))
    return sorted(found, key=lambda item: str(item).casefold())


def serato_volumes(
    platform: str,
    *,
    volumes_root: Path,
    letters: Sequence[str] = _LETTERS,
    label_for: Callable[[Path], str] | None = None,
    is_dir: Callable[[Path], bool] | None = None,
    is_link: Callable[[Path], bool] | None = None,
) -> list[tuple[Path, str]]:
    """Return mounted drives that contain a ``_Serato_`` directory.

    Args:
        platform: ``darwin`` reads ``volumes_root``. ``win32`` checks
            ``letters``. Any other platform returns an empty list.
        volumes_root: Directory whose children are macOS volumes.
        letters: Windows drive letters, without a colon.
        label_for: Volume label for a mount. Defaults to the folder name
            or the Windows volume label.
        is_dir: Directory check. Defaults to :meth:`Path.is_dir`.
        is_link: Shortcut check. Defaults to :meth:`Path.is_symlink`.

    Returns:
        ``(mount, label)`` pairs. The label does not include the ``USB:``
        prefix. Shortcuts are skipped.
    """
    directory = is_dir or _safe_isdir
    link = is_link or _safe_islink
    names = label_for or volume_label
    if platform == "darwin":
        return _mac_volumes(volumes_root, directory, link, names)
    if platform == "win32":
        return _windows_volumes(letters, directory, link, names)
    return []


def name_roots(
    folders: Sequence[Path],
    drives: Sequence[tuple[Path, str]],
    *,
    exists: Callable[[Path], bool] | None = None,
) -> list[dict[str, str]]:
    """Name music folders and USB drives for the Files page.

    A folder whose name is ``Music`` in any case is labeled ``Music``.
    A drive is labeled ``USB:`` plus its volume label. The same path is
    listed once, and the drive name wins.

    Args:
        folders: Collapsed track folders.
        drives: Mounts from :func:`serato_volumes`.
        exists: Keeps a path when this returns true. Defaults to a real
            directory that is not a shortcut.

    Returns:
        ``name``, ``path``, and ``kind`` (``folder`` or ``drive``),
        folders first.
    """
    present = exists or _real_dir
    found: dict[str, dict[str, str]] = {}
    for folder in folders:
        if not present(folder):
            continue
        key = _path_key(folder)
        found[key] = {
            "name": _folder_label(folder),
            "path": _path_text(folder),
            "kind": "folder",
        }
    for mount, label in drives:
        if not present(mount):
            continue
        key = _path_key(mount)
        found[key] = {
            "name": f"USB: {_clean_label(label)}",
            "path": _path_text(mount),
            "kind": "drive",
        }
    return sorted(found.values(), key=lambda item: (item["kind"] != "folder", item["name"].casefold()))


def music_roots() -> list[dict[str, str]]:
    """Discover the roots for the open library and the mounted drives.

    Returns:
        The named roots. An unreadable library contributes no track
        folders. A platform other than macOS or Windows contributes no
        drives.
    """
    folders = [Path(item) for item in collapse_track_folders(track_directories())]
    drives = serato_volumes(
        sys.platform,
        volumes_root=Path("/Volumes"),
        letters=_mounted_letters(),
    )
    return name_roots(folders, drives)


def _mounted_letters() -> tuple[str, ...]:
    """Return the Windows drive letters that are currently mounted.

    Returns:
        Letters from ``GetLogicalDrives`` on Windows, so an empty bay is
        not probed. Other platforms return every letter; volume discovery
        ignores them unless the platform is Windows.
    """
    if sys.platform != "win32":
        return _LETTERS
    try:
        import ctypes

        mask = int(ctypes.windll.kernel32.GetLogicalDrives())
    except (AttributeError, OSError, ValueError):
        return _LETTERS
    letters = tuple(chr(ord("A") + index) for index in range(26) if mask & (1 << index))
    return letters or _LETTERS


def track_directories() -> list[Path]:
    """Return the parent folder of each track path in ``master.sqlite``.

    Returns:
        Distinct parent folders. A missing library or a missing asset
        table returns an empty list.
    """
    import files
    import library

    try:
        connection = closing(library.read_conn())
    except library.LibraryError:
        return []
    found: list[Path] = []
    seen: set[str] = set()
    with connection as conn:
        try:
            rows = conn.execute(
                "SELECT portable_id FROM asset WHERE portable_id IS NOT NULL AND portable_id != ''"
            )
        except sqlite3.Error:
            return []
        for row in rows:
            portable = row[0]
            if not isinstance(portable, str) or not portable.strip():
                continue
            resolved = files.resolve_stored(portable)
            if resolved is None:
                continue
            parent = resolved.parent
            key = os.path.normcase(os.path.normpath(str(parent)))
            if key in seen:
                continue
            seen.add(key)
            found.append(parent)
    return found


def volume_label(path: Path) -> str:
    """Return the volume label for a mount.

    Args:
        path: Drive root or volume directory.

    Returns:
        The Windows volume label when the system reports one, otherwise
        the last path component or the drive letter.
    """
    if sys.platform == "win32":
        label = _windows_label(path)
        if label:
            return label
        letter = path.drive[:1] if path.drive else ""
        return letter or "Drive"
    return path.name or "Drive"


def _volume_prefix(directory: PurePath) -> PurePath:
    """Return the volume that owns ``directory``.

    Args:
        directory: A track folder.

    Returns:
        ``/Volumes/<name>`` for a macOS external volume, otherwise the
        drive anchor.
    """
    parts = directory.parts
    if directory.anchor == "/" and len(parts) >= 3 and parts[1] == "Volumes":
        return PurePosixPath("/Volumes") / parts[2]
    if directory.anchor:
        if isinstance(directory, PureWindowsPath):
            return PureWindowsPath(directory.anchor)
        return PurePosixPath(directory.anchor)
    return directory


def _relative_parts(directory: PurePath, prefix: PurePath) -> tuple[str, ...]:
    """Return the parts of ``directory`` below ``prefix``.

    Args:
        directory: Track folder.
        prefix: Volume prefix from :func:`_volume_prefix`.

    Returns:
        The remaining parts. An empty tuple means the tracks sit on the
        volume itself.
    """
    try:
        return directory.relative_to(prefix).parts
    except ValueError:
        return directory.parts[1:]


def _insert(node: _Node, parts: tuple[str, ...]) -> None:
    """Mark ``parts`` as a track folder in ``node``.

    Args:
        node: Trie root for one volume.
        parts: Path parts below the volume.
    """
    current = node
    if not parts:
        current.terminal = True
        return
    for part in parts:
        current = current.children.setdefault(part, _Node())
    current.terminal = True


def _emit(node: _Node, prefix: PurePath, *, at_anchor: bool) -> list[PurePath]:
    """Return collapsed folders under ``prefix``.

    Args:
        node: Trie node for ``prefix``.
        prefix: Directory this node represents.
        at_anchor: True when ``prefix`` is the volume root.

    Returns:
        Collapsed folders. A branch at the volume root is split so the
        computer root itself is not a result.
    """
    if len(node.children) == 1 and not node.terminal:
        name, child = next(iter(node.children.items()))
        return _emit(child, prefix / name, at_anchor=False)
    if at_anchor and node.children and not node.terminal:
        found: list[PurePath] = []
        for name, child in sorted(node.children.items(), key=lambda item: item[0].casefold()):
            found.extend(_emit(child, prefix / name, at_anchor=False))
        return found
    return [prefix]


def _mac_volumes(
    volumes_root: Path,
    is_dir: Callable[[Path], bool],
    is_link: Callable[[Path], bool],
    label_for: Callable[[Path], str],
) -> list[tuple[Path, str]]:
    """List macOS volumes that contain ``_Serato_``.

    Args:
        volumes_root: Usually ``/Volumes``.
        is_dir: Directory check.
        is_link: Shortcut check.
        label_for: Volume label.

    Returns:
        Mount and label pairs, sorted by label.
    """
    if is_link(volumes_root) or not is_dir(volumes_root):
        return []
    try:
        children = sorted(volumes_root.iterdir(), key=lambda item: item.name.casefold())
    except OSError:
        return []
    found: list[tuple[Path, str]] = []
    for child in children:
        if child.name.startswith("."):
            continue
        if is_link(child):
            continue
        marker = child / "_Serato_"
        if is_link(marker) or not is_dir(marker):
            continue
        found.append((child, _clean_label(label_for(child) or child.name)))
    return found


def _windows_volumes(
    letters: Sequence[str],
    is_dir: Callable[[Path], bool],
    is_link: Callable[[Path], bool],
    label_for: Callable[[Path], str],
) -> list[tuple[Path, str]]:
    """List Windows drives that contain ``_Serato_``.

    Args:
        letters: Drive letters without a colon.
        is_dir: Directory check.
        is_link: Shortcut check.
        label_for: Volume label.

    Returns:
        Drive root and label pairs.
    """
    found: list[tuple[Path, str]] = []
    for letter in letters:
        if len(letter) != 1 or not letter.isalpha():
            continue
        root = Path(f"{letter}:\\")
        marker = root / "_Serato_"
        if is_link(root) or is_link(marker) or not is_dir(marker):
            continue
        found.append((root, _clean_label(label_for(root) or letter)))
    return found


def _windows_label(path: Path) -> str:
    """Read a Windows volume label.

    Args:
        path: Drive root.

    Returns:
        The label, or an empty string when the system has none.
    """
    try:
        import ctypes

        buffer = ctypes.create_unicode_buffer(261)
        root = str(path)
        if not root.endswith("\\"):
            root += "\\"
        ok = ctypes.windll.kernel32.GetVolumeInformationW(root, buffer, 261, None, None, None, None, 0)
    except (AttributeError, OSError):
        return ""
    if not ok:
        return ""
    return buffer.value


def _folder_label(path: Path) -> str:
    """Return the name a DJ would use for a music folder.

    Args:
        path: Folder on disk.

    Returns:
        ``Music`` when the folder has that name, otherwise the folder name.
    """
    raw = path.name
    if raw.casefold() == "music":
        return "Music"
    cleaned = "".join(ch for ch in raw if ch.isprintable()).strip()
    if cleaned:
        return cleaned[:64]
    letter = path.drive[:1] if path.drive else ""
    return letter or "Folder"


def _clean_label(text: str) -> str:
    """Drop characters that do not belong in a folder name on screen.

    Args:
        text: Raw folder or volume name.

    Returns:
        A short printable label. An empty value becomes ``Drive``.
    """
    cleaned = "".join(ch for ch in text if ch.isprintable()).strip()
    if not cleaned:
        return "Drive"
    return cleaned[:64]


def _real_dir(path: Path) -> bool:
    """Return whether ``path`` is a real directory.

    Args:
        path: Candidate root.

    Returns:
        True when the path is a directory and not a shortcut.
    """
    try:
        return path.is_dir() and not path.is_symlink()
    except OSError:
        return False


def _safe_isdir(path: Path) -> bool:
    """Return whether ``path`` is a directory, ignoring OS errors.

    Args:
        path: Path to check.

    Returns:
        True when the path is a directory.
    """
    try:
        return path.is_dir()
    except OSError:
        return False


def _safe_islink(path: Path) -> bool:
    """Return whether ``path`` is a shortcut, ignoring OS errors.

    Args:
        path: Path to check.

    Returns:
        True when the path is a shortcut.
    """
    try:
        return path.is_symlink()
    except OSError:
        return False


def _path_key(path: Path) -> str:
    """Return a comparison key for a root path.

    Args:
        path: Folder or drive.

    Returns:
        The resolved path when it exists, otherwise the normalized text.
    """
    try:
        if path.exists() and not path.is_symlink():
            return os.path.normcase(os.path.normpath(str(path.resolve())))
    except OSError:
        pass
    return os.path.normcase(os.path.normpath(str(path)))


def _path_text(path: Path) -> str:
    """Return the path string stored in a root record.

    Args:
        path: Folder or drive.

    Returns:
        The resolved path when it exists, otherwise the path text.
    """
    try:
        if path.exists() and not path.is_symlink():
            return str(path.resolve())
    except OSError:
        pass
    return str(path)
