"""Parser tests for Serato GEOB frames and for FLAC and M4A markers."""

from __future__ import annotations

import base64
import struct
import tempfile
import unittest
from pathlib import Path

from tests.fixture import ROOT
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tags import (
    _TAG_LIMIT,
    _parse_beatgrid,
    _parse_cue,
    _parse_markers2,
    copy_serato_geob,
    plan_serato_geob,
    read_serato_tags,
    serato_tags_from_regions,
)


def _entry(kind: str, blob: bytes) -> bytes:
    """Wrap one Markers2 record as a name, a length, and a payload.

    The name is ASCII and NUL-terminated. The length is a 4-byte big-endian
    count of ``blob``. This builds bytes the parser reads. It does not write
    an audio file.

    Args:
        kind: Entry name such as ``CUE``, ``LOOP``, or ``FLIP``.
        blob: Record payload.

    Returns:
        The encoded entry.
    """
    return kind.encode("ascii") + b"\x00" + len(blob).to_bytes(4, "big") + blob


def _cue(index: int, start_ms: int, color: bytes, name: str) -> bytes:
    """Build a CUE record with the offsets ``_parse_cue`` expects.

    Byte 1 is the index, bytes 2-5 the start in milliseconds, bytes 7-9 the
    RGB color, and the UTF-8 name begins at byte 12.

    Args:
        index: Cue index stored at byte 1.
        start_ms: Start time in milliseconds.
        color: Three RGB bytes.
        name: UTF-8 cue name.

    Returns:
        The record bytes. No file is written.
    """
    raw = bytearray(13 + len(name))
    raw[1] = index
    raw[2:6] = start_ms.to_bytes(4, "big")
    raw[7:10] = color
    raw[12:] = name.encode("utf-8") + b"\x00"
    return bytes(raw)


def _loop(index: int, start_ms: int, end_ms: int, locked: bool, name: str) -> bytes:
    """Build a LOOP record with the offsets ``_parse_loop`` expects.

    Bytes 2-5 and 6-9 are the start and end. Bytes 15-17 are RGB, byte 19
    is the lock flag, and the name begins at byte 20.

    Args:
        index: Loop index.
        start_ms: Loop start in milliseconds.
        end_ms: Loop end in milliseconds.
        locked: True stores a lock flag of 1.
        name: UTF-8 loop name.

    Returns:
        The record bytes. No file is written.
    """
    raw = bytearray(21 + len(name))
    raw[1] = index
    raw[2:6] = start_ms.to_bytes(4, "big")
    raw[6:10] = end_ms.to_bytes(4, "big")
    raw[15:18] = b"\x00\x11\x22"
    raw[19] = 1 if locked else 0
    raw[20:] = name.encode("utf-8") + b"\x00"
    return bytes(raw)


def _flip(index: int, enabled: bool, name: str) -> bytes:
    """Build a FLIP record with the offsets ``_parse_flip`` expects.

    Byte 1 is the index, byte 2 is the enabled flag, and the UTF-8 name follows.

    Args:
        index: Flip index.
        enabled: True stores an enabled flag of 1.
        name: UTF-8 flip name.

    Returns:
        The record bytes. No file is written.
    """
    return bytes([0, index, 1 if enabled else 0]) + name.encode("utf-8") + b"\x00"


def _markers_payload() -> bytes:
    """Encode a cue, a loop, and a flip as a Markers2 GEOB body.

    The body starts with the ``01 01`` header and a base64 body, which is
    the layout ``read_serato_tags`` decodes. No audio file is written.

    Returns:
        The Markers2 payload bytes.
    """
    decoded = _entry("CUE", _cue(3, 1500, b"\xCC\x00\x00", "Drop"))
    decoded += _entry("LOOP", _loop(1, 2000, 4000, True, "Break"))
    decoded += _entry("FLIP", _flip(2, True, "Chop"))
    return b"\x01\x01" + base64.b64encode(decoded)


def _beatgrid_payload() -> bytes:
    """Encode a two-marker beatgrid at version 1.

    The first marker stores a beat count. The last marker stores BPM.
    Positions and BPM are big-endian floats, matching ``_parse_beatgrid``.

    Returns:
        The BeatGrid payload bytes. No audio file is written.
    """
    body = bytes([1, 0]) + (2).to_bytes(4, "big")
    body += struct.pack(">f", 0.5) + (4).to_bytes(4, "big")
    body += struct.pack(">f", 10.0) + struct.pack(">f", 128.0)
    return body


