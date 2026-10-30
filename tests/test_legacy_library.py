"""Older Serato libraries: ``database V2`` and crates, no ``master.sqlite`` (#126).

Read-only. The fixtures are the synthetic, spec-derived Serato 4 and 5 trees
under ``tests/fixtures``. They were built with ``build_fixtures.py``, not
captured from a real older install. Tests that need audio on disk copy the
``_Serato_`` folder into a temporary directory. No test writes inside a
fixture tree or a ``_Serato_`` folder.
"""

from __future__ import annotations

import builtins
import hashlib
import json
import os
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path, PurePosixPath, PureWindowsPath
from unittest import mock

import legacy_library
import library
import server
import setup_flow
import snapshots

FIXTURES = Path(__file__).resolve().parent / "fixtures"
VERSIONS = ("serato4", "serato5")


def _golden(version: str) -> dict[str, object]:
    """Load a fixture tree's golden.json."""
    return json.loads((FIXTURES / version / "golden.json").read_text(encoding="utf-8"))


def _tree_state(root: Path) -> dict[str, tuple[int, str]]:
    """Return every path under ``root`` with its size and SHA-256 (folders get "dir")."""
    state: dict[str, tuple[int, str]] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_dir():
            state[rel] = (0, "dir")
        else:
            data = path.read_bytes()
            state[rel] = (len(data), hashlib.sha256(data).hexdigest())
    return state


def _symlinks_work() -> bool:
    """Return whether this OS lets the test create a symlink."""
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.symlink(tmp, Path(tmp) / "link", target_is_directory=True)
        except (OSError, NotImplementedError):
            return False
    return True


class _LegacyTree:
    """A temporary drive with a copied ``_Serato_`` folder and some audio."""

    def __init__(self, version: str = "serato4", audio: tuple[str, ...] = ("one-grid.mp3", "several-grid.aiff", "café-loop.flac", "several-grid.m4a")) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.drive = Path(self._tmp.name)
        self.serato = self.drive / "_Serato_"
        shutil.copytree(FIXTURES / version / "_Serato_", self.serato)
        music = self.drive / "Music"
        music.mkdir()
        for name in audio:
            (music / name).write_bytes(b"synthetic")

    def close(self) -> None:
        """Remove the temporary drive."""
        self._tmp.cleanup()


class ParseDatabaseV2Tests(unittest.TestCase):
    """``snapshots.parse_database_v2`` reads the fixture rows exactly."""

    def test_rows_match_golden_for_serato4_and_serato5(self) -> None:
        for version in VERSIONS:
            with self.subTest(version=version):
                golden = _golden(version)
                database = golden["database"]
                assert isinstance(database, dict)
                expected = [t for t in database["tracks"] if t["path"] is not None]
                rows = snapshots.parse_database_v2((FIXTURES / version / "_Serato_" / "database V2").read_bytes())
                self.assertEqual([r["path"] for r in rows], [t["path"] for t in expected])
                self.assertEqual([r["title"] for r in rows], [t["title"] for t in expected])
                self.assertEqual([r["artist"] for r in rows], [t["artist"] for t in expected])
                self.assertEqual([r["bpm"] for r in rows], [t["bpm"] for t in expected])
                self.assertEqual([r["type"] for r in rows], [t["type"] for t in expected])
                self.assertEqual([r["serato_missing"] for r in rows], [t["missing"] for t in expected])

    def test_row_without_path_is_dropped_and_truncated_tail_is_ignored(self) -> None:
        data = (FIXTURES / "serato4" / "_Serato_" / "database V2").read_bytes()
        full = snapshots.parse_database_v2(data)
        self.assertEqual(len(full), 5)
        cut = snapshots.parse_database_v2(data[:-3])
        self.assertEqual([r["path"] for r in cut], [r["path"] for r in full][: len(cut)])
        self.assertLess(len(cut), 6)
        self.assertEqual(snapshots.parse_database_v2(b""), [])
        self.assertEqual(snapshots.parse_database_v2(b"\x00\x01garbage"), [])

    def test_crate_paths_are_not_database_rows(self) -> None:
        crate = (FIXTURES / "serato4" / "_Serato_" / "Subcrates" / "House.crate").read_bytes()
        self.assertEqual(snapshots.parse_database_v2(crate), [])


