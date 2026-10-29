"""Move, rename, replace, and trash audio without dropping Serato crates.

Serato stores the file path on the library row. Cue points stay in the
audio file. This module rewrites path columns in ``master.sqlite`` and in
the mirrored location database after the file is in its new place, in one
transaction. If that write fails, the files are put back. If a file move
fails, the database transaction is rolled back.

A preview uses the same path checks and does not copy the database. The
save copies the database first. An interrupted save leaves a journal in
``Library/Backups`` that the next save finishes or undoes, and only while
Serato is quit.

Two checks run before a new name is used. The name itself cannot be a
path. The resolved path must also stay inside the chosen folder, which is
what stops a shortcut from landing outside that folder.
"""

from __future__ import annotations

import errno
import json
import logging
import os
import shutil
import sqlite3
import sys
import time
import uuid
from collections.abc import Mapping
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

import library
import telemetry
from tags import copy_serato_geob, plan_serato_geob

logger = logging.getLogger("serato.files")

_ACTIONS = frozenset({"rename", "move", "move_folder", "replace", "delete"})
_AUDIO = frozenset(
    {
        ".mp3",
        ".wav",
        ".wave",
        ".aiff",
        ".aif",
        ".aifc",
        ".flac",
        ".m4a",
        ".aac",
        ".ogg",
        ".oga",
        ".mp4",
        ".wma",
        ".alac",
    }
)
_NAME_RE_MAX = 255
_LIST_CAP = 2000
_SCAN_CAP = 5000
_CHANGE_CAP = 200
_FILE_CAP = 500
_TREE_CAP = 50000
_JOURNAL = "file-ops-journal.json"
_TRASH_ENV = "SERATO_LIBRARY_TRASH"
FO_DELETE = 3
FOF_SILENT = 0x0004
FOF_NOCONFIRMATION = 0x0010
FOF_ALLOWUNDO = 0x0040
FOF_NOERRORUI = 0x0400
_SKIP_TABLES = frozenset(
    {
        "connection",
        "location",
        "lock",
        "serato",
        "sqlite_sequence",
        "sqlite_stat1",
    }
)


class _Refuse(Exception):
    """A file change the user can see, raised before anything is written."""

    def __init__(self, message: str) -> None:
        """Store the sentence returned to the page.

        Args:
            message: Refusal text. It does not include a traceback.
        """
        super().__init__(message)
        self.message = message


class _Expand(Exception):
    """A directory rename crossed drives and must be copied file by file."""

    def __init__(self, moves: list[dict[str, str]]) -> None:
        """Store the per-file moves that replace one directory rename.

        Args:
            moves: Journal move records.
        """
        super().__init__("expand")
        self.moves = moves


@dataclass
class FileChange:
    """One path the library should follow."""

    source: Path
    dest: Path
    asset_ids: tuple[int, ...] = ()
    external: tuple[tuple[int, int], ...] = ()
    crates: tuple[str, ...] = ()
    spaces: tuple[str, ...] = ()
    missing: bool = False


@dataclass
class Removal:
    """One file to take out of the library and, when it exists, the Trash."""

    path: Path | None
    name: str
    asset_ids: tuple[int, ...] = ()
    external: tuple[tuple[int, int], ...] = ()
    crates: tuple[str, ...] = ()
    spaces: tuple[str, ...] = ()
    missing: bool = False