def _id3_file(payload: bytes, path: Path) -> None:
    """Write a tiny ID3v2.3 file that holds one Serato Markers2 frame.

    The tag size is synchsafe. The frame size is a plain big-endian length,
    which is the ID3v2.3 rule. The file is a fixture, not a playable track.

    Args:
        payload: Markers2 bytes stored in the GEOB frame.
        path: File to create or replace.

    Returns:
        None.
    """
    description = b"Serato Markers2\x00"
    body = bytes([0]) + b"application/octet-stream\x00" + b"\x00" + description + payload
    frame = b"GEOB" + len(body).to_bytes(4, "big") + b"\x00\x00" + body
    size = len(frame)
    synchsafe = bytes(
        (
            (size >> 21) & 0x7F,
            (size >> 14) & 0x7F,
            (size >> 7) & 0x7F,
            size & 0x7F,
        )
    )
    path.write_bytes(b"ID3" + bytes([3, 0, 0]) + synchsafe + frame)


class TagTests(unittest.TestCase):
    """Parse cue, loop, flip, and beatgrid bytes without a live library.

    The cases use fixtures built in this module. They do not open
    ``master.sqlite`` or rewrite a real audio file.
    """
    def test_missing_path_is_empty(self) -> None:
        """Return an empty result when no audio path is given.

        ``read_serato_tags`` must not touch the filesystem for ``None``.

        Returns:
            None. The test fails if a cue is reported or ``found`` is true.
        """
        parsed = read_serato_tags(None)
        self.assertFalse(parsed["found"])
        self.assertEqual(parsed["cues"], [])

    def test_markers_round_trip(self) -> None:
        """Decode the cue, loop, and flip built by the fixture helpers.

        Confirms index, color, times, the lock flag, and names. No file is read.

        Returns:
            None. The test fails if a field moves to the wrong offset.
        """
        parsed = _parse_markers2(_markers_payload())
        self.assertEqual(parsed["cues"][0]["name"], "Drop")
        self.assertEqual(parsed["cues"][0]["start_ms"], 1500)
        self.assertEqual(parsed["cues"][0]["color"], "#CC0000")
        self.assertEqual(parsed["loops"][0]["end_ms"], 4000)
        self.assertTrue(parsed["loops"][0]["locked"])
        self.assertEqual(parsed["loops"][0]["color"], "#001122")
        self.assertEqual(parsed["flips"][0]["name"], "Chop")
        self.assertTrue(parsed["flips"][0]["enabled"])

    def test_short_cue_is_ignored(self) -> None:
        """Ignore a CUE record shorter than the fixed header.

        A five-byte blob cannot hold an index, a time, and a color. The parser
        returns ``None`` instead of inventing a cue.

        Returns:
            None. The test fails if a short record is accepted.
        """
        self.assertIsNone(_parse_cue(b"\x00" * 5))

    def test_beatgrid_markers(self) -> None:
        """Read a beat count from the first marker and BPM from the last.

        Uses the version-1 payload. No file is read.

        Returns:
            None. The test fails if the two marker roles are swapped.
        """
        markers = _parse_beatgrid(_beatgrid_payload())
        self.assertEqual(markers[0].get("beats"), 4)
        self.assertEqual(markers[1].get("bpm"), 128.0)
        self.assertEqual(markers[0]["position"], 0.5)

    def test_beatgrid_position_keeps_the_stored_float(self) -> None:
        """Keep a position that three-decimal rounding would change.

        The Rekordbox export divides by this float. Rounding it first
        changes the BPM.

        Returns:
            None. The test fails if the position is rounded to three decimals.
        """
        raw = struct.pack(">f", 1.23456)
        position = struct.unpack(">f", raw)[0]
        body = bytes([1, 0]) + (1).to_bytes(4, "big") + raw + struct.pack(">f", 128.0)
        markers = _parse_beatgrid(body)
        self.assertEqual(markers[0]["position"], position)
        self.assertNotEqual(markers[0]["position"], round(position, 3))
        self.assertEqual(markers[0].get("bpm"), 128.0)

    def test_bad_beatgrid_is_empty(self) -> None:
        """Reject an unknown version, too many markers, and a short payload.

        Version byte 2 is ignored. More than 4096 markers is rejected. A count
        that asks for bytes the payload does not contain returns an empty list.

        Returns:
            None. The test fails if any of those payloads yields a marker.
        """
        self.assertEqual(_parse_beatgrid(b"\x02\x00\x00\x00\x00\x01"), [])
        huge = bytes([1, 0]) + (4097).to_bytes(4, "big")
        self.assertEqual(_parse_beatgrid(huge), [])
        short = bytes([1, 0]) + (2).to_bytes(4, "big") + struct.pack(">f", 1.0)
        self.assertEqual(_parse_beatgrid(short), [])

    def test_bad_markers_base64_is_empty(self) -> None:
        """Return no cues when the Markers2 body is not base64.

        The ``01 01`` header is present, but the rest does not decode. No file
        is read.

        Returns:
            None. The test fails if a cue, loop, or flip is returned.
        """
        parsed = _parse_markers2(b"\x01\x01@")
        self.assertEqual(parsed["cues"], [])
        self.assertEqual(parsed["loops"], [])
        self.assertEqual(parsed["flips"], [])

    def test_file_header_is_read(self) -> None:
        """Read a Markers2 frame from the front of an ID3 file.

        Writes a temporary file and parses it. The file is removed with the
        temporary directory. The Serato library database is not involved.

        Returns:
            None. The test fails if the cue index is not recovered.
        """
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "track.mp3"
            _id3_file(_markers_payload(), path)
            parsed = read_serato_tags(str(path))
        self.assertTrue(parsed["found"])
        self.assertEqual(parsed["cues"][0]["index"], 3)


