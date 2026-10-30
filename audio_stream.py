"""Stream one library audio file with HTTP Range requests.

The request may name a track only by its library id. The id is read from
the raw query string and must be decimal digits, so a path, a ``..``
segment, or a percent-encoded id is refused before the database is
opened. The stored path is resolved with ``os.path.realpath``. It must be
a regular audio file. Playback is allowed when that real path sits inside
a music root (each root is realpath'd too) or when it is exactly the
file the library row names. A file symlink is refused when its real path
leaves the directory that row names, even if that outside folder was
listed as a music root. A music folder that is itself a symlink still
plays, including when it points at another disk. The file is
opened read-only, in chunks, and nothing under the Serato folder is written.
"""

from __future__ import annotations

import os
import re
import sqlite3
import stat
from collections.abc import Iterator
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import library

# One read is this many bytes. The handler never asks for the whole file.
CHUNK = 64 * 1024

_CONTENT_TYPES = {
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".alac": "audio/mp4",
    ".flac": "audio/flac",
    ".wav": "audio/wav",
    ".aiff": "audio/aiff",
    ".aif": "audio/aiff",
    ".ogg": "audio/ogg",
    ".oga": "audio/ogg",
}
_AUDIO_SUFFIXES = frozenset(_CONTENT_TYPES)
_TRACK_ID = re.compile(r"[0-9]{1,18}")

_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$", re.IGNORECASE)


class AudioRefusal(Exception):
    """A play request that must not open a file.

    Attributes:
        message: Sentence returned to the page. It does not include a path.
        status: HTTP status. 400 is a malformed request, 403 is outside the
            library index, and 404 is a track or file that is not there.
    """

    def __init__(self, message: str, status: int) -> None:
        """Store the message and HTTP status.

        Args:
            message: Sentence returned to the page.
            status: HTTP status code.
        """
        super().__init__(message)
        self.message = message
        self.status = status


@dataclass(frozen=True)
class AudioTarget:
    """One library file that may be streamed.

    Attributes:
        path: Real path of a regular file from the library index.
        size: Size in bytes from ``lstat``. Not the whole file.
        media_type: Content-Type for the file suffix.
    """

    path: Path
    size: int
    media_type: str


@dataclass(frozen=True)
class ByteRange:
    """The bytes a response will send.

    Attributes:
        status: 200 for the whole file, 206 for a slice, 416 when the
            Range header cannot be satisfied.
        start: First byte, inclusive. Zero when the status is 416.
        end: Last byte, inclusive. ``-1`` when the body is empty.
    """

    status: int
    start: int
    end: int


def content_type_for(path: Path) -> str:
    """Return the audio Content-Type for a file suffix.

    Args:
        path: Library file. The suffix is compared in lower case.

    Returns:
        A media type. An unknown suffix is ``application/octet-stream``.
    """
    return _CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")


def parse_range(header: str | None, size: int) -> ByteRange:
    """Parse one ``Range`` header against a file size.

    Args:
        header: The Range header, or None when the client wants the whole file.
        size: File size in bytes. A negative size is treated as empty.

    Returns:
        A 200 span for the whole file, a 206 span for one byte range, or
        416 when the range is missing, backwards, or past the end. The end
        of an open range is the last byte. An end past the file is clamped
        to the last byte. A suffix range (``bytes=-N``) keeps the last N
        bytes. More than one range is 416.
    """
    if size < 0:
        size = 0
    if header is None or header.strip() == "":
        if size == 0:
            return ByteRange(200, 0, -1)
        return ByteRange(200, 0, size - 1)
    text = header.strip()
    if "," in text:
        return ByteRange(416, 0, -1)
    match = _RANGE.match(text)
    if match is None or size == 0:
        return ByteRange(416, 0, -1)
    start_text, end_text = match.group(1), match.group(2)
    if start_text == "" and end_text == "":
        return ByteRange(416, 0, -1)
    if start_text == "":
        suffix = int(end_text)
        if suffix <= 0:
            return ByteRange(416, 0, -1)
        if suffix > size:
            suffix = size
        return ByteRange(206, size - suffix, size - 1)
    start = int(start_text)
    if start >= size:
        return ByteRange(416, 0, -1)
    if end_text == "":
        end = size - 1
    else:
        end = int(end_text)
        if end < start:
            return ByteRange(416, 0, -1)
        if end >= size:
            end = size - 1
    return ByteRange(206, start, end)


def invalidate_index() -> None:
    """Drop the cached music roots used to decide where a track may play.

    The next play reads the roots again. Called when the server drops its
    library cache, including at the end of a test.
    """
    import music_roots

    music_roots.invalidate()


