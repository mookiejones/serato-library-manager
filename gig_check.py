#!/usr/bin/env python3
"""Read-only check a DJ can run before a gig.

Opens the library with a SQLite URI in mode=ro and opens audio with rb.
It never writes the database, a journal, or an audio file. The result is
a frozen GigReport: a ready score and the Holding it back lines that
explain each deduction. A missing drive, or missing files in the selected
crate, is not ready no matter what the score would have been.
"""

from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
import tempfile
import threading
from collections.abc import Callable, Mapping, Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

import gig_snapshots
import library
import snapshots
from gig_snapshots import (
    ChangeReport,
    CueMark,
    GigSnapshotReader,
    GridMark,
    LoadedSnapshot,
    SnapshotCrate,
    SnapshotTrack,
    TrackTags,
    track_key,
)
from tags import read_serato_tags

# Apple Music is third_party_type 6.
# This app's schema map assigns 0 to a local file, 1 to iTunes, and 6 to
# Apple Music (server.py THIRD_PARTY, docs/architecture.md). iTunes is a
# local library and is not a streaming marker.
# Serato, "Music Streaming in Serato DJ Pro",
# https://serato.com/dj/pro/music-streaming (read 2026-10-28):
# "Apple Music tracks are streamed at 256kbps using AAC format in Serato
# DJ software."
APPLE_MUSIC_THIRD_PARTY = 6

# Serato's library clean-up note says empty crates are removed after quit:
# https://the-drop.serato.com/how-to/pro-tip-library-clean-up-advanced/
# ("empty crates are automatically deleted"; the empty crate "disappears
# automatically with the next start of Serato DJ"). That note does not
# name a Serato version. The Serato DJ 4.0 crate article does not say an
# empty crate is deleted:
# https://support.serato.com/hc/en-us/articles/227561407-Crates-in-Serato-DJ-Pro-Serato-DJ-Lite-4-0
# Until a version is verified, the warning says "may delete".
EMPTY_CRATE_WARNING = "Serato may delete this crate when it closes."

NO_SNAPSHOTS = "No snapshots yet"
STALE_SNAPSHOT = "No snapshot in the last 7 days"
SNAPSHOTS_UNREADABLE = "Snapshots could not be read."

SCORE_START = 100
READY_AT = 70
FRESH_DAYS = 7
MISSING_POINTS = 8
MISSING_CAP = 40
DRIVE_POINTS = 20
STREAM_POINTS = 2
STREAM_CAP = 16
EMPTY_POINTS = 4
EMPTY_CAP = 12
STALE_POINTS = 10
CHANGE_POINTS = 5
READ_MODE = "rb"
_LETTER = re.compile(r"^(?P<letter>[A-Za-z]):[\\/]")
_UNC = re.compile(r"^(?P<root>\\\\[^\\]+\\[^\\]+|//[^/]+/[^/]+)")


@dataclass(frozen=True, slots=True)
class MissingFile:
    """A file the selected crate cannot play because it is not on a mounted drive.

    Attributes:
        path: Path that was opened and was not there.
        title: Track title.
        artist: Artist.
        crate: Crate the track was checked in.
    """

    path: str
    title: str
    artist: str
    crate: str


@dataclass(frozen=True, slots=True)
class UnavailableDrive:
    """One drive that is not connected. Tracks on it are not missing files.

    Attributes:
        name: Drive name, once, such as ``GIGDRIVE`` or ``E:``.
        track_count: Tracks in scope that live on this drive.
        crates: Crate labels in scope that live on this drive.
    """

    name: str
    track_count: int
    crates: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StreamingTrack:
    """A track that plays only while its streaming service is logged in.

    Attributes:
        service: Service name from a documented marker.
        path: Stored path or service id.
        title: Track title.
        artist: Artist.
        crate: Crate the track was checked in.
    """

    service: str
    path: str
    title: str
    artist: str
    crate: str


@dataclass(frozen=True, slots=True)
class EmptyCrate:
    """A normal crate with no tracks and no subcrates.

    Attributes:
        name: Crate label.
        warning: The sentence shown to the DJ.
    """

    name: str
    warning: str


@dataclass(frozen=True, slots=True)
class Deduction:
    """One line in Holding it back.

    Attributes:
        code: Stable id for the page and tests.
        points: Points removed from the ready score.
        hard_red: True when the library is not ready, even if the score
            would otherwise pass.
        summary: The sentence the DJ reads.
    """

    code: str
    points: int
    hard_red: bool
    summary: str


@dataclass(frozen=True, slots=True)
class GigReport:
    """The whole check. Frozen. Nothing in it is a live database handle.

    Attributes:
        ready: True when the score is high enough and nothing is a hard red.
        score: Ready score from 0 to 100.
        hard_red: True when a drive is absent or the selected crate has
            missing files.
        holding_it_back: Each deduction, hard reds first.
        missing_files: Files that are gone on a drive that is connected.
        unavailable_drives: Absent drives, one row per name.
        streaming_tracks: Tracks matched by a documented streaming marker.
        empty_crates: Empty normal crates and their warning.
        snapshot_note: ``No snapshots yet`` or a sentence about the latest one.
        changes: Diff against the latest snapshot. None when there is nothing
            to compare.
        scope_space: Space that was checked.
        scope_crate_id: Crate id, or None for the whole space.
        scope_crate: Crate label, or None for the whole space.
        checked_at: Time the check used for the seven-day snapshot window.
    """

    ready: bool
    score: int
    hard_red: bool
    holding_it_back: tuple[Deduction, ...]
    missing_files: tuple[MissingFile, ...]
    unavailable_drives: tuple[UnavailableDrive, ...]
    streaming_tracks: tuple[StreamingTrack, ...]
    empty_crates: tuple[EmptyCrate, ...]
    snapshot_note: str
    changes: ChangeReport | None
    scope_space: str
    scope_crate_id: int | None
    scope_crate: str | None
    checked_at: datetime


@dataclass(frozen=True, slots=True)
class _Volume:
    """A drive a path can sit on.

    Attributes:
        name: Name shown once in the report.
        root: Directory or drive root whose absence means the drive is out.
        kind: ``letter``, ``unc``, or ``posix``.
    """

    name: str
    root: str
    kind: str


@dataclass(frozen=True, slots=True)
class _Asset:
    """One track row copied out of the database before the connection closes."""

    asset_id: int
    title: str
    artist: str
    album: str
    genre: str
    key: str
    bpm: str
    comments: str
    portable_id: str
    third_party_type: int | None
    location_id: int | None


@dataclass(frozen=True, slots=True)
class _Crate:
    """One crate row copied out of the database."""

    crate_id: int
    parent_id: int | None
    name: str
    crate_type: int
    label: str


