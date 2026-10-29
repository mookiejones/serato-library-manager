"""Read Serato crates, database V2, and tag carriers from the published spec.

This module is the fixture reader. It follows the Holzhaus notes and does
not import the application, so a disagreement with ``tags.py`` is visible
in the tests instead of being hidden by one shared implementation.

Citations:

- https://github.com/Holzhaus/mixxx/wiki/Serato-Database-Format
- https://github.com/Holzhaus/serato-tags/blob/master/scripts/database_v2.py
- https://github.com/Holzhaus/serato-tags/blob/main/docs/serato_markers2.md
- https://github.com/Holzhaus/serato-tags/blob/main/docs/serato_beatgrid.md
- https://github.com/Holzhaus/serato-tags/blob/main/docs/fileformats.md
"""

from __future__ import annotations

import base64
import binascii
import struct
from pathlib import Path


CRATE_VERSION = "1.0/Serato ScratchLive Crate"
DATABASE_VERSION = "2.0/Serato Scratch LIVE Database"


def parse_chunks(data: bytes) -> tuple[list[dict[str, object]], str | None]:
    """Parse a crate or database V2 byte string.

    Args:
        data: Concatenated records. Each record is a 4-byte ASCII tag, a
            big-endian length, and that many bytes.

    Returns:
        The records that ended inside ``data``, and an error code when a
        header or body is cut off. Complete records before the cut are kept.
    """
    records: list[dict[str, object]] = []
    pos = 0
    error: str | None = None
    while pos < len(data):
        if pos + 8 > len(data):
            error = "truncated-header"
            break
        tag = data[pos : pos + 4].decode("ascii", "replace")
        length = int.from_bytes(data[pos + 4 : pos + 8], "big")
        start = pos + 8
        end = start + length
        if end > len(data):
            error = "truncated-body"
            break
        payload = data[start:end]
        pos = end
        records.append({"tag": tag, "value": _value(tag, payload)})
    return records, error


def _value(tag: str, payload: bytes) -> object:
    """Decode one record payload from its tag prefix.

    Args:
        tag: Four-character tag. ``vrsn`` is text even though it does not
            start with ``t``.
        payload: The length-delimited bytes.

    Returns:
        Nested records, text, an integer, a bool, or the raw bytes.
    """
    kind = "t" if tag == "vrsn" else tag[:1]
    if kind in {"o", "r"}:
        nested, _error = parse_chunks(payload)
        return nested
    if kind in {"t", "p"}:
        return payload.decode("utf-16-be")
    if kind == "u":
        return int.from_bytes(payload, "big") if payload else 0
    if kind == "b":
        return bool(payload[:1] and payload[0])
    if kind == "s":
        return int.from_bytes(payload, "big") if payload else 0
    return payload


def chunk_tracks(data: bytes) -> tuple[str | None, list[dict[str, object]], str | None]:
    """Return the version string and the track rows from a chunk file.

    Args:
        data: Crate or database V2 bytes.

    Returns:
        The ``vrsn`` text, one dict per ``otrk``, and a truncation error.
        A track with no path field has ``path`` None. The row is still
        returned.
    """
    records, error = parse_chunks(data)
    version: str | None = None
    tracks: list[dict[str, object]] = []
    for record in records:
        if record["tag"] == "vrsn" and isinstance(record["value"], str):
            version = record["value"]
        elif record["tag"] == "otrk" and isinstance(record["value"], list):
            tracks.append(_track_row(record["value"]))
    return version, tracks, error


def _track_row(fields: list[dict[str, object]]) -> dict[str, object]:
    """Flatten one ``otrk`` into a dict.

    Args:
        fields: Nested records.

    Returns:
        Path, title, artist, type, bpm, and the missing flag when present.
    """
    row: dict[str, object] = {"path": None, "missing": False}
    for field in fields:
        tag = field["tag"]
        value = field["value"]
        if tag in {"ptrk", "pfil"} and isinstance(value, str):
            row["path"] = value
        elif tag == "tsng" and isinstance(value, str):
            row["title"] = value
        elif tag == "tart" and isinstance(value, str):
            row["artist"] = value
        elif tag == "ttyp" and isinstance(value, str):
            row["type"] = value
        elif tag == "tbpm" and isinstance(value, str):
            row["bpm"] = value
        elif tag == "bmis":
            row["missing"] = bool(value)
    return row


