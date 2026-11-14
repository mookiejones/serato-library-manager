"""Read extra Serato views and write the library when Serato DJ Pro is quit.

master.sqlite is the library Serato and this app display. root.sqlite is the
on-disk location database and is updated to match, when it is connected.
Writes are refused while Serato's lock is held by a live process. The first
write in a process copies the databases, and each present drive's ``_Serato_``
folder, into Library/Backups first. An unplugged or unreadable drive is
recorded and skipped. ``Recording`` and ``DJ Sessions`` are not copied.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Protocol, cast
from urllib.parse import quote, unquote, urlparse

import app_log
import snapshot_frames
import telemetry
from tags import SeratoTags, read_serato_tags


def default_library_path() -> Path:
    """Return the Serato master database for this operating system.

    Returns:
        On Windows, master.sqlite under %LOCALAPPDATA%\\Serato\\Library.
        On macOS and other systems, master.sqlite under Application Support.
    """
    # Windows keeps the library under %LOCALAPPDATA%. macOS uses
    # ~/Library/Application Support. Other hosts follow the macOS path.
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        base = Path(local) if local else Path.home() / "AppData" / "Local"
        return base / "Serato" / "Library" / "master.sqlite"
    return Path.home() / "Library/Application Support/Serato/Library/master.sqlite"


def file_manager_name() -> str:
    """Return the name of the host file manager.

    Returns:
        Finder on macOS, File Explorer on Windows, and file manager elsewhere.
    """
    if sys.platform == "win32":
        return "File Explorer"
    if sys.platform == "darwin":
        return "Finder"
    return "file manager"


LIVE_MASTER = default_library_path()
MASTER = LIVE_MASTER
# Serato stores a crate's visible name and a unique suffix in one column,
# split by this private-use character. display_name keeps the text before it.
NAME_SPLIT = "\U00105e8a"
LIBRARY_SPACE = "Serato Library"
ALLOWED_SPACES = ("Serato Library", "Serato Video", "Apple Music", "Prepare")

TEXT_FIELDS = {
    "name",
    "artist",
    "album",
    "genre",
    "year",
    "composer",
    "remixer",
    "label",
    "grouping",
    "comments",
    "key",
    "emoji",
}
TRACK_FIELDS = TEXT_FIELDS | {"bpm", "color", "rating", "is_beatgrid_locked", "portable_id"}
NORM_FIELDS = {
    "file_name",
    "name",
    "artist",
    "album",
    "genre",
    "comments",
    "label",
    "remixer",
    "grouping",
    "composer",
    "year",
    "key",
}

_KEY_VALUES = {
    "g#m": 0, "abm": 0, "1a": 0,
    "ebm": 1, "d#m": 1, "2a": 1,
    "bbm": 2, "a#m": 2, "3a": 2,
    "fm": 3, "4a": 3,
    "cm": 4, "5a": 4,
    "gm": 5, "6a": 5,
    "dm": 6, "7a": 6,
    "am": 7, "8a": 7,
    "em": 8, "9a": 8,
    "bm": 9, "10a": 9,
    "f#m": 10, "gbm": 10, "11a": 10,
    "c#m": 11, "dbm": 11, "12a": 11,
    "b": 12, "1b": 12,
    "f#": 13, "gb": 13, "2b": 13,
    "c#": 14, "db": 14, "3b": 14,
    "g#": 15, "ab": 15, "4b": 15,
    "d#": 16, "eb": 16, "5b": 16,
    "a#": 17, "bb": 17, "6b": 17,
    "f": 18, "7b": 18,
    "c": 19, "8b": 19,
    "g": 20, "9b": 20,
    "d": 21, "10b": 21,
    "a": 22, "11b": 22,
    "e": 23, "12b": 23,
}

_backed_up: set[str] = set()
# Drive ids whose ``_Serato_`` folder was copied for one master path.
# A drive that was absent, read-only, or unreadable is not listed, so a
# later call tries it again. ``_backup_guard`` covers both sets for the
# whole copy, so two writes cannot publish the same drive twice or drop an id.
_copied_drives: dict[str, set[str]] = {}
_backup_guard = threading.Lock()

# Fixed sentences. error_codes maps the same text to a stable code.
BACKUP_NO_SPACE = "There is not enough disk space to back up the library."
BACKUP_SERATO_RUNNING = (
    "Quit Serato DJ Pro before backing up drive crates. "
    "Serato DJ is still running, so nothing was copied."
)
# Room for drives.json, the COMPLETE marker, and directory entries.
BACKUP_SPACE_MARGIN = 1024 * 1024
DRIVES_MANIFEST = "drives.json"


def _as_int(value: object) -> int:
    """Convert a SQLite or JSON number the way int() does.

    Args:
        value: A number or numeric text.

    Returns:
        The integer value. bool becomes 0 or 1.

    Raises:
        TypeError: If value is not a number or text.
        ValueError: If text is not an integer.
    """
    if isinstance(value, int):
        return int(value)
    if isinstance(value, (float, str, bytes, bytearray)):
        return int(value)
    raise TypeError(
        "int() argument must be a string, a bytes-like object or a real number, not "
        f"{type(value).__name__}"
    )


def _as_float(value: object) -> float:
    """Convert a SQLite or JSON number the way float() does.

    Args:
        value: A number or numeric text.

    Returns:
        The float value.

    Raises:
        TypeError: If value is not a number or text.
        ValueError: If text is not a float.
    """
    if isinstance(value, (int, float, str, bytes, bytearray)):
        return float(value)
    raise TypeError(
        "float() argument must be a string or a real number, not "
        f"{type(value).__name__}"
    )


from serato_web.completeness import CompletenessError


class LibraryError(CompletenessError):
    """Raised when a library request cannot be completed.

    Attributes:
        message: Text returned to the page.
        status: HTTP status for that failure. Defaults to 400.
        code: Stable ``error.<code>`` key when the page should translate
            a parameterized sentence. None for a fixed English sentence
            that ``error_codes.with_code`` already maps.
        params: Placeholder values for ``code``. None when unused.
    """
    def __init__(
        self,
        message: str,
        status: int = 400,
        *,
        code: str | None = None,
        params: Mapping[str, str] | None = None,
    ):
        """Store the message, HTTP status, and optional catalog fields.

        Args:
            message: Text returned to the page.
            status: HTTP status. Defaults to 400.
            code: Catalog key for a parameterized notice.
            params: Placeholder values for that key.
        """
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
        self.params = dict(params) if params else None

    def to_json(self) -> dict[str, object]:
        """Return the JSON object the page reads for this failure.

        Returns:
            ``error``, ``serato`` (None unless a subclass set ``info``),
            and ``code`` / ``params`` when those were stored.
        """
        body: dict[str, object] = {
            "error": self.message,
            "serato": getattr(self, "info", None),
        }
        if self.code:
            body["code"] = self.code
            if self.params:
                body["params"] = dict(self.params)
        return body


class SeratoOpen(LibraryError):
    """Raised when Serato DJ Pro still holds the library lock.

    The HTTP status is 409. info is the status() payload.
    """
    def __init__(self, info: dict[str, object]):
        """Build a lock error from a status payload.

        Args:
            info: Dict from status() with a message key.
        """
        super().__init__(cast(str, info["message"]), 409)
        self.info = info


def serato_str_norm(value: object) -> str | None:
    """Normalize text the way Serato smart crates compare strings.

    Args:
        value: A field value.

    Returns:
        The lowercased text, or None when value is None.

    Example:
        >>> serato_str_norm("Ab")
        'ab'
    """
    if value is None:
        return None
    return str(value).lower()


def serato_key_type(value: object) -> int:
    """Map a key name to Serato's integer key type.

    Args:
        value: A Camelot or traditional key, or None.

    Returns:
        The integer key, or -1 when the name is empty or unknown.

    Example:
        >>> serato_key_type("1A")
        0
        >>> serato_key_type(None)
        -1
    """
    if value is None:
        return -1
    text = str(value).strip().lower()
    if not text:
        return -1
    return _KEY_VALUES.get(text, -1)


def register(conn: sqlite3.Connection) -> None:
    """Install Serato comparison functions on a SQLite connection.

    Args:
        conn: Connection that will run smart-crate SQL.
    """
    conn.create_function("serato_str_norm", 1, serato_str_norm, deterministic=True)
    conn.create_function("serato_raw_key_string_to_key_type", 1, serato_key_type, deterministic=True)


def read_conn(path: Path | None = None) -> sqlite3.Connection:
    """Open a read-only connection to a Serato database.

    Args:
        path: Database path. None selects MASTER.

    Returns:
        A connection with row access and query_only enabled.

    Raises:
        LibraryError: If the database file does not exist.
    """
    database = Path(path or MASTER)
    if not database.exists():
        raise LibraryError(f"Serato library not found at {database}", 404)
    # mode=ro rejects writes at the SQLite layer. query_only is a second guard.
    conn = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def is_serato_database(path: Path) -> bool:
    """Return whether a file is a Serato master database.

    Args:
        path: Candidate file. A missing file, a shortcut, or any other
            SQLite file is not a Serato library.

    Returns:
        True when a temporary copy has the ``asset``, ``container``, and
        ``space`` tables. The library folder is not opened as a database,
        so the check creates no ``-wal``, ``-shm``, or journal file there.
    """
    candidate = Path(path)
    try:
        if candidate.is_symlink() or not candidate.is_file():
            return False
        names = _serato_table_names(candidate)
    except (OSError, sqlite3.Error):
        return False
    return names == {"asset", "container", "space"}


def _serato_table_names(path: Path) -> set[str]:
    """Read Serato table names from a temporary copy.

    Args:
        path: ``master.sqlite`` to copy. It is not opened.

    Returns:
        Table names from the copy. The set is empty when the file has
        none of the three Serato tables.

    Raises:
        OSError: If the copy cannot be made.
        sqlite3.Error: If the copy cannot be read.
        LibraryError: If ``path`` is missing or a shortcut.

    The original folder is not opened as a database.
    """
    with copied_read_conn(path) as conn:
        rows = conn.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name IN ('asset', 'container', 'space')
            """
        ).fetchall()
    return {str(row[0]) for row in rows}


@contextmanager
def copied_read_conn(path: Path) -> Iterator[sqlite3.Connection]:
    """Open a read-only connection to a temporary copy of a library file.

    Args:
        path: ``master.sqlite`` to copy. A shortcut is refused.

    Yields:
        A connection to the copy, with row access and ``query_only`` on.

    Raises:
        LibraryError: If ``path`` is missing or a shortcut.
        OSError: If the copy cannot be made.
        sqlite3.Error: If the copy cannot be opened.

    ``master.sqlite`` and a real ``-wal`` file are copied into a temporary
    directory. The original folder is not opened. When no ``-wal`` file is
    copied, the copy is opened with ``immutable=1`` so a WAL-mode header
    cannot create ``-wal`` or ``-shm`` beside it. A ``-wal`` shortcut is
    not followed. Any sidecar SQLite creates stays in the temporary
    directory and is removed with it.
    """
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise LibraryError("That folder is not the Serato library on this computer.")
    wal = Path(str(source) + "-wal")
    copy_wal = wal.is_file() and not wal.is_symlink()
    with tempfile.TemporaryDirectory(prefix="serato-library-check-") as raw:
        root = Path(raw)
        copied = root / "master.sqlite"
        shutil.copyfile(source, copied)
        if copy_wal:
            shutil.copyfile(wal, root / "master.sqlite-wal")
        query = "mode=ro" if copy_wal else "mode=ro&immutable=1"
        conn = sqlite3.connect(_read_only_uri(copied, query), uri=True)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only=ON")
            yield conn
        finally:
            conn.close()


def _read_only_uri(path: Path, query: str) -> str:
    """Return a ``file:`` URI for a database path.

    Args:
        path: Database file. It is resolved before the URI is built.
        query: URI query, such as ``mode=ro`` or ``mode=ro&immutable=1``.

    Returns:
        An absolute ``file://`` URI. The path is escaped so a space cannot
        end the URI early.
    """
    posix = path.resolve().as_posix()
    # A drive letter needs an empty URI authority (file:///C:/...). Checking
    # the path, not sys.platform, still does that when a test has patched
    # the platform to linux while the file remains on a Windows drive.
    if len(posix) >= 2 and posix[1] == ":":
        posix = "/" + posix
    return "file://" + quote(posix, safe="/:") + "?" + query


def use_library_file(path: Path) -> None:
    """Point this process at an existing Serato database.

    Args:
        path: ``master.sqlite`` to read. It must already be a Serato
            library file, and it must not be a shortcut.

    Returns:
        None.

    Raises:
        LibraryError: If the path is not an absolute ``master.sqlite``
            file, is a shortcut, or is not a Serato library.

    The tables are read from a temporary copy. The library folder gains
    no ``-wal``, ``-shm``, or journal file, and no backup is taken,
    because the file is not changed.
    """
    global MASTER
    candidate = Path(path)
    if (
        not candidate.is_absolute()
        or candidate.name != "master.sqlite"
        or "\x00" in str(candidate)
    ):
        raise LibraryError("That folder is not the Serato library on this computer.")
    try:
        if candidate.is_symlink() or not candidate.is_file():
            raise LibraryError("That folder is not the Serato library on this computer.")
        if not is_serato_database(candidate):
            raise LibraryError("That folder is not the Serato library on this computer.")
        MASTER = candidate.resolve()
    except OSError as exc:
        raise LibraryError("That folder is not the Serato library on this computer.") from exc


def _process_is_serato(pid: int) -> bool:
    """Return whether a process id is a live Serato process.

    Args:
        pid: Process id from the lock table.

    Returns:
        True when the process image name contains serato.
    """
    if not pid or pid <= 0:
        return False
    if sys.platform == "win32":
        return _windows_process_is_serato(pid)
    return _unix_process_is_serato(pid)