def _text_frame(frame_id: bytes, text: str) -> bytes:
    """Build one Latin-1 ID3v2.3 text frame.

    Args:
        frame_id: Four-byte frame name, such as ``TIT2``.
        text: Frame text.

    Returns:
        The raw frame, including its header.
    """
    body = b"\x00" + text.encode("latin-1")
    return frame_id + len(body).to_bytes(4, "big") + b"\x00\x00" + body


def _tag_file(frames: bytes, audio: bytes, path: Path) -> None:
    """Write a plain ID3v2.3 tag and an audio tail.

    Args:
        frames: Raw frames, concatenated.
        audio: Bytes that must survive a cue copy.
        path: File to create.

    Returns:
        None.
    """
    size = len(frames)
    synchsafe = bytes(
        (
            (size >> 21) & 0x7F,
            (size >> 14) & 0x7F,
            (size >> 7) & 0x7F,
            size & 0x7F,
        )
    )
    path.write_bytes(b"ID3" + bytes([3, 0, 0]) + synchsafe + frames + audio)


class CueCopyTests(unittest.TestCase):
    """Serato frames are copied only when the destination tag can take them."""

    def test_copy_keeps_other_frames_and_the_audio(self) -> None:
        """Copy Markers2 onto a tagged file and leave its title and audio.

        The destination starts with a TIT2 frame and a distinctive tail.
        After the copy, the cue index is readable, the title text is still
        in the file, and the tail is still the last bytes. Temporary tag
        files are removed.

        Returns:
            None. The test fails if the audio tail or the title moves.
        """
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "old.mp3"
            dest = root / "new.mp3"
            _id3_file(_markers_payload(), source)
            source.write_bytes(source.read_bytes() + b"SOURCE-AUDIO")
            _tag_file(_text_frame(b"TIT2", "Hello"), b"DEST-AUDIO", dest)
            before_title = dest.read_bytes()
            result = copy_serato_geob(source, dest)
            copied = dest.read_bytes()
            leftovers = list(root.glob(".serato-cue*"))
            parsed = read_serato_tags(str(dest))
        self.assertEqual(result["status"], "copied")
        self.assertNotIn("/", result["detail"])
        self.assertTrue(copied.endswith(b"DEST-AUDIO"))
        self.assertIn(b"Hello", copied)
        self.assertNotEqual(copied, before_title)
        self.assertTrue(parsed["found"])
        self.assertEqual(parsed["cues"][0]["index"], 3)
        self.assertEqual(leftovers, [])

    def test_existing_serato_frames_are_left_alone(self) -> None:
        """Leave a destination that already has Serato frames unchanged.

        Both files carry Markers2. The copy reports kept and the
        destination bytes stay identical.

        Returns:
            None. The test fails if the destination is rewritten.
        """
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "old.mp3"
            dest = root / "new.mp3"
            _id3_file(_markers_payload(), source)
            _id3_file(_markers_payload(), dest)
            dest.write_bytes(dest.read_bytes() + b"KEEP")
            before = dest.read_bytes()
            result = copy_serato_geob(source, dest)
            self.assertEqual(result["status"], "kept")
            self.assertEqual(dest.read_bytes(), before)

    def test_flac_is_not_rewritten(self) -> None:
        """Refuse a FLAC destination and leave its bytes in place.

        Returns:
            None. The test fails if the FLAC file changes.
        """
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "old.mp3"
            dest = root / "new.flac"
            _id3_file(_markers_payload(), source)
            payload = b"fLaC" + b"\x00" * 12
            dest.write_bytes(payload)
            result = plan_serato_geob(source, dest)
            copied = copy_serato_geob(source, dest)
            self.assertEqual(result["status"], "unsupported")
            self.assertEqual(copied["status"], "unsupported")
            self.assertEqual(dest.read_bytes(), payload)

    def test_mp3_without_a_tag_can_receive_one(self) -> None:
        """Prepend an ID3v2.3 tag to an MP3 that has none.

        The audio bytes stay at the end of the file.

        Returns:
            None. The test fails if the cue is missing or the audio moves.
        """
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "old.mp3"
            dest = root / "new.mp3"
            _id3_file(_markers_payload(), source)
            dest.write_bytes(b"MPEG-AUDIO")
            result = copy_serato_geob(source, dest)
            self.assertEqual(result["status"], "copied")
            self.assertTrue(dest.read_bytes().endswith(b"MPEG-AUDIO"))
            self.assertTrue(read_serato_tags(str(dest))["found"])

    def test_a_shortcut_is_not_rewritten(self) -> None:
        """Refuse a destination that is a shortcut to another file.

        Returns:
            None. The test fails if the target bytes change. The test is
            skipped when this user cannot create a shortcut.
        """
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "old.mp3"
            target = root / "target.mp3"
            link = root / "link.mp3"
            _id3_file(_markers_payload(), source)
            target.write_bytes(b"UNTOUCHED")
            try:
                link.symlink_to(target)
            except OSError:
                self.skipTest("This user cannot create shortcuts.")
            result = plan_serato_geob(source, link)
            self.assertEqual(result["status"], "unsupported")
            self.assertEqual(target.read_bytes(), b"UNTOUCHED")


