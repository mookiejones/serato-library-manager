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

from tags import _parse_beatgrid, _parse_cue, _parse_markers2, read_serato_tags


def _entry(kind: str, blob: bytes) -> bytes:
    return kind.encode("ascii") + b"\x00" + len(blob).to_bytes(4, "big") + blob


def _cue(index: int, start_ms: int, color: bytes, name: str) -> bytes:
    raw = bytearray(13 + len(name))
    raw[1] = index
    raw[2:6] = start_ms.to_bytes(4, "big")
    raw[7:10] = color
    raw[12:] = name.encode("utf-8") + b"\x00"
    return bytes(raw)


def _loop(index: int, start_ms: int, end_ms: int, locked: bool, name: str) -> bytes:
    raw = bytearray(21 + len(name))
    raw[1] = index
    raw[2:6] = start_ms.to_bytes(4, "big")
    raw[6:10] = end_ms.to_bytes(4, "big")
    raw[15:18] = b"\x00\x11\x22"
    raw[19] = 1 if locked else 0
    raw[20:] = name.encode("utf-8") + b"\x00"
    return bytes(raw)


def _flip(index: int, enabled: bool, name: str) -> bytes:
    return bytes([0, index, 1 if enabled else 0]) + name.encode("utf-8") + b"\x00"


def _markers_payload() -> bytes:
    decoded = _entry("CUE", _cue(3, 1500, b"\xCC\x00\x00", "Drop"))
    decoded += _entry("LOOP", _loop(1, 2000, 4000, True, "Break"))
    decoded += _entry("FLIP", _flip(2, True, "Chop"))
    return b"\x01\x01" + base64.b64encode(decoded)


def _beatgrid_payload() -> bytes:
    body = bytes([1, 0]) + (2).to_bytes(4, "big")
    body += struct.pack(">f", 0.5) + (4).to_bytes(4, "big")
    body += struct.pack(">f", 10.0) + struct.pack(">f", 128.0)
    return body


def _id3_file(payload: bytes, path: Path) -> None:
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
    def test_missing_path_is_empty(self) -> None:
        parsed = read_serato_tags(None)
        self.assertFalse(parsed["found"])
        self.assertEqual(parsed["cues"], [])

    def test_markers_round_trip(self) -> None:
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
        self.assertIsNone(_parse_cue(b"\x00" * 5))

    def test_beatgrid_markers(self) -> None:
        markers = _parse_beatgrid(_beatgrid_payload())
        self.assertEqual(markers[0].get("beats"), 4)
        self.assertEqual(markers[1].get("bpm"), 128.0)
        self.assertEqual(markers[0]["position"], 0.5)

    def test_bad_beatgrid_is_empty(self) -> None:
        self.assertEqual(_parse_beatgrid(b"\x02\x00\x00\x00\x00\x01"), [])
        huge = bytes([1, 0]) + (4097).to_bytes(4, "big")
        self.assertEqual(_parse_beatgrid(huge), [])
        short = bytes([1, 0]) + (2).to_bytes(4, "big") + struct.pack(">f", 1.0)
        self.assertEqual(_parse_beatgrid(short), [])

    def test_bad_markers_base64_is_empty(self) -> None:
        parsed = _parse_markers2(b"\x01\x01@")
        self.assertEqual(parsed["cues"], [])
        self.assertEqual(parsed["loops"], [])
        self.assertEqual(parsed["flips"], [])

    def test_file_header_is_read(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "track.mp3"
            _id3_file(_markers_payload(), path)
            parsed = read_serato_tags(str(path))
        self.assertTrue(parsed["found"])
        self.assertEqual(parsed["cues"][0]["index"], 3)


if __name__ == "__main__":
    unittest.main()
