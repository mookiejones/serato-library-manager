# Is my library safe?

!!! warning "PREVIEW"

    Restore, undo, snapshots, the outside-change watcher, and the gig check on this page are PREVIEW until [#35](https://github.com/mookiejones/serato-library-manager/issues/35) and [#41](https://github.com/mookiejones/serato-library-manager/issues/41) merge. They are not in the app. The rules below describe how Library Manager is designed to work. This page will only say those features work once that code is merged. The Rekordbox export in the first rule is already shipped. See [Coming from Rekordbox](coming-from-rekordbox.md).

## The rules we follow
- **Read first.** Checks, reports and the Rekordbox export only read your Serato files. The export writes a separate XML file and never writes back (see [Coming from Rekordbox](coming-from-rekordbox.md)).
- **No write while unsure.** If we can't confirm Protect Library and Lucid Beatgrid status, we won't write at all.
- **Snapshot first.** Before any change, we save a snapshot and check it against what's on disk.
- **Every restore can be undone.** A restore takes its own snapshot first.
- **A missing drive is never a deletion.** Its tracks and crates are marked unavailable, never removed.
- **Empty crates warned.** Serato deletes empty crates when it closes, so the gig check flags them first.
- **Outside changes get caught.** If another app changes your Serato folder, we take a snapshot, show what changed and offer an undo. We can't catch the moment *before* an outside app writes, so undo returns you to our last snapshot.
- **Restore is free.**

## What a restore covers

| Restores | Doesn't restore |
|---|---|
| Crates and subcrates, on every drive | The audio itself (we never touch the sound) |
| Serato's library database | Tracks on drives that aren't plugged in (marked unavailable, never deleted) |
| Cues, beatgrids, loops and tags stored in each file, checked against the snapshot | |

## Common myths
| Myth | Reality |
|---|---|
| "Protect Library is a backup." | It only blocks removing tracks. It doesn't snapshot or restore. |
| "Serato keeps a history of backups." | Serato keeps one backup and overwrites it each time. |
| "Serato can restore for me." | Serato has no in-app restore; it's a manual file swap. |
| "Backing up `~/Music/_Serato_` is enough." | Each external drive has its own `_Serato_`, and Serato 4+ also uses a database elsewhere. |
| "Missing crates means deleted crates." | Usually the drive isn't mounted or access is blocked. See the [Panic page](panic.md). |

![Backups rewind. Example data. A seven-day chart and a list of changes, with a Snapshot and rewind button. The picture is labeled Mock, example data.](media/layout-v4-rewind.png)

*Example data. PREVIEW of restore and undo. This screen is not in the app.*

![Outside change. Example data. A notice that the Serato folder changed, with See changes, Undo, and Keep it. The picture is labeled Sample data.](media/layout-v3-outside-change.png)

*Example data. PREVIEW of the outside-change watcher. This screen is not in the app.*
