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

    Remote URLs, anchors, and data URLs are skipped. Query strings and
    fragments are removed. Each name is relative to the page's directory.
    The order is the order of the tags, without duplicates.

    Raises:
        OSError: If the page cannot be read.
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

    The page itself is reported as ``index.html`` when it is missing.

    Returns:
        Paths relative to ``static_dir``, in tag order.
    """
    page = static_dir / "index.html"
    if not page.is_file():
        return ["index.html"]
    missing = []
    for name in local_asset_names(page):
        if not (static_dir / name).is_file():
            missing.append(name)
    return missing
