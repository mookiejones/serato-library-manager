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
    def test_library_page_assets(self) -> None:
        names = static_assets.local_asset_names(ROOT / "static" / "index.html")
        self.assertEqual(names, ["app.css", "app.js"])

    def test_remote_links_are_not_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            page = Path(tmp) / "index.html"
            page.write_text(
                '<link href="https://example.com/a.css"><script src="app.js?v=1"></script>',
                encoding="utf-8",
            )
            self.assertEqual(static_assets.local_asset_names(page), ["app.js"])

    def test_missing_page_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(static_assets.missing_static_files(Path(tmp)), ["index.html"])

    def test_spec_uses_the_shared_asset_check(self) -> None:
        text = (ROOT / "serato-library.spec").read_text(encoding="utf-8")
        self.assertIn("missing_static_files", text)
        self.assertIn("SystemExit", text)


class PinTests(unittest.TestCase):
    def test_build_requirements_match_the_app_pin(self) -> None:
        app = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        build = (ROOT / "requirements-build.txt").read_text(encoding="utf-8").splitlines()
        webview = [line for line in app if line.startswith("pywebview==")]
        self.assertEqual(webview, [line for line in build if line.startswith("pywebview==")])
        self.assertEqual(len(webview), 1)
        pinned = [line for line in build if line.startswith("pyinstaller==")]
        self.assertEqual(len(pinned), 1)
        self.assertIn("==", pinned[0])


class TagAndFooterTests(unittest.TestCase):
    def test_tag_shape(self) -> None:
        release_bundle.check_tag("v1.2.3")
        with self.assertRaises(SystemExit):
            release_bundle.check_tag("v1.2")
        with self.assertRaises(SystemExit):
            release_bundle.check_tag("1.2.3")
        with self.assertRaises(SystemExit):
            release_bundle.check_tag("v1.2.3-rc.1")

    def test_footer_fills_in_the_repository(self) -> None:
        text = release_bundle.footer("mookiejones/serato-library-manager")
        self.assertIn("mookiejones/serato-library-manager", text)
        self.assertNotIn("OWNER/REPO", text)
        self.assertIn("unsigned", text)
        self.assertIn("127.0.0.1", text)
        self.assertIn("gh attestation verify", text)


class ZipTests(unittest.TestCase):
    def _static(self, directory: Path) -> Path:
        static = directory / "static"
        static.mkdir(parents=True)
        (static / "index.html").write_text("<script src=\"app.js\"></script>", encoding="utf-8")
        (static / "app.js").write_text("ok", encoding="utf-8")
        return static

    def _bundle(self, dist: Path, static: Path) -> Path:
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
        inside = Path("Serato Library.app/Contents/Frameworks/current")
        self.assertTrue(release_bundle._link_stays_inside(inside, "../MacOS/Serato Library"))
        self.assertFalse(release_bundle._link_stays_inside(Path("Serato Library.app/escape"), "/tmp"))
        self.assertFalse(release_bundle._link_stays_inside(Path("Serato Library.app/escape"), "../../outside"))

    @unittest.skipUnless(sys.platform != "win32", "the fixture is a macOS app bundle")
    def test_roundtrip_keeps_mode_symlink_and_page(self) -> None:
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
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "dist" / "Serato Library.app"
            root.mkdir(parents=True)
            (root / "escape").symlink_to("/tmp")
            with self.assertRaises(SystemExit):
                release_bundle.zip_bundle(root, base / "out.zip")

    def test_unsafe_zip_entry_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "bad.zip"
            with zipfile.ZipFile(archive, "w") as zipped:
                zipped.writestr("../outside.txt", "no")
            with self.assertRaises(SystemExit):
                release_bundle.assert_zip(archive, Path(tmp), min_bytes=1, max_bytes=5_000_000)

    def test_run_smoke_accepts_the_marker(self) -> None:
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
        with self.assertRaises(SystemExit):
            release_bundle.run_smoke(ROOT / "desktop.py", ROOT)


class WorkflowTests(unittest.TestCase):
    def test_workflows_declare_permissions_and_timeouts(self) -> None:
        workflows = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(
            [path.name for path in workflows],
            ["ci.yml", "codeql.yml", "dependency-review.yml", "release.yml"],
        )
        for path in workflows:
            text = path.read_text(encoding="utf-8")
            self.assertIn("permissions:", text, path.name)
            self.assertIn("contents: read", text, path.name)
            self.assertIn("timeout-minutes:", text, path.name)
            self.assertIn("concurrency:", text, path.name)

    def test_ci_matches_the_documented_suite(self) -> None:
        text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("python -m unittest discover -s tests -t . -v", text)
        self.assertIn("branches: [main]", text)
        self.assertIn("pull_request:", text)
        self.assertIn("pip-audit==2.10.1", text)
        self.assertIn("cancel-in-progress: true", text)
        self.assertNotIn("macos-latest", text)

    def test_release_does_not_cancel_and_checks_the_zip(self) -> None:
        text = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        self.assertIn("cancel-in-progress: false", text)
        self.assertIn("requirements-build.txt", text)
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
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("python3 -m unittest discover -s tests -t . -v", readme)
        guide = (ROOT / "docs" / "github.md").read_text(encoding="utf-8")
        self.assertIn("python3 -m unittest discover -s tests -t . -v", guide)
        self.assertIn("127.0.0.1", guide)


class OutsideLaunchTests(unittest.TestCase):
    def test_smoke_script_is_what_the_frozen_app_runs(self) -> None:
        """The pack command launches the unzipped executable, not the source tree."""
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