@dataclass(frozen=True, slots=True)
class _Library:
    """The rows the check needs. Detached from SQLite."""

    assets: tuple[_Asset, ...]
    crates: tuple[_Crate, ...]
    membership: Mapping[int, tuple[int, ...]]
    locations: Mapping[int, str]
    crate_locations: Mapping[int, int]
    scope_ids: frozenset[int] | None
    scope_crate: str | None


@dataclass(frozen=True, slots=True)
class _Classified:
    """Tracks and crates after the file and drive checks."""

    missing: tuple[MissingFile, ...]
    drives: tuple[UnavailableDrive, ...]
    streaming: tuple[StreamingTrack, ...]
    empty: tuple[EmptyCrate, ...]
    present_paths: Mapping[int, str]


def open_read_only(path: Path) -> sqlite3.Connection:
    """Open a SQLite database that cannot be written.

    Args:
        path: Database file. It must already exist.

    Returns:
        A connection with ``mode=ro`` and ``query_only``. The caller closes it.

    Raises:
        library.LibraryError: If the file is missing or SQLite cannot open it
            read-only. The status is 404 or 409.
    """
    database = path.expanduser()
    if not database.is_absolute():
        database = database.resolve()
    if not database.is_file():
        raise library.LibraryError(f"Serato library not found at {database}", 404)
    # mode=ro is the SQLite URI guard. query_only is the second guard.
    uri = database.as_uri() + "?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.OperationalError as exc:
        raise library.LibraryError(
            "The library could not be read. Quit Serato and try the check again.",
            409,
        ) from exc
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    conn.execute("PRAGMA busy_timeout=1000")
    return conn


def _moment(now: datetime | None) -> datetime:
    """Return the timezone-aware time the freshness window uses.

    Args:
        now: Caller-supplied time, or None for the current UTC time.

    Returns:
        A timezone-aware datetime in UTC.

    Raises:
        library.LibraryError: If ``now`` has no timezone.
    """
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise library.LibraryError("The check time needs a timezone.")
    return now.astimezone(timezone.utc)


def _text(value: object) -> str:
    """Return text, or an empty string for NULL.

    Args:
        value: A database value.

    Returns:
        The string form, stripped of surrounding space. Empty for None.
    """
    if value is None:
        return ""
    return str(value).strip()


def _bpm_text(value: object) -> str:
    """Return BPM as stable text.

    Args:
        value: A number, text, or None.

    Returns:
        Trimmed decimal text. Empty when the value is missing.
    """
    if value is None or value == "":
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return _text(value)
    return f"{number:.4f}".rstrip("0").rstrip(".")


def _optional_int(value: object) -> int | None:
    """Return an int, or None when the cell is empty.

    Args:
        value: A database value.

    Returns:
        The integer, or None.
    """
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _expr(columns: set[str], name: str) -> str:
    """Return a SELECT expression for a column that may not exist.

    Args:
        columns: Column names on the asset table.
        name: Column to read.

    Returns:
        ``a.name`` when the column exists, otherwise NULL under that name.
        ``name`` is one of a fixed set in this module, not request text.
    """
    if name in columns:
        return f"a.{name}"
    return f"NULL AS {name}"


def _location_path(uri: str) -> str:
    """Turn a connection URI into the path whose drive we test.

    Args:
        uri: ``connection.database_uri``, a file URI or a plain path.

    Returns:
        A filesystem path. A Windows ``file:///Z:/...`` URI keeps the drive
        letter. The leading slash urlparse leaves in front of ``Z:`` is removed.
    """
    if uri.startswith("file:"):
        parsed = unquote(urlparse(uri).path)
        if len(parsed) >= 4 and parsed[0] == "/" and parsed[2] == ":":
            parsed = parsed[1:]
        return parsed
    return uri


def _posix_volume(path: str) -> _Volume | None:
    """Return the external volume of a POSIX path.

    Args:
        path: Absolute path using forward slashes.

    Returns:
        The volume, or None when the path is on the boot volume. macOS
        volumes are ``/Volumes/NAME``. Linux desktop mounts are ``/media``,
        ``/run/media``, and ``/mnt``.
    """
    parts = path.split("/")
    # ('', 'Volumes', 'NAME', ...)
    if len(parts) >= 3 and parts[1] == "Volumes" and parts[2]:
        name = parts[2]
        return _Volume(name, f"/Volumes/{name}", "posix")
    if len(parts) >= 5 and parts[1] == "run" and parts[2] == "media" and parts[4]:
        name = parts[4]
        root = "/" + "/".join(parts[1:5])
        return _Volume(name, root, "posix")
    if len(parts) >= 4 and parts[1] == "media" and parts[3]:
        name = parts[3]
        root = "/" + "/".join(parts[1:4])
        return _Volume(name, root, "posix")
    if len(parts) >= 3 and parts[1] == "mnt" and parts[2]:
        name = parts[2]
        return _Volume(name, f"/mnt/{name}", "posix")
    return None


def _volume_of(path: str) -> _Volume | None:
    """Return the volume a path addresses, including the boot drive letter.

    Args:
        path: Stored path or a location-database path.

    Returns:
        A volume, or None for a relative path or a POSIX boot-volume path.
        A Windows drive letter is returned on every operating system so a
        ``Z:`` path is never treated as a missing file on the boot drive.
    """
    if not path:
        return None
    letter = _LETTER.match(path)
    if letter:
        name = letter.group("letter").upper() + ":"
        return _Volume(name, name + "\\", "letter")
    if path.startswith("\\\\") or path.startswith("//"):
        match = _UNC.match(path)
        if match is None:
            return None
        root = match.group("root").replace("/", "\\")
        if not root.startswith("\\\\"):
            root = "\\\\" + root.lstrip("\\")
        return _Volume(root, root, "unc")
    if sys.platform == "win32":
        return None
    if path.startswith("/"):
        return _posix_volume(path)
    return None


def _external_volume(path: str) -> _Volume | None:
    """Return a volume only when it is not the boot drive.

    Args:
        path: Stored path or a location-database path.

    Returns:
        The external volume, or None for the boot drive and for relative paths.
        On Windows the system drive comes from ``SystemDrive``.
    """
    volume = _volume_of(path)
    if volume is None:
        return None
    if volume.kind == "letter" and sys.platform == "win32":
        system = os.environ.get("SystemDrive", "C:").upper()
        if volume.name.upper() == system:
            return None
    return volume


