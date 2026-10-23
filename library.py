"""Read extra Serato views and write the library when Serato DJ Pro is quit.

master.sqlite is the library Serato and this app display. root.sqlite is the
on-disk location database and is updated to match, when it is connected.
Writes are refused while Serato's lock is held by a live process. The first
write in a process copies the database into Library/Backups first.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import time
import uuid
from contextlib import closing
from pathlib import Path
from urllib.parse import unquote, urlparse

from tags import read_serato_tags

LIVE_MASTER = Path.home() / "Library/Application Support/Serato/Library/master.sqlite"
MASTER = LIVE_MASTER
NAME_SPLIT = "\U00105e8a"
LIBRARY_SPACE = "Serato Library"
ALLOWED_SPACES = ("Serato Library", "Serato Video", "Apple Music", "Prepare")

TEXT_FIELDS = {
    "name",
    "artist",
    "album",
    "genre",
    "year",
    "composer",
    "remixer",
    "label",
    "grouping",
    "comments",
    "key",
    "emoji",
}
TRACK_FIELDS = TEXT_FIELDS | {"bpm", "color", "rating", "is_beatgrid_locked", "portable_id"}
NORM_FIELDS = {
    "file_name",
    "name",
    "artist",
    "album",
    "genre",
    "comments",
    "label",
    "remixer",
    "grouping",
    "composer",
    "year",
    "key",
}

_KEY_VALUES = {
    "g#m": 0, "abm": 0, "1a": 0,
    "ebm": 1, "d#m": 1, "2a": 1,
    "bbm": 2, "a#m": 2, "3a": 2,
    "fm": 3, "4a": 3,
    "cm": 4, "5a": 4,
    "gm": 5, "6a": 5,
    "dm": 6, "7a": 6,
    "am": 7, "8a": 7,
    "em": 8, "9a": 8,
    "bm": 9, "10a": 9,
    "f#m": 10, "gbm": 10, "11a": 10,
    "c#m": 11, "dbm": 11, "12a": 11,
    "b": 12, "1b": 12,
    "f#": 13, "gb": 13, "2b": 13,
    "c#": 14, "db": 14, "3b": 14,
    "g#": 15, "ab": 15, "4b": 15,
    "d#": 16, "eb": 16, "5b": 16,
    "a#": 17, "bb": 17, "6b": 17,
    "f": 18, "7b": 18,
    "c": 19, "8b": 19,
    "g": 20, "9b": 20,
    "d": 21, "10b": 21,
    "a": 22, "11b": 22,
    "e": 23, "12b": 23,
}

_backed_up: set[str] = set()


class LibraryError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


class SeratoOpen(LibraryError):
    def __init__(self, info: dict):
        super().__init__(info["message"], 409)
        self.info = info


def serato_str_norm(value):
    if value is None:
        return None
    return str(value).lower()


def serato_key_type(value):
    if value is None:
        return -1
    text = str(value).strip().lower()
    if not text:
        return -1
    return _KEY_VALUES.get(text, -1)


def register(conn: sqlite3.Connection) -> None:
    conn.create_function("serato_str_norm", 1, serato_str_norm, deterministic=True)
    conn.create_function("serato_raw_key_string_to_key_type", 1, serato_key_type, deterministic=True)


def read_conn(path: Path | None = None) -> sqlite3.Connection:
    database = Path(path or MASTER)
    if not database.exists():
        raise LibraryError(f"Serato library not found at {database}", 404)
    conn = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _process_is_serato(pid: int) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        result = subprocess.run(
            ["ps", "-p", str(int(pid)), "-o", "comm="],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if result.returncode != 0:
        return False
    return "serato" in result.stdout.lower()


def _status_rows(conn: sqlite3.Connection) -> dict:
    try:
        rows = conn.execute(
            "SELECT owner_process_id, owner_process_name FROM lock"
        ).fetchall()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            rows = []
        else:
            raise
    for row in rows:
        pid = int(row["owner_process_id"] or 0)
        name = row["owner_process_name"] or "Serato DJ Pro"
        if _process_is_serato(pid):
            return {
                "open": True,
                "writable": False,
                "pid": pid,
                "process": name,
                "message": f"{name} is open. Edits stay off until it quits.",
            }
    return {
        "open": False,
        "writable": True,
        "pid": None,
        "process": None,
        "message": "Serato is quit. Edits save to the library.",
    }


def status(path: Path | None = None) -> dict:
    try:
        with closing(read_conn(path)) as conn:
            return _status_rows(conn)
    except sqlite3.OperationalError as exc:
        if "locked" in str(exc).lower():
            return {
                "open": True,
                "writable": False,
                "pid": None,
                "process": "Serato DJ Pro",
                "message": "Serato DJ Pro has the library open. Edits stay off until it quits.",
            }
        raise


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _parse_db_path(value: str | None) -> Path | None:
    if not value:
        return None
    if value.startswith("file:"):
        return Path(unquote(urlparse(value).path))
    return Path(value)


def _location_paths(conn: sqlite3.Connection) -> dict[int, Path]:
    found: dict[int, Path] = {}
    try:
        rows = conn.execute("SELECT location_id, database_uri FROM connection").fetchall()
    except sqlite3.OperationalError:
        rows = []
    for row in rows:
        path = _parse_db_path(row["database_uri"])
        if path is not None and path.is_file():
            found[int(row["location_id"])] = path
    if 3 not in found:
        candidate = Path(MASTER).resolve().parent / "root.sqlite"
        if candidate.is_file():
            found[3] = candidate
    return found


def _mirror_allowed(path: Path) -> bool:
    """A relocated test database may only touch files beside itself."""
    master = Path(MASTER).resolve()
    if master == LIVE_MASTER.resolve():
        return True
    resolved = path.resolve()
    return resolved.parent == master.parent or str(resolved).startswith("/tmp/")


def _backup_database(source: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(f"file:{source}?mode=ro", uri=True)) as src:
        with closing(sqlite3.connect(dest)) as dst:
            src.backup(dst)


def ensure_backup() -> Path | None:
    master = Path(MASTER)
    key = str(master.resolve())
    if key in _backed_up:
        return None
    stamp = time.strftime("%Y%m%d-%H%M%S")
    folder = master.resolve().parent / "Backups" / f"serato-web-{stamp}"
    folder.mkdir(parents=True, exist_ok=False)
    _backup_database(master, folder / "master.sqlite")
    root = master.resolve().parent / "root.sqlite"
    if root.is_file() and _mirror_allowed(root):
        _backup_database(root, folder / "root.sqlite")
    _backed_up.add(key)
    return folder


def begin_write() -> sqlite3.Connection:
    info = status()
    if info["open"]:
        raise SeratoOpen(info)
    ensure_backup()
    conn = sqlite3.connect(Path(MASTER), timeout=1)
    conn.row_factory = sqlite3.Row
    register(conn)
    try:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("BEGIN IMMEDIATE")
    except sqlite3.OperationalError as exc:
        conn.close()
        if "locked" in str(exc).lower():
            raise SeratoOpen(status()) from exc
        raise
    if _status_rows(conn)["open"]:
        conn.rollback()
        conn.close()
        raise SeratoOpen(status())
    return conn


def _space_id(conn: sqlite3.Connection, space: str) -> int:
    if space not in ALLOWED_SPACES:
        raise LibraryError("That space is not available here.")
    row = conn.execute("SELECT id FROM space WHERE name = ?", (space,)).fetchone()
    if row is None:
        raise LibraryError(f"{space} is not in this library.", 404)
    return int(row[0])


def _space_root(conn: sqlite3.Connection, space: str) -> int:
    row = conn.execute(
        """
        SELECT c.id FROM container c
        JOIN space s ON s.id = c.space_id
        WHERE s.name = ? AND c.type = 0
        """,
        (space,),
    ).fetchone()
    if row is None:
        raise LibraryError(f"{space} has no root crate.", 404)
    return int(row[0])


def _container(conn: sqlite3.Connection, crate_id: int, space: str) -> sqlite3.Row:
    row = conn.execute(
        """
        SELECT c.id, c.parent_id, c.name, c.type, c.space_id, s.name AS space_name
        FROM container c
        JOIN space s ON s.id = c.space_id
        WHERE c.id = ? AND s.name = ?
        """,
        (crate_id, space),
    ).fetchone()
    if row is None:
        raise LibraryError("That crate is not in this space.", 404)
    return row


def display_name(name: str) -> str:
    return name.split(NAME_SPLIT, 1)[0]


def _ancestry(conn: sqlite3.Connection, crate_id: int) -> list[str]:
    names = []
    seen: set[int] = set()
    current = crate_id
    while current and current not in seen:
        seen.add(current)
        row = conn.execute(
            "SELECT parent_id, name, type FROM container WHERE id = ?",
            (current,),
        ).fetchone()
        if row is None or int(row["type"]) == 0:
            break
        names.append(display_name(row["name"]))
        current = row["parent_id"]
    names.reverse()
    return names


def _descendant_ids(conn: sqlite3.Connection, crate_id: int) -> list[int]:
    rows = conn.execute(
        """
        WITH RECURSIVE tree(id) AS (
            SELECT id FROM container WHERE id = ?
            UNION ALL
            SELECT c.id
            FROM container c
            JOIN tree t ON c.parent_id = t.id
            WHERE c.parent_id != c.id
        )
        SELECT id FROM tree
        """,
        (crate_id,),
    ).fetchall()
    return [int(row[0]) for row in rows]


def _stored_name(conn: sqlite3.Connection, parent_id: int, display: str, crate_type: int, existing_id: int | None) -> str:
    text = (display or "").strip()
    if not text or NAME_SPLIT in text:
        raise LibraryError("Use a crate name without the Serato name separator.")
    if len(text) > 400:
        raise LibraryError("That crate name is too long.")
    suffix = ""
    if existing_id is not None:
        current = conn.execute("SELECT name FROM container WHERE id = ?", (existing_id,)).fetchone()
        if current and NAME_SPLIT in current[0]:
            suffix = current[0][current[0].find(NAME_SPLIT):]
    candidate = text + suffix
    clash = conn.execute(
        """
        SELECT id FROM container
        WHERE parent_id = ? AND name = ? COLLATE NOCASE AND type = ? AND id != ?
        """,
        (parent_id, candidate, crate_type, existing_id or -1),
    ).fetchone()
    if clash is None:
        return candidate
    if suffix:
        raise LibraryError("A crate with that name already exists here.")
    return text + NAME_SPLIT + uuid.uuid4().hex


def _filename(conn: sqlite3.Connection, crate_id: int, crate_type: int) -> str:
    ext = ".scrate" if int(crate_type) == 2 else ".crate"
    return "%%".join(_ancestry(conn, crate_id)) + ext


def _upsert_filename(conn: sqlite3.Connection, crate_id: int, filename: str, revision: int | None = None) -> None:
    columns = _columns(conn, "dj_container_metadata")
    if "revision" in columns:
        conn.execute(
            """
            INSERT INTO dj_container_metadata (container_id, revision, export_state, filename)
            VALUES (?, ?, 0, ?)
            ON CONFLICT(container_id) DO UPDATE SET
                filename = excluded.filename,
                revision = excluded.revision
            """,
            (crate_id, revision if revision is not None else int(time.time()), filename),
        )
        return
    conn.execute(
        """
        INSERT INTO dj_container_metadata (container_id, export_state, filename)
        VALUES (?, 0, ?)
        ON CONFLICT(container_id) DO UPDATE SET filename = excluded.filename
        """,
        (crate_id, filename),
    )


def _refresh_filenames(conn: sqlite3.Connection, crate_id: int, revision: int | None = None) -> None:
    for current in _descendant_ids(conn, crate_id):
        row = conn.execute("SELECT type FROM container WHERE id = ?", (current,)).fetchone()
        if row is None or int(row[0]) == 0:
            continue
        _upsert_filename(conn, current, _filename(conn, current, int(row[0])), revision)


def _next_revision(conn: sqlite3.Connection) -> int:
    columns = _columns(conn, "serato")
    if "revision" not in columns:
        return int(time.time())
    conn.execute("UPDATE serato SET revision = COALESCE(revision, 0) + 1")
    return int(conn.execute("SELECT revision FROM serato").fetchone()[0])


def _with_location(path: Path, fn) -> str | None:
    if not path.is_file() or not _mirror_allowed(path):
        return "Saved in the main library. That track's drive is not connected, so Serato may reconcile the edit when the drive returns."
    conn = sqlite3.connect(path, timeout=1)
    conn.row_factory = sqlite3.Row
    register(conn)
    try:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("BEGIN IMMEDIATE")
        warning = fn(conn)
        conn.commit()
        return warning
    except Exception as exc:
        conn.rollback()
        return f"Saved in the main library. The location database was not updated ({exc})."
    finally:
        conn.close()


def _asset_location(conn: sqlite3.Connection, asset_id: int) -> sqlite3.Row:
    row = conn.execute(
        "SELECT id, location_id, external_id, portable_id, file_name FROM asset WHERE id = ?",
        (asset_id,),
    ).fetchone()
    if row is None:
        raise LibraryError("That track is not in the library.", 404)
    return row


def _clean_text(field: str, value) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise LibraryError(f"{field} needs text.")
    limit = 16 if field == "emoji" else 4000
    if len(value) > limit:
        raise LibraryError(f"{field} is too long.")
    return value


def _clean_fields(fields: dict) -> dict:
    if not isinstance(fields, dict) or not fields:
        raise LibraryError("Choose a field to save.")
    unknown = set(fields) - TRACK_FIELDS
    if unknown:
        raise LibraryError("That field cannot be edited.")
    cleaned = {}
    for field, value in fields.items():
        if field in TEXT_FIELDS:
            cleaned[field] = _clean_text(field, value)
        elif field == "bpm":
            if value is None or value == "":
                cleaned[field] = None
            else:
                try:
                    number = float(value)
                except (TypeError, ValueError):
                    raise LibraryError("BPM needs a number.") from None
                if number < 0 or number > 999:
                    raise LibraryError("BPM needs to be between 0 and 999.")
                cleaned[field] = number
        elif field == "color":
            if value is None or value == "":
                cleaned[field] = 0xFFFFFF
            else:
                try:
                    color = int(value)
                except (TypeError, ValueError):
                    raise LibraryError("Color needs a number.") from None
                if color < 0 or color > 0xFFFFFF:
                    raise LibraryError("Color is out of range.")
                cleaned[field] = color
        elif field == "rating":
            if value is None or value == "":
                cleaned[field] = None
            else:
                try:
                    rating = float(value)
                except (TypeError, ValueError):
                    raise LibraryError("Rating needs a number.") from None
                if rating < 0 or rating > 1:
                    raise LibraryError("Rating needs to be from 0 to 1.")
                cleaned[field] = rating
        elif field == "is_beatgrid_locked":
            cleaned[field] = 1 if value in (True, 1, "1", "true") else 0
        elif field == "portable_id":
            cleaned[field] = _portable_for_existing_file(value)
    return cleaned


def _portable_for_existing_file(value) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LibraryError("Choose a file path.")
    path = Path(value).expanduser()
    try:
        if not path.is_file():
            raise LibraryError("That file is not on disk.", 404)
    except OSError as exc:
        raise LibraryError("That path could not be read.", 400) from exc
    try:
        relative = path.resolve().relative_to(Path.home())
        return relative.as_posix()
    except ValueError:
        return str(path)


def _assign(conn: sqlite3.Connection, table: str, columns: dict, where: str, key) -> None:
    present = _columns(conn, table)
    pairs = [(name, value) for name, value in columns.items() if name in present]
    if not pairs:
        return
    sql = f"UPDATE {table} SET {', '.join(name + ' = ?' for name, _ in pairs)} WHERE {where}"
    conn.execute(sql, [value for _, value in pairs] + [key])


def _mirror_asset(master: sqlite3.Connection, asset_id: int, columns: dict) -> str | None:
    asset = _asset_location(master, asset_id)
    paths = _location_paths(master)
    path = paths.get(int(asset["location_id"] or 0))
    external_id = asset["external_id"]
    if path is None or external_id is None:
        return "Saved in the main library. That track's drive is not connected, so Serato may reconcile the edit when the drive returns."

    def apply(conn: sqlite3.Connection) -> None:
        revision = _next_revision(conn)
        values = dict(columns)
        values["revision"] = revision
        _assign(conn, "asset", values, "id = ?", int(external_id))

    return _with_location(path, apply)


def save_track(asset_id: int, fields: dict, space: str = LIBRARY_SPACE) -> dict:
    cleaned = _clean_fields(fields)
    portable = cleaned.get("portable_id")
    conn = begin_write()
    try:
        _space_id(conn, space)
        row = conn.execute(
            """
            SELECT a.id FROM asset a
            JOIN space_asset sa ON sa.asset_id = a.id
            JOIN space s ON s.id = sa.space_id
            WHERE a.id = ? AND s.name = ?
            """,
            (asset_id, space),
        ).fetchone()
        if row is None:
            raise LibraryError("That track is not in this space.", 404)
        values = dict(cleaned)
        if portable is not None:
            values["file_name"] = Path(portable).name
            values["is_missing"] = 0
            try:
                values["file_size"] = Path(portable).stat().st_size if Path(portable).is_absolute() else (Path.home() / portable).stat().st_size
            except OSError:
                pass
        values["time_modified"] = int(time.time())
        _assign(conn, "asset", values, "id = ?", asset_id)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    mirror_values = {key: value for key, value in values.items() if key != "time_modified"}
    mirror_values["time_modified"] = values["time_modified"]
    with closing(read_conn()) as master:
        warning = _mirror_asset(master, asset_id, mirror_values)
    return {"ok": True, "id": asset_id, "warning": warning}


def _mark_smart(conn: sqlite3.Connection, crate_id: int) -> None:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'updated_smart_crate'"
    ).fetchone()
    if exists is None or "container_id" not in _columns(conn, "updated_smart_crate"):
        return
    conn.execute("INSERT INTO updated_smart_crate (container_id) VALUES (?)", (crate_id,))


def _rules_blob(rules) -> str:
    if isinstance(rules, str):
        try:
            rules = json.loads(rules)
        except json.JSONDecodeError as exc:
            raise LibraryError("Smart crate rules need to be JSON.") from exc
    if not isinstance(rules, dict) or not isinstance(rules.get("rules", []), list):
        raise LibraryError("Smart crate rules need a rules list.")
    return json.dumps(rules, ensure_ascii=False, separators=(",", ":"))


def _root_parent(master: sqlite3.Connection, root: sqlite3.Connection, parent_id: int, space: str) -> int | None:
    row = master.execute(
        """
        SELECT external_container_id FROM location_container
        WHERE container_id = ? AND location_id = 3 AND external_container_id IS NOT NULL
        """,
        (parent_id,),
    ).fetchone()
    if row is not None:
        return int(row[0])
    space_row = root.execute("SELECT id FROM space WHERE name = ?", (space,)).fetchone()
    if space_row is None:
        return None
    root_row = root.execute(
        "SELECT id FROM container WHERE space_id = ? AND type = 0",
        (int(space_row[0]),),
    ).fetchone()
    return int(root_row[0]) if root_row else None


def _insert_root_container(root: sqlite3.Connection, parent_id: int, name: str, crate_type: int, space: str, rules: str | None) -> int | None:
    space_row = root.execute("SELECT id FROM space WHERE name = ?", (space,)).fetchone()
    if space_row is None:
        return None
    revision = _next_revision(root)
    order = root.execute(
        "SELECT COALESCE(MAX(list_order), 0) + 1 FROM container WHERE parent_id = ?",
        (parent_id,),
    ).fetchone()[0]
    root.execute(
        """
        INSERT INTO container (revision, parent_id, name, type, list_order, space_id, time_added, expanded, portable_id, color)
        VALUES (?, ?, ?, ?, ?, ?, ?, 0, '', NULL)
        """,
        (revision, parent_id, name, crate_type, order, int(space_row[0]), int(time.time())),
    )
    crate_id = int(root.execute("SELECT last_insert_rowid()").fetchone()[0])
    _upsert_filename(root, crate_id, _filename(root, crate_id, crate_type), revision)
    if crate_type == 2 and rules is not None and "smart_crate_rules" in _tables(root):
        root.execute(
            """
            INSERT INTO smart_crate_rules (container_id, revision, version, rules, needs_refresh)
            VALUES (?, ?, 1, ?, 1)
            """,
            (crate_id, revision, rules),
        )
    return crate_id


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def _create_crate(conn: sqlite3.Connection, space: str, parent_id: int | None, name: str, smart: bool, rules) -> dict:
    root_id = _space_root(conn, space)
    parent = root_id if not parent_id or parent_id == root_id else int(parent_id)
    if parent != root_id:
        parent_row = _container(conn, parent, space)
        if int(parent_row["type"]) == 2:
            raise LibraryError("A smart crate cannot contain another crate.")
        if int(parent_row["type"]) == 0:
            parent = root_id
    crate_type = 2 if smart else 1
    stored = _stored_name(conn, parent, name, crate_type, None)
    if smart and not rules:
        rules = {"conjunction": "AND", "live_updates": True, "rules": [], "spaces": [space]}
    blob = _rules_blob(rules) if smart else None
    order = conn.execute(
        "SELECT COALESCE(MAX(list_order), 0) + 1 FROM container WHERE parent_id = ?",
        (parent,),
    ).fetchone()[0]
    conn.execute(
        """
        INSERT INTO container (parent_id, name, type, list_order, space_id, time_added, expanded, portable_id, color)
        VALUES (?, ?, ?, ?, ?, ?, 0, '', NULL)
        """,
        (parent, stored, crate_type, order, _space_id(conn, space), int(time.time())),
    )
    crate_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    _upsert_filename(conn, crate_id, _filename(conn, crate_id, crate_type))
    if smart:
        conn.execute(
            "INSERT INTO smart_crate_rules (container_id, version, rules) VALUES (?, 1, ?)",
            (crate_id, blob),
        )
        _mark_smart(conn, crate_id)
    warning = _link_new_crate(conn, crate_id, parent, stored, crate_type, space, blob)
    return {"ok": True, "id": crate_id, "name": display_name(stored), "warning": warning}


def _link_new_crate(conn: sqlite3.Connection, crate_id: int, parent_id: int, name: str, crate_type: int, space: str, rules: str | None) -> str | None:
    paths = _location_paths(conn)
    root_path = paths.get(3)
    if root_path is None:
        return "The crate is saved. The main drive database is not connected, so Serato may drop it on the next sync."

    created: dict[str, int | None | bool] = {"id": None, "ok": False}

    def apply(root: sqlite3.Connection):
        parent = _root_parent(conn, root, parent_id, space)
        if parent is None:
            return "The crate is saved. Its parent is not on the main drive, so Serato may drop it on the next sync."
        created["id"] = _insert_root_container(root, parent, name, crate_type, space, rules)
        created["ok"] = True
        return None

    warning = _with_location(root_path, apply)
    external_id = created["id"] if created["ok"] else None
    if external_id:
        conn.execute(
            """
            INSERT INTO location_container (container_id, location_id, external_container_id)
            VALUES (?, 3, ?)
            """,
            (crate_id, external_id),
        )
    return warning


def _rename_crate(conn: sqlite3.Connection, space: str, crate_id: int, name: str) -> dict:
    row = _container(conn, crate_id, space)
    if int(row["type"]) == 0:
        raise LibraryError("The space root cannot be renamed.")
    stored = _stored_name(conn, int(row["parent_id"]), name, int(row["type"]), crate_id)
    conn.execute("UPDATE container SET name = ? WHERE id = ?", (stored, crate_id))
    _refresh_filenames(conn, crate_id)
    warning = _mirror_container_fields(conn, crate_id, {"name": stored}, refresh_names=True)
    return {"ok": True, "id": crate_id, "name": display_name(stored), "warning": warning}


def _external_ids(conn: sqlite3.Connection, crate_ids: list[int]) -> list[int]:
    if not crate_ids:
        return []
    marks = ",".join("?" * len(crate_ids))
    rows = conn.execute(
        f"""
        SELECT external_container_id FROM location_container
        WHERE location_id = 3 AND external_container_id IS NOT NULL
          AND container_id IN ({marks})
        """,
        crate_ids,
    ).fetchall()
    return [int(row[0]) for row in rows]


def _delete_ids(conn: sqlite3.Connection, crate_ids: list[int]) -> None:
    if not crate_ids:
        return
    marks = ",".join("?" * len(crate_ids))
    location_column = "location_container_id" if "location_container_id" in _columns(conn, "container_asset") else None
    if location_column:
        conn.execute(
            f"""
            DELETE FROM container_asset
            WHERE location_container_id IN (
                SELECT id FROM location_container WHERE container_id IN ({marks})
            )
            """,
            crate_ids,
        )
        conn.execute(f"DELETE FROM location_container WHERE container_id IN ({marks})", crate_ids)
    elif "container_id" in _columns(conn, "container_asset"):
        conn.execute(f"DELETE FROM container_asset WHERE container_id IN ({marks})", crate_ids)
    if "smart_crate_rules" in _tables(conn):
        conn.execute(f"DELETE FROM smart_crate_rules WHERE container_id IN ({marks})", crate_ids)
    if "dj_container_metadata" in _tables(conn):
        conn.execute(f"DELETE FROM dj_container_metadata WHERE container_id IN ({marks})", crate_ids)
    for crate_id in reversed(crate_ids):
        conn.execute("DELETE FROM container WHERE id = ? AND type != 0", (crate_id,))


def _delete_crate(conn: sqlite3.Connection, space: str, crate_id: int) -> dict:
    row = _container(conn, crate_id, space)
    if int(row["type"]) == 0:
        raise LibraryError("The space root cannot be deleted.")
    ids = _descendant_ids(conn, crate_id)
    external = _external_ids(conn, ids)
    _delete_ids(conn, ids)
    warning = None
    root_path = _location_paths(conn).get(3)
    if external and root_path is not None:
        def apply(root: sqlite3.Connection):
            whole: list[int] = []
            for external_id in external:
                whole.extend(_descendant_ids(root, external_id))
            _delete_ids(root, list(dict.fromkeys(whole)))
            return None

        warning = _with_location(root_path, apply)
    elif external:
        warning = "Deleted from the main library. The drive database was not connected."
    return {"ok": True, "id": crate_id, "warning": warning}


def _mirror_container_fields(conn: sqlite3.Connection, crate_id: int, columns: dict, refresh_names: bool = False) -> str | None:
    external = _external_ids(conn, [crate_id])
    root_path = _location_paths(conn).get(3)
    if not external or root_path is None:
        return "Saved in the main library. This crate is not linked to the main drive, so Serato may reconcile it later."

    def apply(root: sqlite3.Connection):
        revision = _next_revision(root)
        values = dict(columns)
        values["revision"] = revision
        _assign(root, "container", values, "id = ?", external[0])
        if refresh_names:
            _refresh_filenames(root, external[0], revision)
        return None

    return _with_location(root_path, apply)


def _set_color(conn: sqlite3.Connection, space: str, crate_id: int, color) -> dict:
    row = _container(conn, crate_id, space)
    if int(row["type"]) == 0:
        raise LibraryError("The space root has no color.")
    if color is None or color == "":
        value = None
    else:
        try:
            value = int(color)
        except (TypeError, ValueError):
            raise LibraryError("Color needs a number.") from None
        if value < 0 or value > 0xFFFFFF:
            raise LibraryError("Color is out of range.")
        if value == 0xFFFFFF:
            value = None
    conn.execute("UPDATE container SET color = ? WHERE id = ?", (value, crate_id))
    warning = _mirror_container_fields(conn, crate_id, {"color": value})
    return {"ok": True, "id": crate_id, "warning": warning}


def _set_expanded(conn: sqlite3.Connection, space: str, crate_id: int, expanded) -> dict:
    _container(conn, crate_id, space)
    value = 1 if expanded in (True, 1, "1", "true") else 0
    conn.execute("UPDATE container SET expanded = ? WHERE id = ?", (value, crate_id))
    warning = _mirror_container_fields(conn, crate_id, {"expanded": value})
    return {"ok": True, "id": crate_id, "warning": warning}


def _set_rules(conn: sqlite3.Connection, space: str, crate_id: int, rules) -> dict:
    row = _container(conn, crate_id, space)
    if int(row["type"]) != 2:
        raise LibraryError("Only a smart crate has rules.")
    blob = _rules_blob(rules)
    conn.execute(
        "UPDATE smart_crate_rules SET version = 1, rules = ? WHERE container_id = ?",
        (blob, crate_id),
    )
    _mark_smart(conn, crate_id)
    external = _external_ids(conn, [crate_id])
    root_path = _location_paths(conn).get(3)
    warning = None
    if external and root_path is not None:
        def apply(root: sqlite3.Connection):
            revision = _next_revision(root)
            if "needs_refresh" in _columns(root, "smart_crate_rules"):
                root.execute(
                    """
                    UPDATE smart_crate_rules
                    SET rules = ?, version = 1, needs_refresh = 1, revision = ?
                    WHERE container_id = ?
                    """,
                    (blob, revision, external[0]),
                )
            return None

        warning = _with_location(root_path, apply)
    return {"ok": True, "id": crate_id, "warning": warning}


def _ensure_location_container(conn: sqlite3.Connection, crate_id: int, location_id: int) -> int:
    row = conn.execute(
        """
        SELECT id FROM location_container
        WHERE container_id = ? AND location_id = ?
        """,
        (crate_id, location_id),
    ).fetchone()
    if row is not None:
        return int(row[0])
    paths = _location_paths(conn)
    external = None
    if location_id in paths:
        raise LibraryError("That crate is not stored on the same drive as this track.")
    conn.execute(
        """
        INSERT INTO location_container (container_id, location_id, external_container_id)
        VALUES (?, ?, ?)
        """,
        (crate_id, location_id, external),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def _space_asset(conn: sqlite3.Connection, asset_id: int, space: str, create: bool) -> int:
    row = conn.execute(
        """
        SELECT sa.id FROM space_asset sa
        JOIN space s ON s.id = sa.space_id
        WHERE sa.asset_id = ? AND s.name = ?
        """,
        (asset_id, space),
    ).fetchone()
    if row is not None:
        return int(row[0])
    if not create:
        raise LibraryError("That track is not in this space.", 404)
    conn.execute(
        "INSERT INTO space_asset (asset_id, space_id) VALUES (?, ?)",
        (asset_id, _space_id(conn, space)),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def _membership(conn: sqlite3.Connection, crate_id: int, asset_id: int, space: str, add: bool) -> dict:
    row = _container(conn, crate_id, space)
    if int(row["type"]) == 2:
        raise LibraryError("Smart crates choose their tracks from rules.")
    if int(row["type"]) == 0:
        raise LibraryError("Tracks live in a crate, not the space root.")
    asset = _asset_location(conn, asset_id)
    _space_asset(conn, asset_id, space, create=False)
    if add:
        existing = conn.execute(
            """
            SELECT ca.id FROM container_asset ca
            JOIN location_container lc ON lc.id = ca.location_container_id
            WHERE lc.container_id = ? AND ca.asset_id = ?
            """,
            (crate_id, asset_id),
        ).fetchone()
        if existing is not None:
            return {"ok": True, "id": crate_id, "warning": None}
        location_id = int(asset["location_id"])
        location_container_id = _ensure_location_container(conn, crate_id, location_id)
        space_asset_id = _space_asset(conn, asset_id, space, create=False)
        order = conn.execute(
            """
            SELECT COALESCE(MAX(list_order), 0) + 1 FROM container_asset
            WHERE location_container_id IN (SELECT id FROM location_container WHERE container_id = ?)
            """,
            (crate_id,),
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO container_asset
                (asset_id, location_container_id, space_asset_id, external_container_asset_id, list_order, time_added)
            VALUES (?, ?, ?, NULL, ?, ?)
            """,
            (asset_id, location_container_id, space_asset_id, order, int(time.time())),
        )
        warning = _mirror_membership(conn, crate_id, asset_id, space, True)
        return {"ok": True, "id": crate_id, "warning": warning}

    conn.execute(
        """
        DELETE FROM container_asset
        WHERE asset_id = ? AND location_container_id IN (
            SELECT id FROM location_container WHERE container_id = ?
        )
        """,
        (asset_id, crate_id),
    )
    warning = _mirror_membership(conn, crate_id, asset_id, space, False)
    return {"ok": True, "id": crate_id, "warning": warning}


