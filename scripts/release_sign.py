#!/usr/bin/env python3
"""Sign a frozen build when the release secrets are present.

The secrets are not configured. When every secret for this operating
system is missing, signing is skipped and the process exits 0. When some
of them are set and some are not, the process exits 1 so a half-configured
release is not published as if signing had been turned off on purpose.

Nothing in this file prints a secret. Certificate bytes are written to a
0600 file under a temporary directory and deleted before returning.
"""

from __future__ import annotations

import argparse
import base64
import os
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# SIGNING HOOKS. These names are the GitHub Actions secrets. They do not
# exist yet. Add them on the repository when a Developer ID certificate
# and a Windows code-signing certificate are available. Do not commit the
# values.
APPLE_SECRETS = (
    "APPLE_CERTIFICATE_P12_BASE64",
    "APPLE_CERTIFICATE_PASSWORD",
    "APPLE_SIGNING_IDENTITY",
    "APPLE_NOTARY_KEY_BASE64",
    "APPLE_NOTARY_KEY_ID",
    "APPLE_NOTARY_ISSUER_ID",
)
WINDOWS_SECRETS = (
    "WINDOWS_CERTIFICATE_PFX_BASE64",
    "WINDOWS_CERTIFICATE_PASSWORD",
)
_MACHO = (
    b"\xfe\xed\xfa\xce",
    b"\xfe\xed\xfa\xcf",
    b"\xce\xfa\xed\xfe",
    b"\xcf\xfa\xed\xfe",
    b"\xca\xfe\xba\xbe",
    b"\xbe\xba\xfe\xca",
)


def signing_plan(platform: str, environ: Mapping[str, str]) -> str:
    """Decide whether this platform signs or skips.

    Args:
        platform: ``darwin``, ``win32``, or another ``sys.platform`` value.
        environ: Environment to read. Tests pass a dict. The command line
            passes ``os.environ``.

    Returns:
        ``skip`` when this platform has no hook, or when every secret for
        the platform is empty. ``sign`` when every secret is non-empty.

    Raises:
        SystemExit: If at least one secret is set and another is empty.
    """
    if platform == "darwin":
        names = APPLE_SECRETS
        label = "Apple Developer ID notarization"
    elif platform == "win32":
        names = WINDOWS_SECRETS
        label = "Windows signing"
    else:
        print(f"Signing skipped: no signing hook for {platform}.")
        return "skip"
    present = [name for name in names if environ.get(name, "").strip()]
    if not present:
        print(f"Signing skipped: {label} secrets are not set.")
        return "skip"
    if len(present) != len(names):
        missing = [name for name in names if name not in present]
        raise SystemExit(
            f"Signing secrets are incomplete ({', '.join(missing)}). "
            "Refusing to sign, and refusing to skip."
        )
    print(f"Signing with {label}.")
    return "sign"


def _redact(text: str, secrets: list[str]) -> str:
    """Replace secret values in ``text``.

    Args:
        text: Command output.
        secrets: Values that must not be shown. Empty strings are ignored.

    Returns:
        ``text`` with each secret replaced by ``[redacted]``.
    """
    redacted = text
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[redacted]")
    return redacted


