"""Content-addressed snapshots of a Serato library.

A snapshot stores the master database, each drive's ``_Serato_`` crates and
``database V2``, and the Serato frames inside audio files (Markers2, BeatGrid,
Autotags). Blob names are the SHA-256 of their bytes, and every read checks
that hash. Nothing in the store is deleted because of age.

``Export Backups`` and ``Lexicon`` inside ``_Serato_`` are never listed,
read, snapshotted, or restored. Lexicon keeps its own zip files there.
A change Lexicon makes to the Serato files outside that folder is an outside
change: the snapshot is taken after the write, the log names Lexicon when
that can be inferred, and undo restores the previous snapshot.

Serato 5 writes and restores stay off. Protect Library is the plist key
``library_protect`` (1 on, 0 off). A missing or unreadable value is unknown.
Lucid and Flexible beatgrid storage has no confirmed layout, so it is not
parsed or written. Snapshots stay available. A restore also refuses while a
Serato DJ process is running.

Restoring writes a snapshot first, so the restore itself can be undone.
``plan`` reports crate, track, cue, and grid differences and writes nothing.
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import os
import plistlib
import re
import secrets
import sqlite3
import struct
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, TypedDict

import app_log
import completeness
import snapshot_frames

FORMAT = 1
EXCLUDED_DIRS = frozenset({"Export Backups", "Lexicon"})
_EXCLUDED_FOLDED = frozenset(name.casefold() for name in EXCLUDED_DIRS)
FRAME_KINDS = snapshot_frames.FRAME_KINDS
TRIGGERS = frozenset({
    "manual",
    "before-write",
    "before-restore",
    "external-change",
    "version-change",
})
AUDIO_SUFFIXES = {".mp3", ".flac", ".m4a", ".aiff", ".aif"}
# Serato 5 Lucid and Flexible beatgrids have no confirmed on-disk format.
# Leave this false until a format is verified. Do not invent a layout.
LUCID_BEATGRID_VERIFIED = False
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,200}$")
_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
_VERSION_RE = re.compile(r"^[0-9]+(?:\.[0-9]+)*$")
_JOURNAL_NAME = "restore-journal.json"
_KEY_NAME = "manifest.key"
_MAX_FILE = 512 * 1024 * 1024
_LEXICON_WINDOW = 3.0

SERATO_RUNNING_MESSAGE = (
    "Quit Serato DJ Pro before restoring. Serato DJ is still running, "
    "so nothing was restored."
)

_stores: dict[str, SnapshotStore] = {}
_watch: FolderWatch | None = None


class SnapshotError(Exception):
    """Raised when a snapshot cannot be saved or read.

    Attributes:
        message: Text safe to show. It does not include a file path.
        status: HTTP status for the failure.
    """

    def __init__(self, message: str, status: int = 400):
        """Store the message and status.

        Args:
            message: Text safe to show.
            status: HTTP status. Defaults to 400.
        """
        super().__init__(message)
        self.message = message
        self.status = status


class SnapshotBlocked(SnapshotError):
    """Raised when a restore or write is refused before anything changes."""

    def __init__(self, message: str):
        """Store a refusal that must not be retried with a force flag.

        Args:
            message: The reason the operation was refused.
        """
        super().__init__(message, 409)


class SnapshotInfo(TypedDict):
    """One row in the snapshot list."""

    id: str
    created: str
    trigger: str
    reason: str
    source: str | None
    serato_version: str
    serato_build: str
    unavailable_drives: list[str]
    integrity: str


class CrateView(TypedDict):
    """One crate, or the track list from database V2."""

    drive_id: str
    drive_label: str
    present: bool
    name: str
    path: str
    source: str
    tracks: list[str]


class CueTrackView(TypedDict):
    """Parsed Markers2 data for one audio file."""

    path: str
    drive_id: str
    present: bool
    sha256: str
    cues: list[dict[str, object]]
    loops: list[dict[str, object]]
    flips: list[dict[str, object]]


class GridTrackView(TypedDict):
    """Parsed BeatGrid data for one audio file."""

    path: str
    drive_id: str
    present: bool
    sha256: str
    markers: list[dict[str, object]]


class TagView(TypedDict):
    """One Autotags frame. The bytes are not parsed into a guessed layout."""

    path: str
    drive_id: str
    present: bool
    kind: str
    sha256: str
    size: int


class SnapshotContents(TypedDict):
    """What ``SnapshotReader.load`` returns for one snapshot."""

    info: SnapshotInfo
    crates: list[CrateView]
    cues: list[CueTrackView]
    grids: list[GridTrackView]
    tags: list[TagView]


class SnapshotReader(Protocol):
    """Read-only snapshot access for a later gig check.

    ``list_snapshots`` returns the newest snapshot first. ``load`` returns
    crates, cues, grids, and autotags. Neither method writes.
    """

    def list_snapshots(self) -> Sequence[SnapshotInfo]:
        """Return stored snapshots, newest first."""

    def load(self, snapshot_id: str) -> SnapshotContents:
        """Return crates, cues, grids, and tags for one snapshot.

        Args:
            snapshot_id: Id from ``list_snapshots``.
        """


@dataclass(frozen=True)
class DriveSpec:
    """One drive the snapshot should cover.

    ``serato_root`` is the ``_Serato_`` directory. ``music_root`` is the
    folder whose tracks that database points at. A missing drive has
    ``present`` false and both roots None.
    """

    drive_id: str
    label: str
    serato_root: Path | None
    music_root: Path | None
    role: str = "external"
    present: bool = True


@dataclass(frozen=True)
class SeratoInstall:
    """Version, build, and Protect Library as read from this machine."""

    version: str
    build: str
    protect: str


def read_install() -> SeratoInstall:
    """Read the Serato app version and Protect Library.

    A relocated test library does not read the machine's real app or
    preferences unless ``SERATO_LIBRARY_APP_INFO`` or
    ``SERATO_LIBRARY_PREFERENCES`` is set. An unreadable file becomes
    ``unknown`` and does not raise.

    Returns:
        Version, build, and ``on``, ``off``, or ``unknown``.
    """
    version, build = _read_version()
    protect = _read_protect() if _is_serato_5(version) else "unknown"
    return SeratoInstall(version, build, protect)


def write_block_message(install: SeratoInstall | None = None) -> str | None:
    """Return why a library cannot be written or restored.

    An unknown version blocks. So does an unreadable version plist, because
    that is stored as unknown. Serato 5 also blocks when Protect Library is
    on, off, or unknown, until Lucid and Flexible beatgrid storage is verified.

    Args:
        install: Version to judge. None reads the install on this machine.

    Returns:
        The refusal, or None when a known Serato older than 5 may be written.
    """
    chosen = install if install is not None else read_install()
    parsed = _parsed_version(chosen.version)
    if parsed is None:
        return (
            f"Serato version is unknown (build {chosen.build}). "
            "Writes and restores are off until the installed Serato version can be read. "
            "A value that is not a dotted number, including an unreadable plist, is unknown. "
            "Snapshots can still be taken and read."
        )
    install = chosen
    if parsed[0] < 5:
        return None
    if install.protect == "off" and LUCID_BEATGRID_VERIFIED:
        return None
    if install.protect == "on":
        protect = "Protect Library is on (library_protect is 1)."
    elif install.protect == "off":
        protect = "Protect Library is off."
    else:
        protect = "Protect Library is unknown because library_protect could not be read."
    return (
        f"Serato {install.version} (build {install.build}): writes and restores are off. "
        f"{protect} "
        "Lucid and Flexible beatgrid storage is not verified, so this library stays read-only. "
        "Snapshots can still be taken and read."
    )


def detection_command(platform: str) -> list[str]:
    """Return the process-list command for an operating system.

    Args:
        platform: A ``sys.platform`` value.

    Returns:
        ``tasklist`` on Windows and ``ps`` on macOS and other systems.
    """
    if platform == "win32":
        return ["tasklist", "/FO", "CSV", "/NH"]
    return ["ps", "-ax", "-o", "comm="]


def serato_dj_running(runner: Callable[[list[str]], str] | None = None) -> bool:
    """Return whether a Serato DJ process is running.

    macOS uses ``ps``. Windows uses ``tasklist``. The command name must
    contain both ``serato`` and ``dj``. This process and a path that only
    contains ``serato-library`` do not count. A command failure or a timeout
    is treated as running, so a restore stops. The result is not cached.

    Args:
        runner: Replacement for the process command. Tests pass one.

    Returns:
        True when Serato DJ is running, or when the process list could not
        be read.
    """
    command = detection_command(sys.platform)
    try:
        text = runner(command) if runner is not None else _run(command)
    except (OSError, subprocess.TimeoutExpired):
        return True
    if sys.platform == "win32":
        return _serato_in_tasklist(text)
    return _serato_in_ps(text)


def _serato_in_ps(text: str) -> bool:
    """Return whether ``ps`` output names Serato DJ.

    Args:
        text: ``ps -ax -o comm=`` output.

    Returns:
        True when a command basename is Serato DJ.
    """
    return any(_is_serato_dj_name(line) for line in text.splitlines())


def _serato_in_tasklist(text: str) -> bool:
    """Return whether ``tasklist`` output names Serato DJ.

    Args:
        text: ``tasklist /FO CSV /NH`` output.

    Returns:
        True when an image name is Serato DJ.
    """
    for row in csv.reader(io.StringIO(text)):
        if row and _is_serato_dj_name(row[0]):
            return True
    return False


def _is_serato_dj_name(command: str) -> bool:
    """Return whether a process command is Serato DJ.

    Args:
        command: A process command or image name.

    Returns:
        True when the base name contains ``serato`` and ``dj`` and is not
        this library app.
    """
    name = Path(command.strip()).name.lower()
    if "serato-library" in name or "serato_library" in name:
        return False
    return "serato" in name and "dj" in name


def parse_serato_bytes(data: bytes) -> list[str]:
    """Return track paths from a database V2 file or a crate file.

    Both files are a run of four-byte tags, a big-endian length, and that
    many bytes. ``otrk`` holds a ``ptrk`` path encoded as UTF-16-BE. Serato
    5.0 still writes this ``database V2`` layout.

    Args:
        data: File bytes.

    Returns:
        Track paths in file order. A short or unfamiliar file returns the
        paths it could parse.
    """
    tracks: list[str] = []
    for tag, body in _chunks(data):
        if tag == "ptrk":
            text = _utf16be(body)
            if text:
                tracks.append(text)
        elif tag == "otrk":
            for inner, payload in _chunks(body):
                if inner == "ptrk":
                    text = _utf16be(payload)
                    if text:
                        tracks.append(text)
    return tracks


def current_store() -> SnapshotStore:
    """Return the snapshot store for the library this process has open.

    Returns:
        A store next to ``library.MASTER``. One store is kept per path.
    """
    import library

    master = Path(library.MASTER).resolve()
    key = str(master)
    store = _stores.get(key)
    if store is None:
        store = SnapshotStore(master)
        _stores[key] = store
    return store


def snapshot_before_write() -> None:
    """Save a snapshot before a library write.

    Raises:
        LibraryError: If the snapshot cannot be saved. Nothing in the
            library has been written yet.
    """
    import library

    try:
        current_store().take("before-write", "Before a library write.")
    except SnapshotError as exc:
        raise library.LibraryError(exc.message, exc.status) from exc


@contextmanager
def own_writes() -> Iterator[SnapshotStore]:
    """Mark library changes as ours so the watcher does not treat them as outside.

    Yields:
        The current snapshot store. The watch fingerprint is refreshed when
        the outermost block ends.
    """
    store = current_store()
    store._depth += 1
    try:
        yield store
    finally:
        store._depth -= 1
        if store._depth == 0:
            try:
                store.rebase_fingerprint()
            except OSError:
                app_log.logger.exception("Snapshot watch could not refresh.")


class SnapshotStore:
    """Save, list, plan, and restore hash-checked snapshots for one library."""

    def __init__(self, master: Path, drives: Sequence[DriveSpec] | None = None):
        """Open the store beside a master database.

        Args:
            master: ``master.sqlite`` for this library.
            drives: Drives to snapshot. None discovers them, and a relocated
                library discovers none unless this list is passed.
        """
        self.master = Path(master)
        self.drives = None if drives is None else list(drives)
        self.root = self.master.resolve().parent / "Backups" / "snapshots"
        self.objects = self.root / "objects"
        self.manifests = self.root / "manifests"
        self.serato_running = serato_dj_running
        self.process_names: Callable[[], Sequence[str]] = default_process_names
        self._depth = 0
        self._recover_if_journal()

    def list_snapshots(self) -> list[SnapshotInfo]:
        """Return snapshots, newest first.

        Returns:
            Summary rows. A manifest that is not JSON is skipped.
        """
        rows: list[SnapshotInfo] = []
        if not self.manifests.is_dir():
            return rows
        for path in self.manifests.iterdir():
            if not completeness.is_complete(path):
                continue
            try:
                manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, UnicodeError):
                continue
            if isinstance(manifest, dict) and isinstance(manifest.get("id"), str) and _body_digest_matches(manifest, self._manifest_key()):
                rows.append(_info(manifest))
        rows.sort(key=lambda item: item["created"], reverse=True)
        return rows

    def load(self, snapshot_id: str) -> SnapshotContents:
        """Return crates, cues, grids, and autotags for one snapshot.

        Args:
            snapshot_id: Id from ``list_snapshots``.

        Returns:
            The parsed snapshot. Hashes are checked before parsing.

        Raises:
            SnapshotError: If the id, a path, or a blob hash is not valid.
        """
        manifest = self._manifest(snapshot_id)
        self._verify(manifest)
        return _contents(manifest, self._read_blob)

    def take(self, trigger: str, reason: str, source: str | None = None) -> SnapshotInfo:
        """Save a snapshot of the database, crates, and Serato frames.

        Args:
            trigger: Why this snapshot is being saved.
            reason: A short sentence stored with it.
            source: ``Lexicon`` when an outside change was inferred, else None.

        Returns:
            The summary row. Version and build are ``unknown`` when the app
            bundle cannot be read.

        Raises:
            SnapshotError: If the trigger is unknown or a blob fails its hash.
        """
        if trigger not in TRIGGERS:
            raise SnapshotError("That snapshot trigger is not valid.")
        install = read_install()
        previous = self._latest_manifest()
        drive_records = self._capture_drives(previous)
        track_records = self._capture_tracks(previous, drive_records)
        database = self._capture_database()
        manifest = {
            "format": FORMAT,
            "id": _new_id(),
            "created": _now(),
            "trigger": trigger,
            "reason": reason[:500],
            "source": source,
            "serato_version": install.version,
            "serato_build": install.build,
            "database": database,
            "drives": drive_records,
            "tracks": track_records,
        }
        self._verify(manifest)
        self._write_manifest(manifest)
        if not completeness.is_complete(self._snapshot_dir(str(manifest["id"]))):
            raise SnapshotError("The snapshot was not finished.")
        self._remember_version(install)
        return _info(manifest)

    def plan(self, snapshot_id: str) -> dict[str, object]:
        """Describe a restore and change nothing.

        Args:
            snapshot_id: Snapshot to compare with the library as it is now.

        Returns:
            Crate, track, cue, and grid differences. ``dry_run`` is true.
            ``restore_blocked`` is the refusal text when a real restore
            would be refused, and None when it would be allowed.

        Raises:
            SnapshotError: If the snapshot cannot be read. Nothing is written.
        """
        diff = self._diff(snapshot_id)
        blocked = None
        if self.serato_running():
            blocked = SERATO_RUNNING_MESSAGE
        else:
            message = write_block_message()
            if message:
                blocked = message
            else:
                status = _library_status()
                if status.get("open"):
                    blocked = str(status.get("message") or SERATO_RUNNING_MESSAGE)
        diff["dry_run"] = True
        diff["changed"] = False
        diff["restore_blocked"] = blocked
        return diff

    def _refuse_restore(self) -> None:
        """Refuse a restore before any library file is changed.

        Raises:
            SnapshotBlocked: If Serato DJ is running, the version gate
                refuses the library, or Serato holds the database.
        """
        if self.serato_running():
            raise SnapshotBlocked(SERATO_RUNNING_MESSAGE)
        message = write_block_message()
        if message:
            raise SnapshotBlocked(message)
        status = _library_status()
        if status.get("open"):
            raise SnapshotBlocked(str(status.get("message") or SERATO_RUNNING_MESSAGE))

    def _refuse_if_running(self) -> None:
        """Refuse before the next restore phase when Serato DJ is running.

        Raises:
            SnapshotBlocked: If the process check says Serato DJ is running,
                or if that check errors or times out.
        """
        if self.serato_running():
            raise SnapshotBlocked(SERATO_RUNNING_MESSAGE)

    def _write_restore_journal(self, target_id: str, undo_id: str) -> None:
        """Record the pre-restore snapshot before the first file is replaced.

        Args:
            target_id: Snapshot that is about to be restored.
            undo_id: Snapshot that puts the library back.

        Raises:
            SnapshotError: If the journal cannot be written inside the store.
        """
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / _JOURNAL_NAME
        if path.is_symlink() or not _contained(path, self.root):
            raise SnapshotError("The restore journal is not inside the snapshot store.")
        payload = json.dumps(
            {"version": 1, "target": target_id, "undo": undo_id},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        _atomic_write(path, payload)

    def _clear_restore_journal(self) -> None:
        """Remove the restore journal after a finished restore or rollback.

        Raises:
            SnapshotError: If the journal is a shortcut or leaves the store.
        """
        path = self.root / _JOURNAL_NAME
        if not path.exists() and not path.is_symlink():
            return
        if path.is_symlink() or not _contained(path, self.root):
            raise SnapshotError("The restore journal is not inside the snapshot store.")
        path.unlink()

    def _rollback_restore(self, undo_id: str, exc: BaseException) -> None:
        """Put the pre-restore snapshot back, then raise.

        Serato DJ is checked again before any file is replaced. A
        ``KeyboardInterrupt`` or ``SystemExit`` is raised again after the
        library is put back.

        Args:
            undo_id: Snapshot saved before the restore.
            exc: Failure from the restore that was in progress.

        Raises:
            SnapshotBlocked: If Serato DJ is running. The journal stays.
            SnapshotError: If the library was put back, or if that also failed.
            KeyboardInterrupt: After a successful rollback, when that was the
                original failure.
            SystemExit: After a successful rollback, when that was the
                original failure.
        """
        if self.serato_running():
            raise SnapshotBlocked(SERATO_RUNNING_MESSAGE) from exc
        try:
            self._apply(undo_id)
        except BaseException as rollback:
            raise SnapshotError(
                f"Restore failed and snapshot {undo_id} could not be put back either."
            ) from rollback
        self._clear_restore_journal()
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise exc
        raise SnapshotError(
            f"Restore failed. The library was put back using snapshot {undo_id}."
        ) from exc

    def recover_interrupted_restore(self) -> bool:
        """Roll an unfinished restore back to the snapshot from before it.

        Returns:
            True when a journal was found and the pre-restore snapshot was
            applied. False when there is no journal.

        Raises:
            SnapshotBlocked: If Serato DJ is running. The journal stays.
            SnapshotError: If the journal or the pre-restore snapshot is not
                valid. The journal stays.
        """
        path = self.root / _JOURNAL_NAME
        if path.is_symlink() or not _contained(path, self.root):
            raise SnapshotError("The restore journal is not inside the snapshot store.")
        if not path.is_file():
            return False
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise SnapshotError("The restore journal could not be read.") from exc
        undo = payload.get("undo") if isinstance(payload, dict) else None
        if not isinstance(undo, str):
            raise SnapshotError("The restore journal is not valid.")
        self._refuse_if_running()
        if not completeness.is_complete(self._snapshot_dir(undo)):
            raise SnapshotError("The pre-restore snapshot is incomplete.")
        self._verify(self._manifest(undo))
        self._apply(undo)
        self._clear_restore_journal()
        self.rebase_fingerprint()
        return True

    def _recover_if_journal(self) -> None:
        """Roll back an unfinished restore when this store is opened.

        A missing journal does nothing. A failure is logged and the journal
        is left in place so the next open can try again.
        """
        path = self.root / _JOURNAL_NAME
        try:
            if not path.is_file() or path.is_symlink():
                return
        except OSError:
            return
        try:
            self.recover_interrupted_restore()
        except SnapshotBlocked:
            app_log.logger.warning("An unfinished restore is waiting until Serato DJ quits.")
        except (OSError, SnapshotError, snapshot_frames.FrameRewriteError):
            app_log.logger.exception("An unfinished restore could not be rolled back.")

    def _manifest_key(self) -> bytes:
        """Return the key that signs manifest hashes for this library.

        The key is 32 random bytes in ``manifest.key`` beside the snapshot
        store, not inside a snapshot directory. Replacing a manifest without
        this key fails the check. Replacing the key file as well can still
        produce a matching hash; the file mode is ``0o600``.

        Returns:
            The key bytes.

        Raises:
            SnapshotError: If the key is missing, the wrong length, or not
                inside the store.
        """
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / _KEY_NAME
        if path.is_symlink() or not _contained(path, self.root):
            raise SnapshotError("The manifest key is not inside the snapshot store.")
        if path.is_file():
            key = path.read_bytes()
            if len(key) != 32:
                raise SnapshotError("The manifest key is not valid.")
            return key
        key = secrets.token_bytes(32)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            key = path.read_bytes()
            if len(key) != 32:
                raise SnapshotError("The manifest key is not valid.")
            return key
        try:
            os.write(fd, key)
            os.fsync(fd)
        finally:
            os.close(fd)
        return key

    def restore(self, snapshot_id: str) -> dict[str, object]:
        """Restore one snapshot after saving the current library.

        Args:
            snapshot_id: Snapshot to put back.

        Returns:
            The id that was restored and the snapshot that can undo it.

        Raises:
            SnapshotBlocked: If Serato DJ is running, the Serato 5 gate
                refuses the library, or Serato holds the database. Nothing
                is changed, and no snapshot is saved.
            SnapshotError: If a hash or a path is not valid. A failure after
                the pre-restore snapshot tries to put that snapshot back.
        """
        self._refuse_restore()
        if not completeness.is_complete(self._snapshot_dir(snapshot_id)):
            raise SnapshotError("That snapshot is incomplete.", 404)
        diff = self._diff(snapshot_id)
        pre = self.take("before-restore", f"Before restoring snapshot {snapshot_id}.")
        pre_dir = self._snapshot_dir(pre["id"])
        if not completeness.is_complete(pre_dir):
            raise SnapshotError("The pre-restore snapshot is incomplete. Nothing was restored.")
        self._verify(self._manifest(pre["id"]))
        if self.serato_running():
            raise SnapshotBlocked(SERATO_RUNNING_MESSAGE)
        self._write_restore_journal(snapshot_id, pre["id"])
        try:
            self._apply(snapshot_id)
        except BaseException as exc:
            self._rollback_restore(pre["id"], exc)
        self._clear_restore_journal()
        self.rebase_fingerprint()
        return {
            "ok": True,
            "dry_run": False,
            "restored": snapshot_id,
            "undo_snapshot": pre["id"],
            "changes": diff,
        }

    def undo_outside(self) -> dict[str, object]:
        """Restore the snapshot from before the last outside change.

        Returns:
            The restore result.

        Raises:
            SnapshotError: If there is no outside change waiting.
            SnapshotBlocked: If the restore is refused. Nothing is changed.
        """
        pending = self.pending_undo()
        if pending is None:
            raise SnapshotError("There is no outside change to undo.")
        result = self.restore(str(pending["restore_id"]))
        state = self._load_state()
        state["pending_undo"] = None
        state["fingerprint"] = self.fingerprint()
        self._save_state(state)
        return result

    def pending_undo(self) -> dict[str, object] | None:
        """Return the outside change that can be undone, if there is one.

        Returns:
            The after-snapshot id, the snapshot undo would restore, and the
            source when it was inferred. None when nothing is waiting.
        """
        pending = self._load_state().get("pending_undo")
        if not isinstance(pending, dict) or not pending.get("restore_id"):
            return None
        return pending

    def check_version(self) -> SnapshotInfo | None:
        """Snapshot when the Serato version or build changes.

        The first time a version is seen, it is recorded and no snapshot is
        taken. A later change snapshots the library as it is now. That is
        not a copy from before Serato wrote.

        Returns:
            The new snapshot, or None when the version and build are unchanged.
        """
        install = read_install()
        state = self._load_state()
        seen_version = state.get("observed_version")
        seen_build = state.get("observed_build")
        if not isinstance(seen_version, str) or not isinstance(seen_build, str):
            state["observed_version"] = install.version
            state["observed_build"] = install.build
            self._save_state(state)
            return None
        if seen_version == install.version and seen_build == install.build:
            return None
        reason = (
            f"Serato changed from {seen_version} (build {seen_build}) "
            f"to {install.version} (build {install.build}). "
            "This snapshot is the library as it is now."
        )
        return self.take("version-change", reason)

    def poll(self) -> dict[str, object] | None:
        """Snapshot after an outside change to the Serato files.

        Our own writes are ignored. A change inside ``Lexicon`` or
        ``Export Backups`` is not a library change, because those folders
        are not read. The snapshot is taken after the other write.

        Returns:
            The undo record, or None when nothing outside changed.
        """
        self.check_version()
        if self._depth:
            return None
        current = self.fingerprint()
        state = self._load_state()
        previous = state.get("fingerprint")
        if not isinstance(previous, str):
            state["fingerprint"] = current
            self._save_state(state)
            return None
        if previous == current:
            return None
        source = "Lexicon" if self._lexicon_inferred() else None
        previous_id = self._latest_id()
        if source == "Lexicon":
            reason = (
                "Lexicon changed the Serato folder. This snapshot was taken after that write. "
                "A snapshot from before the write is not available."
            )
        else:
            reason = (
                "The Serato folder changed outside this app. This snapshot was taken after that change. "
                "A snapshot from before the change is not available."
            )
        info = self.take("external-change", reason, source=source)
        state = self._load_state()
        state["fingerprint"] = self.fingerprint()
        state["pending_undo"] = {
            "snapshot_id": info["id"],
            "restore_id": previous_id,
            "source": source,
        }
        self._save_state(state)
        if source == "Lexicon":
            message = (
                f"Lexicon changed the Serato folder. Snapshot {info['id']} was saved after that write. "
                f"Undo restores snapshot {previous_id}. "
                "This snapshot is from after Lexicon wrote; a copy from before that write is not available."
            )
        else:
            message = (
                f"The Serato folder changed outside this app. Snapshot {info['id']} was saved after the change. "
                f"Undo restores snapshot {previous_id}. "
                "This snapshot is from after the change; a copy from before the outside write is not available."
            )
        app_log.logger.info("%s", message)
        for handler in app_log.logger.handlers:
            handler.flush()
        return state["pending_undo"]

    def rebase_fingerprint(self) -> None:
        """Remember the current Serato files as unchanged."""
        state = self._load_state()
        state["fingerprint"] = self.fingerprint()
        self._save_state(state)

    def fingerprint(self) -> str:
        """Hash the names, sizes, and times of the watched Serato files.

        Returns:
            A digest. ``Lexicon`` and ``Export Backups`` are not included.
            The snapshot store itself is not included.
        """
        rows: list[str] = []
        library_dir = self.master.resolve().parent
        for name in ("master.sqlite", "master.sqlite-wal", "master.sqlite-shm", "root.sqlite"):
            path = library_dir / name
            rows.append(_stat_row(path, name))
        for spec in self._drive_specs():
            if not spec.present or spec.serato_root is None:
                rows.append(f"absent\0{spec.drive_id}")
                continue
            for rel, path in _iter_serato_files(spec.serato_root):
                rows.append(_stat_row(path, f"{spec.drive_id}/{rel}"))
        rows.sort()
        return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()

    def _diff(self, snapshot_id: str) -> dict[str, object]:
        """Compare the live library with one snapshot.

        Args:
            snapshot_id: Snapshot to treat as the restore target.

        Returns:
            Crate, track, cue, and grid differences.

        Raises:
            SnapshotError: If the snapshot cannot be read.
        """
        target = self.load(snapshot_id)
        current = self._live_contents()
        visible = {spec.drive_id for spec in self._drive_specs()}
        absent = {spec.drive_id for spec in self._drive_specs() if not spec.present}
        for crate in target["crates"]:
            drive_id = crate["drive_id"]
            if drive_id != "library" and (drive_id not in visible or drive_id in absent):
                crate["present"] = False
        for rows in (target["cues"], target["grids"], target["tags"]):
            for row in rows:
                drive_id = row["drive_id"]
                if drive_id not in visible or drive_id in absent:
                    row["present"] = False
        return _diff_contents(current, target, snapshot_id)

    def _apply(self, snapshot_id: str) -> None:
        """Put one snapshot's files back.

        Args:
            snapshot_id: Snapshot whose hashes have been accepted.

        Raises:
            SnapshotError: If a path is not safe or a hash does not match.
            FrameRewriteError: If an audio file cannot be restored.
            OSError: If a file cannot be replaced.
        """
        manifest = self._manifest(snapshot_id)
        self._verify(manifest)
        self._refuse_if_running()
        self._apply_database(manifest)
        self._refuse_if_running()
        self._apply_drives(manifest)
        self._refuse_if_running()
        self._apply_tracks(manifest)

    def _apply_database(self, manifest: Mapping[str, object]) -> None:
        """Replace the master and root databases.

        Args:
            manifest: Verified snapshot.
        """
        database = manifest.get("database")
        if not isinstance(database, dict):
            return
        library_dir = self.master.resolve().parent
        master = database.get("master")
        if isinstance(master, dict) and isinstance(master.get("sha256"), str):
            _replace_database(library_dir / "master.sqlite", self._read_blob(master["sha256"]), library_dir)
        root = database.get("root")
        if isinstance(root, dict) and isinstance(root.get("sha256"), str):
            _replace_database(library_dir / "root.sqlite", self._read_blob(root["sha256"]), library_dir)

    def _apply_drives(self, manifest: Mapping[str, object]) -> None:
        """Replace crate files on drives that are present.

        Args:
            manifest: Verified snapshot.

        Raises:
            SnapshotError: If a relative path is excluded or escapes the drive.
        """
        for record in _drive_records(manifest):
            if not record.get("present"):
                continue
            root = _present_root(record, self._drive_specs())
            if root is None:
                continue
            wanted: set[str] = set()
            for item in record.get("files") or []:
                if not isinstance(item, dict):
                    continue
                rel = _safe_relative(str(item.get("path") or ""))
                digest = item.get("sha256")
                if not isinstance(digest, str):
                    raise SnapshotError("A snapshot file has no hash.")
                target = _join(root, rel)
                _atomic_write(target, self._read_blob(digest))
                wanted.add(rel)
            for rel, path in _iter_serato_files(root):
                if rel not in wanted:
                    if path.is_symlink():
                        raise SnapshotError("Refusing to remove a shortcut in the Serato folder.")
                    path.unlink()

    def _apply_tracks(self, manifest: Mapping[str, object]) -> None:
        """Restore Serato frames in audio files on present drives.

        Args:
            manifest: Verified snapshot.
        """
        specs = {spec.drive_id: spec for spec in self._drive_specs()}
        for track in _track_records(manifest):
            if not track.get("present"):
                continue
            spec = specs.get(str(track.get("drive_id")))
            if spec is None or not spec.present or spec.music_root is None:
                continue
            raw_path = track.get("path")
            if not isinstance(raw_path, str):
                continue
            path = Path(raw_path)
            if not _contained(path, spec.music_root) or path.is_symlink() or not path.is_file():
                continue
            frames = track.get("frames")
            if not isinstance(frames, dict):
                continue
            restored: dict[str, bytes] = {}
            for kind in FRAME_KINDS:
                digest = frames.get(kind)
                if isinstance(digest, str):
                    restored[kind] = self._read_blob(digest)
            snapshot_frames.restore_stored_frames(path, restored)

    def _capture_database(self) -> dict[str, object]:
        """Snapshot the master database and root database.

        Returns:
            Hash, size, and integrity for each file that exists.
        """
        result: dict[str, object] = {"master": _sqlite_blob(self, self.master), "root": None}
        root = self.master.resolve().parent / "root.sqlite"
        if root.is_file() and not root.is_symlink():
            result["root"] = _sqlite_blob(self, root)
        return result

    def _capture_drives(self, previous: Mapping[str, object] | None) -> list[dict[str, object]]:
        """Snapshot crate files, carrying absent drives forward.

        Args:
            previous: The newest manifest, or None.

        Returns:
            Drive records. An absent drive keeps its earlier files and is
            marked not present. Those crates are not recorded as removed.
        """
        previous_drives = {str(item.get("drive_id")): item for item in _drive_records(previous)}
        seen: set[str] = set()
        records: list[dict[str, object]] = []
        for spec in self._drive_specs():
            seen.add(spec.drive_id)
            if spec.present and spec.serato_root is not None and spec.serato_root.is_dir():
                files = []
                for rel, path in _iter_serato_files(spec.serato_root):
                    data = path.read_bytes()
                    files.append({"path": rel, "sha256": self._put_blob(data), "size": len(data)})
                records.append({
                    "drive_id": spec.drive_id,
                    "label": spec.label,
                    "role": spec.role,
                    "present": True,
                    "root": str(spec.serato_root),
                    "music_root": None if spec.music_root is None else str(spec.music_root),
                    "files": files,
                })
            else:
                records.append(_carry_drive(previous_drives.get(spec.drive_id), spec))
        for drive_id, old in previous_drives.items():
            if drive_id not in seen:
                records.append(_carry_drive(old, None))
        return records

    def _capture_tracks(
        self,
        previous: Mapping[str, object] | None,
        drives: Sequence[Mapping[str, object]],
    ) -> list[dict[str, object]]:
        """Snapshot Serato frames, carrying tracks on absent drives forward.

        Args:
            previous: The newest manifest, or None.
            drives: Drive records just captured.

        Returns:
            Track records. A track on an absent drive stays in the list
            with ``present`` false. It is not recorded as removed.
        """
        absent = {str(item.get("drive_id")) for item in drives if not item.get("present")}
        records: list[dict[str, object]] = []
        seen: set[str] = set()
        for spec in self._drive_specs():
            if not spec.present or spec.music_root is None:
                continue
            for path in _audio_paths(self.master, spec, drives):
                key = str(path)
                if key in seen:
                    continue
                seen.add(key)
                stored = snapshot_frames.read_stored_frames(path)
                frames: dict[str, str | None] = {}
                for kind in FRAME_KINDS:
                    blob = stored.get(kind)
                    frames[kind] = None if blob is None else self._put_blob(blob)
                records.append({
                    "path": key,
                    "drive_id": spec.drive_id,
                    "present": True,
                    "frames": frames,
                })
        for track in _track_records(previous):
            drive_id = str(track.get("drive_id") or "")
            path = track.get("path")
            if drive_id in absent and isinstance(path, str) and path not in seen:
                carried = dict(track)
                carried["present"] = False
                records.append(carried)
                seen.add(path)
        return records

    def _live_contents(self) -> SnapshotContents:
        """Read the library as it is now, without writing a snapshot.

        Returns:
            The same shape as ``load``, with an empty id.
        """
        drives = self._capture_drives_live()
        tracks = self._capture_tracks_live(drives)
        manifest = {
            "format": FORMAT,
            "id": "live",
            "created": _now(),
            "trigger": "manual",
            "reason": "The library as it is now.",
            "source": None,
            "serato_version": read_install().version,
            "serato_build": read_install().build,
            "database": {"master": None, "root": None},
            "drives": drives,
            "tracks": tracks,
        }
        reader = _live_reader(drives, tracks)
        contents = _contents(manifest, reader)
        contents["crates"].extend(_query_sqlite_crates(self.master))
        return contents

    def _capture_drives_live(self) -> list[dict[str, object]]:
        """Read crate files without storing blobs.

        Returns:
            Drive records whose file entries hold raw bytes under ``data``.
        """
        records = []
        for spec in self._drive_specs():
            if not spec.present or spec.serato_root is None or not spec.serato_root.is_dir():
                records.append({
                    "drive_id": spec.drive_id,
                    "label": spec.label,
                    "role": spec.role,
                    "present": False,
                    "root": None,
                    "music_root": None,
                    "files": [],
                })
                continue
            files = []
            for rel, path in _iter_serato_files(spec.serato_root):
                data = path.read_bytes()
                files.append({"path": rel, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data), "data": data})
            records.append({
                "drive_id": spec.drive_id,
                "label": spec.label,
                "role": spec.role,
                "present": True,
                "root": str(spec.serato_root),
                "music_root": None if spec.music_root is None else str(spec.music_root),
                "files": files,
            })
        return records

    def _capture_tracks_live(self, drives: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
        """Read Serato frames without storing blobs.

        Args:
            drives: Live drive records.

        Returns:
            Track records. Frame values are hashes. The bytes are reread
            while the contents are built.
        """
        records = []
        for spec in self._drive_specs():
            if not spec.present or spec.music_root is None:
                continue
            for path in _audio_paths(self.master, spec, drives):
                stored = snapshot_frames.read_stored_frames(path)
                frames: dict[str, str | None] = {}
                for kind in FRAME_KINDS:
                    blob = stored.get(kind)
                    frames[kind] = None if blob is None else hashlib.sha256(blob).hexdigest()
                records.append({
                    "path": str(path),
                    "drive_id": spec.drive_id,
                    "present": True,
                    "frames": frames,
                    "stored": stored,
                })
        return records

    def _drive_specs(self) -> list[DriveSpec]:
        """Return the drives configured for this store.

        Returns:
            The list passed to the store, or the discovered list.
        """
        if self.drives is not None:
            return list(self.drives)
        return discover_drives()

    def _lexicon_inferred(self) -> bool:
        """Return whether the outside change looks like Lexicon.

        A running Lexicon process counts. So does a ``Lexicon`` directory
        whose own timestamp is within a few seconds of the Serato files.
        The directory is stated, not listed, and nothing inside it is opened.

        Returns:
            True when the source can be named Lexicon.
        """
        try:
            names = self.process_names()
        except (OSError, subprocess.TimeoutExpired):
            names = []
        for name in names:
            if "lexicon" in Path(str(name)).name.lower():
                return True
        newest = 0.0
        for spec in self._drive_specs():
            if not spec.present or spec.serato_root is None:
                continue
            for _rel, path in _iter_serato_files(spec.serato_root):
                try:
                    newest = max(newest, path.stat().st_mtime)
                except OSError:
                    continue
            folder = spec.serato_root / "Lexicon"
            try:
                if not folder.is_dir() or folder.is_symlink():
                    continue
                modified = folder.stat().st_mtime
            except OSError:
                continue
            if newest and abs(modified - newest) <= _LEXICON_WINDOW:
                return True
        return False

    def _verify(self, manifest: Mapping[str, object]) -> None:
        """Check every path and every blob hash.

        Args:
            manifest: Snapshot manifest.

        Raises:
            SnapshotError: If a path is unsafe or a hash does not match.
        """
        for record in _drive_records(manifest):
            for item in record.get("files") or []:
                if not isinstance(item, dict):
                    continue
                rel = str(item.get("path") or "")
                _safe_relative(rel)
                digest = item.get("sha256")
                data = item.get("data")
                if isinstance(data, bytes):
                    if hashlib.sha256(data).hexdigest() != digest:
                        raise SnapshotError("A snapshot file does not match its hash.")
                elif isinstance(digest, str):
                    self._read_blob(digest)
        for track in _track_records(manifest):
            frames = track.get("frames")
            stored = track.get("stored")
            if not isinstance(frames, dict):
                continue
            for kind in FRAME_KINDS:
                digest = frames.get(kind)
                if not isinstance(digest, str):
                    continue
                if isinstance(stored, dict) and isinstance(stored.get(kind), bytes):
                    if hashlib.sha256(stored[kind]).hexdigest() != digest:
                        raise SnapshotError("A snapshot frame does not match its hash.")
                else:
                    self._read_blob(digest)
        database = manifest.get("database")
        if isinstance(database, dict):
            for name in ("master", "root"):
                item = database.get(name)
                if isinstance(item, dict) and isinstance(item.get("sha256"), str):
                    blob = self._read_blob(item["sha256"])
                    if blob[:15] != b"SQLite format 3":
                        raise SnapshotError("A database snapshot is not a SQLite file.")

    def _put_blob(self, data: bytes) -> str:
        """Store bytes by their hash.

        Args:
            data: Bytes to store.

        Returns:
            The SHA-256 hex digest.

        Raises:
            SnapshotError: If the bytes on disk do not match the hash.
        """
        digest = hashlib.sha256(data).hexdigest()
        path = self._blob_path(digest)
        if path.is_file() and not path.is_symlink():
            existing = path.read_bytes()
            if existing != data or hashlib.sha256(existing).hexdigest() != digest:
                raise SnapshotError("A stored snapshot blob does not match its hash.")
            return digest
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.parent / f".{digest}.{secrets.token_hex(4)}.tmp"
        try:
            with temporary.open("wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()
        written = path.read_bytes()
        if written != data or hashlib.sha256(written).hexdigest() != digest:
            raise SnapshotError("A snapshot blob failed its hash check.")
        return digest

    def _read_blob(self, digest: str) -> bytes:
        """Read one blob and check its hash.

        Args:
            digest: SHA-256 hex digest.

        Returns:
            The blob bytes.

        Raises:
            SnapshotError: If the blob is missing, a shortcut, or mismatched.
        """
        path = self._blob_path(digest)
        base = os.path.realpath(self.objects)
        resolved = os.path.realpath(path)
        prefix = base + os.sep
        if not resolved.startswith(prefix) or Path(base) not in Path(resolved).parents:
            raise SnapshotError("A snapshot blob escapes the store.")
        if os.path.islink(resolved) or not os.path.isfile(resolved):
            raise SnapshotError("A snapshot blob is missing.")
        data = Path(resolved).read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise SnapshotError("A snapshot blob does not match its hash.")
        return data

    def _blob_path(self, digest: str) -> Path:
        """Return the path for one content hash.

        Args:
            digest: SHA-256 hex digest.

        Returns:
            A path inside the object store.

        Raises:
            SnapshotError: If the digest is not 64 hex characters or the
                path would leave the store.
        """
        if not _HEX_RE.fullmatch(digest):
            raise SnapshotError("A snapshot hash is not valid.")
        try:
            return _realpath_within(self.objects, digest[:2], digest)
        except OSError as exc:
            raise SnapshotError("A snapshot blob escapes the store.") from exc

    def _manifest(self, snapshot_id: str) -> dict[str, object]:
        """Load one manifest.

        Args:
            snapshot_id: Snapshot id.

        Returns:
            The manifest object.

        Raises:
            SnapshotError: If the id or the file is not valid.
        """
        folder = self._snapshot_dir(snapshot_id)
        if not completeness.is_complete(folder):
            raise SnapshotError("That snapshot is incomplete.", 404)
        base = os.path.realpath(folder)
        full = os.path.normpath(os.path.join(base, "manifest.json"))
        prefix = base + os.sep
        if not full.startswith(prefix):
            raise SnapshotError("That snapshot could not be read.")
        try:
            resolved = os.path.realpath(full)
            if not resolved.startswith(prefix) or Path(base) not in Path(resolved).parents:
                raise SnapshotError("That snapshot could not be read.")
            manifest = json.loads(Path(resolved).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeError) as exc:
            raise SnapshotError("That snapshot could not be read.") from exc
        if not isinstance(manifest, dict) or manifest.get("id") != snapshot_id:
            raise SnapshotError("That snapshot could not be read.")
        if not _body_digest_matches(manifest, self._manifest_key()):
            raise SnapshotError("That snapshot manifest does not match its hash.")
        return manifest

    def _snapshot_dir(self, snapshot_id: str) -> Path:
        """Return the directory for one snapshot id.

        Args:
            snapshot_id: Snapshot id.

        Returns:
            A path inside the manifest directory.

        Raises:
            SnapshotError: If the id is not valid or leaves the directory.
        """
        if not _ID_RE.fullmatch(snapshot_id):
            raise SnapshotError("That snapshot id is not valid.")
        try:
            return _realpath_within(self.manifests, snapshot_id)
        except OSError as exc:
            raise SnapshotError("That snapshot id is not valid.") from exc

    def _manifest_path(self, snapshot_id: str) -> Path:
        """Return the directory for one snapshot id.

        Args:
            snapshot_id: Snapshot id.

        Returns:
            The same path as ``_snapshot_dir``.
        """
        return self._snapshot_dir(snapshot_id)

    def _write_manifest(self, manifest: dict[str, object]) -> None:
        """Publish a manifest only after its blobs have been verified.

        The directory is written as ``id.partial``, ``COMPLETE`` is last, and
        the directory is renamed to ``id``. A failed attempt is not listed.

        Args:
            manifest: Manifest to write. Its id and sha256 change if the name
                exists.

        Raises:
            SnapshotError: If a free id cannot be created.
        """
        self.manifests.mkdir(parents=True, exist_ok=True)
        for _attempt in range(5):
            snapshot_id = str(manifest["id"])
            folder = self._snapshot_dir(snapshot_id)
            if folder.exists():
                manifest["id"] = _new_id()
                manifest.pop("sha256", None)
                continue
            manifest.pop("sha256", None)
            manifest["sha256"] = _body_digest(manifest, self._manifest_key())
            payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
            try:
                completeness.publish_directory(folder, {"manifest.json": payload})
            except FileExistsError:
                manifest["id"] = _new_id()
                manifest.pop("sha256", None)
                continue
            return
        raise SnapshotError("A snapshot id could not be saved.")

    def _latest_manifest(self) -> dict[str, object] | None:
        """Return the newest manifest, or None.

        Returns:
            The manifest, or None when the store is empty.
        """
        rows = self.list_snapshots()
        if not rows:
            return None
        return self._manifest(rows[0]["id"])

    def _latest_id(self) -> str | None:
        """Return the newest snapshot id.

        Returns:
            The id, or None when the store is empty.
        """
        rows = self.list_snapshots()
        if not rows:
            return None
        return rows[0]["id"]

    def _load_state(self) -> dict[str, object]:
        """Read the store state file.

        Returns:
            A dict. A missing or unreadable file returns an empty dict.
        """
        path = self.root / "state.json"
        if not path.is_file() or path.is_symlink():
            return {}
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeError):
            return {}
        return loaded if isinstance(loaded, dict) else {}

    def _save_state(self, state: Mapping[str, object]) -> None:
        """Replace the store state file.

        Args:
            state: JSON-ready state.
        """
        self.root.mkdir(parents=True, exist_ok=True)
        _atomic_write(self.root / "state.json", (json.dumps(state, indent=2, sort_keys=True) + "\n").encode("utf-8"))

    def _remember_version(self, install: SeratoInstall) -> None:
        """Record the version stored in the snapshot just saved.

        Args:
            install: Version and build that were written into the manifest.
        """
        state = self._load_state()
        state["observed_version"] = install.version
        state["observed_build"] = install.build
        self._save_state(state)


class FolderWatch:
    """Poll the Serato files and snapshot outside changes."""

    def __init__(self, interval: float = 5.0):
        """Store the poll interval.

        Args:
            interval: Seconds between polls.
        """
        self.interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the poll thread if it is not already running."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="serato-snapshot-watch", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the poll thread."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def _loop(self) -> None:
        """Poll until stopped. A failed poll is logged and does not exit."""
        while not self._stop.wait(self.interval):
            try:
                current_store().poll()
            except Exception:
                app_log.logger.exception("Snapshot watch failed.")


def start_watch() -> None:
    """Start the folder watch unless it is switched off for a test."""
    global _watch
    if os.environ.get("SERATO_LIBRARY_DISABLE_WATCH") == "1":
        return
    if _watch is None:
        _watch = FolderWatch()
    _watch.start()


def stop_watch() -> None:
    """Stop the folder watch."""
    if _watch is not None:
        _watch.stop()


def discover_drives() -> list[DriveSpec]:
    """Find ``_Serato_`` folders for the live library.

    Returns:
        An empty list when this process is using a relocated library.
        Otherwise the Music folder and mounted volumes that contain
        ``_Serato_``.
    """
    if not _using_live_library():
        return []
    found: list[DriveSpec] = []
    music = Path.home() / "Music"
    internal = music / "_Serato_"
    if internal.is_dir() and not internal.is_symlink():
        found.append(DriveSpec(
            drive_id=_volume_key(internal) or "internal-music",
            label="Music",
            serato_root=internal,
            music_root=music,
            role="internal",
            present=True,
        ))
    for root in _external_roots():
        found.append(DriveSpec(
            drive_id=_volume_key(root) or f"drive-{root.parent.name}",
            label=root.parent.name or root.name,
            serato_root=root,
            music_root=root.parent,
            role="external",
            present=True,
        ))
    return found


def default_process_names() -> list[str]:
    """Return command names of running processes.

    Returns:
        Base names from ``ps`` or image names from ``tasklist``. An empty
        list when the command cannot be run.
    """
    try:
        if sys.platform == "win32":
            return [row[0] for row in csv.reader(io.StringIO(_run(detection_command("win32")))) if row]
        return [line.strip() for line in _run(detection_command(sys.platform)).splitlines() if line.strip()]
    except (OSError, subprocess.TimeoutExpired):
        return []


def _sqlite_blob(store: SnapshotStore, source: Path) -> dict[str, object]:
    """Back up one SQLite file into the content store.

    Args:
        store: Store that receives the blob.
        source: Database to copy.

    Returns:
        Hash, size, and integrity. The integrity text is ``ok`` or ``failed``.
    """
    fd, name = tempfile.mkstemp(prefix="serato-snapdb-", suffix=".sqlite")
    os.close(fd)
    dest = Path(name)
    try:
        dest.unlink()
        with closing(sqlite3.connect(f"file:{source}?mode=ro", uri=True)) as src:
            with closing(sqlite3.connect(dest)) as copied:
                src.backup(copied)
        integrity = "failed"
        try:
            with closing(sqlite3.connect(f"file:{dest}?mode=ro", uri=True)) as conn:
                row = conn.execute("PRAGMA integrity_check").fetchone()
            if row and row[0] == "ok":
                integrity = "ok"
        except sqlite3.Error:
            integrity = "failed"
        data = dest.read_bytes()
    finally:
        dest.unlink(missing_ok=True)
    return {"sha256": store._put_blob(data), "size": len(data), "integrity": integrity}


def _info(manifest: Mapping[str, object]) -> SnapshotInfo:
    """Build the public summary for one manifest.

    Args:
        manifest: Stored manifest.

    Returns:
        The summary row.
    """
    unavailable = [
        str(item.get("label") or item.get("drive_id"))
        for item in _drive_records(manifest)
        if not item.get("present")
    ]
    database = manifest.get("database")
    integrity = "ok"
    if isinstance(database, dict):
        master = database.get("master")
        if isinstance(master, dict) and master.get("integrity") not in (None, "ok"):
            integrity = "failed"
    source = manifest.get("source")
    return {
        "id": str(manifest.get("id") or ""),
        "created": str(manifest.get("created") or ""),
        "trigger": str(manifest.get("trigger") or ""),
        "reason": str(manifest.get("reason") or ""),
        "source": source if isinstance(source, str) else None,
        "serato_version": str(manifest.get("serato_version") or "unknown"),
        "serato_build": str(manifest.get("serato_build") or "unknown"),
        "unavailable_drives": unavailable,
        "integrity": integrity,
    }


def _contents(manifest: Mapping[str, object], reader: Callable[[str], bytes]) -> SnapshotContents:
    """Parse crates, cues, grids, and autotags from a manifest.

    Args:
        manifest: Snapshot or live manifest.
        reader: Returns blob bytes for a hash. Live reads pass a reader that
            understands inline bytes.

    Returns:
        The loaded snapshot.
    """
    crates: list[CrateView] = []
    for record in _drive_records(manifest):
        present = bool(record.get("present"))
        drive_id = str(record.get("drive_id") or "")
        label = str(record.get("label") or drive_id)
        for item in record.get("files") or []:
            if not isinstance(item, dict):
                continue
            rel = str(item.get("path") or "")
            data = item.get("data")
            if not isinstance(data, bytes):
                digest = item.get("sha256")
                if not isinstance(digest, str):
                    continue
                data = reader(digest)
            crates.extend(_crates_from_file(drive_id, label, present, rel, data))
    crates.extend(_sqlite_crates(manifest, reader))
    cues: list[CueTrackView] = []
    grids: list[GridTrackView] = []
    tag_rows: list[TagView] = []
    for track in _track_records(manifest):
        frames = track.get("frames")
        stored = track.get("stored") if isinstance(track.get("stored"), dict) else {}
        if not isinstance(frames, dict):
            continue
        path = str(track.get("path") or "")
        drive_id = str(track.get("drive_id") or "")
        present = bool(track.get("present"))
        for kind in FRAME_KINDS:
            digest = frames.get(kind)
            blob = stored.get(kind) if isinstance(stored, dict) else None
            if not isinstance(blob, bytes):
                if not isinstance(digest, str):
                    continue
                blob = reader(digest)
            if not isinstance(digest, str):
                digest = hashlib.sha256(blob).hexdigest()
            if not isinstance(blob, bytes):
                continue
            payload = snapshot_frames.payload_from_stored(blob)
            if kind == "Markers2":
                parsed = snapshot_frames.parse_markers_payload(payload)
                cues.append({
                    "path": path,
                    "drive_id": drive_id,
                    "present": present,
                    "sha256": digest,
                    "cues": list(parsed["cues"]),
                    "loops": list(parsed["loops"]),
                    "flips": list(parsed["flips"]),
                })
            elif kind == "BeatGrid":
                grids.append({
                    "path": path,
                    "drive_id": drive_id,
                    "present": present,
                    "sha256": digest,
                    "markers": list(snapshot_frames.parse_beatgrid_payload(payload)),
                })
            else:
                tag_rows.append({
                    "path": path,
                    "drive_id": drive_id,
                    "present": present,
                    "kind": kind,
                    "sha256": digest,
                    "size": len(blob),
                })
    return {"info": _info(manifest), "crates": crates, "cues": cues, "grids": grids, "tags": tag_rows}


def _crates_from_file(drive_id: str, label: str, present: bool, rel: str, data: bytes) -> list[CrateView]:
    """Turn one Serato file into crate rows.

    Args:
        drive_id: Drive id.
        label: Drive label.
        present: Whether the drive is available.
        rel: Path relative to ``_Serato_``.
        data: File bytes.

    Returns:
        One row for a crate file or for database V2. Other files add nothing.
    """
    name = Path(rel).name
    suffix = Path(rel).suffix.lower()
    if name == "database V2":
        return [{
            "drive_id": drive_id,
            "drive_label": label,
            "present": present,
            "name": "database V2",
            "path": rel,
            "source": "database-v2",
            "tracks": parse_serato_bytes(data),
        }]
    if suffix not in {".crate", ".scrate"}:
        return []
    label_name = Path(rel).stem.replace("%%", " / ")
    return [{
        "drive_id": drive_id,
        "drive_label": label,
        "present": present,
        "name": label_name,
        "path": rel,
        "source": "smart-crate" if suffix == ".scrate" else "crate",
        "tracks": parse_serato_bytes(data),
    }]


def _sqlite_crates(manifest: Mapping[str, object], reader: Callable[[str], bytes]) -> list[CrateView]:
    """Read crate rows from the snapshotted master database.

    Args:
        manifest: Manifest with a master hash or no database snapshot.
        reader: Returns blob bytes for a hash.

    Returns:
        Crates from the ``container`` table. Type 0, the space root, is
        omitted. A database without that table returns nothing.
    """
    database = manifest.get("database")
    if not isinstance(database, dict):
        return []
    master = database.get("master")
    if not isinstance(master, dict) or not isinstance(master.get("sha256"), str):
        return []
    try:
        data = reader(master["sha256"])
    except SnapshotError:
        return []
    fd, name = tempfile.mkstemp(prefix="serato-snapread-", suffix=".sqlite")
    os.close(fd)
    path = Path(name)
    crates: list[CrateView] = []
    try:
        path.write_bytes(data)
        with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as conn:
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(
                    "SELECT id, name, type FROM container WHERE type != 0 ORDER BY list_order, id"
                ).fetchall()
            except sqlite3.Error:
                return []
            for row in rows:
                tracks: list[str] = []
                try:
                    found = conn.execute(
                        """
                        SELECT asset.portable_id FROM container_asset
                        JOIN asset ON asset.id = container_asset.asset_id
                        WHERE container_asset.container_id = ?
                        ORDER BY container_asset.list_order
                        """,
                        (row["id"],),
                    ).fetchall()
                    tracks = [str(item["portable_id"]) for item in found if item["portable_id"]]
                except sqlite3.Error:
                    tracks = []
                raw_name = str(row["name"] or "")
                crates.append({
                    "drive_id": "library",
                    "drive_label": "Library",
                    "present": True,
                    "name": raw_name.split("\U00105e8a", 1)[0],
                    "path": f"container/{row['id']}",
                    "source": "database",
                    "tracks": tracks,
                })
    finally:
        path.unlink(missing_ok=True)
    return crates


def _query_sqlite_crates(master: Path) -> list[CrateView]:
    """Read crate rows from the live master database.

    Args:
        master: Database file.

    Returns:
        Crates from the ``container`` table. A missing table returns nothing.
        The file is opened read-only.
    """
    if not master.is_file() or master.is_symlink():
        return []
    crates: list[CrateView] = []
    try:
        with closing(sqlite3.connect(f"file:{master}?mode=ro", uri=True)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id, name, type FROM container WHERE type != 0 ORDER BY list_order, id"
            ).fetchall()
            for row in rows:
                found = conn.execute(
                    """
                    SELECT asset.portable_id FROM container_asset
                    JOIN asset ON asset.id = container_asset.asset_id
                    WHERE container_asset.container_id = ?
                    ORDER BY container_asset.list_order
                    """,
                    (row["id"],),
                ).fetchall()
                raw_name = str(row["name"] or "")
                crates.append({
                    "drive_id": "library",
                    "drive_label": "Library",
                    "present": True,
                    "name": raw_name.split("\U00105e8a", 1)[0],
                    "path": f"container/{row['id']}",
                    "source": "database",
                    "tracks": [str(item["portable_id"]) for item in found if item["portable_id"]],
                })
    except sqlite3.Error:
        return crates
    return crates


def _diff_contents(
    current: SnapshotContents,
    target: SnapshotContents,
    snapshot_id: str,
) -> dict[str, object]:
    """Compare two loaded snapshots.

    Args:
        current: The library as it is now.
        target: The snapshot that would be restored.
        snapshot_id: Target id, reported on the result.

    Returns:
        Added, removed, and changed crates and tracks, plus per-file cue
        and grid differences. An unavailable drive is listed as unavailable
        and is not listed as removed.
    """
    unavailable = {
        crate["drive_id"]
        for crate in target["crates"]
        if not crate["present"]
    }
    unavailable.update(
        track["drive_id"] for track in target["cues"] if not track["present"]
    )
    unavailable.update(
        track["drive_id"] for track in target["tags"] if not track["present"]
    )
    current_crates = {_crate_key(crate): crate for crate in current["crates"] if crate["drive_id"] not in unavailable}
    target_crates = {_crate_key(crate): crate for crate in target["crates"] if crate["drive_id"] not in unavailable}
    added = [_public_crate(target_crates[key]) for key in target_crates if key not in current_crates]
    removed = [_public_crate(current_crates[key]) for key in current_crates if key not in target_crates]
    changed = []
    for key in current_crates.keys() & target_crates.keys():
        before = list(current_crates[key]["tracks"])
        after = list(target_crates[key]["tracks"])
        if before != after:
            changed.append({
                "drive_id": target_crates[key]["drive_id"],
                "name": target_crates[key]["name"],
                "path": target_crates[key]["path"],
                "tracks_added": [item for item in after if item not in before],
                "tracks_removed": [item for item in before if item not in after],
            })
    current_tracks = {_track_key(track): track for track in _track_views(current) if track["drive_id"] not in unavailable}
    target_tracks = {_track_key(track): track for track in _track_views(target) if track["drive_id"] not in unavailable}
    cue_diffs = []
    grid_diffs = []
    for key in sorted(set(current_tracks) | set(target_tracks)):
        before = current_tracks.get(key)
        after = target_tracks.get(key)
        before_cue = None if before is None else before.get("cue_sha")
        after_cue = None if after is None else after.get("cue_sha")
        if before_cue != after_cue:
            cue_diffs.append({
                "path": (after or before or {})["path"],
                "drive_id": (after or before or {})["drive_id"],
                "before": None if before is None else before.get("cues"),
                "after": None if after is None else after.get("cues"),
            })
        before_grid = None if before is None else before.get("grid_sha")
        after_grid = None if after is None else after.get("grid_sha")
        if before_grid != after_grid:
            grid_diffs.append({
                "path": (after or before or {})["path"],
                "drive_id": (after or before or {})["drive_id"],
                "before": None if before is None else before.get("grid"),
                "after": None if after is None else after.get("grid"),
            })
    track_added = [
        {"path": target_tracks[key]["path"], "drive_id": target_tracks[key]["drive_id"]}
        for key in target_tracks
        if key not in current_tracks
    ]
    track_removed = [
        {"path": current_tracks[key]["path"], "drive_id": current_tracks[key]["drive_id"]}
        for key in current_tracks
        if key not in target_tracks
    ]
    unavailable_crates = [_public_crate(crate) for crate in target["crates"] if not crate["present"]]
    unavailable_tracks = [
        {"path": track["path"], "drive_id": track["drive_id"]}
        for track in target["tags"]
        if not track["present"]
    ]
    return {
        "snapshot_id": snapshot_id,
        "crates": {
            "added": added,
            "removed": removed,
            "changed": changed,
            "unavailable": unavailable_crates,
        },
        "tracks": {
            "added": track_added,
            "removed": track_removed,
            "unavailable": unavailable_tracks,
        },
        "cues": cue_diffs,
        "grids": grid_diffs,
        "deleted": {
            "crates": removed,
            "tracks": track_removed,
            "cues": [item for item in cue_diffs if item.get("after") is None],
            "grids": [item for item in grid_diffs if item.get("after") is None],
        },
    }


def _track_views(contents: SnapshotContents) -> list[dict[str, object]]:
    """Index cue, grid, and tag rows by path.

    Args:
        contents: Loaded snapshot.

    Returns:
        One dict per path.
    """
    by_path: dict[str, dict[str, object]] = {}
    for cue in contents["cues"]:
        row = by_path.setdefault(cue["path"], {"path": cue["path"], "drive_id": cue["drive_id"]})
        row["cue_sha"] = cue["sha256"]
        row["cues"] = {"cues": cue["cues"], "loops": cue["loops"], "flips": cue["flips"]}
    for grid in contents["grids"]:
        row = by_path.setdefault(grid["path"], {"path": grid["path"], "drive_id": grid["drive_id"]})
        row["grid_sha"] = grid["sha256"]
        row["grid"] = grid["markers"]
    for tag in contents["tags"]:
        row = by_path.setdefault(tag["path"], {"path": tag["path"], "drive_id": tag["drive_id"]})
        row["tag_sha"] = tag["sha256"]
    return list(by_path.values())


def _public_crate(crate: CrateView) -> dict[str, object]:
    """Copy the crate fields a dry run shows.

    Args:
        crate: Crate row.

    Returns:
        Name, path, drive, and track list.
    """
    return {
        "drive_id": crate["drive_id"],
        "drive_label": crate["drive_label"],
        "name": crate["name"],
        "path": crate["path"],
        "tracks": list(crate["tracks"]),
    }


def _crate_key(crate: CrateView) -> tuple[str, str]:
    """Return the identity of a crate.

    Args:
        crate: Crate row.

    Returns:
        Drive id and relative path.
    """
    return (crate["drive_id"], crate["path"])


def _track_key(track: Mapping[str, object]) -> str:
    """Return the identity of a track row.

    Args:
        track: Track view.

    Returns:
        The path.
    """
    return str(track.get("path") or "")


def _live_reader(drives: Sequence[Mapping[str, object]], tracks: Sequence[Mapping[str, object]]) -> Callable[[str], bytes]:
    """Return a blob reader for a live manifest's inline bytes.

    Args:
        drives: Live drive records.
        tracks: Live track records.

    Returns:
        A function that finds inline bytes by hash.
    """
    found: dict[str, bytes] = {}
    for record in drives:
        for item in record.get("files") or []:
            if isinstance(item, dict) and isinstance(item.get("data"), bytes) and isinstance(item.get("sha256"), str):
                found[item["sha256"]] = item["data"]
    for track in tracks:
        stored = track.get("stored")
        frames = track.get("frames")
        if not isinstance(stored, dict) or not isinstance(frames, dict):
            continue
        for kind, blob in stored.items():
            digest = frames.get(kind)
            if isinstance(blob, bytes) and isinstance(digest, str):
                found[digest] = blob

    def read(digest: str) -> bytes:
        if digest not in found:
            raise SnapshotError("A snapshot blob is missing.")
        return found[digest]

    return read


def _audio_paths(master: Path, spec: DriveSpec, drives: Sequence[Mapping[str, object]]) -> list[Path]:
    """Return audio files a drive's crates and database V2 point at.

    Args:
        master: Library database whose tracks may point at this drive.
        spec: Drive being snapshotted.
        drives: Captured drive records, including file bytes for a live read.

    Returns:
        Existing regular files under the drive's music root. Paths inside
        ``Lexicon`` or ``Export Backups`` are not returned.
    """
    if spec.music_root is None:
        return []
    record = next((item for item in drives if item.get("drive_id") == spec.drive_id), None)
    paths: list[Path] = []
    seen: set[Path] = set()
    files = record.get("files") if isinstance(record, Mapping) else []
    for item in files or []:
        if not isinstance(item, dict):
            continue
        rel = str(item.get("path") or "")
        if _excluded_relative(rel):
            continue
        if not rel.endswith((".crate", ".scrate")) and not rel.endswith("database V2"):
            continue
        data = item.get("data")
        if not isinstance(data, bytes):
            if spec.serato_root is None:
                continue
            file_path = spec.serato_root / rel
            if not file_path.is_file() or file_path.is_symlink():
                continue
            try:
                data = file_path.read_bytes()
            except OSError:
                continue
        for track in parse_serato_bytes(data):
            resolved = _resolve_track(track, spec.music_root)
            if resolved is not None and resolved not in seen:
                seen.add(resolved)
                paths.append(resolved)
    for path in _sqlite_audio_paths(master, spec.music_root):
        if path not in seen:
            seen.add(path)
            paths.append(path)
    return paths


def _sqlite_audio_paths(master: Path, music_root: Path) -> list[Path]:
    """Resolve library tracks that live under one drive's music root.

    Args:
        master: Library database to read.
        music_root: Drive folder the path must stay inside.

    Returns:
        Audio files from ``asset.portable_id``. A relocated test library
        does not resolve paths against the real home directory. Tracks that
        are missing or outside the root are skipped.
    """
    if not master.is_file() or master.is_symlink():
        return []
    found: list[Path] = []
    try:
        with closing(sqlite3.connect(f"file:{master}?mode=ro", uri=True)) as conn:
            rows = conn.execute("SELECT portable_id FROM asset").fetchall()
    except sqlite3.Error:
        return []
    for row in rows:
        portable = row[0]
        if isinstance(portable, str):
            resolved = _resolve_track(portable, music_root)
            if resolved is not None:
                found.append(resolved)
    return found


def _resolve_track(text: str, music_root: Path) -> Path | None:
    """Resolve a crate path against a drive's music root.

    Args:
        text: Path stored in a crate or database V2.
        music_root: Root the path must stay inside.

    Returns:
        The file, or None when it is missing, a shortcut, or outside the root.
    """
    raw = text.replace("\\", "/").lstrip("/")
    parts = [part for part in raw.split("/") if part != ""]
    if not raw or not parts or any(part in {".", ".."} for part in parts):
        return None
    if any(":" in part for part in parts):
        return None
    relatives = [raw]
    # Format fixtures record Music/track.mp3 and keep the clip in audio/.
    if len(parts) > 1 and _fold_component(parts[0]) == "music":
        relatives.append("/".join(["audio", *parts[1:]]))
    if parts[-1] not in relatives:
        relatives.append(parts[-1])
    root = music_root.resolve()
    for rel in relatives:
        candidate = (music_root / rel)
        if candidate.is_symlink():
            continue
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if _contained(resolved, root) and resolved.is_file():
            return resolved
    return None


def _iter_serato_files(root: Path) -> list[tuple[str, Path]]:
    """List Serato files that a snapshot is allowed to touch.

    Args:
        root: ``_Serato_`` directory.

    Returns:
        Relative POSIX path and file path. ``Export Backups`` and ``Lexicon``
        are not entered. Shortcuts are skipped.
    """
    found: list[tuple[str, Path]] = []
    if not root.is_dir() or root.is_symlink():
        return found
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(dirpath)
        dirnames[:] = [
            name for name in dirnames
            if _fold_component(name) not in _EXCLUDED_FOLDED and not (current / name).is_symlink()
        ]
        for name in filenames:
            path = current / name
            if path.is_symlink() or not path.is_file():
                continue
            try:
                if path.stat().st_size > _MAX_FILE:
                    continue
            except OSError:
                continue
            rel = path.relative_to(root).as_posix()
            if _excluded_relative(rel) or _fold_component(name) in _EXCLUDED_FOLDED:
                continue
            found.append((rel, path))
    return found


def _carry_drive(old: Mapping[str, object] | None, spec: DriveSpec | None) -> dict[str, object]:
    """Copy a drive record forward as unavailable.

    Args:
        old: Previous drive record, or None.
        spec: Current drive, or None when the drive was omitted.

    Returns:
        A record with ``present`` false. Files and the label are kept.
        Crates are not dropped.
    """
    if isinstance(old, Mapping):
        carried = {key: value for key, value in old.items() if key != "data"}
        files = []
        for item in old.get("files") or []:
            if isinstance(item, dict):
                files.append({key: value for key, value in item.items() if key != "data"})
        carried["files"] = files
        carried["present"] = False
        carried["root"] = None
        return carried
    return {
        "drive_id": "" if spec is None else spec.drive_id,
        "label": "" if spec is None else spec.label,
        "role": "external" if spec is None else spec.role,
        "present": False,
        "root": None,
        "music_root": None,
        "files": [],
    }


def _drive_records(manifest: Mapping[str, object] | None) -> list[dict[str, object]]:
    """Return the drive list from a manifest.

    Args:
        manifest: Manifest or None.

    Returns:
        Drive dicts. A missing list is empty.
    """
    if not isinstance(manifest, Mapping):
        return []
    drives = manifest.get("drives")
    if not isinstance(drives, list):
        return []
    return [item for item in drives if isinstance(item, dict)]


def _track_records(manifest: Mapping[str, object] | None) -> list[dict[str, object]]:
    """Return the track list from a manifest.

    Args:
        manifest: Manifest or None.

    Returns:
        Track dicts.
    """
    if not isinstance(manifest, Mapping):
        return []
    tracks = manifest.get("tracks")
    if not isinstance(tracks, list):
        return []
    return [item for item in tracks if isinstance(item, dict)]


def _present_root(record: Mapping[str, object], specs: Sequence[DriveSpec]) -> Path | None:
    """Find the current ``_Serato_`` directory for a present drive.

    Args:
        record: Drive record from the snapshot.
        specs: Drives visible now.

    Returns:
        The directory, or None when that drive is not plugged in.
    """
    for spec in specs:
        if spec.drive_id == record.get("drive_id") and spec.present and spec.serato_root is not None:
            if spec.serato_root.is_dir() and not spec.serato_root.is_symlink():
                return spec.serato_root
    return None


def _safe_relative(value: str) -> str:
    """Validate a path relative to a ``_Serato_`` directory.

    Args:
        value: Relative path from a manifest.

    Returns:
        The same path, using forward slashes.

    Raises:
        SnapshotError: If the path is absolute, climbs out, or names
            ``Export Backups`` or ``Lexicon``.
    """
    if not value or value.startswith(("/", "\\")):
        raise SnapshotError("A snapshot path is not valid.")
    text = value.replace("\\", "/")
    parts = text.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise SnapshotError("A snapshot path is not valid.")
    if _excluded_relative(text):
        raise SnapshotError("Export Backups and Lexicon are not restored.")
    if any(":" in part for part in parts):
        raise SnapshotError("A snapshot path is not valid.")
    return "/".join(parts)


def _fold_component(part: str) -> str:
    """Normalize one path component before an exclusion check.

    Trailing dots and spaces are removed first. Windows treats ``Lexicon.``
    and ``Lexicon `` as ``Lexicon``. Text after a colon is an alternate data
    stream, so ``Lexicon::$DATA`` is compared as ``Lexicon``.

    Args:
        part: One path component.

    Returns:
        The folded name.
    """
    return part.split(":", 1)[0].rstrip(" .").casefold()


def _excluded_relative(value: str) -> bool:
    """Return whether a relative path enters an excluded folder.

    Args:
        value: Relative path.

    Returns:
        True when any path part matches ``Export Backups`` or ``Lexicon``
        after trailing dots, spaces, and an alternate-data-stream suffix are
        removed. A sibling such as ``Export Backups-extra`` is not excluded.
    """
    parts = value.replace("\\", "/").split("/")
    return any(_fold_component(part) in _EXCLUDED_FOLDED for part in parts if part)


def _join(root: Path, rel: str) -> Path:
    """Join a relative Serato path onto a drive root.

    Args:
        root: ``_Serato_`` directory.
        rel: Validated relative path.

    Returns:
        The target file.

    Raises:
        SnapshotError: If the path leaves the root or a parent is a shortcut.
    """
    target = root / rel
    current = target
    while True:
        if current.is_symlink():
            raise SnapshotError("Refusing to follow a shortcut in the Serato folder.")
        if current == root:
            break
        if current == current.parent:
            raise SnapshotError("A snapshot path is not valid.")
        current = current.parent
    if not _contained(target, root):
        raise SnapshotError("A snapshot path is not valid.")
    return target


def _replace_database(path: Path, data: bytes, library_dir: Path) -> None:
    """Replace one database and remove its WAL files.

    Args:
        path: ``master.sqlite`` or ``root.sqlite``.
        data: Snapshot bytes.
        library_dir: Directory that must contain the file.

    Raises:
        SnapshotError: If the name or the location is not the library database.
    """
    if path.name not in {"master.sqlite", "root.sqlite"}:
        raise SnapshotError("Refusing to restore an unexpected database.")
    if path.is_symlink() or not _contained(path, library_dir):
        raise SnapshotError("Refusing to restore a database outside the library folder.")
    _clear_sqlite_sidecars(path, library_dir)
    _atomic_write(path, data)
    _clear_sqlite_sidecars(path, library_dir)


def _clear_sqlite_sidecars(path: Path, library_dir: Path) -> None:
    """Remove SQLite sidecars so they cannot replay over a restored database.

    Args:
        path: ``master.sqlite`` or ``root.sqlite``.
        library_dir: Directory that must contain the sidecars.

    Raises:
        SnapshotError: If a sidecar is a shortcut or leaves the library folder.
    """
    for suffix in ("-journal", "-wal", "-shm"):
        sidecar = Path(str(path) + suffix)
        if not sidecar.exists() and not sidecar.is_symlink():
            continue
        if sidecar.is_symlink() or not _contained(sidecar, library_dir):
            raise SnapshotError("Refusing to remove a database sidecar that is a shortcut.")
        sidecar.unlink()


def _body_digest(manifest: Mapping[str, object], key: bytes) -> str:
    """Hash a manifest without its own sha256 field.

    The digest is HMAC-SHA256 with the library's manifest key. A copied
    ``manifest.json`` does not verify on this machine unless that key is
    copied too. The key file is not inside the snapshot directory.

    Args:
        manifest: Manifest object.
        key: 32-byte key from ``manifest.key``.

    Returns:
        The HMAC-SHA256 hex digest of the canonical JSON.
    """
    body = {item: value for item, value in manifest.items() if item != "sha256"}
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(key, canonical, hashlib.sha256).hexdigest()


def _body_digest_matches(manifest: Mapping[str, object], key: bytes) -> bool:
    """Return whether a manifest's sha256 matches its other fields.

    Args:
        manifest: Manifest that includes ``sha256``.
        key: 32-byte key from ``manifest.key``.

    Returns:
        True when the recorded HMAC matches.
    """
    recorded = manifest.get("sha256")
    if not isinstance(recorded, str):
        return False
    expected = _body_digest(manifest, key)
    return len(recorded) == len(expected) and hmac.compare_digest(recorded, expected)


def _atomic_write(path: Path, data: bytes) -> None:
    """Replace one file by writing a temporary file beside it.

    Args:
        path: Destination.
        data: Bytes to store.

    Raises:
        OSError: If the file cannot be written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{secrets.token_hex(4)}.tmp"
    try:
        with temporary.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _realpath_within(root: Path, *parts: str) -> Path:
    """Resolve a child of a directory and refuse a path that leaves it.

    The path is normalized, then checked with a prefix that ends in a
    separator, then checked again as a parent. A shortcut that points
    outside the directory fails the second check.

    Args:
        root: Directory the result must stay inside.
        parts: Path components under ``root``.

    Returns:
        The resolved path.

    Raises:
        OSError: If the path leaves ``root``.
    """
    base = os.path.realpath(root)
    prefix = base if base.endswith(os.sep) else base + os.sep
    full = os.path.normpath(os.path.join(base, *parts))
    if full != base and not full.startswith(prefix):
        raise OSError("That path leaves the directory.")
    resolved = os.path.realpath(full)
    if resolved != base and not resolved.startswith(prefix):
        raise OSError("That path leaves the directory.")
    base_path = Path(base)
    resolved_path = Path(resolved)
    if resolved_path != base_path and base_path not in resolved_path.parents:
        raise OSError("That path leaves the directory.")
    return resolved_path