class _Mounts:
    """Remembers, per check, whether each drive root was present."""

    def __init__(self) -> None:
        """Start with an empty cache. Drive letters are read at most once."""
        self._cache: dict[str, bool] = {}
        self._letters: set[str] | None = None

    def mounted(self, volume: _Volume) -> bool:
        """Return whether this volume's root is connected.

        Args:
            volume: Drive to test.

        Returns:
            True when the drive letter is in ``os.listdrives`` or the volume
            directory exists. A UNC root that does not answer within a second
            and a half counts as absent, so one dead share cannot stall the check.
        """
        cached = self._cache.get(volume.root)
        if cached is not None:
            return cached
        if volume.kind == "letter":
            present = volume.name.upper() in self._windows_letters()
        elif volume.kind == "unc":
            present = _directory_exists(volume.root, timeout=1.5)
        else:
            present = _directory_exists(volume.root, timeout=None)
        self._cache[volume.root] = present
        return present

    def _windows_letters(self) -> set[str]:
        """Return mounted Windows drive letters.

        Returns:
            Letters such as ``C:``. Empty when this is not Windows.
        """
        if self._letters is not None:
            return self._letters
        found: set[str] = set()
        listdrives = getattr(os, "listdrives", None)
        if sys.platform == "win32" and listdrives is not None:
            for drive in listdrives():
                if len(drive) >= 2 and drive[1] == ":":
                    found.add(drive[:2].upper())
        self._letters = found
        return found


