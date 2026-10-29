"""Checks for the release zip and the GitHub workflow files."""

from __future__ import annotations

import os
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
import zipfile
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import release_bundle  # noqa: E402
import static_assets  # noqa: E402
import version_info  # noqa: E402


def _pe(machine: int) -> bytes:
    """Return a tiny PE whose machine field is ``machine``.

    Args:
        machine: 16-bit PE machine id, such as ``0x14C`` or ``0x8664``.

    Returns:
        DOS and PE headers only. The body is not a runnable program.
    """
    data = bytearray(70)
    data[0:2] = b"MZ"
    data[0x3C:0x40] = (64).to_bytes(4, "little")
    data[64:68] = b"PE\0\0"
    data[68:70] = machine.to_bytes(2, "little")
    return bytes(data)


def _zip_windows_exes(archive: Path, members: dict[str, bytes]) -> None:
    """Write a zip of named Windows executables and nothing else.

    Args:
        archive: Zip path to create.
        members: Zip member name to file bytes.

    Returns:
        None.

    Writes ``archive``. The page files are omitted so a PE failure is
    reached before the page comparison.
    """
    with zipfile.ZipFile(archive, "w") as zipped:
        for name, payload in members.items():
            zipped.writestr(name, payload)


def _zip_tree(root: Path, archive: Path) -> None:
    """Zip ``root`` with paths relative to its parent.

    Args:
        root: Directory to pack, including its own name.
        archive: Zip path to create.

    Returns:
        None.

    Writes ``archive``.
    """
    parent = root.parent
    with zipfile.ZipFile(archive, "w") as zipped:
        for path in root.rglob("*"):
            if path.is_file():
                zipped.write(path, path.relative_to(parent).as_posix())


class AssetTests(unittest.TestCase):
    """Check the static-file list the spec and the zip check share.

    The cases read ``static/index.html`` or a temporary page. They do not
    build an app.
    """
    def test_library_page_assets(self) -> None:
        """List the local stylesheets and script on the library page.

        Remote font links must not count as bundled files. The order is the
        order of the tags. tokens.css comes before app.css.

        Returns:
            None. The test fails if the page names a different local file.
        """
        names = static_assets.local_asset_names(ROOT / "static" / "index.html")
        self.assertEqual(names, ["tokens.css", "app.css", "wizard.js", "app.js"])
        page = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        for name in (
            "wizard-welcome.svg",
            "wizard-find-library.svg",
            "wizard-safety-snapshot.svg",
            "wizard-consent.svg",
            "wizard-done.svg",
        ):
            artwork = (ROOT / "static" / "img" / "wizard" / name).read_text(encoding="utf-8").strip()
            self.assertIn(artwork, page)
        self.assertEqual(static_assets.missing_static_files(ROOT / "static"), [])

    def test_remote_links_are_not_assets(self) -> None:
        """Skip an https link and keep a local script with a query string.

        Writes a temporary HTML file. The query string is stripped so the asset
        name is ``app.js``.

        Returns:
            None. The test fails if the remote link is returned.
        """
        with tempfile.TemporaryDirectory() as tmp:
            page = Path(tmp) / "index.html"
            page.write_text(
                '<link href="https://example.com/a.css"><script src="app.js?v=1"></script>',
                encoding="utf-8",
            )
            self.assertEqual(static_assets.local_asset_names(page), ["app.js"])

    def test_missing_page_is_reported(self) -> None:
        """Report ``index.html`` when the static directory is empty.

        The directory is temporary and unused. No bundle is built.

        Returns:
            None. The test fails if a missing page is ignored.
        """
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(static_assets.missing_static_files(Path(tmp)), ["index.html"])

    def test_spec_uses_the_shared_asset_check(self) -> None:
        """Require the PyInstaller spec to stop when a page file is missing.

        Reads ``serato-library.spec``. It must call ``missing_static_files`` and
        raise ``SystemExit``. The spec is not executed.

        Returns:
            None. The test fails if the spec no longer shares that check.
        """
        text = (ROOT / "serato-library.spec").read_text(encoding="utf-8")
        self.assertIn("missing_static_files", text)
        self.assertIn("SystemExit", text)


