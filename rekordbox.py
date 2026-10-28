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
import unicodedata
from collections.abc import Mapping, MutableMapping, Sequence
from contextlib import closing
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import cast
from urllib.parse import quote
from xml.etree import ElementTree

import app_config
import library
import tags


_ILLEGAL_XML = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\uFFFE\uFFFF]")
# Cases B and C of the LAME/Xing header (pestrela). Serato's stored time
# sits this far later than the time Rekordbox uses for the same MP3.
# Cases A and D, and every file that is not an MP3, stay put.
_MP3_SHIFT_MS = 26
_KEY_NOTATIONS = ("asis", "camelot", "classical")
_CAMELOT_CLASSICAL = {
    "1A": "Abm",
    "2A": "Ebm",
    "3A": "Bbm",
    "4A": "Fm",
    "5A": "Cm",
    "6A": "Gm",
    "7A": "Dm",
    "8A": "Am",
    "9A": "Em",
    "10A": "Bm",
    "11A": "F#m",
    "12A": "C#m",
    "1B": "B",
    "2B": "F#",
    "3B": "Db",
    "4B": "Ab",
    "5B": "Eb",
    "6B": "Bb",
    "7B": "F",
    "8B": "C",
    "9B": "G",
    "10B": "D",
    "11B": "A",
    "12B": "E",
}
_CLASSICAL_CAMELOT = {
    "Abm": "1A",
    "G#m": "1A",
    "Ebm": "2A",
    "D#m": "2A",
    "Bbm": "3A",
    "A#m": "3A",
    "Fm": "4A",
    "Cm": "5A",
    "Gm": "6A",
    "Dm": "7A",
    "Am": "8A",
    "Em": "9A",
    "Bm": "10A",
    "F#m": "11A",
    "Gbm": "11A",
    "C#m": "12A",
    "Dbm": "12A",
    "B": "1B",
    "F#": "2B",
    "Gb": "2B",
    "Db": "3B",
    "C#": "3B",
    "Ab": "4B",
    "G#": "4B",
    "Eb": "5B",
    "D#": "5B",
    "Bb": "6B",
    "A#": "6B",
    "F": "7B",
    "C": "8B",
    "G": "9B",
    "D": "10B",
    "A": "11B",
    "E": "12B",
}
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


def position_marks(
    parsed: tags.SeratoTags,
    shift_ms: int = 0,
    *,
    memory_cues: bool = True,
    hot_loops: bool = False,
    stats: MutableMapping[str, int] | None = None,
) -> list[dict[str, str]]:
    """Turn Serato cues and loops into rekordbox POSITION_MARK attributes.

    A hot cue is Type 0 with Num equal to its Serato index when that index
    is 0 through 7. Each of those cues is also written again as a memory
    cue (Num -1) when ``memory_cues`` is true, which is what CDJs show in
    memory-cue mode. An index outside 0 through 7 is only a memory cue.
    A saved loop is Type 4 and carries End. Its Num is -1 so it does not
    take the hot cue pad of the same number. ``hot_loops`` true uses the
    loop index when that pad is free. Start and End are seconds with three
    decimal places. ``shift_ms`` is subtracted first (the MP3 correction).
    A time that would fall before 0 is written at 0. Red, Green, and Blue
    are the marker color. A marker with no color is white. Flips are omitted.

    Args:
        parsed: Result of tags.read_serato_tags.
        shift_ms: Milliseconds to subtract. 0 leaves the stored time.
        memory_cues: True also writes each hot cue as a memory cue.
        hot_loops: True puts a loop on a free hot cue pad.
        stats: Counts named clamped, flips, memory_cues, memory_only,
            loops_memory, loops_hot, and loops_blocked. None ignores them.

    Returns:
        Attribute dicts. Hot cues come first, each followed by its memory
        copy when that copy is written, then loops.
    """
    marks: list[dict[str, str]] = []
    hot_slots = {cue["index"] for cue in parsed["cues"] if 0 <= cue["index"] <= 7}
    _note(stats, "flips", len(parsed["flips"]))
    for cue in parsed["cues"]:
        if len(cue["name"]) > 20:
            _note(stats, "long_cue_names")
        start, clamped = _shift_time(cue["start_ms"], shift_ms)
        _note(stats, "clamped", 1 if clamped else 0)
        if 0 <= cue["index"] <= 7:
            marks.append(_mark(cue["name"], "0", start, None, cue["index"], cue["color"]))
            if memory_cues:
                marks.append(_mark(cue["name"], "0", start, None, -1, cue["color"]))
                _note(stats, "memory_cues")
        else:
            marks.append(_mark(cue["name"], "0", start, None, -1, cue["color"]))
            _note(stats, "memory_only")
    for loop in parsed["loops"]:
        if len(loop["name"]) > 20:
            _note(stats, "long_cue_names")
        start, start_clamped = _shift_time(loop["start_ms"], shift_ms)
        end, end_clamped = _shift_time(loop["end_ms"], shift_ms)
        _note(stats, "clamped", int(start_clamped) + int(end_clamped))
        number = -1
        if hot_loops and 0 <= loop["index"] <= 7 and loop["index"] not in hot_slots:
            number = loop["index"]
            hot_slots.add(loop["index"])
            _note(stats, "loops_hot")
        elif hot_loops and 0 <= loop["index"] <= 7:
            _note(stats, "loops_blocked")
        else:
            _note(stats, "loops_memory")
        marks.append(_mark(loop["name"], "4", start, end, number, loop["color"]))
    return marks


