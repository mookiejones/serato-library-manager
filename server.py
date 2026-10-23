#!/usr/bin/env python3
"""Browser for the Serato DJ Pro music library.

Reads master.sqlite. Writes are allowed only while Serato DJ Pro is quit,
and the first write in a process is backed up first.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import closing
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import NotRequired, TypedDict, cast
from urllib.parse import parse_qs, urlparse

import library

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
HOST = "127.0.0.1"
PORT = 8765
LIBRARY_SPACE = library.LIBRARY_SPACE
NAME_SPLIT = library.NAME_SPLIT
BODY_LIMIT = 2_000_000


def db_path() -> Path:
    """Return the Serato master database path.

    Returns:
        The path stored on library.MASTER.
    """
    return Path(library.MASTER)


BOOL_COLUMNS = {
    "is_corrupt",
    "is_missing",
    "is_readonly",
    "is_beatgrid_locked",
    "is_stale",
    "is_whitelabel",
    "is_karaoke",
    "dj_recently_played",
    "explicit",
    "pending_tempo_map_analysis",
    "should_loop",
    "is_itunes",
    "has_read_tags",
    "is_whitelabel_acl",
    "is_unsupported",
}

THIRD_PARTY = {
    0: "Local file",
    1: "iTunes",
    6: "Apple Music",
}

# column, label, group
FIELDS = [
    ("name", "Title", "Song"),
    ("artist", "Artist", "Song"),
    ("album", "Album", "Song"),
    ("genre", "Genre", "Song"),
    ("year", "Year", "Song"),
    ("composer", "Composer", "Song"),
    ("remixer", "Remixer", "Song"),
    ("label", "Label", "Song"),
    ("grouping", "Grouping", "Song"),
    ("comments", "Comments", "Song"),
    ("comment_language", "Comment language", "Song"),
    ("comment_descriptor", "Comment descriptor", "Song"),
    ("key", "Key", "Song"),
    ("key_value", "Key value", "Song"),
    ("bpm", "BPM", "Song"),
    ("color", "Color", "Song"),
    ("rating", "Rating", "Song"),
    ("emoji", "Emoji", "Song"),
    ("explicit", "Explicit", "Song"),
    ("part_of_set", "Disc", "Song"),
    ("track_number", "Track number", "Song"),
    ("file_name", "File name", "File"),
    ("portable_id", "Stored path", "File"),
    ("resolved_path", "Resolved path", "File"),
    ("file_on_disk", "File on disk", "File"),
    ("file_size", "File size", "File"),
    ("file_bit_rate", "Bitrate", "File"),
    ("file_sample_rate", "Sample rate", "File"),
    ("length_ms", "Length", "File"),
    ("length_sec", "Length in seconds", "File"),
    ("format", "Format", "File"),
    ("type", "Type", "File"),
    ("video_portable_id", "Video path", "File"),
    ("time_added", "Date added", "Status"),
    ("time_modified", "Date modified", "Status"),
    ("dj_play_count", "Play count", "Status"),
    ("dj_recently_played", "Recently played", "Status"),
    ("is_missing", "Missing", "Status"),
    ("is_corrupt", "Corrupt", "Status"),
    ("corrupt_description", "Corrupt description", "Status"),
    ("is_readonly", "Read only", "Status"),
    ("is_beatgrid_locked", "Beatgrid locked", "Status"),
    ("is_whitelabel", "Whitelabel", "Status"),
    ("is_karaoke", "Karaoke", "Status"),
    ("is_stale", "Stale", "Status"),
    ("analysis_flags", "Analysis flags", "Status"),
    ("stems_analyze_state", "Stems analysis", "Status"),
    ("architectures", "Architectures", "Status"),
    ("pending_tempo_map_analysis", "Tempo map pending", "Status"),
    ("third_party_type", "Source", "Status"),
    ("is_itunes", "iTunes", "Status"),
    ("itunes_id", "iTunes id", "Status"),
    ("has_read_tags", "Tags read", "Status"),
    ("is_unsupported", "Unsupported", "Status"),
    ("is_whitelabel_acl", "Whitelabel ACL", "Status"),
    ("should_loop", "Loop", "Status"),
    ("batch_analysis_version", "Batch analysis version", "Status"),
    ("video_effects", "Video effects", "Status"),
    ("id", "Asset id", "Identity"),
    ("external_id", "External id", "Identity"),
    ("dj_external_id", "DJ external id", "Identity"),
    ("location_id", "Location id", "Identity"),
    ("location_path", "Location path", "Identity"),
    ("import_id", "Import id", "Identity"),
    ("type_specific_data", "Type-specific data", "Identity"),
    ("crates", "Crates", "Identity"),
    ("file_name_norm", "File name", "Search copies"),
    ("name_norm", "Title", "Search copies"),
    ("artist_norm", "Artist", "Search copies"),
    ("album_norm", "Album", "Search copies"),
    ("genre_norm", "Genre", "Search copies"),
    ("comments_norm", "Comments", "Search copies"),
    ("label_norm", "Label", "Search copies"),
    ("remixer_norm", "Remixer", "Search copies"),
    ("grouping_norm", "Grouping", "Search copies"),
    ("composer_norm", "Composer", "Search copies"),
    ("year_norm", "Year", "Search copies"),
    ("key_norm", "Key", "Search copies"),
]
class _Cache(TypedDict):
    """In-process library payload cache."""

    stamp: tuple[int, ...] | None
    libraries: dict[str, dict[str, object]]


class _Crate(TypedDict):
    """One crate row sent to the page."""

    id: object
    parent: object
    name: str
    smart: bool
    order: object
    color: object
    expanded: int
    added: object
    tracks: list[object]
    rules: NotRequired[object]


_cache: _Cache = {"stamp": None, "libraries": {}}
_lock = threading.Lock()


def cell(row: sqlite3.Row, column: str) -> object:
    """Return one SQLite value as a concrete object.

    Args:
        row: Result row.
        column: Column name.

    Returns:
        The stored value. SQLite's own annotation is Any, which strict checking treats as unknown.
    """
    value: object = row[column]
    return value


def row_dict(row: sqlite3.Row) -> dict[str, object]:
    """Copy a SQLite row into a string-keyed dict.

    Args:
        row: Result row.

    Returns:
        Column names and values.
    """
    copied: dict[str, object] = {}
    for key in row.keys():
        copied[key] = cell(row, key)
    return copied


def _library_call(name: str, /, *args: object) -> object:
    """Call a library function whose return annotation is still a bare dict.

    Args:
        name: Function name on the library module.
        *args: Arguments for that function.

    Returns:
        The function result.

    Raises:
        TypeError: If name is not callable.
    """
    function: object = getattr(library, name)
    if not callable(function):
        raise TypeError(name)
    return function(*args)


def as_dict(value: object) -> dict[str, object]:
    """Return value when it is a dict with string keys.

    Args:
        value: A library or JSON value.

    Returns:
        A string-keyed copy.

    Raises:
        TypeError: If value is not a dict or a key is not a string.
    """
    if not isinstance(value, dict):
        raise TypeError(value)
    raw = cast("dict[object, object]", value)
    copied: dict[str, object] = {}
    for key, item in raw.items():
        if not isinstance(key, str):
            raise TypeError(key)
        copied[key] = item
    return copied


def as_dicts(value: object) -> list[dict[str, object]]:
    """Return value when it is a list of string-keyed dicts.

    Args:
        value: A library result.

    Returns:
        One dict per list item.

    Raises:
        TypeError: If value is not a list or an item is not a dict.
    """
    if not isinstance(value, list):
        raise TypeError(value)
    items = cast("list[object]", value)
    return [as_dict(item) for item in items]


def text_or_empty(value: object) -> str:
    """Return text, or an empty string for a missing or blank value.

    Args:
        value: A column or JSON value.

    Returns:
        The string, or an empty string when value is missing or blank.

    Raises:
        ValueError: If a present value is not text.
    """
    if not value:
        return ""
    if isinstance(value, str):
        return value
    raise ValueError(value)


def text_cell(row: sqlite3.Row, column: str) -> str:
    """Return a text column, using an empty string when it is null.

    Args:
        row: Result row.
        column: Column name.

    Returns:
        The stored text, or an empty string.
    """
    return text_or_empty(cell(row, column))


def required_int(value: object) -> int:
    """Return value as an int.

    Args:
        value: A number or a decimal string.

    Returns:
        The integer value.

    Raises:
        ValueError: If value cannot be read as an int.
    """
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        return int(value)
    raise ValueError(value)


def int_flag(value: object) -> int:
    """Return an integer flag, treating a missing value as 0.

    Args:
        value: A SQLite integer, or None.

    Returns:
        The integer, or 0 when value is missing.
    """
    if not value:
        return 0
    return required_int(value)


def optional_text(value: object) -> str | None:
    """Return a string or None.

    Args:
        value: A JSON value.

    Returns:
        None when value is missing, otherwise the text.

    Raises:
        ValueError: If value is present and is not text.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise ValueError(value)