class PinTests(unittest.TestCase):
    """Check that the build requirements pin the same app packages.

    The case reads the two requirements files. It does not install them.
    """
    def test_build_requirements_match_the_app_pin(self) -> None:
        """Repeat every app pin in the build file and pin PyInstaller.

        ``requirements-build.txt`` must contain each ``requirements.txt``
        line and pin ``pyinstaller`` with ``==``. ``requirements-macos.txt``
        pins the WKWebView frameworks the same way. Neither file is passed
        to pip.

        Returns:
            None. The test fails if a pin drifts or pystray returns.
        """
        app = [
            line
            for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
            if line and not line.startswith("#")
        ]
        build = (ROOT / "requirements-build.txt").read_text(encoding="utf-8").splitlines()
        for line in app:
            self.assertIn(line, build)
            self.assertIn("==", line)
        self.assertTrue(any(line.startswith("pyinstaller==") for line in build))
        self.assertTrue(any(line.startswith("pywebview==") for line in app))
        self.assertFalse(any(line.startswith("pystray==") or line.startswith("pillow==") for line in app + build))
        self.assertFalse(any(line.startswith("cefpython3") for line in app + build))
        macos = [
            line
            for line in (ROOT / "requirements-macos.txt").read_text(encoding="utf-8").splitlines()
            if line and not line.startswith("#")
        ]
        self.assertEqual(
            macos,
            [
                "pyobjc-core==12.2.2",
                "pyobjc-framework-Cocoa==12.2.2",
                "pyobjc-framework-Quartz==12.2.2",
                "pyobjc-framework-WebKit==12.2.2",
                "pyobjc-framework-Security==12.2.2",
                "pyobjc-framework-UniformTypeIdentifiers==12.2.2",
            ],
        )


class TagAndFooterTests(unittest.TestCase):
    """Check the release tag shape and the notes footer.

    The cases call ``release_bundle`` helpers. They do not publish a release.
    """
    def test_tag_shape(self) -> None:
        """Accept a final tag and an ``-rcN`` or ``-betaN`` prerelease.

        A tag without the leading ``v``, a missing component, a dotted
        suffix such as ``-rc.1``, or a full ref raises ``SystemExit``.
        No git command is run.

        Returns:
            None. The test fails if a rejected shape is accepted.
        """
        release_bundle.check_tag("v1.2.3")
        release_bundle.check_tag("v1.2.3-rc1")
        release_bundle.check_tag("v1.2.3-rc12")
        release_bundle.check_tag("v1.2.3-beta1")
        release_bundle.check_tag("v0.0.0-beta10")
        with self.assertRaises(SystemExit):
            release_bundle.check_tag("v1.2")
        with self.assertRaises(SystemExit):
            release_bundle.check_tag("1.2.3")
        with self.assertRaises(SystemExit):
            release_bundle.check_tag("v1.2.3-rc.1")
        with self.assertRaises(SystemExit):
            release_bundle.check_tag("v1.2.3-rc")
        with self.assertRaises(SystemExit):
            release_bundle.check_tag("v1.2.3-beta")
        with self.assertRaises(SystemExit):
            release_bundle.check_tag("v1.2.3-alpha1")
        with self.assertRaises(SystemExit):
            release_bundle.main(["check-tag", "refs/tags/v1.2.3"])

    def test_prerelease_flags_are_not_latest(self) -> None:
        """Publish prereleases without marking them latest.

        ``-rcN`` and ``-betaN`` take ``--prerelease`` and ``--latest=false``.
        A final tag takes ``--latest``. The command prints one flag per line.

        Returns:
            None. The test fails if a final tag is marked as a prerelease.
        """
        self.assertEqual(release_bundle.release_create_flags("v1.2.3"), ["--latest"])
        self.assertFalse(release_bundle.is_prerelease("v1.2.3"))
        for tag in ("v1.2.3-rc1", "v1.2.3-rc12", "v1.2.3-beta1", "v0.0.0-beta10"):
            self.assertTrue(release_bundle.is_prerelease(tag))
            self.assertEqual(
                release_bundle.release_create_flags(tag),
                ["--prerelease", "--latest=false"],
            )
        with mock.patch.dict(os.environ, {"RELEASE_TAG": "v1.2.3-rc2"}, clear=False):
            with mock.patch("sys.stdout") as stdout:
                release_bundle.main(["release-flags"])
        printed = "".join(call.args[0] for call in stdout.write.call_args_list)
        self.assertEqual(printed, "--prerelease\n--latest=false\n")

    def test_footer_fills_in_the_repository(self) -> None:
        """Substitute the repository name into the release-notes footer.

        Reads ``scripts/release-notes-footer.md`` and replaces ``OWNER/REPO``.
        The notes must still say the build is unsigned, that the server binds
        to loopback, and how to verify an attestation.

        Returns:
            None. The test fails if the placeholder remains.
        """
        text = release_bundle.footer("mookiejones/serato-library-manager")
        self.assertIn("mookiejones/serato-library-manager", text)
        self.assertNotIn("OWNER/REPO", text)
        self.assertIn("unsigned", text)
        self.assertIn("127.0.0.1", text)
        self.assertIn("gh attestation verify", text)