def _unix_process_is_serato(pid: int) -> bool:
    """Return whether ps shows a Serato command for this process id.

    Args:
        pid: Process id from the lock table.

    Returns:
        True when ps reports a command name that contains serato. An error,
        a timeout, or a non-zero exit counts as running, so a write stops.
    """
    try:
        result = subprocess.run(
            ["ps", "-p", str(int(pid)), "-o", "comm="],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return True
    if result.returncode != 0:
        return True
    return "serato" in result.stdout.lower()


def _windows_process_is_serato(pid: int) -> bool:
    """Return whether tasklist shows a Serato image for this process id.

    Args:
        pid: Process id from the lock table.

    Returns:
        True when the tasklist image name contains serato. An error, a
        timeout, or a non-zero exit counts as running, so a write stops.
    """
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {int(pid)}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return True
    if result.returncode != 0:
        return True
    return "serato" in result.stdout.lower()


def _status_rows(conn: sqlite3.Connection) -> dict[str, object]:
    """Read the lock table and decide whether edits are allowed.

    Args:
        conn: Open database connection.

    Returns:
        A status dict with open, writable, pid, process, and message.

    Raises:
        sqlite3.OperationalError: If the lock query fails for a reason other than a missing table.
    """
    try:
        rows = conn.execute(
            "SELECT owner_process_id, owner_process_name FROM lock"
        ).fetchall()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            rows = []
        else:
            raise
    for row in rows:
        pid = int(row["owner_process_id"] or 0)
        name = row["owner_process_name"] or "Serato DJ Pro"
        try:
            running = _process_is_serato(pid)
        except (OSError, subprocess.TimeoutExpired, subprocess.SubprocessError):
            running = True
        except Exception:
            running = True
        if running:
            return {
                "open": True,
                "writable": False,
                "pid": pid,
                "process": name,
                "message": f"{name} is open. Edits stay off until it quits.",
            }
    return {
        "open": False,
        "writable": True,
        "pid": None,
        "process": None,
        "message": "Serato is quit. Edits save to the library.",
    }


LOCKED_MESSAGE = "Serato DJ Pro has the library open. Edits stay off until it quits."


def open_error_status(exc: sqlite3.OperationalError) -> dict[str, object]:
    """Build the busy status for a library file that exists but did not open.

    A locked database keeps the plain Serato message. Any other open or
    first-query error is also treated as Serato holding the file, so every
    write refuses, but the message carries the SQLite text so a damaged
    file is not hidden behind "Serato is open".

    Args:
        exc: The error from opening or first querying ``master.sqlite``.

    Returns:
        A status dict with ``open`` true, ``writable`` false, and
        ``open_error`` set to the SQLite text (None for a plain lock).
    """
    text = str(exc).strip() or type(exc).__name__
    if "locked" in text.lower():
        return {
            "open": True,
            "writable": False,
            "pid": None,
            "process": "Serato DJ Pro",
            "message": LOCKED_MESSAGE,
            "open_error": None,
        }
    return {
        "open": True,
        "writable": False,
        "pid": None,
        "process": "Serato DJ Pro",
        "message": (
            "The library could not be opened (SQLite: "
            f"{text}). Serato DJ Pro may have it open. Edits stay off until it opens."
        ),
        "open_error": text,
    }


def status(path: Path | None = None, *, from_copy: bool = False) -> dict[str, object]:
    """Report whether Serato has the library open.

    Args:
        path: Database path. None selects MASTER.
        from_copy: When true, read the lock table from a temporary copy
            so the library folder gains no ``-wal``, ``-shm``, or journal
            file. Setup uses this. The sidebar reads the live file.

    Returns:
        A status dict. A locked database is reported as open. Any other
        ``OperationalError`` from opening or first querying a file that
        exists is reported as open too, with the SQLite text in
        ``message`` and ``open_error``. ``generation`` says whether the
        session logs named Serato 4, Serato 5, or neither. file_manager
        names Finder or File Explorer.

    Raises:
        LibraryError: If the database file does not exist.
    """
    info: dict[str, object]
    database = Path(path or MASTER)
    try:
        if from_copy:
            opener = copied_read_conn(database)
        else:
            opener = closing(read_conn(database))
        with opener as conn:
            info = _status_rows(conn)
    except sqlite3.OperationalError as exc:
        if not database.exists():
            raise LibraryError(f"Serato library not found at {database}", 404) from exc
        info = open_error_status(exc)
    info.setdefault("open_error", None)
    info["file_manager"] = file_manager_name()
    import snapshots

    notice, generation = snapshots.library_gate()
    info["generation"] = generation
    info["write_block"] = None if notice is None else notice.text
    info["serato_running"] = snapshots.serato_dj_running()
    # The sidebar and the setup wizard share this flag. A running Serato DJ
    # process blocks edits even when the database lock row has not been written yet.
    if info["serato_running"] and not info.get("open"):
        info["open"] = True
        info["writable"] = False
        info["process"] = "Serato DJ"
        info["message"] = "Serato DJ is open. Edits stay off until it quits."
    if notice is not None and not info.get("open"):
        info["writable"] = False
        info["message"] = notice.text
        if notice.code:
            info["code"] = notice.code
            info["params"] = dict(notice.params or {})
    return info


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    """Return the column names of one table.

    Args:
        conn: Open database connection.
        table: Table name.

    Returns:
        Column names from PRAGMA table_info.
    """
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _parse_db_path(value: str | None) -> Path | None:
    """Turn a connection URI into a filesystem path.

    Args:
        value: A file URI, a plain path, or None.

    Returns:
        The path, or None when value is empty.
    """
    if not value:
        return None
    # connection.database_uri is a file URI. Percent-decoding recovers spaces.
    # urlparse leaves the leading slash that file URIs put before the path.
    if value.startswith("file:"):
        return Path(unquote(urlparse(value).path))
    return Path(value)


def _location_paths(conn: sqlite3.Connection) -> dict[int, Path]:
    """Map location ids to database files that exist on disk.

    Args:
        conn: Open master connection.

    Returns:
        Location id to database path. Location 3 falls back to root.sqlite beside the master file.
    """
    found: dict[int, Path] = {}
    try:
        rows = conn.execute("SELECT location_id, database_uri FROM connection").fetchall()
    except sqlite3.OperationalError:
        rows = []
    for row in rows:
        path = _parse_db_path(row["database_uri"])
        if path is not None and path.is_file():
            found[int(row["location_id"])] = path
    if 3 not in found:
        candidate = Path(MASTER).resolve().parent / "root.sqlite"
        if candidate.is_file():
            found[3] = candidate
    return found


def _mirror_allowed(path: Path) -> bool:
    """Return whether a location database may be updated.

    A live master database may mirror any connected location file. A relocated
    test database may mirror only a file beside itself, or a file under /tmp.

    Args:
        path: Location database path.

    Returns:
        True when a write to path is allowed.
    """
    master = Path(MASTER).resolve()
    if master == LIVE_MASTER.resolve():
        return True
    # A test relocates MASTER. Mirror only a sibling file, or a database
    # under /tmp, so the suite cannot write a drive Serato still uses.
    resolved = path.resolve()
    return resolved.parent == master.parent or str(resolved).startswith("/tmp/")


def _backup_database(source: Path, dest: Path) -> None:
    """Copy one SQLite database with the backup API.

    Args:
        source: Database to read.
        dest: New database file. Parent directories are created.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(f"file:{source}?mode=ro", uri=True)) as src:
        with closing(sqlite3.connect(dest)) as dst:
            src.backup(dst)


# File change counter, schema cookie, and version-valid-for. The backup API
# resets these three big-endian fields in the 100-byte SQLite header.
_SQLITE_HEADER_COUNTERS = (24, 40, 92)


def _match_quiescent_header(source: Path, dest: Path) -> None:
    """Copy SQLite header counters so a quiescent backup matches the source.

    The backup API resets the file change counter, the schema cookie, and
    the version-valid-for number. When the source has no WAL or rollback
    journal, those twelve bytes are the only difference, so copying them
    back makes the backup file identical to the source. A sidecar means
    the snapshot includes pages that are not in the main file, and the
    counters the backup API wrote stay in place.

    Args:
        source: Database that was read.
        dest: Backup file just written by the backup API.

    Raises:
        OSError: If a header field cannot be read or written.
    """
    for suffix in ("-wal", "-shm", "-journal"):
        if Path(str(source) + suffix).is_file():
            return
    if source.stat().st_size != dest.stat().st_size:
        return
    with source.open("rb") as handle:
        header = handle.read(100)
    if len(header) < 100 or not header.startswith(b"SQLite format 3\x00"):
        return
    with dest.open("r+b") as handle:
        current = handle.read(100)
        if len(current) < 100:
            return
        updated = bytearray(current)
        # Patching these counters assumes writes happen only after Serato quits.
        # ensure_backup runs before this process writes, so a quiescent file
        # differs from the backup API output only in these fields. A live
        # writer can change pages the snapshot includes and the main file does not.
        for offset in _SQLITE_HEADER_COUNTERS:
            updated[offset : offset + 4] = header[offset : offset + 4]
        if updated == current:
            return
        handle.seek(0)
        handle.write(updated)


from serato_web.completeness import (
    COMPLETE_NAME as BACKUP_COMPLETE_NAME,
    FAILED_SUFFIX as BACKUP_FAILED_SUFFIX,
    INCOMPLETE_NAME as BACKUP_INCOMPLETE_NAME,
    LEGACY_STATUS as LEGACY_BACKUP_STATUS,
    LOCK_NAME as PARTIAL_LOCK_NAME,
    backup_status,
    is_complete,
    is_failed_name as _is_failed_name,
    is_staging_name as _is_staging_name,
    verify_legacy_backup as _verify_legacy_backup,
    write_complete_marker as _write_complete_marker,
)


def verify_legacy_backup(backup_dir: Path) -> None:
    """Check a legacy backup and report a library error.

    Args:
        backup_dir: Folder the user picked.

    Raises:
        LibraryError: When the folder is not an unverified legacy backup
            or the integrity check fails. The cause is the
            :class:`serato_web.completeness.CompletenessError`. The status
            is 400, so a request handler returns that status instead of a
            server error.
    """
    try:
        _verify_legacy_backup(backup_dir)
    except CompletenessError as exc:
        raise LibraryError(exc.message) from exc

def list_backups(directory: Path | None = None) -> list[Path]:
    """Return backup folders that are safe to restore.

    Uses :func:`is_complete`. A legacy folder, a ``-failed`` folder, and a
    hidden ``.partial`` folder are omitted. No restore calls this yet.
    The snapshot work in #62 will call :func:`is_complete` on its store
    directory. The file browser hides staging and failed folders when it
    lists ``Library/Backups``.

    Args:
        directory: Folder that holds the backups. When omitted, this is
            ``Backups`` beside the current master database.

    Returns:
        Complete backup directories, sorted by name. A missing directory
        yields an empty list.
    """
    root = Path(MASTER).resolve().parent / "Backups" if directory is None else directory
    try:
        if root.is_symlink() or not root.is_dir():
            return []
        found = [
            child
            for child in root.iterdir()
            if not child.is_symlink() and child.is_dir() and is_complete(child)
        ]
    except OSError:
        return []
    return sorted(found, key=lambda path: path.name)


def _discard_failed_backup(folder: Path, backups: Path) -> None:
    """Quarantine a backup folder this call created, then try to remove it.

    Args:
        folder: Directory claimed for this backup.
        backups: The ``Backups`` directory that must contain ``folder``.

    The folder must be a real directory strictly inside ``backups``. A
    symlink is left in place so the removal cannot follow a link out of
    that directory. ``backups`` itself is not removed. The folder is
    renamed to end with :data:`BACKUP_FAILED_SUFFIX` before it is deleted,
    because a rename can succeed when a delete is blocked by a file lock.
    If the rename fails, :data:`BACKUP_INCOMPLETE_NAME` is written inside
    the folder. An ``OSError`` during this cleanup is logged and not
    raised. The caller still re-raises the copy error.
    """
    try:
        if folder.is_symlink() or not folder.is_dir():
            return
        resolved = folder.resolve()
        root = backups.resolve()
        if root not in resolved.parents:
            return
        _quarantine_failed_backup(folder)
    except OSError as exc:
        app_log.logger.warning(
            "Could not remove the failed backup folder %s: %s",
            folder,
            exc,
        )


def _failed_names(name: str) -> list[str]:
    """Return the failed-folder names to try, in order.

    Args:
        name: Current directory name.

    Returns:
        ``<name>-failed``, then ``<name>-failed-02`` through
        ``<name>-failed-99``.
    """
    base = f"{name}{BACKUP_FAILED_SUFFIX}"
    return [base, *[f"{base}-{suffix:02d}" for suffix in range(2, 100)]]


def _quarantine_failed_backup(folder: Path) -> None:
    """Rename a failed backup, then delete that renamed folder.

    Args:
        folder: Real directory this call created inside ``Backups``.

    The first free name is ``-failed``, then ``-failed-02`` and so on.
    A delete error leaves the renamed folder. When every rename fails,
    the original folder gets an ``INCOMPLETE`` marker. A staging name
    and a failed name both make :func:`is_complete` return false.
    """
    rename_error: OSError | None = None
    for name in _failed_names(folder.name):
        destination = folder.with_name(name)
        try:
            folder.rename(destination)
        except FileExistsError as exc:
            rename_error = exc
            continue
        except OSError as exc:
            # Linux reports ENOTEMPTY when the target name is an existing
            # directory. That is a collision, so try the next suffix.
            if exc.errno == errno.ENOTEMPTY:
                rename_error = exc
                continue
            _write_incomplete_marker(folder, exc)
            return
        try:
            shutil.rmtree(destination)
        except OSError as exc:
            app_log.logger.warning(
                "Could not remove the failed backup folder %s: %s",
                destination,
                exc,
            )
        return
    _write_incomplete_marker(
        folder,
        rename_error or OSError("Every failed backup name is already taken."),
    )


def _write_incomplete_marker(folder: Path, rename_error: OSError) -> None:
    """Mark a failed backup that could not be renamed.

    Args:
        folder: Directory that is still at its original name.
        rename_error: Error from the rename attempt.
    """
    marker = folder / BACKUP_INCOMPLETE_NAME
    try:
        marker.write_text("This backup did not finish.\n", encoding="utf-8")
    except OSError as exc:
        app_log.logger.warning(
            "Could not mark the failed backup folder %s: %s",
            folder,
            exc,
        )
        return
    app_log.logger.warning(
        "Could not rename the failed backup folder %s: %s",
        folder,
        rename_error,
    )


class DriveBackupSpec(Protocol):
    """One drive :func:`ensure_backup` can copy.

    ``snapshots.DriveSpec`` satisfies this. ``serato_root`` is that drive's
    ``_Serato_`` directory. A missing drive has ``present`` false.
    """

    drive_id: str
    label: str
    serato_root: Path | None
    role: str
    present: bool


def _discovered_drives() -> list[DriveBackupSpec]:
    """Return the drives a backup of the open library should record.

    Returns:
        Present drives from :func:`snapshots.discover_drives`, plus drives
        the newest snapshot already marked unavailable. A relocated library
        discovers none.
    """
    import snapshots

    return list(snapshots.drives_for_backup())


def _unique_drives(specs: Sequence[DriveBackupSpec]) -> list[DriveBackupSpec]:
    """Drop a repeated drive id, keeping the first record.

    Args:
        specs: Drives the caller asked to record.

    Returns:
        The first record for each id.
    """
    found: list[DriveBackupSpec] = []
    seen: set[str] = set()
    for spec in specs:
        if spec.drive_id in seen:
            continue
        seen.add(spec.drive_id)
        found.append(spec)
    return found


def _drive_skip_reason(spec: DriveBackupSpec) -> str | None:
    """Return why a drive is not copied.

    Args:
        spec: Drive to judge.

    Returns:
        ``absent`` when the drive is unplugged or its ``_Serato_`` folder
        is gone. ``permission`` when that folder cannot be read or is a
        shortcut. ``read-only`` when it can be read and is not writable, so
        the backup does not write on it. None when the folder can be copied.
    """
    if not spec.present or spec.serato_root is None:
        return "absent"
    root = spec.serato_root
    try:
        if root.is_symlink():
            return "permission"
        if not root.is_dir():
            return "absent"
        mode = root.stat().st_mode
        if not (mode & stat.S_IRUSR) or not os.access(root, os.R_OK):
            return "permission"
        if not (mode & stat.S_IWUSR) or not os.access(root, os.W_OK):
            return "read-only"
        with os.scandir(root) as scan:
            next(scan, None)
    except PermissionError:
        return "permission"
    except OSError as exc:
        if exc.errno in (errno.EACCES, errno.EPERM):
            return "permission"
        if exc.errno == errno.ENOENT:
            return "absent"
        return "permission"
    return None


class DriveUnreadable(OSError):
    """One drive's ``_Serato_`` tree cannot be read.

    The backup removes that drive's partial copy, records ``permission``,
    and continues with the other drives. A full disk, a missing file, and
    any other copy error are not this exception.
    """

    def __init__(self) -> None:
        """Record the refusal as ``EACCES``.

        Returns:
            None.
        """
        super().__init__(errno.EACCES, "A drive folder could not be read.")


def _is_permission(exc: BaseException) -> bool:
    """Return whether an error is a refusal to read, not a failed copy.

    Args:
        exc: Error from listing, measuring, or opening a drive file.

    Returns:
        True for ``PermissionError``, ``EACCES``, and ``EPERM``. A full
        disk, a missing file, and an I/O error are false.
    """
    if isinstance(exc, PermissionError):
        return True
    return isinstance(exc, OSError) and exc.errno in (errno.EACCES, errno.EPERM)


def _drive_backup_files(root: Path) -> list[tuple[str, Path]]:
    """List one drive's backup files, or report that the tree is unreadable.

    Args:
        root: ``_Serato_`` directory.

    Returns:
        Relative POSIX path and file path. ``Recording`` and ``DJ Sessions``
        are already left out.

    Raises:
        DriveUnreadable: If listing the tree is refused.
        OSError: If listing fails for another reason, including a drive
            that disappeared.
    """
    import snapshots

    try:
        return snapshots.iter_backup_files(root)
    except OSError as exc:
        if _is_permission(exc):
            raise DriveUnreadable() from exc
        raise


def _backup_payload_bytes(master: Path, specs: Sequence[DriveBackupSpec]) -> int:
    """Return how many source bytes this backup will read.

    Args:
        master: ``master.sqlite``.
        specs: Drives to consider. A skipped drive, including one whose
            subdirectory cannot be read, is not counted.

    Returns:
        The size of the database files plus each file that will be copied.
        ``drives.json`` and ``COMPLETE`` are not included. The space check
        keeps a margin for those.

    Raises:
        OSError: If a file that would be copied cannot be measured for a
            reason other than permission. A permission error skips that
            drive and does not fail the measurement.
    """
    total = 0
    if master.is_file() and not master.is_symlink():
        total += master.stat().st_size
    root = master.resolve().parent / "root.sqlite"
    if root.is_file() and not root.is_symlink() and _mirror_allowed(root):
        total += root.stat().st_size
    for spec in specs:
        if _drive_skip_reason(spec) is not None or spec.serato_root is None:
            continue
        drive_bytes = 0
        try:
            for _rel, path in _drive_backup_files(spec.serato_root):
                try:
                    drive_bytes += path.stat().st_size
                except OSError as exc:
                    if _is_permission(exc):
                        raise DriveUnreadable() from exc
                    raise OSError(
                        exc.errno or errno.EIO,
                        "A drive file could not be measured.",
                    ) from exc
        except DriveUnreadable:
            continue
        total += drive_bytes
    return total


def _require_backup_space(folder: Path, backups: Path, needed: int) -> None:
    """Refuse a backup the destination disk cannot hold.

    Args:
        folder: Staging directory that will receive the copy. Free space is
            read for this directory, which is under ``Library/Backups``.
        backups: The ``Backups`` directory. ``folder`` must sit inside it.
        needed: Source bytes the copy will write.

    Raises:
        OSError: ``ENOSPC`` with :data:`BACKUP_NO_SPACE` when the free space
            is below ``needed`` plus :data:`BACKUP_SPACE_MARGIN`, when the
            free space cannot be read, or when ``folder`` is not inside
            ``backups``. Nothing has been copied yet.
    """
    try:
        resolved = folder.resolve()
        root = backups.resolve()
    except OSError as exc:
        raise OSError(errno.ENOSPC, BACKUP_NO_SPACE) from exc
    if root != resolved and root not in resolved.parents:
        raise OSError(errno.ENOSPC, BACKUP_NO_SPACE)
    try:
        free = shutil.disk_usage(folder).free
    except OSError as exc:
        raise OSError(errno.ENOSPC, BACKUP_NO_SPACE) from exc
    if free < needed + BACKUP_SPACE_MARGIN:
        raise OSError(errno.ENOSPC, BACKUP_NO_SPACE)


def _drive_dir_name(drive_id: str) -> str:
    """Return a backup directory name for one drive id.

    Args:
        drive_id: Id from the drive record. It may contain a colon, a
            slash, or ``..``.

    Returns:
        A single path component. A short hash of the original id keeps two
        different ids from sharing a folder.
    """
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", drive_id).strip(".-")
    if not cleaned:
        cleaned = "drive"
    suffix = hashlib.sha256(drive_id.encode("utf-8")).hexdigest()[:10]
    return f"{cleaned[:40]}-{suffix}"


def _contained(path: Path, root: Path) -> bool:
    """Return whether a path stays inside a directory.

    Args:
        path: File or directory to test.
        root: Directory that must contain it.

    Returns:
        True when ``path`` is ``root`` or a file inside it. A shortcut that
        resolves outside is false.
    """
    try:
        resolved = path.resolve()
        base = root.resolve()
    except OSError:
        return False
    return resolved == base or base in resolved.parents


def _bad_drive_rel(rel: str) -> bool:
    """Return whether a relative drive path must not be copied.

    Args:
        rel: Path relative to ``_Serato_``.

    Returns:
        True for an empty, absolute, or climbing path.
    """
    if not rel or "\\" in rel or rel.startswith("/") or (len(rel) >= 2 and rel[1] == ":"):
        return True
    return any(part in {"", ".", ".."} for part in rel.split("/"))


def _copy_readonly(source: Path, dest: Path) -> None:
    """Copy one file with a read-only open and check the copy.

    Args:
        source: File to read. It is opened ``O_RDONLY``.
        dest: New file. The parent directory is created. An existing file
            is not replaced.

    Raises:
        DriveUnreadable: If the source cannot be opened because permission
            is refused. Nothing is written for this file.
        OSError: If the file cannot be copied, the disk fills, the source
            disappears, or the copied bytes do not hash to the bytes that
            were read.
    """
    digest = hashlib.sha256()
    # O_NOFOLLOW refuses a shortcut that appears after the path was checked.
    read_flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        src_fd = os.open(source, read_flags)
    except OSError as exc:
        if _is_permission(exc):
            raise DriveUnreadable() from exc
        raise
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        write_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        out_fd = os.open(dest, write_flags, 0o644)
        try:
            while True:
                block = os.read(src_fd, 1024 * 1024)
                if not block:
                    break
                digest.update(block)
                written = 0
                while written < len(block):
                    count = os.write(out_fd, block[written:])
                    if count <= 0:
                        raise OSError(errno.ENOSPC, BACKUP_NO_SPACE)
                    written += count
            os.fsync(out_fd)
        finally:
            os.close(out_fd)
    except OSError as exc:
        if exc.errno == errno.ENOSPC:
            raise OSError(errno.ENOSPC, BACKUP_NO_SPACE) from exc
        raise
    finally:
        os.close(src_fd)
    copied = hashlib.sha256()
    with dest.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            copied.update(block)
    if copied.digest() != digest.digest():
        raise OSError("The drive copy did not match the source.")


def _discard_drive_copy(dest_root: Path, staging: Path) -> None:
    """Remove one drive's partial copy from the staging directory.

    Args:
        dest_root: ``drives/<id>/`` for the drive that could not be read.
        staging: Hidden backup directory that must contain ``dest_root``.

    Raises:
        OSError: If the directory is a shortcut, would leave the staging
            folder, or cannot be removed. The caller then fails the whole
            backup so a partial drive tree is not published.
    """
    if not dest_root.exists():
        return
    if dest_root.is_symlink() or not dest_root.is_dir() or not _contained(dest_root, staging):
        raise OSError("The drive backup would leave the backup folder.")
    shutil.rmtree(dest_root)


def _copy_drive_tree(spec: DriveBackupSpec, staging: Path) -> int:
    """Copy one drive's ``_Serato_`` files under the staging directory.

    Args:
        spec: Drive whose folder can be read. Its files stay in
            ``drives/<id>/``. Another drive's files are not written there.
        staging: Hidden backup directory.

    Returns:
        How many files were copied.

    Raises:
        DriveUnreadable: If listing or reading this drive is refused.
            Any files already copied for this drive are removed first.
        OSError: If a path would leave the backup folder, the disk fills,
            the drive disappears, or another copy error occurs. Those
            failures are not turned into a skipped drive.
    """
    root = spec.serato_root
    if root is None:
        return 0
    dest_root = staging / "drives" / _drive_dir_name(spec.drive_id)
    if not _contained(dest_root, staging):
        raise OSError("The drive backup would leave the backup folder.")
    count = 0
    try:
        for rel, source in _drive_backup_files(root):
            try:
                link = source.is_symlink()
                regular = source.is_file()
            except OSError as exc:
                if _is_permission(exc):
                    raise DriveUnreadable() from exc
                raise
            if _bad_drive_rel(rel) or link or not regular:
                raise OSError("A drive path is not valid.")
            target = dest_root.joinpath(*rel.split("/"))
            if not _contained(target, dest_root):
                raise OSError("A drive path is not valid.")
            try:
                _copy_readonly(source, target)
            except DriveUnreadable:
                raise
            except OSError as exc:
                # A refusal before this file exists is the source. A full
                # disk or a missing file still fails the backup. A refusal
                # after the destination file exists is a copy error too.
                if _is_permission(exc) and not target.exists():
                    raise DriveUnreadable() from exc
                raise
            count += 1
    except DriveUnreadable:
        _discard_drive_copy(dest_root, staging)
        raise
    if count:
        _fsync_directory(dest_root)
        drives = staging / "drives"
        if drives.is_dir():
            _fsync_directory(drives)
    return count


def _drive_record(spec: DriveBackupSpec, status: str, files: int) -> dict[str, object]:
    """Build one drives.json row.

    Args:
        spec: Drive that was copied or skipped.
        status: ``copied``, ``absent``, ``read-only``, or ``permission``.
        files: How many files were copied.

    Returns:
        A row with the label and whether the drive was present. It does
        not include a filesystem path.
    """
    role = spec.role if spec.role in {"internal", "external"} else "external"
    label = spec.label if isinstance(spec.label, str) and spec.label else spec.drive_id
    return {
        "drive_id": spec.drive_id,
        "files": files,
        "label": label,
        "present": bool(spec.present) and status != "absent",
        "role": role,
        "status": status,
    }


def _write_drives_manifest(folder: Path, records: list[dict[str, object]]) -> None:
    """Write ``drives.json`` into a staging directory.

    Args:
        folder: Staging directory.
        records: One row per drive, including drives that were not copied.

    Raises:
        OSError: If the file cannot be written or flushed.
    """
    ordered = sorted(records, key=lambda item: str(item.get("drive_id") or ""))
    payload = {"drives": ordered, "version": 1}
    path = folder / DRIVES_MANIFEST
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _fsync_file(path)


def ensure_backup(drives: Sequence[DriveBackupSpec] | None = None) -> Path | None:
    """Copy the library once per process, and each drive the first time it is mounted.

    Files are copied into a hidden ``.serato-web-<stamp>.partial`` directory.
    When that name exists, the next free name is ``-02`` through ``-99``.
    ``mkdir(parents=True, exist_ok=False)`` claims it. The copy includes
    ``master.sqlite``, ``root.sqlite`` when that file may be mirrored, and
    each present writable drive's ``_Serato_`` folder under
    ``drives/<drive id>/``. ``Export Backups``, ``Lexicon``, ``Recording``,
    and ``DJ Sessions`` are not copied. ``Recording`` and ``DJ Sessions``
    are audio, not library metadata. The destination is ``Library/Backups``
    on the disk that holds the library, never the external drive. A drive
    that is unplugged, read-only, or unreadable is listed in ``drives.json``
    and skipped. An unreadable subdirectory is the same ``permission``
    result: that drive's partial copy is removed, and the other drives are
    still copied. Nothing is written on the skipped drive.

    Free space is checked before the first byte is copied. When the
    destination does not have room for the source bytes plus
    :data:`BACKUP_SPACE_MARGIN`, :data:`BACKUP_NO_SPACE` is raised and the
    staging directory is discarded. A copy that fails, including a full
    disk while a file is being written or a drive unplugged while it is
    being read, is discarded the same way. No partial folder is published.
    A permission refusal is not one of those failures.

    :data:`_backup_guard` is held for the whole call, including the update
    of :data:`_backed_up` and :data:`_copied_drives`.

    After every copy succeeds, a ``COMPLETE`` marker is written last, with
    a SHA-256 for every file, including ``drives.json``, and the directory
    is renamed to ``serato-web-<stamp>``. :func:`is_complete` is the check
    a restore uses. A leftover ``.partial`` directory is removed on a later
    backup only when its newest mtime is at least an hour old and its lock
    file can be taken. A directory another process is still writing is left
    in place. If this copy fails, the staging directory is renamed so the
    name ends with ``-failed`` (or ``-failed-02`` when that name is taken)
    and then removed. If the rename fails, an ``INCOMPLETE`` file is written
    in the staging directory. A failure to rename or remove it is logged
    and does not replace the copy error. :func:`is_complete` is false for a
    staging directory, a failed name, and a folder with no verified
    ``COMPLETE`` marker.

    The databases are copied once per process. A drive plugged in later is
    copied on the next call. A drive that was skipped is tried again when
    it becomes readable and writable.

    Args:
        drives: Drives to record. None discovers them. A test library passes
            its own list. An empty list records no drives.

    Returns:
        The new backup directory, or None when this process already backed
        up that database and every drive it can copy.

    Raises:
        FileExistsError: If ``serato-web-<stamp>`` and every suffix from
            ``-02`` through ``-99`` already exist. Nothing was copied.
        OSError: If a claimed backup file cannot be written, or the disk
            does not have room. ``errno`` is ``ENOSPC`` and the message is
            :data:`BACKUP_NO_SPACE` when the disk check refuses the copy.
            A permission error on one drive is not raised.
    """
    with _backup_guard:
        return _ensure_backup_held(drives)


def _ensure_backup_held(drives: Sequence[DriveBackupSpec] | None) -> Path | None:
    """Copy the library while :data:`_backup_guard` is already held.

    Args:
        drives: Drives to record. None discovers them.

    Returns:
        The new backup directory, or None when this process already backed
        up that database and every drive it can copy.

    Raises:
        FileExistsError: If every backup name for this second exists.
        OSError: If the copy cannot be written or the disk is full.
    """
    master = Path(MASTER)
    key = str(master.resolve())
    specs = _unique_drives(list(drives) if drives is not None else _discovered_drives())
    copyable = [spec for spec in specs if _drive_skip_reason(spec) is None]
    already = _copied_drives.get(key, set())
    pending = [spec for spec in copyable if spec.drive_id not in already]
    if key in _backed_up and not pending:
        return None
    stamp = time.strftime("%Y%m%d-%H%M%S")
    parent = master.resolve().parent / "Backups"
    _cleanup_partial_backups(parent)
    staging, final_name = _claim_staging(parent, stamp)
    lock: int | None = None
    try:
        try:
            lock = _lock_partial(staging)
            _require_backup_space(staging, parent, _backup_payload_bytes(master, specs))
            _backup_database(master, staging / "master.sqlite")
            _match_quiescent_header(master, staging / "master.sqlite")
            _fsync_file(staging / "master.sqlite")
            root = master.resolve().parent / "root.sqlite"
            if root.is_file() and _mirror_allowed(root):
                _backup_database(root, staging / "root.sqlite")
                _match_quiescent_header(root, staging / "root.sqlite")
                _fsync_file(staging / "root.sqlite")
            records: list[dict[str, object]] = []
            copied_now: list[DriveBackupSpec] = []
            for spec in specs:
                reason = _drive_skip_reason(spec)
                copied = 0
                if reason is None:
                    try:
                        copied = _copy_drive_tree(spec, staging)
                    except DriveUnreadable:
                        reason = "permission"
                    else:
                        records.append(_drive_record(spec, "copied", copied))
                        copied_now.append(spec)
                        continue
                records.append(_drive_record(spec, reason or "permission", 0))
                app_log.logger.info(
                    "Drive backup skipped %s (%s).",
                    spec.label or spec.drive_id,
                    reason,
                )
            if records:
                _write_drives_manifest(staging, records)
            _write_complete_marker(staging)
            _fsync_directory(staging)
            # Windows refuses to rename a directory that still has an open file.
            # Close the lock once, then delete it, before publish or cleanup.
            _release_staging_lock(staging, lock)
            lock = None
            folder = staging.with_name(final_name)
            # os.replace is atomic on the same directory. File moves use
            # os.rename so a cross-device fallback does not publish this folder.
            os.replace(staging, folder)
            _fsync_directory(parent)
        finally:
            if lock is not None:
                _release_staging_lock(staging, lock)
                lock = None
    except Exception:
        _discard_failed_backup(staging, parent)
        raise
    copied_ids = _copied_drives.setdefault(key, set())
    for spec in copied_now:
        copied_ids.add(spec.drive_id)
    _backed_up.add(key)
    telemetry.capture(telemetry.EVENT_BACKUP_MADE)
    return folder


def drive_backup_report(directory: Path | None = None) -> dict[str, object] | None:
    """Return the newest finished backup's drive list.

    The folder must pass :func:`is_complete`, which checks every file hash.
    A backup that does not pass is not reported.

    Args:
        directory: Folder that holds the backups. None uses ``Backups``
            beside the current master database.

    Returns:
        ``folder``, ``verified`` true, and ``drives``. None when no finished
        backup exists. A finished backup with no ``drives.json`` has an
        empty drive list.
    """
    folders = list_backups(directory)
    if not folders:
        return None
    folder = folders[-1]
    if not is_complete(folder):
        return None
    manifest = folder / DRIVES_MANIFEST
    drives: list[object] = []
    if manifest.exists():
        if manifest.is_symlink() or not manifest.is_file():
            return None
        try:
            loaded = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeError):
            return None
        rows = loaded.get("drives") if isinstance(loaded, dict) else None
        if not isinstance(rows, list):
            return None
        drives = [item for item in rows if isinstance(item, dict)]
    return {"drives": drives, "folder": folder.name, "verified": True}


def backup_connected_drives() -> dict[str, object]:
    """Copy drive crates into ``Library/Backups`` without changing the library.

    This is a read of the databases and of each drive folder. It is refused
    while Serato holds the library lock or a Serato DJ process is running.
    It does not use the Serato version gate, so a library that cannot be
    edited can still be copied.

    Returns:
        ``ok``, ``created`` (false when this process already copied every
        drive it can), and ``drive_backup`` from :func:`drive_backup_report`.

    Raises:
        SeratoOpen: If Serato holds the lock.
        LibraryError: If Serato DJ is running, the disk does not have room,
            or the copy fails.
    """
    import snapshots

    if snapshots.serato_dj_running():
        raise LibraryError(BACKUP_SERATO_RUNNING, 409)
    info = status()
    if info["open"]:
        raise SeratoOpen(info)
    try:
        folder = ensure_backup()
    except OSError as exc:
        if exc.errno == errno.ENOSPC:
            raise LibraryError(BACKUP_NO_SPACE, 507) from exc
        app_log.logger.exception("Drive backup failed.")
        raise LibraryError("The library could not be saved.", 500) from exc
    return {"created": folder is not None, "drive_backup": drive_backup_report(), "ok": True}


def _backup_name_choices(stamp: str) -> list[str]:
    """Return the public backup names for one second, in order.

    Args:
        stamp: ``%Y%m%d-%H%M%S`` text.

    Returns:
        ``serato-web-<stamp>``, then ``-02`` through ``-99``.
    """
    base = f"serato-web-{stamp}"
    return [base, *[f"{base}-{suffix:02d}" for suffix in range(2, 100)]]


def _claim_staging(parent: Path, stamp: str) -> tuple[Path, str]:
    """Create the hidden directory that receives this backup.

    Args:
        parent: ``Library/Backups``.
        stamp: ``%Y%m%d-%H%M%S`` text.

    Returns:
        The staging directory and the public name it will be renamed to.

    Raises:
        FileExistsError: If every staging name for this second exists.
            Nothing is copied.
    """
    for name in _backup_name_choices(stamp):
        final = parent / name
        staging = parent / f".{name}.partial"
        if final.exists():
            continue
        try:
            staging.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            continue
        return staging, name
    base = f"serato-web-{stamp}"
    raise FileExistsError(
        f"Every backup folder for this second already exists: "
        f"{base} through {base}-99. Nothing was copied."
    )


def _fsync_file(path: Path) -> None:
    """Flush a file's bytes to disk.

    Args:
        path: File to flush.

    Raises:
        OSError: If the file cannot be opened or flushed.

    The handle is opened for writing. Windows rejects ``fsync`` on a
    read-only handle.
    """
    fd = os.open(path, os.O_RDWR | getattr(os, "O_BINARY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


# The real operating system, captured before a test replaces
# ``sys.platform`` to exercise another product path. File locks and
# directory flushes follow the host, not that stand-in.
_HOST_PLATFORM = sys.platform


def _fsync_directory(path: Path) -> None:
    """Flush a directory entry on POSIX.

    Args:
        path: Directory to flush. Windows skips this. A directory cannot
            be opened for ``fsync`` there.
    """
    if _HOST_PLATFORM == "win32":
        return
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _lock_partial(folder: Path) -> int | None:
    """Take the exclusive lock inside a staging directory.

    Args:
        folder: Staging directory.

    Returns:
        An open file descriptor, or None when another process holds the lock.
    """
    path = folder / PARTIAL_LOCK_NAME
    fd: int | None = None
    try:
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
        _acquire_lock(fd)
        held = fd
        fd = None
        return held
    except OSError:
        return None
    finally:
        if fd is not None:
            os.close(fd)


def _acquire_lock(fd: int) -> None:
    """Lock an open descriptor with the host's file lock.

    Args:
        fd: Open descriptor for ``.write-lock``.

    Raises:
        OSError: If another process already holds the lock.
    """
    if _HOST_PLATFORM == "win32":
        import msvcrt

        if os.fstat(fd).st_size < 1:
            os.write(fd, b"\0")
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        return
    import fcntl

    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_partial(fd: int | None) -> None:
    """Release a staging lock exactly once.

    Args:
        fd: Descriptor from :func:`_lock_partial`, or None. A second close
            is ignored so a cleanup path cannot raise ``EBADF``.
    """
    if fd is None:
        return
    try:
        if _HOST_PLATFORM == "win32":
            import msvcrt

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        os.close(fd)
    except OSError:
        pass


def _release_staging_lock(folder: Path, fd: int | None) -> None:
    """Close the staging lock and delete the lock file.

    Args:
        folder: Directory that currently holds ``.write-lock``.
        fd: Open descriptor, or None when it was already closed.
    """
    _unlock_partial(fd)
    try:
        (folder / PARTIAL_LOCK_NAME).unlink(missing_ok=True)
    except OSError:
        pass


def _newest_mtime(folder: Path) -> float:
    """Return the newest mtime in a directory, including the directory.

    Args:
        folder: Directory to inspect.

    Returns:
        The largest ``st_mtime`` that can be read. A missing child is skipped.
    """
    newest = folder.stat().st_mtime
    for path in folder.rglob("*"):
        try:
            newest = max(newest, path.stat().st_mtime)
        except OSError:
            continue
    return newest


# A staging directory younger than this is left alone. Its newest mtime
# is what counts, so a file still being written keeps the directory.
PARTIAL_STALE_SECONDS = 60 * 60


def _cleanup_partial_backups(parent: Path) -> None:
    """Remove staging directories that are stale and not being written.

    Args:
        parent: ``Library/Backups``. A missing directory is left missing.

    A ``.partial`` directory is removed only when its newest mtime is at
    least :data:`PARTIAL_STALE_SECONDS` old and :func:`_lock_partial` can
    take its lock. A fresh directory, or one whose lock is held, stays.
    """
    if not parent.is_dir() or parent.is_symlink():
        return
    now = time.time()
    for child in list(parent.iterdir()):
        if child.is_symlink() or not child.is_dir() or not _is_staging_name(child.name):
            continue
        try:
            if now - _newest_mtime(child) < PARTIAL_STALE_SECONDS:
                continue
        except OSError:
            continue
        held = _lock_partial(child)
        if held is None:
            continue
        _unlock_partial(held)
        try:
            shutil.rmtree(child)
        except OSError:
            _discard_failed_backup(child, parent)


def begin_write(*, snapshot: bool = True) -> sqlite3.Connection:
    """Open a write transaction after Serato has quit.

    The first call in a process also copies the databases and each present
    drive's ``_Serato_`` folder into Library/Backups. A later call copies a
    drive the first time it is mounted. The write does not open when that
    copy does not fit on the disk, or when a copy error is not a permission
    refusal. An unreadable drive is recorded and does not block the write.
    A normal call first saves a content-addressed snapshot, after Serato 5 has
    been allowed to proceed. A ``safe_write`` session takes that snapshot
    once and this function does not take a second one while the session is open.
    Restore passes ``snapshot=False`` because it already saved a snapshot and
    is holding the restore journal. A nested snapshot would open the store
    again and roll that journal back.

    Args:
        snapshot: When true, save a snapshot before the transaction opens.
            When false, the caller has already saved the undo snapshot.

    Returns:
        A connection inside BEGIN IMMEDIATE. The caller commits and closes it.
        Library edits go through ``safe_write.run``, which checks the commit
        and puts the snapshot back when the rows do not match.

    Raises:
        SeratoOpen: If Serato holds the lock, the database is locked, or
            opening the write transaction raises any ``OperationalError``.
            The message then carries the SQLite text.
        LibraryError: If the version gate refuses the library.
    """
    info = status()
    if info["open"]:
        raise SeratoOpen(info)
    import snapshots
    import safe_write

    blocked = snapshots.write_block_message()
    if blocked:
        raise LibraryError(blocked, 409)
    if not safe_write.holding_snapshot():
        if snapshot:
            snapshots.snapshot_before_write()
        try:
            ensure_backup()
        except OSError as exc:
            if exc.errno == errno.ENOSPC:
                raise LibraryError(BACKUP_NO_SPACE, 507) from exc
            raise
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(Path(MASTER), timeout=1)
        conn.row_factory = sqlite3.Row
        register(conn)
        _keep_wal(conn)
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("BEGIN IMMEDIATE")
    except sqlite3.OperationalError as exc:
        if conn is not None:
            conn.close()
        info = status()
        if not info["open"]:
            info = {**info, **open_error_status(exc)}
        raise SeratoOpen(info) from exc
    try:
        held = _status_rows(conn)["open"]
    except sqlite3.OperationalError as exc:
        conn.rollback()
        conn.close()
        raise SeratoOpen({**status(), **open_error_status(exc)}) from exc
    if held:
        conn.rollback()
        conn.close()
        raise SeratoOpen(status())
    return conn


def _keep_wal(conn: sqlite3.Connection) -> None:
    """Leave committed frames in the WAL file until the write is checked.

    The check copies ``master.sqlite`` and ``-wal``. A checkpoint on close
    would fold those frames into the main file first, and the copy of
    ``-wal`` would no longer be what the write committed.

    Args:
        conn: Connection that is about to start a write transaction.
    """
    flag = getattr(sqlite3, "SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE", None)
    if flag is not None:
        conn.setconfig(flag, True)
    conn.execute("PRAGMA wal_autocheckpoint=0")


def _space_id(conn: sqlite3.Connection, space: str) -> int:
    """Return the id of an allowed space.

    Args:
        conn: Open write connection.
        space: Space name.

    Returns:
        The space id.

    Raises:
        LibraryError: If the space is not allowed or is missing from this library.
    """
    if space not in ALLOWED_SPACES:
        raise LibraryError("That space is not available here.")
    row = conn.execute("SELECT id FROM space WHERE name = ?", (space,)).fetchone()
    if row is None:
        raise LibraryError(f"{space} is not in this library.", 404)
    return int(row[0])


def _space_root(conn: sqlite3.Connection, space: str) -> int:
    """Return the root container id for a space.

    Args:
        conn: Open connection.
        space: Space name.

    Returns:
        The container whose type is 0.

    Raises:
        LibraryError: If the space has no root crate.
    """
    row = conn.execute(
        """
        SELECT c.id FROM container c
        JOIN space s ON s.id = c.space_id
        WHERE s.name = ? AND c.type = 0
        """,
        (space,),
    ).fetchone()
    if row is None:
        raise LibraryError(f"{space} has no root crate.", 404)
    return int(row[0])


def _container(conn: sqlite3.Connection, crate_id: int, space: str) -> sqlite3.Row:
    """Load one crate that belongs to a space.

    Args:
        conn: Open connection.
        crate_id: Container id.
        space: Space name.

    Returns:
        The container row.

    Raises:
        LibraryError: If the crate is not in that space.
    """
    row = conn.execute(
        """
        SELECT c.id, c.parent_id, c.name, c.type, c.space_id, s.name AS space_name
        FROM container c
        JOIN space s ON s.id = c.space_id
        WHERE c.id = ? AND s.name = ?
        """,
        (crate_id, space),
    ).fetchone()
    if row is None:
        raise LibraryError("That crate is not in this space.", 404)
    return row


def container_in_space(conn: sqlite3.Connection, crate_id: int, space: str) -> sqlite3.Row:
    """Load one crate that belongs to a space.

    Args:
        conn: Open connection.
        crate_id: Container id.
        space: Space name.

    Returns:
        The container row.

    Raises:
        LibraryError: If the crate is not in that space.
    """
    return _container(conn, crate_id, space)


def display_name(name: str) -> str:
    """Return the visible portion of a stored crate name.

    Args:
        name: Name stored in container.name.

    Returns:
        Text before the Serato name separator.

    Example:
        >>> display_name("Warmup")
        'Warmup'
    """
    return name.split(NAME_SPLIT, 1)[0]


def _ancestry(conn: sqlite3.Connection, crate_id: int) -> list[str]:
    """Return crate names from the space root down to one crate.

    Args:
        conn: Open connection.
        crate_id: Container id.

    Returns:
        Display names. The space root is omitted.
    """
    names: list[str] = []
    seen: set[int] = set()
    current = crate_id
    while current and current not in seen:
        seen.add(current)
        row = conn.execute(
            "SELECT parent_id, name, type FROM container WHERE id = ?",
            (current,),
        ).fetchone()
        if row is None:
            break
        kind: object = row["type"]
        if _as_int(kind) == 0:
            break
        stored: object = row["name"]
        names.append(display_name(cast(str, stored)))
        parent: object = row["parent_id"]
        if parent is None:
            break
        current = _as_int(parent)
    names.reverse()
    return names


def _descendant_ids(conn: sqlite3.Connection, crate_id: int) -> list[int]:
    """Return a crate id and the ids of crates nested under it.

    Args:
        conn: Open connection.
        crate_id: Container id.

    Returns:
        Ids from a recursive container query, including crate_id.
    """
    rows = conn.execute(
        """
        WITH RECURSIVE tree(id) AS (
            SELECT id FROM container WHERE id = ?
            UNION ALL
            SELECT c.id
            FROM container c
            JOIN tree t ON c.parent_id = t.id
            WHERE c.parent_id != c.id  -- a crate must not list itself as its parent
        )
        SELECT id FROM tree
        """,
        (crate_id,),
    ).fetchall()
    return [int(row[0]) for row in rows]


def descendant_ids(conn: sqlite3.Connection, crate_id: int) -> list[int]:
    """Return a crate id and the ids of crates nested under it.

    Args:
        conn: Open connection.
        crate_id: Container id.

    Returns:
        Ids from a recursive container query, including crate_id.
    """
    return _descendant_ids(conn, crate_id)


def _stored_name(conn: sqlite3.Connection, parent_id: int, display: str, crate_type: int, existing_id: int | None) -> str:
    """Build a unique stored crate name.

    Args:
        conn: Open connection.
        parent_id: Parent container id.
        display: Name typed in the page.
        crate_type: Container type. Smart crates use 2.
        existing_id: Crate being renamed, or None for a new crate.

    Returns:
        The name to store, including a hidden suffix when needed to avoid a clash.

    Raises:
        LibraryError: If the name is empty, contains the separator, is longer than 400 characters, or clashes with a suffixed crate.
    """
    text = (display or "").strip()
    if not text or NAME_SPLIT in text:
        raise LibraryError("Use a crate name without the Serato name separator.")
    if len(text) > 400:
        raise LibraryError("That crate name is too long.")
    suffix = ""
    if existing_id is not None:
        current = conn.execute("SELECT name FROM container WHERE id = ?", (existing_id,)).fetchone()
        if current and NAME_SPLIT in current[0]:
            suffix = current[0][current[0].find(NAME_SPLIT):]
    candidate = text + suffix
    clash = conn.execute(
        """
        SELECT id FROM container
        WHERE parent_id = ? AND name = ? COLLATE NOCASE AND type = ? AND id != ?
        """,
        (parent_id, candidate, crate_type, -1 if existing_id is None else existing_id),
    ).fetchone()
    if clash is None:
        return candidate
    if suffix:
        raise LibraryError("A crate with that name already exists here.")
    return text + NAME_SPLIT + uuid.uuid4().hex


def _export_basename(filename: str) -> str:
    """Return the crate file name Serato compares at launch.

    Args:
        filename: A stored export name or a path. Backslashes are separators.

    Returns:
        The last path piece, or an empty string when there is nothing to keep.
    """
    return filename.replace("\\", "/").split("/")[-1].strip()


def _split_crate_filename(filename: str) -> tuple[str, list[str], bool]:
    """Split a crate file name into a leaf, parents, and smart-crate flag.

    Args:
        filename: Base name such as ``House%%Café.crate`` or ``Friday.scrate``.
            A ``.scrate`` name is not treated as a ``.crate`` name.

    Returns:
        The leaf name, parent names from the root down, and True for a
        smart crate.

    Raises:
        LibraryError: If the name has no crate suffix or no leaf.
    """
    base = _export_basename(filename)
    folded = base.casefold()
    if folded.endswith(".scrate"):
        stem = base[:-7]
        smart = True
    elif folded.endswith(".crate"):
        stem = base[:-6]
        smart = False
    else:
        raise LibraryError("That file is not a crate.")
    pieces = [piece for piece in stem.split("%%") if piece]
    if not pieces:
        raise LibraryError("That crate file has no name.")
    return pieces[-1], pieces[:-1], smart


def is_registerable_crate_name(filename: str) -> bool:
    """Return whether a crate file name can be stored in the database.

    Args:
        filename: Base name or path.

    Returns:
        False when the suffix is missing or the leaf name is empty, as with
        a file named ``.crate``.
    """
    try:
        _split_crate_filename(filename)
    except LibraryError:
        return False
    return True


def _export_index(conn: sqlite3.Connection) -> dict[str, tuple[int, str]]:
    """Map casefolded crate file names to the container that owns them.

    Generated names are recorded first. A stored ``dj_container_metadata``
    filename replaces the generated spelling, including a Windows path.

    Args:
        conn: Open connection.

    Returns:
        Casefolded basename to ``(container id, exact basename)``.
    """
    found: dict[str, tuple[int, str]] = {}
    if "container" not in _tables(conn) or "space" not in _tables(conn):
        return found
    rows = conn.execute(
        """
        SELECT c.id, c.type FROM container c
        JOIN space s ON s.id = c.space_id
        WHERE c.type != 0 AND s.name = ?
        ORDER BY c.id
        """,
        (LIBRARY_SPACE,),
    ).fetchall()
    for row in rows:
        base = _export_basename(_filename(conn, int(row["id"]), int(row["type"])))
        if base:
            found[base.casefold()] = (int(row["id"]), base)
    if "dj_container_metadata" in _tables(conn):
        stored = conn.execute(
            "SELECT container_id, filename FROM dj_container_metadata"
        ).fetchall()
        for row in stored:
            raw = row["filename"]
            if not isinstance(raw, str):
                continue
            base = _export_basename(raw)
            if base:
                found[base.casefold()] = (int(row["container_id"]), base)
    return found


def can_register_crates(master: Path) -> bool:
    """Return whether restored crate files can be written into this database.

    Args:
        master: ``master.sqlite``.

    Returns:
        True when the file is a database with a Serato Library root crate.
        False when it is missing, a shortcut, unreadable, or has no such
        root. Nothing is written.
    """
    if not master.is_file() or master.is_symlink():
        return False
    try:
        with closing(sqlite3.connect(f"file:{master}?mode=ro", uri=True)) as conn:
            conn.row_factory = sqlite3.Row
            if "space" not in _tables(conn) or "container" not in _tables(conn):
                return False
            row = conn.execute(
                """
                SELECT 1 FROM container c
                JOIN space s ON s.id = c.space_id
                WHERE s.name = ? AND c.type = 0
                """,
                (LIBRARY_SPACE,),
            ).fetchone()
    except sqlite3.Error:
        return False
    return row is not None


def crate_export_names(master: Path) -> set[str]:
    """Return the crate file names a Serato 4/5 database has heard of.

    Serato deletes a ``.crate`` or ``.scrate`` whose name is not in this set
    the next time it launches. The set contains casefolded basenames.
    A stored path keeps only its last piece, so ``Subcrates\\\\House.crate``
    is the same name as ``House.crate``. The database is opened read-only.
    A symlink is not opened.

    Args:
        master: ``master.sqlite``.

    Returns:
        Casefolded basenames. An empty set when the file is missing or has
        no crate tables.

    Raises:
        sqlite3.Error: If the database cannot be read.
    """
    if not master.is_file() or master.is_symlink():
        return set()
    with closing(sqlite3.connect(f"file:{master}?mode=ro", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        return set(_export_index(conn))


def _filename(conn: sqlite3.Connection, crate_id: int, crate_type: int) -> str:
    """Build the export filename Serato stores for a crate.

    Args:
        conn: Open connection.
        crate_id: Container id.
        crate_type: 2 for a smart crate, otherwise a normal crate.

    Returns:
        A path of ancestor names joined by %% with a .crate or .scrate suffix.
    """
    ext = ".scrate" if int(crate_type) == 2 else ".crate"
    return "%%".join(_ancestry(conn, crate_id)) + ext


def _upsert_filename(conn: sqlite3.Connection, crate_id: int, filename: str, revision: int | None = None) -> None:
    """Store a crate export filename.

    Args:
        conn: Open connection.
        crate_id: Container id.
        filename: Export filename.
        revision: Revision to store when the table has that column. None uses the current time.
    """
    columns = _columns(conn, "dj_container_metadata")
    if "revision" in columns:
        conn.execute(
            """
            INSERT INTO dj_container_metadata (container_id, revision, export_state, filename)
            VALUES (?, ?, 0, ?)
            ON CONFLICT(container_id) DO UPDATE SET
                filename = excluded.filename,
                revision = excluded.revision
            """,
            (crate_id, revision if revision is not None else int(time.time()), filename),
        )
        return
    conn.execute(
        """
        INSERT INTO dj_container_metadata (container_id, export_state, filename)
        VALUES (?, 0, ?)
        ON CONFLICT(container_id) DO UPDATE SET filename = excluded.filename
        """,
        (crate_id, filename),
    )


def _refresh_filenames(conn: sqlite3.Connection, crate_id: int, revision: int | None = None) -> None:
    """Rebuild export filenames for a crate and its descendants.

    Args:
        conn: Open connection.
        crate_id: Container id.
        revision: Revision passed to each filename update.
    """
    for current in _descendant_ids(conn, crate_id):
        row = conn.execute("SELECT type FROM container WHERE id = ?", (current,)).fetchone()
        if row is None or int(row[0]) == 0:
            continue
        _upsert_filename(conn, current, _filename(conn, current, int(row[0])), revision)


def _next_revision(conn: sqlite3.Connection) -> int:
    """Advance the serato.revision counter when that column exists.

    Args:
        conn: Open write connection.

    Returns:
        The new revision, or the current time when the column is absent.
    """
    columns = _columns(conn, "serato")
    if "revision" not in columns:
        return int(time.time())
    conn.execute("UPDATE serato SET revision = COALESCE(revision, 0) + 1")
    return int(conn.execute("SELECT revision FROM serato").fetchone()[0])


def _with_location(path: Path, fn: Callable[[sqlite3.Connection], str | None]) -> str | None:
    """Run a write against a location database and return a warning on failure.

    Args:
        path: Location database file.
        fn: Callable that receives the location connection and returns a warning or None.

    Returns:
        None on success, or a warning when the mirror is skipped or the location database raises sqlite3.Error or OSError. Other exceptions propagate.
    """
    if not path.is_file() or not _mirror_allowed(path):
        return "Saved in the main library. That track's drive is not connected, so Serato may reconcile the edit when the drive returns."
    conn = sqlite3.connect(path, timeout=1)
    conn.row_factory = sqlite3.Row
    register(conn)
    try:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("BEGIN IMMEDIATE")
        warning = fn(conn)
        conn.commit()
        return warning
    except (sqlite3.Error, OSError) as exc:
        conn.rollback()
        return f"Saved in the main library. The location database was not updated ({exc})."
    finally:
        conn.close()


def _asset_location(conn: sqlite3.Connection, asset_id: int) -> sqlite3.Row:
    """Load the location columns for one asset.

    Args:
        conn: Open connection.
        asset_id: Asset id.

    Returns:
        The asset row.

    Raises:
        LibraryError: If the track is not in the library.
    """
    row = conn.execute(
        "SELECT id, location_id, external_id, portable_id, file_name FROM asset WHERE id = ?",
        (asset_id,),
    ).fetchone()
    if row is None:
        raise LibraryError("That track is not in the library.", 404)
    return row


def _clean_text(field: str, value: object) -> str:
    """Validate one text field before it is saved.

    Args:
        field: Field name. emoji is limited to 16 characters. Other text is limited to 4000.
        value: Submitted value.

    Returns:
        The text to store. None becomes an empty string.

    Raises:
        LibraryError: If the value is not text or is too long.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        raise LibraryError(f"{field} needs text.")
    limit = 16 if field == "emoji" else 4000
    if len(value) > limit:
        raise LibraryError(f"{field} is too long.")
    return value


def _clean_fields(fields: object) -> dict[str, object]:
    """Validate a track edit payload.

    Args:
        fields: Map of column name to submitted value.

    Returns:
        Values safe to assign on the asset row.

    Raises:
        LibraryError: If the payload is empty, names an unknown column, or contains an out-of-range value.
    """
    if not isinstance(fields, dict) or not fields:
        raise LibraryError("Choose a field to save.")
    raw = cast("dict[object, object]", fields)
    if any(key not in TRACK_FIELDS for key in raw):
        raise LibraryError("That field cannot be edited.")
    cleaned: dict[str, object] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            raise LibraryError("That field cannot be edited.")
        field = key
        if field in TEXT_FIELDS:
            cleaned[field] = _clean_text(field, value)
        elif field == "bpm":
            if value is None or value == "":
                cleaned[field] = None
            else:
                try:
                    number = _as_float(value)
                except (TypeError, ValueError):
                    raise LibraryError("BPM needs a number.") from None
                if number < 0 or number > 999:
                    raise LibraryError("BPM needs to be between 0 and 999.")
                cleaned[field] = number
        elif field == "color":
            if value is None or value == "":
                cleaned[field] = 0xFFFFFF
            else:
                try:
                    color = _as_int(value)
                except (TypeError, ValueError):
                    raise LibraryError("Color needs a number.") from None
                if color < 0 or color > 0xFFFFFF:
                    raise LibraryError("Color is out of range.")
                cleaned[field] = color
        elif field == "rating":
            if value is None or value == "":
                cleaned[field] = None
            else:
                try:
                    rating = _as_float(value)
                except (TypeError, ValueError):
                    raise LibraryError("Rating needs a number.") from None
                if rating < 0 or rating > 1:
                    raise LibraryError("Rating needs to be from 0 to 1.")
                cleaned[field] = rating
        elif field == "is_beatgrid_locked":
            cleaned[field] = 1 if value in (True, 1, "1", "true") else 0
        elif field == "portable_id":
            cleaned[field] = _portable_for_existing_file(value)
    return cleaned


def _portable_for_existing_file(value: object) -> str:
    """Turn a submitted path into a portable_id for a file that exists.

    Args:
        value: Path typed in the page.

    Returns:
        A path relative to the home directory when possible, otherwise the absolute path.

    Raises:
        LibraryError: If the value is empty, the file is missing, or the path cannot be read.
    """
    if not isinstance(value, str) or not value.strip():
        raise LibraryError("Choose a file path.")
    path = Path(value).expanduser()
    try:
        if not path.is_file():
            raise LibraryError("That file is not on disk.", 404)
    except OSError as exc:
        raise LibraryError("That path could not be read.", 400) from exc
    try:
        # Serato stores portable_id with forward slashes, relative to home
        # when the file lives there. A file outside home keeps its absolute path.
        relative = path.resolve().relative_to(Path.home())
        return relative.as_posix()
    except ValueError:
        return str(path)


def _assign(conn: sqlite3.Connection, table: str, columns: Mapping[str, object], where: str, key: object) -> None:
    """Update columns that exist on a table.

    Args:
        conn: Open write connection.
        table: Table name.
        columns: Column names and values.
        where: SQL predicate with one bound parameter.
        key: Value for that parameter.
    """
    present = _columns(conn, table)
    pairs = [(name, value) for name, value in columns.items() if name in present]
    if not pairs:
        return
    sql = f"UPDATE {table} SET {', '.join(name + ' = ?' for name, _ in pairs)} WHERE {where}"
    conn.execute(sql, [value for _, value in pairs] + [key])


def _mirror_asset(master: sqlite3.Connection, asset_id: int, columns: Mapping[str, object]) -> str | None:
    """Copy saved asset columns into the track's location database.

    Args:
        master: Read connection for the master database.
        asset_id: Asset id.
        columns: Columns already saved on the master asset row.

    Returns:
        None, or a warning when the location database is not updated.
    """
    asset = _asset_location(master, asset_id)
    paths = _location_paths(master)
    path = paths.get(int(asset["location_id"] or 0))
    external_id = asset["external_id"]
    if path is None or external_id is None:
        return "Saved in the main library. That track's drive is not connected, so Serato may reconcile the edit when the drive returns."

    def apply(conn: sqlite3.Connection) -> None:
        """Write mirrored asset columns inside the location transaction.

        Args:
            conn: Location database connection.
        """
        revision = _next_revision(conn)
        values = dict(columns)
        values["revision"] = revision
        _assign(conn, "asset", values, "id = ?", int(external_id))

    return _with_location(path, apply)


def _expect_asset(session: object, asset_id: int, values: Mapping[str, object]) -> None:
    """Register the track fields a save must leave behind.

    Args:
        session: The safe-write session, or another object when this helper
            is called without one.
        asset_id: Asset id.
        values: Columns this save assigned.
    """
    import safe_write

    if not isinstance(session, safe_write.Session):
        return
    allowed = TRACK_FIELDS | {"file_name", "is_missing", "file_size", "time_modified"}
    columns = tuple(name for name in values if isinstance(name, str) and name.isidentifier() and name in allowed)
    expected = tuple(values[name] for name in columns)

    def check(
        copied: sqlite3.Connection,
        columns: tuple[str, ...] = columns,
        expected: tuple[object, ...] = expected,
        asset_id: int = asset_id,
    ) -> None:
        """Fail when the copied row does not hold the saved fields.

        Args:
            copied: Read-only connection to the temporary database copy.
            columns: Column names that were assigned.
            expected: Values those columns should have.
            asset_id: Asset id.

        Raises:
            VerifyMismatch: If the row is missing or different.
        """
        if not columns:
            return
        sql = "SELECT " + ", ".join(columns) + " FROM asset WHERE id = ?"
        row = copied.execute(sql, (asset_id,)).fetchone()
        if row is None or tuple(row) != expected:
            raise safe_write.VerifyMismatch("The track fields do not match.")

    session.check(check)


def save_track(asset_id: int, fields: object, space: str = LIBRARY_SPACE) -> dict[str, object]:
    """Save editable fields for one track.

    Args:
        asset_id: Asset id.
        fields: Columns accepted by TRACK_FIELDS.
        space: Space that must contain the track.

    Returns:
        A dict with ok, id, and warning.

    Raises:
        LibraryError: If the fields are invalid, the track is not in the space, or the new file's size cannot be read.
        SeratoOpen: If Serato still has the library open.
    """
    cleaned = _clean_fields(fields)
    portable = cleaned.get("portable_id")
    target = str(cleaned.get("name") or f"track {asset_id}")

    def apply(conn: sqlite3.Connection, write: object) -> dict[str, object]:
        """Update the asset row and register the fields the check must see.

        Args:
            conn: Open write connection.
            write: The safe-write session.

        Returns:
            The column values that were saved.

        Raises:
            LibraryError: If the track is not in the space or a path cannot be read.
        """
        import safe_write

        session = write if isinstance(write, safe_write.Session) else None
        _space_id(conn, space)
        row = conn.execute(
            """
            SELECT a.id FROM asset a
            JOIN space_asset sa ON sa.asset_id = a.id
            JOIN space s ON s.id = sa.space_id
            WHERE a.id = ? AND s.name = ?
            """,
            (asset_id, space),
        ).fetchone()
        if row is None:
            raise LibraryError("That track is not in this space.", 404)
        values = dict(cleaned)
        if isinstance(portable, str):
            values["file_name"] = Path(portable).name
            values["is_missing"] = 0
            size_path = Path(portable) if Path(portable).is_absolute() else Path.home() / portable
            try:
                values["file_size"] = size_path.stat().st_size
            except OSError as exc:
                raise LibraryError("That path could not be read.", 400) from exc
        values["time_modified"] = int(time.time())
        _assign(conn, "asset", values, "id = ?", asset_id)
        if isinstance(values.get("name"), str):
            if session is not None:
                session.set_target(str(values["name"]))
        _expect_asset(session, asset_id, values)
        return values

    import safe_write

    values = safe_write.run("save_track", target, apply)
    mirror_values = {key: value for key, value in values.items() if key != "time_modified"}
    mirror_values["time_modified"] = values["time_modified"]
    with closing(read_conn()) as master:
        warning = _mirror_asset(master, asset_id, mirror_values)
    return {"ok": True, "id": asset_id, "warning": warning}


def _mark_smart(conn: sqlite3.Connection, crate_id: int) -> None:
    """Record a smart crate as needing a refresh when that table exists.

    Args:
        conn: Open write connection.
        crate_id: Smart crate id.
    """
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'updated_smart_crate'"
    ).fetchone()
    if exists is None or "container_id" not in _columns(conn, "updated_smart_crate"):
        return
    conn.execute("INSERT INTO updated_smart_crate (container_id) VALUES (?)", (crate_id,))


