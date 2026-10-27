# Related tracks

A DJ can save which tracks go well together. The links live in a sidecar SQLite file next to the app settings. They are not stored in Serato's `master.sqlite`, so the file can be updated while Serato DJ Pro is open.

Suggestions are computed when the page or `GET /api/related` asks for them. They are not written into the sidecar file.

`serato-listener` can open the sidecar file read-only. It must not write the file.

## File location

The file name is `related.sqlite`. It sits in the same directory as `settings.json`.

| System | Path |
|--------|------|
| macOS | `~/Library/Application Support/Serato Library/related.sqlite` |
| Windows | `%APPDATA%\Serato Library\related.sqlite` |
| Linux | `$XDG_CONFIG_HOME/serato-library/related.sqlite`, or `~/.config/serato-library/related.sqlite` |

`SERATO_LIBRARY_CONFIG_DIR` overrides the directory when the value is an absolute path. A relative value is ignored.

## Opening the file

Open the database read-only. Do not create tables, do not run `INSERT`, `UPDATE`, or `DELETE`, and do not change `user_version`.

```text
file:<absolute path of related.sqlite>?mode=ro
```

Set `PRAGMA query_only=ON` as well. Foreign keys are declared. A reader does not need to turn them on.

The schema version is `PRAGMA user_version`. Version 1 is the schema in this document. A version other than 1 was written by a different app build. Do not guess at columns.

## Tables

### `track`

One row is one file the DJ has linked.

| Column | Type | Meaning |
|--------|------|---------|
| `id` | INTEGER | Primary key. |
| `path` | TEXT | Canonical absolute path. Unique. |
| `title` | TEXT | Title. An empty string when unknown. |
| `artist` | TEXT | Artist. An empty string when unknown. |
| `length_ms` | INTEGER | Length in milliseconds, or NULL. |
| `created_at` | TEXT | UTC time `YYYY-MM-DDTHH:MM:SSZ`. |
| `updated_at` | TEXT | UTC time `YYYY-MM-DDTHH:MM:SSZ`. |

`length_ms` is NULL or a number greater than or equal to 0.

Index `track_path` is unique on `path`. Index `track_fallback` is on `(title, artist, length_ms)`.

### `link`

One row is one saved relationship.

| Column | Type | Meaning |
|--------|------|---------|
| `id` | INTEGER | Primary key. |
| `from_track_id` | INTEGER | Source `track.id`. |
| `to_track_id` | INTEGER | Target `track.id`. |
| `mutual` | INTEGER | `0` is one-way. `1` is two-way. |
| `note` | TEXT | Optional note. An empty string when the DJ left it blank. At most 500 characters. |
| `rating` | INTEGER | NULL, or a whole number from 1 to 5. |
| `created_at` | TEXT | UTC time `YYYY-MM-DDTHH:MM:SSZ`. |
| `updated_at` | TEXT | UTC time `YYYY-MM-DDTHH:MM:SSZ`. |

`from_track_id` and `to_track_id` are different. The pair is unique. Both columns reference `track.id`.

`mutual` `0` is visible only from `from_track_id`. The note and the rating belong to that direction. A second row may point the other way, with its own note and rating.

`mutual` `1` is visible from both tracks. The app keeps a single row for that pair and deletes the opposite row when a link is saved as two-way.

Notes such as `blend out of` and `acapella over` are ordinary text. The file does not store Serato asset ids, crate ids, or suggestion scores.

## Resolving a track

1. Canonicalize the path without reading the file. Expand a leading `~`. Collapse `.` and `..`. Keep an absolute path absolute. Join a relative path to the home directory. Do not follow symlinks.
2. Select `track` where `path` equals that canonical path. When the path is a Serato `portable_id` for a track in the open library, also try the absolute path that library already resolved: the file under the home directory when it exists, otherwise the file at the filesystem root when that exists, otherwise the home-directory candidate. The app stores that resolved path.
3. If that misses, and the title and the artist are both non-blank, and `length_ms` is not NULL, select rows whose title and artist match case-insensitively and whose `length_ms / 1000` (integer division) equals the requested length in whole seconds.
4. Use that fallback only when exactly one row matches. Zero rows and two or more rows are not a match. Do not pick one of an ambiguous pair.
5. Do not treat that row as the same file when its stored path is still a different track in the open library. That is a second copy, not a move.

The app writes the new path onto a unique fallback row when it next opens the track. A read-only client applies the same steps and does not write.

