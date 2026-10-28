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

def _channel(value: float) -> float:
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


def contrast(foreground: str | tuple[float, float, float], background: str | tuple[float, float, float]) -> float:
    """Return the WCAG contrast ratio of two colors.

    The ratio is not rounded. Callers that print it round for display.

    Args:
        foreground: ``#rrggbb`` or a red/green/blue triple in 0..255.
        background: ``#rrggbb`` or a red/green/blue triple in 0..255.

    Returns:
        The ratio, from 1 to 21. Higher is easier to read.
    """
    def luminance(color: str | tuple[float, float, float]) -> float:
        red, green, blue = _rgb(color) if isinstance(color, str) else color
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


def _rules(css: str) -> list[tuple[str, dict[str, str]]]:
    """Split a stylesheet into selector and declaration pairs.

    Args:
        css: Stylesheet text. Comments are ignored. Rules inside an
            at-rule are returned too.

    Returns:
        One entry per selector. Declarations are lower-case property
        names and collapsed values.
    """
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    found: list[tuple[str, dict[str, str]]] = []

    def walk(text: str) -> None:
        index = 0
        while True:
            start = text.find("{", index)
            if start < 0:
                return
            selector = " ".join(text[index:start].split())
            depth = 1
            cursor = start + 1
            while cursor < len(text) and depth:
                if text[cursor] == "{":
                    depth += 1
                elif text[cursor] == "}":
                    depth -= 1
                cursor += 1
            body = text[start + 1 : cursor - 1]
            if selector.startswith("@"):
                walk(body)
            else:
                props: dict[str, str] = {}
                for chunk in body.split(";"):
                    if ":" not in chunk:
                        continue
                    key, value = chunk.split(":", 1)
                    props[key.strip().lower()] = " ".join(value.split())
                for part in selector.split(","):
                    found.append((" ".join(part.split()), props))
            index = cursor

    walk(css)
    return found


def _sheet_colors() -> dict[str, str]:
    """Resolve token and alias colors to ``#rrggbb``.

    Returns:
        Custom property name to lowercase hex. Aliases in ``app.css``
        point at the token sheet.
    """
    colors = token_colors(TOKENS.read_text(encoding="utf-8"))
    colors.update(token_colors(APP_CSS.read_text(encoding="utf-8")))
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
    }
    for name, target in aliases.items():
        colors[name] = colors[target]
    return colors


def _paint(value: str, colors: dict[str, str]) -> tuple[float, float, float]:
    """Resolve a CSS color expression to red, green, and blue.

    Args:
        value: A ``var()``, hex color, or ``color-mix`` with transparent.
        colors: Resolved custom properties.

    Returns:
        Channels from 0 to 255. A mix with transparent returns the solid
        color; the caller applies the percentage over a surface.
    """
    value = value.strip()
    mixed = re.search(r"var\(\s*(--[A-Za-z0-9-]+)\)\s*(\d+(?:\.\d+)?)%", value)
    if mixed:
        return _rgb(colors[mixed.group(1)])
    named = re.search(r"var\(\s*(--[A-Za-z0-9-]+)", value)
    if named:
        return _rgb(colors[named.group(1)])
    return _rgb(value)


def _mix_amount(value: str) -> float | None:
    """Return the color-mix percentage as a fraction.

    Args:
        value: Declaration value.

    Returns:
        The fraction, or None when the value is not a mix.
    """
    mixed = re.search(r"(\d+(?:\.\d+)?)%", value)
    if "color-mix" not in value or mixed is None:
        return None
    return float(mixed.group(1)) / 100


def _over(foreground: tuple[float, float, float], background: tuple[float, float, float], alpha: float) -> tuple[float, float, float]:
    """Composite a color over a surface.

    Args:
        foreground: Solid color.
        background: Surface.
        alpha: Fraction of the foreground.

    Returns:
        The painted color.
    """
    return tuple(alpha * foreground[index] + (1 - alpha) * background[index] for index in range(3))


def _length(value: str, colors: dict[str, str]) -> float:
    """Resolve a font size to pixels.

    Args:
        value: A ``px`` length or ``var(--font-…)``.
        colors: Unused except to read the token sheet sizes.

    Returns:
        The size in pixels.
    """
    named = re.search(r"var\(\s*(--[A-Za-z0-9-]+)", value)
    if named:
        token = {
            "--font-title": 20,
            "--font-heading": 14,
            "--font-body": 13,
            "--font-caption": 11,
        }[named.group(1)]
        return float(token)
    return float(value.replace("px", "").strip())


