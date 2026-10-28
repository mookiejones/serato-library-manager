#!/usr/bin/env python3
"""Check a PyInstaller build and pack it for a GitHub release.

macOS jobs write a UDIF disk image. The Windows job writes a portable zip
and an Inno Setup installer. Each pack command launches the frozen app
outside the repository with SERATO_LIBRARY_SMOKE. The app binds a free
port, the harness requests /api/health, then it shuts the app down.
Publishing checks the files again and does not launch them: a Linux
runner cannot start the macOS or Windows app.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import re
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import desktop  # noqa: E402
import server  # noqa: E402
import static_assets  # noqa: E402

APP_NAME = "Serato Library"
MACOS_APP = "Serato Library.app"
MACOS_EXE = Path("Contents/MacOS/Serato Library")
WINDOWS_EXE = Path("Serato Library.exe")
MACOS_ARM_DMG = "Serato-Library-macos-arm64.dmg"
MACOS_INTEL_DMG = "Serato-Library-macos-x64.dmg"
WINDOWS_ZIP = "Serato-Library-windows.zip"
WINDOWS_SETUP = "Serato-Library-windows-setup.exe"
CHECKSUMS_NAME = "SHA256SUMS"
RELEASE_FILES = (MACOS_ARM_DMG, MACOS_INTEL_DMG, WINDOWS_SETUP, WINDOWS_ZIP)
# Inno Setup 6.7.3, downloaded from the jrsoftware GitHub release and
# hashed in this repository on 2026-10-28. install-inno refuses any other bytes.
INNO_VERSION = "6.7.3"
INNO_URL = "https://github.com/jrsoftware/issrc/releases/download/is-6_7_3/innosetup-6.7.3.exe"
INNO_SHA256 = "9c73c3bae7ed48d44112a0f48e66742c00090bdb5bef71d9d3c056c66e97b732"
ISS_PATH = ROOT / "packaging" / "serato-library.iss"
PE_MACHINE_AMD64 = 0x8664
# Final tags are vMAJOR.MINOR.PATCH. A prerelease is that plus -rcN or -betaN.
TAG_RE = re.compile(r"v[0-9]+\.[0-9]+\.[0-9]+(?:-(?:rc|beta)[0-9]+)?")
PRERELEASE_RE = re.compile(r"v[0-9]+\.[0-9]+\.[0-9]+-(?:rc|beta)[0-9]+")
LAUNCH_TIMEOUT_SECONDS = 120
# Page assets are compared by content. This floor only catches a bundle
# that did not collect the Python runtime. A healthy build is several
# times this size; raise the floor when a measured build says to.
MIN_BUNDLE_BYTES = 8 * 1024 * 1024
MAX_BUNDLE_BYTES = 250 * 1024 * 1024
MIN_ZIP_BYTES = 4 * 1024 * 1024
MAX_ZIP_BYTES = 180 * 1024 * 1024
_KEPT_ENV = ("PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP", "LANG", "LC_ALL")


@dataclass(frozen=True)
class Bundle:
    """A PyInstaller onedir build for one operating system."""

    kind: str
    root: Path
    exe_rel: Path

    @property
    def exe(self) -> Path:
        """Return the frozen executable inside this bundle.

        The path is the macOS binary under Contents/MacOS, or
        ``Serato Library.exe`` on Windows. It is not launched here.

        Returns:
            Absolute or relative path of the executable, joined onto ``root``.
        """
        return self.root / self.exe_rel


def source_static() -> Path:
    """Return the repository ``static`` directory.

    Zip checks compare the bundled page with this directory byte for byte.

    Returns:
        ``static`` beside the repository root. The directory is not read here.
    """
    return ROOT / "static"


def check_tag(tag: str) -> None:
    """Refuse a tag that is not a final version or an ``-rcN`` / ``-betaN`` prerelease.

    Accepted shapes are ``vMAJOR.MINOR.PATCH``, ``vMAJOR.MINOR.PATCH-rcN``,
    and ``vMAJOR.MINOR.PATCH-betaN``. ``N`` is one or more digits. A dotted
    suffix such as ``-rc.1``, a tag without the leading ``v``, and a full
    ref such as ``refs/tags/v1.2.3`` are refused.

    Args:
        tag: Git tag text, such as ``v1.2.3`` or ``v1.2.3-rc1``.

    Returns:
        None.

    Raises:
        SystemExit: If ``tag`` does not match that shape.

    Does not read the git repository or write a file.
    """
    if TAG_RE.fullmatch(tag) is None:
        raise SystemExit(
            f"Tag must look like v1.2.3, v1.2.3-rc1, or v1.2.3-beta1, got {tag!r}"
        )


def is_prerelease(tag: str) -> bool:
    """Return whether ``tag`` is an ``-rcN`` or ``-betaN`` prerelease.

    Args:
        tag: Tag text that :func:`check_tag` accepts.

    Returns:
        True for ``v1.2.3-rc1`` and ``v1.2.3-beta2``. False for ``v1.2.3``.

    Raises:
        SystemExit: If ``tag`` is not an accepted release tag.
    """
    check_tag(tag)
    return PRERELEASE_RE.fullmatch(tag) is not None


def release_create_flags(tag: str) -> list[str]:
    """Return the ``gh release create`` flags for ``tag``.

    Args:
        tag: Tag text that :func:`check_tag` accepts.

    Returns:
        ``--prerelease`` and ``--latest=false`` for a prerelease.
        ``--latest`` for a final tag.

    Raises:
        SystemExit: If ``tag`` is not an accepted release tag.
    """
    if is_prerelease(tag):
        return ["--prerelease", "--latest=false"]
    return ["--latest"]


def footer(repo: str) -> str:
    """Return the release-notes footer with ``repo`` filled in.

    The template lives in ``scripts/release-notes-footer.md`` and still
    says ``OWNER/REPO`` until this substitution.

    Args:
        repo: GitHub repository as ``owner/name``.

    Returns:
        The footer text with that repository name in place of ``OWNER/REPO``.

    Raises:
        SystemExit: If the footer template has no repository placeholder,
            or ``repo`` does not contain a slash.
        OSError: If the footer template cannot be read.

    Reads the template. Does not write it.
    """
    text = (ROOT / "scripts" / "release-notes-footer.md").read_text(encoding="utf-8")
    if "OWNER/REPO" not in text:
        raise SystemExit("Release notes footer is missing OWNER/REPO")
    if not repo or "/" not in repo:
        raise SystemExit(f"Repository must look like owner/name, got {repo!r}")
    return text.replace("OWNER/REPO", repo)


def find_bundle(dist: Path) -> Bundle:
    """Find the macOS app or the Windows folder inside ``dist``.

    A PyInstaller onedir build is ``Serato Library.app`` on macOS and a
    ``Serato Library`` folder containing ``Serato Library.exe`` on Windows.
    One tree must not hold both.

    Args:
        dist: Directory that contains the build, or the unzipped archive.

    Returns:
        The bundle kind, its root directory, and the executable path
        relative to that root.

    Raises:
        SystemExit: If neither build is present, both are, or the executable is missing.

    Checks the filesystem. Does not launch the executable.
    """
    app = dist / MACOS_APP
    folder = dist / APP_NAME
    windows_exe = folder / WINDOWS_EXE
    has_app = app.is_dir()
    has_windows = windows_exe.is_file()
    if has_app and has_windows:
        raise SystemExit(f"{dist} contains both a macOS app and a Windows build.")
    if has_app:
        exe = app / MACOS_EXE
        if not exe.is_file():
            raise SystemExit(f"Missing executable: {exe}")
        return Bundle("macos", app, MACOS_EXE)
    if has_windows:
        return Bundle("windows", folder, WINDOWS_EXE)
    raise SystemExit(f"No Serato Library build in {dist}")


def directory_bytes(root: Path) -> int:
    """Return the size of regular files under ``root``.

    The release size check uses this so a bundle that forgot the Python
    runtime fails before it is zipped. Symlinks count as zero. Their
    targets are counted when they are also files in the tree.

    Args:
        root: Bundle directory to measure.

    Returns:
        Total size in bytes of regular files. Symlinks and directories add nothing.

    Reads file sizes. Does not follow symlink targets that sit outside the walk.
    """
    total = 0
    for path in root.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        total += path.stat().st_size
    return total


def assert_size(label: str, size: int, floor: int, ceiling: int) -> None:
    """Refuse a size outside the inclusive bounds.

    A too-small zip usually means the runtime was left out. A too-large
    zip means something outside the app was packed.

    Args:
        label: Name printed when the size is refused.
        size: Measured size in bytes.
        floor: Smallest accepted size, inclusive.
        ceiling: Largest accepted size, inclusive.

    Returns:
        None.

    Raises:
        SystemExit: If ``size`` is below ``floor`` or above ``ceiling``.
    """
    if size < floor or size > ceiling:
        raise SystemExit(f"{label} is {size} bytes, outside {floor}..{ceiling}")


def _source_files(static_dir: Path) -> list[str]:
    """List the real files under a ``static`` directory.

    The release check compares this list with the files inside the zip.
    ``index.html`` has to be present, and every local asset that page
    references has to be a real file. Symlinks are left out so a link
    cannot stand in for the page.

    Args:
        static_dir: Source or bundled ``static`` directory.

    Returns:
        Paths relative to ``static_dir``, using forward slashes, sorted.

    Raises:
        SystemExit: If ``index.html`` is missing or a page asset is not a file.

    Reads the directory and ``index.html``. Does not write.
    """
    names = sorted(
        path.relative_to(static_dir).as_posix()
        for path in static_dir.rglob("*")
        if path.is_file() and not path.is_symlink()
    )
    if not names or "index.html" not in names:
        raise SystemExit(f"{static_dir} has no index.html")
    missing = static_assets.missing_static_files(static_dir)
    if missing:
        raise SystemExit("Missing source assets: " + ", ".join(missing))
    return names


def assert_static_matches(root: Path, source: Path) -> None:
    """Require every bundled ``static`` directory to match ``source``.

    PyInstaller copies ``static/`` into the app. This comparison catches
    a stale or partial copy before the zip is published.

    Args:
        root: Bundle root that should contain one or more ``static`` folders.
        source: Repository ``static`` directory.

    Returns:
        None.

    Raises:
        SystemExit: If no bundled page is present, or a copy differs.

    Reads file bytes from both trees. Does not write.
    """
    found = [
        path.parent
        for path in root.rglob("index.html")
        if path.parent.name == "static" and path.is_file() and not path.is_symlink()
    ]
    if not found:
        raise SystemExit(f"{root} has no static/index.html")
    expected = _source_files(source)
    for static_dir in found:
        bundled = sorted(
            path.relative_to(static_dir).as_posix()
            for path in static_dir.rglob("*")
            if path.is_file() and not path.is_symlink()
        )
        if bundled != expected:
            raise SystemExit(f"Bundled files {bundled} do not match source {expected}")
        for name in expected:
            if (source / name).read_bytes() != (static_dir / name).read_bytes():
                raise SystemExit(f"Bundled static/{name} does not match source")


def _unsafe_member(name: str) -> bool:
    """Return whether a zip entry name could write outside the destination.

    An absolute path, a drive letter, an empty segment, or ``..`` would
    escape the unpack directory. Those names are refused before any byte
    is written.

    Args:
        name: Zip member name, with either slash style.

    Returns:
        True when the name is not a relative path that stays inside the archive.
    """
    if not name or name.startswith(("/", "\\")):
        return True
    parts = re.split(r"[\\/]", name)
    # A segment ending in ":" is a Windows drive (C:). An empty segment is
    # an absolute path or a doubled slash. ".." climbs out of the destination.
    return any(part in ("", "..") or part.endswith(":") for part in parts)


def _link_stays_inside(link_rel: Path, target: str) -> bool:
    """Return whether a relative symlink stays inside the bundle directory.

    macOS app bundles contain symlinks under Contents. An absolute target,
    a Windows drive path, or a target that climbs out of the bundle root
    is refused so unpacking cannot write elsewhere.

    Args:
        link_rel: Archive path of the symlink, including the bundle directory.
        target: Link text stored in the zip entry.

    Returns:
        True when the joined target still starts with the bundle's top directory.
    """
    if not target or "\n" in target or "\x00" in target:
        return False
    if os.path.isabs(target) or target.startswith("\\"):
        return False
    # "C:\..." is absolute on Windows even when os.path.isabs is false on POSIX.
    if len(target) > 1 and target[1] == ":":
        return False
    combined = Path(os.path.normpath(Path(link_rel).parent / target))
    if combined.is_absolute() or ".." in combined.parts or not combined.parts:
        return False
    # The first path component is the bundle directory name. A target that
    # leaves it, such as a sibling folder, is outside the archive.
    return combined.parts[0] == Path(link_rel).parts[0]


def zip_bundle(root: Path, dest: Path) -> None:
    """Write ``root`` into a new zip at ``dest``.

    The archive entries keep the bundle directory name. Unix modes are
    stored in the high half of ``external_attr``, which is where Info-ZIP
    and Python keep them, and symlinks stay symlinks. An existing ``dest``
    is left alone. ``.DS_Store`` files are skipped so a Finder browse does
    not change the zip.

    Args:
        root: App bundle or Windows folder to pack.
        dest: Zip path to create.

    Returns:
        None.

    Raises:
        SystemExit: If ``dest`` exists, a member path is unsafe, or a
            symlink points outside the bundle.
        OSError: If the archive cannot be written.

    Creates ``dest`` and reads every file under ``root``.
    """
    if dest.exists():
        raise SystemExit(f"Refusing to overwrite {dest}")
    parent = root.parent
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if path.name == ".DS_Store":
                continue
            rel = path.relative_to(parent).as_posix()
            if _unsafe_member(rel):
                raise SystemExit(f"Refusing archive path {rel}")
            info = zipfile.ZipInfo(rel)
            # A fixed timestamp keeps the zip bytes stable across machines.
            # create_system 3 marks the entry as Unix so modes survive.
            info.date_time = (2026, 1, 1, 0, 0, 0)
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            if path.is_symlink():
                target = os.readlink(path)
                if not _link_stays_inside(path.relative_to(parent), target):
                    raise SystemExit(f"Symlink escapes the bundle: {rel} -> {target}")
                mode = stat.S_IFLNK | 0o777
                info.external_attr = mode << 16
                archive.writestr(info, target.encode())
                continue
            if not path.is_file():
                continue
            mode = path.stat().st_mode & 0xFFFF
            info.external_attr = mode << 16
            archive.writestr(info, path.read_bytes())


def _unix_mode(info: zipfile.ZipInfo) -> int:
    """Return the Unix mode stored on a zip entry.

    Python and Info-ZIP keep that mode in the high 16 bits of
    ``external_attr``. The low half is the DOS attribute and is ignored.

    Args:
        info: Zip member metadata.

    Returns:
        The 16-bit Unix mode, including the file-type bits. Zero when the
        entry was written without a Unix mode.
    """
    return (info.external_attr >> 16) & 0xFFFF


def _is_symlink_member(info: zipfile.ZipInfo) -> bool:
    """Return whether a zip entry is a Unix symlink.

    Args:
        info: Zip member metadata.

    Returns:
        True when the Unix mode has the symlink file type.
    """
    return stat.S_ISLNK(_unix_mode(info))


def assert_zip(
    archive: Path,
    source: Path,
    *,
    min_bytes: int = MIN_ZIP_BYTES,
    max_bytes: int = MAX_ZIP_BYTES,
) -> str:
    """Require a release zip to contain the executable and the page.

    The publish job calls this without launching the app. The executable
    must be a regular file, the macOS binary must be marked executable,
    and every bundled ``static`` file must match ``source``.

    Args:
        archive: Zip file to inspect.
        source: Repository ``static`` directory the page must match.
        min_bytes: Smallest accepted zip size, inclusive.
        max_bytes: Largest accepted zip size, inclusive.

    Returns:
        ``macos`` or ``windows``, from the executable entry.

    Raises:
        SystemExit: If the zip is the wrong size, unsafe, or incomplete.

    Reads the archive. Does not extract it onto disk.
    """
    assert_size(archive.name, archive.stat().st_size, min_bytes, max_bytes)
    with zipfile.ZipFile(archive) as zipped:
        infos = zipped.infolist()
        for info in infos:
            if _unsafe_member(info.filename):
                raise SystemExit(f"Unsafe zip entry {info.filename}")
        expected = _source_files(source)
        names = [info.filename for info in infos]
        kind = _zip_kind(names)
        exe_name = _exe_name(names, kind)
        exe_info = zipped.getinfo(exe_name)
        if _is_symlink_member(exe_info) or exe_info.file_size <= 0:
            raise SystemExit(f"{exe_name} is not a regular executable")
        if kind == "macos" and _unix_mode(exe_info) & 0o111 == 0:
            raise SystemExit(f"{exe_name} is not marked executable")
        prefixes = [
            info.filename[: -len("index.html")]
            for info in infos
            if info.filename.endswith("static/index.html") and not _is_symlink_member(info)
        ]
        if not prefixes:
            raise SystemExit(f"{archive} has no static/index.html")
        for prefix in prefixes:
            for name in expected:
                member = prefix + name
                try:
                    info = zipped.getinfo(member)
                except KeyError as exc:
                    raise SystemExit(f"{archive} is missing {member}") from exc
                if _is_symlink_member(info):
                    raise SystemExit(f"{member} is a symlink")
                if zipped.read(info) != (source / name).read_bytes():
                    raise SystemExit(f"{member} does not match source")
    return kind


def _zip_kind(names: list[str]) -> str:
    """Decide whether a zip is the macOS app or the Windows folder.

    The two release zips are built on different runners and must not be
    combined. The kind is taken from the executable path, not from the
    zip file name.

    Args:
        names: Member names from the archive.

    Returns:
        ``macos`` or ``windows``.

    Raises:
        SystemExit: If both executables are present, or neither is.
    """
    macos = any(name.endswith("Serato Library.app/Contents/MacOS/Serato Library") for name in names)
    windows = any(name.endswith("Serato Library/Serato Library.exe") for name in names)
    if macos and windows:
        raise SystemExit("Zip contains both macOS and Windows executables.")
    if macos:
        return "macos"
    if windows:
        return "windows"
    raise SystemExit("Zip has no Serato Library executable")


def _exe_name(names: list[str], kind: str) -> str:
    """Return the single executable member for a bundle kind.

    Args:
        names: Member names from the archive.
        kind: ``macos`` or ``windows``, as returned by ``_zip_kind``.

    Returns:
        The member name of that executable.

    Raises:
        SystemExit: If the archive does not contain exactly one match.
    """
    suffix = (
        "Serato Library.app/Contents/MacOS/Serato Library"
        if kind == "macos"
        else "Serato Library/Serato Library.exe"
    )
    matches = [name for name in names if name.endswith(suffix)]
    if len(matches) != 1:
        raise SystemExit(f"Expected one {suffix}, found {matches}")
    return matches[0]


def unzip_bundle(archive: Path, dest: Path) -> None:
    """Extract ``archive`` under ``dest``, restoring modes and symlinks.

    Symlink entries are recreated with ``symlink_to`` instead of being
    written as regular files. Unix permission bits are restored when the
    entry stored them. This is the unpack step before the smoke launch.

    Args:
        archive: Zip produced by ``zip_bundle``.
        dest: Directory that will contain the bundle. It is created if needed.

    Returns:
        None.

    Raises:
        SystemExit: If an entry is unsafe or a symlink points outside the archive.
        OSError: If a member cannot be written.

    Writes files and symlinks under ``dest``.
    """
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zipped:
        for info in zipped.infolist():
            if _unsafe_member(info.filename):
                raise SystemExit(f"Unsafe zip entry {info.filename}")
            target = dest / info.filename
            if _is_symlink_member(info):
                link_to = zipped.read(info).decode()
                if not _link_stays_inside(Path(info.filename), link_to):
                    raise SystemExit(f"Symlink escapes the bundle: {info.filename} -> {link_to}")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.symlink_to(link_to)
                continue
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zipped.read(info))
            mode = _unix_mode(info)
            if mode:
                os.chmod(target, stat.S_IMODE(mode))


def _outside_repo(path: Path) -> None:
    """Refuse to launch an executable that lives inside this repository.

    The smoke check has to run the unzipped app, not ``desktop.py`` from
    the source tree. A path inside the repo would see the checkout and
    could read a live library path from the developer's machine.

    Args:
        path: Executable path about to be launched.

    Returns:
        None.

    Raises:
        SystemExit: If ``path`` is the repository root or a file inside it.
    """
    resolved = path.resolve()
    root = ROOT.resolve()
    if resolved == root or root in resolved.parents:
        raise SystemExit(f"Refusing to launch inside the repository: {resolved}")


def _http(url: str, method: str, token: str | None = None) -> tuple[int, bytes]:
    """Request ``url`` and return the status and body.

    Args:
        url: Absolute URL. The caller has already limited it to loopback.
        method: ``GET`` or ``POST``.
        token: Shutdown token. None sends no shutdown header.

    Returns:
        The HTTP status and the raw body. HTTP errors are returned, not raised.

    Raises:
        OSError: If the connection fails.
    """
    headers = {}
    data = None
    if token is not None:
        headers[server.SHUTDOWN_HEADER] = token
        data = b"{}"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read()
        exc.close()
        return exc.code, body


def _json_object(body: bytes) -> object:
    """Decode a JSON object from an HTTP body.

    Args:
        body: Response bytes.

    Returns:
        The decoded value, or None when the body is not JSON.
    """
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return None


def _smoke_output(path: Path) -> str:
    """Return the tail of a smoke log.

    Args:
        path: File the child process wrote.

    Returns:
        At most the last 4000 characters. An empty string when the file is missing.
    """
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")[-4000:]


def run_smoke(exe: Path, cwd: Path) -> None:
    """Run ``exe`` until ``/api/health`` answers, then shut it down.

    The process gets an empty home directory, so a missing smoke hook
    cannot see the live Serato library. ``PYTHONPATH`` is not passed
    through. ``HOME``, ``USERPROFILE``, ``LOCALAPPDATA``, and ``APPDATA``
    all point at that empty directory, which covers macOS and Windows.

    Args:
        exe: Frozen executable, or a smoke stand-in used by the tests.
        cwd: Working directory outside the repository. The marker file
            is written here.

    Returns:
        None.

    Raises:
        SystemExit: If ``exe`` is inside the repository, health does not
            answer, shutdown fails, or the process does not exit 0.

    Starts a subprocess and writes the marker path into its environment.
    The launched program writes the marker, then waits for shutdown.
    """
    _outside_repo(exe)
    home = cwd / "empty-home"
    home.mkdir(exist_ok=True)
    marker = (cwd / "smoke-marker.txt").resolve()
    env = {key: os.environ[key] for key in _KEPT_ENV if key in os.environ}
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["LOCALAPPDATA"] = str(home)
    env["APPDATA"] = str(home)
    env[desktop.SMOKE_ENV] = str(marker)
    stdout_path = cwd / "smoke-stdout.txt"
    stderr_path = cwd / "smoke-stderr.txt"
    stdout = stdout_path.open("wb")
    stderr = stderr_path.open("wb")
    proc = subprocess.Popen([str(exe)], cwd=cwd, env=env, stdout=stdout, stderr=stderr)
    try:
        deadline = time.monotonic() + LAUNCH_TIMEOUT_SECONDS
        parsed = None
        while time.monotonic() < deadline:
            if marker.is_file():
                parsed = desktop.parse_smoke_marker(marker.read_text(encoding="utf-8"))
                if parsed:
                    break
            if proc.poll() is not None:
                break
            time.sleep(0.05)
        if not parsed:
            raise SystemExit(
                "Smoke marker was not written.\n"
                + _smoke_output(stdout_path)
                + "\n"
                + _smoke_output(stderr_path)
            )
        url, token = parsed
        try:
            status, body = _http(url + "/api/health", "GET")
        except OSError as exc:
            raise SystemExit(f"Health request failed: {exc}") from exc
        if status != 200 or _json_object(body) != {"ok": True}:
            raise SystemExit(f"Health check returned {status} {body!r}")
        try:
            status, body = _http(url + "/api/shutdown", "POST", token)
        except OSError as exc:
            raise SystemExit(f"Shutdown request failed: {exc}") from exc
        if status != 200 or _json_object(body) != {"ok": True}:
            raise SystemExit(f"Shutdown returned {status} {body!r}")
        remaining = deadline - time.monotonic()
        try:
            code = proc.wait(timeout=max(1.0, remaining))
        except subprocess.TimeoutExpired as exc:
            raise SystemExit(f"Bundle did not exit within {LAUNCH_TIMEOUT_SECONDS}s") from exc
        if code != 0:
            raise SystemExit(
                f"Smoke check failed (exit {code}).\n"
                + _smoke_output(stdout_path)
                + "\n"
                + _smoke_output(stderr_path)
            )
    finally:
        stdout.close()
        stderr.close()
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)


def launch_unzipped(archive: Path) -> None:
    """Unpack ``archive`` outside the repository and run its smoke check.

    The temporary directory is removed when the check finishes. This is
    the launch the pack command performs. The publish job does not call
    it, because a Linux runner cannot start the macOS or Windows app.

    Args:
        archive: Checked release zip.

    Returns:
        None.

    Raises:
        SystemExit: If unpacking or the smoke check fails.

    Creates a temporary directory, extracts the zip, and starts the executable.
    """
    with tempfile.TemporaryDirectory(prefix="serato-library-artifact-") as tmp:
        dest = Path(tmp) / "unzipped"
        unzip_bundle(archive, dest)
        bundle = find_bundle(dest)
        _outside_repo(bundle.exe)
        run_smoke(bundle.exe, Path(tmp))


def verify_tree(dist: Path) -> Bundle:
    """Check bundle size and that its page matches ``static/``.

    Args:
        dist: PyInstaller ``dist`` directory, or a folder that contains the app.

    Returns:
        The bundle that was checked.

    Raises:
        SystemExit: If the build is missing, the wrong size, or its page differs.

    Reads the tree. Does not zip or launch it.
    """
    bundle = find_bundle(dist)
    assert_size(str(bundle.root), directory_bytes(bundle.root), MIN_BUNDLE_BYTES, MAX_BUNDLE_BYTES)
    assert_static_matches(bundle.root, source_static())
    return bundle


def pack(dist: Path, dest: Path) -> None:
    """Zip a checked build, check the zip, then launch the unpacked app.

    Args:
        dist: PyInstaller ``dist`` directory.
        dest: Zip path to create. An existing file is refused.

    Returns:
        None.

    Raises:
        SystemExit: If any check fails. A failed launch deletes ``dest``.

    Writes ``dest``, then extracts a second copy under a temporary directory
    and runs the frozen executable.
    """
    verify_tree(dist)
    bundle = find_bundle(dist)
    if dest.exists():
        raise SystemExit(f"Refusing to overwrite {dest}")
    try:
        zip_bundle(bundle.root, dest)
        assert_zip(dest, source_static())
        launch_unzipped(dest)
    except BaseException:
        dest.unlink(missing_ok=True)
        raise


def sha256_file(path: Path) -> str:
    """Return the hex SHA-256 of ``path``.

    Args:
        path: File to hash.

    Returns:
        64 lowercase hex characters.

    Reads the file in 1 MiB chunks.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def app_version() -> str:
    """Return the version declared in ``app_config.APP_VERSION``.

    Returns:
        ``MAJOR.MINOR.PATCH``.

    Raises:
        SystemExit: If the constant is any other shape.

    Imports ``app_config``. Does not parse the file as text.
    """
    import app_config

    version = app_config.APP_VERSION
    if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) is None:
        raise SystemExit(f"APP_VERSION must look like 1.2.3, got {version!r}")
    return version