def crate_name(filename: str) -> tuple[list[str], str]:
    """Split a crate filename into parent names and its own name.

    The crate record does not store the name. Scratch Live writes the
    display name in the filename and joins a nested crate to its parents
    with ``%%``.

    Args:
        filename: File name such as ``House%%Café.crate``.

    Returns:
        Parent names and the leaf name.
    """
    stem = filename[:-6] if filename.endswith(".crate") else filename
    parts = stem.split("%%")
    return parts[:-1], parts[-1]


def normalize_path(stored: str) -> str:
    """Return a crate path with forward slashes.

    Args:
        stored: Path text from ``ptrk`` or ``pfil``.

    Returns:
        The same path using ``/`` separators and no leading slash.
    """
    return stored.replace("\\", "/").lstrip("/")


def availability(stored: str | None, volume_root: Path | None) -> str:
    """Classify a crate path against a volume that may not be mounted.

    Args:
        stored: Path relative to the volume root, or None when the crate
            record has no path.
        volume_root: Directory that would be the mounted volume. None, or
            a path that is not a directory, means the drive is unplugged.

    Returns:
        ``present`` when the file is on a mounted volume, otherwise
        ``unavailable``. This never reports the row as deleted.
    """
    if volume_root is None or not volume_root.is_dir() or not isinstance(stored, str) or stored == "":
        return "unavailable"
    candidate = volume_root / normalize_path(stored)
    try:
        if candidate.is_file():
            return "present"
    except OSError:
        return "unavailable"
    return "unavailable"


def _rgb(raw: bytes) -> str | None:
    """Format three color bytes as ``#RRGGBB``.

    Args:
        raw: Red, green, and blue.

    Returns:
        The hex color, or None when fewer than three bytes are present.
    """
    if len(raw) < 3:
        return None
    return f"#{raw[0]:02X}{raw[1]:02X}{raw[2]:02X}"


def parse_markers2(payload: bytes) -> dict[str, object]:
    """Decode a Markers2 GEOB payload.

    The layout is the Markers2 note: a ``01 01`` header, base64 with a
    linefeed every 72 characters, null padding, then entries. A base64
    length of 4n+1 gains a trailing ``A`` before padding, as that note
    describes.

    Args:
        payload: Bytes stored in the GEOB frame or, after the FLAC/MP4
            envelope is removed, the same Markers2 bytes.

    Returns:
        Cues, loops, flips, the track color, and the beatgrid lock flag.
        An unrecognized payload has empty lists.
    """
    result: dict[str, object] = {
        "cues": [],
        "loops": [],
        "flips": [],
        "track_color": None,
        "beatgrid_locked": None,
    }
    if len(payload) < 2 or payload[:2] != b"\x01\x01":
        return result
    encoded = payload[2:].replace(b"\n", b"").replace(b"\x00", b"")
    if not encoded:
        return result
    while len(encoded) % 4 == 1:
        encoded += b"A"
    pad = (-len(encoded)) % 4
    try:
        decoded = base64.b64decode(encoded + (b"=" * pad), validate=False)
    except binascii.Error:
        return result
    if decoded.startswith(b"\x01\x01"):
        decoded = decoded[2:]
    cues: list[dict[str, object]] = []
    loops: list[dict[str, object]] = []
    flips: list[dict[str, object]] = []
    pos = 0
    while pos < len(decoded):
        if decoded[pos] == 0:
            break
        end = decoded.find(b"\x00", pos)
        if end < 0 or end + 5 > len(decoded):
            break
        kind = decoded[pos:end].decode("ascii", "replace")
        length = int.from_bytes(decoded[end + 1 : end + 5], "big")
        start = end + 5
        blob = decoded[start : start + length]
        if len(blob) < length:
            break
        pos = start + length
        if kind == "CUE" and len(blob) >= 13:
            cues.append(
                {
                    "index": blob[1],
                    "start_ms": int.from_bytes(blob[2:6], "big"),
                    "color": _rgb(blob[7:10]),
                    "name": blob[12:].split(b"\x00", 1)[0].decode("utf-8", "replace"),
                }
            )
        elif kind == "LOOP" and len(blob) >= 20:
            loops.append(
                {
                    "index": blob[1],
                    "start_ms": int.from_bytes(blob[2:6], "big"),
                    "end_ms": int.from_bytes(blob[6:10], "big"),
                    "color": _rgb(blob[15:18]),
                    "locked": bool(blob[19]),
                    "name": blob[20:].split(b"\x00", 1)[0].decode("utf-8", "replace"),
                }
            )
        elif kind == "FLIP" and len(blob) >= 4:
            name_end = blob.find(b"\x00", 3)
            name = blob[3:] if name_end < 0 else blob[3:name_end]
            flips.append({"index": blob[1], "enabled": bool(blob[2]), "name": name.decode("utf-8", "replace")})
        elif kind == "COLOR" and len(blob) >= 4:
            result["track_color"] = _rgb(blob[1:4])
        elif kind == "BPMLOCK" and blob:
            result["beatgrid_locked"] = bool(blob[0])
    cues.sort(key=lambda item: (int(item["index"]), int(item["start_ms"])))
    loops.sort(key=lambda item: (int(item["index"]), int(item["start_ms"])))
    result["cues"] = cues
    result["loops"] = loops
    result["flips"] = flips
    return result


