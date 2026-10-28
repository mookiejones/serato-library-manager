# Troubleshooting

## The edit buttons are off

Serato DJ Pro still has the library, or the database is locked.

1. Read the status line under **Library**.
2. Quit Serato DJ Pro. Quit it fully. A window in the Dock or on the taskbar still counts.
3. Return to Serato Library.
4. Click **Reload**.

The line you want is **Serato is quit. Edits save to the library.**

A save that hits a lock shows the error in the bar above the list. The merge dialog says **Quit Serato before merging. The preview shows the plan.** The file dialog shows the same status line and leaves **Confirm** off.

## The app closes as soon as it opens

`master.sqlite` is not where the app looks. The message is **Serato library not found at** and then a path.

1. Install Serato DJ Pro if it is not installed.
2. Open Serato DJ Pro once, then quit it.
3. Open the folder in [Install](install.md#where-serato-keeps-the-library).
4. Confirm `master.sqlite` is there.
5. Open Serato Library again.

## macOS says the app is damaged or cannot be opened

The download is unsigned. Gatekeeper shows a warning.

1. Open the folder that contains `Serato Library.app`.
2. Right-click the app.
3. Choose Open.
4. Choose Open in the next dialog.

Do not move only the app out of a half-unpacked download. Unpack the zip first.

## Windows SmartScreen stops the app

1. Open the extracted `Serato Library` folder.
2. Double-click `Serato Library.exe`.
3. Choose More info.
4. Choose Run anyway.

Run the exe from the extracted folder. Do not run it from inside the zip.

## The window never appears, and no error is obvious

Another copy may already be listening.

1. Quit every Serato Library window.
2. Open the app again.

If you started it from a terminal, the message is **http://127.0.0.1:8765 is already in use.** Quit the other copy.

## Serato put my edit back

The main library was saved, and a drive database was not. The bar includes **Saved in the main library.** and a sentence about the other drive.

1. Connect the drive that holds the tracks.
2. Quit Serato Library.
3. Open Serato DJ Pro so it can read both databases.
4. Check the crate again.

Use one backup folder when you [restore](safety.md#restore-a-backup). `master.sqlite` and `root.sqlite` from different times can disagree.

## Merge warns about cue points

The file you chose to keep has no Serato cues, and another copy does. The merge does not copy cues from one audio file onto another.

1. Click **Cancel**.
2. Select the copy that has the cues.
3. Read the plan again.
4. Merge only when that copy is the one you are keeping.

## Replace says the file type cannot take a Serato tag

The new file was not rewritten. Cue points stay on the old file, and the old file stays on disk. The library track now points at the new file.

1. Open the old file from the path in the review if you still need those cues.
2. Leave the old file in place until you have checked the new one in Serato.

A plain MP3 is the case where the dialog can say the cue points will be copied.

## An interrupted file change does not match the library

A Files action stopped halfway, and the journal does not match the database. The message is **An interrupted file change does not match the library. Restore the copy in Library/Backups.**

1. Quit Serato DJ Pro.
2. Quit Serato Library.
3. Follow [Restore a backup](safety.md#restore-a-backup). Pick the newest `serato-web-` folder from before the interrupted change.
4. Open Serato Library again.

Do not delete `file-ops-journal.json` by hand before the restore.

## Import skipped some lines

The bar counts **lines did not match a library track.** Those lines were not paths the library already knows.

1. Add the missing audio in Serato DJ Pro.
2. Quit Serato.
3. Import the playlist again.

**The playlist is empty.** means the file had no tracks to read.

## I cannot make a smart crate

**New** creates a normal crate. Make the smart crate in Serato DJ Pro. Then select it here and use **Save rules**. The steps are in [Crates](crates.md#smart-crates).

**Smart crate rules need to be JSON.** means the text in the box is not valid JSON. Nothing was saved. Fix the text, or reload the crate and start from the rules Serato stored.

## Related tracks do not show while I play

Saving links in this app does not put a live view on screen. The live view is [serato-listener](https://github.com/mookiejones/serato-listener), on `http://127.0.0.1:8787/`, while Serato is open. On a Mac, Serato can connect to it. On Windows, pairing does not start. Details are in [Related tracks](related.md#while-a-track-is-playing).

A track with no file path cannot be linked. The section says **This track has no file path, so it cannot be linked.**

## Sharing is on, and I am not sure anything is sent

Read the line under the checkbox in **Settings**. **This copy has no telemetry keys, so nothing is sent either way.** means the choice is saved and this copy has no key. Sharing still does not send titles or paths when a key is present. The list is in [Settings and privacy](settings.md).

## Where is the log?

**Settings**, then **Open logs folder** or **Copy logs**. The folders are in [Settings and privacy](settings.md#logs). The log can include the path of `master.sqlite`. It is not uploaded.

## Does this upload my music?

No. The window stays on this computer. Audio files stay on disk unless you move them to the Trash from [Duplicates](duplicates.md) or [Files](files.md). Those files go to the Trash or the Recycle Bin, not to a server.