def _mirror_membership(conn: sqlite3.Connection, crate_id: int, asset_id: int, space: str, add: bool) -> str | None:
    external = _external_ids(conn, [crate_id])
    asset = _asset_location(conn, asset_id)
    root_path = _location_paths(conn).get(int(asset["location_id"] or 0))
    if int(asset["location_id"] or 0) != 3:
        root_path = _location_paths(conn).get(3) if external else None
    if not external or asset["external_id"] is None or root_path is None:
        return "Saved in the main library. This track's drive is not connected, so the crate membership may be reconciled later."
    if int(asset["location_id"] or 0) != 3 and root_path == _location_paths(conn).get(3):
        return "Saved in the main library. This track lives on another drive, so that drive's database was not changed."

    def apply(root: sqlite3.Connection):
        space_row = root.execute("SELECT id FROM space WHERE name = ?", (space,)).fetchone()
        if space_row is None:
            return "Saved in the main library. This space is not in the drive database."
        asset_row = root.execute(
            """
            SELECT sa.id FROM space_asset sa
            WHERE sa.asset_id = ? AND sa.space_id = ?
            """,
            (int(asset["external_id"]), int(space_row[0])),
        ).fetchone()
        revision = _next_revision(root)
        if add:
            if asset_row is None:
                root.execute(
                    "INSERT INTO space_asset (asset_id, space_id, revision) VALUES (?, ?, ?)",
                    (int(asset["external_id"]), int(space_row[0]), revision),
                )
                space_asset_id = int(root.execute("SELECT last_insert_rowid()").fetchone()[0])
            else:
                space_asset_id = int(asset_row[0])
            found = root.execute(
                "SELECT id FROM container_asset WHERE container_id = ? AND space_asset_id = ?",
                (external[0], space_asset_id),
            ).fetchone()
            if found is None:
                order = root.execute(
                    "SELECT COALESCE(MAX(list_order), 0) + 1 FROM container_asset WHERE container_id = ?",
                    (external[0],),
                ).fetchone()[0]
                root.execute(
                    """
                    INSERT INTO container_asset (revision, container_id, space_asset_id, list_order, time_added)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (revision, external[0], space_asset_id, order, int(time.time())),
                )
        else:
            if asset_row is not None:
                root.execute(
                    "DELETE FROM container_asset WHERE container_id = ? AND space_asset_id = ?",
                    (external[0], int(asset_row[0])),
                )
        return None

    return _with_location(root_path, apply)


def _prepare_container(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        """
        SELECT c.id FROM container c
        JOIN space s ON s.id = c.space_id
        WHERE s.name = 'Prepare' AND c.type = 1
        ORDER BY c.id
        LIMIT 1
        """,
    ).fetchone()
    if row is None:
        raise LibraryError("Prepare is not in this library.", 404)
    return int(row[0])


def _set_prepare(conn: sqlite3.Connection, asset_id: int, add: bool) -> dict:
    _asset_location(conn, asset_id)
    crate_id = _prepare_container(conn)
    if add:
        _space_asset(conn, asset_id, "Prepare", create=True)
        # Membership insert requires the asset to already be in the space.
        result = _membership(conn, crate_id, asset_id, "Prepare", True)
        return result
    conn.execute(
        """
        DELETE FROM container_asset
        WHERE asset_id = ? AND location_container_id IN (
            SELECT id FROM location_container WHERE container_id = ?
        )
        """,
        (asset_id, crate_id),
    )
    conn.execute(
        """
        DELETE FROM space_asset
        WHERE asset_id = ? AND space_id = (SELECT id FROM space WHERE name = 'Prepare')
        """,
        (asset_id,),
    )
    warning = _mirror_prepare(conn, asset_id, False)
    return {"ok": True, "id": asset_id, "warning": warning}


def _mirror_prepare(conn: sqlite3.Connection, asset_id: int, add: bool) -> str | None:
    asset = _asset_location(conn, asset_id)
    root_path = _location_paths(conn).get(3)
    if asset["external_id"] is None or root_path is None or int(asset["location_id"] or 0) != 3:
        return "Saved in the main library. Prepare on the drive database was left unchanged."

    def apply(root: sqlite3.Connection):
        space_row = root.execute("SELECT id FROM space WHERE name = 'Prepare'").fetchone()
        crate = root.execute(
            """
            SELECT c.id FROM container c
            JOIN space s ON s.id = c.space_id
            WHERE s.name = 'Prepare' AND c.type = 1
            ORDER BY c.id LIMIT 1
            """
        ).fetchone()
        if space_row is None or crate is None:
            return "Saved in the main library. Prepare is not in the drive database."
        revision = _next_revision(root)
        if add:
            row = root.execute(
                "SELECT id FROM space_asset WHERE asset_id = ? AND space_id = ?",
                (int(asset["external_id"]), int(space_row[0])),
            ).fetchone()
            if row is None:
                root.execute(
                    "INSERT INTO space_asset (asset_id, space_id, revision) VALUES (?, ?, ?)",
                    (int(asset["external_id"]), int(space_row[0]), revision),
                )
                space_asset_id = int(root.execute("SELECT last_insert_rowid()").fetchone()[0])
            else:
                space_asset_id = int(row[0])
            found = root.execute(
                "SELECT id FROM container_asset WHERE container_id = ? AND space_asset_id = ?",
                (int(crate[0]), space_asset_id),
            ).fetchone()
            if found is None:
                order = root.execute(
                    "SELECT COALESCE(MAX(list_order), 0) + 1 FROM container_asset WHERE container_id = ?",
                    (int(crate[0]),),
                ).fetchone()[0]
                root.execute(
                    """
                    INSERT INTO container_asset (revision, container_id, space_asset_id, list_order, time_added)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (revision, int(crate[0]), space_asset_id, order, int(time.time())),
                )
        else:
            row = root.execute(
                "SELECT id FROM space_asset WHERE asset_id = ? AND space_id = ?",
                (int(asset["external_id"]), int(space_row[0])),
            ).fetchone()
            if row is not None:
                root.execute(
                    "DELETE FROM container_asset WHERE container_id = ? AND space_asset_id = ?",
                    (int(crate[0]), int(row[0])),
                )
                root.execute("DELETE FROM space_asset WHERE id = ?", (int(row[0]),))
        return None

    return _with_location(root_path, apply)


