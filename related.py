"""Saved links between tracks that go well together.

The links live in ``related.sqlite`` beside ``settings.json``. That file
is not Serato's ``master.sqlite``, so it can be written while Serato DJ
Pro is open. A track is stored by its file path. Title, artist, and
length are kept so a later lookup can still find the row when a move
changed the path and :func:`update_path` was not called.

:func:`update_path` is the function the file manager calls after a
cue-safe move. It rewrites the stored path and does not open
``master.sqlite`` for writing.

Suggestions are computed when the page asks. They are not stored.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from collections.abc import Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import app_config
import library

logger = logging.getLogger("serato.library.related")

SCHEMA_VERSION = 1
DB_NAME = "related.sqlite"
RELATED_CRATE_PREFIX = "Related - "
BPM_TOLERANCE = 0.06
SCORE_SAME_KEY = 40
SCORE_RELATIVE_KEY = 30
SCORE_ADJACENT_KEY = 24
SCORE_BPM = 30
SCORE_CRATE = 8
SCORE_CRATE_CAP = SCORE_CRATE * 3
SUGGEST_LIMIT = 12
NOTE_LIMIT = 500
LENGTH_LIMIT = 86_400_000
PATH_LIMIT = 4096
TRACK_COLUMNS = (
    "id",
    "path",
    "title",
    "artist",
    "length_ms",
    "created_at",
    "updated_at",
)
LINK_COLUMNS = (
    "id",
    "from_track_id",
    "to_track_id",
    "mutual",
    "note",
    "rating",
    "created_at",
    "updated_at",
)

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS track (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    artist TEXT NOT NULL DEFAULT '',
    length_ms INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (length_ms IS NULL OR length_ms >= 0)
);
CREATE UNIQUE INDEX IF NOT EXISTS track_path ON track(path);
CREATE INDEX IF NOT EXISTS track_fallback ON track(title, artist, length_ms);

CREATE TABLE IF NOT EXISTS link (
    id INTEGER PRIMARY KEY,
    from_track_id INTEGER NOT NULL REFERENCES track(id) ON DELETE CASCADE,
    to_track_id INTEGER NOT NULL REFERENCES track(id) ON DELETE CASCADE,
    mutual INTEGER NOT NULL CHECK (mutual IN (0, 1)),
    note TEXT NOT NULL DEFAULT '',
    rating INTEGER CHECK (rating IS NULL OR (rating BETWEEN 1 AND 5)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (from_track_id != to_track_id),
    UNIQUE (from_track_id, to_track_id)
);
CREATE INDEX IF NOT EXISTS link_from ON link(from_track_id);
CREATE INDEX IF NOT EXISTS link_to ON link(to_track_id);
"""

_lock = threading.RLock()
_KEY_POINTS = {
    "same": SCORE_SAME_KEY,
    "relative": SCORE_RELATIVE_KEY,
    "adjacent": SCORE_ADJACENT_KEY,
}
_KEY_REASONS = {
    "same": "same key",
    "relative": "relative key",
    "adjacent": "adjacent key",
}


@dataclass(frozen=True)
class CatalogTrack:
    """One library track used to match links and rank suggestions.

    Attributes:
        asset_id: Asset id in ``master.sqlite``.
        path: Canonical file path. Empty when the asset has no path.
        portable_id: Path stored by Serato, before canonicalizing.
        title: Track title. Empty when Serato has none.
        artist: Artist. Empty when Serato has none.
        length_ms: Length in milliseconds, or None.
        bpm: Tempo, or None when it is missing or not positive.
        key: Key text as stored. Empty when Serato has none.
        file_name: File name. Empty when Serato has none.
        crate_ids: Normal crate ids, excluding generated related crates.
    """

    asset_id: int
    path: str
    portable_id: str
    title: str
    artist: str
    length_ms: int | None
    bpm: float | None
    key: str
    file_name: str
    crate_ids: frozenset[int]


@dataclass(frozen=True)
class _Identity:
    """Path and fallback fields for one end of a link.

    Attributes:
        path: Canonical file path.
        title: Title stored beside the path.
        artist: Artist stored beside the path.
        length_ms: Length in milliseconds, or None.
    """

    path: str
    title: str
    artist: str
    length_ms: int | None


def related_db_path() -> Path:
    """Return the sidecar database path.

    Returns:
        ``related.sqlite`` inside the settings directory. The file is
        not created.
    """
    return app_config.config_dir() / DB_NAME


def identity_path(value: str) -> str:
    """Return the canonical path used as a track's key.

    Args:
        value: An absolute path, a home-relative Serato ``portable_id``,
            or a path starting with ``~``.

    Returns:
        The absolute path. An existing file wins. A relative id that is
        not on disk is resolved under the home directory.

    Raises:
        LibraryError: If the value is empty or longer than 4096 characters.
    """
    if not isinstance(value, str):
        raise library.LibraryError("A track path is required.")
    text = value.strip()
    if not text or "\x00" in text:
        raise library.LibraryError("A track path is required.")
    if len(text) > PATH_LIMIT:
        raise library.LibraryError("That track path is too long.")
    expanded = Path(text).expanduser()
    if expanded.is_absolute():
        chosen = expanded
    else:
        home_candidate = Path.home() / expanded
        root_candidate = Path("/") / expanded
        chosen = home_candidate
        for candidate in (home_candidate, root_candidate):
            try:
                if candidate.exists():
                    chosen = candidate
                    break
            except OSError:
                continue
    try:
        resolved = chosen.resolve(strict=False)
    except OSError:
        resolved = chosen
    return str(resolved)