def _run(argv: list[str], secrets: list[str]) -> None:
    """Run a signing command and hide secret values in its output.

    Args:
        argv: Program and arguments.
        secrets: Values to strip from captured output.

    Raises:
        SystemExit: If the command exits non-zero.
    """
    completed = subprocess.run(argv, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        out = _redact(completed.stdout or "", secrets)
        err = _redact(completed.stderr or "", secrets)
        raise SystemExit(f"{argv[0]} failed ({completed.returncode}).\n{out}\n{err}")


def _write_secret_file(value: str, dest: Path) -> None:
    """Decode a base64 secret into ``dest`` with mode 0600.

    Args:
        value: Base64 text. The text itself is not written into an error.
        dest: File to create.

    Raises:
        SystemExit: If the text is not valid base64 or decodes to nothing.
    """
    try:
        data = base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as exc:
        raise SystemExit("A signing secret is not valid base64.") from exc
    if not data:
        raise SystemExit("A signing secret decoded to an empty file.")
    dest.write_bytes(data)
    os.chmod(dest, 0o600)


def _is_macho(path: Path) -> bool:
    """Return whether ``path`` starts with a Mach-O magic number.

    Args:
        path: File inside the app bundle.

    Returns:
        True for thin and universal Mach-O. False for other files and
        for files that cannot be read.
    """
    try:
        with path.open("rb") as handle:
            magic = handle.read(4)
    except OSError:
        return False
    return magic in _MACHO


def sign_macos(app: Path, environ: Mapping[str, str]) -> None:
    """Codesign ``app``, notarize it, and staple the ticket.

    Args:
        app: ``Serato Library.app`` bundle.
        environ: Mapping that holds the Apple secrets.

    Raises:
        SystemExit: If a tool fails, or the entitlements file is missing.

    The Developer ID certificate and the notary key are deleted in a
    ``finally`` block. The keychain created for the import is deleted too.
    """
    entitlements = ROOT / "packaging" / "entitlements.plist"
    if not entitlements.is_file():
        raise SystemExit(f"Missing signing input: {entitlements}")
    identity = environ["APPLE_SIGNING_IDENTITY"].strip()
    password = environ["APPLE_CERTIFICATE_PASSWORD"]
    hidden = [password, environ["APPLE_NOTARY_KEY_BASE64"], environ["APPLE_CERTIFICATE_P12_BASE64"]]
    keychain_password = os.urandom(16).hex()
    hidden.append(keychain_password)
    with tempfile.TemporaryDirectory(prefix="serato-library-sign-") as tmp:
        folder = Path(tmp)
        certificate = folder / "developer-id.p12"
        key = folder / "AuthKey.p8"
        keychain = folder / "signing.keychain-db"
        archive = folder / "SeratoLibrary.zip"
        _write_secret_file(environ["APPLE_CERTIFICATE_P12_BASE64"], certificate)
        _write_secret_file(environ["APPLE_NOTARY_KEY_BASE64"], key)
        try:
            _run(["security", "create-keychain", "-p", keychain_password, str(keychain)], hidden)
            _run(
                ["security", "unlock-keychain", "-p", keychain_password, str(keychain)],
                hidden,
            )
            _run(
                [
                    "security",
                    "import",
                    str(certificate),
                    "-k",
                    str(keychain),
                    "-P",
                    password,
                    "-T",
                    "/usr/bin/codesign",
                    "-T",
                    "/usr/bin/security",
                ],
                hidden,
            )
            _run(
                [
                    "security",
                    "set-key-partition-list",
                    "-S",
                    "apple-tool:,apple:,codesign:",
                    "-s",
                    "-k",
                    keychain_password,
                    str(keychain),
                ],
                hidden,
            )
            binaries = [
                path
                for path in app.rglob("*")
                if path.is_file() and not path.is_symlink() and _is_macho(path)
            ]
            binaries.sort(key=lambda path: len(path.parts), reverse=True)
            for path in binaries:
                _run(
                    [
                        "codesign",
                        "--force",
                        "--sign",
                        identity,
                        "--options",
                        "runtime",
                        "--timestamp",
                        "--keychain",
                        str(keychain),
                        str(path),
                    ],
                    hidden,
                )
            _run(
                [
                    "codesign",
                    "--force",
                    "--sign",
                    identity,
                    "--options",
                    "runtime",
                    "--timestamp",
                    "--keychain",
                    str(keychain),
                    "--entitlements",
                    str(entitlements),
                    str(app),
                ],
                hidden,
            )
            _run(["ditto", "-c", "-k", "--keepParent", str(app), str(archive)], hidden)
            _run(
                [
                    "xcrun",
                    "notarytool",
                    "submit",
                    str(archive),
                    "--key",
                    str(key),
                    "--key-id",
                    environ["APPLE_NOTARY_KEY_ID"].strip(),
                    "--issuer",
                    environ["APPLE_NOTARY_ISSUER_ID"].strip(),
                    "--wait",
                ],
                hidden,
            )
            _run(["xcrun", "stapler", "staple", str(app)], hidden)
        finally:
            subprocess.run(
                ["security", "delete-keychain", str(keychain)],
                check=False,
                capture_output=True,
            )


def _signtool() -> Path:
    """Return the newest Windows SDK ``signtool.exe``.

    Returns:
        Absolute path of the tool.

    Raises:
        SystemExit: If the Windows SDK is not installed.
    """
    roots = [
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Windows Kits" / "10" / "bin",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Windows Kits" / "10" / "bin",
    ]
    found = []
    for root in roots:
        if root.is_dir():
            found.extend(root.glob("*/x64/signtool.exe"))
    found = [path for path in found if path.is_file()]
    if not found:
        raise SystemExit("signtool.exe was not found. Install the Windows SDK.")
    return sorted(found)[-1]


def sign_windows(target: Path, environ: Mapping[str, str]) -> None:
    """Authenticode-sign an executable, or every exe and dll under a folder.

    Args:
        target: ``Serato Library.exe``, the installer, or the PyInstaller folder.
        environ: Mapping that holds the Windows secrets.

    Raises:
        SystemExit: If signtool fails, or the target contains nothing to sign.
    """
    password = environ["WINDOWS_CERTIFICATE_PASSWORD"]
    hidden = [password, environ["WINDOWS_CERTIFICATE_PFX_BASE64"]]
    if target.is_dir():
        files = [
            path
            for path in target.rglob("*")
            if path.is_file() and path.suffix.lower() in {".exe", ".dll"}
        ]
    elif target.is_file() and target.suffix.lower() == ".exe":
        files = [target]
    else:
        raise SystemExit(f"Nothing to sign at {target}")
    if not files:
        raise SystemExit(f"No executables under {target}")
    tool = _signtool()
    with tempfile.TemporaryDirectory(prefix="serato-library-sign-") as tmp:
        certificate = Path(tmp) / "codesign.pfx"
        _write_secret_file(environ["WINDOWS_CERTIFICATE_PFX_BASE64"], certificate)
        for path in files:
            _run(
                [
                    str(tool),
                    "sign",
                    "/fd",
                    "SHA256",
                    "/tr",
                    "http://timestamp.acs.microsoft.com",
                    "/td",
                    "SHA256",
                    "/f",
                    str(certificate),
                    "/p",
                    password,
                    str(path),
                ],
                hidden,
            )


def _bundle(path: Path, platform: str) -> Path:
    """Return the app or folder inside ``path``.

    Args:
        path: ``dist``, an ``.app``, an ``.exe``, or the Windows folder.
        platform: ``darwin`` or ``win32``.

    Returns:
        The path that should be signed.

    Raises:
        SystemExit: If the expected build is missing.
    """
    if platform == "darwin":
        if path.name.endswith(".app") and path.is_dir():
            return path
        app = path / "Serato Library.app"
        if app.is_dir():
            return app
        raise SystemExit(f"No macOS app to sign in {path}")
    if path.is_file() and path.suffix.lower() == ".exe":
        return path
    folder = path / "Serato Library" if (path / "Serato Library").is_dir() else path
    if folder.is_dir():
        return folder
    raise SystemExit(f"No Windows build to sign in {path}")


def main(argv: list[str] | None = None) -> None:
    """Sign ``target`` or skip when the secrets are absent.

    Args:
        argv: Arguments after the program name. None reads the process arguments.

    Raises:
        SystemExit: If the target is missing, the secrets are incomplete,
            or a signing tool fails.
    """
    parser = argparse.ArgumentParser(description="Sign a Serato Library build, or skip.")
    parser.add_argument("target", type=Path)
    parser.add_argument("--platform", default=sys.platform)
    args = parser.parse_args(argv)
    if not args.target.exists():
        raise SystemExit(f"Nothing to sign at {args.target}")
    plan = signing_plan(args.platform, os.environ)
    if plan != "sign":
        return
    bundle = _bundle(args.target, args.platform)
    if args.platform == "darwin":
        sign_macos(bundle, os.environ)
    elif args.platform == "win32":
        sign_windows(bundle, os.environ)


if __name__ == "__main__":
    main()
