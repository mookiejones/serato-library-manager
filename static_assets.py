"""Local files referenced by the library page.

The PyInstaller spec and the release check both use this module. A new
script or stylesheet in ``index.html`` has to be a real file under
``static/`` or the build stops.
"""

from __future__ import annotations

import re
from pathlib import Path

_REF = re.compile(r'(?:src|href)="([^"]+)"')
_REMOTE = ("http://", "https://", "//", "#", "data:")


def local_asset_names(page: Path) -> list[str]:
    """Return static files linked from an HTML page.

    The PyInstaller spec and the release zip check both need this list so
    a new script or stylesheet cannot ship without its file. Remote URLs,
    anchors, and data URLs are skipped. Query strings and fragments are
    removed. Each name is relative to the page's directory. The order is
    the order of the tags, without duplicates.

    Args:
        page: HTML file to scan, normally ``static/index.html``.

    Returns:
        Local ``src`` and ``href`` paths, in tag order, without duplicates.

    Raises:
        OSError: If the page cannot be read.

    Reads the page text. Does not write, and does not check that the
    named files exist.
    """
    names: list[str] = []
    for ref in _REF.findall(page.read_text(encoding="utf-8")):
        if ref.startswith(_REMOTE):
            continue
        local = ref.split("?", 1)[0].split("#", 1)[0].lstrip("/")
        if local and local not in names:
            names.append(local)
    return names


def missing_static_files(static_dir: Path) -> list[str]:
    """Return page assets that are not files under ``static_dir``.

    The build stops when this list is not empty, so a frozen app cannot
    ship a page that points at a missing file. The page itself is
    reported as ``index.html`` when it is missing.

    Args:
        static_dir: Directory that should contain ``index.html`` and the
            local files that page references.

    Returns:
        Paths relative to ``static_dir``, in tag order. Empty when every
        referenced file is present.

    Reads ``index.html`` and checks the filesystem. Does not write.
    """
    page = static_dir / "index.html"
    if not page.is_file():
        return ["index.html"]
    missing = []
    for name in local_asset_names(page):
        if not (static_dir / name).is_file():
            missing.append(name)
    return missing
