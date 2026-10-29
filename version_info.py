"""Resolve the running version and the Windows version resource.

The release workflow writes ``_version.py`` from the tag before
PyInstaller runs. A development checkout leaves that file empty. This
module then asks git, and uses ``0.0.0+dev`` when git is missing or
fails. The Windows file version, the macOS bundle version, and
``GET /api/version`` all read the same identity.
"""

from __future__ import annotations

import os
import re
import struct
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import _version

ROOT = Path(__file__).resolve().parent
VERSION_PATH = ROOT / "_version.py"
FALLBACK_VERSION = "0.0.0+dev"
PRODUCT_NAME = "Serato Library"
COMPANY_NAME = "Serato Library"
FILE_DESCRIPTION = "Serato Library"
INTERNAL_NAME = "Serato Library"
ORIGINAL_FILENAME = "Serato Library.exe"
SOURCES = ("release", "git", "dev")
# Same shapes as scripts/release_bundle.TAG_RE. The groups are the triple.
TAG_RE = re.compile(r"v([0-9]+)\.([0-9]+)\.([0-9]+)(?:-(?:rc|beta)[0-9]+)?")
_LEADING_TRIPLE = re.compile(r"v?([0-9]+)\.([0-9]+)\.([0-9]+)")
_HEX_SHA = re.compile(r"[0-9a-f]{7,40}")
_GIT_TIMEOUT_SECONDS = 5
_VERSION_RESOURCE = 16
_FIXED_INFO_BYTES = 52
_FIXED_SIGNATURE = 0xFEEF04BD


@dataclass(frozen=True)
class VersionIdentity:
    """The version a running process should report.

    Attributes:
        version: Release tag, ``git describe`` text, or ``0.0.0+dev``.
        commit: Short hex SHA, or None when no commit is known.
        source: ``release`` for a stamped tag, ``git`` for describe, or
            ``dev`` for the fallback.
    """

    version: str
    commit: str | None
    source: str


@dataclass(frozen=True)
class WindowsVersion:
    """File and product versions stored in a Windows executable.

    Attributes:
        file_version: Four integers for ``VS_FIXEDFILEINFO``.
        product_version: Four integers for ``VS_FIXEDFILEINFO``.
        file_version_text: String ``FileVersion``.
        product_version_text: String ``ProductVersion``.
        company_name: String ``CompanyName``.
        product_name: String ``ProductName``.
        file_description: String ``FileDescription``.
        internal_name: String ``InternalName``.
        original_filename: String ``OriginalFilename``.
    """

    file_version: tuple[int, int, int, int]
    product_version: tuple[int, int, int, int]
    file_version_text: str
    product_version_text: str
    company_name: str
    product_name: str
    file_description: str
    internal_name: str
    original_filename: str


def is_release_tag(value: str) -> bool:
    """Return whether ``value`` is a tag this project ships.

    Args:
        value: Tag text, such as ``v1.2.3`` or ``v1.2.3-rc1``.

    Returns:
        True for ``vMAJOR.MINOR.PATCH`` and the ``-rcN`` / ``-betaN``
        forms. False for a bare ``1.2.3``, a full ref, or an empty string.
    """
    return isinstance(value, str) and TAG_RE.fullmatch(value) is not None


def baked_identity() -> VersionIdentity | None:
    """Return the identity written into ``_version.py``.

    Returns:
        The stamped version, or None when ``VERSION`` is empty. A value
        that is not text, or that contains a newline, is treated as empty.

    Does not run git. Does not raise if the constants are the wrong type.
    """
    version = _clean_text(getattr(_version, "VERSION", ""))
    if not version:
        return None
    source = _clean_text(getattr(_version, "SOURCE", ""))
    if source not in SOURCES:
        source = "release" if is_release_tag(version) else "git"
    return VersionIdentity(version, _clean_commit(getattr(_version, "COMMIT", "")), source)


