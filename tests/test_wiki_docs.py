"""Wiki draft and agent-guide checks.

The cases read files in the repository. They do not build the site,
open a wiki, or start the app.
"""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CAPTIONS = (
    "1 Download",
    "2 Open (right-click > Open)",
    "3 Point it at your Serato library",
    "4 Make a Backup",
    "5 Start crate digging",
)

RELEASE_NAMES = (
    "Serato-Library-macos-arm64.dmg",
    "Serato-Library-macos-x64.dmg",
    "Serato-Library-windows-setup.exe",
    "Serato-Library-windows.zip",
    "SHA256SUMS",
)

LEGACY_NAMES = (
    "Serato-Library-macos.zip",
    "Serato-Library-windows.zip",
)


class AgentGuideTests(unittest.TestCase):
    """Keep the two agent guides on the same text."""

    def test_agents_md_mirrors_claude_md(self) -> None:
        """Require ``AGENTS.md`` to match ``CLAUDE.md`` byte for byte.

        Returns:
            None. The test fails when either copy drifts.
        """
        agents = (ROOT / "AGENTS.md").read_bytes()
        claude = (ROOT / "CLAUDE.md").read_bytes()
        self.assertEqual(agents, claude)


class QuickStartTests(unittest.TestCase):
    """Check the wiki page and the guide page describe the same five steps."""

    def test_wiki_page_uses_the_light_png_and_the_captions(self) -> None:
        """Show the light banner and the five captions on the wiki page.

        The logo note stays next to the banner. The wiki page does not
        use a picture element.

        Returns:
            None. The test fails when a caption or the light banner is missing.
        """
        text = (ROOT / "docs" / "wiki" / "Quick-Start.md").read_text(encoding="utf-8")
        self.assertIn("The logo on the banner is not approved yet. It may change.", text)
        self.assertIn("images/quickstart-banner-light.png", text)
        self.assertNotIn("<picture>", text)
        self.assertIn("Restore never changes audio data.", text)
        self.assertNotIn("never touched", text)
        for caption in CAPTIONS:
            self.assertIn(caption, text)
        for name in RELEASE_NAMES + LEGACY_NAMES:
            self.assertIn(name, text)

    def test_guide_page_uses_picture_for_light_and_dark(self) -> None:
        """Switch the guide banner and the step art with a picture element.

        Returns:
            None. The test fails when dark art or a caption is missing.
        """
        text = (ROOT / "docs" / "quick-start.md").read_text(encoding="utf-8")
        self.assertIn("The logo on the banner is not approved yet. It may change.", text)
        self.assertIn("<picture>", text)
        self.assertIn("wiki/images/quickstart-banner-light.png", text)
        self.assertIn("wiki/images/quickstart-banner-dark.png", text)
        self.assertIn("wiki/images/quickstart-banner-dark.svg", text)
        self.assertIn("wiki/images/step-1-light.png", text)
        self.assertIn("wiki/images/step-1-dark.png", text)
        self.assertIn("wiki/images/step-4-dark.png", text)
        self.assertIn("wiki/images/step-5-dark.png", text)
        self.assertIn("Restore never changes audio data.", text)
        self.assertNotIn("never touched", text)
        for caption in CAPTIONS:
            self.assertIn(caption, text)


class InstallPageTests(unittest.TestCase):
    """Check the Mac and Windows wiki pages name the real downloads."""

    def test_install_pages_name_the_release_files_and_the_warnings(self) -> None:
        """Document disk images, SmartScreen, Open Anyway, and Removable Volumes.

        Returns:
            None. The test fails when a download name or a warning step is missing.
        """
        mac = (ROOT / "docs" / "wiki" / "Install-macOS.md").read_text(encoding="utf-8")
        windows = (ROOT / "docs" / "wiki" / "Install-Windows.md").read_text(encoding="utf-8")
        home = (ROOT / "docs" / "wiki" / "Home.md").read_text(encoding="utf-8")
        for name in RELEASE_NAMES:
            self.assertIn(name, mac + windows)
        self.assertIn("Serato-Library-macos.zip", mac)
        self.assertIn("Serato-Library-windows.zip", windows)
        self.assertIn("Open Anyway", mac)
        self.assertIn("right-click", mac.lower())
        self.assertIn("Removable Volumes", mac)
        self.assertIn("Files and Folders", mac)
        self.assertIn("Full Disk Access", mac)
        self.assertIn("More info", windows)
        self.assertIn("Run anyway", windows)
        self.assertIn("WebView2", windows)
        self.assertIn("GitHub Releases is the only download.", home)
        self.assertIn("Crates", home)
        self.assertIn("Snapshots", home)
        self.assertIn("PREVIEW", home)
        self.assertIn("Restore never changes audio data.", home)
        self.assertNotIn("never touched", home + mac + windows)