def crate_name(title: str, path: str) -> str:
    """Build the Serato crate name for one track.

    Args:
        title: Track title. Blank falls through to the file name.
        path: File path used when the title is blank.

    Returns:
        ``Related - `` plus the label, trimmed to 400 characters.
    """
    label = _crate_label(title)
    if not label:
        label = _crate_label(Path(path).stem if path else "")
    if not label:
        label = "Untitled"
    name = f"{RELATED_CRATE_PREFIX}{label}"
    if len(name) > 400:
        name = name[:400].rstrip()
    if len(name) <= len(RELATED_CRATE_PREFIX):
        return f"{RELATED_CRATE_PREFIX}Untitled"
    return name


def clean_length(value: object) -> int | None:
    """Validate a length in milliseconds.

    Args:
        value: JSON or query value. None and an empty string mean unknown.

    Returns:
        The length, or None when it is unknown.

    Raises:
        LibraryError: If the value is not a whole number from 0 through
            24 hours, in milliseconds.
    """
    if value is None or value == "":
        return None
    if isinstance(value, bool) or isinstance(value, float):
        raise library.LibraryError("Length needs a whole number of milliseconds.")
    if isinstance(value, int):
        number = value
    elif isinstance(value, str):
        try:
            number = int(value.strip())
        except ValueError:
            raise library.LibraryError("Length needs a whole number of milliseconds.") from None
    else:
        raise library.LibraryError("Length needs a whole number of milliseconds.")
    if number < 0 or number > LENGTH_LIMIT:
        raise library.LibraryError("Length is out of range.")
    return number


