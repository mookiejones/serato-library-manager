"""OS decoders for m4a, AAC, and ALAC waveforms.

miniaudio does not open these suffixes. This module reads them without
adding a package and without bundling ffmpeg.

macOS runs ``/usr/bin/afconvert`` (AudioToolbox). The command writes a
16-bit mono WAV into a directory created by ``tempfile.TemporaryDirectory``
and the stdlib ``wave`` reader streams that file. Windows reads PCM in
memory through Media Foundation (``mfplat.dll`` and ``mfreadwrite.dll``)
with ``ctypes``. Linux has no decoder here.

A temp directory uses the prefix ``serato-waveform-``. It is removed when
the iterator finishes, when it is closed, and when conversion fails. The
WAV is never placed beside the audio file and never inside the Serato
library folder. ``encode_aac_m4a`` is the Windows fixture writer used by
tests. The server does not call it.
"""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import wave
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, Callable, NoReturn, Protocol, cast

import numpy as np

TEMP_PREFIX = "serato-waveform-"
_AFCONVERT_TIMEOUT_SECONDS = 300
_MF_VERSION = 0x00020070
_MFSTARTUP_NOSOCKET = 0x1
_FIRST_AUDIO = 0xFFFFFFFD
_ALL_STREAMS = 0xFFFFFFFE
_END_OF_STREAM = 0x00000002
_STREAM_ERROR = 0x00000001
_TYPE_CHANGED = 0x00000020
_RPC_E_CHANGED_MODE = 0x80010106
_MAX_BUFFER = 32 * 1024 * 1024

# IMFSourceReader / IMFSinkWriter / IMFAttributes indexes include IUnknown.
_RELEASE = 2
_GET_UINT32 = 7
_GET_GUID = 10
_SET_UINT32 = 21
_SET_GUID = 24
_LOCK = 3
_UNLOCK = 4
_SET_LENGTH = 6
_SET_SAMPLE_TIME = 36
_SET_SAMPLE_DURATION = 38
_CONVERT_BUFFER = 41
_ADD_BUFFER = 42
_READER_SET_SELECTION = 4
_READER_GET_CURRENT = 6
_READER_SET_CURRENT = 7
_READER_READ = 9
_WRITER_ADD_STREAM = 3
_WRITER_SET_INPUT = 4
_WRITER_BEGIN = 5
_WRITER_WRITE = 6
_WRITER_FINALIZE = 11

_ole32_dll: ctypes.CDLL | None = None
_mfplat_dll: ctypes.CDLL | None = None
_mfreadwrite_dll: ctypes.CDLL | None = None
_dll_lock = threading.Lock()


class _GUID(ctypes.Structure):
    """A Windows GUID, laid out the way ``mfobjects.idl`` defines it."""

    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_uint8 * 8),
    ]


def _guid(data1: int, data2: int, data3: int, data4: bytes) -> _GUID:
    """Build one GUID.

    Args:
        data1: First 32-bit field.
        data2: First 16-bit field.
        data3: Second 16-bit field.
        data4: Eight trailing bytes.

    Returns:
        The structure. Callers keep the result alive for the COM call.
    """
    value = _GUID()
    value.Data1 = data1
    value.Data2 = data2
    value.Data3 = data3
    value.Data4[:] = data4
    return value


_MAJOR = _guid(0x48EBA18E, 0xF8C9, 0x4687, bytes.fromhex("bf110a74c9f96a8f"))
_SUBTYPE = _guid(0xF7E34C9A, 0x42E8, 0x4714, bytes.fromhex("b74bcb29d72c35e5"))
_AUDIO = _guid(0x73647561, 0x0000, 0x0010, bytes.fromhex("800000aa00389b71"))
_PCM = _guid(0x00000001, 0x0000, 0x0010, bytes.fromhex("800000aa00389b71"))
_FLOAT = _guid(0x00000003, 0x0000, 0x0010, bytes.fromhex("800000aa00389b71"))
_AAC = _guid(0x00001610, 0x0000, 0x0010, bytes.fromhex("800000aa00389b71"))
_CHANNELS = _guid(0x37E48BF5, 0x645E, 0x4C5B, bytes.fromhex("89deada9e29b696a"))
_RATE = _guid(0x5FAEEAE7, 0x0290, 0x4C31, bytes.fromhex("9e8ac534f68d9dba"))
_BITS = _guid(0xF2DEB57F, 0x40FA, 0x4764, bytes.fromhex("aa33ed4f2d1ff669"))
_BLOCK = _guid(0x322DE230, 0x9EEB, 0x43BD, bytes.fromhex("ab7aff412251541d"))
_AVG = _guid(0x1BA85B5D, 0xFCE7, 0x4C43, bytes.fromhex("8a3e6f6c7e40b4a0"))
_AAC_PAYLOAD = _guid(0xBFBABE79, 0x7434, 0x4D1C, bytes.fromhex("94f072a3b9e17188"))
_CHANNEL_MASK = _guid(0x55FB5765, 0x644A, 0x4CAF, bytes.fromhex("8479938983bb1588"))


class PcmStream(Protocol):
    """PCM chunks that release their decoder when closed."""

    def __iter__(self) -> PcmStream:
        """Return this iterator.

        Returns:
            This object.
        """
        ...

    def __next__(self) -> np.ndarray:
        """Return the next mono chunk.

        Returns:
            Samples at the analyzer rate.
        """
        ...

    def close(self) -> None:
        """Release the decoder and delete any temp files."""
        ...


class _PcmFormat:
    """PCM layout reported by the source reader after the type is set."""

    def __init__(self, channels: int, rate: int, bits: int, floating: bool) -> None:
        """Store one negotiated PCM layout.

        Args:
            channels: Channel count.
            rate: Sample rate in Hz.
            bits: Bits per sample.
            floating: True when the subtype is IEEE float.
        """
        self.channels = channels
        self.rate = rate
        self.bits = bits
        self.floating = floating


def _fail(detail: str = "") -> NoReturn:
    """Raise the decoder refusal the waveform opener loop already catches.

    Args:
        detail: Short reason for a log or a test. It is not shown on the page.

    Raises:
        waveform.DecodeError: Always.
    """
    import waveform

    if detail:
        raise waveform.DecodeError(detail)
    raise waveform.DecodeError()


def _unavailable() -> NoReturn:
    """Raise the page-level waveform failure.

    Raises:
        waveform.WaveformUnavailable: Always. The sentence stays
        ``waveform unavailable``.
    """
    import waveform

    raise waveform.WaveformUnavailable()


