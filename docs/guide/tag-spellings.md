# Tag spellings

**Tag spellings** groups genre and artist spellings that mean the same thing, such as Hip Hop, Hip-Hop, and hiphop. Pick one spelling per group. Review the rows that would change, then Apply. **Titles** strips track numbers, URLs, and (Original Mix), moves feat. into remixer when remixer is empty, and title-cases ALL CAPS or all lowercase. The write goes through the same library path as a crate edit. Quit Serato first. Audio files stay as they are.

The note under the heading says **Pick one spelling per group. Writes the library, not the audio files. Quit Serato first.** On **Titles** it names those cleanup rules instead.

This view covers the whole space. The crate list is hidden.

## Review a group

1. Open crateCraft.
2. Click **Health** in the drawer, then **Tag spellings**.
3. Click **Genre** or **Artist**. **Genre** is the first field.
4. Click a group in the list. The **Suggested spelling** column is the spelling most tracks already use. **Tracks** and **Spellings** are counts.
5. Select the spelling you want. **Review** and **Apply** stay above the list.
6. Click **Review**. The status line names how many rows would change, and the selected group lists each stored spelling and the spelling it would become.
7. Click **Apply**. Apply stays off until Review matches the selected spelling, the library is writable, and at least one row would change.

When a later track still uses another spelling of a saved mapping, a banner lists those rows and **Apply saved mappings** writes them. Opening the view does not write.

**Check again** reloads the groups. A space change or **Reload** does the same.

If the page cannot reach the library server, it says **Couldn't reach the library server. Check it's running, then press Check again**.

When every value already uses one spelling, the report says **Every genre in this space uses one spelling.** (or artist).

While Serato has the library open, Apply stays off.

If Apply cannot finish, a snackbar at the bottom names the file (for example `master.sqlite`) and says to open the local log from **Settings**, or read the operation log on **Backups**. The full path stays in that local log. The snackbar does not ask you to delete a journal file.

## Clean titles

1. Open crateCraft.
2. Click **Health** in the drawer, then **Tag spellings**.
3. Click **Titles**. The report lists each title that would change, including a remixer move.
4. Click **Apply**. Apply stays off when every title already matches, or while Serato has the library open.

**Check again** reloads the title plan.

When every title already matches, the report says **Every title in this space already matches the cleanup rules.**

## What Apply writes

Apply rewrites the genre or artist on those library rows, or the title and remixer for **Titles**. Cue points stay in the audio files. The files themselves are not rewritten.

Apply also remembers that spelling next to the app settings, not in the Serato folder. **Apply saved mappings** rewrites later tracks that still use another form of a saved spelling, including a new import that is no longer in a spelling group.

## Resize the list and the details

This view hides the crate list and the track sheet, so there is no list/details divider here. The width you set in **Crates** is kept for the next time you open a track list.
