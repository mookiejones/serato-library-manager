"""Tests for GET /api/version and the release-tag fallback."""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import _version  # noqa: E402
import app_config  # noqa: E402
import release_bundle  # noqa: E402
import server  # noqa: E402
import version_info  # noqa: E402


def _utf16(text: str) -> bytes:
    """Return ``text`` as UTF-16LE without a terminator.

    Args:
        text: Text to encode.

    Returns:
        Little-endian UTF-16 bytes.
    """
    return text.encode("utf-16le")


def _string_struct(name: str, value: str) -> bytes:
    """Encode one version-resource string the way PyInstaller does.

    Args:
        name: String-table key, such as ``FileVersion``.
        value: String-table value.

    Returns:
        A ``String`` block, including its terminating nulls.
    """
    raw_name = _utf16(name)
    raw_value = _utf16(value)
    value_length = len(value) + 1
    length = 6 + len(raw_name) + 2
    pad = b"\x00\x00" if length % 4 else b""
    length = length + len(pad) + (value_length * 2)
    return struct.pack("<HHH", length, value_length, 1) + raw_name + b"\x00\x00" + pad + raw_value + b"\x00\x00"


def _string_table(pairs: list[tuple[str, str]]) -> bytes:
    """Encode a ``StringTable`` for code page ``040904B0``.

    Args:
        pairs: Key and value pairs, in order.

    Returns:
        The table block. Each child is padded to 4 bytes outside its
        own length, matching PyInstaller's writer.
    """
    raw_name = _utf16("040904B0")
    parts: list[bytes] = []
    for key, value in pairs:
        raw = _string_struct(key, value)
        if len(raw) % 4:
            raw += b"\x00\x00"
        parts.append(raw)
    body = b"".join(parts)
    length = 6 + len(raw_name) + 2 + len(body)
    return struct.pack("<HHH", length, 0, 1) + raw_name + b"\x00\x00" + body


def _container(name: str, body: bytes) -> bytes:
    """Encode a version-resource container around ``body``.

    Args:
        name: ``StringFileInfo`` or ``VarFileInfo``.
        body: Child bytes.

    Returns:
        The container block.
    """
    raw_name = _utf16(name)
    length = 6 + len(raw_name) + 2
    pad = b"\x00\x00" if length % 4 else b""
    length = length + len(pad) + len(body)
    return struct.pack("<HHH", length, 0, 1) + raw_name + b"\x00\x00" + pad + body


def _var_file_info() -> bytes:
    """Encode a translation block for language 1033 and code page 1200.

    Returns:
        A ``VarFileInfo`` block.
    """
    raw_name = _utf16("Translation")
    value_length = 4
    length = 6 + len(raw_name) + 2
    pad = b"\x00\x00" if length % 4 else b""
    length = length + len(pad) + value_length
    var = struct.pack("<HHH", length, value_length, 0) + raw_name + b"\x00\x00" + pad + struct.pack("<HH", 1033, 1200)
    return _container("VarFileInfo", var)


def _fixed(file_version: tuple[int, int, int, int], product_version: tuple[int, int, int, int]) -> bytes:
    """Encode ``VS_FIXEDFILEINFO``.

    Args:
        file_version: Four version integers.
        product_version: Four version integers.

    Returns:
        52 bytes starting with signature ``0xFEEF04BD``.
    """

    def pack(parts: tuple[int, int, int, int]) -> tuple[int, int]:
        return (parts[0] << 16) | parts[1], (parts[2] << 16) | parts[3]

    file_high, file_low = pack(file_version)
    product_high, product_low = pack(product_version)
    return struct.pack(
        "<13I",
        0xFEEF04BD,
        0x10000,
        file_high,
        file_low,
        product_high,
        product_low,
        0x3F,
        0,
        0x40004,
        1,
        0,
        0,
        0,
    )