def _serato_b64(frame_name: str, payload: bytes, *, wrap: bool) -> bytes:
    """Base64-encode one Serato envelope the way FLAC and MP4 store it.

    The envelope is ``application/octet-stream``, two nulls, the frame name,
    a null, and the payload. Padding is omitted. Markers values can also
    insert a newline every 72 characters.

    Args:
        frame_name: Name stored in the envelope, such as ``Serato Markers2``.
        payload: GEOB payload the shared parser already accepts.
        wrap: True inserts a newline every 72 characters.

    Returns:
        The unpadded base64 text. No audio file is written.
    """
    raw = b"application/octet-stream\x00\x00" + frame_name.encode("ascii") + b"\x00" + payload
    encoded = base64.b64encode(raw).rstrip(b"=")
    if not wrap:
        return encoded
    return b"\n".join(encoded[index:index + 72] for index in range(0, len(encoded), 72))


def _flac_block(block_type: int, data: bytes, last: bool) -> bytes:
    """Build one FLAC metadata block header and body.

    Args:
        block_type: Block type. 0 is streaminfo and 4 is the Vorbis comment.
        data: Block body.
        last: True sets the last-block flag.

    Returns:
        The encoded block. No audio file is written.
    """
    header = (0x80 if last else 0) | block_type
    return bytes([header]) + len(data).to_bytes(3, "big") + data


def _vorbis_comment(comments: list[bytes]) -> bytes:
    """Build a Vorbis comment block with a fixed vendor string.

    Lengths are little-endian.

    Args:
        comments: ``KEY=value`` bytes, already encoded.

    Returns:
        The comment block body. No audio file is written.
    """
    vendor = b"qa-fix"
    body = struct.pack("<I", len(vendor)) + vendor + struct.pack("<I", len(comments))
    for comment in comments:
        body += struct.pack("<I", len(comment)) + comment
    return body


def _write_flac(path: Path, comments: list[bytes]) -> None:
    """Write a tiny FLAC whose Vorbis comment holds ``comments``.

    The streaminfo block is 34 zero bytes. The bytes after the metadata are
    not a playable frame. The file is a fixture.

    Args:
        path: File to create or replace.
        comments: Vorbis comments, including any ``SERATO_*`` field.

    Returns:
        None.
    """
    blocks = _flac_block(0, bytes(34), False)
    blocks += _flac_block(4, _vorbis_comment(comments), True)
    path.write_bytes(b"fLaC" + blocks + b"\xff\xf8" + bytes(32))


def _atom(kind: bytes, body: bytes) -> bytes:
    """Build one 32-bit MP4 atom.

    Args:
        kind: Four-byte atom type.
        body: Atom body.

    Returns:
        The size, type, and body. No audio file is written.
    """
    return struct.pack(">I", 8 + len(body)) + kind + body


def _freeform(name: str, value: bytes, *, null_terminate: bool) -> bytes:
    """Build one ``----:com.serato.dj`` freeform atom.

    Args:
        name: Atom name, such as ``markersv2`` or ``beatgrid``.
        value: Base64 text stored after the data atom's type and locale.
        null_terminate: True appends a null to the mean and the name, which
            is the layout of a real file. False matches a fixture that omits it.

    Returns:
        The freeform atom. No audio file is written.
    """
    suffix = b"\x00" if null_terminate else b""
    return _atom(
        b"----",
        _atom(b"mean", bytes(4) + b"com.serato.dj" + suffix)
        + _atom(b"name", bytes(4) + name.encode("ascii") + suffix)
        + _atom(b"data", struct.pack(">II", 1, 0) + value),
    )


def _write_m4a(path: Path, items: bytes) -> None:
    """Write a tiny M4A whose ``ilst`` holds ``items``.

    Args:
        path: File to create or replace.
        items: Concatenated freeform atoms, or empty.

    Returns:
        None.
    """
    meta = _atom(
        b"meta",
        bytes(4)
        + _atom(b"hdlr", bytes(8) + b"mdir" + bytes(13))
        + _atom(b"ilst", items),
    )
    moov = _atom(b"moov", _atom(b"udta", meta))
    path.write_bytes(
        _atom(b"ftyp", b"M4A \x00\x00\x00\x00M4A isom")
        + moov
        + _atom(b"mdat", bytes(16))
    )


