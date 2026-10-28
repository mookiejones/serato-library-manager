"""Export a Serato library to rekordbox.xml.

The file is the DJ_PLAYLISTS document Rekordbox imports from Preferences,
Advanced, rekordbox xml. Crates become playlist folders. Subcrates stay
nested. Hot cues, loops, and the beatgrid are read from the audio file
with the Markers2 and BeatGrid parsers in tags.py. The database and the
audio files are not modified.

Device Library Plus and OneLibrary USB drives are not written.
"""

from __future__ import annotations

import argparse
import math
import os
import re
import sqlite3
import sys
import tempfile
from collections.abc import Mapping, Sequence
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import cast
from urllib.parse import quote
from xml.etree import ElementTree

import app_config
import library
import tags


_ILLEGAL_XML = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\uFFFE\uFFFF]")
_KINDS = {
    ".mp3": "MP3 File",
    ".wav": "WAV File",
    ".wave": "WAV File",
    ".aif": "AIFF File",
    ".aiff": "AIFF File",
    ".flac": "FLAC File",
    ".m4a": "M4A File",
    ".mp4": "M4A File",
    ".aac": "M4A File",
    ".ogg": "OGG File",
    ".alac": "ALAC File",
}


def location_uri(path: str) -> str:
    """Build a rekordbox Location URI for one filesystem path.

    A macOS path keeps its leading slash, so ``/Users/dj/a.mp3`` becomes
    ``file://localhost/Users/dj/a.mp3``. A Windows path gains that slash in
    front of the drive letter, so ``C:\\Users\\dj\\a.mp3`` becomes
    ``file://localhost/C:/Users/dj/a.mp3``. A UNC path keeps two slashes
    after the host (``file://localhost//server/share/a.mp3``). Spaces and
    other reserved characters, including a colon that is not the drive
    separator, are percent-encoded as UTF-8.

    Args:
        path: Filesystem path. Backslashes are separators. An empty path is refused.

    Returns:
        A ``file://localhost`` URI.

    Raises:
        library.LibraryError: If path is empty.
        UnicodeError: If path cannot be encoded as UTF-8.
    """
    if not path or not path.strip():
        raise library.LibraryError("That track has no path.")
    normalized = path.replace("\\", "/")
    drive = ""
    rest = normalized
    # The drive letter is the only colon rekordbox leaves unescaped.
    # A colon later in the name is part of the file name.
    if len(normalized) >= 2 and normalized[0].isalpha() and normalized[1] == ":":
        drive = normalized[:2]
        rest = normalized[2:]
    if not rest.startswith("/"):
        rest = "/" + rest
    encoded = quote(rest, safe="/")
    prefix = f"/{drive}" if drive else ""
    return "file://localhost" + prefix + encoded


def position_marks(parsed: tags.SeratoTags) -> list[dict[str, str]]:
    """Turn Serato cues and loops into rekordbox POSITION_MARK attributes.

    Cues are Type 0. Loops are Type 1 and include End. Start and End are
    seconds with three decimal places, which matches a millisecond source.
    Num keeps the Serato index when it is a hot-cue slot from 0 through 7.
    Any other index is a memory cue (Num -1). Red, Green, and Blue are the
    marker color. A marker with no color is white. Flips are omitted.

    Args:
        parsed: Result of tags.read_serato_tags.

    Returns:
        Attribute dicts in cue order, then loop order.
    """
    marks: list[dict[str, str]] = []
    for cue in parsed["cues"]:
        marks.append(
            _mark(cue["name"], "0", cue["start_ms"], None, cue["index"], cue["color"])
        )
    for loop in parsed["loops"]:
        marks.append(
            _mark(
                loop["name"],
                "1",
                loop["start_ms"],
                loop["end_ms"],
                loop["index"],
                loop["color"],
            )
        )
    return marks


