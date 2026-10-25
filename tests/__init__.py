"""Tests for the Serato library page.

The suite never opens the live Serato database. Each library test points
library.MASTER at a temporary file. Settings and logs are pointed at a
temporary directory so a run does not read or write the machine's
Serato Library config.
"""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile
from pathlib import Path

_ISOLATION = Path(tempfile.mkdtemp(prefix="serato-library-tests-"))
os.environ["SERATO_LIBRARY_CONFIG_DIR"] = str(_ISOLATION / "config")
os.environ["SERATO_LIBRARY_LOG_DIR"] = str(_ISOLATION / "logs")
atexit.register(shutil.rmtree, _ISOLATION, True)