def parse_track_id(raw_query: str) -> int:
    """Return the asset id from a raw query string.

    Args:
        raw_query: The query text from the request URL, still percent-encoded.
            ``parse_qs`` is not used, so ``%31`` is not turned into ``1``.

    Returns:
        The asset id.

    Raises:
        AudioRefusal: The id is missing, percent-encoded, double-encoded,
            or not a decimal integer. A ``..`` segment is in that last group.
    """
    if "\x00" in raw_query:
        raise AudioRefusal("That request is not valid.", 400)
    value: str | None = None
    for part in raw_query.split("&"):
        name, separator, item = part.partition("=")
        if name == "id" and separator:
            value = item
            break
    if value is None or value == "":
        raise AudioRefusal("That request is not valid.", 400)
    if "%" in value or "+" in value or _TRACK_ID.fullmatch(value) is None:
        raise AudioRefusal("That request is not valid.", 400)
    return int(value)


def resolve_audio(*, asset_id: int, space: str | None) -> AudioTarget:
    """Resolve one library id to a real audio file.

    Args:
        asset_id: Asset id that :func:`parse_track_id` already checked.
        space: Space that must contain the asset. None allows any space.

    Returns:
        The file to stream, its size, and its Content-Type.

    Raises:
        AudioRefusal: The id is not in the library, the stored path is not
            a regular audio file, or the resolved path is outside the
            music roots because a symlink carried it there.
        LibraryError: The database file is not there.
    """
    row = _asset_row(asset_id, space)
    if row is None:
        raise AudioRefusal("That track is not in the library.", 404)
    located = _locate(row["portable_id"])
    if located is None:
        raise AudioRefusal("That track is not in the library.", 404)
    nominal, real = located
    if not _is_regular_file(real):
        raise AudioRefusal("That file is not in the library.", 403)
    if real.suffix.lower() not in _AUDIO_SUFFIXES:
        raise AudioRefusal("That file is not in the library.", 403)
    if not library_allows(real, nominal):
        raise AudioRefusal("That file is not in the library.", 403)
    try:
        info = real.lstat()
    except OSError as exc:
        raise AudioRefusal("That track is not in the library.", 404) from exc
    if not stat.S_ISREG(info.st_mode):
        raise AudioRefusal("That file is not in the library.", 403)
    return AudioTarget(path=real, size=info.st_size, media_type=content_type_for(real))


def iter_bytes(path: Path, start: int, end: int, chunk_size: int = CHUNK) -> Iterator[bytes]:
    """Yield a slice of a library file in chunks.

    The file is opened read-only when iteration starts, not when this
    function is called. Each read is at most ``chunk_size`` bytes, so the
    whole file is never loaded.

    Args:
        path: Real path from the library index.
        start: First byte, inclusive.
        end: Last byte, inclusive. An end before start yields nothing.
        chunk_size: Maximum bytes per read. Defaults to ``CHUNK``.

    Yields:
        The next chunk. The concatenation is the requested slice.

    Raises:
        OSError: The file cannot be opened for reading.
    """
    length = 0 if end < start else end - start + 1
    handle = _open_read(path)
    try:
        if length and start:
            handle.seek(start)
        remaining = length
        while remaining > 0:
            block = handle.read(min(chunk_size, remaining))
            if not block:
                break
            remaining -= len(block)
            yield block
    finally:
        handle.close()


def library_allows(real: Path, nominal: Path) -> bool:
    """Return whether a resolved library file may be opened.

    Args:
        real: ``os.path.realpath`` of the stored path. This is the file
            that would be read.
        nominal: Absolute stored path before that resolution. A symlink
            leaf stays a symlink here.

    Returns:
        True when ``real`` is inside a realpath'd music root, or when it
        is exactly the file the library row names. A file symlink whose
        real path leaves the directory that row names is False either
        way, including when root discovery followed the link and listed
        the outside folder. Returning True for every call is what lets
        that shortcut through. A music folder that is itself a symlink
        still returns True, because ``realpath`` of its parent contains
        the file.
    """
    # Checked before the music-root test. On Windows, root discovery can
    # follow a file symlink and treat the outside folder as a root.
    if _left_stored_directory(nominal, real):
        return False
    roots = _music_root_reals()
    if _inside_any(real, roots):
        return True
    try:
        named = Path(os.path.realpath(nominal))
    except OSError:
        return False
    return _key(real) == _key(named)


def _asset_row(asset_id: int, space: str | None) -> sqlite3.Row | None:
    """Read one asset row with a read-only connection.

    Args:
        asset_id: Asset id.
        space: Space name, or None to allow any space.

    Returns:
        The row, or None when the id is not in that space.

    Raises:
        LibraryError: The database file is not there.
    """
    with closing(library.read_conn()) as conn:
        if space is None:
            return conn.execute(
                "SELECT id, portable_id FROM asset WHERE id = ?",
                (asset_id,),
            ).fetchone()
        return conn.execute(
            """
            SELECT a.id, a.portable_id
            FROM asset a
            JOIN space_asset sa ON sa.asset_id = a.id
            JOIN space s ON s.id = sa.space_id
            WHERE a.id = ? AND s.name = ?
            """,
            (asset_id, space),
        ).fetchone()


