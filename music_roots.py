"""Music folders the Files page opens on.

Track folders in ``master.sqlite`` collapse to the shared music folder
(album folders under ``Music`` become ``Music``). Each mounted drive that
contains a ``_Serato_`` folder is added as well. macOS looks in
``/Volumes``. Windows checks drive letters. The browse guard lives in
``files.py`` and uses the paths this module returns.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import sys
import threading
import types
from collections.abc import Callable, Sequence
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath

_LETTERS = tuple("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
_cache_lock = threading.Lock()
_cache: tuple[tuple[object, ...], list[dict[str, object]], str] | None = None


class _Node:
    """One directory in the track-folder trie."""

    def __init__(self) -> None:
        """Start an empty directory node."""
        self.children: dict[str, _Node] = {}
        self.terminal = False


def collapse_track_folders(
    directories: Sequence[PurePath],
    *,
    home: PurePath | None = None,
) -> list[PurePath]:
    """Collapse album folders to the shared music folder on each volume.

    Paths on different drives, and macOS paths under different
    ``/Volumes`` names, stay separate. A branch is not widened to the
    home directory, ``/``, ``/Volumes``, or a drive root. ``~/Music`` and
    ``~/Downloads`` stay two roots.

    Args:
        directories: Parent folders of tracks. Missing folders are kept
            here; the caller marks a folder that is not on disk.
        home: Home directory that must not become a root by widening.
            Defaults to the current home directory.

    Returns:
        One path per collapsed music folder, sorted by the path text.
    """
    if home is None:
        home = Path.home()
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
        found.extend(_emit(root, prefix, at_anchor=True, home=home))
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
) -> list[dict[str, object]]:
    """Name each music folder and drive without repeating a label.

    The label is the folder or volume name. When two roots share that
    name, ``(parent)`` is added until the labels differ. A drive is not
    added again when a music folder on that drive is already a root. A
    folder that is not on disk is kept and marked missing.

    Args:
        folders: Collapsed track folders, including ones on an unmounted drive.
        drives: Mounts from :func:`serato_volumes`.
        exists: True when the path can be opened. Defaults to a real
            directory that is not a shortcut.

    Returns:
        ``name``, ``path``, ``kind`` (``folder`` or ``drive``), and
        ``missing``. Folders come first.
    """
    present = exists or _real_dir
    found: dict[str, dict[str, object]] = {}
    kept: list[Path] = []
    for folder in folders:
        key = _path_key(folder)
        if key in found:
            continue
        on_disk = bool(present(folder))
        found[key] = {
            "name": _folder_name(folder),
            "path": _path_text(folder) if on_disk else str(folder),
            "kind": "folder",
            "missing": not on_disk,
        }
        kept.append(folder)
    for mount, label in drives:
        if not present(mount):
            continue
        if _drive_already_listed(mount, kept):
            continue
        key = _real_key(mount)
        if key in found:
            continue
        found[key] = {
            "name": _clean_label(label) or _folder_name(mount),
            "path": _path_text(mount),
            "kind": "drive",
            "missing": False,
        }
    rows = list(found.values())
    _make_labels_unique(rows)
    return sorted(
        rows,
        key=lambda item: (item["kind"] != "folder", str(item["missing"]), str(item["name"]).casefold()),
    )


def invalidate() -> None:
    """Drop the cached music roots.

    The next read computes them again. A change to ``master.sqlite`` or
    its WAL does not do this by itself. Callers use this, or
    ``refresh=1``, when the drives should be read again.
    """
    global _cache
    with _cache_lock:
        _cache = None


def cache_stamp() -> tuple[object, ...]:
    """Return a stamp for the library path index, not the root cache.

    The root list ignores this stamp. Folder clicks still use it so the
    in-library marks can notice a database write without listing roots again.

    Returns:
        The master database path and modification times, plus the
        settings file time. A missing file contributes 0.
    """
    import app_config
    import library

    master = Path(library.MASTER)
    stamps: list[int] = []
    for candidate in (master, Path(str(master) + "-wal"), Path(str(master) + "-shm")):
        try:
            stamps.append(candidate.stat().st_mtime_ns if candidate.exists() else 0)
        except OSError:
            stamps.append(0)
    settings = app_config.settings_path()
    try:
        settings_stamp = settings.stat().st_mtime_ns if settings.exists() else 0
    except OSError:
        settings_stamp = 0
    return (str(master), tuple(stamps), settings_stamp)


def _load_cached(*, refresh: bool) -> tuple[list[dict[str, object]], str]:
    """Return the cached roots and the time they were computed.

    The lock covers the check and the compute, so concurrent misses run
    ``_discover`` once. ``refresh`` replaces that cache.

    Args:
        refresh: When true, drop the cache and read the library again.

    Returns:
        A copy of the root list and ``computed_at``.
    """
    global _cache
    with _cache_lock:
        if refresh:
            _cache = None
        if _cache is None:
            found = tuple(types.MappingProxyType(dict(item)) for item in _discover())
            _cache = (found, _computed_at())
        rows, computed = _cache
        return [dict(item) for item in rows], computed


def music_roots(*, refresh: bool = False) -> list[dict[str, object]]:
    """Discover the roots for the open library and the mounted drives.

    The result stays cached until :func:`invalidate` or ``refresh``.
    Writing ``master.sqlite`` or its WAL does not recompute it.

    Args:
        refresh: When true, ignore the cache and read the library again.

    Returns:
        The named roots. An unreadable library contributes no track
        folders. A platform other than macOS or Windows contributes no
        drives. An unmounted track folder is included with ``missing`` true.
    """
    rows, _computed = _load_cached(refresh=refresh)
    return rows


def library_roots(*, refresh: bool = False) -> dict[str, object]:
    """Return the Files roots in the public library-roots shape.

    The list is the same cache as :func:`music_roots`, read in one locked
    step with ``computed_at``.

    Args:
        refresh: When true, ignore the cache and read the library again.

    Returns:
        ``roots`` and ``computed_at``. Each root has ``id``, ``path``,
        ``label``, ``detail``, ``kind``, ``serato``, ``removable``, and
        ``missing``. ``id`` is the SHA-256 of the real path. ``kind`` is
        ``music_library`` for a folder taken from the Serato library,
        ``serato_drive`` for a drive, or ``user_folder``.
    """
    rows, computed = _load_cached(refresh=refresh)
    return {"roots": [to_library_root(item) for item in rows], "computed_at": computed}


def to_library_root(item: dict[str, object]) -> dict[str, object]:
    """Map one discovered root onto the library-roots contract.

    Args:
        item: A root from :func:`name_roots` or :func:`music_roots`.

    Returns:
        The public root. ``label`` is the distinct name. ``detail`` is
        the path shown under it.
    """
    path = str(item.get("path") or "")
    kind = _public_kind(item)
    return {
        "id": root_id(path),
        "path": path,
        "label": str(item.get("name") or path or "Folder"),
        "detail": _display_path(path),
        "kind": kind,
        "serato": kind != "user_folder",
        "removable": _removable(path),
        "missing": bool(item.get("missing")),
    }


def root_id(path: str) -> str:
    """Return a stable id for one real root path.

    Args:
        path: Resolved path when the folder is on disk, otherwise the
            path text that was stored.

    Returns:
        The hex SHA-256 of the normalized path.
    """
    key = os.path.normcase(os.path.normpath(path))
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _computed_at() -> str:
    """Return the UTC time a root list was read.

    Returns:
        An ISO-8601 timestamp with a ``Z`` suffix.
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _public_kind(item: dict[str, object]) -> str:
    """Classify a discovered root for the library-roots contract.

    A folder found from tracks in the Serato library is
    ``music_library`` even when it is not named Music. A mounted
    ``_Serato_`` drive is ``serato_drive``. Anything else is a
    ``user_folder``.

    Args:
        item: A root from :func:`name_roots`.

    Returns:
        ``music_library``, ``serato_drive``, or ``user_folder``.
    """
    raw = item.get("kind")
    if raw in {"drive", "serato_drive"}:
        return "serato_drive"
    if raw == "user_folder":
        return "user_folder"
    if raw == "folder":
        return "music_library"
    return "user_folder"


