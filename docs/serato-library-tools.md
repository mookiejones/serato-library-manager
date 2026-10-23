# Serato library tools and requested features

Research notes, 20 October 2026. Sources are vendor sites, Serato's own announcements, the Serato forum, Reddit, and GitHub. Vendor comparison pages (Crate Cleaner, Lexicon, Music Library Doctor) promote their own product. Prices and Serato 4 support claims move. Check the current build before trusting a write.

This project reads the live Serato DJ 4/5 library at `~/Library/Application Support/Serato/Library/master.sqlite` and does not write to it.

## Where the library actually lives

Serato DJ 3 kept the library in `~/Music/_Serato_/database V2`, with crates as files under `Subcrates` and smart crates under `SmartCrates`. Each external drive with music has its own `_Serato_` folder. On Windows the music folder is `C:\Users\<user>\Music\_Serato_`.

Serato DJ 4 moved the live library to SQLite:

- `~/Library/Application Support/Serato/Library/master.sqlite` is the database the app opens. It holds the aggregate library, history, and a lock table. WAL mode.
- `root.sqlite` sits beside it. Serato attaches it as `db1` and aggregates it into `master.sqlite` on startup.
- Automatic backups of `master.sqlite` live in `Library/Backups` next to that folder: about 15 minutes after open, then every 24 hours, and when the schema changes.

The old `database V2` and `.crate` files are still written, as a compatibility export. Renaming `database V2` does not reset a Serato 4 or 5 library. Tools that only edit `.crate` files or `database V2` are editing the compatibility copy, not the library Serato 4/5 runs from.

Cue points, loops, and beatgrids live in the audio files (Serato GEOB tags such as Markers2), not in the crate list. Deleting a file, or retagging it with a tagger that rewrites the whole ID3 block, can drop those even when the crate entry looks fine.

Observed schema: Serato DJ Lite 4.0.9 used SQLite `user_version` 202, with many migration scripts inside `master.sqlite`. Treat an unrecognized schema version as a warning. See `serato-dj-mcp` notes below.

### Safe to delete, with Serato closed

`neworder.pref` and `collapsed.pref` (Serato rebuilds them), old logs and crash reports, and old Export Backups once you have your own copy.

### Never delete

`Subcrates`, `SmartCrates`, `database V2` on Serato 3, or anything in the Serato 4 `Library` folder.

### Write safety

- Quit Serato before any tool writes. The database is locked while it is open.
- Back up `master.sqlite` (and the WAL/SHM files beside it) and `~/Music/_Serato_` first.
- Fix missing files before duplicate cleanup. Re-adding a moved file creates a second entry next to the orange one.
- Syncing the live `master.sqlite` through Dropbox or a similar live sync corrupts it. One source of truth, then a deliberate sync while Serato is closed.

## What Serato itself added

### Serato DJ 4 (public beta August 2025, called the biggest library update)

Taken from support tickets, Reddit, and the Serato forum. Many of these had been requested since Scratch Live.

- Crate search (DJ Pro; not in Lite).
- Show which crates a track is in.
- Favorite crates, pinned to the top.
- Crate color.
- Sort crates by name, date, or a custom order.
- Emoji ratings on tracks and crates (country-flag emoji unavailable on Windows). Star ratings also exist.
- Right-click: beatgrid lock, analyze, rescan metadata, send to Prepare or Stems, relocate, reveal in Finder, delete.
- Analyze on import (BPM, key, length).
- Analyze while hardware stays connected. Previously, batch analysis wanted hardware unplugged. Loading one track to a deck still analyzed it.
- Streaming and local files in the same crate.
- Crate footer: track count, play time, file size.
- Column view for the Prepare panel.

### Serato DJ 5.0 (19 October 2026)

- Lucid beatgrids. Re-analyze to use them. Existing grids are not overwritten. Opening the library in an older Serato version shows the old grids.
- Serato iOS Transfer. Crates, songs, cue points, beatgrids, and key metadata from the laptop to Serato DJ for iOS. Requires 5.0 on the laptop.
- Several streaming services open at once, listed in the library sidebar.
- Cue loops.
- Protect Library, in Setup. Serato will not remove tracks from the library, crates, or disk from inside the app.
- M3U and M3U8 import is back. Drag a playlist in and it becomes a crate. This had been removed in 4.0. People who built crates from MediaMonkey and similar tools rolled back to 3.x because of that. Works with exports from other DJ software, Apple Music, and Spotify.
- Key and BPM show for streaming tracks without loading them. Beatport, Tidal, SoundCloud, and Spotify. Not Apple Music at release.
- Right-click Analyze files runs a full analysis. Set beatgrids re-analyzes the grid. Tracks can also be dragged onto the analyze button.