@dataclass
class Plan:
    """A checked file change that has not been performed."""

    action: str
    ok: bool
    error: str | None = None
    changes: list[FileChange] = field(default_factory=list)
    removals: list[Removal] = field(default_factory=list)
    moves: list[dict[str, str]] = field(default_factory=list)
    directories: list[tuple[Path, Path]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    cues: str | None = None
    cue_source: Path | None = None
    cue_dest: Path | None = None
    summary: str = ""
    browse: str | None = None
    trash: list[str] = field(default_factory=list)


def list_directory(path: str | None) -> dict[str, object]:
    """List one folder for the file browser.

    Args:
        path: Folder to open. Empty selects the home directory.

    Returns:
        The folder, its parent, and up to 2000 entries. Shortcuts are
        listed and are not followed.

    Raises:
        LibraryError: If the path is not a real folder.
    """
    directory = _list_root(path)
    info = library.status()
    entries, truncated = _scan(directory)
    indexed = _index_assets()
    listed: list[dict[str, object]] = []
    for entry in entries:
        assets = indexed.get(entry["path"], []) if entry["kind"] == "file" else []
        listed.append(
            {
                "name": entry["name"],
                "kind": entry["kind"],
                "path": str(entry["path"]),
                "audio": entry["audio"],
                "assets": assets,
                "in_library": bool(assets),
            }
        )
    parent = None if directory.parent == directory else str(directory.parent)
    return {
        "path": str(directory),
        "parent": parent,
        "entries": listed,
        "truncated": truncated,
        "writable": bool(info.get("writable")),
        "serato": info,
    }


def plan(payload: Mapping[str, object]) -> dict[str, object]:
    """Describe a file change without writing it.

    The path checks match the save. Serato being open is included here so
    the page can show the refusal before confirm. The database is not
    copied, and an interrupted journal is not repaired here.

    Args:
        payload: JSON body with an action and the paths that action uses.

    Returns:
        A preview dict. ``ok`` is false when the save would refuse.

    Raises:
        LibraryError: If the body is not a file action.
    """
    built = _build(payload)
    body = _public(built)
    info = library.status()
    body["serato"] = info
    body["writable"] = bool(info.get("writable"))
    body["preview"] = True
    if info.get("open"):
        body["ok"] = False
        body["error"] = str(info.get("message"))
    if _journal_path().is_file():
        note = "A previous file change will be finished or put back when you confirm."
        warnings = list(body["warnings"])
        warnings.append(note)
        body["warnings"] = warnings
        body["warning"] = " ".join(str(item) for item in warnings)
    return body


def execute(payload: Mapping[str, object]) -> dict[str, object]:
    """Perform a file change that the page has confirmed.

    Serato must be quit. The database is copied first. Files move next.
    The database update is one transaction. A failure puts the files back
    and rolls the database back.

    Args:
        payload: The same body as ``plan``, with ``confirm`` set to true.

    Returns:
        The result, including a summary and any cue warning.

    Raises:
        SeratoOpen: If Serato holds the library.
        LibraryError: If the change is refused or cannot be finished.
    """
    if payload.get("confirm") is not True:
        raise library.LibraryError("Confirm the change before it is saved.")
    info = library.status()
    if info.get("open"):
        raise library.SeratoOpen(info)
    import snapshots

    blocked = snapshots.write_block_message()
    if blocked:
        raise library.LibraryError(blocked, 409)
    if recover_interrupted() == "blocked":
        raise library.LibraryError(
            "An interrupted file change does not match the library. Restore the copy in Library/Backups."
        )
    built = _build(payload)
    if not built.ok:
        raise library.LibraryError(built.error or "That change was not saved.")
    import safe_write

    extra = [change.source for change in built.changes]
    extra.extend(removal.path for removal in built.removals if removal.path is not None)
    holder: dict[str, dict[str, object]] = {}

    def undo_files() -> None:
        """Put moved files back from the in-memory journal.

        The journal file may already have been removed. The dict still
        describes the moves.
        """
        journal = holder.get("journal")
        if journal is None:
            return
        _undo_journal(journal)

    with safe_write.session(
        built.action,
        _file_target(built),
        extra,
        on_rollback=undo_files,
    ) as write:
        journal = _journal_for(built)
        holder["journal"] = journal
        _write_journal(journal)
        cue_status = built.cues
        try:
            cue_status = _perform_files(built, journal)
            _commit_database(built, journal)
            journal["done"] = True
            _write_journal(journal)
            write.mark_committed()
        except library.SeratoOpen:
            _undo_and_drop(journal)
            raise
        except library.LibraryError:
            _undo_and_drop(journal)
            raise
        except Exception as exc:
            logger.exception("File change failed")
            _undo_and_drop(journal)
            raise library.LibraryError(
                "The files could not be changed. Nothing was left halfway."
            ) from exc
        _finish_journal(journal)
        _delete_journal()
    related_notes = _retarget_related(built)
    _capture(built, cue_status)
    body = _public(built)
    body["preview"] = False
    body["ok"] = True
    body["cues"] = cue_status
    if built.action == "replace" and cue_status:
        detail = _cue_detail(cue_status)
        warnings = [
            str(item)
            for item in body["warnings"]
            if str(item) != "Cue points will be copied onto the new file."
        ]
        if detail not in warnings:
            warnings.append(detail)
        body["warnings"] = warnings
        body["warning"] = " ".join(warnings) or None
    if related_notes:
        warnings = [str(item) for item in body["warnings"]]
        for note in related_notes:
            if note not in warnings:
                warnings.append(note)
        body["warnings"] = warnings
        body["warning"] = " ".join(warnings) or None
    return body


def recover_interrupted() -> str:
    """Finish or undo a file change that stopped between the disk and the database.

    Returns:
        ``clear`` when there is no journal or it was resolved.
        ``blocked`` when the database and the journal disagree; the files
        are left as they are.

    Serato being open leaves the journal untouched.
    """
    path = _journal_path()
    if not path.is_file():
        return "clear"
    try:
        info = library.status()
    except (library.LibraryError, sqlite3.Error):
        return "blocked"
    if info.get("open"):
        return "clear"
    try:
        journal = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.exception("File journal could not be read")
        return "blocked"
    if not isinstance(journal, dict):
        return "blocked"
    state = _expect_state(journal.get("expect"))
    try:
        if state == "mixed":
            logger.error(
                "An interrupted file change does not match the library. Restore the copy in Library/Backups."
            )
            return "blocked"
        if state == "new" or (state == "empty" and journal.get("done") is True):
            _finish_journal(journal)
            logger.info("Finished an interrupted file change")
        else:
            _undo_journal(journal)
            logger.info("Put an interrupted file change back")
        _delete_journal()
    except (OSError, library.LibraryError, sqlite3.Error):
        logger.exception("Could not repair an interrupted file change")
        return "blocked"
    return "clear"


def _list_root(path: str | None) -> Path:
    """Resolve the folder a listing is allowed to open.

    Args:
        path: Requested folder, or empty for the home directory.

    Returns:
        A real directory.

    Raises:
        LibraryError: If the path is missing, not a directory, or a shortcut.
    """
    if path is None or path == "":
        return Path.home().resolve()
    if not isinstance(path, str) or "\x00" in path or len(path) > 4096:
        raise library.LibraryError("That request is not valid.")
    # Normalize first, then keep only an absolute path on its own drive.
    # Filesystem checks happen after that, so a relative request cannot climb out.
    normalized = os.path.normpath(os.path.abspath(path))
    drive, _rest = os.path.splitdrive(normalized)
    root = drive + os.sep if drive else os.path.abspath(os.sep)
    if not normalized.startswith(root):
        raise library.LibraryError("That folder could not be read.", 404)
    directory = Path(normalized)
    if directory.is_symlink():
        raise library.LibraryError("Shortcuts are left alone.")
    try:
        resolved = directory.resolve(strict=False)
    except OSError as exc:
        raise library.LibraryError("That folder could not be read.", 404) from exc
    if not resolved.is_dir():
        raise library.LibraryError("That folder could not be read.", 404)
    return resolved


def _is_backup_root(directory: Path) -> bool:
    """Return whether a listing is the library backup folder.

    Args:
        directory: Folder being scanned.

    Returns:
        True when ``directory`` is ``Library/Backups`` beside the master
        database. An unreadable path is not that folder.
    """
    try:
        return directory.resolve() == _backups().resolve()
    except OSError:
        return False


def _hide_incomplete_backup(name: str, path: Path, kind: str) -> bool:
    """Return whether a backup listing must omit this entry.

    Args:
        name: Directory entry name.
        path: Path of that entry.
        kind: ``dir``, ``file``, or ``link`` from the scan.

    Returns:
        True for a directory under ``Library/Backups`` that
        :func:`library.is_complete` rejects, when the name is a backup
        folder or the entry contains the incomplete marker. Other files,
        including the file-ops journal, stay visible.
    """
    if kind != "dir":
        return False
    if library._is_staging_name(name) or library._is_failed_name(name):
        return True
    if (path / library.BACKUP_INCOMPLETE_NAME).exists():
        return True
    if (path / library.BACKUP_COMPLETE_NAME).exists() and not library.is_complete(path):
        return True
    return False


def _scan(directory: Path) -> tuple[list[dict[str, object]], bool]:
    """Read one folder without following shortcuts.

    Args:
        directory: Real directory to scan.

    Returns:
        Entry dicts and whether the scan stopped early.

    Raises:
        LibraryError: If the folder cannot be read.
    """
    found: list[dict[str, object]] = []
    truncated = False
    backup_root = _is_backup_root(directory)
    try:
        with os.scandir(directory) as scanner:
            for entry in scanner:
                if len(found) >= _SCAN_CAP:
                    truncated = True
                    break
                kind = "link" if entry.is_symlink() else "dir" if entry.is_dir(follow_symlinks=False) else "file"
                path = Path(entry.path)
                if backup_root and _hide_incomplete_backup(entry.name, path, kind):
                    continue
                audio = kind == "file" and Path(entry.name).suffix.lower() in _AUDIO
                found.append(
                    {
                        "name": entry.name,
                        "kind": kind,
                        "path": Path(entry.path),
                        "audio": audio,
                    }
                )
    except OSError as exc:
        raise library.LibraryError("That folder could not be read.", 404) from exc
    found.sort(key=lambda item: (str(item["kind"]) == "file", str(item["kind"]) == "link", str(item["name"]).casefold()))
    if len(found) > _LIST_CAP:
        return found[:_LIST_CAP], True
    return found, truncated


def _index_assets() -> dict[Path, list[int]]:
    """Map resolved audio paths to asset ids.

    Returns:
        Paths that are on the asset table. A missing database yields an
        empty map so the folder can still be listed.
    """
    indexed: dict[Path, list[int]] = {}
    try:
        conn_cm = closing(library.read_conn())
    except library.LibraryError:
        return indexed
    with conn_cm as conn:
        if not _has(conn, "main", "asset"):
            return indexed
        for row in _asset_rows(conn, "main"):
            resolved = resolve_stored(str(row.get("portable_id") or ""))
            if resolved is None:
                continue
            indexed.setdefault(resolved, []).append(int(row["id"]))
    return indexed


def _build(payload: Mapping[str, object]) -> Plan:
    """Check one request and return the plan, or a refusal.

    Args:
        payload: JSON body.

    Returns:
        A plan. ``ok`` is false when the files would not change.

    Raises:
        LibraryError: If the action or the types are not valid.
    """
    action = payload.get("action")
    if not isinstance(action, str) or action not in _ACTIONS:
        raise library.LibraryError("That file action is not available.")
    try:
        with closing(library.read_conn()) as conn:
            rows = _asset_rows(conn, "main") if _has(conn, "main", "asset") else []
            if action == "rename":
                return _plan_rename(payload, rows, conn)
            if action == "move":
                return _plan_move(payload, rows, conn)
            if action == "move_folder":
                return _plan_folder(payload, rows, conn)
            if action == "replace":
                return _plan_replace(payload, rows, conn)
            return _plan_delete(payload, rows, conn)
    except _Refuse as exc:
        return _failed(action, exc.message)


def _plan_rename(
    payload: Mapping[str, object],
    rows: list[dict[str, object]],
    conn: sqlite3.Connection,
) -> Plan:
    """Plan a new name in the same folder.

    Args:
        payload: Request with ``path`` and ``name``.
        rows: Asset rows.
        conn: Read connection, used to name crates.

    Returns:
        The rename plan.
    """
    src = _real_file(_as_path(payload.get("path")))
    name = _validate_filename(payload.get("name"))
    dest = _contained(src.parent, name)
    if name == src.name:
        raise _Refuse("That file already has this name.")
    if dest.exists() and not _same_file(src, dest):
        raise _Refuse("A file already has that name.")
    _guard_target(dest)
    change = _change_for(src, dest, rows, missing=False, conn=conn)
    summary = _summary("rename", [change], [])
    return Plan(
        action="rename",
        ok=True,
        changes=[change],
        moves=[{"src": str(src), "dst": str(dest), "kind": "rename"}],
        summary=summary,
        browse=str(src.parent),
    )


def _plan_move(
    payload: Mapping[str, object],
    rows: list[dict[str, object]],
    conn: sqlite3.Connection,
) -> Plan:
    """Plan moving files into an existing folder.

    Args:
        payload: Request with ``paths`` and ``destination``.
        rows: Asset rows.
        conn: Read connection, used to name crates.

    Returns:
        The move plan.
    """
    paths = _path_list(payload.get("paths"))
    if not paths:
        raise _Refuse("Choose files to move.")
    if len(paths) > _FILE_CAP:
        raise _Refuse("Choose fewer files at once.")
    destination = _real_dir(_as_path(payload.get("destination")))
    names: list[str] = []
    changes: list[FileChange] = []
    moves: list[dict[str, str]] = []
    for raw in paths:
        src = _real_file(_as_path(raw))
        if src.parent == destination:
            raise _Refuse("That file is already in this folder.")
        name = _validate_filename(src.name)
        names.append(name)
        dest = _contained(destination, name)
        if dest.exists() and not _same_file(src, dest):
            raise _Refuse("A file already has that name.")
        _guard_target(dest)
        changes.append(_change_for(src, dest, rows, missing=False, conn=conn))
        moves.append({"src": str(src), "dst": str(dest), "kind": "rename"})
    if len(names) != len(set(names)):
        raise _Refuse("Two of those files have the same name.")
    return Plan(
        action="move",
        ok=True,
        changes=changes,
        moves=moves,
        summary=_summary("move", changes, []),
        browse=str(destination),
    )


def _plan_folder(
    payload: Mapping[str, object],
    rows: list[dict[str, object]],
    conn: sqlite3.Connection,
) -> Plan:
    """Plan moving one folder and every library path inside it.

    Args:
        payload: Request with ``path`` and ``destination``.
        rows: Asset rows.
        conn: Read connection, used for crate names.

    Returns:
        The folder plan. A shortcut inside the folder refuses the move.
    """
    src = _real_dir(_as_path(payload.get("path")))
    _guard_tree(src)
    destination = _real_dir(_as_path(payload.get("destination")))
    _validate_filename(src.name)
    dest = _contained(destination, src.name)
    if dest == src:
        raise _Refuse("That folder is already there.")
    if src in dest.parents:
        raise _Refuse("A folder cannot be moved into itself.")
    if dest.exists():
        raise _Refuse("A file already has that name.")
    _guard_target(dest)
    _iter_files(src)
    changes: list[FileChange] = []
    for row, resolved in _assets_under(rows, src):
        relative = Path(".") if resolved == src else resolved.relative_to(src)
        new_path = dest if resolved == src else dest / relative
        missing = not resolved.exists() or resolved.is_dir()
        if resolved.is_file():
            missing = False
        changes.append(
            _change_for(resolved, new_path, [row], missing=missing, conn=conn, matched=[row])
        )
    return Plan(
        action="move_folder",
        ok=True,
        changes=changes,
        moves=[{"src": str(src), "dst": str(dest), "kind": "rename"}],
        directories=[(src, dest)],
        summary=_summary("move_folder", changes, []),
        browse=str(dest),
    )


def _plan_replace(
    payload: Mapping[str, object],
    rows: list[dict[str, object]],
    conn: sqlite3.Connection,
) -> Plan:
    """Plan pointing an existing track at another audio file.

    Args:
        payload: Request with ``replacement`` and either ``path`` or ``asset_id``.
        rows: Asset rows.
        conn: Read connection.

    Returns:
        The replace plan. The old file stays on disk.
    """
    replacement = _real_file(_as_path(payload.get("replacement")))
    _guard_target(replacement)
    selected = _replace_sources(payload, rows)
    if not selected:
        raise _Refuse("Choose a file that is in the library.")
    old_ids = {int(row["id"]) for row in selected}
    for other in _assets_at(rows, replacement):
        if int(other["id"]) not in old_ids:
            raise _Refuse("Another library track already uses that file.")
    source_path = resolve_stored(str(selected[0].get("portable_id") or ""))
    if source_path is not None and source_path == replacement:
        raise _Refuse("That file is already this track.")
    warnings: list[str] = []
    cues: str | None = "skipped"
    cue_source: Path | None = None
    if source_path is not None and source_path.is_file() and not source_path.is_symlink():
        cue_source = source_path
        decision = plan_serato_geob(source_path, replacement)
        cues = str(decision["status"])
        if cues == "copied":
            warnings.append("Cue points will be copied onto the new file.")
        else:
            warnings.append(str(decision["detail"]))
    else:
        warnings.append("The old file is not on disk, so its cue points were not copied.")
        cues = "skipped"
    changes = [
        _change_for(
            source_path or replacement,
            replacement,
            selected,
            missing=cue_source is None,
            conn=conn,
            matched=selected,
        )
    ]
    return Plan(
        action="replace",
        ok=True,
        changes=changes,
        warnings=warnings,
        cues=cues,
        cue_source=cue_source,
        cue_dest=replacement,
        summary=_summary("replace", changes, warnings),
        browse=str(replacement.parent),
    )


def _plan_delete(
    payload: Mapping[str, object],
    rows: list[dict[str, object]],
    conn: sqlite3.Connection,
) -> Plan:
    """Plan moving files to the Trash and removing their library rows.

    Args:
        payload: Request with ``paths``.
        rows: Asset rows.
        conn: Read connection.

    Returns:
        The delete plan. Folders are refused.
    """
    paths = _path_list(payload.get("paths"))
    if not paths:
        raise _Refuse("Choose files to delete.")
    if len(paths) > _FILE_CAP:
        raise _Refuse("Choose fewer files at once.")
    removals: list[Removal] = []
    trash: list[str] = []
    for raw in paths:
        path = _as_path(raw)
        if path.is_symlink():
            raise _Refuse("Shortcuts are left alone.")
        if path.is_dir():
            raise _Refuse("Choose files to delete. Folders stay.")
        if path.exists():
            src = _real_file(path)
            matched = _assets_at(rows, src)
            crates, spaces = _membership(conn, [int(row["id"]) for row in matched])
            removals.append(
                Removal(
                    path=src,
                    name=src.name,
                    asset_ids=tuple(int(row["id"]) for row in matched),
                    external=_externals(matched),
                    crates=crates,
                    spaces=spaces,
                    missing=False,
                )
            )
            trash.append(str(src))
        else:
            resolved = path.resolve(strict=False)
            matched = _assets_at(rows, resolved)
            if not matched:
                raise _Refuse("That file is not on disk.")
            _guard_target(resolved)
            crates, spaces = _membership(conn, [int(row["id"]) for row in matched])
            removals.append(
                Removal(
                    path=resolved,
                    name=resolved.name,
                    asset_ids=tuple(int(row["id"]) for row in matched),
                    external=_externals(matched),
                    crates=crates,
                    spaces=spaces,
                    missing=True,
                )
            )
    parent = removals[0].path.parent if removals and removals[0].path is not None else None
    count = len(removals)
    if count == 1:
        summary = "Move this file to the Trash and remove it from the library and its crates."
    else:
        summary = f"Move {count} files to the Trash and remove them from the library and their crates."
    return Plan(
        action="delete",
        ok=True,
        removals=removals,
        trash=trash,
        summary=summary,
        browse=str(parent) if parent is not None else None,
        warnings=[
            "Play history stays. The file leaves the library, its crates, and Prepare."
        ],
    )


def _replace_sources(
    payload: Mapping[str, object], rows: list[dict[str, object]]
) -> list[dict[str, object]]:
    """Find the library rows a replace should keep.

    Args:
        payload: Request body.
        rows: Asset rows.

    Returns:
        Matching asset dicts. Empty when nothing in the library matches.
    """
    if "asset_id" in payload and payload.get("asset_id") is not None:
        try:
            asset_id = int(str(payload.get("asset_id")))
        except (TypeError, ValueError) as exc:
            raise library.LibraryError("That request is not valid.") from exc
        return [row for row in rows if int(row["id"]) == asset_id]
    if "path" not in payload:
        raise library.LibraryError("That request is not valid.")
    raw = payload.get("path")
    path = _as_path(raw)
    if path.is_symlink():
        raise _Refuse("Shortcuts are left alone.")
    resolved = path.resolve(strict=False) if not path.exists() else _real_file(path)
    return _assets_at(rows, resolved)


def _failed(action: str, message: str) -> Plan:
    """Build a refusal plan.

    Args:
        action: Requested action.
        message: Sentence for the page.

    Returns:
        A plan with ``ok`` false.
    """
    return Plan(action=action, ok=False, error=message, summary=message)


def _public(plan: Plan) -> dict[str, object]:
    """Convert a plan to the JSON the page reads.

    Args:
        plan: Checked plan.

    Returns:
        A dict. At most 200 changes are included. ``more`` counts the rest.
    """
    changes: list[dict[str, object]] = []
    for change in plan.changes:
        changes.append(
            {
                "from": str(change.source),
                "to": str(change.dest),
                "effect": "move",
                "assets": list(change.asset_ids),
                "crates": list(change.crates),
                "spaces": list(change.spaces),
                "missing": change.missing,
            }
        )
    for removal in plan.removals:
        changes.append(
            {
                "from": "" if removal.path is None else str(removal.path),
                "to": "",
                "effect": "trash",
                "assets": list(removal.asset_ids),
                "crates": list(removal.crates),
                "spaces": list(removal.spaces),
                "missing": removal.missing,
            }
        )
    shown = changes[:_CHANGE_CAP]
    warnings = list(plan.warnings)
    return {
        "ok": plan.ok,
        "action": plan.action,
        "needs_confirm": True,
        "summary": plan.summary,
        "error": plan.error,
        "changes": shown,
        "more": max(0, len(changes) - len(shown)),
        "count": len(changes),
        "warnings": warnings,
        "warning": " ".join(warnings) or None,
        "cues": plan.cues,
        "browse": plan.browse,
    }


def _summary(action: str, changes: list[FileChange], warnings: list[str]) -> str:
    """Describe a plan in one or two sentences.

    Args:
        action: File action.
        changes: Path updates.
        warnings: Extra sentences. They are not repeated here.

    Returns:
        Text for the confirm dialog. ``warnings`` is accepted so callers
        can pass the cue note through without changing this sentence.
    """
    del warnings
    library_n = sum(1 for change in changes if change.asset_ids)
    missing_n = sum(1 for change in changes if change.missing)
    if action == "rename":
        text = f"Rename {_count(len(changes), 'file', 'files')}. {_count(library_n, 'library track keeps', 'library tracks keep')} its crates."
        if library_n != 1:
            text = text.replace(" its crates.", " their crates.")
    elif action == "move":
        text = (
            f"Move {_count(len(changes), 'file', 'files')}. "
            f"{_count(library_n, 'library track keeps', 'library tracks keep')} "
            f"{'its' if library_n == 1 else 'their'} crates."
        )
    elif action == "move_folder":
        text = (
            "Move this folder. "
            f"{_count(library_n, 'library track keeps', 'library tracks keep')} "
            f"{'its' if library_n == 1 else 'their'} crates."
        )
    elif action == "replace":
        text = "Point this track at the new file. Crates, history, and the other fields stay on this track."
    else:
        text = "Move the file to the Trash and remove it from the library and its crates."
    if missing_n:
        text += f" {_count(missing_n, 'stored path changes', 'stored paths change')} even though the file is not on disk."
    return text


def _count(number: int, singular: str, plural: str) -> str:
    """Format a count with the matching noun.

    Args:
        number: How many.
        singular: Noun phrase for one.
        plural: Noun phrase for any other count.

    Returns:
        The count and the noun.
    """
    noun = singular if number == 1 else plural
    return f"{number} {noun}"


def _journal_for(plan: Plan) -> dict[str, object]:
    """Build the journal written before the first file changes.

    Args:
        plan: Checked plan.

    Returns:
        A JSON-ready dict. Paths are included because the journal stays
        on this computer and is deleted after a successful save.
    """
    paths: list[dict[str, object]] = []
    absent: list[int] = []
    for change in plan.changes:
        portable = to_portable(change.dest)
        for asset_id in change.asset_ids:
            paths.append({"id": asset_id, "portable_id": portable})
    for removal in plan.removals:
        absent.extend(removal.asset_ids)
    return {
        "version": 1,
        "action": plan.action,
        "moves": [dict(move) for move in plan.moves],
        "trash": [],
        "cue_backup": None,
        "expect": {"paths": paths, "absent": absent},
        "done": False,
        "directories": [[str(old), str(new)] for old, new in plan.directories],
    }


def _perform_files(plan: Plan, journal: dict[str, object]) -> str | None:
    """Move, trash, or copy cue tags. The database is still unchanged.

    Args:
        plan: Checked plan.
        journal: Journal dict updated in place and on disk.

    Returns:
        The cue status for a replace, otherwise the planned cue status.

    Raises:
        LibraryError: If a file cannot be moved or trashed.
    """
    if plan.action == "replace":
        return _perform_cues(plan, journal)
    if plan.action == "delete":
        _perform_trash(plan, journal)
        return plan.cues
    _perform_moves(journal)
    return plan.cues


def _perform_cues(plan: Plan, journal: dict[str, object]) -> str | None:
    """Copy cue tags when the plan said that was safe.

    Args:
        plan: Replace plan.
        journal: Journal that records the pre-image until the database commits.

    Returns:
        The status from the copy, or the planned status when nothing was written.
    """
    if plan.cues != "copied" or plan.cue_source is None or plan.cue_dest is None:
        return plan.cues
    backup = _cue_hold(plan.cue_dest)
    journal["cue_backup"] = {"file": str(plan.cue_dest), "backup": str(backup)}
    _write_journal(journal)
    try:
        result = copy_serato_geob(plan.cue_source, plan.cue_dest)
    except OSError:
        _restore_cue(journal)
        return "failed"
    status = str(result["status"])
    if status != "copied":
        _restore_cue(journal)
        return status if status in {"kept", "skipped", "unsupported", "failed"} else "failed"
    return "copied"


def _perform_trash(plan: Plan, journal: dict[str, object]) -> None:
    """Move each existing file to the Trash and record where it went.

    Args:
        plan: Delete plan.
        journal: Journal updated after each file so a crash can put it back.

    Raises:
        LibraryError: If a file cannot be trashed. Earlier files stay in
            the journal for the caller to restore.
    """
    records = journal["trash"]
    if not isinstance(records, list):
        raise library.LibraryError("The file could not be moved to the Trash.")
    for raw in plan.trash:
        record = trash_file(Path(raw))
        records.append(record)
        _write_journal(journal)


def _perform_moves(journal: dict[str, object]) -> None:
    """Move every journalled path, expanding a cross-drive folder if needed.

    Args:
        journal: Journal whose ``moves`` list may grow.

    Raises:
        LibraryError: If a move cannot be finished.
    """
    index = 0
    moves = journal["moves"]
    if not isinstance(moves, list):
        raise library.LibraryError("The file could not be moved. Nothing was changed.")
    while index < len(moves):
        move = moves[index]
        if not isinstance(move, dict):
            raise library.LibraryError("The file could not be moved. Nothing was changed.")
        try:
            _attempt_move(move, journal)
        except _Expand as exc:
            moves[index : index + 1] = exc.moves
            _write_journal(journal)
            continue
        index += 1


def _attempt_move(move: dict[str, object], journal: dict[str, object]) -> None:
    """Perform one journal move.

    Args:
        move: A src, dst, and kind record.
        journal: Journal rewritten before a cross-drive copy.

    Raises:
        LibraryError: If the file cannot be moved.
        _Expand: If a directory rename has to become per-file copies.
    """
    src = Path(str(move.get("src")))
    dst = Path(str(move.get("dst")))
    kind = str(move.get("kind") or "rename")
    if kind == "drop-tree":
        if src.exists():
            shutil.rmtree(src)
        return
    if kind == "copy":
        _copy_unlink(src, dst)
        return
    if dst.exists() and not _same_file(src, dst):
        raise library.LibraryError("A file already has that name.")
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_symlink() or (dst.exists() and dst.is_symlink()):
        raise library.LibraryError("Shortcuts are left alone.")
    if src.is_dir():
        try:
            _iter_files(src)
        except _Refuse as exc:
            raise library.LibraryError(exc.message) from exc
    try:
        os.rename(src, dst)
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise library.LibraryError("The file could not be moved. Nothing was changed.") from exc
        if src.is_dir():
            raise _Expand(_expand_dir_copy(src, dst)) from exc
        move["kind"] = "copy"
        _write_journal(journal)
        _copy_unlink(src, dst)


def _expand_dir_copy(src: Path, dst: Path) -> list[dict[str, str]]:
    """List a cross-drive folder move as file copies plus a cleanup.

    Args:
        src: Folder that is still in place.
        dst: Folder that does not exist yet.

    Returns:
        Journal move records.
    """
    records: list[dict[str, str]] = []
    for file in _iter_files(src):
        records.append(
            {
                "src": str(file),
                "dst": str(dst / file.relative_to(src)),
                "kind": "copy",
            }
        )
    records.append({"src": str(src), "dst": str(dst), "kind": "drop-tree"})
    return records


def _copy_unlink(src: Path, dst: Path) -> None:
    """Copy one file and remove the source only after the sizes match.

    Args:
        src: Existing file.
        dst: New path. Parent directories are created.

    Raises:
        LibraryError: If the copy does not match or the file is a shortcut.
    """
    if src.is_symlink() or src.is_dir():
        raise library.LibraryError("The file could not be moved. Nothing was changed.")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst, follow_symlinks=False)
    if not dst.is_file() or dst.stat().st_size != src.stat().st_size:
        dst.unlink(missing_ok=True)
        raise library.LibraryError("The copy did not match, so the file was left in place.")
    src.unlink()


