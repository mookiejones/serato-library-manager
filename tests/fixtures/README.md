# Serato format fixtures

Tiny libraries for tests. They are built by `tests/fixtures/build_fixtures.py`
from the published Serato notes, not from this repository's tag code.

Regenerate with:

```bash
python3 tests/fixtures/build_fixtures.py
```

Serato 4 entries are `spec-derived` (the Scratch Live compatibility export).
Serato 5 entries are `spec-derived, unverified`. Lucid/Flexible beatgrids and
Protect Library are omitted because their storage is unknown until Byte Beat's
`serato5-probe.sh` runs on a real Serato 5 install.

| Tree | File | Status | Citation |
| --- | --- | --- | --- |
| `serato4` | `_Serato_/database V2` | spec-derived | https://github.com/Holzhaus/mixxx/wiki/Serato-Database-Format (record header, vrsn, otrk, pfil/ptrk as UTF-16BE) and https://github.com/Holzhaus/serato-tags/blob/master/scripts/database_v2.py (field names ttyp, tsng, tart, tbpm, bmis). |
| `serato4` | `_Serato_/Subcrates/House.crate` | spec-derived | https://github.com/Holzhaus/mixxx/wiki/Serato-Database-Format (vrsn '1.0/Serato ScratchLive Crate', otrk/ptrk; the crate name is the filename, not a record). Nested crates join parent and child with %% in the filename. |
| `serato4` | `_Serato_/Subcrates/House%%Café.crate` | spec-derived | https://github.com/Holzhaus/mixxx/wiki/Serato-Database-Format (vrsn '1.0/Serato ScratchLive Crate', otrk/ptrk; the crate name is the filename, not a record). Nested crates join parent and child with %% in the filename. |
| `serato4` | `_Serato_/Subcrates/Empty.crate` | spec-derived | https://github.com/Holzhaus/mixxx/wiki/Serato-Database-Format (vrsn '1.0/Serato ScratchLive Crate', otrk/ptrk; the crate name is the filename, not a record). Nested crates join parent and child with %% in the filename. |
| `serato4` | `drives/UNMOUNTED/_Serato_/Subcrates/Gig.crate` | spec-derived | https://github.com/Holzhaus/mixxx/wiki/Serato-Database-Format (vrsn '1.0/Serato ScratchLive Crate', otrk/ptrk; the crate name is the filename, not a record). Nested crates join parent and child with %% in the filename. |
| `serato4` | `drives/UNMOUNTED/_Serato_/database V2` | spec-derived | https://github.com/Holzhaus/mixxx/wiki/Serato-Database-Format (record header, vrsn, otrk, pfil/ptrk as UTF-16BE) and https://github.com/Holzhaus/serato-tags/blob/master/scripts/database_v2.py (field names ttyp, tsng, tart, tbpm, bmis). |
| `serato4` | `audio/one-grid.mp3` | spec-derived | https://github.com/Holzhaus/serato-tags/blob/main/docs/fileformats.md section 'MP3 and AIFF' (ID3v2.4 GEOB Serato Markers2 and Serato BeatGrid). https://github.com/Holzhaus/serato-tags/blob/main/docs/serato_markers2.md (header, base64 and null padding, CUE, LOOP, FLIP, COLOR, BPMLOCK entries). https://github.com/Holzhaus/serato-tags/blob/main/docs/serato_beatgrid.md (version byte 1, non-terminal beats-until-next, terminal BPM, one-byte footer). |
| `serato4` | `audio/several-grid.aiff` | spec-derived | https://github.com/Holzhaus/serato-tags/blob/main/docs/fileformats.md section 'MP3 and AIFF' (ID3v2.4 GEOB inside an AIFF ID3 chunk). https://github.com/Holzhaus/serato-tags/blob/main/docs/serato_markers2.md (header, base64 and null padding, CUE, LOOP, FLIP, COLOR, BPMLOCK entries). https://github.com/Holzhaus/serato-tags/blob/main/docs/serato_beatgrid.md (version byte 1, non-terminal beats-until-next, terminal BPM, one-byte footer). |
| `serato4` | `audio/one-grid.flac` | spec-derived | https://github.com/Holzhaus/serato-tags/blob/main/docs/fileformats.md section 'FLAC' (VORBIS_COMMENT SERATO_MARKERS_V2 and SERATO_BEATGRID, base64 without padding, linefeed every 72 characters, application/octet-stream envelope). https://github.com/Holzhaus/serato-tags/blob/main/docs/serato_markers2.md (header, base64 and null padding, CUE, LOOP, FLIP, COLOR, BPMLOCK entries). https://github.com/Holzhaus/serato-tags/blob/main/docs/serato_beatgrid.md (version byte 1, non-terminal beats-until-next, terminal BPM, one-byte footer). |
| `serato4` | `audio/several-grid.m4a` | spec-derived | https://github.com/Holzhaus/serato-tags/blob/main/docs/fileformats.md section 'MP4/M4A' (---- atoms, mean com.serato.dj, names markersv2 and beatgrid; markersv2 has linefeeds every 72 characters, beatgrid does not). https://github.com/Holzhaus/serato-tags/blob/main/docs/serato_markers2.md (header, base64 and null padding, CUE, LOOP, FLIP, COLOR, BPMLOCK entries). https://github.com/Holzhaus/serato-tags/blob/main/docs/serato_beatgrid.md (version byte 1, non-terminal beats-until-next, terminal BPM, one-byte footer). |
| `serato4` | `edge/truncated.crate` | spec-derived | https://github.com/Holzhaus/mixxx/wiki/Serato-Database-Format (vrsn '1.0/Serato ScratchLive Crate', otrk/ptrk; the crate name is the filename, not a record). Nested crates join parent and child with %% in the filename. |
| `serato4` | `edge/truncated-tags.mp3` | spec-derived | https://github.com/Holzhaus/serato-tags/blob/main/docs/fileformats.md section 'MP3 and AIFF' (ID3v2.4 GEOB Serato Markers2 and Serato BeatGrid). |
| `serato4` | `edge/cut-header.mp3` | spec-derived | https://github.com/Holzhaus/serato-tags/blob/main/docs/fileformats.md section 'MP3 and AIFF' (ID3v2.4 GEOB Serato Markers2 and Serato BeatGrid). |
| `serato5` | `_Serato_/database V2` | spec-derived, unverified | https://github.com/Holzhaus/mixxx/wiki/Serato-Database-Format (record header, vrsn, otrk, pfil/ptrk as UTF-16BE) and https://github.com/Holzhaus/serato-tags/blob/master/scripts/database_v2.py (field names ttyp, tsng, tart, tbpm, bmis). |
| `serato5` | `_Serato_/Subcrates/House.crate` | spec-derived, unverified | https://github.com/Holzhaus/mixxx/wiki/Serato-Database-Format (vrsn '1.0/Serato ScratchLive Crate', otrk/ptrk; the crate name is the filename, not a record). Nested crates join parent and child with %% in the filename. |
| `serato5` | `_Serato_/Subcrates/House%%深夜.crate` | spec-derived, unverified | https://github.com/Holzhaus/mixxx/wiki/Serato-Database-Format (vrsn '1.0/Serato ScratchLive Crate', otrk/ptrk; the crate name is the filename, not a record). Nested crates join parent and child with %% in the filename. |
| `serato5` | `_Serato_/Subcrates/Empty.crate` | spec-derived, unverified | https://github.com/Holzhaus/mixxx/wiki/Serato-Database-Format (vrsn '1.0/Serato ScratchLive Crate', otrk/ptrk; the crate name is the filename, not a record). Nested crates join parent and child with %% in the filename. |
| `serato5` | `drives/UNMOUNTED/_Serato_/Subcrates/Gig.crate` | spec-derived, unverified | https://github.com/Holzhaus/mixxx/wiki/Serato-Database-Format (vrsn '1.0/Serato ScratchLive Crate', otrk/ptrk; the crate name is the filename, not a record). Nested crates join parent and child with %% in the filename. |
| `serato5` | `drives/UNMOUNTED/_Serato_/database V2` | spec-derived, unverified | https://github.com/Holzhaus/mixxx/wiki/Serato-Database-Format (record header, vrsn, otrk, pfil/ptrk as UTF-16BE) and https://github.com/Holzhaus/serato-tags/blob/master/scripts/database_v2.py (field names ttyp, tsng, tart, tbpm, bmis). |
| `serato5` | `audio/tempo.mp3` | spec-derived, unverified | https://github.com/Holzhaus/serato-tags/blob/main/docs/fileformats.md section 'MP3 and AIFF' (ID3v2.4 GEOB Serato Markers2 and Serato BeatGrid). https://github.com/Holzhaus/serato-tags/blob/main/docs/serato_markers2.md (header, base64 and null padding, CUE, LOOP, FLIP, COLOR, BPMLOCK entries). https://github.com/Holzhaus/serato-tags/blob/main/docs/serato_beatgrid.md (version byte 1, non-terminal beats-until-next, terminal BPM, one-byte footer). |
| `serato5` | `audio/downbeat.aiff` | spec-derived, unverified | https://github.com/Holzhaus/serato-tags/blob/main/docs/fileformats.md section 'MP3 and AIFF' (ID3v2.4 GEOB inside an AIFF ID3 chunk). https://github.com/Holzhaus/serato-tags/blob/main/docs/serato_markers2.md (header, base64 and null padding, CUE, LOOP, FLIP, COLOR, BPMLOCK entries). https://github.com/Holzhaus/serato-tags/blob/main/docs/serato_beatgrid.md (version byte 1, non-terminal beats-until-next, terminal BPM, one-byte footer). |
| `serato5` | `audio/shifts.flac` | spec-derived, unverified | https://github.com/Holzhaus/serato-tags/blob/main/docs/fileformats.md section 'FLAC' (VORBIS_COMMENT SERATO_MARKERS_V2 and SERATO_BEATGRID, base64 without padding, linefeed every 72 characters, application/octet-stream envelope). https://github.com/Holzhaus/serato-tags/blob/main/docs/serato_markers2.md (header, base64 and null padding, CUE, LOOP, FLIP, COLOR, BPMLOCK entries). https://github.com/Holzhaus/serato-tags/blob/main/docs/serato_beatgrid.md (version byte 1, non-terminal beats-until-next, terminal BPM, one-byte footer). |
| `serato5` | `audio/anchor.m4a` | spec-derived, unverified | https://github.com/Holzhaus/serato-tags/blob/main/docs/fileformats.md section 'MP4/M4A' (---- atoms, mean com.serato.dj, names markersv2 and beatgrid; markersv2 has linefeeds every 72 characters, beatgrid does not). https://github.com/Holzhaus/serato-tags/blob/main/docs/serato_markers2.md (header, base64 and null padding, CUE, LOOP, FLIP, COLOR, BPMLOCK entries). https://github.com/Holzhaus/serato-tags/blob/main/docs/serato_beatgrid.md (version byte 1, non-terminal beats-until-next, terminal BPM, one-byte footer). |
| `serato5` | `edge/truncated.crate` | spec-derived, unverified | https://github.com/Holzhaus/mixxx/wiki/Serato-Database-Format (vrsn '1.0/Serato ScratchLive Crate', otrk/ptrk; the crate name is the filename, not a record). Nested crates join parent and child with %% in the filename. |
| `serato5` | `edge/truncated-tags.mp3` | spec-derived, unverified | https://github.com/Holzhaus/serato-tags/blob/main/docs/fileformats.md section 'MP3 and AIFF' (ID3v2.4 GEOB Serato Markers2 and Serato BeatGrid). |
| `serato5` | `edge/cut-header.mp3` | spec-derived, unverified | https://github.com/Holzhaus/serato-tags/blob/main/docs/fileformats.md section 'MP3 and AIFF' (ID3v2.4 GEOB Serato Markers2 and Serato BeatGrid). |

## Notes

- `database V2` and `.crate` files are the legacy chunk format: a 4-byte tag,
  a big-endian length, and UTF-16BE text for `vrsn`, `pfil`, and `ptrk`.
- A nested crate is a second file. Parents and the leaf are joined with `%%`.
- Markers2 and BeatGrid inside MP3 and AIFF are ID3v2.4 GEOB frames.
- FLAC stores the same payloads as base64 Vorbis comments.
- M4A stores them as `----` atoms with mean `com.serato.dj`.
- `edge/truncated.crate` and `edge/truncated-tags.mp3` are cut on purpose.
- `edge/cut-header.mp3` is an ID3 header that stops early.
- `drives/UNMOUNTED` is a crate for a volume the tests do not mount.
- `drive_check/GIGDRIVE` is a portable drive for the read-only drive check.
  Unsafe FAT names are inside the crate bytes, not file names.
