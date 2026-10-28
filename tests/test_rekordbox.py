"""Rekordbox XML export tests.

The cases build a temporary library and tiny ID3 files. They do not open
the live Serato database and they do not write a USB.
"""

from __future__ import annotations

import base64
import contextlib
import io
import struct
import unittest
from pathlib import Path
from xml.etree import ElementTree

import app_config
import library
import rekordbox
import tags
from library import LibraryError
from tests.fixture import ROOT, TempLibrary, open_database


def _entry(kind: str, blob: bytes) -> bytes:
    """Wrap one Markers2 record as a name, a length, and a payload.

    Args:
        kind: Entry name such as ``CUE``, ``LOOP``, or ``FLIP``.
        blob: Record payload.

    Returns:
        The encoded entry. No audio file is written.
    """
    return kind.encode("ascii") + b"\x00" + len(blob).to_bytes(4, "big") + blob


def _cue(index: int, start_ms: int, color: bytes, name: str) -> bytes:
    """Build a CUE record with the offsets the Markers2 parser expects.

    Args:
        index: Cue index stored at byte 1.
        start_ms: Start time in milliseconds.
        color: Three RGB bytes.
        name: UTF-8 cue name.

    Returns:
        The record bytes.
    """
    encoded = name.encode("utf-8")
    raw = bytearray(13 + len(encoded))
    raw[1] = index
    raw[2:6] = start_ms.to_bytes(4, "big")
    raw[7:10] = color
    raw[12:] = encoded + b"\x00"
    return bytes(raw)


def _loop(index: int, start_ms: int, end_ms: int, color: bytes, name: str) -> bytes:
    """Build a LOOP record with the offsets the Markers2 parser expects.

    Args:
        index: Loop index.
        start_ms: Loop start in milliseconds.
        end_ms: Loop end in milliseconds.
        color: Three RGB bytes stored at bytes 15-17.
        name: UTF-8 loop name.

    Returns:
        The record bytes.
    """
    encoded = name.encode("utf-8")
    raw = bytearray(21 + len(encoded))
    raw[1] = index
    raw[2:6] = start_ms.to_bytes(4, "big")
    raw[6:10] = end_ms.to_bytes(4, "big")
    raw[15:18] = color
    raw[19] = 1
    raw[20:] = encoded + b"\x00"
    return bytes(raw)


def _flip(index: int, name: str) -> bytes:
    """Build a FLIP record.

    Args:
        index: Flip index.
        name: UTF-8 flip name.

    Returns:
        The record bytes.
    """
    return bytes([0, index, 1]) + name.encode("utf-8") + b"\x00"


def _markers() -> bytes:
    """Encode two cues, a loop, and a flip as a Markers2 body.

    Returns:
        The GEOB payload. The flip is present so an export can show it is omitted.
    """
    decoded = _entry("CUE", _cue(0, 1500, b"\xCC\x00\x00", "Drop & go"))
    decoded += _entry("CUE", _cue(9, 500, b"\xFF\xFF\xFF", "Late"))
    decoded += _entry("LOOP", _loop(1, 2000, 4000, b"\x00\xAA\x00", "Break"))
    decoded += _entry("FLIP", _flip(2, "Chop"))
    return b"\x01\x01" + base64.b64encode(decoded)


def _beatgrid(markers: list[tuple[float, object]]) -> bytes:
    """Encode a version-1 beatgrid.

    The last pair stores BPM. Earlier pairs store a beat count.

    Args:
        markers: Position and either a beat count or, for the last item, a BPM.

    Returns:
        The BeatGrid payload.
    """
    body = bytes([1, 0]) + len(markers).to_bytes(4, "big")
    last = len(markers) - 1
    for index, (position, value) in enumerate(markers):
        body += struct.pack(">f", position)
        if index == last:
            body += struct.pack(">f", float(value))
        else:
            body += int(value).to_bytes(4, "big")
    return body


def _geob(description: str, payload: bytes) -> bytes:
    """Build one ID3v2.3 GEOB frame.

    Args:
        description: Frame description, such as ``Serato Markers2``.
        payload: Frame data after the description.

    Returns:
        The frame bytes, including the GEOB header.
    """
    body = (
        bytes([0])
        + b"application/octet-stream\x00"
        + b"\x00"
        + description.encode("ascii")
        + b"\x00"
        + payload
    )
    return b"GEOB" + len(body).to_bytes(4, "big") + b"\x00\x00" + body


