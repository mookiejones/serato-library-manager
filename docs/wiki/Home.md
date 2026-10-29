# Serato Library

```mermaid
flowchart LR
  space["Space: Library, Video, Apple Music, Prepare"] --> views["Crates, History, Missing, Duplicates, Stems, Files, Snapshots"]
  views --> detail["Track details and Cue points"]
```

A window on your computer for the Serato DJ Pro library. Crates, Cue points, and Backups stay on this machine.

- [Quick Start](Quick-Start.md)
- [Install on a Mac](Install-macOS.md)
- [Install on Windows](Install-Windows.md)

The long guide is published at <https://mookiejones.github.io/serato-library-manager/>.

## What you click

**Library** sits at the top of the sidebar. The status line under it starts as **Checking Serato**.

The views are **Crates**, **History**, **Missing**, **Duplicates**, **Stems**, **Files**, and **Snapshots**.

The space menu shows **Library**, **Video**, **Apple Music**, and **Prepare**.

**Settings** is at the bottom of that sidebar.

## Cue points and Backups

Cue points live in the audio file. A normal save does not rewrite them.

**Snapshots** keeps hash-checked copies of the library, the crates on each drive, and the Cue point frames stored in the audio files. The music itself is not copied.

Open **Snapshots**, choose **Review restore**, then **Restore**. Restore never changes audio data. It can put those Cue point frames back.

Quit Serato DJ Pro before a write. On Serato 5, writes and restores stay off.

## One download

GitHub Releases is the only download. There is no Homebrew formula, no winget package, and no other website.

**Rekordbox** can export `rekordbox.xml`. The guide marks that export **PREVIEW**.
