"""Rekordbox XML export tests.

The cases build a temporary library and tiny ID3 files. They do not open
the live Serato database and they do not write a USB.
"""

from __future__ import annotations

import base64
import contextlib
import io
import struct
import unicodedata
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

        Index 9 is outside the hot-cue slots, so Num is -1. A hot cue is
        also copied as a memory cue. A loop is Type 4 with Num -1 so it
        does not take a hot cue pad. A missing color is white. A flip is
        not a position mark.

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
                    "Name": "Drop",
                    "Type": "0",
                    "Start": "1.500",
                    "Num": "-1",
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
                    "Type": "4",
                    "Start": "2.000",
                    "Num": "-1",
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
            xml, report = rekordbox.export_rekordbox("Serato Library", None)
            self.assertIn("Import to Collection", " ".join(report))
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
                        "Name": "Drop & go",
                        "Type": "0",
                        "Start": "1.500",
                        "Num": "-1",
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
                        "Type": "4",
                        "Start": "2.000",
                        "End": "4.000",
                        "Num": "-1",
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
            subtree, _subtree_report = rekordbox.export_rekordbox("Serato Library", int(house["id"]))
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
            prepare_xml, _prepare_report = rekordbox.export_rekordbox("Prepare", None)
            prepare = rekordbox.parse_rekordbox(prepare_xml)
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
            grid_xml, _grid_report = rekordbox.export_rekordbox("Serato Library", None)
            parsed = rekordbox.parse_rekordbox(grid_xml)
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
            self.assertTrue(stdout.getvalue().startswith(str(output)))
            self.assertIn("Import to Collection", stdout.getvalue())
            self.assertIn("load information from imported library", stdout.getvalue())
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
        self.assertIn('id="rekordbox-memory"', html)
        self.assertIn('id="rekordbox-dialog"', html)
        self.assertIn('id="rekordbox-report"', html)
        self.assertIn("showModal", script)
        self.assertIn('createElement("li")', script)
        self.assertIn('startsWith("<?xml")', script)
        self.assertIn("setTimeout", script)
        self.assertIn("revokeObjectURL", script)
        self.assertIn("report=1", script)
        self.assertIn("Preferences", guide)
        self.assertIn("rekordbox xml", guide)
        self.assertIn("Database", guide)
        self.assertIn("Import to Collection", guide)
        self.assertIn("load information from imported library", guide)
        self.assertIn("overwrites", guide.lower())
        self.assertIn("Device Library Plus", guide)
        self.assertIn("OneLibrary", guide)


def _cue_payload(cues: list[tuple[int, int, bytes, str]], loops: list[tuple[int, int, int, bytes, str]] | None = None) -> bytes:
    """Encode cues and loops as a Markers2 body.

    Args:
        cues: Index, start in milliseconds, RGB, and name.
        loops: Index, start, end, RGB, and name.

    Returns:
        The GEOB payload.
    """
    decoded = b""
    for index, start_ms, color, name in cues:
        decoded += _entry("CUE", _cue(index, start_ms, color, name))
    for index, start_ms, end_ms, color, name in loops or []:
        decoded += _entry("LOOP", _loop(index, start_ms, end_ms, color, name))
    return b"\x01\x01" + base64.b64encode(decoded)


def _lame_frame(encoder: bytes, crc: bytes | None = None) -> bytes:
    """Build one MPEG frame with an Info tag and a 9-byte encoder name.

    Args:
        encoder: Nine bytes such as ``LAME3.100`` or ``Lavc60.31``.
        crc: Two CRC bytes. None computes a valid LAME CRC.

    Returns:
        The frame bytes. No audio samples are included.
    """
    header = bytes([0xFF, 0xFB, 0x90, 0x00])
    prefix = b"Info" + (0x0F).to_bytes(4, "big") + bytes(4) + bytes(4) + bytes(100) + bytes(4)
    body = header + bytes(32) + prefix + encoder + bytes(25)
    if crc is None:
        crc = rekordbox._crc16_lame(body).to_bytes(2, "big")
    return body + crc