def serato_b64(frame_name: str, payload: bytes, *, wrap: bool) -> bytes:
    """Encode one Serato envelope for a fixture another test module can call.

    Args:
        frame_name: Name stored in the envelope.
        payload: GEOB payload.
        wrap: True inserts a newline every 72 characters.

    Returns:
        The unpadded base64 text.
    """
    return _serato_b64(frame_name, payload, wrap=wrap)


def write_flac_fixture(path: Path, comments: list[bytes]) -> None:
    """Write a tiny FLAC fixture for a test outside this module.

    Args:
        path: File to create or replace.
        comments: Vorbis comments.
    """
    _write_flac(path, comments)


def freeform_atom(name: str, value: bytes, *, null_terminate: bool) -> bytes:
    """Build one Serato freeform atom for a test outside this module.

    Args:
        name: Atom name, such as ``overview``.
        value: Data bytes.
        null_terminate: True appends a null after the name.

    Returns:
        The atom bytes.
    """
    return _freeform(name, value, null_terminate=null_terminate)


def write_m4a_fixture(path: Path, items: bytes) -> None:
    """Write a tiny M4A fixture for a test outside this module.

    Args:
        path: File to create or replace.
        items: Concatenated freeform atoms.
    """
    _write_m4a(path, items)


def _line_wrapped_markers() -> bytes:
    """Build a Markers2 body with Serato's inner newline wrapping.

    The base64 replaces ``=`` with ``A``, inserts a newline every 72
    characters, and is padded with nulls. A ``COLOR`` entry and a
    ``BPMLOCK`` entry sit beside the cue so an unknown entry does not hide it.

    Returns:
        The GEOB payload. No audio file is written.
    """
    inner = b"\x01\x01" + _entry("COLOR", bytes([0, 0x99, 0xFF, 0x99]))
    inner += _entry("BPMLOCK", bytes([1]))
    inner += _entry("CUE", _cue(3, 1500, b"\xCC\x00\x00", "Drop"))
    inner += _entry("LOOP", _loop(1, 2000, 4000, True, "Break"))
    inner += _entry("FLIP", _flip(2, True, "Chop"))
    text = base64.b64encode(inner).replace(b"=", b"A")
    wrapped = b"\n".join(text[index:index + 72] for index in range(0, len(text), 72))
    return (b"\x01\x01" + wrapped).ljust(470, b"\x00")