def resolve() -> VersionIdentity:
    """Return the version for this process.

    Returns:
        The baked identity when ``_version.VERSION`` is set. Otherwise
        ``git describe --tags --always --dirty`` and a short commit, or
        ``0.0.0+dev`` when git cannot be run.

    A missing git executable, a non-repository directory, a non-zero
    exit, and a timeout all take the fallback. This function does not raise
    for those cases.
    """
    baked = baked_identity()
    if baked is not None:
        return baked
    described = _git_describe()
    commit = _git_commit()
    if described:
        return VersionIdentity(described, commit, "git")
    return VersionIdentity(FALLBACK_VERSION, commit, "dev")


def payload() -> dict[str, object]:
    """Return the JSON object for ``GET /api/version``.

    Returns:
        ``version``, ``commit``, and ``source``. ``commit`` is a string
        or None. A failure while reading the identity becomes
        ``0.0.0+dev`` with ``commit`` null and ``source`` ``dev``, so the
        request still answers.
    """
    try:
        info = resolve()
    except Exception:
        info = VersionIdentity(FALLBACK_VERSION, None, "dev")
    return {"version": info.version, "commit": info.commit, "source": info.source}


def package_version() -> str:
    """Return ``app_config.APP_VERSION`` when it is ``MAJOR.MINOR.PATCH``.

    Returns:
        The package version constant.

    Raises:
        ValueError: If the constant is any other shape.
    """
    import app_config

    version = app_config.APP_VERSION
    if not isinstance(version, str) or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) is None:
        raise ValueError(f"APP_VERSION must look like 1.2.3, got {version!r}")
    return version


def installer_version() -> str:
    """Return the version string passed to Inno Setup.

    Returns:
        A baked release tag without the leading ``v``, including
        ``-rcN`` or ``-betaN``. A development checkout returns
        ``APP_VERSION``.

    Raises:
        ValueError: If ``APP_VERSION`` is not ``MAJOR.MINOR.PATCH`` and
            no release tag was baked.
    """
    baked = baked_identity()
    if baked is not None and baked.source == "release" and is_release_tag(baked.version):
        return baked.version[1:]
    return package_version()


def version_numbers(version: str) -> tuple[int, int, int, int]:
    """Return the four Windows version integers for ``version``.

    Args:
        version: A release tag, a describe string, or the dev fallback.

    Returns:
        ``(major, minor, patch, 0)`` from the leading triple. A string
        with no triple returns ``(0, 0, 0, 0)``.

    Raises:
        ValueError: If a component does not fit in 16 bits.
    """
    match = _LEADING_TRIPLE.match(version)
    if match is None:
        return (0, 0, 0, 0)
    parts = tuple(int(part) for part in match.groups())
    if any(part > 0xFFFF for part in parts):
        raise ValueError(f"Version component does not fit in a Windows version: {version}")
    return (parts[0], parts[1], parts[2], 0)


def windows_version_text(version: str) -> str:
    """Return the string Windows should show for ``version``.

    Args:
        version: A release tag or any other version string.

    Returns:
        A release tag without the leading ``v`` (``1.2.3`` or
        ``1.2.3-rc1``). Any other string is returned unchanged.
    """
    if is_release_tag(version):
        return version[1:]
    return version


def windows_version(version: str) -> WindowsVersion:
    """Return the version resource fields for ``version``.

    Args:
        version: The identity's version string.

    Returns:
        Numeric file and product versions, plus the string table. File
        and product text are the same string. Company and product names
        are ``Serato Library``.

    Raises:
        ValueError: If a numeric component does not fit in 16 bits.
    """
    numbers = version_numbers(version)
    text = windows_version_text(version)
    return WindowsVersion(
        file_version=numbers,
        product_version=numbers,
        file_version_text=text,
        product_version_text=text,
        company_name=COMPANY_NAME,
        product_name=PRODUCT_NAME,
        file_description=FILE_DESCRIPTION,
        internal_name=INTERNAL_NAME,
        original_filename=ORIGINAL_FILENAME,
    )