def _version_blob(strings: list[tuple[str, str]], numbers: tuple[int, int, int, int]) -> bytes:
    """Encode a ``VS_VERSION_INFO`` blob.

    Args:
        strings: String-table pairs.
        numbers: Numeric file and product version.

    Returns:
        The resource bytes PyInstaller writes with ``toRaw``.
    """
    info = _fixed(numbers, numbers)
    kids = _container("StringFileInfo", _string_table(strings)) + _var_file_info()
    raw_name = _utf16("VS_VERSION_INFO")
    value_length = len(info)
    length = 6 + len(raw_name) + 2
    pad = b"\x00\x00" if length % 4 else b""
    length = length + len(pad) + value_length
    pad2 = b"\x00\x00" if length % 4 else b""
    length = length + len(pad2) + len(kids)
    return struct.pack("<HHH", length, value_length, 0) + raw_name + b"\x00\x00" + pad + info + pad2 + kids


def _directory(entries: list[tuple[int, int]]) -> bytes:
    """Encode one resource directory.

    Args:
        entries: ``(id, offset_field)`` pairs. Ids only. No named entries.

    Returns:
        The directory header plus its entries.
    """
    header = struct.pack("<IIHHHH", 0, 0, 0, 0, 0, len(entries))
    body = b"".join(struct.pack("<II", ident, relative) for ident, relative in entries)
    return header + body


def _pe_with_version(blob: bytes) -> bytes:
    """Wrap ``blob`` in a tiny 64-bit PE with one resource section.

    Args:
        blob: ``VS_VERSION_INFO`` bytes.

    Returns:
        A non-runnable executable whose resource tree points at ``blob``.
    """
    blob_at = 96
    resource = bytearray(blob_at + len(blob))
    resource[0:24] = _directory([(16, 0x80000000 | 24)])
    resource[24:48] = _directory([(1, 0x80000000 | 48)])
    resource[48:72] = _directory([(1033, 72)])
    resource[72:88] = struct.pack("<IIII", 0x1000 + blob_at, len(blob), 0, 0)
    resource[blob_at : blob_at + len(blob)] = blob
    section = bytes(resource)
    file_align = 0x200
    padded = section + b"\x00" * ((file_align - (len(section) % file_align)) % file_align)
    e_lfanew = 0x80
    optional_size = 240
    headers_end = e_lfanew + 4 + 20 + optional_size + 40
    raw_pointer = (headers_end + file_align - 1) & ~(file_align - 1)
    pe = bytearray(raw_pointer + len(padded))
    pe[0:2] = b"MZ"
    struct.pack_into("<I", pe, 0x3C, e_lfanew)
    pe[e_lfanew : e_lfanew + 4] = b"PE\0\0"
    coff = e_lfanew + 4
    struct.pack_into("<H", pe, coff, 0x8664)
    struct.pack_into("<H", pe, coff + 2, 1)
    struct.pack_into("<H", pe, coff + 16, optional_size)
    optional = coff + 20
    struct.pack_into("<H", pe, optional, 0x20B)
    struct.pack_into("<I", pe, optional + 108, 16)
    struct.pack_into("<II", pe, optional + 128, 0x1000, len(section))
    section_header = optional + optional_size
    pe[section_header : section_header + 8] = b".rsrc\x00\x00\x00"
    struct.pack_into("<IIII", pe, section_header + 8, len(section), 0x1000, len(padded), raw_pointer)
    pe[raw_pointer : raw_pointer + len(padded)] = padded
    return bytes(pe)


def _strings_for(version: str) -> list[tuple[str, str]]:
    """Return the string table ``windows_version`` would write.

    Args:
        version: Identity version, such as ``v1.2.3``.

    Returns:
        Key and value pairs in the version-file order.
    """
    info = version_info.windows_version(version)
    return [
        ("CompanyName", info.company_name),
        ("FileDescription", info.file_description),
        ("FileVersion", info.file_version_text),
        ("InternalName", info.internal_name),
        ("OriginalFilename", info.original_filename),
        ("ProductName", info.product_name),
        ("ProductVersion", info.product_version_text),
    ]


def _empty_bake():
    """Patch ``_version`` so the checkout looks unstamped.

    Returns:
        A context manager that restores the three constants.
    """
    return mock.patch.multiple(_version, VERSION="", COMMIT="", SOURCE="")


