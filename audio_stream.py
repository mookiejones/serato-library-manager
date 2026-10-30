"""Stream one library audio file with HTTP Range requests.

The file that is opened is taken from the Serato library index. A request
path is only a lookup key: it is normalized with ``os.path.realpath`` and
must name a regular file already stored on an asset row. A path that is
not in that index, a path that climbs with ``..``, and a symlink are
refused before any audio bytes are read. The file is opened read-only and
is never locked. Nothing under the Serato library folder is written.
"""

from __future__ import annotations

import errno
import os
import re
import sqlite3
import stat
import threading
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
    ".flac": "audio/flac",
    ".wav": "audio/wav",
    ".aiff": "audio/aiff",
    ".aif": "audio/aiff",
    ".ogg": "audio/ogg",
    ".oga": "audio/ogg",
}

_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$", re.IGNORECASE)
_SPLIT = re.compile(r"[\\/]")

_index_lock = threading.Lock()
_cached_index: dict[str, Path] | None = None
_cached_token: tuple[int, int] | None = None


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
    """Drop the cached map of library audio paths.

    The next play rebuilds it from ``master.sqlite``. Called when the
    server drops its library cache, including at the end of a test.
    """
    global _cached_index, _cached_token
    with _index_lock:
        _cached_index = None
        _cached_token = None


def resolve_audio(
    *,
    asset_id: int | None,
    raw_path: str | None,
    space: str | None,
) -> AudioTarget:
    """Resolve a library id or a path to one real audio file.

    Args:
        asset_id: Asset id from the page. None when the request names a path.
        raw_path: Request path. Used only when ``asset_id`` is None. It is
            not opened. A relative path, a ``..`` segment, or a symlink is
            refused.
        space: Space that must contain the asset. None allows any space.
            Ignored for a path request: the path must still be in the index.

    Returns:
        The indexed file, its size, and its Content-Type.

    Raises:
        AudioRefusal: The request is malformed, the track is not in the
            library, or the path is outside the index.
        LibraryError: The database file is not there.
    """
    if asset_id is None and (raw_path is None or raw_path == ""):
        raise AudioRefusal("That request is not valid.", 400)
    if asset_id is not None:
        return _resolve_id(asset_id, space)
    if raw_path is None:
        raise AudioRefusal("That request is not valid.", 400)
    return _resolve_path(raw_path)


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
        OSError: The file cannot be opened for reading, including when it
            is a symlink at the moment of the open.
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


def indexed_path(real: Path) -> Path | None:
    """Return the indexed file for a real path, or None when it is outside.

    The value is the path stored from the asset row. It is not the request
    string, even when the two names are the same file. Removing this
    membership test is what lets a path outside the library through.

    Args:
        real: Normalized real path of the file the caller wants to open.

    Returns:
        The library path to open, or None when ``real`` is not indexed.
    """
    return _index().get(_key(real))


def _resolve_id(asset_id: int, space: str | None) -> AudioTarget:
    """Resolve one asset id through the library index.

    Args:
        asset_id: Asset id. A negative id is refused by the caller.
        space: Space that must contain the asset, or None for any space.

    Returns:
        The indexed audio file.

    Raises:
        AudioRefusal: The id is not in the library, or the stored path is
            missing or is a symlink.
        LibraryError: The database file is not there.
    """
    row = _asset_row(asset_id, space)
    if row is None:
        raise AudioRefusal("That track is not in the library.", 404)
    canonical = _canonical_library_file(row["portable_id"])
    if canonical is None:
        raise AudioRefusal("That track is not in the library.", 404)
    return _target_for(canonical)


def _resolve_path(raw: str) -> AudioTarget:
    """Resolve a request path through the library index.

    Args:
        raw: Path from the query string.

    Returns:
        The indexed audio file.

    Raises:
        AudioRefusal: The path is malformed, climbs out with ``..``, is a
            symlink, or is not in the library index.
    """
    _refuse_raw_path(raw)
    try:
        candidate = Path(raw)
        linked = candidate.is_symlink()
    except (OSError, ValueError) as exc:
        raise AudioRefusal("That track is not in the library.", 404) from exc
    if linked:
        raise AudioRefusal("That file is not in the library.", 403)
    try:
        real = Path(os.path.realpath(candidate))
    except (OSError, ValueError) as exc:
        raise AudioRefusal("That track is not in the library.", 404) from exc
    return _target_for(real)