def bundle_version() -> str:
    """Return ``MAJOR.MINOR.PATCH`` for the macOS bundle versions.

    Returns:
        The numeric triple of the resolved version. A describe string
        uses its leading triple. A value with no triple is ``0.0.0``.

    Raises:
        ValueError: If a component does not fit in 16 bits.
    """
    major, minor, patch, _build = version_numbers(resolve().version)
    return f"{major}.{minor}.{patch}"


def render_windows_version_file(info: WindowsVersion) -> str:
    """Return a PyInstaller version-file for ``info``.

    Args:
        info: Fields to embed. Strings are quoted with ``repr``.

    Returns:
        Python source that evaluates to ``VSVersionInfo`` when
        PyInstaller loads it.
    """
    strings = (
        ("CompanyName", info.company_name),
        ("FileDescription", info.file_description),
        ("FileVersion", info.file_version_text),
        ("InternalName", info.internal_name),
        ("OriginalFilename", info.original_filename),
        ("ProductName", info.product_name),
        ("ProductVersion", info.product_version_text),
    )
    body = ",\n".join(f"        StringStruct({key!r}, {value!r})" for key, value in strings)
    return (
        "# UTF-8\n"
        "#\n"
        "# Generated from the release identity. Do not edit.\n"
        "VSVersionInfo(\n"
        "  ffi=FixedFileInfo(\n"
        f"    filevers={info.file_version!r},\n"
        f"    prodvers={info.product_version!r},\n"
        "    mask=0x3f,\n"
        "    flags=0x0,\n"
        "    OS=0x40004,\n"
        "    fileType=0x1,\n"
        "    subtype=0x0,\n"
        "    date=(0, 0)\n"
        "    ),\n"
        "  kids=[\n"
        "    StringFileInfo([\n"
        "      StringTable(\n"
        "        '040904B0',\n"
        "        [\n"
        f"{body}\n"
        "        ])\n"
        "      ]),\n"
        "    VarFileInfo([VarStruct('Translation', [1033, 1200])])\n"
        "  ]\n"
        ")\n"
    )


def write_windows_version_file(path: Path, version: str | None = None) -> Path:
    """Write a PyInstaller version file for the resolved version.

    Args:
        path: Destination. Parent directories are created.
        version: Version string to embed. None uses :func:`resolve`.

    Returns:
        ``path``.

    Raises:
        ValueError: If a numeric component does not fit in 16 bits.
        OSError: If the file cannot be written.
    """
    chosen = resolve().version if version is None else version
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_windows_version_file(windows_version(chosen)), encoding="utf-8")
    return path


def assert_windows_resource(data: bytes, version: str) -> None:
    """Require ``data`` to carry the version resource for ``version``.

    Args:
        data: Windows executable bytes.
        version: Expected identity version. A release tag is compared
            without its leading ``v``. The numeric file and product
            versions are the leading ``MAJOR.MINOR.PATCH`` plus ``0``.

    Returns:
        None.

    Raises:
        ValueError: If the executable has no version resource, or a
            field does not match.
    """
    found_file, found_product, strings = read_pe_version(data)
    expected = windows_version(version)
    if found_file != expected.file_version or found_product != expected.product_version:
        raise ValueError(
            f"numeric version {found_file}/{found_product} != {expected.file_version}"
        )
    expected_strings = {
        "CompanyName": expected.company_name,
        "ProductName": expected.product_name,
        "FileVersion": expected.file_version_text,
        "ProductVersion": expected.product_version_text,
    }
    for key, value in expected_strings.items():
        if strings.get(key) != value:
            raise ValueError(f"{key} is {strings.get(key)!r}, expected {value!r}")


def read_pe_version(data: bytes) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int], dict[str, str]]:
    """Read the version resource from a Windows executable.

    Args:
        data: Executable bytes, starting at the DOS header.

    Returns:
        Numeric file version, numeric product version, and the string
        table. Keys include ``FileVersion``, ``ProductVersion``,
        ``CompanyName``, and ``ProductName`` when the resource has them.

    Raises:
        ValueError: If ``data`` is not a PE file or it has no version
            resource.
    """
    blob = _version_blob(data)
    return _parse_version_blob(blob)