def pe_machine(path: Path) -> int:
    """Return the PE machine field of a Windows executable.

    Args:
        path: ``.exe`` file.

    Returns:
        The 16-bit machine id. ``0x8664`` is 64-bit x86.

    Raises:
        SystemExit: If the file is not a PE executable.
    """
    data = path.read_bytes()
    if len(data) < 64 or data[:2] != b"MZ":
        raise SystemExit(f"{path.name} is not a Windows executable")
    offset = int.from_bytes(data[0x3C:0x40], "little")
    if offset < 0 or offset + 6 > len(data) or data[offset : offset + 4] != b"PE\0\0":
        raise SystemExit(f"{path.name} has no PE header")
    return int.from_bytes(data[offset + 4 : offset + 6], "little")


def assert_frozen_arch(exe: Path, arch: str) -> None:
    """Require the frozen executable to be exactly one architecture.

    Args:
        exe: Mach-O or PE executable.
        arch: ``arm64`` or ``x64``.

    Raises:
        SystemExit: If the binary is universal, the other architecture,
            or this operating system cannot inspect it.

    A universal build is refused. Each release file is built on the
    runner that matches its name.
    """
    if arch not in ("arm64", "x64"):
        raise SystemExit(f"Unknown arch {arch!r}")
    if sys.platform == "darwin":
        output = subprocess.check_output(["lipo", "-archs", str(exe)], text=True).split()
        expected = "arm64" if arch == "arm64" else "x86_64"
        if output != [expected]:
            raise SystemExit(f"{exe} is {output}, expected [{expected}]")
        return
    if sys.platform == "win32":
        machine = pe_machine(exe)
        if arch != "x64" or machine != PE_MACHINE_AMD64:
            raise SystemExit(f"{exe} machine {machine:#x} is not x64")
        return
    raise SystemExit(f"Cannot check a {arch} binary on {sys.platform}")