def optional_int(value: object) -> int | None:
    """Return an int or None.

    Args:
        value: A JSON value.

    Returns:
        None when value is missing, otherwise the integer.

    Raises:
        ValueError: If value is present and is not an integer.
    """
    if value is None:
        return None
    return required_int(value)


def query_text(
    query: dict[str, list[str]], key: str, default: str | None = None
) -> str | None:
    """Return the first query-string value for key.

    Args:
        query: Parsed query string.
        key: Parameter name.
        default: Value used when the parameter is absent. Defaults to None.

    Returns:
        The first value, or default.
    """
    values = query.get(key)
    if not values:
        return default
    return values[0]


def connect() -> sqlite3.Connection:
    """Open the master database for a read-only query.

    Returns:
        A connection with row access and query_only enabled.

    Raises:
        FileNotFoundError: If the master database file does not exist.
    """
    path = db_path()
    if not path.exists():
        raise FileNotFoundError(f"Serato library not found at {path}")
    uri = f"file:{path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def db_stamp() -> tuple[int, ...]:
    """Return the cache key for the master database and its WAL file.

    Returns:
        Modification times in nanoseconds. A missing file contributes 0.
    """
    path = db_path()
    stamps: list[int] = []
    for candidate in (path, Path(str(path) + "-wal")):
        stamps.append(candidate.stat().st_mtime_ns if candidate.exists() else 0)
    return tuple(stamps)