def _commit_database(plan: Plan, journal: dict[str, object]) -> None:
    """Apply path updates or deletions and commit master and location databases together.

    Args:
        plan: Checked plan.
        journal: Unused except to keep the call next to the journal the
            caller already wrote. The expect block was stored before this.

    Raises:
        LibraryError: If a location database cannot be updated.
        sqlite3.Error: If the commit fails. The caller puts the files back.
    """
    del journal
    import safe_write

    active = safe_write.current_session()
    if active is not None:
        _expect_file_plan(active, plan)
    conn = library.begin_write()
    schemas: dict[Path, str] = {}
    try:
        schemas = _attach(conn)
        if plan.action == "delete":
            _purge_all(conn, schemas, plan)
        else:
            exact = {change.source: change.dest for change in plan.changes}
            _rewrite(conn, "main", exact, plan.directories)
            for schema in schemas.values():
                _rewrite(conn, schema, exact, plan.directories)
            _rewrite_history(conn, plan.changes)
        _commit(conn)
    except Exception:
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        raise
    finally:
        for schema in schemas.values():
            try:
                conn.execute(f"DETACH DATABASE {_q(schema)}")
            except sqlite3.Error:
                pass
        conn.close()


def _file_target(plan: Plan) -> str:
    """Return the file name a person would recognize for this change.

    Args:
        plan: Checked plan.

    Returns:
        The destination or removal name. Several files are joined, up to three.
    """
    names = [change.dest.name for change in plan.changes]
    if not names:
        names = [removal.name for removal in plan.removals]
    if not names:
        return plan.action
    shown = names[:3]
    if len(names) > 3:
        shown.append(f"and {len(names) - 3} more")
    return ", ".join(shown)