def _contains(parent: Path, child: Path) -> bool:
    """Return whether ``child`` is ``parent`` or a file inside it.

    Args:
        parent: Directory that is allowed to contain ``child``.
        child: Path to test.

    Returns:
        True when the common path is ``parent``. A sibling whose name only
        starts with the parent name is False.
    """
    parent_text = os.path.normcase(os.path.normpath(os.fspath(parent)))
    child_text = os.path.normcase(os.path.normpath(os.fspath(child)))
    if child_text == parent_text:
        return True
    try:
        return os.path.commonpath([child_text, parent_text]) == parent_text
    except ValueError:
        return False


def _library_blocked(directory: Path) -> bool:
    """Return whether ``directory`` must not receive a temp file.

    Args:
        directory: Candidate directory.

    Returns:
        True when the waveform cache would also refuse this directory,
        including when the real path cannot be read.
    """
    import waveform

    return waveform.cache_directory_blocked(directory)


def separate_temp_output(source: Path, dest: Path) -> bool:
    """Return whether ``dest`` is a safe temp file for ``source``.

    Args:
        source: Audio file that must not gain a neighbor.
        dest: Proposed output file. Its parent has to exist.

    Returns:
        True when ``dest`` is inside the system temp directory, outside
        the Serato library folder, and not in the same directory as
        ``source``.
    """
    try:
        source_real = Path(os.path.realpath(source))
        dest_real = Path(os.path.realpath(dest))
        temp_root = Path(os.path.realpath(tempfile.gettempdir()))
    except OSError:
        return False
    if dest_real == source_real or dest_real.parent == source_real.parent:
        return False
    if not _contains(temp_root, dest_real):
        return False
    return not _library_blocked(dest_real.parent)


def destination_in_temp(dest: Path) -> bool:
    """Return whether ``dest`` may be written by the test encoder.

    Args:
        dest: Proposed output file.

    Returns:
        True when the parent is inside the system temp directory and is
        not the Serato library folder.
    """
    try:
        dest_real = Path(os.path.realpath(dest))
        temp_root = Path(os.path.realpath(tempfile.gettempdir()))
    except OSError:
        return False
    if dest_real == temp_root or not _contains(temp_root, dest_real.parent):
        return False
    return not _library_blocked(dest_real.parent)


def apple_converter() -> str | None:
    """Return an absolute ``afconvert`` path, preferring the system binary.

    Returns:
        ``/usr/bin/afconvert`` when it is executable. Otherwise an absolute
        ``afconvert`` from ``PATH``. None when neither exists. A relative
        path is not returned.
    """
    preferred = "/usr/bin/afconvert"
    if os.path.isfile(preferred) and os.access(preferred, os.X_OK):
        return preferred
    found = shutil.which("afconvert")
    if found and Path(found).is_absolute() and Path(found).name == "afconvert":
        return found
    return None


def afconvert_command(executable: str, source: Path, dest: Path) -> list[str]:
    """Build the AudioToolbox conversion argv.

    Args:
        executable: Absolute path whose file name is ``afconvert``.
        source: Input audio file. It is one argument, not a shell string.
        dest: WAV path that :func:`separate_temp_output` accepts.

    Returns:
        The argument vector. The output path is the last item, so
        ``afconvert`` cannot invent a file beside ``source``.

    Raises:
        waveform.DecodeError: The executable or the output path is refused.
    """
    exe = Path(executable)
    if not exe.is_absolute() or exe.name != "afconvert":
        _fail("afconvert path was refused")
    if not separate_temp_output(source, dest):
        _fail("afconvert output path was refused")
    return [
        os.fspath(exe),
        "-f",
        "WAVE",
        "-d",
        "LEI16@44100",
        "-c",
        "1",
        os.fspath(source),
        os.fspath(dest),
    ]


class _AppleChunks:
    """WAV samples from an ``afconvert`` temp directory, closed exactly once."""

    def __init__(self, directory: tempfile.TemporaryDirectory[str], inner: Iterator[np.ndarray]) -> None:
        """Keep the temp directory alive until :meth:`close`.

        Args:
            directory: Directory that holds ``pcm.wav``.
            inner: Stdlib WAV reader. Its ``close`` runs before the directory
                is removed.
        """
        self._directory = directory
        self._inner = inner
        self._closed = False

    def __iter__(self) -> _AppleChunks:
        """Return this iterator.

        Returns:
            This object.
        """
        return self

    def __next__(self) -> np.ndarray:
        """Return the next PCM chunk.

        Returns:
            One mono chunk at the analyzer rate.

        Raises:
            StopIteration: The WAV has been consumed. The temp directory is
                removed first.
        """
        if self._closed:
            raise StopIteration
        try:
            return next(self._inner)
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        """Close the WAV and delete the temp directory.

        A second call does nothing. Errors from the inner close are ignored
        so a closed generator cannot become an HTTP 500.
        """
        if self._closed:
            return
        self._closed = True
        closer = getattr(self._inner, "close", None)
        if callable(closer):
            try:
                closer()
            except Exception:
                pass
        try:
            self._directory.cleanup()
        except Exception:
            return

    def __del__(self) -> None:
        """Delete the temp directory if the caller never closed the iterator."""
        self.close()