def _remove_from_space(conn: sqlite3.Connection, asset_id: int, space: str) -> dict:
    _asset_location(conn, asset_id)
    _space_asset(conn, asset_id, space, create=False)
    conn.execute(
        """
        DELETE FROM container_asset
        WHERE asset_id = ? AND space_asset_id IN (
            SELECT sa.id FROM space_asset sa
            JOIN space s ON s.id = sa.space_id
            WHERE sa.asset_id = ? AND s.name = ?
        )
        """,
        (asset_id, asset_id, space),
    )
    external = conn.execute(
        "SELECT external_id, location_id FROM asset WHERE id = ?",
        (asset_id,),
    ).fetchone()
    conn.execute(
        """
        DELETE FROM space_asset
        WHERE asset_id = ? AND space_id = (SELECT id FROM space WHERE name = ?)
        """,
        (asset_id, space),
    )
    warning = None
    root_path = _location_paths(conn).get(3)
    if external and external["external_id"] is not None and int(external["location_id"] or 0) == 3 and root_path is not None:
        def apply(root: sqlite3.Connection):
            space_row = root.execute("SELECT id FROM space WHERE name = ?", (space,)).fetchone()
            if space_row is None:
                return None
            row = root.execute(
                "SELECT id FROM space_asset WHERE asset_id = ? AND space_id = ?",
                (int(external["external_id"]), int(space_row[0])),
            ).fetchone()
            if row is None:
                return None
            _next_revision(root)
            root.execute("DELETE FROM container_asset WHERE space_asset_id = ?", (int(row[0]),))
            root.execute("DELETE FROM space_asset WHERE id = ?", (int(row[0]),))
            return None

        warning = _with_location(root_path, apply)
    elif external and int(external["location_id"] or 0) != 3:
        warning = "Removed from the main library. The file was kept. The other drive's database was not changed."
    else:
        warning = "Removed from the library. The audio file was kept."
    return {"ok": True, "id": asset_id, "warning": warning}


