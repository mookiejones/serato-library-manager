#!/usr/bin/env python3
"""Open the Serato library page in a native window.

The window loads the same server as server.py. Closing the window stops it.
pywebview is imported here so server.py stays on the standard library.
"""

from __future__ import annotations

import threading

import server


def main() -> None:
    """Start the library server and open it in a native window.

    Raises:
        SystemExit: If pywebview is missing, the library is missing, or port 8765 is taken.
    """
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
