# Panic page: something's wrong before a gig

Snapshots, restore, and undo are in the app. The sidebar views include **Crates** and **Snapshots**. **Prepare** is a space in the space menu. Open **Snapshots**, then **Review restore**. Quit Serato first. [Safety and backups](guide/safety.md#snapshots) has the steps.

!!! warning "PREVIEW"

    **Gig check** is **PREVIEW** until [#41](https://github.com/mookiejones/serato-library-manager/issues/41) merges. It is not in the app. The panic card below is an example layout, not the current window.

> **Do this first.** Don't delete, re-import or "rebuild" anything yet. Most crates that look gone are only hidden.
> Close Serato, then copy the whole `_Serato_` folder (on every drive) somewhere safe. That way every step below can be undone.

## Which one do you have?

![Which one do you have? Four rows: red or missing tracks, crates gone or empty, one drive's crates gone, and a problem that started after a Serato update.](media/docs-panic-which.png)

| What you see | Most likely cause | Go to |
|---|---|---|
| Tracks are **red** or "file not found" | The file moved or was renamed. Your crates are fine. | [A](#a-red-or-missing-tracks) |
| Crates **gone** or **empty** | A drive isn't mounted, macOS blocked access, or an outside app or update rewrote them | [B](#b-crates-gone-or-empty) |
| Only **one drive's** crates are gone | That drive isn't mounted, or Serato can't read it | [C](#c-drive-wont-mount) |
| Started right after a **Serato update** | The library moved to a new format | [D](#d-after-a-serato-update) |

![Gig-night panic card. Example layout. Three columns for missing tracks, a vanished crate, and a drive that will not mount. The card shows Gig check and a Rewind control.](media/docs-panic-card.png)

*Example layout, not the current window. **Gig check** on the card is **PREVIEW** until [#41](https://github.com/mookiejones/serato-library-manager/issues/41) merges. It is not in the app. Restore is **Snapshots**, then **Review restore**.*

## A. Red or missing tracks
1. Plug in every drive your music lives on.
2. In Serato, drag the folder that holds the music onto **Relocate Lost Files** (in the Files panel).
3. Don't restore a backup for a file that only moved. Restore puts crates back and can rewrite Serato tags in the audio file. It does not point a track at a new path. **Files** can move, rename, and trash audio files. [Files](guide/files.md) is that view.

## B. Crates gone or empty
1. Check that every drive is plugged in and shows up in Finder or Explorer.
2. On a Mac, for an external drive, macOS asks for the **Files and Folders › Removable Volumes** permission under **System Settings, Privacy & Security**. Check that Serato has it. **Full Disk Access** is a secondary thing to check. Unsigned builds may ask for it again after each update.
3. Restart Serato.
4. Still gone? Open **Snapshots** and choose **Review restore**. Serato's `_Serato_Backup` folder is the other copy. Quit Serato first. Restore can rewrite the Serato tags (cue points, beatgrid, autotags) inside each audio file, and removes Serato tags the snapshot didn't have. The audio stream is hash-checked before and after; if it would change, the file is left as it was. [Safety and backups](guide/safety.md#snapshots).

## C. Drive won't mount
1. Try another cable and port, and check that the drive appears in Disk Utility or Disk Management.
2. Every external drive keeps its own `_Serato_` folder, so its crates come back once it mounts.
3. FAT32 or read-only drives can stop crates from saving.

## D. After a Serato update
- On Serato 4 and later, the live library is a database in Application Support (Mac) or AppData (Windows), not just `_Serato_`.
- Serato 5.0 came out **Oct 19, 2026**. If you updated without a backup, stop and copy both locations before trying anything else.

---

!!! warning "PREVIEW"

    **Gig check** is **PREVIEW** until [#41](https://github.com/mookiejones/serato-library-manager/issues/41) merges. It is not in the app.

**About this app.** Open **Snapshots** to restore, or to undo a change another program made. **Review restore** writes nothing until you confirm, and confirm saves a snapshot first. **Review undo** puts back the previous snapshot. [Is my library safe?](is-my-library-safe.md).

Sources: Serato support articles and DJ reports collected in `faq-top20.md` and `docs-references.md`.