def assert_dmg(
    archive: Path,
    *,
    min_bytes: int = MIN_ZIP_BYTES,
    max_bytes: int = MAX_ZIP_BYTES,
) -> None:
    """Require a disk image to be a sized UDIF file.

    Args:
        archive: ``.dmg`` path.
        min_bytes: Smallest accepted size, inclusive.
        max_bytes: Largest accepted size, inclusive.

    Raises:
        SystemExit: If the size is outside the bounds or the UDIF trailer
            is missing.

    Reads the size and the last 512-byte trailer. Does not mount the image.
    """
    assert_size(archive.name, archive.stat().st_size, min_bytes, max_bytes)
    with archive.open("rb") as handle:
        handle.seek(-512, os.SEEK_END)
        magic = handle.read(4)
    if magic != b"koly":
        raise SystemExit(f"{archive.name} is not a UDIF disk image")


def assert_setup(archive: Path) -> None:
    """Require the installer to be a 64-bit PE file of a plausible size.

    Args:
        archive: ``Serato-Library-windows-setup.exe``.

    Raises:
        SystemExit: If the size or the machine type is wrong.
    """
    assert_size(archive.name, archive.stat().st_size, MIN_ZIP_BYTES, MAX_ZIP_BYTES)
    machine = pe_machine(archive)
    if machine != PE_MACHINE_AMD64:
        raise SystemExit(f"{archive.name} machine {machine:#x} is not x64")


