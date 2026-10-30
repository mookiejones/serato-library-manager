#!/usr/bin/env python3
"""Browser for the Serato DJ Pro music library.

Reads master.sqlite. Writes are allowed only while Serato DJ Pro is quit,
and the first write in a process is backed up first.
"""

from __future__ import annotations

import errno
import hmac
import json
import math
import os
import sqlite3
import sys
import threading
from contextlib import closing
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import NotRequired, TypedDict, cast
from urllib.parse import parse_qs, urlparse

import app_config
import app_log
import drive_check
import files
import library
import music_roots
import rekordbox
import related
import setup_flow
import snapshots
import telemetry
import version_info


def app_root() -> Path:
    """Return the directory that holds static/.

    Returns:
        The PyInstaller extract directory when the app is frozen, otherwise the directory of this file.
    """
    # A PyInstaller build extracts static/ into sys._MEIPASS. A source
    # checkout serves the directory beside this file.
    meipass = getattr(sys, "_MEIPASS", None)
    if getattr(sys, "frozen", False) and meipass:
        return Path(meipass)
    return Path(__file__).resolve().parent


ROOT = app_root()
STATIC = ROOT / "static"
HOST = "127.0.0.1"
PORT = 8765
# Required on POST /api/shutdown and POST /api/focus. A page on another
# origin cannot set these headers without a preflight, and this server
# does not allow one. Neither token is placed in the page.
SHUTDOWN_HEADER = "X-Serato-Library-Shutdown"
FOCUS_HEADER = "X-Serato-Library-Focus"
LIBRARY_SPACE = library.LIBRARY_SPACE
NAME_SPLIT = library.NAME_SPLIT
BODY_LIMIT = 2_000_000


def db_path() -> Path:
    """Return the Serato master database path.

    Returns:
        The path stored on library.MASTER.
    """
    return Path(library.MASTER)


_MONTHS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)

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


def _related_end(
    payload: dict[str, object],
    space: str,
    asset_key: str,
    path_key: str,
    title_key: str,
    artist_key: str,
    length_key: str,
) -> tuple[str, str, str, int | None]:
    """Resolve one end of a related-track link from a POST body.

    Args:
        payload: JSON object.
        space: Space used when the body names an asset id.
        asset_key: Key holding an asset id. When present, the library
            supplies the path and the fallback fields.
        path_key: Key holding a path when there is no asset id.
        title_key: Key holding a title for a path that is not in the library.
        artist_key: Key holding an artist for that path.
        length_key: Key holding a length in milliseconds for that path.

    Returns:
        Path, title, artist, and length. Title and artist are empty when
        the body omits them.

    Raises:
        LibraryError: If both the asset and the path are missing, or a
            text field is not text.
        ValueError: If the asset id is not an integer.
    """
    if payload.get(asset_key) is not None:
        return related.identity_for_asset(required_int(payload[asset_key]), space)
    raw_path = payload.get(path_key)
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise library.LibraryError("A track path is required.")
    raw_title = payload.get(title_key, "")
    raw_artist = payload.get(artist_key, "")
    if raw_title is None:
        raw_title = ""
    if raw_artist is None:
        raw_artist = ""
    if not isinstance(raw_title, str) or not isinstance(raw_artist, str):
        raise library.LibraryError("That request is not valid.")
    length = related.clean_length(payload[length_key]) if length_key in payload else None
    return raw_path, raw_title, raw_artist, length


def crate_query(raw: str) -> int | None:
    """Parse a crate query value.

    Args:
        raw: The crate parameter. ``all`` and an empty string mean the whole space.

    Returns:
        The crate id, or None for the whole space.

    Raises:
        library.LibraryError: If the value is not a crate id. The status is 400.
            A number that does not fit in a SQLite integer is rejected here so
            the database does not answer with an overflow.
    """
    if raw in {"", "all"}:
        return None
    if not raw.isascii() or not raw.isdigit():
        raise library.LibraryError("That request is not valid.", 400)
    try:
        crate_id = int(raw, 10)
    except (TypeError, ValueError, OverflowError):
        raise library.LibraryError("That request is not valid.", 400) from None
    if crate_id < 0 or crate_id > 2**63 - 1:
        raise library.LibraryError("That request is not valid.", 400)
    return crate_id