def open_apple(path: Path) -> PcmStream:
    """Decode one AAC-family file with ``afconvert``.

    Args:
        path: Audio file. It is passed as one argv element and is not opened
            for writing by this function.

    Returns:
        Mono chunks at the analyzer rate. The temp WAV lives until the
        iterator is exhausted or closed.

    Raises:
        waveform.DecodeError: ``afconvert`` is missing, the output path is
            refused, the process fails, or the WAV cannot be opened.
        waveform.WaveformUnavailable: ``afconvert`` does not exit before the
            timeout. The process is killed first.
    """
    executable = apple_converter()
    if executable is None:
        _fail("afconvert is not installed")
    directory = tempfile.TemporaryDirectory(prefix=TEMP_PREFIX)
    proc: subprocess.Popen[bytes] | None = None
    try:
        dest = Path(directory.name) / "pcm.wav"
        command = afconvert_command(executable, path, dest)
        proc = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
        )
        try:
            proc.communicate(timeout=_AFCONVERT_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            _unavailable()
        if proc.returncode != 0 or not dest.is_file() or dest.stat().st_size < 44:
            _fail("afconvert did not write a WAV")
        import waveform

        inner = waveform.wave_chunks(dest)
    except Exception:
        if proc is not None and proc.poll() is None:
            proc.kill()
            try:
                proc.communicate(timeout=5)
            except Exception:
                pass
        directory.cleanup()
        raise
    return _AppleChunks(directory, inner)


def temporary_m4a_alias(path: Path) -> tuple[Path, Callable[[], None]]:
    """Point a temp ``.m4a`` name at ``path`` without writing beside it.

    Args:
        path: Existing audio file, usually named ``.alac``.

    Returns:
        The temp path and a callback that deletes the temp directory.
        A hard link is used when the filesystem allows it. Otherwise the
        bytes are copied into the temp directory.

    Raises:
        waveform.DecodeError: The temp path is refused or the alias cannot
            be created. Nothing is left behind in that case.
    """
    directory = tempfile.TemporaryDirectory(prefix=TEMP_PREFIX)
    try:
        dest = Path(directory.name) / "track.m4a"
        if not separate_temp_output(path, dest):
            _fail("alias temp path was refused")
        try:
            os.link(path, dest)
        except OSError:
            shutil.copyfile(path, dest)
        if not dest.is_file():
            _fail("alias was not created")
    except Exception:
        directory.cleanup()
        raise

    def cleanup() -> None:
        directory.cleanup()

    return dest, cleanup


def _windll(name: str) -> ctypes.CDLL:
    """Load a system DLL with the Windows calling convention.

    Args:
        name: DLL name, such as ``mfplat``.

    Returns:
        The loaded library.

    Raises:
        waveform.DecodeError: This Python has no ``WinDLL`` or the load
            did not return a ``CDLL``.
        OSError: The DLL is not installed.
    """
    loader = getattr(ctypes, "WinDLL", None)
    if not callable(loader):
        _fail("WinDLL is unavailable")
    loaded = loader(name)
    if not isinstance(loaded, ctypes.CDLL):
        _fail("WinDLL did not return a library")
    return loaded


def _configure_dlls(ole: ctypes.CDLL, plat: ctypes.CDLL, readwrite: ctypes.CDLL) -> None:
    """Set argument and result types for the Media Foundation entry points.

    Args:
        ole: ``ole32``.
        plat: ``mfplat``.
        readwrite: ``mfreadwrite``.
    """
    ole.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    ole.CoInitializeEx.restype = ctypes.c_long
    ole.CoUninitialize.argtypes = []
    ole.CoUninitialize.restype = None
    plat.MFStartup.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
    plat.MFStartup.restype = ctypes.c_long
    plat.MFShutdown.argtypes = []
    plat.MFShutdown.restype = ctypes.c_long
    plat.MFCreateMediaType.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
    plat.MFCreateMediaType.restype = ctypes.c_long
    plat.MFCreateMemoryBuffer.argtypes = [ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)]
    plat.MFCreateMemoryBuffer.restype = ctypes.c_long
    plat.MFCreateSample.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
    plat.MFCreateSample.restype = ctypes.c_long
    readwrite.MFCreateSourceReaderFromURL.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    readwrite.MFCreateSourceReaderFromURL.restype = ctypes.c_long
    readwrite.MFCreateSinkWriterFromURL.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    readwrite.MFCreateSinkWriterFromURL.restype = ctypes.c_long


def _bind_libraries() -> tuple[ctypes.CDLL, ctypes.CDLL, ctypes.CDLL]:
    """Load and type the three Media Foundation DLLs once per process.

    Returns:
        ``ole32``, ``mfplat``, and ``mfreadwrite``.

    Raises:
        waveform.DecodeError: ``WinDLL`` is unavailable.
        OSError: A DLL could not be loaded.
    """
    global _ole32_dll, _mfplat_dll, _mfreadwrite_dll
    with _dll_lock:
        if _ole32_dll is None or _mfplat_dll is None or _mfreadwrite_dll is None:
            ole = _windll("ole32")
            plat = _windll("mfplat")
            readwrite = _windll("mfreadwrite")
            _configure_dlls(ole, plat, readwrite)
            _ole32_dll = ole
            _mfplat_dll = plat
            _mfreadwrite_dll = readwrite
        return _ole32_dll, _mfplat_dll, _mfreadwrite_dll


def _ole32() -> ctypes.CDLL:
    """Return ``ole32``.

    Returns:
        The loaded library.
    """
    ole, _plat, _readwrite = _bind_libraries()
    return ole


def _mfplat() -> ctypes.CDLL:
    """Return ``mfplat``.

    Returns:
        The loaded library.
    """
    _ole, plat, _readwrite = _bind_libraries()
    return plat


def _mfreadwrite() -> ctypes.CDLL:
    """Return ``mfreadwrite``.

    Returns:
        The loaded library.
    """
    _ole, _plat, readwrite = _bind_libraries()
    return readwrite


def media_foundation_available() -> bool:
    """Return whether the Media Foundation DLLs load on this machine.

    Returns:
        True on Windows when ``ole32``, ``mfplat``, and ``mfreadwrite``
        load. False on every other system and when a DLL is missing.
        This does not start COM.
    """
    if sys.platform != "win32":
        return False
    try:
        _bind_libraries()
    except OSError:
        return False
    return True


def _check(hr: int, step: str) -> None:
    """Turn a failed HRESULT into a decoder refusal.

    Args:
        hr: Raw HRESULT. Negative values are failures.
        step: API name included in the exception text.

    Raises:
        waveform.DecodeError: ``hr`` is negative.
    """
    if hr < 0:
        _fail(f"{step} failed ({hr & 0xFFFFFFFF:08X})")


def _invoke(pointer: int, index: int, restype: Any, argtypes: list[Any], *args: object) -> int:
    """Call one COM method.

    Args:
        pointer: Interface pointer.
        index: Vtable slot, counting ``QueryInterface`` as 0.
        restype: ``ctypes`` result type.
        argtypes: Argument types after the ``this`` pointer.
        *args: Arguments after the ``this`` pointer.

    Returns:
        The integer result.

    Raises:
        waveform.DecodeError: The pointer is null or ``WINFUNCTYPE`` is
            missing.
    """
    if pointer == 0:
        _fail("COM pointer was null")
    slot_table = ctypes.cast(pointer, ctypes.POINTER(ctypes.c_void_p))
    function_address = ctypes.cast(slot_table[0], ctypes.POINTER(ctypes.c_void_p))[index]
    factory = getattr(ctypes, "WINFUNCTYPE", None)
    if not callable(factory):
        _fail("WINFUNCTYPE is unavailable")
    make_prototype = cast(Callable[..., Any], factory)
    prototype = make_prototype(restype, ctypes.c_void_p, *argtypes)
    bound = cast(Callable[..., int], prototype(function_address))
    return bound(pointer, *args)