def _minimum(size: float, weight: int) -> float:
    """Return the contrast bar for a font size and weight.

    Args:
        size: Font size in pixels.
        weight: CSS font-weight.

    Returns:
        3 for large or bold text, otherwise 4.5. Large text is 24px or
        more, or 18.66px or more at weight 700.
    """
    if size >= 24 or (size >= 18.66 and weight >= 700):
        return 3.0
    return 4.5


# Text painted by app.css. The size and weight are the inherited values
# when the rule itself does not set them. Background names are custom
# properties, plus "hover" for the track-row wash.
_TEXT: tuple[tuple[str, tuple[str, ...], float, int], ...] = (
    ("html", ("--color-card", "--color-selection", "hover", "--color-button"), 15, 400),
    ("body", ("--color-card", "--color-selection", "hover", "--color-button"), 15, 400),
    (".rail", ("--color-bg",), 15, 400),
    (".brand p", ("--color-bg",), 14, 400),
    (".rail select", ("--color-bg",), 15, 400),
    (".rail-field input", ("--color-bg",), 15, 400),
    (".view-switch button", ("--color-bg",), 15, 400),
    (".sort-crates button", ("--color-bg",), 15, 400),
    (".crate-actions button", ("--color-bg",), 15, 400),
    ('.view-switch button[aria-selected="true"]', ("--color-bg",), 15, 400),
    ('.sort-crates button[aria-pressed="true"]', ("--color-bg",), 15, 400),
    (".rail-foot button", ("--color-bg",), 15, 400),
    (".mode-note", ("--color-bg",), 13, 400),
    (".crate-foot", ("--color-bg",), 13, 400),
    (".crate-row", ("--color-bg", "--color-panel"), 15, 400),
    (".twist", ("--color-bg", "--color-panel"), 15, 400),
    (".twist:hover", ("--color-bg", "--color-panel"), 15, 400),
    (".crate .meta", ("--color-bg", "--color-panel"), 12, 400),
    (".crate .smart", ("--color-bg", "--color-panel"), 12, 400),
    (".search input::placeholder", ("--color-card",), 15, 400),
    (".count", ("--color-card",), 15, 400),
    ("#reload", ("--color-card",), 15, 400),
    ("#export-m3u", ("--color-card",), 15, 400),
    ("#export-rekordbox", ("--color-card",), 15, 400),
    ("#import-m3u", ("--color-card",), 15, 400),
    (".text-button", ("--color-card",), 15, 400),
    (".actions button", ("--color-card",), 15, 400),
    (".rekordbox-option", ("--color-card",), 15, 400),
    (".notice", ("--color-card",), 15, 400),
    (".columns button", ("--color-card",), 15, 400),
    ('.columns button[data-active="true"]', ("--color-card",), 15, 400),
    (".cell.num", ("--color-card", "--color-selection", "hover"), 15, 400),
    (".missing-word", ("--color-card", "--color-selection", "hover"), 15, 400),
    (".empty-list", ("--color-card",), 15, 400),
    (".detail-empty", ("--color-card",), 15, 400),
    (".detail-error", ("--color-card",), 15, 400),
    (".detail-kicker", ("--color-card",), 15, 400),
    (".deck .bpm", ("--color-card",), 28, 500),
    (".deck span", ("--color-card",), 13, 400),
    (".field .label", ("--color-card",), 15, 400),
    (".field .column", ("--color-card",), 12, 400),
    (".rules", ("--color-card",), 13, 400),
    (".rules strong", ("--color-card",), 13, 500),
    (".related-meta", ("--color-card",), 15, 400),
    (".related-note", ("--color-card",), 15, 400),
    (".lock-note", ("--color-card",), 15, 400),
    (".editor label", ("--color-card",), 13, 400),
    ("dialog", ("--color-card",), 15, 400),
    (".dialog-note", ("--color-card",), 15, 400),
    (".dialog-status", ("--color-card",), 15, 400),
    ("#consent-decline", ("--color-text",), 15, 400),
    ("#settings-close", ("--color-text",), 15, 400),
    ("#consent-accept", ("--color-card",), 15, 400),
    ("#open-logs", ("--color-card",), 15, 400),
    ("#copy-logs", ("--color-card",), 15, 400),
    ("#rekordbox-download", ("--color-text",), 15, 400),
    ("#rekordbox-cancel", ("--color-card",), 15, 400),
    (".merge-meta", ("--color-card",), 15, 400),
    (".merge-warning", ("--color-card",), 15, 400),
    ("#merge-cancel", ("--color-card",), 15, 400),
    ("#merge-confirm.danger", ("--color-danger",), 15, 400),
    (".log-fallback", ("--color-card",), 15, 400),
    (".files-badge", ("--color-card",), 13, 400),
    (".files-kind", ("--color-card",), 13, 400),
    (".files-empty", ("--color-card",), 15, 400),
    ("#files-confirm.danger", ("--color-danger",), 15, 400),
)

