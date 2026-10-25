"""Build a temporary Serato-shaped database for tests."""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import library
import server

SCHEMA = """
CREATE TABLE space (
    id INTEGER PRIMARY KEY,
    name TEXT
);
CREATE TABLE asset (
    id INTEGER PRIMARY KEY,
    name TEXT,
    artist TEXT,
    album TEXT,
    genre TEXT,
    year TEXT,
    composer TEXT,
    remixer TEXT,
    label TEXT,
    grouping TEXT,
    comments TEXT,
    key TEXT,
    emoji TEXT,
    bpm REAL,
    color INTEGER,
    rating REAL,
    is_beatgrid_locked INTEGER,
    portable_id TEXT,
    file_name TEXT,
    file_size INTEGER,
    is_missing INTEGER,
    length_ms INTEGER,
    length_sec INTEGER,
    format TEXT,
    type TEXT,
    time_added INTEGER,
    time_modified INTEGER,
    dj_play_count INTEGER,
    stems_analyze_state INTEGER,
    file_bit_rate INTEGER,
    file_sample_rate INTEGER,
    location_id INTEGER,
    external_id INTEGER,
    key_value INTEGER,
    third_party_type INTEGER,
    video_portable_id TEXT,
    part_of_set TEXT,
    track_number TEXT,
    comment_language TEXT,
    comment_descriptor TEXT,
    explicit INTEGER,
    is_corrupt INTEGER,
    corrupt_description TEXT,
    is_readonly INTEGER,
    is_whitelabel INTEGER,
    is_karaoke INTEGER,
    is_stale INTEGER,
    analysis_flags INTEGER,
    architectures INTEGER,
    pending_tempo_map_analysis INTEGER,
    dj_recently_played INTEGER,
    import_id BLOB,
    type_specific_data TEXT
);
CREATE TABLE location (
    id INTEGER PRIMARY KEY,
    path TEXT
);
CREATE TABLE space_asset (
    id INTEGER PRIMARY KEY,
    asset_id INTEGER,
    space_id INTEGER,
    revision INTEGER
);
CREATE TABLE container (
    id INTEGER PRIMARY KEY,
    parent_id INTEGER,
    name TEXT,
    type INTEGER,
    list_order INTEGER,
    space_id INTEGER,
    time_added INTEGER,
    expanded INTEGER,
    portable_id TEXT,
    color INTEGER,
    revision INTEGER
);
CREATE TABLE location_container (
    id INTEGER PRIMARY KEY,
    container_id INTEGER,
    location_id INTEGER,
    external_container_id INTEGER
);
CREATE TABLE container_asset (
    id INTEGER PRIMARY KEY,
    asset_id INTEGER,
    location_container_id INTEGER,
    space_asset_id INTEGER,
    external_container_asset_id INTEGER,
    list_order INTEGER,
    time_added INTEGER,
    container_id INTEGER,
    revision INTEGER
);
CREATE TABLE smart_crate_rules (
    container_id INTEGER PRIMARY KEY,
    version INTEGER,
    rules TEXT,
    revision INTEGER,
    needs_refresh INTEGER
);
CREATE TABLE dj_container_metadata (
    container_id INTEGER PRIMARY KEY,
    revision INTEGER,
    export_state INTEGER,
    filename TEXT
);
CREATE TABLE dj_asset_metadata (
    asset_id INTEGER PRIMARY KEY,
    video_effects BLOB,
    batch_analysis_version INTEGER,
    should_loop INTEGER,
    is_itunes INTEGER,
    itunes_id TEXT,
    has_read_tags INTEGER,
    is_whitelabel_acl INTEGER,
    is_unsupported INTEGER,
    external_id TEXT
);
CREATE TABLE connection (
    location_id INTEGER,
    database_uri TEXT
);
CREATE TABLE lock (
    owner_process_id INTEGER,
    owner_process_name TEXT
);
CREATE TABLE serato (
    revision INTEGER
);
CREATE TABLE history_session (
    id INTEGER PRIMARY KEY,
    name TEXT,
    start_time INTEGER,
    end_time INTEGER,
    notes TEXT
);
CREATE TABLE history_entry (
    id INTEGER PRIMARY KEY,
    session_id INTEGER,
    asset_id INTEGER,
    name TEXT,
    artist TEXT,
    album TEXT,
    bpm REAL,
    key TEXT,
    length_ms INTEGER,
    start_time INTEGER,
    end_time INTEGER,
    played INTEGER,
    deck TEXT,
    notes TEXT,
    file_name TEXT,
    is_missing INTEGER
);
CREATE TABLE updated_smart_crate (
    container_id INTEGER
);
"""


