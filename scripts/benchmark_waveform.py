#!/usr/bin/env python3
"""Time a cold waveform analysis and print the peak traced memory.

The default length is 60 minutes of a 440 Hz sine in a temporary WAV.
``--seconds`` shortens that for a quick check. The process writes the WAV
in one-minute pieces so the PCM is not held as one array. The report is
wall time and tracemalloc peak for ``waveform.load``.
"""

from __future__ import annotations

import argparse
import math
import resource
import tempfile
import time
import tracemalloc
import wave
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import numpy as np

import waveform


def _write_wav(path: Path, seconds: int, channels: int) -> None:
    """Write ``seconds`` of 16-bit audio at 44100 Hz.

    Args:
        path: File to replace.
        seconds: Duration. Each minute is generated and written, then dropped.
        channels: 1 or 2. Stereo is two copies of the same sine.
    """
    rate = 44100
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        remaining = seconds
        while remaining:
            piece = min(60, remaining)
            count = rate * piece
            times = np.arange(count) / rate
            mono = np.sin(2 * math.pi * 440.0 * times)
            if channels == 1:
                samples = mono
            else:
                samples = np.column_stack((mono, mono)).reshape(-1)
            frames = np.clip(np.rint(samples * 32767.0), -32768, 32767).astype("<i2")
            handle.writeframes(frames.tobytes())
            remaining -= piece


def main() -> None:
    """Analyze one temporary WAV and print time and peak memory."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=int, default=3600)
    parser.add_argument("--channels", type=int, default=1)
    args = parser.parse_args()
    if args.seconds < 1:
        raise SystemExit("--seconds must be at least 1")
    if args.channels not in (1, 2):
        raise SystemExit("--channels must be 1 or 2")
    with tempfile.TemporaryDirectory() as raw:
        path = Path(raw) / "bench.wav"
        _write_wav(path, args.seconds, args.channels)
        tracemalloc.start()
        started = time.perf_counter()
        body, cached = waveform.load(path)
        elapsed = time.perf_counter() - started
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    parsed = waveform.parse_waveform(body)
    print(f"seconds={args.seconds}")
    print(f"channels={args.channels}")
    print(f"wall_s={elapsed:.3f}")
    print(f"tracemalloc_peak_mb={peak / (1024 * 1024):.2f}")
    print(f"ru_maxrss_mb={rss_kb / 1024:.2f}")
    print(f"cached={cached}")
    print(f"detail_points={parsed['detail_count']}")


if __name__ == "__main__":
    main()
