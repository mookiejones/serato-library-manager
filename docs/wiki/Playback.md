# Playback

Play a track that is already in the library. The sound stays on this computer. The request uses the track's library id.

Double-click a row, press **Enter**, or click **Play**. **Enter** on the list plays the selected track. **Enter** on a focused row plays that row.

The bar under the list shows the title, the artist, **Previous**, **Play** or **Pause**, **Next**, a seek bar, and volume. **Previous** and **Next** follow the list in its sort and filter order. When a track ends, the next row starts.

Cue points from the file sit on the seek bar in their colors. Click a cue to jump there. A track with no cues has no marks. With the seek bar focused, **Left** and **Right** move 5 seconds. **Shift** with **Left** or **Right** moves 30 seconds.

The bar also shows a waveform. The zoomed view keeps the playhead in the center and scrolls the track past it. Lows are red, mids are green, and highs are blue. **+** and **−** zoom in and out. Hold **Ctrl**, or **Command** on a Mac, and roll the mouse wheel to zoom. Those controls are not shortcut keys.

Under that is the whole track. The part you have already played is darker. Click or drag there to move through the track. Cue points and loops are drawn on both views, in the colors stored on the file. A loop is a shaded region. Beat marks sit on the zoomed view, as short lines along the top and bottom. A downbeat is a little longer than the other beats.

While the waveform is still being read, the overview uses the Serato Overview stored in the file, then switches to the computed one. If the file has no waveform, the bar says **Waveform unavailable for this format**. The track still plays.

**Play** and **Pause** are one button. Its name changes with the state. Hover a player control, or tab to it, and a note names the action. **Space**, **Left**, and **Right** are written there when they apply. **+** and **−** and the overview do the same.

**Space** plays or pauses. When nothing is playing, it starts the selected track. It does nothing while you are typing in a field. **Left** moves 5 seconds back. **Right** moves 5 seconds forward. Those are the only playback keys in the shortcut table. With the seek bar focused, **Shift** with **Left** or **Right** moves 30 seconds.

Playback does not change the audio file and does not add a history row. If the track is not in the library, or the file is missing, the bar says **Not in the library or file missing**. If the window cannot play the file, the bar says **This file cannot be played in this window.**

Music behind a shortcut folder still plays, including when that folder points at another disk. A shortcut that points at a file outside the folder named in the library does not.

The server builds a waveform for the same library id. WAV, AIFF, FLAC, MP3, and OGG are decoded here. M4A, AAC, and ALAC are decoded by the Mac or Windows audio system. On Linux they need ffmpeg already installed on this computer. This app does not include ffmpeg. Without a decoder the waveform is unavailable and the track still plays. A 60-minute stereo 44.1 kHz WAV is analyzed in 7.9 seconds and cached next to the app settings. The Serato folder and the audio file are not changed.
