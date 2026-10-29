"""Build Serato 4 and Serato 5 fixtures from the published tag notes.

The bytes come from the Holzhaus reverse-engineering notes, not from this
repository's tag writer. Run it from the repository root:

    python3 tests/fixtures/build_fixtures.py

Serato 5 Lucid/Flexible beatgrids and Protect Library are not written.
Their on-disk layout is not in those notes. Every serato5 file is marked
``spec-derived, unverified`` until Byte Beat's serato5-probe.sh is run on
a real install.

Citations are repeated in the manifest written next to the files.
"""

from __future__ import annotations

import base64
import hashlib
import json
import struct
from pathlib import Path


CRATE_VERSION = "1.0/Serato ScratchLive Crate"
DATABASE_VERSION = "2.0/Serato Scratch LIVE Database"

# Portable-drive check fixture. Paths are synthetic. Names that Windows
# would reject (CON, a trailing space, a colon) live only inside the crate
# bytes, never as file names in this tree.
DRIVE_CHECK_HOUSE = [
    "Music/on-drive.mp3",
    "Music/gone.mp3",
    "Music/CON.mp3",
    "Music/NUL.txt",
    "Music/COM1.mp3",
    "Music/COM10.mp3",
    "Music/concert.mp3",
    "Music/late.mp3.",
    "Music/what?.mp3",
    "Music/space.mp3 ",
    "Music/a:b.mp3",
    "Users/serato-drive-check-absent/night.mp3",
    "Music/" + ("b" * 256) + ".mp3",
]
DRIVE_CHECK_PEAK = ["Music\\peak-win.mp3"]
DRIVE_CHECK_KEEP = ["Music/from-the-extra-folder.mp3"]
DRIVE_CHECK_EXPORT_BACKUP = ["Music/from-export-backups.mp3"]
DRIVE_CHECK_LEXICON = ["Music/from-lexicon.mp3"]
DRIVE_CHECK_SMART = ["Music/smart-only.mp3"]
DRIVE_CHECK_DATABASE_ONLY = "Music/only-in-database.mp3"

# Silent AAC-LC carrier. The access unit decodes to digital silence. The
# moov skeleton is the ISO-BMFF track for that one access unit. Serato
# ---- atoms are added separately from the fileformats note.
_FTYP = base64.b64decode("AAAAHGZ0eXBNNEEgAAACAE00QSBpc29taXNvMg==")
_MDAT = base64.b64decode("AAAAKW1kYXTeAgBMYXZjNjAuMzEuMTAyAAIwQA4BGCAHARggBwEYIAc=")
_MVHD = base64.b64decode(
    "AAAAbG12aGQAAAAAAAAAAAAAAAAAAAPoAAAAMgABAAABAAAAAAAAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAE"
    "AAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAC"
)
_TRAK = base64.b64decode(
    "AAACNXRyYWsAAABcdGtoZAAAAAMAAAAAAAAAAAAAAAEAAAAAAAAAMgAAAAAAAAAAAAAAAQEAAAAAAQAAAAAAAAAAAAAAAAAAAAE"
    "AAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAACRlZHRzAAAAHGVsc3QAAAAAAAAAAQAAADIAAAQAAAEAAAAAAa1tZGlhAAAAIG1kaGQ"
    "AAAAAAAAAAAAAAAAAAKxEAAAMnVXEAAAAAAAtaGRscgAAAAAAAAAAc291bgAAAAAAAAAAAAAAAFNvdW5kSGFuZGxlcgAAAAFYbWluZgAAABBzbWhk"
    "AAAAAAAAAAAAAAAkZGluZgAAABxkcmVmAAAAAAAAAAEAAAAMdXJsIAAAAAEAAAEcc3RibAAAAGpzdHNkAAAAAAAAAAEAAABabXA0YQAAAAAAAAAB"
    "AAAAAAAAAAAAAQAQAAAAAKxEAAAAAAA2ZXNkcwAAAAADgICAJQABAASAgIAXQBUAAAAAAH0AAAAOFQWAgIAFEghW5QAGgICAAQIAAAAgc3R0cw"
    "AAAAAAAAACAAAAAwAABAAAAAABAAAAnQAAABxzdHNjAAAAAAAAAAEAAAABAAAABAAAAAEAAAAkc3RzegAAAAAAAAAAAAAABAAAABUAAAAEAAAABAAAAAQ"
    "AAAAUc3RjbwAAAAAAAAABAAAALAAAABpzZ3BkAQAAAHJvbGwAAAACAAAAAf//AAAAHHNiZ3AAAAAAcm9sbAAAAAEAAAAEAAAAAQ=="
)

WIKI = "https://github.com/Holzhaus/mixxx/wiki/Serato-Database-Format"
DATABASE_SCRIPT = "https://github.com/Holzhaus/serato-tags/blob/master/scripts/database_v2.py"
MARKERS2 = "https://github.com/Holzhaus/serato-tags/blob/main/docs/serato_markers2.md"
BEATGRID = "https://github.com/Holzhaus/serato-tags/blob/main/docs/serato_beatgrid.md"
FILEFORMATS = "https://github.com/Holzhaus/serato-tags/blob/main/docs/fileformats.md"