def _release(pointer: int) -> None:
    """Release one COM pointer.

    Args:
        pointer: Interface pointer. Zero is ignored. A second release of a
            dangling pointer is not attempted by callers.
    """
    if pointer == 0:
        return
    try:
        _invoke(pointer, _RELEASE, ctypes.c_ulong, [])
    except Exception:
        return


def _com_start() -> bool:
    """Initialize COM on this thread.

    Returns:
        True when this call must be balanced with ``CoUninitialize``,
        including ``S_FALSE``. False when the thread is already in another
        apartment.

    Raises:
        waveform.DecodeError: COM could not be initialized.
        OSError: ``ole32`` did not load.
    """
    hr = int(_ole32().CoInitializeEx(None, 0))
    if hr < 0:
        if (hr & 0xFFFFFFFF) == _RPC_E_CHANGED_MODE:
            return False
        _fail(f"CoInitializeEx failed ({hr & 0xFFFFFFFF:08X})")
    return True


def _com_stop() -> None:
    """Balance one successful :func:`_com_start`."""
    try:
        _ole32().CoUninitialize()
    except Exception:
        return


def _mf_start() -> None:
    """Start Media Foundation for this decode or encode.

    Raises:
        waveform.DecodeError: ``MFStartup`` failed.
    """
    _check(int(_mfplat().MFStartup(_MF_VERSION, _MFSTARTUP_NOSOCKET)), "MFStartup")


def _mf_stop() -> None:
    """Balance one successful :func:`_mf_start`."""
    try:
        _mfplat().MFShutdown()
    except Exception:
        return


def _set_guid(target: int, key: _GUID, value: _GUID) -> None:
    """Set a GUID attribute.

    Args:
        target: ``IMFAttributes`` pointer.
        key: Attribute name.
        value: Attribute value.

    Raises:
        waveform.DecodeError: The call failed.
    """
    _check(
        _invoke(target, _SET_GUID, ctypes.c_long, [ctypes.POINTER(_GUID), ctypes.POINTER(_GUID)], ctypes.byref(key), ctypes.byref(value)),
        "SetGUID",
    )


def _set_uint32(target: int, key: _GUID, value: int) -> None:
    """Set a 32-bit attribute.

    Args:
        target: ``IMFAttributes`` pointer.
        key: Attribute name.
        value: Attribute value.

    Raises:
        waveform.DecodeError: The call failed.
    """
    _check(
        _invoke(target, _SET_UINT32, ctypes.c_long, [ctypes.POINTER(_GUID), ctypes.c_uint32], ctypes.byref(key), value),
        "SetUINT32",
    )


def _get_uint32(target: int, key: _GUID) -> int:
    """Read a 32-bit attribute.

    Args:
        target: ``IMFAttributes`` pointer.
        key: Attribute name.

    Returns:
        The stored value.

    Raises:
        waveform.DecodeError: The call failed.
    """
    out = ctypes.c_uint32()
    _check(
        _invoke(
            target,
            _GET_UINT32,
            ctypes.c_long,
            [ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_uint32)],
            ctypes.byref(key),
            ctypes.byref(out),
        ),
        "GetUINT32",
    )
    return int(out.value)


def _get_guid(target: int, key: _GUID) -> _GUID:
    """Read a GUID attribute.

    Args:
        target: ``IMFAttributes`` pointer.
        key: Attribute name.

    Returns:
        The stored GUID.

    Raises:
        waveform.DecodeError: The call failed.
    """
    out = _GUID()
    _check(
        _invoke(
            target,
            _GET_GUID,
            ctypes.c_long,
            [ctypes.POINTER(_GUID), ctypes.POINTER(_GUID)],
            ctypes.byref(key),
            ctypes.byref(out),
        ),
        "GetGUID",
    )
    return out


def _create_media_type() -> int:
    """Create an empty media type.

    Returns:
        An ``IMFMediaType`` pointer the caller must release.

    Raises:
        waveform.DecodeError: The call failed.
    """
    out = ctypes.c_void_p()
    _check(int(_mfplat().MFCreateMediaType(ctypes.byref(out))), "MFCreateMediaType")
    if not out.value:
        _fail("MFCreateMediaType returned a null type")
    return int(out.value)


def _pcm_type(channels: int, rate: int, channel_mask: int | None = None) -> int:
    """Create a 16-bit PCM media type.

    Args:
        channels: Channel count.
        rate: Sample rate in Hz.
        channel_mask: Speaker mask. The AAC encoder requires one for stereo.

    Returns:
        An ``IMFMediaType`` pointer the caller must release.

    Raises:
        waveform.DecodeError: An attribute could not be set.
    """
    media = _create_media_type()
    try:
        _set_guid(media, _MAJOR, _AUDIO)
        _set_guid(media, _SUBTYPE, _PCM)
        _set_uint32(media, _CHANNELS, channels)
        _set_uint32(media, _RATE, rate)
        _set_uint32(media, _BITS, 16)
        block = channels * 2
        _set_uint32(media, _BLOCK, block)
        _set_uint32(media, _AVG, rate * block)
        if channel_mask is not None:
            _set_uint32(media, _CHANNEL_MASK, channel_mask)
    except Exception:
        _release(media)
        raise
    return media


def _blank_pcm_type() -> int:
    """Create a PCM media type without a rate or channel count.

    Returns:
        An ``IMFMediaType`` pointer the caller must release.

    Raises:
        waveform.DecodeError: An attribute could not be set.
    """
    media = _create_media_type()
    try:
        _set_guid(media, _MAJOR, _AUDIO)
        _set_guid(media, _SUBTYPE, _PCM)
    except Exception:
        _release(media)
        raise
    return media


def _aac_type(rate: int, channels: int) -> int:
    """Create an AAC media type for an ``.m4a`` sink.

    Args:
        rate: Sample rate in Hz.
        channels: Channel count.

    Returns:
        An ``IMFMediaType`` pointer the caller must release.

    Raises:
        waveform.DecodeError: An attribute could not be set.
    """
    media = _create_media_type()
    try:
        _set_guid(media, _MAJOR, _AUDIO)
        _set_guid(media, _SUBTYPE, _AAC)
        _set_uint32(media, _RATE, rate)
        _set_uint32(media, _CHANNELS, channels)
        _set_uint32(media, _BITS, 16)
        _set_uint32(media, _AVG, 16000)
        _set_uint32(media, _AAC_PAYLOAD, 0)
    except Exception:
        _release(media)
        raise
    return media