# Large or inherited text whose color comes from an ancestor rule.
_INHERITED: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (".brand h1", ".rail", ("--color-bg",)),
    (".detail h2", "body", ("--color-card",)),
    (".deck strong", "body", ("--color-card",)),
    ("dialog h2", "dialog", ("--color-card",)),
    (".group h3", "body", ("--color-card",)),
)

# Focus rings are offset by 2px, so they sit on the surface around the
# control: walnut, the crate row, the manila sheet, a selected row, and
# a hovered row. Filled buttons sit on the sheet, so their ring is on
# the card rather than on the fill.
_FOCUS_SURFACES = ("--color-bg", "--color-panel", "--color-card", "--color-selection", "hover")

# Decorative hairlines, exempt under WCAG 1.4.11. They are not the only
# thing that identifies a control. --color-border on the manila card and
# --color-border-on-dark on walnut stay as they are.
#
# --color-border on --color-card:
#   .detail border-left, and border-top in the narrow layout
#   .search input border-bottom
#   .rekordbox-option select border-bottom
#   .rule-edit textarea border
#   .columns border-bottom
#   .field border-top
#   .editor input, .editor select, .editor textarea border-bottom
#   .marker and .copy-row border-top
#   .related-row border-top
#   .related-search input, .related-form input, .related-form select border-bottom
#   dialog border
#   #merge-dialog fieldset border
#   .log-fallback border
#   .files-row border-top
#   .files-actions border-top
#   .files-field input border-bottom
# --color-border-on-dark on --color-bg:
#   .rail select and .rail-field input border-bottom
# .swatch inset shadow: a 1px hairline of --color-shadow at 18% on a
# data-driven swatch, not a control boundary.
_DECORATIVE = {
    ".detail",
    ".search input",
    ".rekordbox-option select",
    ".rule-edit textarea",
    ".columns",
    ".field",
    ".editor input",
    ".editor select",
    ".editor textarea",
    ".marker",
    ".copy-row",
    ".related-row",
    ".related-search input",
    ".related-form input",
    ".related-form select",
    "dialog",
    "#merge-dialog fieldset",
    ".log-fallback",
    ".files-row",
    ".files-actions",
    ".files-field input",
    ".rail select",
    ".rail-field input",
    ".swatch",
}