def _file_names(directory: Path) -> list[str]:
    """Return the sorted file names directly inside ``directory``.

    Args:
        directory: Folder to list.

    Returns:
        File names. Directories are ignored.
    """
    return sorted(path.name for path in directory.iterdir() if path.is_file())


def check_binaries(directory: Path) -> None:
    """Check the four release files without launching them.

    The publish job runs on Linux. It can read the Windows zip and the
    PE header, and it can read the UDIF trailer. It cannot mount a disk
    image or start either app. The build jobs already did that.

    Args:
        directory: Folder that holds the downloaded artifacts and no checksum
            file yet.

    Raises:
        SystemExit: If a file is missing, extra, or fails its check.
    """
    found = _file_names(directory)
    expected = sorted(RELEASE_FILES)
    if found != expected:
        raise SystemExit(f"Expected {', '.join(expected)}; found {', '.join(found) or 'nothing'}")
    assert_zip(directory / WINDOWS_ZIP, source_static())
    assert_dmg(directory / MACOS_ARM_DMG)
    assert_dmg(directory / MACOS_INTEL_DMG)
    assert_setup(directory / WINDOWS_SETUP)


def write_checksums(directory: Path) -> None:
    """Write ``SHA256SUMS`` for the four release files.

    Args:
        directory: Folder that already passed :func:`check_binaries`.

    Raises:
        SystemExit: If a release file is missing.

    Overwrites ``SHA256SUMS`` in that folder. The line format is the
    ``sha256sum`` format: hash, two spaces, file name.
    """
    lines = []
    for name in RELEASE_FILES:
        path = directory / name
        if not path.is_file():
            raise SystemExit(f"Missing {name}")
        lines.append(f"{sha256_file(path)}  {name}\n")
    (directory / CHECKSUMS_NAME).write_text("".join(lines), encoding="utf-8")


