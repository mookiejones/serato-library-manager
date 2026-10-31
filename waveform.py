"""Frequency-band waveform for one library track.

The file is opened read-only. Nothing under the Serato library folder is
written, and the audio file is not modified. Samples are decoded in
chunks, mixed to mono, and split into low (under 250 Hz), mid (250 Hz to
4 kHz), and high (over 4 kHz) with FFT overlap-save. Detail is 150 points
per second. The overview is 1000 points, or fewer when the track is shorter
than that. One decode chunk and one FFT block are in memory at a time.

Decoding uses miniaudio (MIT; dr_mp3, dr_flac, and stb_vorbis, which are
public domain). That covers ``.wav``, ``.aiff``, ``.aif``, ``.flac``,
``.mp3``, and ``.ogg``. A WAV or AIFF that miniaudio cannot open falls
back to the stdlib ``wave`` module or a pure-Python AIFF reader. ``.m4a``,
``.aac``, and ``.alac`` are not in those decoders. macOS reads them with
``afconvert`` (AudioToolbox), which writes a temporary WAV under the system
temp directory. Windows reads them with Media Foundation, in memory.
Linux tries ``ffmpeg`` only when ``shutil.which`` finds it on ``PATH``.
The other two systems try that same ffmpeg when the native decoder
refuses the file. ffmpeg is not bundled, and the PyInstaller spec is not
changed to add it. soundfile and libsndfile are not used. A temp file is
removed when decoding finishes or fails, and it is not written beside the
audio file or inside the Serato library folder. A file that still cannot
be decoded raises :class:`WaveformUnavailable`. Playback is a different
route and is left alone.

The response body is little-endian ``SWF1``:

| Offset | Type | Field |
| --- | --- | --- |
| 0 | 4 bytes | ``SWF1`` |
| 4 | uint16 | Header size in bytes (64) |
| 6 | uint16 | Format version (1) |
| 8 | uint16 | Flags. Bit 0 detail, bit 1 overview, bit 2 Serato Overview |
| 10 | uint16 | Analyzer version |
| 12 | uint32 | Sample rate used for the analysis (44100) |
| 16 | uint32 | Detail points per second, times 1000 (150000 means 150) |
| 20 | uint32 | Duration in milliseconds |
| 24 | uint32 | Detail point count ``N`` |
| 28 | uint32 | Overview point count ``M`` |
| 32 | uint32 | Serato Overview column count ``S`` |
| 36 | uint16 | Serato Overview bands per column (16, or 0 when ``S`` is 0) |
| 38 | uint16 | Reserved, zero |
| 40 | uint32 | Low/mid split in Hz, times 1000 (250000) |
| 44 | uint32 | Mid/high split in Hz, times 1000 (4000000) |
| 48 | 16 bytes | Reserved, zero |

After the 64-byte header:

1. Detail, ``N * 6`` uint8 values. Each point is low peak, low RMS, mid
   peak, mid RMS, high peak, high RMS. 255 is full scale.
2. Overview, ``M * 6`` uint8 values, same order. Peaks are the maximum in
   the bucket. RMS is the root of the mean square of the detail RMS values.
3. Serato Overview, ``S * 16`` uint8 values, one column at a time, in the
   order stored in the tag. This is the file's own overview, not the
   computed one. It is empty when the tag is absent.

A tail shorter than one detail point is dropped. A track with fewer than
1000 detail points keeps that many overview points. A longer track is
bucketed into exactly 1000. The cache lives in the app data directory
beside ``settings.json``, under ``waveforms/``. The key is the real path,
size, mtime, and analyzer version. Failures are not cached.
"""

from __future__ import annotations

import hashlib
import itertools
import logging
import os
import shutil
import struct
import subprocess
import sys
import threading
import wave
from collections.abc import Generator, Iterator
from pathlib import Path
from typing import BinaryIO, Callable, TypedDict

import miniaudio
import numpy as np

import app_config
import library
import tags
import waveform_native

logger = logging.getLogger("serato.waveform")

ANALYZER_VERSION = 2
HEADER_BYTES = 64
DETAIL_HZ = 150
OVERVIEW_POINTS = 1000
LOW_HZ = 250.0
HIGH_HZ = 4000.0
ANALYZE_RATE = 44100
DECODE_FRAMES = 16384
_TAPS = 1023
_HEADER = struct.Struct("<4s4H6I2H2I")
_SERATO_BANDS = 16

# miniaudio's bundled decoders do not open these. The OS reader or ffmpeg does.
AAC_FAMILY_SUFFIXES = frozenset({".m4a", ".aac", ".alac"})

_FLAG_DETAIL = 1
_FLAG_OVERVIEW = 2
_FLAG_SERATO = 4

_FILTERS: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
_fft_plan_cache: tuple[int, list[np.ndarray]] | None = None
_PARTIAL_SEQ = itertools.count()


class WaveformUnavailable(Exception):
    """The track is in the library and its waveform cannot be decoded.

    Attributes:
        message: Sentence returned to the page. It does not include a path.
    """

    def __init__(self, message: str = "waveform unavailable") -> None:
        """Store the page sentence.

        Args:
            message: Sentence returned as JSON. Defaults to the stable
                ``waveform unavailable`` text.
        """
        super().__init__(message)
        self.message = message


class DecodeError(Exception):
    """One decoder could not open this file.

    Another decoder may still be tried. The message is not shown to the page.
    """


