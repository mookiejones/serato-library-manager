#!/usr/bin/env python3
"""Read-only check that a Serato portable drive can stand alone at a gig.

The drive is a folder with ``_Serato_`` at its root. Crate files under
``Subcrates`` and ``SmartCrates`` are the list that travels with the
drive. Track paths are read with ``snapshots.parse_serato_bytes``, the
same chunk parser snapshots use for ``database V2`` and ``.crate`` files.
``database V2`` itself is not a crate: a track that appears only there
is not reported.

Serato Support, "Using a USB external hard drive for your portable
library" (read 2026-10-29),
https://support.serato.com/hc/en-us/articles/202304844-Using-a-USB-external-hard-drive-for-your-portable-library
says "IMPORTANT: Smart crates cannot be transferred to a portable library."
A ``.scrate`` file is reported once. Its rules are not resolved, and any
paths stored inside it are not treated as tracks on the drive.

Names are checked against the Windows and FAT rules in Microsoft's
"Naming Files, Paths, and Namespaces" (read 2026-10-29),
https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file
The characters ``\\ / : * ? " < > |``, a trailing space or period, and
the reserved device names (``CON``, ``PRN``, ``AUX``, ``NUL``,
``COM0``–``COM9``, ``LPT0``–``LPT9``, including an extension) are unsafe
on FAT32 and exFAT. ``MAX_PATH`` is 260 including the terminating NUL,
so the path text can be 259 characters
(https://learn.microsoft.com/en-us/windows/win32/fileio/maximum-file-path-limitation).
A FAT long name component can be 255 characters. FAT32 cannot store a
file larger than ``2**32 - 1`` bytes. That size check runs only when
the filesystem is detected, or supplied by the caller, as FAT.

Nothing in this module writes. Crate bytes are read with ``os.open``
and ``O_RDONLY``. Audio files are not opened; size comes from ``stat``.
The HTTP handler does not pass a filesystem override, so a request
cannot hide a FAT32 volume.
"""

from __future__ import annotations

import argparse
import ctypes
import os
import re
import stat
import subprocess
import sys
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import library
import snapshots


FINDING_KINDS = (
    "off_drive",
    "missing",
    "smart_crate",
    "unsafe_name",
    "path_length",
    "file_size",
)

# FAT32's largest file is one byte under 4 GiB.
FAT32_MAX_BYTES = 2**32 - 1
# MAX_PATH includes the NUL, so the characters of the path stop at 259.
WINDOWS_PATH_MAX = 259
COMPONENT_MAX = 255

_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{index}" for index in range(10)}
    | {f"LPT{index}" for index in range(10)}
)
_ILLEGAL = '\\/:*?"<>|'
_FAT = frozenset({"fat", "fat12", "fat16", "fat32", "vfat", "msdos"})
_KIND_ORDER = {kind: index for index, kind in enumerate(FINDING_KINDS)}
_LETTER = re.compile(r"^[A-Za-z]:[\\/]")
_UNC = re.compile(r"^(?:\\\\|//)[^\\/]+[\\/][^\\/]+")
_MOUNT_ESCAPE = re.compile(r"\\([0-7]{3})")
_EXCLUDED = frozenset(name.casefold() for name in snapshots.EXCLUDED_DIRS)
_COUNT_KEYS = (
    "tracks",
    "off_drive",
    "missing",
    "smart_crates",
    "unsafe_names",
    "path_length",
    "file_size",
)


@dataclass(frozen=True, slots=True)
class Finding:
    """One thing to fix on the laptop before the drive leaves.

    Attributes:
        kind: ``off_drive``, ``missing``, ``smart_crate``, ``unsafe_name``,
            ``path_length``, or ``file_size``.
        crate: Crate label. Nested crates use `` / ``.
        track: File name. Empty when the finding is the Smart Crate itself.
        path: Path stored in the crate. Empty for a Smart Crate.
        found: Where the file was found, when it exists off the drive.
        fix: What to change on the laptop.
    """

    kind: str
    crate: str
    track: str
    path: str
    found: str
    fix: str

    def to_dict(self) -> dict[str, object]:
        """Return the JSON object for this finding.

        Returns:
            The six fields, in contract order.
        """
        return {
            "kind": self.kind,
            "crate": self.crate,
            "track": self.track,
            "path": self.path,
            "found": self.found,
            "fix": self.fix,
        }


@dataclass(frozen=True, slots=True)
class CrateReport:
    """Counts for one crate.

    Attributes:
        name: Crate label.
        smart: True when the file is a ``.scrate``.
        tracks: Track entries checked. A Smart Crate contributes none.
        off_drive: Tracks found somewhere other than this drive.
        missing: Tracks not found on the drive or elsewhere.
        unsafe_names: Tracks whose stored name is unsafe on FAT32.
        path_length: Tracks whose path exceeds a Windows or FAT limit.
        file_size: Tracks larger than FAT32 can store.
    """

    name: str
    smart: bool
    tracks: int
    off_drive: int
    missing: int
    unsafe_names: int
    path_length: int
    file_size: int

    def to_dict(self) -> dict[str, object]:
        """Return the JSON object for this crate.

        Returns:
            The crate counts.
        """
        return {
            "name": self.name,
            "smart": self.smart,
            "tracks": self.tracks,
            "off_drive": self.off_drive,
            "missing": self.missing,
            "unsafe_names": self.unsafe_names,
            "path_length": self.path_length,
            "file_size": self.file_size,
        }


@dataclass(frozen=True, slots=True)
class ReadError:
    """A crate file or folder that could not be read.

    Attributes:
        crate: Crate label, or the folder name when the folder was skipped.
        message: What the DJ should know. No traceback.
    """

    crate: str
    message: str

    def to_dict(self) -> dict[str, str]:
        """Return the JSON object for this error.

        Returns:
            ``crate`` and ``message``.
        """
        return {"crate": self.crate, "message": self.message}


