"""Read-only portable-drive check.

Fixtures come from ``tests/fixtures/drive_check``, which
``tests/fixtures/build_fixtures.py`` writes. The tests also build small
drives in a temporary directory with that same ``crate_bytes`` encoder.
Nothing here is a copy of a real Serato library.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stderr, redirect_stdout
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote, urlencode

import drive_check
import library
import server


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
DRIVE = FIXTURES / "drive_check" / "GIGDRIVE"


def _builder():
    """Load the fixture builder.

    Returns:
        The builder module.
    """
    path = FIXTURES / "build_fixtures.py"
    spec = importlib.util.spec_from_file_location("drive_check_fixture_builder", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("The fixture builder could not be loaded.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BUILDER = _builder()


def _fingerprint(root: Path) -> list[tuple[str, str, int]]:
    """Hash a tree without following directory shortcuts.

    Args:
        root: Directory to hash.

    Returns:
        Relative path, content hash or link target, and size.
    """
    rows: list[tuple[str, str, int]] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames.sort()
        for name in sorted(filenames):
            path = Path(dirpath) / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                rows.append((relative, "link:" + os.readlink(path), 0))
                continue
            data = path.read_bytes()
            rows.append((relative, hashlib.sha256(data).hexdigest(), len(data)))
    return rows


def _kinds(report: drive_check.DriveReport) -> dict[str, set[str]]:
    """Group finding kinds by stored path.

    Args:
        report: A drive report.

    Returns:
        Path to the kinds reported for it.
    """
    found: dict[str, set[str]] = {}
    for finding in report.findings:
        found.setdefault(finding.path, set()).add(finding.kind)
    return found


class DriveCheckTests(unittest.TestCase):
    """Every finding type, both path styles, a missing drive, and no writes."""

    def setUp(self) -> None:
        """Pin the home directory so a laptop lookup cannot see the real one.

        Returns:
            None.
        """
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        home = Path(self._tmp.name) / "home"
        home.mkdir()
        self._old = {key: os.environ.get(key) for key in ("HOME", "USERPROFILE")}
        os.environ["HOME"] = str(home)
        os.environ["USERPROFILE"] = str(home)
        self.addCleanup(self._restore_env)

    def _restore_env(self) -> None:
        """Put HOME and USERPROFILE back.

        Returns:
            None.
        """
        for key, value in self._old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _copy_fixture(self) -> Path:
        """Copy the committed portable drive into the temp directory.

        Returns:
            The copied drive root.
        """
        dest = Path(self._tmp.name) / "GIGDRIVE"
        shutil.copytree(DRIVE, dest)
        return dest

    def _drive(self, paths: list[str | None], files: dict[str, bytes] | None = None, name: str = "GIGDRIVE") -> Path:
        """Build a one-crate drive with the fixture encoder.

        Args:
            paths: Crate paths.
            files: Relative path to bytes for files that exist on the drive.
            name: Drive folder name.

        Returns:
            The drive root.
        """
        drive = Path(self._tmp.name) / name
        crate_dir = drive / "_Serato_" / "Subcrates"
        crate_dir.mkdir(parents=True)
        (crate_dir / "House.crate").write_bytes(BUILDER.crate_bytes(paths))
        for relative, data in (files or {}).items():
            target = drive.joinpath(*relative.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        return drive

    def test_fixture_drive_reports_every_committed_finding(self) -> None:
        """Read the committed drive and classify each stored path.

        Returns:
            None.
        """
        report = drive_check.check_drive(self._copy_fixture(), filesystem="ext4")
        found = _kinds(report)
        present = {"Music/on-drive.mp3", "Music/COM10.mp3", "Music/concert.mp3", "Music\\peak-win.mp3"}
        unsafe = {
            "Music/CON.mp3",
            "Music/NUL.txt",
            "Music/COM1.mp3",
            "Music/late.mp3.",
            "Music/what?.mp3",
            "Music/space.mp3 ",
            "Music/a:b.mp3",
        }
        long_path = "Music/" + ("b" * 256) + ".mp3"
        for path in BUILDER.DRIVE_CHECK_HOUSE:
            if path in present:
                self.assertNotIn(path, found, path)
                continue
            self.assertIn("missing", found[path], path)
            self.assertNotIn("off_drive", found[path], path)
        for path in unsafe:
            self.assertIn("unsafe_name", found[path], path)
        self.assertEqual(found[long_path], {"missing", "path_length"})
        self.assertNotIn("unsafe_name", found.get("Music/COM10.mp3", set()))
        self.assertNotIn("unsafe_name", found.get("Music/concert.mp3", set()))
        self.assertNotIn(BUILDER.DRIVE_CHECK_DATABASE_ONLY, found)
        self.assertNotIn(BUILDER.DRIVE_CHECK_SMART[0], found)
        self.assertNotIn("Music\\peak-win.mp3", found)
        self.assertNotIn(BUILDER.DRIVE_CHECK_EXPORT_BACKUP[0], found)
        self.assertNotIn(BUILDER.DRIVE_CHECK_LEXICON[0], found)
        self.assertEqual(found[BUILDER.DRIVE_CHECK_KEEP[0]], {"missing"})
        smart = [item for item in report.findings if item.kind == "smart_crate"]
        self.assertEqual([item.crate for item in smart], ["Warmup"])
        self.assertEqual(smart[0].track, "")
        self.assertIn("Serato does not copy Smart Crates", smart[0].fix)
        self.assertIn("On the laptop, make a normal crate", smart[0].fix)
        self.assertEqual(
            report.counts,
            {
                "tracks": 15,
                "off_drive": 0,
                "missing": 11,
                "smart_crates": 1,
                "unsafe_names": 7,
                "path_length": 1,
                "file_size": 0,
            },
        )
        self.assertFalse(report.ready)
        self.assertEqual(report.filesystem, "ext4")
        self.assertEqual(report.name, "GIGDRIVE")
        con = next(item for item in report.findings if item.path == "Music/CON.mp3" and item.kind == "unsafe_name")
        self.assertEqual(con.crate, "House")
        self.assertEqual(con.track, "CON.mp3")
        self.assertIn("The name CON is reserved on Windows.", con.fix)
        self.assertIn('Rename "CON.mp3" on the laptop', con.fix)
        late = next(item for item in report.findings if item.path == "Music/late.mp3." and item.kind == "unsafe_name")
        self.assertIn("The name ends with a space or a period.", late.fix)
        what = next(item for item in report.findings if item.path == "Music/what?.mp3" and item.kind == "unsafe_name")
        self.assertIn("The name contains ?.", what.fix)

    def test_parent_crate_includes_its_subcrate_only(self) -> None:
        """House includes House / Peak and does not include the extra folder.

        Returns:
            None.
        """
        drive = self._copy_fixture()
        house = drive_check.check_drive(drive, ["house"])
        names = {item.name for item in house.crates}
        self.assertEqual(names, {"House", "House / Peak"})
        self.assertIn("House", {item.crate for item in house.findings})
        self.assertNotIn("Export Backups-extra / Keep", {item.crate for item in house.findings})
        peak = drive_check.check_drive(drive, ["House / Peak"])
        self.assertEqual({item.crate for item in peak.findings}, set())
        self.assertEqual(peak.counts["tracks"], 1)
        self.assertTrue(peak.ready)
        with self.assertRaises(library.LibraryError) as caught:
            drive_check.check_drive(drive, ["House / Nope"])
        self.assertEqual(caught.exception.status, 404)
        self.assertIn("House / Nope", caught.exception.message)

    def test_same_drive_when_the_caller_passes_the_serato_folder(self) -> None:
        """Accept the _Serato_ directory and check the drive that contains it.

        Returns:
            None.
        """
        drive = self._copy_fixture()
        parent = drive_check.check_drive(drive, filesystem="ext4")
        child = drive_check.check_drive(drive / "_Serato_", filesystem="ext4")
        self.assertEqual(parent.to_dict(), child.to_dict())

    def test_off_drive_file_is_not_called_missing(self) -> None:
        """A crate path that exists on the laptop is off the drive.

        Returns:
            None.
        """
        laptop = Path(self._tmp.name) / "laptop" / "night.mp3"
        laptop.parent.mkdir()
        laptop.write_bytes(b"laptop")
        drive = self._drive([str(laptop), "Music/here.mp3"], {"Music/here.mp3": b"drive"})
        report = drive_check.check_drive(drive)
        found = _kinds(report)
        self.assertEqual(found[str(laptop)], {"off_drive"})
        self.assertNotIn("Music/here.mp3", found)
        finding = report.findings[0]
        self.assertEqual(finding.crate, "House")
        self.assertEqual(finding.track, "night.mp3")
        self.assertEqual(finding.found, str(laptop))
        self.assertEqual(
            finding.fix,
            f'Copy "night.mp3" onto this drive. It is in "House", and the file on the laptop is {laptop}.',
        )
        self.assertEqual(report.summary, "1 of 2 tracks are not on this drive.")

    def test_eighty_five_of_one_hundred_fifty(self) -> None:
        """The venue failure is a count of tracks that are not on the drive.

        Returns:
            None.
        """
        laptop = Path(self._tmp.name) / "laptop"
        laptop.mkdir()
        paths: list[str | None] = []
        files: dict[str, bytes] = {}
        for index in range(85):
            file = laptop / f"track-{index:03d}.mp3"
            file.write_bytes(b"x")
            paths.append(str(file))
        for index in range(65):
            relative = f"Music/ok-{index:03d}.mp3"
            files[relative] = b"x"
            paths.append(relative)
        drive = self._drive(paths, files)
        report = drive_check.check_drive(drive)
        self.assertEqual(report.counts["tracks"], 150)
        self.assertEqual(report.counts["off_drive"], 85)
        self.assertEqual(report.counts["missing"], 0)
        self.assertEqual(report.summary, "85 of 150 tracks are not on this drive.")

    def test_missing_file_is_not_called_off_drive(self) -> None:
        """A path that exists only in some other folder is missing.

        Returns:
            None.
        """
        random = Path(self._tmp.name) / "random" / "serato-drive-check-random" / "only-random.mp3"
        random.parent.mkdir(parents=True)
        random.write_bytes(b"x")
        stored = "serato-drive-check-random/only-random.mp3"
        drive = self._drive([stored])
        report = drive_check.check_drive(drive)
        self.assertEqual(_kinds(report)[stored], {"missing"})
        finding = report.findings[0]
        self.assertEqual(finding.found, "")
        self.assertIn("Restore the file on the laptop", finding.fix)
        self.assertNotIn("Copy ", finding.fix)

    def test_stripped_mac_path_finds_the_laptop_file(self) -> None:
        """A crate path without a leading slash still finds /that/path.

        Returns:
            None.
        """
        if sys.platform == "win32":
            self.skipTest("The leading-slash form is the macOS stored path.")
        folder = Path("/tmp") / f"serato-drive-check-{Path(self._tmp.name).name}"
        self.addCleanup(lambda: shutil.rmtree(folder, ignore_errors=True))
        target = folder / "night.mp3"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"mac")
        stored = target.as_posix().lstrip("/")
        drive = self._drive([stored])
        outside = drive_check.check_drive(drive)
        self.assertEqual(_kinds(outside)[stored], {"off_drive"})
        self.assertEqual(outside.findings[0].found, str(target))
        both = self._drive([stored], {stored: b"on-drive"}, name="BOTH")
        preferred = drive_check.check_drive(both)
        self.assertNotIn(stored, _kinds(preferred))
        self.assertTrue(preferred.ready)

    def test_home_copy_is_off_drive(self) -> None:
        """A relative path that exists under the home directory is on the laptop.

        Returns:
            None.
        """
        stored = "serato-drive-check-home/from-home.mp3"
        home_file = Path.home() / stored
        home_file.parent.mkdir(parents=True)
        home_file.write_bytes(b"home")
        drive = self._drive([stored])
        report = drive_check.check_drive(drive)
        self.assertEqual(_kinds(report)[stored], {"off_drive"})
        self.assertEqual(report.findings[0].found, str(home_file))

    def test_windows_and_macos_paths(self) -> None:
        """A drive letter and a /Volumes path are off this drive when the file exists.

        Returns:
            None.
        """
        windows = "C:\\Users\\dj\\Music\\night.mp3"
        volumes = "/Volumes/OTHER/Music/night.mp3"
        mac_stored = "Users/ada/Music/night.mp3"

        def exists(path: Path) -> bool:
            text = os.fspath(path).replace("\\", "/")
            folded = text.casefold()
            return folded in {
                "c:/users/dj/music/night.mp3",
                "/volumes/other/music/night.mp3",
                "/users/ada/music/night.mp3",
            }

        drive = self._drive([windows, volumes, mac_stored, "Music/gone.mp3"])
        report = drive_check.check_drive(drive, exists=exists)
        found = _kinds(report)
        self.assertEqual(found[windows], {"off_drive"})
        self.assertEqual(found[volumes], {"off_drive"})
        self.assertEqual(found[mac_stored], {"off_drive"})
        self.assertEqual(found["Music/gone.mp3"], {"missing"})
        for finding in report.findings:
            if finding.path == windows:
                self.assertNotEqual(finding.kind, "unsafe_name")
                self.assertNotIn("contains :", finding.fix)
        absent = drive_check.check_drive(drive, exists=lambda _path: False)
        self.assertEqual({item.kind for item in absent.findings}, {"missing"})

    def test_case_difference_on_the_drive_is_present(self) -> None:
        """Music/On-Drive.mp3 matches Music/on-drive.mp3 on the drive.

        Returns:
            None.
        """
        drive = self._drive(["Music/On-Drive.mp3"], {"Music/on-drive.mp3": b"x"})
        report = drive_check.check_drive(drive)
        self.assertTrue(report.ready)
        self.assertEqual(report.summary, "Every crate track on GIGDRIVE is on this drive.")

    def test_repeated_path_counts_once_and_two_crates_count_twice(self) -> None:
        """One crate lists a path twice. Two crates list it once each.

        Returns:
            None.
        """
        drive = self._drive(["Music/gone.mp3", "Music/gone.mp3"])
        once = drive_check.check_drive(drive)
        self.assertEqual(once.counts["tracks"], 1)
        self.assertEqual(once.counts["missing"], 1)
        second = drive / "_Serato_" / "Subcrates" / "Friday.crate"
        second.write_bytes(BUILDER.crate_bytes(["Music/gone.mp3"]))
        twice = drive_check.check_drive(drive)
        self.assertEqual(twice.counts["tracks"], 2)
        self.assertEqual(twice.counts["missing"], 2)
        self.assertEqual({item.crate for item in twice.findings}, {"House", "Friday"})

    def test_null_path_record_is_skipped(self) -> None:
        """A crate entry with no path is not a track.

        Returns:
            None.
        """
        drive = self._drive([None, "Music/on-drive.mp3"], {"Music/on-drive.mp3": b"x"})
        report = drive_check.check_drive(drive)
        self.assertEqual(report.counts["tracks"], 1)
        self.assertTrue(report.ready)

    def test_path_length_boundaries(self) -> None:
        """255 and 259 fit. 256 and 260 do not.

        Returns:
            None.
        """
        short_name = "a" * 255
        long_name = "b" * 256
        exact = "Music/" + ("c" * 250)
        over = "Music/" + ("d" * 251)
        report = drive_check.check_drive(self._drive([short_name, long_name, exact, over]))
        found = _kinds(report)
        self.assertEqual(found[short_name], {"missing"})
        self.assertEqual(found[exact], {"missing"})
        self.assertEqual(found[long_name], {"missing", "path_length"})
        self.assertEqual(found[over], {"missing", "path_length"})
        over_fix = next(item.fix for item in report.findings if item.path == over and item.kind == "path_length")
        self.assertIn("Windows allows 259", over_fix)
        self.assertNotIn("FAT32 allows 255", over_fix)
        long_fix = next(item.fix for item in report.findings if item.path == long_name and item.kind == "path_length")
        self.assertIn("FAT32 allows 255", long_fix)

    def test_fat32_size_boundary(self) -> None:
        """One byte over 4 GB is a finding. The last legal size is not.

        Returns:
            None.
        """
        limit = drive_check.FAT32_MAX_BYTES
        drive = self._drive(
            ["Music/max.wav", "Music/over.wav", "Music/small.mp3"],
            {"Music/small.mp3": b"x"},
        )
        self._sparse(drive / "Music" / "max.wav", limit)
        self._sparse(drive / "Music" / "over.wav", limit + 1)
        before = (drive / "Music" / "over.wav").stat().st_size
        fat = drive_check.check_drive(drive, filesystem="FAT32")
        self.assertEqual((drive / "Music" / "over.wav").stat().st_size, before)
        found = _kinds(fat)
        self.assertNotIn("Music/max.wav", found)
        self.assertNotIn("Music/small.mp3", found)
        self.assertEqual(found["Music/over.wav"], {"file_size"})
        self.assertIn(str(limit + 1), fat.findings[0].fix)
        self.assertIn("This drive is FAT32", fat.findings[0].fix)
        self.assertEqual(fat.counts["file_size"], 1)
        exfat = drive_check.check_drive(drive, filesystem="exFAT")
        self.assertNotIn("file_size", {item.kind for item in exfat.findings})
        with patch.object(drive_check, "detect_filesystem", return_value=None):
            unknown = drive_check.check_drive(drive)
        self.assertIsNone(unknown.filesystem)
        self.assertNotIn("file_size", {item.kind for item in unknown.findings})

    def test_vfat_is_fat_and_exfat_is_not(self) -> None:
        """Linux calls a FAT volume vfat. exFAT can hold a large file.

        Returns:
            None.
        """
        self.assertTrue(drive_check.is_fat_filesystem("FAT32"))
        self.assertTrue(drive_check.is_fat_filesystem("vfat"))
        self.assertTrue(drive_check.is_fat_filesystem("msdos"))
        self.assertFalse(drive_check.is_fat_filesystem("exFAT"))
        self.assertFalse(drive_check.is_fat_filesystem("ExFAT"))
        self.assertFalse(drive_check.is_fat_filesystem("NTFS"))
        self.assertFalse(drive_check.is_fat_filesystem(None))
        self.assertFalse(drive_check.is_fat_filesystem(""))

    def test_mount_sibling_does_not_match(self) -> None:
        """GIGDRIVE-backup is not the filesystem of GIGDRIVE.

        Returns:
            None.
        """
        mounts = "\n".join(
            [
                "/dev/sda1 / ext4 rw 0 0",
                "/dev/sdb1 /Volumes/GIGDRIVE vfat rw 0 0",
                "/dev/sdb2 /Volumes/GIGDRIVE-backup ext4 rw 0 0",
                "/dev/sdc1 /Volumes/GIG\\040DRIVE vfat rw 0 0",
            ]
        )
        self.assertEqual(
            drive_check.filesystem_from_mounts("/Volumes/GIGDRIVE/Music/a.mp3", mounts),
            "vfat",
        )
        self.assertEqual(
            drive_check.filesystem_from_mounts("/Volumes/GIGDRIVE-backup/Music/a.mp3", mounts),
            "ext4",
        )
        self.assertEqual(
            drive_check.filesystem_from_mounts("/Volumes/GIG DRIVE/a.mp3", mounts),
            "vfat",
        )
        self.assertEqual(drive_check.filesystem_from_mounts("/", mounts), "ext4")
        volumes_only = "\n".join(mounts.splitlines()[1:])
        self.assertIsNone(drive_check.filesystem_from_mounts("/nowhere", volumes_only))

    def test_detect_filesystem_does_not_raise(self) -> None:
        """Detection on this machine returns a name or nothing.

        Returns:
            None.
        """
        found = drive_check.detect_filesystem(Path(self._tmp.name))
        self.assertTrue(found is None or (isinstance(found, str) and found != ""))

    def test_missing_drive_is_not_created(self) -> None:
        """An absent drive is one report, and the path stays absent.

        Returns:
            None.
        """
        missing = Path(self._tmp.name) / "no-such-gigdrive"
        report = drive_check.check_drive(missing)
        self.assertTrue(report.missing_drive)
        self.assertFalse(report.ready)
        self.assertEqual(report.findings, ())
        self.assertEqual(report.summary, "no-such-gigdrive is not connected. Plug it in and check again.")
        self.assertFalse(missing.exists())

    def test_backup_sibling_is_not_a_serato_drive(self) -> None:
        """_Serato_-backup does not satisfy the _Serato_ folder.

        Returns:
            None.
        """
        drive = Path(self._tmp.name) / "sibling"
        (drive / "_Serato_-backup").mkdir(parents=True)
        with self.assertRaises(library.LibraryError) as caught:
            drive_check.check_drive(drive)
        self.assertEqual(caught.exception.status, 404)
        self.assertIn("no _Serato_ folder", caught.exception.message)

    def test_serato_shortcut_is_not_followed(self) -> None:
        """A symlinked _Serato_ folder is refused before it is read.

        Returns:
            None.
        """
        real = Path(self._tmp.name) / "real-serato"
        (real / "Subcrates").mkdir(parents=True)
        (real / "Subcrates" / "House.crate").write_bytes(BUILDER.crate_bytes(["Music/secret.mp3"]))
        drive = Path(self._tmp.name) / "linked"
        drive.mkdir()
        try:
            os.symlink(real, drive / "_Serato_")
        except OSError as exc:
            self.skipTest(f"this OS cannot create a shortcut: {exc}")
        before = _fingerprint(real)
        with self.assertRaises(library.LibraryError) as caught:
            drive_check.check_drive(drive)
        self.assertEqual(caught.exception.status, 400)
        self.assertIn("shortcut", caught.exception.message)
        self.assertEqual(_fingerprint(real), before)

    def test_symlink_track_pointing_outside_is_off_drive(self) -> None:
        """A file on the drive that points at the laptop is not on the drive.

        Returns:
            None.
        """
        laptop = Path(self._tmp.name) / "laptop-target.mp3"
        laptop.write_bytes(b"target")
        drive = self._drive(["Music/link.mp3"])
        (drive / "Music").mkdir()
        try:
            os.symlink(laptop, drive / "Music" / "link.mp3")
        except OSError as exc:
            self.skipTest(f"this OS cannot create a shortcut: {exc}")
        report = drive_check.check_drive(drive)
        self.assertEqual(_kinds(report)["Music/link.mp3"], {"off_drive"})
        self.assertEqual(report.findings[0].found, str(laptop.resolve()))

    def test_empty_serato_folder_has_no_crates(self) -> None:
        """A drive with no crate files is ready and says so.

        Returns:
            None.
        """
        drive = Path(self._tmp.name) / "empty"
        (drive / "_Serato_").mkdir(parents=True)
        report = drive_check.check_drive(drive)
        self.assertTrue(report.ready)
        self.assertEqual(report.summary, "This drive has no crates.")
        self.assertEqual(report.counts["tracks"], 0)

    def test_check_does_not_write(self) -> None:
        """Every open is read-only, and the drive bytes do not change.

        Returns:
            None.
        """
        drive = self._copy_fixture()
        before = _fingerprint(drive)
        opened: list[str] = []
        real_open = os.open

        def guard(path: object, flags: int, *args: object, **kwargs: object) -> int:
            accmode = getattr(os, "O_ACCMODE", os.O_RDONLY | os.O_WRONLY | os.O_RDWR)
            acc = flags & accmode
            blocked = 0
            for name in ("O_WRONLY", "O_RDWR", "O_CREAT", "O_TRUNC", "O_APPEND"):
                blocked |= getattr(os, name, 0)
            if acc != os.O_RDONLY or flags & blocked:
                raise AssertionError(f"write open {path} flags={flags:#x}")
            opened.append(os.fspath(path))
            return real_open(path, flags, *args, **kwargs)

        real_builtin = open

        def guard_builtin(file: object, mode: str = "r", *args: object, **kwargs: object) -> object:
            if any(char in mode for char in "wax+"):
                raise AssertionError(f"write mode {mode}")
            return real_builtin(file, mode, *args, **kwargs)

        def boom(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("the drive check wrote")

        with (
            patch("os.open", guard),
            patch("builtins.open", guard_builtin),
            patch("os.remove", boom),
            patch("os.unlink", boom),
            patch("os.rename", boom),
            patch("os.replace", boom),
            patch("os.mkdir", boom),
            patch("os.makedirs", boom),
            patch("os.rmdir", boom),
            patch("os.write", boom),
            patch("os.truncate", boom),
            patch("os.link", boom),
            patch("os.symlink", boom),
            patch.object(Path, "write_bytes", boom),
            patch.object(Path, "write_text", boom),
            patch.object(Path, "mkdir", boom),
            patch.object(Path, "unlink", boom),
            patch.object(Path, "rename", boom),
            patch.object(Path, "touch", boom),
        ):
            report = drive_check.check_drive(drive, filesystem="ext4")
        self.assertFalse(report.ready)
        self.assertEqual(_fingerprint(drive), before)
        self.assertTrue(opened)
        self.assertTrue(any(path.endswith(".crate") for path in opened))
        self.assertFalse(any(path.endswith(".mp3") for path in opened))
        self.assertFalse(any(path.endswith(".scrate") for path in opened))

    def test_unc_probe_does_not_wait_forever(self) -> None:
        """A share that does not answer is absent.

        Returns:
            None.
        """

        def slow(_path: Path) -> bool:
            time.sleep(5)
            return True

        started = time.perf_counter()
        with patch.object(drive_check, "_is_regular", slow):
            present = drive_check._exists_timed(Path("//server/share/a.mp3"), 0.2)
        self.assertFalse(present)
        self.assertLess(time.perf_counter() - started, 2)

    def test_null_byte_in_the_drive_path_is_refused(self) -> None:
        """A NUL in the drive path is not opened.

        Returns:
            None.
        """
        with self.assertRaises(library.LibraryError) as caught:
            drive_check.check_drive("/tmp/ok\x00/drive")
        self.assertEqual(caught.exception.status, 400)

    def test_missing_siblings_are_not_statted_one_by_one(self) -> None:
        """Thirty tracks under one absent folder do not become thirty stats.

        Returns:
            None.
        """
        calls: list[str] = []

        def exists(path: Path) -> bool:
            calls.append(os.fspath(path))
            return False

        paths = [f"Music/missing-{index}.mp3" for index in range(30)]
        drive = self._drive(paths)
        report = drive_check.check_drive(drive, exists=exists, filesystem="ext4")
        self.assertEqual(report.counts["missing"], 30)
        self.assertLess(len(calls), 20)

    def test_ten_thousand_tracks_finish_within_ten_seconds(self) -> None:
        """A crate of 10,000 missing tracks is classified in under 10 seconds.

        Returns:
            None.
        """
        paths = [f"Music/missing-{index:05d}.mp3" for index in range(10_000)]
        drive = self._drive(paths)
        started = time.perf_counter()
        report = drive_check.check_drive(drive, filesystem="ext4")
        elapsed = time.perf_counter() - started
        self.assertEqual(report.counts["tracks"], 10_000)
        self.assertEqual(report.counts["missing"], 10_000)
        self.assertEqual(report.counts["off_drive"], 0)
        self.assertLess(elapsed, 10, f"{elapsed:.3f}s")

    def test_cli_prints_json_and_refuses_a_plain_folder(self) -> None:
        """The command prints the report and does not write a file.

        Returns:
            None.
        """
        drive = self._drive(["Music/on-drive.mp3"], {"Music/on-drive.mp3": b"x"})
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            ready = drive_check.main([str(drive), "--json"])
        self.assertEqual(ready, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ready"])
        plain = Path(self._tmp.name) / "plain"
        plain.mkdir()
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            refused = drive_check.main([str(plain)])
        self.assertEqual(refused, 2)
        self.assertIn("no _Serato_ folder", stderr.getvalue())

    def test_architecture_names_the_contract(self) -> None:
        """The code reference names the endpoint and every finding kind.

        Returns:
            None.
        """
        text = (ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")
        self.assertIn("`/api/drive-check`", text)
        for kind in drive_check.FINDING_KINDS:
            self.assertIn(f"`{kind}`", text)
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("`/api/drive-check`", agents)
        self.assertEqual(agents, (ROOT / "CLAUDE.md").read_text(encoding="utf-8"))

    def test_http_report_matches_the_check(self) -> None:
        """GET /api/drive-check returns the report and does not require a library.

        Returns:
            None.
        """
        drive = self._copy_fixture()
        expected = drive_check.check_drive(drive).to_dict()
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        host, port = httpd.server_address[:2]
        try:
            query = urlencode([("drive", str(drive)), ("crate", "Warmup")], quote_via=quote)
            with urllib.request.urlopen(f"http://{host}:{port}/api/drive-check?{query}", timeout=10) as response:
                self.assertEqual(response.status, 200)
                body = json.loads(response.read().decode("utf-8"))
            self.assertEqual([item["kind"] for item in body["findings"]], ["smart_crate"])
            self.assertEqual(body["crates"][0]["name"], "Warmup")
            missing = urlencode({"drive": str(Path(self._tmp.name) / "absent")}, quote_via=quote)
            with urllib.request.urlopen(f"http://{host}:{port}/api/drive-check?{missing}", timeout=10) as response:
                absent = json.loads(response.read().decode("utf-8"))
            self.assertTrue(absent["missing_drive"])
            self.assertEqual(absent["findings"], [])
            plain = Path(self._tmp.name) / "plain-http"
            plain.mkdir()
            bad = urlencode({"drive": str(plain)}, quote_via=quote)
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(f"http://{host}:{port}/api/drive-check?{bad}", timeout=10)
            self.assertEqual(caught.exception.code, 404)
            with self.assertRaises(urllib.error.HTTPError) as empty:
                urllib.request.urlopen(f"http://{host}:{port}/api/drive-check", timeout=10)
            self.assertEqual(empty.exception.code, 400)
        finally:
            httpd.shutdown()
            httpd.server_close()
        self.assertEqual(expected["counts"]["smart_crates"], 1)

    def _sparse(self, path: Path, size: int) -> None:
        """Create a sparse file of a logical size.

        Args:
            path: Destination. The parent must exist.
            size: Logical size in bytes.

        Returns:
            None.

        Raises:
            AssertionError: The file's reported size is not ``size``.
        """
        fd = os.open(path, os.O_CREAT | os.O_RDWR)
        try:
            os.ftruncate(fd, size)
        finally:
            os.close(fd)
        actual = path.stat().st_size
        self.assertEqual(actual, size)


class FilesystemNameTests(unittest.TestCase):
    """Volume labels do not depend on the machine that reads them."""

    def test_volume_labels(self) -> None:
        """Name a drive letter, a macOS volume, and a folder.

        Returns:
            None.
        """
        self.assertEqual(drive_check._volume_label("E:\\"), "E:")
        self.assertEqual(drive_check._volume_label("/Volumes/GIGDRIVE"), "GIGDRIVE")
        self.assertEqual(drive_check._volume_label("/mnt/stick"), "stick")
        self.assertEqual(drive_check._volume_label("/media/ada/stick"), "stick")
        self.assertEqual(drive_check._volume_label("/run/media/ada/stick"), "stick")
        self.assertEqual(drive_check._volume_label("/tmp/pytest/GIGDRIVE"), "GIGDRIVE")


if __name__ == "__main__":
    unittest.main()