5.0 does not add a duplicate finder, bulk tag editing, folder-to-crate sync, or a CDJ USB export.

## Tools, by job

There is no single best tool. Cleanup, conversion, and phone prep are different jobs.

### Cross-app library, with Serato as one target

**Lexicon** — https://www.lexicondj.com/

One library, synced out to Serato, Rekordbox (5/6/7), Traktor Pro (3/4), VirtualDJ, Engine DJ, djay Pro, and iTunes. Mac, Windows, iOS, Android.

Serato 4 support since 1.10 (March 2026): import and export of the new database, Spotify and Beatport streaming tracks inside Serato, smart crates, external and network drives, playlist color, and crate order. Serato 3 and Serato 4 are separate sync targets. Syncing to the wrong one writes a database that the app you actually run will not read.

- Serato 4 library path: macOS `~/Library/Application Support/Serato/Library`, Windows `AppData\Local\Serato\Library`. Crates are no longer the files in `_Serato_/Subcrates`.
- Serato 3 still uses `_Serato_` in the Music folder and on each external drive.
- Close Serato first. Lexicon waits until it is fully quit.
- A Full sync removes Serato crates that are not in Lexicon.
- Conversion between DJ apps is free. Essential (about $10–17/month or a lifetime in the $200–250 range, depending on the page and date) covers track and playlist editing, the mobile app, smart playlists, and analysis. Ultimate (about $20/month or $400–500 lifetime) adds cue generation, duplicate finding, watch folders, and cloud backup. Prices rose on 8 September 2026. Confirm on the site.
- Local-first. Cloud backup is optional, for moving one library between machines. It does not live-sync two open databases.
- Path mappings so a different drive letter does not break the library.
- Rekordbox to Serato: playlists become crates, intelligent playlists become smart crates where the rules translate, hot cues come across (Rekordbox has 16, Serato has 8; Lexicon takes the first 8 unless you reorder them), memory cues are folded into hot cues because Serato has no memory cues.

**MIXO** — https://www.mixo.dj/

The same library on a laptop and a phone, synced through your own Dropbox, Google Drive, or OneDrive. Mac, Windows, Linux, iOS, Android. You can edit cues, playlists, and metadata on the phone.

Imports and exports Serato, Rekordbox, Traktor, VirtualDJ, Engine DJ, djay Pro, Cross DJ, Mixxx, DEX 3, iTunes, and others. Gold is required to sync or bridge apps. Subscription only, no lifetime option, and a device cap (reported as two computers plus mobile).

Serato v4: since MIXO 2.7 the v4 database is the default. Compatibility Mode falls back to the old Subcrates folder. Only tracks that were active in Serato's last session are imported (the drives and streaming services last connected). For several streaming services, open Serato, enable the service, quit, then import.

Export options that matter: Update Track Tags must be on for cues and beatgrids to be written. Overwrite existing Serato beatgrids is off by default. Save MIXO Tags To Comments overwrites the comments field. Update Changed Tags Only limits the rewrite to tracks edited in MIXO.

**DJ Conversion Utility 2 (DJCU2)** — MixMasterG / ATGR

One-shot conversion between DJ apps, including cues, beatgrids, and a Mixed In Key integration. The source library is read-only. Smart playlists are not converted. Empty crates and crates that contain only streaming tracks are filtered out. There is a Force Serato 3 Legacy option, encoder-shift correction, and a Mixed In Key bug correction. Analysis in the destination app can overwrite converted grids and cues, so auto-analysis in Serato should be off for the import. Paid, sold with the other ATGR utilities. This is the practical path when a Serato crate has to play on CDJs.

### Serato-only cleanup

**Music Library Tools (MLT / MLT Pro)** — https://musiclibrarytools.co.uk/

Mac and Windows. Serato 4 since MLT 2.0. Missing tracks, acoustic duplicate finding, crate management, and MLT Switch, which gathers files into one folder and rewrites Serato's paths so crates and cue points stay attached.

Duplicate scanning is free. Replacing duplicates inside crates is paid. Suite price reported around £159.99 one-time. Single tools about £9.99 to £39.99, some free. It does not convert the library to other DJ apps.

**Crate Cleaner** — https://cratecleaner.com/

