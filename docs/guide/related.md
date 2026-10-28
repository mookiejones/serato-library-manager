# Related tracks

Related tracks are songs you want to remember together. A link can be two-way, so each track lists the other, or one-way, so only the track you started from lists the other.

The links are stored in a file named `related.sqlite`, next to this app's settings. They are not stored in Serato's library. Saving or removing a link works while Serato DJ Pro is open. Writing a Serato crate from those links does not.

!!! note "Related tracks and version 0.1.1"
    Related tracks were added after release v0.1.1. [Install](install.md) explains which download includes them.

## Where the file is

| System | File |
| --- | --- |
| macOS | `~/Library/Application Support/Serato Library/related.sqlite` |
| Windows | `%APPDATA%\Serato Library\related.sqlite` |

This is the **Serato Library** folder, with a space. It is not the **Serato/Library** folder that holds `master.sqlite`.

The file holds paths, titles, artists, lengths, notes, and ratings. It stays on this computer. [Settings and privacy](settings.md) lists what sharing can send. Notes and titles are not part of that.

## Save a link

1. Open a track that has a file path. A track with no path says **This track has no file path, so it cannot be linked.**
2. Find **Related tracks**.
3. In **Find a track to link**, type a title or an artist. The matches are tracks already loaded in this space.
4. Click the track.
5. Type a **Note** if you want one. The box holds 500 characters. The hint text is **blend out of**.
6. Choose a **Link rating** from **Not rated** through **5**, or leave **Not rated**.
7. Leave **Two-way link** ticked unless you want a one-way link.
8. Click **Save link**.

The bar says **Link saved.** The line under the heading counts saved links. A two-way link reads **Two-way**. A one-way link reads **One-way**.

## Save a suggestion

Under the search box, the page suggests other tracks in this space. A suggestion needs one of these:

- The same key, the relative major or minor, or one step around the Camelot wheel.
- A tempo within 6 percent, including half time and double time.
- A shared normal crate. Crates whose names start with `Related - ` are not counted. Smart crates are not counted.

The line above the list says **Suggested from key, tempo within 6%, and shared crates. Save stores a two-way link.** Each row names the reason, such as **same key** or **BPM within 6%**.

1. Click **Save** on a suggestion.

A suggestion save is two-way, with no note and no rating. Add a note later by removing the link and saving it from the search box.

When nothing is close, the page says **No suggestions from key, tempo, or shared crates.**

## Remove a link

1. Click **Remove** on the saved row.
2. Confirm **Remove the link to** the track name.

The bar says **Link removed.** The audio file and the Serato library do not change. A two-way link is removed from both tracks.

## Put the links in a Serato crate

This step writes Serato's library. Quit Serato first.

1. Click **Update Serato crate**.

The button creates or refreshes a normal crate named `Related - ` plus the track title. A track with no title uses the file name, then **Untitled**. The note under the button shows the crate name before you click.

The crate contains the saved related tracks that are in the same space. The open track is not added. A linked file that is not in the library is skipped. Click the button again after you change the links. The membership is replaced with the current list.

While Serato is open, the button stays off and the note says **Quit Serato before writing the crate.**

## While a track is playing

The live view is a different app, [serato-listener](https://github.com/mookiejones/serato-listener). Serato Library is where you save links and read suggestions. The listener is what you open while a deck is playing.

The listener reads `related.sqlite` and does not change it. On a Mac, with Serato DJ Pro open on the same computer, Serato can connect to it. Open `http://127.0.0.1:8787/` to see the decks and the related tracks for the song that is loaded. Pairing does not start on Windows. The listener page on Windows can still read the library and the saved links.

Install and run steps for that app are in its own repository. This guide does not repeat them.