def invalidate() -> None:
    """Drop the cached library payloads."""
    _cache["stamp"] = None
    _cache["libraries"] = {}


def display_name(name: str) -> str:
    """Return the visible crate name.

    Args:
        name: Stored crate name. Text after the Serato name separator is hidden.

    Returns:
        The name shown in the page.
    """
    return name.split(NAME_SPLIT, 1)[0]


def blank(value: object) -> bool:
    """Return whether a field should display as empty.

    Args:
        value: A database value.

    Returns:
        True when value is None or an empty string.

    Example:
        >>> blank(None)
        True
        >>> blank(0)
        False
    """
    return value is None or value == ""


def format_when(value: object) -> str:
    """Format a Unix timestamp for the track detail pane.

    Args:
        value: Seconds since the epoch, or an empty value.

    Returns:
        A local date and time, or a dash when the value is empty or not positive.
    """
    if blank(value):
        return "—"
    try:
        stamp = int(str(value))
    except (TypeError, ValueError):
        return str(value)
    if stamp <= 0:
        return "—"
    return datetime.fromtimestamp(stamp).strftime("%b %-d, %Y %-I:%M %p")


def format_bool(value: object) -> str:
    """Format a SQLite boolean for display.

    Args:
        value: A numeric flag, or None.

    Returns:
        Yes, No, or a dash.

    Example:
        >>> format_bool(1)
        'Yes'
    """
    if value is None:
        return "—"
    return "Yes" if int(str(value)) else "No"


def format_size(value: object) -> str:
    """Format a file size in bytes.

    Args:
        value: Size in bytes, or an empty value.

    Returns:
        A unit label plus the exact byte count, or a dash.
    """
    if blank(value):
        return "—"
    size = int(str(value))
    units = ["bytes", "KB", "MB", "GB"]
    amount = float(size)
    unit = 0
    while amount >= 1024 and unit < len(units) - 1:
        amount /= 1024
        unit += 1
    if unit == 0:
        return f"{size} bytes"
    return f"{amount:.1f} {units[unit]} ({size:,} bytes)"


def format_bitrate(value: object) -> str:
    """Format a bit rate stored in bits per second.

    Args:
        value: Bits per second, or an empty value.

    Returns:
        A kilobit label, or a dash.
    """
    if blank(value):
        return "—"
    kbps = float(str(value)) / 1000
    if abs(kbps - round(kbps)) < 0.05:
        return f"{round(kbps)} kbps"
    return f"{kbps:.1f} kbps"


def format_rate(value: object) -> str:
    """Format a sample rate stored in hertz.

    Args:
        value: Hertz, or an empty value.

    Returns:
        A kilohertz or hertz label, or a dash.
    """
    if blank(value):
        return "—"
    hz = float(str(value))
    if hz >= 1000:
        khz = hz / 1000
        text = f"{khz:.1f}".rstrip("0").rstrip(".")
        return f"{text} kHz"
    return f"{hz:g} Hz"