Mac only, Serato only. Finds duplicate groups and shows which copy has cue points or the higher bitrate, archives the extra copies instead of deleting them, and moves crate membership onto the copy you keep. Missing-file relink is confidence-scored. Fake-320 check. Smart crates from BPM, Camelot key, energy, and play data, exported back to Serato, or as M3U8 / Rekordbox on the Studio plan.

Free tier with daily caps (reported as 10 duplicate actions and 5 relinks a day). Pro about $9/month, Studio about $15/month, lifetime about $199.

Serato 4 support is their own claim: the comparison page says yes since version 2.9.0. A different page of theirs, checked around the same time, still described Serato 4 support as in progress and targeted for October–November 2026. Confirm the build before a write.

**Music Library Doctor** — https://musiclibrarydoctor.com/

Mac and Windows. Local only, no account, no upload. One-time purchase, with a free scan. Aimed at library health across Rekordbox, Serato, and VirtualDJ: acoustic duplicates and a 0–100 audio-quality score from spectral analysis (fake 320 MP3s and fake FLACs). Their own 2026 buyer's guide. Serato 4 support is not clearly stated. No set building and no cross-app conversion in the sense Lexicon does it.

**CrateSync** — https://cratesync.bornd-fono.de/ (forum thread: https://serato.com/forum/discussion/2107047)

Free Mac app by Bornd Fono, announced June 2026. Built for one annoyance: crates drifting away from folders.

- Link a folder to a crate once. Sync adds what is new and removes what is gone. Audio files are not touched.
- Point it at a folder tree and it builds the matching subcrate hierarchy.
- Backs up the Serato folder.
- Reorders crates faster than doing it inside Serato.
- Version 2.0 (30 June 2026) adds crate to playlist and playlist to crate for M3U8, M3U, PLS, and CSV.

This is the feature people have asked Serato for since Scratch Live. A different commercial product also uses the name CrateSync (`cratesync.pro`, about $29.99 at launch). That one scans folders, fixes metadata, and exports toward Serato, iTunes, and Rekordbox. Do not confuse the two.

**Crate Sweep** — https://cratesweep.com/

Publishes a Serato cleanup workflow and is listed alongside tools that claim Serato 4 support. Not verified here beyond that.

### Set prep and cue moving

These do not replace a library manager.

**Crate Hackers** — set prep. Export a finished crate to Serato, VirtualDJ, Rekordbox, or M3U. Tracks must already match files on a connected drive. Close Serato before the write. If direct export fails, export M3U and drag that into Serato. M3U import works again in Serato 5.0.

**DJ Cue Bridge** — https://djcuebridge.com/

Free, in the browser, no upload (v0.4 as of this research). Converts hot cues and loops between Mixed In Key, Rekordbox XML, Serato (Markers2 in FLAC, MP3, AIFF), Traktor `collection.nml`, and VirtualDJ `database.xml`. Engine DJ is read-only. It does not edit crates or the Serato database.

**Mixed In Key**

Key detection and energy cues written into the files. Not a library manager. One 2026 comparison found Mixed In Key and Serato disagreeing on key for about 45% of tracks, and all three of Mixed In Key, Rekordbox, and Serato agreeing on only about 39%. DJCU2 can apply Mixed In Key data without letting Mixed In Key's own write options clobber cues you already set.

**dupeGuru**

Free, Mac and Windows. File-level duplicate scan. Serato's own old tutorial points at it: scan by filename, review, trash the dupes. Deleting the files leaves orange library rows and broken crate entries unless the database is cleaned afterwards.

**General taggers (Mp3tag, beets, OneTagger, and similar)**

Fine for title, artist, and genre. Dangerous if they rewrite the file and drop Serato GEOB frames. Cues, loops, color, and the beatgrid live there. Preserve unknown frames, or do not retag files that have been prepared in Serato.

### Browser and one-off converters

**Mixgraph crate reader** — https://www.mixgraph.io/tools/serato-crate-reader

Drop a `.crate` or a whole `_Serato_` folder in the browser. Crates are joined to `database V2` on the file path (case-insensitive, both slash styles). Export Rekordbox XML, M3U8, or CSV, including title, artist, album, genre, label, BPM, key, and length. Cue points, loops, beatgrids, and the overview waveform stay in the files and are not exported. Crate files are a flat run of chunks: a four-character tag, a 32-bit length, and that many bytes. A crate starts with a `vrsn` chunk.

**serato2rekordbox** — https://github.com/BytePhoenixCoding/serato2rekordbox

