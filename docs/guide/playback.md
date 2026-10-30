# Play a track

Play a file that is already in the library. The app streams it from this computer. It does not upload the file, write to it, or add a Serato history row. The request uses the track's library id. A filesystem path is not accepted.

1. Click a track.
2. Double-click the row, press **Enter**, or click the play button on the row. **Enter** on the list plays the selected track. **Enter** on a focused row plays that row. In the detail pane, click **Play**.
3. The bar shows the title, the artist, **Previous**, **Play** or **Pause**, **Next**, a seek bar, the elapsed time, the total time, and **Volume**.

**Previous** and **Next** follow the list you are looking at, in its current sort and filter order. When a track ends, the next row starts. The last row stops.

Cue points read from the file sit on the seek bar in their colors. The name shows when you point at a cue, and in the cue's label for a screen reader. Click a cue to jump there. A track with no cues has no marks.

Drag the seek bar to move through the track. With the seek bar focused, **Left** and **Right** move 5 seconds. **Shift** with **Left** or **Right** moves 30 seconds.

**Play** and **Pause** are one button. Its name changes with the state.

If the track is not in the library, or the file is missing, the bar says **Not in the library or file missing**. If this window cannot decode the file, the bar says **This file cannot be played in this window.**

MP3, M4A, AAC, ALAC, FLAC, WAV, AIFF, and OGG are the types the server will send.

Music that lives behind a shortcut folder still plays, including when that folder points at another disk. A shortcut that points at a file outside the folder named in the library does not.
