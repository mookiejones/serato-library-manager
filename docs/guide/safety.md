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

## Automatic backups

The first time you save anything after you open the app, the app copies the library into a backup folder. Later saves in that same session do not make another copy.

1. Quit Serato DJ Pro.
2. Open Serato Library.
3. Make one small edit you can stand to keep, if you want a fresh copy before a larger change.
4. Close Serato Library.
5. Open it again before the larger change.

The copy is a folder next to `master.sqlite`:

`Library/Backups/serato-web-YYYYMMDD-HHMMSS`

`YYYYMMDD` is the date. `HHMMSS` is the time on this computer. When a folder for that same second already exists, the name ends with `-02`, then `-03`, up through `-99`. A later number is a later copy from that second. Sorting the folder names keeps them in the order they were made. The folder contains `master.sqlite`. It also contains `root.sqlite` when that file was beside the library. A finished folder also contains a file named `COMPLETE`. That file is JSON. It lists a SHA-256 hash for every other file in the folder.

Do not restore a folder whose name ends with `-failed` or `-failed-02` (any capitalization). Do not restore a hidden folder whose name ends with `.partial`. Do not restore a folder that contains a file named `INCOMPLETE`. Those copies did not finish. Leave them where they are.

An older folder that has `master.sqlite` but no `COMPLETE` file is **legacy, unverified**. The app does not offer it as a finished backup. Nothing in this app restores that folder yet. When a restore is added, it will check `master.sqlite` first, on a copy, and will not use the folder unless that check is exactly ok.

A file change in the Files view copies the database first as well. During the change, the app also writes `Library/Backups/file-ops-journal.json`. That file is removed when the change finishes. Leave it alone.

The backup is the database, not your audio. A backup does not contain your music files.

## Restore a backup

Restoring replaces the live library with an older copy. Tracks you added after that copy are not in it.

1. Quit Serato DJ Pro.
2. Quit Serato Library. Close the window.
3. Open the [library folder](install.md#where-serato-keeps-the-library).
4. Open `Backups`.
5. Open a `serato-web-` folder that contains `COMPLETE`. A suffix `-02` through `-99` is a later copy from that same second. Skip a name that ends with `-failed` or `-failed-02`, a hidden name that ends with `.partial`, and a folder that contains `INCOMPLETE`. An older folder with no `COMPLETE` file is legacy, unverified. Do not use it unless you mean to, and stop if its check does not come back ok.
6. Copy the current `master.sqlite` to a different folder, so you still have it.
7. If `root.sqlite` is in the library folder, copy that file aside too.
8. Copy `master.sqlite` from the backup folder into the library folder. Replace the current file.
9. If the backup folder contains `root.sqlite`, copy that file into the library folder the same way.
10. Open Serato DJ Pro and check the crates.

Use `master.sqlite` and `root.sqlite` from the same backup folder. The two files are a pair.

## Before you merge or delete files

Read the review in the dialog. **Cancel** writes nothing. The Trash options are off until you turn them on. Files that go to the Trash can be put back from the Trash on a Mac, or from the Recycle Bin on Windows. They are not deleted forever by this app.