def parse_beatgrid(payload: bytes) -> dict[str, object]:
    """Decode a BeatGrid payload, including its footer byte.

    Args:
        payload: Header, markers, and the final footer byte from the
            BeatGrid note.

    Returns:
        ``markers`` and ``footer``. A short or unsupported payload has no
        markers. Earlier markers carry ``beats``. The last marker carries
        ``bpm``.
    """
    empty: dict[str, object] = {"markers": [], "footer": None}
    if len(payload) < 6 or payload[0] != 1:
        return empty
    count = int.from_bytes(payload[2:6], "big")
    if count <= 0 or 6 + count * 8 > len(payload):
        return empty
    markers: list[dict[str, float | int]] = []
    pos = 6
    for index in range(count):
        position = struct.unpack(">f", payload[pos : pos + 4])[0]
        pos += 4
        if index == count - 1:
            bpm = struct.unpack(">f", payload[pos : pos + 4])[0]
            pos += 4
            markers.append({"position": round(position, 3), "bpm": round(bpm, 2)})
        else:
            beats = int.from_bytes(payload[pos : pos + 4], "big")
            pos += 4
            markers.append({"position": round(position, 3), "beats": beats})
    footer = payload[pos] if pos < len(payload) else None
    return {"markers": markers, "footer": footer}


def geob_frames(blob: bytes) -> list[tuple[str, bytes]]:
    """Collect GEOB description and payload pairs from ID3 tags in ``blob``.

    Args:
        blob: An MP3 or AIFF byte string. ID3v2.3 frame sizes are plain
            big-endian. ID3v2.4 frame sizes are synchsafe.

    Returns:
        Frames whose description is non-empty. A truncated header is skipped.
    """
    found: list[tuple[str, bytes]] = []
    cursor = 0
    while cursor < len(blob) - 10:
        offset = blob.find(b"ID3", cursor)
        if offset < 0:
            break
        cursor = offset + 3
        parsed = _id3_geob(blob, offset)
        if parsed:
            found.extend(parsed)
    return found


def _synchsafe(raw: bytes) -> int:
    """Decode a synchsafe integer.

    Args:
        raw: Four size bytes.

    Returns:
        The integer with the high bit of each byte dropped.
    """
    value = 0
    for byte in raw:
        value = (value << 7) | (byte & 0x7F)
    return value


def _id3_geob(blob: bytes, offset: int) -> list[tuple[str, bytes]] | None:
    """Return GEOB frames from one ID3 header.

    Args:
        blob: Buffer that may contain the tag.
        offset: Index of the ``ID3`` bytes.

    Returns:
        Description and payload pairs, or None when this is not an ID3v2.3
        or ID3v2.4 tag.
    """
    if blob[offset : offset + 3] != b"ID3" or offset + 10 > len(blob):
        return None
    version = blob[offset + 3]
    if version not in (3, 4):
        return None
    tag_size = _synchsafe(blob[offset + 6 : offset + 10])
    start = offset + 10
    end = min(len(blob), start + tag_size)
    frames: list[tuple[str, bytes]] = []
    pos = start
    while pos + 10 <= end:
        frame_id = blob[pos : pos + 4]
        if frame_id == b"\x00\x00\x00\x00" or frame_id[0] == 0:
            break
        if version == 4:
            frame_size = _synchsafe(blob[pos + 4 : pos + 8])
        else:
            frame_size = int.from_bytes(blob[pos + 4 : pos + 8], "big")
        body = blob[pos + 10 : pos + 10 + frame_size]
        pos += 10 + frame_size
        if frame_id != b"GEOB" or not body:
            continue
        name, payload = _geob_body(body)
        if name:
            frames.append((name, payload))
    return frames


