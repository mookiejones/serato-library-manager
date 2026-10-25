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


def _cleanup_isolation() -> None:
    """Close the log file, then delete the temporary settings directory.

    A rotating handler keeps the log open. Windows refuses to remove
    that file until the handler is closed. Errors during cleanup are
    ignored so a test failure is not replaced by a cleanup error.
    """
    try:
        import app_log

        app_log.close_files()
    except Exception:
        pass
    shutil.rmtree(_ISOLATION, True)


atexit.register(_cleanup_isolation)
