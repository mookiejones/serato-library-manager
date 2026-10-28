"""Read Serato cue points, loops, flips, and beatgrids from audio files.

Serato stores these in GEOB frames (Markers2 and BeatGrid), not in the
library database. Reading never rewrites a file. ``copy_serato_geob``
copies existing Serato GEOB frames onto another file when that file has a
plain ID3v2.3 tag, or when it is an MP3 with no tag yet. Other frames and
the audio bytes stay as they are. Any other layout is left untouched.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
import shutil
import struct
import tempfile
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
    beatgrid_warning: NotRequired[str | None]


class CueCopy(TypedDict):
    """Result of copying Serato GEOB frames onto another file.

    status is copied, kept, skipped, unsupported, or failed. detail is a
    short sentence for the page. It does not include a path.
    """

    status: str
    detail: str


def read_serato_tags(path: str | None) -> SeratoTags:
    """Read Serato cue, loop, flip, and beatgrid data from an audio file.

    The read covers the first 2,000,000 bytes and, for a longer file, the last
    512,000 bytes. A missing path or an unreadable file returns an empty result.

    Args:
        path: Filesystem path of the audio file, or None.

    Returns:
        A dict with keys cues, loops, flips, beatgrid, beatgrid_warning, and found.
        beatgrid_warning is a sentence when a BeatGrid frame was present and
        could not be read, including a version this parser does not know
        and a grid with more than 4096 markers.

    Example:
        >>> read_serato_tags(None)["found"]
        False
    """
    empty: SeratoTags = {
        "cues": [],
        "loops": [],
        "flips": [],
        "beatgrid": [],
        "beatgrid_warning": None,
        "found": False,
    }
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

    return serato_tags_from_regions(head, tail)


def serato_tags_from_regions(head: bytes, tail: bytes = b"") -> SeratoTags:
    """Parse Serato frames from bytes already read from a file.

    ``read_serato_tags`` uses this after it has opened the file. An export
    can open the file once, keep those bytes, and parse them here.

    Args:
        head: The first bytes of the file.
        tail: The last bytes. Used when an ID3 tag sits at the end of a WAV.

    Returns:
        The same dict ``read_serato_tags`` returns.
    """
    frames = _geob_frames(head) + _geob_frames(tail)
    cues: list[Cue] = []
    loops: list[Loop] = []
    flips: list[Flip] = []
    beatgrid: list[BeatMarker] = []
    beatgrid_warning: str | None = None
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
            issue = beatgrid_issue(payload)
            if issue:
                beatgrid = []
                beatgrid_warning = issue
            else:
                beatgrid = _parse_beatgrid(payload)
                beatgrid_warning = None
    cues.sort(key=lambda item: (item["index"], item["start_ms"]))
    loops.sort(key=lambda item: (item["index"], item["start_ms"]))
    return {
        "cues": cues,
        "loops": loops,
        "flips": flips,
        "beatgrid": beatgrid,
        "beatgrid_warning": beatgrid_warning,
        "found": found,
    }


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
        # ID3v2.4 stores the frame size as a synchsafe integer. ID3v2.3
        # stores the same four bytes as a plain big-endian length.
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
    # Serato omits base64 padding. A length of 4n+1 is not a valid group,
    # so one alphabet character is added before the standard '=' pad.
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
        # Each entry is a NUL-terminated name, a 4-byte big-endian length,
        # then that many payload bytes (CUE, LOOP, or FLIP).
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
    # Byte 1 is the cue index, bytes 2-5 the start in milliseconds,
    # bytes 7-9 the RGB color, and the UTF-8 name begins at byte 12.
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
    # Bytes 2-5 and 6-9 are start and end in milliseconds. The color
    # field is four bytes beginning at offset 14; the first byte is
    # skipped so the remaining three are RGB. Byte 19 is the lock flag.
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


def beatgrid_issue(payload: bytes) -> str | None:
    """Explain why a BeatGrid payload cannot be read.

    Args:
        payload: BeatGrid bytes, including the version byte.

    Returns:
        A short sentence when the payload is not a supported grid.
        None when ``_parse_beatgrid`` can read it. Version byte 1 with
        at most 4096 markers is supported, including a Serato 5.0 grid
        that stores one marker per tempo change.
    """
    if len(payload) < 6:
        return "The beatgrid is too short to read."
    if payload[0] != 1:
        return "That beatgrid version is not supported."
    count = int.from_bytes(payload[2:6], "big")
    if count <= 0:
        return "The beatgrid has no markers."
    if count > 4096:
        return "The beatgrid has more than 4096 markers."
    if 6 + count * 8 > len(payload):
        return "The beatgrid is shorter than its marker count."
    return None


def _parse_beatgrid(payload: bytes) -> list[BeatMarker]:
    """Parse a Serato BeatGrid payload.

    Args:
        payload: BeatGrid bytes. Version byte 1 is accepted. More than 4096 markers is rejected.

    Returns:
        Marker dicts. Earlier markers store a beat count. The last marker stores BPM, rounded to two decimal places. Positions keep the stored float so a later BPM calculation is not based on a three-decimal rounding. A payload shorter than the declared marker count is empty.
    """
    # Version byte 1 is the only layout this reader accepts. The marker
    # count is a big-endian integer at bytes 2-5. Byte 1 is unused.
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
        # Every marker stores a position in seconds. Earlier markers then
        # store a beat count. Only the last marker stores BPM.
        if index == count - 1:
            bpm = struct.unpack(">f", payload[pos:pos + 4])[0]
            pos += 4
            markers.append({"position": position, "bpm": round(bpm, 2)})
        else:
            beats = int.from_bytes(payload[pos:pos + 4], "big")
            pos += 4
            markers.append({"position": position, "beats": beats})
    return markers


_TAG_LIMIT = 16_000_000
_UNSYNC = 0x80
_EXTENDED = 0x40
_V23_COMPRESSED = 0x80
_V23_ENCRYPTED = 0x40
_COPIED = "Cue points were copied onto the new file."
_KEPT = "The new file already has Serato cue points, so they were left as they are."
_SKIPPED = "The old file has no Serato cue points to copy."
_UNSUPPORTED = "Cue points stay on the old file. This file type cannot take a Serato tag safely."
_FAILED = "Cue points could not be copied. The new file was left unchanged."


def plan_serato_geob(source: str | Path | None, dest: str | Path | None) -> CueCopy:
    """Decide whether Serato frames can be copied without rewriting other tags.

    The check only reads. A plain ID3v2.3 tag can take the frames. An MP3
    with no tag yet can take a new ID3v2.3 tag. A file that already has
    Serato frames is left alone. Every other layout is refused.

    Args:
        source: Audio file that already has the cue points.
        dest: Audio file that should receive them.

    Returns:
        A status of copied (meaning the copy is safe to try), kept,
        skipped, or unsupported, plus a sentence that does not name a path.
    """
    if not source or not dest:
        return {"status": "unsupported", "detail": _UNSUPPORTED}
    src = Path(source)
    dst = Path(dest)
    try:
        if not src.is_file() or src.is_symlink() or not dst.is_file() or dst.is_symlink():
            return {"status": "unsupported", "detail": _UNSUPPORTED}
        if src.resolve() == dst.resolve():
            return {"status": "skipped", "detail": _SKIPPED}
        source_tag = _read_id3v23(src)
        if source_tag is None:
            return {"status": "unsupported", "detail": _UNSUPPORTED}
        serato = [frame for frame in source_tag["frames"] if _serato_frame(frame)]
        if any(_unsafe_frame(frame) for frame in serato):
            return {"status": "unsupported", "detail": _UNSUPPORTED}
        if not serato:
            return {"status": "skipped", "detail": _SKIPPED}
        dest_tag = _read_id3v23(dst)
        if dest_tag is None:
            if _can_prepend_mp3(dst):
                return {"status": "copied", "detail": _COPIED}
            return {"status": "unsupported", "detail": _UNSUPPORTED}
        if any(_serato_frame(frame) for frame in dest_tag["frames"]):
            return {"status": "kept", "detail": _KEPT}
        return {"status": "copied", "detail": _COPIED}
    except OSError:
        return {"status": "unsupported", "detail": _UNSUPPORTED}


def copy_serato_geob(source: str | Path, dest: str | Path) -> CueCopy:
    """Copy Serato GEOB frames from source onto dest when that is safe.

    Other ID3 frames are copied as raw bytes. The audio after the tag is
    streamed unchanged. The destination is replaced only after the new
    file is written beside it. A failed check restores the previous bytes.

    Args:
        source: Audio file that already has the cue points.
        dest: Audio file that should receive them.

    Returns:
        The same status vocabulary as ``plan_serato_geob``. failed means
        the destination was restored.
    """
    decision = plan_serato_geob(source, dest)
    if decision["status"] != "copied":
        return decision
    dst = Path(dest)
    try:
        written = _write_copied_tag(Path(source), dst)
    except OSError:
        return {"status": "failed", "detail": _FAILED}
    if not written:
        return {"status": "failed", "detail": _FAILED}
    parsed = read_serato_tags(str(dst))
    if not parsed["found"]:
        return {"status": "failed", "detail": _FAILED}
    return {"status": "copied", "detail": _COPIED}


def _encode_synchsafe(size: int) -> bytes:
    """Encode a tag size the way an ID3 header stores it.

    Args:
        size: Number of bytes after the 10-byte header.

    Returns:
        Four synchsafe bytes.
    """
    return bytes(
        (
            (size >> 21) & 0x7F,
            (size >> 14) & 0x7F,
            (size >> 7) & 0x7F,
            size & 0x7F,
        )
    )


def _read_id3v23(path: Path) -> dict[str, object] | None:
    """Read a plain ID3v2.3 tag from the start of a file.

    Args:
        path: Audio file.

    Returns:
        The version, the frames, the padding, and the audio offset.
        None when the file has no plain ID3v2.3 tag. Unsynchronisation,
        an extended header, and a tag larger than 16,000,000 bytes are
        refused so the caller does not rewrite them.
    """
    with path.open("rb") as handle:
        header = handle.read(10)
        if len(header) < 10 or header[:3] != b"ID3" or header[3] != 3:
            return None
        if header[5] & _UNSYNC or header[5] & _EXTENDED:
            return None
        tag_size = _synchsafe(header[6:10])
        if tag_size <= 0 or tag_size > _TAG_LIMIT:
            return None
        body = handle.read(tag_size)
    if len(body) < tag_size:
        return None
    frames: list[bytes] = []
    pos = 0
    while pos + 10 <= tag_size:
        frame_id = body[pos:pos + 4]
        if frame_id == b"\x00\x00\x00\x00" or frame_id[0] == 0:
            break
        frame_size = int.from_bytes(body[pos + 4:pos + 8], "big")
        if frame_size < 0 or pos + 10 + frame_size > tag_size:
            return None
        frames.append(body[pos:pos + 10 + frame_size])
        pos += 10 + frame_size
    return {
        "frames": frames,
        "audio_offset": 10 + tag_size,
        "tag_size": tag_size,
    }


def _unsafe_frame(frame: bytes) -> bool:
    """Return whether a frame is compressed or encrypted.

    Args:
        frame: One raw ID3 frame, header included.

    Returns:
        True when the ID3v2.3 compression or encryption flag is set.
    """
    if len(frame) < 10:
        return True
    flags = frame[9]
    return bool(flags & _V23_COMPRESSED or flags & _V23_ENCRYPTED)


def _serato_frame(frame: bytes) -> bool:
    """Return whether a raw frame is a Serato GEOB frame.

    Args:
        frame: One raw ID3 frame, header included.

    Returns:
        True when the frame is GEOB and its description starts with Serato.
    """
    if len(frame) < 11 or frame[:4] != b"GEOB":
        return False
    name, _payload = _geob_body(frame[10:])
    return name.startswith("Serato ")


def _can_prepend_mp3(path: Path) -> bool:
    """Return whether an MP3 with no ID3 tag can take a new tag.

    Args:
        path: Destination file.

    Returns:
        True for an ``.mp3`` file that does not already start with a
        container this module refuses to rewrite.
    """
    if path.suffix.lower() != ".mp3":
        return False
    with path.open("rb") as handle:
        head = handle.read(12)
    if head.startswith((b"fLaC", b"RIFF", b"FORM", b"OggS", b"ID3")):
        return False
    if len(head) >= 8 and head[4:8] == b"ftyp":
        return False
    return True


def _audio_hash(path: Path, offset: int) -> str:
    """Hash the bytes after an ID3 tag.

    Args:
        path: Audio file.
        offset: Index of the first audio byte.

    Returns:
        The SHA-256 hex digest of that tail.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        handle.seek(offset)
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _build_tag(source: Path, dest: Path) -> tuple[bytes, int] | None:
    """Build a new ID3v2.3 tag and report the old audio offset.

    Args:
        source: File that holds the Serato frames.
        dest: File that will keep its other frames.

    Returns:
        The new tag bytes (header included) and the offset of the
        destination audio. None when the plan no longer applies.
    """
    source_tag = _read_id3v23(source)
    if source_tag is None:
        return None
    serato = [frame for frame in source_tag["frames"] if _serato_frame(frame) and not _unsafe_frame(frame)]
    if not serato:
        return None
    dest_tag = _read_id3v23(dest)
    if dest_tag is None:
        if not _can_prepend_mp3(dest):
            return None
        kept: list[bytes] = []
        audio_offset = 0
        old_size = 0
    else:
        if any(_serato_frame(frame) for frame in dest_tag["frames"]):
            return None
        kept = list(dest_tag["frames"])
        audio_offset = int(dest_tag["audio_offset"])
        old_size = int(dest_tag["tag_size"])
    body = b"".join([*kept, *serato])
    if old_size >= len(body):
        padding = old_size - len(body)
        tag_size = old_size
    else:
        padding = 1024
        tag_size = len(body) + padding
    tag = b"ID3" + bytes((3, 0, 0)) + _encode_synchsafe(tag_size) + body + (b"\x00" * padding)
    return tag, audio_offset


