"""Snapshot data the gig check compares. This module does not read or write files.

``snapshots.py`` stores the snapshots. ``gig_check.StoreSnapshots`` turns
one of them into a ``LoadedSnapshot``, so the snapshot and the library as
it is now are built from the same rows and compared here. ``NoSnapshots``
is the reader used when nothing has been saved. Tests supply their own
reader. Nothing here opens a database.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


def track_key(asset_id: int, path: str) -> str:
    """Build the identity a snapshot uses for one library track.

    Args:
        asset_id: Asset id in master.sqlite.
        path: Stored path, or the path the file was resolved to.

    Returns:
        A key that stays unique when two assets share a path. The path
        may contain any character except a newline, which this key uses
        as the separator.
    """
    return f"{asset_id}\n{path}"


@dataclass(frozen=True, slots=True)
class CueMark:
    """One cue or saved loop stored in a snapshot.

    Attributes:
        kind: ``cue`` or ``loop``.
        index: Serato pad index.
        start_ms: Start time in milliseconds.
        end_ms: Loop end in milliseconds. None for a cue.
        name: Cue name. Empty when Serato stored none.
    """

    kind: str
    index: int
    start_ms: int
    end_ms: int | None
    name: str


@dataclass(frozen=True, slots=True)
class GridMark:
    """One beatgrid marker stored in a snapshot.

    Attributes:
        position: Position in seconds.
        bpm: BPM on the last marker. None on earlier markers.
        beats: Beat count on an earlier marker. None on the last marker.
    """

    position: float
    bpm: float | None
    beats: int | None


@dataclass(frozen=True, slots=True)
class TrackTags:
    """Library text a snapshot keeps for one track.

    Attributes:
        title: Track title.
        artist: Artist.
        album: Album.
        genre: Genre.
        key: Key text.
        bpm: BPM as text, so 120 and 120.0 compare equal.
        comments: Comments.
    """

    title: str
    artist: str
    album: str
    genre: str
    key: str
    bpm: str
    comments: str


@dataclass(frozen=True, slots=True)
class SnapshotTrack:
    """One track inside a snapshot.

    Attributes:
        key: Identity from ``track_key``.
        path: Path shown in the change report.
        crates: Crate labels that contain the track, in display order.
        cues: Cues and loops.
        grid: Beatgrid markers.
        tags: Library text.
        cues_known: False when this side could not read cues. The diff
            then skips cues instead of reporting every cue as edited.
        grid_known: False when this side could not read the beatgrid.
    """

    key: str
    path: str
    crates: tuple[str, ...]
    cues: tuple[CueMark, ...]
    grid: tuple[GridMark, ...]
    tags: TrackTags
    cues_known: bool = True
    grid_known: bool = True


@dataclass(frozen=True, slots=True)
class SnapshotCrate:
    """One crate inside a snapshot.

    Attributes:
        name: Display label. Ancestor names are joined with `` / `` so
            two crates with the same visible name stay distinct.
        track_keys: Track keys in playlist order.
    """

    name: str
    track_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SnapshotInfo:
    """A snapshot the reader can load, without its tracks.

    Attributes:
        snapshot_id: Id passed to ``load``.
        taken_at: When the snapshot was taken. Timezone-aware.
        label: Short text for the report, such as the gig date.
    """

    snapshot_id: str
    taken_at: datetime
    label: str


@dataclass(frozen=True, slots=True)
class LoadedSnapshot:
    """Crates, cues, grids, and tags from one snapshot.

    Attributes:
        info: Id, time, and label.
        crates: Crates in that snapshot.
        tracks: Tracks in that snapshot.
    """

    info: SnapshotInfo
    crates: tuple[SnapshotCrate, ...]
    tracks: tuple[SnapshotTrack, ...]


class GigSnapshotReader(Protocol):
    """Reads saved snapshots for the gig check. Implementations must not write.

    ``list_snapshots`` returns the newest last or in any order. The gig
    check picks the latest ``taken_at``. ``load`` returns that snapshot's
    crates, cues, grids, and tags.
    """

    def list_snapshots(self) -> Sequence[SnapshotInfo]:
        """List snapshots that can be loaded.

        Returns:
            One info row per snapshot. Empty when none have been saved.
        """

    def load(self, snapshot_id: str) -> LoadedSnapshot:
        """Load one snapshot.

        Args:
            snapshot_id: Id from ``list_snapshots``.

        Returns:
            The crates, cues, grids, and tags in that snapshot.

        Raises:
            KeyError: If that id is not in the list, or the snapshot
                could not be read.
        """


class NoSnapshots:
    """Reader used when no snapshot has been saved."""

    def list_snapshots(self) -> Sequence[SnapshotInfo]:
        """Return no snapshots.

        Returns:
            An empty tuple.
        """
        return ()

    def load(self, snapshot_id: str) -> LoadedSnapshot:
        """Refuse a load, because there is nothing to load.

        Args:
            snapshot_id: Id that was requested.

        Raises:
            KeyError: Always. ``list_snapshots`` is empty.
        """
        raise KeyError(snapshot_id)


@dataclass(frozen=True, slots=True)
class ChangeReport:
    """What differs between an older snapshot and a newer one.

    Attributes:
        crates_added: Crate labels only in the newer snapshot.
        crates_removed: Crate labels only in the older snapshot.
        crates_edited: Crate labels whose track list changed.
        tracks_added: Paths only in the newer snapshot.
        tracks_removed: Paths only in the older snapshot.
        cues_edited: Paths whose cues or loops changed.
        grids_edited: Paths whose beatgrid changed.
        tags_edited: Paths whose library text changed.
    """

    crates_added: tuple[str, ...]
    crates_removed: tuple[str, ...]
    crates_edited: tuple[str, ...]
    tracks_added: tuple[str, ...]
    tracks_removed: tuple[str, ...]
    cues_edited: tuple[str, ...]
    grids_edited: tuple[str, ...]
    tags_edited: tuple[str, ...]

    def empty(self) -> bool:
        """Return whether nothing changed.

        Returns:
            True when every list is empty.
        """
        return not any(
            (
                self.crates_added,
                self.crates_removed,
                self.crates_edited,
                self.tracks_added,
                self.tracks_removed,
                self.cues_edited,
                self.grids_edited,
                self.tags_edited,
            )
        )


def _ordered_cues(cues: tuple[CueMark, ...]) -> tuple[CueMark, ...]:
    """Sort cues so pad order, not read order, decides equality.

    Args:
        cues: Cues and loops as stored.

    Returns:
        The same marks ordered by kind, index, times, and name.
    """
    return tuple(sorted(cues, key=lambda mark: (mark.kind, mark.index, mark.start_ms, mark.end_ms or -1, mark.name)))


def _ordered_grid(grid: tuple[GridMark, ...]) -> tuple[GridMark, ...]:
    """Sort beatgrid markers by position.

    Args:
        grid: Markers as stored.

    Returns:
        Markers ordered by position, then BPM, then beat count.
    """
    return tuple(sorted(grid, key=lambda mark: (mark.position, mark.bpm or -1.0, mark.beats or -1)))


def diff_snapshots(before: LoadedSnapshot, after: LoadedSnapshot) -> ChangeReport:
    """Compare two snapshots.

    Args:
        before: The older snapshot, usually the last gig.
        after: The newer snapshot, usually the library right now.

    Returns:
        Added and removed crates and tracks, and paths whose cues,
        beatgrid, or tags differ. Cue and grid comparisons are skipped
        for a track whose cues or grid were not read on either side.
    """
    older = {track.key: track for track in before.tracks}
    newer = {track.key: track for track in after.tracks}
    old_crates = {crate.name: crate.track_keys for crate in before.crates}
    new_crates = {crate.name: crate.track_keys for crate in after.crates}
    cues: list[str] = []
    grids: list[str] = []
    tags: list[str] = []
    for key, track in newer.items():
        previous = older.get(key)
        if previous is None:
            continue
        if track.cues_known and previous.cues_known and _ordered_cues(track.cues) != _ordered_cues(previous.cues):
            cues.append(track.path)
        if track.grid_known and previous.grid_known and _ordered_grid(track.grid) != _ordered_grid(previous.grid):
            grids.append(track.path)
        if track.tags != previous.tags:
            tags.append(track.path)
    added_tracks = [newer[key].path for key in newer.keys() - older.keys()]
    removed_tracks = [older[key].path for key in older.keys() - newer.keys()]
    edited_crates = [
        name
        for name in new_crates.keys() & old_crates.keys()
        if tuple(new_crates[name]) != tuple(old_crates[name])
    ]
    return ChangeReport(
        crates_added=tuple(sorted(new_crates.keys() - old_crates.keys())),
        crates_removed=tuple(sorted(old_crates.keys() - new_crates.keys())),
        crates_edited=tuple(sorted(edited_crates)),
        tracks_added=tuple(sorted(added_tracks)),
        tracks_removed=tuple(sorted(removed_tracks)),
        cues_edited=tuple(sorted(cues)),
        grids_edited=tuple(sorted(grids)),
        tags_edited=tuple(sorted(tags)),
    )