def _id3(path: Path, frames: list[bytes]) -> None:
    """Write a tiny ID3v2.3 file that holds the given frames.

    Args:
        path: File to create or replace.
        frames: Complete GEOB frames.

    Returns:
        None.
    """
    blob = b"".join(frames)
    size = len(blob)
    synchsafe = bytes(
        (
            (size >> 21) & 0x7F,
            (size >> 14) & 0x7F,
            (size >> 7) & 0x7F,
            size & 0x7F,
        )
    )
    path.write_bytes(b"ID3" + bytes([3, 0, 0]) + synchsafe + blob)


def _node(tree: dict[str, object], name: str) -> dict[str, object] | None:
    """Find a playlist node by its visible name.

    Args:
        tree: A node from parse_rekordbox.
        name: Node name to find.

    Returns:
        The first matching node, or None.
    """
    if tree["name"] == name:
        return tree
    children = tree["children"]
    if not isinstance(children, list):
        return None
    for child in children:
        if isinstance(child, dict):
            found = _node(child, name)
            if found is not None:
                return found
    return None


def _counts_match(node: dict[str, object]) -> None:
    """Check folder counts and playlist entry counts against their children.

    Args:
        node: A playlist node from parse_rekordbox.

    Returns:
        None.

    Raises:
        AssertionError: If Count or Entries disagrees with the children.
    """
    children = node["children"]
    tracks = node["tracks"]
    if not isinstance(children, list) or not isinstance(tracks, list):
        raise AssertionError(node)
    if node["type"] == "0":
        if node["count"] != str(len(children)):
            raise AssertionError(node)
    if node["type"] == "1":
        if node["entries"] != str(len(tracks)) or children:
            raise AssertionError(node)
    for child in children:
        if isinstance(child, dict):
            _counts_match(child)


class LocationTests(unittest.TestCase):
    """Path encoding for rekordbox Location values.

    These cases do not open a database or an audio file.
    """

    def test_macos_windows_and_unc_paths(self) -> None:
        """Percent-encode macOS, Windows, and UNC paths.

        The drive colon stays a colon. A colon in the file name is encoded.
        Spaces, ``#``, ``&``, and ``?`` are encoded. Non-ASCII is UTF-8.

        Returns:
            None. The test fails if a URI differs.
        """
        self.assertEqual(
            rekordbox.location_uri("/Users/dj/My Music/café #1.mp3"),
            "file://localhost/Users/dj/My%20Music/caf%C3%A9%20%231.mp3",
        )
        self.assertEqual(
            rekordbox.location_uri(r"C:\Users\dj\My Music\café #1.mp3"),
            "file://localhost/C:/Users/dj/My%20Music/caf%C3%A9%20%231.mp3",
        )
        self.assertEqual(
            rekordbox.location_uri("/Users/dj/Artist: Title.mp3"),
            "file://localhost/Users/dj/Artist%3A%20Title.mp3",
        )
        self.assertEqual(
            rekordbox.location_uri(r"\\nas\music\a b.mp3"),
            "file://localhost//nas/music/a%20b.mp3",
        )
        self.assertEqual(
            rekordbox.location_uri("/tmp/a&b?c.mp3"),
            "file://localhost/tmp/a%26b%3Fc.mp3",
        )
        self.assertEqual(
            rekordbox.location_uri("Music/track.mp3"),
            "file://localhost/Music/track.mp3",
        )

    def test_empty_path_is_refused(self) -> None:
        """Refuse a blank path before any URI is built.

        Returns:
            None. The test fails if LibraryError is not raised.
        """
        with self.assertRaises(LibraryError):
            rekordbox.location_uri("   ")