def tempo_entries(beatgrid: Sequence[tags.BeatMarker]) -> list[dict[str, str]]:
    """Turn a Serato beatgrid into rekordbox TEMPO attributes.

    Each marker becomes one TEMPO. Inizio is the marker position in
    seconds. An earlier marker stores a beat count; its BPM is that count
    times 60, divided by the seconds until the next marker. The last
    marker stores BPM directly. Metro is 4/4 and Battito is 1. A segment
    with no positive span uses the last marker's BPM. A BPM that is not
    positive is left out.

    Args:
        beatgrid: Markers from tags.read_serato_tags. An empty list writes nothing.

    Returns:
        Attribute dicts with Inizio, Bpm, Metro, and Battito.
    """
    if not beatgrid:
        return []
    terminal = _terminal_bpm(beatgrid)
    entries: list[dict[str, str]] = []
    last = len(beatgrid) - 1
    for index, marker in enumerate(beatgrid):
        if index == last and "bpm" in marker:
            bpm: float | None = float(marker["bpm"])
        elif index < last:
            bpm = _segment_bpm(marker, beatgrid[index + 1], terminal)
        else:
            bpm = terminal
        if bpm is None or not math.isfinite(bpm) or bpm <= 0:
            continue
        entries.append(
            {
                "Inizio": f"{float(marker['position']):.3f}",
                "Bpm": f"{bpm:.2f}",
                "Metro": "4/4",
                "Battito": "1",
            }
        )
    return entries


def export_rekordbox(space: str, crate_id: int | None) -> str:
    """Build a rekordbox.xml document for one Serato space.

    The collection lists each track that has a path. Crates become a
    playlist tree under ROOT. A crate with subcrates is a folder, and its
    own tracks are a playlist of the same name inside that folder. A crate
    with no subcrates is a playlist. ``crate_id`` None exports the whole
    space. A crate id exports that crate and its subcrates only. The space
    root is not a playlist.

    Args:
        space: Space name. Must be one of library.ALLOWED_SPACES.
        crate_id: Crate to export, including subcrates. None exports the space.

    Returns:
        XML text, including the declaration, ending in a newline.

    Raises:
        library.LibraryError: If the space is not allowed or the crate is not in that space.
    """
    if space not in library.ALLOWED_SPACES:
        raise library.LibraryError("That space is not available here.")
    with closing(library.read_conn()) as conn:
        if crate_id is not None:
            chosen = library._container(conn, crate_id, space)
            if int(chosen["type"]) == 0:
                crate_id = None
        crates = _load_crates(conn, space)
        root_id = _root_id(conn, space)
        tracks = _load_tracks(conn, space)
        membership = _membership(conn, space)
        if crate_id is None:
            selected = {crate["id"] for crate in crates}
            roots = [crate for crate in crates if _is_top(crate, root_id, selected)]
        else:
            selected = set(library._descendant_ids(conn, crate_id))
            roots = [crate for crate in crates if crate["id"] == crate_id]
            wanted: set[int] = set()
            for crate in selected:
                wanted.update(membership.get(crate, ()))
            tracks = [row for row in tracks if int(row["id"]) in wanted]
    present: set[int] = set()
    track_elements: list[ElementTree.Element] = []
    for row in tracks:
        element = _track_element(row)
        if element is None:
            continue
        track_elements.append(element)
        present.add(int(row["id"]))
    collection = ElementTree.Element("COLLECTION", Entries=str(len(track_elements)))
    collection.extend(track_elements)
    root_node = ElementTree.Element("NODE", Type="0", Name="ROOT")
    for crate in roots:
        if crate["id"] not in selected:
            continue
        root_node.append(_crate_node(crate, crates, selected, membership, present))
    root_node.set("Count", str(len(list(root_node))))
    playlists = ElementTree.Element("PLAYLISTS")
    playlists.append(root_node)
    document = ElementTree.Element("DJ_PLAYLISTS", Version="1.0.0")
    document.append(
        ElementTree.Element(
            "PRODUCT",
            Name="Serato Library",
            Version=app_config.APP_VERSION,
            Company="Serato Library",
        )
    )
    document.append(collection)
    document.append(playlists)
    body = ElementTree.tostring(document, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + body + "\n"


def parse_rekordbox(xml_text: str) -> dict[str, object]:
    """Read a DJ_PLAYLISTS document back into tracks and playlist nodes.

    Args:
        xml_text: rekordbox.xml text, with or without an XML declaration.

    Returns:
        A dict with version, tracks, and playlists. Each track has
        track_id, name, artist, album, genre, bpm, key, length, bitrate,
        comments, location, tempos, and marks. playlists is the ROOT node,
        or None when the document has no playlist tree. A node has type,
        name, count, entries, tracks, and children.

    Raises:
        ValueError: If the text is not a DJ_PLAYLISTS document.
    """
    try:
        root = ElementTree.fromstring(xml_text.encode("utf-8"))
    except ElementTree.ParseError as exc:
        raise ValueError("That file is not rekordbox XML.") from exc
    if root.tag != "DJ_PLAYLISTS":
        raise ValueError("That file is not rekordbox XML.")
    tracks: list[dict[str, object]] = []
    collection = root.find("COLLECTION")
    if collection is not None:
        for track in collection.findall("TRACK"):
            tracks.append(
                {
                    "track_id": track.get("TrackID") or "",
                    "name": track.get("Name") or "",
                    "artist": track.get("Artist") or "",
                    "album": track.get("Album") or "",
                    "genre": track.get("Genre") or "",
                    "bpm": track.get("AverageBpm") or "",
                    "key": track.get("Tonality") or "",
                    "length": track.get("TotalTime") or "",
                    "bitrate": track.get("BitRate") or "",
                    "comments": track.get("Comments") or "",
                    "location": track.get("Location") or "",
                    "tempos": [dict(item.attrib) for item in track.findall("TEMPO")],
                    "marks": [dict(item.attrib) for item in track.findall("POSITION_MARK")],
                }
            )
    playlists = None
    playlist_tree = root.find("PLAYLISTS")
    if playlist_tree is not None:
        node = playlist_tree.find("NODE")
        if node is not None:
            playlists = _parse_node(node)
    return {"version": root.get("Version") or "", "tracks": tracks, "playlists": playlists}


def write_export(path: Path, xml_text: str) -> None:
    """Write rekordbox XML to a file, replacing it only after the write finishes.

    Args:
        path: Destination. ``~`` is expanded. A directory is refused.
            ``master.sqlite`` and ``root.sqlite`` are refused.
        xml_text: Document from export_rekordbox.

    Returns:
        None.

    Raises:
        library.LibraryError: If the destination is a library database, a directory, or a missing folder.
        OSError: If the file cannot be written.

    The bytes are written to a temporary file in the destination folder,
    then moved into place. A failed write removes the temporary file.
    """
    destination = path.expanduser()
    if destination.exists() and destination.is_dir():
        raise library.LibraryError("Choose a file for the rekordbox export.")
    _refuse_library_database(destination)
    parent = destination.parent
    if not parent.is_dir():
        raise library.LibraryError("The export folder does not exist.")
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        dir=parent,
        prefix=".rekordbox-",
        suffix=".xml",
        delete=False,
    )
    temporary = Path(handle.name)
    try:
        handle.write(xml_text)
        handle.close()
        os.replace(temporary, destination)
    except Exception:
        handle.close()
        temporary.unlink(missing_ok=True)
        raise
    finally:
        if not handle.closed:
            handle.close()


