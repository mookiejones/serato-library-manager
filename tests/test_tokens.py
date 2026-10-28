"""Checks that the page uses the token sheet and that text pairs are measured.

The cases read static files. They do not start a server or open a library.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "static" / "index.html"
APP_CSS = ROOT / "static" / "app.css"
APP_JS = ROOT / "static" / "app.js"
TOKENS = ROOT / "static" / "tokens.css"

# A CSS hex color. The digits must include a decimal digit so an id such
# as #reload is not treated as a color. The match must not continue into
# a longer identifier.
HEX_COLOR = re.compile(
    r"#(?=[0-9a-fA-F]*[0-9])(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})(?![0-9a-fA-F])"
)
TOKEN_DECL = re.compile(r"(--[A-Za-z0-9-]+)\s*:\s*(#[0-9A-Fa-f]{6})\b")

# Text needs 4.5:1. Manila is --color-card. Walnut is --color-bg.
# The third item is the ratio rounded to two decimals.
TEXT_PAIRS = (
    ("safe-text on manila", "--color-safe-text", "--color-card", 5.43),
    ("safe-text on safe-bg", "--color-safe-text", "--color-safe-bg", 5.34),
    ("warn-text on manila", "--color-warn-text", "--color-card", 5.62),
    ("warn-text on warn-bg", "--color-warn-text", "--color-warn-bg", 5.35),
    ("safe-on-dark on walnut", "--color-safe-on-dark", "--color-bg", 8.00),
    ("warn-on-dark on walnut", "--color-warn-on-dark", "--color-bg", 8.07),
)

# Borders, fills, and icons need 3:1. Warn on the tint uses the border token.
NON_TEXT_PAIRS = (
    ("safe on manila", "--color-safe", "--color-card", 4.20),
    ("safe on safe-bg", "--color-safe", "--color-safe-bg", 4.13),
    ("safe-border on manila", "--color-safe-border", "--color-card", 4.20),
    ("safe-border on safe-bg", "--color-safe-border", "--color-safe-bg", 4.13),
    ("warn on manila", "--color-warn", "--color-card", 3.10),
    ("warn-border on warn-bg", "--color-warn-border", "--color-warn-bg", 5.35),
)


def _channel(value: int) -> float:
    """Convert one sRGB channel to linear light.

    Args:
        value: Channel from 0 to 255.

    Returns:
        The linearized channel used by the WCAG luminance formula.
    """
    unit = value / 255
    if unit <= 0.04045:
        return unit / 12.92
    return ((unit + 0.055) / 1.055) ** 2.4


def _rgb(color: str) -> tuple[int, int, int]:
    """Parse a #rrggbb color.

    Args:
        color: Six-digit hex color with a leading hash.

    Returns:
        Red, green, and blue from 0 to 255.
    """
    return (int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16))


def contrast(foreground: str, background: str) -> float:
    """Return the WCAG contrast ratio of two #rrggbb colors.

    Args:
        foreground: Text color.
        background: Surface color.

    Returns:
        The ratio, from 1 to 21. Higher is easier to read.
    """
    def luminance(color: str) -> float:
        red, green, blue = _rgb(color)
        return 0.2126 * _channel(red) + 0.7152 * _channel(green) + 0.0722 * _channel(blue)

    lighter = max(luminance(foreground), luminance(background))
    darker = min(luminance(foreground), luminance(background))
    return (lighter + 0.05) / (darker + 0.05)


def token_colors(text: str) -> dict[str, str]:
    """Return hex custom properties declared in a token sheet.

    Args:
        text: CSS source.

    Returns:
        Map of custom property name to lowercase #rrggbb. Later
        declarations replace earlier ones of the same name.
    """
    found: dict[str, str] = {}
    for name, value in TOKEN_DECL.findall(text):
        found[name] = value.lower()
    return found


class TokenSheetTests(unittest.TestCase):
    """Check the link order and that stylesheets do not keep raw colors."""

    def test_page_links_tokens_before_app_css(self) -> None:
        """Load tokens.css before app.css.

        The alias block in app.css reads the tokens. A later link would
        leave the aliases unset on the first paint. The check is the
        source order of the two link tags.

        Returns:
            None. The test fails if either link is missing or app.css is first.
        """
        page = INDEX.read_text(encoding="utf-8")
        tokens_at = page.index('href="/tokens.css"')
        app_at = page.index('href="/app.css"')
        self.assertLess(tokens_at, app_at)

    def test_app_css_has_no_raw_hex_colors(self) -> None:
        """Keep every color in app.css on a token or a color-mix.

        A raw #rrggbb or an rgba() value would bypass the sheet. A
        color-mix of a token is allowed. Id selectors such as #reload
        are not colors.

        Returns:
            None. The test fails if a hex color or rgb() function remains.
        """
        text = APP_CSS.read_text(encoding="utf-8")
        self.assertEqual(HEX_COLOR.findall(text), [])
        self.assertNotIn("rgba(", text)
        self.assertNotIn("rgb(", text)

    def test_app_js_has_no_hex_colors(self) -> None:
        """Keep CSS colors out of app.js.

        Serato color integers such as 0xffffff stay. They are data, not
        paints. A #rrggbb literal in the script is a color that belongs
        in the stylesheet. The detail swatch size and the BPM color are
        classes.

        Returns:
            None. The test fails if a hex color, marginTop, or inline BPM color remains.
        """
        text = APP_JS.read_text(encoding="utf-8")
        self.assertEqual(HEX_COLOR.findall(text), [])
        self.assertNotIn("marginTop", text)
        self.assertNotIn("style.color", text)
        self.assertIn('strong.className = "bpm"', text)
        self.assertIn('"swatch swatch-lg"', text)
        self.assertIn("spacer.style.height", text)
        self.assertIn("rows.style.transform", text)
        self.assertIn("row.style.paddingLeft", text)

    def test_palette_aliases_point_at_tokens(self) -> None:
        """Point the old palette names at the token roles.

        app.css no longer stores the hex values. The row height stays a
        literal because the list painter reads ROW in app.js.

        Returns:
            None. The test fails if an alias or the row comment is missing.
        """
        text = APP_CSS.read_text(encoding="utf-8")
        aliases = {
            "--walnut": "--color-bg",
            "--walnut-lift": "--color-panel",
            "--manila": "--color-card",
            "--manila-deep": "--color-button",
            "--ink": "--color-text",
            "--quiet": "--color-text-muted",
            "--cadmium": "--color-primary",
            "--missing": "--color-danger",
            "--rule": "--color-border",
            "--font": "--font-family",
        }
        for name, token in aliases.items():
            self.assertIn(f"{name}: var({token})", text)
        self.assertIn("--row: 36px; /* must match ROW in app.js */", text)


class ContrastTests(unittest.TestCase):
    """Measure text at 4.5:1 and borders, fills, and icons at 3:1."""

    def setUp(self) -> None:
        """Read the token sheet once for the contrast cases.

        Returns:
            None.
        """
        self.colors = token_colors(TOKENS.read_text(encoding="utf-8"))
        self.sheet = TOKENS.read_text(encoding="utf-8")

    def test_text_pairs_clear_body_contrast(self) -> None:
        """Require 4.5:1 for every text token on its surface.

        Safe text and warn text are measured on manila and on their
        tints. The on-dark tokens are measured on walnut. The ratios
        are rounded to two decimals.

        Returns:
            None. The test fails if a text pair drops under 4.5:1.
        """
        for label, foreground, background, expected in TEXT_PAIRS:
            ratio = round(contrast(self.colors[foreground], self.colors[background]), 2)
            self.assertEqual(ratio, expected, label)
            self.assertGreaterEqual(ratio, 4.5, label)

    def test_non_text_pairs_clear_ui_contrast(self) -> None:
        """Require 3:1 for borders, fills, and icons.

        Safe and the safe border use ``#3f7d4e``. Warn on manila stays
        ``#b7791f``. A warn border or icon on the warn tint uses
        ``--color-warn-border`` (``#7f5417``). Every pair clears 3:1.

        Returns:
            None. The test fails if a non-text pair drops under 3:1.
        """
        self.assertEqual(self.colors["--color-safe"], "#3f7d4e")
        self.assertEqual(self.colors["--color-safe-border"], "#3f7d4e")
        self.assertEqual(self.colors["--color-warn"], "#b7791f")
        self.assertEqual(self.colors["--color-warn-border"], "#7f5417")
        self.assertEqual(self.colors["--color-safe-text"], "#356a41")
        self.assertEqual(self.colors["--color-warn-text"], "#7f5417")
        for label, foreground, background, expected in NON_TEXT_PAIRS:
            ratio = round(contrast(self.colors[foreground], self.colors[background]), 2)
            self.assertEqual(ratio, expected, label)
            self.assertGreaterEqual(ratio, 3, label)
        text_colors = [
            line.split(":", 1)[1].strip().rstrip(";")
            for line in self.sheet.splitlines()
            if line.strip().startswith("color:")
        ]
        self.assertEqual(
            text_colors,
            [
                "var(--color-safe-text)",
                "var(--color-warn-text)",
                "var(--color-danger)",
            ],
        )

    def test_warm_palette_values(self) -> None:
        """Fill the role tokens with the existing walnut and manila colors.

        Primary is cadmium. Danger is the missing-file red. The sheet
        must not pick up the dark navy reference.

        Returns:
            None. The test fails if a role color changes.
        """
        self.assertEqual(
            {name: self.colors[name] for name in (
                "--color-bg",
                "--color-panel",
                "--color-card",
                "--color-button",
                "--color-text",
                "--color-text-muted",
                "--color-border",
                "--color-primary",
                "--color-danger",
            )},
            {
                "--color-bg": "#231910",
                "--color-panel": "#32261c",
                "--color-card": "#f3ecdf",
                "--color-button": "#e7ddcc",
                "--color-text": "#1b140e",
                "--color-text-muted": "#6f655b",
                "--color-border": "#d9cfbf",
                "--color-primary": "#e23b16",
                "--color-danger": "#a33a32",
            },
        )
        sheet = TOKENS.read_text(encoding="utf-8")
        self.assertIn("Green = safe/undoable", sheet)
        self.assertIn("Amber = heads-up", sheet)
        self.assertIn("Red = data leaves the library", sheet)
        self.assertIn(".pill-preview", sheet)
        self.assertNotIn("#0d0f14", sheet)


if __name__ == "__main__":
    unittest.main()