def _media_path(path: Path) -> str:
    """Return a path Media Foundation can open.

    Args:
        path: Existing file.

    Returns:
        The absolute path. A long Windows path is prefixed so the
        260-character limit does not apply.
    """
    text = os.fspath(path.resolve())
    if os.name != "nt":
        return text
    if text.startswith("\\\\?\\"):
        return text
    if text.startswith("\\\\"):
        return "\\\\?\\UNC\\" + text[2:]
    if len(text) >= 240:
        return "\\\\?\\" + text
    return text


def _create_reader(text: str) -> int:
    """Open a source reader on one URL.

    Args:
        text: Absolute file path.

    Returns:
        An ``IMFSourceReader`` pointer the caller must release.

    Raises:
        waveform.DecodeError: The file could not be opened.
    """
    out = ctypes.c_void_p()
    _check(int(_mfreadwrite().MFCreateSourceReaderFromURL(text, None, ctypes.byref(out))), "MFCreateSourceReaderFromURL")
    if not out.value:
        _fail("source reader was null")
    return int(out.value)


def _set_current(reader: int, media: int) -> int:
    """Ask the source reader for one output type.

    Args:
        reader: ``IMFSourceReader`` pointer.
        media: ``IMFMediaType`` pointer.

    Returns:
        The HRESULT. The caller decides whether to retry.
    """
    return _invoke(
        reader,
        _READER_SET_CURRENT,
        ctypes.c_long,
        [ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p],
        _FIRST_AUDIO,
        None,
        media,
    )


def _read_format(reader: int) -> _PcmFormat:
    """Read the PCM layout the source reader is producing.

    Args:
        reader: ``IMFSourceReader`` pointer.

    Returns:
        Channels, rate, bits, and whether the samples are float.

    Raises:
        waveform.DecodeError: The type is missing or not 16-bit or 32-bit PCM.
    """
    out = ctypes.c_void_p()
    _check(
        _invoke(
            reader,
            _READER_GET_CURRENT,
            ctypes.c_long,
            [ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)],
            _FIRST_AUDIO,
            ctypes.byref(out),
        ),
        "GetCurrentMediaType",
    )
    media = int(out.value or 0)
    if media == 0:
        _fail("current media type was null")
    try:
        channels = _get_uint32(media, _CHANNELS)
        rate = _get_uint32(media, _RATE)
        bits = _get_uint32(media, _BITS)
        subtype = _get_guid(media, _SUBTYPE)
    finally:
        _release(media)
    if channels < 1 or rate <= 0 or bits not in (16, 32):
        _fail("PCM format is unsupported")
    return _PcmFormat(channels=channels, rate=rate, bits=bits, floating=subtype.Data1 == _FLOAT.Data1)


def _configure_reader(reader: int) -> _PcmFormat:
    """Select the first audio stream and request PCM.

    Args:
        reader: ``IMFSourceReader`` pointer.

    Returns:
        The PCM layout that was negotiated.

    Raises:
        waveform.DecodeError: The stream could not be selected or decoded.
    """
    # Selection is best-effort. A file with one audio stream still decodes
    # when the reader refuses to deselect every stream first.
    _invoke(reader, _READER_SET_SELECTION, ctypes.c_long, [ctypes.c_uint32, ctypes.c_int], _ALL_STREAMS, 0)
    _invoke(reader, _READER_SET_SELECTION, ctypes.c_long, [ctypes.c_uint32, ctypes.c_int], _FIRST_AUDIO, 1)
    full = _pcm_type(1, 44100)
    try:
        negotiated = _set_current(reader, full)
    finally:
        _release(full)
    if negotiated < 0:
        partial = _blank_pcm_type()
        try:
            _check(_set_current(reader, partial), "SetCurrentMediaType")
        finally:
            _release(partial)
    return _read_format(reader)


def _read_sample(reader: int) -> tuple[int, int]:
    """Read one sample from the first audio stream.

    Args:
        reader: ``IMFSourceReader`` pointer.

    Returns:
        Stream flags and an ``IMFSample`` pointer. The pointer is zero when
        this call delivered no sample. The caller releases a non-zero pointer.

    Raises:
        waveform.DecodeError: ``ReadSample`` failed.
    """
    flags = ctypes.c_uint32()
    timestamp = ctypes.c_longlong()
    sample = ctypes.c_void_p()
    actual = ctypes.c_uint32()
    _check(
        _invoke(
            reader,
            _READER_READ,
            ctypes.c_long,
            [
                ctypes.c_uint32,
                ctypes.c_uint32,
                ctypes.POINTER(ctypes.c_uint32),
                ctypes.POINTER(ctypes.c_uint32),
                ctypes.POINTER(ctypes.c_longlong),
                ctypes.POINTER(ctypes.c_void_p),
            ],
            _FIRST_AUDIO,
            0,
            ctypes.byref(actual),
            ctypes.byref(flags),
            ctypes.byref(timestamp),
            ctypes.byref(sample),
        ),
        "ReadSample",
    )
    return int(flags.value), int(sample.value or 0)


def _contiguous(sample: int) -> int:
    """Return one buffer that holds the whole sample.

    Args:
        sample: ``IMFSample`` pointer.

    Returns:
        An ``IMFMediaBuffer`` pointer the caller must release.

    Raises:
        waveform.DecodeError: The sample has no buffer.
    """
    out = ctypes.c_void_p()
    _check(
        _invoke(sample, _CONVERT_BUFFER, ctypes.c_long, [ctypes.POINTER(ctypes.c_void_p)], ctypes.byref(out)),
        "ConvertToContiguousBuffer",
    )
    if not out.value:
        _fail("sample buffer was null")
    return int(out.value)