def check_checksums(directory: Path) -> None:
    """Require ``SHA256SUMS`` to match the four release files.

    Args:
        directory: Folder that contains the files and the checksum list.

    Raises:
        SystemExit: If a line is malformed, a hash differs, or an extra
            file is present.
    """
    path = directory / CHECKSUMS_NAME
    if not path.is_file():
        raise SystemExit(f"Missing {CHECKSUMS_NAME}")
    seen: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        if "  " not in line:
            raise SystemExit(f"Bad checksum line: {line!r}")
        digest, name = line.split("  ", 1)
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise SystemExit(f"Bad checksum for {name}")
        if name in seen:
            raise SystemExit(f"Duplicate checksum for {name}")
        seen[name] = digest
    if set(seen) != set(RELEASE_FILES):
        raise SystemExit(
            f"Checksum names {', '.join(sorted(seen)) or 'nothing'} "
            f"!= {', '.join(RELEASE_FILES)}"
        )
    for name, digest in seen.items():
        if sha256_file(directory / name) != digest:
            raise SystemExit(f"Checksum mismatch for {name}")
    extras = [
        item.name
        for item in directory.iterdir()
        if item.is_file() and item.name not in seen and item.name != CHECKSUMS_NAME
    ]
    if extras:
        raise SystemExit("Unexpected release files: " + ", ".join(sorted(extras)))