def tempo_entries(
    beatgrid: Sequence[tags.BeatMarker],
    shift_ms: int = 0,
    stats: MutableMapping[str, int] | None = None,
) -> list[dict[str, str]]:
    """Turn a Serato beatgrid into rekordbox TEMPO attributes.

    Each marker becomes one TEMPO, including a Serato 5.0 grid with a
    marker at every tempo change. Inizio is the marker position in
    seconds. An earlier marker stores a beat count; its BPM is that count
    times 60, divided by the seconds until the next marker. The last
    marker stores BPM directly. Metro is 4/4. Battito is the beat in the
    bar, counting from the first marker as a downbeat, so a marker every
    beat walks 1, 2, 3, 4. ``shift_ms`` is subtracted from Inizio only.
    The BPM still uses the stored positions. A time before 0 is written
    at 0. A BPM that is not positive is left out.

    Args:
        beatgrid: Markers from tags.read_serato_tags. An empty list writes nothing.
        shift_ms: Milliseconds to subtract from each Inizio.
        stats: When set, ``clamped`` counts times written at 0, and
            ``grid_markers`` counts TEMPO entries.

    Returns:
        Attribute dicts with Inizio, Bpm, Metro, and Battito.
    """
    if not beatgrid:
        return []
    terminal = _terminal_bpm(beatgrid)
    entries: list[dict[str, str]] = []
    last = len(beatgrid) - 1
    beats_before = 0
    for index, marker in enumerate(beatgrid):
        if index == last and "bpm" in marker:
            bpm: float | None = float(marker["bpm"])
        elif index < last:
            bpm = _segment_bpm(marker, beatgrid[index + 1], terminal)
        else:
            bpm = terminal
        if bpm is not None and math.isfinite(bpm) and bpm > 0:
            inizio_ms, clamped = _shift_time(int(round(float(marker["position"]) * 1000)), shift_ms)
            _note(stats, "clamped", 1 if clamped else 0)
            shown = f"{bpm:.2f}"
            if abs(bpm - float(shown)) > 0.0001:
                _note(stats, "bpm_rounded")
            entries.append(
                {
                    "Inizio": _seconds(inizio_ms),
                    "Bpm": shown,
                    "Metro": "4/4",
                    "Battito": str((beats_before % 4) + 1),
                }
            )
        if index < last:
            beats = marker.get("beats")
            if isinstance(beats, int) and not isinstance(beats, bool) and beats > 0:
                beats_before += beats
    _note(stats, "grid_markers", len(entries))
    return entries


