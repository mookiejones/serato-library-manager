"""Exact Serato frame bytes for snapshots.

This module reads and writes the stored Markers2, BeatGrid, and Autotags
bytes in MP3, AIFF, FLAC, and M4A files. Parsed cue and beatgrid values
come from ``tags.py``. The FLAC and M4A readers that turn those payloads
into cue lists stay in ``tags.py`` when that work lands; this file keeps
the bytes a snapshot hashes and puts back.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path

import tags

FRAME_KINDS = ("Markers2", "BeatGrid", "Autotags")

_KIND_BY_DESCRIPTION = {
    "Serato Markers2": "Markers2",
    "Serato BeatGrid": "BeatGrid",
    "Serato Autotags": "Autotags",
}
_FLAC_KEYS = {
    "SERATO_MARKERS_V2": "Markers2",
    "SERATO_MARKERS2": "Markers2",
    "SERATO_BEATGRID": "BeatGrid",
    "SERATO_AUTOTAGS": "Autotags",
}
_FLAC_KEY_FOR_KIND = {
    "Markers2": b"SERATO_MARKERS_V2",
    "BeatGrid": b"SERATO_BEATGRID",
    "Autotags": b"SERATO_AUTOTAGS",
}
_MP4_NAMES = {
    "markersv2": "Markers2",
    "markers2": "Markers2",
    "beatgrid": "BeatGrid",
    "autotags": "Autotags",
}
_B64_ALPHABET = set(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")
_MP4_CONTAINERS = {b"moov", b"trak", b"mdia", b"minf", b"stbl", b"udta", b"ilst"}


class FrameRewriteError(Exception):
    """Raised when Serato frames cannot be written back without touching audio.

    Attributes:
        message: Text a caller can show. It does not include a path.
    """

    def __init__(self, message: str):
        """Store the refusal.

        Args:
            message: Text a caller can show.
        """
        super().__init__(message)
        self.message = message


def parse_markers_payload(payload: bytes) -> tags.MarkerEntries:
    """Parse a Markers2 payload into cues, loops, and flips.

    Args:
        payload: Serato Markers2 bytes, including the ``01 01`` header.

    Returns:
        The parsed entries. An unrecognized payload is empty.
    """
    return tags._parse_markers2(payload)


def parse_beatgrid_payload(payload: bytes) -> list[tags.BeatMarker]:
    """Parse a BeatGrid payload into markers.

    Args:
        payload: Serato BeatGrid bytes.

    Returns:
        Marker dicts. An unrecognized payload is empty.
    """
    return tags._parse_beatgrid(payload)


def payload_from_stored(stored: bytes) -> bytes:
    """Return the Serato binary payload inside one stored frame.

    ID3 stores a whole GEOB frame. FLAC stores the base64 comment value.
    M4A stores the MP4 ``data`` atom body, whose first eight bytes are the
    version and locale.

    Args:
        stored: Exact bytes kept by a snapshot for one frame.

    Returns:
        The payload parsers accept. The original stored bytes are not modified.
    """
    if stored.startswith(b"GEOB") and len(stored) > 10:
        _name, payload = tags._geob_body(stored[10:])
        return payload
    compact = b"".join(stored.split())
    if len(compact) >= 4 and all(byte in _B64_ALPHABET for byte in compact):
        pad = (-len(compact)) % 4
        try:
            decoded = base64.b64decode(compact + (b"=" * pad), validate=False)
        except binascii.Error:
            decoded = b""
        if decoded:
            return decoded
    if len(stored) >= 8 and stored[:8] == b"\x00" * 8:
        return stored[8:]
    return stored


def read_stored_frames(path: str | Path | None) -> dict[str, bytes]:
    """Read the exact stored Serato frames from an audio file.

    Args:
        path: Audio file, or None.

    Returns:
        A map of Markers2, BeatGrid, and Autotags to the bytes stored in
        that container. Missing frames are omitted. A shortcut, a missing
        file, or an unreadable file returns an empty map. The file is not
        modified.
    """
    if not path:
        return {}
    file = Path(path)
    try:
        if not file.is_file() or file.is_symlink():
            return {}
        kind = _sniff_container(file)
        if kind == "flac":
            return _read_flac_frames(file)
        if kind == "aiff":
            return _read_aiff_frames(file)
        if kind == "mp4":
            return _read_mp4_frames(file)
        return _read_id3_frames(file)
    except (OSError, ValueError):
        return {}


def read_audio(path: str | Path) -> bytes:
    """Return the audio bytes, leaving every metadata container out.

    Args:
        path: Audio file.

    Returns:
        The audio region for that container. An empty result means the
        container has no separated audio region.

    Raises:
        OSError: If the file cannot be read.
        FrameRewriteError: If the container is not one this module rewrites.
    """
    return _audio_region(Path(path))


def audio_digest(path: str | Path) -> str:
    """Hash the audio region.

    Args:
        path: Audio file.

    Returns:
        The SHA-256 hex digest of ``read_audio``.
    """
    return hashlib.sha256(read_audio(path)).hexdigest()


def restore_stored_frames(path: str | Path, frames: Mapping[str, bytes]) -> None:
    """Put stored Serato frames back without changing the audio bytes.

    The file is replaced only after the audio region still hashes the same.
    A failure leaves the previous bytes in place. Kinds that are absent from
    ``frames`` are removed. Other tags are kept.

    Args:
        path: Audio file to update. Shortcuts are refused.
        frames: Markers2, BeatGrid, and Autotags mapped to the exact bytes
            ``read_stored_frames`` returned for that container.

    Raises:
        FrameRewriteError: If the file is not a regular file, the container
            cannot be rewritten, or the audio region would change.
        OSError: If the file cannot be read or replaced.
    """
    file = Path(path)
    if not file.is_file() or file.is_symlink():
        raise FrameRewriteError("The audio file is not a regular file.")
    wanted = {kind: blob for kind, blob in frames.items() if kind in FRAME_KINDS}
    before = audio_digest(file)
    container = _sniff_container(file)
    directory = file.parent
    temp_fd, temp_name = tempfile.mkstemp(prefix=".serato-frame-", dir=directory)
    os.close(temp_fd)
    temp: Path | None = Path(temp_name)
    backup_fd, backup_name = tempfile.mkstemp(prefix=".serato-framebak-", dir=directory)
    os.close(backup_fd)
    backup = Path(backup_name)
    try:
        shutil.copy2(file, backup)
        assert temp is not None
        if container == "flac":
            _write_flac(file, temp, wanted)
        elif container == "aiff":
            _write_aiff(file, temp, wanted)
        elif container == "mp4":
            _write_mp4(file, temp, wanted)
        else:
            _write_id3_file(file, temp, wanted)
        with temp.open("rb+") as handle:
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, file)
        temp = None
        if audio_digest(file) != before:
            os.replace(backup, file)
            raise FrameRewriteError(
                "The audio bytes would have changed, so the file was left as it was."
            )
    except Exception:
        try:
            if backup.is_file() and audio_digest(file) != before:
                os.replace(backup, file)
        except OSError:
            pass
        raise
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)
        backup.unlink(missing_ok=True)


def _sniff_container(path: Path) -> str:
    """Decide which metadata container an audio file uses.

    Args:
        path: Audio file.

    Returns:
        ``flac``, ``aiff``, ``mp4``, or ``id3``.
    """
    with path.open("rb") as handle:
        head = handle.read(12)
    if head.startswith(b"fLaC"):
        return "flac"
    if head.startswith(b"FORM"):
        return "aiff"
    if len(head) >= 8 and head[4:8] == b"ftyp":
        return "mp4"
    suffix = path.suffix.lower()
    if suffix == ".flac":
        return "flac"
    if suffix in {".aiff", ".aif"}:
        return "aiff"
    if suffix in {".m4a", ".mp4"}:
        return "mp4"
    return "id3"


def _audio_region(path: Path) -> bytes:
    """Return the container's audio bytes.

    Args:
        path: Audio file.

    Returns:
        Audio bytes. Metadata containers are not included.
    """
    container = _sniff_container(path)
    if container == "flac":
        _blocks, offset = _read_flac_blocks(path)
        with path.open("rb") as handle:
            handle.seek(offset)
            return handle.read()
    if container == "aiff":
        return b"".join(data for cid, data in _read_aiff_chunks(path) if cid == b"SSND")
    if container == "mp4":
        return _mp4_mdat(path)
    _version, _frames, offset = _split_id3(path)
    with path.open("rb") as handle:
        handle.seek(offset)
        return handle.read()


def _split_id3(path: Path) -> tuple[int, list[bytes], int]:
    """Split a leading ID3 tag into its version, raw frames, and audio offset.

    Args:
        path: Audio file.

    Returns:
        Version 3 or 4, the raw frames, and the offset of the audio. A file
        with no leading tag returns version 3, no frames, and offset 0.
        Unsynchronisation and an extended header are left as a single opaque
        body so this function does not guess their layout; the caller then
        refuses to rewrite them.
    """
    with path.open("rb") as handle:
        header = handle.read(10)
        if len(header) < 10 or header[:3] != b"ID3" or header[3] not in (3, 4):
            return 3, [], 0
        version = header[3]
        flags = header[5]
        tag_size = tags._synchsafe(header[6:10])
        if tag_size > tags._TAG_LIMIT:
            return version, [], 10 + tag_size
        body = handle.read(tag_size)
        footer = 10 if flags & 0x10 else 0
        offset = 10 + tag_size + footer
    if flags & tags._UNSYNC or flags & tags._EXTENDED:
        return version, [b"\xffID3-OPAQUE" + body], offset
    frames: list[bytes] = []
    pos = 0
    while pos + 10 <= len(body):
        frame_id = body[pos:pos + 4]
        if frame_id == b"\x00\x00\x00\x00" or frame_id[0] == 0:
            break
        if version == 4:
            frame_size = tags._synchsafe(body[pos + 4:pos + 8])
        else:
            frame_size = int.from_bytes(body[pos + 4:pos + 8], "big")
        if frame_size < 0 or pos + 10 + frame_size > len(body):
            break
        frames.append(body[pos:pos + 10 + frame_size])
        pos += 10 + frame_size
    return version, frames, offset


def _read_id3_frames(path: Path) -> dict[str, bytes]:
    """Collect raw Serato GEOB frames from a leading ID3 tag.

    Args:
        path: Audio file.

    Returns:
        Kind to raw frame bytes, header included.
    """
    _version, frames, _offset = _split_id3(path)
    found: dict[str, bytes] = {}
    for frame in frames:
        kind = _frame_kind(frame)
        if kind and kind not in found:
            found[kind] = frame
    return found


def _frame_kind(frame: bytes) -> str | None:
    """Return the Serato kind of one raw ID3 frame.

    Args:
        frame: Raw frame, header included.

    Returns:
        Markers2, BeatGrid, Autotags, or None.
    """
    if len(frame) < 11 or frame[:4] != b"GEOB" or frame.startswith(b"\xffID3-OPAQUE"):
        return None
    name, _payload = tags._geob_body(frame[10:])
    return _KIND_BY_DESCRIPTION.get(name)


def _build_id3(version: int, frames: list[bytes]) -> bytes:
    """Build a leading ID3 tag from raw frames.

    Args:
        version: 3 or 4.
        frames: Raw frames, each with its own header.

    Returns:
        The tag bytes, with no padding and no footer.
    """
    body = b"".join(frames)
    return b"ID3" + bytes([version, 0, 0]) + tags._encode_synchsafe(len(body)) + body


def _rewrite_id3_frames(version: int, frames: list[bytes], wanted: Mapping[str, bytes]) -> bytes:
    """Replace Serato GEOB frames and keep every other frame.

    Args:
        version: ID3 major version.
        frames: Existing raw frames.
        wanted: Frames that should remain, keyed by kind.

    Returns:
        A new ID3 tag.

    Raises:
        FrameRewriteError: If the tag is unsynchronised or extended.
    """
    if any(frame.startswith(b"\xffID3-OPAQUE") for frame in frames):
        raise FrameRewriteError("This ID3 tag cannot be rewritten safely.")
    kept: list[bytes] = []
    replaced: set[str] = set()
    for frame in frames:
        kind = _frame_kind(frame)
        if kind is None:
            kept.append(frame)
            continue
        if kind in wanted:
            kept.append(wanted[kind])
            replaced.add(kind)
    for kind in FRAME_KINDS:
        if kind in wanted and kind not in replaced:
            kept.append(wanted[kind])
    return _build_id3(version, kept)


def _write_id3_file(source: Path, dest: Path, wanted: Mapping[str, bytes]) -> None:
    """Write an ID3 file with restored Serato frames and the original audio.

    Args:
        source: File to read.
        dest: Temporary file to write.
        wanted: Stored frames keyed by kind.
    """
    version, frames, offset = _split_id3(source)
    tag = _rewrite_id3_frames(version, frames, wanted)
    with dest.open("wb") as out, source.open("rb") as src:
        out.write(tag)
        src.seek(offset)
        shutil.copyfileobj(src, out)


def _read_flac_blocks(path: Path) -> tuple[list[tuple[int, int, bytes]], int]:
    """Read FLAC metadata blocks and the offset where audio frames start.

    Args:
        path: FLAC file.

    Returns:
        Blocks as last-flag, type, and data, plus the audio offset.

    Raises:
        FrameRewriteError: If the file is not FLAC.
    """
    blocks: list[tuple[int, int, bytes]] = []
    with path.open("rb") as handle:
        if handle.read(4) != b"fLaC":
            raise FrameRewriteError("This file is not a FLAC file.")
        while True:
            header = handle.read(4)
            if len(header) < 4:
                break
            last = 1 if header[0] & 0x80 else 0
            block_type = header[0] & 0x7F
            length = int.from_bytes(header[1:4], "big")
            data = handle.read(length)
            blocks.append((last, block_type, data))
            if last:
                return blocks, handle.tell()
    return blocks, path.stat().st_size


def _parse_vorbis_comments(data: bytes) -> tuple[bytes, list[tuple[bytes, bytes]]]:
    """Split a Vorbis comment block into a vendor string and comments.

    Args:
        data: Vorbis comment packet without the FLAC block header.

    Returns:
        Vendor bytes and key/value pairs. A short block returns what it can.
    """
    if len(data) < 4:
        return b"", []
    vendor_len = int.from_bytes(data[:4], "little")
    vendor = data[4:4 + vendor_len]
    pos = 4 + vendor_len
    if pos + 4 > len(data):
        return vendor, []
    count = int.from_bytes(data[pos:pos + 4], "little")
    pos += 4
    comments: list[tuple[bytes, bytes]] = []
    for _ in range(count):
        if pos + 4 > len(data):
            break
        length = int.from_bytes(data[pos:pos + 4], "little")
        pos += 4
        entry = data[pos:pos + length]
        pos += length
        key, sep, value = entry.partition(b"=")
        if sep:
            comments.append((key, value))
    return vendor, comments


def _pack_vorbis_comments(vendor: bytes, comments: list[tuple[bytes, bytes]]) -> bytes:
    """Encode a vendor string and comments as a Vorbis comment block.

    Args:
        vendor: Vendor bytes.
        comments: Key/value pairs. The value is stored exactly.

    Returns:
        The block payload, without the four-byte FLAC header.
    """
    out = len(vendor).to_bytes(4, "little") + vendor
    out += len(comments).to_bytes(4, "little")
    for key, value in comments:
        entry = key + b"=" + value
        out += len(entry).to_bytes(4, "little") + entry
    return out


def _read_flac_frames(path: Path) -> dict[str, bytes]:
    """Read Serato Vorbis comments from a FLAC file.

    Args:
        path: FLAC file.

    Returns:
        Kind to the exact comment value bytes.
    """
    try:
        blocks, _offset = _read_flac_blocks(path)
    except FrameRewriteError:
        return {}
    found: dict[str, bytes] = {}
    for _last, block_type, data in blocks:
        if block_type != 4:
            continue
        _vendor, comments = _parse_vorbis_comments(data)
        for key, value in comments:
            kind = _FLAC_KEYS.get(key.decode("ascii", "replace").upper())
            if kind and kind not in found:
                found[kind] = value
    return found


def _write_flac(source: Path, dest: Path, wanted: Mapping[str, bytes]) -> None:
    """Write a FLAC file with restored Serato comments and the original audio.

    Args:
        source: FLAC file to read.
        dest: Temporary file to write.
        wanted: Stored comment values keyed by kind.

    Raises:
        FrameRewriteError: If the file has no FLAC marker.
    """
    blocks, offset = _read_flac_blocks(source)
    comments_seen = False
    rewritten: list[tuple[int, int, bytes]] = []
    for last, block_type, data in blocks:
        if block_type == 4:
            comments_seen = True
            data = _rewrite_vorbis(data, wanted)
        rewritten.append((last, block_type, data))
    if not comments_seen and wanted:
        vendor = b"serato-library"
        data = _rewrite_vorbis(_pack_vorbis_comments(vendor, []), wanted)
        if rewritten:
            last, block_type, previous = rewritten[-1]
            rewritten[-1] = (0, block_type, previous)
            rewritten.append((1, 4, data))
        else:
            rewritten.append((1, 4, data))
    with dest.open("wb") as out, source.open("rb") as src:
        out.write(b"fLaC")
        for last, block_type, data in rewritten:
            if len(data) > 0xFFFFFF:
                raise FrameRewriteError("The FLAC comment block is too large.")
            out.write(bytes([(0x80 if last else 0) | block_type]))
            out.write(len(data).to_bytes(3, "big"))
            out.write(data)
        src.seek(offset)
        shutil.copyfileobj(src, out)


def _rewrite_vorbis(data: bytes, wanted: Mapping[str, bytes]) -> bytes:
    """Replace Serato comments and keep the others.

    Args:
        data: Vorbis comment payload.
        wanted: Stored values keyed by kind.

    Returns:
        A new Vorbis comment payload.
    """
    vendor, comments = _parse_vorbis_comments(data)
    kept: list[tuple[bytes, bytes]] = []
    replaced: set[str] = set()
    for key, value in comments:
        kind = _FLAC_KEYS.get(key.decode("ascii", "replace").upper())
        if kind is None:
            kept.append((key, value))
            continue
        if kind in wanted and kind not in replaced:
            kept.append((key, wanted[kind]))
            replaced.add(kind)
    for kind in FRAME_KINDS:
        if kind in wanted and kind not in replaced:
            kept.append((_FLAC_KEY_FOR_KIND[kind], wanted[kind]))
    return _pack_vorbis_comments(vendor, kept)


def _read_aiff_chunks(path: Path) -> list[tuple[bytes, bytes]]:
    """Read AIFF chunks.

    Args:
        path: AIFF file.

    Returns:
        Chunk id and payload pairs. The pad byte is not included.

    Raises:
        FrameRewriteError: If the file is not a FORM AIFF file.
    """
    chunks: list[tuple[bytes, bytes]] = []
    with path.open("rb") as handle:
        header = handle.read(12)
        if len(header) < 12 or header[:4] != b"FORM" or header[8:12] not in {b"AIFF", b"AIFC"}:
            raise FrameRewriteError("This file is not an AIFF file.")
        while True:
            head = handle.read(8)
            if len(head) < 8:
                break
            size = int.from_bytes(head[4:8], "big")
            data = handle.read(size)
            if size % 2 == 1:
                handle.read(1)
            chunks.append((head[:4], data))
    return chunks


def _read_aiff_frames(path: Path) -> dict[str, bytes]:
    """Read Serato GEOB frames from an AIFF ID3 chunk.

    Args:
        path: AIFF file.

    Returns:
        Kind to raw GEOB frame bytes.
    """
    try:
        chunks = _read_aiff_chunks(path)
    except FrameRewriteError:
        return {}
    found: dict[str, bytes] = {}
    for cid, data in chunks:
        if cid not in {b"ID3 ", b"id3 "}:
            continue
        found.update(_frames_from_id3_bytes(data))
    return found


def _frames_from_id3_bytes(data: bytes) -> dict[str, bytes]:
    """Read Serato GEOB frames from an ID3 tag held in memory.

    Args:
        data: A complete ID3 tag, header included.

    Returns:
        Kind to raw frame bytes.
    """
    if len(data) < 10 or data[:3] != b"ID3":
        return {}
    version = data[3]
    if version not in (3, 4):
        return {}
    tag_size = tags._synchsafe(data[6:10])
    body = data[10:10 + tag_size]
    pos = 0
    found: dict[str, bytes] = {}
    while pos + 10 <= len(body):
        if body[pos] == 0:
            break
        if version == 4:
            frame_size = tags._synchsafe(body[pos + 4:pos + 8])
        else:
            frame_size = int.from_bytes(body[pos + 4:pos + 8], "big")
        if pos + 10 + frame_size > len(body):
            break
        frame = body[pos:pos + 10 + frame_size]
        kind = _frame_kind(frame)
        if kind and kind not in found:
            found[kind] = frame
        pos += 10 + frame_size
    return found


def _retarget_id3_bytes(data: bytes, wanted: Mapping[str, bytes]) -> bytes:
    """Restore Serato frames inside one ID3 tag blob.

    Args:
        data: Complete ID3 tag.
        wanted: Stored frames keyed by kind.

    Returns:
        A new ID3 tag.

    Raises:
        FrameRewriteError: If the blob is not a supported ID3 tag.
    """
    if len(data) < 10 or data[:3] != b"ID3" or data[3] not in (3, 4):
        raise FrameRewriteError("The AIFF ID3 chunk is not a supported tag.")
    if data[5] & tags._UNSYNC or data[5] & tags._EXTENDED:
        raise FrameRewriteError("This ID3 tag cannot be rewritten safely.")
    version = data[3]
    tag_size = tags._synchsafe(data[6:10])
    body = data[10:10 + tag_size]
    frames: list[bytes] = []
    pos = 0
    while pos + 10 <= len(body):
        if body[pos] == 0:
            break
        if version == 4:
            frame_size = tags._synchsafe(body[pos + 4:pos + 8])
        else:
            frame_size = int.from_bytes(body[pos + 4:pos + 8], "big")
        if pos + 10 + frame_size > len(body):
            break
        frames.append(body[pos:pos + 10 + frame_size])
        pos += 10 + frame_size
    return _rewrite_id3_frames(version, frames, wanted)


def _write_aiff(source: Path, dest: Path, wanted: Mapping[str, bytes]) -> None:
    """Write an AIFF file with a restored ID3 chunk and the original chunks.

    Args:
        source: AIFF file to read.
        dest: Temporary file to write.
        wanted: Stored GEOB frames keyed by kind.

    Raises:
        FrameRewriteError: If the file is not AIFF or the ID3 chunk is unsafe.
    """
    chunks = _read_aiff_chunks(source)
    form = b"AIFF"
    with source.open("rb") as handle:
        header = handle.read(12)
        if len(header) >= 12:
            form = header[8:12]
    replaced = False
    written: list[tuple[bytes, bytes]] = []
    for cid, data in chunks:
        if cid in {b"ID3 ", b"id3 "} and not replaced:
            data = _retarget_id3_bytes(data, wanted)
            replaced = True
        written.append((cid, data))
    if not replaced and wanted:
        tag = _rewrite_id3_frames(3, [], wanted)
        written.append((b"ID3 ", tag))
    payload = bytearray(form)
    for cid, data in written:
        payload.extend(cid)
        payload.extend(len(data).to_bytes(4, "big"))
        payload.extend(data)
        if len(data) % 2 == 1:
            payload.append(0)
    with dest.open("wb") as out:
        out.write(b"FORM")
        out.write(len(payload).to_bytes(4, "big"))
        out.write(payload)


class _Atom:
    """One MP4 atom and the slice it occupied in its parent body."""

    def __init__(self, typ: bytes, body: bytes, start: int, end: int):
        self.typ = typ
        self.body = body
        self.start = start
        self.end = end


def _parse_atom_list(blob: bytes) -> list[_Atom]:
    """Parse a sequence of MP4 atoms.

    Args:
        blob: Bytes that begin on an atom boundary.

    Returns:
        Atoms in order. A truncated atom stops the parse.
    """
    atoms: list[_Atom] = []
    pos = 0
    while pos + 8 <= len(blob):
        size = int.from_bytes(blob[pos:pos + 4], "big")
        typ = blob[pos + 4:pos + 8]
        header = 8
        if size == 1:
            if pos + 16 > len(blob):
                break
            size = int.from_bytes(blob[pos + 8:pos + 16], "big")
            header = 16
        elif size == 0:
            size = len(blob) - pos
        if size < header or pos + size > len(blob):
            break
        atoms.append(_Atom(typ, blob[pos + header:pos + size], pos, pos + size))
        pos += size
    return atoms


def _pack_atom(typ: bytes, body: bytes) -> bytes:
    """Encode one atom with an 8-byte header.

    Args:
        typ: Four-byte atom type.
        body: Atom body.

    Returns:
        The atom bytes.

    Raises:
        FrameRewriteError: If the atom does not fit in a 32-bit size.
    """
    size = 8 + len(body)
    if size >= 2**32:
        raise FrameRewriteError("The audio file's metadata atom is too large.")
    return size.to_bytes(4, "big") + typ + body


def _mp4_text(body: bytes) -> bytes:
    """Return the text of a ``mean`` or ``name`` atom.

    Args:
        body: Atom body. The first four bytes are version and flags.

    Returns:
        The remaining bytes without a trailing NUL.
    """
    return body[4:].split(b"\x00", 1)[0] if len(body) >= 4 else b""


def _edit_freeform(body: bytes, wanted: Mapping[str, bytes]) -> bytes | None:
    """Replace the ``data`` body of one Serato freeform atom.

    Args:
        body: Body of a ``----`` atom.
        wanted: Stored data-atom bodies keyed by kind.

    Returns:
        A new body when this atom is a Serato frame we restore or remove.
        None when the atom should be copied unchanged.
    """
    children = _parse_atom_list(body)
    mean = b""
    name = ""
    for child in children:
        if child.typ == b"mean":
            mean = _mp4_text(child.body)
        elif child.typ == b"name":
            name = _mp4_text(child.body).decode("latin-1", "replace").lower()
    kind = _MP4_NAMES.get(name)
    if mean != b"com.serato.dj" or kind is None:
        return None
    if kind not in wanted:
        return b""
    rebuilt: list[bytes] = []
    wrote = False
    for child in children:
        if child.typ == b"data":
            rebuilt.append(_pack_atom(b"data", wanted[kind]))
            wrote = True
        else:
            rebuilt.append(_pack_atom(child.typ, child.body))
    if not wrote:
        rebuilt.append(_pack_atom(b"data", wanted[kind]))
    return b"".join(rebuilt)


def _rewrite_atom_sequence(blob: bytes, wanted: Mapping[str, bytes]) -> bytes:
    """Copy an atom sequence, replacing Serato freeform atoms.

    Args:
        blob: Bytes that begin on an atom boundary.
        wanted: Stored ``data`` atom bodies keyed by kind.

    Returns:
        The sequence to write. Unchanged atoms are copied as raw slices.
    """
    pieces: list[bytes] = []
    cursor = 0
    for atom in _parse_atom_list(blob):
        if atom.start > cursor:
            pieces.append(blob[cursor:atom.start])
        pieces.append(_rewrite_one_atom(blob[atom.start:atom.end], atom, wanted))
        cursor = atom.end
    if cursor < len(blob):
        pieces.append(blob[cursor:])
    return b"".join(pieces)


def _rewrite_one_atom(raw: bytes, atom: _Atom, wanted: Mapping[str, bytes]) -> bytes:
    """Return one atom, edited when it contains Serato frames.

    Args:
        raw: Original atom bytes, header included.
        atom: Parsed atom.
        wanted: Stored ``data`` atom bodies keyed by kind.

    Returns:
        Replacement bytes. An empty result drops the atom.
    """
    if atom.typ == b"----":
        edited = _edit_freeform(atom.body, wanted)
        if edited is None:
            return raw
        if not edited:
            return b""
        return _pack_atom(b"----", edited)
    if atom.typ == b"meta":
        prefix = atom.body[:4]
        return _pack_atom(b"meta", prefix + _rewrite_atom_sequence(atom.body[4:], wanted))
    if atom.typ in _MP4_CONTAINERS:
        return _pack_atom(atom.typ, _rewrite_atom_sequence(atom.body, wanted))
    return raw


def _read_mp4_frames(path: Path) -> dict[str, bytes]:
    """Read Serato freeform atoms from an M4A or MP4 file.

    Args:
        path: MP4 file.

    Returns:
        Kind to the exact ``data`` atom body.
    """
    found: dict[str, bytes] = {}

    def visit(blob: bytes) -> None:
        for atom in _parse_atom_list(blob):
            if atom.typ == b"mdat":
                continue
            if atom.typ == b"----":
                children = _parse_atom_list(atom.body)
                mean = b""
                name = ""
                data = b""
                for child in children:
                    if child.typ == b"mean":
                        mean = _mp4_text(child.body)
                    elif child.typ == b"name":
                        name = _mp4_text(child.body).decode("latin-1", "replace").lower()
                    elif child.typ == b"data":
                        data = child.body
                kind = _MP4_NAMES.get(name)
                if mean == b"com.serato.dj" and kind and kind not in found:
                    found[kind] = data
            elif atom.typ == b"meta" and len(atom.body) >= 4:
                visit(atom.body[4:])
            elif atom.typ in _MP4_CONTAINERS:
                visit(atom.body)

    with path.open("rb") as handle:
        end = path.stat().st_size
        while handle.tell() + 8 <= end:
            pos = handle.tell()
            head = handle.read(8)
            if len(head) < 8:
                break
            size = int.from_bytes(head[:4], "big")
            typ = head[4:8]
            header = 8
            if size == 1:
                large = handle.read(8)
                if len(large) < 8:
                    break
                size = int.from_bytes(large, "big")
                header = 16
            elif size == 0:
                size = end - pos
            if size < header or pos + size > end:
                break
            if typ == b"mdat":
                handle.seek(pos + size)
                continue
            body = handle.read(size - header)
            if typ == b"meta" and len(body) >= 4:
                visit(body[4:])
            elif typ in _MP4_CONTAINERS or typ == b"moov":
                visit(body)
            elif typ == b"----":
                visit(_pack_atom(typ, body))
    return found


def _mp4_mdat(path: Path) -> bytes:
    """Return every ``mdat`` body in an MP4 file.

    Args:
        path: MP4 file.

    Returns:
        The concatenated media data. Atom headers are not included.
    """
    pieces: list[bytes] = []
    with path.open("rb") as handle:
        end = path.stat().st_size
        while handle.tell() + 8 <= end:
            pos = handle.tell()
            head = handle.read(8)
            if len(head) < 8:
                break
            size = int.from_bytes(head[:4], "big")
            typ = head[4:8]
            header = 8
            if size == 1:
                large = handle.read(8)
                size = int.from_bytes(large, "big") if len(large) == 8 else 0
                header = 16
            elif size == 0:
                size = end - pos
            if size < header or pos + size > end:
                break
            if typ == b"mdat":
                pieces.append(handle.read(size - header))
            else:
                handle.seek(pos + size)
    return b"".join(pieces)


def _write_mp4(source: Path, dest: Path, wanted: Mapping[str, bytes]) -> None:
    """Write an MP4 file with restored Serato atoms and the original ``mdat``.

    Args:
        source: MP4 file to read.
        dest: Temporary file to write.
        wanted: Stored ``data`` atom bodies keyed by kind.

    Raises:
        FrameRewriteError: If an atom size is not usable.
    """
    with dest.open("wb") as out, source.open("rb") as src:
        end = source.stat().st_size
        while src.tell() + 8 <= end:
            pos = src.tell()
            head = src.read(8)
            if len(head) < 8:
                break
            size = int.from_bytes(head[:4], "big")
            typ = head[4:8]
            header = 8
            header_bytes = head
            if size == 1:
                large = src.read(8)
                header_bytes += large
                size = int.from_bytes(large, "big") if len(large) == 8 else 0
                header = 16
            elif size == 0:
                size = end - pos
            if size < header or pos + size > end:
                raise FrameRewriteError("The audio file has a metadata atom this restore cannot read.")
            if typ == b"mdat":
                out.write(header_bytes)
                remaining = size - header
                while remaining:
                    chunk = src.read(min(remaining, 1024 * 1024))
                    if not chunk:
                        break
                    out.write(chunk)
                    remaining -= len(chunk)
                continue
            body = src.read(size - header)
            if typ == b"meta":
                prefix = body[:4]
                edited = prefix + _rewrite_atom_sequence(body[4:], wanted)
                out.write(_pack_atom(typ, edited))
            elif typ in _MP4_CONTAINERS:
                out.write(_pack_atom(typ, _rewrite_atom_sequence(body, wanted)))
            else:
                out.write(header_bytes)
                out.write(body)