@dataclass(frozen=True, slots=True)
class DriveReport:
    """The whole check. Frozen. It holds no open file.

    Attributes:
        drive: Drive root that was checked.
        name: Short name, such as ``GIGDRIVE`` or ``E:``.
        filesystem: Detected filesystem, or None when it could not be read.
        ready: True when the drive is connected and nothing needs a fix.
        missing_drive: True when the drive path is not there.
        summary: The sentences a DJ can read without the finding list.
        counts: Totals across the crates that were checked.
        crates: One row per checked crate.
        findings: One row per fix, crate then kind then path.
        errors: Crates that could not be read. The drive is not ready.
    """

    drive: str
    name: str
    filesystem: str | None
    ready: bool
    missing_drive: bool
    summary: str
    counts: Mapping[str, int]
    crates: tuple[CrateReport, ...]
    findings: tuple[Finding, ...]
    errors: tuple[ReadError, ...]

    def to_dict(self) -> dict[str, object]:
        """Return the JSON object for this report.

        Returns:
            The contract documented in ``docs/architecture.md``.
        """
        return {
            "drive": self.drive,
            "name": self.name,
            "filesystem": self.filesystem,
            "ready": self.ready,
            "missing_drive": self.missing_drive,
            "summary": self.summary,
            "counts": {key: int(self.counts[key]) for key in _COUNT_KEYS},
            "crates": [crate.to_dict() for crate in self.crates],
            "findings": [finding.to_dict() for finding in self.findings],
            "errors": [error.to_dict() for error in self.errors],
        }


def is_fat_filesystem(name: str | None) -> bool:
    """Return whether a filesystem name cannot hold a file over 4 GB.

    Args:
        name: A detected or caller-supplied name. None and ``""`` are unknown.

    Returns:
        True for FAT12, FAT16, FAT32, ``vfat``, and ``msdos``. exFAT is false.
    """
    if name is None or name == "":
        return False
    return name.casefold() in _FAT


def filesystem_from_mounts(path: str, mounts: str) -> str | None:
    """Return the filesystem of the longest mount that contains ``path``.

    Args:
        path: Absolute POSIX path.
        mounts: ``/proc/mounts`` text. Mount points use octal escapes.

    Returns:
        The fstype, or None when no mount contains the path. A sibling
        such as ``/Volumes/GIGDRIVE-backup`` does not match
        ``/Volumes/GIGDRIVE``.
    """
    target = PurePosixPath(path)
    best_depth = -1
    best_type: str | None = None
    for line in mounts.splitlines():
        fields = line.split()
        if len(fields) < 3:
            continue
        mount = PurePosixPath(_unescape_mount(fields[1]))
        if target != mount and mount not in target.parents:
            continue
        depth = len(mount.parts)
        if depth > best_depth:
            best_depth = depth
            best_type = fields[2]
    return best_type


def detect_filesystem(path: Path) -> str | None:
    """Return the filesystem name for a directory, when this OS can say.

    Args:
        path: A directory that exists.

    Returns:
        A name such as ``FAT32``, ``vfat``, ``exfat``, or ``NTFS``. None
        when the OS does not say. Linux reads ``/proc/mounts`` and cannot
        tell FAT16 from FAT32; both arrive as ``vfat`` and both fail the
        4 GB check.
    """
    try:
        if os.name == "nt":
            return _windows_filesystem(path)
        if sys.platform == "darwin":
            return _darwin_filesystem(path)
        text = _read_bytes(Path("/proc/mounts")).decode("utf-8", "replace")
    except OSError:
        return None
    try:
        return filesystem_from_mounts(str(path.resolve()), text)
    except OSError:
        return None