def crate_action(payload: dict) -> dict:
    action = payload.get("action")
    space = payload.get("space") or LIBRARY_SPACE
    conn = begin_write()
    try:
        if action == "create":
            result = _create_crate(
                conn,
                space,
                payload.get("parent"),
                payload.get("name") or "",
                bool(payload.get("smart")),
                payload.get("rules"),
            )
        elif action == "rename":
            result = _rename_crate(conn, space, int(payload["id"]), payload.get("name") or "")
        elif action == "delete":
            result = _delete_crate(conn, space, int(payload["id"]))
        elif action == "color":
            result = _set_color(conn, space, int(payload["id"]), payload.get("color"))
        elif action == "expanded":
            result = _set_expanded(conn, space, int(payload["id"]), payload.get("expanded"))
        elif action == "rules":
            result = _set_rules(conn, space, int(payload["id"]), payload.get("rules"))
        elif action == "add":
            result = _membership(conn, int(payload["id"]), int(payload["asset"]), space, True)
        elif action == "remove":
            result = _membership(conn, int(payload["id"]), int(payload["asset"]), space, False)
        elif action == "prepare":
            result = _set_prepare(conn, int(payload["asset"]), bool(payload.get("add", True)))
            if payload.get("add", True):
                # _set_prepare(add) mirrors through _membership. A remove mirrors itself.
                pass
            if payload.get("add", True):
                extra = _mirror_prepare(conn, int(payload["asset"]), True)
                if extra and not result.get("warning"):
                    result["warning"] = extra
        elif action == "remove_library":
            result = _remove_from_space(conn, int(payload["asset"]), space)
        else:
            raise LibraryError("That crate action is not available.")
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def history_sessions() -> list[dict]:
    with closing(read_conn()) as conn:
        rows = conn.execute(
            """
            SELECT s.id, s.name, s.start_time, s.end_time,
                   COUNT(e.id) AS entries,
                   COALESCE(SUM(CASE WHEN e.played THEN 1 ELSE 0 END), 0) AS played
            FROM history_session s
            LEFT JOIN history_entry e ON e.session_id = s.id
            GROUP BY s.id
            ORDER BY s.start_time DESC, s.id DESC
            """
        ).fetchall()
    return [
        {
            "id": row["id"],
            "name": row["name"] or "Session",
            "start_time": row["start_time"],
            "end_time": row["end_time"],
            "entries": row["entries"],
            "played": row["played"],
        }
        for row in rows
    ]