class PathTests(unittest.TestCase):
    """Drive bases and stored paths on macOS and Windows, whatever the host."""

    def test_drive_base_mac(self) -> None:
        self.assertEqual(legacy_library.drive_base(PurePosixPath("/Users/dj/Music/_Serato_")), PurePosixPath("/"))
        self.assertEqual(legacy_library.drive_base(PurePosixPath("/Volumes/USB/_Serato_")), PurePosixPath("/Volumes/USB"))
        self.assertEqual(legacy_library.drive_base(PurePosixPath("/Volumes/USB/Sub/_Serato_")), PurePosixPath("/"))
        self.assertEqual(legacy_library.drive_base(PurePosixPath("/_Serato_")), PurePosixPath("/"))

    def test_drive_base_windows(self) -> None:
        self.assertEqual(legacy_library.drive_base(PureWindowsPath(r"C:\Users\dj\Music\_Serato_")), PureWindowsPath("C:\\"))
        self.assertEqual(legacy_library.drive_base(PureWindowsPath(r"E:\_Serato_")), PureWindowsPath("E:\\"))
        self.assertEqual(legacy_library.drive_base(PureWindowsPath(r"E:\Volumes\USB\_Serato_")), PureWindowsPath("E:\\"))

    def test_track_location_joins_both_separators(self) -> None:
        mac = PurePosixPath("/Volumes/USB")
        win = PureWindowsPath("E:\\")
        self.assertEqual(legacy_library.track_location("Music/a.mp3", mac), PurePosixPath("/Volumes/USB/Music/a.mp3"))
        self.assertEqual(legacy_library.track_location("Music\\a.mp3", mac), PurePosixPath("/Volumes/USB/Music/a.mp3"))
        self.assertEqual(legacy_library.track_location("/Users/dj/Music/a.mp3", PurePosixPath("/")), PurePosixPath("/Users/dj/Music/a.mp3"))
        self.assertEqual(legacy_library.track_location("Music\\a.mp3", win), PureWindowsPath(r"E:\Music\a.mp3"))
        self.assertEqual(legacy_library.track_location("Users/dj/./Music//a.mp3", win), PureWindowsPath(r"E:\Users\dj\Music\a.mp3"))

    def test_track_location_refuses_escape_drive_letters_and_empty(self) -> None:
        base = PurePosixPath("/Volumes/USB")
        for bad in ("", "/", "\\", "../a.mp3", "Music/../../a.mp3", "Music\\..\\a.mp3", "C:\\Music\\a.mp3", "Music/a.mp3:stream"):
            with self.subTest(bad=bad):
                self.assertIsNone(legacy_library.track_location(bad, base))

    def test_track_status(self) -> None:
        present = {"/Volumes/USB", "/Volumes/USB/Music/a.mp3"}
        exists = present.__contains__
        base = PurePosixPath("/Volumes/USB")
        self.assertEqual(legacy_library.track_status(PurePosixPath("/Volumes/USB/Music/a.mp3"), base, exists=exists), "ok")
        self.assertEqual(legacy_library.track_status(PurePosixPath("/Volumes/USB/Music/b.mp3"), base, exists=exists), "missing")
        self.assertEqual(legacy_library.track_status(None, base, exists=exists), "invalid")
        unplugged = PurePosixPath("/Volumes/GONE")
        self.assertEqual(legacy_library.track_status(PurePosixPath("/Volumes/GONE/Music/a.mp3"), unplugged, exists=exists), "offline")
        win_present = {"E:\\", r"E:\Music\a.mp3"}
        self.assertEqual(legacy_library.track_status(PureWindowsPath(r"E:\Music\a.mp3"), PureWindowsPath("E:\\"), exists=win_present.__contains__), "ok")
        self.assertEqual(legacy_library.track_status(PureWindowsPath(r"F:\Music\a.mp3"), PureWindowsPath("F:\\"), exists=win_present.__contains__), "offline")

    def test_crate_name(self) -> None:
        self.assertEqual(legacy_library.crate_name("House.crate"), ("House", []))
        self.assertEqual(legacy_library.crate_name("House%%Café.crate"), ("Café", ["House"]))
        self.assertEqual(legacy_library.crate_name("A%%B%%C.crate"), ("C", ["A", "B"]))
        self.assertEqual(legacy_library.crate_name("A%%%%C.crate"), ("C", ["A"]))