def make_dmg(app: Path, dest: Path) -> None:
    """Write a compressed disk image that contains ``app`` and an Applications link.

    Args:
        app: ``Serato Library.app``.
        dest: ``.dmg`` path to create.

    Raises:
        SystemExit: If this is not macOS, or ``dest`` already exists.
        subprocess.CalledProcessError: If ``hdiutil`` fails.

    Uses ``ditto`` so a signed bundle is copied without breaking its seal.
    """
    if sys.platform != "darwin":
        raise SystemExit("Disk images are built on macOS.")
    if dest.exists():
        raise SystemExit(f"Refusing to overwrite {dest}")
    with tempfile.TemporaryDirectory(prefix="serato-library-dmg-") as tmp:
        staging = Path(tmp) / "stage"
        staging.mkdir()
        subprocess.run(["ditto", str(app), str(staging / MACOS_APP)], check=True)
        (staging / "Applications").symlink_to("/Applications")
        subprocess.run(
            [
                "hdiutil",
                "create",
                "-volname",
                APP_NAME,
                "-srcfolder",
                str(staging),
                "-format",
                "UDZO",
                str(dest),
            ],
            check=True,
        )


def _mount_dmg(archive: Path) -> Path:
    """Attach ``archive`` read-only and return the mount point.

    Args:
        archive: Disk image.

    Returns:
        The volume path reported by ``hdiutil``.

    Raises:
        SystemExit: If no mount point is listed.
    """
    raw = subprocess.check_output(
        ["hdiutil", "attach", "-nobrowse", "-readonly", "-plist", str(archive)]
    )
    listing = plistlib.loads(raw)
    for entity in listing.get("system-entities", []):
        point = entity.get("mount-point")
        if point:
            return Path(point)
    raise SystemExit("hdiutil did not report a mount point")


