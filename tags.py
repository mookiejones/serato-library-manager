"""Read Serato cue points, loops, flips, and beatgrids from audio files.

Serato stores these in GEOB frames (Markers2 and BeatGrid), not in the
library database. This module only reads. It does not rewrite audio files,
because replacing an ID3 tag can drop those frames.
"""

from __future__ import annotations

import base64
import binascii
import struct
from pathlib import Path
from typing import NotRequired, TypedDict


class Cue(TypedDict):
    """One Serato cue point."""

    index: int
    start_ms: int
    color: str | None
    name: str


class Loop(TypedDict):
    """One Serato loop."""

    index: int
    start_ms: int
    end_ms: int
    color: str | None
    locked: bool
    name: str


class Flip(TypedDict):
    """One Serato flip."""

    index: int
    enabled: bool
    name: str


class BeatMarker(TypedDict):
    """One beatgrid marker.

    Earlier markers store a beat count. The last marker stores BPM.
    """

    position: float
    bpm: NotRequired[float]
    beats: NotRequired[int]


class MarkerEntries(TypedDict):
    """Cues, loops, and flips from one Markers2 payload."""

    cues: list[Cue]
    loops: list[Loop]
    flips: list[Flip]


class SeratoTags(TypedDict):
    """Cue data read from an audio file.

    unavailable is set by the library layer when the file was not read.
    """

    cues: list[Cue]
    loops: list[Loop]
    flips: list[Flip]
    beatgrid: list[BeatMarker]
    found: bool
    unavailable: NotRequired[bool]


def read_serato_tags(path: str | None) -> SeratoTags:
    """Read Serato cue, loop, flip, and beatgrid data from an audio file.

    The read covers the first 2,000,000 bytes and, for a longer file, the last
    512,000 bytes. A missing path or an unreadable file returns an empty result.

    Args:
        path: Filesystem path of the audio file, or None.

    Returns:
        A dict with keys cues, loops, flips, beatgrid, and found.

    Example:
        >>> read_serato_tags(None)["found"]
        False
    """
    empty: SeratoTags = {"cues": [], "loops": [], "flips": [], "beatgrid": [], "found": False}
    if not path:
        return empty
    file = Path(path)
    try:
        if not file.is_file():
            return empty
        # Cues sit in the tag header. The tail covers ID3 written at the end of a WAV.
        size = file.stat().st_size
        with file.open("rb") as handle:
            head = handle.read(min(size, 2_000_000))
            tail = b""
            if size > 2_000_000:
                handle.seek(max(0, size - 512_000))
                tail = handle.read(512_000)
    except OSError:
        return empty

    frames = _geob_frames(head) + _geob_frames(tail)
    cues: list[Cue] = []
    loops: list[Loop] = []
    flips: list[Flip] = []
    beatgrid: list[BeatMarker] = []
    found = False
    for name, payload in frames:
        if name == "Serato Markers2":
            found = True
            parsed = _parse_markers2(payload)
            cues.extend(parsed["cues"])
            loops.extend(parsed["loops"])
            flips.extend(parsed["flips"])
        elif name == "Serato BeatGrid":
            found = True
            beatgrid = _parse_beatgrid(payload)
    cues.sort(key=lambda item: (item["index"], item["start_ms"]))
    loops.sort(key=lambda item: (item["index"], item["start_ms"]))
    return {"cues": cues, "loops": loops, "flips": flips, "beatgrid": beatgrid, "found": found}


def _geob_frames(blob: bytes) -> list[tuple[str, bytes]]:
    """Collect Serato GEOB payloads from an ID3 byte string.

    Args:
        blob: Bytes that may contain one or more ID3 tags.

    Returns:
        Pairs of GEOB description and payload.
    """
    frames: list[tuple[str, bytes]] = []
    cursor = 0
    while cursor < len(blob) - 10:
        offset = blob.find(b"ID3", cursor)
        if offset < 0:
            break
        cursor = offset + 3
        parsed = _parse_id3(blob, offset)
        if parsed is None:
            continue
        frames.extend(parsed)
        cursor = offset + 10
    return frames