def _expect_file_plan(session: safe_write.Session, plan: Plan) -> None:
    """Register the path check for a file change.

    Args:
        session: The write session that will open the temporary copy.
        plan: Checked plan. Delete expects the asset rows to be gone.
            Other actions expect each asset's file name and portable id.
    """
    import safe_write as safe

    if plan.action == "delete":
        ids = tuple(asset_id for removal in plan.removals for asset_id in removal.asset_ids)

        def check_gone(copied: sqlite3.Connection, ids: tuple[int, ...] = ids) -> None:
            """Fail when a deleted track is still in the library.

            Args:
                copied: Read-only connection to the temporary database copy.
                ids: Asset ids that should be gone.

            Raises:
                VerifyMismatch: If an asset row remains.
            """
            for asset_id in ids:
                row = copied.execute("SELECT COUNT(*) FROM asset WHERE id = ?", (asset_id,)).fetchone()
                if row is None or int(row[0]) != 0:
                    raise safe.VerifyMismatch("A deleted track is still in the library.")

        session.check(check_gone)
        return
    expected = tuple(
        (asset_id, change.dest.name, to_portable(change.dest))
        for change in plan.changes
        for asset_id in change.asset_ids
    )

    def check_paths(
        copied: sqlite3.Connection,
        expected: tuple[tuple[int, str, str], ...] = expected,
    ) -> None:
        """Fail when a moved track does not store its new path.

        Args:
            copied: Read-only connection to the temporary database copy.
            expected: Asset id, file name, and portable id.

        Raises:
            VerifyMismatch: If the row is missing or still has the old path.
        """
        for asset_id, name, portable in expected:
            row = copied.execute(
                "SELECT file_name, portable_id FROM asset WHERE id = ?",
                (asset_id,),
            ).fetchone()
            if row is None or row[0] != name or row[1] != portable:
                raise safe.VerifyMismatch("The saved file path does not match.")

    session.check(check_paths)


def _commit(conn: sqlite3.Connection) -> None:
    """Commit one write transaction.

    Args:
        conn: Connection inside a transaction. Tests replace this function
            when they need the commit itself to fail.
    """
    conn.commit()


def _attach(conn: sqlite3.Connection) -> dict[Path, str]:
    """Attach each allowed location database.

    Args:
        conn: Open master write connection.

    Returns:
        Resolved location path to the attached schema name.

    Raises:
        LibraryError: If a connected database cannot be attached.
    """
    attached: dict[Path, str] = {}
    index = 0
    for path in library._location_paths(conn).values():
        if not path.is_file() or not library._mirror_allowed(path):
            continue
        resolved = path.resolve()
        if resolved in attached:
            continue
        schema = f"loc{index}"
        index += 1
        try:
            conn.execute(f"ATTACH DATABASE ? AS {_q(schema)}", (str(resolved),))
        except sqlite3.Error as exc:
            raise library.LibraryError(
                "The drive database could not be updated. Nothing was changed."
            ) from exc
        attached[resolved] = schema
    return attached


def _rewrite(
    conn: sqlite3.Connection,
    schema: str,
    exact: dict[Path, Path],
    directories: list[tuple[Path, Path]],
) -> None:
    """Rewrite path columns whose stored value points at a moved file.

    Args:
        conn: Write connection.
        schema: ``main`` or an attached schema name.
        exact: Resolved old file to its new path.
        directories: Folders that moved, used for other path columns.
    """
    now = int(time.time())
    revision = _bump_revision(conn, schema)
    for table in _tables(conn, schema):
        columns = _table_columns(conn, schema, table)
        path_columns = [name for name in columns if _is_path_column(name)]
        if not path_columns:
            continue
        keys = _primary_key(conn, schema, table)
        if not keys:
            continue
        selected = [*keys, *path_columns]
        if "file_name" in columns and "file_name" not in selected:
            selected.append("file_name")
        rows = conn.execute(
            f"SELECT {', '.join(_q(name) for name in selected)} FROM {_q(schema)}.{_q(table)}"
        ).fetchall()
        for row in rows:
            updates: dict[str, object] = {}
            new_path: Path | None = None
            for name in path_columns:
                value = row[name]
                if not isinstance(value, str) or value == "":
                    continue
                mapped = _map_stored(value, exact, directories)
                if mapped is None:
                    continue
                updates[name] = to_portable(mapped)
                if name.lower() == "portable_id":
                    new_path = mapped
            if new_path is not None and "file_name" in columns:
                updates["file_name"] = new_path.name
            if not updates:
                continue
            if table == "asset" and new_path is not None:
                if new_path.is_file():
                    if "is_missing" in columns:
                        updates["is_missing"] = 0
                    if "file_size" in columns:
                        try:
                            updates["file_size"] = new_path.stat().st_size
                        except OSError:
                            pass
                elif "is_missing" in columns:
                    updates["is_missing"] = 1
                if "time_modified" in columns:
                    updates["time_modified"] = now
                if revision is not None and "revision" in columns:
                    updates["revision"] = revision
            assignments = ", ".join(f"{_q(name)} = ?" for name in updates)
            where = " AND ".join(f"{_q(name)} = ?" for name in keys)
            params = [*updates.values(), *[row[name] for name in keys]]
            conn.execute(
                f"UPDATE {_q(schema)}.{_q(table)} SET {assignments} WHERE {where}",
                params,
            )