Python CLI, v1.3. Crates and subcrates, title, artist, BPM, key, hot cues, and the first beat of the Serato beatgrid, written as Rekordbox XML. MP3, M4A, and WAV. Tested against Rekordbox 6.8.5. Import under Settings, Advanced, rekordbox xml.

**cratetom3u** — https://github.com/MartinHH/cratetom3u

CLI, `.crate` to `.m3u`. Smart crates are not supported. Paths in crate files have no leading slash, so on a Mac you usually pass `-a /`.

**rekordbox-serato-bridge** — https://github.com/xxvw/rekordbox-serato-bridge

Rust CLI. The README still marks rekordbox XML, rekordbox USB, and Serato GEOB as planned. Not a working converter as documented.

## Developer libraries

Most of these speak Serato 3 (`database V2` and `.crate`). The live Serato 4/5 library is SQLite.

**serato-tools** — https://github.com/bvandrc/serato-tools

Python. `pip install serato-tools`. Releases through 4.0.2 (August 2026). The most complete read/write library for the old format:

- Track tags: cue points, color, beatgrid, waveform, autogain.
- `database V2` parse and modify, including renaming a file and updating the path so it does not go missing.
- Crate parse and modify.
- Smart crate rules.

It checks for the version string `2.0/Serato Scratch LIVE Database`. Back up `database V2` before any modify call. This does not write `master.sqlite`.

**serato-dj-mcp** — https://github.com/Venut-Technologies/serato-dj-mcp

Closest open-source project to a Serato 4 tool. Local, macOS. Not affiliated with Serato.

- Reads the 4.x SQLite library. Other 4.x schema versions are read with a `schema_unknown` warning. Serato DJ Pro 4.x was expected to match Lite and had not been fully tested when the notes were written.
- Harmonic search by BPM and Camelot key, crate browsing, duplicate and missing-file audits.
- Can create new top-level crates in `root.sqlite`, shown before anything is written. Serato picks them up a few seconds after launch.
- Writes nothing else. It does not change or delete an existing crate, does not edit a track, and does not touch `master.sqlite`, `database V2`, or `Subcrates`. Serato regenerates those.
- Serato 3 is detected and refused. That version has no SQLite library.

Notes from their `docs/serato-4x-notes.md`, taken from Serato DJ Lite 4.0.9, schema 202, on macOS, by watching files rather than from Serato's source:

- `master.sqlite` is what the GUI opens. It has the lock table, history, and every location.
- `root.sqlite` is attached as `db1`. Triggers are declared `ON db1.<table>` and will not run if you open that file as the main connection.
- `root.sqlite` has its own `master` table. `last_sync_secret` does not fit in a JavaScript number, so `SELECT *` throws.
- Serato copies `root.sqlite` into `master.sqlite` on startup (a few seconds on a tiny library).
- `user_version` 202 on Lite 4.0.9. `master.sqlite` ships dozens of its own migration scripts.

**serato-connect** — https://github.com/chrisle/serato-connect

Node. Read-only. History sessions (polls by mtime), GEOB cues, loops, flips, beatgrid with tempo changes, track color, BPM lock. MP3, AIFF, FLAC, Ogg Vorbis, M4A/MP4. Crate files, `database V2`, search, and library stats.

**pyserato** — https://github.com/laker-93/pyserato

Create, read, and write crates, including hot cues and loops. Points at Holzhaus/serato-tags for the format. Default root is `~/Music/_Serato_`.

**seratoparser** — https://github.com/SpinTools/seratoparser

Go, MIT. Read-only. `database V2`, crates, history database, and history sessions.

**cratedigger** — https://github.com/adammillerio/cratedigger

Python. Mirrors a folder tree into Serato crates, prefixed so several libraries do not collide. Successor to the abandoned serato-itch-sync. Speaks crate files, not `master.sqlite`.

**Serato-lib** — https://github.com/jesseward/Serato-lib

Early notes on the Scratch Live crate and library binary formats, plus a limited crate editor. Historical. The format description is still the right mental model for `.crate` files: sequential tagged chunks.

**Holzhaus/serato-tags** — https://github.com/Holzhaus/serato-tags

Reference write-up of the GEOB tag format. Read this before any code that rewrites audio tags.

## What people still ask for

Resolved in Serato DJ 4, so these are no longer open requests: searchable crates, "which crates is this track in", alphabetical crates, favorite crates, crate color, ratings, right-click, analyze on import, analyze with hardware connected, streaming and local files in one crate, crate count and duration.