def render_version_module(info: VersionIdentity) -> str:
    """Return the source of ``_version.py`` for ``info``.

    Args:
        info: Identity to bake. ``source`` must be ``release``, ``git``,
            or ``dev``.

    Returns:
        Python source that assigns ``VERSION``, ``COMMIT``, and ``SOURCE``.

    Raises:
        ValueError: If a field contains a newline or ``source`` is unknown.
    """
    if info.source not in SOURCES:
        raise ValueError(f"Unknown version source {info.source!r}.")
    commit = info.commit or ""
    for label, value in (("version", info.version), ("commit", commit)):
        if not isinstance(value, str) or any(ch in value for ch in "\r\n\x00"):
            raise ValueError(f"{label} contains a control character.")
    return (
        '"""Generated release identity. Empty version means a dev checkout."""\n'
        "\n"
        f"VERSION = {info.version!r}\n"
        f"COMMIT = {commit!r}\n"
        f"SOURCE = {info.source!r}\n"
    )


def write_version_module(path: Path, info: VersionIdentity) -> None:
    """Overwrite ``path`` with the baked identity.

    Args:
        path: Destination, normally ``_version.py``.
        info: Identity to write.

    Raises:
        ValueError: If a field cannot be quoted safely.
        OSError: If the file cannot be written.
    """
    path.write_text(render_version_module(info), encoding="utf-8")


def stamp_from_environ(environ: Mapping[str, str]) -> VersionIdentity:
    """Choose the identity a build should bake.

    Args:
        environ: ``RELEASE_TAG`` and optional ``VERSION_COMMIT``. A blank
            tag uses git. An invalid tag is refused.

    Returns:
        A release identity, a git-describe identity, or ``0.0.0+dev``.
        ``commit`` is taken from ``VERSION_COMMIT`` when that is a hex
        SHA, otherwise from git. It is None when neither is available.

    Raises:
        ValueError: If ``RELEASE_TAG`` or ``VERSION_COMMIT`` is set and
            does not match the accepted shape.

    Does not raise when git is missing.
    """
    raw_tag = environ.get("RELEASE_TAG", "")
    if not isinstance(raw_tag, str):
        raise ValueError("RELEASE_TAG must be a string.")
    tag = raw_tag.strip()
    if tag and not is_release_tag(tag):
        raise ValueError(
            f"RELEASE_TAG must look like v1.2.3, v1.2.3-rc1, or v1.2.3-beta1, got {tag!r}"
        )
    commit = _commit_from_environ(environ)
    if tag:
        return VersionIdentity(tag, commit, "release")
    described = _git_describe()
    if described:
        return VersionIdentity(described, commit, "git")
    return VersionIdentity(FALLBACK_VERSION, commit, "dev")


def main() -> None:
    """Write the repository ``_version.py`` from the process environment.

    Prints the version, the source, and whether a commit was recorded.
    The function does not print the environment.

    Raises:
        SystemExit: If ``RELEASE_TAG`` or ``VERSION_COMMIT`` is invalid.
    """
    try:
        info = stamp_from_environ(os.environ)
        write_version_module(VERSION_PATH, info)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    commit = info.commit or "none"
    print(f"Wrote _version.py version={info.version} source={info.source} commit={commit}")


def _clean_text(value: object) -> str:
    """Return ``value`` when it is a single line of text.

    Args:
        value: Attribute from ``_version``. Non-strings are empty.

    Returns:
        The stripped string, or ``""`` when it is not usable.
    """
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if any(ch in text for ch in "\r\n\x00"):
        return ""
    return text