def _rules_blob(rules: object) -> str:
    """Normalize smart-crate rules to a JSON string.

    Args:
        rules: A rules dict, or a JSON string of that dict.

    Returns:
        Compact JSON.

    Raises:
        LibraryError: If the value is not a rules object with a rules list.
    """
    parsed: object = rules
    if isinstance(parsed, str):
        try:
            parsed = json.loads(parsed)
        except json.JSONDecodeError as exc:
            raise LibraryError("Smart crate rules need to be JSON.") from exc
    if not isinstance(parsed, dict):
        raise LibraryError("Smart crate rules need a rules list.")
    raw = cast("dict[object, object]", parsed)
    if not isinstance(raw.get("rules", []), list):
        raise LibraryError("Smart crate rules need a rules list.")
    return json.dumps(raw, ensure_ascii=False, separators=(",", ":"))


def _root_parent(master: sqlite3.Connection, root: sqlite3.Connection, parent_id: int, space: str) -> int | None:
    """Find the parent container id in root.sqlite for a master crate.

    Args:
        master: Master connection.
        root: Location connection.
        parent_id: Parent id in the master database.
        space: Space name.

    Returns:
        The location parent id, or None when the space is missing there.
    """
    row = master.execute(
        """
        SELECT external_container_id FROM location_container
        WHERE container_id = ? AND location_id = 3 AND external_container_id IS NOT NULL
        """,
        (parent_id,),
    ).fetchone()
    if row is not None:
        return int(row[0])
    space_row = root.execute("SELECT id FROM space WHERE name = ?", (space,)).fetchone()
    if space_row is None:
        return None
    root_row = root.execute(
        "SELECT id FROM container WHERE space_id = ? AND type = 0",
        (int(space_row[0]),),
    ).fetchone()
    return int(root_row[0]) if root_row else None