def _directory_exists(root: str, timeout: float | None) -> bool:
    """Return whether a directory exists.

    Args:
        root: Directory to test.
        timeout: Seconds to wait. None tests directly. A number is for a
            UNC root that might not answer.

    Returns:
        True when the directory is there. False when it is missing, cannot
        be read, or does not answer in time.
    """
    if timeout is None:
        try:
            return Path(root).is_dir()
        except OSError:
            return False
    answered: list[bool] = []

    def probe() -> None:
        try:
            answered.append(Path(root).is_dir())
        except OSError:
            answered.append(False)

    worker = threading.Thread(target=probe, daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive() or not answered:
        return False
    return answered[0]


def _opens_for_read(path: Path) -> bool:
    """Return whether a file can be opened for reading.

    Args:
        path: File to open.

    Returns:
        True when the file opens with ``rb``. False when it is missing or
        cannot be read. The handle is closed without writing.
    """
    try:
        with path.open(READ_MODE):
            return True
    except OSError:
        return False


def _streaming_service(third_party_type: int | None) -> str | None:
    """Return the streaming service for a documented marker.

    Args:
        third_party_type: The asset column, or None when the column is empty.

    Returns:
        ``Apple Music`` for marker 6. None for every other value, including
        iTunes (1) and values this app has not documented.
    """
    if third_party_type == APPLE_MUSIC_THIRD_PARTY:
        return "Apple Music"
    return None


def _candidates(portable_id: str, external_root: str | None) -> tuple[Path, ...]:
    """Return the paths a stored id might occupy on a mounted drive.

    Args:
        portable_id: Path Serato stored.
        external_root: Root of a mounted external drive, or None for the boot drive.

    Returns:
        Absolute candidates. An absolute id is used as stored. A relative id
        on an external drive is joined to that drive. A relative id on the
        boot drive is tried under the home directory, then at the filesystem root,
        which is the same order ``library.resolved_path`` uses.
    """
    if not portable_id:
        return ()
    raw = Path(portable_id)
    if raw.is_absolute():
        return (raw,)
    if external_root is not None:
        return (Path(external_root) / portable_id,)
    return (Path.home() / portable_id, Path(os.sep) / portable_id)


def _read_membership(conn: sqlite3.Connection) -> dict[int, list[int]]:
    """Read crate membership from whichever columns this database has.

    Args:
        conn: Open read-only connection.

    Returns:
        Crate id to asset ids. A live Serato library links
        ``container_asset`` through ``location_container``. The test schema
        also stores ``container_id`` on the membership row. Both are read.
    """
    found: dict[int, list[int]] = {}

    def add(crate_id: object, asset_id: object) -> None:
        crate = _optional_int(crate_id)
        asset = _optional_int(asset_id)
        if crate is None or asset is None:
            return
        bucket = found.setdefault(crate, [])
        if asset not in bucket:
            bucket.append(asset)

    columns = {row[1] for row in conn.execute("PRAGMA table_info(container_asset)")}
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    if "location_container_id" in columns and "location_container" in tables:
        for row in conn.execute(
            """
            SELECT lc.container_id AS crate_id, ca.asset_id
            FROM container_asset ca
            JOIN location_container lc ON lc.id = ca.location_container_id
            """
        ):
            add(row["crate_id"], row["asset_id"])
    if "container_id" in columns:
        for row in conn.execute("SELECT container_id, asset_id FROM container_asset"):
            add(row["container_id"], row["asset_id"])
    return found


def _labels(crates: list[_Crate]) -> tuple[_Crate, ...]:
    """Fill each crate's display label from its ancestors.

    Args:
        crates: Crates with an empty label.

    Returns:
        The same crates with labels. A crate under Friday named Peak is
        ``Friday / Peak``.
    """
    by_id = {crate.crate_id: crate for crate in crates}
    labels: dict[int, str] = {}

    def label(crate_id: int) -> str:
        cached = labels.get(crate_id)
        if cached is not None:
            return cached
        crate = by_id[crate_id]
        parent = crate.parent_id
        if parent is None or parent == crate.crate_id or parent not in by_id or by_id[parent].crate_type == 0:
            text = crate.name or "Crate"
        else:
            text = f"{label(parent)} / {crate.name or 'Crate'}"
        labels[crate_id] = text
        return text

    labeled: list[_Crate] = []
    for crate in crates:
        labeled.append(
            _Crate(crate.crate_id, crate.parent_id, crate.name, crate.crate_type, label(crate.crate_id))
        )
    return tuple(labeled)


def _read_library(conn: sqlite3.Connection, space: str, crate_id: int | None) -> _Library:
    """Copy the rows the check needs, then return. The caller closes ``conn``.

    Args:
        conn: Open read-only connection.
        space: Space name.
        crate_id: Crate to check, including subcrates. None checks the space.

    Returns:
        Detached rows.

    Raises:
        library.LibraryError: If the crate is not in the space. Status 404.
    """
    asset_columns = {row[1] for row in conn.execute("PRAGMA table_info(asset)")}
    select = ", ".join(
        _expr(asset_columns, name)
        for name in (
            "name",
            "artist",
            "album",
            "genre",
            "key",
            "bpm",
            "comments",
            "portable_id",
            "file_name",
            "third_party_type",
            "location_id",
        )
    )
    assets: list[_Asset] = []
    for row in conn.execute(
        f"""
        SELECT a.id, {select}
        FROM asset a
        JOIN space_asset sa ON sa.asset_id = a.id
        JOIN space s ON s.id = sa.space_id
        WHERE s.name = ?
        ORDER BY a.id
        """,
        (space,),
    ):
        title = _text(row["name"]) or _text(row["file_name"]) or "Untitled"
        assets.append(
            _Asset(
                int(row["id"]),
                title,
                _text(row["artist"]),
                _text(row["album"]),
                _text(row["genre"]),
                _text(row["key"]),
                _bpm_text(row["bpm"]),
                _text(row["comments"]),
                _text(row["portable_id"]),
                _optional_int(row["third_party_type"]),
                _optional_int(row["location_id"]),
            )
        )
    raw_crates: list[_Crate] = []
    for row in conn.execute(
        """
        SELECT c.id, c.parent_id, c.name, c.type
        FROM container c
        JOIN space s ON s.id = c.space_id
        WHERE s.name = ?
        ORDER BY c.list_order, c.id
        """,
        (space,),
    ):
        stored = row["name"] if isinstance(row["name"], str) else ""
        raw_crates.append(
            _Crate(
                int(row["id"]),
                _optional_int(row["parent_id"]),
                library.display_name(stored),
                int(row["type"] or 0),
                "",
            )
        )
    crates = _labels(raw_crates)
    by_id = {crate.crate_id: crate for crate in crates}
    scope_crate: str | None = None
    scope_ids: frozenset[int] | None = None
    if crate_id is not None:
        chosen = by_id.get(crate_id)
        if chosen is None:
            raise library.LibraryError("That crate is not in this space.", 404)
        scope_crate = chosen.label
        scope_ids = frozenset(int(item) for item in library.descendant_ids(conn, crate_id))
    membership = {crate: tuple(ids) for crate, ids in _read_membership(conn).items()}
    locations: dict[int, str] = {}
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    if "connection" in tables:
        try:
            rows = conn.execute("SELECT location_id, database_uri FROM connection").fetchall()
        except sqlite3.OperationalError:
            rows = []
        for row in rows:
            location = _optional_int(row["location_id"])
            uri = row["database_uri"]
            if location is not None and isinstance(uri, str) and uri:
                locations[location] = uri
    crate_locations: dict[int, int] = {}
    if "location_container" in tables:
        for row in conn.execute("SELECT container_id, location_id FROM location_container"):
            crate = _optional_int(row["container_id"])
            location = _optional_int(row["location_id"])
            if crate is not None and location is not None and crate not in crate_locations:
                crate_locations[crate] = location
    return _Library(
        tuple(assets),
        crates,
        membership,
        locations,
        crate_locations,
        scope_ids,
        scope_crate,
    )


def _asset_crates(library_rows: _Library) -> dict[int, tuple[str, ...]]:
    """Map each asset to the labels of crates that contain it.

    Args:
        library_rows: Loaded rows.

    Returns:
        Asset id to crate labels.
    """
    labels = {crate.crate_id: crate.label for crate in library_rows.crates}
    found: dict[int, list[str]] = {}
    for crate_id, asset_ids in library_rows.membership.items():
        label = labels.get(crate_id)
        if not label:
            continue
        for asset_id in asset_ids:
            found.setdefault(asset_id, []).append(label)
    return {asset_id: tuple(names) for asset_id, names in found.items()}


def _scope_assets(library_rows: _Library) -> tuple[_Asset, ...]:
    """Return the tracks this check classifies.

    Args:
        library_rows: Loaded rows.

    Returns:
        Every track in the space, or the tracks in the selected crate tree.
    """
    if library_rows.scope_ids is None:
        return library_rows.assets
    wanted: set[int] = set()
    for crate_id in library_rows.scope_ids:
        wanted.update(library_rows.membership.get(crate_id, ()))
    return tuple(asset for asset in library_rows.assets if asset.asset_id in wanted)


def _classify(library_rows: _Library) -> _Classified:
    """Sort tracks into missing, unavailable, streaming, and present.

    Args:
        library_rows: Loaded rows. The database is already closed.

    Returns:
        The groups the score reads. Tracks on an absent drive are unavailable
        and are not opened, so they cannot be counted as missing files.
    """
    mounts = _Mounts()
    crate_names = _asset_crates(library_rows)
    scope_name = library_rows.scope_crate
    missing: list[MissingFile] = []
    streaming: list[StreamingTrack] = []
    present: dict[int, str] = {}
    drive_tracks: dict[str, int] = {}
    drive_crates: dict[str, set[str]] = {}

    def remember_drive(name: str, crate: str, track: bool) -> None:
        if track:
            drive_tracks[name] = drive_tracks.get(name, 0) + 1
        else:
            drive_tracks.setdefault(name, 0)
        if crate:
            drive_crates.setdefault(name, set()).add(crate)

    for asset in _scope_assets(library_rows):
        crate = scope_name or (crate_names.get(asset.asset_id) or ("",))[0]
        service = _streaming_service(asset.third_party_type)
        if service is not None:
            streaming.append(
                StreamingTrack(service, asset.portable_id, asset.title, asset.artist, crate)
            )
            continue
        location_uri = library_rows.locations.get(asset.location_id or -1, "")
        location_volume = _external_volume(_location_path(location_uri)) if location_uri else None
        path_volume = _external_volume(asset.portable_id) if Path(asset.portable_id).is_absolute() else None
        absent: _Volume | None = None
        if location_volume is not None and not mounts.mounted(location_volume):
            absent = location_volume
        if absent is None and path_volume is not None and not mounts.mounted(path_volume):
            absent = path_volume
        if absent is not None:
            remember_drive(absent.name, crate, True)
            continue
        external_root = None
        if location_volume is not None and mounts.mounted(location_volume):
            external_root = location_volume.root
        elif path_volume is not None and mounts.mounted(path_volume):
            external_root = path_volume.root
        candidates = _candidates(asset.portable_id, external_root)
        opened = next((candidate for candidate in candidates if _opens_for_read(candidate)), None)
        if opened is not None:
            present[asset.asset_id] = str(opened)
            continue
        reported = str(candidates[0]) if candidates else asset.portable_id
        missing.append(MissingFile(reported, asset.title, asset.artist, crate))

    for crate in library_rows.crates:
        if library_rows.scope_ids is not None and crate.crate_id not in library_rows.scope_ids:
            continue
        location_id = library_rows.crate_locations.get(crate.crate_id)
        if location_id is None:
            continue
        uri = library_rows.locations.get(location_id, "")
        volume = _external_volume(_location_path(uri)) if uri else None
        if volume is not None and not mounts.mounted(volume):
            remember_drive(volume.name, crate.label, False)

    drives = tuple(
        UnavailableDrive(name, drive_tracks.get(name, 0), tuple(sorted(drive_crates.get(name, set()))))
        for name in sorted(set(drive_tracks) | set(drive_crates))
    )
    # Crates on an absent drive are unavailable, not empty.
    absent_crates = {label for names in drive_crates.values() for label in names}
    empty = tuple(crate for crate in _empty_crates(library_rows) if crate.name not in absent_crates)
    return _Classified(
        tuple(sorted(missing, key=lambda item: item.path)),
        drives,
        tuple(sorted(streaming, key=lambda item: (item.service, item.title, item.path))),
        empty,
        present,
    )


def _empty_crates(library_rows: _Library) -> tuple[EmptyCrate, ...]:
    """List normal crates that have no tracks and no subcrates.

    Args:
        library_rows: Loaded rows.

    Returns:
        Empty crates in scope. The space root and smart crates are skipped.
        A parent that still has a subcrate is skipped. The caller drops a
        crate that lives on an absent drive.
    """
    parents = {crate.parent_id for crate in library_rows.crates if crate.parent_id is not None}
    found: list[EmptyCrate] = []
    for crate in library_rows.crates:
        if crate.crate_type in {0, 2}:
            continue
        if library_rows.scope_ids is not None and crate.crate_id not in library_rows.scope_ids:
            continue
        if crate.crate_id in parents:
            continue
        if library_rows.membership.get(crate.crate_id):
            continue
        found.append(EmptyCrate(crate.label, EMPTY_CRATE_WARNING))
    return tuple(sorted(found, key=lambda item: item.name))


def _tags_for(asset: _Asset) -> TrackTags:
    """Copy library text into a snapshot tag record.

    Args:
        asset: Track row.

    Returns:
        Tags the diff can compare.
    """
    return TrackTags(
        asset.title,
        asset.artist,
        asset.album,
        asset.genre,
        asset.key,
        asset.bpm,
        asset.comments,
    )


def _marks(
    cue_rows: Sequence[Mapping[str, object]],
    loop_rows: Sequence[Mapping[str, object]],
    grid_rows: Sequence[Mapping[str, object]],
) -> tuple[tuple[CueMark, ...], tuple[GridMark, ...]]:
    """Turn parsed Markers2 and BeatGrid rows into marks the diff compares.

    Args:
        cue_rows: Cue dicts from the Markers2 parser in ``tags.py``.
        loop_rows: Loop dicts from the same parser.
        grid_rows: Marker dicts from the BeatGrid parser in ``tags.py``.

    Returns:
        Cues and loops, and grid markers.
    """
    cues = [
        CueMark("cue", _int(cue.get("index")), _int(cue.get("start_ms")), None, _text(cue.get("name")))
        for cue in cue_rows
    ]
    cues.extend(
        CueMark(
            "loop",
            _int(loop.get("index")),
            _int(loop.get("start_ms")),
            _int(loop.get("end_ms")),
            _text(loop.get("name")),
        )
        for loop in loop_rows
    )
    grid: list[GridMark] = []
    for marker in grid_rows:
        bpm = marker.get("bpm")
        beats = marker.get("beats")
        position = marker.get("position")
        grid.append(
            GridMark(
                float(position) if isinstance(position, (int, float)) else 0.0,
                float(bpm) if isinstance(bpm, (int, float)) else None,
                int(beats) if isinstance(beats, int) else None,
            )
        )
    return tuple(cues), tuple(grid)


def _int(value: object) -> int:
    """Return a parsed marker number as an int.

    Args:
        value: Number from a parser dict.

    Returns:
        The int, or 0 when the value is not a number.
    """
    return int(value) if isinstance(value, (int, float)) else 0


def _marks_from_file(path: str) -> tuple[tuple[CueMark, ...], tuple[GridMark, ...], bool]:
    """Read cues and the beatgrid from a file that is already on disk.

    Args:
        path: File that opened with rb during classification.

    Returns:
        Cues, grid markers, and whether the read found Serato frames.
        ``read_serato_tags`` opens the file with rb and does not write it.
    """
    loaded = read_serato_tags(path)
    cues, grid = _marks(loaded["cues"], loaded["loops"], loaded["beatgrid"])
    return cues, grid, bool(loaded["found"])


_Marks = Callable[[_Asset], tuple[str, tuple[CueMark, ...], tuple[GridMark, ...], bool]]


def _current_snapshot(library_rows: _Library, classified: _Classified, taken_at: datetime) -> LoadedSnapshot:
    """Build a snapshot of the library as it is now.

    Args:
        library_rows: Loaded rows.
        classified: Which files opened.
        taken_at: Time stamped on this in-memory snapshot.

    Returns:
        Crates, cues, grids, and tags for the diff. Cues and grids are marked
        unknown when the file was not opened, so a missing file is not also
        reported as every cue being deleted.
    """

    def marks(asset: _Asset) -> tuple[str, tuple[CueMark, ...], tuple[GridMark, ...], bool]:
        path = classified.present_paths.get(asset.asset_id)
        if path is None:
            return asset.portable_id, (), (), False
        cues, grid, _found = _marks_from_file(path)
        return path, cues, grid, True

    info = gig_snapshots.SnapshotInfo("current", taken_at, "Library now")
    return _library_snapshot(library_rows, marks, info)


def _library_snapshot(library_rows: _Library, marks: _Marks, info: gig_snapshots.SnapshotInfo) -> LoadedSnapshot:
    """Build a snapshot from library rows and a source of cues and grids.

    Args:
        library_rows: Rows read from the live database or a snapshot copy.
        marks: Returns the path to show, the cues, the grid, and whether
            they are known for one track.
        info: Id, time, and label for the result.

    Returns:
        Crates, cues, grids, and tags for the diff. Both sides of the diff
        are built here, so a track or a crate has the same key on each side.
    """
    names = _asset_crates(library_rows)
    tracks: list[SnapshotTrack] = []
    for asset in library_rows.assets:
        path, cues, grid, known = marks(asset)
        tracks.append(
            SnapshotTrack(
                track_key(asset.asset_id, asset.portable_id or path),
                path,
                names.get(asset.asset_id, ()),
                cues,
                grid,
                _tags_for(asset),
                known,
                known,
            )
        )
    keys_for_asset = {asset.asset_id: track_key(asset.asset_id, asset.portable_id or "") for asset in library_rows.assets}
    crate_rows: list[SnapshotCrate] = []
    for crate in library_rows.crates:
        if crate.crate_type == 0:
            continue
        keys = tuple(
            keys_for_asset[asset_id]
            for asset_id in library_rows.membership.get(crate.crate_id, ())
            if asset_id in keys_for_asset
        )
        crate_rows.append(SnapshotCrate(crate.label, keys))
    return LoadedSnapshot(info, tuple(crate_rows), tuple(tracks))


def _as_utc(value: datetime) -> datetime:
    """Return a timezone-aware UTC time.

    Args:
        value: Snapshot time. A naive value is treated as UTC, which is what
            a reader should already have stored.

    Returns:
        UTC time.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _changes(
    reader: GigSnapshotReader,
    library_rows: _Library,
    classified: _Classified,
    now: datetime,
) -> tuple[str, ChangeReport | None, bool]:
    """Compare the library with the latest snapshot.

    Args:
        reader: Snapshot source.
        library_rows: Loaded rows.
        classified: Files that opened.
        now: Freshness clock.

    Returns:
        The snapshot note, the diff, and whether a snapshot is fresh.
        No snapshots yields ``No snapshots yet``, no diff, and not fresh.
        A store that cannot be listed says so and is also not fresh.
    """
    try:
        listed = list(reader.list_snapshots())
    except OSError:
        return SNAPSHOTS_UNREADABLE, None, False
    if not listed:
        return NO_SNAPSHOTS, None, False
    latest = max(listed, key=lambda info: (_as_utc(info.taken_at), info.snapshot_id))
    fresh = _as_utc(latest.taken_at) >= now - timedelta(days=FRESH_DAYS)
    when = _as_utc(latest.taken_at).strftime("%Y-%m-%d")
    label = latest.label or latest.snapshot_id
    note = f"Latest snapshot: {label} on {when}."
    try:
        loaded = reader.load(latest.snapshot_id)
    except (KeyError, OSError):
        return f"{note} The latest snapshot could not be read.", None, fresh
    current = _current_snapshot(library_rows, classified, now)
    return note, gig_snapshots.diff_snapshots(loaded, current), fresh


class StoreSnapshots:
    """Reads snapshots from ``snapshots.py`` for the gig check, without writing.

    ``load`` opens the snapshot's ``master.sqlite`` copy read-only and reads
    the same rows the check reads from the live library. Cues and grids come
    from the Markers2 and BeatGrid frames saved in that snapshot, so the
    audio files are not opened. A track whose file had no saved Serato frame
    is marked unknown and its cues and grid are not compared.
    """

    def __init__(self, store: snapshots.SnapshotStore, space: str = library.LIBRARY_SPACE):
        """Wrap a store.

        Args:
            store: Snapshot store for the library being checked.
            space: Space whose rows are compared.
        """
        self.store = store
        self.space = space

    def list_snapshots(self) -> Sequence[gig_snapshots.SnapshotInfo]:
        """List snapshots whose database copy passed its integrity check.

        Returns:
            One row per snapshot. The label is the reason the snapshot was taken.

        Raises:
            OSError: If the store cannot be listed.
        """
        try:
            stored = self.store.list_snapshots()
        except snapshots.SnapshotError as exc:
            raise OSError(exc.message) from exc
        rows: list[gig_snapshots.SnapshotInfo] = []
        for info in stored:
            if info["integrity"] != "ok":
                continue
            try:
                taken_at = datetime.fromisoformat(info["created"])
            except ValueError:
                continue
            label = info["reason"].rstrip(".") or info["trigger"]
            rows.append(gig_snapshots.SnapshotInfo(info["id"], _as_utc(taken_at), label))
        return rows

    def load(self, snapshot_id: str) -> LoadedSnapshot:
        """Load one snapshot in the shape the diff compares.

        Args:
            snapshot_id: Id from ``list_snapshots``.

        Returns:
            Crates, cues, grids, and tags from that snapshot.

        Raises:
            KeyError: If the snapshot, its database copy, or a blob cannot be
                read, or the copy is not a library this check can read.
        """
        try:
            listed = {info.snapshot_id: info for info in self.list_snapshots()}
            info = listed[snapshot_id]
            contents = self.store.load(snapshot_id)
            data = self.store.database_bytes(snapshot_id)
        except snapshots.SnapshotError as exc:
            raise KeyError(snapshot_id) from exc
        if data is None:
            raise KeyError(snapshot_id)
        rows = _snapshot_rows(data, self.space)
        if rows is None:
            raise KeyError(snapshot_id)
        frames = _SavedFrames(contents)
        return _library_snapshot(rows, frames.marks, info)


def _snapshot_rows(data: bytes, space: str) -> _Library | None:
    """Read library rows from a snapshot's database copy.

    Args:
        data: ``master.sqlite`` bytes from the snapshot.
        space: Space name.

    Returns:
        Detached rows, or None when the copy cannot be read.
    """
    fd, name = tempfile.mkstemp(prefix="serato-gigsnap-", suffix=".sqlite")
    path = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        with closing(open_read_only(path)) as conn:
            return _read_library(conn, space, None)
    except (library.LibraryError, sqlite3.Error):
        return None
    finally:
        path.unlink(missing_ok=True)


class _SavedFrames:
    """Cues and grids saved in one snapshot, looked up by track."""

    def __init__(self, contents: snapshots.SnapshotContents):
        """Index the saved frames by path.

        Args:
            contents: Result of ``SnapshotStore.load``.
        """
        self.cues: dict[str, snapshots.CueTrackView] = {row["path"]: row for row in contents["cues"]}
        self.grids: dict[str, snapshots.GridTrackView] = {row["path"]: row for row in contents["grids"]}
        self.seen: set[str] = set(self.cues) | set(self.grids) | {row["path"] for row in contents["tags"]}
        self.by_name: dict[str, list[str]] = {}
        for path in self.seen:
            self.by_name.setdefault(_base_name(path), []).append(path)

    def _find(self, portable_id: str) -> str | None:
        """Return the saved path for a stored id.

        Args:
            portable_id: Path Serato stored.

        Returns:
            The saved path that is that id, or ends with it on some drive.
            None when the snapshot saved no frame for that track.
        """
        if not portable_id:
            return None
        for candidate in _candidates(portable_id, None):
            if str(candidate) in self.seen:
                return str(candidate)
        tail = portable_id.replace("\\", "/").lstrip("/")
        for path in self.by_name.get(_base_name(portable_id), ()):
            if path.replace("\\", "/").endswith("/" + tail):
                return path
        return None

    def marks(self, asset: _Asset) -> tuple[str, tuple[CueMark, ...], tuple[GridMark, ...], bool]:
        """Return the saved cues and grid for one track.

        Args:
            asset: Track row from the snapshot's database copy.

        Returns:
            The path to show, cues, grid, and whether they are known.
        """
        path = self._find(asset.portable_id)
        if path is None:
            return asset.portable_id, (), (), False
        cue = self.cues.get(path)
        grid = self.grids.get(path)
        cue_rows = [] if cue is None else cue["cues"]
        loop_rows = [] if cue is None else cue["loops"]
        grid_rows = [] if grid is None else grid["markers"]
        cues, markers = _marks(cue_rows, loop_rows, grid_rows)
        return path, cues, markers, True


def _base_name(path: str) -> str:
    """Return the last path part, for either separator.

    Args:
        path: File path.

    Returns:
        The file name, folded to lower case.
    """
    return path.replace("\\", "/").rsplit("/", 1)[-1].casefold()


def default_reader(database: Path | None, space: str) -> StoreSnapshots:
    """Return the snapshot reader for a library without writing anything.

    Args:
        database: master.sqlite. None uses ``library.MASTER``.
        space: Space whose rows are compared.

    Returns:
        A reader. An unfinished restore is not rolled back here, because the
        check must not write.
    """
    master = Path(library.MASTER) if database is None else Path(database)
    return StoreSnapshots(snapshots.SnapshotStore(master, recover=False), space)


def _count(count: int, singular: str) -> str:
    """Return a count and a word.

    Args:
        count: How many.
        singular: Singular noun. The plural adds ``s``.

    Returns:
        ``1 file`` or ``3 files``.
    """
    word = singular if count == 1 else singular + "s"
    return f"{count} {word}"


def _drive_summary(drives: Sequence[UnavailableDrive]) -> str:
    """Describe absent drives in one sentence.

    Args:
        drives: Drives that were not connected.

    Returns:
        A hard-red sentence that names each drive and says it is absent.
    """
    names = [drive.name for drive in drives]
    if len(names) == 1:
        listed = names[0]
        verb = "is"
        pronoun = "that drive"
    else:
        listed = ", ".join(names[:-1]) + " and " + names[-1]
        verb = "are"
        pronoun = "those drives"
    return (
        f"Not ready: {listed} {verb} absent. "
        f"Tracks on {pronoun} are unavailable, not missing."
    )


def _score(
    classified: _Classified,
    fresh: bool,
    changes: ChangeReport | None,
    scope_crate: str | None,
) -> tuple[int, bool, bool, tuple[Deduction, ...]]:
    """Turn the groups into a score and Holding it back.

    Args:
        classified: Missing files, drives, streaming tracks, and empty crates.
        fresh: Whether a snapshot was taken in the last seven days.
        changes: Diff, or None when there was nothing to compare.
        scope_crate: Selected crate label. None means the whole space.

    Returns:
        Score, ready flag, hard-red flag, and deductions. A hard red is not
        ready even when the remaining points would pass ``READY_AT``.
    """
    lines: list[Deduction] = []
    hard = False
    if classified.drives:
        hard = True
        lines.append(
            Deduction(
                "absent_drive",
                DRIVE_POINTS * len(classified.drives),
                True,
                _drive_summary(classified.drives),
            )
        )
    if classified.missing:
        hard = True
        points = min(MISSING_CAP, MISSING_POINTS * len(classified.missing))
        place = "in the selected crate" if scope_crate else "in this space"
        lines.append(
            Deduction(
                "missing_files",
                points,
                True,
                f"Not ready: {_count(len(classified.missing), 'missing file')} {place}.",
            )
        )
    if classified.streaming:
        lines.append(
            Deduction(
                "streaming",
                min(STREAM_CAP, STREAM_POINTS * len(classified.streaming)),
                False,
                f"{_count(len(classified.streaming), 'streaming track')}. "
                "They play only while you are logged in to that service.",
            )
        )
    if classified.empty:
        lines.append(
            Deduction(
                "empty_crates",
                min(EMPTY_CAP, EMPTY_POINTS * len(classified.empty)),
                False,
                f"{_count(len(classified.empty), 'empty crate')}. {EMPTY_CRATE_WARNING}",
            )
        )
    if not fresh:
        lines.append(Deduction("snapshot_stale", STALE_POINTS, False, STALE_SNAPSHOT))
    if changes is not None and not changes.empty():
        lines.append(
            Deduction(
                "changes",
                CHANGE_POINTS,
                False,
                _change_summary(changes),
            )
        )
    spent = sum(line.points for line in lines)
    score = max(0, SCORE_START - spent)
    ready = (not hard) and score >= READY_AT
    return score, ready, hard, tuple(lines)


def _change_summary(changes: ChangeReport) -> str:
    """Summarize a diff in one Holding it back line.

    Args:
        changes: Diff that is not empty.

    Returns:
        A short count of what changed.
    """
    parts: list[str] = []
    if changes.crates_added:
        parts.append(f"{_count(len(changes.crates_added), 'crate')} added")
    if changes.crates_removed:
        parts.append(f"{_count(len(changes.crates_removed), 'crate')} removed")
    if changes.crates_edited:
        parts.append(f"{_count(len(changes.crates_edited), 'crate')} edited")
    if changes.tracks_added:
        parts.append(f"{_count(len(changes.tracks_added), 'track')} added")
    if changes.tracks_removed:
        parts.append(f"{_count(len(changes.tracks_removed), 'track')} removed")
    if changes.cues_edited:
        parts.append(f"{_count(len(changes.cues_edited), 'cue edit')}")
    if changes.grids_edited:
        parts.append(f"{_count(len(changes.grids_edited), 'beatgrid edit')}")
    if changes.tags_edited:
        parts.append(f"{_count(len(changes.tags_edited), 'tag edit')}")
    return "Changes since the last snapshot: " + ", ".join(parts) + "."


def run_gig_check(
    database: Path | None = None,
    space: str = library.LIBRARY_SPACE,
    crate_id: int | None = None,
    snapshots_reader: GigSnapshotReader | None = None,
    now: datetime | None = None,
) -> GigReport:
    """Check one space, or one crate, without writing.

    Args:
        database: master.sqlite. None uses ``library.MASTER``.
        space: Space name. The default is Serato Library.
        crate_id: Crate id, including its subcrates. None checks the whole space.
        snapshots_reader: Where saved snapshots come from. None reads the
            snapshot store beside the database, without writing.
        now: Clock for the seven-day window. None uses the current UTC time.

    Returns:
        A frozen report. Missing files in the selected scope, and any absent
        drive in that scope, set ``ready`` false.

    Raises:
        library.LibraryError: If the space name is not one this app reads,
            the database cannot be opened read-only, or the crate is not in
            the space.
    """
    moment = _moment(now)
    if space not in library.ALLOWED_SPACES:
        raise library.LibraryError("That space is not available here.")
    path = Path(library.MASTER) if database is None else Path(database)
    reader = default_reader(path, space) if snapshots_reader is None else snapshots_reader
    with closing(open_read_only(path)) as conn:
        loaded = _read_library(conn, space, crate_id)
    classified = _classify(loaded)
    note, changes, fresh = _changes(reader, loaded, classified, moment)
    score, ready, hard, lines = _score(classified, fresh, changes, loaded.scope_crate)
    return GigReport(
        ready,
        score,
        hard,
        lines,
        classified.missing,
        classified.drives,
        classified.streaming,
        classified.empty,
        note,
        changes,
        space,
        crate_id,
        loaded.scope_crate,
        moment,
    )


def report_to_dict(report: GigReport) -> dict[str, object]:
    """Serialize a report for the page.

    Args:
        report: Check result.

    Returns:
        JSON-ready objects. Field names are the ones ``static/app.js`` reads.
    """
    changes: object
    if report.changes is None:
        changes = None
    else:
        diff = report.changes
        changes = {
            "crates_added": list(diff.crates_added),
            "crates_removed": list(diff.crates_removed),
            "crates_edited": list(diff.crates_edited),
            "tracks_added": list(diff.tracks_added),
            "tracks_removed": list(diff.tracks_removed),
            "cues_edited": list(diff.cues_edited),
            "grids_edited": list(diff.grids_edited),
            "tags_edited": list(diff.tags_edited),
        }
    return {
        "ready": report.ready,
        "score": report.score,
        "hard_red": report.hard_red,
        "holding_it_back": [
            {
                "code": line.code,
                "points": line.points,
                "hard_red": line.hard_red,
                "summary": line.summary,
            }
            for line in report.holding_it_back
        ],
        "missing_files": [
            {"path": item.path, "title": item.title, "artist": item.artist, "crate": item.crate}
            for item in report.missing_files
        ],
        "unavailable_drives": [
            {"name": drive.name, "track_count": drive.track_count, "crates": list(drive.crates)}
            for drive in report.unavailable_drives
        ],
        "streaming_tracks": [
            {
                "service": item.service,
                "path": item.path,
                "title": item.title,
                "artist": item.artist,
                "crate": item.crate,
            }
            for item in report.streaming_tracks
        ],
        "empty_crates": [{"name": item.name, "warning": item.warning} for item in report.empty_crates],
        "snapshot_note": report.snapshot_note,
        "changes": changes,
        "scope": {
            "space": report.scope_space,
            "crate_id": report.scope_crate_id,
            "crate_name": report.scope_crate,
        },
        "checked_at": report.checked_at.isoformat(),
    }


def _section(title: str, lines: Sequence[str]) -> list[str]:
    """Format one block of the CLI report.

    Args:
        title: Heading.
        lines: Body lines. An empty sequence omits the block.

    Returns:
        Heading and indented lines, or an empty list.
    """
    if not lines:
        return []
    block = [title]
    block.extend(f"- {line}" for line in lines)
    return block


def format_report(report: GigReport) -> str:
    """Format a report as plain text.

    Args:
        report: Check result.

    Returns:
        Text ending in a newline. The score, the ready line, and Holding it
        back use the same sentences as the page.
    """
    blocks = [
        f"Ready score: {report.score}",
        "Ready" if report.ready else "Not ready",
        "",
        "Holding it back",
    ]
    if report.holding_it_back:
        blocks.extend(f"- {line.summary}" for line in report.holding_it_back)
    else:
        blocks.append("- Nothing is holding it back.")
    blocks.append("")
    blocks.extend(
        _section(
            "Missing files",
            [item.path for item in report.missing_files],
        )
    )
    if report.missing_files:
        blocks.append("")
    drive_lines = [
        f"{drive.name}: {_count(drive.track_count, 'track')} unavailable"
        for drive in report.unavailable_drives
    ]
    blocks.extend(_section("Unavailable drives", drive_lines))
    if drive_lines:
        blocks.append("")
    stream_lines = [
        f"{item.service}: {item.title}" + (f" — {item.artist}" if item.artist else "")
        for item in report.streaming_tracks
    ]
    blocks.extend(_section("Streaming tracks", stream_lines))
    if stream_lines:
        blocks.append("")
    empty_lines = [f"{item.name} — {item.warning}" for item in report.empty_crates]
    blocks.extend(_section("Empty crates", empty_lines))
    if empty_lines:
        blocks.append("")
    blocks.append("Since last gig")
    blocks.append(report.snapshot_note)
    if report.changes is not None:
        if report.changes.empty():
            blocks.append("Nothing changed since the last snapshot.")
        else:
            diff = report.changes
            for heading, values in (
                ("Crates added", diff.crates_added),
                ("Crates removed", diff.crates_removed),
                ("Crates edited", diff.crates_edited),
                ("Tracks added", diff.tracks_added),
                ("Tracks removed", diff.tracks_removed),
                ("Cues edited", diff.cues_edited),
                ("Beatgrids edited", diff.grids_edited),
                ("Tags edited", diff.tags_edited),
            ):
                blocks.extend(_section(heading, values))
    text = "\n".join(blocks).rstrip() + "\n"
    return text


def main(argv: Sequence[str] | None = None) -> int:
    """Print a gig check and return a status code.

    Args:
        argv: Arguments, without the program name. None reads sys.argv.

    Returns:
        0 when the library is ready. 1 when it is not ready, or the library
        cannot be read. 2 when ``--crate`` is not a number or ``all``.

    The check does not write a file. The report goes to stdout.
    """
    parser = argparse.ArgumentParser(
        prog="gig_check.py",
        description="Read-only pre-gig check. Prints a ready score and what is holding it back.",
    )
    parser.add_argument(
        "--database",
        default=None,
        help="Path to master.sqlite. The default is the live Serato library.",
    )
    parser.add_argument(
        "--space",
        default=library.LIBRARY_SPACE,
        help="Serato space name (default: Serato Library).",
    )
    parser.add_argument(
        "--crate",
        default="all",
        help="Crate id to check, including its subcrates, or all (default: all).",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    crate_text = str(args.crate)
    if crate_text in {"", "all"}:
        crate_id = None
    else:
        try:
            crate_id = int(crate_text)
        except ValueError:
            print("Crate id needs a number, or all.", file=sys.stderr)
            return 2
        if crate_id < 0:
            print("Crate id needs a number, or all.", file=sys.stderr)
            return 2
    database = None if args.database is None else Path(str(args.database))
    try:
        report = run_gig_check(database, str(args.space), crate_id)
    except library.LibraryError as exc:
        print(exc.message, file=sys.stderr)
        return 1
    print(format_report(report), end="")
    return 0 if report.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