def _write_audio(path: Path, payload: bytes, frame: bytes = b"") -> None:
    """Write an ID3 tag and an optional MPEG frame.

    Args:
        path: File to create.
        payload: Markers2 GEOB body.
        frame: MPEG frame bytes appended after the tag.

    Returns:
        None.
    """
    _id3(path, [_geob("Serato Markers2", payload)])
    if frame:
        path.write_bytes(path.read_bytes() + frame)


class RoundTripChecklistTests(unittest.TestCase):
    """Cover the Rekordbox round-trip checks with fixtures, not a live CDJ.

    Each case uses a temporary file or a temporary library. Nothing is
    written to a USB.
    """

    def test_every_hot_cue_round_trips_to_the_millisecond(self) -> None:
        """Keep number, name, color, and millisecond position for slots 0 through 7.

        The file is WAV, so no MP3 shift applies. Each hot cue is also a
        memory cue. The loop is Type 4 and does not reuse a hot cue number.
        ``1.005`` seconds must come back as 1005 milliseconds.

        Returns:
            None. The test fails if any field differs after the XML is parsed.
        """
        colors = [
            (b"\xCC\x00\x00", "204", "0", "0"),
            (b"\xFF\x8C\x00", "255", "140", "0"),
            (b"\xFF\xFF\x00", "255", "255", "0"),
            (b"\x00\x80\x00", "0", "128", "0"),
            (b"\x00\xFF\xFF", "0", "255", "255"),
            (b"\x00\x00\xCC", "0", "0", "204"),
            (b"\x80\x00\x80", "128", "0", "128"),
            (b"\xFF\x69\xB4", "255", "105", "180"),
        ]
        times = [0, 1, 10, 100, 1000, 1005, 60000, 218400]
        cues = [
            (index, times[index], colors[index][0], f"Cue {index}")
            for index in range(8)
        ]
        with TempLibrary() as temp:
            audio = temp.root / "all-cues.wav"
            _write_audio(
                audio,
                _cue_payload(cues, [(3, 2000, 3500, b"\x00\xAA\x00", "Loop 3")]),
            )
            with open_database(temp.db) as conn:
                conn.execute(
                    "UPDATE asset SET portable_id = ?, file_name = ? WHERE id = 1",
                    (str(audio), audio.name),
                )
            xml, report = rekordbox.export_rekordbox("Serato Library", None, memory_cues=True)
            parsed = rekordbox.parse_rekordbox(xml)
            tracks = parsed["tracks"]
            assert isinstance(tracks, list)
            marks = next(track["marks"] for track in tracks if track["track_id"] == "1")
            assert isinstance(marks, list)
            numbered = [mark for mark in marks if mark["Num"] != "-1" and mark["Type"] == "0"]
            self.assertEqual([mark["Num"] for mark in numbered], [str(index) for index in range(8)])
            for index, mark in enumerate(numbered):
                self.assertEqual(mark["Name"], f"Cue {index}")
                self.assertEqual(rekordbox.position_ms(str(mark["Start"])), times[index])
                self.assertEqual(mark["Red"], colors[index][1])
                self.assertEqual(mark["Green"], colors[index][2])
                self.assertEqual(mark["Blue"], colors[index][3])
                copies = [
                    other
                    for other in marks
                    if other["Name"] == mark["Name"] and other["Num"] == "-1" and other["Type"] == "0"
                ]
                self.assertEqual(len(copies), 1)
                self.assertEqual(rekordbox.position_ms(str(copies[0]["Start"])), times[index])
            loop = next(mark for mark in marks if mark["Type"] == "4")
            self.assertEqual(loop["Name"], "Loop 3")
            self.assertEqual(loop["Num"], "-1")
            self.assertEqual(rekordbox.position_ms(str(loop["Start"])), 2000)
            self.assertEqual(rekordbox.position_ms(str(loop["End"])), 3500)
            self.assertNotIn("Type=\"1\"", xml)
            self.assertIn("palette", " ".join(report))
            ids = [track["track_id"] for track in tracks]
            self.assertEqual(len(ids), len(set(ids)))
            playlists = parsed["playlists"]
            assert isinstance(playlists, dict)
            _counts_match(playlists)

    def test_memory_cues_can_be_turned_off_and_loops_avoid_hot_cue_slots(self) -> None:
        """Skip memory copies, and refuse a loop pad that a hot cue already uses.

        Returns:
            None. The test fails if a loop takes pad 0 or a memory copy remains.
        """
        parsed: tags.SeratoTags = {
            "cues": [{"index": 0, "start_ms": 1000, "color": "#CC0000", "name": "One"}],
            "loops": [
                {
                    "index": 0,
                    "start_ms": 2000,
                    "end_ms": 3000,
                    "color": "#00AA00",
                    "locked": False,
                    "name": "Taken",
                },
                {
                    "index": 2,
                    "start_ms": 4000,
                    "end_ms": 5000,
                    "color": "#0000CC",
                    "locked": False,
                    "name": "Free",
                },
            ],
            "flips": [],
            "beatgrid": [],
            "found": True,
        }
        quiet: dict[str, int] = {}
        plain = rekordbox.position_marks(parsed, memory_cues=False, stats=quiet)
        self.assertEqual([mark["Num"] for mark in plain if mark["Type"] == "0"], ["0"])
        self.assertEqual(quiet["loops_memory"], 2)
        placed: dict[str, int] = {}
        marks = rekordbox.position_marks(parsed, memory_cues=False, hot_loops=True, stats=placed)
        by_name = {mark["Name"]: mark for mark in marks}
        self.assertEqual(by_name["Taken"]["Num"], "-1")
        self.assertEqual(by_name["Taken"]["Type"], "4")
        self.assertEqual(by_name["Free"]["Num"], "2")
        self.assertEqual(placed["loops_blocked"], 1)
        self.assertEqual(placed["loops_hot"], 1)

    def test_mp3_shift_follows_the_lame_header_and_aac_does_not_move(self) -> None:
        """Align a case C MP3 with an AAC cue, and leave cases A and D alone.

        The same musical hit is stored 26 ms later on the case C file.
        After export it matches the AAC file. Cases A and D keep 1000 ms,
        so the correction is not applied to every MP3.

        Returns:
            None. The test fails if a case is shifted the wrong way.
        """
        with TempLibrary() as temp:
            files = {
                "case-c.mp3": (_lame_frame(b"LAME3.100", b"\x00\x00"), 1026),
                "case-d.mp3": (_lame_frame(b"LAME3.100"), 1000),
                "case-a.mp3": (bytes([0xFF, 0xFB, 0x90, 0x00]) + bytes(80), 1000),
                "case-b.mp3": (_lame_frame(b"Lavc60.31", b"\x00\x00"), 1026),
                "track.m4a": (b"", 1000),
            }
            for name, (frame, start_ms) in files.items():
                _write_audio(
                    temp.root / name,
                    _cue_payload(
                        [(0, start_ms, b"\xCC\x00\x00", "Hit")],
                        [(1, start_ms + 1000, start_ms + 2000, b"\x00\xAA\x00", "Hold")],
                    ),
                    frame,
                )
            self.assertEqual(rekordbox.mp3_timing(str(temp.root / "case-c.mp3")), ("C", 26))
            self.assertEqual(rekordbox.mp3_timing(str(temp.root / "case-d.mp3"))[0], "D")
            self.assertEqual(rekordbox.mp3_timing(str(temp.root / "case-a.mp3")), ("A", 0))
            self.assertEqual(rekordbox.mp3_timing(str(temp.root / "case-b.mp3")), ("B", 26))
            self.assertEqual(rekordbox.mp3_timing(str(temp.root / "track.m4a")), ("skip", 0))
            with open_database(temp.db) as conn:
                conn.execute("DELETE FROM space_asset")
                conn.execute("DELETE FROM asset")
                rows = [
                    (1, "Case C", str(temp.root / "case-c.mp3")),
                    (2, "Case D", str(temp.root / "case-d.mp3")),
                    (3, "Case A", str(temp.root / "case-a.mp3")),
                    (4, "Case B", str(temp.root / "case-b.mp3")),
                    (5, "AAC", str(temp.root / "track.m4a")),
                ]
                for asset_id, title, path in rows:
                    conn.execute(
                        """
                        INSERT INTO asset (id, name, artist, portable_id, file_name, location_id)
                        VALUES (?, ?, 'DJ', ?, ?, 1)
                        """,
                        (asset_id, title, path, Path(path).name),
                    )
                    conn.execute(
                        "INSERT INTO space_asset (asset_id, space_id) VALUES (?, 1)",
                        (asset_id,),
                    )
            xml, report = rekordbox.export_rekordbox("Serato Library", None, memory_cues=False)
            parsed = rekordbox.parse_rekordbox(xml)
            tracks = parsed["tracks"]
            assert isinstance(tracks, list)
            by_name = {track["name"]: track for track in tracks}
            for title in ("Case C", "Case D", "Case A", "Case B", "AAC"):
                cue = next(mark for mark in by_name[title]["marks"] if mark["Type"] == "0")
                loop = next(mark for mark in by_name[title]["marks"] if mark["Type"] == "4")
                self.assertEqual(rekordbox.position_ms(str(cue["Start"])), 1000, title)
                self.assertEqual(rekordbox.position_ms(str(loop["Start"])), 2000, title)
                self.assertEqual(loop["Num"], "-1")
            text = " ".join(report)
            self.assertIn("2 MP3s were moved 26 ms earlier", text)
            self.assertIn("2 MP3s kept their cue times", text)

    def test_dynamic_grid_exports_every_marker_and_a_bad_grid_warns(self) -> None:
        """Write one TEMPO per marker, and warn when the beatgrid cannot be read.

        Three hundred markers is the Serato 5.0 shape of a grid that changes
        tempo along the track. A version byte of 2 is left out and named in
        the loss report. The first marker is beat 1 of the bar.

        Returns:
            None. The test fails if a marker is dropped or a bad grid is silent.
        """
        markers: list[tags.BeatMarker] = []
        for index in range(299):
            markers.append({"position": index * 0.5, "beats": 1})
        markers.append({"position": 299 * 0.5, "bpm": 120.0})
        tempos = rekordbox.tempo_entries(markers)
        self.assertEqual(len(tempos), 300)
        self.assertEqual([item["Battito"] for item in tempos[:5]], ["1", "2", "3", "4", "1"])
        self.assertEqual(tempos[0]["Bpm"], "120.00")
        self.assertEqual(rekordbox.position_ms(tempos[2]["Inizio"]), 1000)
        self.assertEqual(tags.beatgrid_issue(bytes([2, 0, 0, 0, 0, 1])), "That beatgrid version is not supported.")
        with TempLibrary() as temp:
            good = temp.root / "grid.wav"
            bad = temp.root / "bad-grid.wav"
            payload = _beatgrid([(index * 0.5, 1) for index in range(299)] + [(149.5, 120.0)])
            _id3(good, [_geob("Serato BeatGrid", payload)])
            _id3(bad, [_geob("Serato BeatGrid", bytes([2, 0, 0, 0, 0, 1]))])
            with open_database(temp.db) as conn:
                conn.execute(
                    "UPDATE asset SET portable_id = ?, file_name = 'grid.wav' WHERE id = 1",
                    (str(good),),
                )
                conn.execute(
                    """
                    INSERT INTO asset (id, name, artist, portable_id, file_name, location_id)
                    VALUES (3, 'Bad grid', 'DJ', ?, 'bad-grid.wav', 1)
                    """,
                    (str(bad),),
                )
                conn.execute("INSERT INTO space_asset (asset_id, space_id) VALUES (3, 1)")
            xml, report = rekordbox.export_rekordbox("Serato Library", None)
            parsed = rekordbox.parse_rekordbox(xml)
            tracks = parsed["tracks"]
            assert isinstance(tracks, list)
            grid = next(track for track in tracks if track["name"] == "Same" and track["track_id"] == "1")
            broken = next(track for track in tracks if track["name"] == "Bad grid")
            self.assertEqual(len(grid["tempos"]), 300)
            self.assertEqual(broken["tempos"], [])
            self.assertIn("could not be read", " ".join(report))
            self.assertIn("more than one marker", " ".join(report))
            self.assertIn("downbeat", " ".join(report))
            self.assertIn("bars in Rekordbox are shifted", " ".join(report))
            self.assertIn("two decimal places", " ".join(report))

    def test_key_notation_and_filesystem_spelling(self) -> None:
        """Convert a known key, and use the directory entry's Unicode form.

        Returns:
            None. The test fails if Camelot stays classical or the URI uses the other spelling.
        """
        self.assertEqual(rekordbox.notation_key("8A", "classical"), ("Am", "converted"))
        self.assertEqual(rekordbox.notation_key("Am", "camelot"), ("8A", "converted"))
        self.assertEqual(rekordbox.notation_key("not a key", "camelot")[0], "not a key")
        self.assertEqual(rekordbox.position_ms("1.005"), 1005)
        with TempLibrary() as temp:
            music = temp.root / "songs"
            music.mkdir()
            nfd = unicodedata.normalize("NFD", "café.wav")
            nfc = unicodedata.normalize("NFC", "café.wav")
            (music / nfd).write_bytes(b"cafe")
            actual = next(entry.name for entry in music.iterdir())
            other = nfc if actual == nfd else nfd
            if other == actual:
                other = actual
            found = rekordbox.filesystem_path(str(music / other))
            self.assertEqual(Path(found).name, actual)
            uri = rekordbox.location_uri(found)
            from urllib.parse import unquote
            self.assertIn(actual, unquote(uri))

    def test_a_cue_inside_the_mp3_shift_is_written_at_zero(self) -> None:
        """Clamp a cue that the 26 ms correction would place before the start.

        Returns:
            None. The test fails if the XML contains a negative time.
        """
        stats: dict[str, int] = {}
        parsed: tags.SeratoTags = {
            "cues": [{"index": 1, "start_ms": 10, "color": "#010203", "name": "Early"}],
            "loops": [],
            "flips": [],
            "beatgrid": [],
            "found": True,
        }
        marks = rekordbox.position_marks(parsed, 26, memory_cues=False, stats=stats)
        self.assertEqual(marks[0]["Start"], "0.000")
        self.assertEqual(stats["clamped"], 1)
        self.assertEqual(marks[0]["Num"], "1")
        self.assertEqual(marks[0]["Red"], "1")

    def test_large_id3_tag_still_finds_the_lame_header(self) -> None:
        """Seek past a 1 MB ID3 tag, including its footer, before reading the frame.

        A read of the first 512 KB would stop inside the tag and miss the
        Info header.

        Returns:
            None. The test fails if the file is not classified as case D.
        """
        frame = _lame_frame(b"LAME3.100")
        body = b"\x00" * 1_000_000
        flags = 0x10
        size = bytes(
            (
                (len(body) >> 21) & 0x7F,
                (len(body) >> 14) & 0x7F,
                (len(body) >> 7) & 0x7F,
                len(body) & 0x7F,
            )
        )
        header = b"ID3" + bytes([4, 0, flags]) + size
        footer = b"3DI" + bytes([4, 0, flags]) + size
        with TempLibrary() as temp:
            path = temp.root / "large-tag.mp3"
            path.write_bytes(header + body + footer + frame)
            self.assertEqual(rekordbox.mp3_timing(str(path)), ("D", 0))

    def test_folder_listing_is_reused_and_an_mp3_is_opened_once(self) -> None:
        """List a folder once for two files, and open an MP3 once per export.

        Returns:
            None. The test fails if the folder is listed again or the file is opened twice.
        """
        from unittest.mock import patch

        with TempLibrary() as temp:
            folder = temp.root / "batch"
            folder.mkdir()
            (folder / "a.wav").write_bytes(b"a")
            (folder / "b.wav").write_bytes(b"b")
            cache: dict[str, dict[str, str]] = {}
            calls = 0
            original = Path.iterdir

            def wrapped(self: Path):
                nonlocal calls
                if self == folder:
                    calls += 1
                return original(self)

            with patch.object(Path, "iterdir", wrapped):
                self.assertEqual(Path(rekordbox.filesystem_path(str(folder / "a.wav"), cache)).name, "a.wav")
                self.assertEqual(Path(rekordbox.filesystem_path(str(folder / "b.wav"), cache)).name, "b.wav")
            self.assertEqual(calls, 1)
            audio = temp.root / "once.mp3"
            _write_audio(audio, _cue_payload([(0, 1000, b"\xCC\x00\x00", "Hit")]), _lame_frame(b"LAME3.100"))
            with open_database(temp.db) as conn:
                conn.execute(
                    "UPDATE asset SET portable_id = ?, file_name = 'once.mp3' WHERE id = 1",
                    (str(audio),),
                )
            opens = 0
            real_open = Path.open

            def counting(self: Path, *args: object, **kwargs: object):
                nonlocal opens
                if self.suffix.lower() == ".mp3":
                    opens += 1
                return real_open(self, *args, **kwargs)

            with patch.object(Path, "open", counting):
                rekordbox.export_rekordbox("Serato Library", None, memory_cues=False)
            self.assertEqual(opens, 1)

    def test_unencodable_path_is_named_and_rating_uses_star_steps(self) -> None:
        """Count a path that cannot be encoded apart from a missing path.

        Rating 0.5 is the middle Rekordbox step, 153. A real track color is
        written as Colour. A non-integer segment BPM is rounded to two decimals.

        Returns:
            None. The test fails if the file name is missing or the rating step is wrong.
        """
        self.assertEqual(rekordbox._rating(0.5), "153")
        self.assertEqual(rekordbox._rating(1), "255")
        self.assertEqual(rekordbox._rating(0), "0")
        rounded: dict[str, int] = {}
        tempos = rekordbox.tempo_entries(
            [
                {"position": 0.0, "beats": 1},
                {"position": 0.47, "bpm": 120.0},
            ],
            stats=rounded,
        )
        self.assertEqual(tempos[0]["Bpm"], "127.66")
        self.assertGreater(rounded["bpm_rounded"], 0)
        report = rekordbox._loss_report(
            {"bpm_rounded": 1, "grid_dynamic": 1, "long_cue_names": 2},
            True,
            False,
            "asis",
            ["drop\ufffd.mp3"],
        )
        text = " ".join(report)
        self.assertIn("two decimal places", text)
        self.assertIn("bars in Rekordbox are shifted", text)
        self.assertIn("drop\ufffd.mp3", text)
        self.assertIn("could not be encoded", text)
        self.assertIn("Beatgrid lock", text)
        self.assertIn("Smart crates", text)
        self.assertIn("20 characters", text)
        stats: dict[str, int] = {}
        names: list[str] = []
        skipped = rekordbox._track_element(
            {"id": 8, "portable_id": "Music/drop\udcff.mp3", "name": "Odd", "color": 0xCC0000, "rating": 0.5},
            memory_cues=False,
            hot_loops=False,
            key_notation="asis",
            stats=stats,
            unicode_names=names,
            unreadable_names=[],
            folder_cache={},
        )
        self.assertIsNone(skipped)
        self.assertEqual(stats.get("omitted", 0), 0)
        self.assertIn("drop", names[0])
        with TempLibrary() as temp:
            with open_database(temp.db) as conn:
                conn.execute("UPDATE asset SET color = ?, rating = 0.5 WHERE id = 1", (0xCC0000,))
            xml, _exported = rekordbox.export_rekordbox("Serato Library", None)
            document = ElementTree.fromstring(xml.encode("utf-8"))
            collection = document.find("COLLECTION")
            assert collection is not None
            colored = next(item for item in collection.findall("TRACK") if item.get("TrackID") == "1")
            self.assertEqual(colored.get("Colour"), "0xCC0000")
            self.assertEqual(colored.get("Rating"), "153")


    def test_a_locked_file_does_not_stop_the_export(self) -> None:
        """Export the rest of the library when one audio file cannot be opened.

        PermissionError is the Windows sharing-violation case. The locked
        file stays in the collection without cue points, and the loss report
        names it.

        Returns:
            None. The test fails if the export raises or omits the other track.
        """
        from unittest.mock import patch

        with TempLibrary() as temp:
            locked = temp.root / "locked.wav"
            locked.write_bytes(b"locked")
            with open_database(temp.db) as conn:
                conn.execute(
                    "UPDATE asset SET portable_id = ?, file_name = 'locked.wav', name = 'Locked' WHERE id = 1",
                    (str(locked),),
                )
            real_open = Path.open

            def refuse_locked(self: Path, *args: object, **kwargs: object):
                if self.name == "locked.wav":
                    raise PermissionError("locked")
                return real_open(self, *args, **kwargs)

            with patch.object(Path, "open", refuse_locked):
                xml, report = rekordbox.export_rekordbox("Serato Library", None)
            text = " ".join(report)
            self.assertIn("could not be read", text)
            self.assertIn("locked.wav", text)
            document = ElementTree.fromstring(xml.encode("utf-8"))
            collection = document.find("COLLECTION")
            assert collection is not None
            names = {item.get("Name") for item in collection.findall("TRACK")}
            self.assertIn("Locked", names)
            self.assertIn("Same", names)

    def test_id3_without_a_footer_and_a_size_past_the_end(self) -> None:
        """Read an ID3v2.3 tag with no footer, and refuse a size past the end.

        Returns:
            None. The test fails if the plain tag is unread or the short file crashes.
        """
        frame = _lame_frame(b"LAME3.100")
        body = b"\x00" * 32
        size = bytes(
            (
                (len(body) >> 21) & 0x7F,
                (len(body) >> 14) & 0x7F,
                (len(body) >> 7) & 0x7F,
                len(body) & 0x7F,
            )
        )
        header = b"ID3" + bytes([3, 0, 0]) + size
        with TempLibrary() as temp:
            plain = temp.root / "plain.mp3"
            plain.write_bytes(header + body + frame)
            self.assertEqual(rekordbox.mp3_timing(str(plain)), ("D", 0))
            short = temp.root / "short.mp3"
            # Synchsafe size that claims five million bytes the file does not have.
            claimed = bytes(
                (
                    (5_000_000 >> 21) & 0x7F,
                    (5_000_000 >> 14) & 0x7F,
                    (5_000_000 >> 7) & 0x7F,
                    5_000_000 & 0x7F,
                )
            )
            short.write_bytes(b"ID3" + bytes([4, 0, 0]) + claimed + b"\x00" * 16)
            self.assertEqual(rekordbox.mp3_timing(str(short))[0], "unread")

    def test_a_file_without_xing_keeps_its_cue_time(self) -> None:
        """Leave a cue where Serato stored it when the MP3 has no Xing header.

        Returns:
            None. The test fails if the exported time is shifted.
        """
        with TempLibrary() as temp:
            audio = temp.root / "noxing.mp3"
            frame = bytes([0xFF, 0xFB, 0x90, 0x00]) + bytes(80)
            _write_audio(audio, _cue_payload([(0, 1000, b"\xCC\x00\x00", "Hit")]), frame)
            with open_database(temp.db) as conn:
                conn.execute("DELETE FROM space_asset")
                conn.execute("DELETE FROM asset")
                conn.execute(
                    """
                    INSERT INTO asset (id, name, artist, portable_id, file_name, location_id)
                    VALUES (1, 'No Xing', 'DJ', ?, 'noxing.mp3', 1)
                    """,
                    (str(audio),),
                )
                conn.execute("INSERT INTO space_asset (asset_id, space_id) VALUES (1, 1)")
            xml, report = rekordbox.export_rekordbox("Serato Library", None, memory_cues=False)
            parsed = rekordbox.parse_rekordbox(xml)
            tracks = parsed["tracks"]
            assert isinstance(tracks, list)
            mark = tracks[0]["marks"][0]
            assert isinstance(mark, dict)
            self.assertEqual(rekordbox.position_ms(str(mark["Start"])), 1000)
            self.assertIn("case A", " ".join(report))

    def test_a_segment_of_six_beats_is_not_the_downbeat(self) -> None:
        """Place the next marker on beat 3 after a six-beat segment.

        Six is not a multiple of four, so Battito must not stay at 1.

        Returns:
            None. The test fails if both markers are written as downbeats.
        """
        tempos = rekordbox.tempo_entries(
            [
                {"position": 0.0, "beats": 6},
                {"position": 3.0, "bpm": 120.0},
            ]
        )
        self.assertEqual([item["Battito"] for item in tempos], ["1", "3"])
        self.assertEqual(tempos[0]["Bpm"], "120.00")


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
