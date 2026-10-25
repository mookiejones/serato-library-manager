#!/usr/bin/env python3
"""Check a PyInstaller build and zip it for a GitHub release.

The zip is unpacked outside the repository and the frozen app is started
with SERATO_LIBRARY_SMOKE. That path writes a marker and exits. It does
not open the Serato library or a window. Publishing checks the zip again
and does not launch it: a Linux runner cannot start the macOS app.
"""

from __future__ import annotations

import argparse
import os
import re
import stat
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import desktop  # noqa: E402
import static_assets  # noqa: E402

APP_NAME = "Serato Library"
MACOS_APP = "Serato Library.app"
MACOS_EXE = Path("Contents/MacOS/Serato Library")
WINDOWS_EXE = Path("Serato Library.exe")
MACOS_ZIP = "Serato-Library-macos.zip"
WINDOWS_ZIP = "Serato-Library-windows.zip"
EXPECTED_ZIPS = (MACOS_ZIP, WINDOWS_ZIP)
SMOKE_TEXT = "ok\n"
TAG_RE = re.compile(r"v[0-9]+\.[0-9]+\.[0-9]+")
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
    """Refuse a tag that is not ``vMAJOR.MINOR.PATCH``.

    Release zips are published only for that shape, so a pre-release or
    a tag without the leading ``v`` stops before any file is packed.

    Args:
        tag: Git tag text, such as ``v1.2.3``.

    Returns:
        None.

    Raises:
        SystemExit: If ``tag`` does not match that shape.

    Does not read the git repository or write a file.
    """
    if TAG_RE.fullmatch(tag) is None:
        raise SystemExit(f"Tag must look like v1.2.3, got {tag!r}")


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


def run_smoke(exe: Path, cwd: Path) -> None:
    """Run ``exe`` until it writes the smoke marker.

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
        SystemExit: If ``exe`` is inside the repository, the process fails,
            it hangs past the timeout, or it does not write ``ok``.

    Starts a subprocess and writes the marker path into its environment.
    The launched program writes the marker file.
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
    try:
        proc = subprocess.run(
            [str(exe)],
            cwd=cwd,
            env=env,
            capture_output=True,
            timeout=LAUNCH_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise SystemExit(f"Bundle did not exit within {LAUNCH_TIMEOUT_SECONDS}s") from exc
    text = marker.read_text(encoding="utf-8") if marker.is_file() else ""
    if proc.returncode != 0 or text != SMOKE_TEXT:
        out = (proc.stdout or b"").decode("utf-8", "replace")
        err = (proc.stderr or b"").decode("utf-8", "replace")
        raise SystemExit(f"Smoke check failed (exit {proc.returncode}).\n{out}\n{err}")


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


def check_zips(directory: Path) -> None:
    """Check the two release zips without launching them.

    The publish job runs on Linux and can only inspect the archives.
    The directory must contain exactly the macOS zip and the Windows zip.

    Args:
        directory: Folder that holds the downloaded release artifacts.

    Returns:
        None.

    Raises:
        SystemExit: If the directory does not hold exactly those two zips,
            or either zip fails its content check.

    Reads the zips. Does not extract them or start an executable.
    """
    found = sorted(path.name for path in directory.iterdir() if path.is_file() and path.suffix == ".zip")
    if tuple(found) != tuple(sorted(EXPECTED_ZIPS)):
        raise SystemExit(f"Expected {', '.join(EXPECTED_ZIPS)}; found {', '.join(found) or 'nothing'}")
    source = source_static()
    for name in EXPECTED_ZIPS:
        assert_zip(directory / name, source)


def main(argv: list[str] | None = None) -> None:
    """Run a release-bundle subcommand.

    ``verify`` checks a dist tree. ``pack`` zips it and launches the
    unpacked app. ``check-zips`` inspects the two release archives.
    ``check-tag`` and ``footer`` serve the GitHub release workflow.

    Args:
        argv: Arguments after the program name. None reads the process arguments.

    Returns:
        None. ``footer`` prints the notes text to stdout.

    Raises:
        SystemExit: If the arguments are incomplete or a check fails.
    """
    parser = argparse.ArgumentParser(description="Check and zip a Serato Library build.")
    sub = parser.add_subparsers(dest="command", required=True)

    verify = sub.add_parser("verify", help="check a dist directory")
    verify.add_argument("dist", type=Path)

    packed = sub.add_parser("pack", help="check, zip, and launch a build")
    packed.add_argument("dist", type=Path)
    packed.add_argument("zip", type=Path)

    zips = sub.add_parser("check-zips", help="check release zips without launching them")
    zips.add_argument("directory", type=Path)

    tag = sub.add_parser("check-tag", help="require a vMAJOR.MINOR.PATCH tag")
    tag.add_argument("tag")

    notes = sub.add_parser("footer", help="print the release-notes footer")
    notes.add_argument("repo")

    args = parser.parse_args(argv)
    if args.command == "verify":
        verify_tree(args.dist)
    elif args.command == "pack":
        pack(args.dist, args.zip)
    elif args.command == "check-zips":
        check_zips(args.directory)
    elif args.command == "check-tag":
        check_tag(args.tag)
    elif args.command == "footer":
        print(footer(args.repo), end="")


if __name__ == "__main__":
    main()