def clean_note(value: object) -> str:
    """Validate an optional link note.

    Args:
        value: Note text. None is an empty note.

    Returns:
        The stripped note.

    Raises:
        LibraryError: If the value is not text or is longer than 500 characters.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        raise library.LibraryError("The note needs text.")
    text = value.strip()
    if len(text) > NOTE_LIMIT:
        raise library.LibraryError("The note is too long.")
    return text


def clean_rating(value: object) -> int | None:
    """Validate an optional link rating.

    Args:
        value: None, or a whole number from 1 to 5.

    Returns:
        The rating, or None when the link is unrated.

    Raises:
        LibraryError: If the value is not an allowed rating. Booleans are
            rejected.
    """
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise library.LibraryError("Rating needs a whole number from 1 to 5.")
    if value < 1 or value > 5:
        raise library.LibraryError("Rating needs a whole number from 1 to 5.")
    return value


def camelot_code(key: str) -> tuple[int, str] | None:
    """Map a key name onto the Camelot wheel.

    Args:
        key: Camelot code or traditional key. Blank and unknown names
            have no code.

    Returns:
        The wheel number from 1 to 12 and ``A`` or ``B``, or None.
    """
    kind = library.serato_key_type(key)
    if kind < 0:
        return None
    number = (kind % 12) + 1
    letter = "A" if kind < 12 else "B"
    return number, letter


def key_relation(left: str, right: str) -> str | None:
    """Compare two keys on the Camelot wheel.

    Args:
        left: Anchor key.
        right: Candidate key.

    Returns:
        ``same``, ``relative`` (same number, other letter), ``adjacent``
        (one step on the wheel, same letter, wrapping 12 to 1), or None.
    """
    first = camelot_code(left)
    second = camelot_code(right)
    if first is None or second is None:
        return None
    if first == second:
        return "same"
    if first[0] == second[0]:
        return "relative"
    if first[1] == second[1] and (second[0] - first[0]) % 12 in (1, 11):
        return "adjacent"
    return None


def bpm_relation(anchor: float, other: float) -> tuple[str, float] | None:
    """Compare tempos, including half time and double time.

    Args:
        anchor: Tempo of the open track.
        other: Tempo of the candidate.

    Returns:
        ``tempo``, ``half``, or ``double``, plus the relative distance
        from 0 to 0.06. None when neither the candidate nor its half or
        double sits within 6 percent of the anchor. ``half`` means the
        candidate is about half the anchor. ``double`` means it is about
        twice the anchor.
    """
    if anchor <= 0 or other <= 0:
        return None
    best: tuple[str, float] | None = None
    for kind, candidate in (("tempo", other), ("half", other * 2), ("double", other / 2)):
        delta = abs(candidate - anchor) / anchor
        if round(delta, 6) > BPM_TOLERANCE:
            continue
        if best is None or delta < best[1]:
            best = (kind, delta)
    return best


def score_pair(anchor: CatalogTrack, other: CatalogTrack) -> tuple[int, list[str]] | None:
    """Score one candidate against the open track.

    Args:
        anchor: Open track.
        other: Candidate.

    Returns:
        The score and the reason phrases, or None when the tracks share
        no compatible key, no tempo, and no crate. A same key scores
        higher than a relative key, which scores higher than an adjacent
        key. A closer tempo scores higher than one at the edge of the
        window. Shared crates add until the third crate.
    """
    reasons: list[str] = []
    score = 0
    relation = key_relation(anchor.key, other.key)
    if relation is not None:
        score += _KEY_POINTS[relation]
        reasons.append(_KEY_REASONS[relation])
    if anchor.bpm is not None and other.bpm is not None:
        tempo = bpm_relation(anchor.bpm, other.bpm)
        if tempo is not None:
            kind, delta = tempo
            points = round(SCORE_BPM * (1 - min(delta, BPM_TOLERANCE) / BPM_TOLERANCE))
            if points < 1:
                points = 1
            score += points
            reasons.append(_bpm_reason(kind, delta))
    shared = len(anchor.crate_ids & other.crate_ids)
    if shared:
        score += min(shared * SCORE_CRATE, SCORE_CRATE_CAP)
        reasons.append(_crate_reason(shared))
    if score <= 0:
        return None
    return score, reasons


def rank_suggestions(
    anchor: CatalogTrack,
    catalog: Sequence[CatalogTrack],
    linked_paths: set[str],
) -> list[dict[str, object]]:
    """Rank library tracks that fit the open track.

    Args:
        anchor: Open track.
        catalog: Tracks in the same space.
        linked_paths: Canonical paths that are already saved. Those
            tracks are left out of the list.

    Returns:
        Up to 12 suggestion dicts, highest score first. Each dict has
        ``asset_id``, ``path``, ``title``, ``artist``, ``length_ms``,
        ``bpm``, ``key``, ``score``, and ``reasons``.
    """
    if not anchor.path:
        return []
    linked = {path.casefold() for path in linked_paths}
    anchor_path = anchor.path.casefold()
    ranked: list[tuple[int, str, int, CatalogTrack, list[str]]] = []
    for track in catalog:
        if track.asset_id == anchor.asset_id or not track.path:
            continue
        folded = track.path.casefold()
        if folded == anchor_path or folded in linked:
            continue
        scored = score_pair(anchor, track)
        if scored is None:
            continue
        score, reasons = scored
        ranked.append((-score, track.title.casefold(), track.asset_id, track, reasons))
    ranked.sort()
    suggestions: list[dict[str, object]] = []
    for _neg, _title, _asset, track, reasons in ranked[:SUGGEST_LIMIT]:
        suggestions.append(
            {
                "asset_id": track.asset_id,
                "path": track.path,
                "title": track.title,
                "artist": track.artist,
                "length_ms": track.length_ms,
                "bpm": track.bpm,
                "key": track.key,
                "score": -_neg,
                "reasons": reasons,
            }
        )
    return suggestions


def load_catalog(space: str) -> list[CatalogTrack]:
    """Read the tracks and normal crates for one space.

    Args:
        space: An allowed Serato space name.

    Returns:
        Tracks in asset id order. Smart crates and crates whose visible
        name starts with ``Related - `` are not included in ``crate_ids``.

    Raises:
        LibraryError: If the space name is not allowed or the library
            file is missing.
    """
    _require_space(space)
    membership: dict[int, set[int]] = {}
    with closing(library.read_conn()) as conn:
        assets = conn.execute(
            """
            SELECT a.id, a.name, a.artist, a.bpm, a.key, a.length_ms,
                   a.portable_id, a.file_name
            FROM asset a
            JOIN space_asset sa ON sa.asset_id = a.id
            JOIN space s ON s.id = sa.space_id
            WHERE s.name = ?
            ORDER BY a.id
            """,
            (space,),
        ).fetchall()
        for row in conn.execute(
            """
            SELECT c.id AS crate_id, c.name, c.type, ca.asset_id
            FROM container_asset ca
            JOIN location_container lc ON lc.id = ca.location_container_id
            JOIN container c ON c.id = lc.container_id
            JOIN space s ON s.id = c.space_id
            WHERE s.name = ?
            """,
            (space,),
        ):
            if _as_int(row["type"]) != 1:
                continue
            stored = row["name"]
            if not isinstance(stored, str):
                continue
            visible = library.display_name(stored)
            if visible.startswith(RELATED_CRATE_PREFIX):
                continue
            membership.setdefault(_as_int(row["asset_id"]), set()).add(_as_int(row["crate_id"]))
    tracks: list[CatalogTrack] = []
    for row in assets:
        portable = row["portable_id"] if isinstance(row["portable_id"], str) else ""
        path = ""
        if portable.strip():
            try:
                path = identity_path(portable)
            except library.LibraryError:
                path = ""
        tracks.append(
            CatalogTrack(
                asset_id=_as_int(row["id"]),
                path=path,
                portable_id=portable,
                title=_label(row["name"]),
                artist=_label(row["artist"]),
                length_ms=_optional_db_int(row["length_ms"]),
                bpm=_optional_bpm(row["bpm"]),
                key=_label(row["key"]),
                file_name=_label(row["file_name"]),
                crate_ids=frozenset(membership.get(_as_int(row["id"]), ())),
            )
        )
    return tracks


def match_catalog(catalog: Sequence[CatalogTrack], requested: str) -> CatalogTrack | None:
    """Find the library track for a path.

    Args:
        catalog: Tracks from :func:`load_catalog`.
        requested: Absolute path or Serato ``portable_id``.

    Returns:
        The first matching track in catalog order, or None.
    """
    if not isinstance(requested, str) or not requested.strip():
        return None
    try:
        wanted = identity_path(requested)
    except library.LibraryError:
        return None
    raw = requested.strip()
    for track in catalog:
        if not track.path:
            continue
        if track.path == wanted or track.portable_id == raw:
            return track
    folded = wanted.casefold()
    for track in catalog:
        if track.path and track.path.casefold() == folded:
            return track
    return None


def identity_for_asset(asset_id: int, space: str) -> tuple[str, str, str, int | None]:
    """Return the stored identity of one library track.

    Args:
        asset_id: Asset id.
        space: Space that must contain the track.

    Returns:
        Path, title, artist, and length in milliseconds.

    Raises:
        LibraryError: If the track is not in the space or has no file path.
    """
    if isinstance(asset_id, bool) or not isinstance(asset_id, int):
        raise library.LibraryError("That track is not in this space.", 404)
    for track in load_catalog(space):
        if track.asset_id != asset_id:
            continue
        if not track.path:
            raise library.LibraryError("That track has no file path.")
        return track.path, track.title, track.artist, track.length_ms
    raise library.LibraryError("That track is not in this space.", 404)


def update_path(old_path: str, new_path: str) -> bool:
    """Point a stored identity at a new file path.

    The file manager calls this after a cue-safe move. The sidecar row
    is updated. ``master.sqlite`` is not opened.

    Args:
        old_path: Path currently stored, or the path before the move.
        new_path: Path after the move.

    Returns:
        True when a row uses the new path, including when it already
        did. False when ``old_path`` does not match a stored path.

    Raises:
        LibraryError: If either path is empty, or ``new_path`` already
            belongs to a different identity.
    """
    old_key = identity_path(old_path)
    new_key = identity_path(new_path)
    with _lock:
        conn = _connect()
        try:
            row = _track_by_path(conn, old_key)
            if row is None and old_path.strip() != old_key:
                row = _track_by_path(conn, old_path.strip())
            if row is None:
                conn.rollback()
                return False
            track_id = _as_int(row["id"])
            occupant = _track_by_path(conn, new_key)
            if occupant is not None and _as_int(occupant["id"]) != track_id:
                raise library.LibraryError(
                    "That path already identifies a different track.",
                    409,
                )
            if str(row["path"]) != new_key:
                conn.execute(
                    "UPDATE track SET path = ?, updated_at = ? WHERE id = ?",
                    (new_key, _now(), track_id),
                )
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def add_link(
    source_path: str,
    target_path: str,
    *,
    mutual: bool,
    note: object = "",
    rating: object = None,
    source_title: str = "",
    source_artist: str = "",
    source_length_ms: int | None = None,
    target_title: str = "",
    target_artist: str = "",
    target_length_ms: int | None = None,
    space: str = library.LIBRARY_SPACE,
) -> dict[str, object]:
    """Save or update one related-track link.

    Args:
        source_path: Path of the open track.
        target_path: Path of the track it links to.
        mutual: True stores a two-way link. False stores a one-way link
            from the source to the target.
        note: Optional note such as ``blend out of``. None stores an empty note.
        rating: Optional whole number from 1 to 5, or None.
        source_title: Title used when the source is not in the library.
        source_artist: Artist used when the source is not in the library.
        source_length_ms: Length used when the source is not in the library.
        target_title: Title used when the target is not in the library.
        target_artist: Artist used when the target is not in the library.
        target_length_ms: Length used when the target is not in the library.
        space: Space used to fill titles from the library when the path
            matches a track there.

    Returns:
        ``ok``, the link ``id``, and ``mutual``.

    Raises:
        LibraryError: If the paths are the same, the note or rating is
            invalid, or the sidecar file cannot be written.
    """
    if not isinstance(mutual, bool):
        raise library.LibraryError("Choose a one-way or two-way link.")
    stored_note = clean_note(note)
    stored_rating = clean_rating(rating)
    source_length = clean_length(source_length_ms)
    target_length = clean_length(target_length_ms)
    catalog = load_catalog(space)
    source = _coalesce(catalog, source_path, source_title, source_artist, source_length)
    target = _coalesce(catalog, target_path, target_title, target_artist, target_length)
    if source.path == target.path:
        raise library.LibraryError("A track cannot be related to itself.")
    with _lock:
        conn = _connect()
        try:
            source_id = _ensure_track(conn, source, catalog)
            target_id = _ensure_track(conn, target, catalog)
            link_id = _upsert_link(conn, source_id, target_id, mutual, stored_note, stored_rating)
            conn.commit()
        except library.LibraryError:
            conn.rollback()
            raise
        except sqlite3.Error:
            conn.rollback()
            logger.exception("Related tracks file failed")
            raise library.LibraryError("The related-tracks file could not be saved.", 500) from None
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    return {"ok": True, "id": link_id, "mutual": mutual}


def remove_link(link_id: int) -> dict[str, object]:
    """Delete one saved link.

    Args:
        link_id: Link id from a saved-link payload.

    Returns:
        ``ok`` and the deleted id. The identity rows are kept.

    Raises:
        LibraryError: If the id is not a saved link.
    """
    if isinstance(link_id, bool) or not isinstance(link_id, int) or link_id <= 0:
        raise library.LibraryError("That link is not in the related tracks.", 404)
    with _lock:
        conn = _connect()
        try:
            deleted = conn.execute("DELETE FROM link WHERE id = ?", (link_id,))
            if deleted.rowcount == 0:
                raise library.LibraryError("That link is not in the related tracks.", 404)
            conn.commit()
        except library.LibraryError:
            conn.rollback()
            raise
        except sqlite3.Error:
            conn.rollback()
            logger.exception("Related tracks file failed")
            raise library.LibraryError("The related-tracks file could not be saved.", 500) from None
        finally:
            conn.close()
    return {"ok": True, "id": link_id}


def overview(
    path: str,
    *,
    space: str = library.LIBRARY_SPACE,
    title: str | None = None,
    artist: str | None = None,
    length_ms: int | None = None,
) -> dict[str, object]:
    """Return saved links and suggestions for one track.

    Args:
        path: File path or Serato ``portable_id``.
        space: Space whose tracks are ranked as suggestions.
        title: Fallback title when the path is not in the library.
        artist: Fallback artist when the path is not in the library.
        length_ms: Fallback length when the path is not in the library.

    Returns:
        ``schema_version``, the canonical ``path``, the anchor ``track``,
        ``crate_name``, ``saved``, and ``suggested``. A unique fallback
        match updates the stored path. Suggestions are not written.

    Raises:
        LibraryError: If the path is empty or the space is not allowed.
    """
    canonical = identity_path(path)
    catalog = load_catalog(space)
    anchor = match_catalog(catalog, path)
    query_title = _label(title)
    query_artist = _label(artist)
    query_length = clean_length(length_ms)
    saved: list[dict[str, object]] = []
    with _lock:
        conn = _connect()
        try:
            row = _track_by_path(conn, canonical)
            if row is None and anchor is not None:
                row = _rebind_fallback(
                    conn,
                    canonical,
                    anchor.title,
                    anchor.artist,
                    anchor.length_ms,
                    catalog,
                )
            elif row is None:
                row = _rebind_fallback(
                    conn, canonical, query_title, query_artist, query_length, catalog
                )
            if row is not None and str(row["path"]) != canonical:
                occupant = _track_by_path(conn, canonical)
                if occupant is None or _as_int(occupant["id"]) == _as_int(row["id"]):
                    conn.execute(
                        "UPDATE track SET path = ?, updated_at = ? WHERE id = ?",
                        (canonical, _now(), _as_int(row["id"])),
                    )
            if row is not None and anchor is not None:
                _sync_metadata(
                    conn, _as_int(row["id"]), anchor.title, anchor.artist, anchor.length_ms
                )
            if row is not None:
                saved = _saved_links(conn, _as_int(row["id"]), catalog)
            conn.commit()
        except sqlite3.Error:
            conn.rollback()
            logger.exception("Related tracks file failed")
            raise library.LibraryError("The related-tracks file could not be read.", 500) from None
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    track = _anchor_payload(anchor, canonical, query_title, query_artist, query_length)
    linked_paths = {str(item["track"]["path"]) for item in saved if isinstance(item.get("track"), dict)}
    suggested = rank_suggestions(anchor, catalog, linked_paths) if anchor is not None else []
    return {
        "schema_version": SCHEMA_VERSION,
        "path": canonical,
        "track": track,
        "crate_name": crate_name(str(track["title"]), str(track["path"])),
        "saved": saved,
        "suggested": suggested,
    }


def refresh_crate(
    path: str,
    *,
    space: str = library.LIBRARY_SPACE,
    title: str | None = None,
    artist: str | None = None,
    length_ms: int | None = None,
) -> dict[str, object]:
    """Create or replace a Serato crate of the saved related tracks.

    Args:
        path: File path or Serato ``portable_id`` of the open track.
        space: Space that receives the crate.
        title: Fallback title passed through to :func:`overview`.
        artist: Fallback artist passed through to :func:`overview`.
        length_ms: Fallback length passed through to :func:`overview`.

    Returns:
        ``ok``, the crate ``id``, ``name``, ``created``, ``added`` asset
        ids, ``removed`` asset ids, ``missing`` tracks that are not in
        the library, and ``warning``.

    Raises:
        LibraryError: If the track is not in the space.
        SeratoOpen: If Serato still has the library open. The sidecar
            links are left as they were.
    """
    view = overview(path, space=space, title=title, artist=artist, length_ms=length_ms)
    anchor = view["track"]
    if not isinstance(anchor, dict) or not anchor.get("in_library"):
        raise library.LibraryError("That track is not in this space.", 404)
    name = str(view["crate_name"])
    desired: list[int] = []
    missing: list[dict[str, object]] = []
    saved = view["saved"]
    if isinstance(saved, list):
        for item in saved:
            if not isinstance(item, dict):
                continue
            track = item.get("track")
            if not isinstance(track, dict):
                continue
            asset_id = track.get("asset_id")
            if track.get("in_library") and isinstance(asset_id, int) and not isinstance(asset_id, bool):
                desired.append(asset_id)
            else:
                missing.append(
                    {
                        "path": track.get("path"),
                        "title": track.get("title"),
                        "artist": track.get("artist"),
                    }
                )
    crate_id, created, warning = _ensure_crate(space, name)
    current = _crate_asset_ids(crate_id)
    wanted = set(desired)
    removed = sorted(current - wanted)
    added = sorted(wanted - current)
    for asset_id in removed:
        result = library.crate_action(
            {"action": "remove", "space": space, "id": crate_id, "asset": asset_id}
        )
        if result.get("warning") and not warning:
            warning = result.get("warning")
    for asset_id in added:
        result = library.crate_action(
            {"action": "add", "space": space, "id": crate_id, "asset": asset_id}
        )
        if result.get("warning") and not warning:
            warning = result.get("warning")
    return {
        "ok": True,
        "id": crate_id,
        "name": name,
        "created": created,
        "added": added,
        "removed": removed,
        "missing": missing,
        "warning": warning,
    }


def _require_space(space: str) -> None:
    """Reject a space this page does not edit.

    Args:
        space: Requested space name.

    Raises:
        LibraryError: If the space is not one of the four allowed names.
    """
    if space not in library.ALLOWED_SPACES:
        raise library.LibraryError("That space is not available here.")


def _crate_label(value: str) -> str:
    """Collapse a title into a crate label.

    Args:
        value: Title or file stem.

    Returns:
        The label with the Serato name separator removed, or an empty string.
    """
    return " ".join(value.replace(library.NAME_SPLIT, " ").split())


def _label(value: object) -> str:
    """Return stripped text, or an empty string.

    Args:
        value: A database or JSON value.

    Returns:
        The stripped string. Any other type becomes an empty string.
    """
    if not isinstance(value, str):
        return ""
    return value.strip()


def _optional_db_int(value: object) -> int | None:
    """Return a database integer, or None.

    Args:
        value: A SQLite integer.

    Returns:
        The integer. Booleans, other types, and negative numbers become None.
    """
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _optional_bpm(value: object) -> float | None:
    """Return a positive tempo, or None.

    Args:
        value: A SQLite number.

    Returns:
        The tempo when it is greater than 0 and at most 999. Other values
        become None.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if number <= 0 or number > 999:
        return None
    return number