def _lock_copy(buffer: int) -> bytes:
    """Copy the bytes currently stored in a media buffer.

    Args:
        buffer: ``IMFMediaBuffer`` pointer.

    Returns:
        A copy of the current bytes. The buffer is unlocked before return.

    Raises:
        waveform.DecodeError: The buffer could not be locked or is larger
            than :data:`_MAX_BUFFER`.
    """
    copied = b""
    data = ctypes.c_void_p()
    maximum = ctypes.c_uint32()
    current = ctypes.c_uint32()
    _check(
        _invoke(
            buffer,
            _LOCK,
            ctypes.c_long,
            [ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32)],
            ctypes.byref(data),
            ctypes.byref(maximum),
            ctypes.byref(current),
        ),
        "Lock",
    )
    try:
        size = int(current.value)
        if size > _MAX_BUFFER:
            _fail("PCM buffer was too large")
        if data.value and size > 0:
            copied = ctypes.string_at(data.value, size)
    finally:
        try:
            _invoke(buffer, _UNLOCK, ctypes.c_long, [])
        except Exception:
            pass
    return copied


def _copy_sample(sample: int) -> bytes:
    """Copy one sample's bytes.

    Args:
        sample: ``IMFSample`` pointer. The caller still owns it.

    Returns:
        The contiguous PCM bytes.

    Raises:
        waveform.DecodeError: The sample could not be read.
    """
    buffer = _contiguous(sample)
    try:
        return _lock_copy(buffer)
    finally:
        _release(buffer)


