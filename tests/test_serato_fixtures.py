"""Parse the spec-derived Serato fixtures without a live Serato install.

The builder writes the bytes from the published notes. These tests read
them back. MP3, AIFF, FLAC, and M4A all go through ``tags.read_serato_tags``.
Issue #47, which ignored FLAC and M4A, was fixed by pull request #55.
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from tests.fixture import ROOT
from tests.serato_spec import (
    CRATE_VERSION,
    DATABASE_VERSION,
    availability,
    chunk_tracks,
    crate_name,
    normalize_path,
    tags_from_audio,
)
from tags import _parse_beatgrid, _parse_markers2, read_serato_tags


FIXTURES = ROOT / "tests" / "fixtures"


def _builder():
    """Load the fixture builder without running it.

    Returns:
        The builder module. It does not import the application.
    """
    path = FIXTURES / "build_fixtures.py"
    spec = importlib.util.spec_from_file_location("serato_fixture_builder", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("The fixture builder could not be loaded.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _golden(version: str) -> dict[str, object]:
    """Load one tree's expected parse.

    Args:
        version: ``serato4`` or ``serato5``.

    Returns:
        The golden document.
    """
    return json.loads((FIXTURES / version / "golden.json").read_text(encoding="utf-8"))


def _manifest(version: str) -> dict[str, object]:
    """Load one tree's manifest.

    Args:
        version: ``serato4`` or ``serato5``.

    Returns:
        The manifest document.
    """
    return json.loads((FIXTURES / version / "manifest.json").read_text(encoding="utf-8"))


class FixtureManifestTests(unittest.TestCase):
    """The committed trees cite the notes and do not invent Serato 5 storage."""

    def test_builder_does_not_import_the_application(self) -> None:
        """Keep the builder independent of the tag and library modules.

        Returns:
            None. The test fails if the builder imports application code.
        """
        text = (FIXTURES / "build_fixtures.py").read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                self.assertNotIn("tags", stripped)
                self.assertNotIn("library", stripped)
                self.assertNotIn("files", stripped)
                self.assertNotIn("rekordbox", stripped)
                self.assertNotIn("server", stripped)

    def test_committed_bytes_match_a_fresh_build(self) -> None:
        """Regenerate into a temporary directory and compare every fixture.

        Returns:
            None. The test fails if a committed file drifts from the builder.
        """
        builder = _builder()
        with tempfile.TemporaryDirectory() as folder:
            builder.build(Path(folder))
            fresh = Path(folder)
            committed = [
                path.relative_to(FIXTURES)
                for path in FIXTURES.rglob("*")
                if path.is_file() and path.name != "build_fixtures.py" and "__pycache__" not in path.parts
            ]
            rebuilt = [
                path.relative_to(fresh)
                for path in fresh.rglob("*")
                if path.is_file() and "__pycache__" not in path.parts
            ]
            self.assertEqual(sorted(committed), sorted(rebuilt))
            for rel in committed:
                self.assertEqual((FIXTURES / rel).read_bytes(), (fresh / rel).read_bytes(), str(rel))

    def test_serato5_is_unverified_and_does_not_invent_storage(self) -> None:
        """Mark every Serato 5 file unverified and leave Lucid and Protect out.

        Returns:
            None. The test fails if a Serato 5 file is marked verified or the
            note stops mentioning the probe.
        """
        manifest = _manifest("serato5")
        self.assertEqual(manifest["status"], "spec-derived, unverified")
        note = str(manifest["note"])
        self.assertIn("serato5-probe.sh", note)
        self.assertIn("Lucid", note)
        self.assertIn("Protect Library", note)
        files = manifest["files"]
        self.assertIsInstance(files, list)
        assert isinstance(files, list)
        self.assertGreaterEqual(len(files), 1)
        for item in files:
            self.assertIsInstance(item, dict)
            assert isinstance(item, dict)
            self.assertEqual(item["status"], "spec-derived, unverified")
            self.assertIn("Holzhaus", str(item["citation"]))
            self.assertLess(int(item["bytes"]), 8192)
        golden = json.dumps(_golden("serato5"))
        self.assertNotIn("lucid", golden.lower())
        self.assertNotIn("protect library", golden.lower())

    def test_serato4_is_spec_derived(self) -> None:
        """Mark every Serato 4 file spec-derived and cite a published note.

        Returns:
            None. The test fails if a file is unverified or has no citation.
        """
        manifest = _manifest("serato4")
        self.assertEqual(manifest["status"], "spec-derived")
        files = manifest["files"]
        self.assertIsInstance(files, list)
        assert isinstance(files, list)
        for item in files:
            self.assertIsInstance(item, dict)
            assert isinstance(item, dict)
            self.assertEqual(item["status"], "spec-derived")
            self.assertNotIn("unverified", str(item["status"]))
            self.assertTrue((FIXTURES / "serato4" / str(item["path"])).is_file())
            self.assertIn("https://github.com/Holzhaus/", str(item["citation"]))
            self.assertLess(int(item["bytes"]), 8192)

    def test_readme_lists_each_fixture(self) -> None:
        """Point the README at every committed fixture and its status.

        Returns:
            None. The test fails if a manifest path is missing from the README.
        """
        readme = (FIXTURES / "README.md").read_text(encoding="utf-8")
        for version in ("serato4", "serato5"):
            files = _manifest(version)["files"]
            self.assertIsInstance(files, list)
            assert isinstance(files, list)
            for item in files:
                self.assertIsInstance(item, dict)
                assert isinstance(item, dict)
                self.assertIn(str(item["path"]), readme)
                self.assertIn(str(item["status"]), readme)


class ChunkParseTests(unittest.TestCase):
    """Crates and database V2 match the golden field for field."""

    def test_database_and_crates_match_the_golden(self) -> None:
        """Read both trees' database and crate files.

        Covers a nested crate, a unicode name, an empty crate, a Windows
        path, a POSIX path, a path with no file, and a track with no path
        field. None of those rows are dropped.

        Returns:
            None. The test fails if a field differs or a row disappears.
        """
        for version in ("serato4", "serato5"):
            golden = _golden(version)
            root = FIXTURES / version
            database = golden["database"]
            self.assertIsInstance(database, dict)
            assert isinstance(database, dict)
            version_text, tracks, error = chunk_tracks((root / "_Serato_" / "database V2").read_bytes())
            self.assertIsNone(error)
            self.assertEqual(version_text, DATABASE_VERSION)
            self.assertEqual(version_text, database["version"])
            expected_tracks = database["tracks"]
            self.assertIsInstance(expected_tracks, list)
            assert isinstance(expected_tracks, list)
            self.assertEqual(len(tracks), len(expected_tracks))
            separators = set()
            for got, expected in zip(tracks, expected_tracks):
                self.assertIsInstance(expected, dict)
                assert isinstance(expected, dict)
                self.assertEqual(got["path"], expected["path"])
                self.assertEqual(got["title"], expected["title"])
                self.assertEqual(got["artist"], expected["artist"])
                self.assertEqual(got["bpm"], expected["bpm"])
                self.assertEqual(got["type"], expected["type"])
                self.assertEqual(got["missing"], expected["missing"])
                if isinstance(got["path"], str) and got["path"]:
                    separators.add("windows" if "\\" in got["path"] else "posix")
            self.assertEqual(separators, {"windows", "posix"})
            missing_paths = [row for row in tracks if row["path"] is None or row["missing"] is True]
            self.assertGreaterEqual(len(missing_paths), 2)
            crates = golden["crates"]
            self.assertIsInstance(crates, list)
            assert isinstance(crates, list)
            names = []
            for crate in crates:
                self.assertIsInstance(crate, dict)
                assert isinstance(crate, dict)
                path = root / str(crate["file"])
                parents, name = crate_name(path.name)
                self.assertEqual(name, crate["name"])
                self.assertEqual(parents, crate["parents"])
                names.append(name)
                text, rows, crate_error = chunk_tracks(path.read_bytes())
                self.assertIsNone(crate_error)
                self.assertEqual(text, CRATE_VERSION)
                expected_rows = crate["tracks"]
                self.assertIsInstance(expected_rows, list)
                assert isinstance(expected_rows, list)
                self.assertEqual([row["path"] for row in rows], [item["path"] for item in expected_rows])
            self.assertIn("Empty", names)
            self.assertTrue(any(len(part) > 0 for part in names if part != "House" and part != "Empty"))
            empty = next(crate for crate in crates if crate["name"] == "Empty")
            self.assertEqual(empty["tracks"], [])

    def test_truncated_crate_keeps_the_rows_that_were_complete(self) -> None:
        """Keep earlier tracks when a crate is cut off mid-record.

        Returns:
            None. The test fails if the cut file is rewritten or the first
            track disappears.
        """
        for version in ("serato4", "serato5"):
            root = FIXTURES / version
            full_path = root / "_Serato_" / "Subcrates" / "House.crate"
            cut_path = root / "edge" / "truncated.crate"
            before = cut_path.read_bytes()
            full_version, full_rows, full_error = chunk_tracks(full_path.read_bytes())
            cut_version, cut_rows, cut_error = chunk_tracks(before)
            self.assertIsNone(full_error)
            self.assertEqual(cut_error, "truncated-body")
            self.assertEqual(cut_version, full_version)
            self.assertGreater(len(full_rows), len(cut_rows))
            self.assertGreaterEqual(len(cut_rows), 1)
            self.assertEqual(cut_rows[0]["path"], full_rows[0]["path"])
            self.assertEqual(cut_path.read_bytes(), before)

    def test_unmounted_volume_is_unavailable_and_not_deleted(self) -> None:
        """Leave an unmounted drive's crate rows in place.

        Returns:
            None. The test fails if a track is dropped or the crate file changes.
        """
        for version in ("serato4", "serato5"):
            golden = _golden(version)
            unmounted = golden["unmounted"]
            self.assertIsInstance(unmounted, dict)
            assert isinstance(unmounted, dict)
            path = FIXTURES / version / str(unmounted["crate"])
            before = path.read_bytes()
            text, rows, error = chunk_tracks(before)
            self.assertIsNone(error)
            self.assertEqual(text, unmounted["version"])
            self.assertEqual([row["path"] for row in rows], unmounted["tracks"])
            self.assertGreaterEqual(len(rows), 2)
            absent = Path("/Volumes/NOT-MOUNTED")
            self.assertFalse(absent.exists())
            for row in rows:
                status = availability(row["path"] if isinstance(row["path"], str) else None, absent)
                self.assertEqual(status, "unavailable")
            with tempfile.TemporaryDirectory() as mounted:
                for row in rows:
                    status = availability(row["path"] if isinstance(row["path"], str) else None, Path(mounted))
                    self.assertEqual(status, "unavailable")
            self.assertEqual(path.read_bytes(), before)
            normalized = {normalize_path(str(row["path"])) for row in rows}
            self.assertEqual(len(normalized), len(rows))


class AudioParseTests(unittest.TestCase):
    """Markers2 and BeatGrid fields match the golden."""

    def test_spec_reader_matches_every_audio_fixture(self) -> None:
        """Decode MP3, AIFF, FLAC, and M4A with the spec reader.

        Returns:
            None. The test fails if a cue, loop, flip, color, lock, or grid
            field differs, including the beatgrid footer.
        """
        for version in ("serato4", "serato5"):
            golden = _golden(version)
            audio = golden["audio"]
            self.assertIsInstance(audio, list)
            assert isinstance(audio, list)
            grids = set()
            for spec in audio:
                self.assertIsInstance(spec, dict)
                assert isinstance(spec, dict)
                parsed = tags_from_audio(FIXTURES / version / str(spec["file"]))
                self.assertIsNotNone(parsed)
                assert parsed is not None
                self._assert_fields(parsed, spec)
                self.assertEqual(parsed["track_color"], spec["track_color"])
                self.assertEqual(parsed["beatgrid_locked"], spec["beatgrid_locked"])
                self.assertEqual(parsed["footer"], spec["footer"])
                beatgrid = spec["beatgrid"]
                self.assertIsInstance(beatgrid, list)
                assert isinstance(beatgrid, list)
                grids.add(len(beatgrid))
            self.assertIn(1, grids)
            self.assertTrue(any(count > 1 for count in grids))

    def test_mp3_and_aiff_match_the_production_reader(self) -> None:
        """Read ID3 GEOB fixtures with ``read_serato_tags``.

        Returns:
            None. The test fails if a parsed field differs from the golden.
        """
        for version in ("serato4", "serato5"):
            for spec in self._audio(version):
                container = spec["container"]
                if container not in {"mp3", "aiff"}:
                    continue
                parsed = read_serato_tags(str(FIXTURES / version / str(spec["file"])))
                self.assertTrue(parsed["found"])
                self._assert_fields(parsed, spec)

    def test_flac_read_matches_the_golden(self) -> None:
        """Read SERATO_MARKERS_V2 from the FLAC fixtures.

        Issue #47 was fixed by pull request #55. ``read_serato_tags`` now
        reads the Vorbis comment, so these cues, loops, flips, and beatgrid
        markers match the golden. This test is not an expected failure.

        Returns:
            None. The test fails if a FLAC fixture is unread or a field differs.
        """
        self._expect_production("flac")

    def test_m4a_read_matches_the_golden(self) -> None:
        """Read ``com.serato.dj`` ``markersv2`` atoms from the M4A fixtures.

        Issue #47 was fixed by pull request #55. ``read_serato_tags`` now
        reads the freeform atom, so these cues, loops, flips, and beatgrid
        markers match the golden. This test is not an expected failure.

        Returns:
            None. The test fails if an M4A fixture is unread or a field differs.
        """
        self._expect_production("m4a")

    def test_truncated_and_missing_audio_do_not_raise(self) -> None:
        """Return empty markers for a cut tag, a cut header, and a missing path.

        Returns:
            None. The test fails if a short tag raises or invents a cue.
        """
        for version in ("serato4", "serato5"):
            root = FIXTURES / version / "edge"
            short = read_serato_tags(str(root / "truncated-tags.mp3"))
            self.assertTrue(short["found"])
            self.assertEqual(short["cues"], [])
            self.assertEqual(short["loops"], [])
            self.assertEqual(short["beatgrid"], [])
            cut = read_serato_tags(str(root / "cut-header.mp3"))
            self.assertFalse(cut["found"])
            self.assertEqual(cut["cues"], [])
            missing = read_serato_tags(str(root / "no-such-track.mp3"))
            self.assertFalse(missing["found"])
            self.assertEqual(missing["cues"], [])

    def test_marker_fields_round_trip(self) -> None:
        """Encode edited cue, loop, and beatgrid fields and parse them back.

        The encoder is the fixture builder. The parser is the application.
        Each edited field has to come back unchanged.

        Returns:
            None. The test fails if a field moves or a unicode name is lost.
        """
        builder = _builder()
        spec = self._audio("serato4")[0]
        for name, color, start_ms in (("Drop", "#CC0000", 1500), ("Caf\u00e9", "#112233", 50), ("\u6df1\u591c", "#ABCDEF", 9000)):
            edited = json.loads(json.dumps(spec))
            edited["cues"][0]["name"] = name
            edited["cues"][0]["color"] = color
            edited["cues"][0]["start_ms"] = start_ms
            edited["loops"][0]["locked"] = False
            edited["loops"][0]["end_ms"] = 4242
            parsed = _parse_markers2(builder.markers2_payload(edited))
            self.assertEqual(parsed["cues"][0]["name"], name)
            self.assertEqual(parsed["cues"][0]["color"], color)
            self.assertEqual(parsed["cues"][0]["start_ms"], start_ms)
            self.assertEqual(parsed["cues"][0]["index"], edited["cues"][0]["index"])
            self.assertFalse(parsed["loops"][0]["locked"])
            self.assertEqual(parsed["loops"][0]["end_ms"], 4242)
            self.assertEqual(parsed["loops"][0]["color"], edited["loops"][0]["color"])
            self.assertEqual(parsed["flips"][0]["name"], edited["flips"][0]["name"])
            self.assertTrue(parsed["flips"][0]["enabled"])
        grid = [
            {"position": 0.0, "beats": 16},
            {"position": 4.0, "beats": 8},
            {"position": 8.0, "bpm": 140.0},
        ]
        payload = builder.beatgrid_payload(grid, 0x37)
        parsed_grid = _parse_beatgrid(payload)
        self.assertEqual(parsed_grid[0]["beats"], 16)
        self.assertEqual(parsed_grid[0]["position"], 0.0)
        self.assertEqual(parsed_grid[1]["beats"], 8)
        self.assertEqual(parsed_grid[2]["bpm"], 140.0)
        self.assertEqual(parsed_grid[2]["position"], 8.0)
        single = _parse_beatgrid(builder.beatgrid_payload([{"position": 0.5, "bpm": 128.0}], 0))
        self.assertEqual(single, [{"position": 0.5, "bpm": 128.0}])

    def _expect_production(self, container: str) -> None:
        """Assert the production reader matches one container's goldens.

        Args:
            container: ``flac`` or ``m4a``.

        Returns:
            None. The assertion fails while that container is unread.
        """
        for version in ("serato4", "serato5"):
            matched = [spec for spec in self._audio(version) if spec["container"] == container]
            self.assertEqual(len(matched), 1)
            spec = matched[0]
            parsed = read_serato_tags(str(FIXTURES / version / str(spec["file"])))
            self.assertTrue(parsed["found"])
            self._assert_fields(parsed, spec)

    def _audio(self, version: str) -> list[dict[str, object]]:
        """Return the audio specs for one tree.

        Args:
            version: ``serato4`` or ``serato5``.

        Returns:
            The golden audio list.
        """
        audio = _golden(version)["audio"]
        self.assertIsInstance(audio, list)
        assert isinstance(audio, list)
        specs = [item for item in audio if isinstance(item, dict)]
        self.assertEqual(len(specs), len(audio))
        return specs

    def _assert_fields(self, parsed: dict[str, object], spec: dict[str, object]) -> None:
        """Compare cue, loop, flip, and beatgrid fields.

        Args:
            parsed: Reader output.
            spec: Golden audio entry.

        Returns:
            None. The test fails if a field differs.
        """
        self.assertEqual(parsed["cues"], spec["cues"])
        self.assertEqual(parsed["loops"], spec["loops"])
        self.assertEqual(parsed["flips"], spec["flips"])
        self.assertEqual(parsed["beatgrid"], spec["beatgrid"])


if __name__ == "__main__":
    unittest.main()
