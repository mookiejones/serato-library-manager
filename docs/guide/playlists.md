# Playlists

**Export** writes an M3U playlist. **Import** makes a crate from an M3U file. Both use the tracks already in the library. Import does not copy audio onto the computer.

Quit Serato before you import. Export only reads the library.

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