class MarkerConversionTests(unittest.TestCase):
    """Cue, loop, and beatgrid conversion without a library file."""

    def test_cues_loops_and_memory_cues(self) -> None:
        """Map hot cues, memory cues, and loops onto POSITION_MARK attributes.

        Index 9 is outside the hot-cue slots, so Num is -1. A missing color
        is white. A flip is not a position mark.

        Returns:
            None. The test fails if a mark attribute differs.
        """
        parsed: tags.SeratoTags = {
            "cues": [
                {"index": 0, "start_ms": 1500, "color": "#CC0000", "name": "Drop"},
                {"index": 9, "start_ms": 500, "color": None, "name": "Late"},
            ],
            "loops": [
                {
                    "index": 1,
                    "start_ms": 2000,
                    "end_ms": 4000,
                    "color": "#00AA00",
                    "locked": True,
                    "name": "Break",
                }
            ],
            "flips": [{"index": 2, "enabled": True, "name": "Chop"}],
            "beatgrid": [],
            "found": True,
        }
        marks = rekordbox.position_marks(parsed)
        self.assertEqual(
            marks,
            [
                {
                    "Name": "Drop",
                    "Type": "0",
                    "Start": "1.500",
                    "Num": "0",
                    "Red": "204",
                    "Green": "0",
                    "Blue": "0",
                },
                {
                    "Name": "Late",
                    "Type": "0",
                    "Start": "0.500",
                    "Num": "-1",
                    "Red": "255",
                    "Green": "255",
                    "Blue": "255",
                },
                {
                    "Name": "Break",
                    "Type": "1",
                    "Start": "2.000",
                    "Num": "1",
                    "Red": "0",
                    "Green": "170",
                    "Blue": "0",
                    "End": "4.000",
                },
            ],
        )

    def test_beatgrid_bpm_uses_the_span(self) -> None:
        """Compute an earlier marker's BPM from its beat count and span.

        Four beats across two seconds is 120. The last marker keeps its own
        BPM of 100. A zero span uses that BPM instead of dividing by zero.
        A span that would exceed 999 BPM also uses it.

        Returns:
            None. The test fails if a TEMPO value differs.
        """
        entries = rekordbox.tempo_entries(
            [
                {"position": 0.0, "beats": 4},
                {"position": 2.0, "bpm": 100.0},
            ]
        )
        self.assertEqual(entries[0]["Bpm"], "120.00")
        self.assertEqual(entries[0]["Inizio"], "0.000")
        self.assertEqual(entries[0]["Metro"], "4/4")
        self.assertEqual(entries[0]["Battito"], "1")
        self.assertEqual(entries[1]["Bpm"], "100.00")
        self.assertEqual(entries[1]["Inizio"], "2.000")
        stalled = rekordbox.tempo_entries(
            [
                {"position": 1.0, "beats": 4},
                {"position": 1.0, "bpm": 128.0},
            ]
        )
        self.assertEqual(stalled[0]["Bpm"], "128.00")
        huge = rekordbox.tempo_entries(
            [
                {"position": 0.0, "beats": 100},
                {"position": 0.1, "bpm": 90.0},
            ]
        )
        self.assertEqual(huge[0]["Bpm"], "90.00")
        self.assertEqual(rekordbox.tempo_entries([]), [])