def _synchsafe(raw: bytes) -> int:
    """Decode a synchsafe integer used by an ID3 tag size.

    Args:
        raw: Four size bytes. The high bit of each byte is ignored.

    Returns:
        The decoded integer.
    """
    value = 0
    for byte in raw:
        value = (value << 7) | (byte & 0x7F)
    return value


def _parse_id3(blob: bytes, offset: int) -> list[tuple[str, bytes]] | None:
    """Parse one ID3v2.3 or ID3v2.4 tag and return its GEOB frames.

    Args:
        blob: The buffer that contains the tag.
        offset: Index of the ID3 header.

    Returns:
        GEOB name and payload pairs, or None when the header is not a supported tag.
    """
    if blob[offset:offset + 3] != b"ID3":
        return None
    if offset + 10 > len(blob):
        return None
    version = blob[offset + 3]
    if version not in (3, 4):
        return None
    tag_size = _synchsafe(blob[offset + 6:offset + 10])
    start = offset + 10
    end = min(len(blob), start + tag_size)
    if end <= start:
        return None
    frames: list[tuple[str, bytes]] = []
    pos = start
    while pos + 10 <= end:
        frame_id = blob[pos:pos + 4]
        if frame_id == b"\x00\x00\x00\x00" or frame_id[0] == 0:
            break
        if version == 4:
            frame_size = _synchsafe(blob[pos + 4:pos + 8])
        else:
            frame_size = int.from_bytes(blob[pos + 4:pos + 8], "big")
        body = blob[pos + 10:pos + 10 + frame_size]
        pos += 10 + frame_size
        if frame_id != b"GEOB" or not body:
            continue
        name, payload = _geob_body(body)
        if name:
            frames.append((name, payload))
    return frames


def _geob_body(body: bytes) -> tuple[str, bytes]:
    """Split a GEOB frame body into its description and data.

    Args:
        body: Frame bytes after the GEOB header. The first byte is the text encoding.

    Returns:
        The frame description and the remaining payload.
    """
    encoding = body[0]
    rest = body[1:]
    _, rest = _split_text(0, rest)  # MIME is always Latin-1
    _, rest = _split_text(encoding, rest)  # filename
    name, payload = _split_text(encoding, rest)
    return name, payload


def _split_text(encoding: int, buf: bytes) -> tuple[str, bytes]:
    """Split one encoded text field from the front of a buffer.

    Args:
        encoding: ID3 text encoding byte.
        buf: Remaining frame bytes.

    Returns:
        The decoded text and the unused tail.
    """
    if encoding in (1, 2):
        width = 2
        index = 0
        if buf.startswith((b"\xff\xfe", b"\xfe\xff")):
            index = 2
        while index + 1 < len(buf):
            if buf[index] == 0 and buf[index + 1] == 0 and (index % width == 0):
                return _decode_text(encoding, buf[:index]), buf[index + 2:]
            index += 2
        return _decode_text(encoding, buf), b""
    text, _, rest = buf.partition(b"\x00")
    return _decode_text(encoding, text), rest


def _decode_text(encoding: int, raw: bytes) -> str:
    """Decode an ID3 text field.

    Args:
        encoding: 0 for Latin-1, 1 for UTF-16, 2 for UTF-16-BE, otherwise UTF-8.
        raw: Encoded field bytes.

    Returns:
        The decoded text with trailing NUL bytes removed.
    """
    if encoding == 0:
        return raw.decode("latin-1", "replace").rstrip("\x00")
    if encoding == 1:
        return raw.decode("utf-16", "replace").rstrip("\x00")
    if encoding == 2:
        return raw.decode("utf-16-be", "replace").rstrip("\x00")
    return raw.decode("utf-8", "replace").rstrip("\x00")