CITE_DATABASE = (
    f"{WIKI} (record header, vrsn, otrk, pfil/ptrk as UTF-16BE) and "
    f"{DATABASE_SCRIPT} (field names ttyp, tsng, tart, tbpm, bmis)."
)
CITE_CRATE = (
    f"{WIKI} (vrsn '1.0/Serato ScratchLive Crate', otrk/ptrk; the crate name is the "
    "filename, not a record). Nested crates join parent and child with %% in the filename."
)
CITE_MARKERS = (
    f"{MARKERS2} (header, base64 and null padding, CUE, LOOP, FLIP, COLOR, BPMLOCK entries)."
)
CITE_GRID = (
    f"{BEATGRID} (version byte 1, non-terminal beats-until-next, terminal BPM, one-byte footer)."
)
CITE_MP3 = f"{FILEFORMATS} section 'MP3 and AIFF' (ID3v2.4 GEOB Serato Markers2 and Serato BeatGrid)."
CITE_AIFF = f"{FILEFORMATS} section 'MP3 and AIFF' (ID3v2.4 GEOB inside an AIFF ID3 chunk)."
CITE_FLAC = (
    f"{FILEFORMATS} section 'FLAC' (VORBIS_COMMENT SERATO_MARKERS_V2 and SERATO_BEATGRID, "
    "base64 without padding, linefeed every 72 characters, application/octet-stream envelope)."
)
CITE_M4A = (
    f"{FILEFORMATS} section 'MP4/M4A' (---- atoms, mean com.serato.dj, names markersv2 and "
    "beatgrid; markersv2 has linefeeds every 72 characters, beatgrid does not)."
)

SERATO5_NOTE = (
    "spec-derived, unverified. Lucid/Flexible beatgrid storage and Protect Library storage "
    "are not in the published notes, so these fixtures do not invent them. The beatgrid here "
    "is the documented version-byte-1 layout. Unverified until Byte Beat's serato5-probe.sh "
    "runs on a real Serato 5 install."
)
SERATO4_NOTE = (
    "spec-derived from the published Scratch Live compatibility format that Serato 4 still "
    "writes beside the SQLite library. Not captured from a live Serato install."
)


def _rgb(color: str) -> bytes:
    """Return three RGB bytes from a ``#RRGGBB`` color.

    Args:
        color: Hex color.

    Returns:
        Red, green, and blue.
    """
    return bytes.fromhex(color.removeprefix("#"))


def _entry(kind: str, blob: bytes) -> bytes:
    """Wrap one Markers2 entry.

    Args:
        kind: ASCII type such as ``CUE``.
        blob: Entry payload. The length covers only this payload.

    Returns:
        Null-terminated type, big-endian length, and payload.
    """
    return kind.encode("ascii") + b"\x00" + len(blob).to_bytes(4, "big") + blob


def _cue(index: int, start_ms: int, color: str, name: str) -> bytes:
    """Encode one CUE entry from the Markers2 table.

    Offsets follow that table: index at 0x01, milliseconds at 0x02, RGB at
    0x07, UTF-8 name at 0x0c.

    Args:
        index: Cue index.
        start_ms: Position in milliseconds.
        color: ``#RRGGBB``.
        name: Cue name.

    Returns:
        The CUE payload.
    """
    name_bytes = name.encode("utf-8") + b"\x00"
    raw = bytearray(12 + len(name_bytes))
    raw[1] = index
    raw[2:6] = start_ms.to_bytes(4, "big")
    raw[7:10] = _rgb(color)
    raw[12:] = name_bytes
    return bytes(raw)


def _loop(index: int, start_ms: int, end_ms: int, color: str, locked: bool, name: str) -> bytes:
    """Encode one LOOP entry from the Markers2 table.

    The table's offsets put the 4-byte color at 0x0e, the lock flag at
    0x13, and the name at 0x14. The length column on the 0x12 row says 3
    while the raw value and the next offset are a single byte, so this
    writes one byte at 0x12.

    Args:
        index: Loop index.
        start_ms: Loop start in milliseconds.
        end_ms: Loop end in milliseconds.
        color: ``#RRGGBB``. Stored as ARGB with a zero alpha byte.
        locked: True stores a lock flag of 1.
        name: Loop name.

    Returns:
        The LOOP payload.
    """
    name_bytes = name.encode("utf-8") + b"\x00"
    raw = bytearray(20 + len(name_bytes))
    raw[1] = index
    raw[2:6] = start_ms.to_bytes(4, "big")
    raw[6:10] = end_ms.to_bytes(4, "big")
    raw[10:14] = b"\xff\xff\xff\xff"
    raw[14:18] = b"\x00" + _rgb(color)
    raw[19] = 1 if locked else 0
    raw[20:] = name_bytes
    return bytes(raw)


def _flip(index: int, enabled: bool, name: str) -> bytes:
    """Encode one FLIP entry from the Markers2 table.

    Args:
        index: Flip index.
        enabled: True stores an enabled flag of 1.
        name: Flip name.

    Returns:
        The FLIP payload, including one jump subentry so the length fields
        in that table are present.
    """
    name_bytes = name.encode("utf-8") + b"\x00"
    jump = struct.pack(">d", 1.0) + struct.pack(">d", 2.0)
    sub = bytes([0]) + len(jump).to_bytes(4, "big") + jump
    return bytes([0, index, 1 if enabled else 0]) + name_bytes + bytes([0]) + (1).to_bytes(4, "big") + sub


