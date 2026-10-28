# Safety and backups

Quit Serato DJ Pro before you change the library. Serato and this app must not write the same database at the same time.

## How you know edits are on

Read the status line under **Library**.

| Status line | What it means |
| --- | --- |
| **Serato is quit. Edits save to the library.** | Saves, crate edits, merges, and file changes are allowed. |
| A sentence that names Serato and says **Edits stay off until it quits.** | Serato still has the library. Buttons that write stay off. |
| **Serato DJ Pro has the library open. Edits stay off until it quits.** | The database is locked. Quit Serato, then choose Reload. |

The same sentence appears on the open track. A failed save shows the error in the bar above the track list.

Saving a related-track link is the exception. That link is stored beside the app settings, not in Serato's library, so it can be saved while Serato is open. Writing those links into a Serato crate still waits until Serato has quit. [Related tracks](related.md) explains the difference.

## What a save changes

A track edit writes Serato's library database. It does not rewrite the audio file. Cue points, loops, flips, and the beatgrid live in the audio file. This app reads them. A normal save does not write them back.

File changes in the [Files](files.md) view are different. Rename and move carry the audio file, cues included, to a new name or folder, and then update the path in the library. Replace can copy cue points onto the new file when that is safe. Delete moves the audio file to the Trash. Read that page before you use it.

## Snapshots

The first time you finish setup, **Take a safety snapshot** saves a copy of the library data before you change anything. If Serato DJ is open, that step says **Close Serato DJ to continue** and checks again on its own.

**Snapshots** in the sidebar keeps hash-checked copies of the library database, the crates on each drive (including a drive's `_Serato_` folder and `database V2`), and the Serato cue, beatgrid, and autotag data stored inside MP3, FLAC, M4A, and AIFF files. The music itself is not copied. Snapshots are kept with no time limit. The page does not delete old ones.

Quit Serato DJ Pro before you restore. If Serato DJ is still running, restore stops and the page tells you to quit it first. That check runs again before the database, the crates, and the audio are replaced. **Review restore** shows what would change: crates, tracks, and the cue and beatgrid differences for each file. Nothing is written until you confirm. Confirm saves a new snapshot first, so the restore can be undone from the list. If the app stops in the middle of a restore, the next time it opens it puts that saved snapshot back.

A drive that is not plugged in is shown as unavailable. Its crates and tracks stay in the snapshot. They are not treated as deleted, and a restore does not remove them.

If something else changes the Serato folder while this app is open, including Lexicon, the app saves a snapshot after that change and offers **Review undo**. That restore puts back the previous snapshot. It cannot put back a copy from before the other program wrote, because that moment was not captured. The log names Lexicon when a Lexicon process is running, or when Lexicon's own folder was updated at the same time. The app does not open files inside `_Serato_/Lexicon/` or `_Serato_/Export Backups/`, and it does not include them in a snapshot or a restore.

Each snapshot records the Serato version and build when those can be read from the app. On a Mac that is the app bundle. On Windows it is the Serato DJ program under Program Files, or the registry. If Serato's version or build changes, one new snapshot is saved of the library as it is then. If the version cannot be read, or it is not a plain number such as `4.1.0`, the snapshot says unknown and is still saved, and writes and restores stay off until a version can be read. An unreadable preferences file is treated the same way.

## Serato 5

On Serato 5, writes and restores stay off. The status line says why.

Protect Library is read from the Mac preferences key `library_protect`. On means it is set. Off means it is cleared. If the preference cannot be read, it is treated as unknown. All three block writes and restores. Separately, Lucid and Flexible beatgrid storage does not have a confirmed file layout, so this app does not write a Serato 5 library until that is known. Snapshots can still be taken and read. Serato 5.0 still keeps crates in `database V2` inside `_Serato_`, and those files are included in the snapshot. Protect Library does not lock that file; the block is the version and the preference, not a file lock.

## Automatic backups

The first time you save anything after you open the app, the app also copies the library database into a backup folder. Later saves in that same session do not make another of these copies. Each save does add a snapshot, described above.

1. Quit Serato DJ Pro.
2. Open Serato Library.
3. Make one small edit you can stand to keep, if you want a fresh copy before a larger change.
4. Close Serato Library.
5. Open it again before the larger change.

The copy is a folder next to `master.sqlite`:

`Library/Backups/serato-web-YYYYMMDD-HHMMSS`

`YYYYMMDD` is the date. `HHMMSS` is the time on this computer. When a folder for that same second already exists, the name ends with `-02`, then `-03`, up through `-99`. A later number is a later copy from that second. Sorting the folder names keeps them in the order they were made. The folder contains `master.sqlite`. It also contains `root.sqlite` when that file was beside the library. A finished folder also contains a file named `COMPLETE`. That file is JSON. It lists a SHA-256 hash for every other file in the folder.

Do not restore a folder whose name ends with `-failed` or `-failed-` and digits, such as `-failed-02` or `-failed-100` (any capitalization). Do not restore a hidden folder whose name ends with `.partial`. Do not restore a folder that contains a file named `INCOMPLETE`. Those copies did not finish. Leave them where they are.

An older folder that has `master.sqlite` but no `COMPLETE` file is **legacy, unverified**. The snapshot list does not offer it. A restore pointed at that folder checks `master.sqlite` on a copy first and stops unless that check is exactly ok.

A file change in the Files view copies the database first as well. During the change, the app also writes `Library/Backups/file-ops-journal.json`. That file is removed when the change finishes. Leave it alone.

The backup is the database, not your audio. A backup does not contain your music files.

## Restore an older database copy by hand

The snapshot list is the restore to use. The steps below are only for a `serato-web-` folder made by the first save in a session. Restoring that folder replaces the live library database with an older copy. Tracks you added after that copy are not in it. Cue points inside audio files are not in that folder.

1. Quit Serato DJ Pro.
2. Quit Serato Library. Close the window.
3. Open the [library folder](install.md#where-serato-keeps-the-library).
4. Open `Backups`.
5. Open a `serato-web-` folder that contains `COMPLETE`. A suffix `-02` through `-99` is a later copy from that same second. Skip a name that ends with `-failed` or `-failed-` and digits (any capitalization), a hidden name that ends with `.partial`, and a folder that contains `INCOMPLETE`. An older folder with no `COMPLETE` file is legacy, unverified. Do not use it unless you mean to, and stop if its check does not come back ok.
6. Copy the current `master.sqlite` to a different folder, so you still have it.
7. If `root.sqlite` is in the library folder, copy that file aside too.
8. Copy `master.sqlite` from the backup folder into the library folder. Replace the current file.
9. If the backup folder contains `root.sqlite`, copy that file into the library folder the same way.
10. Open Serato DJ Pro and check the crates.

Use `master.sqlite` and `root.sqlite` from the same backup folder. The two files are a pair.

## Before you merge or delete files

Read the review in the dialog. **Cancel** writes nothing. The Trash options are off until you turn them on. Files that go to the Trash can be put back from the Trash on a Mac, or from the Recycle Bin on Windows. They are not deleted forever by this app.