def _parse_markers2(payload: bytes) -> MarkerEntries:
    """Parse a Serato Markers2 payload into cues, loops, and flips.

    Args:
        payload: Decoded GEOB data. A leading 01 01 byte pair marks the base64 body.

    Returns:
        A dict with keys cues, loops, and flips. An unrecognized payload is empty.
    """
    result: MarkerEntries = {"cues": [], "loops": [], "flips": []}
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
    pos = 0
    while pos < len(decoded):
        end = decoded.find(b"\x00", pos)
        if end < 0 or end + 5 > len(decoded):
            break
        kind = decoded[pos:end].decode("ascii", "replace")
        length = int.from_bytes(decoded[end + 1:end + 5], "big")
        start = end + 5
        blob = decoded[start:start + length]
        pos = start + length
        if len(blob) < length:
            break
        if kind == "CUE":
            cue = _parse_cue(blob)
            if cue:
                result["cues"].append(cue)
        elif kind == "LOOP":
            loop = _parse_loop(blob)
            if loop:
                result["loops"].append(loop)
        elif kind == "FLIP":
            flip = _parse_flip(blob)
            if flip:
                result["flips"].append(flip)
    return result


def _color3(raw: bytes) -> str | None:
    """Format three color bytes as a CSS hex color.

    Args:
        raw: At least three bytes of red, green, and blue.

    Returns:
        A string such as #CC0000, or None when raw is shorter than three bytes.
    """
    if len(raw) < 3:
        return None
    return f"#{raw[0]:02X}{raw[1]:02X}{raw[2]:02X}"


def _parse_cue(blob: bytes) -> Cue | None:
    """Parse one CUE entry.

    Args:
        blob: Bytes of a single CUE record.

    Returns:
        Index, start time in milliseconds, color, and name. None when the record is short.
    """
    if len(blob) < 13:
        return None
    name = blob[12:].split(b"\x00", 1)[0].decode("utf-8", "replace")
    return {
        "index": blob[1],
        "start_ms": int.from_bytes(blob[2:6], "big"),
        "color": _color3(blob[7:10]),
        "name": name,
    }


def _parse_loop(blob: bytes) -> Loop | None:
    """Parse one LOOP entry.

    Args:
        blob: Bytes of a single LOOP record.

    Returns:
        Index, start, end, color, locked flag, and name. None when the record is short.
    """
    if len(blob) < 20:
        return None
    color = blob[14:18]
    name = blob[20:].split(b"\x00", 1)[0].decode("utf-8", "replace") if len(blob) > 20 else ""
    return {
        "index": blob[1],
        "start_ms": int.from_bytes(blob[2:6], "big"),
        "end_ms": int.from_bytes(blob[6:10], "big"),
        "color": _color3(color[1:]) if len(color) == 4 else _color3(color),
        "locked": bool(blob[19]),
        "name": name,
    }


def _parse_flip(blob: bytes) -> Flip | None:
    """Parse one FLIP entry.

    Args:
        blob: Bytes of a single FLIP record.

    Returns:
        Index, enabled flag, and name. None when the record is short.
    """
    if len(blob) < 4:
        return None
    name_end = blob.find(b"\x00", 3)
    if name_end < 0:
        name = blob[3:].decode("utf-8", "replace")
    else:
        name = blob[3:name_end].decode("utf-8", "replace")
    return {"index": blob[1], "enabled": bool(blob[2]), "name": name}


def _parse_beatgrid(payload: bytes) -> list[BeatMarker]:
    """Parse a Serato BeatGrid payload.

    Args:
        payload: BeatGrid bytes. Version byte 1 is accepted. More than 4096 markers is rejected.

    Returns:
        Marker dicts. Earlier markers store a beat count. The last marker stores BPM. A payload shorter than the declared marker count is empty.
    """
    if len(payload) < 6 or payload[0] != 1:
        return []
    count = int.from_bytes(payload[2:6], "big")
    if count <= 0 or count > 4096:
        return []
    pos = 6
    markers: list[BeatMarker] = []
    for index in range(count):
        if pos + 8 > len(payload):
            return []
        position = struct.unpack(">f", payload[pos:pos + 4])[0]
        pos += 4
        if index == count - 1:
            bpm = struct.unpack(">f", payload[pos:pos + 4])[0]
            pos += 4
            markers.append({"position": round(position, 3), "bpm": round(bpm, 2)})
        else:
            beats = int.from_bytes(payload[pos:pos + 4], "big")
            pos += 4
            markers.append({"position": round(position, 3), "beats": beats})
    return markers