def _as_int(value: object) -> int:
    """Return a SQLite integer.

    Args:
        value: A value already known to be an integer column.

    Returns:
        The integer.

    Raises:
        LibraryError: If the column is not an integer.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise library.LibraryError("The related-tracks file could not be read.", 500)
    return value


def _now() -> str:
    """Return the current UTC time as text.

    Returns:
        ``YYYY-MM-DDTHH:MM:SSZ``.
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _bpm_reason(kind: str, delta: float) -> str:
    """Describe a tempo match.

    Args:
        kind: ``tempo``, ``half``, or ``double``.
        delta: Relative distance from 0 to 0.06.

    Returns:
        A short reason such as ``BPM match`` or ``half-time BPM within 3%``.
    """
    percent = delta * 100
    extra = ""
    if percent >= 0.05:
        shown = round(percent, 1)
        text = str(int(shown)) if float(shown).is_integer() else str(shown)
        extra = f" within {text}%"
    if kind == "half":
        return f"half-time BPM{extra}"
    if kind == "double":
        return f"double-time BPM{extra}"
    if extra:
        return f"BPM{extra}"
    return "BPM match"


def _crate_reason(count: int) -> str:
    """Describe how many crates two tracks share.

    Args:
        count: Shared crate count, at least 1.

    Returns:
        ``1 shared crate`` or ``N shared crates``.
    """
    if count == 1:
        return "1 shared crate"
    return f"{count} shared crates"