def _refuse_raw_path(raw: str) -> None:
    """Refuse a path that is not a single absolute name.

    Args:
        raw: Path from the query string.

    Raises:
        AudioRefusal: A null, an empty path, a path that is too long, a
            relative path, or a ``..`` segment. The ``..`` refusal happens
            before ``realpath``, so a climb that lands on a library file
            is still refused.
    """
    if "\x00" in raw or len(raw) > 4096 or not raw.strip():
        raise AudioRefusal("That request is not valid.", 400)
    if _contains_traversal(raw) or not os.path.isabs(raw):
        raise AudioRefusal("That file is not in the library.", 403)


def _contains_traversal(raw: str) -> bool:
    """Return whether a path has a ``..`` segment.

    Args:
        raw: Path text. Slashes and backslashes both separate segments.

    Returns:
        True when a segment is exactly ``..``.
    """
    return ".." in _SPLIT.split(raw)


def _target_for(real: Path) -> AudioTarget:
    """Build a stream target when ``real`` is in the library index.

    Args:
        real: Normalized real path.

    Returns:
        The indexed file and its size.

    Raises:
        AudioRefusal: ``real`` is not in the index, or it is no longer a
            regular file.
    """
    indexed = indexed_path(real)
    if indexed is None:
        raise AudioRefusal("That file is not in the library.", 403)
    try:
        info = indexed.lstat()
    except OSError as exc:
        raise AudioRefusal("That track is not in the library.", 404) from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise AudioRefusal("That file is not in the library.", 403)
    return AudioTarget(path=indexed, size=info.st_size, media_type=content_type_for(indexed))


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


def _index() -> dict[str, Path]:
    """Return the real paths of playable library files, keyed for lookup.

    The map is cached until ``master.sqlite`` changes size or mtime, or
    until ``invalidate_index`` runs. Building it only reads the database
    and stats audio files.

    Returns:
        A map from ``normcase`` real path to the path that may be opened.

    Raises:
        LibraryError: The database file is not there.
    """
    global _cached_index, _cached_token
    token = _library_token()
    with _index_lock:
        if token is not None and token == _cached_token and _cached_index is not None:
            return _cached_index
    built = _build_index()
    with _index_lock:
        _cached_index = built
        _cached_token = token
        return built


def _library_token() -> tuple[int, int] | None:
    """Return the size and mtime of the open library file.

    Returns:
        ``(mtime_ns, size)``, or None when the file cannot be statted.
    """
    database = Path(library.MASTER)
    try:
        info = database.stat()
    except OSError:
        return None
    return (info.st_mtime_ns, info.st_size)


def _build_index() -> dict[str, Path]:
    """Read asset paths and keep the regular files.

    A symlink stored as a portable id is left out, so following it cannot
    add a file outside the path Serato recorded.

    Returns:
        The index map. Empty when the database has no playable files.

    Raises:
        LibraryError: The database file is not there.
    """
    with closing(library.read_conn()) as conn:
        rows = conn.execute("SELECT portable_id FROM asset").fetchall()
    index: dict[str, Path] = {}
    for row in rows:
        canonical = _canonical_library_file(row["portable_id"])
        if canonical is None:
            continue
        index[_key(canonical)] = canonical
    return index


def _canonical_library_file(portable_id: object) -> Path | None:
    """Resolve one stored portable id to a real regular file.

    Args:
        portable_id: Value from the asset row.

    Returns:
        The real path, or None when it is empty, missing, or a symlink.
    """
    if not isinstance(portable_id, str) or not portable_id or "\x00" in portable_id:
        return None
    raw = Path(portable_id)
    # Relative ids are tried under the home directory first, then at the
    # filesystem root. An absolute id is used as stored. This matches
    # library._resolved so a file the detail pane can see can be played.
    candidates = [raw] if raw.is_absolute() else [Path.home() / portable_id, Path("/") / portable_id]
    for candidate in candidates:
        try:
            if candidate.is_symlink() or not candidate.is_file():
                continue
            real = Path(os.path.realpath(candidate))
            if real.is_symlink() or not real.is_file():
                continue
            return real
        except (OSError, ValueError):
            continue
    return None


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
        OSError: The path is a symlink, or it cannot be opened read-only.
    """
    if os.path.islink(path):
        raise OSError(errno.ELOOP, "That file is not in the library.")
    flags = os.O_RDONLY
    if os.name == "nt":
        flags |= os.O_BINARY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    fd = os.open(os.fspath(path), flags)
    return os.fdopen(fd, "rb", buffering=0)
