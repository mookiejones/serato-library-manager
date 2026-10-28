"""Snapshots of the Serato database, crates, and in-file Serato frames.

The cases build a temporary library. They do not open a live Serato
database, and they do not read the machine's Serato preferences unless a
test points ``SERATO_LIBRARY_APP_INFO`` or ``SERATO_LIBRARY_PREFERENCES``
at a file it just wrote.
"""

from __future__ import annotations

import base64
import os
import plistlib
import struct
import subprocess
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import app_log
import completeness
import library
import snapshot_frames
import snapshots
from library import LibraryError
from snapshots import DriveSpec, SnapshotBlocked, SnapshotStore
from tests.fixture import TempLibrary


def _geob(description: str, payload: bytes) -> bytes:
    """Build one Latin-1 GEOB frame.

    Args:
        description: Frame description, such as ``Serato Markers2``.
        payload: Data stored after the description.

    Returns:
        The raw frame, header included.
    """
    body = bytes([0]) + b"application/octet-stream\x00\x00" + description.encode("latin-1") + b"\x00" + payload
    return b"GEOB" + len(body).to_bytes(4, "big") + b"\x00\x00" + body


def _id3(frames: list[bytes], audio: bytes) -> bytes:
    """Build an ID3v2.3 tag followed by audio bytes.

    Args:
        frames: Raw frames.
        audio: Bytes that must survive a frame restore.

    Returns:
        The whole file.
    """
    body = b"".join(frames)
    size = len(body)
    synchsafe = bytes((
        (size >> 21) & 0x7F,
        (size >> 14) & 0x7F,
        (size >> 7) & 0x7F,
        size & 0x7F,
    ))
    return b"ID3" + bytes([3, 0, 0]) + synchsafe + body + audio


def _markers() -> bytes:
    """Return a Markers2 payload with one cue named Drop.

    Returns:
        Payload bytes, including the ``01 01`` header.
    """
    cue = bytearray(16)
    cue[1] = 3
    cue[2:6] = (1500).to_bytes(4, "big")
    cue[7:10] = b"\xcc\x00\x00"
    cue[12:16] = b"Drop"
    entry = b"CUE\x00" + len(cue).to_bytes(4, "big") + bytes(cue)
    return b"\x01\x01" + base64.b64encode(entry)


def _grid() -> bytes:
    """Return a one-marker BeatGrid at 128 BPM.

    Returns:
        BeatGrid payload bytes.
    """
    return bytes([1, 0]) + (1).to_bytes(4, "big") + struct.pack(">f", 1.0) + struct.pack(">f", 128.0)


def _autotags() -> bytes:
    """Return a distinctive Autotags payload.

    Returns:
        Bytes that are not a guessed Serato struct. The snapshot stores them
        as-is.
    """
    return b"\x01AUTOTAGS-TEST"


def _audio_file(path: Path) -> bytes:
    """Write an MP3-shaped file and return its audio bytes.

    Args:
        path: File to create.

    Returns:
        The audio region stored after the tag.
    """
    audio = b"AUDIOFRAME" * 8
    frames = [
        _geob("Serato Markers2", _markers()),
        _geob("Serato BeatGrid", _grid()),
        _geob("Serato Autotags", _autotags()),
    ]
    path.write_bytes(_id3(frames, audio))
    return audio


def _chunk(tag: str, data: bytes) -> bytes:
    """Build one Serato chunk.

    Args:
        tag: Four-character tag.
        data: Payload.

    Returns:
        Tag, big-endian length, and payload.
    """
    return tag.encode("ascii") + len(data).to_bytes(4, "big") + data


def _utf16(text: str) -> bytes:
    """Encode a Serato path.

    Args:
        text: Path text.

    Returns:
        UTF-16-BE bytes.
    """
    return text.encode("utf-16-be")


def _crate(paths: list[str]) -> bytes:
    """Build a crate file that points at the given paths.

    Args:
        paths: Track paths stored in ``ptrk`` chunks.

    Returns:
        Crate bytes.
    """
    body = _chunk("vrsn", _utf16("1.0/Serato ScratchLive Crate"))
    for path in paths:
        body += _chunk("otrk", _chunk("ptrk", _utf16(path)))
    return body


def _plist(path: Path, values: dict[str, object]) -> None:
    """Write an XML plist.

    Args:
        path: Destination.
        values: Keys to store.
    """
    with path.open("wb") as handle:
        plistlib.dump(values, handle)


@contextmanager
def _env(**values: str | None) -> Iterator[None]:
    """Set environment variables for one test and restore them afterwards.

    Args:
        values: Names to set. None removes the variable.

    Yields:
        None.
    """
    previous = {key: os.environ.get(key) for key in values}
    for key, value in values.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _quiet(store: SnapshotStore) -> SnapshotStore:
    """Point process checks at empty results.

    Args:
        store: Store under test.

    Returns:
        The same store. A machine that is running Serato DJ or Lexicon does
        not change the result.
    """
    store.serato_running = lambda: False
    store.process_names = lambda: []
    return store