class FlacM4aMarkerTests(unittest.TestCase):
    """Serato blocks in FLAC and M4A are read, and those files are not rewritten.

    The fixtures are built in memory. They are not playable audio and they
    are not copied from a Serato library.
    """

    def _assert_markers(self, parsed: dict[str, object], suffix: str) -> None:
        """Assert the shared cue, loop, flip, and color fields.

        Args:
            parsed: Result of ``read_serato_tags``.
            suffix: File suffix used in the failure text.

        Returns:
            None. The test fails when a marker is missing or duplicated.
        """
        self.assertTrue(parsed["found"], f"Serato markers in {suffix} not detected")
        self.assertEqual(
            parsed["cues"],
            [{"index": 3, "start_ms": 1500, "color": "#CC0000", "name": "Drop"}],
        )
        self.assertEqual(
            parsed["loops"],
            [{
                "index": 1,
                "start_ms": 2000,
                "end_ms": 4000,
                "color": "#001122",
                "locked": True,
                "name": "Break",
            }],
        )
        self.assertEqual(
            parsed["flips"],
            [{"index": 2, "enabled": True, "name": "Chop"}],
        )

    def test_flac_markers_are_read(self) -> None:
        """Read cues, loops, flips, and cue color from a FLAC Vorbis comment.

        The comment is ``SERATO_MARKERS_V2`` with the padding characters
        removed. A title comment is present as well. The file bytes are
        unchanged after the read.

        Returns:
            None. The test fails when the cue color or the file bytes change.
        """
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "cues.flac"
            value = _serato_b64("Serato Markers2", _markers_payload(), wrap=False)
            _write_flac(path, [b"TITLE=t", b"SERATO_MARKERS_V2=" + value])
            before = path.read_bytes()
            parsed = read_serato_tags(str(path))
            self.assertEqual(path.read_bytes(), before)
        self._assert_markers(parsed, ".flac")

    def test_m4a_markers_are_read(self) -> None:
        """Read cues, loops, flips, and cue color from an M4A freeform atom.

        The atom mean is ``com.serato.dj`` and the name is ``markersv2``.
        The data is the same unpadded base64 a FLAC comment stores.

        Returns:
            None. The test fails when the markers are missing or the file changes.
        """
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "cues.m4a"
            value = _serato_b64("Serato Markers2", _markers_payload(), wrap=False)
            _write_m4a(path, _freeform("markersv2", value, null_terminate=False))
            before = path.read_bytes()
            parsed = read_serato_tags(str(path))
            self.assertEqual(path.read_bytes(), before)
        self._assert_markers(parsed, ".m4a")

    def test_mp4_markers_are_read(self) -> None:
        """Read the same atom when the file name ends in ``.mp4``.

        Returns:
            None. The test fails when the suffix hides the markers.
        """
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "cues.mp4"
            value = _serato_b64("Serato Markers2", _markers_payload(), wrap=False)
            _write_m4a(path, _freeform("markersv2", value, null_terminate=False))
            parsed = read_serato_tags(str(path))
        self._assert_markers(parsed, ".mp4")

    def test_line_wrapped_blocks_keep_cue_color(self) -> None:
        """Read markers when the base64 is wrapped and the names are null-terminated.

        FLAC inserts a newline every 72 characters. The M4A mean and name end
        with a null. The inner Markers2 body also uses Serato's newline
        wrapping, an ``A`` in place of ``=``, and a track ``COLOR`` entry.

        Returns:
            None. The test fails when either file drops the cue color.
        """
        payload = _line_wrapped_markers()
        value = _serato_b64("Serato Markers2", payload, wrap=True)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            flac = root / "wrapped.flac"
            m4a = root / "wrapped.m4a"
            _write_flac(flac, [b"serato_markers_v2=" + value])
            _write_m4a(m4a, _freeform("markersv2", value, null_terminate=True))
            flac_parsed = read_serato_tags(str(flac))
            m4a_parsed = read_serato_tags(str(m4a))
        self._assert_markers(flac_parsed, ".flac")
        self.assertEqual(flac_parsed["loops"][0]["name"], "Break")
        self._assert_markers(m4a_parsed, ".m4a")

    def test_beatgrid_is_read_from_flac_and_m4a(self) -> None:
        """Read a beatgrid when the file has no cue points.

        FLAC uses ``SERATO_BEATGRID``. M4A uses the ``beatgrid`` atom. The
        payload is the same version-1 body an ID3 frame stores, plus the
        footer byte Serato appends. ``found`` is true so a duplicate merge
        can see the grid.

        Returns:
            None. The test fails when the BPM is missing.
        """
        payload = _beatgrid_payload() + b"\x37"
        value = _serato_b64("Serato BeatGrid", payload, wrap=False)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            flac = root / "grid.flac"
            m4a = root / "grid.m4a"
            _write_flac(flac, [b"SERATO_BEATGRID=" + value])
            _write_m4a(m4a, _freeform("beatgrid", value, null_terminate=True))
            flac_parsed = read_serato_tags(str(flac))
            m4a_parsed = read_serato_tags(str(m4a))
        for parsed in (flac_parsed, m4a_parsed):
            self.assertTrue(parsed["found"])
            self.assertEqual(parsed["cues"], [])
            self.assertEqual(parsed["beatgrid"][0].get("beats"), 4)
            self.assertEqual(parsed["beatgrid"][1].get("bpm"), 128.0)
            self.assertEqual(parsed["beatgrid"][0]["position"], 0.5)

    def test_markers_and_beatgrid_are_both_kept(self) -> None:
        """Read a cue and a beatgrid stored in the same file.

        Returns:
            None. The test fails when one block replaces the other.
        """
        markers = _serato_b64("Serato Markers2", _markers_payload(), wrap=False)
        grid = _serato_b64("Serato BeatGrid", _beatgrid_payload(), wrap=False)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            flac = root / "both.flac"
            m4a = root / "both.m4a"
            _write_flac(
                flac,
                [b"SERATO_MARKERS_V2=" + markers, b"SERATO_BEATGRID=" + grid],
            )
            _write_m4a(
                m4a,
                _freeform("markersv2", markers, null_terminate=False)
                + _freeform("beatgrid", grid, null_terminate=False),
            )
            flac_parsed = read_serato_tags(str(flac))
            m4a_parsed = read_serato_tags(str(m4a))
        for parsed in (flac_parsed, m4a_parsed):
            self.assertEqual(parsed["cues"][0]["color"], "#CC0000")
            self.assertEqual(parsed["beatgrid"][1].get("bpm"), 128.0)

    def test_files_without_serato_blocks_are_empty(self) -> None:
        """Return no markers from a FLAC or M4A that has none.

        An unrelated Vorbis title and an empty item list stay unread. A
        ``SERATO_OVERVIEW`` envelope is not a cue block. A broken base64
        value does not raise.

        Returns:
            None. The test fails when ``found`` is true.
        """
        overview = _serato_b64("Serato Overview", b"\x00\x01", wrap=False)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            plain_flac = root / "plain.flac"
            plain_m4a = root / "plain.m4a"
            overview_flac = root / "overview.flac"
            broken = root / "broken.flac"
            _write_flac(plain_flac, [b"TITLE=t"])
            _write_m4a(plain_m4a, b"")
            _write_flac(overview_flac, [b"SERATO_OVERVIEW=" + overview])
            _write_flac(broken, [b"SERATO_MARKERS_V2=!!!!"])
            parsed = [
                read_serato_tags(str(plain_flac)),
                read_serato_tags(str(plain_m4a)),
                read_serato_tags(str(overview_flac)),
                read_serato_tags(str(broken)),
            ]
            short = root / "short.flac"
            short.write_bytes(b"fLaC" + b"\x00" * 12)
            parsed.append(read_serato_tags(str(short)))
        for item in parsed:
            self.assertFalse(item["found"])
            self.assertEqual(item["cues"], [])
            self.assertEqual(item["beatgrid"], [])

    def test_m4a_markers_outside_the_head_and_tail_windows_are_read(self) -> None:
        """Read markers from a ``moov`` that sits past the scanned windows.

        The audio atom is large enough that the markers start after byte
        2,000,000. Padding after the markers keeps them out of the last
        512,000 bytes as well. The reader follows the atom size and does
        not load the audio. The file is not rewritten.

        Returns:
            None. The test fails when the cue is missed or the bytes change.
        """
        value = _serato_b64("Serato Markers2", _markers_payload(), wrap=False)
        items = _freeform("markersv2", value, null_terminate=True)
        meta = _atom(
            b"meta",
            bytes(4)
            + _atom(b"hdlr", bytes(8) + b"mdir" + bytes(13))
            + _atom(b"ilst", items),
        )
        udta = _atom(b"udta", meta)
        pad = 600_000
        free = struct.pack(">I", 8 + pad) + b"free" + (b"\x00" * pad)
        moov = struct.pack(">I", 8 + len(udta) + len(free)) + b"moov" + udta + free
        ftyp = _atom(b"ftyp", b"M4A \x00\x00\x00\x00M4A isom")
        mdat_body = 2_000_000 - len(ftyp) - 8
        mdat = struct.pack(">I", 8 + mdat_body) + b"mdat" + (b"\x00" * mdat_body)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "late.m4a"
            path.write_bytes(ftyp + mdat + moov)
            raw = path.read_bytes()
            marker_at = raw.find(b"com.serato.dj")
            self.assertGreaterEqual(marker_at, 2_000_000)
            self.assertLess(marker_at, len(raw) - 512_000)
            before = raw
            parsed = read_serato_tags(str(path))
            self.assertEqual(path.read_bytes(), before)
        self._assert_markers(parsed, ".m4a")

    def test_flac_markers_after_album_art_over_two_megabytes(self) -> None:
        """Read markers that follow a picture block larger than 2 MB.

        STREAMINFO, then a type-6 picture of 3,000,000 bytes, then the Vorbis
        comment. Padding after the comment keeps it out of the last 512,000
        bytes as well. The picture body is a hole. The reader seeks over it
        and still returns the cue. ``serato_tags_from_regions`` sees only the
        ID3 windows, so the leading bytes alone do not contain the markers.
        The file size does not change.

        Returns:
            None. The test fails when the cue is missed or the art is loaded
            into the ID3 window and mistaken for the whole tag.
        """
        picture = 3_000_000
        self.assertGreater(picture, 2_000_000)
        value = _serato_b64("Serato Markers2", _markers_payload(), wrap=False)
        comment = _vorbis_comment([b"TITLE=t", b"SERATO_MARKERS_V2=" + value])
        comment_block = _flac_block(4, comment, True)
        streaminfo = _flac_block(0, bytes(34), False)
        trailer = 600_000
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "art.flac"
            with path.open("wb") as handle:
                handle.write(b"fLaC")
                handle.write(streaminfo)
                handle.write(bytes([6]) + picture.to_bytes(3, "big"))
                handle.seek(picture, 1)
                comment_at = handle.tell()
                handle.write(comment_block)
                handle.write(b"\x00" * trailer)
            size = path.stat().st_size
            self.assertGreaterEqual(comment_at, 2_000_000)
            self.assertLess(comment_at + len(comment_block), size - 512_000)
            with path.open("rb") as handle:
                head = handle.read(2_000_000)
                self.assertNotIn(b"SERATO_MARKERS_V2", head)
                handle.seek(max(0, size - 512_000))
                tail = handle.read(512_000)
                self.assertNotIn(b"SERATO_MARKERS_V2", tail)
                handle.seek(comment_at)
                self.assertIn(b"SERATO_MARKERS_V2", handle.read(len(comment_block)))
            self.assertFalse(serato_tags_from_regions(head, tail)["found"])
            parsed = read_serato_tags(str(path))
            self.assertEqual(path.stat().st_size, size)
        self._assert_markers(parsed, ".flac")

    def test_an_mp3_is_not_scanned_for_mp4_atoms(self) -> None:
        """Leave a freeform atom unread when the file is an MP3 without ``ftyp``.

        The same atom is read when the name ends in ``.m4a`` and when an
        ``.mp3`` name still starts with ``ftyp``.

        Returns:
            None. The test fails if the MP3 scan reports a cue.
        """
        value = _serato_b64("Serato Markers2", _markers_payload(), wrap=False)
        items = _freeform("markersv2", value, null_terminate=False)
        meta = _atom(
            b"meta",
            bytes(4)
            + _atom(b"hdlr", bytes(8) + b"mdir" + bytes(13))
            + _atom(b"ilst", items),
        )
        moov = _atom(b"moov", _atom(b"udta", meta))
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            mp3 = root / "track.mp3"
            m4a = root / "track.m4a"
            ftyp_mp3 = root / "wrapped.mp3"
            mp3.write_bytes(moov)
            m4a.write_bytes(moov)
            _write_m4a(ftyp_mp3, items)
            self.assertNotEqual(mp3.read_bytes()[4:8], b"ftyp")
            plain = read_serato_tags(str(mp3))
            named = read_serato_tags(str(m4a))
            branded = read_serato_tags(str(ftyp_mp3))
            self.assertEqual(mp3.read_bytes(), moov)
        self.assertFalse(plain["found"])
        self.assertEqual(plain["cues"], [])
        self._assert_markers(named, ".m4a")
        self._assert_markers(branded, ".mp3")

    def test_oversized_moov_logs_a_warning(self) -> None:
        """Log a warning when a ``moov`` is larger than 16 MB and keep its front.

        The markers sit at the start of the atom. The rest is a hole. The
        read stops at the cap. The file is not rewritten.

        Returns:
            None. The test fails when the warning is missing or the cue is dropped.
        """
        value = _serato_b64("Serato Markers2", _markers_payload(), wrap=False)
        items = _freeform("markersv2", value, null_terminate=True)
        meta = _atom(
            b"meta",
            bytes(4)
            + _atom(b"hdlr", bytes(8) + b"mdir" + bytes(13))
            + _atom(b"ilst", items),
        )
        udta = _atom(b"udta", meta)
        body_len = _TAG_LIMIT + 1
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "huge.m4a"
            with path.open("wb") as handle:
                handle.write(_atom(b"ftyp", b"M4A \x00\x00\x00\x00M4A isom"))
                handle.write(struct.pack(">I", 8 + body_len) + b"moov")
                handle.write(udta)
                handle.seek(body_len - len(udta) - 1, 1)
                handle.write(b"\x00")
            size = path.stat().st_size
            with self.assertLogs("serato.tags", level="WARNING") as caught:
                parsed = read_serato_tags(str(path))
            self.assertEqual(path.stat().st_size, size)
        self.assertTrue(any("moov" in line for line in caught.output))
        self._assert_markers(parsed, ".m4a")

    def test_copy_onto_flac_is_refused_and_bytes_unchanged(self) -> None:
        """Refuse to copy markers onto a FLAC file.

        The destination bytes stay identical. The read of the source still
        sees its cues. Nothing is written to either file.

        Returns:
            None. The test fails when the destination changes.
        """
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "s.flac"
            dest = root / "d.flac"
            value = _serato_b64("Serato Markers2", _markers_payload(), wrap=False)
            _write_flac(source, [b"SERATO_MARKERS_V2=" + value])
            _write_flac(dest, [b"TITLE=t"])
            before_source = source.read_bytes()
            before_dest = dest.read_bytes()
            planned = plan_serato_geob(source, dest)
            copied = copy_serato_geob(source, dest)
            self.assertEqual(planned["status"], "unsupported")
            self.assertIn(copied["status"], {"unsupported", "skipped"})
            self.assertNotIn("\\", copied["detail"])
            self.assertNotIn("/", copied["detail"])
            self.assertEqual(source.read_bytes(), before_source)
            self.assertEqual(dest.read_bytes(), before_dest)
            self.assertTrue(read_serato_tags(str(source))["found"])

    def test_copy_onto_m4a_is_refused_and_bytes_unchanged(self) -> None:
        """Refuse to copy markers onto an M4A file.

        Returns:
            None. The test fails when the destination changes.
        """
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "s.m4a"
            dest = root / "d.m4a"
            value = _serato_b64("Serato Markers2", _markers_payload(), wrap=False)
            _write_m4a(source, _freeform("markersv2", value, null_terminate=False))
            _write_m4a(dest, b"")
            before_source = source.read_bytes()
            before_dest = dest.read_bytes()
            planned = plan_serato_geob(source, dest)
            copied = copy_serato_geob(source, dest)
            self.assertEqual(planned["status"], "unsupported")
            self.assertIn(copied["status"], {"unsupported", "skipped"})
            self.assertEqual(source.read_bytes(), before_source)
            self.assertEqual(dest.read_bytes(), before_dest)


if __name__ == "__main__":
    unittest.main()
