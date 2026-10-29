#!/usr/bin/env python3
"""Write ``_version.py`` before a PyInstaller build.

``RELEASE_TAG`` stamps a release when it is ``vMAJOR.MINOR.PATCH`` or an
``-rcN`` / ``-betaN`` tag. Any other build uses ``git describe``, or
``0.0.0+dev`` when git is missing. ``VERSION_COMMIT`` is a hex SHA. A
missing git executable does not fail this command; an invalid tag does.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from version_info import main

if __name__ == "__main__":
    main()