def main(argv: Sequence[str] | None = None) -> int:
    """Export the Serato library to rekordbox.xml.

    Args:
        argv: Arguments, without the program name. None reads sys.argv.

    Returns:
        0 when the file is written. 1 when the library or the path is refused.
        2 when ``--crate`` is not a number or ``all``.

    The default file is ``rekordbox.xml`` in the current directory. The
    default space is Serato Library and the default crate is the whole space.
    """
    parser = argparse.ArgumentParser(
        prog="rekordbox.py",
        description="Export the Serato library to a rekordbox.xml file (DJ_PLAYLISTS).",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="rekordbox.xml",
        help="XML file to write (default: rekordbox.xml).",
    )
    parser.add_argument(
        "--space",
        default=library.LIBRARY_SPACE,
        help="Serato space name (default: Serato Library).",
    )
    parser.add_argument(
        "--crate",
        default="all",
        help="Crate id to export, including its subcrates, or all (default: all).",
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
    try:
        xml_text = export_rekordbox(str(args.space), crate_id)
        write_export(Path(str(args.output)), xml_text)
    except library.LibraryError as exc:
        print(exc.message, file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Could not write the export: {exc.strerror or exc}", file=sys.stderr)
        return 1
    print(args.output)
    return 0


def _xml_text(value: str) -> str:
    """Remove characters XML 1.0 cannot store in a document.

    Args:
        value: Text that may contain control characters.

    Returns:
        The same text without characters XML 1.0 forbids.
    """
    return _ILLEGAL_XML.sub("", value)


def _mark(
    name: str,
    kind: str,
    start_ms: int,
    end_ms: int | None,
    index: int,
    color: str | None,
) -> dict[str, str]:
    """Build one POSITION_MARK attribute dict.

    Args:
        name: Cue or loop name.
        kind: ``0`` for a cue, ``1`` for a loop.
        start_ms: Start time in milliseconds.
        end_ms: End time in milliseconds. None omits End.
        index: Serato hot-cue or loop index.
        color: ``#RRGGBB``, or None for white.

    Returns:
        Attributes Name, Type, Start, Num, Red, Green, and Blue. Loops also have End.
    """
    red, green, blue = _rgb(color)
    attrs = {
        "Name": _xml_text(name),
        "Type": kind,
        "Start": f"{start_ms / 1000:.3f}",
        "Num": _num(index),
        "Red": red,
        "Green": green,
        "Blue": blue,
    }
    if end_ms is not None:
        attrs["End"] = f"{end_ms / 1000:.3f}"
    return attrs


def _num(index: int) -> str:
    """Map a Serato marker index onto a rekordbox Num.

    Args:
        index: Marker index from Markers2.

    Returns:
        The index as text when it is 0 through 7. Otherwise ``-1``.
    """
    if 0 <= index <= 7:
        return str(index)
    return "-1"


def _rgb(color: str | None) -> tuple[str, str, str]:
    """Split a ``#RRGGBB`` color into rekordbox channel values.

    Args:
        color: CSS hex color from the tag parser, or None.

    Returns:
        Red, green, and blue as decimal strings from 0 to 255. A missing
        or unreadable color is white.
    """
    if not color or len(color) != 7 or not color.startswith("#"):
        return "255", "255", "255"
    try:
        return (
            str(int(color[1:3], 16)),
            str(int(color[3:5], 16)),
            str(int(color[5:7], 16)),
        )
    except ValueError:
        return "255", "255", "255"


def _terminal_bpm(beatgrid: Sequence[tags.BeatMarker]) -> float | None:
    """Return the BPM stored on the last beatgrid marker.

    Args:
        beatgrid: Markers from the BeatGrid parser.

    Returns:
        A positive BPM, or None when the last marker has none.
    """
    for marker in reversed(beatgrid):
        bpm = marker.get("bpm")
        if isinstance(bpm, (int, float)) and not isinstance(bpm, bool) and bpm > 0:
            return float(bpm)
    return None


def _segment_bpm(
    marker: tags.BeatMarker,
    nxt: tags.BeatMarker,
    fallback: float | None,
) -> float | None:
    """Compute the BPM of one beatgrid span.

    Args:
        marker: Earlier marker. It stores a beat count.
        nxt: The next marker. Its position ends the span.
        fallback: BPM to use when the span cannot be divided.

    Returns:
        Beats times 60 divided by the span in seconds, or the fallback.
    """
    beats = marker.get("beats")
    if not isinstance(beats, int) or isinstance(beats, bool) or beats <= 0:
        return fallback
    span = float(nxt["position"]) - float(marker["position"])
    if span <= 0:
        return fallback
    bpm = beats * 60.0 / span
    if not math.isfinite(bpm) or bpm <= 0 or bpm > 999:
        return fallback
    return bpm


def _cell(row: Mapping[str, object], name: str) -> object:
    """Read one column from a track row.

    Args:
        row: Asset columns copied out of the database.
        name: Column name.

    Returns:
        The stored value, or None when the column is absent.
    """
    return row.get(name)


def _text(row: Mapping[str, object], name: str) -> str:
    """Read one text column and strip characters XML cannot store.

    Args:
        row: Asset columns.
        name: Column name.

    Returns:
        The text, or an empty string when the column is empty.
    """
    value = _cell(row, name)
    if value is None:
        return ""
    return _xml_text(str(value))


def _bitrate(value: object) -> str:
    """Convert a Serato bit rate in bits per second to kilobits per second.

    Args:
        value: ``file_bit_rate``, or None.

    Returns:
        The nearest whole kilobit rate, or ``0`` when the value is missing.
    """
    if value is None or value == "":
        return "0"
    try:
        bps = float(cast(float, value))
    except (TypeError, ValueError):
        return "0"
    if not math.isfinite(bps) or bps <= 0:
        return "0"
    return str(int(round(bps / 1000)))


def _total_time(value: object) -> str:
    """Convert length in milliseconds to whole seconds.

    Args:
        value: ``length_ms``, or None.

    Returns:
        Whole seconds, or ``0`` when the length is missing.
    """
    if value is None or value == "":
        return "0"
    try:
        milliseconds = int(cast(int, value))
    except (TypeError, ValueError):
        return "0"
    if milliseconds < 0:
        return "0"
    return str(milliseconds // 1000)


def _average_bpm(row: Mapping[str, object], beatgrid: Sequence[tags.BeatMarker]) -> str:
    """Choose the AverageBpm value for one track.

    Args:
        row: Asset columns. ``bpm`` is the library tempo.
        beatgrid: Markers from the audio file.

    Returns:
        A tempo with two decimal places. The library BPM wins when it is
        positive. Otherwise the last beatgrid BPM is used. Otherwise ``0.00``.
    """
    raw = _cell(row, "bpm")
    if isinstance(raw, (int, float)) and not isinstance(raw, bool) and raw > 0:
        return f"{float(raw):.2f}"
    fallback = _terminal_bpm(beatgrid)
    if fallback is None:
        return "0.00"
    return f"{fallback:.2f}"


def _kind(path: str, row: Mapping[str, object]) -> str:
    """Choose the rekordbox Kind label for one file.

    Args:
        path: Filesystem path used for the extension.
        row: Asset columns. ``format`` is used when the extension is unknown.

    Returns:
        A label such as ``MP3 File``, the stored format, or ``Unknown``.
    """
    suffix = Path(path.replace("\\", "/")).suffix.lower()
    if suffix in _KINDS:
        return _KINDS[suffix]
    stored = _text(row, "format") or _text(row, "type")
    return stored or "Unknown"


def _date_added(value: object) -> str:
    """Format a Serato added time as a calendar date.

    Args:
        value: Unix timestamp, or None.

    Returns:
        ``YYYY-MM-DD`` in UTC, or an empty string when the time is missing.
    """
    if value is None or value == "":
        return ""
    try:
        stamp = int(cast(int, value))
    except (TypeError, ValueError):
        return ""
    if stamp <= 0:
        return ""
    return datetime.fromtimestamp(stamp, timezone.utc).strftime("%Y-%m-%d")


def _rating(value: object) -> str:
    """Map Serato's 0-to-1 rating onto rekordbox's 0-to-255 rating.

    Args:
        value: Stored rating, or None.

    Returns:
        A whole number from 0 to 255.
    """
    if value is None or value == "":
        return "0"
    try:
        number = float(cast(float, value))
    except (TypeError, ValueError):
        return "0"
    if not math.isfinite(number) or number <= 0:
        return "0"
    if number > 1:
        number = 1.0
    return str(int(round(number * 255)))


def _whole(value: object) -> str:
    """Return a non-negative integer stored as text.

    Args:
        value: Disc or track number text, or None.

    Returns:
        The integer text, or ``0`` when the value is not a whole number.
    """
    if value is None:
        return "0"
    text = str(value).strip()
    if text.isdigit():
        return str(int(text))
    return "0"


def _load_crates(conn: sqlite3.Connection, space: str) -> list[dict[str, object]]:
    """Load the crates in one space, in Serato's list order.

    Args:
        conn: Open read connection.
        space: Space name.

    Returns:
        Crates other than the space root. Each dict has id, parent_id, name, and type.
    """
    rows = conn.execute(
        """
        SELECT c.id, c.parent_id, c.name, c.type
        FROM container c
        JOIN space s ON s.id = c.space_id
        WHERE s.name = ? AND c.type != 0
        ORDER BY c.list_order, c.id
        """,
        (space,),
    ).fetchall()
    crates: list[dict[str, object]] = []
    for row in rows:
        parent = row["parent_id"]
        crates.append(
            {
                "id": int(row["id"]),
                "parent_id": None if parent is None else int(parent),
                "name": "" if row["name"] is None else str(row["name"]),
                "type": int(row["type"] or 0),
            }
        )
    return crates


def _root_id(conn: sqlite3.Connection, space: str) -> int | None:
    """Return the space root container id.

    Args:
        conn: Open read connection.
        space: Space name.

    Returns:
        The type 0 container id, or None when this space has no root row.
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
        return None
    return int(row[0])


def _is_top(crate: Mapping[str, object], root_id: int | None, known: set[int]) -> bool:
    """Decide whether a crate sits directly under the space root.

    Args:
        crate: One crate dict from _load_crates.
        root_id: Space root id, or None.
        known: Ids of crates in this export.

    Returns:
        True when the parent is missing, is the space root, or is not part of this export.
    """
    parent = crate["parent_id"]
    if parent is None:
        return True
    parent_id = int(cast(int, parent))
    if root_id is not None and parent_id == root_id:
        return True
    return parent_id not in known


def _load_tracks(conn: sqlite3.Connection, space: str) -> list[dict[str, object]]:
    """Load the asset rows in one space.

    Args:
        conn: Open read connection.
        space: Space name.

    Returns:
        One dict per asset id, in id order. Columns are whatever the asset table stores.
    """
    rows = conn.execute(
        """
        SELECT a.*
        FROM asset a
        JOIN space_asset sa ON sa.asset_id = a.id
        JOIN space s ON s.id = sa.space_id
        WHERE s.name = ?
        ORDER BY a.id
        """,
        (space,),
    ).fetchall()
    seen: set[int] = set()
    tracks: list[dict[str, object]] = []
    for row in rows:
        copied = dict(row)
        asset_id = int(cast(int, copied["id"]))
        if asset_id in seen:
            continue
        seen.add(asset_id)
        tracks.append(copied)
    return tracks


def _membership(conn: sqlite3.Connection, space: str) -> dict[int, list[int]]:
    """Map each crate to its track ids, in playlist order.

    Args:
        conn: Open read connection.
        space: Space name.

    Returns:
        Crate id to asset ids. Order follows container_asset.list_order.
    """
    rows = conn.execute(
        """
        SELECT lc.container_id AS container_id, ca.asset_id AS asset_id
        FROM container_asset ca
        JOIN location_container lc ON lc.id = ca.location_container_id
        JOIN container c ON c.id = lc.container_id
        JOIN space s ON s.id = c.space_id
        WHERE s.name = ?
        ORDER BY ca.list_order, ca.id
        """,
        (space,),
    ).fetchall()
    grouped: dict[int, list[int]] = {}
    for row in rows:
        grouped.setdefault(int(row["container_id"]), []).append(int(row["asset_id"]))
    return grouped


def _track_element(row: Mapping[str, object]) -> ElementTree.Element | None:
    """Build one TRACK element, including tempo and position marks.

    Args:
        row: Asset columns.

    Returns:
        The element, or None when the track has no path.
    """
    portable = _cell(row, "portable_id")
    if not isinstance(portable, str) or not portable.strip():
        return None
    resolved = library._resolved(portable)
    if not resolved:
        return None
    try:
        location = location_uri(resolved)
    except UnicodeError:
        return None
    parsed = tags.read_serato_tags(resolved)
    asset_id = int(cast(int, row["id"]))
    name = _text(row, "name") or "Untitled"
    element = ElementTree.Element(
        "TRACK",
        TrackID=str(asset_id),
        Name=name,
        Artist=_text(row, "artist"),
        Composer=_text(row, "composer"),
        Album=_text(row, "album"),
        Grouping=_text(row, "grouping"),
        Genre=_text(row, "genre"),
        Kind=_kind(resolved, row),
        Size=_whole(_cell(row, "file_size")),
        TotalTime=_total_time(_cell(row, "length_ms")),
        DiscNumber=_whole(_cell(row, "part_of_set")),
        TrackNumber=_whole(_cell(row, "track_number")),
        Year=_text(row, "year"),
        AverageBpm=_average_bpm(row, parsed["beatgrid"]),
        DateAdded=_date_added(_cell(row, "time_added")),
        BitRate=_bitrate(_cell(row, "file_bit_rate")),
        SampleRate=_whole(_cell(row, "file_sample_rate")),
        Comments=_text(row, "comments"),
        PlayCount=_whole(_cell(row, "dj_play_count")),
        Rating=_rating(_cell(row, "rating")),
        Location=location,
        Remixer=_text(row, "remixer"),
        Tonality=_text(row, "key"),
        Label=_text(row, "label"),
        Mix="",
    )
    for tempo in tempo_entries(parsed["beatgrid"]):
        element.append(ElementTree.Element("TEMPO", tempo))
    for mark in position_marks(parsed):
        element.append(ElementTree.Element("POSITION_MARK", mark))
    return element


def _playlist(name: str, track_ids: Sequence[int]) -> ElementTree.Element:
    """Build a playlist NODE for one crate's own tracks.

    Args:
        name: Visible crate name.
        track_ids: Asset ids that are present in the collection, in list order.

    Returns:
        A Type 1 NODE. Entries matches the number of TRACK children.
    """
    node = ElementTree.Element(
        "NODE",
        Type="1",
        Name=name,
        KeyType="0",
        Entries=str(len(track_ids)),
    )
    for asset_id in track_ids:
        node.append(ElementTree.Element("TRACK", Key=str(asset_id)))
    return node


def _crate_tracks(
    crate_id: int,
    membership: Mapping[int, Sequence[int]],
    present: set[int],
) -> list[int]:
    """List the tracks in one crate that were written to the collection.

    Args:
        crate_id: Container id.
        membership: Crate id to asset ids.
        present: Asset ids included in COLLECTION.

    Returns:
        Asset ids, in playlist order, without duplicates.
    """
    tracks: list[int] = []
    seen: set[int] = set()
    for asset_id in membership.get(crate_id, []):
        if asset_id not in present or asset_id in seen:
            continue
        seen.add(asset_id)
        tracks.append(asset_id)
    return tracks


def _crate_node(
    crate: Mapping[str, object],
    crates: Sequence[Mapping[str, object]],
    selected: set[int],
    membership: Mapping[int, Sequence[int]],
    present: set[int],
) -> ElementTree.Element:
    """Build the playlist node for one crate and its selected subcrates.

    Args:
        crate: Crate dict.
        crates: Every crate in the space, in list order.
        selected: Crate ids included in this export.
        membership: Crate id to asset ids.
        present: Asset ids included in COLLECTION.

    Returns:
        A folder NODE when the crate has subcrates, otherwise a playlist NODE.
        A folder's Count is the number of child nodes. A crate that has both
        tracks and subcrates keeps its tracks in a same-named playlist.
    """
    raw_name = library.display_name(str(crate["name"] or ""))
    name = _xml_text(raw_name).strip() or "Crate"
    crate_id = int(cast(int, crate["id"]))
    children = [
        child
        for child in crates
        if child["parent_id"] == crate_id and int(cast(int, child["id"])) in selected
    ]
    tracks = _crate_tracks(crate_id, membership, present)
    if not children:
        return _playlist(name, tracks)
    folder = ElementTree.Element("NODE", Type="0", Name=name)
    if tracks:
        folder.append(_playlist(name, tracks))
    for child in children:
        folder.append(_crate_node(child, crates, selected, membership, present))
    folder.set("Count", str(len(list(folder))))
    return folder


def _parse_node(node: ElementTree.Element) -> dict[str, object]:
    """Read one playlist NODE into a dict.

    Args:
        node: A NODE element from PLAYLISTS.

    Returns:
        type, name, count, entries, track keys, and child nodes.
    """
    return {
        "type": node.get("Type") or "",
        "name": node.get("Name") or "",
        "count": node.get("Count"),
        "entries": node.get("Entries"),
        "tracks": [track.get("Key") or "" for track in node.findall("TRACK")],
        "children": [_parse_node(child) for child in node.findall("NODE")],
    }


def _refuse_library_database(path: Path) -> None:
    """Refuse an export path that would replace a Serato database file.

    Args:
        path: Destination path. It does not need to exist yet.

    Returns:
        None.

    Raises:
        library.LibraryError: If the path is master.sqlite, root.sqlite, or the open library file.
    """
    if path.name in {"master.sqlite", "root.sqlite"}:
        raise library.LibraryError(
            "Choose an XML file. The library database is not an export target."
        )
    try:
        candidate = path.resolve()
        master = Path(library.MASTER).resolve()
    except OSError:
        return
    if candidate == master:
        raise library.LibraryError(
            "Choose an XML file. The library database is not an export target."
        )


if __name__ == "__main__":
    raise SystemExit(main())