def _to_mono(raw: bytes, fmt: _PcmFormat) -> np.ndarray:
    """Mix one PCM buffer down to mono floats at the analyzer rate.

    Args:
        raw: Interleaved little-endian frames.
        fmt: Layout of ``raw``.

    Returns:
        Mono samples at 44100 Hz. An empty input stays empty.

    Raises:
        waveform.DecodeError: The width is not 1, 2, or 4 bytes.
    """
    import waveform

    if not raw:
        return np.zeros(0, dtype=np.float64)
    if fmt.floating and fmt.bits == 32:
        data = np.frombuffer(raw, dtype="<f4").astype(np.float64)
        if fmt.channels > 1:
            usable = (data.size // fmt.channels) * fmt.channels
            data = data[:usable].reshape(-1, fmt.channels).mean(axis=1)
        return waveform.resample_mono(data, fmt.rate, waveform.ANALYZE_RATE)
    width = fmt.bits // 8
    if width not in (1, 2, 4):
        _fail("PCM width is unsupported")
    samples = waveform.mix_pcm(raw, width, fmt.channels, little=True)
    return waveform.resample_mono(samples, fmt.rate, waveform.ANALYZE_RATE)


class _MfReader:
    """One Media Foundation source reader and the COM startup it owns."""

    def __init__(self, path: Path) -> None:
        """Open ``path`` and negotiate PCM.

        Args:
            path: Audio file.

        Raises:
            waveform.DecodeError: The file or its ``.alac`` alias could not
                be decoded. COM is shut down before the exception leaves.
        """
        self._balance = False
        self._started = False
        self._reader = 0
        self._format = _PcmFormat(1, 44100, 16, False)
        self._pending = b""
        self._alias_cleanup: Callable[[], None] | None = None
        self._closed = False
        try:
            self._balance = _com_start()
            _mf_start()
            self._started = True
            self._open(path)
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        """Release the reader, delete an alias, and shut Media Foundation down."""
        if self._closed:
            return
        self._closed = True
        if self._reader:
            _release(self._reader)
            self._reader = 0
        if self._alias_cleanup is not None:
            try:
                self._alias_cleanup()
            except Exception:
                pass
            self._alias_cleanup = None
        if self._started:
            _mf_stop()
            self._started = False
        if self._balance:
            _com_stop()
            self._balance = False

    def _drop_reader(self) -> None:
        """Release the current reader so a second open can replace it."""
        if self._reader:
            _release(self._reader)
            self._reader = 0

    def _start(self, path: Path) -> None:
        """Open ``path`` and store the negotiated PCM layout.

        Args:
            path: File the source resolver can open.

        Raises:
            waveform.DecodeError: The resolver or the PCM negotiation failed.
        """
        self._reader = _create_reader(_media_path(path))
        self._format = _configure_reader(self._reader)

    def _open(self, path: Path) -> None:
        """Open ``path``, retrying a ``.alac`` name through a temp ``.m4a``.

        Args:
            path: Audio file.

        Raises:
            waveform.DecodeError: Both attempts failed. The alias directory
                is still owned by this object so :meth:`close` removes it.
        """
        try:
            self._start(path)
        except Exception:
            self._drop_reader()
            if path.suffix.lower() != ".alac":
                raise
        else:
            return
        alias, cleanup = temporary_m4a_alias(path)
        self._alias_cleanup = cleanup
        self._start(alias)

    def _frame_bytes(self) -> int:
        """Return the size of one interleaved frame.

        Returns:
            Channel count times the sample width.

        Raises:
            waveform.DecodeError: The width is not a whole number of bytes.
        """
        width = 4 if self._format.floating else self._format.bits // 8
        if width <= 0 or self._format.channels <= 0:
            _fail("PCM frame size is invalid")
        return width * self._format.channels

    def _take(self, raw: bytes) -> np.ndarray:
        """Append ``raw`` and return every complete frame.

        Args:
            raw: Newly copied PCM. Empty when this call is only a flush check.

        Returns:
            Mono samples, or an empty array when a whole frame is not yet
            buffered. A trailing partial frame stays buffered.
        """
        if raw:
            self._pending += raw
        frame = self._frame_bytes()
        usable = len(self._pending) - (len(self._pending) % frame)
        if usable <= 0:
            return np.zeros(0, dtype=np.float64)
        piece = self._pending[:usable]
        self._pending = self._pending[usable:]
        return _to_mono(piece, self._format)

    def read_chunk(self) -> np.ndarray | None:
        """Read until one mono chunk is available, or the stream ends.

        Returns:
            Mono samples, or None at the end of the stream.

        Raises:
            waveform.DecodeError: The reader reported an error or returned
                eight empty reads in a row.
        """
        empties = 0
        while True:
            flags, sample = _read_sample(self._reader)
            if flags & _TYPE_CHANGED:
                self._pending = b""
                self._format = _read_format(self._reader)
            try:
                raw = _copy_sample(sample) if sample else b""
            finally:
                if sample:
                    _release(sample)
            if flags & _STREAM_ERROR:
                _fail("ReadSample reported an error")
            if raw:
                chunk = self._take(raw)
                if chunk.size:
                    return chunk
            if flags & _END_OF_STREAM:
                tail = self._take(b"")
                return tail if tail.size else None
            if not raw:
                empties += 1
                if empties > 8:
                    _fail("ReadSample returned no audio")


class _EmptyChunks:
    """An iterator that yields nothing and has a close method."""

    def __iter__(self) -> _EmptyChunks:
        """Return this iterator.

        Returns:
            This object.
        """
        return self

    def __next__(self) -> np.ndarray:
        """End the stream.

        Raises:
            StopIteration: Always. There are no samples.
        """
        raise StopIteration

    def close(self) -> None:
        """Do nothing. The reader was already released."""


class _MfChunks:
    """PCM from a Media Foundation reader, released on close."""

    def __init__(self, reader: _MfReader, first: np.ndarray) -> None:
        """Store the reader and the chunk already pulled during open.

        Args:
            reader: Open reader. This object closes it.
            first: First chunk. It is returned by the first ``next`` call.
        """
        self._reader = reader
        self._first: np.ndarray | None = first
        self._closed = False

    def __iter__(self) -> _MfChunks:
        """Return this iterator.

        Returns:
            This object.
        """
        return self

    def __next__(self) -> np.ndarray:
        """Return the next mono chunk.

        Returns:
            Samples at the analyzer rate.

        Raises:
            StopIteration: The stream ended. The reader is released first.
        """
        if self._closed:
            raise StopIteration
        if self._first is not None:
            chunk = self._first
            self._first = None
            return chunk
        try:
            chunk = self._reader.read_chunk()
        except Exception:
            self.close()
            raise
        if chunk is None:
            self.close()
            raise StopIteration
        return chunk

    def close(self) -> None:
        """Release the source reader and shut Media Foundation down."""
        if self._closed:
            return
        self._closed = True
        self._reader.close()

    def __del__(self) -> None:
        """Release the reader if the caller dropped the iterator."""
        self.close()


def _as_decode_error(exc: Exception) -> NoReturn:
    """Keep a decoder refusal, and wrap any other failure as one.

    Args:
        exc: The error raised while opening or reading.

    Raises:
        waveform.DecodeError: ``exc`` was already that type, or it is wrapped
            so the page still gets ``waveform unavailable`` instead of HTTP 500.
        waveform.WaveformUnavailable: ``exc`` was already that type.
    """
    import waveform

    if isinstance(exc, (waveform.DecodeError, waveform.WaveformUnavailable)):
        raise exc
    raise waveform.DecodeError(f"Media Foundation decode failed ({exc})") from exc


def open_media_foundation(path: Path) -> PcmStream:
    """Decode one AAC-family file with Media Foundation.

    Args:
        path: Audio file. It is opened read-only by the source reader.

    Returns:
        Mono chunks at the analyzer rate. An empty iterator means the file
        opened and contained no samples.

    Raises:
        waveform.DecodeError: This is not Windows, or the file could not be
            decoded. A ``.alac`` name is retried through a temp ``.m4a``
            before this exception is raised.
    """
    if sys.platform != "win32":
        _fail("Media Foundation is Windows-only")
    try:
        reader = _MfReader(path)
    except Exception as exc:
        _as_decode_error(exc)
    try:
        first = reader.read_chunk()
    except Exception as exc:
        reader.close()
        _as_decode_error(exc)
    if first is None or first.size == 0:
        reader.close()
        return _EmptyChunks()
    return _MfChunks(reader, first)


def _read_pcm_wav(path: Path) -> tuple[bytes, int, int, int]:
    """Read a PCM WAV for the fixture encoder.

    Args:
        path: WAV file.

    Returns:
        Frames, sample rate, channel count, and sample width in bytes.

    Raises:
        waveform.DecodeError: The file is not a WAV this reader can open.
    """
    try:
        handle = wave.open(os.fspath(path), "rb")
    except (wave.Error, OSError) as exc:
        import waveform

        raise waveform.DecodeError("encoder could not read the WAV") from exc
    try:
        return handle.readframes(handle.getnframes()), handle.getframerate(), handle.getnchannels(), handle.getsampwidth()
    finally:
        handle.close()


def _mono_to_stereo(raw: bytes) -> bytes:
    """Duplicate each 16-bit sample into a stereo pair.

    Args:
        raw: Little-endian mono ``int16`` frames.

    Returns:
        Interleaved stereo frames of the same samples.
    """
    mono = np.frombuffer(raw, dtype="<i2")
    stereo = np.empty(mono.size * 2, dtype="<i2")
    stereo[0::2] = mono
    stereo[1::2] = mono
    return stereo.tobytes()


def _memory_buffer(pcm: bytes) -> int:
    """Copy ``pcm`` into a new media buffer.

    Args:
        pcm: Bytes to store.

    Returns:
        An ``IMFMediaBuffer`` pointer the caller must release.

    Raises:
        waveform.DecodeError: The buffer could not be created or filled.
    """
    out = ctypes.c_void_p()
    _check(int(_mfplat().MFCreateMemoryBuffer(len(pcm), ctypes.byref(out))), "MFCreateMemoryBuffer")
    buffer = int(out.value or 0)
    if buffer == 0:
        _fail("memory buffer was null")
    data = ctypes.c_void_p()
    maximum = ctypes.c_uint32()
    current = ctypes.c_uint32()
    try:
        _check(
            _invoke(
                buffer,
                _LOCK,
                ctypes.c_long,
                [ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32)],
                ctypes.byref(data),
                ctypes.byref(maximum),
                ctypes.byref(current),
            ),
            "Lock",
        )
        if not data.value or int(maximum.value) < len(pcm):
            _fail("buffer lock was short")
        ctypes.memmove(data.value, pcm, len(pcm))
    except Exception:
        try:
            _invoke(buffer, _UNLOCK, ctypes.c_long, [])
        except Exception:
            pass
        _release(buffer)
        raise
    try:
        _invoke(buffer, _UNLOCK, ctypes.c_long, [])
    except Exception:
        _release(buffer)
        raise
    try:
        _check(_invoke(buffer, _SET_LENGTH, ctypes.c_long, [ctypes.c_uint32], len(pcm)), "SetCurrentLength")
    except Exception:
        _release(buffer)
        raise
    return buffer