def _rewrite_history(conn: sqlite3.Connection, changes: list[FileChange]) -> None:
    """Point history rows at a file's new name.

    Args:
        conn: Master write connection.
        changes: Path updates that include asset ids.
    """
    if not _has(conn, "main", "history_entry"):
        return
    columns = _table_columns(conn, "main", "history_entry")
    if "asset_id" not in columns:
        return
    name_column = "file_name" if "file_name" in columns else "filename" if "filename" in columns else ""
    for change in changes:
        if not name_column or change.source.name == change.dest.name:
            continue
        for asset_id in change.asset_ids:
            conn.execute(
                f"UPDATE history_entry SET {_q(name_column)} = ? WHERE asset_id = ?",
                (change.dest.name, asset_id),
            )


def _purge_all(
    conn: sqlite3.Connection, schemas: dict[Path, str], plan: Plan
) -> None:
    """Remove library rows for a delete, including the mirrored asset.

    Args:
        conn: Master write connection with location databases attached.
        schemas: Location path to schema name.
        plan: Delete plan.
    """
    locations = {path.resolve(): schema for path, schema in schemas.items()}
    by_location = {path.resolve(): path for path in library._location_paths(conn).values()}
    del by_location
    path_schema = {path.resolve(): schema for path, schema in schemas.items()}
    location_paths = library._location_paths(conn)
    for removal in plan.removals:
        for asset_id in removal.asset_ids:
            _clear_history(conn, asset_id)
            _purge_asset(conn, "main", asset_id)
        for location_id, external_id in removal.external:
            path = location_paths.get(location_id)
            schema = path_schema.get(path.resolve()) if path is not None else None
            if schema is None:
                continue
            _purge_asset(conn, schema, external_id)
    del locations


def _clear_history(conn: sqlite3.Connection, asset_id: int) -> None:
    """Keep a play record and drop the link to a deleted asset when the column allows it.

    Args:
        conn: Master write connection.
        asset_id: Asset id being removed.
    """
    if not _has(conn, "main", "history_entry"):
        return
    if "asset_id" not in _table_columns(conn, "main", "history_entry"):
        return
    if _notnull(conn, "main", "history_entry", "asset_id"):
        return
    conn.execute("UPDATE history_entry SET asset_id = NULL WHERE asset_id = ?", (asset_id,))


def _purge_asset(conn: sqlite3.Connection, schema: str, asset_id: int) -> None:
    """Delete one asset and its crate and space membership.

    Args:
        conn: Write connection.
        schema: Database schema name.
        asset_id: Asset id in that database.
    """
    tables = set(_tables(conn, schema))
    if "space_asset" in tables and "asset_id" in _table_columns(conn, schema, "space_asset"):
        space_ids = [
            int(row[0])
            for row in conn.execute(
                f"SELECT id FROM {_q(schema)}.space_asset WHERE asset_id = ?",
                (asset_id,),
            ).fetchall()
        ]
        if space_ids and "container_asset" in tables:
            container_columns = _table_columns(conn, schema, "container_asset")
            if "space_asset_id" in container_columns:
                marks = ",".join("?" for _ in space_ids)
                conn.execute(
                    f"DELETE FROM {_q(schema)}.container_asset WHERE space_asset_id IN ({marks})",
                    space_ids,
                )
        conn.execute(
            f"DELETE FROM {_q(schema)}.space_asset WHERE asset_id = ?",
            (asset_id,),
        )
    if "container_asset" in tables and "asset_id" in _table_columns(conn, schema, "container_asset"):
        conn.execute(
            f"DELETE FROM {_q(schema)}.container_asset WHERE asset_id = ?",
            (asset_id,),
        )
    for table in ("dj_asset_metadata",):
        if table in tables and "asset_id" in _table_columns(conn, schema, table):
            conn.execute(
                f"DELETE FROM {_q(schema)}.{_q(table)} WHERE asset_id = ?",
                (asset_id,),
            )
    if "asset" in tables:
        conn.execute(f"DELETE FROM {_q(schema)}.asset WHERE id = ?", (asset_id,))


def _map_stored(
    stored: str,
    exact: dict[Path, Path],
    directories: list[tuple[Path, Path]],
) -> Path | None:
    """Map one stored path onto its new location.

    Args:
        stored: Value from a path column.
        exact: File moves.
        directories: Folder moves.

    Returns:
        The new path, or None when this value is not part of the change.
    """
    resolved = resolve_stored(stored)
    if resolved is None:
        return None
    if resolved in exact:
        return exact[resolved]
    for old, new in directories:
        if resolved == old or old in resolved.parents:
            suffix = Path(".") if resolved == old else resolved.relative_to(old)
            return new if suffix == Path(".") else new / suffix
    return None


def _undo_and_drop(journal: dict[str, object]) -> None:
    """Put files back and remove the journal.

    Args:
        journal: The journal for the change that failed.

    Raises:
        LibraryError: If the files cannot be put back.
    """
    try:
        _undo_journal(journal)
    except (OSError, library.LibraryError) as exc:
        logger.exception("Could not put files back")
        raise library.LibraryError(
            "The files could not be put back. Restore the copy in Library/Backups."
        ) from exc
    _delete_journal()


def _undo_journal(journal: dict[str, object]) -> None:
    """Reverse file moves, trash, and a cue copy.

    Args:
        journal: Journal written before the change.
    """
    moves = [item for item in _records(journal.get("moves")) if item.get("kind") != "drop-tree"]
    drops = [item for item in _records(journal.get("moves")) if item.get("kind") == "drop-tree"]
    for move in reversed(moves):
        _undo_move(move)
    for drop in drops:
        dst = Path(str(drop.get("dst")))
        if dst.exists():
            shutil.rmtree(dst)
    for record in _records(journal.get("trash")):
        _undo_trash(record)
    _restore_cue(journal)


def _finish_journal(journal: dict[str, object]) -> None:
    """Complete file moves that the database already points at.

    Args:
        journal: Journal whose database half already committed, or an
            untracked change marked done.
    """
    for move in _records(journal.get("moves")):
        kind = str(move.get("kind") or "rename")
        src = Path(str(move.get("src")))
        dst = Path(str(move.get("dst")))
        if kind == "drop-tree":
            if src.exists():
                shutil.rmtree(src)
            continue
        if kind == "copy":
            _finish_copy(src, dst)
        elif src.exists() and not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            os.rename(src, dst)
    for record in _records(journal.get("trash")):
        if record.get("mode") == "safety":
            Path(str(record.get("dst"))).unlink(missing_ok=True)
    backup = _cue_record(journal)
    if backup is not None:
        Path(backup["backup"]).unlink(missing_ok=True)


def _finish_copy(src: Path, dst: Path) -> None:
    """Finish one cross-drive copy.

    Args:
        src: Original file.
        dst: Copied file.

    Raises:
        LibraryError: If both copies exist and their sizes differ.
    """
    if src.exists() and not dst.exists():
        _copy_unlink(src, dst)
    elif src.exists() and dst.exists():
        if src.is_file() and dst.is_file() and src.stat().st_size == dst.stat().st_size:
            src.unlink()
        else:
            raise library.LibraryError(
                "A previous file change is incomplete. Restore the copy in Library/Backups."
            )


def _undo_move(move: dict[str, object]) -> None:
    """Put one moved file or folder back.

    Args:
        move: Journal move record.
    """
    src = Path(str(move.get("src")))
    dst = Path(str(move.get("dst")))
    kind = str(move.get("kind") or "rename")
    if kind == "copy":
        if dst.exists() and src.exists() and dst.is_file():
            dst.unlink()
        elif dst.exists() and not src.exists():
            _relocate_back(dst, src)
        return
    if dst.exists() and not src.exists():
        _relocate_back(dst, src)