class FrameRestoreTests(unittest.TestCase):
    """Round-trip Serato frames for the containers a snapshot restores."""

    def test_mp3_flac_aiff_and_m4a_frames_round_trip(self) -> None:
        """Restore stored frames and leave each container's audio bytes alone.

        MP3 and AIFF compare the raw GEOB frames. FLAC compares the Vorbis
        comment value. M4A compares the freeform ``data`` atom body.

        Returns:
            None. The test fails if a stored frame or the audio region changes.
        """
        audio = b"AUDIOFRAME" * 4
        frames = [
            _geob("Serato Markers2", _markers()),
            _geob("Serato BeatGrid", _grid()),
            _geob("Serato Autotags", _autotags()),
        ]
        with TempLibrary() as temp:
            mp3 = temp.root / "track.mp3"
            mp3.write_bytes(_id3(frames, audio))
            original = snapshot_frames.read_stored_frames(mp3)
            self._corrupt(mp3, original)
            snapshot_frames.restore_stored_frames(mp3, original)
            self.assertEqual(snapshot_frames.read_stored_frames(mp3), original)
            self.assertEqual(snapshot_frames.read_audio(mp3), audio)

            flac = temp.root / "track.flac"
            flac.write_bytes(_flac_file(original, audio))
            self.assertEqual(snapshot_frames.read_audio(flac), audio)
            snapshot_frames.restore_stored_frames(flac, snapshot_frames.read_stored_frames(flac))
            self.assertEqual(snapshot_frames.read_stored_frames(flac), _flac_stored(original))
            self.assertEqual(snapshot_frames.read_audio(flac), audio)

            aiff = temp.root / "track.aiff"
            aiff.write_bytes(_aiff_file(_id3(frames, b""), audio))
            aiff_frames = snapshot_frames.read_stored_frames(aiff)
            self.assertEqual(set(aiff_frames), set(original))
            self._corrupt(aiff, aiff_frames)
            snapshot_frames.restore_stored_frames(aiff, aiff_frames)
            self.assertEqual(snapshot_frames.read_stored_frames(aiff), aiff_frames)
            self.assertEqual(snapshot_frames.read_audio(aiff), b"\x00" * 8 + audio)

            m4a = temp.root / "track.m4a"
            m4a.write_bytes(_m4a_file(audio))
            m4a_frames = snapshot_frames.read_stored_frames(m4a)
            self.assertIn("Markers2", m4a_frames)
            self.assertIn("BeatGrid", m4a_frames)
            before_audio = snapshot_frames.read_audio(m4a)
            self._corrupt(m4a, m4a_frames)
            snapshot_frames.restore_stored_frames(m4a, m4a_frames)
            self.assertEqual(snapshot_frames.read_stored_frames(m4a), m4a_frames)
            self.assertEqual(snapshot_frames.read_audio(m4a), before_audio)

    def _corrupt(self, path: Path, frames: dict[str, bytes]) -> None:
        """Flip the last byte of each stored frame inside the file.

        Args:
            path: Audio file.
            frames: Frames returned by ``read_stored_frames``.
        """
        raw = bytearray(path.read_bytes())
        for blob in frames.values():
            index = raw.find(blob)
            self.assertGreaterEqual(index, 0)
            raw[index + len(blob) - 1] ^= 0xFF
        path.write_bytes(raw)


