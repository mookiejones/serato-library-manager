"""Types for the parts of miniaudio this program calls.

The package is imported at runtime. This stub is what strict checking sees.
It covers the decoder stream and the error that stream can raise.
"""

from collections.abc import Iterator
from enum import Enum
from typing import Any


class SampleFormat(Enum):
    """Sample formats ``stream_file`` can emit."""

    UNKNOWN = 0
    UNSIGNED8 = 1
    SIGNED16 = 2
    SIGNED24 = 3
    SIGNED32 = 4
    FLOAT32 = 5


class DecodeError(Exception):
    """miniaudio could not decode a file, including after some samples."""

    args: tuple[Any, ...]


def stream_file(
    filename: str,
    output_format: SampleFormat = ...,
    nchannels: int = ...,
    sample_rate: int = ...,
    frames_to_read: int = ...,
    dither: Any = ...,
    seek_frame: int = ...,
) -> Iterator[Any]:
    """Yield decoded frames.

    The iterator raises :class:`DecodeError` when the decoder fails,
    including after the first chunk has already been produced.
    """
    ...