def format_length(ms: object, sec: object) -> str:
    """Format a track length.

    Args:
        ms: Length in milliseconds.
        sec: Length in whole seconds, used when ms is empty.

    Returns:
        A minutes and seconds label, or a dash when both inputs are empty.
    """
    if not blank(ms):
        total = int(str(ms)) / 1000
    elif not blank(sec):
        total = int(str(sec))
    else:
        return "—"
    minutes = int(total // 60)
    seconds = total - minutes * 60
    return (
        f"{minutes}:{seconds:06.3f}"
        if not blank(ms)
        else f"{minutes}:{int(seconds):02d}"
    )


def format_color(value: object) -> str:
    """Format a Serato color integer.

    Args:
        value: A 24-bit color, or None. White (0xFFFFFF) means no color.

    Returns:
        None, a #RRGGBB string, or a dash.

    Example:
        >>> format_color(0xFFFFFF)
        'None'
    """
    if value is None:
        return "—"
    color = int(str(value))
    if color == 0xFFFFFF:
        return "None"
    return f"#{color:06X}"


def format_rating(value: object) -> str:
    """Format a rating stored from 0 to 1.

    Args:
        value: A fraction of five stars, or None.

    Returns:
        A five-star label, or the text Not rated.
    """
    if value is None:
        return "Not rated"
    score = float(str(value))
    filled = max(0, min(5, round(score * 5)))
    return f"{'★' * filled}{'☆' * (5 - filled)} ({score:g})"


def format_bits(value: object) -> str:
    """Format an integer bit field.

    Args:
        value: A bit mask, or None.

    Returns:
        The number and the indexes of set bits, or a dash.
    """
    if value is None:
        return "—"
    number = int(str(value))
    if number == 0:
        return "0"
    bits = [str(index) for index in range(32) if number & (1 << index)]
    return f"{number} (bits {', '.join(bits)})"


def format_bpm(value: object) -> str:
    """Format a BPM value.

    Args:
        value: Beats per minute, or an empty value.

    Returns:
        A whole number or a trimmed decimal, or a dash.

    Example:
        >>> format_bpm(120)
        '120'
    """
    if blank(value):
        return "—"
    number = float(str(value))
    if abs(number - round(number)) < 0.001:
        return f"{round(number)}"
    return f"{number:.2f}".rstrip("0").rstrip(".")


def format_source(value: object) -> str:
    """Format the third_party_type column.

    Args:
        value: 0 for a local file, 1 for iTunes, 6 for Apple Music, or another integer.

    Returns:
        A source label, the raw number, or a dash.
    """
    if value is None:
        return "—"
    number = int(str(value))
    label = THIRD_PARTY.get(number)
    if label:
        return label
    return str(number)


def hex_blob(value: object) -> str:
    """Format a binary column as hex text.

    Args:
        value: Bytes, another value, or None.

    Returns:
        Hex text, the string form, or a dash when the value is empty.
    """
    if value is None:
        return "—"
    if isinstance(value, bytes):
        if not value:
            return "—"
        return value.hex()
    return str(value)


def resolve_path(portable_id: str | None) -> tuple[str | None, bool | None]:
    """Resolve a Serato portable_id to a local path.

    Args:
        portable_id: An absolute path, a path under the home directory, or None.

    Returns:
        The candidate path and whether that path exists. Both items are None when the id is empty.
    """
    if portable_id is None or portable_id == "":
        return None, None
    raw = Path(portable_id)
    candidates = (
        [raw]
        if raw.is_absolute()
        else [Path.home() / portable_id, Path("/") / portable_id]
    )
    for candidate in candidates:
        try:
            if candidate.exists():
                return str(candidate), True
        except OSError:
            continue
    return str(candidates[0]), False


def format_field(column: str, row: dict[str, object]) -> str:
    """Format one track column for the detail pane.

    Args:
        column: Asset column name.
        row: Track row, including derived fields such as crates and resolved_path.

    Returns:
        Display text for that column.
    """
    value = row.get(column)
    if column in BOOL_COLUMNS or column == "file_on_disk":
        if column == "file_on_disk" and value is None:
            return "—"
        return format_bool(value)
    if column in {"time_added", "time_modified"}:
        return format_when(value)
    if column == "file_size":
        return format_size(value)
    if column == "file_bit_rate":
        return format_bitrate(value)
    if column == "file_sample_rate":
        return format_rate(value)
    if column == "length_ms":
        return format_length(value, row.get("length_sec"))
    if column == "length_sec":
        if blank(value):
            return "—"
        return str(required_int(value))
    if column == "color":
        return format_color(value)
    if column == "rating":
        return format_rating(value)
    if column in {"analysis_flags", "stems_analyze_state", "architectures"}:
        return format_bits(value)
    if column == "bpm":
        return format_bpm(value)
    if column == "third_party_type":
        return format_source(value)
    if column == "import_id":
        return hex_blob(value)
    if column == "video_effects":
        if not isinstance(value, bytes) or not value:
            return "—"
        return f"Binary, {len(value):,} bytes"
    if column == "crates":
        if not isinstance(value, str) or value == "":
            return "—"
        return value
    if column == "type_specific_data":
        if blank(value):
            return "—"
        text = str(value)
        try:
            parsed: object = json.loads(text)
        except json.JSONDecodeError:
            return text
        return json.dumps(parsed, indent=2, ensure_ascii=False)
    if column == "key_value" and value == -1:
        return "—"
    if blank(value):
        return "—"
    return str(value)


def require_space(space: str | None) -> str:
    """Return an allowed Serato space name.

    Args:
        space: Requested space. None selects Serato Library.

    Returns:
        The space name to query.

    Raises:
        LibraryError: If the space is not one of the four spaces this page edits.
    """
    chosen = space or LIBRARY_SPACE
    if chosen not in library.ALLOWED_SPACES:
        raise library.LibraryError("That space is not available here.")
    return chosen


def load_library(space: str | None = None) -> dict[str, object]:
    """Load the track list and crate tree for one space.

    Args:
        space: Space name. None selects Serato Library.

    Returns:
        Tracks, crates, counts, lock status, and whether edits are allowed.

    Raises:
        LibraryError: If the space name is not allowed.
    """
    chosen = require_space(space)
    with _lock:
        payload = dict(_load_library(chosen))
    info = as_dict(_library_call("status"))
    payload["serato"] = info
    payload["writable"] = info["writable"]
    return payload


def _load_library(space: str) -> dict[str, object]:
    """Query and cache one space.

    Args:
        space: An allowed space name.

    Returns:
        The cached payload for that space. The cache drops when the database stamp changes.

    Raises:
        FileNotFoundError: If the master database is missing.
    """
    stamp = db_stamp()
    if _cache["stamp"] != stamp:
        _cache["stamp"] = stamp
        _cache["libraries"] = {}
    cached = _cache["libraries"].get(space)
    if cached is not None:
        return cached

    with closing(connect()) as conn:
        tracks: list[dict[str, object]] = []
        for row in conn.execute(
            """
            SELECT a.id, a.name, a.artist, a.album, a.genre, a.bpm, a.key,
                   a.length_ms, a.color, a.is_missing, a.format, a.file_name,
                   a.file_size, a.time_added, a.rating, a.emoji,
                   a.is_beatgrid_locked, a.dj_play_count, a.stems_analyze_state,
                   a.file_bit_rate
            FROM asset a
            JOIN space_asset sa ON sa.asset_id = a.id
            JOIN space s ON s.id = sa.space_id
            WHERE s.name = ?
            ORDER BY a.name COLLATE NOCASE, a.artist COLLATE NOCASE, a.id
            """,
            (space,),
        ):
            tracks.append(
                {
                    "id": cell(row, "id"),
                    "name": text_cell(row, "name"),
                    "artist": text_cell(row, "artist"),
                    "album": text_cell(row, "album"),
                    "genre": text_cell(row, "genre"),
                    "bpm": cell(row, "bpm"),
                    "key": text_cell(row, "key"),
                    "length_ms": cell(row, "length_ms"),
                    "color": cell(row, "color"),
                    "missing": int_flag(cell(row, "is_missing")),
                    "format": text_cell(row, "format"),
                    "file": text_cell(row, "file_name"),
                    "file_size": cell(row, "file_size"),
                    "time_added": cell(row, "time_added"),
                    "rating": cell(row, "rating"),
                    "emoji": text_cell(row, "emoji"),
                    "beatgrid_locked": int_flag(cell(row, "is_beatgrid_locked")),
                    "play_count": cell(row, "dj_play_count"),
                    "stems": int_flag(cell(row, "stems_analyze_state")),
                    "bitrate": cell(row, "file_bit_rate"),
                }
            )

        crates: list[_Crate] = []
        root_id: object | None = None
        for row in conn.execute(
            """
            SELECT c.id, c.parent_id, c.name, c.type, c.list_order,
                   c.color, c.expanded, c.time_added
            FROM container c
            JOIN space s ON s.id = c.space_id
            WHERE s.name = ?
            ORDER BY c.list_order, c.id
            """,
            (space,),
        ):
            if cell(row, "type") == 0:
                root_id = cell(row, "id")
            stored_name = cell(row, "name")
            if not isinstance(stored_name, str):
                raise TypeError("crate name is not text")
            crates.append(
                {
                    "id": cell(row, "id"),
                    "parent": cell(row, "parent_id"),
                    "name": display_name(stored_name),
                    "smart": cell(row, "type") == 2,
                    "order": cell(row, "list_order"),
                    "color": cell(row, "color"),
                    "expanded": int_flag(cell(row, "expanded")),
                    "added": cell(row, "time_added"),
                    "tracks": [],
                }
            )

        by_id = {crate["id"]: crate for crate in crates}
        for row in conn.execute(
            """
            SELECT lc.container_id AS crate_id, ca.asset_id
            FROM container_asset ca
            JOIN location_container lc ON lc.id = ca.location_container_id
            JOIN container c ON c.id = lc.container_id
            JOIN space s ON s.id = c.space_id
            WHERE s.name = ?
            ORDER BY lc.container_id, ca.list_order, ca.id
            """,
            (space,),
        ):
            crate = by_id.get(cell(row, "crate_id"))
            if crate is not None:
                crate["tracks"].append(cell(row, "asset_id"))

        rules: dict[object, object] = {}
        for row in conn.execute(
            """
            SELECT r.container_id, r.rules
            FROM smart_crate_rules r
            JOIN container c ON c.id = r.container_id
            JOIN space s ON s.id = c.space_id
            WHERE s.name = ?
            """,
            (space,),
        ):
            blob = cell(row, "rules")
            if not isinstance(blob, (str, bytes, bytearray)):
                raise TypeError("smart crate rules are not text")
            try:
                parsed: object = json.loads(blob)
            except json.JSONDecodeError:
                parsed = blob
            rules[cell(row, "container_id")] = parsed
        for crate in crates:
            if crate["id"] in rules:
                crate["rules"] = rules[crate["id"]]

    payload: dict[str, object] = {
        "source": str(db_path()),
        "space": space,
        "spaces": list(library.ALLOWED_SPACES),
        "track_count": len(tracks),
        "root_id": root_id,
        "tracks": tracks,
        "crates": [crate for crate in crates if crate["id"] != root_id],
    }
    _cache["libraries"][space] = payload
    return payload


def load_track(asset_id: int, space: str | None = None) -> dict[str, object] | None:
    """Load one track, its editable fields, and its marker data.

    Args:
        asset_id: Asset id in master.sqlite.
        space: Space that must contain the track. None selects Serato Library.

    Returns:
        The detail payload, or None when the track is not in the space.

    Raises:
        LibraryError: If the space name is not allowed.
    """
    chosen = require_space(space)
    with closing(connect()) as conn:
        row = conn.execute(
            """
            SELECT a.*,
                   d.video_effects,
                   d.batch_analysis_version,
                   d.should_loop,
                   d.is_itunes,
                   d.itunes_id,
                   d.has_read_tags,
                   d.is_whitelabel_acl,
                   d.is_unsupported,
                   d.external_id AS dj_external_id,
                   l.path AS location_path
            FROM asset a
            JOIN space_asset sa ON sa.asset_id = a.id
            JOIN space s ON s.id = sa.space_id AND s.name = ?
            LEFT JOIN dj_asset_metadata d ON d.asset_id = a.id
            LEFT JOIN location l ON l.id = a.location_id
            WHERE a.id = ?
            """,
            (chosen, asset_id),
        ).fetchone()
        if row is None:
            return None
        data = row_dict(row)
        crate_names: list[str] = []
        crate_ids: list[object] = []
        for crate_row in conn.execute(
            """
            SELECT c.id, c.name
            FROM container_asset ca
            JOIN location_container lc ON lc.id = ca.location_container_id
            JOIN container c ON c.id = lc.container_id
            JOIN space s ON s.id = c.space_id
            WHERE ca.asset_id = ? AND s.name = ?
            ORDER BY c.name COLLATE NOCASE
            """,
            (asset_id, chosen),
        ):
            stored_name = cell(crate_row, "name")
            if not isinstance(stored_name, str):
                raise TypeError("crate name is not text")
            crate_names.append(display_name(stored_name))
            crate_ids.append(cell(crate_row, "id"))
        in_prepare = (
            conn.execute(
                """
            SELECT 1 FROM space_asset sa
            JOIN space s ON s.id = sa.space_id
            WHERE sa.asset_id = ? AND s.name = 'Prepare'
            """,
                (asset_id,),
            ).fetchone()
            is not None
        )
        copies: list[dict[str, object]] = []
        track_name = data.get("name")
        track_artist = data.get("artist")
        length_ms = data.get("length_ms")
        if track_name and track_artist and length_ms is not None:
            seconds = required_int(length_ms) // 1000
            others: list[sqlite3.Row] = []
            copy_params: list[object] = [
                chosen,
                track_name,
                track_artist,
                seconds,
                asset_id,
            ]
            for other in conn.execute(
                """
                SELECT a.id, a.file_bit_rate, a.dj_play_count, a.is_missing, a.file_name
                FROM asset a
                JOIN space_asset sa ON sa.asset_id = a.id
                JOIN space s ON s.id = sa.space_id
                WHERE s.name = ? AND a.name = ? AND a.artist = ?
                  AND CAST(a.length_ms / 1000 AS INTEGER) = ? AND a.id != ?
                ORDER BY a.id
                LIMIT 12
                """,
                copy_params,
            ):
                others.append(other)
            if others:
                other_ids = [cell(other, "id") for other in others]
                marks = ",".join("?" * len(other_ids))
                membership: dict[object, list[str]] = {}
                member_params: list[object] = [chosen, *other_ids]
                for member in conn.execute(
                    f"""
                    SELECT ca.asset_id, c.name
                    FROM container_asset ca
                    JOIN location_container lc ON lc.id = ca.location_container_id
                    JOIN container c ON c.id = lc.container_id
                    JOIN space s ON s.id = c.space_id
                    WHERE s.name = ? AND ca.asset_id IN ({marks})
                    ORDER BY c.name COLLATE NOCASE
                    """,
                    member_params,
                ):
                    member_name = cell(member, "name")
                    if not isinstance(member_name, str):
                        raise TypeError("crate name is not text")
                    membership.setdefault(cell(member, "asset_id"), []).append(
                        display_name(member_name)
                    )
                for other in others:
                    other_id = cell(other, "id")
                    copies.append(
                        {
                            "id": other_id,
                            "file": text_cell(other, "file_name"),
                            "bitrate": format_bitrate(cell(other, "file_bit_rate")),
                            "play_count": cell(other, "dj_play_count"),
                            "missing": int_flag(cell(other, "is_missing")),
                            "crates": ", ".join(membership.get(other_id, [])),
                        }
                    )

    portable = data.get("portable_id")
    if portable is not None and not isinstance(portable, str):
        raise TypeError("portable_id is not text")
    resolved, exists = resolve_path(portable)
    data["resolved_path"] = resolved
    data["file_on_disk"] = None if exists is None else int(exists)
    data["crates"] = ", ".join(crate_names)
    on_disk = exists is True
    markers = as_dict(_library_call("markers_for", resolved, on_disk))
    color_value = data.get("color")
    edit: dict[str, object] = {
        "name": text_or_empty(data.get("name")),
        "artist": text_or_empty(data.get("artist")),
        "album": text_or_empty(data.get("album")),
        "genre": text_or_empty(data.get("genre")),
        "year": text_or_empty(data.get("year")),
        "composer": text_or_empty(data.get("composer")),
        "remixer": text_or_empty(data.get("remixer")),
        "label": text_or_empty(data.get("label")),
        "grouping": text_or_empty(data.get("grouping")),
        "comments": text_or_empty(data.get("comments")),
        "key": text_or_empty(data.get("key")),
        "emoji": text_or_empty(data.get("emoji")),
        "bpm": data.get("bpm"),
        "color": 0xFFFFFF if color_value is None else color_value,
        "rating": data.get("rating"),
        "is_beatgrid_locked": int_flag(data.get("is_beatgrid_locked")),
        "portable_id": text_or_empty(data.get("portable_id")),
    }

    groups: dict[str, list[dict[str, str]]] = {}
    for column, label, group in FIELDS:
        groups.setdefault(group, []).append(
            {
                "column": column,
                "label": label,
                "display": format_field(column, data),
            }
        )

    color_hex: str | None = None
    if color_value is not None and required_int(color_value) != 0xFFFFFF:
        color_hex = f"#{required_int(color_value):06X}"

    return {
        "id": data["id"],
        "title": text_or_empty(data.get("name")) or "Untitled",
        "artist": text_or_empty(data.get("artist")),
        "album": text_or_empty(data.get("album")),
        "bpm": format_bpm(data.get("bpm")),
        "key": text_or_empty(data.get("key")),
        "length": format_length(data.get("length_ms"), data.get("length_sec")),
        "color": color_hex,
        "missing": bool(data.get("is_missing")),
        "groups": [{"name": name, "fields": fields} for name, fields in groups.items()],
        "edit": edit,
        "crate_ids": crate_ids,
        "copies": copies,
        "in_prepare": in_prepare,
        "resolved_path": resolved,
        "file_on_disk": on_disk,
        "cues": markers["cues"],
        "loops": markers["loops"],
        "flips": markers["flips"],
        "beatgrid": markers["beatgrid"],
        "markers_found": markers["found"],
        "markers_unavailable": markers["unavailable"],
        "serato": as_dict(_library_call("status")),
    }


class Handler(BaseHTTPRequestHandler):
    """Serve the JSON API and the files in static/."""

    server_version = "SeratoLibrary/1.0"

    def log_message(self, format: str, *args: object) -> None:
        """Print one access-log line.

        Args:
            format: Log format string from BaseHTTPRequestHandler.
            *args: Values for that format string.
        """
        print(
            f"[{self.log_date_time_string()}] {self.address_string()} {format % args}"
        )

    def do_GET(self) -> None:
        """Answer a GET request.

        Library, status, track, history, duplicate, and M3U paths return data.
        Every other path is a file under static/.
        """
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        try:
            if parsed.path == "/api/library":
                self.send_json(load_library(query_text(query, "space")))
                return
            if parsed.path == "/api/status":
                self.send_json(as_dict(_library_call("status")))
                return
            if parsed.path == "/api/track":
                raw = query_text(query, "id", "") or ""
                try:
                    asset_id = int(raw)
                except ValueError:
                    self.send_json({"error": "Track id is required."}, status=400)
                    return
                track = load_track(asset_id, query_text(query, "space"))
                if track is None:
                    self.send_json({"error": "Track is not in this space."}, status=404)
                    return
                self.send_json(track)
                return
            if parsed.path == "/api/history":
                raw = query_text(query, "session", "") or ""
                if raw:
                    self.send_json(as_dict(_library_call("history_entries", int(raw))))
                else:
                    self.send_json(
                        {"sessions": as_dicts(_library_call("history_sessions"))}
                    )
                return
            if parsed.path == "/api/duplicates":
                space = require_space(query_text(query, "space"))
                groups = as_dicts(_library_call("duplicate_groups", space))
                self.send_json({"space": space, "groups": groups, "count": len(groups)})
                return
            if parsed.path == "/api/export.m3u":
                space = require_space(query_text(query, "space"))
                raw_crate = query_text(query, "crate", "all") or "all"
                crate_id = None if raw_crate in {"", "all"} else int(raw_crate)
                body = library.export_m3u(space, crate_id).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "audio/x-mpegurl; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header(
                    "Content-Disposition", "attachment; filename=crate.m3u"
                )
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return
        except library.LibraryError as exc:
            self.send_json({"error": exc.message}, status=exc.status)
            return
        except (TypeError, ValueError):
            self.send_json({"error": "That request is not valid."}, status=400)
            return
        self.send_file(parsed.path)

    def do_POST(self) -> None:
        """Answer a JSON POST that edits the library or reveals a file.

        A body larger than BODY_LIMIT returns 413. Serato holding the database returns 409.
        """
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        if length > BODY_LIMIT:
            self.send_json({"error": "That upload is too large."}, status=413)
            return
        try:
            parsed_body: object = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self.send_json({"error": "The request body is not JSON."}, status=400)
            return
        try:
            payload = as_dict(parsed_body)
        except TypeError:
            self.send_json({"error": "The request body is not an object."}, status=400)
            return
        try:
            if parsed.path == "/api/reveal":
                self.send_json(
                    as_dict(_library_call("reveal", required_int(payload["id"])))
                )
                return
            with _lock:
                invalidate()
                if parsed.path == "/api/track":
                    result = as_dict(
                        _library_call(
                            "save_track",
                            required_int(payload["id"]),
                            payload.get("fields") or {},
                            require_space(optional_text(payload.get("space"))),
                        )
                    )
                elif parsed.path == "/api/crate":
                    result = as_dict(_library_call("crate_action", payload))
                elif parsed.path == "/api/import.m3u":
                    result = as_dict(
                        _library_call(
                            "import_m3u",
                            require_space(optional_text(payload.get("space"))),
                            optional_int(payload.get("parent")),
                            text_or_empty(payload.get("name")),
                            text_or_empty(payload.get("text")),
                        )
                    )
                else:
                    self.send_json(
                        {"error": "That action is not available."}, status=404
                    )
                    return
            self.send_json(result)
        except library.SeratoOpen as exc:
            detail: object = getattr(exc, "info")
            self.send_json({"error": exc.message, "serato": detail}, status=409)
        except library.LibraryError as exc:
            extra: object = getattr(exc, "info", None)
            self.send_json(
                {"error": exc.message, "serato": extra},
                status=exc.status,
            )
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc).lower():
                info = as_dict(_library_call("status"))
                self.send_json({"error": info["message"], "serato": info}, status=409)
                return
            self.send_json({"error": "The library could not be saved."}, status=500)
        except (TypeError, ValueError, KeyError):
            self.send_json({"error": "That request is not valid."}, status=400)

    def send_json(self, payload: object, status: int = 200) -> None:
        """Write a JSON response.

        Args:
            payload: Object encoded as UTF-8 JSON.
            status: HTTP status code. Defaults to 200.
        """
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, url_path: str) -> None:
        """Write one file from static/.

        Args:
            url_path: Request path. An empty path or / serves index.html.
        """
        rel = "index.html" if url_path in {"", "/"} else url_path.lstrip("/")
        candidate = (STATIC / rel).resolve()
        static_root = STATIC.resolve()
        if not str(candidate).startswith(str(static_root)) or not candidate.is_file():
            self.send_error(404)
            return
        kind = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
        }.get(candidate.suffix, "application/octet-stream")
        body = candidate.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    """Start the library server on 127.0.0.1 port 8765.

    Raises:
        SystemExit: If the master database does not exist.
    """
    if not db_path().exists():
        raise SystemExit(f"Serato library not found at {db_path()}")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Serato library  http://{HOST}:{PORT}")
    print(f"Library         {db_path()}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
