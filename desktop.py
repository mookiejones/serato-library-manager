#!/usr/bin/env python3
"""Open the Serato library page in a native window.

The window loads the same server as server.py. Closing the window stops it.
pywebview is imported here so server.py stays on the standard library.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

import server
import static_assets

SMOKE_ENV = "SERATO_LIBRARY_SMOKE"


def smoke_check(marker: Path) -> None:
    """Write ``ok`` once the bundled page assets are readable.

    ``SERATO_LIBRARY_SMOKE`` selects this path. It does not open the
    library, bind a port, or open a window.

    Raises:
        SystemExit: If the marker path is unusable or a page asset is missing.
    """
    if not marker.is_absolute():
        raise SystemExit(f"{SMOKE_ENV} must be an absolute path.")
    if marker.is_symlink():
        raise SystemExit(f"{SMOKE_ENV} must not be a symlink.")
    if marker.exists() and marker.is_dir():
        raise SystemExit(f"{SMOKE_ENV} must be a file path.")
    if not marker.parent.is_dir():
        raise SystemExit(f"{SMOKE_ENV} directory does not exist: {marker.parent}")
    missing = static_assets.missing_static_files(server.app_root() / "static")
    if missing:
        raise SystemExit("Missing bundled files: " + ", ".join(missing))
    marker.write_text("ok\n", encoding="utf-8")


def main() -> None:
    """Start the library server and open it in a native window.

    When ``SERATO_LIBRARY_SMOKE`` is an absolute file path, check the
    bundled page and exit instead. That path does not open a window.

    Raises:
        SystemExit: If pywebview is missing, the library is missing, the port
            is taken, or the smoke check cannot write its marker.
    """
    marker = os.environ.get(SMOKE_ENV)
    if marker:
        smoke_check(Path(marker))
        return
    try:
        import webview
    except ImportError as exc:
        raise SystemExit(
            "The desktop window needs pywebview. "
            "From this directory, run python3 -m venv .venv, then install requirements.txt. "
            "On macOS that is .venv/bin/pip. On Windows it is .venv\\Scripts\\pip."
        ) from exc
    httpd = server.serve()
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    url = f"http://{server.HOST}:{server.PORT}"
    print(f"Serato library  {url}")
    print(f"Library         {server.db_path()}")
    webview.create_window(
        "Serato library",
        url,
        width=1280,
        height=840,
        text_select=True,
    )
    try:
        webview.start()
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=3)


if __name__ == "__main__":
    main()
