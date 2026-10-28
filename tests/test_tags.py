"""Parser tests for Serato GEOB frames."""

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
    _parse_beatgrid,
    _parse_cue,
    _parse_markers2,
    copy_serato_geob,
    plan_serato_geob,
    read_serato_tags,
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


if __name__ == "__main__":
    unittest.main()