def history_entries(session_id: int) -> dict:
    with closing(read_conn()) as conn:
        session = conn.execute(
            "SELECT id, name, start_time, end_time, notes FROM history_session WHERE id = ?",
            (session_id,),
        ).fetchone()
        if session is None:
            raise LibraryError("That history session is not in the library.", 404)
        rows = conn.execute(
            """
            SELECT id, asset_id, name, artist, album, bpm, key, length_ms,
                   start_time, end_time, played, deck, notes, file_name, is_missing
            FROM history_entry
            WHERE session_id = ?
            ORDER BY start_time, id
            """,
            (session_id,),
        ).fetchall()
    return {
        "id": session["id"],
        "name": session["name"] or "Session",
        "start_time": session["start_time"],
        "end_time": session["end_time"],
        "notes": session["notes"] or "",
        "entries": [
            {
                "id": row["id"],
                "asset_id": row["asset_id"],
                "name": row["name"] or "",
                "artist": row["artist"] or "",
                "album": row["album"] or "",
                "bpm": row["bpm"],
                "key": row["key"] or "",
                "length_ms": row["length_ms"],
                "start_time": row["start_time"],
                "end_time": row["end_time"],
                "played": int(row["played"] or 0),
                "deck": row["deck"] or "",
                "notes": row["notes"] or "",
                "file": row["file_name"] or "",
                "missing": int(row["is_missing"] or 0),
            }
            for row in rows
        ],
    }