def _geob_body(body: bytes) -> tuple[str, bytes]:
    """Split a GEOB body into description and data.

    Args:
        body: Frame bytes after the 10-byte header.

    Returns:
        The description and the encapsulated object.
    """
    encoding = body[0]
    rest = body[1:]
    _mime, rest = _split_text(0, rest)
    _filename, rest = _split_text(encoding, rest)
    name, payload = _split_text(encoding, rest)
    return name, payload


def _split_text(encoding: int, buf: bytes) -> tuple[str, bytes]:
    """Split one terminated text field.

    Args:
        encoding: ID3 encoding byte.
        buf: Remaining frame bytes.

    Returns:
        The text and the unused tail.
    """
    if encoding in (1, 2):
        index = 2 if buf.startswith((b"\xff\xfe", b"\xfe\xff")) else 0
        while index + 1 < len(buf):
            if buf[index] == 0 and buf[index + 1] == 0:
                return buf[:index].decode("utf-16-be" if encoding == 2 else "utf-16", "replace"), buf[index + 2 :]
            index += 2
        return "", b""
    text, _, rest = buf.partition(b"\x00")
    return text.decode("latin-1", "replace"), rest


def flac_comments(data: bytes) -> dict[str, str]:
    """Read Vorbis comments from a FLAC byte string.

    Args:
        data: A file that starts with ``fLaC``.

    Returns:
        Comment names and values. Serato keys are ``SERATO_MARKERS_V2`` and
        ``SERATO_BEATGRID``.
    """
    if not data.startswith(b"fLaC"):
        return {}
    pos = 4
    while pos + 4 <= len(data):
        header = data[pos]
        length = int.from_bytes(data[pos + 1 : pos + 4], "big")
        block = data[pos + 4 : pos + 4 + length]
        pos += 4 + length
        if header & 0x7F == 4:
            return _vorbis_comments(block)
        if header & 0x80:
            break
    return {}


def _vorbis_comments(block: bytes) -> dict[str, str]:
    """Parse one Vorbis comment packet.

    Args:
        block: Vendor string and user comments, little-endian lengths.

    Returns:
        The user comments. The vendor string is not included.
    """
    if len(block) < 8:
        return {}
    vendor_len = int.from_bytes(block[:4], "little")
    pos = 4 + vendor_len
    if pos + 4 > len(block):
        return {}
    count = int.from_bytes(block[pos : pos + 4], "little")
    pos += 4
    comments: dict[str, str] = {}
    for _ in range(count):
        if pos + 4 > len(block):
            break
        size = int.from_bytes(block[pos : pos + 4], "little")
        pos += 4
        raw = block[pos : pos + size]
        pos += size
        text = raw.decode("utf-8", "replace")
        key, sep, value = text.partition("=")
        if sep:
            comments[key] = value
    return comments


def mp4_freeform(data: bytes) -> dict[str, bytes]:
    """Read ``----:com.serato.dj`` data atoms from an MP4 byte string.

    Args:
        data: An M4A or MP4 file.

    Returns:
        Atom names (``markersv2``, ``beatgrid``) and the raw data payload.
    """
    found: dict[str, bytes] = {}
    for typ, start, end in _atoms(data, 0, len(data)):
        if typ != b"moov":
            continue
        for child, cstart, cend in _atoms(data, start, end):
            if child != b"udta":
                continue
            for meta_name, mstart, mend in _atoms(data, cstart, cend):
                if meta_name != b"meta":
                    continue
                # meta is a full box: 4 bytes of version and flags, then children.
                ilst_start = mstart + 4
                for ilst_name, istart, iend in _atoms(data, ilst_start, mend):
                    if ilst_name != b"ilst":
                        continue
                    for free_name, fstart, fend in _atoms(data, istart, iend):
                        if free_name != b"----":
                            continue
                        name, payload = _freeform(data[fstart:fend])
                        if name:
                            found[name] = payload
    return found