def export_rekordbox(
    space: str,
    crate_id: int | None,
    *,
    memory_cues: bool = True,
    hot_loops: bool = False,
    key_notation: str = "asis",
) -> tuple[str, list[str]]:
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
        The XML text, including the declaration and a trailing newline, and
        the loss-report lines. The report names what Rekordbox will not keep.

    Raises:
        library.LibraryError: If the space is not allowed, the crate is not in that space, or the key notation is unknown.
    """
    if key_notation not in _KEY_NOTATIONS:
        raise library.LibraryError("Key notation needs to be as stored, Camelot, or classical.")
    if space not in library.ALLOWED_SPACES:
        raise library.LibraryError("That space is not available here.")
    with closing(library.read_conn()) as conn:
        if crate_id is not None:
            chosen = library.container_in_space(conn, crate_id, space)
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
            selected = set(library.descendant_ids(conn, crate_id))
            roots = [crate for crate in crates if crate["id"] == crate_id]
            wanted: set[int] = set()
            for crate in selected:
                wanted.update(membership.get(crate, ()))
            tracks = [row for row in tracks if int(row["id"]) in wanted]
    present: set[int] = set()
    track_elements: list[ElementTree.Element] = []
    stats: dict[str, int] = {}
    unicode_names: list[str] = []
    folder_cache: dict[str, dict[str, str]] = {}
    for row in tracks:
        element = _track_element(
            row,
            memory_cues=memory_cues,
            hot_loops=hot_loops,
            key_notation=key_notation,
            stats=stats,
            unicode_names=unicode_names,
            folder_cache=folder_cache,
        )
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
    xml_text = '<?xml version="1.0" encoding="UTF-8"?>\n' + body + "\n"
    return xml_text, _loss_report(stats, memory_cues, hot_loops, key_notation, unicode_names)


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
    parser.add_argument(
        "--memory-cues",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Also write each hot cue as a memory cue (default: on).",
    )
    parser.add_argument(
        "--hot-loops",
        action="store_true",
        help="Put a saved loop on a free hot cue pad. Otherwise loops are memory loops.",
    )
    parser.add_argument(
        "--key",
        default="asis",
        choices=_KEY_NOTATIONS,
        help="Key text to write: asis, camelot, or classical (default: asis).",
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
        xml_text, report = export_rekordbox(
            str(args.space),
            crate_id,
            memory_cues=bool(args.memory_cues),
            hot_loops=bool(args.hot_loops),
            key_notation=str(args.key),
        )
        write_export(Path(str(args.output)), xml_text)
    except library.LibraryError as exc:
        print(exc.message, file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Could not write the export: {exc.strerror or exc}", file=sys.stderr)
        return 1
    print(args.output)
    for line in report:
        print(line)
    return 0


def position_ms(text: str) -> int:
    """Read a Rekordbox seconds attribute as whole milliseconds.

    Rekordbox keeps three decimal places. The value is read as a decimal,
    so 1.005 stays 1005 milliseconds.

    Args:
        text: A Start, End, or Inizio attribute.

    Returns:
        The nearest millisecond, half up.
    """
    return int((Decimal(text) * 1000).to_integral_value(rounding=ROUND_HALF_UP))


def filesystem_path(path: str, cache: dict[str, dict[str, str]] | None = None) -> str:
    """Return the path spelling the filesystem uses for one file.

    Rekordbox matches Location by the exact string. macOS stores names in
    NFD, so a Serato path in NFC is rewritten to the directory entry when
    that file is on disk. A missing file keeps the stored spelling.
    ``cache`` stores one directory listing per folder so a crate of many
    files in the same folder is not listed once per track.

    Args:
        path: Absolute or relative filesystem path.
        cache: Optional map from a parent path to names found in that folder.
            None lists the folder on every call.

    Returns:
        The directory entry's path when one name matches under NFC, otherwise ``path``.
    """
    candidate = Path(path)
    parent = candidate.parent
    key = str(parent)
    listing = None if cache is None else cache.get(key)
    if listing is None:
        listing = _folder_index(parent)
        if cache is not None:
            cache[key] = listing
    exact = listing.get("\n" + candidate.name)
    if exact is not None:
        return exact
    folded = listing.get(unicodedata.normalize("NFC", candidate.name))
    if folded is not None:
        return folded
    return path


def mp3_timing(path: str) -> tuple[str, int]:
    """Classify one MP3 and return the cue shift Rekordbox needs.

    The shift is subtracted from Serato's stored milliseconds. It depends
    on the LAME/Xing header of that file, not on a single correction for
    every MP3. Case A has no Xing header and case D has a LAME tag whose
    CRC matches, so both stay at 0. Case B is Xing or Info without a LAME
    tag (Lavc is the usual one) and case C is a LAME tag with a CRC of 0
    or any other CRC that does not match. Those two move 26 ms earlier.
    A file that is not an MP3, or an MP3 with no readable frame, stays at 0.

    Args:
        path: Filesystem path of one audio file.

    Returns:
        A case label (``A``, ``B``, ``C``, ``D``, ``unread``, or ``skip``)
        and the milliseconds to subtract.
    """
    if Path(path).suffix.lower() != ".mp3":
        return "skip", 0
    try:
        with Path(path).open("rb") as handle:
            return _mp3_timing_handle(handle)
    except OSError:
        return "unread", 0


def _folder_index(parent: Path) -> dict[str, str]:
    """Index one folder by exact name and by NFC name.

    Args:
        parent: Directory to list. A missing directory yields an empty index.

    Returns:
        Map keys are ``\\n`` plus the exact name, or the NFC name. Values are paths.
    """
    found: dict[str, str] = {}
    if not parent.is_dir():
        return found
    try:
        entries = list(parent.iterdir())
    except OSError:
        return found
    for entry in entries:
        found.setdefault("\n" + entry.name, str(entry))
        found.setdefault(unicodedata.normalize("NFC", entry.name), str(entry))
    return found


def _mp3_timing_handle(handle: object) -> tuple[str, int]:
    """Classify an open MP3 from the frame that follows its ID3 tag.

    Args:
        handle: A binary file positioned anywhere. It is seeked to the start.

    Returns:
        The same pair ``mp3_timing`` returns.
    """
    window = _mp3_header_window(handle)
    frame_at = _mpeg_frame_at(window)
    if frame_at is None:
        return "unread", 0
    header = _mpeg_header(window[frame_at:frame_at + 4])
    if header is None:
        return "unread", 0
    xing_at = frame_at + header
    if xing_at + 8 > len(window) or window[xing_at:xing_at + 4] not in {b"Xing", b"Info"}:
        return "A", 0
    return _xing_case(window, frame_at, xing_at)


def _mp3_header_window(handle: object) -> bytes:
    """Read the first MPEG frame after an ID3 tag.

    The tag size is the synchsafe length in the ID3 header. A footer flag
    adds ten more bytes. About 4 KB after that point holds the Xing or
    Info header, even when the tag itself is a megabyte of artwork.

    Args:
        handle: A binary file. It must support seek and read.

    Returns:
        The bytes at the start of the audio, or an empty string when the
        header cannot be read.
    """
    reader = cast("object", handle)
    seek = getattr(reader, "seek")
    read = getattr(reader, "read")
    seek(0)
    header = read(10)
    start = 0
    if isinstance(header, bytes) and len(header) >= 10 and header[:3] == b"ID3":
        size = 0
        for byte in header[6:10]:
            size = (size << 7) | (byte & 0x7F)
        footer = 10 if header[5] & 0x10 else 0
        start = 10 + size + footer
    seek(start)
    chunk = read(4096)
    return chunk if isinstance(chunk, bytes) else b""


def _inspect_audio(path: str, on_disk: bool) -> tuple[tags.SeratoTags, tuple[str, int]]:
    """Read Serato tags and the MP3 timing case in one open.

    Args:
        path: Filesystem path.
        on_disk: False skips the open and returns an empty tag result.

    Returns:
        Parsed tags, and the MP3 timing pair. A file that is not an MP3
        is ``skip`` with a shift of 0.
    """
    if not on_disk:
        return tags.serato_tags_from_regions(b""), ("skip", 0)
    file = Path(path)
    size = file.stat().st_size
    with file.open("rb") as handle:
        head = handle.read(min(size, 2_000_000))
        tail = b""
        if size > 2_000_000:
            handle.seek(max(0, size - 512_000))
            tail = handle.read(512_000)
        timing = ("skip", 0)
        if file.suffix.lower() == ".mp3":
            timing = _mp3_timing_handle(handle)
    return tags.serato_tags_from_regions(head, tail), timing


def _file_label(portable: str) -> str:
    """Return a file name that can be printed when the path will not encode.

    Args:
        portable: Stored path, which may contain a lone surrogate.

    Returns:
        The last path segment, with characters that cannot be encoded replaced.
    """
    text = portable.replace("\\", "/")
    name = text.rsplit("/", 1)[-1]
    safe = name.encode("utf-8", "replace").decode("utf-8")
    return safe or "a track"


def _track_colour(value: object) -> str | None:
    """Format a Serato track color for the Rekordbox Colour attribute.

    Args:
        value: Integer color from the asset row, or None. White is Serato's
            empty color and is not written.

    Returns:
        ``#RRGGBB``, or None when there is no color.
    """
    if value is None or value == "":
        return None
    try:
        color = int(cast(int, value))
    except (TypeError, ValueError):
        return None
    if color < 0 or color > 0xFFFFFF or color == 0xFFFFFF:
        return None
    return f"#{color:06X}"


def notation_key(stored: str, notation: str) -> tuple[str, str]:
    """Rewrite a musical key into the notation Rekordbox should show.

    Args:
        stored: The key text from Serato. Empty stays empty.
        notation: ``asis``, ``camelot``, or ``classical``.

    Returns:
        The text to write, and a status of ``asis``, ``converted``, or
        ``unrecognized``. An empty key is ``asis``.

    Raises:
        library.LibraryError: If notation is not one of the three names.
    """
    if notation not in _KEY_NOTATIONS:
        raise library.LibraryError("Key notation needs to be as stored, Camelot, or classical.")
    text = stored.strip()
    if not text or notation == "asis":
        return stored, "asis"
    camelot = _as_camelot(text)
    if camelot is None:
        return stored, "unrecognized"
    if notation == "camelot":
        return camelot, "converted" if camelot != text else "asis"
    classical = _CAMELOT_CLASSICAL[camelot]
    return classical, "converted" if classical != text else "asis"


def _as_camelot(text: str) -> str | None:
    """Map one key name onto a Camelot code.

    Args:
        text: A Camelot code or a classical name such as ``Am`` or ``A minor``.

    Returns:
        A code such as ``8A``, or None when the name is not recognized.
    """
    compact = text.strip().replace(" ", "")
    camelot = compact.upper()
    if camelot in _CAMELOT_CLASSICAL:
        return camelot
    minor = compact.lower().endswith("minor") or compact.lower().endswith("min")
    base = compact
    for suffix in ("minor", "min", "m"):
        if base.lower().endswith(suffix) and len(base) > len(suffix):
            base = base[: -len(suffix)]
            minor = True
            break
    base = base[:1].upper() + base[1:]
    if minor:
        return _CLASSICAL_CAMELOT.get(f"{base}m")
    return _CLASSICAL_CAMELOT.get(base)


def _note(stats: MutableMapping[str, int] | None, key: str, amount: int = 1) -> None:
    """Add a count to a loss-report map.

    Args:
        stats: Counter map. None does nothing.
        key: Counter name.
        amount: How much to add. 0 leaves the map unchanged.
    """
    if stats is None or amount == 0:
        return
    stats[key] = stats.get(key, 0) + amount


def _shift_time(stored_ms: int, shift_ms: int) -> tuple[int, bool]:
    """Subtract a timing correction and clamp at zero.

    Args:
        stored_ms: Position from the Serato tag, in milliseconds.
        shift_ms: Milliseconds to subtract.

    Returns:
        The written millisecond and True when a positive time was clamped.
    """
    adjusted = int(stored_ms) - int(shift_ms)
    if adjusted < 0:
        return 0, int(stored_ms) > 0
    return adjusted, False


def _seconds(milliseconds: int) -> str:
    """Format whole milliseconds as Rekordbox seconds.

    Args:
        milliseconds: A time that is already on the millisecond grid.

    Returns:
        Three decimal places, such as ``1.005``.
    """
    whole, frac = divmod(max(0, int(milliseconds)), 1000)
    return f"{whole}.{frac:03d}"


def _crc16_lame(data: bytes) -> int:
    """Compute the CRC-16 LAME stores in an Info tag.

    Args:
        data: Bytes from the start of the MPEG frame up to the CRC field.

    Returns:
        The 16-bit CRC. The polynomial is the reflected form of 0x8005.
    """
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
        crc &= 0xFFFF
    return crc


def _mpeg_frame_at(blob: bytes) -> int | None:
    """Find the first MPEG audio frame after an optional ID3 tag.

    Args:
        blob: The start of an audio file.

    Returns:
        The index of the frame header, or None when none is found.
    """
    pos = 0
    if blob.startswith(b"ID3") and len(blob) >= 10:
        size = 0
        for byte in blob[6:10]:
            size = (size << 7) | (byte & 0x7F)
        pos = 10 + size
    limit = min(len(blob) - 4, pos + 262144)
    while pos < limit:
        if blob[pos] == 0xFF and _mpeg_header(blob[pos:pos + 4]) is not None:
            return pos
        pos += 1
    return None


def _mpeg_header(word: bytes) -> int | None:
    """Return the byte offset of a Xing tag inside one MPEG frame.

    Args:
        word: Four header bytes.

    Returns:
        How many bytes from the header to the Xing or Info tag, or None
        when the word is not an MPEG Layer III header.
    """
    if len(word) < 4 or word[0] != 0xFF or word[1] & 0xE0 != 0xE0:
        return None
    version_id = (word[1] >> 3) & 0x03
    layer = (word[1] >> 1) & 0x03
    bitrate_idx = (word[2] >> 4) & 0x0F
    sample_idx = (word[2] >> 2) & 0x03
    if version_id == 1 or layer != 1 or bitrate_idx in {0, 0x0F} or sample_idx == 3:
        return None
    channel = (word[3] >> 6) & 0x03
    if version_id == 3:
        side = 17 if channel == 3 else 32
    else:
        side = 9 if channel == 3 else 17
    return 4 + side


def _xing_case(blob: bytes, frame_at: int, xing_at: int) -> tuple[str, int]:
    """Classify a Xing or Info tag as LAME case B, C, or D.

    Args:
        blob: File bytes that contain the frame.
        frame_at: Index of the MPEG header.
        xing_at: Index of the Xing or Info magic.

    Returns:
        The case label and the milliseconds to subtract.
    """
    if xing_at + 8 > len(blob):
        return "unread", 0
    flags = int.from_bytes(blob[xing_at + 4:xing_at + 8], "big")
    pos = xing_at + 8
    if flags & 0x01:
        pos += 4
    if flags & 0x02:
        pos += 4
    if flags & 0x04:
        pos += 100
    if flags & 0x08:
        pos += 4
    if pos + 9 > len(blob):
        return "unread", 0
    encoder = blob[pos:pos + 9].lower()
    if not encoder.startswith(b"lame"):
        return "B", _MP3_SHIFT_MS
    crc_at = pos + 34
    if crc_at + 2 > len(blob):
        return "C", _MP3_SHIFT_MS
    stored = int.from_bytes(blob[crc_at:crc_at + 2], "big")
    if stored == 0 or stored != _crc16_lame(blob[frame_at:crc_at]):
        return "C", _MP3_SHIFT_MS
    return "D", 0


def _loss_report(
    stats: Mapping[str, int],
    memory_cues: bool,
    hot_loops: bool,
    key_notation: str,
    unicode_names: Sequence[str] = (),
) -> list[str]:
    """Build the lines that say what this export cannot carry into Rekordbox.

    Args:
        stats: Counters from the track loop.
        memory_cues: Whether hot cues were duplicated as memory cues.
        hot_loops: Whether loops were allowed onto free hot cue pads.
        key_notation: The key notation that was requested.
        unicode_names: File names whose paths could not be encoded.

    Returns:
        One sentence per line. The import warning is always first.
    """
    lines = [
        "Rekordbox 5.6.1 and later leaves tracks that are already in the collection unchanged.",
        "Overwrite them from the rekordbox xml list: select all, right-click, Import to Collection, and answer Yes to load information from imported library.",
        "That replaces cues, the beatgrid, and tags. A cue that exists only in Rekordbox is removed.",
    ]
    omitted = stats.get("omitted", 0)
    if omitted:
        lines.append(f"{omitted} tracks had no path and were left out.")
    missing = stats.get("missing_file", 0)
    if missing:
        lines.append(f"{missing} tracks were not on disk, so the path spelling was left as Serato stored it.")
    flips = stats.get("flips", 0)
    if flips:
        lines.append(f"{flips} flips were left out. Rekordbox has no flip markers.")
    if stats.get("marks_written"):
        lines.append("Cue colors are written as red, green, and blue. Rekordbox may snap them to its palette.")
    long_names = stats.get("long_cue_names", 0)
    if long_names:
        lines.append(
            f"{long_names} cue names are longer than 20 characters. A CDJ shows only the start of the name."
        )
    else:
        lines.append("A CDJ shows only about the first 20 characters of a cue name.")
    if memory_cues and stats.get("memory_cues"):
        lines.append(f"{stats['memory_cues']} hot cues were also written as memory cues.")
    elif not memory_cues:
        lines.append("Hot cues were not copied to memory cues. Some CDJ screens only list memory cues.")
    memory_only = stats.get("memory_only", 0)
    if memory_only:
        lines.append(f"{memory_only} cues outside slots 0-7 were written only as memory cues.")
    if stats.get("loops_memory") and not hot_loops:
        lines.append(
            f"{stats['loops_memory']} saved loops were written as memory loops so they do not take a hot cue slot."
        )
    if stats.get("loops_hot"):
        lines.append(f"{stats['loops_hot']} saved loops were written on a free hot cue slot.")
    if stats.get("loops_blocked"):
        lines.append(
            f"{stats['loops_blocked']} saved loops stayed memory loops because that slot already has a hot cue."
        )
    if stats.get("mp3_shift"):
        lines.append(
            f"{stats['mp3_shift']} MP3s were moved 26 ms earlier to match Rekordbox (LAME/Xing case B or C)."
        )
    if stats.get("mp3_kept"):
        lines.append(f"{stats['mp3_kept']} MP3s kept their cue times (LAME/Xing case A or a valid LAME CRC).")
    if stats.get("mp3_unread"):
        lines.append(f"{stats['mp3_unread']} MP3s had no readable MPEG frame, so no timing correction was applied.")
    if stats.get("clamped"):
        lines.append(
            f"{stats['clamped']} cue or grid times fell before 0 after the MP3 correction and were written at the start."
        )
    if stats.get("grid_unsupported"):
        lines.append(f"{stats['grid_unsupported']} beatgrids could not be read and were left out.")
    if stats.get("grid_dynamic"):
        lines.append(
            f"{stats['grid_dynamic']} tracks have a beatgrid with more than one marker. "
            "Each marker is a TEMPO entry. The first marker is treated as a downbeat. "
            "If it is not a downbeat, the bars in Rekordbox are shifted."
        )
    if stats.get("bpm_rounded") or stats.get("grid_dynamic"):
        lines.append("TEMPO BPM values are written to two decimal places, so a grid can drift.")
    if unicode_names:
        shown = ", ".join(unicode_names[:20])
        extra = f" and {len(unicode_names) - 20} more" if len(unicode_names) > 20 else ""
        lines.append(
            f"{len(unicode_names)} tracks had a path that could not be encoded and were left out: {shown}{extra}."
        )
    lines.append("Track color is written as Colour when Serato has one. Rekordbox may ignore it.")
    lines.append("Beatgrid lock, replay gain, overview waveforms, stems, and play history are not copied.")
    lines.append("Smart crates are ordinary playlists in this file. Their rules are not copied.")
    if key_notation == "asis":
        lines.append("Musical key is the text Serato stores. It was not translated between Camelot and classical.")
    elif key_notation == "camelot":
        lines.append("Musical key was written as Camelot.")
    else:
        lines.append("Musical key was written as classical names.")
    unrecognized = stats.get("key_unrecognized", 0)
    if unrecognized and key_notation != "asis":
        lines.append(f"{unrecognized} keys were left unchanged because they were not Camelot or a classical name.")
    return lines


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
        "Start": _seconds(start_ms),
        "Num": _num(index),
        "Red": red,
        "Green": green,
        "Blue": blue,
    }
    if end_ms is not None:
        attrs["End"] = _seconds(end_ms)
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
    """Map Serato's 0-to-1 rating onto a Rekordbox star step.

    Rekordbox stores stars as 0, 51, 102, 153, 204, or 255. The Serato
    value is split into those six steps.

    Args:
        value: Stored rating, or None.

    Returns:
        One of 0, 51, 102, 153, 204, or 255.
    """
    steps = (0, 51, 102, 153, 204, 255)
    if value is None or value == "":
        return "0"
    try:
        number = float(cast(float, value))
    except (TypeError, ValueError):
        return "0"
    if not math.isfinite(number) or number <= 0:
        return "0"
    if number >= 1:
        return "255"
    index = min(5, int(number * 5 + 0.5))
    return str(steps[index])


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


def _track_element(
    row: Mapping[str, object],
    *,
    memory_cues: bool,
    hot_loops: bool,
    key_notation: str,
    stats: MutableMapping[str, int],
    unicode_names: list[str],
    folder_cache: dict[str, dict[str, str]],
) -> ElementTree.Element | None:
    """Build one TRACK element, including tempo and position marks.

    Args:
        row: Asset columns.
        memory_cues: True also writes each hot cue as a memory cue.
        hot_loops: True puts a saved loop on a free hot cue pad.
        key_notation: ``asis``, ``camelot``, or ``classical``.
        stats: Loss-report counters for this export.
        unicode_names: File names whose paths could not be encoded.
        folder_cache: Directory listings shared by every track in this export.

    Returns:
        The element, or None when the track has no path or the path cannot be encoded.
    """
    portable = _cell(row, "portable_id")
    if not isinstance(portable, str) or not portable.strip():
        _note(stats, "omitted")
        return None
    try:
        resolved = library.resolved_path(portable)
        if not resolved:
            _note(stats, "omitted")
            return None
        on_disk = Path(resolved).is_file()
        spelled = filesystem_path(resolved, folder_cache) if on_disk else resolved
        if not on_disk:
            _note(stats, "missing_file")
        location = location_uri(spelled)
        parsed, timing = _inspect_audio(spelled if on_disk else resolved, on_disk)
    except UnicodeError:
        unicode_names.append(_file_label(portable))
        return None
    shift = 0
    if on_disk and Path(spelled).suffix.lower() == ".mp3":
        case, shift = timing
        if case in {"B", "C"}:
            _note(stats, "mp3_shift")
        elif case in {"A", "D"}:
            _note(stats, "mp3_kept")
        else:
            _note(stats, "mp3_unread")
    warning = parsed.get("beatgrid_warning")
    if warning:
        _note(stats, "grid_unsupported")
    elif len(parsed["beatgrid"]) > 1:
        _note(stats, "grid_dynamic")
    tonality, key_status = notation_key(_text(row, "key"), key_notation)
    _note(stats, f"key_{key_status}")
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
        Tonality=tonality,
        Label=_text(row, "label"),
        Mix="",
    )
    for tempo in tempo_entries(parsed["beatgrid"], shift, stats):
        element.append(ElementTree.Element("TEMPO", tempo))
    marks = position_marks(
        parsed,
        shift,
        memory_cues=memory_cues,
        hot_loops=hot_loops,
        stats=stats,
    )
    if marks:
        _note(stats, "marks_written", len(marks))
    colour = _track_colour(_cell(row, "color"))
    if colour:
        element.set("Colour", colour)
    for mark in marks:
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