Duplicate copies that share a title, an artist, and a whole-second length will not move by fallback. The file manager must call the path update after it moves the file.

## Path update

After a cue-safe move, call either function. Both write the sidecar file and do not open `master.sqlite`.

```python
import related
related.update_path(old_path, new_path)
```

```python
import library
library.update_related_path(old_path, new_path)
```

`related.update_path` is the implementation. `library.update_related_path` calls it.

The return value is true when a row now uses the new path, including when it already did. The return value is false when the old path is not stored. The call does not create a row. If the new path already belongs to a different row, the call fails and changes nothing.

## Reading links for one track

Resolve the track to a `track.id` with the steps above. Then:

```sql
SELECT l.id, l.mutual, l.note, l.rating,
       t.path, t.title, t.artist, t.length_ms
FROM link AS l
JOIN track AS t ON t.id = CASE
    WHEN l.from_track_id = :id THEN l.to_track_id
    ELSE l.from_track_id
END
WHERE l.from_track_id = :id
   OR (l.mutual = 1 AND l.to_track_id = :id)
ORDER BY l.id;
```

`:id` is the anchor `track.id`. A one-way link is included only when the anchor is `from_track_id`. A two-way link is included from either end.

## HTTP

`GET /api/related?path=` returns JSON. Optional query fields are `space`, `title`, `artist`, and `length_ms`. `space` defaults to `Serato Library`.

The body has:

| Field | Meaning |
|-------|---------|
| `schema_version` | Same number as `PRAGMA user_version`. |
| `path` | Canonical path. |
| `track` | Anchor. `in_library` is true when the path is in the space. |
| `crate_name` | Name a Serato crate refresh would use. |
| `saved` | Saved links. Each has `id`, `mutual`, `direction` (`outgoing` or `mutual`), `note`, `rating`, and `track`. |
| `suggested` | Ranked candidates. Not stored in the sidecar file. |

A track object has `asset_id`, `path`, `title`, `artist`, `length_ms`, `bpm`, `key`, and `in_library`. `asset_id` is null when the file is not in the space. `bpm` and `key` come from the library and are null or empty for a file that is only in the sidecar.

`POST /api/related` takes `action`:

| Action | Body | Writes |
|--------|------|--------|
| `add` | `asset` and `target` asset ids, or `path` and `target_path`, plus `mutual` (boolean), optional `note` and `rating` | Sidecar only |
| `remove` | `id` of a saved link | Sidecar only |
| `crate` | `asset` or `path`, optional `space` | Serato crate. Serato must be quit. The first write in the process copies the library into `Library/Backups`. |

`add` and `remove` work while Serato is open. `crate` returns 409 when Serato holds the library lock.

## Serato crate

The crate is a normal crate named `Related - ` plus the track title. A blank title uses the file name, then `Untitled`. The visible name is at most 400 characters. Refreshing the crate replaces its membership with the saved related tracks that are in the same space. The anchor track is not added. A linked file that is not in the library is skipped.

Two tracks with the same title share one crate name.

## Suggestions

A candidate is another track in the same space with a file path. The open track and tracks that are already saved are left out. Crates whose visible name starts with `Related - ` are not counted as shared crates. Smart crates are not counted.

A candidate needs at least one of these:

- The same Camelot code, the relative major or minor (same number, other letter), or one step around the wheel on the same letter. The wheel wraps from 12 to 1. Traditional key names are mapped through the same table Serato uses.
- Tempo within 6 percent of the anchor, or within 6 percent after taking the candidate at half time or double time. Half time means the candidate is about half the anchor. Double time means it is about twice the anchor.
- One or more shared normal crates. The third shared crate is the last one that adds to the score.

The same key ranks above a relative key, which ranks above an adjacent key. A closer tempo ranks above a tempo at the edge of the 6 percent window. The JSON field `reasons` uses the phrases `same key`, `relative key`, `adjacent key`, `BPM match`, `BPM within N%`, `half-time BPM`, `double-time BPM`, `1 shared crate`, and `N shared crates`. `score` orders the list. At most 12 suggestions are returned.

## What is not sent

Saving a link, removing a link, or writing the crate can record `related_link_saved`, `related_link_removed`, or `related_crate_written` after the person opts in. `related_link_saved` may include `link_direction` as `one_way` or `two_way`. Titles, artists, notes, ratings, crate names, and file paths are not properties of those events. The sidecar file stays on this machine.