class ZipTests(unittest.TestCase):
    """Pack and unpack a tiny stand-in for the macOS bundle.

    The archive is built in a temporary directory. The real PyInstaller
    output is not required. Symlink cases are how the macOS app bundle is
    protected from a link that leaves the zip.
    """
    def _static(self, directory: Path) -> Path:
        """Write a two-file static directory for a bundle fixture.

        Args:
            directory: Parent that will contain ``static``.

        Returns:
            The ``static`` directory. ``index.html`` points at ``app.js``.
        """
        static = directory / "static"
        static.mkdir(parents=True)
        (static / "index.html").write_text("<script src=\"app.js\"></script>", encoding="utf-8")
        (static / "app.js").write_text("ok", encoding="utf-8")
        return static

    def _bundle(self, dist: Path, static: Path) -> Path:
        """Build a macOS-shaped app tree with an executable and one symlink.

        The executable is a shell script that writes the smoke marker. The
        symlink is the kind of Contents link a real bundle contains, and it
        stays inside the app.

        Args:
            dist: Directory that will contain ``Serato Library.app``.
            static: Page files copied into the bundle.

        Returns:
            ``dist``. The executable bit is set on the stand-in binary.
        """
        root = dist / "Serato Library.app" / "Contents" / "MacOS"
        root.mkdir(parents=True)
        exe = root / "Serato Library"
        exe.write_text("#!/bin/sh\nprintf 'ok\\n' > \"$SERATO_LIBRARY_SMOKE\"\n", encoding="utf-8")
        exe.chmod(0o755)
        bundled = root / "static"
        bundled.mkdir()
        for name in ("index.html", "app.js"):
            (bundled / name).write_bytes((static / name).read_bytes())
        link = dist / "Serato Library.app" / "Contents" / "Frameworks"
        link.mkdir()
        (link / "current").symlink_to(Path("..") / "MacOS" / "Serato Library")
        return dist

    def test_symlink_targets_must_stay_inside_the_bundle(self) -> None:
        """Allow a Contents symlink and refuse one that escapes the bundle.

        Absolute targets and targets that climb out of the app are rejected.
        No zip is written.

        Returns:
            None. The test fails if an escaping link is treated as safe.
        """
        inside = Path("Serato Library.app/Contents/Frameworks/current")
        self.assertTrue(release_bundle._link_stays_inside(inside, "../MacOS/Serato Library"))
        self.assertFalse(release_bundle._link_stays_inside(Path("Serato Library.app/escape"), "/tmp"))
        self.assertFalse(release_bundle._link_stays_inside(Path("Serato Library.app/escape"), "../../outside"))

    @unittest.skipUnless(sys.platform != "win32", "the fixture is a macOS app bundle")
    def test_roundtrip_keeps_mode_symlink_and_page(self) -> None:
        """Zip a macOS bundle and restore its mode, symlink, and page.

        Skipped on Windows because the fixture is an app bundle with a symlink.
        The executable bit and the relative link target must survive the zip.

        Returns:
            None. The test fails if the unpacked tree changes the link or the mode.
        """
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            static = self._static(base / "source")
            dist = self._bundle(base / "dist", static)
            archive = base / "Serato-Library-macos.zip"
            release_bundle.zip_bundle(dist / "Serato Library.app", archive)
            kind = release_bundle.assert_zip(archive, static, min_bytes=20, max_bytes=5_000_000)
            self.assertEqual(kind, "macos")
            unpacked = base / "out"
            release_bundle.unzip_bundle(archive, unpacked)
            exe = unpacked / "Serato Library.app" / "Contents" / "MacOS" / "Serato Library"
            self.assertTrue(exe.stat().st_mode & stat.S_IXUSR)
            restored = unpacked / "Serato Library.app" / "Contents" / "Frameworks" / "current"
            self.assertTrue(restored.is_symlink())
            self.assertEqual(os.readlink(restored), os.path.join("..", "MacOS", "Serato Library"))

    def test_symlink_out_of_the_bundle_is_refused(self) -> None:
        """Refuse to zip a symlink whose target is outside the bundle.

        Creates a temporary link to ``/tmp``. ``zip_bundle`` must raise
        ``SystemExit`` before it writes an archive that could escape later.

        Returns:
            None. The test fails if the zip is written.
        """
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "dist" / "Serato Library.app"
            root.mkdir(parents=True)
            (root / "escape").symlink_to("/tmp")
            with self.assertRaises(SystemExit):
                release_bundle.zip_bundle(root, base / "out.zip")

    def test_unsafe_zip_entry_is_refused(self) -> None:
        """Refuse a zip member that climbs out with ``..``.

        Writes a hostile archive and asks ``assert_zip`` to inspect it. The
        member must be rejected before it is extracted.

        Returns:
            None. The test fails if the entry is accepted.
        """
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "bad.zip"
            with zipfile.ZipFile(archive, "w") as zipped:
                zipped.writestr("../outside.txt", "no")
            with self.assertRaises(SystemExit):
                release_bundle.assert_zip(archive, Path(tmp), min_bytes=1, max_bytes=5_000_000)

    def test_run_smoke_accepts_the_marker(self) -> None:
        """Run a stand-in that serves health and exits on shutdown.

        On Windows the stand-in is a ``.cmd`` file. Elsewhere it is a
        Python script with a shebang. The harness must read the marker,
        GET ``/api/health``, POST shutdown, and see exit 0.

        Returns:
            None. The test fails if the smoke helper rejects that process.
        """
        standin = textwrap.dedent(
            """\
            import os
            import threading
            from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
            from pathlib import Path

            TOKEN = "smoke-token"

            class Handler(BaseHTTPRequestHandler):
                def do_GET(self):
                    body = b'{"ok": true}'
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

                def do_POST(self):
                    if self.headers.get("X-Serato-Library-Shutdown") != TOKEN:
                        self.send_error(403)
                        return
                    body = b'{"ok": true}'
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    threading.Thread(target=self.server.shutdown, daemon=True).start()

                def log_message(self, fmt, *args):
                    return

            httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            port = httpd.server_address[1]
            Path(os.environ["SERATO_LIBRARY_SMOKE"]).write_text(
                f"http://127.0.0.1:{port}\\n{TOKEN}\\n", encoding="utf-8"
            )
            httpd.serve_forever()
            """
        )
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            if sys.platform == "win32":
                script = base / "standin.py"
                script.write_text(standin, encoding="utf-8")
                exe = base / "smoke.cmd"
                exe.write_text(f'@echo off\r\n"{sys.executable}" "{script}"\r\n', encoding="utf-8")
            else:
                exe = base / "smoke"
                exe.write_text(f"#!{sys.executable}\n{standin}", encoding="utf-8")
                exe.chmod(0o755)
            release_bundle.run_smoke(exe, base)

    def test_run_smoke_refuses_the_repository(self) -> None:
        """Refuse to launch an executable that lives in this repository.

        ``desktop.py`` is inside the checkout. The smoke helper must raise
        before it starts that file, so a pack step cannot run the source tree.

        Returns:
            None. The test fails if ``SystemExit`` is not raised.
        """
        with self.assertRaises(SystemExit):
            release_bundle.run_smoke(ROOT / "desktop.py", ROOT)


