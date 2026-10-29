# Hot loops and Cue points

> **TODO-SCREENSHOT:** A track open on the right under **Cues, loops, and beatgrid**, with a few colored Cue points and one loop. The bar above the list shows **Memory cues** checked, **Hot loops** clear, the help line **Uses a free hot-cue pad**, and the key menu on **Key as stored**.

```mermaid
flowchart TD
  open["Open a track from Crates"] --> read["Cues, loops, and beatgrid"]
  read --> file["Read from the audio file"]
  file --> save["Save track writes the library only"]
  bar["Memory cues and Hot loops"] --> xml["Rekordbox writes rekordbox.xml"]
  snap["Snapshots, then Restore"] --> frames["Saved Cue point frames go back"]
  frames --> audio["Restore never changes audio data"]
```

Cue points, loops, and the beatgrid live in the audio file. Open a track from **Crates**. The section is **Cues, loops, and beatgrid**. The line under it reads **Read from the audio file. These are not written back.**

**Save track** writes the library. It does not rewrite the audio file. A missing file says **The file is not on disk, so cues cannot be read.** A file with no Serato markers says **No Serato cues in this file.**

**Hot loops** sits beside **Memory cues** in the bar above the list. **Memory cues** starts on. **Hot loops** starts off. The help line reads **Uses a free hot-cue pad.** The app remembers Memory cues, Hot loops, and the key notation (**Key as stored**, **Camelot key**, or **Classical key**) in `settings.json`.

Those boxes change the Rekordbox file only. They do not move pads inside Serato. With **Hot loops** on, a saved loop takes its own pad when that pad is free and it is one of the first eight. A loop whose pad is already taken stays a memory loop. A loop past those eight pads stays a memory loop too. With the box clear, every saved loop stays a memory loop.

Putting Cue points back is a restore from **Snapshots**. Restore never changes audio data. It can put the saved Cue point frames back. [Backups and restore](Backups-and-Restore.md) is that flow. The export keeps **Status: preview** on [Export to Rekordbox](Export-to-Rekordbox.md).