def markers2_payload(spec: dict[str, object]) -> bytes:
    """Encode a Markers2 payload for one track.

    Args:
        spec: Cues, loops, flips, track color, and beatgrid lock flag.

    Returns:
        The GEOB payload: ``01 01``, base64 with a linefeed every 72
        characters, and null padding out to 470 bytes.
    """
    parts: list[bytes] = []
    color = spec.get("track_color")
    if isinstance(color, str):
        parts.append(_entry("COLOR", bytes([0]) + _rgb(color)))
    locked = spec.get("beatgrid_locked")
    if isinstance(locked, bool):
        parts.append(_entry("BPMLOCK", bytes([1 if locked else 0])))
    for cue in _dicts(spec.get("cues")):
        parts.append(
            _entry("CUE", _cue(int(cue["index"]), int(cue["start_ms"]), str(cue["color"]), str(cue["name"])))
        )
    for loop in _dicts(spec.get("loops")):
        parts.append(
            _entry(
                "LOOP",
                _loop(
                    int(loop["index"]),
                    int(loop["start_ms"]),
                    int(loop["end_ms"]),
                    str(loop["color"]),
                    bool(loop["locked"]),
                    str(loop["name"]),
                ),
            )
        )
    for flip in _dicts(spec.get("flips")):
        parts.append(_entry("FLIP", _flip(int(flip["index"]), bool(flip["enabled"]), str(flip["name"]))))
    decoded = b"\x01\x01" + b"".join(parts) + b"\x00"
    text = base64.b64encode(decoded).decode("ascii").rstrip("=")
    lined = "\n".join(text[i : i + 72] for i in range(0, len(text), 72)).encode("ascii")
    payload = b"\x01\x01" + lined
    if len(payload) < 470:
        payload += b"\x00" * (470 - len(payload))
    return payload


def beatgrid_payload(markers: list[dict[str, object]], footer: int) -> bytes:
    """Encode a BeatGrid payload.

    Args:
        markers: Earlier markers store ``beats``. The last stores ``bpm``.
        footer: The single footer byte. The note calls it apparently random.

    Returns:
        Header, markers, and footer. Version byte 1.
    """
    body = bytes([1, 0]) + len(markers).to_bytes(4, "big")
    last = len(markers) - 1
    for index, marker in enumerate(markers):
        body += struct.pack(">f", float(marker["position"]))
        if index == last:
            body += struct.pack(">f", float(marker["bpm"]))
        else:
            body += int(marker["beats"]).to_bytes(4, "big")
    return body + bytes([footer & 0xFF])


def _dicts(value: object) -> list[dict[str, object]]:
    """Return a list of dicts, or an empty list.

    Args:
        value: A JSON-like list.

    Returns:
        The dict items.
    """
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _chunk(tag: str, data: bytes) -> bytes:
    """Encode one crate or database record.

    Args:
        tag: Four ASCII characters.
        data: Payload. The length is a big-endian uint32.

    Returns:
        The record bytes.
    """
    return tag.encode("ascii") + struct.pack(">I", len(data)) + data


def _text(tag: str, value: str) -> bytes:
    """Encode a UTF-16BE text record.

    Args:
        tag: Four-character tag.
        value: Text. No BOM and no extra terminator; the length bounds it.

    Returns:
        The record.
    """
    return _chunk(tag, value.encode("utf-16-be"))


def crate_bytes(paths: list[str | None]) -> bytes:
    """Encode a crate file.

    Args:
        paths: ``ptrk`` values. None is an ``otrk`` with no path field.

    Returns:
        ``vrsn`` plus one ``otrk`` per path.
    """
    parts = [_text("vrsn", CRATE_VERSION)]
    for path in paths:
        inner = b"" if path is None else _text("ptrk", path)
        parts.append(_chunk("otrk", inner))
    return b"".join(parts)


def database_bytes(tracks: list[dict[str, object]]) -> bytes:
    """Encode a legacy ``database V2`` file.

    Args:
        tracks: Rows with optional path, type, title, artist, bpm, and missing.

    Returns:
        ``vrsn`` plus one ``otrk`` per row.
    """
    parts = [_text("vrsn", DATABASE_VERSION)]
    for track in tracks:
        inner = b""
        path = track.get("path")
        if isinstance(path, str):
            inner += _text("pfil", path)
        kind = track.get("type")
        if isinstance(kind, str):
            inner += _text("ttyp", kind)
        inner += _text("tsng", str(track.get("title") or ""))
        inner += _text("tart", str(track.get("artist") or ""))
        inner += _text("tbpm", str(track.get("bpm") or ""))
        inner += _chunk("bmis", bytes([1 if track.get("missing") else 0]))
        parts.append(_chunk("otrk", inner))
    return b"".join(parts)


def _synchsafe(size: int) -> bytes:
    """Encode an ID3v2.4 size.

    Args:
        size: Byte count.

    Returns:
        Four synchsafe bytes.
    """
    return bytes(((size >> 21) & 0x7F, (size >> 14) & 0x7F, (size >> 7) & 0x7F, size & 0x7F))