def _sample_with_buffer(buffer: int, timestamp: int, duration: int) -> int:
    """Wrap a buffer in a sample with a time and a duration.

    Args:
        buffer: ``IMFMediaBuffer`` pointer. The sample adds its own reference.
        timestamp: Start time in 100-nanosecond units.
        duration: Duration in 100-nanosecond units.

    Returns:
        An ``IMFSample`` pointer the caller must release.

    Raises:
        waveform.DecodeError: The sample could not be built.
    """
    out = ctypes.c_void_p()
    _check(int(_mfplat().MFCreateSample(ctypes.byref(out))), "MFCreateSample")
    sample = int(out.value or 0)
    if sample == 0:
        _fail("sample was null")
    try:
        _check(_invoke(sample, _ADD_BUFFER, ctypes.c_long, [ctypes.c_void_p], buffer), "AddBuffer")
        _check(_invoke(sample, _SET_SAMPLE_TIME, ctypes.c_long, [ctypes.c_longlong], timestamp), "SetSampleTime")
        _check(_invoke(sample, _SET_SAMPLE_DURATION, ctypes.c_long, [ctypes.c_longlong], duration), "SetSampleDuration")
    except Exception:
        _release(sample)
        raise
    return sample


def _write_one(writer: int, index: int, piece: bytes, timestamp: int, duration: int) -> None:
    """Write one PCM chunk to the sink writer.

    Args:
        writer: ``IMFSinkWriter`` pointer.
        index: Stream index from ``AddStream``.
        piece: Interleaved 16-bit PCM.
        timestamp: Start time in 100-nanosecond units.
        duration: Duration in 100-nanosecond units.

    Raises:
        waveform.DecodeError: The sample could not be written.
    """
    buffer = _memory_buffer(piece)
    sample = 0
    try:
        sample = _sample_with_buffer(buffer, timestamp, duration)
        _release(buffer)
        buffer = 0
        _check(
            _invoke(writer, _WRITER_WRITE, ctypes.c_long, [ctypes.c_uint32, ctypes.c_void_p], index, sample),
            "WriteSample",
        )
    finally:
        if buffer:
            _release(buffer)
        if sample:
            _release(sample)


def _write_pcm_samples(writer: int, index: int, pcm: bytes, rate: int, channels: int) -> None:
    """Write ``pcm`` in 1024-frame AAC blocks.

    Args:
        writer: ``IMFSinkWriter`` pointer.
        index: Stream index.
        pcm: Interleaved 16-bit PCM whose length is a multiple of 1024 frames.
        rate: Sample rate in Hz.
        channels: Channel count.

    Raises:
        waveform.DecodeError: A block could not be written.
    """
    frame = channels * 2
    chunk = 1024 * frame
    timestamp = 0
    for offset in range(0, len(pcm), chunk):
        piece = pcm[offset:offset + chunk]
        frames = len(piece) // frame
        if frames <= 0:
            break
        duration = frames * 10_000_000 // rate
        _write_one(writer, index, piece, timestamp, duration)
        timestamp += duration


def _create_writer(text: str) -> int:
    """Create an ``.m4a`` sink writer.

    Args:
        text: Absolute output path. The ``.m4a`` suffix selects the MPEG-4 sink.

    Returns:
        An ``IMFSinkWriter`` pointer the caller must release.

    Raises:
        waveform.DecodeError: The sink could not be created.
    """
    out = ctypes.c_void_p()
    _check(int(_mfreadwrite().MFCreateSinkWriterFromURL(text, None, None, ctypes.byref(out))), "MFCreateSinkWriterFromURL")
    if not out.value:
        _fail("sink writer was null")
    return int(out.value)


def _add_stream(writer: int, media: int) -> int:
    """Add the AAC output type to the sink writer.

    Args:
        writer: ``IMFSinkWriter`` pointer.
        media: Output media type.

    Returns:
        The new stream index.

    Raises:
        waveform.DecodeError: The stream was refused.
    """
    index = ctypes.c_uint32()
    _check(
        _invoke(
            writer,
            _WRITER_ADD_STREAM,
            ctypes.c_long,
            [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)],
            media,
            ctypes.byref(index),
        ),
        "AddStream",
    )
    return int(index.value)


def _write_aac(pcm: bytes, rate: int, dest: Path) -> None:
    """Encode stereo PCM to ``dest``.

    Args:
        pcm: Interleaved 16-bit stereo, a multiple of 1024 frames.
        rate: Sample rate in Hz.
        dest: ``.m4a`` path inside the temp directory.

    Raises:
        waveform.DecodeError: Media Foundation refused the file.
    """
    balance = False
    started = False
    writer = 0
    try:
        balance = _com_start()
        _mf_start()
        started = True
        writer = _create_writer(_media_path(dest))
        output_type = _aac_type(rate, 2)
        try:
            index = _add_stream(writer, output_type)
        finally:
            _release(output_type)
        input_type = _pcm_type(2, rate, channel_mask=3)
        try:
            _check(
                _invoke(
                    writer,
                    _WRITER_SET_INPUT,
                    ctypes.c_long,
                    [ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p],
                    index,
                    input_type,
                    None,
                ),
                "SetInputMediaType",
            )
        finally:
            _release(input_type)
        _check(_invoke(writer, _WRITER_BEGIN, ctypes.c_long, []), "BeginWriting")
        _write_pcm_samples(writer, index, pcm, rate, 2)
        _check(_invoke(writer, _WRITER_FINALIZE, ctypes.c_long, []), "Finalize")
    finally:
        if writer:
            _release(writer)
        if started:
            _mf_stop()
        if balance:
            _com_stop()


def encode_aac_m4a(pcm_wav: Path, dest: Path) -> None:
    """Encode a 16-bit mono WAV to AAC in an ``.m4a`` file.

    The server does not call this. Tests on Windows use it when ``afconvert``
    and ffmpeg are both absent, so the real Media Foundation decoder has a
    file to read. The output has to sit in the system temp directory.

    Args:
        pcm_wav: 16-bit mono WAV.
        dest: ``.m4a`` path inside the system temp directory.

    Raises:
        waveform.DecodeError: The destination is refused, this is not
            Windows, or Media Foundation could not encode the file. A
            partial ``dest`` is deleted.
    """
    if not destination_in_temp(dest) or dest.suffix.lower() != ".m4a":
        _fail("encoder output is outside the temp directory")
    if sys.platform != "win32":
        _fail("Media Foundation encoder is Windows-only")
    raw, rate, channels, width = _read_pcm_wav(pcm_wav)
    if width != 2 or channels != 1 or rate <= 0 or not raw:
        _fail("encoder expected 16-bit mono PCM")
    stereo = _mono_to_stereo(raw)
    frame = 4
    pad = (-(len(stereo) // frame)) % 1024
    if pad:
        stereo += b"\x00" * (pad * frame)
    try:
        _write_aac(stereo, rate, dest)
    except Exception:
        try:
            dest.unlink()
        except OSError:
            pass
        raise
