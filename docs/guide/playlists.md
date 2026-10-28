# Playlists

**Export** writes an M3U playlist. **Rekordbox** writes `rekordbox.xml`. **Import** makes a crate from an M3U file. Both playlists use the tracks already in the library. Import does not copy audio onto the computer.

Quit Serato before you import. Export and Rekordbox only read the library. Rekordbox also reads cue points from the audio files and does not change them.

## Export

1. Select **Crates**.
2. Select the crate to export. Select **All tracks** to export the whole space.
3. Click **Export**.

The browser downloads `crate.m3u`. In History, Missing, Duplicates, or Stems, **Export** uses the whole current space.

The file is an extended M3U. It has a playlist name, a length, and a path for each track. A track with no path is a comment line that says it was omitted. Open the file in a text editor if you want to read it.

## Import

1. Select **Crates**.
2. Select the crate that should hold the new playlist. Select **All tracks** to put it at the top of the space.
3. Click **Import**.
4. Choose a `.m3u` or `.m3u8` file.

The crate name is the file name without `.m3u` or `.m3u8`. A file with no name becomes **Imported playlist**.

The bar reports how many tracks were added. Lines that do not match a track already in the library are counted in the same sentence: **lines did not match a library track.** Those lines are skipped. The page does not search the disk for a new file.

An empty playlist says **The playlist is empty.**

Import matches a line to a track that is already in the library. Put the audio in the library in Serato first when the path is new.

## Rekordbox

**Rekordbox** writes `rekordbox.xml`, the file Rekordbox imports. A CDJ USB is then prepared in Rekordbox. This app does not write the newer USB formats (Device Library Plus or OneLibrary). A follow-up can cover those. [Moving between Serato and Rekordbox](../coming-from-rekordbox.md) lists what the file keeps.

1. Select **Crates**.
2. Select the crate to export. Select **All tracks** to export the whole space.
3. Click **Rekordbox**.

**Rekordbox** opens a dialog that lists what could not be copied. The file downloads after you confirm. The download is the XML from that same check, so a failed request is not saved as `rekordbox.xml`. A file that is locked or cannot be opened is still in the XML, without its cue points, and the dialog names that file. In History, Missing, Duplicates, or Stems, **Rekordbox** uses the whole current space.

**Memory cues** is on until you clear it. Each hot cue is then also saved as a memory cue, which is what some CDJ screens show. **Key as stored** leaves the key text Serato has. Choose **Camelot key** or **Classical key** when Rekordbox is set to the other notation.

The file lists each track's location, title, artist, album, genre, BPM, key, length, bitrate, and comments. Hot cues keep their number, name, and color. Saved loops are loops. The beatgrid is included when the file has one, including a grid with a marker at each tempo change. A track with no path is left out. An MP3 is shifted only when its LAME or Xing header says Serato and Rekordbox disagree, which is about 26 milliseconds. An AAC file is not shifted by that amount.

Crates become playlist folders. A subcrate stays inside its parent. A crate that has both tracks and subcrates becomes a folder, and its own tracks are a playlist with the same name inside that folder.

From the project folder, the same file can be written without opening the page. The command prints the same loss report the bar shows:

```bash
python3 rekordbox.py -o rekordbox.xml
```

## Import into Rekordbox

In Rekordbox 6 and 7 the import control is at **Preferences**, **Advanced**, **Database**, **rekordbox xml**.

Since Rekordbox 5.6.1, importing an XML file does not update a track that is already in the collection. Rekordbox 6 and 7 do the same. The cues already in Rekordbox stay as they are.

To replace the cues, the beatgrid, and the tags on tracks that are already in the collection:

1. Open the **rekordbox xml** list in the sidebar.
2. Select all the tracks.
3. Right-click and choose **Import to Collection**.
4. Answer **Yes** to **load information from imported library**.

**This overwrites cues, the beatgrid, and tags in Rekordbox.** It does not merge them. A cue that exists only in Rekordbox is removed. Export a Rekordbox XML backup first if you need those cues.

Rekordbox can then export a USB for CDJs. Device Library Plus and OneLibrary drives are not produced by this export. Cue colors may snap to Rekordbox's palette. Flips are left out, because Rekordbox has no flip markers. A beatgrid with more than 4096 markers is left out and named in the loss report.