class ReadLibraryTests(unittest.TestCase):
    """Browse, missing files, duplicates, and an unmounted drive."""

    def test_browse_missing_and_crates_for_both_versions(self) -> None:
        for version in VERSIONS:
            with self.subTest(version=version):
                golden = _golden(version)
                database = golden["database"]
                assert isinstance(database, dict)
                rows = [t for t in database["tracks"] if t["path"] is not None]
                present = tuple(t["path"].replace("\\", "/").rsplit("/", 1)[-1] for t in rows if not t["missing"])
                absent = [t["path"] for t in rows if t["missing"]]
                self.assertEqual(len(absent), 1)
                tree = _LegacyTree(version, audio=present)
                try:
                    result = legacy_library.read_library(tree.serato, base=tree.drive)
                finally:
                    tree.close()
                self.assertIs(result["read_only"], True)
                tracks = result["tracks"]
                assert isinstance(tracks, list)
                self.assertEqual([t["path"] for t in tracks], [t["path"] for t in rows])
                statuses = {t["path"]: t["status"] for t in tracks}
                for row in rows:
                    self.assertEqual(statuses[row["path"]], "missing" if row["missing"] else "ok", row["path"])
                missing = result["missing"]
                assert isinstance(missing, list)
                self.assertEqual([t["path"] for t in missing], absent)
                self.assertEqual(result["offline"], [])
                self.assertEqual(result["duplicates"], [])
                crates = {c["name"]: c for c in result["crates"]}  # type: ignore[union-attr]
                expected = {c["name"]: c for c in golden["crates"]}  # type: ignore[union-attr]
                self.assertEqual(sorted(crates), sorted(expected))
                for name, crate in expected.items():
                    self.assertEqual(crates[name]["parents"], crate["parents"])
                    self.assertEqual(crates[name]["tracks"], [t["path"] for t in crate["tracks"] if t["path"] is not None])

    def test_unmounted_drive_is_offline_not_missing(self) -> None:
        serato = FIXTURES / "serato4" / "drives" / "UNMOUNTED" / "_Serato_"
        gone = Path(tempfile.gettempdir()) / "serato-legacy-unplugged-drive-that-does-not-exist"
        self.assertFalse(gone.exists())
        result = legacy_library.read_library(serato, base=gone)
        self.assertEqual(result["missing"], [])
        offline = result["offline"]
        tracks = result["tracks"]
        assert isinstance(offline, list) and isinstance(tracks, list)
        self.assertEqual(len(offline), len(tracks))
        crates = result["crates"]
        assert isinstance(crates, list)
        self.assertEqual(crates[0]["name"], "Gig")
        self.assertEqual(crates[0]["tracks"], ["Music/gig-opener.mp3", "Music\\gig-closer.aiff"])

    def test_duplicates_group_same_name_ignoring_case(self) -> None:
        rows: list[dict[str, object]] = [
            {"path": "Music/A/Song.mp3", "location": "/x/Music/A/Song.mp3"},
            {"path": "Music\\B\\song.MP3", "location": "/x/Music/B/song.MP3"},
            {"path": "Music/Other.mp3", "location": "/x/Music/Other.mp3"},
            {"path": "../Song.mp3", "location": None},
        ]
        groups = legacy_library.duplicate_groups(rows)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["name"], "song.mp3")
        self.assertEqual([t["path"] for t in groups[0]["tracks"]], ["Music/A/Song.mp3", "Music\\B\\song.MP3"])  # type: ignore[union-attr]
        self.assertEqual(legacy_library.duplicate_groups(rows[2:]), [])

    def test_not_a_legacy_folder_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(legacy_library.LegacyLibraryError) as caught:
                legacy_library.read_library(Path(tmp))
            self.assertEqual(caught.exception.status, 404)
            (Path(tmp) / "_Serato_").mkdir()
            self.assertFalse(legacy_library.is_legacy_folder(Path(tmp)))
            (Path(tmp) / "_Serato_" / "database V2").mkdir()
            self.assertFalse(legacy_library.is_legacy_folder(Path(tmp)))

    def test_parent_folder_and_serato_folder_both_work(self) -> None:
        tree = _LegacyTree()
        try:
            self.assertTrue(legacy_library.is_legacy_folder(tree.drive))
            self.assertTrue(legacy_library.is_legacy_folder(tree.serato))
        finally:
            tree.close()

    @unittest.skipUnless(_symlinks_work(), "symlinks are not available")
    def test_symlinks_are_not_followed(self) -> None:
        tree = _LegacyTree()
        try:
            with tempfile.TemporaryDirectory() as other:
                link = Path(other) / "_Serato_"
                os.symlink(tree.serato, link, target_is_directory=True)
                self.assertFalse(legacy_library.is_legacy_folder(link))
                db_link_dir = Path(other) / "x" / "_Serato_"
                db_link_dir.mkdir(parents=True)
                os.symlink(tree.serato / "database V2", db_link_dir / "database V2")
                self.assertFalse(legacy_library.is_legacy_folder(db_link_dir))
                crate_link = tree.serato / "Subcrates" / "Linked.crate"
                os.symlink(tree.serato / "Subcrates" / "House.crate", crate_link)
                names = [c["name"] for c in legacy_library.read_library(tree.serato, base=tree.drive)["crates"]]  # type: ignore[union-attr]
                self.assertNotIn("Linked", names)
                self.assertIn("House", names)
        finally:
            tree.close()

    def test_read_never_writes_inside_the_serato_folder(self) -> None:
        tree = _LegacyTree()
        try:
            before = _tree_state(tree.serato)
            real_open = builtins.open
            opened: list[tuple[str, str]] = []

            def guarded(file: object, mode: str = "r", *args: object, **kwargs: object) -> object:
                opened.append((str(file), mode))
                if str(file).startswith(str(tree.serato)) and any(flag in mode for flag in "wax+"):
                    raise AssertionError(f"write inside _Serato_: {file} {mode}")
                return real_open(file, mode, *args, **kwargs)  # type: ignore[call-overload]

            master = tree.drive / "nowhere" / "master.sqlite"
            with mock.patch("builtins.open", guarded), mock.patch.object(library, "MASTER", master), \
                    mock.patch.object(legacy_library, "home_serato_folder", return_value=tree.serato), \
                    mock.patch.object(snapshots, "serato_dj_running", return_value=False):
                legacy_library.read_library(tree.serato, base=tree.drive)
                setup_flow.describe_library()
            self.assertTrue(any(path.endswith("database V2") and mode == "rb" for path, mode in opened))
            self.assertEqual(_tree_state(tree.serato), before)
            self.assertFalse((tree.drive / "nowhere").exists())
        finally:
            tree.close()

    def test_fixture_trees_are_unchanged(self) -> None:
        for version in VERSIONS:
            root = FIXTURES / version
            before = _tree_state(root)
            legacy_library.read_library(root / "_Serato_", base=Path(tempfile.gettempdir()) / "serato-legacy-nothing")
            legacy_library.read_library(root / "drives" / "UNMOUNTED" / "_Serato_")
            self.assertEqual(_tree_state(root), before)