def duplicate_groups(space: str = LIBRARY_SPACE) -> list[dict]:
    if space not in ALLOWED_SPACES:
        raise LibraryError("That space is not available here.")
    with closing(read_conn()) as conn:
        rows = conn.execute(
            """
            SELECT a.name, a.artist, CAST(a.length_ms / 1000 AS INTEGER) AS seconds,
                   GROUP_CONCAT(a.id) AS ids
            FROM asset a
            JOIN space_asset sa ON sa.asset_id = a.id
            JOIN space s ON s.id = sa.space_id
            WHERE s.name = ?
              AND TRIM(COALESCE(a.name, '')) != ''
              AND TRIM(COALESCE(a.artist, '')) != ''
              AND a.length_ms IS NOT NULL
            GROUP BY a.name, a.artist, seconds
            HAVING COUNT(*) > 1
            ORDER BY COUNT(*) DESC, a.name COLLATE NOCASE
            """,
            (space,),
        ).fetchall()
    groups = []
    for row in rows:
        ids = [int(part) for part in (row["ids"] or "").split(",") if part]
        groups.append(
            {
                "name": row["name"],
                "artist": row["artist"],
                "seconds": row["seconds"],
                "ids": ids,
            }
        )
    return groups


def _resolved(portable_id: str | None) -> str | None:
    if not portable_id:
        return None
    raw = Path(portable_id)
    candidates = [raw] if raw.is_absolute() else [Path.home() / portable_id, Path("/") / portable_id]
    for candidate in candidates:
        try:
            if candidate.is_file():
                return str(candidate)
        except OSError:
            continue
    return str(candidates[0])