def _geob(description: str, payload: bytes) -> bytes:
    """Encode one ID3v2.4 GEOB frame.

    Args:
        description: Frame description, Latin-1.
        payload: Encapsulated object.

    Returns:
        The frame, size included. The frame size is synchsafe.
    """
    body = bytes([0]) + b"application/octet-stream\x00\x00" + description.encode("latin-1") + b"\x00" + payload
    return b"GEOB" + _synchsafe(len(body)) + b"\x00\x00" + body


def id3_tag(frames: list[bytes]) -> bytes:
    """Wrap frames in an ID3v2.4 tag.

    Args:
        frames: Raw frames.

    Returns:
        The tag, header included.
    """
    body = b"".join(frames)
    return b"ID3" + bytes((4, 0, 0)) + _synchsafe(len(body)) + body


def _mp3_frames() -> bytes:
    """Return two silent MPEG-1 Layer III frames.

    A second frame is what makes the first frame's length check out. The
    side information and main data are zeros, which decode as silence.

    Returns:
        208 bytes of audio.
    """
    frame = bytes((0xFF, 0xFB, 0x10, 0xC0)) + (b"\x00" * 100)
    return frame + frame


def _crc8(data: bytes) -> int:
    """CRC-8 used by a FLAC frame header.

    Args:
        data: Header bytes before the CRC.

    Returns:
        The CRC.
    """
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x07) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


def _crc16(data: bytes) -> int:
    """CRC-16 used by a FLAC frame footer.

    Args:
        data: Frame bytes before the footer.

    Returns:
        The CRC.
    """
    crc = 0
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x8005) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def _flac_frame(samples: int = 16) -> bytes:
    """Encode one constant FLAC frame of 16-bit silence.

    Args:
        samples: Block size. 16 uses the 8-bit block-size code.

    Returns:
        One frame, footer included.
    """
    header = bytearray(b"\xff\xf8\x69\x08\x00")
    header.append(samples - 1)
    header.append(_crc8(header))
    frame = bytes(header) + b"\x00\x00\x00"
    return frame + struct.pack(">H", _crc16(frame))


def _vorbis_comment(comments: list[tuple[str, str]]) -> bytes:
    """Encode a Vorbis comment block.

    Args:
        comments: Name and value pairs. Values may contain newlines.

    Returns:
        The block payload, little-endian lengths.
    """
    vendor = b"fixture"
    body = struct.pack("<I", len(vendor)) + vendor + struct.pack("<I", len(comments))
    for key, value in comments:
        raw = f"{key}={value}".encode("utf-8")
        body += struct.pack("<I", len(raw)) + raw
    return body


def _envelope(field_name: str, payload: bytes, linefeeds: bool) -> str:
    """Base64-encode a FLAC/MP4 Serato envelope.

    Args:
        field_name: Inner name such as ``Serato Markers2``.
        payload: Markers2 or BeatGrid bytes.
        linefeeds: Insert a linefeed every 72 characters when true.

    Returns:
        Base64 without padding.
    """
    raw = b"application/octet-stream\x00\x00" + field_name.encode("ascii") + b"\x00" + payload
    text = base64.b64encode(raw).decode("ascii").rstrip("=")
    if linefeeds:
        return "\n".join(text[i : i + 72] for i in range(0, len(text), 72))
    return text


def _mp3(spec: dict[str, object]) -> bytes:
    """Build a tiny MP3 with Serato GEOB frames and silent audio.

    Args:
        spec: Marker spec.

    Returns:
        ID3v2.4 tag plus two silent frames.
    """
    tag = id3_tag(
        [
            _geob("Serato Markers2", markers2_payload(spec)),
            _geob("Serato BeatGrid", beatgrid_payload(_dicts(spec.get("beatgrid")), int(spec["footer"]))),
        ]
    )
    return tag + _mp3_frames()


def _aiff(spec: dict[str, object]) -> bytes:
    """Build a tiny AIFF with silence and an ID3 chunk.

    Args:
        spec: Marker spec.

    Returns:
        FORM/AIFF with COMM, SSND, and ID3.
    """
    frames = 16
    comm = struct.pack(">hI", 1, frames) + struct.pack(">h", 16) + bytes.fromhex("400eac44000000000000")
    ssnd = struct.pack(">II", 0, 0) + (b"\x00\x00" * frames)
    tag = id3_tag(
        [
            _geob("Serato Markers2", markers2_payload(spec)),
            _geob("Serato BeatGrid", beatgrid_payload(_dicts(spec.get("beatgrid")), int(spec["footer"]))),
        ]
    )
    form = b"AIFF" + _aiff_chunk(b"COMM", comm) + _aiff_chunk(b"SSND", ssnd) + _aiff_chunk(b"ID3 ", tag)
    return b"FORM" + struct.pack(">I", len(form)) + form


def _aiff_chunk(tag: bytes, payload: bytes) -> bytes:
    """Encode one even-aligned AIFF chunk.

    Args:
        tag: Four-byte chunk id.
        payload: Chunk data.

    Returns:
        The chunk, with a pad byte when the payload length is odd.
    """
    pad = b"\x00" if len(payload) % 2 else b""
    return tag + struct.pack(">I", len(payload)) + payload + pad