def export_option(value: str, *, default: bool, name: str) -> bool:
    """Read one Rekordbox export switch from a query value.

    Args:
        value: The query text. The caller passes the default word when the
            parameter is absent.
        default: Value used when the text is not a known on or off word.
        name: Parameter name included in the warning.

    Returns:
        True for ``1``, ``true``, and ``yes``. False for ``0``, ``false``,
        and ``no``. Any other text logs a warning and returns ``default``.
    """
    token = value.lower()
    if token in {"1", "true", "yes"}:
        return True
    if token in {"0", "false", "no"}:
        return False
    app_log.logger.warning(
        "Rekordbox option %s=%r is not recognized. Using %s.",
        name,
        value,
        "on" if default else "off",
    )
    return default


def _safe_folder_error(message: str) -> str:
    """Return a folder error that does not include a path.

    Args:
        message: Text from a library error.

    Returns:
        The message when it is one of the short folder sentences.
        A generic sentence when the text contains a path.
    """
    if message in {
        "That folder could not be read.",
        "Shortcuts are left alone.",
        "That request is not valid.",
        "That folder is outside the music folders.",
    }:
        return message
    return "That folder could not be read."


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


def _flag(query: dict[str, list[str]], key: str) -> bool:
    """Return whether a query flag is ``1``, ``true``, or ``yes``.

    Args:
        query: Parsed query string.
        key: Parameter name.

    Returns:
        True when the first value is one of those words, ignoring case.
    """
    raw = query_text(query, key, "") or ""
    return raw.lower() in {"1", "true", "yes"}


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
    """Drop the cached library payloads and the Files music-root cache."""
    _cache["stamp"] = None
    _cache["libraries"] = {}
    files.invalidate_browse_cache()


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
        A local date and time with an English month name, or a dash when the value is empty or not positive.
    """
    if blank(value) or isinstance(value, bool):
        return "—"
    try:
        if isinstance(value, int):
            stamp = int(value)
        elif isinstance(value, (float, str, bytes, bytearray)):
            stamp = int(float(value))
        else:
            return str(value)
    except (TypeError, ValueError):
        return str(value)
    if stamp <= 0:
        return "—"
    when = datetime.fromtimestamp(stamp)
    hour = when.hour % 12
    if hour == 0:
        hour = 12
    period = "AM" if when.hour < 12 else "PM"
    return f"{_MONTHS[when.month - 1]} {when.day}, {when.year} {hour}:{when.minute:02d} {period}"


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


def format_beat_position(value: object) -> str:
    """Format a beatgrid position for the track panel.

    Serato stores the position as a binary float. Printed in full it looks
    like ``1.2300000190734863``. The panel shows milliseconds. The Rekordbox
    export does not use this string. It divides by the stored float.

    Args:
        value: Position in seconds.

    Returns:
        Three decimal places, or an empty string when the value is not a
        finite number.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return ""
    number = float(value)
    if not math.isfinite(number):
        return ""
    return f"{number:.3f}"


def display_bpm(value: object) -> float | None:
    """Return a beatgrid BPM the track panel can show.

    Args:
        value: BPM from a beatgrid marker, or a missing value.

    Returns:
        The number when it is finite. ``None`` when it is missing, ``NaN``,
        or infinite. The panel JSON then contains ``null`` instead of ``NaN``.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return number


def display_beatgrid(markers: object) -> list[dict[str, object]]:
    """Copy beatgrid markers for the track panel.

    Args:
        markers: Beatgrid list from ``markers_for``.

    Returns:
        Marker dicts whose ``position`` is a three-decimal seconds string.
        A non-finite ``bpm`` is ``None``. The export reads the audio file
        itself and does not use this copy.
    """
    shown: list[dict[str, object]] = []
    for marker in as_dicts(markers):
        copy = dict(marker)
        copy["position"] = format_beat_position(marker.get("position"))
        if "bpm" in copy:
            copy["bpm"] = display_bpm(marker.get("bpm"))
        shown.append(copy)
    return shown


def json_ready(value: object) -> object:
    """Replace non-finite floats so the value can be encoded as JSON.

    Args:
        value: A response payload, or a value nested inside one.

    Returns:
        The same structure with ``NaN`` and infinities replaced by ``None``.
        Other values are left as they are.
    """
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return value
    if isinstance(value, dict):
        ready: dict[str, object] = {}
        items = cast("dict[object, object]", value)
        for key, item in items.items():
            ready[str(key)] = json_ready(item)
        return ready
    if isinstance(value, (list, tuple)):
        return [json_ready(item) for item in value]
    return value


def encode_json(payload: object) -> bytes:
    """Encode one API payload as UTF-8 JSON.

    Args:
        payload: Object to send. Non-finite floats become ``null``.

    Returns:
        UTF-8 JSON. ``allow_nan`` is false, so a non-finite number cannot
        be written as the tokens ``NaN`` or ``Infinity``.

    Raises:
        TypeError: If a value cannot be encoded as JSON.
        ValueError: If a non-finite float remains after cleaning.
    """
    return json.dumps(json_ready(payload), ensure_ascii=False, allow_nan=False).encode("utf-8")


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
    # Relative portable ids are tried under the home directory, then at
    # the filesystem root. An absolute id is used as Serato stored it.
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
    telemetry.capture(
        telemetry.EVENT_LIBRARY_SCANNED,
        {"track_count": len(tracks)},
    )
    return payload


def load_track(asset_id: int, space: str | None = None) -> dict[str, object] | None:
    """Load one track, its editable fields, and its marker data.

    Args:
        asset_id: Asset id in master.sqlite.
        space: Space that must contain the track. None selects Serato Library.

    Returns:
        The detail payload, or None when the track is not in the space.
        Beatgrid positions in that payload are three-decimal strings for
        the panel. The export does not read them.

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
        "beatgrid": display_beatgrid(markers["beatgrid"]),
        "markers_found": markers["found"],
        "markers_unavailable": markers["unavailable"],
        "serato": as_dict(_library_call("status")),
    }