def _clean_commit(value: object) -> str | None:
    """Return a 7 to 12 character hex SHA, or None.

    Args:
        value: Full or short SHA. A 40-character SHA is shortened to 12.

    Returns:
        Lowercase hex, or None when ``value`` is not a SHA.
    """
    text = _clean_text(value).lower()
    if _HEX_SHA.fullmatch(text) is None:
        return None
    return text[:12]


def _commit_from_environ(environ: Mapping[str, str]) -> str | None:
    """Return the commit from ``VERSION_COMMIT`` or from git.

    Args:
        environ: Mapping that may contain ``VERSION_COMMIT``.

    Returns:
        A short SHA, or None when the variable is blank and git has no
        commit.

    Raises:
        ValueError: If the variable is set to something that is not hex.
    """
    if "VERSION_COMMIT" not in environ:
        return _git_commit()
    raw = environ.get("VERSION_COMMIT", "")
    if not isinstance(raw, str):
        raise ValueError("VERSION_COMMIT must be a string.")
    if raw.strip() == "":
        return _git_commit()
    commit = _clean_commit(raw)
    if commit is None:
        raise ValueError("VERSION_COMMIT must be a hex SHA.")
    return commit


def _git_env() -> dict[str, str]:
    """Return an environment that stops git from asking for credentials.

    Returns:
        A copy of the process environment with ``GIT_TERMINAL_PROMPT``
        set to ``0``.
    """
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def _run_git(args: list[str]) -> str | None:
    """Run one git command and return its single line of output.

    Args:
        args: Command and arguments. The first item is ``git``.

    Returns:
        The stripped stdout, or None when git is missing, the command
        fails, it times out, or the output is not one line.

    Does not raise.
    """
    try:
        result = subprocess.run(
            args,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GIT_TIMEOUT_SECONDS,
            env=_git_env(),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    text = result.stdout.strip()
    if not text or any(ch in text for ch in "\r\n\x00 \t"):
        return None
    return text


def _git_describe() -> str | None:
    """Return ``git describe --tags --always --dirty``, or None.

    Returns:
        The describe string, or None when git cannot answer.
    """
    return _run_git(["git", "describe", "--tags", "--always", "--dirty"])


def _git_commit() -> str | None:
    """Return a 12-character commit from ``git rev-parse``, or None.

    Returns:
        Lowercase hex, or None when git cannot answer.
    """
    return _clean_commit(_run_git(["git", "rev-parse", "--short=12", "HEAD"]))


def _align4(offset: int) -> int:
    """Return ``offset`` rounded up to a multiple of 4.

    Args:
        offset: Byte index inside a version resource.

    Returns:
        The next 4-byte boundary, or ``offset`` when it is already aligned.
    """
    return (offset + 3) & ~3


def _utf16z(data: bytes, start: int, limit: int) -> tuple[int, str]:
    """Read a null-terminated UTF-16LE string.

    Args:
        data: Buffer that holds the string.
        start: First byte of the string.
        limit: Index that must not be read.

    Returns:
        The index after the terminating null, and the text without that
        null.

    Raises:
        ValueError: If the string is out of range or has no terminator.
    """
    if start < 0 or limit > len(data) or start > limit:
        raise ValueError("version string is out of range")
    end = start
    while end + 1 < limit:
        if data[end : end + 2] == b"\x00\x00":
            text = data[start:end].decode("utf-16le")
            return end + 2, text
        end += 2
    raise ValueError("version string is not terminated")


def _parse_fixed(data: bytes, offset: int) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]]:
    """Read ``VS_FIXEDFILEINFO`` at ``offset``.

    Args:
        data: Version resource bytes.
        offset: Start of the 52-byte structure.

    Returns:
        File version and product version as four-integer tuples.

    Raises:
        ValueError: If the signature is not ``0xFEEF04BD``.
    """
    fields = struct.unpack_from("<13I", data, offset)
    if fields[0] != _FIXED_SIGNATURE:
        raise ValueError("fixed file info signature is wrong")

    def split(high: int, low: int) -> tuple[int, int, int, int]:
        return (high >> 16, high & 0xFFFF, low >> 16, low & 0xFFFF)

    return split(fields[2], fields[3]), split(fields[4], fields[5])


