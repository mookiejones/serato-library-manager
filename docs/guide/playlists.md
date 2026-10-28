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

**Rekordbox** writes `rekordbox.xml`, the file Rekordbox imports. A CDJ USB is then prepared in Rekordbox. This app does not write the newer USB formats (Device Library Plus or OneLibrary). A follow-up can cover those.

1. Select **Crates**.
2. Select the crate to export. Select **All tracks** to export the whole space.
3. Click **Rekordbox**.

The browser downloads `rekordbox.xml`. In History, Missing, Duplicates, or Stems, **Rekordbox** uses the whole current space.

The file lists each track's location, title, artist, album, genre, BPM, key, length, bitrate, and comments. Hot cues and loops are included, with their colors and names, when the audio file has Serato markers. The beatgrid is included when the file has one. A track with no path is left out.

Crates become playlist folders. A subcrate stays inside its parent. A crate that has both tracks and subcrates becomes a folder, and its own tracks are a playlist with the same name inside that folder.

From the project folder, the same file can be written without opening the page:

```bash
python3 rekordbox.py -o rekordbox.xml
```

## Import into Rekordbox

1. Open Rekordbox.
2. Open **Preferences**.
3. Choose **Advanced**.
4. Choose **rekordbox xml**.
5. Import `rekordbox.xml`.

Rekordbox can then export a USB for CDJs. Device Library Plus and OneLibrary drives are not produced by this export.