def _flac(spec: dict[str, object]) -> bytes:
    """Build a tiny FLAC with Serato Vorbis comments and one silent frame.

    Args:
        spec: Marker spec.

    Returns:
        A FLAC file.
    """
    markers = _envelope("Serato Markers2", markers2_payload(spec), True)
    grid = _envelope(
        "Serato BeatGrid",
        beatgrid_payload(_dicts(spec.get("beatgrid")), int(spec["footer"])),
        True,
    )
    frame = _flac_frame()
    samples = 16
    info = struct.pack(">HH", samples, samples)
    info += len(frame).to_bytes(3, "big") + len(frame).to_bytes(3, "big")
    packed = (44100 << 44) | (15 << 36) | samples
    info += packed.to_bytes(8, "big") + hashlib.md5(b"\x00" * (samples * 2)).digest()
    comment = _vorbis_comment([("SERATO_MARKERS_V2", markers), ("SERATO_BEATGRID", grid)])
    stream = bytes([0x00]) + len(info).to_bytes(3, "big") + info
    last = bytes([0x84]) + len(comment).to_bytes(3, "big") + comment
    return b"fLaC" + stream + last + frame


def _atom(tag: bytes, body: bytes) -> bytes:
    """Encode one MP4 atom.

    Args:
        tag: Four-byte type.
        body: Payload.

    Returns:
        Size, type, and payload.
    """
    return struct.pack(">I", 8 + len(body)) + tag + body


def _freeform(name: str, text: str) -> bytes:
    """Encode one ``----:com.serato.dj`` atom.

    Args:
        name: Atom name such as ``markersv2``.
        text: Base64 field text.

    Returns:
        The freeform atom. The data atom uses type 1 (UTF-8).
    """
    mean = _atom(b"mean", b"\x00\x00\x00\x00" + b"com.serato.dj")
    title = _atom(b"name", b"\x00\x00\x00\x00" + name.encode("ascii"))
    data = _atom(b"data", b"\x00\x00\x00\x01\x00\x00\x00\x00" + text.encode("ascii"))
    return _atom(b"----", mean + title + data)


def _m4a(spec: dict[str, object]) -> bytes:
    """Build a tiny M4A with Serato freeform atoms and silent AAC.

    Args:
        spec: Marker spec.

    Returns:
        ftyp, mdat, and moov. ``markersv2`` is line-wrapped. ``beatgrid`` is not.
    """
    markers = _envelope("Serato Markers2", markers2_payload(spec), True)
    grid = _envelope(
        "Serato BeatGrid",
        beatgrid_payload(_dicts(spec.get("beatgrid")), int(spec["footer"])),
        False,
    )
    trak = bytearray(_TRAK)
    stco = trak.find(b"stco")
    trak[stco + 12 : stco + 16] = struct.pack(">I", len(_FTYP) + 8)
    ilst = _atom(b"ilst", _freeform("markersv2", markers) + _freeform("beatgrid", grid))
    hdlr = _atom(b"hdlr", b"\x00\x00\x00\x00\x00\x00\x00\x00mdirappl" + (b"\x00" * 12))
    meta = _atom(b"meta", b"\x00\x00\x00\x00" + hdlr + ilst)
    moov = _atom(b"moov", _MVHD + bytes(trak) + _atom(b"udta", meta))
    return _FTYP + _MDAT + moov


def _short_tag() -> bytes:
    """Build an ID3 tag whose Serato frames are too short to hold markers.

    Returns:
        A tag with a Markers2 header and a beatgrid that declares two
        markers without their bytes.
    """
    return id3_tag(
        [
            _geob("Serato Markers2", b"\x01\x01"),
            _geob("Serato BeatGrid", bytes([1, 0]) + (2).to_bytes(4, "big")),
        ]
    )


def _libraries() -> list[dict[str, object]]:
    """Return the two fixture libraries.

    Returns:
        Serato 4 and Serato 5 descriptions. Serato 5 uses the same published
        record layouts with different marker values. It does not add a Lucid
        grid or a Protect Library flag.
    """
    one = [{"position": 0.5, "bpm": 128.0}]
    several = [
        {"position": 0.0, "beats": 4},
        {"position": 2.0, "beats": 8},
        {"position": 6.0, "bpm": 174.0},
    ]
    return [
        _library(
            "serato4",
            "spec-derived",
            SERATO4_NOTE,
            "Caf\u00e9",
            "Music/caf\u00e9-loop.flac",
            one,
            several,
            "Drop",
            "End",
            "#CC0000",
            "#00CC66",
        ),
        _library(
            "serato5",
            "spec-derived, unverified",
            SERATO5_NOTE,
            "\u6df1\u591c",
            "Music/\u6df1\u591c-loop.flac",
            several,
            one,
            "Intro",
            "Break",
            "#FF8800",
            "#2244CC",
        ),
    ]