class SnapshotTests(unittest.TestCase):
    """Hash-checked snapshots, restore, and the Serato 5 gate."""

    def test_corrupt_cues_and_grids_restore_to_the_same_geob_bytes(self) -> None:
        """Snapshot, corrupt Markers2 and BeatGrid, and restore those GEOB bytes.

        The audio frames after the tag stay byte-identical. Autotags are
        restored by the same path.

        Returns:
            None. The test fails if a GEOB frame or the audio suffix differs.
        """
        with TempLibrary() as temp:
            music, serato, store = _drive(temp.root, temp.db)
            audio = _audio_file(music / "track.mp3")
            (serato / "Subcrates").mkdir(parents=True)
            (serato / "Subcrates" / "House.crate").write_bytes(_crate(["track.mp3"]))
            original = snapshot_frames.read_stored_frames(music / "track.mp3")
            saved = store.take("manual", "Before the file was corrupted.")
            self._flip_frames(music / "track.mp3", original)
            self.assertNotEqual(snapshot_frames.read_stored_frames(music / "track.mp3"), original)
            store.restore(saved["id"])
            self.assertEqual(snapshot_frames.read_stored_frames(music / "track.mp3"), original)
            self.assertEqual(snapshot_frames.read_audio(music / "track.mp3"), audio)
            loaded = store.load(saved["id"])
            self.assertTrue(any(cue["cues"] and cue["cues"][0]["name"] == "Drop" for cue in loaded["cues"]))
            self.assertTrue(any(grid["markers"] for grid in loaded["grids"]))
            self.assertTrue(any(tag["kind"] == "Autotags" for tag in loaded["tags"]))

    def test_restore_round_trip_keeps_an_undo_snapshot(self) -> None:
        """Restore a crate and keep a snapshot taken before that restore.

        Returns:
            None. The test fails if the crate is not put back, or if the
            restore did not save a snapshot first.
        """
        with TempLibrary() as temp:
            _music, serato, store = _drive(temp.root, temp.db)
            crate = serato / "Subcrates" / "House.crate"
            crate.parent.mkdir(parents=True)
            original = _crate(["track.mp3"])
            crate.write_bytes(original)
            saved = store.take("manual", "Crate as it was.")
            crate.write_bytes(_crate(["other.mp3"]))
            result = store.restore(saved["id"])
            self.assertEqual(crate.read_bytes(), original)
            self.assertNotEqual(result["undo_snapshot"], result["restored"])
            undo = store.load(str(result["undo_snapshot"]))
            self.assertEqual(undo["info"]["trigger"], "before-restore")
            self.assertIn(saved["id"], [item["id"] for item in store.list_snapshots()])

    def test_missing_drive_is_unavailable_and_not_removed(self) -> None:
        """Keep crates and tracks when their drive is no longer passed in.

        Returns:
            None. The test fails if the crate or its cue disappears, or if a
            dry run calls that disappearance a removal.
        """
        with TempLibrary() as temp:
            music, serato, store = _drive(temp.root, temp.db)
            _audio_file(music / "track.mp3")
            crate = serato / "Subcrates" / "House.crate"
            crate.parent.mkdir(parents=True)
            crate.write_bytes(_crate(["track.mp3"]))
            (serato / "database V2").write_bytes(_chunk("otrk", _chunk("ptrk", _utf16("track.mp3"))))
            store.take("manual", "Drive is plugged in.")
            store.drives = []
            second = store.take("manual", "Drive is unplugged.")
            loaded = store.load(second["id"])
            kept = [item for item in loaded["crates"] if item["path"] == "Subcrates/House.crate"]
            self.assertEqual(len(kept), 1)
            self.assertFalse(kept[0]["present"])
            self.assertEqual(kept[0]["tracks"], ["track.mp3"])
            database = [item for item in loaded["crates"] if item["source"] == "database-v2"]
            self.assertEqual(database[0]["tracks"], ["track.mp3"])
            self.assertFalse(database[0]["present"])
            cues = [item for item in loaded["cues"] if item["path"].endswith("track.mp3")]
            self.assertEqual(len(cues), 1)
            self.assertFalse(cues[0]["present"])
            diff = store.plan(second["id"])
            self.assertEqual(diff["crates"]["removed"], [])
            self.assertTrue(diff["crates"]["unavailable"])

    def test_outside_change_is_snapshotted_after_the_write_and_can_be_undone(self) -> None:
        """Log an outside edit and undo it back to the previous snapshot.

        The log says the snapshot was taken after the change. It does not
        claim a copy from before the other program wrote.

        Returns:
            None. The test fails if the crate is not restored or the log
            claims a pre-change snapshot.
        """
        with TempLibrary() as temp:
            _music, serato, store = _drive(temp.root, temp.db)
            crate = serato / "Subcrates" / "House.crate"
            crate.parent.mkdir(parents=True)
            original = _crate(["track.mp3"])
            crate.write_bytes(original)
            store.take("manual", "Before the outside edit.")
            store.rebase_fingerprint()
            crate.write_bytes(_crate(["changed.mp3"]))
            log_directory = app_log.configure()
            pending = store.poll()
            self.assertIsNotNone(pending)
            assert pending is not None
            text = (log_directory / "serato-library.log").read_text(encoding="utf-8")
            self.assertIn("outside this app", text)
            self.assertIn("after the change", text)
            self.assertIn("not available", text)
            self.assertIn(str(pending["snapshot_id"]), text)
            store.undo_outside()
            self.assertEqual(crate.read_bytes(), original)

    def test_two_snapshots_in_the_same_second_both_save(self) -> None:
        """Save two snapshots when their ids would otherwise collide.

        ``ensure_backup`` raises ``FileExistsError`` for two directories in
        the same second. Snapshot ids carry a random suffix and the writer
        retries if that file already exists.

        Returns:
            None. The test fails if the second snapshot raises or replaces
            the first.
        """
        with TempLibrary() as temp:
            _music, _serato, store = _drive(temp.root, temp.db)
            first = store.take("manual", "First.")
            second = store.take("manual", "Second.")
            self.assertNotEqual(first["id"], second["id"])
            ids = iter([
                "20261028T000000000000Z-aaaa1111",
                "20261028T000000000000Z-aaaa1111",
                "20261028T000000000000Z-bbbb2222",
            ])
            original = snapshots._new_id
            snapshots._new_id = lambda: next(ids)
            try:
                third = store.take("manual", "Collision.")
                fourth = store.take("manual", "Retried.")
            finally:
                snapshots._new_id = original
            self.assertEqual(third["id"], "20261028T000000000000Z-aaaa1111")
            self.assertEqual(fourth["id"], "20261028T000000000000Z-bbbb2222")
            self.assertEqual(len(store.list_snapshots()), 4)

    def test_restore_plan_lists_changes_and_writes_nothing(self) -> None:
        """Show crate, track, cue, and grid differences without saving.

        Returns:
            None. The test fails if a file or the snapshot list changes.
        """
        with TempLibrary() as temp:
            music, serato, store = _drive(temp.root, temp.db)
            track = music / "track.mp3"
            _audio_file(track)
            crate = serato / "Subcrates" / "House.crate"
            crate.parent.mkdir(parents=True)
            crate.write_bytes(_crate(["track.mp3"]))
            saved = store.take("manual", "Clean copy.")
            before = {
                "track": track.read_bytes(),
                "crate": crate.read_bytes(),
                "database": temp.db.read_bytes(),
                "snapshots": [item["id"] for item in store.list_snapshots()],
            }
            original = snapshot_frames.read_stored_frames(track)
            self._flip_frames(track, original)
            extra = serato / "Subcrates" / "New.crate"
            extra.write_bytes(_crate(["added.mp3"]))
            plan = store.plan(saved["id"])
            self.assertTrue(plan["dry_run"])
            self.assertFalse(plan["changed"])
            self.assertIsNone(plan["restore_blocked"])
            self.assertTrue(any(item["path"].endswith("track.mp3") for item in plan["cues"]))
            self.assertTrue(any(item["path"].endswith("track.mp3") for item in plan["grids"]))
            self.assertTrue(any(item["path"] == "Subcrates/New.crate" for item in plan["crates"]["removed"]))
            self.assertEqual(track.read_bytes(), self._flipped(before["track"], original))
            self.assertEqual(crate.read_bytes(), before["crate"])
            self.assertEqual(temp.db.read_bytes(), before["database"])
            self.assertEqual([item["id"] for item in store.list_snapshots()], before["snapshots"])

    def test_restore_refuses_while_serato_dj_is_running(self) -> None:
        """Refuse a restore when the process list reports Serato DJ.

        The dry run still describes the change and writes nothing. macOS
        ``ps`` output and Windows ``tasklist`` output are both recognized.

        Returns:
            None. The test fails if a file changes or the message omits the
            instruction to quit Serato.
        """
        self.assertTrue(snapshots._serato_in_ps("Serato DJ Pro\n"))
        self.assertFalse(snapshots._serato_in_ps("python\n/tmp/serato-library-manager/.venv/bin/python\n"))
        self.assertTrue(snapshots._serato_in_tasklist('"Serato DJ Pro.exe","10","Console","1","12 K"\n'))
        self.assertFalse(snapshots._serato_in_tasklist('"python.exe","10","Console","1","12 K"\n'))
        self.assertEqual(snapshots.detection_command("darwin")[0], "ps")
        self.assertEqual(snapshots.detection_command("win32")[0], "tasklist")
        seen: dict[str, list[str]] = {}

        def runner(command: list[str]) -> str:
            seen["command"] = command
            if command[0] == "tasklist":
                return '"Serato DJ Pro.exe","10","Console","1","12 K"\n'
            return "Serato DJ Pro\n"

        self.assertTrue(snapshots.serato_dj_running(runner))
        self.assertEqual(seen["command"][0], "tasklist" if os.name == "nt" else "ps")
        with TempLibrary() as temp:
            _music, serato, store = _drive(temp.root, temp.db)
            crate = serato / "Subcrates" / "House.crate"
            crate.parent.mkdir(parents=True)
            original = _crate(["track.mp3"])
            crate.write_bytes(original)
            saved = store.take("manual", "While Serato is quit.")
            crate.write_bytes(_crate(["changed.mp3"]))
            changed = crate.read_bytes()
            count = len(store.list_snapshots())
            store.serato_running = lambda: True
            plan = store.plan(saved["id"])
            self.assertEqual(plan["restore_blocked"], snapshots.SERATO_RUNNING_MESSAGE)
            self.assertEqual(crate.read_bytes(), changed)
            self.assertEqual(len(store.list_snapshots()), count)
            with self.assertRaises(SnapshotBlocked) as caught:
                store.restore(saved["id"])
            self.assertIn("Quit Serato DJ Pro", caught.exception.message)
            self.assertEqual(crate.read_bytes(), changed)
            self.assertEqual(len(store.list_snapshots()), count)

    def test_serato_5_gate_reads_protect_library_and_still_snapshots(self) -> None:
        """Refuse writes and restores for Serato 5, and still save a snapshot.

        Protect Library on, off, missing, and unreadable each refuse.
        Lucid and Flexible beatgrid storage stays unverified. The refusal
        does not depend on a file lock. Build ``5.0.0.1251`` is recorded.
        An unreadable bundle is stored as unknown.

        Returns:
            None. The test fails if a refused write changes the database.
        """
        with TempLibrary() as temp:
            info = temp.root / "Info.plist"
            prefs = temp.root / "com.serato.seratodj.plist"
            _plist(info, {
                "CFBundleShortVersionString": "5.0.0",
                "CFBundleVersion": "5.0.0.1251",
            })
            _plist(prefs, {"library_protect": 1})
            with _env(SERATO_LIBRARY_APP_INFO=str(info), SERATO_LIBRARY_PREFERENCES=str(prefs)):
                before = temp.db.read_bytes()
                with self.assertRaises(LibraryError) as caught:
                    library.begin_write()
                self.assertIn("Protect Library is on", caught.exception.message)
                self.assertIn("Lucid", caught.exception.message)
                self.assertIn("Flexible", caught.exception.message)
                self.assertNotIn("lock", caught.exception.message.lower())
                self.assertEqual(temp.db.read_bytes(), before)
                _music, serato, store = _drive(temp.root, temp.db)
                (serato / "database V2").write_bytes(b"still-writable")
                saved = store.take("manual", "Read-only snapshot of Serato 5.")
                self.assertEqual(saved["serato_version"], "5.0.0")
                self.assertEqual(saved["serato_build"], "5.0.0.1251")
                with self.assertRaises(SnapshotBlocked) as blocked:
                    store.restore(saved["id"])
                self.assertIn("Protect Library is on", blocked.exception.message)
                _plist(prefs, {"library_protect": 0})
                message = snapshots.write_block_message()
                assert message is not None
                self.assertIn("Protect Library is off", message)
                self.assertIn("not verified", message)
                prefs.unlink()
                self.assertIn("unknown", snapshots.write_block_message() or "")
                _plist(prefs, {"something_else": 1})
                self.assertIn("unknown", snapshots.write_block_message() or "")
                prefs.write_bytes(b"this is not a plist")
                self.assertIn("unknown", snapshots.write_block_message() or "")
                info.write_bytes(b"this is not a plist")
                unknown = store.take("manual", "Version could not be read.")
                self.assertEqual(unknown["serato_version"], "unknown")
                self.assertEqual(unknown["serato_build"], "unknown")
                with self.assertRaises(LibraryError) as unknown_write:
                    library.begin_write()
                self.assertIn("unknown", unknown_write.exception.message.lower())
                with self.assertRaises(SnapshotBlocked):
                    store.restore(unknown["id"])

    def test_version_change_snapshots_once(self) -> None:
        """Snapshot when the recorded build changes, and only once.

        Returns:
            None. The test fails if the first sight of a version snapshots,
            or if a second check snapshots again.
        """
        with TempLibrary() as temp:
            info = temp.root / "Info.plist"
            _plist(info, {"CFBundleShortVersionString": "4.1.0", "CFBundleVersion": "4.1.0.1"})
            _music, _serato, store = _drive(temp.root, temp.db)
            with _env(SERATO_LIBRARY_APP_INFO=str(info), SERATO_LIBRARY_PREFERENCES=None):
                self.assertIsNone(store.check_version())
                self.assertEqual(store.list_snapshots(), [])
                _plist(info, {"CFBundleShortVersionString": "5.0.0", "CFBundleVersion": "5.0.0.1251"})
                saved = store.check_version()
                assert saved is not None
                self.assertEqual(saved["trigger"], "version-change")
                self.assertEqual(saved["serato_build"], "5.0.0.1251")
                self.assertIn("as it is now", saved["reason"])
                self.assertIsNone(store.check_version())

    def test_lexicon_write_is_named_and_excluded_folders_are_never_touched(self) -> None:
        """Treat a Lexicon write as an outside change and leave its folder alone.

        A running Lexicon process names the source. A ``Lexicon`` directory
        timestamp close to the edited crate does too. ``Lexicon`` and
        ``Export Backups`` are not snapshotted or restored. A sibling named
        ``Export Backups-extra`` is.

        Returns:
            None. The test fails if a zip changes, if the log omits Lexicon,
            or if undo does not put the crate back.
        """
        with TempLibrary() as temp:
            music, serato, store = _drive(temp.root, temp.db)
            crate = serato / "Subcrates" / "House.crate"
            crate.parent.mkdir(parents=True)
            original = _crate(["track.mp3"])
            crate.write_bytes(original)
            lexicon = serato / "Lexicon"
            exports = serato / "Export Backups"
            sibling = serato / "Export Backups-extra"
            lexicon.mkdir()
            exports.mkdir()
            sibling.mkdir()
            secret = lexicon / "backup.zip"
            old = exports / "old.zip"
            kept = sibling / "keep.txt"
            secret.write_bytes(b"lexicon-zip")
            old.write_bytes(b"serato-export")
            kept.write_bytes(b"sibling")
            saved = store.take("manual", "With the extra folders present.")
            loaded = store.load(saved["id"])
            paths = [item["path"] for item in loaded["crates"]]
            manifest = store._manifest(saved["id"])
            stored_paths = [
                item["path"]
                for drive in manifest["drives"]
                if isinstance(drive, dict)
                for item in drive.get("files", [])
                if isinstance(item, dict)
            ]
            self.assertNotIn("Lexicon/backup.zip", stored_paths)
            self.assertNotIn("Export Backups/old.zip", stored_paths)
            self.assertIn("Export Backups-extra/keep.txt", stored_paths)
            self.assertNotIn("backup.zip", " ".join(paths))
            if os.name != "nt":
                lexicon.chmod(0)
                exports.chmod(0)
                try:
                    store.take("manual", "Unreadable excluded folders.")
                finally:
                    lexicon.chmod(0o755)
                    exports.chmod(0o755)
            self.assertEqual(secret.read_bytes(), b"lexicon-zip")
            self.assertEqual(old.read_bytes(), b"serato-export")
            store.rebase_fingerprint()
            crate.write_bytes(_crate(["lexicon-edit.mp3"]))
            os.utime(lexicon, (crate.stat().st_mtime, crate.stat().st_mtime))
            log_directory = app_log.configure()
            pending = store.poll()
            assert pending is not None
            self.assertEqual(pending["source"], "Lexicon")
            text = (log_directory / "serato-library.log").read_text(encoding="utf-8")
            self.assertIn("Lexicon changed the Serato folder", text)
            self.assertIn("after Lexicon wrote", text)
            store.undo_outside()
            self.assertEqual(crate.read_bytes(), original)
            store.rebase_fingerprint()
            store.process_names = lambda: ["Lexicon"]
            crate.write_bytes(_crate(["lexicon-again.mp3"]))
            named = store.poll()
            assert named is not None
            self.assertEqual(named["source"], "Lexicon")
            bad = {
                "format": 1,
                "id": "badpath0001",
                "created": "2026-10-28T00:00:00.000000Z",
                "trigger": "manual",
                "reason": "Tampered.",
                "source": None,
                "serato_version": "unknown",
                "serato_build": "unknown",
                "database": {"master": None, "root": None},
                "drives": [{
                    "drive_id": "tour",
                    "label": "Tour",
                    "role": "external",
                    "present": True,
                    "files": [{"path": "Lexicon/backup.zip", "sha256": "ab" * 32, "size": 1}],
                }],
                "tracks": [],
            }
            store._write_manifest(bad)
            with self.assertRaises(snapshots.SnapshotError):
                store.restore("badpath0001")
            self.assertEqual(secret.read_bytes(), b"lexicon-zip")
            self.assertFalse((serato / "Lexicon" / "from-restore.zip").exists())
            self.assertEqual(kept.read_bytes(), b"sibling")
            del music

    def test_unknown_version_blocks_on_darwin_and_win32(self) -> None:
        """Block writes when Darwin or Windows cannot read a Serato version.

        Windows looks for Serato DJ Pro.exe under Program Files, not a
        relative app bundle. A missing install is version unknown.

        Returns:
            None. The test fails if an unknown version is allowed to write.
        """
        missing = Path("/no/such/serato-install")
        for platform in ("darwin", "win32"):
            install = snapshots.detect_install(
                platform,
                info_plist=missing / "Info.plist",
                program_files=missing,
                registry=lambda: None,
                exe_reader=lambda path: None,
            )
            self.assertEqual(install.version, "unknown")
            message = snapshots.write_block_message(install)
            assert message is not None
            self.assertIn("unknown", message.lower())
            self.assertIn("Writes and restores are off", message)
        with TempLibrary() as temp:
            program = temp.root / "Program Files"
            exe = program / "Serato" / "Serato DJ Pro" / "Serato DJ Pro.exe"
            exe.parent.mkdir(parents=True)
            exe.write_bytes(b"MZ")
            seen: list[Path] = []

            def reader(path: Path) -> tuple[str, str]:
                seen.append(path)
                return ("5.0.0", "5.0.0.1251")

            found = snapshots.detect_install(
                "win32",
                info_plist=Path("Serato DJ Pro.app/Contents/Info.plist"),
                program_files=program,
                registry=lambda: None,
                exe_reader=reader,
            )
            self.assertEqual(found.version, "5.0.0")
            self.assertEqual(found.build, "5.0.0.1251")
            self.assertEqual(seen, [exe])
            self.assertTrue(snapshots.write_block_message(found))

    def test_process_list_failure_blocks_restore_and_is_rechecked(self) -> None:
        """Treat a lister error or timeout as Serato still running.

        The check runs again after the pre-restore snapshot and before any
        library file is replaced. It is not cached.

        Returns:
            None. The test fails if the crate changes.
        """
        def fail_listing(command: list[str]) -> str:
            raise OSError("ps failed")

        def time_out(command: list[str]) -> str:
            raise subprocess.TimeoutExpired(command, 2)

        self.assertTrue(snapshots.serato_dj_running(fail_listing))
        self.assertTrue(snapshots.serato_dj_running(time_out))
        with TempLibrary() as temp:
            _music, serato, store = _drive(temp.root, temp.db)
            crate = serato / "Subcrates" / "House.crate"
            crate.parent.mkdir(parents=True)
            original = _crate(["track.mp3"])
            crate.write_bytes(original)
            saved = store.take("manual", "Before Serato starts.")
            crate.write_bytes(_crate(["changed.mp3"]))
            calls = {"n": 0}

            def running() -> bool:
                calls["n"] += 1
                return calls["n"] >= 2

            store.serato_running = running
            with self.assertRaises(SnapshotBlocked) as caught:
                store.restore(saved["id"])
            self.assertIn("Quit Serato", caught.exception.message)
            self.assertGreaterEqual(calls["n"], 2)
            self.assertEqual(crate.read_bytes(), _crate(["changed.mp3"]))

    def test_restore_removes_sqlite_journal_wal_and_shm(self) -> None:
        """Drop SQLite sidecars before and after the database file is replaced.

        Returns:
            None. The test fails if a journal, WAL, or SHM file remains.
        """
        with TempLibrary() as temp:
            _music, _serato, store = _drive(temp.root, temp.db)
            saved = store.take("manual", "Database only.")
            data = temp.db.read_bytes()
            journal = temp.db.parent / "master.sqlite-journal"
            wal = temp.db.parent / "master.sqlite-wal"
            shm = temp.db.parent / "master.sqlite-shm"
            journal.write_bytes(b"journal")
            wal.write_bytes(b"wal")
            shm.write_bytes(b"shm")
            snapshots._replace_database(temp.db, data, temp.db.parent)
            self.assertEqual(temp.db.read_bytes(), data)
            self.assertFalse(journal.exists())
            self.assertFalse(wal.exists())
            self.assertFalse(shm.exists())
            self.assertTrue(completeness.is_complete(store._snapshot_dir(saved["id"])))

    def test_lexicon_case_is_left_untouched_by_restore(self) -> None:
        """Leave ``LEXICON`` files unchanged when a snapshot is restored.

        Returns:
            None. The test fails if the changed database or the new file is
            reverted or deleted.
        """
        with TempLibrary() as temp:
            _music, serato, store = _drive(temp.root, temp.db)
            folder = serato / "LEXICON"
            folder.mkdir()
            old = folder / "old.db"
            old.write_bytes(b"original")
            saved = store.take("manual", "Before the Lexicon folder changed.")
            old.write_bytes(b"changed")
            new = folder / "new.db"
            new.write_bytes(b"added")
            store.restore(saved["id"])
            self.assertEqual(old.read_bytes(), b"changed")
            self.assertEqual(new.read_bytes(), b"added")
            manifest = store._manifest(saved["id"])
            stored = [
                item["path"]
                for drive in manifest["drives"]
                if isinstance(drive, dict)
                for item in drive.get("files", [])
                if isinstance(item, dict)
            ]
            self.assertFalse(any("lexicon" in str(path).casefold() for path in stored))

    def test_incomplete_snapshot_is_skipped(self) -> None:
        """Skip a snapshot that has no COMPLETE marker.

        Returns:
            None. The test fails if a partial directory is listed or restored.
        """
        with TempLibrary() as temp:
            _music, _serato, store = _drive(temp.root, temp.db)
            saved = store.take("manual", "Finished.")
            self.assertTrue(completeness.is_complete(store._snapshot_dir(saved["id"])))
            partial = store.manifests / "partial-one.partial"
            partial.mkdir(parents=True)
            (partial / "manifest.json").write_text("{}", encoding="utf-8")
            self.assertFalse(completeness.is_complete(partial))
            self.assertNotIn("partial-one.partial", [item["id"] for item in store.list_snapshots()])
            self.assertIn("deleted", store.plan(saved["id"]))

    def test_page_reads_the_restore_plan_fields(self) -> None:
        """Keep the Snapshots page on the dry-run fields the server returns.

        Returns:
            None. The test fails if the page stops reading a plan field.
        """
        page = Path("static/app.js").read_text(encoding="utf-8")
        markup = Path("static/index.html").read_text(encoding="utf-8")
        self.assertIn('data-view="snapshots"', markup)
        for field in ("plan.crates", "plan.tracks", "plan.cues", "plan.grids", "plan.dry_run", "plan.restore_blocked", "plan.deleted"):
            self.assertIn(field, page)

    def test_reader_protocol_returns_crates_cues_grids_and_tags(self) -> None:
        """Expose list and load for a later gig check.

        Returns:
            None. The test fails if a required field is missing.
        """
        with TempLibrary() as temp:
            music, serato, store = _drive(temp.root, temp.db)
            _audio_file(music / "track.mp3")
            (serato / "Subcrates").mkdir(parents=True)
            (serato / "Subcrates" / "House.crate").write_bytes(_crate(["track.mp3"]))
            reader: snapshots.SnapshotReader = store
            saved = store.take("manual", "For the reader.")
            listed = reader.list_snapshots()
            self.assertEqual(listed[0]["id"], saved["id"])
            loaded = reader.load(saved["id"])
            self.assertIn("crates", loaded)
            self.assertIn("cues", loaded)
            self.assertIn("grids", loaded)
            self.assertIn("tags", loaded)
            self.assertTrue(loaded["crates"])
            self.assertTrue(loaded["cues"])
            self.assertTrue(loaded["grids"])
            self.assertTrue(loaded["tags"])

    def _flip_frames(self, path: Path, frames: dict[str, bytes]) -> None:
        """Flip the last byte of each stored frame.

        Args:
            path: Audio file.
            frames: Original frames.
        """
        path.write_bytes(self._flipped(path.read_bytes(), frames))

    def _flipped(self, raw: bytes, frames: dict[str, bytes]) -> bytes:
        """Return file bytes with each frame's last byte flipped.

        Args:
            raw: Original file.
            frames: Frames to locate.

        Returns:
            The corrupted file.
        """
        data = bytearray(raw)
        for blob in frames.values():
            index = data.find(blob)
            self.assertGreaterEqual(index, 0)
            data[index + len(blob) - 1] ^= 0xFF
        return bytes(data)