def _contained(path: Path, root: Path) -> bool:
    """Return whether a path stays inside a directory.

    Args:
        path: Candidate path.
        root: Directory that must contain it.

    Returns:
        True when the resolved path is the directory or a child of it.
    """
    try:
        base = os.path.realpath(root)
        resolved = os.path.realpath(path)
    except OSError:
        return False
    prefix = base if base.endswith(os.sep) else base + os.sep
    if resolved != base and not resolved.startswith(prefix):
        return False
    base_path = Path(base)
    resolved_path = Path(resolved)
    return resolved_path == base_path or base_path in resolved_path.parents


def _chunks(data: bytes) -> list[tuple[str, bytes]]:
    """Split a Serato chunk file.

    Args:
        data: File bytes.

    Returns:
        Tag and payload pairs. Parsing stops at a truncated chunk.
    """
    chunks: list[tuple[str, bytes]] = []
    pos = 0
    while pos + 8 <= len(data):
        tag = data[pos:pos + 4]
        if not tag.isascii() or not tag.isalnum():
            break
        length = int.from_bytes(data[pos + 4:pos + 8], "big")
        if pos + 8 + length > len(data):
            break
        chunks.append((tag.decode("ascii"), data[pos + 8:pos + 8 + length]))
        pos += 8 + length
    return chunks


