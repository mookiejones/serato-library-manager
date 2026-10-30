"""``database V2`` tracks reach snapshots (#128).

``database V2`` keeps each path in an ``otrk``'s ``pfil`` field, while crates
use ``ptrk``. Before the fix the shared parser read only ``ptrk`` and returned
nothing for ``database V2``, so a track listed only there was left out of a
snapshot. Synthetic fixtures only; nothing is written inside a fixture tree.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import snapshots

FIXTURES = Path(__file__).resolve().parent / "fixtures"
VERSIONS = ("serato4", "serato5")


def _chunk(tag: str, body: bytes) -> bytes:
    """Encode one Serato chunk."""
    return tag.encode("ascii") + len(body).to_bytes(4, "big") + body


def _text(tag: str, value: str) -> bytes:
    """Encode one UTF-16-BE text chunk."""
    return _chunk(tag, value.encode("utf-16-be"))


def _golden(version: str) -> dict[str, object]:
    """Load a fixture tree's golden.json."""
    return json.loads((FIXTURES / version / "golden.json").read_text(encoding="utf-8"))


def _tree_hash(root: Path) -> str:
    """Hash every name and byte under ``root``."""
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        digest.update(path.relative_to(root).as_posix().encode())
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()


class ParseDatabaseV2PathsTests(unittest.TestCase):
    """``parse_serato_bytes`` returns ``pfil`` paths from ``database V2``."""

    def test_database_v2_paths_match_golden(self) -> None:
        for version in VERSIONS:
            with self.subTest(version=version):
                database = _golden(version)["database"]
                assert isinstance(database, dict)
                expected = [t["path"] for t in database["tracks"] if t["path"] is not None]
                self.assertEqual(len(expected), 5)
                data = (FIXTURES / version / "_Serato_" / "database V2").read_bytes()
                self.assertEqual(snapshots.parse_serato_bytes(data), expected)

    def test_legacy_reader_and_snapshot_parser_agree(self) -> None:
        for version in VERSIONS:
            for rel in ("_Serato_/database V2", "drives/UNMOUNTED/_Serato_/database V2"):
                with self.subTest(version=version, rel=rel):
                    data = (FIXTURES / version / rel).read_bytes()
                    rows = snapshots.parse_database_v2(data)
                    self.assertEqual([r["path"] for r in rows], snapshots.parse_serato_bytes(data))
        both = _chunk("otrk", _text("pfil", "Music/a.mp3") + _text("ptrk", "Music/b.mp3") + _text("tsng", "T"))
        self.assertEqual(snapshots.parse_database_v2(both), [{"title": "T", "path": "Music/a.mp3"}])
        self.assertEqual(snapshots.parse_database_v2(_chunk("otrk", _text("pfil", "") + _text("tsng", "T"))), [])

    def test_unmounted_drive_database_is_read(self) -> None:
        for version in VERSIONS:
            with self.subTest(version=version):
                data = (FIXTURES / version / "drives" / "UNMOUNTED" / "_Serato_" / "database V2").read_bytes()
                self.assertGreater(len(snapshots.parse_serato_bytes(data)), 0)

    def test_crates_are_unchanged(self) -> None:
        for version in VERSIONS:
            for crate in _golden(version)["crates"]:  # type: ignore[union-attr]
                with self.subTest(version=version, crate=crate["file"]):
                    data = (FIXTURES / version / crate["file"]).read_bytes()
                    expected = [t["path"] for t in crate["tracks"] if t["path"] is not None]
                    self.assertEqual(snapshots.parse_serato_bytes(data), expected)

    def test_one_path_per_track_when_both_fields_exist(self) -> None:
        data = _chunk("otrk", _text("pfil", "Music/a.mp3") + _text("ptrk", "Music/b.mp3"))
        self.assertEqual(snapshots.parse_serato_bytes(data), ["Music/a.mp3"])
        data = _chunk("otrk", _text("ptrk", "Music/b.mp3") + _text("pfil", "Music/a.mp3"))
        self.assertEqual(snapshots.parse_serato_bytes(data), ["Music/b.mp3"])

    def test_empty_truncated_and_odd_input(self) -> None:
        good = _chunk("otrk", _text("pfil", "Music/a.mp3"))
        self.assertEqual(snapshots.parse_serato_bytes(b""), [])
        self.assertEqual(snapshots.parse_serato_bytes(_chunk("otrk", _text("pfil", ""))), [])
        self.assertEqual(snapshots.parse_serato_bytes(_chunk("otrk", _text("tsng", "Title"))), [])
        self.assertEqual(snapshots.parse_serato_bytes(good + good[:-2]), ["Music/a.mp3"])
        self.assertEqual(snapshots.parse_serato_bytes(_text("pfil", "Music/top.mp3")), [])
        self.assertEqual(
            snapshots.parse_serato_bytes(_chunk("otrk", _text("pfil", "Music\\Win\\c.aiff"))),
            ["Music\\Win\\c.aiff"],
        )
        self.assertEqual(
            snapshots.parse_serato_bytes(_chunk("otrk", _chunk("pfil", b"\xfe\xff" + "Music/d.mp3".encode("utf-16-be") + b"\x00\x00"))),
            ["Music/d.mp3"],
        )


class AudioPathsTests(unittest.TestCase):
    """A track only in ``database V2`` is now part of a snapshot."""

    def test_database_only_tracks_reach_audio_paths(self) -> None:
        for version in VERSIONS:
            with self.subTest(version=version), tempfile.TemporaryDirectory() as tmp:
                drive = Path(tmp)
                serato = drive / "_Serato_"
                serato.mkdir()
                source = FIXTURES / version / "_Serato_" / "database V2"
                shutil.copyfile(source, serato / "database V2")
                database = _golden(version)["database"]
                assert isinstance(database, dict)
                present = [t["path"] for t in database["tracks"] if t["path"] is not None and not t["missing"]]
                music = drive / "Music"
                music.mkdir()
                for path in present:
                    (music / path.replace("\\", "/").rsplit("/", 1)[-1]).write_bytes(b"synthetic")
                spec = snapshots.DriveSpec(
                    drive_id="usb", label="USB", serato_root=serato, music_root=drive, role="external", present=True,
                )
                before = _tree_hash(serato)
                record = {"drive_id": "usb", "files": [{"path": "database V2"}]}
                found = snapshots._audio_paths(drive / "no-master.sqlite", spec, [record])
                self.assertEqual(sorted(p.name for p in found), sorted(p.replace("\\", "/").rsplit("/", 1)[-1] for p in present))
                self.assertEqual(len(found), 4)
                self.assertEqual(_tree_hash(serato), before)
                self.assertFalse((drive / "no-master.sqlite").exists())

    def test_database_v2_crate_row_lists_tracks(self) -> None:
        data = (FIXTURES / "serato4" / "_Serato_" / "database V2").read_bytes()
        rows = snapshots._crates_from_file("usb", "USB", False, "database V2", data)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], "database-v2")
        self.assertEqual(len(rows[0]["tracks"]), 5)

    def test_fixture_tree_unchanged(self) -> None:
        for version in VERSIONS:
            before = _tree_hash(FIXTURES / version)
            snapshots.parse_serato_bytes((FIXTURES / version / "_Serato_" / "database V2").read_bytes())
            self.assertEqual(_tree_hash(FIXTURES / version), before)


if __name__ == "__main__":
    unittest.main()
