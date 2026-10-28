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
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import release_bundle  # noqa: E402
import static_assets  # noqa: E402


class AssetTests(unittest.TestCase):
    """Check the static-file list the spec and the zip check share.

    The cases read ``static/index.html`` or a temporary page. They do not
    build an app.
    """
    def test_library_page_assets(self) -> None:
        """List the local stylesheet and script on the library page.

        Remote font links must not count as bundled files. The order is the
        order of the tags.

        Returns:
            None. The test fails if the page names a different local file.
        """
        names = static_assets.local_asset_names(ROOT / "static" / "index.html")
        self.assertEqual(names, ["app.css", "app.js"])

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
        """Keep pywebview on one pin and require a pinned PyInstaller.

        ``requirements-build.txt`` must repeat the pywebview line from
        ``requirements.txt`` and pin ``pyinstaller`` with ``==``. Neither file
        is passed to pip.

        Returns:
            None. The test fails if the pins drift apart.
        """
        app = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        build = (ROOT / "requirements-build.txt").read_text(encoding="utf-8").splitlines()
        webview = [line for line in app if line.startswith("pywebview==")]
        self.assertEqual(webview, [line for line in build if line.startswith("pywebview==")])
        self.assertEqual(len(webview), 1)
        pinned = [line for line in build if line.startswith("pyinstaller==")]
        self.assertEqual(len(pinned), 1)
        self.assertIn("==", pinned[0])


class TagAndFooterTests(unittest.TestCase):
    """Check the release tag shape and the notes footer.

    The cases call ``release_bundle`` helpers. They do not publish a release.
    """
    def test_tag_shape(self) -> None:
        """Accept ``vMAJOR.MINOR.PATCH`` and reject shorter or pre-release tags.

        A tag without the leading ``v``, a missing component, or a suffix such
        as ``-rc.1`` raises ``SystemExit``. No git command is run.

        Returns:
            None. The test fails if a rejected shape is accepted.
        """
        release_bundle.check_tag("v1.2.3")
        with self.assertRaises(SystemExit):
            release_bundle.check_tag("v1.2")
        with self.assertRaises(SystemExit):
            release_bundle.check_tag("1.2.3")
        with self.assertRaises(SystemExit):
            release_bundle.check_tag("v1.2.3-rc.1")

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
        """Run a stand-in executable that writes the smoke marker.

        On Windows the stand-in is a ``.cmd`` file. Elsewhere it is a shell
        script. The process must see ``SERATO_LIBRARY_SMOKE`` and write ``ok``.

        Returns:
            None. The test fails if the smoke helper rejects that marker.
        """
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            if sys.platform == "win32":
                exe = base / "smoke.cmd"
                exe.write_text(
                    textwrap.dedent(
                        """\
                        @echo off
                        python -c "from pathlib import Path; import os; Path(os.environ['SERATO_LIBRARY_SMOKE']).write_text('ok\\n', encoding='utf-8')"
                        """
                    ),
                    encoding="utf-8",
                )
            else:
                exe = base / "smoke"
                exe.write_text("#!/bin/sh\nprintf 'ok\\n' > \"$SERATO_LIBRARY_SMOKE\"\n", encoding="utf-8")
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
        self.assertIn("branches: [main]", text)
        self.assertIn("pull_request:", text)
        self.assertIn("pip-audit==2.10.1", text)
        self.assertIn("cancel-in-progress: true", text)
        self.assertNotIn("macos-latest", text)

    def test_release_does_not_cancel_and_checks_the_zip(self) -> None:
        """Keep a release running, and check the zip without launching it on Linux.

        The release workflow must not cancel in progress, must pack on the
        build runners, and must run ``check-zips`` plus ``gh attestation verify``.
        Steps that use bash syntax must set ``shell: bash`` so Windows runners
        do not parse them with PowerShell.

        Returns:
            None. The test fails if the publish job starts launching apps.
        """
        text = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        self.assertIn("cancel-in-progress: false", text)
        self.assertIn("requirements-build.txt", text)
        self.assertIn("run: python scripts/write_build_config.py", text)
        self.assertIn("secrets.SENTRY_DSN", text)
        self.assertIn("secrets.POSTHOG_KEY", text)
        self.assertIn("secrets.POSTHOG_HOST", text)
        self.assertIn("scripts/release_bundle.py pack", text)
        self.assertIn("scripts/release_bundle.py check-zips", text)
        self.assertIn("gh attestation verify", text)
        self.assertIn("contents: write", text)
        self.assertNotIn("pull_request:", text)
        self.assertNotIn("pull_request_target:", text)
        self.assertIn("shell: bash", text)
        for step in text.split("\n      - "):
            if "run:" not in step:
                continue
            uses_bash = "${GITHUB_" in step or ">/dev/null" in step or "printf " in step
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
        self.assertNotIn("PYTHONPATH", release_bundle._KEPT_ENV)
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "release_bundle.py"), "check-tag", "v0.0.0"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()