_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def host_name(value: str) -> str:
    """Return the host from a Host header or an Origin netloc.

    Args:
        value: ``localhost:8765``, ``127.0.0.1``, or ``[::1]:8765``.

    Returns:
        The host, lowercased, without a port. Empty when the value is not a host.
    """
    text = value.strip().lower()
    if not text:
        return ""
    if text.startswith("["):
        end = text.find("]")
        if end < 0:
            return ""
        return text[1:end]
    if text.count(":") == 1:
        return text.split(":", 1)[0]
    return text


def request_hosts_allowed(host: str | None, origin: str | None) -> bool:
    """Return whether this request is from this computer.

    Args:
        host: The ``Host`` header. Required. A DNS rebinding page sends another name.
        origin: The ``Origin`` header, or None when the client did not send one.

    Returns:
        True when Host is ``localhost``, ``127.0.0.1``, or ``[::1]``, with or
        without a port, and Origin is absent or names one of those hosts.
    """
    if host is None or host_name(host) not in _LOCAL_HOSTS:
        return False
    if origin is None or origin == "":
        return True
    named = urlparse(origin).hostname
    if named is None:
        return False
    return named.lower() in _LOCAL_HOSTS


class Handler(BaseHTTPRequestHandler):
    """Serve the JSON API and the files in static/."""

    server_version = "SeratoLibrary/1.0"

    def log_message(self, format: str, *args: object) -> None:
        """Print one access-log line.

        Args:
            format: Log format string from BaseHTTPRequestHandler.
            *args: Values for that format string.
        """
        line = f"[{self.log_date_time_string()}] {self.address_string()} {format % args}"
        print(line)
        app_log.logger.info("%s", format % args)

    def _report_failure(self, exc: BaseException) -> None:
        """Log an unexpected error and answer with a generic message.

        Args:
            exc: Exception that escaped a request method.

        The response does not include the exception text, which can contain
        a file path. The local log keeps the traceback. Sentry receives the
        exception only after the person has opted in, and the before-send
        hook still removes paths.
        """
        telemetry.capture_exception(exc)
        app_log.logger.exception("Request failed")
        try:
            self.send_json(
                {"error": "Something went wrong. The details are in the local log."},
                status=500,
            )
        except Exception:
            app_log.logger.exception("Could not write the error response")

    def do_GET(self) -> None:
        """Answer a GET request.

        Health, version, and the portable-drive check are answered before the library is opened.
        Settings and logs are answered before the library routes. Library,
        status, track, history, duplicate, file, related-track, M3U, and
        rekordbox XML paths return data. Every other path is a file under static/.
        A Host or Origin that is not this computer is refused first.
        """
        try:
            if self._refuse_foreign_host():
                return
            self._do_GET()
        except Exception as exc:
            self._report_failure(exc)

    def _do_GET(self) -> None:
        """Answer a GET request.

        Health, version, and the portable-drive check do not open the library.
        Library, status, track, history, duplicate, file, M3U, and rekordbox
        XML paths return data. Every other path is a file under static/.
        """
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path == "/api/health":
            self.send_json({"ok": True})
            return
        if parsed.path == "/api/version":
            self.send_json(version_info.payload())
            return
        try:
            if parsed.path == "/api/drive-check":
                self._get_drive_check(query)
                return
            if parsed.path == "/api/settings":
                self.send_json(telemetry.public_settings())
                return
            if parsed.path == "/api/setup":
                self._get_setup(query)
                return
            if parsed.path == "/api/logs":
                text, truncated = app_log.read_logs()
                self.send_json({"text": text, "truncated": truncated})
                return
            if parsed.path == "/api/related":
                self._get_related(query)
                return
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
            if parsed.path == "/api/library-roots":
                self.send_json(music_roots.library_roots(refresh=_flag(query, "refresh")))
                return
            if parsed.path == "/api/files":
                elsewhere = _flag(query, "elsewhere")
                refresh = _flag(query, "refresh")
                self.send_json(
                    files.list_directory(
                        query_text(query, "path", "") or "",
                        elsewhere=elsewhere,
                        refresh=refresh,
                    )
                )
                return
            if parsed.path == "/api/snapshots":
                self._get_snapshots(query)
                return
            if parsed.path == "/api/export.m3u":
                space = require_space(query_text(query, "space"))
                raw_crate = query_text(query, "crate", "all") or "all"
                crate_id = crate_query(raw_crate)
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
            if parsed.path == "/api/export.rekordbox.xml":
                space = require_space(query_text(query, "space"))
                raw_crate = query_text(query, "crate", "all") or "all"
                crate_id = crate_query(raw_crate)
                memory = export_option(query_text(query, "memory", "1") or "1", default=True, name="memory")
                hot_loops = export_option(
                    query_text(query, "hot_loops", "0") or "0", default=False, name="hot_loops"
                )
                key_notation = query_text(query, "key", "asis") or "asis"
                xml_text, report = rekordbox.export_rekordbox(
                    space,
                    crate_id,
                    memory_cues=memory,
                    hot_loops=hot_loops,
                    key_notation=key_notation,
                )
                if (query_text(query, "report", "") or "") == "1":
                    self.send_json({"report": report, "xml": xml_text, "filename": "rekordbox.xml"})
                    return
                body = xml_text.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/xml; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header(
                    "Content-Disposition", "attachment; filename=rekordbox.xml"
                )
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return
        except snapshots.SnapshotError as exc:
            self.send_json({"error": exc.message}, status=exc.status)
            return
        except library.LibraryError as exc:
            self.send_json({"error": exc.message}, status=exc.status)
            return
        except FileNotFoundError as exc:
            if "Serato library not found" not in str(exc):
                raise
            self.send_json(
                {"error": "No Serato library was found on this computer."},
                status=404,
            )
            return
        except (TypeError, ValueError, OverflowError):
            self.send_json({"error": "That request is not valid."}, status=400)
            return
        self.send_file(parsed.path)

    def do_POST(self) -> None:
        """Answer a JSON POST that edits the library, reveals a file, or saves settings.

        A body larger than BODY_LIMIT returns 413. Serato holding the database returns 409.
        Settings and the logs folder do not take the library write lock.
        A Host or Origin that is not this computer is refused first.
        """
        try:
            if self._refuse_foreign_host():
                return
            self._do_POST()
        except Exception as exc:
            self._report_failure(exc)

    def _do_POST(self) -> None:
        """Answer a JSON POST.

        Settings and opening the logs folder return before the library lock.
        Track, crate, import, reveal, duplicate merge, and file changes
        take that lock. A merge preview does not drop the library cache.
        A file preview does.
        """
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        if length > BODY_LIMIT:
            self.send_json({"error": "That upload is too large."}, status=413)
            return
        if parsed.path == "/api/shutdown":
            if length:
                self.rfile.read(length)
            self._post_shutdown()
            return
        if parsed.path == "/api/focus":
            if length:
                self.rfile.read(length)
            self._post_focus()
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
        if parsed.path == "/api/settings":
            self._post_settings(payload)
            return
        if parsed.path == "/api/setup":
            self._post_setup(payload)
            return
        if parsed.path == "/api/logs/open":
            self._post_open_logs()
            return
        try:
            if parsed.path == "/api/related":
                self._post_related(payload)
                return
            if parsed.path == "/api/reveal":
                self.send_json(
                    as_dict(_library_call("reveal", required_int(payload["id"])))
                )
                return
            if parsed.path == "/api/snapshots":
                with _lock:
                    with snapshots.own_writes():
                        self._post_snapshots(payload)
                return
            with _lock:
                with snapshots.own_writes():
                    merging = parsed.path == "/api/duplicates/merge"
                    preview = merging and payload.get("preview") is True
                    if not preview:
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
                        if payload.get("action") == "create":
                            telemetry.capture(telemetry.EVENT_CRATE_CREATED)
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
                        telemetry.capture(telemetry.EVENT_CRATE_CREATED)
                    elif merging:
                        result = as_dict(_library_call("merge_duplicates", payload))
                        if not preview:
                            telemetry.capture(telemetry.EVENT_DUPLICATES_MERGED)
                    elif parsed.path == "/api/files":
                        if payload.get("confirm") is True:
                            result = files.execute(payload)
                        else:
                            result = files.plan(payload)
                    else:
                        self.send_json(
                            {"error": "That action is not available."}, status=404
                        )
                        return
            self.send_json(result)
        except snapshots.SnapshotBlocked as exc:
            self.send_json({"error": exc.message}, status=exc.status)
        except snapshots.SnapshotError as exc:
            self.send_json({"error": exc.message}, status=exc.status)
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

    def _post_shutdown(self) -> None:
        """Stop the server when the caller presents the desktop token.

        The token is set only by the desktop app and the release smoke
        check. ``server.py`` leaves it unset, and this route then answers
        404. A wrong token answers 403. The comparison does not branch on
        the character that differed.

        The listening thread is shut down from another thread so this
        response can finish first.
        """
        expected = getattr(self.server, "shutdown_token", None)
        if not isinstance(expected, str) or not expected:
            self.send_json({"error": "That action is not available."}, status=404)
            return
        provided = self.headers.get(SHUTDOWN_HEADER, "")
        if not isinstance(provided, str) or not hmac.compare_digest(provided, expected):
            self.send_json({"error": "That action is not available."}, status=403)
            return
        self.send_json({"ok": True})
        threading.Thread(target=self.server.shutdown, daemon=True).start()

    def _post_focus(self) -> None:
        """Bring the desktop window forward when the caller presents its token.

        The token is set only by the desktop app. ``server.py`` leaves it
        unset, and this route then answers 404. A wrong token answers 403.
        The comparison does not branch on the character that differed.
        The callback runs on this thread. pywebview moves that call onto
        the GUI thread.
        """
        expected = getattr(self.server, "focus_token", None)
        if not isinstance(expected, str) or not expected:
            self.send_json({"error": "That action is not available."}, status=404)
            return
        provided = self.headers.get(FOCUS_HEADER, "")
        if not isinstance(provided, str) or not hmac.compare_digest(provided, expected):
            self.send_json({"error": "That action is not available."}, status=403)
            return
        callback = getattr(self.server, "focus_window", None)
        if callable(callback):
            try:
                callback()
            except Exception:
                app_log.logger.exception("The window could not be focused")
                self.send_json({"error": "The window could not be focused."}, status=500)
                return
        self.send_json({"ok": True})

    def _post_settings(self, payload: dict[str, object]) -> None:
        """Save the sharing choice, the export bar, the layout, or whether setup finished.

        Args:
            payload: JSON object. ``{"wizard_complete": bool}`` is accepted
                alone, and setup can be marked finished only after the
                sharing choice is already a boolean.
                ``{"layout": {"track_list_width": int | None}}`` is accepted
                alone. A null width resets the default split. Otherwise
                ``telemetry_consent`` must be a boolean when it is present,
                and ``rekordbox`` must be an object whose fields are
                ``hot_loops``, ``memory_cues``, and ``key_notation``.
                Booleans reject integers. ``key_notation`` must be
                ``asis``, ``camelot``, or ``classical``. Any other shape is
                a 400, and the file is left unchanged.
        """
        keys = set(payload)
        if keys == {"wizard_complete"} and isinstance(payload.get("wizard_complete"), bool):
            done = payload["wizard_complete"]
            if not isinstance(done, bool):
                self.send_json({"error": "That request is not valid."}, status=400)
                return
            try:
                app_config.set_wizard_complete(done)
            except ValueError:
                self.send_json(
                    {"error": "Choose whether to share stats before finishing setup."},
                    status=400,
                )
                return
            except OSError:
                self.send_json({"error": "Setup could not be saved."}, status=500)
                return
            self.send_json(telemetry.public_settings())
            return
        if keys == {"layout"} and isinstance(payload.get("layout"), dict):
            layout = payload["layout"]
            assert isinstance(layout, dict)
            width = layout.get("track_list_width")
            if set(layout) != {"track_list_width"} or not (width is None or isinstance(width, int)):
                self.send_json({"error": "That request is not valid."}, status=400)
                return
            try:
                app_config.set_track_list_width(width)
            except ValueError:
                self.send_json({"error": "That request is not valid."}, status=400)
                return
            except OSError:
                self.send_json({"error": "The layout could not be saved."}, status=500)
                return
            self.send_json(telemetry.public_settings())
            return
        allowed = {"telemetry_consent", "rekordbox"}
        if not keys or not keys <= allowed:
            self.send_json({"error": "That request is not valid."}, status=400)
            return
        consent: bool | None = None
        if "telemetry_consent" in payload:
            raw_consent = payload.get("telemetry_consent")
            if not isinstance(raw_consent, bool):
                self.send_json({"error": "That request is not valid."}, status=400)
                return
            consent = raw_consent
        changes: dict[str, bool | str] | None = None
        if "rekordbox" in payload:
            try:
                changes = app_config.rekordbox_changes(payload.get("rekordbox"))
            except ValueError:
                self.send_json({"error": "That request is not valid."}, status=400)
                return
        if consent is None and changes is None:
            self.send_json({"error": "That request is not valid."}, status=400)
            return
        try:
            if changes is not None:
                hot_loops = changes["hot_loops"] if "hot_loops" in changes else None
                memory_cues = changes["memory_cues"] if "memory_cues" in changes else None
                key_notation = changes["key_notation"] if "key_notation" in changes else None
                app_config.update_rekordbox(
                    hot_loops=hot_loops if isinstance(hot_loops, bool) else None,
                    memory_cues=memory_cues if isinstance(memory_cues, bool) else None,
                    key_notation=key_notation if isinstance(key_notation, str) else None,
                )
            if isinstance(consent, bool):
                self.send_json(telemetry.set_consent(consent))
                return
            self.send_json(telemetry.public_settings())
        except OSError:
            self.send_json(
                {"error": "The sharing choice could not be saved."},
                status=500,
            )
        except ValueError:
            self.send_json({"error": "That request is not valid."}, status=400)

    def _get_setup(self, query: dict[str, list[str]]) -> None:
        """Return the library summary, or one folder listing.

        Args:
            query: Parsed query. ``browse`` lists folders. Without it,
                the response describes the library in plain words.

        A missing library is a normal response, not an error. The page
        stays up so the wizard can say what to do next.
        """
        if "browse" in query:
            raw = query_text(query, "browse", "") or ""
            try:
                self.send_json(setup_flow.browse_folders(raw))
            except library.LibraryError as exc:
                self.send_json({"error": _safe_folder_error(exc.message)}, status=exc.status)
            return
        self.send_json(setup_flow.describe_library())

    def _post_setup(self, payload: dict[str, object]) -> None:
        """Check a folder the person picked in the wizard.

        Args:
            payload: JSON object whose only field is ``folder``.
        """
        folder = payload.get("folder")
        if set(payload) != {"folder"} or not isinstance(folder, str):
            self.send_json({"error": "That request is not valid."}, status=400)
            return
        before = Path(library.MASTER)
        try:
            chosen = setup_flow.accept_folder(folder)
        except library.LibraryError as exc:
            self.send_json({"error": _safe_folder_error(exc.message)}, status=exc.status)
            return
        if Path(library.MASTER) != before:
            invalidate()
        self.send_json(chosen)

    def _get_related(self, query: dict[str, list[str]]) -> None:
        """Return saved links and suggestions for one track path.

        Args:
            query: Parsed query string. ``path`` is required. ``space``,
                ``title``, ``artist``, and ``length_ms`` are optional.

        The sidecar file is read. A unique title, artist, and length
        match can update a stored path. ``master.sqlite`` is not written.
        """
        raw_length = query_text(query, "length_ms")
        length_ms = None if raw_length in (None, "") else related.clean_length(raw_length)
        self.send_json(
            related.overview(
                query_text(query, "path", "") or "",
                space=require_space(query_text(query, "space")),
                title=query_text(query, "title"),
                artist=query_text(query, "artist"),
                length_ms=length_ms,
            )
        )

    def _post_related(self, payload: dict[str, object]) -> None:
        """Save, remove, or copy related tracks into a Serato crate.

        Args:
            payload: JSON object with ``action`` of ``add``, ``remove``,
                or ``crate``.

        ``add`` and ``remove`` write only the sidecar file, so they work
        while Serato is open. ``crate`` writes ``master.sqlite`` and uses
        the same backup rules as other library writes. Titles and paths
        are not passed to telemetry.
        """
        action = payload.get("action")
        space = require_space(optional_text(payload.get("space")))
        if action == "add":
            source = _related_end(payload, space, "asset", "path", "title", "artist", "length_ms")
            target = _related_end(
                payload,
                space,
                "target",
                "target_path",
                "target_title",
                "target_artist",
                "target_length_ms",
            )
            mutual = payload.get("mutual")
            if not isinstance(mutual, bool):
                raise library.LibraryError("Choose a one-way or two-way link.")
            result = related.add_link(
                source[0],
                target[0],
                mutual=mutual,
                note=payload.get("note", ""),
                rating=payload.get("rating", None),
                source_title=source[1],
                source_artist=source[2],
                source_length_ms=source[3],
                target_title=target[1],
                target_artist=target[2],
                target_length_ms=target[3],
                space=space,
            )
            direction = "two_way" if result["mutual"] else "one_way"
            telemetry.capture(
                telemetry.EVENT_RELATED_LINK_SAVED,
                {telemetry.LINK_DIRECTION: direction},
            )
            self.send_json(result)
            return
        if action == "remove":
            result = related.remove_link(required_int(payload["id"]))
            telemetry.capture(telemetry.EVENT_RELATED_LINK_REMOVED)
            self.send_json(result)
            return
        if action == "crate":
            if payload.get("asset") is not None:
                path, title, artist, length_ms = related.identity_for_asset(
                    required_int(payload["asset"]), space
                )
            else:
                raw_path = payload.get("path")
                if not isinstance(raw_path, str):
                    raise library.LibraryError("A track path is required.")
                path = raw_path
                raw_title = payload.get("title")
                raw_artist = payload.get("artist")
                title = raw_title if isinstance(raw_title, str) else None
                artist = raw_artist if isinstance(raw_artist, str) else None
                length_ms = (
                    related.clean_length(payload.get("length_ms"))
                    if "length_ms" in payload
                    else None
                )
            with _lock:
                result = related.refresh_crate(
                    path,
                    space=space,
                    title=title,
                    artist=artist,
                    length_ms=length_ms,
                )
                invalidate()
            telemetry.capture(telemetry.EVENT_RELATED_CRATE_WRITTEN)
            self.send_json(result)
            return
        raise library.LibraryError("That related-tracks action is not available.")

    def _post_open_logs(self) -> None:
        """Open the local logs folder.

        The path is the app log directory. The request body cannot choose
        a different folder. The response does not include that path.
        """
        try:
            app_log.open_logs_folder()
        except (OSError, RuntimeError):
            self.send_json(
                {"error": "The logs folder could not be opened."},
                status=500,
            )
            return
        self.send_json({"ok": True})

    def _get_snapshots(self, query: dict[str, list[str]]) -> None:
        """Return the snapshot list, or one restore plan.

        Args:
            query: Parsed query. ``id`` asks for a dry-run plan of that snapshot.
        """
        store = snapshots.current_store()
        snapshot_id = query_text(query, "id", "") or ""
        if snapshot_id:
            self.send_json(store.plan(snapshot_id))
            return
        pending = store.pending_undo()
        self.send_json({
            "snapshots": store.list_snapshots(),
            "pending_undo": pending,
            "write_block": snapshots.write_block_message(),
            "serato_running": store.serato_running(),
        })

    def _post_snapshots(self, payload: dict[str, object]) -> None:
        """Create a snapshot, plan a restore, restore, or undo an outside change.

        Args:
            payload: JSON body with ``action`` of ``create``, ``plan``,
                ``restore``, or ``undo``. ``restore`` also needs ``id`` and
                ``confirm`` true. ``plan`` changes nothing.
        """
        store = snapshots.current_store()
        action = payload.get("action")
        if action == "create":
            info = store.take("manual", "Snapshot taken in the app.")
            self.send_json({"ok": True, "snapshot": info})
            return
        if action == "plan":
            self.send_json(store.plan(str(payload.get("id") or "")))
            return
        if action == "undo":
            if payload.get("confirm") is not True:
                pending = store.pending_undo()
                self.send_json({
                    "ok": False,
                    "preview": True,
                    "pending_undo": pending,
                    "error": "Confirm undo before it is saved." if pending else "There is no outside change to undo.",
                })
                return
            self.send_json(store.undo_outside())
            return
        if action == "restore":
            snapshot_id = str(payload.get("id") or "")
            if payload.get("confirm") is not True:
                self.send_json(store.plan(snapshot_id))
                return
            self.send_json(store.restore(snapshot_id))
            return
        self.send_json({"error": "That action is not available."}, status=404)

    def _refuse_foreign_host(self) -> bool:
        """Refuse a request whose Host or Origin is not this computer.

        Returns:
            True when a 403 response has been sent.
        """
        if request_hosts_allowed(self.headers.get("Host"), self.headers.get("Origin")):
            return False
        self.send_json({"error": "This page only answers on this computer."}, status=403)
        return True

    def _get_drive_check(self, query: dict[str, list[str]]) -> None:
        """Report whether a portable drive's crates can leave the laptop.

        Args:
            query: Parsed query. ``drive`` is the drive root. ``crate`` may
                be repeated. A filesystem name in the query is ignored.

        Raises:
            library.LibraryError: The drive was not chosen, the folder has
                no ``_Serato_`` directory, or a requested crate is not there.
        """
        raw = query_text(query, "drive", "") or ""
        if not raw.strip():
            raise library.LibraryError("Choose a drive.", 400)
        crates = [item.strip() for item in query.get("crate", []) if item.strip()]
        report = drive_check.check_drive(raw, crates or None)
        self.send_json(report.to_dict())

    def send_json(self, payload: object, status: int = 200) -> None:
        """Write a JSON response.

        Args:
            payload: Object encoded as UTF-8 JSON. A non-finite float becomes null.
            status: HTTP status code. Defaults to 200.
        """
        body = encode_json(payload)
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

        The request is joined to ``static/`` and passed through
        ``os.path.realpath``. The result must sit inside that directory.
        A path that climbs out, including one that only shares a prefix
        with the directory name, returns 404.
        """
        rel = "index.html" if url_path in {"", "/"} else url_path.lstrip("/")
        root = os.path.realpath(STATIC)
        candidate = os.path.realpath(os.path.join(root, rel))
        # realpath collapses ".." before the prefix check. The separator
        # stops a sibling such as "static-evil" from matching "static".
        if candidate.startswith(root + os.sep):
            path = Path(candidate)
            if path.is_file():
                kind = {
                    ".html": "text/html; charset=utf-8",
                    ".css": "text/css; charset=utf-8",
                    ".js": "text/javascript; charset=utf-8",
                    ".svg": "image/svg+xml",
                }.get(path.suffix, "application/octet-stream")
                body = path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return
        self.send_error(404)


def serve(port: int | None = None, *, require_library: bool = True) -> ThreadingHTTPServer:
    """Bind the library server on 127.0.0.1.

    Args:
        port: TCP port. None uses 8765. ``0`` asks the operating system
            for a free port. The desktop app uses ``0``.
        require_library: When true, a library chosen on an earlier launch
            is used when that file is still a Serato library, then
            telemetry and the snapshot watch start after the bind if the
            master database exists. A missing database still serves the
            page, so the first-run wizard can explain what to do. The
            release smoke check passes false so a runner without Serato
            does not start telemetry or open a remembered library either.

    Returns:
        A server that is listening and not yet serving. ``shutdown_token``
        and ``focus_token`` are None until the desktop app sets them.

    Raises:
        SystemExit: If the port is already taken. A missing library does
            not exit.
    """
    if require_library:
        setup_flow.apply_remembered_library()
    library_present = db_path().exists()
    app_log.configure()
    if require_library and library_present:
        app_log.logger.info("Library file: %s", db_path())
        try:
            files.recover_interrupted()
        except Exception:
            app_log.logger.exception("An interrupted file change could not be finished.")
    elif require_library:
        app_log.logger.info("No Serato library file yet. The setup wizard will explain the next step.")
    bind_port = PORT if port is None else port
    try:
        httpd = ThreadingHTTPServer((HOST, bind_port), Handler)
    except OSError as exc:
        if exc.errno != errno.EADDRINUSE:
            raise
        shown = PORT if port is None else bind_port
        raise SystemExit(
            f"http://{HOST}:{shown} is already in use. "
            "Quit the other Serato library server (server.py or the desktop app) and try again."
        ) from exc
    httpd.shutdown_token = None
    httpd.focus_token = None
    httpd.focus_window = None
    app_log.logger.info("Server listening on %s:%s", HOST, httpd.server_address[1])
    if require_library and library_present:
        telemetry.activate()
        telemetry.note_app_opened()
        try:
            snapshots.current_store().check_version()
        except snapshots.SnapshotError:
            app_log.logger.exception("A version snapshot could not be saved.")
        snapshots.start_watch()
    return httpd


def main() -> None:
    """Start the library server on 127.0.0.1 port 8765.

    Raises:
        SystemExit: If the port is taken. A missing library still serves
            the page.
    """
    httpd = serve()
    print(f"Serato library  http://{HOST}:{PORT}")
    print(f"Library         {db_path()}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        snapshots.stop_watch()
        telemetry.shutdown()
        httpd.server_close()


if __name__ == "__main__":
    main()