def cache_key(path: Path, size: int, mtime_ns: int, version: int) -> str:
    """Return the cache id for one analyzed file.

    Args:
        path: Real path of the audio file.
        size: Size in bytes from ``lstat``.
        mtime_ns: Modification time in nanoseconds from ``lstat``.
        version: Analyzer version that produced the bytes.

    Returns:
        A lowercase SHA-256 hex digest. The text is the real path, the
        size, the mtime, and the version, separated by NUL. The path is
        compared the way this operating system compares file names.
    """
    text = "\0".join(
        (
            os.path.normcase(os.path.normpath(os.fspath(path))),
            str(size),
            str(mtime_ns),
            str(version),
        )
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load(path: Path) -> tuple[bytes, bool]:
    """Return the ``SWF1`` body for one real audio file, and whether it was cached.

    Args:
        path: Real path of a regular file that the access check already allowed.

    Returns:
        The binary body and True when that body was read from the cache.

    Raises:
        WaveformUnavailable: No decoder could read samples. The audio file
            is not modified, and a failure is not written to the cache.
    """
    try:
        info = path.lstat()
    except OSError as exc:
        raise WaveformUnavailable() from exc
    overview = tags.read_serato_overview(os.fspath(path))
    key = cache_key(path, info.st_size, info.st_mtime_ns, ANALYZER_VERSION)
    cached = _read_cache(key)
    if cached is not None:
        return cached, True
    try:
        body = _render(path, overview)
    except (DecodeError, OSError, ValueError, WaveformUnavailable, subprocess.TimeoutExpired, miniaudio.DecodeError) as exc:
        raise WaveformUnavailable() from exc
    _write_cache(key, body)
    return body, False


def analyze_samples(samples: np.ndarray, sample_rate: int, overview: bytes | None = None) -> bytes:
    """Analyze one mono buffer and return an ``SWF1`` body.

    Args:
        samples: Mono samples in the range -1 to 1.
        sample_rate: Sample rate of ``samples``. It is resampled to 44100
            when it is something else.
        overview: Normalized Serato Overview payload (``01 05`` plus
            columns), or None.

    Returns:
        The binary body.

    Raises:
        WaveformUnavailable: ``samples`` has no samples, or the rate is not usable.
    """
    mono = _clean(samples)
    if sample_rate != ANALYZE_RATE:
        mono = _resample(mono, sample_rate, ANALYZE_RATE)
    rows, total = _collect(iter((mono,)))
    if total <= 0 or rows.shape[0] == 0:
        raise WaveformUnavailable()
    return _pack(rows, total, overview)


class WaveformHeader(TypedDict):
    """Integer fields in an ``SWF1`` header."""

    header_bytes: int
    version: int
    flags: int
    analyzer_version: int
    sample_rate: int
    detail_hz_milli: int
    duration_ms: int
    detail_count: int
    overview_count: int
    serato_columns: int
    serato_bands: int
    reserved: int
    low_hz_milli: int
    high_hz_milli: int


class WaveformParts(WaveformHeader):
    """Header fields plus the three uint8 sections."""

    detail: bytes
    overview: bytes
    serato: bytes


def parse_waveform(body: bytes) -> WaveformParts:
    """Split an ``SWF1`` body into its header fields and sections.

    Args:
        body: Bytes from :func:`load` or :func:`analyze_samples`.

    Returns:
        Header integers plus ``detail``, ``overview``, and ``serato`` as
        raw uint8 bytes.

    Raises:
        ValueError: The magic, header size, or section lengths do not match.
    """
    header = _header(body)
    offset = HEADER_BYTES
    detail_n = int(header["detail_count"]) * 6
    overview_n = int(header["overview_count"]) * 6
    serato_n = int(header["serato_columns"]) * int(header["serato_bands"])
    end = offset + detail_n + overview_n + serato_n
    if len(body) != end:
        raise ValueError("waveform section lengths do not match the body")
    detail = body[offset:offset + detail_n]
    offset += detail_n
    overview = body[offset:offset + overview_n]
    offset += overview_n
    serato = body[offset:offset + serato_n]
    parts: WaveformParts = {
        "header_bytes": header["header_bytes"],
        "version": header["version"],
        "flags": header["flags"],
        "analyzer_version": header["analyzer_version"],
        "sample_rate": header["sample_rate"],
        "detail_hz_milli": header["detail_hz_milli"],
        "duration_ms": header["duration_ms"],
        "detail_count": header["detail_count"],
        "overview_count": header["overview_count"],
        "serato_columns": header["serato_columns"],
        "serato_bands": header["serato_bands"],
        "reserved": header["reserved"],
        "low_hz_milli": header["low_hz_milli"],
        "high_hz_milli": header["high_hz_milli"],
        "detail": detail,
        "overview": overview,
        "serato": serato,
    }
    return parts


def describe(body: bytes, *, cached: bool) -> dict[str, object]:
    """Return JSON metadata for an ``SWF1`` body.

    Args:
        body: Bytes from :func:`load`.
        cached: True when ``body`` was read from the cache.

    Returns:
        Counts, rates, and band names. The samples stay in the binary body.
    """
    header = _header(body)
    return {
        "available": True,
        "error": None,
        "format": "SWF1",
        "cached": cached,
        "header_bytes": HEADER_BYTES,
        "version": int(header["version"]),
        "analyzer_version": int(header["analyzer_version"]),
        "sample_rate": int(header["sample_rate"]),
        "detail_hz": int(header["detail_hz_milli"]) / 1000,
        "low_hz": int(header["low_hz_milli"]) / 1000,
        "high_hz": int(header["high_hz_milli"]) / 1000,
        "duration_ms": int(header["duration_ms"]),
        "detail_points": int(header["detail_count"]),
        "overview_points": int(header["overview_count"]),
        "serato_overview_columns": int(header["serato_columns"]),
        "serato_overview_bands": int(header["serato_bands"]),
        "bands": ["low_peak", "low_rms", "mid_peak", "mid_rms", "high_peak", "high_rms"],
    }


def overview_document(path: Path) -> dict[str, object]:
    """Return the file's Serato Overview without decoding audio.

    Args:
        path: Real path of a library file. It is opened read-only.

    Returns:
        ``available`` false when the tag is missing. Otherwise the version,
        column count, 16 bands, and one list of 16 integers per column.
    """
    raw = tags.read_serato_overview(os.fspath(path))
    if not raw or len(raw) < 2:
        return {"available": False, "version": [1, 5], "columns": 0, "bands": _SERATO_BANDS, "data": []}
    columns = _serato_columns(raw)
    data = [list(columns[index:index + _SERATO_BANDS]) for index in range(0, len(columns), _SERATO_BANDS)]
    return {
        "available": True,
        "version": [1, 5],
        "columns": len(data),
        "bands": _SERATO_BANDS,
        "data": data,
    }


def wave_chunks(path: Path) -> Iterator[np.ndarray]:
    """Read a PCM WAV with the stdlib and yield mono float chunks.

    The macOS container decoder uses this after ``afconvert`` has written
    a temporary WAV. The file is opened read-only.

    Args:
        path: WAV path.

    Returns:
        Chunks at :data:`ANALYZE_RATE`.

    Raises:
        DecodeError: The file is not a PCM WAV this reader understands.
    """
    return _open_wave(path)


def mix_pcm(raw: bytes, width: int, channels: int, *, little: bool) -> np.ndarray:
    """Convert interleaved PCM to mono floats in -1 to 1.

    Args:
        raw: Interleaved frames.
        width: Bytes per sample. 1, 2, or 4.
        channels: Channel count. More than one is averaged.
        little: True for little-endian integer PCM.

    Returns:
        Mono float samples.

    Raises:
        DecodeError: ``width`` is not 1, 2, or 4.
    """
    return _pcm_bytes(raw, width, channels, little=little)


def resample_mono(samples: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    """Resample mono samples with linear interpolation.

    Args:
        samples: Mono samples.
        source_rate: Current sample rate.
        target_rate: Desired sample rate.

    Returns:
        Samples at ``target_rate``.

    Raises:
        DecodeError: ``source_rate`` is not a positive number.
    """
    return _resample(samples, source_rate, target_rate)


def cache_directory_blocked(directory: Path) -> bool:
    """Return whether a temp or cache directory would land in the Serato folder.

    Args:
        directory: Directory that would receive a new file.

    Returns:
        True when that directory must not be written.
    """
    return _cache_blocked(directory)


def native_container_opener() -> Callable[[Path], Iterator[np.ndarray]] | None:
    """Return the built-in decoder for m4a, AAC, and ALAC, or None on Linux.

    macOS uses AudioToolbox through ``afconvert``. Windows uses Media
    Foundation. Linux has no built-in decoder for these suffixes, so the
    caller tries ffmpeg only when it is already on ``PATH``.

    Returns:
        The opener for this operating system, or None.
    """
    if sys.platform == "darwin":
        return waveform_native.open_apple
    if sys.platform == "win32":
        return waveform_native.open_media_foundation
    return None


def iter_pcm(path: Path) -> Generator[np.ndarray, None, None]:
    """Yield mono float samples at 44100 Hz for one file.

    Args:
        path: Real audio path. It is opened read-only, in chunks.

    Yields:
        One chunk of mono samples. The concatenation is the track.

    Raises:
        WaveformUnavailable: Every decoder refused the file. On Linux that
            includes an AAC-family file when ffmpeg is not on ``PATH``.
    """
    suffix = path.suffix.lower()
    openers: list[Callable[[Path], Iterator[np.ndarray]]] = []
    if suffix in AAC_FAMILY_SUFFIXES:
        native = native_container_opener()
        if native is not None:
            openers.append(native)
    else:
        openers.append(_open_miniaudio)
        if suffix == ".wav":
            openers.append(_open_wave)
        elif suffix in {".aiff", ".aif"}:
            openers.append(_open_aiff)
    openers.append(_open_ffmpeg)
    for opener in openers:
        try:
            stream = opener(path)
        except DecodeError:
            continue
        yield from stream
        return
    raise WaveformUnavailable()


def _render(path: Path, overview: bytes | None) -> bytes:
    """Decode ``path`` and pack the waveform.

    Args:
        path: Real audio path.
        overview: Normalized Serato Overview payload, or None.

    Returns:
        The ``SWF1`` body.

    Raises:
        WaveformUnavailable: The decoder produced no samples.
        DecodeError: A decoder refused the file while samples were still arriving.
        miniaudio.DecodeError: miniaudio failed after the file had opened.
        subprocess.TimeoutExpired: ffmpeg did not exit after its stdout closed.
    """
    stream = iter_pcm(path)
    try:
        rows, total = _collect(stream)
    finally:
        close = getattr(stream, "close", None)
        if callable(close):
            close()
    if total <= 0 or rows.shape[0] == 0:
        raise WaveformUnavailable()
    return _pack(rows, total, overview)


def analyze_chunks(chunks: Iterator[np.ndarray], overview: bytes | None = None) -> bytes:
    """Analyze mono chunks that are already at 44100 Hz.

    Args:
        chunks: Sample blocks. They are consumed one block at a time.
        overview: Normalized Serato Overview payload, or None.

    Returns:
        The ``SWF1`` body.

    Raises:
        WaveformUnavailable: The chunks contained no samples.
    """
    rows, total = _collect(chunks)
    if total <= 0 or rows.shape[0] == 0:
        raise WaveformUnavailable()
    return _pack(rows, total, overview)


def partial_cache_name(dest: Path) -> Path:
    """Return a unique temporary path beside a cache file.

    Args:
        dest: Final cache file.

    Returns:
        The path :func:`_write_cache` replaces into ``dest``.
    """
    return _partial_cache_path(dest)


def _collect(chunks: Iterator[np.ndarray]) -> tuple[np.ndarray, int]:
    """Turn a stream of mono samples into peak and RMS rows.

    Args:
        chunks: Mono chunks at :data:`ANALYZE_RATE`. Samples are gathered
            into one FFT block, filtered, and reduced before the next block
            is kept. The PCM is not stored.

    Returns:
        A float array of shape ``(N, 6)`` and the number of input samples.
        Columns are low peak, low RMS, mid peak, mid RMS, high peak, high RMS.
        A remainder shorter than one detail point is not a row.
    """
    fft_n, spectra = _fft_plan()
    block_len = fft_n - (_TAPS - 1)
    hop = ANALYZE_RATE // DETAIL_HZ
    state = np.zeros(_TAPS - 1, dtype=np.float64)
    carry = np.zeros(0, dtype=np.float64)
    pending = [np.zeros(0, dtype=np.float64) for _ in range(3)]
    peaks: list[list[np.ndarray]] = [[], [], []]
    rms: list[list[np.ndarray]] = [[], [], []]
    total = 0
    for chunk in chunks:
        mono = _clean(chunk)
        if mono.size == 0:
            continue
        total += int(mono.size)
        carry = np.concatenate((carry, mono))
        while carry.size >= block_len:
            block = carry[:block_len]
            carry = carry[block_len:]
            filtered, state = _fft_filter(block, state, spectra, fft_n)
            _reduce_hops(filtered, pending, peaks, rms, hop)
    if carry.size:
        filtered, state = _fft_filter(carry, state, spectra, fft_n)
        _reduce_hops(filtered, pending, peaks, rms, hop)
    return _stack_rows(peaks, rms), total


def _pack(rows: np.ndarray, total_samples: int, overview: bytes | None) -> bytes:
    """Pack detail, overview, and the Serato tag into ``SWF1``.

    Args:
        rows: Float rows from :func:`_collect`.
        total_samples: Input samples at :data:`ANALYZE_RATE`.
        overview: Normalized Serato Overview payload, or None.

    Returns:
        The binary body.
    """
    detail = _quantize(rows)
    overview_rows = _downsample(rows, OVERVIEW_POINTS)
    overview_bytes = _quantize(overview_rows)
    serato = _serato_columns(overview)
    flags = 0
    if detail:
        flags |= _FLAG_DETAIL
    if overview_bytes:
        flags |= _FLAG_OVERVIEW
    bands = _SERATO_BANDS if serato else 0
    if serato:
        flags |= _FLAG_SERATO
    duration_ms = int(round(total_samples * 1000 / ANALYZE_RATE))
    header = _HEADER.pack(
        b"SWF1",
        HEADER_BYTES,
        1,
        flags,
        ANALYZER_VERSION,
        ANALYZE_RATE,
        DETAIL_HZ * 1000,
        duration_ms,
        rows.shape[0],
        overview_rows.shape[0],
        len(serato) // _SERATO_BANDS if serato else 0,
        bands,
        0,
        int(LOW_HZ * 1000),
        int(HIGH_HZ * 1000),
    )
    return header + bytes(16) + detail + overview_bytes + serato


def _header(body: bytes) -> WaveformHeader:
    """Read the fixed ``SWF1`` header.

    Args:
        body: Waveform bytes.

    Returns:
        Header fields as integers.

    Raises:
        ValueError: The body is shorter than the header or the magic is wrong.
    """
    if len(body) < HEADER_BYTES or body[:4] != b"SWF1":
        raise ValueError("not a waveform")
    unpacked = _HEADER.unpack_from(body, 0)
    if int(unpacked[1]) != HEADER_BYTES:
        raise ValueError("unexpected waveform header size")
    header: WaveformHeader = {
        "header_bytes": int(unpacked[1]),
        "version": int(unpacked[2]),
        "flags": int(unpacked[3]),
        "analyzer_version": int(unpacked[4]),
        "sample_rate": int(unpacked[5]),
        "detail_hz_milli": int(unpacked[6]),
        "duration_ms": int(unpacked[7]),
        "detail_count": int(unpacked[8]),
        "overview_count": int(unpacked[9]),
        "serato_columns": int(unpacked[10]),
        "serato_bands": int(unpacked[11]),
        "reserved": int(unpacked[12]),
        "low_hz_milli": int(unpacked[13]),
        "high_hz_milli": int(unpacked[14]),
    }
    return header


def _quantize(rows: np.ndarray) -> bytes:
    """Scale float rows in the 0 to 1 range to uint8 bytes.

    Args:
        rows: Peak and RMS values. Values outside 0 to 1 are clipped.

    Returns:
        Row-major uint8 bytes, six values per row.
    """
    if rows.size == 0:
        return b""
    scaled = np.clip(np.rint(rows * 255.0), 0, 255).astype(np.uint8)
    return scaled.tobytes()


def _downsample(rows: np.ndarray, points: int) -> np.ndarray:
    """Bucket detail rows into at most ``points`` overview rows.

    Args:
        rows: Detail rows.
        points: Maximum overview rows.

    Returns:
        The same rows when there are fewer than ``points``. Otherwise
        exactly ``points`` rows. Even columns are the maximum peak. Odd
        columns are the root of the mean square of the detail RMS.
    """
    count = rows.shape[0]
    if count == 0 or count <= points:
        return rows
    out = np.zeros((points, rows.shape[1]), dtype=np.float64)
    base, extra = divmod(count, points)
    start = 0
    for index in range(points):
        width = base + (1 if index < extra else 0)
        window = rows[start:start + width]
        out[index, 0::2] = window[:, 0::2].max(axis=0)
        out[index, 1::2] = np.sqrt(np.mean(window[:, 1::2] ** 2, axis=0))
        start += width
    return out


def _serato_columns(overview: bytes | None) -> bytes:
    """Return the column bytes of a normalized Serato Overview.

    Args:
        overview: Payload starting with ``01 05``, or None.

    Returns:
        Column bytes with the two-byte version removed. Empty when the
        tag is missing or shorter than one column.
    """
    if not overview or len(overview) < 2 or overview[0] != 1 or overview[1] != 5:
        return b""
    body = overview[2:]
    cols = len(body) // _SERATO_BANDS
    if cols < 1:
        return b""
    return body[: cols * _SERATO_BANDS]


def _filters(sample_rate: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return the low, mid, and high FIR kernels for ``sample_rate``.

    Args:
        sample_rate: Samples per second. The kernels are cached for it.

    Returns:
        Three 1023-tap kernels. Low passes under 250 Hz. High passes over
        4 kHz. Mid is the band between those cuts.
    """
    found = _FILTERS.get(sample_rate)
    if found is not None:
        return found
    low = _lowpass(sample_rate, LOW_HZ)
    below_high = _lowpass(sample_rate, HIGH_HZ)
    high = -below_high
    high = high.copy()
    high[(_TAPS - 1) // 2] += 1.0
    mid = below_high - low
    packed = (low, mid, high)
    _FILTERS[sample_rate] = packed
    return packed


def _lowpass(sample_rate: int, cutoff: float) -> np.ndarray:
    """Build a windowed-sinc lowpass.

    Args:
        sample_rate: Samples per second.
        cutoff: Cutoff frequency in Hz.

    Returns:
        A unit-sum kernel of :data:`_TAPS` samples.
    """
    half = (_TAPS - 1) / 2.0
    slots = np.arange(_TAPS) - half
    kernel = np.sinc(2.0 * cutoff / sample_rate * slots)
    kernel *= np.hamming(_TAPS)
    kernel /= float(np.sum(kernel))
    return kernel


def _fast_length(size: int) -> int:
    """Return a FFT length at least ``size`` whose factors are 2, 3, and 5.

    Args:
        size: Minimum length.

    Returns:
        The next smooth length. PocketFFT is fastest on those sizes.
    """
    if size < 1:
        return 1
    candidate = size
    while True:
        value = candidate
        for factor in (2, 3, 5):
            while value % factor == 0:
                value //= factor
        if value == 1:
            return candidate
        candidate += 1


def _fft_plan() -> tuple[int, list[np.ndarray]]:
    """Return the FFT length and the three band spectra.

    Returns:
        A length of 40,000 (already 2-3-5 smooth) and the rFFT of each
        1023-tap kernel at that length. The plan is built once per process.
    """
    global _fft_plan_cache
    if _fft_plan_cache is not None:
        return _fft_plan_cache
    fft_n = _fast_length(40_000)
    kernels = _filters(ANALYZE_RATE)
    spectra = [np.fft.rfft(kernel, n=fft_n) for kernel in kernels]
    _fft_plan_cache = (fft_n, spectra)
    return _fft_plan_cache


def _fft_filter(
    samples: np.ndarray,
    state: np.ndarray,
    spectra: list[np.ndarray],
    fft_n: int,
) -> tuple[list[np.ndarray], np.ndarray]:
    """Filter one block with overlap-save.

    Args:
        samples: Mono samples. At most ``fft_n - len(state)`` long.
        state: The previous ``_TAPS - 1`` input samples. The same history
            feeds every band.
        spectra: rFFT of the low, mid, and high kernels.
        fft_n: FFT length.

    Returns:
        Three filtered arrays the same length as ``samples``, and the
        input history for the next block. The forward transform is shared.
    """
    count = int(samples.size)
    history = int(state.size)
    block = np.zeros(fft_n, dtype=np.float64)
    block[:history] = state
    block[history:history + count] = samples
    spectrum = np.fft.rfft(block)
    bands: list[np.ndarray] = []
    for kernel in spectra:
        filtered = np.fft.irfft(spectrum * kernel, n=fft_n)
        bands.append(filtered[history:history + count])
    joined = np.concatenate((state, samples))
    return bands, joined[-history:].copy()


def _reduce_hops(
    bands: list[np.ndarray],
    pending: list[np.ndarray],
    peaks: list[list[np.ndarray]],
    rms: list[list[np.ndarray]],
    hop: int,
) -> None:
    """Turn filtered samples into one peak and one RMS per hop.

    Args:
        bands: Low, mid, and high samples for this block.
        pending: Samples shorter than one hop, kept from the previous block.
        peaks: Peak pieces collected so far, one list per band.
        rms: RMS pieces collected so far, one list per band.
        hop: Samples per detail point.

    Returns:
        None. Complete hops are appended. A short tail stays in ``pending``.
    """
    for index, band in enumerate(bands):
        buf = np.concatenate((pending[index], band))
        usable = (buf.size // hop) * hop
        if usable:
            frames = buf[:usable].reshape(-1, hop)
            peaks[index].append(np.max(np.abs(frames), axis=1))
            rms[index].append(np.sqrt(np.mean(frames * frames, axis=1)))
        pending[index] = buf[usable:].copy()


def _stack_rows(peaks: list[list[np.ndarray]], rms: list[list[np.ndarray]]) -> np.ndarray:
    """Join hop pieces into one ``(N, 6)`` array.

    Args:
        peaks: Peak pieces per band.
        rms: RMS pieces per band.

    Returns:
        Columns low peak, low RMS, mid peak, mid RMS, high peak, high RMS.
        Empty when no hop was completed.
    """
    if not peaks[0]:
        return np.zeros((0, 6), dtype=np.float64)
    count = int(sum(piece.size for piece in peaks[0]))
    rows = np.empty((count, 6), dtype=np.float64)
    for index in range(3):
        rows[:, index * 2] = np.concatenate(peaks[index])
        rows[:, index * 2 + 1] = np.concatenate(rms[index])
    return rows


def _clean(chunk: object) -> np.ndarray:
    """Return a 1-D float array with non-finite values replaced by zero.

    Args:
        chunk: A buffer of samples. Multi-dimensional input is flattened.

    Returns:
        A float64 array clipped to -4 to 4.
    """
    values = np.asarray(chunk, dtype=np.float64).reshape(-1)
    if values.size == 0:
        return values
    np.nan_to_num(values, copy=False, nan=0.0, posinf=0.0, neginf=0.0)
    np.clip(values, -4.0, 4.0, out=values)
    return values


def _resample(samples: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    """Linearly resample one mono chunk.

    Args:
        samples: Mono samples.
        source_rate: Current sample rate.
        target_rate: Desired sample rate.

    Returns:
        Samples at ``target_rate``. An empty input stays empty.

    Raises:
        DecodeError: ``source_rate`` is not a positive number.
    """
    if samples.size == 0 or source_rate == target_rate:
        return samples
    if source_rate <= 0:
        raise DecodeError()
    out_n = int(round(samples.size * target_rate / source_rate))
    if out_n <= 0:
        return np.zeros(0, dtype=np.float64)
    source_x = np.linspace(0.0, 1.0, samples.size, endpoint=False)
    target_x = np.linspace(0.0, 1.0, out_n, endpoint=False)
    return np.interp(target_x, source_x, samples)


def _open_miniaudio(path: Path) -> Iterator[np.ndarray]:
    """Open ``path`` with miniaudio and yield mono float chunks.

    Args:
        path: Real audio path.

    Returns:
        An iterator of chunks. The file is not opened until the first read,
        which this function performs so a refusal happens before a yield.

    Raises:
        DecodeError: miniaudio cannot decode the file.
    """
    try:
        stream = miniaudio.stream_file(
            os.fspath(path),
            output_format=miniaudio.SampleFormat.FLOAT32,
            nchannels=1,
            sample_rate=ANALYZE_RATE,
            frames_to_read=DECODE_FRAMES,
        )
        iterator = iter(stream)
        first = next(iterator)
    except StopIteration:
        return iter(())
    except Exception as exc:
        raise DecodeError() from exc

    def chunks() -> Iterator[np.ndarray]:
        yield _clean(first)
        for block in iterator:
            yield _clean(block)

    return chunks()


def _open_wave(path: Path) -> Iterator[np.ndarray]:
    """Read a PCM WAV with the stdlib and yield mono float chunks.

    Args:
        path: Real ``.wav`` path.

    Returns:
        An iterator of chunks at :data:`ANALYZE_RATE`.

    Raises:
        DecodeError: The file is not a PCM WAV this reader understands.
    """
    try:
        handle = wave.open(os.fspath(path), "rb")
    except (wave.Error, EOFError, OSError) as exc:
        raise DecodeError() from exc
    channels = handle.getnchannels()
    width = handle.getsampwidth()
    rate = handle.getframerate()
    if channels < 1 or width not in (1, 2, 4) or rate <= 0:
        handle.close()
        raise DecodeError()

    def chunks() -> Iterator[np.ndarray]:
        try:
            while True:
                try:
                    raw = handle.readframes(DECODE_FRAMES)
                except (wave.Error, EOFError) as exc:
                    raise WaveformUnavailable() from exc
                if not raw:
                    break
                yield _resample(_pcm_bytes(raw, width, channels, little=True), rate, ANALYZE_RATE)
        finally:
            handle.close()

    return chunks()


def _open_aiff(path: Path) -> Iterator[np.ndarray]:
    """Read a 16-bit PCM AIFF and yield mono float chunks.

    Args:
        path: Real ``.aiff`` or ``.aif`` path.

    Returns:
        An iterator of chunks at :data:`ANALYZE_RATE`. Audio is read from
        the SSND chunk in pieces. The whole file is not loaded.

    Raises:
        DecodeError: The file is not a plain 16-bit AIFF.
    """
    try:
        handle = path.open("rb")
    except OSError as exc:
        raise DecodeError() from exc
    try:
        located = _aiff_ssnd(handle)
    except DecodeError:
        handle.close()
        raise
    channels, rate, ssnd_at = located
    frame = 2 * channels

    def chunks() -> Iterator[np.ndarray]:
        try:
            handle.seek(ssnd_at)
            while True:
                raw = handle.read(frame * DECODE_FRAMES)
                if not raw:
                    break
                usable = len(raw) - (len(raw) % frame)
                if usable <= 0:
                    break
                yield _resample(_pcm_bytes(raw[:usable], 2, channels, little=False), rate, ANALYZE_RATE)
        finally:
            handle.close()

    return chunks()


def _aiff_ssnd(handle: BinaryIO) -> tuple[int, int, int]:
    """Find the 16-bit PCM payload inside an AIFF file.

    Args:
        handle: A binary file positioned at the start.

    Returns:
        Channel count, sample rate, and the absolute offset of the PCM.

    Raises:
        DecodeError: The container is not a 16-bit AIFF, or COMM/SSND is missing.
    """
    header = handle.read(12)
    if len(header) < 12 or header[:4] != b"FORM" or header[8:12] != b"AIFF":
        raise DecodeError()
    channels: int | None = None
    rate: int | None = None
    ssnd_at: int | None = None
    for _ in range(64):
        chunk = handle.read(8)
        if len(chunk) < 8:
            break
        kind = chunk[:4]
        size = int.from_bytes(chunk[4:8], "big")
        start = handle.tell()
        if size < 0 or start + size < start:
            break
        if kind == b"COMM" and size >= 18:
            comm = handle.read(18)
            if len(comm) < 18:
                break
            channels = int.from_bytes(comm[0:2], "big")
            width = int.from_bytes(comm[6:8], "big")
            rate = _ieee80(comm[8:18])
            if width != 16 or channels < 1 or rate <= 0:
                raise DecodeError()
        elif kind == b"SSND" and size >= 8:
            offset_bytes = handle.read(8)
            if len(offset_bytes) < 8:
                break
            data_offset = int.from_bytes(offset_bytes[:4], "big")
            ssnd_at = handle.tell() + data_offset
        next_at = start + size + (size & 1)
        handle.seek(next_at)
    if channels is None or rate is None or ssnd_at is None:
        raise DecodeError()
    return channels, rate, ssnd_at


def _ieee80(raw: bytes) -> int:
    """Decode an AIFF 80-bit sample rate to an integer.

    Args:
        raw: Ten bytes from the COMM chunk.

    Returns:
        The nearest integer sample rate. Zero when the field is zero.
    """
    exponent = int.from_bytes(raw[0:2], "big") & 0x7FFF
    mantissa = int.from_bytes(raw[2:10], "big")
    if exponent == 0 or mantissa == 0:
        return 0
    power = exponent - 16383 - 63
    return int(round(mantissa * (2.0 ** power)))


def _pcm_bytes(raw: bytes, width: int, channels: int, *, little: bool) -> np.ndarray:
    """Convert interleaved PCM to mono floats in -1 to 1.

    Args:
        raw: Interleaved frames.
        width: Bytes per sample. 1, 2, or 4.
        channels: Channel count. More than one is averaged.
        little: True for WAV little-endian. False for AIFF big-endian.

    Returns:
        Mono float samples.

    Raises:
        DecodeError: ``width`` is not 1, 2, or 4.
    """
    if width == 1:
        data = np.frombuffer(raw, dtype=np.uint8).astype(np.float64)
        data = (data - 128.0) / 128.0
    elif width == 2:
        kind = "<i2" if little else ">i2"
        data = np.frombuffer(raw, dtype=kind).astype(np.float64) / 32768.0
    elif width == 4:
        kind = "<i4" if little else ">i4"
        data = np.frombuffer(raw, dtype=kind).astype(np.float64) / 2147483648.0
    else:
        raise DecodeError()
    if channels > 1:
        usable = (data.size // channels) * channels
        data = data[:usable].reshape(-1, channels).mean(axis=1)
    return data


def _open_ffmpeg(path: Path) -> Iterator[np.ndarray]:
    """Decode ``path`` with ffmpeg when it is already on ``PATH``.

    Args:
        path: Real audio path. It is an input argument, not a shell string.

    Returns:
        An iterator of float32-decoded mono chunks. An empty iterator means
        ffmpeg produced no samples.

    Raises:
        DecodeError: ``ffmpeg`` is not on ``PATH``, or the process could not start.
    """
    exe = shutil.which("ffmpeg")
    if not exe:
        raise DecodeError()
    command = [
        exe,
        "-nostdin",
        "-v",
        "error",
        "-i",
        os.fspath(path),
        "-f",
        "f32le",
        "-ac",
        "1",
        "-ar",
        str(ANALYZE_RATE),
        "-",
    ]
    try:
        proc = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            shell=False,
        )
    except OSError as exc:
        raise DecodeError() from exc
    stdout = proc.stdout
    if stdout is None:
        proc.kill()
        raise DecodeError()

    def chunks() -> Iterator[np.ndarray]:
        try:
            while True:
                raw = stdout.read(DECODE_FRAMES * 4)
                if not raw:
                    break
                usable = len(raw) - (len(raw) % 4)
                if usable:
                    yield _clean(np.frombuffer(raw[:usable], dtype="<f4"))
            try:
                proc.wait(timeout=60)
            except subprocess.TimeoutExpired as exc:
                raise WaveformUnavailable() from exc
        finally:
            try:
                stdout.close()
            except OSError:
                pass
            _reap_ffmpeg(proc)

    return chunks()


def _reap_ffmpeg(proc: subprocess.Popen[bytes]) -> None:
    """Kill ffmpeg if it is still running, then wait until it exits.

    Args:
        proc: Process started by :func:`_open_ffmpeg`.

    Returns:
        None. A second wait covers a process that ignored the first kill.
        A timeout after that is ignored so closing the generator cannot
        become a 500.
    """
    if proc.poll() is None:
        proc.kill()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            return


def _read_cache(key: str) -> bytes | None:
    """Return a cached body, or None when the entry is missing or not ``SWF1``.

    Args:
        key: Digest from :func:`cache_key`.

    Returns:
        The stored bytes when the header and section lengths match. None
        when the cache cannot be used. The Serato folder is not read.
    """
    dest = _cache_path(key)
    if dest is None or not dest.is_file():
        return None
    try:
        body = dest.read_bytes()
        parse_waveform(body)
    except (OSError, ValueError):
        return None
    return body


def _partial_cache_path(dest: Path) -> Path:
    """Return a temporary name that no other writer in this process uses.

    Args:
        dest: Final cache file.

    Returns:
        A sibling path whose name includes the process id, the thread id,
        and a process-wide counter. ``os.replace`` publishes ``dest``.
    """
    ticket = next(_PARTIAL_SEQ)
    return dest.with_name(f"{dest.name}.{os.getpid()}.{threading.get_ident()}.{ticket}.partial")


def _write_cache(key: str, body: bytes) -> None:
    """Store ``body`` outside the Serato library folder.

    Args:
        key: Digest from :func:`cache_key`.
        body: A complete ``SWF1`` body.

    A cache directory that resolves inside the library folder is not
    created. A failed write leaves the audio file alone and keeps the
    response. The previous cache file is replaced only after the new
    bytes are in place.
    """
    dest = _cache_path(key)
    if dest is None:
        return
    temporary = _partial_cache_path(dest)
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if _cache_blocked(dest.parent):
            return
        temporary.write_bytes(body)
        os.replace(temporary, dest)
    except OSError:
        logger.warning("Waveform cache was not written.")
        try:
            temporary.unlink()
        except OSError:
            return


def _cache_path(key: str) -> Path | None:
    """Return the cache file for ``key``, or None when it must not be written.

    Args:
        key: Lowercase SHA-256 hex.

    Returns:
        A path under the app data ``waveforms`` directory. None when the
        key is not hex, or when that directory would sit inside the Serato
        library folder.
    """
    if len(key) != 64 or any(char not in "0123456789abcdef" for char in key):
        return None
    root = _cache_root()
    if root is None:
        return None
    return root / key[:2] / key


def _cache_root() -> Path | None:
    """Return the waveform cache directory, or None when it is not safe.

    Returns:
        The real path of ``<config>/waveforms``. None when that path is the
        Serato library folder, is inside it, or contains it. The directory
        is not created here.
    """
    candidate = app_config.config_dir() / "waveforms"
    try:
        root = Path(os.path.realpath(candidate))
        library_root = Path(os.path.realpath(Path(library.MASTER).parent))
    except OSError:
        return None
    if root == library_root or _inside(root, library_root) or _inside(library_root, root):
        return None
    return root


def _cache_blocked(directory: Path) -> bool:
    """Return whether ``directory`` resolved into the Serato library folder.

    Args:
        directory: Directory that is about to receive a cache file.

    Returns:
        True when the real path is the library folder or sits inside it.
        The caller writes nothing in that case.
    """
    try:
        landed = Path(os.path.realpath(directory))
        library_root = Path(os.path.realpath(Path(library.MASTER).parent))
    except OSError:
        return True
    return landed == library_root or _inside(landed, library_root) or _inside(library_root, landed)


def _inside(child: Path, parent: Path) -> bool:
    """Return whether ``child`` is strictly inside ``parent``.

    Args:
        child: Real path.
        parent: Real directory.

    Returns:
        True when ``parent`` is the common path and the two are not equal.
        A sibling whose name only starts with the parent name is False.
    """
    child_text = os.path.normcase(os.path.normpath(os.fspath(child)))
    parent_text = os.path.normcase(os.path.normpath(os.fspath(parent)))
    if child_text == parent_text:
        return False
    try:
        return os.path.commonpath([child_text, parent_text]) == parent_text
    except ValueError:
        return False


if _HEADER.size != 48:
    raise RuntimeError("waveform header struct drifted")