def check_drive(
    drive: Path | str,
    crates: Sequence[str] | None = None,
    *,
    filesystem: str | None = None,
    exists: Callable[[Path], bool] | None = None,
) -> DriveReport:
    """Check one portable drive. Reads crate files. Does not write.

    Args:
        drive: Drive root, or the ``_Serato_`` directory on that drive.
        crates: Crate labels to check. A parent includes its subcrates.
            None, or an empty sequence, checks every crate.
        filesystem: Filesystem name to use instead of detection. The HTTP
            handler does not pass this. None detects. ``""`` means unknown.
        exists: How to ask whether an off-drive path is a file. None uses
            ``stat``, with a short timeout for a UNC path. Tests pass a
            stand-in for a drive letter this computer does not have.

    Returns:
        The report. A missing drive is a report with ``missing_drive``
        set, not an exception, and it does not create the folder.

    Raises:
        library.LibraryError: The folder is not a directory, it has no
            ``_Serato_`` directory, ``_Serato_`` is a shortcut, or a
            requested crate is not on the drive. Status 400 or 404.
    """
    root = _drive_path(drive)
    name = _volume_label(str(root))
    if not root.exists():
        return _empty_report(
            str(root),
            name,
            missing_drive=True,
            summary=f"{name} is not connected. Plug it in and check again.",
        )
    if not root.is_dir():
        raise library.LibraryError("Choose the drive itself, not a file.", 400)
    serato_root, serato = _serato_dir(root)
    name = _volume_label(str(serato_root))
    detected = detect_filesystem(serato_root) if filesystem is None else (filesystem or None)
    files, errors = _crate_files(serato)
    parsed = _parse_crates(serato, files, errors)
    wanted = [item.strip() for item in crates if item.strip()] if crates else []
    if wanted:
        labels = [item.label for item in parsed]
        unknown = _unknown_crates(labels, wanted)
        if unknown:
            raise library.LibraryError(f"{unknown[0]} is not a crate on this drive.", 404)
        parsed = tuple(item for item in parsed if _selected(item.label, wanted))
    probe = exists if exists is not None else _exists
    findings, crate_rows = _classify(serato_root, parsed, detected, probe)
    counts = _counts(crate_rows, findings)
    no_crates = not files and not errors
    summary = _summary(name, counts, missing_drive=False, no_crates=no_crates, errors=len(errors))
    ready = not findings and not errors
    return DriveReport(
        str(serato_root),
        name,
        detected,
        ready,
        False,
        summary,
        counts,
        crate_rows,
        findings,
        tuple(errors),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Print a drive check. Writes nothing.

    Args:
        argv: Arguments, without the program name. None reads the command line.

    Returns:
        0 when the drive is ready, 1 when it is not, 2 when the folder
        cannot be checked.
    """
    parser = argparse.ArgumentParser(description="Check a Serato portable drive. Reads only.")
    parser.add_argument("drive", help="Drive root, the folder that contains _Serato_")
    parser.add_argument(
        "--crate",
        action="append",
        default=None,
        help="Crate to check. Repeat to check more than one. The default is every crate.",
    )
    parser.add_argument("--json", action="store_true", help="Print the JSON report.")
    args = parser.parse_args(argv)
    try:
        report = check_drive(args.drive, args.crate)
    except library.LibraryError as exc:
        print(exc.message, file=sys.stderr)
        return 2
    if args.json:
        import json

        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(report.summary)
        for finding in report.findings:
            track = finding.track or finding.crate
            print(f"{finding.crate}\t{track}\t{finding.fix}")
        for error in report.errors:
            print(f"{error.crate}\t{error.message}", file=sys.stderr)
    return 0 if report.ready else 1


@dataclass(frozen=True, slots=True)
class _CrateFile:
    """One crate file after its paths have been read.

    Attributes:
        label: Display name.
        smart: True for a ``.scrate``.
        paths: Stored paths. Empty for a Smart Crate, whose rules are not read.
    """

    label: str
    smart: bool
    paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Hit:
    """Where a stored path landed.

    Attributes:
        kind: ``on_drive``, ``off_drive``, or ``missing``.
        found: Absolute path when the file was found.
        size: Byte size when ``stat`` succeeded.
    """

    kind: str
    found: str
    size: int | None


def _empty_report(drive: str, name: str, *, missing_drive: bool, summary: str) -> DriveReport:
    """Return a report with no crates.

    Args:
        drive: Drive path.
        name: Short name.
        missing_drive: True when the path is absent.
        summary: The sentence to show.

    Returns:
        A report with zero counts.
    """
    return DriveReport(
        drive,
        name,
        None,
        False,
        missing_drive,
        summary,
        {key: 0 for key in _COUNT_KEYS},
        (),
        (),
        (),
    )


def _drive_path(drive: Path | str) -> Path:
    """Return an absolute drive path. Does not create it.

    Args:
        drive: A path the caller passed. This is the drive the person
            chose on this computer. The server binds ``127.0.0.1`` and the
            check only reads.

    Returns:
        The expanded absolute path.

    Raises:
        library.LibraryError: The path contains a NUL, or it is a shortcut
            to another folder. Status 400.
    """
    text = os.fspath(drive)
    if "\x00" in text or not text.strip():
        raise library.LibraryError("Choose a drive.", 400)
    expanded = os.path.abspath(os.path.expanduser(text))
    normalized = os.path.realpath(expanded)
    # The leaf the caller named, after resolving shortcuts in its parents.
    # A leaf that is itself a shortcut to another folder does not start there.
    boundary = _caller_boundary(expanded)
    checked = normalized if normalized.endswith(os.sep) else normalized + os.sep
    if os.path.normcase(checked).startswith(os.path.normcase(boundary)):
        return Path(normalized)
    raise library.LibraryError("That drive path is a shortcut. The check will not follow it.", 400)


def _caller_boundary(expanded: str) -> str:
    """Return the folder a resolved drive path must stay inside.

    Args:
        expanded: Absolute path, with ``..`` collapsed and shortcuts not followed.

    Returns:
        The real path of the parent plus the leaf name, with a trailing
        separator. The filesystem root is itself.
    """
    trimmed = expanded.rstrip("\\/")
    parent = os.path.dirname(trimmed)
    name = os.path.basename(trimmed)
    if not trimmed or parent == trimmed:
        return expanded if expanded.endswith(os.sep) else expanded + os.sep
    expected = os.path.join(os.path.realpath(parent), name) if name else os.path.realpath(parent)
    return expected if expected.endswith(os.sep) else expected + os.sep


def _volume_label(raw: str) -> str:
    """Return the short drive name.

    Args:
        raw: A path string. Slashes may point either way.

    Returns:
        ``E:`` for a Windows drive root, the volume name for
        ``/Volumes``, ``/mnt``, ``/media``, and ``/run/media``, otherwise
        the last path component.
    """
    text = raw.replace("\\", "/").rstrip("/")
    letter = re.fullmatch(r"([A-Za-z]):", text)
    if letter:
        return letter.group(1).upper() + ":"
    parts = [part for part in text.split("/") if part]
    if len(parts) >= 2 and parts[0] == "Volumes":
        return parts[1]
    if len(parts) >= 2 and parts[0] == "mnt":
        return parts[1]
    if len(parts) >= 3 and parts[0] == "media":
        return parts[2]
    if len(parts) >= 4 and parts[0] == "run" and parts[1] == "media":
        return parts[3]
    if parts:
        return parts[-1]
    return raw or "Drive"


def _folded_component(name: str) -> str:
    """Fold a path component the way snapshots compare excluded names.

    Args:
        name: One path component.

    Returns:
        The name without a trailing dot, space, or alternate-data-stream
        suffix, case-folded.
    """
    return name.split(":", 1)[0].rstrip(" .").casefold()


def _is_serato_name(name: str) -> bool:
    """Return whether a directory name is exactly ``_Serato_``.

    Args:
        name: Directory name.

    Returns:
        True for ``_Serato_`` in any case, including a trailing dot or
        space. ``_Serato_-backup`` is false.
    """
    return _folded_component(name) == "_serato_"


def _excluded_name(name: str) -> bool:
    """Return whether a directory is Export Backups or Lexicon.

    Args:
        name: Directory name.

    Returns:
        True for those two names after the snapshot fold. A sibling such
        as ``Export Backups-extra`` is false.
    """
    return _folded_component(name) in _EXCLUDED


def _serato_dir(root: Path) -> tuple[Path, Path]:
    """Find the ``_Serato_`` directory on a drive.

    Args:
        root: Drive root, or the ``_Serato_`` directory itself.

    Returns:
        The drive root and the ``_Serato_`` directory.

    Raises:
        library.LibraryError: The folder is missing, or it is a shortcut.
            A shortcut is not followed.
    """
    if _is_serato_name(root.name):
        if root.is_symlink():
            raise library.LibraryError("The _Serato_ folder is a shortcut. The check will not follow it.", 400)
        if root.is_dir():
            return root.parent, root
    try:
        with os.scandir(root) as scan:
            entries = list(scan)
    except OSError as exc:
        raise library.LibraryError("That drive could not be read.", 400) from exc
    matches = [entry for entry in entries if _is_serato_name(entry.name)]
    for entry in matches:
        if entry.is_symlink():
            raise library.LibraryError("The _Serato_ folder is a shortcut. The check will not follow it.", 400)
    directories = [entry for entry in matches if entry.is_dir(follow_symlinks=False)]
    if not directories:
        raise library.LibraryError("This folder has no _Serato_ folder.", 404)
    exact = [entry for entry in directories if entry.name == "_Serato_"]
    chosen = exact[0] if exact else sorted(directories, key=lambda entry: entry.name)[0]
    return root, Path(chosen.path)


def _child_named(parent: Path, name: str) -> Path | None:
    """Return a direct child whose folded name matches.

    Args:
        parent: Directory to scan.
        name: Expected name, matched with the snapshot fold.

    Returns:
        The child, or None. An exact name wins over another fold.
    """
    folded = _folded_component(name)
    try:
        with os.scandir(parent) as scan:
            entries = [entry for entry in scan if _folded_component(entry.name) == folded]
    except OSError:
        return None
    if not entries:
        return None
    exact = [entry for entry in entries if entry.name == name]
    chosen = exact[0] if exact else sorted(entries, key=lambda entry: entry.name)[0]
    return Path(chosen.path)


def _crate_files(serato: Path) -> tuple[list[tuple[Path, str]], list[ReadError]]:
    """List crate files under Subcrates and SmartCrates.

    Args:
        serato: The ``_Serato_`` directory.

    Returns:
        ``(path, folder)`` pairs and errors for shortcut folders. Export
        Backups and Lexicon are not entered. ``database V2`` is not a crate.
    """
    found: list[tuple[Path, str]] = []
    errors: list[ReadError] = []
    for folder_name in ("Subcrates", "SmartCrates"):
        folder = _child_named(serato, folder_name)
        if folder is None:
            continue
        if folder.is_symlink():
            errors.append(ReadError(folder_name, f"{folder_name} is a shortcut. The check will not follow it."))
            continue
        _collect_crates(folder, folder, found, errors)
    found.sort(key=lambda item: item[0].as_posix().casefold())
    return found, errors


def _collect_crates(
    folder: Path,
    current: Path,
    found: list[tuple[Path, str]],
    errors: list[ReadError],
) -> None:
    """Walk one crate folder. Does not follow directory shortcuts.

    Args:
        folder: The Subcrates or SmartCrates directory. Labels are relative
            to this.
        current: Directory being listed.
        found: Collected crate files.
        errors: Shortcut and unreadable directories.
    """
    try:
        with os.scandir(current) as scan:
            entries = list(scan)
    except OSError:
        errors.append(ReadError(current.name, "This folder could not be read."))
        return
    for entry in sorted(entries, key=lambda item: item.name.casefold()):
        if _excluded_name(entry.name):
            continue
        path = Path(entry.path)
        if entry.is_dir(follow_symlinks=False):
            _collect_crates(folder, path, found, errors)
            continue
        if entry.is_symlink() and entry.is_dir():
            errors.append(ReadError(entry.name, f"{entry.name} is a shortcut. The check will not follow it."))
            continue
        suffix = Path(entry.name).suffix.casefold()
        if suffix not in {".crate", ".scrate"}:
            continue
        if entry.is_file(follow_symlinks=False) or entry.is_symlink():
            found.append((path, folder.name))


def _parse_crates(
    serato: Path,
    files: Sequence[tuple[Path, str]],
    errors: list[ReadError],
) -> tuple[_CrateFile, ...]:
    """Read crate paths. Smart Crate rules are not parsed.

    Args:
        serato: ``_Serato_`` directory. A shortcut crate file must stay inside it.
        files: Crate paths and the folder they were found under.
        errors: Unreadable files are appended here.

    Returns:
        One record per crate file that could be read. A ``.scrate`` has no
        track list, even when the file contains paths.
    """
    parsed: list[_CrateFile] = []
    for path, folder_name in files:
        folder = _child_named(serato, folder_name)
        if folder is None:
            continue
        label = _crate_label(folder, path)
        smart = path.suffix.casefold() == ".scrate"
        if smart:
            parsed.append(_CrateFile(label, True, ()))
            continue
        try:
            data = _read_crate(serato, path)
        except OSError:
            errors.append(ReadError(label, "This crate could not be read."))
            continue
        paths = tuple(snapshots.parse_serato_bytes(data))
        parsed.append(_CrateFile(label, False, paths))
    return tuple(parsed)


def _read_crate(serato: Path, path: Path) -> bytes:
    """Read a crate file that stays inside ``_Serato_``.

    Args:
        serato: ``_Serato_`` directory.
        path: Crate file.

    Returns:
        The file bytes.

    Raises:
        OSError: The file cannot be read, or a shortcut points outside
            ``_Serato_``.
    """
    if path.is_symlink():
        target = path.resolve()
        if not _contained(serato, target):
            raise OSError("shortcut leaves the Serato folder")
    return _read_bytes(path)


def _crate_label(folder: Path, path: Path) -> str:
    """Return the display name of a crate file.

    Args:
        folder: Subcrates or SmartCrates directory.
        path: Crate file inside it.

    Returns:
        Parents and the leaf joined with `` / ``. ``%%`` in the file name
        is a parent boundary, and so is a directory.
    """
    try:
        relative = path.relative_to(folder).as_posix()
    except ValueError:
        relative = path.name
    suffix = path.suffix
    if relative.casefold().endswith(suffix.casefold()):
        relative = relative[: -len(suffix)]
    parts: list[str] = []
    for segment in relative.split("/"):
        for piece in segment.split("%%"):
            if piece:
                parts.append(piece)
    return " / ".join(parts) if parts else "Crate"


def _selected(label: str, wanted: Sequence[str]) -> bool:
    """Return whether a crate label was requested.

    Args:
        label: Crate label.
        wanted: Requested names. A request for ``House`` includes
            ``House / Peak``.

    Returns:
        True when the label matches, or it sits under a requested crate.
    """
    folded = label.casefold()
    for name in wanted:
        item = name.casefold()
        if folded == item or folded.startswith(item + " / "):
            return True
    return False


def _unknown_crates(labels: Sequence[str], wanted: Sequence[str]) -> list[str]:
    """Return requested names that match no crate.

    Args:
        labels: Crate labels on the drive.
        wanted: Requested names.

    Returns:
        Names that are not a crate and not a parent of one. A request for
        ``House / Peak`` does not match a crate that is only named ``House``.
    """
    unknown: list[str] = []
    for name in wanted:
        if not any(_selected(label, (name,)) for label in labels):
            unknown.append(name)
    return unknown


def _classify(
    drive_root: Path,
    crates: Sequence[_CrateFile],
    filesystem: str | None,
    exists: Callable[[Path], bool],
) -> tuple[tuple[Finding, ...], tuple[CrateReport, ...]]:
    """Turn crate paths into findings.

    Args:
        drive_root: Drive root.
        crates: Parsed crates, already filtered.
        filesystem: Detected or supplied name. None skips the 4 GB check.
        exists: Off-drive existence probe.

    Returns:
        Findings and crate rows, both in a stable order.
    """
    cache: dict[Path, list[tuple[str, Path]]] = {}
    missing_parents: set[str] = set()
    resolved_root = drive_root.resolve()
    letters = _mounted_letters(drive_root)
    findings: list[Finding] = []
    rows: list[CrateReport] = []
    fat = is_fat_filesystem(filesystem)
    for crate in crates:
        counts = {key: 0 for key in ("tracks", "off_drive", "missing", "unsafe_names", "path_length", "file_size")}
        if crate.smart:
            findings.append(
                Finding(
                    "smart_crate",
                    crate.label,
                    "",
                    "",
                    "",
                    (
                        f'"{crate.label}" is a Smart Crate. Serato does not copy Smart Crates '
                        "to a portable library. On the laptop, make a normal crate with these "
                        "tracks and copy that crate to the drive."
                    ),
                )
            )
        seen: set[str] = set()
        for stored in crate.paths:
            if stored in seen:
                continue
            seen.add(stored)
            counts["tracks"] += 1
            hit = _locate(stored, drive_root, cache, exists, missing_parents, resolved_root, letters)
            track = _track_name(stored)
            if hit.kind == "off_drive":
                counts["off_drive"] += 1
                findings.append(
                    Finding(
                        "off_drive",
                        crate.label,
                        track,
                        stored,
                        hit.found,
                        (
                            f'Copy "{track}" onto this drive. It is in "{crate.label}", '
                            f"and the file on the laptop is {hit.found}."
                        ),
                    )
                )
            elif hit.kind == "missing":
                counts["missing"] += 1
                findings.append(
                    Finding(
                        "missing",
                        crate.label,
                        track,
                        stored,
                        "",
                        (
                            f'"{track}" in "{crate.label}" is not on this drive, and it was not '
                            "found on this computer. Restore the file on the laptop, then copy "
                            "it onto the drive."
                        ),
                    )
                )
            problems = _name_problems(stored)
            if problems:
                counts["unsafe_names"] += 1
                findings.append(
                    Finding(
                        "unsafe_name",
                        crate.label,
                        track,
                        stored,
                        hit.found,
                        (
                            f'Rename "{track}" on the laptop, then copy it onto the drive '
                            f'and update "{crate.label}". ' + " ".join(problems)
                        ),
                    )
                )
            length_note = _length_problem(stored)
            if length_note:
                counts["path_length"] += 1
                findings.append(
                    Finding(
                        "path_length",
                        crate.label,
                        track,
                        stored,
                        hit.found,
                        (
                            f'Shorten "{track}" on the laptop, then copy it onto the drive '
                            f'and update "{crate.label}". {length_note}'
                        ),
                    )
                )
            if fat and hit.size is not None and hit.size > FAT32_MAX_BYTES:
                counts["file_size"] += 1
                volume = filesystem if filesystem is not None else "FAT"
                findings.append(
                    Finding(
                        "file_size",
                        crate.label,
                        track,
                        stored,
                        hit.found,
                        (
                            f'"{track}" in "{crate.label}" is {hit.size} bytes. This drive is '
                            f"{volume}, which cannot store a file over 4 GB. On the laptop, "
                            "shorten the file or use an exFAT drive, then copy it again."
                        ),
                    )
                )
        rows.append(
            CrateReport(
                crate.label,
                crate.smart,
                counts["tracks"],
                counts["off_drive"],
                counts["missing"],
                counts["unsafe_names"],
                counts["path_length"],
                counts["file_size"],
            )
        )
    rows.sort(key=lambda row: row.name.casefold())
    findings.sort(
        key=lambda item: (
            item.crate.casefold(),
            _KIND_ORDER[item.kind],
            item.path.casefold(),
            item.track.casefold(),
        )
    )
    return tuple(findings), tuple(rows)


def _counts(crates: Sequence[CrateReport], findings: Sequence[Finding]) -> dict[str, int]:
    """Sum the report counts.

    Args:
        crates: Crate rows.
        findings: Findings. Smart Crates are counted from these.

    Returns:
        The seven totals.
    """
    totals = {key: 0 for key in _COUNT_KEYS}
    for crate in crates:
        totals["tracks"] += crate.tracks
        totals["off_drive"] += crate.off_drive
        totals["missing"] += crate.missing
        totals["unsafe_names"] += crate.unsafe_names
        totals["path_length"] += crate.path_length
        totals["file_size"] += crate.file_size
    totals["smart_crates"] = sum(1 for finding in findings if finding.kind == "smart_crate")
    return totals


def _summary(
    name: str,
    counts: Mapping[str, int],
    *,
    missing_drive: bool,
    no_crates: bool,
    errors: int,
) -> str:
    """Return the sentences at the top of the report.

    Args:
        name: Short drive name.
        counts: Totals.
        missing_drive: True when the drive path is absent.
        no_crates: True when ``_Serato_`` has no crate files.
        errors: How many crates could not be read.

    Returns:
        One or more sentences separated by a space.
    """
    if missing_drive:
        return f"{name} is not connected. Plug it in and check again."
    if no_crates and errors == 0:
        return "This drive has no crates."
    sentences: list[str] = []
    tracks = counts["tracks"]
    if counts["off_drive"] > 0:
        sentences.append(f"{counts['off_drive']} of {tracks} tracks are not on this drive.")
    if counts["missing"] > 0:
        sentences.append(f"{counts['missing']} of {tracks} tracks could not be found.")
    smart = counts["smart_crates"]
    if smart > 0:
        noun = "Smart Crate" if smart == 1 else "Smart Crates"
        sentences.append(f"{smart} {noun} will not copy to a portable library.")
    if counts["unsafe_names"] > 0:
        sentences.append(f"{counts['unsafe_names']} file names are not safe on FAT32.")
    if counts["path_length"] > 0:
        sentences.append(f"{counts['path_length']} paths are too long for a Windows drive.")
    if counts["file_size"] > 0:
        sentences.append(f"{counts['file_size']} files are over 4 GB for this drive.")
    if errors > 0:
        noun = "crate" if errors == 1 else "crates"
        sentences.append(f"{errors} {noun} could not be read.")
    if not sentences:
        return f"Every crate track on {name} is on this drive."
    return " ".join(sentences)


def _track_name(stored: str) -> str:
    """Return the file name from a stored path.

    Args:
        stored: Crate path.

    Returns:
        The last component, or ``(unnamed)`` when the path has none.
    """
    parts = _stored_parts(stored)
    if not parts:
        return "(unnamed)"
    return parts[-1]


def _stored_parts(stored: str) -> tuple[str, ...]:
    """Split a stored path into components, dropping the drive letter.

    Args:
        stored: Crate path. Slashes may point either way.

    Returns:
        Components. ``.`` is dropped. ``..`` is kept. A Windows drive
        letter is not a component.
    """
    text = stored.replace("\\", "/")
    parts = tuple(part for part in text.split("/") if part not in ("", "."))
    if parts and re.fullmatch(r"[A-Za-z]:", parts[0]):
        return parts[1:]
    return parts


def _name_problems(stored: str) -> list[str]:
    """Return FAT32 name problems for a stored path.

    Args:
        stored: Crate path.

    Returns:
        Sentences, in a stable order. A normal relative path is empty.
    """
    problems: list[str] = []
    seen_illegal: list[str] = []
    trailing = False
    reserved: list[str] = []
    for part in _stored_parts(stored):
        if part == "..":
            continue
        for char in _ILLEGAL:
            if char in part and char not in seen_illegal:
                seen_illegal.append(char)
        if part.endswith(" ") or part.endswith("."):
            trailing = True
        base = part.split(".", 1)[0].upper()
        if base in _RESERVED and base not in reserved:
            reserved.append(base)
    if seen_illegal:
        shown = " ".join(seen_illegal)
        problems.append(f"The name contains {shown}.")
    if trailing:
        problems.append("The name ends with a space or a period.")
    for base in reserved:
        problems.append(f"The name {base} is reserved on Windows.")
    return problems


def _length_problem(stored: str) -> str:
    """Return the path-length sentence, or empty when the path fits.

    Args:
        stored: Crate path.

    Returns:
        A sentence naming the limit that failed, or ``""``.
    """
    parts = _stored_parts(stored)
    longest = max((len(part) for part in parts), default=0)
    relative = "\\".join(parts)
    full = len("X:\\" + relative) if relative else len("X:\\")
    notes: list[str] = []
    if longest > COMPONENT_MAX:
        notes.append(
            f"A folder or file name is {longest} characters, and FAT32 allows {COMPONENT_MAX}."
        )
    if full > WINDOWS_PATH_MAX:
        notes.append(
            f"The Windows path is {full} characters, and Windows allows {WINDOWS_PATH_MAX}."
        )
    return " ".join(notes)


def _locate(
    stored: str,
    drive_root: Path,
    cache: dict[Path, list[tuple[str, Path]]],
    exists: Callable[[Path], bool],
    missing_parents: set[str],
    resolved_root: Path,
    letters: tuple[str, ...],
) -> _Hit:
    """Find a stored path on the drive or somewhere else.

    Args:
        stored: Crate path.
        drive_root: Drive root.
        cache: Directory listings already read.
        exists: Off-drive probe.
        missing_parents: Parents already known to be absent. Siblings under
            one of them are not statted again.
        resolved_root: ``drive_root`` resolved once for this check.
        letters: Other Windows drive letters, computed once for this check.

    Returns:
        On the drive, off the drive with the place it was found, or missing.
    """
    on_drive = _find_on_drive(stored, drive_root, cache, resolved_root)
    if on_drive is not None:
        if on_drive[0]:
            return _Hit("on_drive", str(on_drive[1]), _file_size(on_drive[1]))
        return _Hit("off_drive", str(on_drive[1]), _file_size(on_drive[1]))
    outside = _first_outside(stored, resolved_root, exists, missing_parents, letters)
    if outside is not None:
        return _Hit("off_drive", str(outside), _file_size(outside))
    return _Hit("missing", "", None)


def _find_on_drive(
    stored: str,
    drive_root: Path,
    cache: dict[Path, list[tuple[str, Path]]],
    resolved_root: Path,
) -> tuple[bool, Path] | None:
    """Walk a stored path under the drive.

    Args:
        stored: Crate path.
        drive_root: Drive root.
        cache: Directory listings.
        resolved_root: ``drive_root`` resolved once for this check.

    Returns:
        ``(True, path)`` when the file is inside the drive.
        ``(False, path)`` when the crate path is on the drive but a shortcut
        points at a file outside it. None when the path is not on the drive.
    """
    parts = _on_drive_parts(stored, drive_root, resolved_root)
    if parts is None:
        return None
    current = drive_root
    root_resolved = resolved_root
    for part in parts:
        if part == "..":
            try:
                if current.resolve() == root_resolved:
                    return None
            except OSError:
                return None
            current = current.parent
            continue
        match = _pick(_listing(current, cache), part)
        if match is None:
            return None
        current = match
    try:
        info = os.lstat(current)
    except OSError:
        return None
    if stat.S_ISLNK(info.st_mode):
        try:
            target = current.resolve()
        except OSError:
            return None
        if not target.is_file():
            return None
        return (_contained(drive_root, target), target)
    if not stat.S_ISREG(info.st_mode):
        return None
    if not _contained(drive_root, current):
        return (False, current)
    return (True, current)


def _on_drive_parts(stored: str, drive_root: Path, resolved_root: Path) -> tuple[str, ...] | None:
    """Return the components to walk under the drive, or None.

    Args:
        stored: Crate path.
        drive_root: Drive root.
        resolved_root: ``drive_root`` resolved once for this check.

    Returns:
        Relative components when the stored path belongs on this volume.
        An absolute path on another volume returns None. A relative path
        is always walked here first.
    """
    if _is_unc(stored) or _LETTER.match(stored) or stored.replace("\\", "/").startswith("/"):
        if _is_unc(stored) or (_LETTER.match(stored) and os.name != "nt"):
            return None
        candidate = Path(stored.replace("\\", "/")) if not _LETTER.match(stored) else Path(stored)
        if not _contained(drive_root, candidate, resolved_root):
            return None
        try:
            relative = candidate.absolute().relative_to(resolved_root)
        except ValueError:
            return None
        return _stored_parts(relative.as_posix())
    return _stored_parts(stored)


def _first_outside(
    stored: str,
    resolved_root: Path,
    exists: Callable[[Path], bool],
    missing_parents: set[str],
    letters: tuple[str, ...],
) -> Path | None:
    """Return the first off-drive place this path exists.

    Args:
        stored: Crate path.
        resolved_root: Drive root, already resolved.
        exists: Probe.
        missing_parents: Parents already known to be absent.
        letters: Other Windows drive letters.

    Returns:
        The path, or None. Relative paths are tried at the filesystem root
        and under the home directory, which is where a Mac crate stores a
        laptop track (no leading slash). The search does not scan the disk.
        Once a parent is absent, later tracks under it are not statted.
    """
    for candidate in _outside_candidates(stored, resolved_root, letters):
        parent = os.fspath(candidate.parent)
        if parent in missing_parents:
            continue
        try:
            present = exists(candidate)
        except OSError:
            present = False
        if present:
            return candidate
        if not _node_exists(candidate.parent):
            missing_parents.add(parent)
    return None


def _outside_candidates(stored: str, resolved_root: Path, letters: tuple[str, ...]) -> tuple[Path, ...]:
    """Return off-drive paths worth a single stat.

    Args:
        stored: Crate path.
        resolved_root: Drive root, already resolved.
        letters: Other Windows drive letters.

    Returns:
        Candidates that are not inside the drive. Order is the stored
        absolute path, the Mac root form, the home directory, then other
        Windows drive letters.
    """
    found: list[Path] = []
    normalized = stored.replace("\\", "/")
    if _LETTER.match(stored) or _is_unc(stored) or normalized.startswith("/"):
        found.append(Path(stored) if _LETTER.match(stored) else Path(normalized))
    else:
        stripped = normalized.lstrip("/")
        if stripped:
            found.append(Path("/") / stripped)
            found.append(Path.home() / stripped)
            found.extend(_other_drive_letters(stripped, letters))
    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in found:
        if _path_inside(resolved_root, candidate):
            continue
        key = os.fspath(candidate)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return tuple(unique)


def _mounted_letters(drive_root: Path) -> tuple[str, ...]:
    """Return mounted Windows drive letters other than this drive.

    Args:
        drive_root: Drive being checked.

    Returns:
        Letters such as ``D:``. Empty when this is not Windows. The list is
        read once per check.
    """
    if os.name != "nt":
        return ()
    listdrives = getattr(os, "listdrives", None)
    if listdrives is None:
        return ()
    own = drive_root.drive.upper()
    found: list[str] = []
    for drive in listdrives():
        if len(drive) < 2 or drive[1] != ":":
            continue
        letter = drive[:2].upper()
        if letter != own and letter not in found:
            found.append(letter)
    return tuple(found)


def _other_drive_letters(relative: str, letters: tuple[str, ...]) -> tuple[Path, ...]:
    """Return the same relative path on other Windows drive letters.

    Args:
        relative: Volume-relative path with forward slashes.
        letters: Mounted letters other than the drive being checked.

    Returns:
        One path per letter.
    """
    text = relative.replace("/", "\\").lstrip("\\")
    return tuple(Path(letter + "\\" + text) for letter in letters)


def _path_inside(resolved_root: Path, candidate: Path) -> bool:
    """Return whether a candidate is lexically inside the drive.

    Args:
        resolved_root: Drive root, already resolved.
        candidate: Possible file.

    Returns:
        True when the candidate is the drive or a path under it. A Windows
        drive-letter path is outside a POSIX drive. A missing path is not
        resolved, so this does not stat once per track.
    """
    raw = os.fspath(candidate)
    if _LETTER.match(raw) and os.name != "nt":
        return False
    try:
        lexical = candidate if candidate.is_absolute() else candidate.absolute()
    except OSError:
        return False
    if lexical != resolved_root and resolved_root not in lexical.parents:
        return False
    return _contained(resolved_root, candidate, resolved_root)


def _contained(root: Path, candidate: Path, resolved_root: Path | None = None) -> bool:
    """Return whether a path stays inside a directory.

    Args:
        root: Directory that must contain the candidate.
        candidate: Path to test.
        resolved_root: ``root`` already resolved. None resolves it.

    Returns:
        True when the resolved candidate is the root or a child of it.
        A sibling whose name only starts with the root name is outside.
        A path that is lexically outside is rejected without resolving it.
    """
    try:
        root_resolved = resolved_root if resolved_root is not None else root.resolve()
        lexical = candidate if candidate.is_absolute() else candidate.absolute()
    except OSError:
        return False
    if lexical != root_resolved and root_resolved not in lexical.parents:
        return False
    try:
        resolved = candidate.resolve()
    except OSError:
        return False
    return resolved == root_resolved or root_resolved in resolved.parents


def _listing(directory: Path, cache: dict[Path, list[tuple[str, Path]]]) -> list[tuple[str, Path]]:
    """Return the names in a directory, cached for this check.

    Args:
        directory: Directory to list.
        cache: Cache keyed by the directory.

    Returns:
        Name and path pairs. An unreadable directory is empty.
    """
    cached = cache.get(directory)
    if cached is not None:
        return cached
    rows: list[tuple[str, Path]] = []
    try:
        with os.scandir(directory) as scan:
            for entry in scan:
                rows.append((entry.name, Path(entry.path)))
    except OSError:
        rows = []
    cache[directory] = rows
    return rows


def _pick(entries: Sequence[tuple[str, Path]], want: str) -> Path | None:
    """Return the directory entry for a component.

    Args:
        entries: Names in the parent.
        want: Component from the crate. Matching is case-insensitive, and
            an exact match wins.

    Returns:
        The path, or None.
    """
    folded = want.casefold()
    matches = [path for name, path in entries if name.casefold() == folded]
    if not matches:
        return None
    for path in matches:
        if path.name == want:
            return path
    matches.sort(key=lambda item: item.name)
    return matches[0]


def _node_exists(path: Path) -> bool:
    """Return whether a path is present, file or directory.

    Args:
        path: Path to test. A UNC path that does not answer within a second
            and a half counts as absent.

    Returns:
        True when ``stat`` succeeds.
    """
    raw = os.fspath(path)
    if raw.startswith("\\\\") or raw.startswith("//"):
        answered: list[bool] = []

        def probe() -> None:
            try:
                os.stat(path)
                answered.append(True)
            except OSError:
                answered.append(False)

        worker = threading.Thread(target=probe, daemon=True)
        worker.start()
        worker.join(1.5)
        if worker.is_alive() or not answered:
            return False
        return answered[0]
    try:
        os.stat(path)
    except OSError:
        return False
    return True


def _exists(path: Path) -> bool:
    """Return whether a path is a regular file.

    Args:
        path: File to test.

    Returns:
        True when ``stat`` reports a regular file. A UNC path that does
        not answer within a second and a half counts as absent.
    """
    raw = os.fspath(path)
    if raw.startswith("\\\\") or raw.startswith("//"):
        return _exists_timed(path, 1.5)
    return _is_regular(path)


def _exists_timed(path: Path, timeout: float) -> bool:
    """Return whether a path exists before a timeout.

    Args:
        path: File to test.
        timeout: Seconds to wait.

    Returns:
        True when the file is there in time.
    """
    answered: list[bool] = []

    def probe() -> None:
        answered.append(_is_regular(path))

    worker = threading.Thread(target=probe, daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive() or not answered:
        return False
    return answered[0]


def _is_regular(path: Path) -> bool:
    """Return whether ``stat`` sees a regular file.

    Args:
        path: File to test.

    Returns:
        True for a regular file. A directory, a missing path, and an
        unreadable path are false.
    """
    try:
        return stat.S_ISREG(os.stat(path).st_mode)
    except OSError:
        return False


def _file_size(path: Path) -> int | None:
    """Return the size of a file without reading it.

    Args:
        path: File to measure.

    Returns:
        The size in bytes, or None when it cannot be read.
    """
    try:
        return os.stat(path).st_size
    except OSError:
        return None


def _is_unc(stored: str) -> bool:
    """Return whether a stored path is a UNC path.

    Args:
        stored: Crate path.

    Returns:
        True when the path starts with a host and a share.
    """
    return _UNC.match(stored) is not None


def _read_bytes(path: Path) -> bytes:
    """Read a file with ``O_RDONLY``.

    Args:
        path: File to read.

    Returns:
        The bytes.

    Raises:
        OSError: The file cannot be opened for reading.
    """
    flags = os.O_RDONLY
    cloexec = getattr(os, "O_CLOEXEC", 0)
    binary = getattr(os, "O_BINARY", 0)
    fd = os.open(path, flags | cloexec | binary)
    try:
        chunks: list[bytes] = []
        while True:
            block = os.read(fd, 1024 * 1024)
            if not block:
                break
            chunks.append(block)
        return b"".join(chunks)
    finally:
        os.close(fd)


def _unescape_mount(value: str) -> str:
    """Unescape a ``/proc/mounts`` path.

    Args:
        value: Mount point with octal escapes such as ``\\040``.

    Returns:
        The path.
    """
    return _MOUNT_ESCAPE.sub(lambda match: chr(int(match.group(1), 8)), value)


def _windows_filesystem(path: Path) -> str | None:
    """Return the Windows filesystem name for a path.

    Args:
        path: A file or directory on the volume.

    Returns:
        The filesystem name, such as ``FAT32`` or ``NTFS``, or None.
    """
    root = path.anchor or str(path)
    if len(root) == 2 and root[1] == ":":
        root += "\\"
    buffer = ctypes.create_unicode_buffer(256)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetVolumeInformationW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_wchar_p,
        ctypes.c_uint32,
    ]
    kernel32.GetVolumeInformationW.restype = ctypes.c_int
    ok = kernel32.GetVolumeInformationW(root, None, 0, None, None, None, buffer, 256)
    if not ok:
        return None
    name = buffer.value.strip()
    return name or None


def _darwin_filesystem(path: Path) -> str | None:
    """Return the macOS filesystem name for a path.

    Args:
        path: A file or directory on the volume.

    Returns:
        The ``stat -f %T`` name, such as ``msdos`` or ``exfat``, or None.
    """
    try:
        completed = subprocess.run(
            ["stat", "-f", "%T", os.fspath(path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    name = completed.stdout.strip()
    return name or None


if __name__ == "__main__":
    raise SystemExit(main())
