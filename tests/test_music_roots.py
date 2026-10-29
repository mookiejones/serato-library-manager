"""Music-root discovery for the Files page.

Paths and volumes are fixtures. The tests do not read a live Serato
library or a real external drive.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path, PurePosixPath, PureWindowsPath

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import music_roots
from tests.fixture import TempLibrary, open_database


def _drive_text(path: Path) -> str:
    """Collapse slash styles so a Windows drive letter compares on any OS.

    Args:
        path: Drive or marker path built with pathlib.

    Returns:
        A lowercase path with single backslashes.
    """
    text = str(path).replace("/", "\\").casefold()
    while "\\\\" in text:
        text = text.replace("\\\\", "\\")
    return text


class CollapseTests(unittest.TestCase):
    """Album folders collapse per volume, and the computer root is not a result."""

    def test_mac_album_folders_collapse_to_music_and_a_volume(self) -> None:
        """Share one Music folder, and keep a different volume separate.

        Returns:
            None. The test fails if each album is its own root.
        """
        folders = music_roots.collapse_track_folders(
            [
                PurePosixPath("/Users/dj/Music/House/Album"),
                PurePosixPath("/Users/dj/Music/Techno"),
                PurePosixPath("/Volumes/GIGDRIVE/Sets/Friday"),
                PurePosixPath("/Volumes/GIGDRIVE/Sets/Saturday"),
            ]
        )
        self.assertEqual(
            folders,
            [
                PurePosixPath("/Users/dj/Music"),
                PurePosixPath("/Volumes/GIGDRIVE/Sets"),
            ],
        )

    def test_a_track_folder_and_its_album_stay_the_music_folder(self) -> None:
        """Keep Music when a track sits in Music and another sits in an album.

        Returns:
            None. The test fails if the album replaces Music.
        """
        folders = music_roots.collapse_track_folders(
            [
                PurePosixPath("/Users/dj/Music"),
                PurePosixPath("/Users/dj/Music/House"),
            ]
        )
        self.assertEqual(folders, [PurePosixPath("/Users/dj/Music")])

    def test_paths_that_split_at_the_computer_root_stay_split(self) -> None:
        """Do not offer the computer root when music lives in two top folders.

        Returns:
            None. The test fails if the result is ``/``.
        """
        folders = music_roots.collapse_track_folders(
            [
                PurePosixPath("/Users/dj/Music/House"),
                PurePosixPath("/opt/audio/Sets"),
            ]
        )
        self.assertEqual(
            folders,
            [
                PurePosixPath("/opt/audio/Sets"),
                PurePosixPath("/Users/dj/Music/House"),
            ],
        )
        self.assertNotIn(PurePosixPath("/"), folders)
        self.assertNotIn(PurePosixPath("/Volumes"), folders)

    def test_windows_album_folders_collapse_per_drive(self) -> None:
        """Collapse albums on each drive letter, and keep the drives apart.

        Returns:
            None. The test fails if C: and E: share one root.
        """
        folders = music_roots.collapse_track_folders(
            [
                PureWindowsPath("C:/Users/dj/Music/House"),
                PureWindowsPath("C:/Users/dj/Music/Techno"),
                PureWindowsPath("E:/DJ/Sets/Friday"),
                PureWindowsPath("E:/DJ/Sets/Saturday"),
            ]
        )
        self.assertEqual(
            [str(item) for item in folders],
            [
                str(PureWindowsPath("C:/Users/dj/Music")),
                str(PureWindowsPath("E:/DJ/Sets")),
            ],
        )

    def test_windows_does_not_use_the_drive_root_when_folders_split(self) -> None:
        """Split top-level folders on a drive instead of returning the drive.

        Returns:
            None. The test fails if the result is ``C:\\``.
        """
        folders = music_roots.collapse_track_folders(
            [
                PureWindowsPath("C:/Music/House"),
                PureWindowsPath("C:/Music/Techno"),
                PureWindowsPath("C:/Other/Clip"),
            ]
        )
        self.assertEqual(
            [str(item) for item in folders],
            [
                str(PureWindowsPath("C:/Music")),
                str(PureWindowsPath("C:/Other/Clip")),
            ],
        )


class WidenTests(unittest.TestCase):
    """A common ancestor that is home, /, or /Volumes is not a root."""

    def test_music_and_downloads_stay_apart(self) -> None:
        """Keep ~/Music and ~/Downloads when both hold tracks.

        Returns:
            None. The test fails if the root is the home directory.
        """
        home = PurePosixPath("/Users/dj")
        folders = music_roots.collapse_track_folders(
            [
                home / "Music" / "House",
                home / "Music" / "Techno",
                home / "Downloads" / "mix",
            ],
            home=home,
        )
        self.assertEqual(
            folders,
            [
                home / "Downloads" / "mix",
                home / "Music",
            ],
        )
        self.assertNotIn(home, folders)
        self.assertNotIn(PurePosixPath("/"), folders)
        self.assertNotIn(PurePosixPath("/Volumes"), folders)

    def test_windows_home_is_not_the_root(self) -> None:
        """Keep Music and Downloads apart on a Windows profile.

        Returns:
            None. The test fails if the root is the profile directory.
        """
        home = PureWindowsPath("C:/Users/dj")
        folders = music_roots.collapse_track_folders(
            [
                home / "Music" / "House",
                home / "Downloads" / "Set",
            ],
            home=home,
        )
        self.assertEqual(
            [str(item) for item in folders],
            [
                str(home / "Downloads" / "Set"),
                str(home / "Music" / "House"),
            ],
        )
        self.assertNotIn(str(home), [str(item) for item in folders])
        self.assertNotIn(str(PureWindowsPath("C:/")), [str(item) for item in folders])

    def test_two_volume_roots_do_not_widen_to_volumes(self) -> None:
        """Keep each volume when the tracks sit on the volume itself.

        The volume name is the last component. A looser length check
        groups both volumes under their parent.

        Returns:
            None. The test fails if the root is the Volumes directory.
        """
        folders = music_roots.collapse_track_folders(
            [
                PurePosixPath("/tmp/vtest/Volumes/GIGDRIVE"),
                PurePosixPath("/tmp/vtest/Volumes/BACKUP"),
            ]
        )
        self.assertEqual(
            folders,
            [
                PurePosixPath("/tmp/vtest/Volumes/BACKUP"),
                PurePosixPath("/tmp/vtest/Volumes/GIGDRIVE"),
            ],
        )
        self.assertNotIn(PurePosixPath("/tmp/vtest/Volumes"), folders)
        self.assertNotIn(PurePosixPath("/"), folders)
        self.assertNotIn(PurePosixPath("/Volumes"), folders)

    def test_a_folder_named_volumes_is_not_a_volume_prefix(self) -> None:
        """Collapse a path that ends on Volumes with the sibling folder.

        ``Volumes`` with no volume name after it is an ordinary folder.
        Treating it as a volume prefix leaves it beside Music instead of
        sharing ``/tmp/vtest``.

        Returns:
            None. The test fails if Volumes and Music stay separate.
        """
        folders = music_roots.collapse_track_folders(
            [
                PurePosixPath("/tmp/vtest/Volumes"),
                PurePosixPath("/tmp/vtest/Music/House"),
            ]
        )
        self.assertEqual(folders, [PurePosixPath("/tmp/vtest")])
        self.assertNotIn(PurePosixPath("/tmp/vtest/Volumes"), folders)
        self.assertNotIn(PurePosixPath("/"), folders)


class VolumeTests(unittest.TestCase):
    """Mounted drives are discovered from mocked volumes and drive letters."""

    def test_mac_volumes_with_serato_are_drives(self) -> None:
        """Keep a volume that has ``_Serato_`` and skip the rest.

        A shortcut volume and a hidden name are not roots.

        Returns:
            None. The test fails if an empty volume is included.
        """
        root = Path(self._temp())
        try:
            gig = root / "GIGDRIVE"
            (gig / "_Serato_").mkdir(parents=True)
            (root / "Empty").mkdir()
            (root / ".hidden" / "_Serato_").mkdir(parents=True)
            try:
                (root / "Alias").symlink_to(gig, target_is_directory=True)
                linked = root / "Linked"
                linked.mkdir()
                (linked / "_Serato_").symlink_to(gig / "_Serato_", target_is_directory=True)
            except OSError:
                pass
            found = music_roots.serato_volumes("darwin", volumes_root=root)
        finally:
            self._cleanup(root)
        self.assertEqual(found, [(gig, "GIGDRIVE")])

    def test_windows_drive_letters_use_the_volume_label(self) -> None:
        """Read drive letters and keep the one whose marker exists.

        Returns:
            None. The test fails if C: is included or the label is missing.
        """

        def is_dir(path: Path) -> bool:
            return _drive_text(path) == "e:\\_serato_"

        def is_link(_path: Path) -> bool:
            return False

        def label_for(path: Path) -> str:
            if _drive_text(path).startswith("e:"):
                return "GIGDRIVE"
            return "SYSTEM"

        found = music_roots.serato_volumes(
            "win32",
            volumes_root=Path("/unused"),
            letters=["C", "E", "1"],
            label_for=label_for,
            is_dir=is_dir,
            is_link=is_link,
        )
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0][1], "GIGDRIVE")
        self.assertTrue(_drive_text(found[0][0]).startswith("e:"))

    def test_other_platforms_have_no_drive_letters(self) -> None:
        """Skip volume discovery when the platform is neither Mac nor Windows.

        Returns:
            None. The test fails if a drive is returned.
        """
        root = Path(self._temp())
        try:
            (root / "GIGDRIVE" / "_Serato_").mkdir(parents=True)
            found = music_roots.serato_volumes("linux", volumes_root=root)
        finally:
            self._cleanup(root)
        self.assertEqual(found, [])

    def _temp(self) -> str:
        """Create a temporary directory and return its path.

        Returns:
            The directory path.
        """
        import tempfile

        self._dir = tempfile.TemporaryDirectory()
        return self._dir.name

    def _cleanup(self, _root: Path) -> None:
        """Remove the temporary directory.

        Args:
            _root: Unused. Cleanup uses the directory created in ``_temp``.
        """
        self._dir.cleanup()


class NameTests(unittest.TestCase):
    """Root names are the folder name or the USB label."""

    def test_music_and_a_usb_drive_are_named_for_a_dj(self) -> None:
        """Label a folder with its volume and path, and skip a duplicate drive.

        A music folder on GIGDRIVE is ``Music``. The drive root is not a
        second row. A drive with no tracks is still listed once.

        Returns:
            None. The test fails if two rows say Music or the drive is repeated.
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            volume = Path(tmp) / "Volumes" / "GIGDRIVE"
            music = volume / "Music"
            music.mkdir(parents=True)
            other = Path(tmp) / "Volumes" / "BACKUP"
            other.mkdir()
            spare = Path(tmp) / "STICK"
            spare.mkdir()
            roots = music_roots.name_roots(
                [music],
                [(volume, "GIGDRIVE"), (other, "BACKUP"), (spare, "STICK")],
            )
            self.assertEqual(
                [item["name"] for item in roots],
                ["Music", "BACKUP", "STICK"],
            )
            self.assertEqual([item["kind"] for item in roots], ["folder", "drive", "drive"])
            self.assertEqual(roots[0]["path"], str(music.resolve()))
            self.assertFalse(roots[0]["missing"])
            self.assertEqual(sum(1 for item in roots if "GIGDRIVE" in str(item["path"])), 1)

    def test_a_present_folder_keeps_the_resolved_path(self) -> None:
        """Store the resolved folder when the request path is not canonical.

        Returns:
            None. The test fails if the path still contains ``..``.
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            music = Path(tmp) / "Volumes" / "GIGDRIVE" / "Music"
            music.mkdir(parents=True)
            link = Path(tmp) / "Volumes" / "LINK"
            try:
                link.symlink_to(music.parent, target_is_directory=True)
            except OSError:
                self.skipTest("symlinks are not available")
            weird = link / "Music"
            roots = music_roots.name_roots([weird], [])
            self.assertEqual(len(roots), 1)
            self.assertEqual(roots[0]["path"], str(music.resolve()))
            self.assertNotIn("LINK", str(roots[0]["path"]))
            self.assertFalse(roots[0]["missing"])
            self.assertEqual(roots[0]["kind"], "folder")

    def test_a_closed_folder_keeps_the_path_it_was_given(self) -> None:
        """Keep the original text when the folder cannot be opened.

        Resolving a shortcut parent would swap the path the library stored.

        Returns:
            None. The test fails if the stored path is the resolved folder.
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            music = Path(tmp) / "Volumes" / "GIGDRIVE" / "Music"
            music.mkdir(parents=True)
            link = Path(tmp) / "Volumes" / "LINK"
            try:
                link.symlink_to(music.parent, target_is_directory=True)
            except OSError:
                self.skipTest("symlinks are not available")
            weird = link / "Music"
            roots = music_roots.name_roots([weird], [], exists=lambda _path: False)
            self.assertEqual(len(roots), 1)
            self.assertTrue(roots[0]["missing"])
            self.assertEqual(roots[0]["path"], str(weird))
            self.assertIn("LINK", str(roots[0]["path"]))
            self.assertNotEqual(roots[0]["path"], str(music.resolve()))

    def test_drive_rows_sort_by_name_and_are_present(self) -> None:
        """Sort two drives by label and store a real path for each.

        The drives are inserted out of order. A sort key that ignores the
        name keeps that order.

        Returns:
            None. The test fails if STICK stays first or a drive is missing.
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            stick = Path(tmp) / "STICK"
            backup = Path(tmp) / "BACKUP"
            stick.mkdir()
            backup.mkdir()
            roots = music_roots.name_roots(
                [],
                [(stick, "STICK"), (backup, "BACKUP")],
            )
            self.assertEqual(
                roots,
                [
                    {
                        "name": "BACKUP",
                        "path": str(backup.resolve()),
                        "kind": "drive",
                        "missing": False,
                    },
                    {
                        "name": "STICK",
                        "path": str(stick.resolve()),
                        "kind": "drive",
                        "missing": False,
                    },
                ],
            )

    def test_an_unmounted_drive_is_skipped_and_the_next_one_stays(self) -> None:
        """Leave out a drive that is not mounted, and keep the drive after it.

        Stopping the loop at the missing drive would drop the later one.

        Returns:
            None. The test fails if OLDDRIVE is listed or STICK is absent.
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            gone = Path(tmp) / "OLDDRIVE"
            stick = Path(tmp) / "STICK"
            stick.mkdir()
            roots = music_roots.name_roots([], [(gone, "OLDDRIVE"), (stick, "STICK")])
            self.assertEqual(
                roots,
                [
                    {
                        "name": "STICK",
                        "path": str(stick.resolve()),
                        "kind": "drive",
                        "missing": False,
                    }
                ],
            )

    def test_a_missing_folder_sorts_after_a_present_one(self) -> None:
        """List a folder that is on disk before one that is not.

        The missing folder's name comes first alphabetically. Sorting by
        name alone would put it first.

        Returns:
            None. The test fails if the missing folder is the first row.
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            present = Path(tmp) / "Volumes" / "ZZZDRIVE" / "Music"
            present.mkdir(parents=True)
            missing = Path(tmp) / "Volumes" / "AAA" / "Music"
            roots = music_roots.name_roots(
                [missing, present],
                [],
                exists=lambda path: path == present,
            )
            self.assertEqual([item["name"] for item in roots], ["Music (ZZZDRIVE)", "Music (AAA)"])
            self.assertEqual([item["missing"] for item in roots], [False, True])

    def test_library_tracks_collapse_to_the_music_folder(self) -> None:
        """Read portable ids and collapse two albums to one Music root.

        Returns:
            None. The test fails if House and Techno are separate roots.
        """
        with TempLibrary() as temp:
            music = temp.root / "Music"
            (music / "House").mkdir(parents=True)
            (music / "Techno").mkdir()
            house = music / "House" / "a.mp3"
            techno = music / "Techno" / "b.mp3"
            house.write_bytes(b"a")
            techno.write_bytes(b"b")
            with open_database(temp.db) as conn:
                conn.execute("UPDATE asset SET portable_id = ? WHERE id = 1", (str(house),))
                conn.execute("UPDATE asset SET portable_id = ? WHERE id = 2", (str(techno),))
            music_roots.invalidate()
            roots = [item for item in music_roots.music_roots(refresh=True) if item["kind"] == "folder"]
            match = next(item for item in roots if item["path"] == str(music.resolve()))
            self.assertEqual(match["name"], "Music")
            self.assertFalse(match["missing"])
            self.assertFalse(any(str(item["path"]).endswith("House") or str(item["path"]).endswith("Techno") for item in roots))


class DirectoryTests(unittest.TestCase):
    """Track folders ignore blanks and repeated paths."""

    def test_blank_and_repeated_portable_ids_are_one_folder(self) -> None:
        """Skip a blank path and list one folder when two tracks share it.

        Returns:
            None. The test fails if a blank id becomes a folder or a path is repeated.
        """
        with TempLibrary() as temp:
            music_roots.invalidate()
            shared = temp.root / "Volumes" / "GIGDRIVE" / "Music" / "a.mp3"
            other = temp.root / "Volumes" / "BACKUP" / "Music" / "b.mp3"
            shared.parent.mkdir(parents=True)
            other.parent.mkdir(parents=True)
            shared.write_bytes(b"a")
            other.write_bytes(b"b")
            with open_database(temp.db) as conn:
                conn.execute("UPDATE asset SET portable_id = ? WHERE id = 1", ("   ",))
                conn.execute("UPDATE asset SET portable_id = ? WHERE id = 2", (str(shared),))
                conn.execute(
                    "INSERT INTO asset (id, name, file_name, portable_id) VALUES (3, 'Again', 'a.mp3', ?)",
                    (str(shared),),
                )
                conn.execute(
                    "INSERT INTO asset (id, name, file_name, portable_id) VALUES (4, 'Other', 'b.mp3', ?)",
                    (str(other),),
                )
            found = music_roots.track_directories()
            self.assertEqual(
                [item.resolve() for item in found],
                [shared.parent.resolve(), other.parent.resolve()],
            )


class CacheTests(unittest.TestCase):
    """Roots stay cached until invalidate or an explicit refresh."""

    def test_a_database_write_does_not_reread_the_roots(self) -> None:
        """Keep the cache when master.sqlite changes.

        Returns:
            None. The test fails if a database write reads the library again.
        """
        from unittest import mock

        music_roots.invalidate()
        calls = {"n": 0}

        def counted() -> list[Path]:
            calls["n"] += 1
            return []

        with mock.patch.object(music_roots, "track_directories", counted):
            music_roots.music_roots()
            music_roots.music_roots()
            self.assertEqual(calls["n"], 1)
            music_roots.invalidate()
            music_roots.music_roots()
            self.assertEqual(calls["n"], 2)
            music_roots.music_roots(refresh=True)
            self.assertEqual(calls["n"], 3)

    def test_concurrent_misses_compute_once(self) -> None:
        """Run one discovery when several readers miss the cache together.

        Returns:
            None. The test fails if each thread reads the library.
        """
        import threading
        from unittest import mock

        music_roots.invalidate()
        calls = {"n": 0}
        started = threading.Barrier(4)

        def counted() -> list[Path]:
            calls["n"] += 1
            return []

        def read() -> None:
            started.wait()
            music_roots.music_roots()

        with mock.patch.object(music_roots, "track_directories", counted):
            threads = [threading.Thread(target=read) for _ in range(4)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=5)
        self.assertEqual(calls["n"], 1)


class MissingDriveTests(unittest.TestCase):
    """An unmounted drive stays in the list and cannot be opened."""

    def test_unmounted_root_is_missing_and_refused(self) -> None:
        """Show OLDDRIVE as missing and refuse to browse it.

        A mounted sibling is one row, not a folder plus a USB row.
        Reading the roots twice does not scan the library twice.

        Returns:
            None. The test fails if the missing path is opened or the
            drive is listed twice.
        """
        from unittest import mock

        import files
        import library

        with TempLibrary() as temp:
            music_roots.invalidate()
            files.invalidate_browse_cache()
            volume = temp.root / "Volumes"
            gig = volume / "GIGDRIVE" / "Music"
            (gig / "House").mkdir(parents=True)
            (gig / "Techno").mkdir()
            track = gig / "House" / "a.mp3"
            track.write_bytes(b"a")
            (volume / "GIGDRIVE" / "_Serato_").mkdir()
            missing_house = volume / "OLDDRIVE" / "Music" / "House" / "b.mp3"
            missing_techno = volume / "OLDDRIVE" / "Music" / "Techno" / "c.mp3"
            with open_database(temp.db) as conn:
                conn.execute("UPDATE asset SET portable_id = ? WHERE id = 1", (str(track),))
                conn.execute("UPDATE asset SET portable_id = ? WHERE id = 2", (str(missing_house),))
                conn.execute(
                    "INSERT INTO asset (id, name, file_name, portable_id) VALUES (3, 'T', 'c.mp3', ?)",
                    (str(missing_techno),),
                )
                conn.execute(
                    "INSERT INTO asset (id, name, file_name, portable_id) VALUES (4, 'U', 'd.mp3', ?)",
                    (str(gig / "Techno" / "d.mp3"),),
                )
            calls = {"n": 0}
            real_directories = music_roots.track_directories
            real_volumes = music_roots.serato_volumes

            def counted() -> list[Path]:
                calls["n"] += 1
                return real_directories()

            def volumes(platform: str, **kwargs: object) -> list[tuple[Path, str]]:
                del platform, kwargs
                return real_volumes("darwin", volumes_root=volume)

            with mock.patch.object(music_roots, "serato_volumes", volumes):
                with mock.patch.object(music_roots, "track_directories", counted):
                    roots = music_roots.music_roots(refresh=True)
                    again = music_roots.music_roots()
                    self.assertEqual(calls["n"], 1)
                    files.list_directory(str(gig / "House"))
                    self.assertEqual(calls["n"], 1)
                    listed = files.list_directory(str(gig / "House"), refresh=True)
                    self.assertGreaterEqual(calls["n"], 2)
            self.assertEqual(roots, again)
            names = [str(item["name"]) for item in roots]
            self.assertEqual(names.count("Music (GIGDRIVE)"), 1)
            self.assertFalse(any(name.startswith("USB:") for name in names))
            lost = next(item for item in roots if "OLDDRIVE" in str(item["name"]))
            self.assertEqual(lost["name"], "Music (OLDDRIVE)")
            self.assertTrue(lost["missing"])
            self.assertTrue(str(lost["path"]).replace("\\", "/").endswith("OLDDRIVE/Music"))
            with self.assertRaises(library.LibraryError):
                files.list_directory(str(lost["path"]))
            self.assertIn("GIGDRIVE", str(listed["root"]["name"]))


class LibraryRootsContractTests(unittest.TestCase):
    """GET /api/library-roots is the cached public shape."""

    def test_public_roots_keep_a_stable_id_until_refresh(self) -> None:
        """Label a Music folder, a drive, and Downloads, and reuse the time.

        Returns:
            None. The test fails if the id changes or Downloads is a drive.
        """
        import hashlib
        import os

        music = {
            "name": "Home · /Music",
            "path": "/Users/dj/Music",
            "kind": "folder",
            "missing": False,
        }
        drive = {
            "name": "GIGDRIVE · /",
            "path": "/Volumes/GIGDRIVE",
            "kind": "drive",
            "missing": False,
        }
        downloads = {
            "name": "Home · /Downloads",
            "path": "/Users/dj/Downloads",
            "kind": "folder",
            "missing": True,
        }
        public = [music_roots.to_library_root(item) for item in (music, drive, downloads)]
        self.assertEqual([item["kind"] for item in public], ["music_library", "serato_drive", "music_library"])
        self.assertEqual([item["label"] for item in public], ["Home · /Music", "GIGDRIVE · /", "Home · /Downloads"])
        user = music_roots.to_library_root(
            {"name": "Sets", "path": "/Users/dj/Sets", "kind": "user_folder", "missing": False}
        )
        self.assertEqual(user["kind"], "user_folder")
        self.assertFalse(user["serato"])
        self.assertEqual(public[0]["detail"], "/Users/dj/Music")
        self.assertEqual(public[0]["serato"], True)
        self.assertEqual(public[0]["removable"], False)
        self.assertEqual(public[1]["serato"], True)
        self.assertEqual(public[1]["removable"], True)
        self.assertEqual(public[2]["serato"], True)
        self.assertEqual(public[2]["missing"], True)
        expected = hashlib.sha256(os.path.normcase(os.path.normpath("/Users/dj/Music")).encode("utf-8")).hexdigest()
        self.assertEqual(public[0]["id"], expected)
        self.assertEqual(public[0]["id"], music_roots.root_id("/Users/dj/Music"))

        music_roots.invalidate()
        with self.subTest("cache"):
            from unittest import mock

            stamps = iter(["2026-10-29T13:00:00Z", "2026-10-29T13:05:00Z"])

            def stamped() -> str:
                return next(stamps)

            with mock.patch.object(music_roots, "track_directories", lambda: []):
                with mock.patch.object(music_roots, "_computed_at", stamped):
                    first = music_roots.library_roots(refresh=True)
                    second = music_roots.library_roots()
                    third = music_roots.library_roots(refresh=True)
            self.assertEqual(first["computed_at"], "2026-10-29T13:00:00Z")
            self.assertEqual(second["computed_at"], first["computed_at"])
            self.assertEqual(third["computed_at"], "2026-10-29T13:05:00Z")
            self.assertEqual(first["roots"], [])

    def test_http_library_roots_accepts_refresh(self) -> None:
        """Serve the contract from GET /api/library-roots.

        Returns:
            None. The test fails if refresh is ignored or the shape is wrong.
        """
        import threading
        from http.server import ThreadingHTTPServer

        import server

        music_roots.invalidate()
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        host, port = httpd.server_address
        base = f"http://{host}:{port}"
        try:
            import json
            import urllib.request

            with urllib.request.urlopen(base + "/api/library-roots", timeout=5) as response:
                body = json.loads(response.read().decode("utf-8"))
            self.assertEqual(response.status, 200)
            self.assertIn("computed_at", body)
            self.assertIsInstance(body["roots"], list)
            with urllib.request.urlopen(base + "/api/library-roots?refresh=1", timeout=5) as again:
                refreshed = json.loads(again.read().decode("utf-8"))
            self.assertIn("roots", refreshed)
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=3)


class ReviewTests(unittest.TestCase):
    """Labels, bare roots, UNC paths, and a database that cannot be read."""

    def test_clashing_music_folders_gain_a_parent(self) -> None:
        """Keep /a/x/Music and /b/x/Music from sharing one label.

        Returns:
            None. The test fails if both rows are named Music or x · /Music.
        """
        roots = music_roots.name_roots(
            [Path("/a/x/Music"), Path("/b/x/Music")],
            [],
            exists=lambda _path: False,
        )
        self.assertEqual(
            [item["name"] for item in roots],
            ["Music (a/x)", "Music (b/x)"],
        )
        public = [music_roots.to_library_root(item) for item in roots]
        self.assertEqual(public[0]["detail"], "/a/x/Music")
        self.assertEqual(public[1]["detail"], "/b/x/Music")
        self.assertEqual(public[0]["kind"], "music_library")
        self.assertNotEqual(public[0]["label"], public[1]["label"])

    def test_a_single_music_folder_keeps_its_name(self) -> None:
        """Leave the label as Music when nothing else uses it.

        Returns:
            None. The test fails if a parent is added with no clash.
        """
        roots = music_roots.name_roots([Path("/a/x/Music")], [], exists=lambda _path: False)
        self.assertEqual(roots[0]["name"], "Music")

    def test_unc_share_root_is_removable_and_refused(self) -> None:
        """Treat \\\\server\\share as a bare root and a removable path.

        Returns:
            None. The test fails if the share root can be opened.
        """
        import files
        import library

        self.assertTrue(music_roots._removable("\\\\server\\share\\Music"))
        self.assertTrue(files._bare_root("\\\\server\\share"))
        self.assertTrue(files._bare_root("//server/share"))
        self.assertFalse(files._bare_root("\\\\server\\share\\Music"))
        self.assertTrue(files._bare_root("C:\\"))
        self.assertFalse(files._bare_root("C:\\Music"))
        with self.assertRaises(library.LibraryError) as caught:
            files.list_directory("\\\\server\\share", elsewhere=True)
        self.assertEqual(caught.exception.status, 403)

    def test_elsewhere_still_refuses_the_computer_root(self) -> None:
        """Refuse /, /Volumes, and a missing root even when browsing elsewhere.

        A normal folder outside the music roots can still be listed.

        Returns:
            None. The test fails if / is listed.
        """
        import tempfile

        import files
        import library

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Sets"
            folder.mkdir()
            opened = files.list_directory(str(folder), elsewhere=True)
            self.assertEqual(opened["path"], str(folder.resolve()))
        for blocked in ("/", "/Volumes", "C:\\"):
            with self.assertRaises(library.LibraryError) as caught:
                files.list_directory(blocked, elsewhere=True)
            self.assertEqual(caught.exception.status, 403)
        missing = {
            "name": "Music (OLDDRIVE)",
            "path": "/Volumes/OLDDRIVE/Music",
            "kind": "folder",
            "missing": True,
        }
        with self.assertRaises(library.LibraryError) as lost:
            files._resolve_directory(
                "/Volumes/OLDDRIVE/Music",
                elsewhere=True,
                roots=[missing],
            )
        self.assertEqual(lost.exception.status, 404)

    def test_a_locked_library_contributes_no_roots(self) -> None:
        """Return no track folders when the database cannot be opened.

        Returns:
            None. The test fails if sqlite3.Error or OSError escapes.
        """
        import sqlite3
        from unittest import mock

        import library

        music_roots.invalidate()
        with mock.patch.object(library, "read_conn", side_effect=sqlite3.OperationalError("locked")):
            self.assertEqual(music_roots.track_directories(), [])
        with mock.patch.object(library, "read_conn", side_effect=OSError("unreadable")):
            self.assertEqual(music_roots.track_directories(), [])

    def test_permission_errors_on_volumes_and_listing_do_not_crash(self) -> None:
        """Skip a volume list that cannot be read, and report a folder the same way.

        Returns:
            None. The test fails if PermissionError leaves the function.
        """
        import tempfile
        from unittest import mock

        import files
        import library

        root = Path(tempfile.mkdtemp())
        try:
            with mock.patch.object(Path, "iterdir", side_effect=PermissionError("volumes")):
                found = music_roots.serato_volumes("darwin", volumes_root=root)
            self.assertEqual(found, [])
        finally:
            root.rmdir()
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Sets"
            folder.mkdir()
            with mock.patch("files.os.scandir", side_effect=PermissionError("listing")):
                with self.assertRaises(library.LibraryError) as caught:
                    files.list_directory(str(folder), elsewhere=True)
            self.assertEqual(caught.exception.message, "That folder could not be read.")

    def test_two_drives_with_the_same_real_path_are_one_row(self) -> None:
        """Skip a second drive row when it resolves to the first.

        Returns:
            None. The test fails if the shortcut is a second root.
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            stick = Path(tmp) / "STICK"
            stick.mkdir()
            link = Path(tmp) / "LINK"
            try:
                link.symlink_to(stick, target_is_directory=True)
            except OSError:
                self.skipTest("symlinks are not available")
            roots = music_roots.name_roots(
                [],
                [(stick, "STICK"), (link, "ALIAS")],
                exists=lambda _path: True,
            )
            self.assertEqual([item["name"] for item in roots], ["STICK"])


if __name__ == "__main__":
    unittest.main()
