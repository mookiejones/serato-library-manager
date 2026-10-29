"""Checks for the panic page and the library-safety page.

The cases read files in the repository. They do not build the site or
start the app. Link targets are the Markdown files and headings MkDocs
would publish.
"""

from __future__ import annotations

import re
import unicodedata
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

PAGES = ("panic.md", "is-my-library-safe.md")

RESTORE = (
    "Restore can rewrite the Serato tags (cue points, beatgrid, autotags) "
    "inside each audio file, and removes Serato tags the snapshot didn't have. "
    "The audio stream is hash-checked before and after; if it would change, "
    "the file is left as it was."
)

_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)


def _slug(text: str) -> str:
    """Match the MkDocs toc slug for one heading.

    Python-Markdown drops non-ASCII and punctuation, then joins the
    remaining words with hyphens. That is the permalink the site writes.

    Args:
        text: Heading text, without the leading hashes.

    Returns:
        The fragment MkDocs uses for that heading.
    """
    normal = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^\w\s-]", "", normal).strip().lower()
    return re.sub(r"[-\s]+", "-", cleaned)


def _headings(page: Path) -> set[str]:
    """Return the toc slugs in one Markdown file.

    Args:
        page: A file under ``docs/``.

    Returns:
        Slugs for every ATX heading in the file.
    """
    return {_slug(match.group(1)) for match in _HEADING.finditer(page.read_text(encoding="utf-8"))}


class GuidePageTests(unittest.TestCase):
    """Keep the panic and library-safety pages in the nav, and their links real."""

    def test_pages_exist_and_are_in_the_nav(self) -> None:
        """Require both pages, the home links, and a nav entry for each.

        The whole library-safety page is not labelled PREVIEW. The gig
        check on that page still is.

        Returns:
            None. The test fails when a page or a nav entry is missing.
        """
        nav = (DOCS / "mkdocs.yml").read_text(encoding="utf-8")
        index = (DOCS / "index.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Panic: panic.md", nav)
        self.assertIn("Is my library safe?: is-my-library-safe.md", nav)
        self.assertNotIn("Is my library safe? (PREVIEW)", nav)
        for name in PAGES:
            self.assertTrue((DOCS / name).is_file(), name)
            self.assertIn(name, index)
            self.assertIn(f"docs/{name}", readme)

    def test_internal_links_resolve(self) -> None:
        """Open every relative link and same-page heading on the two pages.

        ``http`` and ``https`` links are left alone. An image is a link
        to a file. A ``#fragment`` has to match a heading slug.

        Returns:
            None. The test fails when a target file or heading is missing.
        """
        for name in PAGES:
            page = DOCS / name
            for target in _LINK.findall(page.read_text(encoding="utf-8")):
                if target.startswith(("http://", "https://", "mailto:")):
                    continue
                path, _sep, fragment = target.partition("#")
                destination = page if path == "" else (page.parent / path).resolve()
                self.assertTrue(
                    destination.is_file(),
                    f"{name} links to missing {target}",
                )
                self.assertTrue(
                    destination.resolve().is_relative_to(ROOT),
                    f"{name} links outside the repository: {target}",
                )
                if fragment:
                    self.assertIn(
                        fragment,
                        _headings(destination),
                        f"{name} links to missing heading {target}",
                    )

    def test_restore_is_shipped_and_the_gig_check_stays_preview(self) -> None:
        """Describe restore as working, and keep PREVIEW on the gig check.

        Issue 35 has shipped. Issue 41 has not. The Rekordbox status
        line is a different label and is not changed here.

        Returns:
            None. The test fails when restore is still tied to issue 35,
            or when the gig check drops PREVIEW.
        """
        for name in PAGES:
            text = (DOCS / name).read_text(encoding="utf-8")
            self.assertIn(RESTORE, text, name)
            self.assertIn("**Crates**", text, name)
            self.assertIn("**Snapshots**", text, name)
            self.assertIn("**Prepare**", text, name)
            self.assertIn("move, rename, and trash audio files", text, name)
            self.assertIn("PREVIEW", text, name)
            self.assertIn("https://github.com/mookiejones/serato-library-manager/issues/41", text, name)
            self.assertIn("gig check", text.lower(), name)
            self.assertNotIn("audio is never touched", text.lower(), name)
            self.assertNotIn("never touch the sound", text.lower(), name)
            self.assertNotIn("never touched", text.lower(), name)
            self.assertNotIn("issues/35", text, name)
            self.assertNotIn("#35", text, name)
        index = (DOCS / "index.md").read_text(encoding="utf-8")
        self.assertIn("issues/41", index)
        self.assertNotIn("issues/35", index)
        self.assertIn("PREVIEW", index)
        guide = (DOCS / "coming-from-rekordbox.md").read_text(encoding="utf-8")
        self.assertIn("Status: preview.", guide)


if __name__ == "__main__":
    unittest.main()
