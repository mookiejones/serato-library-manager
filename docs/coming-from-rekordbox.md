# Moving between Serato and Rekordbox

> **Status: preview.** Rekordbox XML export ships with [PR #39](https://github.com/mookiejones/serato-library-manager/pull/39). Until it merges, nothing here works yet.

## How it works

1. **Rekordbox** reads the Serato library and the cue data in the audio files. This export leaves the library and the audio files unchanged.
2. It writes a Rekordbox XML file (`rekordbox.xml`), the DJ_PLAYLISTS format Pioneer publishes.
3. In Rekordbox 6 and 7 the import control is at **Preferences**, **Advanced**, **Database**, **rekordbox xml**. Since Rekordbox 5.6.1, importing that file leaves a track that is already in the collection unchanged. To replace its cues, beatgrid, and tags, open the **rekordbox xml** list, select all, right-click, choose **Import to Collection**, and answer **Yes** to **load information from imported library**. That replaces what Rekordbox already stored. A cue that exists only in Rekordbox is removed.
4. To play on CDJs, export the USB from Rekordbox. This export does not write a USB drive, Device Library Plus, OneLibrary, or `master.db`.

The page shows a loss report before the download. `python3 rekordbox.py -o rekordbox.xml` prints the same lines. The report is a list of sentences for the whole export. It names a file when the path cannot be encoded, or when the file cannot be opened.

The steps in the app are on the [Playlists](guide/playlists.md) page.

## What carries over

| Item | Serato | Rekordbox | Result |
|---|---|---|---|
| Crates and subcrates | Crates | Playlists and folders | A crate with subcrates becomes a folder, and its own tracks are a playlist of the same name inside that folder. A crate with no subcrates is a playlist. Smart crates become ordinary playlists. Their rules are not copied, and the loss report says so. |
| Track fields | Title, artist, album, genre, BPM, length, bitrate, comments | Track fields | Written. Rating is one of 0, 51, 102, 153, 204, or 255. Replay gain, overview waveforms, stems, and play history are not copied. The loss report says so. |
| Key | Text such as "8A" or "Am" | Free-text `Tonality` | Kept as Serato stored it. **Key as stored** is the default, so a library can contain both Camelot and classical names. **Camelot key** or **Classical key** rewrites names this export recognizes. Anything else is left unchanged and counted in the loss report. |
| Hot cues 1–8 | Named, coloured pads | Hot cues A–H | Kept. Serato's first eight pads are indices 0–7, which Rekordbox numbers A–H. **Memory cues** is on until you clear it, so each of these cues is also written again as a memory cue. The loss report counts those copies. A CDJ shows about the first 20 characters of the name. |
| Extra hot cues past 8 | Pads after the eighth | No hot-cue slot | Written only as memory cues. That happens whether or not **Memory cues** is on. The loss report counts them as cues outside slots 0–7. |
| Saved loops | Named and coloured | Loops | Kept as loops with a start and an end. They are memory loops, so they do not take a hot cue pad. A free pad is used only when hot loops is turned on. The loss report says which. |
| Cue and loop colours | Serato marker colours | Red, green, and blue | Written as channels from 0 to 255. Rekordbox may snap them to its palette. The loss report says so when cues were written. |
| Track colour | Serato track colour | `Colour` `0xRRGGBB` | Written in that form, for example `0xFF007F`. White is left out. Rekordbox's palette is eight colors, so another value may be ignored. The loss report says so. |
| Beatgrid | Fixed grid | `TEMPO` markers | Kept. One marker becomes one `TEMPO`. The bar is 4/4. |
| Flexible or Lucid grids (Serato 5) | Several markers | One `TEMPO` per marker | Written. BPM is two decimal places, so the grid can drift. The first marker is treated as a downbeat. If it is not, the bars in Rekordbox are shifted. The loss report names these tracks. A grid with more than 4096 markers, a truncated grid, or a version other than 1 is left out and named in the loss report. |
| Audio files | On disk | On disk | This export reads them and does not modify them. |

## Known limits

- **Cue timing on some MP3s.** The LAME/Xing header is read per file. No Xing header, and a LAME tag whose CRC matches, keep the cue time Serato stored. Xing or Info without a LAME tag, and a LAME tag whose CRC is missing or does not match, move cues, loops, and the beatgrid start 26 ms earlier. AAC, WAV, AIFF, and FLAC are not shifted. A time that would fall before the start is written at 0. The loss report counts each of these.
- **A file that cannot be opened.** The track stays in the XML without its cue points. The loss report names the file, and the rest of the export continues.
- **Flips.** Rekordbox has no flip markers, so flips are left out. The loss report counts them.
- Rekordbox does not write this file back into Serato, so the export is one-way.