def _connect() -> sqlite3.Connection:
    """Open the sidecar database and create the schema when needed.

    Returns:
        A connection with foreign keys enabled. The caller closes it.

    Raises:
        LibraryError: If the directory cannot be created or the file was
            written by a newer schema.
    """
    with _lock:
        path = related_db_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            logger.exception("Related tracks directory failed")
            raise library.LibraryError("The related-tracks file could not be saved.", 500) from None
        try:
            conn = sqlite3.connect(path, timeout=5)
        except sqlite3.Error:
            logger.exception("Related tracks file failed")
            raise library.LibraryError("The related-tracks file could not be saved.", 500) from None
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            _ensure_schema(conn)
        except Exception:
            conn.close()
            raise
        return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Create version 1 tables when the file is new.

    Args:
        conn: Open sidecar connection.

    Raises:
        LibraryError: If ``user_version`` is not 0 or 1.
    """
    version = _as_int(conn.execute("PRAGMA user_version").fetchone()[0])
    if version == SCHEMA_VERSION:
        return
    if version != 0:
        raise library.LibraryError(
            "The related-tracks file was written by a newer version of this app.",
            500,
        )
    conn.executescript(_SCHEMA_SQL)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()


def _track_by_path(conn: sqlite3.Connection, key: str) -> sqlite3.Row | None:
    """Find one identity row by path.

    Args:
        conn: Open sidecar connection.
        key: Canonical path or a raw stored path.

    Returns:
        The row. A case-insensitive match is used only when it is unique.
        None when the path is missing or ambiguous.
    """
    exact = conn.execute("SELECT * FROM track WHERE path = ?", (key,)).fetchone()
    if exact is not None:
        return exact
    folded = key.casefold()
    matches = [
        row
        for row in conn.execute("SELECT * FROM track")
        if str(row["path"]).casefold() == folded
    ]
    if len(matches) == 1:
        return matches[0]
    return None


def _fallback_ids(
    conn: sqlite3.Connection, title: str, artist: str, length_ms: int | None
) -> list[int]:
    """Find identities with the same title, artist, and whole-second length.

    Args:
        conn: Open sidecar connection.
        title: Title to match. Blank skips the search.
        artist: Artist to match. Blank skips the search.
        length_ms: Length in milliseconds. None skips the search.

    Returns:
        Matching identity ids. More than one means the match is ambiguous.
    """
    if not title.strip() or not artist.strip() or length_ms is None:
        return []
    want_title = title.strip().casefold()
    want_artist = artist.strip().casefold()
    seconds = length_ms // 1000
    found: list[int] = []
    for row in conn.execute("SELECT id, title, artist, length_ms FROM track"):
        if str(row["title"] or "").strip().casefold() != want_title:
            continue
        if str(row["artist"] or "").strip().casefold() != want_artist:
            continue
        stored = row["length_ms"]
        if isinstance(stored, bool) or not isinstance(stored, int):
            continue
        if stored // 1000 != seconds:
            continue
        found.append(_as_int(row["id"]))
    return found


def _rebind_fallback(
    conn: sqlite3.Connection,
    new_path: str,
    title: str,
    artist: str,
    length_ms: int | None,
    catalog: Sequence[CatalogTrack],
) -> sqlite3.Row | None:
    """Move a unique fallback identity onto a new path.

    Args:
        conn: Open sidecar connection inside a transaction.
        new_path: Canonical path that did not match a row.
        title: Title to match.
        artist: Artist to match.
        length_ms: Length to match.
        catalog: Library tracks. When the stored path is still a different
            file in the library, the row is a second copy and is not moved.

    Returns:
        The updated row, or None when the match is missing, ambiguous,
        still present in the library at another path, or the new path
        is already used.
    """
    ids = _fallback_ids(conn, title, artist, length_ms)
    if len(ids) != 1:
        return None
    current = conn.execute("SELECT * FROM track WHERE id = ?", (ids[0],)).fetchone()
    if current is None:
        return None
    still_there = match_catalog(catalog, str(current["path"]))
    if still_there is not None and still_there.path != new_path:
        return None
    occupant = _track_by_path(conn, new_path)
    if occupant is not None:
        if _as_int(occupant["id"]) == ids[0]:
            return occupant
        return None
    conn.execute(
        "UPDATE track SET path = ?, updated_at = ? WHERE id = ?",
        (new_path, _now(), ids[0]),
    )
    return conn.execute("SELECT * FROM track WHERE id = ?", (ids[0],)).fetchone()


def _sync_metadata(
    conn: sqlite3.Connection,
    track_id: int,
    title: str,
    artist: str,
    length_ms: int | None,
) -> None:
    """Copy library title, artist, and length onto an identity.

    Args:
        conn: Open sidecar connection.
        track_id: Identity id.
        title: Library title. Blank leaves the stored title in place.
        artist: Library artist. Blank leaves the stored artist in place.
        length_ms: Library length. None leaves the stored length in place.
    """
    row = conn.execute(
        "SELECT title, artist, length_ms FROM track WHERE id = ?",
        (track_id,),
    ).fetchone()
    if row is None:
        return
    new_title = title.strip() or str(row["title"] or "")
    new_artist = artist.strip() or str(row["artist"] or "")
    new_length = length_ms if length_ms is not None else row["length_ms"]
    if new_title == row["title"] and new_artist == row["artist"] and new_length == row["length_ms"]:
        return
    conn.execute(
        "UPDATE track SET title = ?, artist = ?, length_ms = ?, updated_at = ? WHERE id = ?",
        (new_title, new_artist, new_length, _now(), track_id),
    )


def _coalesce(
    catalog: Sequence[CatalogTrack],
    path: str,
    title: str,
    artist: str,
    length_ms: int | None,
) -> _Identity:
    """Prefer library fields when the path is in the space.

    Args:
        catalog: Tracks in the space.
        path: Caller path.
        title: Caller title, used when the library has no match.
        artist: Caller artist, used when the library has no match.
        length_ms: Caller length, used when the library has no match.

    Returns:
        The identity to store.

    Raises:
        LibraryError: If a caller title or artist is not text.
    """
    key = identity_path(path)
    match = match_catalog(catalog, path)
    if match is not None:
        return _Identity(match.path, match.title, match.artist, match.length_ms)
    return _Identity(key, _clean_caller_label(title), _clean_caller_label(artist), length_ms)


def _clean_caller_label(value: object) -> str:
    """Validate a title or artist supplied by the caller.

    Args:
        value: Text, or None.

    Returns:
        The stripped text.

    Raises:
        LibraryError: If the value is not text or is longer than 4000 characters.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        raise library.LibraryError("That request is not valid.")
    if len(value) > 4000:
        raise library.LibraryError("That request is not valid.")
    return value.strip()