def _drive(root: Path, master: Path) -> tuple[Path, Path, SnapshotStore]:
    """Create one external ``_Serato_`` drive beside a library.

    Args:
        root: Temporary directory.
        master: ``master.sqlite``.

    Returns:
        Music root, ``_Serato_`` directory, and a quiet snapshot store.
    """
    music = root / "music"
    serato = music / "_Serato_"
    serato.mkdir(parents=True)
    store = _quiet(SnapshotStore(master, [DriveSpec(
        drive_id="tour",
        label="Tour",
        serato_root=serato,
        music_root=music,
        role="external",
        present=True,
    )]))
    return music, serato, store


def _flac_stored(frames: dict[str, bytes]) -> dict[str, bytes]:
    """Return the base64 comment values a FLAC file stores.

    Args:
        frames: ID3 frames from the MP3 fixture. Only the payloads are encoded.

    Returns:
        Kind to the exact comment value.
    """
    stored = {}
    for kind, blob in frames.items():
        payload = snapshot_frames.payload_from_stored(blob)
        stored[kind] = base64.b64encode(payload)
    return stored


def _flac_file(frames: dict[str, bytes], audio: bytes) -> bytes:
    """Build a FLAC file with Serato comments and an audio tail.

    Args:
        frames: ID3 frames whose payloads are stored as base64 comments.
        audio: Bytes written after the last metadata block.

    Returns:
        The FLAC file.
    """
    comments = []
    keys = {
        "Markers2": b"SERATO_MARKERS_V2",
        "BeatGrid": b"SERATO_BEATGRID",
        "Autotags": b"SERATO_AUTOTAGS",
    }
    for kind, key in keys.items():
        comments.append(key + b"=" + _flac_stored(frames)[kind])
    vendor = b"test"
    payload = len(vendor).to_bytes(4, "little") + vendor
    payload += len(comments).to_bytes(4, "little")
    for entry in comments:
        payload += len(entry).to_bytes(4, "little") + entry
    stream = b"\x00" * 34
    out = bytearray(b"fLaC")
    out.append(0)
    out += len(stream).to_bytes(3, "big")
    out += stream
    out.append(0x80 | 4)
    out += len(payload).to_bytes(3, "big")
    out += payload
    out += audio
    return bytes(out)