def _library(
    directory: str,
    status: str,
    note: str,
    nested_name: str,
    nested_path: str,
    mp3_grid: list[dict[str, object]],
    aiff_grid: list[dict[str, object]],
    first_cue: str,
    second_cue: str,
    first_color: str,
    second_color: str,
) -> dict[str, object]:
    """Assemble one version's crate rows and audio specs.

    Args:
        directory: ``serato4`` or ``serato5``.
        status: Manifest status for every file.
        note: Manifest note.
        nested_name: Unicode child crate name.
        nested_path: Path stored in the nested crate.
        mp3_grid: Beatgrid for the MP3 and the FLAC.
        aiff_grid: Beatgrid for the AIFF and the M4A.
        first_cue: Name of cue 0.
        second_cue: Name of cue 3.
        first_color: Color of cue 0.
        second_color: Color of cue 3.

    Returns:
        The library description consumed by ``build``.
    """
    flac_grid = mp3_grid
    m4a_grid = aiff_grid

    def audio(file: str, container: str, citation: str, grid: list[dict[str, object]], footer: int) -> dict[str, object]:
        return {
            "file": file,
            "container": container,
            "citation": f"{citation} {CITE_MARKERS} {CITE_GRID}",
            "cues": [
                {"index": 0, "start_ms": 1500, "color": first_color, "name": first_cue},
                {"index": 3, "start_ms": 8000, "color": second_color, "name": second_cue},
            ],
            "loops": [
                {
                    "index": 1,
                    "start_ms": 2000,
                    "end_ms": 8500,
                    "color": "#27AAE1",
                    "locked": True,
                    "name": "Break",
                }
            ],
            "flips": [{"index": 2, "enabled": True, "name": "Chop"}],
            "track_color": "#99FF99",
            "beatgrid_locked": False,
            "beatgrid": grid,
            "footer": footer,
        }

    posix_mp3 = "Music/one-grid.mp3" if directory == "serato4" else "Music/tempo.mp3"
    windows_aiff = "Music\\several-grid.aiff" if directory == "serato4" else "Music\\downbeat.aiff"
    posix_flac = nested_path
    posix_m4a = "Music/several-grid.m4a" if directory == "serato4" else "Music/anchor.m4a"
    missing = "Music/not-on-disk.mp3" if directory == "serato4" else "Music/absent.mp3"
    mp3_file = "audio/one-grid.mp3" if directory == "serato4" else "audio/tempo.mp3"
    aiff_file = "audio/several-grid.aiff" if directory == "serato4" else "audio/downbeat.aiff"
    flac_file = "audio/one-grid.flac" if directory == "serato4" else "audio/shifts.flac"
    m4a_file = "audio/several-grid.m4a" if directory == "serato4" else "audio/anchor.m4a"
    footer_mp3 = 0x00 if len(mp3_grid) == 1 else 0x37
    footer_aiff = 0x00 if len(aiff_grid) == 1 else 0x37
    tracks = [
        {"path": posix_mp3, "type": "mp3", "title": first_cue, "artist": "Fixture", "bpm": "128.00", "missing": False, "audio": mp3_file},
        {"path": windows_aiff, "type": "aiff", "title": second_cue, "artist": "Fixture", "bpm": "174.00", "missing": False, "audio": aiff_file},
        {"path": posix_flac, "type": "flac", "title": nested_name, "artist": "Fixture", "bpm": "128.00", "missing": False, "audio": flac_file},
        {"path": posix_m4a, "type": "mp4", "title": "Anchor", "artist": "Fixture", "bpm": "140.00", "missing": False, "audio": m4a_file},
        {"path": missing, "type": "mp3", "title": "Missing", "artist": "Fixture", "bpm": "0.00", "missing": True, "audio": None},
        {"type": "mp3", "title": "No Path", "artist": "Fixture", "bpm": "0.00", "missing": False, "audio": None},
    ]
    return {
        "dir": directory,
        "status": status,
        "note": note,
        "tracks": tracks,
        "crates": [
            {
                "file": "_Serato_/Subcrates/House.crate",
                "paths": [posix_mp3, windows_aiff, posix_m4a, missing, None],
            },
            {
                "file": f"_Serato_/Subcrates/House%%{nested_name}.crate",
                "paths": [posix_flac],
            },
            {"file": "_Serato_/Subcrates/Empty.crate", "paths": []},
        ],
        "unmounted": {
            "crate": "drives/UNMOUNTED/_Serato_/Subcrates/Gig.crate",
            "database": "drives/UNMOUNTED/_Serato_/database V2",
            "paths": ["Music/gig-opener.mp3", "Music\\gig-closer.aiff"],
        },
        "audio": [
            audio(mp3_file, "mp3", CITE_MP3, mp3_grid, footer_mp3),
            audio(aiff_file, "aiff", CITE_AIFF, aiff_grid, footer_aiff),
            audio(flac_file, "flac", CITE_FLAC, flac_grid, footer_mp3),
            audio(m4a_file, "m4a", CITE_M4A, m4a_grid, footer_aiff),
        ],
    }


def _write_text(path: Path, text: str) -> None:
    """Write UTF-8 text with LF line endings.

    Args:
        path: Destination.
        text: Text. Newlines are LF on every platform so a Windows rebuild
            matches the committed files.

    Returns:
        None.
    """
    path.write_text(text, encoding="utf-8", newline="\n")


