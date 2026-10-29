# Before a gig

**Gig** is a read-only check. It scores the library and lists what is holding it back. It does not change the library, the crates, or the audio files. You can run it while Serato DJ Pro is open.

## Run the check

1. Open Serato Library.
2. Click **Gig**.
3. Click **All tracks** to check the space, or click one crate to check that crate and the crates inside it. The crate name is shown under the crate list.
4. Walk the five steps: **Drives**, **Missing files**, **Streaming**, **Empty crates**, and **Since last gig**. Each step says **Step N of 5**. One button names the thing to do, such as **Locate missing files**. **Back** returns to the previous step. **Exit gig check** leaves the check.
5. Read the score on each step. It shows the number out of 100, such as **72/100**, and **✓ Ready** or **✕ Not ready**. **Ready** means the score is at least 70 and nothing below is a hard stop. **Not ready** means do not treat the crate as ready to play.
6. The last screen says whether you are ready for the gig, the score, the crate, and the time of the check. **Check again** after you plug a drive back in or move a file. The report stays up while the new check runs. If the page cannot reach the library server, it says **Couldn't reach the library server. Check it's running, then press Check again**.

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
| **No snapshots yet** | Nothing has been saved to compare with this library, so there is no list of what changed. The score still drops, because there is no snapshot from the last 7 days. Open **Snapshots** and click **Take a snapshot**. |
| **Snapshots could not be read.** | The snapshot store beside the library did not open. The score drops as if there were no recent snapshot. Open **Snapshots** to see what is wrong. |

A missing drive, or a missing file in the crate you selected, is **Not ready** even when the number would otherwise pass.

## What changed

When a snapshot exists, **Since last gig** lists crates, cues, beatgrids, and tags that differ from the latest one. The snapshots are the ones in the **Snapshots** view. The check compares the library copy and the cues and beatgrids saved in that snapshot with the library now. It does not restore or change the snapshot. With no snapshot, that section says **No snapshots yet**.