@contextmanager
def open_database(path: Path) -> Iterator[sqlite3.Connection]:
    """Open a database, commit on success, and always close the connection.

    ``sqlite3.Connection`` used as a context manager commits or rolls back and
    leaves the connection open. The statement cache keeps that object alive
    until cyclic garbage collection. Windows cannot delete a database file
    while that handle is open, so temporary-library cleanup fails.

    Args:
        path: Database file to open.

    Yields:
        A connection. Writes are committed when the block exits without an
        exception, and rolled back when it raises.
    """
    conn = sqlite3.connect(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _open_sqlite_handles(path: Path) -> list[str]:
    """Return this process's open descriptors for a database and its sidecars.

    Args:
        path: Database file.

    Returns:
        Descriptor targets from ``/proc``. An empty list on systems without
        that directory. Windows reports the same leak when the directory is
        removed.
    """
    proc = Path("/proc") / str(os.getpid()) / "fd"
    if not proc.is_dir():
        return []
    needle = os.path.normpath(path)
    found: list[str] = []
    for entry in proc.iterdir():
        try:
            target = os.readlink(entry)
        except OSError:
            continue
        base = os.path.normpath(target.removesuffix(" (deleted)"))
        if base == needle or base.startswith(needle + "-"):
            found.append(target)
    return found


def build_database(path: Path) -> None:
    """Create a small library with one track, one history row, and a duplicate pair."""
    with open_database(path) as conn:
        conn.executescript(SCHEMA)
        conn.execute("INSERT INTO serato (revision) VALUES (1)")
        conn.execute("INSERT INTO space (id, name) VALUES (1, 'Serato Library')")
        conn.execute("INSERT INTO space (id, name) VALUES (2, 'Prepare')")
        conn.execute(
            """
            INSERT INTO container
                (id, parent_id, name, type, list_order, space_id, time_added, expanded, portable_id)
            VALUES (1, NULL, 'Library', 0, 0, 1, 1, 0, '')
            """
        )
        conn.execute(
            """
            INSERT INTO container
                (id, parent_id, name, type, list_order, space_id, time_added, expanded, portable_id)
            VALUES (2, NULL, 'Prepare', 1, 0, 2, 1, 0, '')
            """
        )
        conn.execute(
            """
            INSERT INTO asset
                (id, name, artist, album, bpm, key, length_ms, color, is_missing,
                 file_name, portable_id, location_id, time_added, dj_play_count)
            VALUES
                (1, 'Same', 'Artist', 'Album', 120, '1A', 180000, 16711680, 0,
                 'same-a.mp3', 'Music/same-a.mp3', 1, 10, 2),
                (2, 'Same', 'Artist', 'Album', 120, '1A', 180500, 16711680, 0,
                 'same-b.mp3', 'Music/same-b.mp3', 1, 11, 0)
            """
        )
        conn.execute("INSERT INTO space_asset (id, asset_id, space_id) VALUES (1, 1, 1)")
        conn.execute("INSERT INTO space_asset (id, asset_id, space_id) VALUES (2, 2, 1)")
        conn.execute(
            """
            INSERT INTO history_session (id, name, start_time, end_time, notes)
            VALUES (1, 'Friday', 100, 200, 'club')
            """
        )
        conn.execute(
            """
            INSERT INTO history_entry
                (id, session_id, asset_id, name, artist, played, start_time, file_name, is_missing)
            VALUES (1, 1, 1, 'Same', 'Artist', 1, 100, 'same-a.mp3', 0)
            """
        )
        conn.commit()


class TempLibrary:
    """Point library.MASTER at a throwaway database for the duration of a test.

    The fixture closes the database it opens, and removal fails while this
    process still has the file open. Windows cannot delete that file.
    """

    def __init__(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.root = Path(self._dir.name)
        self.db = self.root / "master.sqlite"
        self._old_master = library.MASTER
        self._old_backed = set(library._backed_up)

    def __enter__(self) -> TempLibrary:
        build_database(self.db)
        library.MASTER = self.db
        library._backed_up.clear()
        server.invalidate()
        if not str(library.MASTER).startswith(tempfile.gettempdir()):
            raise RuntimeError("The test database is not in a temporary directory.")
        return self

    def __exit__(self, *_) -> None:
        library.MASTER = self._old_master
        library._backed_up.clear()
        library._backed_up.update(self._old_backed)
        server.invalidate()
        leaked = _open_sqlite_handles(self.db)
        try:
            self._dir.cleanup()
        except PermissionError as exc:
            raise RuntimeError(
                "The temporary library could not be removed because a SQLite "
                "connection still has the file open."
            ) from exc
        if leaked:
            raise RuntimeError(
                "The temporary library still has an open SQLite handle "
                f"({leaked[0]}). Close the connection before the directory is removed."
            )
