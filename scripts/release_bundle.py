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
        """Return the frozen executable."""
        return self.root / self.exe_rel


def source_static() -> Path:
    """Return the repository ``static`` directory."""
    return ROOT / "static"


def check_tag(tag: str) -> None:
    """Refuse a tag that is not ``vMAJOR.MINOR.PATCH``.

    Raises:
        SystemExit: If ``tag`` does not match that shape.
    """
    if TAG_RE.fullmatch(tag) is None:
        raise SystemExit(f"Tag must look like v1.2.3, got {tag!r}")


def footer(repo: str) -> str:
    """Return the release-notes footer with ``repo`` filled in.

    Raises:
        SystemExit: If the footer template has no repository placeholder.
    """
    text = (ROOT / "scripts" / "release-notes-footer.md").read_text(encoding="utf-8")
    if "OWNER/REPO" not in text:
        raise SystemExit("Release notes footer is missing OWNER/REPO")
    if not repo or "/" not in repo:
        raise SystemExit(f"Repository must look like owner/name, got {repo!r}")
    return text.replace("OWNER/REPO", repo)


def find_bundle(dist: Path) -> Bundle:
    """Find the macOS app or the Windows folder inside ``dist``.

    Raises:
        SystemExit: If neither build is present, both are, or the executable is missing.
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

    Symlinks count as zero. Their targets are counted when they are also
    files in the tree.
    """
    total = 0
    for path in root.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        total += path.stat().st_size
    return total


def assert_size(label: str, size: int, floor: int, ceiling: int) -> None:
    """Refuse a size outside the inclusive bounds.

    Raises:
        SystemExit: If ``size`` is below ``floor`` or above ``ceiling``.
    """
    if size < floor or size > ceiling:
        raise SystemExit(f"{label} is {size} bytes, outside {floor}..{ceiling}")


def _source_files(static_dir: Path) -> list[str]:
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

    Raises:
        SystemExit: If no bundled page is present, or a copy differs.
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
    if not name or name.startswith(("/", "\\")):
        return True
    parts = re.split(r"[\\/]", name)
    return any(part in ("", "..") or part.endswith(":") for part in parts)


def _link_stays_inside(link_rel: Path, target: str) -> bool:
    """Return whether a relative symlink stays inside the bundle directory."""
    if not target or "\n" in target or "\x00" in target:
        return False
    if os.path.isabs(target) or target.startswith("\\"):
        return False
    if len(target) > 1 and target[1] == ":":
        return False
    combined = Path(os.path.normpath(Path(link_rel).parent / target))
    if combined.is_absolute() or ".." in combined.parts or not combined.parts:
        return False
    return combined.parts[0] == Path(link_rel).parts[0]


def zip_bundle(root: Path, dest: Path) -> None:
    """Write ``root`` into a new zip at ``dest``.

    The archive entries keep the bundle directory name. Unix modes are
    stored, and symlinks stay symlinks. An existing ``dest`` is left alone.

    Raises:
        SystemExit: If ``dest`` exists, or a symlink points outside the bundle.
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
    return (info.external_attr >> 16) & 0xFFFF


def _is_symlink_member(info: zipfile.ZipInfo) -> bool:
    return stat.S_ISLNK(_unix_mode(info))


def assert_zip(
    archive: Path,
    source: Path,
    *,
    min_bytes: int = MIN_ZIP_BYTES,
    max_bytes: int = MAX_ZIP_BYTES,
) -> str:
    """Require a release zip to contain the executable and the page.

    Returns:
        ``macos`` or ``windows``, from the executable entry.

    Raises:
        SystemExit: If the zip is the wrong size, unsafe, or incomplete.
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

    Raises:
        SystemExit: If an entry is unsafe or a symlink points outside the archive.
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
    resolved = path.resolve()
    root = ROOT.resolve()
    if resolved == root or root in resolved.parents:
        raise SystemExit(f"Refusing to launch inside the repository: {resolved}")


def run_smoke(exe: Path, cwd: Path) -> None:
    """Run ``exe`` until it writes the smoke marker.

    The process gets an empty home directory, so a missing smoke hook
    cannot see the live Serato library. ``PYTHONPATH`` is not passed
    through.

    Raises:
        SystemExit: If the process fails, hangs, or does not write ``ok``.
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
    """Unpack ``archive`` outside the repository and run its smoke check."""
    with tempfile.TemporaryDirectory(prefix="serato-library-artifact-") as tmp:
        dest = Path(tmp) / "unzipped"
        unzip_bundle(archive, dest)
        bundle = find_bundle(dest)
        _outside_repo(bundle.exe)
        run_smoke(bundle.exe, Path(tmp))


def verify_tree(dist: Path) -> Bundle:
    """Check bundle size and that its page matches ``static/``.

    Returns:
        The bundle that was checked.

    Raises:
        SystemExit: If the build is missing, the wrong size, or its page differs.
    """
    bundle = find_bundle(dist)
    assert_size(str(bundle.root), directory_bytes(bundle.root), MIN_BUNDLE_BYTES, MAX_BUNDLE_BYTES)
    assert_static_matches(bundle.root, source_static())
    return bundle


def pack(dist: Path, dest: Path) -> None:
    """Zip a checked build, check the zip, then launch the unpacked app.

    Raises:
        SystemExit: If any check fails. A failed launch deletes ``dest``.
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

    Raises:
        SystemExit: If the directory does not hold exactly those two zips,
            or either zip fails its content check.
    """
    found = sorted(path.name for path in directory.iterdir() if path.is_file() and path.suffix == ".zip")
    if tuple(found) != tuple(sorted(EXPECTED_ZIPS)):
        raise SystemExit(f"Expected {', '.join(EXPECTED_ZIPS)}; found {', '.join(found) or 'nothing'}")
    source = source_static()
    for name in EXPECTED_ZIPS:
        assert_zip(directory / name, source)


def main(argv: list[str] | None = None) -> None:
    """Run a release-bundle subcommand.

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