def _collect_strings(data: bytes, pos: int, end: int, strings: dict[str, str]) -> None:
    """Walk version-resource children and record text values.

    Args:
        data: Version resource bytes.
        pos: First byte of a child.
        end: Index that must not be read.
        strings: Map filled with ``FileVersion`` and the other names.

    Raises:
        ValueError: If a text value is not terminated.
    """
    while pos + 6 <= end:
        start = pos
        length, value_length, value_type = struct.unpack_from("<HHH", data, pos)
        if length < 6 or pos + length > end:
            break
        block_end = pos + length
        pos, key = _utf16z(data, pos + 6, block_end)
        pos = _align4(pos)
        if pos > block_end:
            pos = block_end
        if value_length == 0:
            _collect_strings(data, pos, block_end, strings)
        elif value_type == 1:
            _after, value = _utf16z(data, pos, block_end)
            strings[key] = value
        pos = _align4(block_end)
        if pos <= start:
            break


def _parse_version_blob(
    data: bytes,
) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int], dict[str, str]]:
    """Parse a ``VS_VERSION_INFO`` blob.

    Args:
        data: The resource bytes, starting at ``VS_VERSION_INFO``.

    Returns:
        Numeric file version, numeric product version, and the strings.

    Raises:
        ValueError: If the blob is not a version resource.
    """
    if len(data) < 6:
        raise ValueError("version resource is empty")
    length, value_length, _value_type = struct.unpack_from("<HHH", data, 0)
    if length < 6 or length > len(data):
        raise ValueError("version resource length is wrong")
    pos, key = _utf16z(data, 6, length)
    if key != "VS_VERSION_INFO":
        raise ValueError("version resource key is wrong")
    pos = _align4(pos)
    if value_length < _FIXED_INFO_BYTES or pos + _FIXED_INFO_BYTES > length:
        raise ValueError("fixed file info is missing")
    file_version, product_version = _parse_fixed(data, pos)
    child = _align4(pos + value_length)
    strings: dict[str, str] = {}
    _collect_strings(data, child, length, strings)
    return file_version, product_version, strings


def _sections(data: bytes, table: int, count: int) -> list[tuple[int, int, int, int]]:
    """Return ``(virtual_address, virtual_size, raw_pointer, raw_size)``.

    Args:
        data: Executable bytes.
        table: File offset of the first section header.
        count: Number of sections.

    Returns:
        One tuple per section.

    Raises:
        ValueError: If the section table is truncated.
    """
    sections = []
    for index in range(count):
        offset = table + index * 40
        if offset + 40 > len(data):
            raise ValueError("section table is truncated")
        virtual_size, virtual_address, raw_size, raw_pointer = struct.unpack_from("<IIII", data, offset + 8)
        sections.append((virtual_address, virtual_size, raw_pointer, raw_size))
    return sections


def _rva_to_offset(rva: int, sections: list[tuple[int, int, int, int]]) -> int:
    """Convert a relative virtual address to a file offset.

    Args:
        rva: Address relative to the image base.
        sections: Section rows from :func:`_sections`.

    Returns:
        The file offset of ``rva``.

    Raises:
        ValueError: If ``rva`` is not inside a section that is present
            in the file.
    """
    for virtual_address, virtual_size, raw_pointer, raw_size in sections:
        span = max(virtual_size, raw_size)
        if span <= 0 or not virtual_address <= rva < virtual_address + span:
            continue
        delta = rva - virtual_address
        if delta >= raw_size:
            raise ValueError("version resource is outside the file")
        return raw_pointer + delta
    raise ValueError("version resource is not in a section")