def _relocate_back(src: Path, dst: Path) -> None:
    """Move a file or folder back to where it started.

    Args:
        src: Current path.
        dst: Original path.

    Raises:
        OSError: If the move fails.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.rename(src, dst)
    except OSError as exc:
        if exc.errno != errno.EXDEV or src.is_dir():
            raise
        _copy_unlink(src, dst)


def _undo_trash(record: dict[str, object]) -> None:
    """Put one trashed file back.

    Args:
        record: Trash journal record.
    """
    src = Path(str(record.get("src")))
    dst = Path(str(record.get("dst")))
    info = record.get("info")
    if record.get("mode") == "safety":
        if not src.exists() and dst.exists():
            _relocate_back(dst, src)
        elif dst.exists() and dst.is_file():
            dst.unlink()
        return
    if dst.exists() and src.exists() and dst.is_file():
        dst.unlink()
    elif dst.exists() and not src.exists():
        _relocate_back(dst, src)
    if isinstance(info, str):
        Path(info).unlink(missing_ok=True)


def _restore_cue(journal: dict[str, object]) -> None:
    """Restore a replacement file if a cue copy needs to be undone.

    Args:
        journal: Journal that may contain a cue backup.
    """
    record = _cue_record(journal)
    if record is None:
        return
    backup = Path(record["backup"])
    target = Path(record["file"])
    if backup.is_file():
        shutil.copy2(backup, target)
        backup.unlink()
    journal["cue_backup"] = None


def _cue_record(journal: dict[str, object]) -> dict[str, str] | None:
    """Return the cue backup record when it has both paths.

    Args:
        journal: Journal dict.

    Returns:
        The file and backup paths, or None.
    """
    raw = journal.get("cue_backup")
    if not isinstance(raw, dict):
        return None
    file_name = raw.get("file")
    backup = raw.get("backup")
    if not isinstance(file_name, str) or not isinstance(backup, str):
        return None
    return {"file": file_name, "backup": backup}


def _expect_state(expect: object) -> str:
    """Compare the journal's expected rows with the database.

    Args:
        expect: The journal expect object.

    Returns:
        ``new`` when the database already has the change, ``old`` when it
        does not, ``empty`` when the change did not touch rows, and
        ``mixed`` when only some rows match.
    """
    if not isinstance(expect, dict):
        return "empty"
    paths = expect.get("paths")
    absent = expect.get("absent")
    path_rows = paths if isinstance(paths, list) else []
    absent_ids = absent if isinstance(absent, list) else []
    if not path_rows and not absent_ids:
        return "empty"
    try:
        conn_cm = closing(library.read_conn())
    except library.LibraryError:
        return "mixed"
    new_hits = 0
    old_hits = 0
    with conn_cm as conn:
        for item in path_rows:
            if not isinstance(item, dict):
                return "mixed"
            asset_id = item.get("id")
            portable = item.get("portable_id")
            if not isinstance(asset_id, int) or isinstance(asset_id, bool) or not isinstance(portable, str):
                return "mixed"
            row = conn.execute("SELECT portable_id FROM asset WHERE id = ?", (asset_id,)).fetchone()
            if row is None:
                return "mixed"
            stored = row["portable_id"]
            if isinstance(stored, str) and _same_portable(stored, portable):
                new_hits += 1
            else:
                old_hits += 1
        gone = 0
        here = 0
        for asset_id in absent_ids:
            if not isinstance(asset_id, int) or isinstance(asset_id, bool):
                return "mixed"
            row = conn.execute("SELECT 1 FROM asset WHERE id = ?", (asset_id,)).fetchone()
            if row is None:
                gone += 1
            else:
                here += 1
    if new_hits == len(path_rows) and gone == len(absent_ids) and old_hits == 0 and here == 0:
        return "new"
    if new_hits == 0 and gone == 0:
        return "old"
    return "mixed"


def _same_portable(stored: str, expected: str) -> bool:
    """Return whether two stored paths are the same file.

    Args:
        stored: Value currently in the database.
        expected: Value the journal wanted to write.

    Returns:
        True when the strings match or both resolve to the same path.
    """
    if stored == expected:
        return True
    left = resolve_stored(stored)
    right = resolve_stored(expected)
    return left is not None and left == right


def _retarget_related(plan: Plan) -> list[str]:
    """Point saved related-track links at files after they move.

    Args:
        plan: The change that already committed. Delete has no pairs.

    Returns:
        Warning sentences. A missing link is not a warning. A path that
        already identifies another track is. The file move stays.
    """
    notes: list[str] = []
    for old, new in _moved_pairs(plan):
        try:
            library.update_related_path(old, new)
        except library.LibraryError as exc:
            if exc.message not in notes:
                notes.append(exc.message)
        except Exception:
            logger.exception("Related tracks could not follow a moved file")
            note = "Related tracks could not follow this change."
            if note not in notes:
                notes.append(note)
    return notes


def _moved_pairs(plan: Plan) -> list[tuple[str, str]]:
    """List old and new paths for a committed move.

    Args:
        plan: The change that already committed.

    Returns:
        Pairs of the path before the move and the path after it. Folder
        moves include every file now inside the folder, not only library
        rows. Shortcuts are skipped.
    """
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(old: Path, new: Path) -> None:
        key = (str(old), str(new))
        if key in seen or old == new:
            return
        seen.add(key)
        pairs.append(key)

    for change in plan.changes:
        add(change.source, change.dest)
    for old, new in plan.directories:
        if not new.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(new, followlinks=False):
            current = Path(dirpath)
            dirnames[:] = [name for name in dirnames if not (current / name).is_symlink()]
            for name in filenames:
                file = current / name
                if file.is_symlink() or not file.is_file():
                    continue
                try:
                    relative = file.relative_to(new)
                except ValueError:
                    continue
                add(old / relative, file)
    return pairs


def _capture(plan: Plan, cues: str | None) -> None:
    """Record a file change without paths or names.

    Args:
        plan: The change that committed.
        cues: Cue result for a replace, or None.
    """
    properties: dict[str, object] = {
        "file_count": _file_count(plan),
        "change": plan.action,
    }
    if plan.action == "replace" and cues in {"copied", "kept", "skipped", "unsupported", "failed"}:
        properties["cues"] = cues
    telemetry.capture(telemetry.EVENT_FILES_CHANGED, properties)


def _file_count(plan: Plan) -> int:
    """Count files for the telemetry bucket.

    Args:
        plan: Performed plan.

    Returns:
        A non-negative count. Names are not included.
    """
    if plan.action == "delete":
        return len(plan.removals)
    if plan.action == "replace":
        return 1
    if plan.action == "move_folder":
        return max(len(plan.changes), 1)
    return len(plan.moves)


def _cue_detail(status: str) -> str:
    """Return the page sentence for a cue status.

    Args:
        status: copied, kept, skipped, unsupported, or failed.

    Returns:
        A sentence without a path.
    """
    if status == "copied":
        return "Cue points were copied onto the new file."
    if status == "kept":
        return "The new file already has Serato cue points, so they were left as they are."
    if status == "skipped":
        return "The old file has no Serato cue points to copy."
    if status == "failed":
        return "Cue points could not be copied. The new file was left unchanged."
    return "Cue points stay on the old file. This file type cannot take a Serato tag safely."


def trash_file(path: Path) -> dict[str, object]:
    """Move one file to the operating-system Trash.

    ``SERATO_LIBRARY_TRASH`` overrides the destination when it is an
    absolute path. A relative value is ignored. The suite sets it so a
    test does not touch the real Trash.

    Args:
        path: Existing file.

    Returns:
        A journal record with the original path and where the bytes went.

    Raises:
        LibraryError: If the file cannot be moved.
    """
    original = path
    override = _trash_override()
    if override is not None:
        return _trash_move(original, override)
    if sys.platform == "win32":
        return _trash_windows(original)
    if sys.platform == "darwin":
        return _trash_move(original, _darwin_trash_dir(original))
    return _trash_linux(original)


def _trash_override() -> Path | None:
    """Return the test trash directory when the environment sets an absolute path.

    Returns:
        The directory, or None when the variable is missing or relative.
    """
    raw = os.environ.get(_TRASH_ENV, "").strip()
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute() or path.is_symlink():
        return None
    path.mkdir(parents=True, exist_ok=True)
    return path


def _trash_linux(path: Path) -> dict[str, object]:
    """Move a file into the FreeDesktop trash.

    Args:
        path: Existing file.

    Returns:
        A move-mode journal record, including the trashinfo path.
    """
    files, info_dir = _linux_trash_dirs()
    files.mkdir(parents=True, exist_ok=True)
    info_dir.mkdir(parents=True, exist_ok=True)
    record = _trash_move(path, files)
    info = info_dir / (Path(str(record["dst"])).name + ".trashinfo")
    info.write_text(_trashinfo(path), encoding="utf-8")
    record["info"] = str(info)
    return record


def _linux_trash_dirs() -> tuple[Path, Path]:
    """Return the FreeDesktop files and info directories.

    Returns:
        ``Trash/files`` and ``Trash/info`` under the XDG data home.
        A relative ``XDG_DATA_HOME`` is ignored.
    """
    raw = os.environ.get("XDG_DATA_HOME", "").strip()
    root = Path(raw) if raw and Path(raw).is_absolute() else Path.home() / ".local" / "share"
    return root / "Trash" / "files", root / "Trash" / "info"


def _darwin_trash_dir(path: Path) -> Path:
    """Return the Trash folder for a file on macOS.

    Args:
        path: File being trashed.

    Returns:
        ``~/.Trash`` when it is on the same drive, otherwise the volume's
        ``.Trashes`` folder.
    """
    home_trash = Path.home() / ".Trash"
    try:
        home_trash.mkdir(parents=True, exist_ok=True)
        if path.stat().st_dev == home_trash.stat().st_dev:
            return home_trash
    except OSError:
        pass
    parts = path.resolve().parts
    if len(parts) >= 3 and parts[1] == "Volumes":
        return Path(parts[0]) / parts[1] / parts[2] / ".Trashes" / str(os.getuid())
    return home_trash


def _trash_windows(path: Path) -> dict[str, object]:
    """Move a file to the Windows Recycle Bin and keep a copy until the database commits.

    Args:
        path: Existing file.

    Returns:
        A safety-mode journal record. The safety copy is removed after
        the database commit. If the commit fails, the copy is put back.

    Raises:
        LibraryError: If the Recycle Bin refuses the file.
    """
    hold = _backups() / "trash-hold"
    hold.mkdir(parents=True, exist_ok=True)
    safety = _unique_name(hold, path.name)
    shutil.copy2(path, safety)
    try:
        _shell_delete(path)
    except library.LibraryError:
        safety.unlink(missing_ok=True)
        raise
    except OSError as exc:
        safety.unlink(missing_ok=True)
        raise library.LibraryError("The file could not be moved to the Recycle Bin.") from exc
    return {"src": str(path), "dst": str(safety), "info": None, "mode": "safety"}


def _shell_delete(path: Path) -> None:
    """Ask the Windows shell to delete a file into the Recycle Bin.

    Args:
        path: Existing file.

    Raises:
        LibraryError: If the shell returns an error.
    """
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        """The shell file-operation struct used for a Recycle Bin delete."""

        _fields_ = [
            ("hwnd", ctypes.c_void_p),
            ("wFunc", ctypes.c_uint),
            ("pFrom", ctypes.c_wchar_p),
            ("pTo", ctypes.c_wchar_p),
            ("fFlags", ctypes.c_ushort),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", ctypes.c_wchar_p),
        ]

    operation = SHFILEOPSTRUCTW()
    operation.wFunc = FO_DELETE
    source = ctypes.create_unicode_buffer(str(path) + "\0")
    operation.pFrom = ctypes.cast(source, ctypes.c_wchar_p)
    operation.fFlags = FOF_SILENT | FOF_NOCONFIRMATION | FOF_ALLOWUNDO | FOF_NOERRORUI
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
    if result != 0 or operation.fAnyOperationsAborted:
        raise library.LibraryError("The file could not be moved to the Recycle Bin.")


def _trash_move(path: Path, directory: Path) -> dict[str, object]:
    """Move a file into a trash directory.

    Args:
        path: Existing file.
        directory: Folder that receives it.

    Returns:
        A move-mode journal record.
    """
    directory.mkdir(parents=True, exist_ok=True)
    dest = _unique_name(directory, path.name)
    try:
        os.rename(path, dest)
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise library.LibraryError("The file could not be moved to the Trash.") from exc
        _copy_unlink(path, dest)
    return {"src": str(path), "dst": str(dest), "info": None, "mode": "move"}


def _trashinfo(path: Path) -> str:
    """Build a FreeDesktop trashinfo document.

    Args:
        path: Original file path.

    Returns:
        The document text. The path is percent-encoded.
    """
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    return f"[Trash Info]\nPath={quote(str(path), safe='/')}\nDeletionDate={stamp}\n"


def _unique_name(directory: Path, name: str) -> Path:
    """Pick a name that does not exist in a directory.

    Args:
        directory: Destination folder.
        name: Preferred file name.

    Returns:
        A path inside ``directory``.

    Raises:
        LibraryError: If a thousand variants already exist.
    """
    candidate = directory / name
    if not candidate.exists():
        return candidate
    stem = Path(name).stem
    suffix = Path(name).suffix
    for number in range(2, 1000):
        candidate = directory / f"{stem} {number}{suffix}"
        if not candidate.exists():
            return candidate
    raise library.LibraryError("The Trash already has too many copies of that file.")


def _cue_hold(path: Path) -> Path:
    """Copy a file into the backup folder before its tags change.

    Args:
        path: File that may be rewritten.

    Returns:
        The backup path.
    """
    folder = _backups() / "cue-hold"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{uuid.uuid4().hex}{path.suffix}"
    shutil.copy2(path, target)
    return target


def _journal_path() -> Path:
    """Return the path of the in-progress file journal.

    Returns:
        ``Library/Backups/file-ops-journal.json`` beside the master database.
    """
    return _backups() / _JOURNAL


def _write_journal(journal: dict[str, object]) -> None:
    """Atomically write the file journal.

    Args:
        journal: JSON-ready dict.
    """
    folder = _backups()
    folder.mkdir(parents=True, exist_ok=True)
    target = _journal_path()
    temporary = target.with_suffix(".json.tmp")
    payload = json.dumps(journal).encode("utf-8")
    with temporary.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, target)


def _delete_journal() -> None:
    """Remove the file journal after a change is resolved."""
    path = _journal_path()
    path.unlink(missing_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.unlink(missing_ok=True)


def _backups() -> Path:
    """Return the backup directory beside the master database.

    Returns:
        ``Library/Backups``.
    """
    return Path(library.MASTER).resolve().parent / "Backups"


def _records(value: object) -> list[dict[str, object]]:
    """Return dict items from a journal list.

    Args:
        value: A journal field.

    Returns:
        The dict entries. Anything else is skipped.
    """
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def resolve_stored(value: str) -> Path | None:
    """Resolve a portable id the way the page resolves a stored path.

    Args:
        value: Stored path. Relative values are tried under the home
            directory and then at the filesystem root.

    Returns:
        The resolved path, or None when the value is empty. A shortcut is
        returned as itself so a later check can refuse to follow it.
    """
    if not isinstance(value, str) or value == "":
        return None
    raw = Path(value)
    candidates = [raw] if raw.is_absolute() else [Path.home() / value, Path("/") / value]
    chosen = candidates[0]
    for candidate in candidates:
        try:
            if candidate.exists():
                chosen = candidate
                break
        except OSError:
            continue
    try:
        if chosen.is_symlink():
            return chosen.absolute()
        return chosen.resolve(strict=False)
    except OSError:
        return None


def to_portable(path: Path) -> str:
    """Store a path the way a track edit stores a portable id.

    Args:
        path: File or folder path.

    Returns:
        A home-relative path with forward slashes when the file is under
        the home directory, otherwise the absolute path.
    """
    resolved = path
    try:
        if not path.is_symlink():
            resolved = path.resolve(strict=False)
    except OSError:
        resolved = path
    try:
        return resolved.relative_to(Path.home()).as_posix()
    except ValueError:
        return str(resolved)


def _validate_filename(name: object) -> str:
    """Refuse a name that is a path rather than a single file name.

    Args:
        name: Submitted file name.

    Returns:
        The name.

    Raises:
        _Refuse: If the name is empty, a path, or ``.`` or ``..``.
    """
    if not isinstance(name, str):
        raise _Refuse("Use a file name without a folder.")
    if (
        not name
        or name != name.strip()
        or len(name) > _NAME_RE_MAX
        or name in {".", ".."}
        or "/" in name
        or "\\" in name
        or "\x00" in name
    ):
        raise _Refuse("Use a file name without a folder.")
    return name


def _contained(directory: Path, name: str) -> Path:
    """Join a file name onto a folder and refuse a path that escapes it.

    The name check and this check are separate. A name with no slash can
    still be a shortcut whose target is outside the folder.

    Args:
        directory: Real destination folder.
        name: A single file name that has already been validated.

    Returns:
        The destination path.

    Raises:
        _Refuse: If the folder or the result is a shortcut, or the
            resolved parent is not the folder.
    """
    if directory.is_symlink():
        raise _Refuse("Shortcuts are left alone.")
    base = directory.resolve()
    candidate = base / name
    if candidate.is_symlink():
        raise _Refuse("Shortcuts are left alone.")
    resolved = candidate.resolve(strict=False)
    if resolved.parent != base:
        raise _Refuse("Use a file name without a folder.")
    return resolved


def _as_path(value: object) -> Path:
    """Return a caller path after rejecting embedded nulls.

    Args:
        value: JSON value.

    Returns:
        A path.

    Raises:
        LibraryError: If the value is not a usable path string.
    """
    if not isinstance(value, str) or not value.strip() or "\x00" in value or len(value) > 4096:
        raise library.LibraryError("That request is not valid.")
    return Path(value)


def _path_list(value: object) -> list[str]:
    """Return a list of path strings.

    Args:
        value: JSON value.

    Returns:
        The strings.

    Raises:
        LibraryError: If the value is not a list of strings.
    """
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise library.LibraryError("That request is not valid.")
    return list(value)


def _real_file(path: Path) -> Path:
    """Resolve a file the operation is allowed to change.

    Args:
        path: Caller path.

    Returns:
        The resolved file.

    Raises:
        _Refuse: If the path is missing, a shortcut, or protected.
    """
    if path.is_symlink():
        raise _Refuse("Shortcuts are left alone.")
    if not path.is_file():
        raise _Refuse("That file is not on disk.")
    resolved = path.resolve()
    _guard_target(resolved)
    return resolved


def _real_dir(path: Path) -> Path:
    """Resolve a folder the operation is allowed to use.

    Args:
        path: Caller path.

    Returns:
        The resolved folder.

    Raises:
        _Refuse: If the path is not a real folder or is protected.
    """
    if path.is_symlink():
        raise _Refuse("Shortcuts are left alone.")
    if not path.is_dir():
        raise _Refuse("Choose a folder.")
    resolved = path.resolve()
    if _inside_backups(resolved) or resolved in _database_files():
        raise _Refuse("The library backup cannot be changed from here.")
    return resolved


def _guard_target(path: Path) -> None:
    """Refuse the database files and anything inside the backup folder.

    Args:
        path: Resolved path.

    Raises:
        _Refuse: If the path is protected. A sibling of the backup folder
            is not protected.
    """
    if path in _database_files() or _inside_backups(path):
        raise _Refuse("The library backup cannot be changed from here.")


def _guard_tree(path: Path) -> None:
    """Refuse moving the library folder, the home directory, or a filesystem root.

    Args:
        path: Folder the user asked to move.

    Raises:
        _Refuse: If the folder is too broad.
    """
    root = Path(library.MASTER).resolve().parent
    home = Path.home().resolve()
    if path == root or path in root.parents or path == home or path == Path(path.anchor):
        raise _Refuse("That folder is too large to move from here.")


def _inside_backups(path: Path) -> bool:
    """Return whether a path is the backup folder or inside it.

    Args:
        path: Resolved path.

    Returns:
        True for ``Library/Backups`` and its children. A sibling such as
        ``Library/Backups-extra`` is outside.
    """
    backups = _backups()
    return path == backups or backups in path.parents


def _database_files() -> set[Path]:
    """Return the database files this tool must not move or delete.

    Returns:
        The master database, its sidecars, and ``root.sqlite``.
    """
    master = Path(library.MASTER).resolve()
    parent = master.parent
    return {
        master,
        parent / "root.sqlite",
        parent / "master.sqlite-wal",
        parent / "master.sqlite-shm",
        Path(str(master) + "-wal"),
        Path(str(master) + "-shm"),
    }


def _iter_files(root: Path) -> list[Path]:
    """List files under a folder and refuse any shortcut.

    Args:
        root: Folder to walk. Shortcuts are not followed.

    Returns:
        File paths.

    Raises:
        _Refuse: If a shortcut is inside the folder or the tree is too large.
    """
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(dirpath)
        if current != root and current.is_symlink():
            raise _Refuse("Shortcuts are left alone.")
        for name in dirnames:
            if (current / name).is_symlink():
                raise _Refuse("Shortcuts are left alone.")
        for name in filenames:
            file = current / name
            if file.is_symlink():
                raise _Refuse("Shortcuts are left alone.")
            found.append(file)
            if len(found) > _TREE_CAP:
                raise _Refuse("Choose a smaller folder.")
    return found


def _same_file(left: Path, right: Path) -> bool:
    """Return whether two paths are the same directory entry.

    Args:
        left: First path.
        right: Second path.

    Returns:
        True when both exist and share an inode.
    """
    try:
        return left.exists() and right.exists() and os.path.samefile(left, right)
    except OSError:
        return False


def _asset_rows(conn: sqlite3.Connection, schema: str) -> list[dict[str, object]]:
    """Read the asset columns a file change needs.

    Args:
        conn: Database connection.
        schema: Schema name.

    Returns:
        One dict per asset row.
    """
    columns = _table_columns(conn, schema, "asset")
    wanted = ["id", "portable_id"]
    for name in ("file_name", "location_id", "external_id"):
        if name in columns:
            wanted.append(name)
    rows = conn.execute(
        f"SELECT {', '.join(_q(name) for name in wanted)} FROM {_q(schema)}.asset"
    ).fetchall()
    copied: list[dict[str, object]] = []
    for row in rows:
        item: dict[str, object] = {}
        for name in wanted:
            item[name] = row[name]
        copied.append(item)
    return copied


def _assets_at(rows: list[dict[str, object]], path: Path) -> list[dict[str, object]]:
    """Return assets whose stored path is this file.

    Args:
        rows: Asset dicts.
        path: Resolved file path.

    Returns:
        Matching rows.
    """
    found = []
    for row in rows:
        stored = row.get("portable_id")
        resolved = resolve_stored(stored if isinstance(stored, str) else "")
        if resolved == path:
            found.append(row)
    return found


def _assets_under(
    rows: list[dict[str, object]], root: Path
) -> list[tuple[dict[str, object], Path]]:
    """Return assets stored inside a folder.

    Args:
        rows: Asset dicts.
        root: Folder being moved.

    Returns:
        Pairs of the asset row and its resolved path.
    """
    found: list[tuple[dict[str, object], Path]] = []
    for row in rows:
        stored = row.get("portable_id")
        resolved = resolve_stored(stored if isinstance(stored, str) else "")
        if resolved is not None and (resolved == root or root in resolved.parents):
            found.append((row, resolved))
    return found


def _bump_revision(conn: sqlite3.Connection, schema: str) -> int | None:
    """Advance one database's serato revision.

    Args:
        conn: Write connection.
        schema: Schema whose ``serato`` table should move forward.

    Returns:
        The new revision, or None when that table is absent.
    """
    if not _has(conn, schema, "serato"):
        return None
    columns = _table_columns(conn, schema, "serato")
    if "revision" not in columns:
        return None
    row = conn.execute(f"SELECT revision FROM {_q(schema)}.serato").fetchone()
    current = int(row[0]) if row is not None and row[0] is not None else 0
    revision = max(current + 1, int(time.time()))
    conn.execute(f"UPDATE {_q(schema)}.serato SET revision = ?", (revision,))
    return revision


def _change_for(
    source: Path,
    dest: Path,
    rows: list[dict[str, object]],
    missing: bool,
    conn: sqlite3.Connection | None = None,
    matched: list[dict[str, object]] | None = None,
) -> FileChange:
    """Build one library change for a file.

    Args:
        source: Current path.
        dest: New path.
        rows: Asset rows to search when ``matched`` is not given.
        missing: True when the source file is not on disk.
        conn: Read connection used to name crates.
        matched: Asset rows the caller already chose.

    Returns:
        The change, including crate names when ``conn`` is open.
    """
    chosen = matched if matched is not None else _assets_at(rows, source)
    asset_ids = tuple(int(row["id"]) for row in chosen)
    crates: tuple[str, ...] = ()
    spaces: tuple[str, ...] = ()
    if conn is not None and asset_ids:
        crates, spaces = _membership(conn, list(asset_ids))
    return FileChange(
        source=source,
        dest=dest,
        asset_ids=asset_ids,
        external=_externals(chosen),
        crates=crates,
        spaces=spaces,
        missing=missing,
    )


def _externals(rows: list[dict[str, object]]) -> tuple[tuple[int, int], ...]:
    """Collect location and external ids.

    Args:
        rows: Asset dicts.

    Returns:
        Pairs used to update the mirrored database.
    """
    found: list[tuple[int, int]] = []
    for row in rows:
        location_id = row.get("location_id")
        external_id = row.get("external_id")
        if location_id is None or external_id is None:
            continue
        if isinstance(location_id, bool) or isinstance(external_id, bool):
            continue
        if isinstance(location_id, int) and isinstance(external_id, int):
            found.append((location_id, external_id))
    return tuple(found)


def _membership(
    conn: sqlite3.Connection, asset_ids: list[int]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """List crate and space names for a set of assets.

    Args:
        conn: Read connection.
        asset_ids: Asset ids.

    Returns:
        Crate display names and space names.
    """
    crates: list[str] = []
    spaces: list[str] = []
    for asset_id in asset_ids:
        for label in _crate_names(conn, asset_id):
            if label not in crates:
                crates.append(label)
        for label in _space_names(conn, asset_id):
            if label not in spaces:
                spaces.append(label)
    return tuple(crates), tuple(spaces)


def _crate_names(conn: sqlite3.Connection, asset_id: int) -> list[str]:
    """Return crate names that contain one asset.

    Args:
        conn: Read connection.
        asset_id: Asset id.

    Returns:
        Display names. A schema without the membership tables returns an
        empty list.
    """
    names: list[str] = []
    queries = (
        """
        SELECT c.name FROM container c
        JOIN location_container lc ON lc.container_id = c.id
        JOIN container_asset ca ON ca.location_container_id = lc.id
        WHERE ca.asset_id = ?
        """,
        """
        SELECT c.name FROM container c
        JOIN container_asset ca ON ca.container_id = c.id
        WHERE ca.asset_id = ?
        """,
    )
    for sql in queries:
        try:
            for row in conn.execute(sql, (asset_id,)).fetchall():
                raw = row["name"]
                if isinstance(raw, str) and raw:
                    label = library.display_name(raw)
                    if label and label not in names:
                        names.append(label)
        except sqlite3.OperationalError:
            continue
    return names


def _space_names(conn: sqlite3.Connection, asset_id: int) -> list[str]:
    """Return space names that contain one asset.

    Args:
        conn: Read connection.
        asset_id: Asset id.

    Returns:
        Space names.
    """
    try:
        rows = conn.execute(
            """
            SELECT s.name FROM space s
            JOIN space_asset sa ON sa.space_id = s.id
            WHERE sa.asset_id = ?
            """,
            (asset_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [row["name"] for row in rows if isinstance(row["name"], str) and row["name"]]


def _has(conn: sqlite3.Connection, schema: str, table: str) -> bool:
    """Return whether a table exists.

    Args:
        conn: Database connection.
        schema: Schema name.
        table: Table name.

    Returns:
        True when ``sqlite_master`` lists the table.
    """
    row = conn.execute(
        f"SELECT 1 FROM {_q(schema)}.sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _tables(conn: sqlite3.Connection, schema: str) -> list[str]:
    """List ordinary tables in one schema.

    Args:
        conn: Database connection.
        schema: Schema name.

    Returns:
        Table names that are safe to quote. Internal tables are skipped.
    """
    rows = conn.execute(
        f"SELECT name FROM {_q(schema)}.sqlite_master WHERE type = 'table'"
    ).fetchall()
    names: list[str] = []
    for row in rows:
        name = row[0]
        if not isinstance(name, str) or name in _SKIP_TABLES or name.startswith("sqlite_"):
            continue
        if _ident(name):
            names.append(name)
    return names


def _table_columns(conn: sqlite3.Connection, schema: str, table: str) -> set[str]:
    """Return column names for one table.

    Args:
        conn: Database connection.
        schema: Schema name.
        table: Table name.

    Returns:
        Column names.
    """
    rows = conn.execute(f"PRAGMA {_q(schema)}.table_info({_q(table)})").fetchall()
    return {str(row[1]) for row in rows}


def _primary_key(conn: sqlite3.Connection, schema: str, table: str) -> list[str]:
    """Return the primary key columns, or rowid.

    Args:
        conn: Database connection.
        schema: Schema name.
        table: Table name.

    Returns:
        Column names that identify one row. Empty when the table has no
        usable key.
    """
    rows = conn.execute(f"PRAGMA {_q(schema)}.table_info({_q(table)})").fetchall()
    keyed = sorted((int(row[5]), str(row[1])) for row in rows if int(row[5]) > 0)
    if keyed:
        return [name for _, name in keyed]
    try:
        conn.execute(f"SELECT rowid FROM {_q(schema)}.{_q(table)} LIMIT 0")
    except sqlite3.OperationalError:
        return []
    return ["rowid"]


def _notnull(conn: sqlite3.Connection, schema: str, table: str, column: str) -> bool:
    """Return whether a column is declared NOT NULL.

    Args:
        conn: Database connection.
        schema: Schema name.
        table: Table name.
        column: Column name.

    Returns:
        True when the column cannot store NULL.
    """
    rows = conn.execute(f"PRAGMA {_q(schema)}.table_info({_q(table)})").fetchall()
    for row in rows:
        if str(row[1]) == column:
            return bool(row[3])
    return False


def _is_path_column(name: str) -> bool:
    """Return whether a column stores a file path.

    Args:
        name: Column name from the database.

    Returns:
        True for portable ids, file paths, and columns that end in those.
        File names are not paths; they are updated with the row that owns
        the portable id.
    """
    lowered = name.lower()
    if lowered in {"portable_id", "video_portable_id", "file_path", "filepath", "path"}:
        return True
    return lowered.endswith("_path") or lowered.endswith("_portable_id")


def _q(name: str) -> str:
    """Quote a SQL identifier this module generated or checked.

    Args:
        name: Schema, table, or column name.

    Returns:
        The quoted identifier.

    Raises:
        LibraryError: If the name is not a plain identifier.
    """
    if not _ident(name):
        raise library.LibraryError("The library table could not be updated.")
    return '"' + name + '"'


def _ident(name: str) -> bool:
    """Return whether a name is a safe SQL identifier.

    Args:
        name: Candidate identifier.

    Returns:
        True for an ASCII letter or underscore followed by letters, digits,
        or underscores.
    """
    if not name:
        return False
    first = name[0]
    if not (first == "_" or "A" <= first <= "Z" or "a" <= first <= "z"):
        return False
    return all(char == "_" or "A" <= char <= "Z" or "a" <= char <= "z" or "0" <= char <= "9" for char in name[1:])