class BakedVersionTests(unittest.TestCase):
    """The committed module stays empty and a stamp does not call git."""

    def test_committed_module_is_empty(self) -> None:
        """Keep the git copy of ``_version.py`` free of a version.

        A filled-in file would ship in a source checkout and hide the
        tag the release job writes. Nothing is written.

        Returns:
            None. The test fails if a constant is not an empty string.
        """
        self.assertEqual(_version.VERSION, "")
        self.assertEqual(_version.COMMIT, "")
        self.assertEqual(_version.SOURCE, "")

    def test_baked_release_does_not_call_git(self) -> None:
        """Read a stamped tag without running git.

        Patches the three constants. ``subprocess.run`` raises if it is
        called. Nothing is written.

        Returns:
            None. The test fails if the tag, the commit, or the source
            is dropped, or if git runs.
        """
        with (
            mock.patch.object(_version, "VERSION", "v1.2.3-rc2"),
            mock.patch.object(_version, "COMMIT", "0123456789ab"),
            mock.patch.object(_version, "SOURCE", "release"),
            mock.patch("version_info.subprocess.run", side_effect=AssertionError("git")),
        ):
            info = version_info.resolve()
        self.assertEqual(info.version, "v1.2.3-rc2")
        self.assertEqual(info.commit, "0123456789ab")
        self.assertEqual(info.source, "release")

    def test_newline_in_a_baked_version_is_ignored(self) -> None:
        """Treat a broken stamp as empty and fall back.

        A newline cannot be a version. Git is stubbed to fail. Nothing
        is written.

        Returns:
            None. The test fails if resolve raises or keeps the newline.
        """
        with (
            mock.patch.object(_version, "VERSION", "v1\n2"),
            mock.patch.object(_version, "COMMIT", ""),
            mock.patch.object(_version, "SOURCE", ""),
            mock.patch("version_info.subprocess.run", side_effect=FileNotFoundError),
        ):
            info = version_info.resolve()
        self.assertEqual(info, version_info.VersionIdentity("0.0.0+dev", None, "dev"))