def export_m3u(space: str, crate_id: int | None) -> str:
    if space not in ALLOWED_SPACES:
        raise LibraryError("That space is not available here.")
    with closing(read_conn()) as conn:
        if crate_id is None:
            rows = conn.execute(
                """
                SELECT a.name, a.artist, a.length_ms, a.portable_id
                FROM asset a
                JOIN space_asset sa ON sa.asset_id = a.id
                JOIN space s ON s.id = sa.space_id
                WHERE s.name = ?
                ORDER BY a.name COLLATE NOCASE, a.id
                """,
                (space,),
            ).fetchall()
            title = space
        else:
            crate = _container(conn, crate_id, space)
            title = display_name(crate["name"])
            rows = conn.execute(
                """
                SELECT a.name, a.artist, a.length_ms, a.portable_id
                FROM container_asset ca
                JOIN location_container lc ON lc.id = ca.location_container_id
                JOIN asset a ON a.id = ca.asset_id
                WHERE lc.container_id = ?
                ORDER BY ca.list_order, ca.id
                """,
                (crate_id,),
            ).fetchall()
    lines = ["#EXTM3U", f"#PLAYLIST:{title}"]
    for row in rows:
        path = _resolved(row["portable_id"])
        if not path:
            continue
        seconds = int((row["length_ms"] or 0) / 1000)
        artist = row["artist"] or ""
        name = row["name"] or "Untitled"
        label = f"{artist} - {name}" if artist else name
        lines.append(f"#EXTINF:{seconds},{label}")
        lines.append(path)
    return "\n".join(lines) + "\n"