def _locate(portable_id: object) -> tuple[Path, Path] | None:
    """Resolve a stored portable id to a nominal path and its real path.

    Args:
        portable_id: Value from the asset row.

    Returns:
        The absolute stored path and ``os.path.realpath`` of that path.
        None when the id is empty or no candidate exists. A symlink is
        kept as the nominal path so a later check can see that it was followed.
    """
    if not isinstance(portable_id, str) or not portable_id or "\x00" in portable_id:
        return None
    raw = Path(portable_id)
    # Relative ids are tried under the home directory first, then at the
    # filesystem root. An absolute id is used as stored.
    candidates = [raw] if raw.is_absolute() else [Path.home() / portable_id, Path("/") / portable_id]
    for candidate in candidates:
        try:
            if not candidate.exists():
                continue
            nominal = candidate if candidate.is_absolute() else candidate.absolute()
            real = Path(os.path.realpath(nominal))
            if not real.exists():
                continue
            return nominal, real
        except (OSError, ValueError):
            continue
    return None


def _is_regular_file(path: Path) -> bool:
    """Return whether ``path`` is a regular file and not a directory.

    Args:
        path: Real path.

    Returns:
        True when ``lstat`` reports a regular file.
    """
    try:
        info = path.lstat()
    except OSError:
        return False
    return stat.S_ISREG(info.st_mode) and not stat.S_ISDIR(info.st_mode)


def _music_root_reals() -> list[Path]:
    """Return the real paths of the music roots that are on disk.

    Returns:
        One real directory per root. A missing root is skipped. A failure
        to read the roots is an empty list, so the exact-file check still
        decides.
    """
    import music_roots

    try:
        rows = music_roots.music_roots()
    except (OSError, library.LibraryError, sqlite3.Error):
        return []
    found: list[Path] = []
    for row in rows:
        if row.get("missing"):
            continue
        path = row.get("path")
        if not isinstance(path, str) or not path:
            continue
        try:
            real = Path(os.path.realpath(path))
            if real.is_dir():
                found.append(real)
        except OSError:
            continue
    return found


def _inside_any(child: Path, roots: list[Path]) -> bool:
    """Return whether ``child`` is one of ``roots`` or a file inside one.

    Args:
        child: Real path.
        roots: Real directories.

    Returns:
        True when a root contains ``child``. A sibling whose name only
        starts with the root name does not count.
    """
    for root in roots:
        if _inside(child, root):
            return True
    return False


def _inside(child: Path, root: Path) -> bool:
    """Return whether ``child`` is ``root`` or a path inside it.

    Args:
        child: Real path.
        root: Real directory.

    Returns:
        True when the normalized paths share ``root`` as their common path.
    """
    child_text = _key(child)
    root_text = _key(root)
    if child_text == root_text:
        return True
    try:
        return os.path.commonpath([child_text, root_text]) == root_text
    except ValueError:
        return False


def _left_stored_directory(nominal: Path, real: Path) -> bool:
    """Return whether the real file left the directory the library path names.

    ``realpath`` of the parent follows a directory symlink, so a music
    folder that points at another disk still contains the file. A file
    symlink is different: the parent stays the folder that holds the
    link, and the real file is elsewhere. That does not depend on
    ``is_symlink`` for the leaf.

    Args:
        nominal: Stored path. A symlink leaf stays a symlink.
        real: Real path of the file.

    Returns:
        True when ``real`` is outside ``realpath`` of the stored parent.
        An operating-system shortcut such as ``/tmp`` on macOS is followed
        for that parent, so the file remains inside the resolved folder.
    """
    try:
        holder = Path(os.path.realpath(nominal.parent))
    except OSError:
        return True
    return not _inside(real, holder)


def _key(path: Path) -> str:
    """Return the comparison key for a real path.

    Args:
        path: Absolute path.

    Returns:
        The path with case folded the way this operating system compares names.
    """
    return os.path.normcase(os.path.normpath(str(path)))


def _open_read(path: Path) -> BinaryIO:
    """Open a library file for reading, without creating or locking it.

    Args:
        path: Real path from the library index.

    Returns:
        A binary handle positioned at the start of the file. The caller
        closes it.

    Raises:
        OSError: The path cannot be opened read-only. ``O_NOFOLLOW`` refuses
            a last component that was replaced with a symlink after the check.
    """
    flags = os.O_RDONLY
    if os.name == "nt":
        flags |= os.O_BINARY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    fd = os.open(os.fspath(path), flags)
    return os.fdopen(fd, "rb", buffering=0)