class GitFallbackTests(unittest.TestCase):
    """Development checkouts use git, and a missing git does not raise."""

    def test_git_describe_when_the_module_is_empty(self) -> None:
        """Use describe and a 12-character commit when nothing is baked.

        The fake git answers describe and rev-parse. Nothing is written.

        Returns:
            None. The test fails if the fallback replaces a real describe.
        """

        def fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            if "describe" in args:
                return subprocess.CompletedProcess(args, 0, stdout="v1.2.3-4-gabcdef0\n", stderr="")
            if "rev-parse" in args:
                return subprocess.CompletedProcess(args, 0, stdout="abcdef0123456789abcdef\n", stderr="")
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="no")

        with _empty_bake(), mock.patch("version_info.subprocess.run", side_effect=fake_run):
            info = version_info.resolve()
        self.assertEqual(info.version, "v1.2.3-4-gabcdef0")
        self.assertEqual(info.commit, "abcdef012345")
        self.assertEqual(info.source, "git")

    def test_missing_git_falls_back(self) -> None:
        """Return ``0.0.0+dev`` when the git executable does not exist.

        ``FileNotFoundError`` is what ``subprocess`` raises in that case.
        Nothing is written.

        Returns:
            None. The test fails if resolve raises or invents a commit.
        """
        with _empty_bake(), mock.patch("version_info.subprocess.run", side_effect=FileNotFoundError(2, "git")):
            info = version_info.resolve()
            body = version_info.payload()
        self.assertEqual(info, version_info.VersionIdentity("0.0.0+dev", None, "dev"))
        self.assertEqual(body, {"version": "0.0.0+dev", "commit": None, "source": "dev"})

    def test_git_failure_and_timeout_fall_back(self) -> None:
        """Return the dev version when git exits non-zero or times out.

        A commit that rev-parse still prints is kept on a describe
        failure. A timeout drops both. Nothing is written.

        Returns:
            None. The test fails if either case raises.
        """

        def failed(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            if "rev-parse" in args:
                return subprocess.CompletedProcess(args, 0, stdout="0123456789ab\n", stderr="")
            return subprocess.CompletedProcess(args, 128, stdout="", stderr="fatal")

        with _empty_bake(), mock.patch("version_info.subprocess.run", side_effect=failed):
            failed_info = version_info.resolve()
        self.assertEqual(failed_info.version, "0.0.0+dev")
        self.assertEqual(failed_info.commit, "0123456789ab")
        self.assertEqual(failed_info.source, "dev")
        with (
            _empty_bake(),
            mock.patch("version_info.subprocess.run", side_effect=subprocess.TimeoutExpired(["git"], 5)),
        ):
            timed_out = version_info.resolve()
        self.assertEqual(timed_out, version_info.VersionIdentity("0.0.0+dev", None, "dev"))

    def test_payload_survives_an_unexpected_error(self) -> None:
        """Answer the dev version when resolve itself fails.

        The endpoint must not turn a programming error into a crash for
        the page. Nothing is written.

        Returns:
            None. The test fails if payload raises.
        """
        with mock.patch("version_info.resolve", side_effect=RuntimeError("broken")):
            body = version_info.payload()
        self.assertEqual(body, {"version": "0.0.0+dev", "commit": None, "source": "dev"})


class StampTests(unittest.TestCase):
    """The release script stamps the tag and refuses a bad one."""

    def test_tag_pattern_matches_the_release_check(self) -> None:
        """Keep the version module's tag shape equal to ``check-tag``.

        The samples cover a final tag, both prerelease forms, and the
        shapes ``check-tag`` refuses. Nothing is written.

        Returns:
            None. The test fails if one pattern accepts a tag the other rejects.
        """
        samples = (
            "v1.2.3",
            "v1.2.3-rc1",
            "v1.2.3-beta2",
            "v1.2.3-rc0",
            "v0.0.0",
            "v1.2.3-rc",
            "v1.2",
            "1.2.3",
            "v1.2.3-rc.1",
            "refs/tags/v1.2.3",
        )
        for sample in samples:
            self.assertEqual(
                version_info.is_release_tag(sample),
                release_bundle.TAG_RE.fullmatch(sample) is not None,
                sample,
            )

    def test_stamp_uses_the_release_tag_without_git(self) -> None:
        """Bake ``RELEASE_TAG`` and the first 12 digits of the commit.

        Git is not consulted. The module is written under a temporary
        directory and imported from that path.

        Returns:
            None. The test fails if the tag is shortened or git runs.
        """
        with mock.patch("version_info._run_git", side_effect=AssertionError("git")):
            info = version_info.stamp_from_environ(
                {"RELEASE_TAG": "v1.2.3-rc2", "VERSION_COMMIT": "0123456789abcdef"}
            )
        self.assertEqual(info, version_info.VersionIdentity("v1.2.3-rc2", "0123456789ab", "release"))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "_version.py"
            version_info.write_version_module(path, info)
            spec = importlib.util.spec_from_file_location("baked_version_under_test", path)
            self.assertIsNotNone(spec)
            assert spec is not None and spec.loader is not None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        self.assertEqual(module.VERSION, "v1.2.3-rc2")
        self.assertEqual(module.COMMIT, "0123456789ab")
        self.assertEqual(module.SOURCE, "release")

    def test_stamp_falls_back_when_git_is_missing(self) -> None:
        """Write ``0.0.0+dev`` when there is no tag and git returns nothing.

        Nothing is written to the repository copy.

        Returns:
            None. The test fails if stamp raises.
        """
        with mock.patch("version_info._run_git", return_value=None):
            info = version_info.stamp_from_environ({})
        self.assertEqual(info, version_info.VersionIdentity("0.0.0+dev", None, "dev"))

    def test_stamp_refuses_a_bad_tag_or_commit(self) -> None:
        """Refuse a tag without ``v`` and a commit that is not hex.

        The repository file is not written. ``main`` turns the same
        errors into ``SystemExit``.

        Returns:
            None. The test fails if a bad value is baked.
        """
        with self.assertRaises(ValueError):
            version_info.stamp_from_environ({"RELEASE_TAG": "1.2.3"})
        with self.assertRaises(ValueError):
            version_info.stamp_from_environ({"VERSION_COMMIT": "not-a-sha"})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "_version.py"
            with (
                mock.patch.object(version_info, "VERSION_PATH", path),
                mock.patch.dict(os.environ, {"RELEASE_TAG": "refs/tags/v1.2.3"}, clear=False),
                self.assertRaises(SystemExit),
            ):
                version_info.main()
            self.assertFalse(path.exists())

    def test_render_refuses_a_newline(self) -> None:
        """Refuse a version that would break out of the generated module.

        Nothing is written.

        Returns:
            None. The test fails if the newline is quoted into the source.
        """
        info = version_info.VersionIdentity("v1\n2", None, "release")
        with self.assertRaises(ValueError):
            version_info.render_version_module(info)

    def test_installer_version_prefers_a_baked_tag(self) -> None:
        """Pass the tag without ``v`` to Inno Setup.

        An empty stamp with no git uses the numeric triple ``0.0.0``.
        ``APP_VERSION`` stays the full fallback string. Nothing is written.

        Returns:
            None. The test fails if the prerelease is dropped or the
            fallback disagrees with ``__version__``.
        """
        with (
            mock.patch.object(_version, "VERSION", "v1.2.3-rc2"),
            mock.patch.object(_version, "COMMIT", "0123456789ab"),
            mock.patch.object(_version, "SOURCE", "release"),
        ):
            self.assertEqual(version_info.installer_version(), "1.2.3-rc2")
            self.assertEqual(release_bundle.app_version(), "1.2.3-rc2")
            self.assertEqual(app_config.APP_VERSION, "v1.2.3-rc2")
            self.assertEqual(app_config.__version__, app_config.APP_VERSION)
        with _empty_bake(), mock.patch("version_info.subprocess.run", side_effect=FileNotFoundError):
            self.assertEqual(release_bundle.app_version(), "0.0.0")
            self.assertEqual(app_config.APP_VERSION, "0.0.0+dev")
            self.assertEqual(app_config.__version__, "0.0.0+dev")
            self.assertEqual(version_info.payload()["version"], app_config.APP_VERSION)


class WindowsResourceTests(unittest.TestCase):
    """The version file and the PE resource use the release tag."""

    def test_final_tag_reads_as_1_1_0_shape(self) -> None:
        """Show file and product version ``1.1.0`` for tag ``v1.1.0``.

        Company and product names are ``Serato Library``. The generated
        PyInstaller file parses as Python. Nothing is executed.

        Returns:
            None. The test fails if the ``v`` prefix is left on the string
            or the numeric version is not four parts.
        """
        info = version_info.windows_version("v1.1.0")
        self.assertEqual(info.file_version, (1, 1, 0, 0))
        self.assertEqual(info.product_version, (1, 1, 0, 0))
        self.assertEqual(info.file_version_text, "1.1.0")
        self.assertEqual(info.product_version_text, "1.1.0")
        self.assertEqual(info.company_name, "Serato Library")
        self.assertEqual(info.product_name, "Serato Library")
        text = version_info.render_windows_version_file(info)
        ast.parse(text)
        self.assertIn("filevers=(1, 1, 0, 0)", text)
        self.assertIn("StringStruct('ProductVersion', '1.1.0')", text)
        self.assertIn("StringStruct('CompanyName', 'Serato Library')", text)
        self.assertEqual(version_info.version_numbers("v1.1.0-rc2"), (1, 1, 0, 0))
        with mock.patch("version_info.resolve", return_value=version_info.VersionIdentity("v1.1.0-rc2", None, "release")):
            self.assertEqual(version_info.bundle_version(), "1.1.0")

    def test_prerelease_string_keeps_the_suffix(self) -> None:
        """Keep ``-rc2`` on the string version and ``1.1.0.0`` on the numbers.

        ``0.0.0+dev`` has no release tag, so the string stays whole and
        the numbers are zero. Nothing is written.

        Returns:
            None. The test fails if the suffix is stripped or the dev
            string is rewritten.
        """
        preview = version_info.windows_version("v1.1.0-rc2")
        self.assertEqual(preview.file_version_text, "1.1.0-rc2")
        self.assertEqual(preview.product_version_text, "1.1.0-rc2")
        self.assertEqual(preview.file_version, (1, 1, 0, 0))
        dev = version_info.windows_version("0.0.0+dev")
        self.assertEqual(dev.file_version, (0, 0, 0, 0))
        self.assertEqual(dev.product_version_text, "0.0.0+dev")
        ast.parse(version_info.render_windows_version_file(dev))

    def test_pe_resource_matches_the_tag(self) -> None:
        """Read a synthetic executable and require the tag.

        The blob is built with the same layout PyInstaller writes. A
        different tag, a missing resource, and a PE that is not an
        executable are refused. Nothing is launched.

        Returns:
            None. The test fails if the resource is not found or a
            mismatch is accepted.
        """
        numbers = (1, 2, 3, 0)
        blob = _version_blob(_strings_for("v1.2.3"), numbers)
        pe = _pe_with_version(blob)
        version_info.assert_windows_resource(pe, "v1.2.3")
        file_version, product_version, strings = version_info.read_pe_version(pe)
        self.assertEqual(file_version, numbers)
        self.assertEqual(product_version, numbers)
        self.assertEqual(strings["FileVersion"], "1.2.3")
        self.assertEqual(strings["ProductVersion"], "1.2.3")
        self.assertEqual(strings["CompanyName"], "Serato Library")
        self.assertEqual(strings["ProductName"], "Serato Library")
        with self.assertRaises(ValueError):
            version_info.assert_windows_resource(pe, "v9.9.9")
        with self.assertRaises(ValueError):
            version_info.read_pe_version(b"MZ" + b"\x00" * 80)
        with self.assertRaises(ValueError):
            version_info.read_pe_version(b"not a pe")

    def test_assert_version_command_matches_the_baked_tag(self) -> None:
        """Require ``assert-version`` to compare the executable with the tag.

        The executable is the synthetic PE inside a ``Serato Library``
        folder. ``RELEASE_TAG`` must equal the baked version. A missing
        bake is refused. Nothing is launched.

        Returns:
            None. The test fails if a mismatched tag is accepted.
        """
        pe = _pe_with_version(_version_blob(_strings_for("v1.2.3-beta1"), (1, 2, 3, 0)))
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "Serato Library" / "Serato Library.exe"
            exe.parent.mkdir()
            exe.write_bytes(pe)
            baked = {
                "VERSION": "v1.2.3-beta1",
                "COMMIT": "abcdef012345",
                "SOURCE": "release",
            }
            with (
                mock.patch.multiple(_version, **baked),
                mock.patch.dict(os.environ, {"RELEASE_TAG": "v1.2.3-beta1"}, clear=False),
            ):
                release_bundle.main(["assert-version", tmp])
            with (
                mock.patch.multiple(_version, **baked),
                mock.patch.dict(os.environ, {"RELEASE_TAG": "v9.9.9"}, clear=False),
                self.assertRaises(SystemExit),
            ):
                release_bundle.main(["assert-version", tmp])
            with (
                _empty_bake(),
                mock.patch.dict(os.environ, {"RELEASE_TAG": ""}, clear=False),
                self.assertRaises(SystemExit),
            ):
                release_bundle.main(["assert-version", tmp])


class EndpointTests(unittest.TestCase):
    """``GET /api/version`` answers without opening the library."""

    def test_version_endpoint_returns_the_resolved_json(self) -> None:
        """Return the resolver's object when the master database is missing.

        ``serve`` uses a free port and does not require the library.
        ``_library_call`` raises if a library route runs. The body is
        the three documented fields. ``GET /api/settings`` ``app_version``,
        ``APP_VERSION``, and ``__version__`` are that same ``version``.

        Returns:
            None. The test fails if the status is not 200, the library
            is opened, or settings reports a different version.
        """
        identity = version_info.VersionIdentity("v1.4.0-rc2", "abc123def456", "release")
        missing = Path("/tmp/serato-library-missing-master.sqlite")
        with (
            mock.patch.object(version_info, "resolve", return_value=identity),
            mock.patch.object(server, "_library_call", side_effect=AssertionError("library")),
            mock.patch.object(server, "db_path", return_value=missing),
        ):
            httpd = server.serve(port=0, require_library=False)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            host, port = httpd.server_address
            try:
                with urllib.request.urlopen(f"http://{host}:{port}/api/version", timeout=5) as response:
                    self.assertEqual(response.status, 200)
                    self.assertIn("application/json", response.headers.get("Content-Type", ""))
                    body = json.loads(response.read().decode("utf-8"))
                self.assertEqual(
                    body,
                    {"version": "v1.4.0-rc2", "commit": "abc123def456", "source": "release"},
                )
                with urllib.request.urlopen(f"http://{host}:{port}/api/settings", timeout=5) as settings_response:
                    settings = json.loads(settings_response.read().decode("utf-8"))
                self.assertEqual(settings["app_version"], body["version"])
                self.assertEqual(app_config.APP_VERSION, body["version"])
                self.assertEqual(app_config.__version__, body["version"])
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(3)

    def test_version_endpoint_falls_back_when_git_is_missing(self) -> None:
        """Answer ``0.0.0+dev`` through HTTP when git cannot be run.

        The baked module is empty for this call. The library call hook
        still raises. Nothing is written.

        Returns:
            None. The test fails if the response is 500 or names a commit.
        """
        missing = Path("/tmp/serato-library-missing-master.sqlite")
        with (
            _empty_bake(),
            mock.patch("version_info.subprocess.run", side_effect=FileNotFoundError),
            mock.patch.object(server, "_library_call", side_effect=AssertionError("library")),
            mock.patch.object(server, "db_path", return_value=missing),
        ):
            httpd = server.serve(port=0, require_library=False)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            host, port = httpd.server_address
            try:
                with urllib.request.urlopen(f"http://{host}:{port}/api/version", timeout=5) as response:
                    body = json.loads(response.read().decode("utf-8"))
                self.assertEqual(body, {"version": "0.0.0+dev", "commit": None, "source": "dev"})
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(3)


class ReleaseDocTests(unittest.TestCase):
    """The workflow, the spec, and the docs name the same version path."""

    def test_workflow_bakes_and_checks_the_version(self) -> None:
        """Bake ``_version.py`` in both release jobs and check Windows.

        Reads the workflow. It does not run it. The pull-request job
        must not receive a secret for this step.

        Returns:
            None. The test fails if either job drops the bake or the check.
        """
        text = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        self.assertEqual(text.count("python scripts/write_version.py"), 2)
        self.assertEqual(text.count("python scripts/release_bundle.py assert-version dist"), 2)
        self.assertIn("version_info.py", text)
        self.assertIn('"_version.py"', text)
        self.assertIn("scripts/write_version.py", text)
        build = text.split("\n  build:\n", 1)[1].split("\n  release-build:", 1)[0]
        self.assertNotIn("secrets.", build)
        self.assertIn("assert-version", build)

    def test_spec_passes_the_version_file(self) -> None:
        """Point the Windows executable at the generated version file.

        Reads ``serato-library.spec``. It is not executed.

        Returns:
            None. The test fails if the spec still hardcodes the package
            version into the bundle or omits ``version=``.
        """
        text = (ROOT / "serato-library.spec").read_text(encoding="utf-8")
        self.assertIn("import version_info", text)
        self.assertIn("version=windows_version_file", text)
        self.assertIn("write_windows_version_file", text)
        self.assertIn('"_version"', text)
        self.assertNotIn("app_config.APP_VERSION", text)

    def test_docs_describe_the_endpoint(self) -> None:
        """Document ``/api/version`` and the dev fallback.

        Reads the API reference and the release guide. Nothing is written.

        Returns:
            None. The test fails if either page drops the contract.
        """
        architecture = (ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")
        github = (ROOT / "docs" / "github.md").read_text(encoding="utf-8")
        self.assertIn("/api/version", architecture)
        self.assertIn("0.0.0+dev", architecture)
        self.assertIn("git describe", architecture)
        self.assertIn("the same string `GET /api/version` returns", architecture)
        self.assertIn("`app_version` is the `version` field from `GET /api/version`", architecture)
        self.assertNotIn("not the release tag", architecture)
        self.assertIn("assert-version", github)
        self.assertIn("write_version.py", github)
        self.assertIn("0.0.0+dev", github)
        self.assertIn("Serato Library", github)