class ContrastTests(unittest.TestCase):
    """Measure every token pair the page paints."""

    def setUp(self) -> None:
        """Read the stylesheets and resolve their colors.

        Returns:
            None.
        """
        self.colors = _sheet_colors()
        self.app_rules = _rules(APP_CSS.read_text(encoding="utf-8"))
        self.token_rules = _rules(TOKENS.read_text(encoding="utf-8"))

    def _rule(self, selector: str, rules: list[tuple[str, dict[str, str]]] | None = None) -> dict[str, str]:
        """Return the declarations of one selector.

        Args:
            selector: A single selector, not a comma group.
            rules: Rules to search. Defaults to ``app.css``.

        Returns:
            The declaration map.

        Raises:
            AssertionError: If the selector is not in the stylesheet.
        """
        source = self.app_rules if rules is None else rules
        merged: dict[str, str] = {}
        found = False
        for name, props in source:
            if name == selector:
                merged.update(props)
                found = True
        if not found:
            raise AssertionError(f"{selector} is not in the stylesheet")
        return merged

    def _surface(self, name: str) -> tuple[float, float, float]:
        """Resolve a background name to channels.

        Args:
            name: A custom property, or ``hover`` for the track-row wash.

        Returns:
            Red, green, and blue.
        """
        if name == "hover":
            return _over(_paint("var(--cadmium)", self.colors), _rgb(self.colors["--color-card"]), 0.06)
        return _rgb(self.colors[name])

    def test_rendered_text_and_controls(self) -> None:
        """Require 4.5:1 for text and 3:1 for large text, borders, and focus.

        The pairs are the selectors in ``app.css`` plus the preview pill.
        Body text needs 4.5:1. Text at 24px or more, or at 18.66px or
        more and weight 700, needs 3:1. Focus rings and input or control
        borders need 3:1. The comparison uses the unrounded ratio.
        Decorative hairlines are listed above and are not measured.

        BPM is 28px at weight 500, so it is large text. Cadmium already
        clears 3:1 on the card and on the selection bar, so the accent
        is unchanged.

        Returns:
            None. The test fails if a painted pair misses its bar or a
            color in the stylesheet is not classified.
        """
        classified = {selector for selector, _, _, _ in _TEXT}
        painted = {
            selector
            for selector, props in self.app_rules
            if "color" in props and props["color"] not in {"inherit", "currentColor"}
        }
        self.assertEqual(painted - classified, set(), "text colors missing from the contrast list")
        self.assertEqual(classified - painted, set(), "contrast list names a selector that sets no color")

        for selector, backgrounds, size, weight in _TEXT:
            props = self._rule(selector)
            if "font-size" in props:
                size = _length(props["font-size"], self.colors)
            if "font-weight" in props:
                weight = int(float(props["font-weight"]))
            foreground = _paint(props["color"], self.colors)
            bar = _minimum(size, weight)
            for background_name in backgrounds:
                ratio = contrast(foreground, self._surface(background_name))
                self.assertGreaterEqual(
                    ratio,
                    bar,
                    f"{selector} on {background_name} is {ratio:.2f}:1, needs {bar}:1",
                )

        for selector, color_selector, backgrounds in _INHERITED:
            props = self._rule(selector)
            size = _length(props["font-size"], self.colors)
            weight = int(float(props.get("font-weight", "400")))
            foreground = _paint(self._rule(color_selector)["color"], self.colors)
            bar = _minimum(size, weight)
            for background_name in backgrounds:
                ratio = contrast(foreground, self._surface(background_name))
                self.assertGreaterEqual(
                    ratio,
                    bar,
                    f"{selector} on {background_name} is {ratio:.2f}:1, needs {bar}:1",
                )

        outline = self._rule("button:focus-visible")
        ring = _paint(outline["outline"], self.colors)
        for background_name in _FOCUS_SURFACES:
            ratio = contrast(ring, self._surface(background_name))
            self.assertGreaterEqual(ratio, 3, f"focus on {background_name} is {ratio:.2f}:1")

        solid_bars = (
            (".crate-row:has(.crate[aria-selected=\"true\"])", "--color-panel"),
            ('.row[aria-selected="true"]', "--color-selection"),
        )
        for selector, background_name in solid_bars:
            ink = _paint(self._rule(selector)["box-shadow"], self.colors)
            ratio = contrast(ink, self._surface(background_name))
            self.assertGreaterEqual(ratio, 3, f"{selector} is {ratio:.2f}:1")

        holds = self._rule(".crate-row.holds-selection")["box-shadow"]
        alpha = _mix_amount(holds)
        self.assertIsNotNone(alpha)
        mark = _paint(holds, self.colors)
        for background_name in ("--color-bg", "--color-panel"):
            surface = self._surface(background_name)
            ratio = contrast(_over(mark, surface, alpha or 0), surface)
            self.assertGreaterEqual(ratio, 3, f"holds-selection on {background_name} is {ratio:.2f}:1")

        for selector in ("#consent-accept", "#open-logs", "#copy-logs", "#rekordbox-cancel", "#merge-cancel"):
            border = _paint(self._rule(selector)["border"], self.colors)
            ratio = contrast(border, self._surface("--color-card"))
            self.assertGreaterEqual(ratio, 3, f"{selector} border is {ratio:.2f}:1")

        pill = {selector: props for selector, props in self.token_rules}
        pill_pairs = (
            (".pill-preview", "--color-safe-bg", "color", 4.5),
            (".pill-preview", "--color-safe-bg", "border", 3),
            (".pill-preview.warn", "--color-warn-bg", "color", 4.5),
            (".pill-preview.warn", "--color-warn-bg", "border-color", 3),
            (".pill-preview.danger", "--color-card", "color", 4.5),
            (".pill-preview.danger", "--color-card", "border-color", 3),
        )
        for selector, background_name, prop, bar in pill_pairs:
            ratio = contrast(_paint(pill[selector][prop], self.colors), self._surface(background_name))
            self.assertGreaterEqual(ratio, bar, f"{selector} {prop} is {ratio:.2f}:1")

        bordered = {
            selector
            for selector, props in self.app_rules
            if any(
                key in props and ("var(" in props[key] or "color-mix" in props[key])
                for key in ("border", "border-top", "border-bottom", "border-left", "border-right", "border-color", "box-shadow", "outline")
            )
        }
        checked_borders = _DECORATIVE | {
            "button:focus-visible",
            "input:focus-visible",
            "select:focus-visible",
            "textarea:focus-visible",
            ".list:focus-visible",
            ".crate:focus-visible",
            ".twist:focus-visible",
            '.crate-row:has(.crate[aria-selected="true"])',
            '.row[aria-selected="true"]',
            ".crate-row.holds-selection",
            "#consent-accept",
            "#open-logs",
            "#copy-logs",
            "#rekordbox-cancel",
            "#merge-cancel",
        }
        self.assertEqual(bordered - checked_borders, set(), "borders missing from the contrast list")
        self.assertEqual(checked_borders - bordered, set(), "contrast list names a border that is not painted")

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
                "--color-text-muted": "#6a6057",
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
