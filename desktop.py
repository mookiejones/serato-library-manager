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

    ``SERATO_LIBRARY_SMOKE`` selects this path so a release check can
    confirm a frozen build. The check does not open the Serato database,
    bind a port, or open a window.

    Args:
        marker: Absolute file path that receives the text ``ok\\n``.
            A relative path, a symlink, a directory, or a missing parent
            is refused.

    Returns:
        None.

    Raises:
        SystemExit: If the marker path is unusable or a page asset is missing.

    The marker file is created or overwritten. No other file is written.
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

    When ``SERATO_LIBRARY_SMOKE`` is set, ``smoke_check`` runs and this
    function returns without importing pywebview. Otherwise the server
    from ``server.py`` is bound to 127.0.0.1 port 8765 and shown in a
    pywebview window. Closing the window shuts that server down.

    Returns:
        None.

    Raises:
        SystemExit: If pywebview is missing, the library is missing, the port
            is taken, or the smoke check cannot write its marker.

    The window path starts a thread that serves HTTP and opens the live
    Serato database through that server. The smoke path only writes the
    marker file.
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