def _utf16be(data: bytes) -> str:
    """Decode a Serato UTF-16-BE string.

    Args:
        data: Path bytes, with an optional byte-order mark and trailing NUL.

    Returns:
        The text. A short odd length drops the last byte.
    """
    if data.startswith(b"\xfe\xff"):
        data = data[2:]
    if len(data) % 2:
        data = data[:-1]
    return data.decode("utf-16-be", "replace").rstrip("\x00")


def _stat_row(path: Path, label: str) -> str:
    """Describe one watched file for the fingerprint.

    Args:
        path: File to stat.
        label: Stable label stored in the fingerprint.

    Returns:
        Label, size, and modified time, or a missing marker.
    """
    try:
        if not path.is_file() or path.is_symlink():
            return f"missing\0{label}"
        stat = path.stat()
    except OSError:
        return f"missing\0{label}"
    return f"file\0{label}\0{stat.st_size}\0{stat.st_mtime_ns}"


def _new_id() -> str:
    """Return a snapshot id that is unique inside one second.

    Returns:
        A UTC timestamp plus a random suffix. The name has no colon, so it
        is a valid file name on Windows.
    """
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{stamp}-{secrets.token_hex(4)}"


def _now() -> str:
    """Return the current UTC time as text.

    Returns:
        An ISO-8601 timestamp with a ``Z`` suffix.
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _run(command: list[str]) -> str:
    """Run a short process-list command.

    Args:
        command: Argv.

    Returns:
        Standard output.

    Raises:
        OSError: If the command cannot start.
        subprocess.TimeoutExpired: If it runs longer than two seconds.
    """
    result = subprocess.run(command, capture_output=True, text=True, timeout=2, check=False)
    return result.stdout


def _read_version() -> tuple[str, str]:
    """Read the installed Serato version and build.

    Returns:
        Version and build. Either value is ``unknown`` when it cannot be read.
        Windows reads the Serato DJ executable under Program Files, then the
        registry. It does not look for a relative ``.app`` bundle.
    """
    override = os.environ.get("SERATO_LIBRARY_APP_INFO")
    if override:
        return _version_from_plist(Path(override))
    if not _using_live_library():
        return ("unknown", "unknown")
    found = detect_install(sys.platform)
    return found.version, found.build


def detect_install(
    platform: str,
    *,
    info_plist: Path | None = None,
    program_files: Path | None = None,
    registry: Callable[[], tuple[str, str] | None] | None = None,
    exe_reader: Callable[[Path], tuple[str, str] | None] | None = None,
) -> SeratoInstall:
    """Read Serato's version for one operating system.

    Args:
        platform: ``darwin`` or ``win32``. Any other value is unknown.
        info_plist: macOS Info.plist. None uses the absolute app-bundle path.
        program_files: Windows Program Files root. None uses the usual roots.
        registry: Replacement for the Windows registry read.
        exe_reader: Replacement for the executable version read.

    Returns:
        Version and build. Protect Library is left unknown; ``read_install``
        fills it in.
    """
    if platform == "win32":
        version, build = _windows_version(program_files, registry, exe_reader)
    elif platform == "darwin":
        version, build = _version_from_plist(info_plist or _mac_info_plist())
    else:
        version, build = ("unknown", "unknown")
    return SeratoInstall(version, build, "unknown")


def _mac_info_plist() -> Path:
    """Return the absolute Serato DJ Pro Info.plist on macOS.

    Returns:
        ``/Applications/Serato DJ Pro.app/Contents/Info.plist``.
    """
    return Path("/Applications/Serato DJ Pro.app/Contents/Info.plist")


def _windows_version(
    program_files: Path | None,
    registry: Callable[[], tuple[str, str] | None] | None,
    exe_reader: Callable[[Path], tuple[str, str] | None] | None,
) -> tuple[str, str]:
    """Read the Windows Serato DJ version from the exe, then the registry.

    Args:
        program_files: Program Files directory to search.
        registry: Registry reader. None uses ``winreg`` on Windows.
        exe_reader: Executable reader. None uses the version resource.

    Returns:
        Version and build, or unknown when neither source can be read.
    """
    reader = exe_reader if exe_reader is not None else _exe_file_version
    for path in _windows_exe_candidates(program_files):
        try:
            found = reader(path)
        except OSError:
            found = None
        if found is not None:
            return found
    lookup = registry if registry is not None else _registry_version
    try:
        found = lookup()
    except OSError:
        found = None
    if found is not None:
        return found
    return ("unknown", "unknown")


def _windows_exe_candidates(program_files: Path | None) -> list[Path]:
    """Return Serato DJ executables that exist under Program Files.

    Args:
        program_files: One Program Files root, or None for the usual roots.

    Returns:
        Existing ``Serato DJ Pro.exe`` or ``Serato DJ.exe`` paths.
    """
    roots: list[Path] = []
    if program_files is not None:
        roots.append(program_files)
    else:
        for key in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)"):
            value = os.environ.get(key)
            if value:
                roots.append(Path(value))
        roots.extend((Path("C:/Program Files"), Path("C:/Program Files (x86)")))
    relatives = (
        Path("Serato") / "Serato DJ Pro" / "Serato DJ Pro.exe",
        Path("Serato") / "Serato DJ Pro" / "Serato DJ.exe",
        Path("Serato") / "Serato DJ" / "Serato DJ.exe",
    )
    found: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        for relative in relatives:
            candidate = root / relative
            key = str(candidate).casefold()
            if key in seen:
                continue
            seen.add(key)
            try:
                if candidate.is_file() and not candidate.is_symlink():
                    found.append(candidate)
            except OSError:
                continue
    return found


def _exe_file_version(path: Path) -> tuple[str, str] | None:
    """Read FileVersion and ProductVersion from a Windows executable.

    Args:
        path: ``Serato DJ Pro.exe`` or ``Serato DJ.exe``.

    Returns:
        Version and build, or None when the resource cannot be read. This
        returns None off Windows.
    """
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    version_dll = ctypes.windll.version
    size = version_dll.GetFileVersionInfoSizeW(str(path), None)
    if not size:
        return None
    buffer = ctypes.create_string_buffer(size)
    if not version_dll.GetFileVersionInfoW(str(path), 0, size, buffer):
        return None
    pointer = ctypes.c_void_p()
    length = wintypes.UINT()
    if not version_dll.VerQueryValueW(
        buffer, "\\VarFileInfo\\Translation", ctypes.byref(pointer), ctypes.byref(length)
    ):
        return _fixed_file_version(version_dll, buffer)
    if not pointer.value:
        return _fixed_file_version(version_dll, buffer)
    lang, codepage = struct.unpack("<HH", ctypes.string_at(pointer.value, 4))

    def query(field: str) -> str | None:
        block = f"\\StringFileInfo\\{lang:04x}{codepage:04x}\\{field}"
        if not version_dll.VerQueryValueW(buffer, block, ctypes.byref(pointer), ctypes.byref(length)):
            return None
        if not pointer.value or length.value == 0:
            return None
        text = ctypes.wstring_at(pointer.value, length.value).rstrip("\x00").strip()
        return text or None

    file_version = query("FileVersion")
    product = query("ProductVersion")
    if not file_version and not product:
        return _fixed_file_version(version_dll, buffer)
    return _split_file_version(file_version or product or "", product)


def _fixed_file_version(version_dll: object, buffer: object) -> tuple[str, str] | None:
    """Read the fixed numeric version from a version-info block.

    Args:
        version_dll: ``ctypes.windll.version``.
        buffer: Buffer filled by ``GetFileVersionInfoW``.

    Returns:
        Version and build, or None.
    """
    import ctypes
    from ctypes import wintypes

    pointer = ctypes.c_void_p()
    length = wintypes.UINT()
    if not version_dll.VerQueryValueW(buffer, "\\", ctypes.byref(pointer), ctypes.byref(length)):
        return None
    if not pointer.value or length.value < 16:
        return None
    raw = ctypes.string_at(pointer.value, length.value)
    if len(raw) < 16:
        return None
    ms = int.from_bytes(raw[8:12], "little")
    ls = int.from_bytes(raw[12:16], "little")
    numbers = (ms >> 16, ms & 0xFFFF, ls >> 16, ls & 0xFFFF)
    build = ".".join(str(part) for part in numbers)
    return ".".join(str(part) for part in numbers[:3]), build


def _split_file_version(file_version: str, product: str | None) -> tuple[str, str]:
    """Split a Windows file version into a short version and a build.

    Args:
        file_version: FileVersion string, often four numbers.
        product: ProductVersion string, often three numbers.

    Returns:
        Version and build. Empty input is unknown.
    """
    build = file_version.strip() or "unknown"
    version = (product or "").strip()
    if not version:
        parts = [part for part in build.split(".") if part]
        version = ".".join(parts[:3]) if parts else "unknown"
    return version or "unknown", build


def _registry_version() -> tuple[str, str] | None:
    """Read a Serato DJ version from the Windows registry.

    Returns:
        Version and build, or None when the keys are absent. None off Windows.
    """
    if sys.platform != "win32":
        return None
    import winreg

    keys = (
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Serato\Serato DJ Pro"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Serato\Serato DJ Pro"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Serato\Serato DJ Pro"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Serato\Serato DJ"),
    )
    for hive, name in keys:
        try:
            with winreg.OpenKey(hive, name) as key:
                version = _reg_text(key, "DisplayVersion") or _reg_text(key, "Version")
                build = _reg_text(key, "Build") or _reg_text(key, "FileVersion") or version
                if version:
                    return _split_file_version(build or version, version)
        except OSError:
            continue
    return None


def _reg_text(key: object, name: str) -> str | None:
    """Read one string value from an open registry key.

    Args:
        key: Open ``winreg`` key.
        name: Value name.

    Returns:
        The text, or None.
    """
    import winreg

    try:
        value, _kind = winreg.QueryValueEx(key, name)
    except OSError:
        return None
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _read_protect() -> str:
    """Read ``library_protect``.

    Returns:
        ``on``, ``off``, or ``unknown``. Unknown covers a missing file, a
        missing key, and a file that is not a plist. The database is not
        checked for a lock.
    """
    override = os.environ.get("SERATO_LIBRARY_PREFERENCES")
    if override:
        return _protect_from_plist(Path(override))
    if not _using_live_library():
        return "unknown"
    return _protect_from_plist(Path.home() / "Library" / "Preferences" / "com.serato.seratodj.plist")


def _version_from_plist(path: Path) -> tuple[str, str]:
    """Read version keys from an Info.plist.

    Args:
        path: Plist file.

    Returns:
        Version and build, using ``unknown`` for anything unreadable.
    """
    data = _load_plist(path)
    if not isinstance(data, dict):
        return ("unknown", "unknown")
    version = data.get("CFBundleShortVersionString")
    build = data.get("CFBundleVersion")
    return (
        version if isinstance(version, str) and version else "unknown",
        build if isinstance(build, str) and build else "unknown",
    )


def _protect_from_plist(path: Path) -> str:
    """Read Protect Library from a preferences plist.

    Args:
        path: ``com.serato.seratodj.plist``.

    Returns:
        ``on`` for 1, ``off`` for 0, and ``unknown`` otherwise.
    """
    data = _load_plist(path)
    if not isinstance(data, dict) or "library_protect" not in data:
        return "unknown"
    value = data.get("library_protect")
    if value == 1:
        return "on"
    if value == 0:
        return "off"
    return "unknown"


def _load_plist(path: Path) -> object | None:
    """Load a plist, or return None when it cannot be read.

    Args:
        path: Plist file.

    Returns:
        The parsed object, or None.
    """
    try:
        with path.open("rb") as handle:
            return plistlib.load(handle)
    except (OSError, plistlib.InvalidFileException, ValueError, TypeError):
        return None


def _parsed_version(version: str) -> tuple[int, ...] | None:
    """Parse a Serato version that is only decimal numbers.

    Args:
        version: A version string such as ``4.1.0`` or ``5.0.0``.

    Returns:
        The numeric components, or None when the text is not a dotted
        number. ``v5.0`` and ``unknown`` are None.
    """
    if not _VERSION_RE.fullmatch(version):
        return None
    return tuple(int(part) for part in version.split("."))


def _is_serato_5(version: str) -> bool:
    """Return whether a version string is Serato 5 or newer.

    Args:
        version: CFBundleShortVersionString, or ``unknown``.

    Returns:
        True when the version is a dotted number and the first component
        is 5 or more. Anything else is not treated as Serato 5 here; the
        write gate blocks it as unknown.
    """
    parsed = _parsed_version(version)
    return parsed is not None and parsed[0] >= 5


def _using_live_library() -> bool:
    """Return whether this process is pointed at the real Serato library.

    Returns:
        True when ``library.MASTER`` is the live path.
    """
    import library

    return Path(library.MASTER).resolve() == Path(library.LIVE_MASTER).resolve()


def _library_status() -> dict[str, object]:
    """Return the library lock status.

    Returns:
        The status dict. A missing library reports that it is not open so a
        snapshot of a partial fixture can still be planned.
    """
    import library

    try:
        return library.status()
    except library.LibraryError:
        return {"open": False, "writable": True, "message": ""}


def _external_roots() -> list[Path]:
    """Find ``_Serato_`` folders on mounted volumes.

    Returns:
        Directories. The internal Music folder is not included.
    """
    roots: list[Path] = []
    candidates: list[Path] = []
    if sys.platform == "darwin":
        volumes = Path("/Volumes")
        if volumes.is_dir():
            candidates.extend(path / "_Serato_" for path in volumes.iterdir() if path.is_dir())
    elif sys.platform == "win32":
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            candidates.append(Path(f"{letter}:/") / "_Serato_")
    else:
        for base in (Path("/media"), Path("/mnt"), Path("/run/media")):
            if base.is_dir():
                for owner in base.iterdir():
                    if owner.is_dir():
                        candidates.extend(path / "_Serato_" for path in owner.iterdir() if path.is_dir())
                    candidates.append(owner / "_Serato_")
    music = (Path.home() / "Music" / "_Serato_").resolve()
    for path in candidates:
        try:
            if path.is_dir() and not path.is_symlink() and path.resolve() != music:
                roots.append(path)
        except OSError:
            continue
    return roots


def _volume_key(path: Path) -> str | None:
    """Return a stable volume id when the platform exposes one.

    Args:
        path: A directory on the volume.

    Returns:
        An id, or None when it cannot be read. The snapshot still has the
        drive path for this session.
    """
    try:
        stat = path.stat()
    except OSError:
        return None
    return f"dev-{stat.st_dev}"