def _path_pure(path: str) -> PurePath:
    """Return a Windows or POSIX pure path, including UNC shares.

    Args:
        path: Root path text.

    Returns:
        ``PureWindowsPath`` for a drive letter or a ``\\\\server\\share``
        path. Other paths stay POSIX.
    """
    if path.startswith("\\\\") or path.startswith("//"):
        return PureWindowsPath(path)
    if len(path) >= 2 and path[1] == ":":
        return PureWindowsPath(path)
    return PurePosixPath(path)


def _removable(path: str) -> bool:
    """Return whether ``path`` sits on a volume other than the home drive.

    Args:
        path: Root path.

    Returns:
        True for a macOS ``/Volumes/<name>`` path, a UNC share, and a
        Windows drive that is not the home drive.
    """
    pure = _path_pure(path)
    parts = pure.parts
    for index, part in enumerate(parts):
        if part == "Volumes" and index + 1 < len(parts):
            return True
    if path.startswith("\\\\") or path.startswith("//"):
        return True
    if pure.drive:
        home_drive = PureWindowsPath(str(Path.home())).drive
        return os.path.normcase(pure.drive) != os.path.normcase(home_drive)
    return False


def _discover() -> list[dict[str, object]]:
    """Read track folders and mounted drives.

    Returns:
        The named roots, uncached.
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
    except (library.LibraryError, sqlite3.Error, OSError):
        return []
    found: list[Path] = []
    seen: set[str] = set()
    try:
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
    except (sqlite3.Error, OSError):
        return []
    return found


def volume_label(path: Path) -> str:
    """Return the volume label for a mount.

    Args:
        path: Drive root or volume directory.

    Returns:
        The Windows volume label for a drive root, otherwise the last
        path component. A drive root with no label uses its letter.
    """
    if sys.platform == "win32" and path.drive and path.parent == path:
        label = _windows_label(path)
        if label:
            return label
        letter = path.drive[:1]
        return letter or "Drive"
    return path.name or "Drive"


def _volume_prefix(directory: PurePath) -> PurePath:
    """Return the volume that owns ``directory``.

    A ``Volumes/<name>`` path is its own volume even when it is not at
    the filesystem root. Other paths use the drive anchor.

    Args:
        directory: A track folder.

    Returns:
        The volume directory, or the drive anchor when the path is not
        on a named volume.
    """
    parts = directory.parts
    for index, part in enumerate(parts):
        if part == "Volumes" and index + 1 < len(parts):
            return directory.__class__(*parts[: index + 2])
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


def _emit(node: _Node, prefix: PurePath, *, at_anchor: bool, home: PurePath) -> list[PurePath]:
    """Return collapsed folders under ``prefix``.

    Args:
        node: Trie node for ``prefix``.
        prefix: Directory this node represents.
        at_anchor: True when ``prefix`` is the volume root.
        home: Home directory that must not be used as a widened root.

    Returns:
        Collapsed folders. A branch at the volume root, at home, at
        ``/``, or at ``/Volumes`` is split so that ancestor is not a root
        unless tracks live in it and it has no child folders.
    """
    if len(node.children) == 1 and not node.terminal:
        name, child = next(iter(node.children.items()))
        return _emit(child, prefix / name, at_anchor=False, home=home)
    widen = bool(node.children) and (at_anchor or _forbidden(prefix, home)) and not node.terminal
    if widen:
        found: list[PurePath] = []
        for name, child in sorted(node.children.items(), key=lambda item: item[0].casefold()):
            found.extend(_emit(child, prefix / name, at_anchor=False, home=home))
        return found
    if node.children and _forbidden(prefix, home):
        found = [prefix] if node.terminal else []
        for name, child in sorted(node.children.items(), key=lambda item: item[0].casefold()):
            found.extend(_emit(child, prefix / name, at_anchor=False, home=home))
        return found
    return [prefix]


def _forbidden(path: PurePath, home: PurePath) -> bool:
    """Return whether ``path`` must not be a widened root.

    Args:
        path: Candidate common ancestor.
        home: Home directory.

    Returns:
        True for home, ``/``, ``/Volumes``, and a drive root.
    """
    text = _norm(path)
    blocked = {
        _norm(PurePosixPath("/")),
        _norm(PurePosixPath("/Volumes")),
        _norm(home),
    }
    anchor = path.anchor
    if anchor:
        blocked.add(_norm(type(path)(anchor)))
    return text in blocked


def _norm(path: PurePath) -> str:
    """Return a comparison key for a pure path.

    Args:
        path: Path to normalize.

    Returns:
        The normcase, normpath text.
    """
    return os.path.normcase(os.path.normpath(str(path)))


def _folder_name(path: Path) -> str:
    """Return the folder or drive name used as a root label.

    Args:
        path: Music folder or drive root.

    Returns:
        The last path component, or the drive letter when the path is a
        drive root with no folder name.
    """
    text = path.name or (path.drive[:1] if path.drive else "")
    return _clean_label(text or "Folder")


def _display_path(path: str) -> str:
    """Return ``path`` with slashes a person can read.

    Args:
        path: Stored root path.

    Returns:
        The same path with backslashes shown as slashes.
    """
    return path.replace("\\", "/")


def _label_with_parents(path: Path, depth: int) -> str:
    """Return the folder name plus ``depth`` ancestor names.

    Args:
        path: Root path.
        depth: How many parents to include. Zero is the folder name.

    Returns:
        ``Music`` or ``Music (a/x)`` once parents are needed.
    """
    name = _folder_name(path)
    if depth <= 0:
        return name
    bits: list[str] = []
    current = path
    for _ in range(depth):
        parent = current.parent
        if parent == current:
            break
        bit = parent.name or (parent.drive.rstrip("\\/") if parent.drive else "")
        if not bit:
            break
        bits.append(bit)
        current = parent
    if not bits:
        return name
    return f"{name} ({'/'.join(reversed(bits))})"


def _make_labels_unique(rows: list[dict[str, object]]) -> None:
    """Rewrite ``name`` so two roots do not share a label.

    Args:
        rows: Root dicts. Each ``name`` starts as the folder or volume
            name. A clash gains ``(parent)``, then the next parent, until
            the labels differ.
    """
    paths = [Path(str(item.get("path") or "")) for item in rows]
    labels = [str(item.get("name") or _folder_name(path)) for item, path in zip(rows, paths)]
    depth = 0
    while depth < 64:
        counts: dict[str, int] = {}
        for label in labels:
            key = label.casefold()
            counts[key] = counts.get(key, 0) + 1
        if all(count == 1 for count in counts.values()):
            break
        depth += 1
        for index, path in enumerate(paths):
            if counts[labels[index].casefold()] == 1:
                continue
            labels[index] = _label_with_parents(path, depth)
    for item, label in zip(rows, labels):
        item["name"] = label


def _real_key(path: Path) -> str:
    """Return the resolved comparison key for a drive or folder.

    Args:
        path: Path that may be a shortcut.

    Returns:
        The normcase text of the real path. A path that cannot be
        resolved uses its normalized text.
    """
    try:
        return os.path.normcase(os.path.normpath(str(path.resolve())))
    except OSError:
        return os.path.normcase(os.path.normpath(str(path)))


def _key_contains(child: str, parent: str) -> bool:
    """Return whether ``child`` is ``parent`` or a path inside it.

    Args:
        child: Normalized path text.
        parent: Normalized path text.

    Returns:
        True when ``parent`` is a prefix of ``child`` on the same drive.
    """
    try:
        return os.path.commonpath([child, parent]) == parent
    except ValueError:
        return False


def _display_name(path: Path, drives: Sequence[tuple[Path, str]]) -> str:
    """Return ``volume · /path`` for one root.

    Args:
        path: Music folder or drive root.
        drives: Mounted drives and their labels.

    Returns:
        A label that stays distinct when several folders are named Music.
    """
    parts = path.parts
    for index, part in enumerate(parts):
        if part != "Volumes" or index + 1 >= len(parts):
            continue
        volume = parts[index + 1]
        rest = parts[index + 2 :]
        shown = "/" + "/".join(rest) if rest else "/"
        return f"{volume} · {shown}"
    for mount, label in drives:
        if _path_contains(path, mount):
            return f"{_clean_label(label)} · {_relative_display(path, mount)}"
    home = Path.home()
    if _path_contains(path, home):
        return f"Home · {_relative_display(path, home)}"
    parent = path.parent.name or (path.drive[:1] if path.drive else "Folder")
    return f"{parent} · /{path.name}" if path.name else f"{parent} · /"


def _relative_display(path: Path, root: Path) -> str:
    """Return ``path`` below ``root`` with a leading slash.

    Args:
        path: Folder to label.
        root: Volume or home directory that contains it.

    Returns:
        ``/`` when the folder is the root, otherwise ``/Music`` style text.
    """
    try:
        if path.exists() and root.exists() and not path.is_symlink() and not root.is_symlink():
            relative = path.resolve().relative_to(root.resolve())
        else:
            relative = path.relative_to(root)
    except (OSError, ValueError):
        return "/" + path.name if path.name else "/"
    if not relative.parts:
        return "/"
    return "/" + relative.as_posix()


def _path_contains(path: Path, root: Path) -> bool:
    """Return whether ``path`` is ``root`` or a folder inside it.

    Args:
        path: Candidate folder.
        root: Possible ancestor. A missing path is compared as text.

    Returns:
        True when the text of ``path`` stays inside ``root``.
    """
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _drive_already_listed(mount: Path, folders: Sequence[Path]) -> bool:
    """Return whether a music folder already represents this drive.

    Args:
        mount: Drive root from :func:`serato_volumes`.
        folders: Collapsed track folders.

    Returns:
        True when one of those folders is on the drive, so a second USB
        row would be a duplicate.
    """
    mount_key = _real_key(mount)
    for folder in folders:
        folder_key = _real_key(folder)
        if _key_contains(folder_key, mount_key) or _key_contains(mount_key, folder_key):
            return True
    return False


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