def _insert_root_container(root: sqlite3.Connection, parent_id: int, name: str, crate_type: int, space: str, rules: str | None) -> int | None:
    """Insert a crate into a location database.

    Args:
        root: Location connection.
        parent_id: Parent container id in that database.
        name: Stored crate name.
        crate_type: 1 for a normal crate, 2 for a smart crate.
        space: Space name.
        rules: Smart-crate JSON, or None.

    Returns:
        The new container id, or None when the space is missing.
    """
    space_row = root.execute("SELECT id FROM space WHERE name = ?", (space,)).fetchone()
    if space_row is None:
        return None
    revision = _next_revision(root)
    order = root.execute(
        "SELECT COALESCE(MAX(list_order), 0) + 1 FROM container WHERE parent_id = ?",
        (parent_id,),
    ).fetchone()[0]
    root.execute(
        """
        INSERT INTO container (revision, parent_id, name, type, list_order, space_id, time_added, expanded, portable_id, color)
        VALUES (?, ?, ?, ?, ?, ?, ?, 0, '', NULL)
        """,
        (revision, parent_id, name, crate_type, order, int(space_row[0]), int(time.time())),
    )
    crate_id = int(root.execute("SELECT last_insert_rowid()").fetchone()[0])
    _upsert_filename(root, crate_id, _filename(root, crate_id, crate_type), revision)
    if crate_type == 2 and rules is not None and "smart_crate_rules" in _tables(root):
        root.execute(
            """
            INSERT INTO smart_crate_rules (container_id, revision, version, rules, needs_refresh)
            VALUES (?, ?, 1, ?, 1)
            """,
            (crate_id, revision, rules),
        )
    return crate_id


def _tables(conn: sqlite3.Connection) -> set[str]:
    """Return the table names in a database.

    Args:
        conn: Open connection.

    Returns:
        Names from sqlite_master.
    """
    return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def _create_asset_ids(payload: Mapping[str, object]) -> list[int]:
    """Parse optional create assets as unique integer ids in request order.

    A missing ``assets`` key is an empty list. bool is rejected before
    ``_as_int``, which would treat ``True`` as 1.

    Args:
        payload: The crate_action JSON.

    Returns:
        Unique asset ids in first-seen order.

    Raises:
        LibraryError: If assets is present and is not a list of integers.
    """
    if "assets" not in payload:
        return []
    raw = payload["assets"]
    if not isinstance(raw, list):
        raise LibraryError("That request is not valid.")
    ids: list[int] = []
    seen: set[int] = set()
    for item in raw:
        if isinstance(item, bool) or not isinstance(item, int):
            raise LibraryError("That request is not valid.")
        if item in seen:
            continue
        seen.add(item)
        ids.append(item)
    return ids


def _create_crate(conn: sqlite3.Connection, space: str, parent_id: object, name: str, smart: bool, rules: object) -> dict[str, object]:
    """Insert a crate and mirror it to the main drive database.

    Args:
        conn: Open master write connection.
        space: Space name.
        parent_id: Parent crate id. None or the space root places the crate at the top level.
        name: Display name.
        smart: True to create a smart crate.
        rules: Smart-crate rules. An empty value gets a default rule set.

    Returns:
        A dict with ok, id, name, and warning.

    Raises:
        LibraryError: If the name is invalid or the parent is a smart crate.
    """
    root_id = _space_root(conn, space)
    parent = root_id if parent_id is None or parent_id == root_id else _as_int(parent_id)
    if parent != root_id:
        parent_row = _container(conn, parent, space)
        if int(parent_row["type"]) == 2:
            raise LibraryError("A smart crate cannot contain another crate.")
        if int(parent_row["type"]) == 0:
            parent = root_id
    crate_type = 2 if smart else 1
    stored = _stored_name(conn, parent, name, crate_type, None)
    if smart and not rules:
        rules = {"conjunction": "AND", "live_updates": True, "rules": [], "spaces": [space]}
    blob = _rules_blob(rules) if smart else None
    order = conn.execute(
        "SELECT COALESCE(MAX(list_order), 0) + 1 FROM container WHERE parent_id = ?",
        (parent,),
    ).fetchone()[0]
    conn.execute(
        """
        INSERT INTO container (parent_id, name, type, list_order, space_id, time_added, expanded, portable_id, color)
        VALUES (?, ?, ?, ?, ?, ?, 0, '', NULL)
        """,
        (parent, stored, crate_type, order, _space_id(conn, space), int(time.time())),
    )
    crate_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    _upsert_filename(conn, crate_id, _filename(conn, crate_id, crate_type))
    if smart:
        conn.execute(
            "INSERT INTO smart_crate_rules (container_id, version, rules) VALUES (?, 1, ?)",
            (crate_id, blob),
        )
        _mark_smart(conn, crate_id)
    warning = _link_new_crate(conn, crate_id, parent, stored, crate_type, space, blob)
    return {"ok": True, "id": crate_id, "name": display_name(stored), "warning": warning}


def _link_new_crate(conn: sqlite3.Connection, crate_id: int, parent_id: int, name: str, crate_type: int, space: str, rules: str | None) -> str | None:
    """Mirror a new crate into root.sqlite and store the external id.

    Args:
        conn: Open master write connection.
        crate_id: New master container id.
        parent_id: Parent id in the master database.
        name: Stored name.
        crate_type: Container type.
        space: Space name.
        rules: Smart-crate JSON, or None.

    Returns:
        None, or a warning when the drive database is not updated.
    """
    paths = _location_paths(conn)
    root_path = paths.get(3)
    if root_path is None:
        return "The crate is saved. The main drive database is not connected, so Serato may drop it on the next sync."

    created: dict[str, int | None | bool] = {"id": None, "ok": False}

    def apply(root: sqlite3.Connection):
        """Insert the mirrored crate inside the location transaction.

        Args:
            root: Location database connection.

        Returns:
            None, or a warning when the parent crate is not on that drive.
        """
        parent = _root_parent(conn, root, parent_id, space)
        if parent is None:
            return "The crate is saved. Its parent is not on the main drive, so Serato may drop it on the next sync."
        created["id"] = _insert_root_container(root, parent, name, crate_type, space, rules)
        created["ok"] = True
        return None

    warning = _with_location(root_path, apply)
    external_id = created["id"] if created["ok"] else None
    if external_id:
        conn.execute(
            """
            INSERT INTO location_container (container_id, location_id, external_container_id)
            VALUES (?, 3, ?)
            """,
            (crate_id, external_id),
        )
    return warning


def _rename_crate(conn: sqlite3.Connection, space: str, crate_id: int, name: str) -> dict[str, object]:
    """Rename a crate and refresh export filenames.

    Args:
        conn: Open master write connection.
        space: Space name.
        crate_id: Container id.
        name: New display name.

    Returns:
        A dict with ok, id, name, and warning.

    Raises:
        LibraryError: If the crate is the space root or the name is invalid.
    """
    row = _container(conn, crate_id, space)
    if int(row["type"]) == 0:
        raise LibraryError("The space root cannot be renamed.")
    stored = _stored_name(conn, int(row["parent_id"]), name, int(row["type"]), crate_id)
    conn.execute("UPDATE container SET name = ? WHERE id = ?", (stored, crate_id))
    _refresh_filenames(conn, crate_id)
    warning = _mirror_container_fields(conn, crate_id, {"name": stored}, refresh_names=True)
    return {"ok": True, "id": crate_id, "name": display_name(stored), "warning": warning}


def _external_ids(conn: sqlite3.Connection, crate_ids: list[int]) -> list[int]:
    """Return location-database ids for crates linked to location 3.

    Args:
        conn: Open master connection.
        crate_ids: Master container ids.

    Returns:
        External container ids. An empty input returns an empty list.
    """
    if not crate_ids:
        return []
    marks = ",".join("?" * len(crate_ids))
    rows = conn.execute(
        f"""
        SELECT external_container_id FROM location_container
        WHERE location_id = 3 AND external_container_id IS NOT NULL
          AND container_id IN ({marks})
        """,
        crate_ids,
    ).fetchall()
    return [int(row[0]) for row in rows]


def _delete_ids(conn: sqlite3.Connection, crate_ids: list[int]) -> None:
    """Delete crates and their membership rows.

    Args:
        conn: Open write connection. The master and location schemas differ, so the SQL follows the columns that exist.
        crate_ids: Container ids. The space root is not deleted.
    """
    if not crate_ids:
        return
    marks = ",".join("?" * len(crate_ids))
    location_column = "location_container_id" if "location_container_id" in _columns(conn, "container_asset") else None
    if location_column:
        conn.execute(
            f"""
            DELETE FROM container_asset
            WHERE location_container_id IN (
                SELECT id FROM location_container WHERE container_id IN ({marks})
            )
            """,
            crate_ids,
        )
        conn.execute(f"DELETE FROM location_container WHERE container_id IN ({marks})", crate_ids)
    elif "container_id" in _columns(conn, "container_asset"):
        conn.execute(f"DELETE FROM container_asset WHERE container_id IN ({marks})", crate_ids)
    if "smart_crate_rules" in _tables(conn):
        conn.execute(f"DELETE FROM smart_crate_rules WHERE container_id IN ({marks})", crate_ids)
    if "dj_container_metadata" in _tables(conn):
        conn.execute(f"DELETE FROM dj_container_metadata WHERE container_id IN ({marks})", crate_ids)
    for crate_id in reversed(crate_ids):
        conn.execute("DELETE FROM container WHERE id = ? AND type != 0", (crate_id,))


def _delete_crate(conn: sqlite3.Connection, space: str, crate_id: int) -> dict[str, object]:
    """Delete a crate, its descendants, and the mirrored rows.

    Args:
        conn: Open master write connection.
        space: Space name.
        crate_id: Container id.

    Returns:
        A dict with ok, id, and warning.

    Raises:
        LibraryError: If the crate is the space root or is not in the space.
    """
    row = _container(conn, crate_id, space)
    if int(row["type"]) == 0:
        raise LibraryError("The space root cannot be deleted.")
    ids = _descendant_ids(conn, crate_id)
    external = _external_ids(conn, ids)
    _delete_ids(conn, ids)
    warning = None
    root_path = _location_paths(conn).get(3)
    if external and root_path is not None:
        def apply(root: sqlite3.Connection):
            """Delete the mirrored crates inside the location transaction.

            Args:
                root: Location database connection.
            """
            whole: list[int] = []
            for external_id in external:
                whole.extend(_descendant_ids(root, external_id))
            _delete_ids(root, list(dict.fromkeys(whole)))
            return None

        warning = _with_location(root_path, apply)
    elif external:
        warning = "Deleted from the main library. The drive database was not connected."
    return {"ok": True, "id": crate_id, "warning": warning}


def _mirror_container_fields(conn: sqlite3.Connection, crate_id: int, columns: Mapping[str, object], refresh_names: bool = False) -> str | None:
    """Copy crate columns into the linked row in root.sqlite.

    Args:
        conn: Open master connection.
        crate_id: Master container id.
        columns: Columns to assign.
        refresh_names: True to rebuild export filenames after the assign.

    Returns:
        None, or a warning when the crate is not linked to the main drive.
    """
    external = _external_ids(conn, [crate_id])
    root_path = _location_paths(conn).get(3)
    if not external or root_path is None:
        return "Saved in the main library. This crate is not linked to the main drive, so Serato may reconcile it later."

    def apply(root: sqlite3.Connection):
        """Assign mirrored crate columns inside the location transaction.

        Args:
            root: Location database connection.
        """
        revision = _next_revision(root)
        values = dict(columns)
        values["revision"] = revision
        _assign(root, "container", values, "id = ?", external[0])
        if refresh_names:
            _refresh_filenames(root, external[0], revision)
        return None

    return _with_location(root_path, apply)


def _set_color(conn: sqlite3.Connection, space: str, crate_id: int, color: object) -> dict[str, object]:
    """Set a crate color.

    Args:
        conn: Open master write connection.
        space: Space name.
        crate_id: Container id.
        color: A 24-bit integer. Empty or white clears the color.

    Returns:
        A dict with ok, id, and warning.

    Raises:
        LibraryError: If the crate is the space root or the color is not a valid integer.
    """
    row = _container(conn, crate_id, space)
    if int(row["type"]) == 0:
        raise LibraryError("The space root has no color.")
    if color is None or color == "":
        value = None
    else:
        try:
            value = _as_int(color)
        except (TypeError, ValueError):
            raise LibraryError("Color needs a number.") from None
        if value < 0 or value > 0xFFFFFF:
            raise LibraryError("Color is out of range.")
        if value == 0xFFFFFF:
            value = None
    conn.execute("UPDATE container SET color = ? WHERE id = ?", (value, crate_id))
    warning = _mirror_container_fields(conn, crate_id, {"color": value})
    return {"ok": True, "id": crate_id, "warning": warning}


def _set_expanded(conn: sqlite3.Connection, space: str, crate_id: int, expanded: object) -> dict[str, object]:
    """Store whether a crate is expanded in the tree.

    Args:
        conn: Open master write connection.
        space: Space name.
        crate_id: Container id.
        expanded: A true-like value stores 1. Every other value stores 0.

    Returns:
        A dict with ok, id, and warning.

    Raises:
        LibraryError: If the crate is not in the space.
    """
    _container(conn, crate_id, space)
    value = 1 if expanded in (True, 1, "1", "true") else 0
    conn.execute("UPDATE container SET expanded = ? WHERE id = ?", (value, crate_id))
    warning = _mirror_container_fields(conn, crate_id, {"expanded": value})
    return {"ok": True, "id": crate_id, "warning": warning}


def _set_rules(conn: sqlite3.Connection, space: str, crate_id: int, rules: object) -> dict[str, object]:
    """Replace the rules of a smart crate.

    Args:
        conn: Open master write connection.
        space: Space name.
        crate_id: Container id.
        rules: Rules object or JSON text.

    Returns:
        A dict with ok, id, and warning.

    Raises:
        LibraryError: If the crate is not smart or the rules are invalid.
    """
    row = _container(conn, crate_id, space)
    if int(row["type"]) != 2:
        raise LibraryError("Only a smart crate has rules.")
    blob = _rules_blob(rules)
    conn.execute(
        "UPDATE smart_crate_rules SET version = 1, rules = ? WHERE container_id = ?",
        (blob, crate_id),
    )
    _mark_smart(conn, crate_id)
    external = _external_ids(conn, [crate_id])
    root_path = _location_paths(conn).get(3)
    warning = None
    if external and root_path is not None:
        def apply(root: sqlite3.Connection):
            """Update mirrored smart-crate rules inside the location transaction.

            Args:
                root: Location database connection.
            """
            revision = _next_revision(root)
            if "needs_refresh" in _columns(root, "smart_crate_rules"):
                root.execute(
                    """
                    UPDATE smart_crate_rules
                    SET rules = ?, version = 1, needs_refresh = 1, revision = ?
                    WHERE container_id = ?
                    """,
                    (blob, revision, external[0]),
                )
            return None

        warning = _with_location(root_path, apply)
    return {"ok": True, "id": crate_id, "warning": warning}


