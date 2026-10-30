# Play a track

Play a file that is already in the library. The app streams it from this computer. It does not upload the file, write to it, or add a Serato history row. The request uses the track's library id. A filesystem path is not accepted.

1. Click a track.
2. Double-click the row, press **Enter**, or click the play button on the row. **Enter** on the list plays the selected track. **Enter** on a focused row plays that row. In the detail pane, click **Play**.
3. The bar shows the title, the artist, **Previous**, **Play** or **Pause**, **Next**, a seek bar, the elapsed time, the total time, and **Volume**.

**Previous** and **Next** follow the list you are looking at, in its current sort and filter order. When a track ends, the next row starts. The last row stops.

Cue points read from the file sit on the seek bar in their colors. The name shows when you point at a cue, and in the cue's label for a screen reader. Click a cue to jump there. A track with no cues has no marks.

The bar also shows a waveform. The zoomed view keeps the playhead in the center and scrolls the track past it. Lows are red, mids are green, and highs are blue. The brighter core is the sustained level. The fainter edge is the peak. **+** and **−** zoom in and out. Hold **Ctrl**, or **Command** on a Mac, and roll the mouse wheel to zoom. Those controls are not shortcut keys.

Under the zoomed view is the whole track. The part you have already played is darker. Click it, or drag, to move through the track. Cue points and loops are drawn on both views, in the colors stored on the file. A loop is a shaded region. Beat marks sit on the zoomed view, as short lines along the top and bottom. A downbeat is a little longer than the other beats.

While the waveform is still being read, the overview uses the Serato Overview stored in the file, then switches to the computed one. If this computer cannot build a waveform for the file, for example an M4A when ffmpeg is not installed, the bar says **Waveform unavailable for this format**. The track still plays.

Drag the seek bar to move through the track. With the seek bar focused, **Left** and **Right** move 5 seconds. **Shift** with **Left** or **Right** moves 30 seconds.

**Play** and **Pause** are one button. Its name changes with the state.

**Space** plays or pauses. When nothing is playing, it starts the selected track. It does nothing while you are typing in a field. **Left** moves 5 seconds back. **Right** moves 5 seconds forward. Those are the only playback keys in the shortcut table. With the seek bar focused, **Shift** with **Left** or **Right** moves 30 seconds.

If the track is not in the library, or the file is missing, the bar says **Not in the library or file missing**. If this window cannot decode the file, the bar says **This file cannot be played in this window.**

MP3, M4A, AAC, ALAC, FLAC, WAV, AIFF, and OGG are the types the server will send.

The server can also build a frequency-colored waveform for that same library id. WAV, AIFF, FLAC, MP3, and OGG are decoded on this computer. M4A, AAC, and ALAC need ffmpeg already installed; otherwise the waveform says it is unavailable and playback still works. A 60-minute stereo 44.1 kHz WAV is analyzed in 7.9 seconds. The result is cached beside the app settings, not inside the Serato folder, and the audio file is not changed. Cue points, loops, and the beatgrid on the seek bar are read from the file and are not written back.

Music that lives behind a shortcut folder still plays, including when that folder points at another disk. A shortcut that points at a file outside the folder named in the library does not.