def smoke_dmg(archive: Path, arch: str) -> None:
    """Mount ``archive``, copy the app out, and run the health smoke check.

    Args:
        archive: Disk image that already passed :func:`assert_dmg`.
        arch: ``arm64`` or ``x64``, checked on the copied executable.

    Raises:
        SystemExit: If the image has no app, the page differs, or smoke fails.

    The mounted volume is detached even when the check fails. The process
    that is launched is the copy, not the app inside the image.
    """
    mount = _mount_dmg(archive)
    try:
        app = mount / MACOS_APP
        if not app.is_dir():
            raise SystemExit(f"{archive.name} has no {MACOS_APP}")
        assert_static_matches(app, source_static())
        assert_frozen_arch(app / MACOS_EXE, arch)
        with tempfile.TemporaryDirectory(prefix="serato-library-artifact-") as tmp:
            copied = Path(tmp) / MACOS_APP
            subprocess.run(["ditto", str(app), str(copied)], check=True)
            run_smoke(copied / MACOS_EXE, Path(tmp))
    finally:
        subprocess.run(["hdiutil", "detach", str(mount)], check=False)


def pack_dmg(dist: Path, dest: Path, arch: str) -> None:
    """Check a macOS build, write a disk image, and smoke the copy inside it.

    Args:
        dist: PyInstaller ``dist`` directory.
        dest: Disk image to create.
        arch: ``arm64`` or ``x64``.

    Raises:
        SystemExit: If any check fails. A failed check deletes ``dest``.
    """
    verify_tree(dist)
    bundle = find_bundle(dist)
    if bundle.kind != "macos":
        raise SystemExit("pack-dmg needs a macOS app")
    assert_frozen_arch(bundle.exe, arch)
    if dest.exists():
        raise SystemExit(f"Refusing to overwrite {dest}")
    try:
        make_dmg(bundle.root, dest)
        assert_dmg(dest)
        smoke_dmg(dest, arch)
    except BaseException:
        dest.unlink(missing_ok=True)
        raise