class WorkflowTests(unittest.TestCase):
    """Check the GitHub workflow files against the documented suite.

    The cases read YAML. They do not trigger a workflow run.
    """
    def test_workflows_declare_permissions_and_timeouts(self) -> None:
        """Require every workflow to declare permissions, a timeout, and concurrency.

        Reads the workflow files. Each must limit ``contents`` and set
        ``timeout-minutes`` so a job cannot inherit a broad token or hang.

        Returns:
            None. The test fails if a workflow drops one of those blocks.
        """
        workflows = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(
            [path.name for path in workflows],
            [
                "ci.yml",
                "codeql.yml",
                "dependency-review.yml",
                "pages.yml",
                "release.yml",
            ],
        )
        for path in workflows:
            text = path.read_text(encoding="utf-8")
            self.assertIn("permissions:", text, path.name)
            self.assertIn("contents: read", text, path.name)
            self.assertIn("timeout-minutes:", text, path.name)
            self.assertIn("concurrency:", text, path.name)

    def test_ci_matches_the_documented_suite(self) -> None:
        """Match the CI command to the suite documented for this repository.

        CI runs unittest discovery on Ubuntu and Windows. It does not run a
        macOS test job. The dependency audit pins ``pip-audit``.

        Returns:
            None. The test fails if the workflow command drifts from the docs.
        """
        text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("python -m pip install -r requirements.txt", text)
        self.assertIn("python -m unittest discover -s tests -t . -v", text)
        self.assertIn("matrix.os == 'windows-latest'", text)
        self.assertIn("RELEASE_TAG: v0.0.0", text)
        self.assertIn("run: python scripts/release_bundle.py check-tag\n", text)
        self.assertNotIn("check-tag v0.0.0", text)
        self.assertIn("branches: [main]", text)
        self.assertIn("pull_request:", text)
        self.assertIn("pip-audit==2.10.1", text)
        self.assertIn("cancel-in-progress: true", text)
        self.assertNotIn("macos-latest", text)

    def test_release_does_not_cancel_and_checks_the_zip(self) -> None:
        """Keep a release running, and check the zip without launching it on Linux.

        The release workflow must not cancel in progress, must pack on the
        build runners, and must run ``check-binaries`` plus ``gh attestation verify``.
        Steps that use bash syntax must set ``shell: bash`` so Windows runners
        do not parse them with PowerShell. The tag is passed in ``RELEASE_TAG``,
        not by shell expansion.

        Returns:
            None. The test fails if the publish job starts launching apps.
        """
        text = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        self.assertIn("cancel-in-progress: false", text)
        self.assertIn("requirements-build.txt", text)
        self.assertIn("run: python scripts/write_build_config.py", text)
        bake = text.split("- name: Bake telemetry keys", 1)[1].split("\n      - ", 1)[0]
        self.assertIn("github.event_name == 'push'", bake)
        self.assertIn("startsWith(github.ref, 'refs/tags/v')", bake)
        self.assertIn("secrets.SENTRY_DSN", bake)
        self.assertIn("secrets.POSTHOG_KEY", bake)
        self.assertIn("secrets.POSTHOG_HOST", bake)
        self.assertNotIn("workflow_dispatch", bake)
        mac_sign = text.split("- name: Sign the macOS app when secrets are present", 1)[1].split(
            "\n      - ", 1
        )[0]
        self.assertIn("runner.os == 'macOS'", mac_sign)
        self.assertIn("APPLE_CERTIFICATE_P12_BASE64", mac_sign)
        self.assertNotIn("WINDOWS_", mac_sign)
        win_sign = text.split("- name: Sign the Windows app when secrets are present", 1)[1].split(
            "\n      - ", 1
        )[0]
        self.assertIn("runner.os == 'Windows'", win_sign)
        self.assertIn("WINDOWS_CERTIFICATE_PFX_BASE64", win_sign)
        self.assertIn("WINDOWS_CERTIFICATE_PASSWORD", win_sign)
        self.assertNotIn("APPLE_", win_sign)
        build = text.split("\n  build:\n", 1)[1].split("\n  release-build:", 1)[0]
        self.assertIn("github.event_name == 'pull_request'", build)
        build_perms = build.split("permissions:", 1)[1].split("strategy:", 1)[0]
        self.assertEqual(build_perms.strip(), "contents: read")
        self.assertEqual(build.count("uses: actions/upload-artifact@"), 3)
        self.assertIn("name: Serato-Library-windows.zip", build)
        self.assertIn("name: Serato-Library-windows-setup.exe", build)
        self.assertNotIn("secrets.", build)
        self.assertNotIn("id-token", build)
        self.assertNotIn("attestations", build)
        skipped = build.split("- name: Skip signing on a pull request", 1)[1].split("\n      - ", 1)[0]
        self.assertNotIn("secrets.", skipped)
        release_build = text.split("\n  release-build:\n", 1)[1].split("\n  attest:", 1)[0]
        self.assertIn("github.event_name != 'pull_request'", release_build)
        self.assertIn("actions: write", release_build.split("strategy:", 1)[0])
        self.assertNotIn("id-token", release_build.split("strategy:", 1)[0])
        attest = text.split("\n  attest:\n", 1)[1].split("\n  publish:", 1)[0]
        self.assertIn("id-token: write", attest)
        self.assertIn("attestations: write", attest)
        self.assertIn("actions: read", attest)
        self.assertNotIn("actions: write", attest)
        self.assertIn("workflow_dispatch", attest)
        self.assertIn("startsWith(github.ref, 'refs/tags/v')", attest)
        self.assertNotIn("pull_request", attest)
        header = text.split("jobs:", 1)[0]
        self.assertIn("pull_request:", header)
        self.assertIn("packaging/**", header)
        self.assertIn("serato-library.spec", header)
        self.assertIn("scripts/release_*", header)
        self.assertIn(".github/workflows/release.yml", header)
        self.assertIn("desktop.py", header)
        self.assertIn("requirements.txt", header)
        self.assertIn("requirements-build.txt", header)
        self.assertIn("requirements-macos.txt", header)
        self.assertIn("scripts/release_bundle.py pack", text)
        self.assertIn("scripts/release_bundle.py pack-dmg", text)
        self.assertIn("scripts/release_bundle.py check-binaries", text)
        self.assertIn("scripts/release_bundle.py check-checksums", text)
        self.assertIn("macos-15-intel", text)
        self.assertIn("Serato-Library-macos-arm64.dmg", text)
        self.assertIn("Serato-Library-macos-x64.dmg", text)
        self.assertIn("Serato-Library-windows-setup.exe", text)
        self.assertIn("SHA256SUMS", text)
        self.assertIn("gh attestation verify", text)
        self.assertIn("contents: write", text)
        self.assertIn("RELEASE_TAG:", text)
        self.assertIn("release-flags", text)
        publish = text.split("name: publish GitHub release", 1)[1].split("steps:", 1)[0]
        self.assertIn("github.event_name == 'push'", publish)
        self.assertIn("startsWith(github.ref, 'refs/tags/v')", publish)
        self.assertIn("&&", publish)
        self.assertNotIn("pull_request", publish)
        installer = text.split("Sign the installer when secrets are present", 1)[1].split(
            "\n      - ", 1
        )[0]
        self.assertNotIn("APPLE_", installer)
        self.assertIn("WINDOWS_CERTIFICATE_PFX_BASE64", installer)
        self.assertIn("WINDOWS_CERTIFICATE_PASSWORD", installer)
        self.assertNotIn("pull_request_target:", text)
        self.assertNotIn("${GITHUB_REF_NAME}", text)
        self.assertIn("shell: bash", text)
        for step in text.split("\n      - "):
            if "run:" not in step:
                continue
            uses_bash = (
                "${GITHUB_" in step
                or ">/dev/null" in step
                or "printf " in step
                or "$RELEASE_" in step
            )
            if uses_bash:
                self.assertIn("shell: bash", step)

    def test_documented_test_command_is_the_suite(self) -> None:
        """Document the same unittest command in the README and the GitHub guide.

        Reads those files. The guide must also say the server binds to
        ``127.0.0.1``. No test process is started here.

        Returns:
            None. The test fails if a documented command diverges.
        """
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("python3 -m unittest discover -s tests -t . -v", readme)
        guide = (ROOT / "docs" / "github.md").read_text(encoding="utf-8")
        self.assertIn("python3 -m unittest discover -s tests -t . -v", guide)
        self.assertIn("127.0.0.1", guide)