def _match_portable(conn: sqlite3.Connection, space: str, raw_path: str) -> int | None:
    path = Path(raw_path.strip())
    if raw_path.startswith("file:"):
        path = Path(unquote(urlparse(raw_path).path))
    candidates = {str(path), path.as_posix()}
    try:
        candidates.add(path.resolve().relative_to(Path.home()).as_posix())
    except (ValueError, OSError):
        pass
    marks = ",".join("?" * len(candidates))
    row = conn.execute(
        f"""
        SELECT a.id FROM asset a
        JOIN space_asset sa ON sa.asset_id = a.id
        JOIN space s ON s.id = sa.space_id
        WHERE s.name = ? AND a.portable_id IN ({marks})
        LIMIT 1
        """,
        [space, *candidates],
    ).fetchone()
    return int(row[0]) if row else None


def import_m3u(space: str, parent_id: int | None, name: str, text: str) -> dict:
    if not isinstance(text, str) or not text.strip():
        raise LibraryError("The playlist is empty.")
    paths = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        paths.append(line)
    conn = begin_write()
    try:
        matched = []
        unmatched = []
        seen = set()
        for raw in paths:
            asset_id = _match_portable(conn, space, raw)
            if asset_id is None or asset_id in seen:
                if asset_id is None:
                    unmatched.append(raw)
                continue
            seen.add(asset_id)
            matched.append(asset_id)
        created = _create_crate(conn, space, parent_id, name or "Imported playlist", False, None)
        for asset_id in matched:
            _membership(conn, created["id"], asset_id, space, True)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {
        "ok": True,
        "id": created["id"],
        "name": created["name"],
        "added": len(matched),
        "unmatched": unmatched[:50],
        "unmatched_count": len(unmatched),
        "warning": created.get("warning"),
    }


def reveal(asset_id: int) -> dict:
    with closing(read_conn()) as conn:
        row = conn.execute("SELECT portable_id FROM asset WHERE id = ?", (asset_id,)).fetchone()
    if row is None:
        raise LibraryError("That track is not in the library.", 404)
    path = _resolved(row["portable_id"])
    if not path or not Path(path).is_file():
        raise LibraryError("That file is not on disk.", 404)
    subprocess.run(["open", "-R", path], check=False)
    return {"ok": True, "path": path}


def markers_for(path: str | None, on_disk: bool) -> dict:
    if not on_disk:
        return {"cues": [], "loops": [], "flips": [], "beatgrid": [], "found": False, "unavailable": True}
    parsed = read_serato_tags(path)
    parsed["unavailable"] = False
    return parsed