def _aiff_file(id3: bytes, audio: bytes) -> bytes:
    """Build an AIFF file with an ID3 chunk and an SSND chunk.

    Args:
        id3: Complete ID3 tag. Its audio suffix is ignored; pass a tag only.
        audio: Sample bytes stored after the SSND header.

    Returns:
        The AIFF file.
    """
    # The helper's ID3 builder appends audio when given some. Callers pass
    # the tag produced with empty audio.
    def chunk(tag: bytes, data: bytes) -> bytes:
        pad = b"\x00" if len(data) % 2 else b""
        return tag + len(data).to_bytes(4, "big") + data + pad

    ssnd = b"\x00" * 8 + audio
    body = b"AIFF" + chunk(b"COMM", b"\x00" * 18) + chunk(b"SSND", ssnd) + chunk(b"ID3 ", id3)
    return b"FORM" + len(body).to_bytes(4, "big") + body


def _m4a_file(audio: bytes) -> bytes:
    """Build an M4A file with Serato freeform atoms and an mdat atom.

    Args:
        audio: ``mdat`` body.

    Returns:
        The M4A file.
    """
    def atom(tag: bytes, body: bytes) -> bytes:
        return (8 + len(body)).to_bytes(4, "big") + tag + body

    def freeform(name: str, payload: bytes) -> bytes:
        mean = atom(b"mean", b"\x00\x00\x00\x00" + b"com.serato.dj")
        title = atom(b"name", b"\x00\x00\x00\x00" + name.encode("ascii"))
        data = atom(b"data", b"\x00" * 8 + payload)
        return atom(b"----", mean + title + data)

    ilst = atom(b"ilst", freeform("markersv2", _markers()) + freeform("beatgrid", _grid()) + freeform("autotags", _autotags()))
    meta = atom(b"meta", b"\x00\x00\x00\x00" + ilst)
    moov = atom(b"moov", atom(b"udta", meta))
    return atom(b"ftyp", b"M4A ") + moov + atom(b"mdat", audio)