def _atoms(data: bytes, start: int, end: int) -> list[tuple[bytes, int, int]]:
    """List atoms in a range.

    Args:
        data: File bytes.
        start: First byte of the first atom.
        end: End of the parent.

    Returns:
        Type, payload start, and payload end for each atom that fits.
    """
    atoms: list[tuple[bytes, int, int]] = []
    pos = start
    while pos + 8 <= end:
        size = int.from_bytes(data[pos : pos + 4], "big")
        if size < 8 or pos + size > end:
            break
        atoms.append((data[pos + 4 : pos + 8], pos + 8, pos + size))
        pos += size
    return atoms


def _freeform(body: bytes) -> tuple[str | None, bytes]:
    """Read one ``----`` atom's name and data.

    Args:
        body: Children of the freeform atom.

    Returns:
        The name and the data payload. The mean must be ``com.serato.dj``.
        Other means are ignored.
    """
    mean = ""
    name = ""
    payload = b""
    for typ, start, end in _atoms(body, 0, len(body)):
        chunk = body[start:end]
        if typ == b"mean" and len(chunk) >= 4:
            mean = chunk[4:].decode("latin-1", "replace")
        elif typ == b"name" and len(chunk) >= 4:
            name = chunk[4:].decode("latin-1", "replace").strip("\x00")
        elif typ == b"data" and len(chunk) >= 8:
            payload = chunk[8:]
    if mean != "com.serato.dj" or not name:
        return None, b""
    return name, payload


def decode_envelope(text: str) -> tuple[str, bytes] | None:
    """Decode a FLAC or MP4 Serato field.

    The fileformats note stores base64, without padding, of a MIME type,
    an extra null, a field name, and the payload. Markers fields also
    insert a linefeed every 72 characters.

    Args:
        text: The comment or atom text.

    Returns:
        The inner field name and the payload bytes, or None when the
        envelope is not there.
    """
    compact = "".join(text.split())
    if not compact:
        return None
    while len(compact) % 4 == 1:
        compact += "A"
    pad = (-len(compact)) % 4
    try:
        raw = base64.b64decode(compact + ("=" * pad), validate=False)
    except binascii.Error:
        return None
    mime, sep, rest = raw.partition(b"\x00")
    if mime != b"application/octet-stream" or not sep or not rest.startswith(b"\x00"):
        return None
    rest = rest[1:]
    name, sep, payload = rest.partition(b"\x00")
    if not sep:
        return None
    return name.decode("ascii", "replace"), payload


def tags_from_audio(path: Path) -> dict[str, object] | None:
    """Read Markers2 and BeatGrid from a fixture file using the spec.

    Args:
        path: MP3, AIFF, FLAC, or M4A fixture.

    Returns:
        Cues, loops, flips, color, lock, beatgrid markers, and footer.
        None when the file has no Serato payload of either kind.
    """
    data = path.read_bytes()
    markers_payload: bytes | None = None
    grid_payload: bytes | None = None
    suffix = path.suffix.lower()
    if suffix in {".mp3", ".aiff", ".aif"}:
        for name, payload in geob_frames(data):
            if name == "Serato Markers2":
                markers_payload = payload
            elif name == "Serato BeatGrid":
                grid_payload = payload
    elif suffix == ".flac":
        comments = flac_comments(data)
        markers_payload = _envelope_payload(comments.get("SERATO_MARKERS_V2"))
        grid_payload = _envelope_payload(comments.get("SERATO_BEATGRID"))
    elif suffix in {".m4a", ".mp4"}:
        atoms = mp4_freeform(data)
        markers_payload = _envelope_payload(_latin(atoms.get("markersv2")))
        grid_payload = _envelope_payload(_latin(atoms.get("beatgrid")))
    if markers_payload is None and grid_payload is None:
        return None
    parsed = parse_markers2(markers_payload or b"")
    grid = parse_beatgrid(grid_payload or b"")
    parsed["beatgrid"] = grid["markers"]
    parsed["footer"] = grid["footer"]
    return parsed


def _envelope_payload(text: str | None) -> bytes | None:
    """Return the inner payload of one envelope field.

    Args:
        text: Base64 field text, or None.

    Returns:
        The decoded payload, or None when the field is absent.
    """
    if text is None:
        return None
    decoded = decode_envelope(text)
    if decoded is None:
        return None
    return decoded[1]


def _latin(raw: bytes | None) -> str | None:
    """Decode an MP4 data atom as Latin-1 text.

    Args:
        raw: Atom bytes, or None.

    Returns:
        The text, or None when there is no atom.
    """
    if raw is None:
        return None
    return raw.decode("latin-1")