class OutsideLaunchTests(unittest.TestCase):
    """Check that the pack command launches the unpacked app.

    The case reads the release script and runs ``check-tag``. It does not
    zip a real build.
    """
    def test_smoke_script_is_what_the_frozen_app_runs(self) -> None:
        """Confirm pack launches the unzipped executable, not the source tree.

        Reads ``scripts/release_bundle.py`` and runs the ``check-tag``
        subcommand. ``PYTHONPATH`` must stay out of the smoke environment
        so the frozen app cannot import the checkout. The tag check does
        not build or launch an app.

        Returns:
            None. The test fails if the source no longer launches the
            unzipped bundle, or if ``check-tag`` rejects ``v0.0.0``.
        """
        source = (ROOT / "scripts" / "release_bundle.py").read_text(encoding="utf-8")
        self.assertIn("launch_unzipped", source)
        self.assertIn("/api/health", source)
        self.assertNotIn("PYTHONPATH", release_bundle._KEPT_ENV)
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "release_bundle.py"), "check-tag", "v0.0.0"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0)


class PackageTests(unittest.TestCase):
    """Check disk images, checksums, signing decisions, and the install page.

    The cases use temporary files. They do not build an app or call a
    signing tool.
    """

    def test_dmg_trailer_and_checksum_roundtrip(self) -> None:
        """Accept a UDIF trailer and a matching SHA256SUMS file.

        Writes a 512-byte image whose trailer starts with ``koly``, plus a
        tiny zip stand-in is not required. The checksum helper must refuse
        a changed byte.

        Returns:
            None. The test fails if a truncated image or a wrong hash is accepted.
        """
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            image = folder / "sample.dmg"
            image.write_bytes(b"koly" + b"\0" * 508)
            release_bundle.assert_dmg(image, min_bytes=512, max_bytes=600)
            image.write_bytes(b"\0" * 512)
            with self.assertRaises(SystemExit):
                release_bundle.assert_dmg(image, min_bytes=512, max_bytes=600)

    def test_checksums_match_the_release_names(self) -> None:
        """Write SHA256SUMS for stand-in release files and detect a mismatch.

        The four release names are required. An altered byte must fail
        ``check_checksums``. No archive is built.

        Returns:
            None. The test fails if a tampered file still matches.
        """
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for name in release_bundle.RELEASE_FILES:
                (folder / name).write_bytes(name.encode("utf-8"))
            release_bundle.write_checksums(folder)
            release_bundle.check_checksums(folder)
            (folder / release_bundle.WINDOWS_ZIP).write_bytes(b"changed")
            with self.assertRaises(SystemExit):
                release_bundle.check_checksums(folder)

    def test_signing_skips_when_secrets_are_absent(self) -> None:
        """Skip signing when every secret is empty, and refuse a partial set.

        The command must not start ``codesign`` or ``signtool``. A single
        secret without the rest is a configuration error.

        Returns:
            None. The test fails if a skip invokes a signing tool.
        """
        import release_sign

        empty = {name: "" for name in release_sign.APPLE_SECRETS + release_sign.WINDOWS_SECRETS}
        self.assertEqual(release_sign.signing_plan("darwin", empty), "skip")
        self.assertEqual(release_sign.signing_plan("win32", empty), "skip")
        partial = dict(empty)
        partial["APPLE_CERTIFICATE_PASSWORD"] = "secret-value"
        with self.assertRaises(SystemExit):
            release_sign.signing_plan("darwin", partial)
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "dist"
            target.mkdir()
            with mock.patch.dict(os.environ, empty, clear=False):
                with mock.patch("release_sign.subprocess.run") as run:
                    release_sign.main([str(target), "--platform", "darwin"])
            run.assert_not_called()

    def test_check_tag_reads_release_tag_from_the_environment(self) -> None:
        """Accept RELEASE_TAG when the command is given no argument.

        This is the path the Windows release job uses, so the shell does
        not expand the tag. A full ref still fails.

        Returns:
            None. The test fails if the environment value is ignored.
        """
        with mock.patch.dict(os.environ, {"RELEASE_TAG": "v1.2.3"}, clear=False):
            release_bundle.main(["check-tag"])
        with mock.patch.dict(os.environ, {"RELEASE_TAG": ""}, clear=False):
            with self.assertRaises(SystemExit):
                release_bundle.main(["check-tag"])

    def test_installer_script_does_not_hardcode_the_version(self) -> None:
        """Require the Inno script to take AppVersion from the build.

        The script must fail closed without ``/DAppVersion`` and must name
        the portable installer. The version passed to the compiler is the
        release identity, not a literal in the script.

        Returns:
            None. The test fails if the script bakes a version of its own.
        """
        text = (ROOT / "packaging" / "serato-library.iss").read_text(encoding="utf-8")
        self.assertIn("#ifndef AppVersion", text)
        self.assertIn("Serato-Library-windows-setup", text)
        self.assertIn("PrivilegesRequired=lowest", text)
        self.assertNotIn("SignTool=", text)
        self.assertEqual(release_bundle.app_version(), version_info.installer_version())
        self.assertRegex(
            release_bundle.app_version(),
            r"[0-9]+\.[0-9]+\.[0-9]+(?:-(?:rc|beta)[0-9]+)?",
        )
        self.assertIn(release_bundle.INNO_VERSION, release_bundle.INNO_URL)
        self.assertEqual(len(release_bundle.INNO_SHA256), 64)
        self.assertIn("ArchitecturesInstallIn64BitMode=x64compatible", text)
        self.assertIn("ArchitecturesAllowed=x64compatible", text)

    def test_installer_stub_may_be_32_bit(self) -> None:
        """Accept Inno's 32-bit setup stub and still require a PE.

        Inno Setup 6.7.3 writes ``Setup.e32`` (machine ``0x14c``) even
        when the script installs a 64-bit app. A stand-in of that shape
        must pass. Bytes that are not a PE must fail. The real script
        supplies the 64-bit directives.

        Returns:
            None. The test fails if a 32-bit stub is rejected as not x64.
        """
        stub = _pe(0x14C)
        with tempfile.TemporaryDirectory() as tmp:
            setup = Path(tmp) / "Serato-Library-windows-setup.exe"
            setup.write_bytes(stub)
            release_bundle.assert_setup(setup, min_bytes=len(stub), max_bytes=len(stub))
            setup.write_bytes(b"not a pe")
            with self.assertRaises(SystemExit):
                release_bundle.assert_setup(setup, min_bytes=1, max_bytes=20)

    def test_installer_script_must_select_64_bit_mode(self) -> None:
        """Refuse an Inno script that does not install in 64-bit mode.

        A copy of the script with the architecture lines removed must
        fail. The shipped script must pass.

        Returns:
            None. The test fails if a script without those lines is accepted.
        """
        release_bundle.assert_installer_script()
        text = release_bundle.ISS_PATH.read_text(encoding="utf-8")
        stripped = text.replace("ArchitecturesInstallIn64BitMode=x64compatible", "")
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "serato-library.iss"
            script.write_text(stripped, encoding="utf-8")
            with self.assertRaises(SystemExit) as caught:
                release_bundle.assert_installer_script(script)
        self.assertIn("ArchitecturesInstallIn64BitMode=x64compatible", str(caught.exception))

    def test_windows_zip_executable_must_be_x64(self) -> None:
        """Require the portable zip's application executable to be x64.

        A 32-bit PE in ``Serato Library.exe`` must fail. The same zip
        with machine ``0x8664`` must pass. The page files are the real
        ``static`` directory. No installer is built.

        Returns:
            None. The test fails if a 32-bit application executable is accepted.
        """
        static = release_bundle.source_static()
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "Serato Library"
            for path in static.rglob("*"):
                if not path.is_file() or path.is_symlink():
                    continue
                dest = root / "static" / path.relative_to(static)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(path.read_bytes())
            exe = root / "Serato Library.exe"
            exe.write_bytes(_pe(0x14C))
            narrow = base / "narrow.zip"
            _zip_tree(root, narrow)
            with self.assertRaises(SystemExit) as caught:
                release_bundle.assert_zip(narrow, static, min_bytes=20, max_bytes=5_000_000)
            self.assertIn("is not x64", str(caught.exception))
            exe.write_bytes(_pe(0x8664))
            wide = base / "wide.zip"
            _zip_tree(root, wide)
            kind = release_bundle.assert_zip(wide, static, min_bytes=20, max_bytes=5_000_000)
        self.assertEqual(kind, "windows")

    def test_windows_zip_requires_the_app_executable(self) -> None:
        """Refuse a portable zip that has no ``Serato Library.exe``.

        A page file alone is not a Windows bundle. The check must fail
        before it compares page bytes.

        Returns:
            None. The test fails if a zip without the application executable passes.
        """
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "missing.zip"
            with zipfile.ZipFile(archive, "w") as zipped:
                zipped.writestr("Serato Library/static/index.html", b"<p>missing</p>")
            with self.assertRaises(SystemExit) as caught:
                release_bundle.assert_zip(
                    archive,
                    release_bundle.source_static(),
                    min_bytes=1,
                    max_bytes=5_000_000,
                )
        self.assertIn("no Serato Library executable", str(caught.exception))

    def test_windows_zip_rejects_a_corrupt_pe(self) -> None:
        """Refuse an application executable that is not a PE.

        The member is named ``Serato Library.exe`` and starts with ``MZ``,
        but it has no PE signature. No installer is built.

        Returns:
            None. The test fails if a corrupt header is treated as x64.
        """
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "corrupt.zip"
            _zip_windows_exes(archive, {"Serato Library/Serato Library.exe": b"MZ" + b"\0" * 62})
            with self.assertRaises(SystemExit) as caught:
                release_bundle.assert_zip(
                    archive,
                    release_bundle.source_static(),
                    min_bytes=1,
                    max_bytes=5_000_000,
                )
        self.assertIn("has no PE header", str(caught.exception))

    def test_windows_zip_rejects_arm64(self) -> None:
        """Refuse an Arm64 application executable.

        Machine ``0xaa64`` is a PE, and it is not the x64 build this
        release ships. The portable zip must still fail.

        Returns:
            None. The test fails if Arm64 is accepted as x64.
        """
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "arm.zip"
            _zip_windows_exes(archive, {"Serato Library/Serato Library.exe": _pe(0xAA64)})
            with self.assertRaises(SystemExit) as caught:
                release_bundle.assert_zip(
                    archive,
                    release_bundle.source_static(),
                    min_bytes=1,
                    max_bytes=5_000_000,
                )
        self.assertIn("machine 0xaa64 is not x64", str(caught.exception))

    def test_windows_zip_rejects_a_32_bit_helper(self) -> None:
        """Refuse a 32-bit helper next to a 64-bit application executable.

        ``Serato Library.exe`` is machine ``0x8664``. ``helper.exe`` is
        machine ``0x14c``. Every ``.exe`` in the zip has to be x64.

        Returns:
            None. The test fails if the helper is ignored.
        """
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "helper.zip"
            _zip_windows_exes(
                archive,
                {
                    "Serato Library/Serato Library.exe": _pe(0x8664),
                    "Serato Library/helper.exe": _pe(0x14C),
                },
            )
            with self.assertRaises(SystemExit) as caught:
                release_bundle.assert_zip(
                    archive,
                    release_bundle.source_static(),
                    min_bytes=1,
                    max_bytes=5_000_000,
                )
        self.assertIn("helper.exe machine 0x14c is not x64", str(caught.exception))

    def test_first_install_names_the_files_and_the_volume_permission(self) -> None:
        """Document the release files and Removable Volumes beside Open Anyway.

        Reads ``docs/first-install.md``. The page must name each download,
        say the Serato Library window opens, and tell a Mac user to allow
        Removable Volumes rather than Full Disk Access. It must not link
        a missing panic page.

        Returns:
            None. The test fails if a shipped name or the permission is absent.
        """
        text = (ROOT / "docs" / "first-install.md").read_text(encoding="utf-8")
        for name in release_bundle.RELEASE_FILES + (release_bundle.CHECKSUMS_NAME,):
            self.assertIn(name, text)
        self.assertIn("Open Anyway", text)
        self.assertIn("Removable Volumes", text)
        self.assertIn("Full Disk Access", text)
        self.assertIn("Privacy & Security", text)
        self.assertIn("Files and Folders", text)
        self.assertIn("Close the window", text)
        self.assertIn("WebView2", text)
        self.assertNotIn("menu-bar", text)
        self.assertNotIn("notification area", text)
        self.assertIn("127.0.0.1", text)
        self.assertNotIn("panic.md", text)
        self.assertNotIn("PREVIEW", text)
        spec = (ROOT / "serato-library.spec").read_text(encoding="utf-8")
        self.assertIn("NSRemovableVolumesUsageDescription", spec)
        self.assertIn("webview.platforms.edgechromium", spec)
        self.assertIn("webview.platforms.cocoa", spec)
        self.assertIn("webview.platforms.gtk", spec)
        self.assertIn('"cefpython3"', spec)
        self.assertIn('"pystray"', spec)
        self.assertNotIn("pystray._", spec)
        self.assertNotIn("LSUIElement", spec)


if __name__ == "__main__":
    unittest.main()