def _write_copied_tag(source: Path, dest: Path) -> bool:
    """Write a copied tag beside dest and replace dest when the audio matches.

    Args:
        source: File that holds the Serato frames.
        dest: File to replace after the audio tail is checked.

    Returns:
        True when dest now contains the Serato frames and the same audio
        bytes. False when dest was left or restored unchanged.
    """
    built = _build_tag(source, dest)
    if built is None:
        return False
    tag, audio_offset = built
    before = _audio_hash(dest, audio_offset)
    directory = dest.parent
    backup_fd, backup_name = tempfile.mkstemp(prefix=".serato-cuebak-", dir=directory)
    os.close(backup_fd)
    backup = Path(backup_name)
    temp_fd, temp_name = tempfile.mkstemp(prefix=".serato-cue-", dir=directory)
    os.close(temp_fd)
    temp: Path | None = Path(temp_name)
    try:
        shutil.copy2(dest, backup)
        assert temp is not None
        with temp.open("wb") as out, dest.open("rb") as src:
            out.write(tag)
            src.seek(audio_offset)
            shutil.copyfileobj(src, out)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, dest)
        temp = None
        if _audio_hash(dest, len(tag)) != before or not read_serato_tags(str(dest))["found"]:
            shutil.copy2(backup, dest)
            return False
        return True
    except OSError:
        try:
            if backup.is_file():
                shutil.copy2(backup, dest)
        except OSError:
            return False
        return False
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)
        backup.unlink(missing_ok=True)
