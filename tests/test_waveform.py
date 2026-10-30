"""Waveform bands, cache, access checks, Serato Overview, and markers.

The audio is generated here or copied from the synthetic Serato fixtures.
Nothing reads a person's library, and nothing is written into one.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import math
import os
import struct
import tempfile
import threading
import unittest
import urllib.parse
import wave
from pathlib import Path
from unittest import mock

import numpy as np

import app_config
import audio_stream
import server
import tags
import waveform
from tests.fixture import ROOT, TempLibrary, open_database

FIXTURES = ROOT / "tests" / "fixtures"
from tests.test_tags import _freeform, _serato_b64, _write_flac, _write_m4a

SECRET = b"NOT-IN-LIBRARY-SECRET"
_RATE = 44100


def _sine(freq: float, seconds: float, rate: int = _RATE) -> np.ndarray:
    """Build a unit sine.

    Args:
        freq: Frequency in Hz.
        seconds: Duration.
        rate: Sample rate.

    Returns:
        Mono samples. No file is written.
    """
    count = int(rate * seconds)
    times = np.arange(count) / rate
    return np.sin(2 * math.pi * freq * times)


def _write_wav(path: Path, samples: np.ndarray, rate: int = _RATE) -> None:
    """Write 16-bit mono PCM.

    Args:
        path: File to replace.
        samples: Mono samples in -1 to 1.
        rate: Sample rate.

    Returns:
        None.
    """
    frames = np.clip(np.rint(samples * 32767.0), -32768, 32767).astype("<i2")
    with wave.open(os.fspath(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(frames.tobytes())


def _write_aiff(path: Path, samples: np.ndarray, rate: int = _RATE) -> None:
    """Write a 16-bit mono AIFF.

    Args:
        path: File to replace.
        samples: Mono samples in -1 to 1.
        rate: Sample rate.

    Returns:
        None.
    """
    frames = np.clip(np.rint(samples * 32767.0), -32768, 32767).astype(">i2").tobytes()

    def chunk(tag: bytes, data: bytes) -> bytes:
        pad = b"\x00" if len(data) % 2 else b""
        return tag + struct.pack(">I", len(data)) + data + pad

    exponent = int(math.floor(math.log2(rate)))
    mantissa = int(rate / (2 ** exponent) * (1 << 63))
    sample_rate = struct.pack(">H", 16383 + exponent) + struct.pack(">Q", mantissa)
    comm = struct.pack(">H", 1) + struct.pack(">I", len(samples)) + struct.pack(">H", 16) + sample_rate
    ssnd = struct.pack(">II", 0, 0) + frames
    body = chunk(b"COMM", comm) + chunk(b"SSND", ssnd)
    path.write_bytes(b"FORM" + struct.pack(">I", 4 + len(body)) + b"AIFF" + body)


def _overview_columns() -> bytes:
    """Return two known 16-byte overview columns.

    Returns:
        32 bytes. No file is written.
    """
    return bytes(range(16)) + bytes(range(16, 32))


def _id3_overview(path: Path, payload: bytes) -> None:
    """Write an ID3v2.3 file whose only frame is Serato Overview.

    Args:
        path: File to replace.
        payload: Overview bytes stored in the GEOB frame.

    Returns:
        None.
    """
    description = b"Serato Overview\x00"
    body = bytes([0]) + b"application/octet-stream\x00" + b"\x00" + description + payload
    frame = b"GEOB" + len(body).to_bytes(4, "big") + b"\x00\x00" + body
    size = len(frame)
    synchsafe = bytes(
        (
            (size >> 21) & 0x7F,
            (size >> 14) & 0x7F,
            (size >> 7) & 0x7F,
            size & 0x7F,
        )
    )
    path.write_bytes(b"ID3" + bytes([3, 0, 0]) + synchsafe + frame)


def _ogg_overview(path: Path, value: bytes) -> None:
    """Write a two-packet Ogg file whose comment is ``serato_overview``.

    Args:
        path: File to replace.
        value: Comment value. It is not an audio packet.

    Returns:
        None.
    """
    vendor = b"qa"
    comment = b"serato_overview=" + value
    block = struct.pack("<I", len(vendor)) + vendor
    block += struct.pack("<I", 1) + struct.pack("<I", len(comment)) + comment
    packets = [b"\x01vorbis" + bytes(16), b"\x03vorbis" + block + b"\x01"]
    segments = bytes(len(packet) for packet in packets)
    data = b"".join(packets)
    header = bytearray(27)
    header[0:4] = b"OggS"
    header[26] = len(segments)
    path.write_bytes(bytes(header) + segments + data)


def _middle_means(body: bytes) -> np.ndarray:
    """Average the middle half of the detail points.

    Args:
        body: An ``SWF1`` body.

    Returns:
        Six means: low peak, low RMS, mid peak, mid RMS, high peak, high RMS.
    """
    parsed = waveform.parse_waveform(body)
    detail = np.frombuffer(parsed["detail"], dtype=np.uint8).reshape(-1, 6)
    start = len(detail) // 4
    stop = (3 * len(detail)) // 4
    return detail[start:stop].mean(axis=0)


class BandTests(unittest.TestCase):
    """Split synthetic sines without opening a library."""

    def test_sines_land_in_the_matching_band(self) -> None:
        """Put 60 Hz in low, 1 kHz in mid, and 10 kHz in high.

        Each tone is two seconds at 44100 Hz. The middle of the detail
        track is scored so the filter startup does not decide the result.
        No file is written.

        Returns:
            None. The test fails when a tone is not mostly one band.
        """
        expected = {60.0: 0, 1000.0: 2, 10000.0: 4}
        for freq, peak_index in expected.items():
            with self.subTest(freq=freq):
                body = waveform.analyze_samples(_sine(freq, 2.0), _RATE)
                parsed = waveform.parse_waveform(body)
                self.assertEqual(parsed["detail_count"], 300)
                self.assertEqual(parsed["overview_count"], 300)
                means = _middle_means(body)
                others = [index for index in (0, 2, 4) if index != peak_index]
                self.assertGreater(means[peak_index], 200)
                self.assertGreater(means[peak_index], means[others[0]] + means[others[1]])
                self.assertLess(means[others[0]], 20)
                self.assertLess(means[others[1]], 20)

    def test_long_track_overview_is_1000_points(self) -> None:
        """Bucket eight seconds of detail into 1000 overview points.

        Eight seconds is 1200 detail points at 150 per second. A shorter
        track keeps one overview point per detail point.

        Returns:
            None. The test fails if the overview is upsampled or left at 1200.
        """
        body = waveform.analyze_samples(_sine(1000.0, 8.0), _RATE)
        parsed = waveform.parse_waveform(body)
        self.assertEqual(parsed["detail_count"], 1200)
        self.assertEqual(parsed["overview_count"], 1000)
        self.assertEqual(parsed["detail_hz_milli"], 150000)
        self.assertEqual(len(parsed["detail"]), 1200 * 6)
        self.assertEqual(len(parsed["overview"]), 1000 * 6)

    def test_chunks_match_one_buffer(self) -> None:
        """Filter a generator of chunks the same way as one buffer.

        The generator yields 2048 samples at a time. Joining them first
        would still pass a byte compare, so this checks the streamed FIR
        state against the single-buffer result.

        Returns:
            None. The test fails if a chunk boundary changes a detail byte.
        """
        samples = _sine(60.0, 2.0)

        def chunks():
            for start in range(0, len(samples), 2048):
                yield samples[start:start + 2048]

        rows, total = waveform._collect(chunks())
        streamed = waveform._pack(rows, total, None)
        whole = waveform.analyze_samples(samples, _RATE)
        self.assertEqual(waveform.parse_waveform(streamed)["detail"], waveform.parse_waveform(whole)["detail"])

    def test_overview_columns_are_appended(self) -> None:
        """Store the Serato Overview columns after the computed overview.

        The tag bytes are passed in. No container is opened.

        Returns:
            None. The test fails if the columns move or the version bytes are kept.
        """
        columns = _overview_columns()
        payload = bytes((1, 5)) + columns
        body = waveform.analyze_samples(_sine(1000.0, 0.5), _RATE, overview=payload)
        parsed = waveform.parse_waveform(body)
        self.assertEqual(parsed["serato_columns"], 2)
        self.assertEqual(parsed["serato_bands"], 16)
        self.assertEqual(parsed["serato"], columns)
        self.assertEqual(parsed["flags"] & 4, 4)


class DecoderTests(unittest.TestCase):
    """Check which formats need ffmpeg, using generated PCM."""

    def test_ffmpeg_is_required_only_for_aac_family(self) -> None:
        """Name the suffixes miniaudio does not decode.

        A generated AIFF is not in that set. No library file is opened.

        Returns:
            None. The test fails if AIFF is treated as ffmpeg-only.
        """
        self.assertEqual(waveform.FFMPEG_REQUIRED_SUFFIXES, frozenset({".m4a", ".aac", ".alac"}))
        self.assertNotIn(".aiff", waveform.FFMPEG_REQUIRED_SUFFIXES)
        self.assertNotIn(".aif", waveform.FFMPEG_REQUIRED_SUFFIXES)

    def test_wav_falls_back_when_miniaudio_refuses(self) -> None:
        """Decode a WAV with the stdlib when miniaudio raises.

        ``ffmpeg`` is reported missing so the fallback cannot be the
        external program. The file is a temporary sine, not a library file.

        Returns:
            None. The test fails if the WAV is reported unavailable.
        """
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "tone.wav"
            _write_wav(path, _sine(440.0, 0.5))
            with mock.patch("waveform.miniaudio.stream_file", side_effect=RuntimeError("no")):
                with mock.patch("waveform.shutil.which", return_value=None):
                    body, _cached = waveform.load(path)
        parsed = waveform.parse_waveform(body)
        self.assertEqual(parsed["detail_count"], 75)
        self.assertGreater(_middle_means(body)[2], 100)

    def test_aiff_falls_back_without_ffmpeg(self) -> None:
        """Decode a generated AIFF when miniaudio and ffmpeg are both absent.

        The pure-Python reader is the one that has to succeed. The file
        is temporary.

        Returns:
            None. The test fails if AIFF is reported unavailable.
        """
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "tone.aiff"
            _write_aiff(path, _sine(440.0, 0.5))
            with mock.patch("waveform.miniaudio.stream_file", side_effect=RuntimeError("no")):
                with mock.patch("waveform.shutil.which", return_value=None):
                    body, _cached = waveform.load(path)
        self.assertEqual(waveform.parse_waveform(body)["detail_count"], 75)

    def test_m4a_without_ffmpeg_is_unavailable(self) -> None:
        """Return the stable sentence when ffmpeg is not on PATH.

        The file is a few bytes with an ``.m4a`` name. ``Popen`` is not called.

        Returns:
            None. The test fails if a waveform body is produced.
        """
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "song.m4a"
            path.write_bytes(b"not-audio")
            with mock.patch("waveform.shutil.which", return_value=None):
                with mock.patch("waveform.subprocess.Popen") as popen:
                    with self.assertRaises(waveform.WaveformUnavailable) as caught:
                        waveform.load(path)
        self.assertEqual(caught.exception.message, "waveform unavailable")
        popen.assert_not_called()

    def test_ffmpeg_on_path_decodes_m4a(self) -> None:
        """Use ffmpeg only as an argv list when ``which`` finds it.

        The process is fake. Its stdout is one float32 sine. The command
        is not a shell string, and it does not name an output file.

        Returns:
            None. The test fails if ffmpeg is launched through the shell.
        """
        samples = _sine(1000.0, 0.5).astype("<f4")

        class _Stdout:
            def __init__(self, payload: bytes) -> None:
                self._payload = payload
                self._at = 0

            def read(self, count: int) -> bytes:
                piece = self._payload[self._at:self._at + count]
                self._at += count
                return piece

            def close(self) -> None:
                return None

        class _Process:
            def __init__(self) -> None:
                self.stdout = _Stdout(samples.tobytes())

            def wait(self, timeout: int | None = None) -> int:
                del timeout
                return 0

            def kill(self) -> None:
                return None

        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "song.m4a"
            path.write_bytes(b"container")
            with mock.patch("waveform.shutil.which", return_value="/usr/bin/ffmpeg"):
                with mock.patch("waveform.subprocess.Popen", return_value=_Process()) as popen:
                    body, _cached = waveform.load(path)
        command = popen.call_args.args[0]
        self.assertEqual(command[0], "/usr/bin/ffmpeg")
        self.assertIn("-f", command)
        self.assertIn("f32le", command)
        self.assertNotIn("-y", command)
        self.assertIs(popen.call_args.kwargs.get("shell", False), False)
        self.assertEqual(waveform.parse_waveform(body)["detail_count"], 75)
        self.assertGreater(_middle_means(body)[2], 100)


class CacheTests(unittest.TestCase):
    """Store waveforms beside settings, never inside the library folder."""

    def test_key_tracks_size_mtime_and_version(self) -> None:
        """Change the digest when size, mtime, or the analyzer version changes.

        On Windows the same path in another case is the same key. No file
        is written.

        Returns:
            None. The test fails if two different files share a key.
        """
        path = Path(r"C:\Music\Tune.wav")
        base = waveform.cache_key(path, 10, 20, 1)
        self.assertNotEqual(base, waveform.cache_key(path, 11, 20, 1))
        self.assertNotEqual(base, waveform.cache_key(path, 10, 21, 1))
        self.assertNotEqual(base, waveform.cache_key(path, 10, 20, 2))
        if os.name == "nt":
            folded = waveform.cache_key(Path(r"c:\music\tune.wav"), 10, 20, 1)
            self.assertEqual(base, folded)

    def test_hit_then_invalidate_on_mtime_size_and_version(self) -> None:
        """Decode once, then again only when the key changes.

        The second load is a hit. Moving mtime, changing size while
        putting that mtime back, and bumping the analyzer version each
        miss. The audio bytes are not rewritten by the cache.

        Returns:
            None. The test fails if a hit decodes again, or a change does not.
        """
        calls = {"n": 0}
        real = waveform.iter_pcm

        def wrapped(path: Path):
            calls["n"] += 1
            return real(path)

        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "tone.wav"
            _write_wav(path, _sine(440.0, 0.5))
            before = path.read_bytes()
            with mock.patch("waveform.iter_pcm", wrapped):
                first, cached_first = waveform.load(path)
                second, cached_second = waveform.load(path)
                self.assertFalse(cached_first)
                self.assertTrue(cached_second)
                self.assertEqual(first, second)
                self.assertEqual(calls["n"], 1)
                stamped = path.stat().st_mtime_ns + 1_000_000_000
                os.utime(path, ns=(path.stat().st_atime_ns, stamped))
                _third, cached_third = waveform.load(path)
                self.assertFalse(cached_third)
                self.assertEqual(calls["n"], 2)
                _write_wav(path, _sine(440.0, 1.0))
                os.utime(path, ns=(path.stat().st_atime_ns, stamped))
                _fourth, cached_fourth = waveform.load(path)
                self.assertFalse(cached_fourth)
                self.assertEqual(calls["n"], 3)
                with mock.patch.object(waveform, "ANALYZER_VERSION", waveform.ANALYZER_VERSION + 1):
                    _fifth, cached_fifth = waveform.load(path)
                self.assertFalse(cached_fifth)
                self.assertEqual(calls["n"], 4)
            self.assertNotEqual(path.read_bytes(), before)
            cache_root = app_config.config_dir() / "waveforms"
            self.assertTrue(cache_root.is_dir())
            self.assertFalse(str(cache_root).startswith(str(Path(raw))))

    def test_cache_refuses_the_library_folder(self) -> None:
        """Skip the cache when the app data directory is the library folder.

        The waveform is still returned. ``waveforms/`` is not created next
        to ``master.sqlite``.

        Returns:
            None. The test fails if a cache file appears in the library tree.
        """
        with TempLibrary() as temp:
            path = temp.root / "music" / "tone.wav"
            path.parent.mkdir()
            _write_wav(path, _sine(440.0, 0.5))
            before = _tree(temp.root)
            with mock.patch.dict(os.environ, {"SERATO_LIBRARY_CONFIG_DIR": str(temp.root.resolve())}):
                body, cached = waveform.load(path)
            self.assertFalse(cached)
            self.assertTrue(body.startswith(b"SWF1"))
            self.assertEqual(_tree(temp.root), before)
            self.assertFalse((temp.root / "waveforms").exists())


class OverviewTests(unittest.TestCase):
    """Read Serato Overview from ID3, FLAC, MP4, and Ogg fixtures."""

    def test_overview_columns_from_each_container(self) -> None:
        """Read the same two columns from each container Serato uses.

        The ID3 payload has one trailing byte so a partial column is
        dropped. The Ogg value is the hex layout with uint32 version
        words. Marker ``found`` stays false. No file is rewritten.

        Returns:
            None. The test fails if a container loses a column or sets ``found``.
        """
        columns = _overview_columns()
        payload = bytes((1, 5)) + columns + b"\x99"
        expected = bytes((1, 5)) + columns
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            id3 = root / "overview.mp3"
            flac = root / "overview.flac"
            m4a = root / "overview.m4a"
            ogg = root / "overview.ogg"
            _id3_overview(id3, payload)
            wrapped = _serato_b64("Serato Overview", payload, wrap=True)
            _write_flac(flac, [b"SERATO_OVERVIEW=" + wrapped])
            _write_m4a(m4a, _freeform("overview", wrapped, null_terminate=False))
            ogg_value = ((1).to_bytes(4, "big") + (5).to_bytes(4, "big") + columns).hex().encode("ascii")
            _ogg_overview(ogg, ogg_value)
            originals = {path: path.read_bytes() for path in (id3, flac, m4a, ogg)}
            for path in (id3, flac, m4a, ogg):
                with self.subTest(path=path.name):
                    self.assertEqual(tags.read_serato_overview(str(path)), expected)
                    self.assertFalse(tags.read_serato_tags(str(path))["found"])
                    self.assertEqual(path.read_bytes(), originals[path])


class MarkerTests(unittest.TestCase):
    """Read loops and beatgrids from the synthetic Serato 4 and 5 fixtures."""

    def test_fixture_loops_and_beatgrid_are_computable(self) -> None:
        """Read a locked colored loop and a beatgrid from both fixture trees.

        Beat spacing is the gap to the next marker divided by ``beats``.
        After the last marker the spacing is 60 divided by BPM. The files
        are the committed fixtures and are not rewritten.

        Returns:
            None. The test fails if a loop color, lock, or beat time moves.
        """
        cases = (
            (FIXTURES / "serato4" / "audio" / "several-grid.aiff", 174.0),
            (FIXTURES / "serato5" / "audio" / "tempo.mp3", None),
        )
        for path, bpm in cases:
            with self.subTest(path=path.name):
                before = path.read_bytes()
                parsed = tags.read_serato_tags(str(path))
                loop = parsed["loops"][0]
                self.assertEqual(loop["color"], "#27AAE1")
                self.assertTrue(loop["locked"])
                self.assertEqual(loop["start_ms"], 2000)
                self.assertEqual(loop["end_ms"], 8500)
                self.assertGreaterEqual(len(parsed["beatgrid"]), 1)
                if bpm is not None:
                    grid = parsed["beatgrid"]
                    spacing = (grid[1]["position"] - grid[0]["position"]) / grid[0]["beats"]
                    self.assertAlmostEqual(spacing, 0.5)
                    self.assertAlmostEqual(60.0 / grid[-1]["bpm"], 60.0 / bpm)
                self.assertEqual(path.read_bytes(), before)


class WaveformRouteTests(unittest.TestCase):
    """Serve waveforms for library ids and refuse every other selector."""

    def setUp(self) -> None:
        """Start a temporary library and an HTTP server on a free port.

        Returns:
            None.
        """
        self.library = TempLibrary()
        self.library.__enter__()
        self._next_id = 100
        self.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        """Stop the server and delete the temporary library.

        Returns:
            None.
        """
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=3)
        self.library.__exit__(None, None, None)

    def exchange(self, path: str) -> tuple[int, dict[str, str], bytes]:
        """Send one GET and return the status, headers, and body.

        Args:
            path: Absolute path and query.

        Returns:
            Status code, lower-cased header names, and the raw body.
        """
        host, port = self.httpd.server_address
        if isinstance(port, str):
            raise AssertionError("The test server did not bind a TCP port.")
        conn = http.client.HTTPConnection(str(host), port, timeout=10)
        try:
            conn.request("GET", path)
            response = conn.getresponse()
            body = response.read()
            headers = {key.lower(): value for key, value in response.getheaders()}
            return response.status, headers, body
        finally:
            conn.close()

    def add_track(self, relative: str, data: bytes) -> tuple[int, Path]:
        """Insert one asset whose file is ``data``.

        Args:
            relative: Path under the temporary library.
            data: File bytes.

        Returns:
            The asset id and the file path.
        """
        path = self.library.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        asset_id = self._next_id
        self._next_id += 1
        with open_database(self.library.db) as conn:
            conn.execute(
                """
                INSERT INTO asset
                    (id, name, artist, portable_id, file_name, is_missing, length_ms)
                VALUES (?, 'Tune', 'DJ', ?, ?, 0, 1000)
                """,
                (asset_id, str(path), path.name),
            )
            conn.execute(
                "INSERT INTO space_asset (id, asset_id, space_id) VALUES (?, ?, 1)",
                (asset_id, asset_id),
            )
        audio_stream.invalidate_index()
        return asset_id, path

    def insert_asset(self, path: Path) -> int:
        """Insert an asset row for a path that already exists.

        Args:
            path: Stored portable id.

        Returns:
            The new asset id.
        """
        asset_id = self._next_id
        self._next_id += 1
        with open_database(self.library.db) as conn:
            conn.execute(
                """
                INSERT INTO asset
                    (id, name, artist, portable_id, file_name, is_missing, length_ms)
                VALUES (?, 'Tune', 'DJ', ?, ?, 0, 1000)
                """,
                (asset_id, str(path), path.name),
            )
            conn.execute(
                "INSERT INTO space_asset (id, asset_id, space_id) VALUES (?, ?, 1)",
                (asset_id, asset_id),
            )
        audio_stream.invalidate_index()
        return asset_id

    def test_track_route_returns_loop_and_beat_times(self) -> None:
        """Return the fixture loop and a computable beatgrid from ``GET /api/track``.

        The file is a copy of the Serato 4 AIFF fixture. ``position_seconds``
        is the stored float. The copy and the fixture are unchanged.

        Returns:
            None. The test fails if the lock, color, or beat spacing is lost.
        """
        source = FIXTURES / "serato4" / "audio" / "several-grid.aiff"
        original = source.read_bytes()
        asset_id, copied = self.add_track("music/several-grid.aiff", original)
        status, _headers, body = self.exchange(f"/api/track?id={asset_id}")
        self.assertEqual(status, 200)
        payload = json.loads(body)
        loop = payload["loops"][0]
        self.assertEqual(loop["color"], "#27AAE1")
        self.assertTrue(loop["locked"])
        grid = payload["beatgrid"]
        spacing = (grid[1]["position_seconds"] - grid[0]["position_seconds"]) / grid[0]["beats"]
        self.assertAlmostEqual(spacing, 0.5)
        self.assertEqual(grid[0]["position"], "0.000")
        self.assertAlmostEqual(60.0 / grid[-1]["bpm"], 60.0 / 174.0)
        self.assertEqual(copied.read_bytes(), original)
        self.assertEqual(source.read_bytes(), original)

    def test_waveform_and_playback_for_an_undecodable_file(self) -> None:
        """Keep playback when the waveform route cannot decode.

        The asset is an ``.m4a`` of marker bytes. ffmpeg is hidden.
        ``GET /api/audio`` still returns those bytes. The waveform body
        is the unavailable JSON, not a stack trace.

        Returns:
            None. The test fails if playback changes or the sentence is missing.
        """
        payload = b"m4a-bytes-not-decodable"
        asset_id, path = self.add_track("music/song.m4a", payload)
        before = path.read_bytes()
        with mock.patch("waveform.shutil.which", return_value=None):
            status, headers, body = self.exchange(f"/api/waveform?id={asset_id}")
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"].split(";")[0], "application/json")
        self.assertEqual(json.loads(body), {"available": False, "error": "waveform unavailable"})
        audio_status, _audio_headers, audio_body = self.exchange(f"/api/audio?id={asset_id}")
        self.assertEqual(audio_status, 200)
        self.assertEqual(audio_body, payload)
        self.assertEqual(path.read_bytes(), before)

    def test_analysis_leaves_the_library_tree_unchanged(self) -> None:
        """Leave the temporary Serato folder byte-for-byte after a waveform.

        The cache is written under the app data directory. No Backups
        directory is created beside ``master.sqlite``.

        Returns:
            None. The test fails if the library tree gains or changes a file.
        """
        asset_id, path = self.add_track("music/tone.wav", b"")
        _write_wav(path, _sine(440.0, 0.5))
        with open_database(self.library.db) as conn:
            conn.execute("UPDATE asset SET portable_id = ? WHERE id = ?", (str(path), asset_id))
        before = _tree(self.library.root)
        status, headers, body = self.exchange(f"/api/waveform?id={asset_id}")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("x-waveform-format"), "SWF1")
        self.assertTrue(body.startswith(b"SWF1"))
        self.assertEqual(_tree(self.library.root), before)
        names = [row[0] for row in before]
        self.assertFalse(any(name == "Backups" or name.startswith("Backups/") for name in names))
        cache_root = (app_config.config_dir() / "waveforms").resolve()
        library_root = self.library.root.resolve()
        self.assertNotEqual(os.path.commonpath([cache_root, library_root]), str(library_root))

    def test_meta_reports_a_cache_hit(self) -> None:
        """Set ``cached`` on the second metadata request.

        The binary body is the same both times. The file is a short WAV.

        Returns:
            None. The test fails if the second request decodes as a miss.
        """
        asset_id, path = self.add_track("music/tone.wav", b"")
        _write_wav(path, _sine(440.0, 0.5))
        with open_database(self.library.db) as conn:
            conn.execute("UPDATE asset SET portable_id = ? WHERE id = ?", (str(path), asset_id))
        first = self.exchange(f"/api/waveform?id={asset_id}&meta=1")
        second = self.exchange(f"/api/waveform?id={asset_id}&meta=1")
        self.assertEqual(first[0], 200)
        self.assertEqual(second[0], 200)
        first_body = json.loads(first[2])
        second_body = json.loads(second[2])
        self.assertFalse(first_body["cached"])
        self.assertTrue(second_body["cached"])
        self.assertEqual(first_body["detail_points"], 75)
        self.assertEqual(second_body["detail_points"], 75)

    def test_overview_route_does_not_decode(self) -> None:
        """Return Serato Overview columns without a successful decode.

        The file is an ID3 overview and not a playable track. The waveform
        route says unavailable. The overview route returns the columns.

        Returns:
            None. The test fails if the columns are missing or audio is decoded
            into an ``SWF1`` body.
        """
        columns = _overview_columns()
        with tempfile.TemporaryDirectory() as raw:
            source = Path(raw) / "overview.mp3"
            _id3_overview(source, bytes((1, 5)) + columns)
            payload = source.read_bytes()
        asset_id, path = self.add_track("music/overview.mp3", payload)
        with mock.patch("waveform.iter_pcm", side_effect=AssertionError("decoded")):
            overview = self.exchange(f"/api/waveform/overview?id={asset_id}")
        self.assertEqual(overview[0], 200)
        document = json.loads(overview[2])
        self.assertTrue(document["available"])
        self.assertEqual(document["columns"], 2)
        self.assertEqual(document["data"][0], list(columns[:16]))
        with mock.patch("waveform.shutil.which", return_value=None):
            wave_status = self.exchange(f"/api/waveform?id={asset_id}")
        self.assertEqual(wave_status[0], 200)
        self.assertEqual(json.loads(wave_status[2])["error"], "waveform unavailable")
        self.assertEqual(path.read_bytes(), payload)

    def test_path_traversal_and_encoded_ids_are_refused(self) -> None:
        """Refuse a path parameter, a ``..`` id, and a percent-encoded id.

        The raw query is checked before percent-decoding. A real id beside
        ``path`` is refused as well, so the file is not analyzed.

        Returns:
            None. The test fails if any of those queries returns ``SWF1``.
        """
        asset_id, _path = self.add_track("music/tone.wav", b"")
        _write_wav(self.library.root / "music" / "tone.wav", _sine(440.0, 0.2))
        queries = (
            "id=../1",
            "id=1/../../etc/passwd",
            "id=%2e%2e%2f1",
            "id=%31",
            "id=%2531",
            f"path=/etc/passwd&id={asset_id}",
            f"id={asset_id}&path=/etc/passwd",
            "path=/etc/passwd",
        )
        for query in queries:
            with self.subTest(query=query):
                status, _headers, body = self.exchange("/api/waveform?" + query)
                self.assertEqual(status, 400)
                self.assertFalse(body.startswith(b"SWF1"))

    def test_unknown_directory_and_non_audio_are_refused(self) -> None:
        """Refuse an unknown id, a directory, and a file that is not audio.

        Returns:
            None. The test fails if any of those is analyzed.
        """
        missing, _headers, body = self.exchange("/api/waveform?id=99999")
        self.assertEqual(missing, 404)
        self.assertFalse(body.startswith(b"SWF1"))
        folder = self.library.root / "music" / "song.wav"
        folder.mkdir(parents=True)
        folder_id = self.insert_asset(folder)
        notes = self.library.root / "music" / "notes.txt"
        notes.write_bytes(b"notes")
        notes_id = self.insert_asset(notes)
        for asset_id in (folder_id, notes_id):
            with self.subTest(asset_id=asset_id):
                status, _headers, found = self.exchange(f"/api/waveform?id={asset_id}")
                self.assertEqual(status, 403)
                self.assertNotIn(b"notes", found)
                self.assertFalse(found.startswith(b"SWF1"))

    def link_or_skip(self, link: Path, target: Path) -> None:
        """Create a file symlink, or skip when this computer will not.

        Args:
            link: Path of the new symlink.
            target: Existing file.

        Returns:
            None.
        """
        link.parent.mkdir(parents=True, exist_ok=True)
        try:
            link.symlink_to(target)
        except OSError as exc:
            self.skipTest(f"symlink creation is not permitted on this computer ({exc})")

    def test_symlink_outside_roots_is_refused_by_the_access_check(self) -> None:
        """Refuse a file symlink whose real path leaves the stored directory.

        ``audio_stream.library_allows`` is the check ``resolve_audio``
        applies before a waveform is read. Returning True for every path
        would analyze the outside file and this test would fail.

        Returns:
            None. The test fails if the outside sine is returned as ``SWF1``.
        """
        outside = self.library.root / "outside"
        outside.mkdir()
        secret = outside / "secret.wav"
        _write_wav(secret, _sine(60.0, 0.5))
        link = self.library.root / "music" / "escape.wav"
        self.link_or_skip(link, secret)
        asset_id = self.insert_asset(link)
        status, _headers, body = self.exchange(f"/api/waveform?id={asset_id}")
        self.assertEqual(status, 403)
        self.assertFalse(body.startswith(b"SWF1"))
        self.assertNotIn(secret.read_bytes()[:16], body)

    def test_removing_library_allows_fails_this_refusal(self) -> None:
        """Fail when the route no longer calls ``library_allows``.

        The patch makes every path fail the check. A waveform route that
        stopped calling it would return ``SWF1`` for this in-library file.

        Returns:
            None. The test fails if the sine is analyzed while the check refuses.
        """
        asset_id, path = self.add_track("music/tone.wav", b"")
        _write_wav(path, _sine(440.0, 0.2))
        with mock.patch("audio_stream.library_allows", return_value=False):
            status, _headers, body = self.exchange(f"/api/waveform?id={asset_id}")
        self.assertEqual(status, 403)
        self.assertFalse(body.startswith(b"SWF1"))

    def test_quoted_path_is_refused_even_with_an_id(self) -> None:
        """Refuse a filesystem path whether or not an id is present.

        Returns:
            None. The test fails if the secret file is read.
        """
        asset_id, _path = self.add_track("music/tone.wav", b"")
        _write_wav(self.library.root / "music" / "tone.wav", _sine(440.0, 0.2))
        secret = self.library.root / "secret.wav"
        _write_wav(secret, _sine(60.0, 0.2))
        quoted = urllib.parse.quote(str(secret))
        for query in (f"path={quoted}", f"path={quoted}&id={asset_id}", f"id={asset_id}&path={quoted}"):
            with self.subTest(query=query.split("&", 1)[0]):
                status, _headers, body = self.exchange("/api/waveform?" + query)
                self.assertEqual(status, 400)
                self.assertFalse(body.startswith(b"SWF1"))


def _tree(root: Path) -> list[tuple[str, int, int, str]]:
    """Fingerprint a directory without following symlinks.

    Args:
        root: Directory to walk.

    Returns:
        One row per file: relative path, size, mtime, and sha256.
        A symlink records its target instead of the target's bytes.
    """
    rows: list[tuple[str, int, int, str]] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames.sort()
        for name in sorted(filenames):
            file = Path(dirpath) / name
            relative = file.relative_to(root).as_posix()
            if file.is_symlink():
                rows.append((relative, -1, -1, f"link:{os.readlink(file)}"))
                continue
            info = file.stat()
            digest = hashlib.sha256(file.read_bytes()).hexdigest()
            rows.append((relative, info.st_size, info.st_mtime_ns, digest))
    return rows
