#!/usr/bin/env python3
"""Write ``_build_config.py`` before a PyInstaller release build.

GitHub Actions passes ``SENTRY_DSN``, ``POSTHOG_KEY``, and ``POSTHOG_HOST``
from repository secrets. A secret that is not set stays an empty string.
This command prints only whether each one was present.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from build_config import main

if __name__ == "__main__":
    main()