Resolved in Serato DJ 5: M3U/M3U8 import, a lock against deleting tracks from inside the app, key and BPM on streaming tracks, iOS crate transfer.

Still open, from r/Serato and the Serato feature forum through mid-2026:

**Duplicates inside Serato.** No built-in finder. The manual method is open All, sort by song or file name, show bitrate, length, and location, and delete the loser. People want the copy with cues and the higher bitrate kept, and the deleted copy's crate membership moved onto it.

**Smarter smart crates.**

- Duplicate a smart crate, then change one rule. Today the workaround is to nest them, copy the files in `SmartCrates`, and rename the parent prefix in the filename.
- Add or remove one rule across many smart crates at once.
- Nested AND/OR. Serato only has match-all or match-any.
- A rule for "in this crate" or "in no crate".
- An inbox: not in any crate, not hot-cued, or grid not checked. People fake this by putting `needs grid` in the title, or a symbol in comments, and building a smart crate on that.
- Smart crates still do not include streaming tracks (forum request, May 2026), even though ordinary crates can.

**Folder sync.** Mark any folder as auto-import and keep the crate matched when files are added or removed. Asked for about fifteen years. CrateSync is the third-party answer. Serato's own advice is still: keep one music folder, drag folders in once, and drag again to pick up new files. Previously imported songs are not duplicated by that drag.

**Export.**

- Crate to M3U/M3U8. Import returned in 5.0. Export of an existing crate is still requested. Session export exists and is a worse fit for people who organize in crates.
- Copy a crate's files into a folder for a car, a CDJ stick, or another machine. Serato can already do this by dragging the crate onto a destination in the Files panel. Most people do not know that.

**CDJ / standalone USB export.** The loudest remaining request (Serato forum, July 2026): write a USB with cues, loops, and grids that plays on Pioneer CDJs and all-in-ones (Opus Quad and similar) without a laptop. The practical path is still Lexicon, DJCU2, or `serato2rekordbox`. An AI "energy / BPM / sub-genre" organizer was attached to the same request. Nothing in Serato does that. Comment conventions and third-party smart crates are the workaround.

**Two computers.** Copying music with Dropbox is fine. Live-syncing the open database is how libraries break. Lexicon's pattern is one library, path mappings, then sync out to whatever app each machine runs.

**Missing files.** Orange means the stored path does not resolve: moved, renamed, deleted, or the drive is unplugged. Built-in fix: no hardware connected, Files panel, drag the drive or folder onto Relocate Lost Files. People want rename-aware matching with a confidence score, and they want this done before any duplicate pass.

**Metadata at scale.** Genre spelling (`Hip-Hop` vs `Hip Hop` vs `hip hop rap`), energy as a real column rather than emoji or comment hacks, notes that are not the comments field, and column filters (Lexicon lets you double-click a header to search that field). Serato has comments, grouping, and emoji ratings. It does not have bulk tag editing.

**Merging two libraries.** Serato's support article is a long manual procedure: relocate, dump All into a named crate, rename `_Serato_` out of the way, repeat, then rescan ID3 tags and relocate again. Easy to get wrong.

**Smaller library UI requests** that still come up: side-by-side crates, or loading a second crate into the Prepare area; dragging more than one crate at a time; a track count on All Audio; waveform previews in the list; half-time and double-time BPM for sync.

## How a cleanup is usually done

Order matters more than the tool.

1. Quit Serato. Copy `_Serato_` and, on Serato 4/5, the `Library` folder.
2. Fix orange missing files, or remove the ones whose files are gone.
3. Remove duplicates, keeping the copy with cues and the better file, and keeping crate membership.
4. Delete empty crates and merge near-duplicates. Broad crates for working categories, subcrates for context, smart crates for rules.
5. Re-analyze tracks whose BPM or key is wrong. In 5.0, Lucid beatgrids are a separate re-analysis and do not overwrite the old grid until you run it.
6. Only then repair a database that is actually corrupt: crash on launch, hang on the library, empty crates, analysis restarting forever.

On Serato 4/5, restore `master.sqlite` from `Library/Backups`. Move the current `master.sqlite` and the `master.sqlite*` sidecar files out first. Cues and grids are still in the audio files if the database is the only thing that broke.

Corrupt-database symptoms and the backup restore path are documented by Crate Cleaner from Serato's own layout: https://cratecleaner.com/guides/fix-corrupt-serato-database/ and https://cratecleaner.com/guides/serato-folder-explained/

