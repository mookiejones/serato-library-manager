"""Read-only gig check tests.

Each test builds its own temporary database. The live Serato library is
not opened. File hashes are taken with rb before and after the check.
"""

from __future__ import annotations

import base64
import hashlib
import os
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from collections.abc import Callable
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from io import StringIO
from pathlib import Path, PureWindowsPath

import gig_check
import gig_snapshots
import library
import server
import snapshots
from gig_snapshots import (
    ChangeReport,
    CueMark,
    GridMark,
    LoadedSnapshot,
    SnapshotCrate,
    SnapshotInfo,
    SnapshotTrack,
    TrackTags,
    track_key,
)
from tests.fixture import SCHEMA, TempLibrary, open_database
from tests.test_snapshots import _audio_file, _autotags, _geob, _grid, _id3, _markers, _quiet

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[1]


def _digest(path: Path) -> str:
    """Hash a file with rb.

    Args:
        path: File to read.

    Returns:
        SHA-256 hex digest.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _names(path: Path) -> list[str]:
    """List the names in a directory.

    Args:
        path: Directory.

    Returns:
        Sorted file names.
    """
    return sorted(item.name for item in path.iterdir())


def _write_db(root: Path, setup: Callable[[sqlite3.Connection], None]) -> Path:
    """Create a Serato-shaped database and close it.

    Args:
        root: Directory that will hold master.sqlite.
        setup: Inserts rows and must not leave the connection open.

    Returns:
        The database path. The connection is closed before return so
        Windows can delete the directory.
    """
    database = root / "master.sqlite"
    with open_database(database) as conn:
        conn.executescript(SCHEMA)
        conn.execute("INSERT INTO space (id, name) VALUES (1, 'Serato Library')")
        conn.execute(
            """
            INSERT INTO container (id, parent_id, name, type, list_order, space_id)
            VALUES (1, NULL, 'Library', 0, 0, 1)
            """
        )
        setup(conn)
    return database


def _add_crate(conn: sqlite3.Connection, crate_id: int, name: str, crate_type: int = 1, parent: int = 1) -> None:
    """Insert one crate.

    Args:
        conn: Open database.
        crate_id: Container id.
        name: Visible name.
        crate_type: 1 for a normal crate, 2 for a smart crate.
        parent: Parent container id. The space root is 1.
    """
    conn.execute(
        """
        INSERT INTO container (id, parent_id, name, type, list_order, space_id)
        VALUES (?, ?, ?, ?, ?, 1)
        """,
        (crate_id, parent, name, crate_type, crate_id),
    )


def _add_track(
    conn: sqlite3.Connection,
    asset_id: int,
    portable_id: str,
    *,
    title: str = "Track",
    artist: str = "Artist",
    third_party: int | None = None,
    location_id: int | None = None,
    crate_id: int | None = None,
) -> None:
    """Insert one track into the Serato Library space.

    Args:
        conn: Open database.
        asset_id: Asset id. Also used as the space_asset id.
        portable_id: Stored path.
        title: Track title.
        artist: Artist.
        third_party: third_party_type, or None.
        location_id: Location id, or None.
        crate_id: Crate to put the track in, or None.
    """
    conn.execute(
        """
        INSERT INTO asset
            (id, name, artist, album, genre, key, bpm, comments, portable_id,
             file_name, third_party_type, location_id, is_missing)
        VALUES (?, ?, ?, '', '', '', NULL, '', ?, ?, ?, ?, 0)
        """,
        (asset_id, title, artist, portable_id, Path(portable_id).name, third_party, location_id),
    )
    conn.execute(
        "INSERT INTO space_asset (id, asset_id, space_id) VALUES (?, ?, 1)",
        (asset_id, asset_id),
    )
    if crate_id is not None:
        conn.execute(
            """
            INSERT INTO container_asset (id, asset_id, container_id, list_order)
            VALUES (?, ?, ?, ?)
            """,
            (asset_id, asset_id, crate_id, asset_id),
        )


def _absent_drive() -> tuple[str, str, str]:
    """Return a drive name, an absolute track path, and a location URI.

    Returns:
        Name shown in the report, a path on that drive, and a file URI for
        a location database on the same drive. The drive is not mounted.

    Raises:
        unittest.SkipTest: On Windows when every drive letter is in use.
    """
    if sys.platform == "win32":
        used: set[str] = set()
        listdrives = getattr(os, "listdrives", None)
        if listdrives is not None:
            for drive in listdrives():
                if drive:
                    used.add(drive[0].upper())
        for letter in "ZYXWVUTSRQPONMLKJIHGFED":
            if letter not in used:
                name = f"{letter}:"
                return name, f"{letter}:\\Music\\gone.mp3", f"file:///{letter}:/Library/location.sqlite"
        raise unittest.SkipTest("no free drive letter")
    name = "serato-gig-check-absent"
    return (
        name,
        f"/Volumes/{name}/Music/gone.mp3",
        f"file:///Volumes/{name}/Library/location.sqlite",
    )


def _tags(title: str = "Song", artist: str = "Artist") -> TrackTags:
    """Build empty library tags.

    Args:
        title: Track title.
        artist: Artist.

    Returns:
        Tags with blank album, genre, key, BPM, and comments.
    """
    return TrackTags(title, artist, "", "", "", "", "")


class FakeSnapshots:
    """In-memory GigSnapshotReader. It does not touch the disk."""

    def __init__(self, loaded: tuple[LoadedSnapshot, ...]) -> None:
        """Store snapshots.

        Args:
            loaded: Snapshots list_snapshots and load will return.
        """
        self.loaded = loaded

    def list_snapshots(self) -> tuple[SnapshotInfo, ...]:
        """List the stored snapshots.

        Returns:
            One info row per stored snapshot.
        """
        return tuple(item.info for item in self.loaded)

    def load(self, snapshot_id: str) -> LoadedSnapshot:
        """Return one stored snapshot.

        Args:
            snapshot_id: Id from list_snapshots.

        Returns:
            The matching snapshot.

        Raises:
            KeyError: If the id was not stored.
        """
        for item in self.loaded:
            if item.info.snapshot_id == snapshot_id:
                return item
        raise KeyError(snapshot_id)


class GigCheckTests(unittest.TestCase):
    """Acceptance checks for the read-only gig report."""

    def test_source_opens_read_only(self) -> None:
        """The check names mode=ro and rb, and does not call a library write.

        Returns:
            None. The test fails if a write entry point is named.
        """
        source = (ROOT / "gig_check.py").read_text(encoding="utf-8")
        self.assertIn('"?mode=ro"', source)
        self.assertIn('READ_MODE = "rb"', source)
        self.assertNotIn("begin_write", source)

    def test_read_only_connection_rejects_writes(self) -> None:
        """A mode=ro connection cannot update, and the file bytes stay put.

        Returns:
            None. The test fails if UPDATE succeeds or the hash changes.
        """
        with tempfile.TemporaryDirectory() as name:
            database = Path(name) / "master.sqlite"
            with open_database(database) as conn:
                conn.execute("CREATE TABLE asset (id INTEGER PRIMARY KEY, name TEXT)")
                conn.execute("INSERT INTO asset (id, name) VALUES (1, 'Keep')")
            before = _digest(database)
            conn = gig_check.open_read_only(database)
            try:
                with self.assertRaises(sqlite3.OperationalError):
                    conn.execute("UPDATE asset SET name = 'Changed' WHERE id = 1")
            finally:
                conn.close()
            self.assertEqual(_digest(database), before)

    def test_windows_file_uri_keeps_the_drive_letter(self) -> None:
        """A file URI for a Windows drive does not lose the drive letter.

        urlparse leaves a slash in front of ``Z:``. The check strips that
        slash. This assertion uses PureWindowsPath so it runs on Linux too.

        Returns:
            None. The test fails if the drive letter is dropped.
        """
        text = gig_check._location_path("file:///Z:/Music/location.sqlite")
        self.assertEqual(PureWindowsPath(text).drive.upper(), "Z:")
        self.assertEqual(
            gig_check._location_path("file:///Volumes/GIG/Library/location.sqlite"),
            "/Volumes/GIG/Library/location.sqlite",
        )

    def test_three_missing_files_are_reported_with_paths(self) -> None:
        """A crate with 3 missing files reports exactly those paths.

        A fourth missing file in another crate stays out of this check.
        One missing file is a hard red even when the score would still pass.

        Returns:
            None. The test fails if a path is missing or an extra path appears.
        """
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            gone = [root / f"gone-{index}.mp3" for index in range(3)]
            other = root / "other-missing.mp3"

            def setup(conn: sqlite3.Connection) -> None:
                _add_crate(conn, 5, "Friday")
                _add_crate(conn, 6, "Other")
                for index, path in enumerate(gone, start=1):
                    _add_track(conn, index, str(path), title=f"Gone {index}", crate_id=5)
                _add_track(conn, 4, str(other), title="Elsewhere", crate_id=6)

            database = _write_db(root, setup)
            report = gig_check.run_gig_check(database, crate_id=5, now=NOW)
            self.assertEqual({Path(item.path) for item in report.missing_files}, set(gone))
            self.assertEqual(len(report.missing_files), 3)
            self.assertEqual(report.unavailable_drives, ())
            self.assertTrue(report.hard_red)
            self.assertFalse(report.ready)
            missing = next(line for line in report.holding_it_back if line.code == "missing_files")
            self.assertTrue(missing.hard_red)
            whole = gig_check.run_gig_check(database, now=NOW)
            self.assertEqual(len(whole.missing_files), 4)

    def test_one_missing_file_is_not_ready_above_the_score_line(self) -> None:
        """One missing file fails the gig even though the points would pass.

        Returns:
            None. The test fails if ready is true while the score is high.
        """
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            missing = root / "only-one.mp3"

            def setup(conn: sqlite3.Connection) -> None:
                _add_crate(conn, 5, "Friday")
                _add_track(conn, 1, str(missing), crate_id=5)

            database = _write_db(root, setup)
            report = gig_check.run_gig_check(database, crate_id=5, now=NOW)
            self.assertEqual(len(report.missing_files), 1)
            self.assertGreaterEqual(report.score, gig_check.READY_AT)
            self.assertTrue(report.hard_red)
            self.assertFalse(report.ready)

    def test_unmounted_drive_is_one_line_and_not_missing(self) -> None:
        """Tracks on an unplugged drive are unavailable under that drive's name.

        Relative paths on that location are not resolved under the home
        directory and are not counted as missing. An empty crate on the
        same drive is not described as a crate Serato may delete.

        Returns:
            None. The test fails if any of those tracks is listed as missing
            or the drive name is repeated once per track.
        """
        name, absolute, uri = _absent_drive()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def setup(conn: sqlite3.Connection) -> None:
                _add_crate(conn, 5, "Friday")
                _add_crate(conn, 8, "Spare")
                conn.execute(
                    "INSERT INTO connection (location_id, database_uri) VALUES (9, ?)",
                    (uri,),
                )
                conn.execute(
                    """
                    INSERT INTO location_container (id, container_id, location_id)
                    VALUES (1, 5, 9), (2, 8, 9)
                    """
                )
                _add_track(conn, 1, absolute, title="On the drive", crate_id=5)
                _add_track(
                    conn,
                    2,
                    "serato-gig-check-absent-relative/a.mp3",
                    title="Relative A",
                    location_id=9,
                    crate_id=5,
                )
                _add_track(
                    conn,
                    3,
                    "serato-gig-check-absent-relative/b.mp3",
                    title="Relative B",
                    location_id=9,
                    crate_id=5,
                )

            database = _write_db(root, setup)
            report = gig_check.run_gig_check(database, now=NOW)
            self.assertEqual(report.missing_files, ())
            self.assertEqual([drive.name for drive in report.unavailable_drives], [name])
            self.assertEqual(report.unavailable_drives[0].track_count, 3)
            self.assertIn("Friday", report.unavailable_drives[0].crates)
            self.assertIn("Spare", report.unavailable_drives[0].crates)
            self.assertEqual(report.empty_crates, ())
            self.assertTrue(report.hard_red)
            self.assertFalse(report.ready)
            summary = next(line.summary for line in report.holding_it_back if line.code == "absent_drive")
            self.assertIn("absent", summary)
            self.assertIn(name, summary)
            text = gig_check.format_report(report)
            self.assertEqual(text.count(f"{name}:"), 1)
            self.assertIn("unavailable", text)

    def test_streaming_tracks_are_separate_from_local_files(self) -> None:
        """Apple Music is streaming. iTunes and an unknown type are not.

        The Apple Music marker is third_party_type 6. A missing iTunes file
        stays a missing file. An undocumented type is not guessed.

        Returns:
            None. The test fails if the streaming track is counted as missing.
        """
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            local = root / "local-missing.mp3"
            itunes = root / "itunes-missing.mp3"
            unknown = root / "unknown-missing.mp3"

            def setup(conn: sqlite3.Connection) -> None:
                _add_crate(conn, 5, "Friday")
                _add_track(conn, 1, str(local), title="Local", crate_id=5)
                _add_track(conn, 2, "streaming/apple-1", title="Stream", third_party=6, crate_id=5)
                _add_track(conn, 3, str(itunes), title="Purchased", third_party=1, crate_id=5)
                _add_track(conn, 4, str(unknown), title="Unknown", third_party=99, crate_id=5)

            database = _write_db(root, setup)
            report = gig_check.run_gig_check(database, crate_id=5, now=NOW)
            self.assertEqual([item.service for item in report.streaming_tracks], ["Apple Music"])
            self.assertEqual(report.streaming_tracks[0].title, "Stream")
            missing = {Path(item.path).name for item in report.missing_files}
            self.assertEqual(missing, {"local-missing.mp3", "itunes-missing.mp3", "unknown-missing.mp3"})
            self.assertNotIn("apple-1", {item.path for item in report.missing_files})

    def test_snapshot_diff_matches_the_fixture(self) -> None:
        """Added, removed, and edited cues and grids match two hand-built snapshots.

        Returns:
            None. The test fails if a path lands in the wrong list.
        """
        tags = _tags("Keep")
        before = LoadedSnapshot(
            SnapshotInfo("then", NOW - timedelta(days=1), "Last gig"),
            (
                SnapshotCrate("Friday", ("t1", "t2")),
                SnapshotCrate("Warmup", ("t3",)),
            ),
            (
                SnapshotTrack("t1", "/music/a.mp3", ("Friday",), (CueMark("cue", 0, 1000, None, "In"),), (), tags),
                SnapshotTrack("t2", "/music/b.mp3", ("Friday",), (), (GridMark(0.0, 120.0, None),), tags),
                SnapshotTrack("t3", "/music/c.mp3", ("Warmup",), (), (), tags),
            ),
        )
        edited = _tags("Renamed")
        after = LoadedSnapshot(
            SnapshotInfo("now", NOW, "Now"),
            (
                SnapshotCrate("Friday", ("t1", "t4")),
                SnapshotCrate("Peak", ("t4",)),
            ),
            (
                SnapshotTrack("t1", "/music/a.mp3", ("Friday",), (CueMark("cue", 0, 1500, None, "In"),), (), edited),
                SnapshotTrack("t2", "/music/b.mp3", ("Friday",), (), (GridMark(0.0, 128.0, None),), tags),
                SnapshotTrack("t4", "/music/d.mp3", ("Peak",), (), (), tags),
            ),
        )
        diff = gig_snapshots.diff_snapshots(before, after)
        self.assertEqual(diff.crates_added, ("Peak",))
        self.assertEqual(diff.crates_removed, ("Warmup",))
        self.assertEqual(diff.crates_edited, ("Friday",))
        self.assertEqual(diff.tracks_added, ("/music/d.mp3",))
        self.assertEqual(diff.tracks_removed, ("/music/c.mp3",))
        self.assertEqual(diff.cues_edited, ("/music/a.mp3",))
        self.assertEqual(diff.grids_edited, ("/music/b.mp3",))
        self.assertEqual(diff.tags_edited, ("/music/a.mp3",))
        self.assertIsInstance(diff, ChangeReport)

    def test_live_library_diff_uses_the_fake_snapshot(self) -> None:
        """A cue in the snapshot and none in the file is an edited cue.

        The file is opened by the check. Its bytes are hashed before and after.

        Returns:
            None. The test fails if the path is not in cues_edited or the file changes.
        """
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            song = root / "song.mp3"
            song.write_bytes(b"not an mp3, just bytes")
            portable = str(song)

            def setup(conn: sqlite3.Connection) -> None:
                _add_crate(conn, 5, "Friday")
                _add_track(conn, 1, portable, title="Song", crate_id=5)

            database = _write_db(root, setup)
            key = track_key(1, portable)
            previous = LoadedSnapshot(
                SnapshotInfo("last", NOW - timedelta(days=1), "Last gig"),
                (SnapshotCrate("Friday", (key,)),),
                (
                    SnapshotTrack(
                        key,
                        portable,
                        ("Friday",),
                        (CueMark("cue", 0, 1000, None, "Drop"),),
                        (GridMark(0.0, 126.0, None),),
                        _tags("Song"),
                    ),
                ),
            )
            before = _digest(song)
            before_db = _digest(database)
            report = gig_check.run_gig_check(
                database,
                snapshots_reader=FakeSnapshots((previous,)),
                now=NOW,
            )
            self.assertEqual(_digest(song), before)
            self.assertEqual(_digest(database), before_db)
            assert report.changes is not None
            self.assertIn(portable, report.changes.cues_edited)
            self.assertIn(portable, report.changes.grids_edited)
            self.assertEqual(report.changes.tracks_added, ())
            self.assertEqual(report.changes.tags_edited, ())

    def test_no_snapshot_in_seven_days_lowers_the_score(self) -> None:
        """A snapshot older than seven days lowers the score and says so.

        A snapshot taken exactly seven days ago does not. No snapshots at
        all says ``No snapshots yet`` and also lowers the score.

        Returns:
            None. The test fails if the stale run scores the same as the fresh one.
        """
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            song = root / "song.mp3"
            song.write_bytes(b"bytes")
            portable = str(song)

            def setup(conn: sqlite3.Connection) -> None:
                _add_track(conn, 1, portable, title="Song")

            database = _write_db(root, setup)
            key = track_key(1, portable)
            loaded = LoadedSnapshot(
                SnapshotInfo("last", NOW, "Gig"),
                (),
                (SnapshotTrack(key, portable, (), (), (), _tags("Song"), False, False),),
            )

            def at(when: datetime) -> gig_check.GigReport:
                reader = FakeSnapshots(
                    (LoadedSnapshot(SnapshotInfo("last", when, "Gig"), (), loaded.tracks),)
                )
                return gig_check.run_gig_check(database, snapshots_reader=reader, now=NOW)

            fresh = at(NOW - timedelta(days=7))
            stale = at(NOW - timedelta(days=7, seconds=1))
            none = gig_check.run_gig_check(database, now=NOW)
            self.assertEqual(none.snapshot_note, gig_check.NO_SNAPSHOTS)
            self.assertIsNone(none.changes)
            self.assertTrue(any(line.summary == gig_check.STALE_SNAPSHOT for line in none.holding_it_back))
            self.assertLess(stale.score, fresh.score)
            self.assertEqual(stale.score, fresh.score - gig_check.STALE_POINTS)
            self.assertTrue(any(line.summary == gig_check.STALE_SNAPSHOT for line in stale.holding_it_back))
            self.assertFalse(any(line.summary == gig_check.STALE_SNAPSHOT for line in fresh.holding_it_back))
            self.assertNotEqual(stale.snapshot_note, gig_check.NO_SNAPSHOTS)
            self.assertGreaterEqual(fresh.score, gig_check.READY_AT)
            self.assertTrue(fresh.ready)
            self.assertEqual(none.score, fresh.score - gig_check.STALE_POINTS)

    def test_empty_crate_warns_and_writes_nothing(self) -> None:
        """An empty crate is listed, and the database and audio bytes stay put.

        A smart crate and a parent that still has a subcrate are not listed.
        The warning says Serato may delete the crate. It does not claim a
        verified version deletes it.

        Returns:
            None. The test fails if the warning is absent or a hash changes.
        """
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            song = root / "song.mp3"
            song.write_bytes(b"bytes")

            def setup(conn: sqlite3.Connection) -> None:
                _add_crate(conn, 5, "Parent")
                _add_crate(conn, 6, "Child", parent=5)
                _add_crate(conn, 7, "Smart", crate_type=2)
                _add_track(conn, 1, str(song), title="Song", crate_id=5)

            database = _write_db(root, setup)
            before_db = _digest(database)
            before_song = _digest(song)
            before_names = _names(root)
            report = gig_check.run_gig_check(database, now=NOW)
            self.assertEqual(_digest(database), before_db)
            self.assertEqual(_digest(song), before_song)
            self.assertEqual(_names(root), before_names)
            self.assertEqual([item.name for item in report.empty_crates], ["Parent / Child"])
            self.assertEqual(report.empty_crates[0].warning, gig_check.EMPTY_CRATE_WARNING)
            self.assertIn("may delete", report.empty_crates[0].warning)
            self.assertNotIn("Serato deletes this crate when it closes", report.empty_crates[0].warning)
            text = gig_check.format_report(report)
            self.assertIn(gig_check.EMPTY_CRATE_WARNING, text)
            self.assertIn("Holding it back", text)

    def test_check_hashes_are_unchanged_when_files_are_missing(self) -> None:
        """Missing files do not cause the check to create or rewrite anything.

        Returns:
            None. The test fails if the database hash or the directory listing changes.
        """
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            song = root / "kept.mp3"
            song.write_bytes(b"kept")

            def setup(conn: sqlite3.Connection) -> None:
                _add_crate(conn, 5, "Friday")
                _add_track(conn, 1, str(song), title="Kept", crate_id=5)
                _add_track(conn, 2, str(root / "gone.mp3"), title="Gone", crate_id=5)

            database = _write_db(root, setup)
            before = {path.name: _digest(path) for path in root.iterdir() if path.is_file()}
            names = _names(root)
            report = gig_check.run_gig_check(database, crate_id=5, now=NOW)
            after = {path.name: _digest(path) for path in root.iterdir() if path.is_file()}
            self.assertEqual(after, before)
            self.assertEqual(_names(root), names)
            self.assertEqual(len(report.missing_files), 1)
            self.assertFalse(report.ready)

    def test_cli_prints_the_holding_list(self) -> None:
        """The CLI prints Holding it back and returns 1 when the crate is not ready.

        A crate id that is not a number returns 2 before the library is opened.

        Returns:
            None. The test fails if the path or the snapshot sentence is missing.
        """
        usage = StringIO()
        with redirect_stdout(usage):
            code = gig_check.main(["--crate", "nope"])
        self.assertEqual(code, 2)
        self.assertEqual(usage.getvalue(), "")
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            missing = root / "gone.mp3"

            def setup(conn: sqlite3.Connection) -> None:
                _add_crate(conn, 5, "Friday")
                _add_track(conn, 1, str(missing), crate_id=5)

            database = _write_db(root, setup)
            output = StringIO()
            with redirect_stdout(output):
                status = gig_check.main(["--database", str(database), "--crate", "5"])
            text = output.getvalue()
            self.assertEqual(status, 1)
            self.assertIn("Holding it back", text)
            self.assertIn("Not ready", text)
            self.assertIn(str(missing), text)
            self.assertIn(gig_check.NO_SNAPSHOTS, text)

    def test_ten_thousand_tracks_finish_within_ten_seconds(self) -> None:
        """A 10,000-track crate is classified in under 10 seconds.

        The timer starts after the database is built and stops when the
        report returns. The printed line is the measurement recorded for
        the pull request.

        Returns:
            None. The test fails if the check takes 10 seconds or longer,
            or if the tracks are not all reported as missing files.
        """
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            database = root / "master.sqlite"
            with open_database(database) as conn:
                conn.executescript(SCHEMA)
                conn.execute("INSERT INTO space (id, name) VALUES (1, 'Serato Library')")
                conn.execute(
                    """
                    INSERT INTO container (id, parent_id, name, type, list_order, space_id)
                    VALUES (1, NULL, 'Library', 0, 0, 1)
                    """
                )
                _add_crate(conn, 5, "Friday")
                assets = [
                    (index, f"Track {index}", str(root / "missing" / f"{index}.mp3"), f"{index}.mp3")
                    for index in range(1, 10001)
                ]
                conn.executemany(
                    """
                    INSERT INTO asset (id, name, portable_id, file_name, is_missing)
                    VALUES (?, ?, ?, ?, 0)
                    """,
                    assets,
                )
                conn.executemany(
                    "INSERT INTO space_asset (id, asset_id, space_id) VALUES (?, ?, 1)",
                    [(index, index) for index in range(1, 10001)],
                )
                conn.executemany(
                    """
                    INSERT INTO container_asset (id, asset_id, container_id, list_order)
                    VALUES (?, ?, 5, ?)
                    """,
                    [(index, index, index) for index in range(1, 10001)],
                )
            started = time.perf_counter()
            report = gig_check.run_gig_check(database, crate_id=5, now=NOW)
            elapsed = time.perf_counter() - started
            print(f"gig-check 10k: {elapsed:.3f}s", flush=True)
            self.assertEqual(len(report.missing_files), 10000)
            self.assertEqual(report.unavailable_drives, ())
            self.assertLess(elapsed, 10.0, f"10k gig check took {elapsed:.3f}s")

    def test_saved_snapshot_store_feeds_the_change_report(self) -> None:
        """A snapshot from ``snapshots.py`` is compared with the library now.

        The snapshot is taken by ``SnapshotStore.take``. After it, one cue is
        moved, a crate is added, and a title is edited. The check reads the
        store beside the database on its own, reports exactly those changes,
        and leaves the database, the audio, and the store's files unchanged.

        Returns:
            None. The test fails if a change is missed, an extra change is
            reported, or a file hash changes.
        """
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            music = root / "music"
            track = music / "set" / "opener.mp3"
            track.parent.mkdir(parents=True)
            _audio_file(track)

            def setup(conn: sqlite3.Connection) -> None:
                _add_crate(conn, 5, "Friday")
                _add_track(conn, 1, str(track), title="Opener", crate_id=5)

            database = _write_db(root, setup)
            store = _quiet(
                snapshots.SnapshotStore(
                    database,
                    [
                        snapshots.DriveSpec(
                            drive_id="tour",
                            label="Tour",
                            serato_root=music / "_Serato_",
                            # The stored path is absolute, the way a file
                            # outside the home directory is stored. The music
                            # root is this temporary directory, not the
                            # filesystem root, so a drive letter has to be
                            # resolved rather than joined on as a relative name.
                            music_root=root,
                            role="external",
                            present=True,
                        )
                    ],
                )
            )
            (music / "_Serato_").mkdir()
            saved = store.take("manual", "Before Friday.")

            cue = bytearray(16)
            cue[1] = 3
            cue[2:6] = (3000).to_bytes(4, "big")
            cue[12:16] = b"Drop"
            moved = b"\x01\x01" + base64.b64encode(b"CUE\x00" + len(cue).to_bytes(4, "big") + bytes(cue))
            self.assertNotEqual(moved, _markers())
            frames = [
                _geob("Serato Markers2", moved),
                _geob("Serato BeatGrid", _grid()),
                _geob("Serato Autotags", _autotags()),
            ]
            track.write_bytes(_id3(frames, b"AUDIOFRAME" * 8))
            with open_database(database) as conn:
                _add_crate(conn, 6, "Saturday")
                conn.execute("UPDATE asset SET name = 'Opener (edit)' WHERE id = 1")

            watched = [database, track, *sorted(store.root.rglob("*"))]
            before = {str(path): _digest(path) for path in watched if path.is_file()}
            listing = _names(store.root)
            report = gig_check.run_gig_check(database)
            after = {str(path): _digest(path) for path in watched if path.is_file()}

            self.assertEqual(after, before)
            self.assertEqual(_names(store.root), listing)
            self.assertIn("Before Friday", report.snapshot_note)
            changes = report.changes
            assert changes is not None
            self.assertEqual(changes.crates_added, ("Saturday",))
            self.assertEqual(changes.crates_removed, ())
            self.assertEqual(changes.crates_edited, ())
            self.assertEqual(changes.tracks_added, ())
            self.assertEqual(changes.tracks_removed, ())
            self.assertEqual(len(changes.cues_edited), 1)
            self.assertEqual(Path(changes.cues_edited[0]).name, "opener.mp3")
            self.assertEqual(changes.grids_edited, ())
            self.assertEqual(len(changes.tags_edited), 1)
            self.assertNotIn("snapshot_stale", {line.code for line in report.holding_it_back})
            self.assertTrue(saved["id"])

    def test_fixture_audio_keeps_cues_when_the_path_is_absolute(self) -> None:
        """Read Serato 4 and 5 fixture cues through an absolute portable id.

        The clips are the spec-derived files in ``tests/fixtures``. The
        music root is the temporary directory. The stored path uses
        forward slashes, including a Windows drive letter. The cue names
        come from each tree's ``golden.json``, so a snapshot that never
        captured the file cannot pass.

        Returns:
            None. The test fails if a fixture cue is missing or the
            unchanged file is reported as edited.
        """
        fixtures = ROOT / "tests" / "fixtures"
        sources = (
            (fixtures / "serato4" / "audio" / "one-grid.mp3", "Drop", 1500),
            (fixtures / "serato5" / "audio" / "tempo.mp3", "Intro", 1500),
        )
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            music = root / "music"
            music.mkdir()
            stored: list[tuple[Path, str, int]] = []
            for source, cue_name, start_ms in sources:
                dest = music / source.name
                dest.write_bytes(source.read_bytes())
                stored.append((dest, cue_name, start_ms))

            def setup(conn: sqlite3.Connection) -> None:
                _add_crate(conn, 5, "Friday")
                for index, (track, _cue_name, _start_ms) in enumerate(stored, start=1):
                    _add_track(conn, index, track.as_posix(), title="Fixture", crate_id=5)

            database = _write_db(root, setup)
            store = _quiet(
                snapshots.SnapshotStore(
                    database,
                    [
                        snapshots.DriveSpec(
                            drive_id="tour",
                            label="Tour",
                            serato_root=music / "_Serato_",
                            music_root=root,
                            role="external",
                            present=True,
                        )
                    ],
                )
            )
            (music / "_Serato_").mkdir()
            store.take("manual", "Fixture cues.")
            report = gig_check.run_gig_check(database, now=NOW)
            changes = report.changes
            assert changes is not None
            self.assertEqual(changes.cues_edited, ())
            self.assertEqual(changes.grids_edited, ())
            reader = gig_check.StoreSnapshots(store)
            listed = reader.list_snapshots()
            self.assertEqual(len(listed), 1)
            loaded = reader.load(listed[0].snapshot_id)
            for track, cue_name, start_ms in stored:
                match = next(item for item in loaded.tracks if Path(item.path).name == track.name)
                self.assertTrue(match.cues_known, track.name)
                self.assertTrue(
                    any(mark.kind == "cue" and mark.name == cue_name and mark.start_ms == start_ms for mark in match.cues),
                    track.name,
                )

    def test_saved_frames_match_either_separator(self) -> None:
        """Match a saved frame when only the separators differ.

        On Windows the same lookup also ignores case. A relative id still
        matches a saved path that ends with it.

        Returns:
            None. The test fails if a separator or a relative tail misses
            the saved path.
        """
        saved = r"C:\Music\set\opener.mp3"
        frames = gig_check._SavedFrames(
            {
                "cues": [{"path": saved, "cues": [], "loops": []}],
                "grids": [],
                "tags": [],
            }
        )
        self.assertEqual(frames._find("C:/Music/set/opener.mp3"), saved)
        folded = frames._find("c:/music/set/opener.mp3")
        if os.name == "nt":
            self.assertEqual(folded, saved)
        else:
            self.assertIsNone(folded)
        volume = gig_check._SavedFrames(
            {
                "cues": [{"path": "/Volumes/Tour/Music/set/opener.mp3", "cues": [], "loops": []}],
                "grids": [],
                "tags": [],
            }
        )
        self.assertEqual(
            volume._find("Music/set/opener.mp3"),
            "/Volumes/Tour/Music/set/opener.mp3",
        )
        self.assertIsNone(volume._find(""))

    def test_unreadable_snapshot_store_is_reported(self) -> None:
        """A store whose manifest key is broken says so and counts as stale.

        Returns:
            None. The test fails if the check raises or reports no snapshots.
        """
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            database = _write_db(root, lambda conn: None)
            store = _quiet(snapshots.SnapshotStore(database, []))
            store.take("manual", "Kept.")
            (store.root / "manifest.key").write_bytes(b"short")
            report = gig_check.run_gig_check(database, now=NOW)
            self.assertEqual(report.snapshot_note, gig_check.SNAPSHOTS_UNREADABLE)
            self.assertIn("snapshot_stale", {line.code for line in report.holding_it_back})

    def test_page_reads_the_gig_report_fields(self) -> None:
        """The Gig view requests /api/gig-check and reads the report fields.

        The script does not assign innerHTML. Paths are set with textContent.

        Returns:
            None. The test fails if a field the report sends is not read.
        """
        page = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn('data-view="gig"', page)
        self.assertIn('id="gig-report"', page)
        self.assertIn("/api/gig-check", script)
        for field in (
            "score",
            "ready",
            "holding_it_back",
            "missing_files",
            "unavailable_drives",
            "streaming_tracks",
            "empty_crates",
            "snapshot_note",
            "changes",
        ):
            self.assertIn(field, script)
        self.assertNotIn("innerHTML", script)
        guide = (ROOT / "docs" / "guide" / "gig-check.md").read_text(encoding="utf-8")
        self.assertIn(gig_check.EMPTY_CRATE_WARNING, guide)
        self.assertIn(gig_check.NO_SNAPSHOTS, guide)
        self.assertIn(gig_check.STALE_SNAPSHOT, guide)
        self.assertIn("70", guide)
        self.assertIn("Ready score", script)


class GigCheckApiTests(unittest.TestCase):
    """GET /api/gig-check against a temporary library."""

    def test_get_returns_the_report_and_does_not_write(self) -> None:
        """The route returns the score and leaves the database bytes unchanged.

        An unknown crate id is 400, matching the other crate queries. A crate
        id that is not in the library is 404.

        Returns:
            None. The test fails if the body is missing a field or the hash changes.
        """
        library_fixture = TempLibrary()
        library_fixture.__enter__()
        try:
            with open_database(library_fixture.db) as conn:
                _add_crate(conn, 5, "Empty night")
            before = _digest(library_fixture.db)
            names = _names(library_fixture.root)
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            host, port = httpd.server_address
            try:
                with urllib.request.urlopen(f"http://{host}:{port}/api/gig-check?crate=5") as response:
                    body = response.read()
                    status = response.status
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=3)
            self.assertEqual(status, 200)
            import json

            payload = json.loads(body.decode("utf-8"))
            self.assertIn("score", payload)
            self.assertIn("ready", payload)
            self.assertIn("holding_it_back", payload)
            self.assertEqual(payload["snapshot_note"], gig_check.NO_SNAPSHOTS)
            self.assertEqual(payload["empty_crates"][0]["warning"], gig_check.EMPTY_CRATE_WARNING)
            self.assertEqual(_digest(library_fixture.db), before)
            self.assertEqual(_names(library_fixture.root), names)
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            host, port = httpd.server_address
            try:
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(f"http://{host}:{port}/api/gig-check?crate=999")
                self.assertEqual(caught.exception.code, 404)
                caught.exception.close()
                with self.assertRaises(urllib.error.HTTPError) as bad:
                    urllib.request.urlopen(f"http://{host}:{port}/api/gig-check?crate=nope")
                self.assertEqual(bad.exception.code, 400)
                bad.exception.close()
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=3)
        finally:
            library_fixture.__exit__(None, None, None)


if __name__ == "__main__":
    unittest.main()