def iscc_path() -> Path:
    """Return ``ISCC.exe`` from the pinned Inno Setup install.

    Returns:
        Absolute path of the compiler.

    Raises:
        SystemExit: If ``install-inno`` has not been run.
    """
    candidates = [
        Path(tempfile.gettempdir()) / f"innosetup-{INNO_VERSION}" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Inno Setup 6" / "ISCC.exe",
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise SystemExit("ISCC.exe not found. Run install-inno on Windows first.")


def install_inno() -> None:
    """Install the pinned Inno Setup compiler after checking its SHA-256.

    Raises:
        SystemExit: If this is not Windows, the download hash differs, or
            ``ISCC.exe`` is missing after the installer exits.

    A copy that is already present is left in place. The installer is the
    official 6.7.3 executable, not a package-manager latest.
    """
    if sys.platform != "win32":
        raise SystemExit("Inno Setup installs on Windows only.")
    directory = Path(tempfile.gettempdir()) / f"innosetup-{INNO_VERSION}"
    compiler = directory / "ISCC.exe"
    if compiler.is_file():
        return
    downloaded = Path(tempfile.gettempdir()) / f"innosetup-{INNO_VERSION}.exe"
    urllib.request.urlretrieve(INNO_URL, downloaded)
    digest = sha256_file(downloaded)
    if digest != INNO_SHA256:
        downloaded.unlink(missing_ok=True)
        raise SystemExit(f"Inno Setup hash {digest} != {INNO_SHA256}")
    subprocess.run(
        [
            str(downloaded),
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/NORESTART",
            f"/DIR={directory}",
        ],
        check=True,
        timeout=180,
    )
    if not compiler.is_file():
        raise SystemExit(f"ISCC missing after install: {compiler}")


def build_setup(dist: Path, dest: Path) -> None:
    """Compile the Inno Setup installer from the PyInstaller folder.

    Args:
        dist: Directory that contains ``Serato Library``.
        dest: Installer path to create. Its file name must be
            ``Serato-Library-windows-setup.exe``.

    Raises:
        SystemExit: If this is not Windows, the script or the build is
            missing, or the compiler does not write ``dest``.

    The version passed to the script is :func:`app_version`.
    """
    if sys.platform != "win32":
        raise SystemExit("The Windows installer is built on Windows.")
    if dest.name != WINDOWS_SETUP:
        raise SystemExit(f"Installer must be named {WINDOWS_SETUP}")
    if not ISS_PATH.is_file():
        raise SystemExit(f"Missing installer script: {ISS_PATH}")
    source = (dist / APP_NAME).resolve()
    dest = dest.resolve()
    if not (source / WINDOWS_EXE).is_file():
        raise SystemExit(f"Missing {source / WINDOWS_EXE}")
    if dest.exists():
        raise SystemExit(f"Refusing to overwrite {dest}")
    subprocess.run(
        [
            str(iscc_path()),
            f"/DAppVersion={app_version()}",
            f"/DSourceDir={source}",
            f"/O{dest.parent}",
            str(ISS_PATH),
        ],
        check=True,
    )
    if not dest.is_file():
        raise SystemExit(f"Installer was not written to {dest}")


def smoke_setup(setup: Path) -> None:
    """Install ``setup`` into a temporary directory and smoke that copy.

    Args:
        setup: Inno Setup installer.

    Raises:
        SystemExit: If this is not Windows, the install does not write the
            executable, or the health check fails.

    ``/VERYSILENT`` skips the post-install launch. The harness starts the
    installed executable itself, outside the repository.
    """
    if sys.platform != "win32":
        raise SystemExit("The installer smoke test runs on Windows.")
    with tempfile.TemporaryDirectory(prefix="serato-library-install-") as tmp:
        folder = Path(tmp)
        installed = folder / "app"
        subprocess.run(
            [
                str(setup),
                "/VERYSILENT",
                "/SUPPRESSMSGBOXES",
                "/NORESTART",
                f"/DIR={installed}",
            ],
            check=True,
            timeout=LAUNCH_TIMEOUT_SECONDS,
        )
        exe = installed / "Serato Library.exe"
        if not exe.is_file():
            raise SystemExit(f"Installer did not write {exe}")
        run_smoke(exe, folder)


def main(argv: list[str] | None = None) -> None:
    """Run a release-bundle subcommand.

    ``verify`` checks a dist tree. ``pack`` zips a Windows build and
    launches it. ``pack-dmg`` writes and smokes a disk image.
    ``check-binaries`` and ``check-checksums`` inspect a release folder
    without launching it. ``check-tag`` reads its argument, or
    ``RELEASE_TAG`` when the argument is omitted.

    Args:
        argv: Arguments after the program name. None reads the process arguments.

    Returns:
        None. ``footer`` prints the notes text to stdout.

    Raises:
        SystemExit: If the arguments are incomplete or a check fails.
    """
    parser = argparse.ArgumentParser(description="Check and pack a Serato Library build.")
    sub = parser.add_subparsers(dest="command", required=True)

    verify = sub.add_parser("verify", help="check a dist directory")
    verify.add_argument("dist", type=Path)

    packed = sub.add_parser("pack", help="check, zip, and launch a Windows build")
    packed.add_argument("dist", type=Path)
    packed.add_argument("zip", type=Path)

    image = sub.add_parser("pack-dmg", help="check, write, and launch a macOS disk image")
    image.add_argument("dist", type=Path)
    image.add_argument("dmg", type=Path)
    image.add_argument("arch", choices=("arm64", "x64"))

    arch = sub.add_parser("assert-arch", help="require the frozen executable architecture")
    arch.add_argument("dist", type=Path)
    arch.add_argument("arch", choices=("arm64", "x64"))

    binaries = sub.add_parser("check-binaries", help="check release files without launching them")
    binaries.add_argument("directory", type=Path)

    sums = sub.add_parser("write-checksums", help="write SHA256SUMS for the release files")
    sums.add_argument("directory", type=Path)

    checked = sub.add_parser("check-checksums", help="require SHA256SUMS to match the files")
    checked.add_argument("directory", type=Path)

    tag = sub.add_parser("check-tag", help="require a final or rc/beta tag")
    tag.add_argument("tag", nargs="?")

    flags = sub.add_parser("release-flags", help="print gh release create flags for the tag")
    flags.add_argument("tag", nargs="?")

    notes = sub.add_parser("footer", help="print the release-notes footer")
    notes.add_argument("repo")

    inno = sub.add_parser("install-inno", help="install the pinned Inno Setup compiler")

    setup = sub.add_parser("build-setup", help="compile the Windows installer")
    setup.add_argument("dist", type=Path)
    setup.add_argument("exe", type=Path)

    installed = sub.add_parser("smoke-setup", help="install the Windows installer and smoke it")
    installed.add_argument("exe", type=Path)

    args = parser.parse_args(argv)
    if args.command == "verify":
        verify_tree(args.dist)
    elif args.command == "pack":
        pack(args.dist, args.zip)
    elif args.command == "pack-dmg":
        pack_dmg(args.dist, args.dmg, args.arch)
    elif args.command == "assert-arch":
        assert_frozen_arch(find_bundle(args.dist).exe, args.arch)
    elif args.command == "check-binaries":
        check_binaries(args.directory)
    elif args.command == "write-checksums":
        write_checksums(args.directory)
    elif args.command == "check-checksums":
        check_checksums(args.directory)
    elif args.command == "check-tag":
        check_tag(args.tag if args.tag is not None else os.environ.get("RELEASE_TAG", ""))
    elif args.command == "release-flags":
        chosen = args.tag if args.tag is not None else os.environ.get("RELEASE_TAG", "")
        print("\n".join(release_create_flags(chosen)))
    elif args.command == "footer":
        print(footer(args.repo), end="")
    elif args.command == "install-inno":
        install_inno()
    elif args.command == "build-setup":
        build_setup(args.dist, args.exe)
    elif args.command == "smoke-setup":
        smoke_setup(args.exe)


if __name__ == "__main__":
    main()
