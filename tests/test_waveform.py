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
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import tracemalloc
import unittest
import urllib.parse
import wave
from pathlib import Path
from unittest import mock

import miniaudio
import numpy as np

import app_config
import audio_stream
import server
import tags
import waveform
import waveform_native
from tests.fixture import ROOT, TempLibrary, open_database

FIXTURES = ROOT / "tests" / "fixtures"
from tests.test_tags import freeform_atom, serato_b64, write_flac_fixture, write_m4a_fixture

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

        streamed = waveform.analyze_chunks(chunks())
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
    """Check which formats the OS decoder or ffmpeg must open."""

    def test_aac_family_is_not_a_miniaudio_suffix(self) -> None:
        """Name the suffixes miniaudio does not decode.

        A generated AIFF is not in that set. No library file is opened.
        Those suffixes use the OS decoder, then ffmpeg when it is on PATH.

        Returns:
            None. The test fails if AIFF is treated as an AAC-family file.
        """
        self.assertEqual(waveform.AAC_FAMILY_SUFFIXES, frozenset({".m4a", ".aac", ".alac"}))
        self.assertNotIn(".aiff", waveform.AAC_FAMILY_SUFFIXES)
        self.assertNotIn(".aif", waveform.AAC_FAMILY_SUFFIXES)
        self.assertNotIn(".wav", waveform.AAC_FAMILY_SUFFIXES)

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

    @mock.patch("waveform.native_container_opener", return_value=None)
    def test_m4a_without_ffmpeg_is_unavailable(self, _native: mock.MagicMock) -> None:
        """Return the stable sentence when ffmpeg is not on PATH.

        The native opener is patched to None, which is the Linux path and
        the path the other systems take after a native refusal. The file
        is a few bytes with an ``.m4a`` name. ``Popen`` is not called.

        Returns:
            None. The test fails if a waveform body is produced or the
            native opener is not consulted.
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
        self.assertIsNone(_native.return_value)
        _native.assert_called()

    @mock.patch("waveform.native_container_opener", return_value=None)
    def test_ffmpeg_on_path_decodes_m4a(self, _native: mock.MagicMock) -> None:
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
                self.returncode: int | None = None

            def wait(self, timeout: int | None = None) -> int:
                del timeout
                self.returncode = 0
                return 0

            def poll(self) -> int | None:
                return self.returncode

            def kill(self) -> None:
                self.returncode = -9

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
        self.assertIsNone(_native.return_value)
        _native.assert_called()

    def test_mid_file_decode_error_is_unavailable(self) -> None:
        """Turn a miniaudio failure after the first chunk into the stable sentence.

        The HTTP route must answer 200 with ``available`` false. A 500
        would mean the exception left :func:`waveform.load`.

        Returns:
            None. The test fails if the status is 500 or the sentence changes.
        """
        def fail_midway(_path: Path):
            yield np.zeros(ANALYZE_SAFE, dtype=np.float64)
            raise miniaudio.DecodeError("mid-file")

        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "tone.wav"
            _write_wav(path, _sine(440.0, 0.2))
            with mock.patch("waveform.iter_pcm", fail_midway):
                with self.assertRaises(waveform.WaveformUnavailable) as caught:
                    waveform.load(path)
        self.assertEqual(caught.exception.message, "waveform unavailable")

    @mock.patch("waveform.native_container_opener", return_value=None)
    def test_ffmpeg_timeout_is_unavailable_and_the_process_is_killed(self, _native: mock.MagicMock) -> None:
        """Kill ffmpeg when it does not exit, and do not raise 500.

        The fake process raises ``TimeoutExpired`` from the first wait.
        The reaper must kill it. ``load`` becomes waveform unavailable.

        Returns:
            None. The test fails if the process is left running or the error leaks.
        """
        seen: dict[str, object] = {}

        class _Hung:
            def __init__(self) -> None:
                self.stdout = _OneRead(b"")
                self.killed = False
                self.waits = 0

            def poll(self) -> int | None:
                return -9 if self.killed else None

            def kill(self) -> None:
                self.killed = True

            def wait(self, timeout: float | None = None) -> int:
                self.waits += 1
                if self.waits == 1:
                    raise subprocess.TimeoutExpired(cmd="ffmpeg", timeout=timeout or 60)
                return -9

        class _OneRead:
            def __init__(self, payload: bytes) -> None:
                self._payload = payload
                self._done = False

            def read(self, count: int) -> bytes:
                del count
                if self._done:
                    return b""
                self._done = True
                return self._payload

            def close(self) -> None:
                return None

        hung = _Hung()
        seen["proc"] = hung
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "song.m4a"
            path.write_bytes(b"container")
            with mock.patch("waveform.shutil.which", return_value="/usr/bin/ffmpeg"):
                with mock.patch("waveform.subprocess.Popen", return_value=hung):
                    with self.assertRaises(waveform.WaveformUnavailable):
                        waveform.load(path)
        self.assertTrue(hung.killed)
        self.assertIsNone(_native.return_value)
        _native.assert_called()

    @mock.patch("waveform.native_container_opener", return_value=None)
    def test_closing_ffmpeg_early_kills_the_process(self, _native: mock.MagicMock) -> None:
        """Reap ffmpeg when the caller closes the generator before it ends.

        One chunk is taken. ``close`` is what a disconnected client does
        to the generator. The process must be killed and waited on.

        Returns:
            None. The test fails if ``kill`` was not called.
        """
        class _Stdout:
            def read(self, count: int) -> bytes:
                return b"\x00" * min(count, 64)

            def close(self) -> None:
                return None

        class _Alive:
            def __init__(self) -> None:
                self.stdout = _Stdout()
                self.killed = False
                self.waited = False

            def poll(self) -> int | None:
                return -9 if self.killed else None

            def kill(self) -> None:
                self.killed = True

            def wait(self, timeout: float | None = None) -> int:
                del timeout
                self.waited = True
                return -9

        proc = _Alive()
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "song.m4a"
            path.write_bytes(b"container")
            with mock.patch("waveform.shutil.which", return_value="/usr/bin/ffmpeg"):
                with mock.patch("waveform.subprocess.Popen", return_value=proc):
                    stream = waveform.iter_pcm(path)
                    next(iter(stream))
                    stream.close()
        self.assertTrue(proc.killed)
        self.assertTrue(proc.waited)
        self.assertIsNone(_native.return_value)
        _native.assert_called()

    def test_truncated_wav_read_is_unavailable(self) -> None:
        """Map a short WAV read to waveform unavailable.

        The file is a real WAV with its tail cut off. miniaudio is refused
        so the stdlib reader runs. ``readframes`` then raises ``wave.Error``,
        which must not escape as an uncaught error.

        Returns:
            None. The test fails if the exception is not ``WaveformUnavailable``.
        """
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "cut.wav"
            _write_wav(path, _sine(440.0, 0.5))
            whole = path.read_bytes()
            path.write_bytes(whole[: len(whole) // 2])
            self.assertLess(path.stat().st_size, len(whole))
            real_open = wave.open

            def open_truncated(name: str, mode: str | None = None) -> wave.Wave_read:
                handle = real_open(name, mode)

                def readframes(_count: int) -> bytes:
                    raise wave.Error("file is truncated")

                setattr(handle, "readframes", readframes)
                return handle

            with mock.patch("waveform.miniaudio.stream_file", side_effect=RuntimeError("no")):
                with mock.patch("waveform.shutil.which", return_value=None):
                    with mock.patch("waveform.wave.open", open_truncated):
                        with self.assertRaises(waveform.WaveformUnavailable) as caught:
                            waveform.load(path)
        self.assertEqual(caught.exception.message, "waveform unavailable")


ANALYZE_SAFE = 44100


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

    def test_partial_names_differ_by_thread(self) -> None:
        """Give each cache writer its own temporary name.

        Two threads call the helper at the same time. The names include
        the thread id and a counter, so ``os.replace`` cannot clobber
        the other writer's bytes.

        Returns:
            None. The test fails if both threads build the same path.
        """
        dest = Path("/tmp/waveform-cache-key")
        found: list[Path] = []
        lock = threading.Lock()

        def grab() -> None:
            path = waveform.partial_cache_name(dest)
            with lock:
                found.append(path)

        threads = [threading.Thread(target=grab) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len({str(path) for path in found}), 4)


class SharedAnalysisTests(unittest.TestCase):
    """One in-flight analysis serves every overlapping request."""

    def test_two_callers_decode_once(self) -> None:
        """Run ``waveform.load`` once when two threads ask together.

        The stand-in waits until both callers have entered. A second
        decode would increment the counter past 1.

        Returns:
            None. The test fails if each caller analyzes on its own.
        """
        calls = {"n": 0}
        entered = threading.Semaphore(0)
        release = threading.Event()
        body = waveform.analyze_samples(_sine(440.0, 0.2), _RATE)

        def slow(path: Path) -> tuple[bytes, bool]:
            del path
            calls["n"] += 1
            entered.release()
            if not release.wait(timeout=2):
                raise TimeoutError("the second caller did not arrive")
            return body, False

        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "tone.wav"
            _write_wav(path, _sine(440.0, 0.2))
            with mock.patch("waveform.load", slow):
                results: list[tuple[bytes, bool]] = []
                errors: list[BaseException] = []

                def run() -> None:
                    try:
                        results.append(server.load_shared_waveform(path))
                    except BaseException as exc:
                        errors.append(exc)

                threads = [threading.Thread(target=run) for _ in range(2)]
                for thread in threads:
                    thread.start()
                self.assertTrue(entered.acquire(timeout=2))
                time.sleep(0.05)
                release.set()
                for thread in threads:
                    thread.join(timeout=3)
        self.assertEqual(errors, [])
        self.assertEqual(calls["n"], 1)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0][0], body)


class BenchmarkTests(unittest.TestCase):
    """Keep a short track inside a budget scaled from an hour in 10 seconds."""

    def test_short_wav_stays_inside_the_scaled_budget(self) -> None:
        """Analyze thirty seconds without holding the PCM.

        An hour is budgeted at 10 seconds and 80 MiB of traced allocations.
        Thirty seconds gets the same rate plus a second of fixed overhead.
        The traced peak must stay under 80 MiB. The file is temporary.

        Returns:
            None. The test fails if the run is slower or larger than that.
        """
        seconds = 30
        limit = 1.0 + (10.0 * seconds / 3600.0)
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "tone.wav"
            _write_wav(path, _sine(440.0, float(seconds)))
            tracemalloc.start()
            started = time.perf_counter()
            body, _cached = waveform.load(path)
            elapsed = time.perf_counter() - started
            _current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
        parsed = waveform.parse_waveform(body)
        self.assertGreater(parsed["detail_count"], 1000)
        self.assertLess(elapsed, limit)
        self.assertLess(peak, 80 * 1024 * 1024)


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
            wrapped = serato_b64("Serato Overview", payload, wrap=True)
            write_flac_fixture(flac, [b"SERATO_OVERVIEW=" + wrapped])
            write_m4a_fixture(m4a, freeform_atom("overview", wrapped, null_terminate=False))
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
                    beats = grid[0].get("beats")
                    last_bpm = grid[-1].get("bpm")
                    self.assertIsNotNone(beats)
                    self.assertIsNotNone(last_bpm)
                    assert beats is not None and last_bpm is not None
                    spacing = (grid[1]["position"] - grid[0]["position"]) / beats
                    self.assertAlmostEqual(spacing, 0.5)
                    self.assertAlmostEqual(60.0 / last_bpm, 60.0 / bpm)
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
        bound = self.httpd.server_address
        host = bound[0]
        port = bound[1]
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

    def test_mid_decode_on_the_wire_is_unavailable(self) -> None:
        """Answer 200 when miniaudio fails after decoding has started.

        Returns:
            None. The test fails if the status is 500.
        """
        asset_id, path = self.add_track("music/tone.wav", b"")
        _write_wav(path, _sine(440.0, 0.2))

        def fail_midway(_path: Path):
            yield np.zeros(1024, dtype=np.float64)
            raise miniaudio.DecodeError("mid-file")

        with mock.patch("waveform.iter_pcm", fail_midway):
            status, headers, body = self.exchange(f"/api/waveform?id={asset_id}")
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"].split(";")[0], "application/json")
        self.assertEqual(json.loads(body), {"available": False, "error": "waveform unavailable"})

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


class NativeDecoderTests(unittest.TestCase):
    """Exercise the macOS and Windows container decoders with fakes.

    The real files are covered by :class:`NativeFileTests`, which run on
    the macOS and Windows runners. These tests run on every OS.
    """

    def test_platform_selects_one_native_opener(self) -> None:
        """Use AudioToolbox on macOS, Media Foundation on Windows, and neither on Linux.

        No file is opened. The test fails if Linux calls afconvert or if
        macOS skips the native opener and goes straight to ffmpeg.

        Returns:
            None.
        """
        cases = {
            "darwin": waveform_native.open_apple,
            "win32": waveform_native.open_media_foundation,
            "linux": None,
        }
        for platform, expected in cases.items():
            with self.subTest(platform=platform):
                with mock.patch("waveform.sys.platform", platform):
                    opener = waveform.native_container_opener()
                if expected is None:
                    self.assertIsNone(opener)
                else:
                    self.assertIs(opener, expected)

    def test_linux_does_not_call_afconvert(self) -> None:
        """Leave an m4a unavailable on Linux when ffmpeg is absent.

        ``open_apple`` raises if it is called. The file is a few bytes in
        a temp directory.

        Returns:
            None. The test fails if a waveform is produced.
        """
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "song.m4a"
            path.write_bytes(b"not-audio")
            with mock.patch("waveform.sys.platform", "linux"):
                with mock.patch("waveform_native.open_apple", side_effect=AssertionError("afconvert")):
                    with mock.patch("waveform.shutil.which", return_value=None):
                        with self.assertRaises(waveform.WaveformUnavailable) as caught:
                            waveform.load(path)
        self.assertEqual(caught.exception.message, "waveform unavailable")

    def test_each_os_refuses_a_container_the_native_decoder_rejects(self) -> None:
        """Return the stable sentence when that OS decoder and ffmpeg both refuse.

        Upper-case suffixes still select the container path. The source
        directory is unchanged.

        Returns:
            None. The test fails if the native opener is skipped or a body is produced.
        """
        cases = (
            ("darwin", "waveform_native.open_apple", "Song.M4A"),
            ("win32", "waveform_native.open_media_foundation", "Song.AAC"),
            ("linux", None, "song.alac"),
        )
        for platform, opener_name, filename in cases:
            with self.subTest(platform=platform):
                with tempfile.TemporaryDirectory() as raw:
                    path = Path(raw) / filename
                    before = b"not-audio"
                    path.write_bytes(before)
                    seen: list[Path] = []

                    def refuse(source: Path) -> None:
                        seen.append(source)
                        raise waveform.DecodeError()

                    patches = [
                        mock.patch("waveform.sys.platform", platform),
                        mock.patch("waveform.shutil.which", return_value=None),
                    ]
                    if opener_name is not None:
                        patches.append(mock.patch(opener_name, side_effect=refuse))
                    with patches[0], patches[1]:
                        if opener_name is not None:
                            with patches[2]:
                                with self.assertRaises(waveform.WaveformUnavailable) as caught:
                                    waveform.load(path)
                        else:
                            with self.assertRaises(waveform.WaveformUnavailable) as caught:
                                waveform.load(path)
                    self.assertEqual(caught.exception.message, "waveform unavailable")
                    self.assertEqual(path.read_bytes(), before)
                    self.assertEqual([item.name for item in Path(raw).iterdir()], [filename])
                    if opener_name is None:
                        self.assertEqual(seen, [])
                    else:
                        self.assertEqual(seen, [path])

    def test_native_success_does_not_spawn_ffmpeg(self) -> None:
        """Stop after the OS decoder returns samples.

        ffmpeg is reported on PATH. ``Popen`` must not run. The tone is a
        generated 1 kHz sine, not a library file.

        Returns:
            None. The test fails if ffmpeg is launched or the mid band is quiet.
        """
        def succeed(_path: Path):
            return iter((_sine(1000.0, 0.5),))

        for platform, opener_name in (
            ("darwin", "waveform_native.open_apple"),
            ("win32", "waveform_native.open_media_foundation"),
        ):
            with self.subTest(platform=platform):
                with tempfile.TemporaryDirectory() as raw:
                    path = Path(raw) / "song.m4a"
                    path.write_bytes(b"container")
                    with mock.patch("waveform.sys.platform", platform):
                        with mock.patch(opener_name, side_effect=succeed):
                            with mock.patch("waveform.shutil.which", return_value="/usr/bin/ffmpeg"):
                                with mock.patch("waveform.subprocess.Popen") as popen:
                                    body, _cached = waveform.load(path)
                popen.assert_not_called()
                self.assertGreater(_middle_means(body)[2], 100)

    def test_native_refusal_falls_through_to_ffmpeg(self) -> None:
        """Use ffmpeg when the OS decoder raises ``DecodeError``.

        The process is fake. Its stdout is one float32 sine. The command
        is an argv list.

        Returns:
            None. The test fails if ffmpeg is not launched after the refusal.
        """
        samples = _sine(1000.0, 0.5).astype("<f4")

        class _Process:
            def __init__(self) -> None:
                self.stdout = _Stdout(samples.tobytes())
                self.returncode: int | None = None

            def wait(self, timeout: int | None = None) -> int:
                del timeout
                self.returncode = 0
                return 0

            def poll(self) -> int | None:
                return self.returncode

            def kill(self) -> None:
                self.returncode = -9

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

        def refuse(_path: Path) -> None:
            raise waveform.DecodeError("native refused")

        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "song.m4a"
            path.write_bytes(b"container")
            with mock.patch("waveform.sys.platform", "darwin"):
                with mock.patch("waveform_native.open_apple", side_effect=refuse):
                    with mock.patch("waveform.shutil.which", return_value="/usr/bin/ffmpeg"):
                        with mock.patch("waveform.subprocess.Popen", return_value=_Process()) as popen:
                            body, _cached = waveform.load(path)
        self.assertEqual(popen.call_args.args[0][0], "/usr/bin/ffmpeg")
        self.assertIs(popen.call_args.kwargs.get("shell", False), False)
        self.assertGreater(_middle_means(body)[2], 100)

    def test_wav_does_not_use_the_container_decoder(self) -> None:
        """Decode a WAV with miniaudio even when the OS container decoder exists.

        The container opener raises if it is called. ffmpeg is absent.

        Returns:
            None. The test fails if the WAV is sent to afconvert.
        """
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "tone.wav"
            _write_wav(path, _sine(440.0, 0.5))
            with mock.patch("waveform.sys.platform", "darwin"):
                with mock.patch("waveform_native.open_apple", side_effect=AssertionError("container")):
                    with mock.patch("waveform.shutil.which", return_value=None):
                        body, _cached = waveform.load(path)
        self.assertEqual(waveform.parse_waveform(body)["detail_count"], 75)

    def test_afconvert_command_stays_in_temp_and_is_not_a_shell_string(self) -> None:
        """Build an argv list whose output is a different temp directory.

        The source directory name contains a space. No process is started.

        Returns:
            None. The test fails if the output sits beside the source or the
            executable is not absolute ``afconvert``.
        """
        with tempfile.TemporaryDirectory() as source_dir:
            with tempfile.TemporaryDirectory() as dest_dir:
                source = Path(source_dir) / "my music" / "song.m4a"
                source.parent.mkdir()
                source.write_bytes(b"container")
                dest = Path(dest_dir) / "pcm.wav"
                executable = _absolute_named("afconvert")
                command = waveform_native.afconvert_command(executable, source, dest)
        self.assertIsInstance(command, list)
        self.assertEqual(command[0], executable)
        self.assertEqual(command[-2], os.fspath(source))
        self.assertEqual(command[-1], os.fspath(dest))
        self.assertIn("WAVE", command)
        self.assertIn("LEI16@44100", command)
        self.assertIn("1", command)
        self.assertNotIn("--", command)
        with self.assertRaises(waveform.DecodeError):
            waveform_native.afconvert_command("afconvert", source, dest)
        with self.assertRaises(waveform.DecodeError):
            waveform_native.afconvert_command(_absolute_named("ffmpeg"), source, dest)
        with self.assertRaises(waveform.DecodeError):
            waveform_native.afconvert_command("/usr/bin/afconvert", source, source.with_suffix(".wav"))

    def test_temp_output_refuses_the_source_directory_and_the_library(self) -> None:
        """Reject a WAV written next to the audio file or into the library folder.

        Two different temp directories are allowed. The library check is
        patched so the refusal does not depend on this machine's home folder.

        Returns:
            None. The test fails if a same-directory output is accepted.
        """
        with tempfile.TemporaryDirectory() as left:
            with tempfile.TemporaryDirectory() as right:
                source = Path(left) / "song.m4a"
                source.write_bytes(b"container")
                dest = Path(right) / "pcm.wav"
                with mock.patch("waveform_native._library_blocked", return_value=False):
                    self.assertTrue(waveform_native.separate_temp_output(source, dest))
                with mock.patch("waveform_native._library_blocked", return_value=True):
                    self.assertFalse(waveform_native.separate_temp_output(source, dest))
                self.assertFalse(waveform_native.separate_temp_output(source, source.with_suffix(".wav")))
                self.assertFalse(waveform_native.destination_in_temp(Path.cwd() / "song.m4a"))
                self.assertTrue(waveform_native.destination_in_temp(dest))

    def test_afconvert_decodes_and_deletes_the_temp_wav(self) -> None:
        """Run the macOS opener against a fake afconvert and delete its WAV.

        The fake writes a real PCM WAV to the output argument. The source
        name contains a space and is also reached through a symlink. The
        source bytes and mtime stay put, and the temp directory is gone
        after the iterator finishes.

        Returns:
            None. The test fails if a file appears beside the source or the
            command is not an argv list.
        """
        created: list[str] = []
        real_directory = tempfile.TemporaryDirectory

        def tracking(*_args: object, **kwargs: object) -> tempfile.TemporaryDirectory[str]:
            prefix = kwargs.get("prefix")
            directory = real_directory(prefix=prefix if isinstance(prefix, str) else None)
            created.append(directory.name)
            return directory

        class _Proc:
            def __init__(self, command: list[str], **kwargs: object) -> None:
                self.command = command
                self.kwargs = kwargs
                self.returncode: int | None = None
                self.killed = False
                dest = Path(command[-1])
                _write_wav(dest, _sine(1000.0, 0.5))

            def communicate(self, timeout: float | None = None) -> tuple[bytes, bytes]:
                del timeout
                self.returncode = 0
                return b"", b""

            def poll(self) -> int | None:
                return self.returncode

            def kill(self) -> None:
                self.killed = True

        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw) / "my music"
            folder.mkdir()
            source = folder / "song.m4a"
            payload = b"container-bytes"
            source.write_bytes(payload)
            stamp = source.stat().st_mtime_ns
            link = folder / "link.m4a"
            try:
                link.symlink_to(source)
            except OSError:
                link = source
            names_before = sorted(item.name for item in folder.iterdir())
            executable = _absolute_named("afconvert")
            with mock.patch("waveform_native.apple_converter", return_value=executable):
                with mock.patch("waveform_native.tempfile.TemporaryDirectory", tracking):
                    with mock.patch("waveform_native.subprocess.Popen", side_effect=_Proc) as popen:
                        stream = waveform_native.open_apple(link)
                        try:
                            chunks = list(stream)
                        finally:
                            stream.close()
            command = popen.call_args.args[0]
            self.assertIsInstance(command, list)
            self.assertEqual(command[0], executable)
            self.assertEqual(command[-2], os.fspath(link))
            self.assertTrue(Path(command[-1]).parent.name.startswith(waveform_native.TEMP_PREFIX))
            self.assertNotEqual(Path(command[-1]).resolve().parent, folder.resolve())
            self.assertIs(popen.call_args.kwargs.get("shell"), False)
            self.assertIn("shell", popen.call_args.kwargs)
            self.assertIs(popen.call_args.kwargs.get("stdin"), subprocess.DEVNULL)
            self.assertGreater(len(chunks), 0)
            self.assertEqual(source.read_bytes(), payload)
            self.assertEqual(source.stat().st_mtime_ns, stamp)
            self.assertEqual(sorted(item.name for item in folder.iterdir()), names_before)
            self.assertTrue(created)
            self.assertFalse(Path(created[0]).exists())

    def test_afconvert_timeout_kills_the_process_and_removes_the_temp_dir(self) -> None:
        """Kill afconvert when it does not exit, and do not leave the WAV directory.

        The fake ``communicate`` raises ``TimeoutExpired`` once. The source
        is a few bytes in a temp directory.

        Returns:
            None. The test fails if the process is left running or the temp
            directory remains.
        """
        created: list[str] = []
        real_directory = tempfile.TemporaryDirectory

        def tracking(*_args: object, **kwargs: object) -> tempfile.TemporaryDirectory[str]:
            prefix = kwargs.get("prefix")
            directory = real_directory(prefix=prefix if isinstance(prefix, str) else None)
            created.append(directory.name)
            return directory

        class _Hung:
            def __init__(self, command: list[str], **kwargs: object) -> None:
                del command, kwargs
                self.killed = False
                self.calls = 0
                self.returncode: int | None = None

            def communicate(self, timeout: float | None = None) -> tuple[bytes, bytes]:
                self.calls += 1
                if self.calls == 1:
                    raise subprocess.TimeoutExpired(cmd="afconvert", timeout=timeout or 1)
                self.returncode = -9
                return b"", b""

            def poll(self) -> int | None:
                return self.returncode

            def kill(self) -> None:
                self.killed = True

        hung = _Hung([])
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "song.m4a"
            path.write_bytes(b"container")
            with mock.patch("waveform_native.apple_converter", return_value=_absolute_named("afconvert")):
                with mock.patch("waveform_native.tempfile.TemporaryDirectory", tracking):
                    with mock.patch("waveform_native.subprocess.Popen", return_value=hung):
                        with self.assertRaises(waveform.WaveformUnavailable) as caught:
                            waveform_native.open_apple(path)
        self.assertEqual(caught.exception.message, "waveform unavailable")
        self.assertTrue(hung.killed)
        self.assertTrue(created)
        self.assertFalse(Path(created[0]).exists())

    def test_relative_afconvert_is_not_executed(self) -> None:
        """Refuse a relative converter path before starting a process.

        Returns:
            None. The test fails if ``Popen`` is called.
        """
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "song.m4a"
            path.write_bytes(b"container")
            with mock.patch("waveform_native.apple_converter", return_value="afconvert"):
                with mock.patch("waveform_native.subprocess.Popen") as popen:
                    with self.assertRaises(waveform.DecodeError):
                        waveform_native.open_apple(path)
        popen.assert_not_called()

    def test_media_foundation_is_refused_off_windows(self) -> None:
        """Do not load Media Foundation DLLs on Linux or macOS.

        Returns:
            None. The test fails if a non-Windows call returns samples.
        """
        if sys.platform == "win32":
            self.skipTest("the refusal is the non-Windows path")
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "song.m4a"
            path.write_bytes(b"container")
            with mock.patch("waveform_native._com_start", side_effect=AssertionError("com")):
                with self.assertRaises(waveform.DecodeError):
                    waveform_native.open_media_foundation(path)

    def test_alac_alias_is_removed_and_does_not_touch_the_source_directory(self) -> None:
        """Hard-link or copy a ``.alac`` file to a temp ``.m4a`` and then delete it.

        The source bytes and the source directory listing stay the same.
        No library file is used.

        Returns:
            None. The test fails if the alias remains or the source changes.
        """
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw) / "tracks"
            folder.mkdir()
            source = folder / "song.alac"
            payload = b"alac-bytes-not-a-real-file"
            source.write_bytes(payload)
            before = sorted(item.name for item in folder.iterdir())
            alias, cleanup = waveform_native.temporary_m4a_alias(source)
            try:
                self.assertEqual(alias.name, "track.m4a")
                self.assertTrue(alias.parent.name.startswith(waveform_native.TEMP_PREFIX))
                self.assertNotEqual(alias.resolve().parent, folder.resolve())
                self.assertEqual(alias.read_bytes(), payload)
                self.assertEqual(source.read_bytes(), payload)
                self.assertEqual(sorted(item.name for item in folder.iterdir()), before)
                self.assertTrue(waveform_native.separate_temp_output(source, alias))
            finally:
                cleanup()
            self.assertFalse(alias.exists())
            self.assertFalse(alias.parent.exists())
            self.assertEqual(source.read_bytes(), payload)

    def test_encoder_does_not_start_media_foundation_outside_temp(self) -> None:
        """Refuse an ``.m4a`` destination in the working directory.

        COM startup is patched to fail the test if it is reached. The
        destination is deleted if a regression creates it.

        Returns:
            None. The test fails if a file is written outside temp.
        """
        dest = Path.cwd() / "not-a-waveform.m4a"
        try:
            with tempfile.TemporaryDirectory() as raw:
                wav = Path(raw) / "tone.wav"
                _write_wav(wav, _sine(440.0, 0.1))
                with mock.patch("waveform_native.sys.platform", "win32"):
                    with mock.patch("waveform_native._com_start", side_effect=AssertionError("com")):
                        with self.assertRaises(waveform.DecodeError):
                            waveform_native.encode_aac_m4a(wav, dest)
            self.assertFalse(dest.exists())
        finally:
            if dest.exists():
                dest.unlink()


def _absolute_named(name: str) -> str:
    """Return an absolute path whose final component is ``name``.

    Args:
        name: File name, such as ``afconvert``.

    Returns:
        A path under the system temp directory. ``/usr/bin/afconvert`` is
        not absolute on Windows, so tests use this instead.
    """
    return str(Path(tempfile.gettempdir()) / name)


def _aac_tool() -> str | None:
    """Return the AAC encoder this machine can run, or None.

    Returns:
        ``afconvert`` on macOS when the system tool exists, ``ffmpeg`` when
        that program is on PATH, or ``media-foundation`` on Windows when the
        DLLs load. None when no encoder is available.
    """
    if sys.platform == "darwin" and waveform_native.apple_converter():
        return "afconvert"
    found = shutil.which("ffmpeg")
    if found:
        return found
    if sys.platform == "win32" and waveform_native.media_foundation_available():
        return "media-foundation"
    return None


def _alac_tool() -> str | None:
    """Return an ALAC encoder this machine can run, or None.

    Returns:
        ``afconvert`` on macOS, or an ffmpeg path. Media Foundation is not
        an ALAC encoder, so Windows without ffmpeg returns None.
    """
    if sys.platform == "darwin" and waveform_native.apple_converter():
        return "afconvert"
    return shutil.which("ffmpeg")


def _run_encoder(command: list[str]) -> None:
    """Run one encoder argv and raise when it does not write a file.

    Args:
        command: Argument vector. It is not a shell string.

    Raises:
        AssertionError: The process exits non-zero or does not finish.
    """
    completed = subprocess.run(
        command,
        check=False,
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        timeout=60,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", "replace")[:500]
        raise AssertionError(detail)


def _encode_fixture(kind: str, wav: Path, dest: Path) -> None:
    """Encode ``wav`` to ``dest`` with the tool selected for ``kind``.

    Args:
        kind: ``aac``, ``alac``, or ``adts``.
        wav: 16-bit mono WAV.
        dest: Output path in the same temp directory as ``wav``.

    Raises:
        AssertionError: The encoder fails or writes an empty file.
    """
    if kind == "aac" and _aac_tool() == "media-foundation":
        waveform_native.encode_aac_m4a(wav, dest)
    elif sys.platform == "darwin" and waveform_native.apple_converter():
        converter = waveform_native.apple_converter()
        if converter is None:
            raise AssertionError("afconvert is not installed")
        data = {"aac": "aac", "alac": "alac", "adts": "aac"}[kind]
        file_format = "adts" if kind == "adts" else "m4af"
        command = [converter, "-f", file_format, "-d", data, "-c", "1"]
        if kind != "alac":
            command.extend(["-b", "96000"])
        command.extend([os.fspath(wav), os.fspath(dest)])
        _run_encoder(command)
    else:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise AssertionError("no encoder")
        if kind == "alac":
            command = [ffmpeg, "-y", "-i", os.fspath(wav), "-c:a", "alac", os.fspath(dest)]
        elif kind == "adts":
            command = [ffmpeg, "-y", "-i", os.fspath(wav), "-f", "adts", "-c:a", "aac", os.fspath(dest)]
        else:
            command = [ffmpeg, "-y", "-i", os.fspath(wav), "-c:a", "aac", "-b:a", "96k", os.fspath(dest)]
        _run_encoder(command)
    if not dest.is_file() or dest.stat().st_size == 0:
        raise AssertionError("encoder wrote no bytes")


def _prepare_audio(kind: str, folder: Path) -> Path | None:
    """Return a temp AAC or ALAC file, generated or copied from the baked sine.

    Generation is preferred when this machine has an encoder. A failure, or
    a machine with no encoder, uses the synthetic file under
    ``tests/fixtures/waveform``. Those files are one-second 1 kHz sines.

    Args:
        kind: ``aac``, ``alac``, or ``adts``.
        folder: Temp directory that will hold the copy.

    Returns:
        The audio path, or None when neither an encoder nor a baked file exists.
    """
    baked_name = {"aac": "tone-aac.m4a", "alac": "tone-alac.m4a", "adts": "tone.aac"}[kind]
    dest = folder / baked_name
    wav = folder / "tone.wav"
    if not wav.is_file():
        _write_wav(wav, _sine(1000.0, 1.0))
    if kind == "alac":
        has_tool = _alac_tool()
    elif kind == "adts":
        has_tool = (sys.platform == "darwin" and waveform_native.apple_converter()) or shutil.which("ffmpeg")
    else:
        has_tool = _aac_tool()
    if has_tool:
        try:
            _encode_fixture(kind, wav, dest)
        except Exception:
            if dest.exists():
                dest.unlink()
    if not dest.is_file() or dest.stat().st_size == 0:
        baked = FIXTURES / "waveform" / baked_name
        if not baked.is_file():
            return None
        dest.write_bytes(baked.read_bytes())
    return dest


def _assert_mid_tone(test: unittest.TestCase, body: bytes) -> None:
    """Require a 1 kHz tone to land in the mid band.

    Args:
        test: The running test.
        body: An ``SWF1`` body.
    """
    parsed = waveform.parse_waveform(body)
    test.assertGreater(parsed["detail_count"], 40)
    means = _middle_means(body)
    test.assertGreater(float(means[2]), float(means[0]))
    test.assertGreater(float(means[2]), float(means[4]))


@unittest.skipUnless(
    sys.platform in {"darwin", "win32"},
    "OS-native AAC and ALAC decode is exercised on the macOS and Windows runners",
)
class NativeFileTests(unittest.TestCase):
    """Decode AAC or ALAC with the OS decoder.

    The file is generated when an encoder exists. Otherwise the baked
    one-second 1 kHz sine in ``tests/fixtures/waveform`` is copied into a
    temp directory. ffmpeg is hidden for the decode, so a pass is the
    native reader. Linux skips this class.
    """

    def _load_native(self, path: Path) -> bytes:
        """Decode ``path`` with ffmpeg hidden.

        Args:
            path: Generated audio file.

        Returns:
            The ``SWF1`` body.
        """
        before = path.read_bytes()
        stamp = path.stat().st_mtime_ns
        names = sorted(item.name for item in path.parent.iterdir())
        with mock.patch("waveform.shutil.which", return_value=None):
            body, _cached = waveform.load(path)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(path.stat().st_mtime_ns, stamp)
        self.assertEqual(sorted(item.name for item in path.parent.iterdir()), names)
        return body

    def test_aac_m4a_decodes_with_the_native_decoder(self) -> None:
        """Read a mid-band waveform from a one-second AAC file.

        macOS prefers ``afconvert``. Windows prefers Media Foundation and
        falls back to the baked sine when that encoder refuses the type.
        The source directory does not gain a decoded WAV.

        Returns:
            None. The test skips when no AAC bytes are available.
        """
        with tempfile.TemporaryDirectory() as raw:
            dest = _prepare_audio("aac", Path(raw))
            if dest is None:
                self.skipTest("no AAC encoder on this runner")
                return
            body = self._load_native(dest)
        _assert_mid_tone(self, body)

    def test_alac_m4a_and_alac_suffix_decode_with_the_native_decoder(self) -> None:
        """Decode an ALAC file under both a ``.m4a`` name and a ``.alac`` name.

        The ``.alac`` file is a copy of the same bytes in the temp directory.
        Windows uses the baked sine when it has no ALAC encoder.

        Returns:
            None. The test skips when no ALAC bytes are available.
        """
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            dest = _prepare_audio("alac", folder)
            if dest is None:
                self.skipTest("no ALAC encoder on this runner")
                return
            renamed = folder / "tone.alac"
            renamed.write_bytes(dest.read_bytes())
            body = self._load_native(dest)
            renamed_body = self._load_native(renamed)
        _assert_mid_tone(self, body)
        _assert_mid_tone(self, renamed_body)

    def test_adts_aac_decodes_with_the_native_decoder(self) -> None:
        """Read a mid-band waveform from an ADTS ``.aac`` file.

        macOS prefers ``afconvert``. Windows uses the baked sine when
        ffmpeg is not installed.

        Returns:
            None. The test skips when no ADTS bytes are available.
        """
        with tempfile.TemporaryDirectory() as raw:
            dest = _prepare_audio("adts", Path(raw))
            if dest is None:
                self.skipTest("no ADTS encoder on this runner")
                return
            body = self._load_native(dest)
        _assert_mid_tone(self, body)