class FindLegacyTests(unittest.TestCase):
    """A newer library always wins over ``database V2``."""

    def test_master_present_wins(self) -> None:
        tree = _LegacyTree()
        try:
            master = tree.drive / "master.sqlite"
            self.assertEqual(legacy_library.find_legacy_library(master, [tree.serato]), tree.serato)
            master.write_bytes(b"x")
            self.assertIsNone(legacy_library.find_legacy_library(master, [tree.serato]))
        finally:
            tree.close()

    def test_first_matching_candidate_is_used(self) -> None:
        tree = _LegacyTree()
        try:
            missing = tree.drive / "nope"
            self.assertEqual(legacy_library.find_legacy_library(missing / "master.sqlite", [missing, tree.drive]), tree.serato)
            self.assertIsNone(legacy_library.find_legacy_library(missing / "master.sqlite", [missing]))
        finally:
            tree.close()

    def test_refuse_write(self) -> None:
        with self.assertRaises(legacy_library.LegacyLibraryError) as caught:
            legacy_library.refuse_write()
        self.assertEqual(caught.exception.status, 409)
        self.assertEqual(caught.exception.message, legacy_library.WRITE_BLOCKED)


class SetupWordingTests(unittest.TestCase):
    """Setup explains an older library instead of saying not found."""

    def setUp(self) -> None:
        self.tree = _LegacyTree()
        self.master = self.tree.drive / "elsewhere" / "master.sqlite"
        self.patches = [
            mock.patch.object(library, "MASTER", self.master),
            mock.patch.object(snapshots, "serato_dj_running", return_value=False),
            mock.patch.object(setup_flow, "volume_label", return_value="Macintosh HD"),
        ]
        for patch in self.patches:
            patch.start()
        setup_flow._set_chosen_legacy(None)

    def tearDown(self) -> None:
        for patch in reversed(self.patches):
            patch.stop()
        setup_flow._set_chosen_legacy(None)
        self.tree.close()

    def test_legacy_library_is_described_in_plain_words(self) -> None:
        with mock.patch.object(legacy_library, "home_serato_folder", return_value=self.tree.serato):
            info = setup_flow.describe_library()
        self.assertIs(info["found"], False)
        self.assertIs(info["legacy"], True)
        self.assertIs(info["read_only"], True)
        self.assertIs(info["status_writable"], False)
        self.assertEqual(info["summary"], "Found an older Serato library on Macintosh HD, 5 tracks.")
        self.assertEqual(info["next"], legacy_library.LEGACY_NEXT)
        self.assertNotEqual(info["summary"], setup_flow.NOT_FOUND_SUMMARY)
        for word in ("database", "sqlite", "V2", str(self.tree.drive)):
            self.assertNotIn(word, json.dumps(info))

    def test_no_legacy_library_still_says_not_found(self) -> None:
        with mock.patch.object(legacy_library, "home_serato_folder", return_value=self.tree.drive / "none"):
            info = setup_flow.describe_library()
        self.assertEqual(info["summary"], setup_flow.NOT_FOUND_SUMMARY)
        self.assertNotIn("legacy", info)

    def test_choosing_the_older_folder_in_setup(self) -> None:
        with mock.patch.object(legacy_library, "home_serato_folder", return_value=self.tree.drive / "none"):
            info = setup_flow.accept_folder(str(self.tree.drive))
            self.assertIs(info["legacy"], True)
            chosen = setup_flow.legacy_folder()
            assert chosen is not None
            # Windows may hand back an 8.3 short name (RUNNER~1) for the temp dir.
            self.assertTrue(os.path.samefile(chosen, self.tree.serato))
            self.assertEqual(chosen.name, "_Serato_")
        self.assertFalse(self.master.exists())