def _ensure_location_container(conn: sqlite3.Connection, crate_id: int, location_id: int) -> int:
    """Return the location_container row for a crate and a drive.

    Args:
        conn: Open master write connection.
        crate_id: Container id.
        location_id: Asset location id.

    Returns:
        The location_container id.

    Raises:
        LibraryError: If the drive has its own database but this crate is not stored on it.
    """
    row = conn.execute(
        """
        SELECT id FROM location_container
        WHERE container_id = ? AND location_id = ?
        """,
        (crate_id, location_id),
    ).fetchone()
    if row is not None:
        return int(row[0])
    paths = _location_paths(conn)
    external = None
    if location_id in paths:
        raise LibraryError("That crate is not stored on the same drive as this track.")
    conn.execute(
        """
        INSERT INTO location_container (container_id, location_id, external_container_id)
        VALUES (?, ?, ?)
        """,
        (crate_id, location_id, external),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def _space_asset(conn: sqlite3.Connection, asset_id: int, space: str, create: bool) -> int:
    """Return the space_asset id for a track, creating the row when asked.

    Args:
        conn: Open write connection.
        asset_id: Asset id.
        space: Space name.
        create: True inserts the membership when it is missing.

    Returns:
        The space_asset id.

    Raises:
        LibraryError: If the track is not in the space and create is false.
    """
    row = conn.execute(
        """
        SELECT sa.id FROM space_asset sa
        JOIN space s ON s.id = sa.space_id
        WHERE sa.asset_id = ? AND s.name = ?
        """,
        (asset_id, space),
    ).fetchone()
    if row is not None:
        return int(row[0])
    if not create:
        raise LibraryError("That track is not in this space.", 404)
    conn.execute(
        "INSERT INTO space_asset (asset_id, space_id) VALUES (?, ?)",
        (asset_id, _space_id(conn, space)),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def _membership(conn: sqlite3.Connection, crate_id: int, asset_id: int, space: str, add: bool) -> dict[str, object]:
    """Add or remove a track from a normal crate.

    Args:
        conn: Open master write connection.
        crate_id: Container id.
        asset_id: Asset id.
        space: Space name.
        add: True adds the track. False removes it.

    Returns:
        A dict with ok, id, and warning.

    Raises:
        LibraryError: If the crate is smart, is the space root, or the track is not in the space.
    """
    row = _container(conn, crate_id, space)
    if int(row["type"]) == 2:
        raise LibraryError("Smart crates choose their tracks from rules.")
    if int(row["type"]) == 0:
        raise LibraryError("Tracks live in a crate, not the space root.")
    asset = _asset_location(conn, asset_id)
    _space_asset(conn, asset_id, space, create=False)
    if add:
        existing = conn.execute(
            """
            SELECT ca.id FROM container_asset ca
            JOIN location_container lc ON lc.id = ca.location_container_id
            WHERE lc.container_id = ? AND ca.asset_id = ?
            """,
            (crate_id, asset_id),
        ).fetchone()
        if existing is not None:
            return {"ok": True, "id": crate_id, "warning": None}
        location_id = int(asset["location_id"])
        location_container_id = _ensure_location_container(conn, crate_id, location_id)
        space_asset_id = _space_asset(conn, asset_id, space, create=False)
        order = conn.execute(
            """
            SELECT COALESCE(MAX(list_order), 0) + 1 FROM container_asset
            WHERE location_container_id IN (SELECT id FROM location_container WHERE container_id = ?)
            """,
            (crate_id,),
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO container_asset
                (asset_id, location_container_id, space_asset_id, external_container_asset_id, list_order, time_added)
            VALUES (?, ?, ?, NULL, ?, ?)
            """,
            (asset_id, location_container_id, space_asset_id, order, int(time.time())),
        )
        warning = _mirror_membership(conn, crate_id, asset_id, space, True)
        return {"ok": True, "id": crate_id, "warning": warning}

    conn.execute(
        """
        DELETE FROM container_asset
        WHERE asset_id = ? AND location_container_id IN (
            SELECT id FROM location_container WHERE container_id = ?
        )
        """,
        (asset_id, crate_id),
    )
    warning = _mirror_membership(conn, crate_id, asset_id, space, False)
    return {"ok": True, "id": crate_id, "warning": warning}


def _mirror_membership(conn: sqlite3.Connection, crate_id: int, asset_id: int, space: str, add: bool) -> str | None:
    """Mirror a crate membership change into the location database.

    Args:
        conn: Open master connection.
        crate_id: Master container id.
        asset_id: Asset id.
        space: Space name.
        add: True adds the mirrored membership. False removes it.

    Returns:
        None, or a warning when the drive database is left unchanged.
    """
    external = _external_ids(conn, [crate_id])
    asset = _asset_location(conn, asset_id)
    root_path = _location_paths(conn).get(int(asset["location_id"] or 0))
    if int(asset["location_id"] or 0) != 3:
        root_path = _location_paths(conn).get(3) if external else None
    if not external or asset["external_id"] is None or root_path is None:
        return "Saved in the main library. This track's drive is not connected, so the crate membership may be reconciled later."
    if int(asset["location_id"] or 0) != 3 and root_path == _location_paths(conn).get(3):
        return "Saved in the main library. This track lives on another drive, so that drive's database was not changed."

    def apply(root: sqlite3.Connection):
        """Apply a membership change inside the location transaction.

        Args:
            root: Location database connection.

        Returns:
            None, or a warning when the space is missing from that database.
        """
        space_row = root.execute("SELECT id FROM space WHERE name = ?", (space,)).fetchone()
        if space_row is None:
            return "Saved in the main library. This space is not in the drive database."
        asset_row = root.execute(
            """
            SELECT sa.id FROM space_asset sa
            WHERE sa.asset_id = ? AND sa.space_id = ?
            """,
            (int(asset["external_id"]), int(space_row[0])),
        ).fetchone()
        revision = _next_revision(root)
        if add:
            if asset_row is None:
                root.execute(
                    "INSERT INTO space_asset (asset_id, space_id, revision) VALUES (?, ?, ?)",
                    (int(asset["external_id"]), int(space_row[0]), revision),
                )
                space_asset_id = int(root.execute("SELECT last_insert_rowid()").fetchone()[0])
            else:
                space_asset_id = int(asset_row[0])
            found = root.execute(
                "SELECT id FROM container_asset WHERE container_id = ? AND space_asset_id = ?",
                (external[0], space_asset_id),
            ).fetchone()
            if found is None:
                order = root.execute(
                    "SELECT COALESCE(MAX(list_order), 0) + 1 FROM container_asset WHERE container_id = ?",
                    (external[0],),
                ).fetchone()[0]
                root.execute(
                    """
                    INSERT INTO container_asset (revision, container_id, space_asset_id, list_order, time_added)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (revision, external[0], space_asset_id, order, int(time.time())),
                )
        else:
            if asset_row is not None:
                root.execute(
                    "DELETE FROM container_asset WHERE container_id = ? AND space_asset_id = ?",
                    (external[0], int(asset_row[0])),
                )
        return None

    return _with_location(root_path, apply)


def _prepare_container(conn: sqlite3.Connection) -> int:
    """Return the Prepare crate id.

    Args:
        conn: Open connection.

    Returns:
        The first Prepare container whose type is 1.

    Raises:
        LibraryError: If Prepare has no crate.
    """
    row = conn.execute(
        """
        SELECT c.id FROM container c
        JOIN space s ON s.id = c.space_id
        WHERE s.name = 'Prepare' AND c.type = 1
        ORDER BY c.id
        LIMIT 1
        """,
    ).fetchone()
    if row is None:
        raise LibraryError("Prepare is not in this library.", 404)
    return int(row[0])


def _set_prepare(conn: sqlite3.Connection, asset_id: int, add: bool) -> dict[str, object]:
    """Add or remove a track from the Prepare space.

    Args:
        conn: Open master write connection.
        asset_id: Asset id.
        add: True adds the track. False removes it from Prepare.

    Returns:
        A dict with ok, id, and warning.

    Raises:
        LibraryError: If the track or the Prepare crate is missing.
    """
    _asset_location(conn, asset_id)
    crate_id = _prepare_container(conn)
    if add:
        _space_asset(conn, asset_id, "Prepare", create=True)
        # Membership insert requires the asset to already be in the space.
        result = _membership(conn, crate_id, asset_id, "Prepare", True)
        return result
    conn.execute(
        """
        DELETE FROM container_asset
        WHERE asset_id = ? AND location_container_id IN (
            SELECT id FROM location_container WHERE container_id = ?
        )
        """,
        (asset_id, crate_id),
    )
    conn.execute(
        """
        DELETE FROM space_asset
        WHERE asset_id = ? AND space_id = (SELECT id FROM space WHERE name = 'Prepare')
        """,
        (asset_id,),
    )
    warning = _mirror_prepare(conn, asset_id, False)
    return {"ok": True, "id": asset_id, "warning": warning}


def _mirror_prepare(conn: sqlite3.Connection, asset_id: int, add: bool) -> str | None:
    """Mirror a Prepare membership change into root.sqlite.

    Args:
        conn: Open master connection.
        asset_id: Asset id.
        add: True adds the track. False removes it.

    Returns:
        None, or a warning when the drive database is left unchanged.
    """
    asset = _asset_location(conn, asset_id)
    root_path = _location_paths(conn).get(3)
    if asset["external_id"] is None or root_path is None or int(asset["location_id"] or 0) != 3:
        return "Saved in the main library. Prepare on the drive database was left unchanged."

    def apply(root: sqlite3.Connection):
        """Apply a Prepare change inside the location transaction.

        Args:
            root: Location database connection.

        Returns:
            None, or a warning when Prepare is missing from that database.
        """
        space_row = root.execute("SELECT id FROM space WHERE name = 'Prepare'").fetchone()
        crate = root.execute(
            """
            SELECT c.id FROM container c
            JOIN space s ON s.id = c.space_id
            WHERE s.name = 'Prepare' AND c.type = 1
            ORDER BY c.id LIMIT 1
            """
        ).fetchone()
        if space_row is None or crate is None:
            return "Saved in the main library. Prepare is not in the drive database."
        revision = _next_revision(root)
        if add:
            row = root.execute(
                "SELECT id FROM space_asset WHERE asset_id = ? AND space_id = ?",
                (int(asset["external_id"]), int(space_row[0])),
            ).fetchone()
            if row is None:
                root.execute(
                    "INSERT INTO space_asset (asset_id, space_id, revision) VALUES (?, ?, ?)",
                    (int(asset["external_id"]), int(space_row[0]), revision),
                )
                space_asset_id = int(root.execute("SELECT last_insert_rowid()").fetchone()[0])
            else:
                space_asset_id = int(row[0])
            found = root.execute(
                "SELECT id FROM container_asset WHERE container_id = ? AND space_asset_id = ?",
                (int(crate[0]), space_asset_id),
            ).fetchone()
            if found is None:
                order = root.execute(
                    "SELECT COALESCE(MAX(list_order), 0) + 1 FROM container_asset WHERE container_id = ?",
                    (int(crate[0]),),
                ).fetchone()[0]
                root.execute(
                    """
                    INSERT INTO container_asset (revision, container_id, space_asset_id, list_order, time_added)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (revision, int(crate[0]), space_asset_id, order, int(time.time())),
                )
        else:
            row = root.execute(
                "SELECT id FROM space_asset WHERE asset_id = ? AND space_id = ?",
                (int(asset["external_id"]), int(space_row[0])),
            ).fetchone()
            if row is not None:
                root.execute(
                    "DELETE FROM container_asset WHERE container_id = ? AND space_asset_id = ?",
                    (int(crate[0]), int(row[0])),
                )
                root.execute("DELETE FROM space_asset WHERE id = ?", (int(row[0]),))
        return None

    return _with_location(root_path, apply)


def _remove_from_space(conn: sqlite3.Connection, asset_id: int, space: str) -> dict[str, object]:
    """Remove a track from a space and from the crates in that space.

    The audio file stays on disk.

    Args:
        conn: Open master write connection.
        asset_id: Asset id.
        space: Space name.

    Returns:
        A dict with ok, id, and warning.

    Raises:
        LibraryError: If the track is not in the library or the space.
    """
    _asset_location(conn, asset_id)
    _space_asset(conn, asset_id, space, create=False)
    conn.execute(
        """
        DELETE FROM container_asset
        WHERE asset_id = ? AND space_asset_id IN (
            SELECT sa.id FROM space_asset sa
            JOIN space s ON s.id = sa.space_id
            WHERE sa.asset_id = ? AND s.name = ?
        )
        """,
        (asset_id, asset_id, space),
    )
    external = conn.execute(
        "SELECT external_id, location_id FROM asset WHERE id = ?",
        (asset_id,),
    ).fetchone()
    conn.execute(
        """
        DELETE FROM space_asset
        WHERE asset_id = ? AND space_id = (SELECT id FROM space WHERE name = ?)
        """,
        (asset_id, space),
    )
    warning = None
    root_path = _location_paths(conn).get(3)
    if external and external["external_id"] is not None and int(external["location_id"] or 0) == 3 and root_path is not None:
        def apply(root: sqlite3.Connection):
            """Remove the mirrored space membership inside the location transaction.

            Args:
                root: Location database connection.
            """
            space_row = root.execute("SELECT id FROM space WHERE name = ?", (space,)).fetchone()
            if space_row is None:
                return None
            row = root.execute(
                "SELECT id FROM space_asset WHERE asset_id = ? AND space_id = ?",
                (int(external["external_id"]), int(space_row[0])),
            ).fetchone()
            if row is None:
                return None
            _next_revision(root)
            root.execute("DELETE FROM container_asset WHERE space_asset_id = ?", (int(row[0]),))
            root.execute("DELETE FROM space_asset WHERE id = ?", (int(row[0]),))
            return None

        warning = _with_location(root_path, apply)
    elif external and int(external["location_id"] or 0) != 3:
        warning = "Removed from the main library. The file was kept. The other drive's database was not changed."
    else:
        warning = "Removed from the library. The audio file was kept."
    return {"ok": True, "id": asset_id, "warning": warning}


def _crate_target(payload: Mapping[str, object]) -> str:
    """Return the human-readable crate or track name for a crate edit.

    Args:
        payload: Crate action body.

    Returns:
        The name field when it is text, otherwise a short fallback.
    """
    name = payload.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    action = payload.get("action")
    if action == "prepare":
        return "Prepare"
    if action == "remove_library":
        return "library"
    return "crate"


def _expect_crate(
    session: object,
    action: object,
    payload: Mapping[str, object],
    result: Mapping[str, object],
) -> None:
    """Register the row check for one crate edit.

    Args:
        session: The safe-write session.
        action: Action name from the request.
        payload: Request body.
        result: Result dict from the edit. The check uses the request, and
            the result id when the action created a row.
    """
    import safe_write

    if not isinstance(session, safe_write.Session):
        return
    if action in {"create", "rename"}:
        crate_id = result.get("id")
        wanted = str(payload.get("name") or "").strip()
        if not isinstance(crate_id, int):
            return

        def check(copied: sqlite3.Connection, crate_id: int = crate_id, wanted: str = wanted) -> None:
            """Fail when the crate's display name is not the one that was asked for.

            Args:
                copied: Read-only connection to the temporary database copy.
                crate_id: Container id.
                wanted: Display name from the request.

            Raises:
                VerifyMismatch: If the stored name does not display as ``wanted``.
            """
            row = copied.execute("SELECT name FROM container WHERE id = ?", (crate_id,)).fetchone()
            if row is None or display_name(str(row[0])) != wanted:
                raise safe_write.VerifyMismatch("The crate name does not match.")

        session.check(check)
        return
    if action == "delete":
        crate_id = _as_int(payload["id"])

        def check_gone(copied: sqlite3.Connection, crate_id: int = crate_id) -> None:
            """Fail when the deleted crate is still in the library.

            Args:
                copied: Read-only connection to the temporary database copy.
                crate_id: Container id.

            Raises:
                VerifyMismatch: If the crate row remains.
            """
            row = copied.execute("SELECT COUNT(*) FROM container WHERE id = ?", (crate_id,)).fetchone()
            if row is None or int(row[0]) != 0:
                raise safe_write.VerifyMismatch("The crate is still in the library.")

        session.check(check_gone)
        return
    if action in {"add", "remove"}:
        crate_id = _as_int(payload["id"])
        asset_id = _as_int(payload["asset"])
        present = 1 if action == "add" else 0

        def check_member(
            copied: sqlite3.Connection,
            crate_id: int = crate_id,
            asset_id: int = asset_id,
            present: int = present,
        ) -> None:
            """Fail when crate membership does not match the request.

            Args:
                copied: Read-only connection to the temporary database copy.
                crate_id: Container id.
                asset_id: Asset id.
                present: 1 when the track should be in the crate.

            Raises:
                VerifyMismatch: If the membership row is missing or still there.
            """
            row = copied.execute(
                """
                SELECT COUNT(*) FROM container_asset ca
                JOIN location_container lc ON lc.id = ca.location_container_id
                WHERE lc.container_id = ? AND ca.asset_id = ?
                """,
                (crate_id, asset_id),
            ).fetchone()
            count = 0 if row is None else int(row[0])
            if (count > 0) != (present == 1):
                raise safe_write.VerifyMismatch("The crate membership does not match.")

        session.check(check_member)
        return
    if action == "remove_library":
        asset_id = _as_int(payload["asset"])
        space = cast(str, payload.get("space") or LIBRARY_SPACE)

        def check_removed(copied: sqlite3.Connection, asset_id: int = asset_id, space: str = space) -> None:
            """Fail when the track is still in the space.

            Args:
                copied: Read-only connection to the temporary database copy.
                asset_id: Asset id.
                space: Space name.

            Raises:
                VerifyMismatch: If the space membership remains.
            """
            row = copied.execute(
                """
                SELECT COUNT(*) FROM space_asset sa
                JOIN space s ON s.id = sa.space_id
                WHERE sa.asset_id = ? AND s.name = ?
                """,
                (asset_id, space),
            ).fetchone()
            if row is None or int(row[0]) != 0:
                raise safe_write.VerifyMismatch("The track is still in the library.")

        session.check(check_removed)
        return
    if action == "color":
        crate_id = _as_int(payload["id"])
        color = payload.get("color")
        if color is None or color == "":
            wanted_color: int | None = None
        else:
            wanted_color = _as_int(color)
            if wanted_color == 0xFFFFFF:
                wanted_color = None

        def check_color(
            copied: sqlite3.Connection,
            crate_id: int = crate_id,
            wanted_color: int | None = wanted_color,
        ) -> None:
            """Fail when the crate color is not the one that was asked for.

            Args:
                copied: Read-only connection to the temporary database copy.
                crate_id: Container id.
                wanted_color: Stored color, or None when the color was cleared.

            Raises:
                VerifyMismatch: If the stored color does not match.
            """
            row = copied.execute("SELECT color FROM container WHERE id = ?", (crate_id,)).fetchone()
            stored = None if row is None or row[0] is None else int(row[0])
            if row is None or stored != wanted_color:
                raise safe_write.VerifyMismatch("The crate color does not match.")

        session.check(check_color)
        return
    if action == "expanded":
        crate_id = _as_int(payload["id"])
        wanted_expanded = 1 if payload.get("expanded") in (True, 1, "1", "true") else 0

        def check_expanded(
            copied: sqlite3.Connection,
            crate_id: int = crate_id,
            wanted_expanded: int = wanted_expanded,
        ) -> None:
            """Fail when the expanded flag is not the one that was asked for.

            Args:
                copied: Read-only connection to the temporary database copy.
                crate_id: Container id.
                wanted_expanded: 1 when the crate should be expanded.

            Raises:
                VerifyMismatch: If the stored flag does not match.
            """
            row = copied.execute("SELECT expanded FROM container WHERE id = ?", (crate_id,)).fetchone()
            stored = 0 if row is None or row[0] is None else int(row[0])
            if row is None or stored != wanted_expanded:
                raise safe_write.VerifyMismatch("The crate expanded flag does not match.")

        session.check(check_expanded)
        return
    if action == "rules":
        crate_id = _as_int(payload["id"])
        wanted_rules = _rules_blob(payload.get("rules"))

        def check_rules(
            copied: sqlite3.Connection,
            crate_id: int = crate_id,
            wanted_rules: str = wanted_rules,
        ) -> None:
            """Fail when the smart-crate rules are not the ones that were asked for.

            Args:
                copied: Read-only connection to the temporary database copy.
                crate_id: Container id.
                wanted_rules: Compact JSON that was stored.

            Raises:
                VerifyMismatch: If the stored rules do not match.
            """
            row = copied.execute(
                "SELECT rules FROM smart_crate_rules WHERE container_id = ?",
                (crate_id,),
            ).fetchone()
            if row is None or str(row[0]) != wanted_rules:
                raise safe_write.VerifyMismatch("The smart crate rules do not match.")

        session.check(check_rules)
        return
    if action == "prepare":
        asset_id = _as_int(payload["asset"])
        wanted_prepare = bool(payload.get("add", True))

        def check_prepare(
            copied: sqlite3.Connection,
            asset_id: int = asset_id,
            wanted_prepare: bool = wanted_prepare,
        ) -> None:
            """Fail when Prepare membership does not match the request.

            Args:
                copied: Read-only connection to the temporary database copy.
                asset_id: Asset id.
                wanted_prepare: True when the track should be in Prepare.

            Raises:
                VerifyMismatch: If the space membership is missing or still there.
            """
            row = copied.execute(
                """
                SELECT COUNT(*) FROM space_asset sa
                JOIN space s ON s.id = sa.space_id
                WHERE sa.asset_id = ? AND s.name = 'Prepare'
                """,
                (asset_id,),
            ).fetchone()
            count = 0 if row is None else int(row[0])
            if (count > 0) != wanted_prepare:
                raise safe_write.VerifyMismatch("Prepare membership does not match.")

        session.check(check_prepare)


def crate_action(payload: Mapping[str, object]) -> dict[str, object]:
    """Run one crate edit.

    Args:
        payload: JSON object with action and the fields that action requires.
            Actions are create, rename, delete, color, expanded, rules, add,
            remove, prepare, and remove_library. Create may include assets,
            a list of unique integer track ids added in request order.

    Returns:
        The action result dict. Create includes added, the number of tracks
        stored on the new crate.

    Raises:
        LibraryError: If the action is unknown or its fields are invalid.
            A smart crate cannot take members. A track not in the space is
            404. A non-list, a bool, or a non-integer assets value is 400.
        SeratoOpen: If Serato still has the library open.
        KeyError: If a required id is missing.
    """
    action = payload.get("action")
    space = cast(str, payload.get("space") or LIBRARY_SPACE)
    target = _crate_target(payload)
    import safe_write

    def apply(conn: sqlite3.Connection, write: safe_write.Session) -> dict[str, object]:
        """Run the crate edit and register the row the check must see.

        Args:
            conn: Open write connection.
            write: Session that records the expected rows.

        Returns:
            The action result dict.

        Raises:
            LibraryError: If the action is unknown or its fields are invalid.
            KeyError: If a required id is missing.
        """
        if action == "create":
            assets = _create_asset_ids(payload)
            smart = bool(payload.get("smart"))
            if smart and assets:
                raise LibraryError("That request is not valid.")
            for asset_id in assets:
                _space_asset(conn, asset_id, space, create=False)
            result = _create_crate(
                conn,
                space,
                payload.get("parent"),
                cast(str, payload.get("name") or ""),
                smart,
                payload.get("rules"),
            )
            crate_id = int(result["id"])
            for asset_id in assets:
                _membership(conn, crate_id, asset_id, space, True)
            result["added"] = len(assets)
        elif action == "rename":
            result = _rename_crate(conn, space, _as_int(payload["id"]), cast(str, payload.get("name") or ""))
        elif action == "delete":
            result = _delete_crate(conn, space, _as_int(payload["id"]))
        elif action == "color":
            result = _set_color(conn, space, _as_int(payload["id"]), payload.get("color"))
        elif action == "expanded":
            result = _set_expanded(conn, space, _as_int(payload["id"]), payload.get("expanded"))
        elif action == "rules":
            result = _set_rules(conn, space, _as_int(payload["id"]), payload.get("rules"))
        elif action == "add":
            result = _membership(conn, _as_int(payload["id"]), _as_int(payload["asset"]), space, True)
        elif action == "remove":
            result = _membership(conn, _as_int(payload["id"]), _as_int(payload["asset"]), space, False)
        elif action == "prepare":
            result = _set_prepare(conn, _as_int(payload["asset"]), bool(payload.get("add", True)))
            if payload.get("add", True):
                # _set_prepare(add) mirrors through _membership. This also mirrors the Prepare crate.
                extra = _mirror_prepare(conn, _as_int(payload["asset"]), True)
                if extra and not result.get("warning"):
                    result["warning"] = extra
        elif action == "remove_library":
            result = _remove_from_space(conn, _as_int(payload["asset"]), space)
        else:
            raise LibraryError("That crate action is not available.")
        if isinstance(result.get("name"), str):
            write.set_target(str(result["name"]))
        _expect_crate(write, action, payload, result)
        return result

    return safe_write.run(f"crate_{action}", target, apply)


def _library_crate(conn: sqlite3.Connection, crate_id: int) -> bool:
    """Return whether a container is a crate in the Serato Library space.

    Args:
        conn: Open connection.
        crate_id: Container id.

    Returns:
        True when the row exists, is not the space root, and is in
        ``Serato Library``.
    """
    row = conn.execute(
        """
        SELECT 1 FROM container c
        JOIN space s ON s.id = c.space_id
        WHERE c.id = ? AND s.name = ? AND c.type != 0
        """,
        (crate_id, LIBRARY_SPACE),
    ).fetchone()
    return row is not None


def _find_child(conn: sqlite3.Connection, parent_id: int, name: str, crate_type: int) -> int | None:
    """Find a child crate by its visible name.

    Args:
        conn: Open connection.
        parent_id: Parent container id.
        name: Visible crate name.
        crate_type: 1 for a normal crate, 2 for a smart crate.

    Returns:
        The container id, or None when that child is absent. The match
        ignores case so a Windows file and the stored name agree.
    """
    rows = conn.execute(
        "SELECT id, name FROM container WHERE parent_id = ? AND type = ?",
        (parent_id, crate_type),
    ).fetchall()
    want = name.casefold()
    for row in rows:
        stored = row["name"] if isinstance(row["name"], str) else ""
        if display_name(stored).casefold() == want:
            return int(row["id"])
    return None


def _remember_filename(
    conn: sqlite3.Connection,
    crate_id: int,
    filename: str,
    found: dict[str, tuple[int, str]],
) -> None:
    """Store the on-disk crate file name and mirror it to root.sqlite.

    Args:
        conn: Open master write connection.
        crate_id: Container id.
        filename: Exact basename Serato should keep.
        found: Export index updated to that basename.
    """
    _upsert_filename(conn, crate_id, filename)
    previous = [key for key, item in found.items() if item[0] == crate_id]
    for key in previous:
        del found[key]
    found[filename.casefold()] = (crate_id, filename)
    external = _external_ids(conn, [crate_id])
    root_path = _location_paths(conn).get(3)
    if not external or root_path is None:
        return

    def apply(root: sqlite3.Connection) -> None:
        """Copy the export filename into the location database.

        Args:
            root: Location database connection.
        """
        if "dj_container_metadata" not in _tables(root):
            return None
        _upsert_filename(root, external[0], filename)
        return None

    _with_location(root_path, apply)


def _ensure_library_crate(
    conn: sqlite3.Connection,
    parent_id: int,
    name: str,
    smart: bool,
    found: dict[str, tuple[int, str]],
) -> int:
    """Return a Serato Library crate, creating it when it is missing.

    Args:
        conn: Open master write connection.
        parent_id: Parent container id.
        name: Visible name.
        smart: True to create a smart crate.
        found: Export index updated when a crate is created.

    Returns:
        The container id.
    """
    crate_type = 2 if smart else 1
    existing = _find_child(conn, parent_id, name, crate_type)
    if existing is not None:
        return existing
    created = _create_crate(conn, LIBRARY_SPACE, parent_id, name, smart, None)
    crate_id = int(created["id"])
    generated = _export_basename(_filename(conn, crate_id, crate_type))
    if generated:
        found[generated.casefold()] = (crate_id, generated)
    return crate_id


def _path_key(value: str) -> str:
    """Normalize a stored path for comparison.

    Args:
        value: A portable id or a path from a crate file.

    Returns:
        Forward slashes, without a trailing slash, casefolded.
    """
    return value.replace("\\", "/").strip().rstrip("/").casefold()


def _match_asset(index: Sequence[tuple[int, str, str]], stored: str) -> int | None:
    """Find the one library asset a crate path points at.

    A Windows path (``C:\\Users\\dj\\Music\\same-a.mp3``) and a macOS path
    (``/Users/dj/Music/same-a.mp3``) match a portable id of
    ``Music/same-a.mp3``. A path that climbs out with ``..`` matches nothing.
    A file name on its own is not a match, so two different tracks that share
    a name cannot be confused.

    Args:
        index: ``(asset id, portable id, file name)`` rows.
        stored: Path text from the crate file.

    Returns:
        One asset id, or None when there is no single match.
    """
    text = stored.strip()
    if not text:
        return None
    want = _path_key(text)
    parts = [part for part in want.split("/") if part not in {"", "."}]
    if not parts or any(part == ".." for part in parts):
        return None
    exact: list[int] = []
    suffix: list[int] = []
    for asset_id, portable, _file_name in index:
        key = _path_key(portable) if portable else ""
        if key and key == want:
            exact.append(asset_id)
            continue
        # Both sides need a directory. A bare file name is not a suffix of
        # a longer portable id, or the other way around.
        if key and "/" in want and "/" in key and (want.endswith("/" + key) or key.endswith("/" + want)):
            suffix.append(asset_id)
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1 or len(suffix) > 1:
        return None
    if len(suffix) == 1:
        return suffix[0]
    return None


def _add_restored_tracks(
    conn: sqlite3.Connection,
    crate_id: int,
    tracks: Sequence[str],
    index: Sequence[tuple[int, str, str]],
) -> None:
    """Add crate-file tracks that match one library asset.

    Args:
        conn: Open master write connection.
        crate_id: Normal crate id.
        tracks: Paths from the crate file, in file order.
        index: Asset rows from :func:`_asset_rows`.
    """
    seen: set[int] = set()
    for stored in tracks:
        asset_id = _match_asset(index, stored)
        if asset_id is None or asset_id in seen:
            continue
        if not _space_asset_exists(conn, asset_id, LIBRARY_SPACE):
            continue
        seen.add(asset_id)
        try:
            _membership(conn, crate_id, asset_id, LIBRARY_SPACE, True)
        except (LibraryError, TypeError, ValueError):
            continue


def _space_asset_exists(conn: sqlite3.Connection, asset_id: int, space: str) -> bool:
    """Return whether an asset is already in a space.

    Args:
        conn: Open connection.
        asset_id: Asset id.
        space: Space name.

    Returns:
        True when a space_asset row joins that space.
    """
    row = conn.execute(
        """
        SELECT 1 FROM space_asset sa
        JOIN space s ON s.id = sa.space_id
        WHERE sa.asset_id = ? AND s.name = ?
        """,
        (asset_id, space),
    ).fetchone()
    return row is not None


def _asset_rows(conn: sqlite3.Connection) -> list[tuple[int, str, str]]:
    """Load asset ids and paths for crate matching.

    Args:
        conn: Open connection.

    Returns:
        ``(id, portable id, file name)``. Missing columns yield an empty list.
    """
    if "asset" not in _tables(conn):
        return []
    rows = conn.execute("SELECT id, portable_id, file_name FROM asset").fetchall()
    found: list[tuple[int, str, str]] = []
    for row in rows:
        portable = row["portable_id"] if isinstance(row["portable_id"], str) else ""
        file_name = row["file_name"] if isinstance(row["file_name"], str) else ""
        found.append((int(row["id"]), portable, file_name))
    return found


def register_restored_crates(crates: Sequence[tuple[str, Sequence[str]]]) -> list[dict[str, object]]:
    """Register crate files Serato 4/5 would otherwise delete on launch.

    The database is the source of truth. A ``.crate`` or ``.scrate`` whose
    name it has never heard of is removed the next time Serato starts.
    This writes those crates through :func:`begin_write` with
    ``snapshot=False``: Serato must be quit, the version gate must allow
    the library, and the first write in the process still copies the
    databases into Library/Backups. The caller is a restore that already
    saved the undo snapshot. One transaction covers every crate. A file
    with no name is skipped. Tracks are added when one library asset
    matches the path.

    Args:
        crates: ``(filename, track paths)`` pairs. ``filename`` is the
            on-disk basename. Track paths are the crate file's ``ptrk``
            values, in order.

    Returns:
        One dict per crate that was created, whose export filename was
        set to the on-disk name, or whose tracks were added. Each has
        ``filename``, ``id``, and ``name``. The restore check uses that
        list so those rows, and no others, may differ from the snapshot.

    Raises:
        SeratoOpen: If Serato holds the library lock. Nothing is written.
        LibraryError: If the version gate refuses the library, or a crate
            name cannot be stored. The transaction is rolled back.
    """
    def order(item: tuple[str, Sequence[str]]) -> tuple[int, str]:
        base = _export_basename(item[0]).casefold()
        return (base.count("%%"), base)

    ordered = sorted(crates, key=order)
    conn = begin_write(snapshot=False)
    registered: list[dict[str, object]] = []
    try:
        found = _export_index(conn)
        index = _asset_rows(conn)
        for filename, tracks in ordered:
            base = _export_basename(filename)
            try:
                leaf, parents, smart = _split_crate_filename(base)
            except LibraryError:
                app_log.logger.warning("A crate file was not registered because it has no name.")
                continue
            key = base.casefold()
            current = found.get(key)
            if current is not None and _library_crate(conn, current[0]):
                crate_id, exact = current
                if exact != base:
                    _remember_filename(conn, crate_id, base, found)
                if not smart:
                    _add_restored_tracks(conn, crate_id, tracks, index)
                if exact != base or not smart:
                    registered.append({"filename": base, "id": crate_id, "name": leaf})
                continue
            if current is not None:
                continue
            parent_id = _space_root(conn, LIBRARY_SPACE)
            for part in parents:
                parent_id = _ensure_library_crate(conn, parent_id, part, False, found)
            crate_id = _ensure_library_crate(conn, parent_id, leaf, smart, found)
            _remember_filename(conn, crate_id, base, found)
            if not smart:
                _add_restored_tracks(conn, crate_id, tracks, index)
            registered.append({"filename": base, "id": crate_id, "name": leaf})
        conn.commit()
        return registered
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def history_sessions() -> list[dict[str, object]]:
    """List history sessions, newest first.

    Reads history_session and history_entry from the master database.
    The query does not write, and it does not open audio files.

    Returns:
        Session dicts with id, name, times, entry count, and played count.
    """
    with closing(read_conn()) as conn:
        rows = conn.execute(
            """
            SELECT s.id, s.name, s.start_time, s.end_time,
                   COUNT(e.id) AS entries,
                   COALESCE(SUM(CASE WHEN e.played THEN 1 ELSE 0 END), 0) AS played
            FROM history_session s
            LEFT JOIN history_entry e ON e.session_id = s.id
            GROUP BY s.id
            ORDER BY s.start_time DESC, s.id DESC
            """
        ).fetchall()
    return [
        {
            "id": row["id"],
            "name": row["name"] or "Session",
            "start_time": row["start_time"],
            "end_time": row["end_time"],
            "entries": row["entries"],
            "played": row["played"],
        }
        for row in rows
    ]


def history_entries(session_id: int) -> dict[str, object]:
    """Load one history session and its played entries.

    Reads history_session and history_entry. It does not write the database
    or open the audio files named on the rows.

    Args:
        session_id: history_session id.

    Returns:
        The session fields and an entries list.

    Raises:
        LibraryError: If the session does not exist.
    """
    with closing(read_conn()) as conn:
        session = conn.execute(
            "SELECT id, name, start_time, end_time, notes FROM history_session WHERE id = ?",
            (session_id,),
        ).fetchone()
        if session is None:
            raise LibraryError("That history session is not in the library.", 404)
        rows = conn.execute(
            """
            SELECT id, asset_id, name, artist, album, bpm, key, length_ms,
                   start_time, end_time, played, deck, notes, file_name, is_missing
            FROM history_entry
            WHERE session_id = ?
            ORDER BY start_time, id
            """,
            (session_id,),
        ).fetchall()
    return {
        "id": session["id"],
        "name": session["name"] or "Session",
        "start_time": session["start_time"],
        "end_time": session["end_time"],
        "notes": session["notes"] or "",
        "entries": [
            {
                "id": row["id"],
                "asset_id": row["asset_id"],
                "name": row["name"] or "",
                "artist": row["artist"] or "",
                "album": row["album"] or "",
                "bpm": row["bpm"],
                "key": row["key"] or "",
                "length_ms": row["length_ms"],
                "start_time": row["start_time"],
                "end_time": row["end_time"],
                "played": int(row["played"] or 0),
                "deck": row["deck"] or "",
                "notes": row["notes"] or "",
                "file": row["file_name"] or "",
                "missing": int(row["is_missing"] or 0),
            }
            for row in rows
        ],
    }


def duplicate_groups(space: str = LIBRARY_SPACE) -> list[dict[str, object]]:
    """Group tracks that share a title, artist, and length in whole seconds.

    Reads the asset and space tables. Whole seconds come from integer
    division of length_ms. The query does not write.

    Args:
        space: Space to scan.

    Returns:
        Groups with name, artist, seconds, and asset ids sorted by id. Empty titles and artists are skipped.

    Raises:
        LibraryError: If the space is not allowed.
    """
    if space not in ALLOWED_SPACES:
        raise LibraryError("That space is not available here.")
    with closing(read_conn()) as conn:
        rows = conn.execute(
            """
            SELECT a.name, a.artist, CAST(a.length_ms / 1000 AS INTEGER) AS seconds,
                   GROUP_CONCAT(a.id) AS ids
            FROM asset a
            JOIN space_asset sa ON sa.asset_id = a.id
            JOIN space s ON s.id = sa.space_id
            WHERE s.name = ?
              AND TRIM(COALESCE(a.name, '')) != ''
              AND TRIM(COALESCE(a.artist, '')) != ''
              AND a.length_ms IS NOT NULL
            GROUP BY a.name, a.artist, seconds
            HAVING COUNT(*) > 1
            ORDER BY COUNT(*) DESC, a.name COLLATE NOCASE
            """,
            (space,),
        ).fetchall()
    groups: list[dict[str, object]] = []
    for row in rows:
        raw_ids: object = row["ids"] or ""
        ids = sorted(int(part) for part in cast(str, raw_ids).split(",") if part)
        groups.append(
            {
                "name": row["name"],
                "artist": row["artist"],
                "seconds": row["seconds"],
                "ids": ids,
            }
        )
    return groups


# Text copied onto the kept track only when that field is empty. These describe
# the recording. File identity (path, size, bitrate, length) is never copied.
_MERGE_TEXT_FIELDS = (
    "album",
    "genre",
    "year",
    "composer",
    "remixer",
    "label",
    "grouping",
    "comments",
    "key",
    "emoji",
    "part_of_set",
    "track_number",
    "comment_language",
    "comment_descriptor",
)
_MERGE_FIELD_LABELS = {
    "album": "Album",
    "genre": "Genre",
    "year": "Year",
    "composer": "Composer",
    "remixer": "Remixer",
    "label": "Label",
    "grouping": "Grouping",
    "comments": "Comments",
    "key": "Key",
    "emoji": "Emoji",
    "part_of_set": "Disc",
    "track_number": "Track number",
    "comment_language": "Comment language",
    "comment_descriptor": "Comment descriptor",
    "bpm": "BPM",
    "color": "Color",
    "rating": "Rating",
    "dj_play_count": "Play count",
    "time_added": "Date added",
    "dj_recently_played": "Recently played",
    "is_beatgrid_locked": "Beatgrid lock",
}
_NO_COLOR = 0xFFFFFF
_SQL_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_CUE_WARNING_TAIL = (
    "Those markers stay in the other audio file. "
    "This app does not copy them when the frames cannot be rewritten safely. "
    "Keep that copy instead if you need its cues."
)
_PUBLIC_FILE_KEYS = ("id", "file", "on_disk", "blocks_trash", "reason")
_PUBLIC_CUE_COPY_KEYS = ("file", "markers", "beatgrid", "status")


def _optional_bool(value: object, default: bool = False) -> bool:
    """Return a JSON boolean, rejecting other types.

    Args:
        value: A payload field. None uses the default.
        default: Value when the field was omitted.

    Returns:
        The boolean.

    Raises:
        LibraryError: If the value is present and is not a boolean.
    """
    if value is None:
        return default
    if not isinstance(value, bool):
        raise LibraryError("That request is not valid.")
    return value


def _blank_text(value: object) -> bool:
    """Return whether a library text field has nothing to copy.

    Args:
        value: A column value.

    Returns:
        True for None or whitespace.
    """
    return value is None or (isinstance(value, str) and value.strip() == "")


def _sql_name(name: str) -> str:
    """Return a schema identifier that is safe to interpolate.

    Args:
        name: Table name read from sqlite_master.

    Returns:
        The same name when it is a plain identifier.

    Raises:
        LibraryError: If the name is not a simple identifier.
    """
    if not _SQL_IDENT.match(name):
        raise LibraryError("The library schema could not be updated.")
    return name


def _row_values(row: sqlite3.Row) -> dict[str, object]:
    """Copy one SQLite row into a plain dict.

    Args:
        row: Row from a query.

    Returns:
        Column names and values. The dict outlives the connection.
    """
    return {key: row[key] for key in row.keys()}


def _history_count(conn: sqlite3.Connection, asset_ids: list[int]) -> int | None:
    """Count history rows that point at these assets.

    Args:
        conn: Open connection.
        asset_ids: Asset ids to look up.

    Returns:
        The count, or None when history_entry has no asset id column.
    """
    if "history_entry" not in _tables(conn):
        return None
    if "asset_id" not in _columns(conn, "history_entry"):
        return None
    if not asset_ids:
        return 0
    marks = ",".join("?" * len(asset_ids))
    row = conn.execute(
        f"SELECT COUNT(*) FROM history_entry WHERE asset_id IN ({marks})",
        asset_ids,
    ).fetchone()
    return int(row[0])


def _repoint_history(conn: sqlite3.Connection, keep_id: int, remove_ids: list[int]) -> int | None:
    """Point history rows at the kept asset without rewriting the played snapshot.

    The name, artist, and file name on the history row stay as they were
    when the track was played. Only asset_id changes, and only when that
    column exists.

    Args:
        conn: Open write connection.
        keep_id: Asset id that remains.
        remove_ids: Asset ids being removed.

    Returns:
        The number of rows updated, or None when the column is absent.
    """
    count = _history_count(conn, remove_ids)
    if not count:
        return count
    marks = ",".join("?" * len(remove_ids))
    conn.execute(
        f"UPDATE history_entry SET asset_id = ? WHERE asset_id IN ({marks})",
        [keep_id, *remove_ids],
    )
    return count


def _delete_asset_refs(conn: sqlite3.Connection, asset_id: int) -> None:
    """Delete rows that point at an asset, leaving history and the asset row.

    Args:
        conn: Open write connection.
        asset_id: Asset id being removed.

    Raises:
        LibraryError: If a table name from the schema is not a plain identifier.
    """
    for name in sorted(_tables(conn)):
        if name == "asset" or name.startswith("history") or name.startswith("sqlite_"):
            continue
        if not _SQL_IDENT.match(name):
            raise LibraryError("The library schema could not be updated.")
        if "asset_id" not in _columns(conn, name):
            continue
        conn.execute(f"DELETE FROM {_sql_name(name)} WHERE asset_id = ?", (asset_id,))


def _asset_spaces(conn: sqlite3.Connection, asset_id: int) -> list[str]:
    """List space names that contain one asset.

    Args:
        conn: Open connection.
        asset_id: Asset id.

    Returns:
        Space names in alphabetical order.
    """
    rows = conn.execute(
        """
        SELECT s.name FROM space_asset sa
        JOIN space s ON s.id = sa.space_id
        WHERE sa.asset_id = ?
        ORDER BY s.name
        """,
        (asset_id,),
    ).fetchall()
    return [str(row[0]) for row in rows if isinstance(row[0], str)]


def _asset_crates(conn: sqlite3.Connection, asset_id: int) -> list[dict[str, object]]:
    """List crate memberships for one asset.

    Args:
        conn: Open connection.
        asset_id: Asset id.

    Returns:
        Dicts with crate_id, name, type, space, and list_order. Smart crates
        and the space root are included so the caller can skip them.
    """
    columns = _columns(conn, "container_asset")
    if "location_container_id" in columns and "location_container" in _tables(conn):
        rows = conn.execute(
            """
            SELECT c.id AS crate_id, c.name AS name, c.type AS type,
                   s.name AS space_name, ca.list_order AS list_order
            FROM container_asset ca
            JOIN location_container lc ON lc.id = ca.location_container_id
            JOIN container c ON c.id = lc.container_id
            JOIN space s ON s.id = c.space_id
            WHERE ca.asset_id = ?
            ORDER BY ca.list_order, c.id
            """,
            (asset_id,),
        ).fetchall()
    elif "container_id" in columns:
        rows = conn.execute(
            """
            SELECT c.id AS crate_id, c.name AS name, c.type AS type,
                   s.name AS space_name, ca.list_order AS list_order
            FROM container_asset ca
            JOIN container c ON c.id = ca.container_id
            JOIN space s ON s.id = c.space_id
            WHERE ca.asset_id = ?
            ORDER BY ca.list_order, c.id
            """,
            (asset_id,),
        ).fetchall()
    else:
        return []
    found: list[dict[str, object]] = []
    for row in rows:
        stored = row["name"] if isinstance(row["name"], str) else ""
        order = row["list_order"]
        found.append(
            {
                "crate_id": int(row["crate_id"]),
                "name": display_name(stored),
                "type": int(row["type"] or 0),
                "space": str(row["space_name"] or ""),
                "list_order": int(order) if order is not None else None,
            }
        )
    return found


def _ensure_space_member(conn: sqlite3.Connection, asset_id: int, space: str) -> int:
    """Return the space_asset id, inserting the kept track when it is missing.

    Merge may place the kept track in a space the page does not browse, when
    a duplicate was already there. The space name still has to exist.

    Args:
        conn: Open write connection.
        asset_id: Asset id that is being kept.
        space: Space name.

    Returns:
        The space_asset id.

    Raises:
        LibraryError: If the space is not in this library.
    """
    row = conn.execute(
        """
        SELECT sa.id FROM space_asset sa
        JOIN space s ON s.id = sa.space_id
        WHERE sa.asset_id = ? AND s.name = ?
        """,
        (asset_id, space),
    ).fetchone()
    if row is not None:
        return int(row[0])
    space_row = conn.execute("SELECT id FROM space WHERE name = ?", (space,)).fetchone()
    if space_row is None:
        raise LibraryError(f"{space} is not in this library.", 404)
    conn.execute(
        "INSERT INTO space_asset (asset_id, space_id) VALUES (?, ?)",
        (asset_id, int(space_row[0])),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def _insert_at_order(
    conn: sqlite3.Connection,
    crate_id: int,
    asset_id: int,
    space: str,
    list_order: int | None,
) -> None:
    """Add the kept track to a crate at a chosen position.

    Args:
        conn: Open master write connection.
        crate_id: Container id.
        asset_id: Asset id that is being kept.
        space: Space that owns the crate.
        list_order: Position taken from the earliest duplicate. None appends.

    Raises:
        LibraryError: If this database cannot store crate membership.
    """
    needed = {"asset_id", "location_container_id", "space_asset_id", "list_order"}
    if not needed <= _columns(conn, "container_asset"):
        raise LibraryError("This library's crate list cannot be updated.")
    asset = _asset_location(conn, asset_id)
    space_asset_id = _ensure_space_member(conn, asset_id, space)
    location_id = int(asset["location_id"] or 0)
    location_container_id = _ensure_location_container(conn, crate_id, location_id)
    if list_order is None:
        list_order = int(
            conn.execute(
                """
                SELECT COALESCE(MAX(list_order), 0) + 1 FROM container_asset
                WHERE location_container_id IN (
                    SELECT id FROM location_container WHERE container_id = ?
                )
                """,
                (crate_id,),
            ).fetchone()[0]
        )
    conn.execute(
        """
        INSERT INTO container_asset
            (asset_id, location_container_id, space_asset_id, external_container_asset_id, list_order, time_added)
        VALUES (?, ?, ?, NULL, ?, ?)
        """,
        (asset_id, location_container_id, space_asset_id, list_order, int(time.time())),
    )


def _same_file(left: Path, right: Path) -> bool:
    """Return whether two paths name the same directory entry.

    Args:
        left: First path.
        right: Second path.

    Returns:
        True when both exist and share a device and inode. A missing path
        is not the same file.
    """
    try:
        left_stat = left.stat()
        right_stat = right.stat()
    except OSError:
        return False
    return left_stat.st_dev == right_stat.st_dev and left_stat.st_ino == right_stat.st_ino


def _protected_library_path(path: Path) -> bool:
    """Return whether a path is the library database or lives inside its folder.

    The check uses the resolved path and its parents. A sibling directory
    whose name only starts with the library folder name is not protected.

    Args:
        path: Candidate audio path. Symlinks are classified by the caller.

    Returns:
        True when the file must not be moved to the Trash.
    """
    try:
        resolved = path.resolve()
    except OSError:
        return True
    master = Path(MASTER).resolve()
    library_dir = master.parent
    root = library_dir / "root.sqlite"
    if _same_file(path, master) or (root.is_file() and _same_file(path, root)):
        return True
    if resolved == library_dir or library_dir in resolved.parents:
        return True
    return resolved.name in {"master.sqlite", "root.sqlite"}


def _classify_audio(
    portable_id: object,
    file_name: object,
    asset_id: int,
    kept_path: Path | None,
) -> dict[str, object]:
    """Decide whether one duplicate file may move to the Trash.

    Args:
        portable_id: Stored path.
        file_name: Display name stored on the asset.
        asset_id: Asset id.
        kept_path: Resolved path of the copy being kept, or None.

    Returns:
        A file dict. ``path`` is private and is removed before the response
        is sent. ``blocks_trash`` is true when moving the file would be unsafe.
    """
    label = file_name if isinstance(file_name, str) and file_name else f"Track {asset_id}"
    info: dict[str, object] = {
        "id": asset_id,
        "file": label,
        "on_disk": False,
        "blocks_trash": False,
        "reason": "This file is already absent.",
        "path": None,
    }
    raw = _resolved(portable_id if isinstance(portable_id, str) else None)
    if not raw:
        info["reason"] = "This copy has no file path."
        return info
    path = Path(raw)
    info["path"] = path
    if path.is_symlink():
        info["blocks_trash"] = True
        info["reason"] = "This copy is a shortcut. The file was not moved."
        return info
    if path.is_dir():
        info["blocks_trash"] = True
        info["reason"] = "This path is a folder. The folder was not moved."
        return info
    if not path.is_file():
        info["reason"] = "This file is already absent."
        return info
    if _protected_library_path(path):
        info["on_disk"] = True
        info["blocks_trash"] = True
        info["reason"] = "This file is inside the library database folder. It was not moved."
        return info
    if kept_path is not None and _same_file(path, kept_path):
        info["on_disk"] = True
        info["blocks_trash"] = True
        info["reason"] = (
            "This copy points at the same file as the copy you are keeping. That file was not moved."
        )
        return info
    info["on_disk"] = True
    info["reason"] = ""
    return info


def _regular_audio(portable_id: object) -> Path | None:
    """Return a regular audio file for a stored path.

    Args:
        portable_id: Stored path.

    Returns:
        The resolved file, or None when it is missing, a shortcut, or not a file.
    """
    raw = _resolved(portable_id if isinstance(portable_id, str) else None)
    if not raw:
        return None
    path = Path(raw)
    try:
        if path.is_symlink() or not path.is_file():
            return None
    except OSError:
        return None
    return path


def _marker_score(parsed: Mapping[str, object]) -> tuple[int, int, int]:
    """Score cue, loop, and flip counts for a merge.

    Args:
        parsed: Marker lists from ``read_serato_tags``.

    Returns:
        Cue, loop, and flip counts. A missing list counts as zero.
    """
    cues = parsed.get("cues") if isinstance(parsed.get("cues"), list) else []
    loops = parsed.get("loops") if isinstance(parsed.get("loops"), list) else []
    flips = parsed.get("flips") if isinstance(parsed.get("flips"), list) else []
    return (len(cues), len(loops), len(flips))


def _has_beatgrid(parsed: Mapping[str, object], frames: Mapping[str, bytes]) -> bool:
    """Return whether a file has a beatgrid payload or parsed markers.

    Args:
        parsed: Marker lists from ``read_serato_tags``.
        frames: Stored frames from ``snapshot_frames.read_stored_frames``.

    Returns:
        True when a BeatGrid frame or a parsed marker list is present.
    """
    grid = parsed.get("beatgrid")
    return bool(frames.get("BeatGrid")) or (isinstance(grid, list) and bool(grid))


def _frames_compatible(source: Path, dest: Path) -> bool:
    """Return whether stored Serato frames can move from source onto dest.

    The bytes are container-specific. An ID3 destination with no tag is
    written as version 2.3, so the source tag must already be 2.3.

    Args:
        source: File that holds the frames.
        dest: File that should receive them.

    Returns:
        True when both files use the same container and ID3 versions match.
    """
    src_kind = snapshot_frames._sniff_container(source)
    dst_kind = snapshot_frames._sniff_container(dest)
    if src_kind != dst_kind:
        return False
    if src_kind != "id3":
        return True
    src_ver, _, _ = snapshot_frames._split_id3(source)
    dst_ver, dst_frames, dst_off = snapshot_frames._split_id3(dest)
    if dst_off == 0 and not dst_frames:
        return src_ver == 3
    return src_ver == dst_ver


def _cannot_copy_warning(names: list[str]) -> str:
    """Warn when a duplicate has markers that cannot be copied.

    Args:
        names: Duplicate file names, not paths.

    Returns:
        A warning for the preview.
    """
    if len(names) == 1:
        head = f"{names[0]} has Serato cues, loops, flips, or a beatgrid."
    else:
        head = f"{', '.join(names[:-1])} and {names[-1]} have Serato cues, loops, flips, or a beatgrid."
    return f"{head} The copy you are keeping does not. {_CUE_WARNING_TAIL}"


def _plan_cue_copy(
    kept: Mapping[str, object],
    removes: list[dict[str, object]],
) -> dict[str, object]:
    """Choose the best Markers2 and BeatGrid frames to copy onto the kept file.

    Markers2 comes from the copy with the most cues, then loops, then flips.
    The kept file wins a tie. BeatGrid stays on the kept file when it has
    one. Otherwise it comes from the first duplicate that has a grid,
    preferring a locked grid. Frames are copied only when both files use
    the same container. Autotags stay with the kept file.

    Args:
        kept: Kept asset columns.
        removes: Duplicate asset columns, in id order.

    Returns:
        Dest path, frames to write, lock update, public ``cue_copy``, and
        ``cue_warning``. ``write`` is true when the kept file should change.
    """
    dest = _regular_audio(kept.get("portable_id"))
    members: list[dict[str, object]] = []
    for index, row in enumerate([kept, *removes]):
        path = _regular_audio(row.get("portable_id"))
        parsed = read_serato_tags(str(path) if path is not None else None)
        frames = snapshot_frames.read_stored_frames(path)
        members.append(
            {
                "keep": index == 0,
                "path": path,
                "parsed": parsed,
                "frames": frames,
                "score": _marker_score(parsed),
                "grid": _has_beatgrid(parsed, frames),
                "locked": int(row.get("is_beatgrid_locked") or 0),
                "file": str(row.get("file_name") or f"Track {row.get('id')}"),
            }
        )
    dest_member = members[0]
    others = members[1:]
    best_markers = dest_member
    for other in others:
        if cast(tuple[int, int, int], other["score"]) > cast(tuple[int, int, int], best_markers["score"]):
            best_markers = other
    best_grid = dest_member
    if not dest_member["grid"]:
        for other in others:
            if not other["grid"]:
                continue
            if not best_grid["grid"]:
                best_grid = other
                continue
            if int(cast(int, other["locked"])) > int(cast(int, best_grid["locked"])):
                best_grid = other
    wanted: dict[str, bytes] = dict(snapshot_frames.read_stored_frames(dest)) if dest is not None else {}
    copy_markers = False
    copy_grid = False
    source_name = ""
    cannot: list[str] = []
    lock: int | None = None
    if best_markers is not dest_member:
        src_path = best_markers["path"]
        frames = cast(dict[str, bytes], best_markers["frames"])
        if (
            dest is not None
            and isinstance(src_path, Path)
            and "Markers2" in frames
            and _frames_compatible(src_path, dest)
        ):
            wanted["Markers2"] = frames["Markers2"]
            copy_markers = True
            source_name = str(best_markers["file"])
        elif cast(tuple[int, int, int], best_markers["score"]) > (0, 0, 0):
            cannot.append(str(best_markers["file"]))
    if best_grid is not dest_member:
        src_path = best_grid["path"]
        frames = cast(dict[str, bytes], best_grid["frames"])
        if (
            dest is not None
            and isinstance(src_path, Path)
            and "BeatGrid" in frames
            and _frames_compatible(src_path, dest)
        ):
            wanted["BeatGrid"] = frames["BeatGrid"]
            copy_grid = True
            if not copy_markers:
                source_name = str(best_grid["file"])
            lock = int(cast(int, best_grid["locked"]))
        elif best_grid["grid"]:
            name = str(best_grid["file"])
            if name not in cannot:
                cannot.append(name)
    write = bool(dest is not None and (copy_markers or copy_grid))
    public: dict[str, object] | None = None
    warning: str | None = None
    if write:
        public = {
            "file": source_name,
            "markers": copy_markers,
            "beatgrid": copy_grid,
            "status": "planned",
        }
    elif cannot:
        warning = _cannot_copy_warning(cannot)
    return {
        "dest": dest,
        "wanted": wanted,
        "write": write,
        "lock": lock,
        "public": public,
        "warning": warning,
    }


def _apply_cue_copy(plan: dict[str, object]) -> None:
    """Write planned Markers2 and BeatGrid frames onto the kept file.

    A failed rewrite leaves the previous bytes in place and sets
    ``cue_warning``. The planned ``is_beatgrid_locked`` update is dropped
    so the kept row stays unlocked when the dest file still has no grid.
    The library merge still runs.

    Args:
        plan: Merge plan with ``_cue_copy``.
    """
    copy = plan.get("_cue_copy")
    if not isinstance(copy, dict) or not copy.get("write"):
        return
    dest = copy.get("dest")
    wanted = copy.get("wanted")
    public = copy.get("public")
    if not isinstance(dest, Path) or not isinstance(wanted, dict):
        return
    try:
        snapshot_frames.restore_stored_frames(dest, wanted)
    except (OSError, snapshot_frames.FrameRewriteError):
        name = ""
        if isinstance(public, dict) and isinstance(public.get("file"), str):
            name = str(public["file"])
        plan["cue_warning"] = _cannot_copy_warning([name or "A duplicate"])
        if isinstance(public, dict):
            public["status"] = "failed"
            plan["cue_copy"] = public
        updates = plan.get("_updates")
        if isinstance(updates, dict):
            updates.pop("is_beatgrid_locked", None)
        fields = plan.get("fields")
        if isinstance(fields, list):
            plan["fields"] = [
                item
                for item in fields
                if not (isinstance(item, dict) and item.get("field") == "is_beatgrid_locked")
            ]
        return
    if isinstance(public, dict):
        public["status"] = "copied"
        plan["cue_copy"] = public
    plan["cue_warning"] = None


def _color_text(value: object) -> str:
    """Format a Serato color for the merge preview.

    Args:
        value: Color integer, or None.

    Returns:
        ``none`` for white or a missing color, otherwise ``#RRGGBB``.
    """
    if value is None:
        return "none"
    try:
        number = int(cast(int, value))
    except (TypeError, ValueError):
        return "none"
    if number == _NO_COLOR:
        return "none"
    return f"#{number:06X}"


def _preview_change(field: str, before: object, after: object) -> dict[str, object]:
    """Build one preview row for a field that will change.

    Args:
        field: Column name.
        before: Current value on the kept track.
        after: Value after the merge.

    Returns:
        A dict with field, label, before, and after.
    """
    return {
        "field": field,
        "label": _MERGE_FIELD_LABELS.get(field, field),
        "before": before,
        "after": after,
    }


def _merge_field_updates(
    kept: Mapping[str, object],
    removes: list[dict[str, object]],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Choose metadata to copy onto the kept track.

    Empty text and an empty BPM are filled from the first duplicate, in
    asset-id order, that has a value. Play count and rating keep the
    highest number. A white color is filled from the first real color.
    Date added keeps the earliest timestamp. Recently played is set when
    any copy was recently played.

    File fields are not copied. ``is_beatgrid_locked`` is copied only when
    the beatgrid frames themselves are copied onto the kept file.

    Args:
        kept: Kept asset columns.
        removes: Duplicate columns, in id order.

    Returns:
        The column updates, and the preview rows for values that change.
        ``key_value`` is updated when the key is filled and is omitted
        from the preview.
    """
    updates: dict[str, object] = {}
    preview: list[dict[str, object]] = []
    for field in _MERGE_TEXT_FIELDS:
        if field not in kept or not _blank_text(kept.get(field)):
            continue
        limit = 16 if field == "emoji" else 4000
        for other in removes:
            candidate = other.get(field)
            if not isinstance(candidate, str) or candidate.strip() == "":
                continue
            if len(candidate) > limit:
                continue
            updates[field] = candidate
            preview.append(_preview_change(field, "", candidate))
            break
    if "key" in updates and "key_value" in kept:
        updates["key_value"] = serato_key_type(updates["key"])
    if "bpm" in kept and kept.get("bpm") is None:
        for other in removes:
            candidate = other.get("bpm")
            if candidate is None:
                continue
            updates["bpm"] = candidate
            preview.append(_preview_change("bpm", None, candidate))
            break
    for field in ("rating", "dj_play_count"):
        if field not in kept:
            continue
        best = kept.get(field)
        for other in removes:
            candidate = other.get(field)
            if candidate is None:
                continue
            if best is None or float(cast(float, candidate)) > float(cast(float, best)):
                best = candidate
        if best != kept.get(field):
            updates[field] = best
            preview.append(_preview_change(field, kept.get(field), best))
    if "color" in kept:
        current = kept.get("color")
        current_missing = current is None or int(cast(int, current)) == _NO_COLOR
        if current_missing:
            for other in removes:
                candidate = other.get("color")
                if candidate is None or int(cast(int, candidate)) == _NO_COLOR:
                    continue
                updates["color"] = int(cast(int, candidate))
                preview.append(_preview_change("color", _color_text(current), _color_text(candidate)))
                break
    if "time_added" in kept:
        stamps = [kept.get("time_added"), *[row.get("time_added") for row in removes]]
        numbers = [int(cast(int, stamp)) for stamp in stamps if stamp is not None]
        current = kept.get("time_added")
        if numbers and (current is None or min(numbers) < int(cast(int, current))):
            earliest = min(numbers)
            updates["time_added"] = earliest
            preview.append(_preview_change("time_added", current, earliest))
    if "dj_recently_played" in kept:
        current = int(kept.get("dj_recently_played") or 0)
        if current == 0 and any(int(row.get("dj_recently_played") or 0) for row in removes):
            updates["dj_recently_played"] = 1
            preview.append(_preview_change("dj_recently_played", 0, 1))
    return updates, preview


def _group_members(
    conn: sqlite3.Connection, space: str, keep_id: int
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Load the duplicate group that contains the kept track.

    The group is the same set ``duplicate_groups`` would return: one space,
    exact title, exact artist, and length in whole seconds.

    Args:
        conn: Open connection.
        space: Space name.
        keep_id: Asset id to keep.

    Returns:
        The kept row and the other rows, in asset-id order.

    Raises:
        LibraryError: If the track is missing, or it is not in a duplicate group.
    """
    if space not in ALLOWED_SPACES:
        raise LibraryError("That space is not available here.")
    row = conn.execute(
        """
        SELECT a.* FROM asset a
        JOIN space_asset sa ON sa.asset_id = a.id
        JOIN space s ON s.id = sa.space_id
        WHERE a.id = ? AND s.name = ?
        """,
        (keep_id, space),
    ).fetchone()
    if row is None:
        raise LibraryError("That track is not in this space.", 404)
    kept = _row_values(row)
    name = kept.get("name")
    artist = kept.get("artist")
    length = kept.get("length_ms")
    if not isinstance(name, str) or not isinstance(artist, str) or _blank_text(name) or _blank_text(artist):
        raise LibraryError("That track is not in a duplicate group.")
    if length is None:
        raise LibraryError("That track is not in a duplicate group.")
    rows = conn.execute(
        """
        SELECT a.* FROM asset a
        JOIN space_asset sa ON sa.asset_id = a.id
        JOIN space s ON s.id = sa.space_id
        WHERE s.name = ?
          AND a.name = ?
          AND a.artist = ?
          AND a.length_ms IS NOT NULL
          AND CAST(a.length_ms / 1000 AS INTEGER) = CAST(? / 1000 AS INTEGER)
        ORDER BY a.id
        """,
        (space, name, artist, int(cast(int, length))),
    ).fetchall()
    members = [_row_values(item) for item in rows]
    if len(members) < 2 or not any(int(cast(int, item["id"])) == keep_id for item in members):
        raise LibraryError("That track is not in a duplicate group.")
    removes = [item for item in members if int(cast(int, item["id"])) != keep_id]
    kept = next(item for item in members if int(cast(int, item["id"])) == keep_id)
    return kept, removes


def _build_merge_plan(conn: sqlite3.Connection, space: str, keep_id: int) -> dict[str, object]:
    """Describe a merge without writing.

    Args:
        conn: Open connection. A read-only connection is enough.
        space: Space the duplicate group belongs to.
        keep_id: Asset id to keep.

    Returns:
        The plan, including private paths and column updates.

    Raises:
        LibraryError: If the track is not in a duplicate group in that space.
    """
    kept, removes = _group_members(conn, space, keep_id)
    kept_raw = _resolved(kept.get("portable_id") if isinstance(kept.get("portable_id"), str) else None)
    kept_path = Path(kept_raw) if kept_raw else None
    if kept_path is not None and (kept_path.is_symlink() or not kept_path.is_file()):
        kept_path = None
    files = [
        _classify_audio(row.get("portable_id"), row.get("file_name"), int(cast(int, row["id"])), kept_path)
        for row in removes
    ]
    kept_spaces = set(_asset_spaces(conn, keep_id))
    kept_crate_ids = {
        int(cast(int, crate["crate_id"]))
        for crate in _asset_crates(conn, keep_id)
        if int(cast(int, crate["type"])) not in (0, 2)
    }
    placements: dict[int, dict[str, object]] = {}
    spaces: set[str] = set()
    for row in removes:
        asset_id = int(cast(int, row["id"]))
        spaces.update(_asset_spaces(conn, asset_id))
        for crate in _asset_crates(conn, asset_id):
            if int(cast(int, crate["type"])) in (0, 2):
                continue
            crate_id = int(cast(int, crate["crate_id"]))
            order = crate["list_order"]
            current = placements.get(crate_id)
            if current is None or (
                order is not None
                and (current["list_order"] is None or int(cast(int, order)) < int(cast(int, current["list_order"])))
            ):
                placements[crate_id] = {
                    "crate_id": crate_id,
                    "name": crate["name"],
                    "space": crate["space"],
                    "list_order": order,
                }
    crates_added = []
    crates_kept = []
    new_placements = []
    for crate_id, crate in sorted(placements.items()):
        summary = {
            "id": crate_id,
            "name": crate["name"],
            "space": crate["space"],
            "list_order": crate["list_order"],
        }
        if crate_id in kept_crate_ids:
            crates_kept.append({"id": crate_id, "name": crate["name"], "space": crate["space"]})
        else:
            crates_added.append(summary)
            new_placements.append(crate)
    updates, fields = _merge_field_updates(kept, removes)
    cue_copy = _plan_cue_copy(kept, removes)
    lock = cue_copy.get("lock")
    if isinstance(lock, int) and "is_beatgrid_locked" in kept and int(kept.get("is_beatgrid_locked") or 0) != lock:
        updates["is_beatgrid_locked"] = lock
        fields.append(_preview_change("is_beatgrid_locked", kept.get("is_beatgrid_locked"), lock))
    history = _history_count(conn, [int(cast(int, row["id"])) for row in removes])
    drops = []
    for row in removes:
        drops.append(
            {
                "external_id": row.get("external_id"),
                "location_id": int(row.get("location_id") or 0),
            }
        )
    file_label = kept.get("file_name") if isinstance(kept.get("file_name"), str) else ""
    return {
        "keep_id": keep_id,
        "remove_ids": [int(cast(int, row["id"])) for row in removes],
        "space": space,
        "kept": {
            "id": keep_id,
            "file": file_label,
            "name": kept.get("name") or "",
            "artist": kept.get("artist") or "",
        },
        "removed": [
            {
                "id": int(cast(int, row["id"])),
                "file": row.get("file_name") if isinstance(row.get("file_name"), str) else "",
            }
            for row in removes
        ],
        "crates_added": crates_added,
        "crates_kept": crates_kept,
        "spaces_added": sorted(spaces - kept_spaces),
        "fields": fields,
        "history_entries": 0 if history is None else history,
        "history_repointed": history is not None,
        "cue_warning": cue_copy.get("warning"),
        "cue_copy": cue_copy.get("public"),
        "files": files,
        "_cue_copy": cue_copy,
        "_updates": updates,
        "_placements": new_placements,
        "_drops": drops,
        "_keep_external": kept.get("external_id"),
        "_keep_location": int(kept.get("location_id") or 0),
    }


def _apply_merge(conn: sqlite3.Connection, plan: Mapping[str, object]) -> None:
    """Write one merge into the open master transaction.

    Args:
        conn: Connection inside BEGIN IMMEDIATE.
        plan: Plan built on this same connection.

    Raises:
        LibraryError: If the crate schema cannot store the membership.
    """
    keep_id = int(cast(int, plan["keep_id"]))
    remove_ids = [int(item) for item in cast(list[int], plan["remove_ids"])]
    if keep_id in remove_ids or not remove_ids:
        raise LibraryError("That track is not in a duplicate group.")
    updates = dict(cast(dict[str, object], plan["_updates"]))
    if "time_modified" in _columns(conn, "asset"):
        updates["time_modified"] = int(time.time())
    if updates:
        _assign(conn, "asset", updates, "id = ?", keep_id)
    for space in cast(list[str], plan["spaces_added"]):
        _ensure_space_member(conn, keep_id, space)
    for crate in cast(list[dict[str, object]], plan["_placements"]):
        order = crate["list_order"]
        _insert_at_order(
            conn,
            int(cast(int, crate["crate_id"])),
            keep_id,
            str(crate["space"]),
            None if order is None else int(cast(int, order)),
        )
    if plan["history_repointed"]:
        _repoint_history(conn, keep_id, remove_ids)
    for asset_id in remove_ids:
        _delete_asset_refs(conn, asset_id)
        conn.execute("DELETE FROM asset WHERE id = ?", (asset_id,))


def _mirror_space_member(conn: sqlite3.Connection, asset_id: int, space: str) -> str | None:
    """Mirror a new space membership into the location database.

    Args:
        conn: Open master connection.
        asset_id: Kept asset id.
        space: Space name.

    Returns:
        None, or a warning when the drive database is left unchanged.
    """
    asset = _asset_location(conn, asset_id)
    if int(asset["location_id"] or 0) != 3 or asset["external_id"] is None:
        return "Saved in the main library. The other drive's database was not changed."
    root_path = _location_paths(conn).get(3)
    if root_path is None:
        return "Saved in the main library. That track's drive is not connected, so Serato may reconcile the edit when the drive returns."

    def apply(root: sqlite3.Connection) -> str | None:
        """Insert the space membership inside the location transaction.

        Args:
            root: Location database connection.

        Returns:
            None, or a warning when the space is missing there.
        """
        space_row = root.execute("SELECT id FROM space WHERE name = ?", (space,)).fetchone()
        if space_row is None:
            return "Saved in the main library. This space is not in the drive database."
        found = root.execute(
            "SELECT id FROM space_asset WHERE asset_id = ? AND space_id = ?",
            (int(asset["external_id"]), int(space_row[0])),
        ).fetchone()
        if found is None:
            revision = _next_revision(root)
            columns = _columns(root, "space_asset")
            if "revision" in columns:
                root.execute(
                    "INSERT INTO space_asset (asset_id, space_id, revision) VALUES (?, ?, ?)",
                    (int(asset["external_id"]), int(space_row[0]), revision),
                )
            else:
                root.execute(
                    "INSERT INTO space_asset (asset_id, space_id) VALUES (?, ?)",
                    (int(asset["external_id"]), int(space_row[0])),
                )
        return None

    return _with_location(root_path, apply)


def _mirror_placed_membership(
    conn: sqlite3.Connection,
    crate_id: int,
    asset_id: int,
    space: str,
    list_order: int | None,
) -> str | None:
    """Mirror a crate add, keeping the chosen position when the column exists.

    The guards match ``_mirror_membership``. A track that already sits in the
    drive crate is left at its current position.

    Args:
        conn: Open master connection.
        crate_id: Master container id.
        asset_id: Kept asset id.
        space: Space name.
        list_order: Position used on the master crate. None appends.

    Returns:
        None, or a warning when the drive database is left unchanged.
    """
    external = _external_ids(conn, [crate_id])
    asset = _asset_location(conn, asset_id)
    root_path = _location_paths(conn).get(int(asset["location_id"] or 0))
    if int(asset["location_id"] or 0) != 3:
        root_path = _location_paths(conn).get(3) if external else None
    if not external or asset["external_id"] is None or root_path is None:
        return "Saved in the main library. This track's drive is not connected, so the crate membership may be reconciled later."
    if int(asset["location_id"] or 0) != 3 and root_path == _location_paths(conn).get(3):
        return "Saved in the main library. This track lives on another drive, so that drive's database was not changed."

    def apply(root: sqlite3.Connection) -> str | None:
        """Insert the mirrored membership inside the location transaction.

        Args:
            root: Location database connection.

        Returns:
            None, or a warning when the space is missing from that database.
        """
        space_row = root.execute("SELECT id FROM space WHERE name = ?", (space,)).fetchone()
        if space_row is None:
            return "Saved in the main library. This space is not in the drive database."
        asset_row = root.execute(
            "SELECT id FROM space_asset WHERE asset_id = ? AND space_id = ?",
            (int(asset["external_id"]), int(space_row[0])),
        ).fetchone()
        revision = _next_revision(root)
        if asset_row is None:
            root.execute(
                "INSERT INTO space_asset (asset_id, space_id, revision) VALUES (?, ?, ?)",
                (int(asset["external_id"]), int(space_row[0]), revision),
            )
            space_asset_id = int(root.execute("SELECT last_insert_rowid()").fetchone()[0])
        else:
            space_asset_id = int(asset_row[0])
        found = root.execute(
            "SELECT id FROM container_asset WHERE container_id = ? AND space_asset_id = ?",
            (external[0], space_asset_id),
        ).fetchone()
        if found is not None:
            return None
        columns = _columns(root, "container_asset")
        order = list_order
        if order is None or "list_order" not in columns:
            order = root.execute(
                "SELECT COALESCE(MAX(list_order), 0) + 1 FROM container_asset WHERE container_id = ?",
                (external[0],),
            ).fetchone()[0]
        if "revision" in columns and "list_order" in columns:
            root.execute(
                """
                INSERT INTO container_asset (revision, container_id, space_asset_id, list_order, time_added)
                VALUES (?, ?, ?, ?, ?)
                """,
                (revision, external[0], space_asset_id, order, int(time.time())),
            )
        elif "list_order" in columns:
            root.execute(
                """
                INSERT INTO container_asset (container_id, space_asset_id, list_order, time_added)
                VALUES (?, ?, ?, ?)
                """,
                (external[0], space_asset_id, order, int(time.time())),
            )
        else:
            root.execute(
                "INSERT INTO container_asset (container_id, space_asset_id) VALUES (?, ?)",
                (external[0], space_asset_id),
            )
        return None

    return _with_location(root_path, apply)


def _mirror_drop_asset(
    conn: sqlite3.Connection,
    external_id: object,
    location_id: int,
    keep_external: object,
) -> str | None:
    """Remove a duplicate from the location database.

    Space and crate rows are removed the way ``_remove_from_space`` removes
    them. The location asset row is removed in the same transaction so Serato
    does not recreate the duplicate from the drive database. History rows in
    that database are repointed when they have an asset id.

    Args:
        conn: Open master connection.
        external_id: Location asset id, or None.
        location_id: Master location id.
        keep_external: Location id of the kept asset, used to avoid deleting it.

    Returns:
        None, or a warning when the drive database is left unchanged.
    """
    if (
        keep_external is not None
        and external_id is not None
        and int(cast(int, external_id)) == int(cast(int, keep_external))
    ):
        return (
            "A duplicate shares the drive record of the copy you are keeping, "
            "so that drive record was left in place."
        )
    if location_id != 3 or external_id is None:
        return "Removed from the main library. The other drive's database was not changed."
    root_path = _location_paths(conn).get(3)
    if root_path is None:
        return (
            "Removed from the main library. That track's drive is not connected, "
            "so Serato may reconcile the duplicate when the drive returns."
        )
    external = int(cast(int, external_id))
    kept = int(cast(int, keep_external)) if keep_external is not None else None

    def apply(root: sqlite3.Connection) -> None:
        """Delete the mirrored asset inside the location transaction.

        Args:
            root: Location database connection.
        """
        if kept is not None:
            _repoint_history(root, kept, [external])
        if "space_asset" in _tables(root) and "asset_id" in _columns(root, "space_asset"):
            rows = root.execute("SELECT id FROM space_asset WHERE asset_id = ?", (external,)).fetchall()
            ids = [int(row[0]) for row in rows]
            if ids and "container_asset" in _tables(root) and "space_asset_id" in _columns(root, "container_asset"):
                marks = ",".join("?" * len(ids))
                root.execute(f"DELETE FROM container_asset WHERE space_asset_id IN ({marks})", ids)
        _delete_asset_refs(root, external)
        if "asset" in _tables(root):
            root.execute("DELETE FROM asset WHERE id = ?", (external,))
        _next_revision(root)

    return _with_location(root_path, apply)


def _mirror_merge(conn: sqlite3.Connection, plan: Mapping[str, object]) -> list[str]:
    """Mirror a committed-in-memory merge into the location database.

    Args:
        conn: Open master connection, before commit.
        plan: Plan whose master rows are already updated.

    Returns:
        Warning strings. Duplicate warnings are omitted.
    """
    warnings: list[str] = []
    keep_id = int(cast(int, plan["keep_id"]))
    updates = dict(cast(dict[str, object], plan["_updates"]))
    if "time_modified" in _columns(conn, "asset"):
        updates["time_modified"] = int(time.time())
    if updates:
        warning = _mirror_asset(conn, keep_id, updates)
        if warning:
            warnings.append(warning)
    for space in cast(list[str], plan["spaces_added"]):
        warning = _mirror_space_member(conn, keep_id, space)
        if warning and warning not in warnings:
            warnings.append(warning)
    for crate in cast(list[dict[str, object]], plan["_placements"]):
        order = crate["list_order"]
        warning = _mirror_placed_membership(
            conn,
            int(cast(int, crate["crate_id"])),
            keep_id,
            str(crate["space"]),
            None if order is None else int(cast(int, order)),
        )
        if warning and warning not in warnings:
            warnings.append(warning)
    for drop in cast(list[dict[str, object]], plan["_drops"]):
        warning = _mirror_drop_asset(
            conn,
            drop.get("external_id"),
            int(cast(int, drop.get("location_id") or 0)),
            plan.get("_keep_external"),
        )
        if warning and warning not in warnings:
            warnings.append(warning)
    return warnings


def _refuse_unsafe_trash(plan: Mapping[str, object]) -> None:
    """Refuse a file move that could hit the wrong file.

    Args:
        plan: Merge plan.

    Raises:
        LibraryError: If any duplicate file is unsafe to move. Nothing is written.
    """
    for item in cast(list[dict[str, object]], plan["files"]):
        if item.get("blocks_trash"):
            reason = str(item.get("reason") or "The file was not moved.")
            raise LibraryError(f"{reason} Leave the Trash option off to merge the library rows.")


def _public_merge(plan: Mapping[str, object], **extra: object) -> dict[str, object]:
    """Copy the plan fields the page is allowed to see.

    Args:
        plan: Merge plan. Private paths and column maps are dropped.
        **extra: Response fields such as preview and warning.

    Returns:
        The JSON object for the page.
    """
    files = []
    for item in cast(list[dict[str, object]], plan["files"]):
        files.append({key: item[key] for key in _PUBLIC_FILE_KEYS})
    body: dict[str, object] = {
        "ok": True,
        "keep_id": plan["keep_id"],
        "remove_ids": plan["remove_ids"],
        "space": plan["space"],
        "kept": plan["kept"],
        "removed": plan["removed"],
        "crates_added": plan["crates_added"],
        "crates_kept": plan["crates_kept"],
        "spaces_added": plan["spaces_added"],
        "fields": plan["fields"],
        "history_entries": plan["history_entries"],
        "history_repointed": plan["history_repointed"],
        "cue_warning": plan["cue_warning"],
        "cue_copy": None,
        "files": files,
    }
    public_copy = plan.get("cue_copy")
    if isinstance(public_copy, dict):
        body["cue_copy"] = {key: public_copy.get(key) for key in _PUBLIC_CUE_COPY_KEYS}
    body.update(extra)
    return body


def _xdg_trash_dirs() -> tuple[Path, Path]:
    """Return the FreeDesktop home trash files and info directories.

    A relative ``XDG_DATA_HOME`` is ignored.

    Returns:
        ``Trash/files`` and ``Trash/info`` under the data home.
    """
    raw = os.environ.get("XDG_DATA_HOME", "")
    base = Path(raw) if raw and Path(raw).is_absolute() else Path.home() / ".local" / "share"
    trash = base / "Trash"
    return trash / "files", trash / "info"


def _device_root(path: Path) -> Path:
    """Return the mount root that contains a file.

    Args:
        path: Existing file.

    Returns:
        The highest directory that still sits on the file's device.
    """
    device = path.stat().st_dev
    current = path.resolve().parent
    while True:
        parent = current.parent
        if parent == current:
            return current
        try:
            if parent.stat().st_dev != device:
                return current
        except OSError:
            return current
        current = parent


def _trash_directories(origin: Path) -> tuple[Path, Path]:
    """Choose the trash directory for one file.

    The home trash is used when it is on the same device. Otherwise the
    FreeDesktop volume trash is used, so the move stays a rename.

    Args:
        origin: File that will be moved.

    Returns:
        The files directory and the info directory.

    Raises:
        LibraryError: If neither trash directory can be created.
    """
    try:
        files, info = _xdg_trash_dirs()
        files.mkdir(parents=True, exist_ok=True)
        info.mkdir(parents=True, exist_ok=True)
        if files.stat().st_dev == origin.stat().st_dev:
            return files, info
    except OSError:
        pass
    top = _device_root(origin)
    uid = os.getuid() if hasattr(os, "getuid") else 0
    shared = top / ".Trash"
    try:
        sticky = shared.is_dir() and bool(shared.stat().st_mode & 0o1000)
    except OSError:
        sticky = False
    base = shared / str(uid) if sticky else top / f".Trash-{uid}"
    files = base / "files"
    info = base / "info"
    try:
        files.mkdir(parents=True, exist_ok=True)
        info.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise LibraryError("The file could not be moved to the Trash.") from exc
    return files, info


def _trash_freedesktop(path: Path) -> Path:
    """Move one regular file into a FreeDesktop trash directory.

    Args:
        path: Existing regular file. The caller has rejected symlinks.

    Returns:
        The path inside the trash files directory.

    Raises:
        LibraryError: If the file cannot be renamed into the trash.
    """
    files, info = _trash_directories(path)
    files_root = files.resolve()
    info_root = info.resolve()
    stem = path.name
    if not stem or stem in {".", ".."} or "/" in stem or "\\" in stem:
        raise LibraryError("The file could not be moved to the Trash.")
    encoded = quote(path.resolve().as_posix(), safe="/")
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    body = f"[Trash Info]\nPath={encoded}\nDeletionDate={stamp}\n"
    for suffix in range(0, 1000):
        name = stem if suffix == 0 else f"{stem}_{suffix}"
        dest = files / name
        info_path = info / f"{name}.trashinfo"
        if dest.parent.resolve() != files_root or info_path.parent.resolve() != info_root:
            raise LibraryError("The file could not be moved to the Trash.")
        try:
            with info_path.open("x", encoding="utf-8") as handle:
                handle.write(body)
        except FileExistsError:
            continue
        try:
            os.rename(path, dest)
        except OSError as exc:
            info_path.unlink(missing_ok=True)
            if exc.errno == errno.EXDEV:
                raise LibraryError("The file could not be moved to the Trash.") from exc
            raise LibraryError("The file could not be moved to the Trash.") from exc
        return dest
    raise LibraryError("The file could not be moved to the Trash.")


def _trash_macos(path: Path) -> None:
    """Ask Finder to move one file to the Trash.

    Args:
        path: Existing file. The path is an argument, not part of the script.

    Raises:
        LibraryError: If Finder does not move the file.
    """
    script = 'on run argv\ntell application "Finder" to delete POSIX file (item 1 of argv)\nend run\n'
    completed = subprocess.run(
        ["osascript", "-e", script, str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0 or path.exists():
        raise LibraryError("The file could not be moved to the Trash.")


def _trash_windows(path: Path) -> None:
    """Move one file to the Windows Recycle Bin.

    The path is passed in the environment. It is not interpolated into the
    PowerShell script.

    Args:
        path: Existing file.

    Raises:
        LibraryError: If the Recycle Bin move fails or the file is still there.
    """
    script = (
        "Add-Type -AssemblyName Microsoft.VisualBasic; "
        "[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile("
        "[string]$env:SERATO_TRASH_PATH, 'OnlyErrorDialogs', 'SendToRecycleBin')"
    )
    env = os.environ.copy()
    env["SERATO_TRASH_PATH"] = str(path)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        check=False,
        capture_output=True,
        env=env,
        creationflags=flags,
    )
    if completed.returncode != 0 or path.exists():
        raise LibraryError("The file could not be moved to the Recycle Bin.")


def _move_to_trash(path: Path) -> None:
    """Move one duplicate audio file to the operating-system trash.

    macOS uses Finder, Windows uses the Recycle Bin, and other systems use
    the FreeDesktop trash specification. The file is not unlinked.

    Args:
        path: File chosen from a duplicate's stored path.

    Raises:
        LibraryError: If the path is a symlink, a directory, a library
            database file, or the trash move fails. The original file is
            left in place when the move fails.
    """
    if path.is_symlink() or path.is_dir() or not path.is_file() or _protected_library_path(path):
        raise LibraryError("The file could not be moved to the Trash.")
    if sys.platform == "win32":
        _trash_windows(path)
        return
    if sys.platform == "darwin":
        _trash_macos(path)
        return
    _trash_freedesktop(path)


def _trash_plan_files(plan: Mapping[str, object]) -> tuple[list[str], str | None]:
    """Move the duplicate files named by a plan.

    The library rows are already committed. A failure leaves that file on
    disk and is reported as a warning.

    Args:
        plan: Applied merge plan.

    Returns:
        File names that moved, and a warning when one stayed on disk.
    """
    trashed: list[str] = []
    failed: list[str] = []
    for item in cast(list[dict[str, object]], plan["files"]):
        raw = item.get("path")
        if not item.get("on_disk") or item.get("blocks_trash") or not isinstance(raw, Path):
            continue
        try:
            _move_to_trash(raw)
        except (LibraryError, OSError):
            failed.append(str(item.get("file") or "file"))
            continue
        trashed.append(str(item.get("file") or "file"))
    if not failed:
        return trashed, None
    names = ", ".join(failed)
    return trashed, f"Could not move these files to the Trash: {names}. They are still on disk."


def _join_merge_warnings(warnings: list[str]) -> str | None:
    """Collapse repeated drive-offline notes into one sentence.

    A merge mirrors the kept asset, each new space, each new crate, and
    each removed asset. When the drive database is not the connected
    location, every one of those steps returns its own sentence. The page
    shows that fact once. A warning about a shared drive record, or about
    a file that stayed on disk, is kept as written.

    Args:
        warnings: Messages from the location mirrors and the trash move.

    Returns:
        One warning string, or None when there is nothing to report.
    """
    offline = False
    rest: list[str] = []
    for warning in warnings:
        if not warning or warning in rest:
            continue
        if (
            "was not changed" in warning
            or "drive is not connected" in warning
            or "another drive" in warning
        ):
            offline = True
            continue
        rest.append(warning)
    parts: list[str] = []
    if offline:
        parts.append(
            "Saved in the main library. The other drive's database was not changed, "
            "so Serato may reconcile this when that drive is connected."
        )
    parts.extend(rest)
    if not parts:
        return None
    return " ".join(parts)


def merge_duplicates(payload: Mapping[str, object]) -> dict[str, object]:
    """Fold a duplicate group into the copy the user keeps.

    The group matches ``duplicate_groups``: same space, title, artist, and
    length in whole seconds. The kept track is added to every normal crate
    any duplicate was in. When the kept track is already in a crate, it stays
    at its current position. Otherwise it takes the earliest duplicate's
    position in that crate. Smart crates are left to their rules.

    Empty text fields and an empty BPM are filled from the first duplicate
    that has a value. Play count and rating keep the highest value. White
    (no color) is filled from the first colored copy. Date added keeps the
    earliest time. A beatgrid lock is copied only when the beatgrid frames
    are copied onto the kept file. Path, file size, bitrate, sample rate,
    and length stay with the file that was kept.

    History rows are repointed when ``history_entry.asset_id`` exists. The
    played name and file name on those rows are left as a snapshot.

    Cue points live in the audio file. The merge copies the richest
    Markers2 frame and, when the kept file has no beatgrid, the best
    BeatGrid frame onto that file through
    ``snapshot_frames.restore_stored_frames``. The kept audio is in the
    pre-write snapshot. A failed rewrite leaves the file as it was and
    returns ``cue_warning``. Frames stay in place when the containers do
    not match.

    ``preview`` true returns the plan and does not write. A real merge
    requires ``confirm`` true. ``delete_files`` true also requires
    ``confirm_delete_files`` true, and it is refused before any write when a
    duplicate path is a symlink, a directory, the same file as the kept copy,
    or anything inside the library database folder. Files that do move go to
    the operating-system trash after the database commit. The master changes
    are one transaction. Each location database is mirrored in its own
    transaction, the same way other writes are.

    Args:
        payload: JSON object with ``keep_id`` and ``space``. ``preview``,
            ``confirm``, ``delete_files``, and ``confirm_delete_files`` are
            booleans.

    Returns:
        The plan. ``preview`` is true when nothing was written. ``warning``
        is set when a drive database or a trash move was skipped.

    Raises:
        LibraryError: If the request is invalid, the track is not a duplicate,
            or a requested file move is unsafe.
        SeratoOpen: If Serato still has the library open.
    """
    space = cast(str, payload.get("space") or LIBRARY_SPACE)
    if "keep_id" not in payload or isinstance(payload.get("keep_id"), bool):
        raise LibraryError("Choose the copy to keep.")
    try:
        keep_id = _as_int(payload["keep_id"])
    except (TypeError, ValueError):
        raise LibraryError("Choose the copy to keep.") from None
    if keep_id <= 0:
        raise LibraryError("Choose the copy to keep.")
    preview = _optional_bool(payload.get("preview"), False)
    confirm = _optional_bool(payload.get("confirm"), False)
    delete_files = _optional_bool(payload.get("delete_files"), False)
    confirm_delete = _optional_bool(payload.get("confirm_delete_files"), False)
    if preview:
        with closing(read_conn()) as conn:
            plan = _build_merge_plan(conn, space, keep_id)
        info = status()
        return _public_merge(
            plan,
            preview=True,
            delete_files=False,
            writable=bool(info.get("writable")),
            warning=None,
        )
    if not confirm:
        raise LibraryError("Confirm the merge before it runs.")
    if delete_files and not confirm_delete:
        raise LibraryError("Moving audio files to the Trash needs a separate confirmation.")
    with closing(read_conn()) as conn:
        early = _build_merge_plan(conn, space, keep_id)
    if delete_files:
        _refuse_unsafe_trash(early)
    import safe_write

    def apply(conn: sqlite3.Connection, write: safe_write.Session) -> tuple[dict[str, object], list[str | None]]:
        """Merge the group and register the rows the check must see.

        Args:
            conn: Open write connection.
            write: Session that records the expected rows.

        Returns:
            The plan and any mirror warnings.

        Raises:
            LibraryError: If a requested file move is unsafe.
        """
        plan = _build_merge_plan(conn, space, keep_id)
        if delete_files:
            _refuse_unsafe_trash(plan)
        _apply_cue_copy(plan)
        _apply_merge(conn, plan)
        warnings = _mirror_merge(conn, plan)
        kept = plan.get("kept")
        if isinstance(kept, dict) and isinstance(kept.get("name"), str) and kept["name"]:
            write.set_target(str(kept["name"]))
        remove_ids = tuple(int(item) for item in cast(list[int], plan["remove_ids"]))
        kept_id = int(cast(int, plan["keep_id"]))

        def check(
            copied: sqlite3.Connection,
            kept_id: int = kept_id,
            remove_ids: tuple[int, ...] = remove_ids,
        ) -> None:
            """Fail when the kept track is missing or a duplicate remains.

            Args:
                copied: Read-only connection to the temporary database copy.
                kept_id: Asset id that should remain.
                remove_ids: Asset ids that should be gone.

            Raises:
                VerifyMismatch: If the group was not folded into the kept copy.
            """
            row = copied.execute("SELECT COUNT(*) FROM asset WHERE id = ?", (kept_id,)).fetchone()
            if row is None or int(row[0]) != 1:
                raise safe_write.VerifyMismatch("The track that should be kept is missing.")
            for asset_id in remove_ids:
                gone = copied.execute("SELECT COUNT(*) FROM asset WHERE id = ?", (asset_id,)).fetchone()
                if gone is None or int(gone[0]) != 0:
                    raise safe_write.VerifyMismatch("A duplicate track is still in the library.")

        write.check(check)
        return plan, warnings

    kept_name = "track"
    extra: list[Path] = []
    copy = early.get("_cue_copy")
    if isinstance(copy, dict) and copy.get("write"):
        dest = copy.get("dest")
        if isinstance(dest, Path):
            extra.append(dest)
    plan, warnings = safe_write.run("merge_duplicates", kept_name, apply, extra_files=extra)
    trashed: list[str] = []
    trash_warning = None
    if delete_files:
        trashed, trash_warning = _trash_plan_files(plan)
    if trash_warning:
        warnings.append(trash_warning)
    warning = _join_merge_warnings(warnings)
    return _public_merge(
        plan,
        preview=False,
        delete_files=delete_files,
        trashed=trashed,
        writable=True,
        warning=warning,
    )


def _require_asset_id(payload: Mapping[str, object], key: str, message: str) -> int:
    """Read a positive asset id from a JSON body.

    Args:
        payload: Request object.
        key: Field name.
        message: Sentence when the field is missing or not a real id.

    Returns:
        The integer id.

    Raises:
        LibraryError: If the field is missing, a boolean, or not a positive
            integer. ``_as_int`` treats ``True`` as 1, so booleans are
            refused here.
    """
    if key not in payload or isinstance(payload.get(key), bool):
        raise LibraryError(message)
    try:
        asset_id = _as_int(payload[key])
    except (TypeError, ValueError):
        raise LibraryError(message) from None
    if asset_id <= 0:
        raise LibraryError(message)
    return asset_id


def _asset_summary(conn: sqlite3.Connection, asset_id: int) -> dict[str, object]:
    """Return the file name, title, and artist for one asset.

    Args:
        conn: Open connection.
        asset_id: Asset id.

    Returns:
        A dict with id, file, name, and artist.

    Raises:
        LibraryError: If the asset row is missing.
    """
    row = conn.execute(
        "SELECT id, file_name, name, artist FROM asset WHERE id = ?",
        (asset_id,),
    ).fetchone()
    if row is None:
        raise LibraryError("That track is not in the library.", 404)
    file_name = row["file_name"] if isinstance(row["file_name"], str) else ""
    return {
        "id": int(row["id"]),
        "file": file_name,
        "name": row["name"] or "",
        "artist": row["artist"] or "",
    }


def _public_replace(plan: Mapping[str, object], **extra: object) -> dict[str, object]:
    """Copy the crate-replace fields the page is allowed to see.

    Args:
        plan: Replace plan. Private placement lists are dropped.
        **extra: Response fields such as preview and warning.

    Returns:
        The JSON object for the page.
    """
    body: dict[str, object] = {
        "ok": True,
        "from_id": plan["from_id"],
        "to_id": plan["to_id"],
        "space": plan["space"],
        "from": plan["from"],
        "to": plan["to"],
        "crates_added": plan["crates_added"],
        "crates_kept": plan["crates_kept"],
        "crates_removed": plan["crates_removed"],
        "retire": plan["retire"],
    }
    body.update(extra)
    return body


def _build_replace_plan(
    conn: sqlite3.Connection,
    space: str,
    from_id: int,
    to_id: int,
    retire: bool,
) -> dict[str, object]:
    """Plan putting ``to_id`` in every normal crate that holds ``from_id``.

    Args:
        conn: Open connection.
        space: Space that must already contain ``from_id``.
        from_id: Track whose crate slots are copied.
        to_id: Track placed at those ``list_order`` values.
        retire: True also removes ``from_id`` from those crates.

    Returns:
        The plan, including private placement lists.

    Raises:
        LibraryError: If ``from_id`` is not in the space or ``to_id`` is
            missing from the library.
    """
    _space_asset(conn, from_id, space, create=False)
    origin = _asset_summary(conn, from_id)
    replacement = _asset_summary(conn, to_id)
    kept_ids = {
        int(cast(int, crate["crate_id"]))
        for crate in _asset_crates(conn, to_id)
        if int(cast(int, crate["type"])) not in (0, 2)
    }
    crates_added: list[dict[str, object]] = []
    crates_kept: list[dict[str, object]] = []
    crates_removed: list[dict[str, object]] = []
    placements: list[dict[str, object]] = []
    removals: list[dict[str, object]] = []
    seen: set[int] = set()
    for crate in _asset_crates(conn, from_id):
        if int(cast(int, crate["type"])) in (0, 2):
            continue
        crate_id = int(cast(int, crate["crate_id"]))
        if crate_id in seen:
            continue
        seen.add(crate_id)
        summary = {
            "id": crate_id,
            "name": crate["name"],
            "space": crate["space"],
            "list_order": crate["list_order"],
        }
        if crate_id in kept_ids:
            crates_kept.append({"id": crate_id, "name": crate["name"], "space": crate["space"]})
        else:
            crates_added.append(summary)
            placements.append(crate)
        if retire:
            crates_removed.append({"id": crate_id, "name": crate["name"], "space": crate["space"]})
            removals.append(crate)
    crates_added.sort(key=lambda item: int(cast(int, item["id"])))
    crates_kept.sort(key=lambda item: int(cast(int, item["id"])))
    crates_removed.sort(key=lambda item: int(cast(int, item["id"])))
    return {
        "from_id": from_id,
        "to_id": to_id,
        "space": space,
        "from": origin,
        "to": replacement,
        "crates_added": crates_added,
        "crates_kept": crates_kept,
        "crates_removed": crates_removed,
        "retire": retire,
        "_placements": placements,
        "_removals": removals,
    }


def _crate_has_asset(conn: sqlite3.Connection, crate_id: int, asset_id: int) -> sqlite3.Row | None:
    """Return the membership row for one track in one crate.

    Args:
        conn: Open connection.
        crate_id: Container id.
        asset_id: Asset id.

    Returns:
        The ``container_asset`` row, or None.
    """
    return conn.execute(
        """
        SELECT ca.id, ca.list_order FROM container_asset ca
        JOIN location_container lc ON lc.id = ca.location_container_id
        WHERE lc.container_id = ? AND ca.asset_id = ?
        """,
        (crate_id, asset_id),
    ).fetchone()


def replace_in_crates(payload: Mapping[str, object]) -> dict[str, object]:
    """Put one track in every normal crate that holds another track.

    ``from_id`` is the track whose crate slots are copied. ``to_id`` is
    placed at that ``list_order`` in each crate. Smart crates and the
    space root are skipped. When ``to_id`` is already in a crate, it
    stays at its current position. ``retire`` true then removes
    ``from_id`` from those crates only. The asset row, audio file, cues,
    and history stay.

    Duplicate ``list_order`` values are allowed, so both tracks can sit
    at the same playlist position. Empty crate lists are a no-op and do
    not open a write. ``preview`` true returns the plan and does not
    write. A real update requires ``confirm`` true.

    Args:
        payload: JSON object with ``from_id``, ``to_id``, and ``space``.
            ``preview``, ``confirm``, and ``retire`` are booleans.

    Returns:
        The plan. ``preview`` is true when nothing was written.
        ``warning`` is set when a drive database was skipped.

    Raises:
        LibraryError: If the request is invalid or a track is missing.
        SeratoOpen: If Serato still has the library open and a write
            would run.
    """
    space = cast(str, payload.get("space") or LIBRARY_SPACE)
    from_id = _require_asset_id(payload, "from_id", "Choose the track to replace.")
    to_id = _require_asset_id(payload, "to_id", "Choose the track to put in those crates.")
    if from_id == to_id:
        raise LibraryError("Those two tracks are the same.")
    preview = _optional_bool(payload.get("preview"), False)
    confirm = _optional_bool(payload.get("confirm"), False)
    retire = _optional_bool(payload.get("retire"), False)
    if preview:
        with closing(read_conn()) as conn:
            plan = _build_replace_plan(conn, space, from_id, to_id, retire)
        info = status()
        return _public_replace(
            plan,
            preview=True,
            writable=bool(info.get("writable")),
            warning=None,
        )
    if not confirm:
        raise LibraryError("Confirm the crate update before it runs.")
    with closing(read_conn()) as conn:
        early = _build_replace_plan(conn, space, from_id, to_id, retire)
    if not early["_placements"] and not early["_removals"]:
        info = status()
        return _public_replace(
            early,
            preview=False,
            writable=bool(info.get("writable")),
            warning=None,
        )
    import safe_write

    def apply(conn: sqlite3.Connection, write: safe_write.Session) -> tuple[dict[str, object], list[str | None]]:
        """Place the replacement and optionally retire the original.

        Args:
            conn: Open write connection.
            write: Session that records the expected rows.

        Returns:
            The plan and any mirror warnings.
        """
        plan = _build_replace_plan(conn, space, from_id, to_id, retire)
        for crate in cast(list[dict[str, object]], plan["_placements"]):
            order = crate["list_order"]
            _insert_at_order(
                conn,
                int(cast(int, crate["crate_id"])),
                to_id,
                str(crate["space"]),
                None if order is None else int(cast(int, order)),
            )
        for crate in cast(list[dict[str, object]], plan["_removals"]):
            conn.execute(
                """
                DELETE FROM container_asset
                WHERE asset_id = ? AND location_container_id IN (
                    SELECT id FROM location_container WHERE container_id = ?
                )
                """,
                (from_id, int(cast(int, crate["crate_id"]))),
            )
        warnings: list[str | None] = []
        for crate in cast(list[dict[str, object]], plan["_placements"]):
            order = crate["list_order"]
            warnings.append(
                _mirror_placed_membership(
                    conn,
                    int(cast(int, crate["crate_id"])),
                    to_id,
                    str(crate["space"]),
                    None if order is None else int(cast(int, order)),
                )
            )
        for crate in cast(list[dict[str, object]], plan["_removals"]):
            warnings.append(
                _mirror_membership(
                    conn,
                    int(cast(int, crate["crate_id"])),
                    from_id,
                    str(crate["space"]),
                    False,
                )
            )
        placed = plan.get("to")
        if isinstance(placed, dict) and isinstance(placed.get("name"), str) and placed["name"]:
            write.set_target(str(placed["name"]))
        placements = tuple(
            (
                int(cast(int, crate["crate_id"])),
                None if crate["list_order"] is None else int(cast(int, crate["list_order"])),
            )
            for crate in cast(list[dict[str, object]], plan["_placements"])
        )
        removals = tuple(
            int(cast(int, crate["crate_id"]))
            for crate in cast(list[dict[str, object]], plan["_removals"])
        )
        keep_from = not bool(plan["retire"])

        def check(
            copied: sqlite3.Connection,
            to_id: int = to_id,
            from_id: int = from_id,
            placements: tuple[tuple[int, int | None], ...] = placements,
            removals: tuple[int, ...] = removals,
            keep_from: bool = keep_from,
        ) -> None:
            """Fail when crate membership does not match the plan.

            Args:
                copied: Read-only connection to the temporary database copy.
                to_id: Asset that should sit in each added crate.
                from_id: Asset whose crates were copied.
                placements: Crate ids and positions that were added.
                removals: Crate ids the original should leave.
                keep_from: True when the original should stay in those crates.

            Raises:
                VerifyMismatch: If a membership or asset row is wrong.
            """
            kept = copied.execute("SELECT COUNT(*) FROM asset WHERE id = ?", (from_id,)).fetchone()
            if kept is None or int(kept[0]) != 1:
                raise safe_write.VerifyMismatch("The original track was removed from the library.")
            present = copied.execute("SELECT COUNT(*) FROM asset WHERE id = ?", (to_id,)).fetchone()
            if present is None or int(present[0]) != 1:
                raise safe_write.VerifyMismatch("The replacement track is missing.")
            for crate_id, order in placements:
                row = _crate_has_asset(copied, crate_id, to_id)
                if row is None:
                    raise safe_write.VerifyMismatch("The replacement track is missing from a crate.")
                if order is not None and int(row["list_order"]) != order:
                    raise safe_write.VerifyMismatch("The replacement track is not at the crate position.")
            for crate_id in removals:
                row = _crate_has_asset(copied, crate_id, from_id)
                if keep_from:
                    if row is None:
                        raise safe_write.VerifyMismatch("The original track left a crate.")
                elif row is not None:
                    raise safe_write.VerifyMismatch("The original track is still in a crate.")

        write.check(check)
        return plan, warnings

    target = "track"
    to_row = early.get("to")
    if isinstance(to_row, dict) and isinstance(to_row.get("name"), str) and to_row["name"]:
        target = str(to_row["name"])
    plan, warnings = safe_write.run("replace_in_crates", target, apply)
    warning = _join_merge_warnings([item for item in warnings if item])
    return _public_replace(plan, preview=False, writable=True, warning=warning)


def _resolved(portable_id: str | None) -> str | None:
    """Resolve a portable id to a path string.

    An embedded NUL makes ``Path.is_file`` raise ``ValueError`` on some
    Python versions and return false on others. That candidate is not a
    file. The stored spelling is returned so the caller can warn.

    Args:
        portable_id: Stored path, or None.

    Returns:
        An existing file path when one of the candidates is a file, otherwise the first candidate. None when the id is empty.
    """
    if not portable_id:
        return None
    raw = Path(portable_id)
    # Relative ids are tried under the home directory first, then at the
    # filesystem root. An absolute id is used as stored.
    candidates = [raw] if raw.is_absolute() else [Path.home() / portable_id, Path("/") / portable_id]
    for candidate in candidates:
        try:
            if candidate.is_file():
                return str(candidate)
        except (OSError, ValueError):
            continue
    return str(candidates[0])


def resolved_path(portable_id: str | None) -> str | None:
    """Resolve a portable id to a path string.

    An embedded NUL is not treated as a file that exists. The stored
    spelling is returned so the caller can warn instead of crashing.

    Args:
        portable_id: Stored path, or None.

    Returns:
        An existing file path when one of the candidates is a file, otherwise the first candidate. None when the id is empty.
    """
    return _resolved(portable_id)


def export_m3u(space: str, crate_id: int | None) -> str:
    """Build an extended M3U playlist.

    Args:
        space: Space name.
        crate_id: Crate to export. None exports every track in the space.

    Returns:
        Playlist text ending in a newline. A track with no path is named in a comment and left out. A missing length is written as -1.

    Raises:
        LibraryError: If the space is not allowed or the crate is not in that space.
    """
    if space not in ALLOWED_SPACES:
        raise LibraryError("That space is not available here.")
    with closing(read_conn()) as conn:
        if crate_id is None:
            rows = conn.execute(
                """
                SELECT a.name, a.artist, a.length_ms, a.portable_id
                FROM asset a
                JOIN space_asset sa ON sa.asset_id = a.id
                JOIN space s ON s.id = sa.space_id
                WHERE s.name = ?
                ORDER BY a.name COLLATE NOCASE, a.id
                """,
                (space,),
            ).fetchall()
            title = space
        else:
            crate = _container(conn, crate_id, space)
            title = display_name(crate["name"])
            rows = conn.execute(
                """
                SELECT a.name, a.artist, a.length_ms, a.portable_id
                FROM container_asset ca
                JOIN location_container lc ON lc.id = ca.location_container_id
                JOIN asset a ON a.id = ca.asset_id
                WHERE lc.container_id = ?
                ORDER BY ca.list_order, ca.id
                """,
                (crate_id,),
            ).fetchall()
    lines = ["#EXTM3U", f"#PLAYLIST:{title}"]
    for row in rows:
        artist = row["artist"] or ""
        name = row["name"] or "Untitled"
        label = f"{artist} - {name}" if artist else name
        path = _resolved(row["portable_id"])
        if path is None:
            lines.append(f"# omitted, no path: {label}")
            continue
        length = row["length_ms"]
        seconds = -1 if length is None else int(length) // 1000
        lines.append(f"#EXTINF:{seconds},{label}")
        lines.append(path)
    return "\n".join(lines) + "\n"


def _match_portable(conn: sqlite3.Connection, space: str, raw_path: str) -> int | None:
    """Find a track whose portable_id matches a playlist path.

    Args:
        conn: Open connection.
        space: Space name.
        raw_path: A playlist line. file: URLs are accepted.

    Returns:
        The asset id, or None when no track matches.
    """
    path = Path(raw_path.strip())
    if raw_path.startswith("file:"):
        path = Path(unquote(urlparse(raw_path).path))
    candidates = {str(path), path.as_posix()}
    try:
        candidates.add(path.resolve().relative_to(Path.home()).as_posix())
    except (ValueError, OSError):
        pass
    marks = ",".join("?" * len(candidates))
    row = conn.execute(
        f"""
        SELECT a.id FROM asset a
        JOIN space_asset sa ON sa.asset_id = a.id
        JOIN space s ON s.id = sa.space_id
        WHERE s.name = ? AND a.portable_id IN ({marks})
        LIMIT 1
        """,
        [space, *candidates],
    ).fetchone()
    return int(row[0]) if row else None


def import_m3u(space: str, parent_id: int | None, name: str, text: object) -> dict[str, object]:
    """Create a crate from M3U text and add the tracks that already exist.

    Args:
        space: Space that receives the crate.
        parent_id: Parent crate id. None places the crate at the space root.
        name: Crate name. An empty name becomes Imported playlist.
        text: Playlist body. Comment lines are ignored.

    Returns:
        A dict with the new crate id, added count, and unmatched paths.

    Raises:
        LibraryError: If the playlist is empty or the crate cannot be created.
        SeratoOpen: If Serato still has the library open.
    """
    if not isinstance(text, str) or not text.strip():
        raise LibraryError("The playlist is empty.")
    paths: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        paths.append(line)
    label = name or "Imported playlist"
    import safe_write

    def apply(conn: sqlite3.Connection, write: safe_write.Session) -> dict[str, object]:
        """Create the crate, add the known tracks, and register that check.

        Args:
            conn: Open write connection.
            write: Session that records the expected rows.

        Returns:
            The import result, without the fields added after the check.

        Raises:
            LibraryError: If the crate cannot be created.
        """
        matched: list[int] = []
        unmatched: list[str] = []
        seen: set[int] = set()
        for raw in paths:
            asset_id = _match_portable(conn, space, raw)
            if asset_id is None or asset_id in seen:
                if asset_id is None:
                    unmatched.append(raw)
                continue
            seen.add(asset_id)
            matched.append(asset_id)
        created = _create_crate(conn, space, parent_id, label, False, None)
        crate_id = created["id"]
        if not isinstance(crate_id, int):
            raise LibraryError("The crate could not be created.")
        for asset_id in matched:
            _membership(conn, crate_id, asset_id, space, True)
        if isinstance(created.get("name"), str):
            write.set_target(str(created["name"]))
        wanted = tuple(matched)

        def check(copied: sqlite3.Connection, crate_id: int = crate_id, wanted: tuple[int, ...] = wanted) -> None:
            """Fail when the new crate is missing a track the playlist already had.

            Args:
                copied: Read-only connection to the temporary database copy.
                crate_id: New container id.
                wanted: Asset ids that should be members.

            Raises:
                VerifyMismatch: If the crate name or a membership does not match.
            """
            row = copied.execute("SELECT name FROM container WHERE id = ?", (crate_id,)).fetchone()
            if row is None or display_name(str(row[0])) != label:
                raise safe_write.VerifyMismatch("The imported crate name does not match.")
            for asset_id in wanted:
                member = copied.execute(
                    """
                    SELECT COUNT(*) FROM container_asset ca
                    JOIN location_container lc ON lc.id = ca.location_container_id
                    WHERE lc.container_id = ? AND ca.asset_id = ?
                    """,
                    (crate_id, asset_id),
                ).fetchone()
                if member is None or int(member[0]) != 1:
                    raise safe_write.VerifyMismatch("A playlist track was not added.")

        write.check(check)
        return {
            "ok": True,
            "id": created["id"],
            "name": created["name"],
            "added": len(matched),
            "unmatched": unmatched[:50],
            "unmatched_count": len(unmatched),
            "warning": created.get("warning"),
        }

    return safe_write.run("import_m3u", label, apply)


def reveal_command(path: str) -> list[str]:
    """Build the command that shows one file in the system file manager.

    Args:
        path: Absolute path of the audio file.

    Returns:
        Argv for Finder, File Explorer, or the parent folder on another system.
    """
    # Explorer takes the comma as part of the /select switch. The path is
    # the next argument. Finder's -R reveals the file. Other hosts open
    # the parent folder because xdg-open has no select-file switch.
    if sys.platform == "win32":
        return ["explorer", "/select,", path]
    if sys.platform == "darwin":
        return ["open", "-R", path]
    return ["xdg-open", str(Path(path).parent)]


def reveal(asset_id: int) -> dict[str, object]:
    """Show the audio file in the system file manager.

    Args:
        asset_id: Asset id.

    Returns:
        A dict with ok and path.

    Raises:
        LibraryError: If the track is missing or the file is not on disk.
    """
    with closing(read_conn()) as conn:
        row = conn.execute("SELECT portable_id FROM asset WHERE id = ?", (asset_id,)).fetchone()
    if row is None:
        raise LibraryError("That track is not in the library.", 404)
    path = _resolved(row["portable_id"])
    if not path or not Path(path).is_file():
        raise LibraryError("That file is not on disk.", 404)
    subprocess.run(reveal_command(path), check=False)
    return {"ok": True, "path": path}


def markers_for(path: str | None, on_disk: bool) -> SeratoTags:
    """Read cue data when the audio file is on disk.

    Args:
        path: Resolved audio path.
        on_disk: False skips the file read.

    Returns:
        Cue, loop, flip, and beatgrid lists, plus found, unavailable,
        beatgrid_warning, and beatgrid_warning_code.
    """
    if not on_disk:
        return {
            "cues": [],
            "loops": [],
            "flips": [],
            "beatgrid": [],
            "found": False,
            "unavailable": True,
            "beatgrid_warning": None,
            "beatgrid_warning_code": None,
        }
    parsed = read_serato_tags(path)
    parsed["unavailable"] = False
    telemetry.capture(telemetry.EVENT_TAGS_READ)
    return parsed


def update_related_path(old_path: str, new_path: str) -> bool:
    """Point saved related-track links at a file after a move.

    The file manager calls this after a cue-safe move. The sidecar
    database next to the settings file is updated. ``master.sqlite`` is
    not opened.

    Args:
        old_path: Path stored before the move.
        new_path: Path after the move.

    Returns:
        True when a related-track identity uses the new path. False when
        ``old_path`` is not stored.

    Raises:
        LibraryError: If ``new_path`` already identifies a different track,
            or either path is empty.
    """
    import related

    return related.update_path(old_path, new_path)