def _directory_entries(data: bytes, offset: int) -> list[tuple[int, int]]:
    """Return resource-directory entries at ``offset``.

    Args:
        data: Executable bytes.
        offset: File offset of an ``IMAGE_RESOURCE_DIRECTORY``.

    Returns:
        ``(name_or_id, offset_field)`` pairs. The high bit of the offset
        field marks a subdirectory.

    Raises:
        ValueError: If the directory is truncated.
    """
    if offset < 0 or offset + 16 > len(data):
        raise ValueError("resource directory is truncated")
    named, ids = struct.unpack_from("<HH", data, offset + 12)
    count = named + ids
    entries: list[tuple[int, int]] = []
    pos = offset + 16
    for _index in range(count):
        if pos + 8 > len(data):
            raise ValueError("resource directory is truncated")
        name, relative = struct.unpack_from("<II", data, pos)
        entries.append((name, relative))
        pos += 8
    return entries


def _version_blob(data: bytes) -> bytes:
    """Return the ``RT_VERSION`` bytes inside ``data``.

    Args:
        data: Executable bytes.

    Returns:
        The version resource blob.

    Raises:
        ValueError: If ``data`` is not a PE file or it has no version
            resource.
    """
    if len(data) < 0x40 or data[:2] != b"MZ":
        raise ValueError("not a Windows executable")
    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    if e_lfanew < 0 or e_lfanew + 24 > len(data) or data[e_lfanew : e_lfanew + 4] != b"PE\0\0":
        raise ValueError("not a Windows executable")
    coff = e_lfanew + 4
    section_count = struct.unpack_from("<H", data, coff + 2)[0]
    optional_size = struct.unpack_from("<H", data, coff + 16)[0]
    optional = coff + 20
    if optional_size < 2 or optional + optional_size > len(data):
        raise ValueError("optional header is truncated")
    magic = struct.unpack_from("<H", data, optional)[0]
    if magic == 0x20B:
        count_offset = 108
    elif magic == 0x10B:
        count_offset = 92
    else:
        raise ValueError("unknown PE optional header")
    if count_offset + 4 > optional_size:
        raise ValueError("optional header has no data directories")
    directory_count = struct.unpack_from("<I", data, optional + count_offset)[0]
    directories = count_offset + 4
    if directory_count < 3 or directories + 24 > optional_size:
        raise ValueError("no version resource")
    resource_rva, _resource_size = struct.unpack_from("<II", data, optional + directories + 16)
    if resource_rva == 0:
        raise ValueError("no version resource")
    table = optional + optional_size
    sections = _sections(data, table, section_count)
    root = _rva_to_offset(resource_rva, sections)
    type_entry = _id_offset(_directory_entries(data, root), _VERSION_RESOURCE)
    if type_entry is None or type_entry & 0x80000000 == 0:
        raise ValueError("no version resource")
    name_offset = root + (type_entry & 0x7FFFFFFF)
    name_entries = _directory_entries(data, name_offset)
    if not name_entries or name_entries[0][1] & 0x80000000 == 0:
        raise ValueError("version resource has no language")
    language_offset = root + (name_entries[0][1] & 0x7FFFFFFF)
    language_entries = _directory_entries(data, language_offset)
    if not language_entries or language_entries[0][1] & 0x80000000:
        raise ValueError("version resource has no data")
    data_offset = root + language_entries[0][1]
    if data_offset + 8 > len(data):
        raise ValueError("version resource data entry is truncated")
    blob_rva, size = struct.unpack_from("<II", data, data_offset)
    if size < 6 or size > 1_000_000:
        raise ValueError("version resource size is wrong")
    blob_offset = _rva_to_offset(blob_rva, sections)
    if blob_offset + size > len(data):
        raise ValueError("version resource is truncated")
    return data[blob_offset : blob_offset + size]


def _id_offset(entries: list[tuple[int, int]], wanted: int) -> int | None:
    """Return the offset field of the resource entry whose id is ``wanted``.

    Args:
        entries: Directory entries. Named entries are skipped.
        wanted: Integer resource type or name.

    Returns:
        The offset field, or None when no id matches.
    """
    for name, relative in entries:
        if name & 0x80000000:
            continue
        if name == wanted:
            return relative
    return None