def _sha256(data: bytes) -> str:
    """Return the hex SHA-256 of ``data``.

    Args:
        data: File bytes.

    Returns:
        The digest.
    """
    return hashlib.sha256(data).hexdigest()


def _write(path: Path, data: bytes) -> dict[str, object]:
    """Write one fixture and describe it.

    Args:
        path: Destination. Parents are created.
        data: Bytes.

    Returns:
        Path, size, and sha256 relative to the library root's parent. The
        caller fills role, status, and citation.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {"bytes": len(data), "sha256": _sha256(data)}


def _write_drive_check(root: Path) -> None:
    """Write the portable-drive tree the drive check reads.

    Args:
        root: Fixture directory. The tree is ``drive_check/GIGDRIVE``.

    Returns:
        None. Audio placeholders are a few bytes. Unsafe names are stored
        in the crate, not used as file names.
    """
    drive = root / "drive_check" / "GIGDRIVE"
    serato = drive / "_Serato_"
    for name in (
        "on-drive.mp3",
        "peak-win.mp3",
        "concert.mp3",
        "COM10.mp3",
        "only-in-database.mp3",
    ):
        _write(drive / "Music" / name, b"fixture\n")
    _write(serato / "Subcrates" / "House.crate", crate_bytes(DRIVE_CHECK_HOUSE))
    _write(serato / "Subcrates" / "House%%Peak.crate", crate_bytes(DRIVE_CHECK_PEAK))
    _write(
        serato / "Subcrates" / "Export Backups-extra" / "Keep.crate",
        crate_bytes(DRIVE_CHECK_KEEP),
    )
    _write(serato / "SmartCrates" / "Warmup.scrate", crate_bytes(DRIVE_CHECK_SMART))
    _write(serato / "Export Backups" / "Subcrates" / "Skip.crate", crate_bytes(DRIVE_CHECK_EXPORT_BACKUP))
    _write(serato / "Lexicon" / "Subcrates" / "Skip.crate", crate_bytes(DRIVE_CHECK_LEXICON))
    _write(
        serato / "database V2",
        database_bytes(
            [
                {
                    "path": DRIVE_CHECK_DATABASE_ONLY,
                    "title": "Database",
                    "artist": "Fixture",
                    "type": "mp3",
                    "bpm": "0.00",
                    "missing": False,
                }
            ]
        ),
    )


def build(root: Path) -> None:
    """Write both fixture trees, the drive-check drive, their goldens, and the README.

    Args:
        root: Directory that will contain ``serato4``, ``serato5``,
            ``drive_check``, and ``README.md``. Existing fixture files are replaced.

    Returns:
        None.
    """
    root = Path(root)
    readme_rows: list[dict[str, str]] = []
    for library in _libraries():
        directory = root / str(library["dir"])
        status = str(library["status"])
        files: list[dict[str, object]] = []
        tracks = [item for item in library["tracks"] if isinstance(item, dict)]
        database = database_bytes(tracks)
        info = _write(directory / "_Serato_" / "database V2", database)
        files.append({**info, "path": "_Serato_/database V2", "role": "database-v2", "status": status, "citation": CITE_DATABASE})
        golden_crates: list[dict[str, object]] = []
        crates = library["crates"]
        if isinstance(crates, list):
            for crate in crates:
                if not isinstance(crate, dict):
                    continue
                rel = str(crate["file"])
                paths = crate["paths"] if isinstance(crate["paths"], list) else []
                encoded = crate_bytes([path if isinstance(path, str) else None for path in paths])
                info = _write(directory / rel, encoded)
                files.append({**info, "path": rel, "role": "crate", "status": status, "citation": CITE_CRATE})
                filename = Path(rel).name
                parents, name = _crate_parts(filename)
                golden_crates.append(
                    {
                        "file": rel,
                        "name": name,
                        "parents": parents,
                        "version": CRATE_VERSION,
                        "tracks": [{"path": path} for path in paths],
                    }
                )
        unmounted = library["unmounted"]
        gig_paths: list[str] = []
        if isinstance(unmounted, dict):
            gig_paths = [str(path) for path in unmounted["paths"] if isinstance(path, str)]
            gig = crate_bytes(gig_paths)
            gig_rel = str(unmounted["crate"])
            info = _write(directory / gig_rel, gig)
            files.append({**info, "path": gig_rel, "role": "crate", "status": status, "citation": CITE_CRATE})
            gig_tracks = [
                {"path": path, "type": "mp3", "title": "Gig", "artist": "Fixture", "bpm": "128.00", "missing": False}
                for path in gig_paths
            ]
            info = _write(directory / str(unmounted["database"]), database_bytes(gig_tracks))
            files.append(
                {
                    **info,
                    "path": str(unmounted["database"]),
                    "role": "database-v2",
                    "status": status,
                    "citation": CITE_DATABASE,
                }
            )
        audio_golden: list[dict[str, object]] = []
        builders = {"mp3": _mp3, "aiff": _aiff, "flac": _flac, "m4a": _m4a}
        for spec in library["audio"] if isinstance(library["audio"], list) else []:
            if not isinstance(spec, dict):
                continue
            encoded = builders[str(spec["container"])](spec)
            rel = str(spec["file"])
            info = _write(directory / rel, encoded)
            files.append({**info, "path": rel, "role": "audio", "status": status, "citation": str(spec["citation"])})
            audio_golden.append({key: spec[key] for key in spec if key != "citation"})
        house = directory / "_Serato_" / "Subcrates" / "House.crate"
        # The last record is an 8-byte empty otrk. Cutting past it lands
        # inside the previous path so the file is actually truncated.
        truncated = house.read_bytes()[:-24]
        info = _write(directory / "edge" / "truncated.crate", truncated)
        files.append({**info, "path": "edge/truncated.crate", "role": "edge", "status": status, "citation": CITE_CRATE})
        info = _write(directory / "edge" / "truncated-tags.mp3", _short_tag() + _mp3_frames())
        files.append({**info, "path": "edge/truncated-tags.mp3", "role": "edge", "status": status, "citation": CITE_MP3})
        info = _write(directory / "edge" / "cut-header.mp3", b"ID3\x04\x00\x00")
        files.append({**info, "path": "edge/cut-header.mp3", "role": "edge", "status": status, "citation": CITE_MP3})
        golden = {
            "version": str(library["dir"]),
            "status": status,
            "database": {"version": DATABASE_VERSION, "tracks": [_public_track(item) for item in tracks]},
            "crates": golden_crates,
            "unmounted": {
                "root": "drives/UNMOUNTED",
                "crate": "drives/UNMOUNTED/_Serato_/Subcrates/Gig.crate",
                "version": CRATE_VERSION,
                "tracks": gig_paths,
            },
            "audio": audio_golden,
        }
        _write_text(directory / "golden.json", json.dumps(golden, indent=2, ensure_ascii=False) + "\n")
        manifest = {"version": str(library["dir"]), "status": status, "note": str(library["note"]), "files": files}
        _write_text(directory / "manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
        for item in files:
            readme_rows.append(
                {
                    "version": str(library["dir"]),
                    "path": str(item["path"]),
                    "status": status,
                    "citation": str(item["citation"]),
                }
            )
    _write_drive_check(root)
    _write_text(root / "README.md", _readme(readme_rows))


def _crate_parts(filename: str) -> tuple[list[str], str]:
    """Split a crate filename into parents and a leaf name.

    Args:
        filename: Base name ending in ``.crate``.

    Returns:
        Parents and the leaf.
    """
    stem = filename[:-6] if filename.endswith(".crate") else filename
    parts = stem.split("%%")
    return parts[:-1], parts[-1]


def _public_track(track: dict[str, object]) -> dict[str, object]:
    """Copy a database row for the golden file.

    Args:
        track: Builder track, which may point at a fixture audio file.

    Returns:
        The fields a reader should recover. The fixture filename is omitted.
    """
    row: dict[str, object] = {
        "title": track.get("title"),
        "artist": track.get("artist"),
        "bpm": track.get("bpm"),
        "type": track.get("type"),
        "missing": bool(track.get("missing")),
        "path": track.get("path"),
    }
    return row


def _readme(rows: list[dict[str, str]]) -> str:
    """Render the fixture README.

    Args:
        rows: One dict per written file.

    Returns:
        Markdown. Each file cites the note it was built from.
    """
    lines = [
        "# Serato format fixtures",
        "",
        "Tiny libraries for tests. They are built by `tests/fixtures/build_fixtures.py`",
        "from the published Serato notes, not from this repository's tag code.",
        "",
        "Regenerate with:",
        "",
        "```bash",
        "python3 tests/fixtures/build_fixtures.py",
        "```",
        "",
        "Serato 4 entries are `spec-derived` (the Scratch Live compatibility export).",
        "Serato 5 entries are `spec-derived, unverified`. Lucid/Flexible beatgrids and",
        "Protect Library are omitted because their storage is unknown until Byte Beat's",
        "`serato5-probe.sh` runs on a real Serato 5 install.",
        "",
        "| Tree | File | Status | Citation |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        citation = row["citation"].replace("|", "\\|")
        lines.append(f"| `{row['version']}` | `{row['path']}` | {row['status']} | {citation} |")
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- `database V2` and `.crate` files are the legacy chunk format: a 4-byte tag,",
            "  a big-endian length, and UTF-16BE text for `vrsn`, `pfil`, and `ptrk`.",
            "- A nested crate is a second file. Parents and the leaf are joined with `%%`.",
            "- Markers2 and BeatGrid inside MP3 and AIFF are ID3v2.4 GEOB frames.",
            "- FLAC stores the same payloads as base64 Vorbis comments.",
            "- M4A stores them as `----` atoms with mean `com.serato.dj`.",
            "- `edge/truncated.crate` and `edge/truncated-tags.mp3` are cut on purpose.",
            "- `edge/cut-header.mp3` is an ID3 header that stops early.",
            "- `drives/UNMOUNTED` is a crate for a volume the tests do not mount.",
            "- `drive_check/GIGDRIVE` is a portable drive for the read-only drive check.",
            "  Unsafe FAT names are inside the crate bytes, not file names.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    """Write the fixtures next to this script."""
    build(Path(__file__).resolve().parent)


if __name__ == "__main__":
    main()
