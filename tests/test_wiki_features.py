"""Checks for the GitHub wiki feature drafts.

The cases read files in the repository. They do not build the site,
open a wiki, or start the app.
"""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WIKI = ROOT / "docs" / "wiki"

FEATURE_PAGES = (
    "Hot-Loops-and-Cue-Points.md",
    "Backups-and-Restore.md",
    "Crates.md",
    "Export-to-Rekordbox.md",
    "Organizing-Files.md",
    "Related-Tracks.md",
    "First-Run-Wizard.md",
    "Settings.md",
    "Where-Serato-Data-Lives.md",
)

SIDEBAR_LINKS = FEATURE_PAGES + (
    "Home.md",
    "Quick-Start.md",
    "Install-macOS.md",
    "Install-Windows.md",
)


class WikiFeaturePageTests(unittest.TestCase):
    """Keep each feature page visual, short, and tied to the real nav names."""

    def test_each_feature_page_leads_with_a_picture_and_a_diagram(self) -> None:
        """Require a screenshot placeholder and a Mermaid flow on every page.

        Returns:
            None. The test fails when a page drops its picture or its diagram.
        """
        for name in FEATURE_PAGES:
            text = (WIKI / name).read_text(encoding="utf-8")
            self.assertIn("TODO-SCREENSHOT", text, name)
            self.assertIn("```mermaid", text, name)
            self.assertLess(text.index("TODO-SCREENSHOT"), text.index("```mermaid"), name)
            self.assertNotIn("never touched", text, name)

    def test_sidebar_links_features_and_the_quick_start_pages(self) -> None:
        """Link every feature plus Home, Quick Start, and both Install pages.

        Home, Quick Start, and the Install pages may live in another pull
        request. The sidebar still names them.

        Returns:
            None. The test fails when a wiki link is missing.
        """
        sidebar = (WIKI / "_Sidebar.md").read_text(encoding="utf-8")
        for name in SIDEBAR_LINKS:
            self.assertIn(f"]({name})", sidebar)

    def test_backups_restore_audio_and_unplugged_drives(self) -> None:
        """Say restore leaves audio data alone, and an unplugged drive stays.

        Returns:
            None. The test fails when those sentences drift.
        """
        text = (WIKI / "Backups-and-Restore.md").read_text(encoding="utf-8")
        self.assertIn("Snapshots", text)
        self.assertIn("Restore never changes audio data.", text)
        self.assertIn("marked unavailable, never deleted", text)
        self.assertIn("Files and Folders > Removable Volumes", text)
        self.assertIn("PREVIEW", text)
        self.assertIn("https://github.com/mookiejones/serato-library-manager/issues/91", text)

    def test_files_can_change_audio_and_drives_need_permission(self) -> None:
        """Say organizing files moves, renames, and trashes audio files.

        Returns:
            None. The test fails when the file actions are softened.
        """
        text = (WIKI / "Organizing-Files.md").read_text(encoding="utf-8")
        self.assertIn("move, rename, and trash audio files", text)
        self.assertIn("Files and Folders > Removable Volumes", text)
        self.assertIn("**Files**", text)

    def test_export_keeps_the_preview_label(self) -> None:
        """Keep the existing preview label on the Rekordbox export page.

        Returns:
            None. The test fails when the label or the merged pull request
            link is missing.
        """
        page = (WIKI / "Export-to-Rekordbox.md").read_text(encoding="utf-8")
        guide = (ROOT / "docs" / "coming-from-rekordbox.md").read_text(encoding="utf-8")
        self.assertIn("Status: preview.", page)
        self.assertIn("https://github.com/mookiejones/serato-library-manager/pull/39", page)
        self.assertIn("Status: preview.", guide)
        self.assertLess(page.index("Status: preview."), page.index("TODO-SCREENSHOT"))

    def test_pages_use_the_nav_names(self) -> None:
        """Use Crates, Snapshots, and Prepare as the window names them.

        Returns:
            None. The test fails when a page invents a nav label.
        """
        crates = (WIKI / "Crates.md").read_text(encoding="utf-8")
        self.assertIn("**Crates**", crates)
        self.assertIn("**Prepare**", crates)
        hot = (WIKI / "Hot-Loops-and-Cue-Points.md").read_text(encoding="utf-8")
        self.assertIn("**Crates**", hot)
        self.assertIn("**Snapshots**", hot)
        self.assertIn("**Hot loops**", hot)
        self.assertIn("Uses a free hot-cue pad", hot)
        where = (WIKI / "Where-Serato-Data-Lives.md").read_text(encoding="utf-8")
        self.assertIn("marked unavailable, never deleted", where)
        self.assertIn("Files and Folders > Removable Volumes", where)
        self.assertIn("Restore never changes audio data.", where)

    def test_mkdocs_excludes_wiki_markdown(self) -> None:
        """Keep the wiki drafts out of the strict site build.

        Returns:
            None. The test fails when ``wiki/*.md`` is no longer excluded.
        """
        text = (ROOT / "docs" / "mkdocs.yml").read_text(encoding="utf-8")
        self.assertIn("wiki/*.md", text)