def _ensure_track(
    conn: sqlite3.Connection, identity: _Identity, catalog: Sequence[CatalogTrack]
) -> int:
    """Insert an identity or refresh the row that already matches.

    Args:
        conn: Open sidecar connection.
        identity: Path and fallback fields.
        catalog: Library tracks used to tell a move from a second copy.

    Returns:
        The identity id.
    """
    row = _track_by_path(conn, identity.path)
    if row is None:
        row = _rebind_fallback(
            conn, identity.path, identity.title, identity.artist, identity.length_ms, catalog
        )
    if row is None:
        now = _now()
        conn.execute(
            """
            INSERT INTO track (path, title, artist, length_ms, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (identity.path, identity.title, identity.artist, identity.length_ms, now, now),
        )
        inserted = conn.execute("SELECT last_insert_rowid()").fetchone()
        return _as_int(inserted[0])
    track_id = _as_int(row["id"])
    _sync_metadata(conn, track_id, identity.title, identity.artist, identity.length_ms)
    if str(row["path"]) != identity.path:
        occupant = _track_by_path(conn, identity.path)
        if occupant is not None and _as_int(occupant["id"]) != track_id:
            raise library.LibraryError("That path already identifies a different track.", 409)
        conn.execute(
            "UPDATE track SET path = ?, updated_at = ? WHERE id = ?",
            (identity.path, _now(), track_id),
        )
    return track_id


def _insert_link(
    conn: sqlite3.Connection,
    from_id: int,
    to_id: int,
    mutual: bool,
    note: str,
    rating: int | None,
) -> int:
    """Insert one link row.

    Args:
        conn: Open sidecar connection.
        from_id: Source identity.
        to_id: Target identity.
        mutual: True for a two-way link.
        note: Stored note.
        rating: Stored rating, or None.

    Returns:
        The new link id.

    Raises:
        LibraryError: If the two ids are the same.
    """
    if from_id == to_id:
        raise library.LibraryError("A track cannot be related to itself.")
    now = _now()
    cursor = conn.execute(
        """
        INSERT INTO link
            (from_track_id, to_track_id, mutual, note, rating, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (from_id, to_id, 1 if mutual else 0, note, rating, now, now),
    )
    return _as_int(cursor.lastrowid)


def _upsert_link(
    conn: sqlite3.Connection,
    from_id: int,
    to_id: int,
    mutual: bool,
    note: str,
    rating: int | None,
) -> int:
    """Insert or update the link between two identities.

    Args:
        conn: Open sidecar connection.
        from_id: Source identity.
        to_id: Target identity.
        mutual: True for a two-way link.
        note: Stored note.
        rating: Stored rating, or None.

    Returns:
        The link id. A two-way save keeps one row and deletes the reverse
        row. Two one-way rows are kept when each direction was saved on
        its own.
    """
    if from_id == to_id:
        raise library.LibraryError("A track cannot be related to itself.")
    now = _now()
    forward = conn.execute(
        "SELECT * FROM link WHERE from_track_id = ? AND to_track_id = ?",
        (from_id, to_id),
    ).fetchone()
    backward = conn.execute(
        "SELECT * FROM link WHERE from_track_id = ? AND to_track_id = ?",
        (to_id, from_id),
    ).fetchone()
    if mutual:
        if forward is not None and backward is not None:
            conn.execute("DELETE FROM link WHERE id = ?", (_as_int(backward["id"]),))
        if forward is not None:
            conn.execute(
                "UPDATE link SET mutual = 1, note = ?, rating = ?, updated_at = ? WHERE id = ?",
                (note, rating, now, _as_int(forward["id"])),
            )
            return _as_int(forward["id"])
        if backward is not None:
            conn.execute(
                "UPDATE link SET mutual = 1, note = ?, rating = ?, updated_at = ? WHERE id = ?",
                (note, rating, now, _as_int(backward["id"])),
            )
            return _as_int(backward["id"])
        return _insert_link(conn, from_id, to_id, True, note, rating)
    if backward is not None and _as_int(backward["mutual"]) == 1:
        conn.execute(
            """
            UPDATE link
            SET from_track_id = ?, to_track_id = ?, mutual = 0, note = ?, rating = ?, updated_at = ?
            WHERE id = ?
            """,
            (from_id, to_id, note, rating, now, _as_int(backward["id"])),
        )
        return _as_int(backward["id"])
    if forward is not None:
        conn.execute(
            "UPDATE link SET mutual = 0, note = ?, rating = ?, updated_at = ? WHERE id = ?",
            (note, rating, now, _as_int(forward["id"])),
        )
        return _as_int(forward["id"])
    return _insert_link(conn, from_id, to_id, False, note, rating)


def _saved_links(
    conn: sqlite3.Connection, identity_id: int, catalog: Sequence[CatalogTrack]
) -> list[dict[str, object]]:
    """List the links visible from one identity.

    Args:
        conn: Open sidecar connection.
        identity_id: Anchor identity.
        catalog: Library tracks used to attach asset ids.

    Returns:
        Saved link dicts. A one-way link is included only when this
        identity is the source. A two-way link is included from either end.
    """
    rows = conn.execute(
        """
        SELECT l.id, l.mutual, l.note, l.rating,
               o.path, o.title, o.artist, o.length_ms
        FROM link l
        JOIN track o ON o.id = CASE
            WHEN l.from_track_id = ? THEN l.to_track_id
            ELSE l.from_track_id
        END
        WHERE l.from_track_id = ? OR (l.mutual = 1 AND l.to_track_id = ?)
        ORDER BY l.id
        """,
        (identity_id, identity_id, identity_id),
    ).fetchall()
    saved: list[dict[str, object]] = []
    for row in rows:
        mutual = _as_int(row["mutual"]) == 1
        rating = row["rating"]
        saved.append(
            {
                "id": _as_int(row["id"]),
                "mutual": mutual,
                "direction": "mutual" if mutual else "outgoing",
                "note": str(row["note"] or ""),
                "rating": rating if isinstance(rating, int) and not isinstance(rating, bool) else None,
                "track": _public_track(row, catalog),
            }
        )
    return saved


def _public_track(row: sqlite3.Row, catalog: Sequence[CatalogTrack]) -> dict[str, object]:
    """Describe one linked track for the page and the HTTP API.

    Args:
        row: Sidecar track columns.
        catalog: Library tracks.

    Returns:
        Path, title, artist, length, and the library id when the path
        is in the space. ``in_library`` is false when it is not.
    """
    path = str(row["path"])
    match = match_catalog(catalog, path)
    if match is not None:
        return {
            "asset_id": match.asset_id,
            "path": match.path,
            "title": match.title or str(row["title"] or ""),
            "artist": match.artist or str(row["artist"] or ""),
            "length_ms": match.length_ms if match.length_ms is not None else row["length_ms"],
            "bpm": match.bpm,
            "key": match.key,
            "in_library": True,
        }
    length = row["length_ms"]
    return {
        "asset_id": None,
        "path": path,
        "title": str(row["title"] or ""),
        "artist": str(row["artist"] or ""),
        "length_ms": length if isinstance(length, int) and not isinstance(length, bool) else None,
        "bpm": None,
        "key": "",
        "in_library": False,
    }


def _anchor_payload(
    anchor: CatalogTrack | None,
    canonical: str,
    title: str,
    artist: str,
    length_ms: int | None,
) -> dict[str, object]:
    """Describe the open track in an overview payload.

    Args:
        anchor: Library match, or None.
        canonical: Canonical path from the request.
        title: Fallback title.
        artist: Fallback artist.
        length_ms: Fallback length.

    Returns:
        The ``track`` object. ``in_library`` is true only for a library match.
    """
    if anchor is not None:
        return {
            "asset_id": anchor.asset_id,
            "path": anchor.path,
            "title": anchor.title,
            "artist": anchor.artist,
            "length_ms": anchor.length_ms,
            "bpm": anchor.bpm,
            "key": anchor.key,
            "in_library": True,
        }
    return {
        "asset_id": None,
        "path": canonical,
        "title": title,
        "artist": artist,
        "length_ms": length_ms,
        "bpm": None,
        "key": "",
        "in_library": False,
    }


def _ensure_crate(space: str, name: str) -> tuple[int, bool, object]:
    """Find or create the normal crate with this visible name.

    Args:
        space: Space name.
        name: Visible crate name.

    Returns:
        The crate id, whether this call created it, and a warning from
        the create, or None.
    """
    existing = _find_crate_id(space, name)
    if existing is not None:
        return existing, False, None
    result = library.crate_action({"action": "create", "space": space, "name": name})
    return _as_int(result["id"]), True, result.get("warning")


def _find_crate_id(space: str, name: str) -> int | None:
    """Return the oldest normal crate with this visible name.

    Args:
        space: Space name.
        name: Visible name, compared without case.

    Returns:
        The container id, or None.
    """
    folded = name.casefold()
    with closing(library.read_conn()) as conn:
        rows = conn.execute(
            """
            SELECT c.id, c.name
            FROM container c
            JOIN space s ON s.id = c.space_id
            WHERE s.name = ? AND c.type = 1
            ORDER BY c.id
            """,
            (space,),
        ).fetchall()
    for row in rows:
        stored = row["name"]
        if isinstance(stored, str) and library.display_name(stored).casefold() == folded:
            return _as_int(row["id"])
    return None


def _crate_asset_ids(crate_id: int) -> set[int]:
    """Return the asset ids in one crate.

    Args:
        crate_id: Container id.

    Returns:
        Asset ids currently in the crate.
    """
    with closing(library.read_conn()) as conn:
        rows = conn.execute(
            """
            SELECT ca.asset_id
            FROM container_asset ca
            JOIN location_container lc ON lc.id = ca.location_container_id
            WHERE lc.container_id = ?
            """,
            (crate_id,),
        ).fetchall()
    return {_as_int(row["asset_id"]) for row in rows}