Official organization guide: https://support.serato.com/hc/en-us/articles/202538530-The-Most-Professional-Way-to-Organize-and-Manage-your-Music-Library-with-Serato-DJ

Merging libraries: https://support.serato.com/hc/en-us/articles/219871867-Merging-Two-or-more-Serato-Folders

## What is worth building next to a read-only browser

This app already reads the right file. The gaps Serato 5 still does not cover, and that third-party tools charge for, are:

- Duplicate groups that respect cues and crate membership.
- Rename-aware missing-file relink.
- Smart-crate rule editing, including clone and bulk rule changes.
- Folder-to-crate sync.
- Export to M3U or Rekordbox XML, including cues and the first beat of the grid.

Lexicon and MLT already cover the first two on Serato 4. The open-source hole is a careful writer for `root.sqlite`. `serato-dj-mcp` only inserts new crates. Everything else still speaks `database V2`. Any write has to happen with Serato quit, against a backup, and should prefer `root.sqlite` so Serato's own startup aggregation rebuilds `master.sqlite`.

## Source list

Serato

- Serato DJ 4 library announcement: https://the-drop.serato.com/announcements/serato-dj-new-library-beta/
- Serato DJ 4 write-up: https://wearecrossfader.co.uk/blog/serato-dj-4-0/
- Serato DJ 5.0: https://the-drop.serato.com/announcements/lucid-beatgrids-just-dropped-in-the-serato-dj-5-0-beta/
- Organize a library: https://support.serato.com/hc/en-us/articles/202538530-The-Most-Professional-Way-to-Organize-and-Manage-your-Music-Library-with-Serato-DJ
- Merge `_Serato_` folders: https://support.serato.com/hc/en-us/articles/219871867-Merging-Two-or-more-Serato-Folders
- Feature request, CDJ USB export and AI library sorting (24 July 2026): https://serato.com/forum/discussion/2115901
- M3U request thread, and CrateSync 2.0: https://serato.com/forum/discussion/2108487
- CrateSync announcement: https://serato.com/forum/discussion/2107047
- Smart crates still exclude streaming (9 May 2026): https://serato.com/forum/discussion/2102410

Tools

- Lexicon vs Mixo (vendor): https://www.lexicondj.com/lexicon-vs-mixo
- Lexicon Serato sync manual: https://www.lexicondj.com/manual/sync-serato
- Lexicon 1.10 / Serato 4: https://www.digitaldjtips.com/lexicon-1-10-brings-serato-4-0-support-track-timeline-play-history/
- Mixo vs Lexicon (June 2026, The DJ Mixtape): https://thedjmixtape.com/mixo-vs-lexicon/
- MIXO import: https://www.mixo.dj/guides/serato-to-mixo
- MIXO export: https://www.mixo.dj/guides/mixo-to-serato
- Crate Cleaner comparison (vendor, September 2026): https://cratecleaner.com/compare/best-serato-library-software/
- Music Library Tools: https://musiclibrarytools.co.uk/
- Music Library Doctor buyer's guide (vendor, May 2026): https://musiclibrarydoctor.com/best-dj-library-tool-2026.html
- DJ Cue Bridge: https://djcuebridge.com/
- Mixgraph crate reader: https://www.mixgraph.io/tools/serato-crate-reader

Community requests

- How would you improve Serato? (February 2025): https://www.reddit.com/r/Serato/comments/1in2fl7/how_would_you_improve_serato/
- Library management requests (May 2025): https://www.reddit.com/r/Serato/comments/1kz8ztn/library_management_update_we_need_it/
- Duplicate smart crates (April 2026): https://www.reddit.com/r/Serato/comments/1sfbpe8/create_duplicate_smart_crates/
- M3U removed in Serato 4 (December 2025): https://www.reddit.com/r/Serato/comments/1q0nv79/missing_items_on_the_serato_update

Code

- https://github.com/bvandrc/serato-tools
- https://github.com/Venut-Technologies/serato-dj-mcp
- https://github.com/chrisle/serato-connect
- https://github.com/laker-93/pyserato
- https://github.com/SpinTools/seratoparser
- https://github.com/adammillerio/cratedigger
- https://github.com/jesseward/Serato-lib
- https://github.com/Holzhaus/serato-tags
- https://github.com/BytePhoenixCoding/serato2rekordbox
- https://github.com/MartinHH/cratetom3u
- https://github.com/xxvw/rekordbox-serato-bridge
