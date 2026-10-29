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
        """Label the home music folder Music and the drive USB plus its label.

        Returns:
            None. The test fails if the drive is named like a folder.
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            music = Path(tmp) / "Music"
            music.mkdir()
            drive = Path("E:\\")
            roots = music_roots.name_roots(
                [music],
                [(drive, "GIGDRIVE")],
                exists=lambda path: path == music or _drive_text(path) == "e:\\",
            )
            self.assertEqual([item["name"] for item in roots], ["Music", "USB: GIGDRIVE"])
            self.assertEqual([item["kind"] for item in roots], ["folder", "drive"])
            self.assertEqual(roots[0]["path"], str(music.resolve()))

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
            roots = [item for item in music_roots.music_roots() if item["kind"] == "folder"]
            self.assertIn(
                {"name": "Music", "path": str(music.resolve()), "kind": "folder"},
                roots,
            )
            self.assertFalse(any(item["path"].endswith("House") or item["path"].endswith("Techno") for item in roots))


if __name__ == "__main__":
    unittest.main()