class ExportTests(unittest.TestCase):
    """Export a fixture library, then parse the XML back.

    The database is temporary. One audio file holds Markers2 and BeatGrid.
    """

    def test_library_crates_cues_and_round_trip(self) -> None:
        """Write nested crates, cues, a loop, and a beatgrid, then parse them back.

        House contains one track and the Deep subcrate. Deep contains the
        tagged file and the House track again. A second crate holds the
        other copy. A track with no path is left out. Re-parsing the XML
        yields the same tracks and playlist tree.

        Returns:
            None. The test fails if a field, mark, tempo, or folder is wrong.
        """
        with TempLibrary() as temp:
            folder = temp.root / "My Music"
            folder.mkdir()
            audio = folder / "Drop #1.mp3"
            _id3(
                audio,
                [
                    _geob("Serato Markers2", _markers()),
                    _geob("Serato BeatGrid", _beatgrid([(0.0, 4), (2.0, 100.0)])),
                ],
            )
            tagged = tags.read_serato_tags(str(audio))
            self.assertTrue(tagged["found"])
            self.assertEqual(len(tagged["cues"]), 2)
            self.assertEqual(len(tagged["loops"]), 1)
            self.assertEqual(tagged["beatgrid"][1]["bpm"], 100.0)
            with open_database(temp.db) as conn:
                conn.execute(
                    """
                    UPDATE asset
                    SET album = 'Night', genre = 'House', comments = ?,
                        file_bit_rate = 320000, file_sample_rate = 44100,
                        file_size = 4096, year = '2020'
                    WHERE id = 1
                    """,
                    ("peak \x01& \"late\"",),
                )
                conn.execute(
                    """
                    INSERT INTO asset
                        (id, name, artist, album, genre, bpm, key, length_ms, comments,
                         file_bit_rate, file_sample_rate, file_size, portable_id, file_name,
                         location_id, time_added, rating)
                    VALUES
                        (3, 'Drop & go', 'DJ & Co', 'Night', 'House', 120, '8A', 240000,
                         'cue file', 256000, 44100, 2048, ?, 'Drop #1.mp3', 1, 1609459200, 1)
                    """,
                    (str(audio),),
                )
                conn.execute(
                    """
                    INSERT INTO asset (id, name, artist, portable_id, location_id)
                    VALUES (4, 'Ghost', 'Artist', NULL, 1)
                    """
                )
                conn.execute(
                    """
                    INSERT INTO space_asset (id, asset_id, space_id)
                    VALUES (3, 3, 1), (4, 4, 1)
                    """
                )
            house = library.crate_action({"action": "create", "name": "House"})
            deep = library.crate_action(
                {"action": "create", "name": "Deep", "parent": house["id"]}
            )
            other = library.crate_action({"action": "create", "name": "Other"})
            library.crate_action({"action": "create", "name": "Later"})
            library.crate_action({"action": "add", "id": house["id"], "asset": 1})
            library.crate_action({"action": "add", "id": house["id"], "asset": 4})
            library.crate_action({"action": "add", "id": deep["id"], "asset": 3})
            library.crate_action({"action": "add", "id": deep["id"], "asset": 1})
            library.crate_action({"action": "add", "id": other["id"], "asset": 2})
            with open_database(temp.db) as conn:
                conn.execute(
                    "UPDATE container SET name = ? WHERE id = ?",
                    ("House" + library.NAME_SPLIT + "abc", house["id"]),
                )
            xml = rekordbox.export_rekordbox("Serato Library", None)
            self.assertTrue(xml.startswith('<?xml version="1.0" encoding="UTF-8"?>'))
            parsed = rekordbox.parse_rekordbox(xml)
            again = ElementTree.tostring(ElementTree.fromstring(xml.encode("utf-8")), encoding="unicode")
            self.assertEqual(parsed, rekordbox.parse_rekordbox(again))
            self.assertEqual(parsed["version"], "1.0.0")
            tracks = parsed["tracks"]
            self.assertIsInstance(tracks, list)
            assert isinstance(tracks, list)
            names = [track["name"] for track in tracks]
            self.assertNotIn("Ghost", names)
            self.assertEqual(names.count("Same"), 2)
            drop = next(track for track in tracks if track["name"] == "Drop & go")
            self.assertEqual(drop["artist"], "DJ & Co")
            self.assertEqual(drop["album"], "Night")
            self.assertEqual(drop["genre"], "House")
            self.assertEqual(drop["bpm"], "120.00")
            self.assertEqual(drop["key"], "8A")
            self.assertEqual(drop["length"], "240")
            self.assertEqual(drop["bitrate"], "256")
            self.assertEqual(drop["comments"], "cue file")
            self.assertEqual(drop["location"], rekordbox.location_uri(str(audio)))
            self.assertIn("My%20Music/Drop%20%231.mp3", str(drop["location"]))
            self.assertNotIn(" ", str(drop["location"]))
            self.assertNotIn("#", str(drop["location"]).split("file://localhost", 1)[1])
            self.assertNotIn("\\", str(drop["location"]))
            self.assertEqual(
                drop["tempos"],
                [
                    {"Inizio": "0.000", "Bpm": "120.00", "Metro": "4/4", "Battito": "1"},
                    {"Inizio": "2.000", "Bpm": "100.00", "Metro": "4/4", "Battito": "1"},
                ],
            )
            self.assertEqual(
                drop["marks"],
                [
                    {
                        "Name": "Drop & go",
                        "Type": "0",
                        "Start": "1.500",
                        "Num": "0",
                        "Red": "204",
                        "Green": "0",
                        "Blue": "0",
                    },
                    {
                        "Name": "Late",
                        "Type": "0",
                        "Start": "0.500",
                        "Num": "-1",
                        "Red": "255",
                        "Green": "255",
                        "Blue": "255",
                    },
                    {
                        "Name": "Break",
                        "Type": "1",
                        "Start": "2.000",
                        "End": "4.000",
                        "Num": "1",
                        "Red": "0",
                        "Green": "170",
                        "Blue": "0",
                    },
                ],
            )
            kept = next(
                track
                for track in tracks
                if track["name"] == "Same" and "same-a.mp3" in str(track["location"])
            )
            self.assertEqual(kept["comments"], 'peak & "late"')
            self.assertEqual(kept["bitrate"], "320")
            self.assertEqual(kept["length"], "180")
            self.assertEqual(kept["bpm"], "120.00")
            self.assertEqual(kept["key"], "1A")
            self.assertEqual(kept["album"], "Night")
            self.assertEqual(kept["genre"], "House")
            self.assertEqual(kept["tempos"], [])
            self.assertEqual(kept["marks"], [])
            document = ElementTree.fromstring(xml.encode("utf-8"))
            product = document.find("PRODUCT")
            self.assertIsNotNone(product)
            assert product is not None
            self.assertEqual(product.get("Version"), app_config.APP_VERSION)
            kept_xml = next(
                item
                for item in document.find("COLLECTION").findall("TRACK")
                if item.get("TrackID") == "1"
            )
            self.assertEqual(kept_xml.get("BitRate"), "320")
            self.assertEqual(kept_xml.get("SampleRate"), "44100")
            self.assertEqual(kept_xml.get("Size"), "4096")
            self.assertEqual(kept_xml.get("Kind"), "MP3 File")
            self.assertEqual(kept_xml.get("Year"), "2020")
            self.assertEqual(kept_xml.get("DateAdded"), "1970-01-01")
            self.assertEqual(kept_xml.get("TotalTime"), "180")
            drop_xml = next(
                item
                for item in document.find("COLLECTION").findall("TRACK")
                if item.get("TrackID") == "3"
            )
            self.assertEqual(drop_xml.get("DateAdded"), "2021-01-01")
            self.assertEqual(drop_xml.get("Rating"), "255")
            playlists = parsed["playlists"]
            self.assertIsInstance(playlists, dict)
            assert isinstance(playlists, dict)
            _counts_match(playlists)
            self.assertEqual(playlists["name"], "ROOT")
            self.assertEqual(playlists["count"], "3")
            house_node = _node(playlists, "House")
            self.assertIsNotNone(house_node)
            assert house_node is not None
            self.assertEqual(house_node["type"], "0")
            child_names = [child["name"] for child in house_node["children"]]
            self.assertEqual(child_names, ["House", "Deep"])
            own = house_node["children"][0]
            self.assertEqual(own["type"], "1")
            self.assertEqual(own["tracks"], ["1"])
            deep_node = house_node["children"][1]
            self.assertEqual(deep_node["tracks"], ["3", "1"])
            self.assertEqual(_node(playlists, "Other")["tracks"], ["2"])
            self.assertEqual(_node(playlists, "Later")["tracks"], [])
            track_ids = [track["track_id"] for track in tracks]
            self.assertEqual(track_ids.count("1"), 1)
            subtree = rekordbox.export_rekordbox("Serato Library", int(house["id"]))
            sub = rekordbox.parse_rekordbox(subtree)
            sub_tracks = sub["tracks"]
            assert isinstance(sub_tracks, list)
            self.assertEqual({track["track_id"] for track in sub_tracks}, {"1", "3"})
            sub_root = sub["playlists"]
            assert isinstance(sub_root, dict)
            self.assertEqual(sub_root["count"], "1")
            self.assertIsNone(_node(sub_root, "Other"))
            self.assertIsNotNone(_node(sub_root, "Deep"))
            with self.assertRaises(LibraryError) as missing:
                rekordbox.export_rekordbox("Serato Library", 99999)
            self.assertEqual(missing.exception.status, 404)
            with self.assertRaises(LibraryError):
                rekordbox.export_rekordbox("Streaming", None)
            prepare = rekordbox.parse_rekordbox(rekordbox.export_rekordbox("Prepare", None))
            prepare_root = prepare["playlists"]
            assert isinstance(prepare_root, dict)
            self.assertEqual(_node(prepare_root, "Prepare")["type"], "1")
            self.assertEqual(prepare["tracks"], [])

    def test_empty_library_bpm_uses_the_beatgrid(self) -> None:
        """Fill AverageBpm from the beatgrid when the library BPM is empty.

        The audio file has one BeatGrid marker and no cues. The asset BPM
        is cleared before the export.

        Returns:
            None. The test fails if the tempo or the average is not 128.00.
        """
        with TempLibrary() as temp:
            audio = temp.root / "grid.mp3"
            _id3(audio, [_geob("Serato BeatGrid", _beatgrid([(0.25, 128.0)]))])
            with open_database(temp.db) as conn:
                conn.execute(
                    """
                    UPDATE asset
                    SET bpm = NULL, portable_id = ?, file_name = 'grid.mp3'
                    WHERE id = 1
                    """,
                    (str(audio),),
                )
            parsed = rekordbox.parse_rekordbox(rekordbox.export_rekordbox("Serato Library", None))
            tracks = parsed["tracks"]
            assert isinstance(tracks, list)
            track = next(item for item in tracks if item["track_id"] == "1")
            self.assertEqual(track["bpm"], "128.00")
            self.assertEqual(track["marks"], [])
            self.assertEqual(
                track["tempos"],
                [{"Inizio": "0.250", "Bpm": "128.00", "Metro": "4/4", "Battito": "1"}],
            )

    def test_command_writes_xml_and_refuses_the_database(self) -> None:
        """Write rekordbox.xml from the command and refuse a database path.

        ``--crate`` selects the House tree. A crate id that is not a number
        returns 2. The library file and a missing folder are refused. The
        fixture database is left in place.

        Returns:
            None. The test fails if the command writes the wrong file or replaces the database.
        """
        with TempLibrary() as temp:
            house = library.crate_action({"action": "create", "name": "House"})
            library.crate_action({"action": "add", "id": house["id"], "asset": 1})
            output = temp.root / "out" / "rekordbox.xml"
            output.parent.mkdir()
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = rekordbox.main(
                    ["-o", str(output), "--crate", str(house["id"]), "--space", "Serato Library"]
                )
            self.assertEqual(code, 0)
            self.assertEqual(stdout.getvalue().strip(), str(output))
            parsed = rekordbox.parse_rekordbox(output.read_text(encoding="utf-8"))
            tracks = parsed["tracks"]
            assert isinstance(tracks, list)
            self.assertEqual([track["track_id"] for track in tracks], ["1"])
            playlists = parsed["playlists"]
            assert isinstance(playlists, dict)
            self.assertEqual(_node(playlists, "House")["tracks"], ["1"])
            before = temp.db.read_bytes()[:16]
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                refused = rekordbox.main(["-o", str(temp.db)])
            self.assertEqual(refused, 1)
            self.assertIn("XML", stderr.getvalue())
            self.assertEqual(temp.db.read_bytes()[:16], before)
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                missing = rekordbox.main(["--crate", "nope", "-o", str(output)])
            self.assertEqual(missing, 2)
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                absent = rekordbox.main(["-o", str(temp.root / "missing" / "out.xml")])
            self.assertEqual(absent, 1)
            self.assertIn("folder", stderr.getvalue())

    def test_page_offers_the_export(self) -> None:
        """Point the Rekordbox button at the XML route.

        Reads the page and the script from the repository. No server is started.

        Returns:
            None. The test fails if the button or the route is missing.
        """
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        style = (ROOT / "static" / "app.css").read_text(encoding="utf-8")
        guide = (ROOT / "docs" / "guide" / "playlists.md").read_text(encoding="utf-8")
        self.assertIn('id="export-rekordbox"', html)
        self.assertIn(">Rekordbox<", html)
        self.assertIn("/api/export.rekordbox.xml", script)
        self.assertIn("rekordbox.xml", script)
        self.assertIn("#export-rekordbox", style)
        self.assertIn("Preferences", guide)
        self.assertIn("rekordbox xml", guide)
        self.assertIn("Device Library Plus", guide)
        self.assertIn("OneLibrary", guide)


class ParseTests(unittest.TestCase):
    """Reject text that is not a rekordbox playlist document."""

    def test_malformed_xml_is_refused(self) -> None:
        """Raise ValueError when the file is not DJ_PLAYLISTS XML.

        Returns:
            None. The test fails if the bad text is accepted.
        """
        with self.assertRaises(ValueError):
            rekordbox.parse_rekordbox("<playlist></playlist>")
        with self.assertRaises(ValueError):
            rekordbox.parse_rekordbox("not xml")