class LegacyApiTests(unittest.TestCase):
    """``GET /api/legacy-library`` reads; write routes answer 409."""

    def setUp(self) -> None:
        self.tree = _LegacyTree()
        self.master = self.tree.drive / "elsewhere" / "master.sqlite"
        self.patches = [
            mock.patch.object(library, "MASTER", self.master),
            mock.patch.object(snapshots, "serato_dj_running", return_value=False),
            mock.patch.object(legacy_library, "home_serato_folder", return_value=self.tree.serato),
            mock.patch.object(legacy_library, "drive_base", return_value=self.tree.drive),
        ]
        for patch in self.patches:
            patch.start()
        setup_flow._set_chosen_legacy(None)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
        for patch in reversed(self.patches):
            patch.stop()
        self.tree.close()

    def _call(self, path: str, payload: dict[str, object] | None = None) -> tuple[int, dict[str, object]]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(self.base + path, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            body = json.loads(exc.read())
            exc.close()
            return exc.code, body

    def test_get_reads_tracks_missing_and_crates(self) -> None:
        status, body = self._call("/api/legacy-library")
        self.assertEqual(status, 200)
        self.assertIs(body["read_only"], True)
        self.assertEqual(len(body["tracks"]), 5)  # type: ignore[arg-type]
        self.assertEqual([t["path"] for t in body["missing"]], ["Music/not-on-disk.mp3"])  # type: ignore[union-attr]

    def test_every_write_route_is_refused_and_nothing_changes(self) -> None:
        before = _tree_state(self.tree.serato)
        self.assertEqual(server.LEGACY_ALLOWED_POSTS, frozenset({"/api/related", "/api/reveal"}))
        routes = ["/api/track", "/api/crate", "/api/import.m3u", "/api/duplicates/merge", "/api/files", "/api/snapshots", "/api/some-future-write"]
        for route in routes:
            with self.subTest(route=route):
                status, body = self._call(route, {})
                self.assertEqual(status, 409)
                self.assertEqual(body["error"], legacy_library.WRITE_BLOCKED)
        self.assertEqual(_tree_state(self.tree.serato), before)
        self.assertFalse(self.master.exists())

    def test_without_an_older_library_get_is_404_and_writes_are_not_intercepted(self) -> None:
        with mock.patch.object(legacy_library, "home_serato_folder", return_value=self.tree.drive / "none"):
            status, _ = self._call("/api/legacy-library")
            self.assertEqual(status, 404)
            status, body = self._call("/api/crate", {})
            self.assertNotEqual(status, 409)
            self.assertNotEqual(body.get("error"), legacy_library.WRITE_BLOCKED)

    def test_related_and_reveal_are_not_blocked(self) -> None:
        for route in ("/api/related", "/api/reveal"):
            with self.subTest(route=route):
                status, body = self._call(route, {})
                self.assertNotEqual(status, 409)
                self.assertNotEqual(body.get("error"), legacy_library.WRITE_BLOCKED)


if __name__ == "__main__":
    unittest.main()
