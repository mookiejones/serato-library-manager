# Before a gig

**Gig** is a read-only check. It scores the library and lists what is holding it back. It does not change the library, the crates, or the audio files. You can run it while Serato DJ Pro is open.

## Run the check

1. Open Serato Library.
2. Click **Gig**.
3. Click **All tracks** to check the space, or click one crate to check that crate and the crates inside it.
4. Read the score. **Ready** means the score is at least 70 and nothing below is a hard stop. **Not ready** means do not treat the crate as ready to play.
5. Click **Check again** after you plug a drive back in or move a file.

The same check from a terminal, in the repository directory:

```bash
python3 gig_check.py
```

`--crate` is a crate id, or `all`. `--space` selects the space. The default space is Serato Library. The command prints the report. It does not write a file.

## Holding it back

The list under **Holding it back** is each reason the score is not 100.

| What you see | What to do |
| --- | --- |
| **Not ready**, and a drive name, with the word **absent** | Plug that drive in. Tracks on it are **unavailable**. They are not listed as missing files. The drive is named once. |
| **Not ready**, and missing files | Each missing path is listed under **Missing files**. [Missing files](missing.md) is where you point a track at a file that moved. |
| A streaming track | Apple Music tracks play only while you are logged in to Apple Music. They are counted on their own, not as missing files. |
| An empty crate | The line is **Serato may delete this crate when it closes.** Put a track in the crate if you want to keep it. Serato's own clean-up note describes empty crates disappearing after quit, and that note does not name a version. The Serato DJ 4.0 crate page does not say they are deleted. |
| **No snapshot in the last 7 days** | The score drops. A snapshot from the last 7 days does not drop it. |
| **No snapshots yet** | Nothing has been saved to compare with this library, so there is no list of what changed. The score still drops, because there is no snapshot from the last 7 days. |

A missing drive, or a missing file in the crate you selected, is **Not ready** even when the number would otherwise pass.

## What changed

When a snapshot exists, **Since last gig** lists crates, cues, beatgrids, and tags that differ from the latest one. With no snapshot, that section says **No snapshots yet**.
