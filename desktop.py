#!/usr/bin/env python3
"""Open the Serato library page in the browser.

The process binds 127.0.0.1 on a free port, opens that page, and stays
running until Quit is chosen from the menu bar (macOS) or the notification
area (Windows). A second launch opens the page again and does not start
another server. pystray is imported only when that icon is shown, so the
server and the smoke check do not require a display.
"""

from __future__ import annotations

import errno
import json
import os
import secrets
import signal
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

import app_config
import app_log
import server
import snapshots
import static_assets
import telemetry

SMOKE_ENV = "SERATO_LIBRARY_SMOKE"
LOCK_NAME = "instance.lock"
PORT_NAME = "instance.port"
_READY_SECONDS = 5.0


class Instance:
    """The process that holds the single-instance lock, or a join of one that does.

    Attributes:
        existing_url: Page URL of the copy that is already running.
            None when this process holds the lock.
    """

    def __init__(self, fd: int | None, directory: Path, existing_url: str | None) -> None:
        self._fd = fd
        self.directory = directory
        self.existing_url = existing_url

    def publish(self, url: str) -> None:
        """Record the page URL for a later launch.

        Args:
            url: ``http://127.0.0.1`` URL with a port and no path.

        Raises:
            SystemExit: If this process does not hold the lock, or the URL
                is not a loopback page.

        Writes ``instance.port`` in the config directory. The shutdown
        token is not stored there.
        """
        if self._fd is None:
            raise SystemExit("This launch does not hold the instance lock.")
        loopback = _loopback_url(url)
        if loopback is None:
            raise SystemExit(f"Refusing to publish {url!r}.")
        path = self.directory / PORT_NAME
        temporary = path.with_name(PORT_NAME + ".tmp")
        temporary.write_text(loopback + "\n", encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)

    def release(self) -> None:
        """Drop the lock. A second launch can then start the server.

        Safe to call when this object only observed another running copy.
        """
        if self._fd is None:
            return
        _unlock(self._fd)
        self._fd = None


def _loopback_url(text: str) -> str | None:
    """Return a canonical loopback URL, or None.

    Args:
        text: Candidate URL. A path, query, user, or host other than
            ``127.0.0.1`` is refused.

    Returns:
        ``http://127.0.0.1:<port>`` when the text is that page. None otherwise.
    """
    parsed = urlparse(text.strip())
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.port is None:
        return None
    if parsed.path not in ("", "/") or parsed.params or parsed.query or parsed.fragment:
        return None
    if parsed.username or parsed.password:
        return None
    return f"http://127.0.0.1:{parsed.port}"


def _try_lock(fd: int) -> bool:
    """Take a non-blocking exclusive lock on ``fd``.

    Args:
        fd: Open file descriptor. On Windows the file is at least one byte.

    Returns:
        True when this process holds the lock. False when another process
        holds it.

    Raises:
        OSError: If the lock cannot be attempted.
    """
    if sys.platform == "win32":
        import msvcrt

        os.lseek(fd, 0, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True
    import fcntl

    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        if exc.errno in (errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK):
            return False
        raise
    return True


def _unlock(fd: int) -> None:
    """Release a lock taken by :func:`_try_lock` and close ``fd``.

    Args:
        fd: Descriptor returned by the successful lock.
    """
    if sys.platform == "win32":
        import msvcrt

        os.lseek(fd, 0, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_UN)
    os.close(fd)


def _health_ok(url: str) -> bool:
    """Return whether ``url`` answers ``/api/health``.

    Args:
        url: Loopback origin, without a path.

    Returns:
        True when the body is ``{"ok": true}`` and the status is 200.
    """
    try:
        with urllib.request.urlopen(url + "/api/health", timeout=0.5) as response:
            if response.status != 200:
                return False
            body = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError, UnicodeError, ValueError):
        return False
    return isinstance(body, dict) and body.get("ok") is True


def _wait_for_url(directory: Path) -> str:
    """Wait until the running copy publishes a healthy page URL.

    Args:
        directory: Config directory that holds ``instance.port``.

    Returns:
        The loopback URL.

    Raises:
        SystemExit: If the URL never appears or never answers.
    """
    import time

    deadline = time.monotonic() + _READY_SECONDS
    path = directory / PORT_NAME
    while time.monotonic() < deadline:
        if path.is_file():
            url = _loopback_url(path.read_text(encoding="utf-8"))
            if url and _health_ok(url):
                return url
        time.sleep(0.05)
    raise SystemExit(
        "Serato Library is already running, but its page did not answer. "
        "Quit it from the menu bar or the notification area and try again."
    )


def acquire_instance(directory: Path | None = None) -> Instance:
    """Become the only running copy, or learn the URL of the one that is.

    Args:
        directory: Config directory. None uses :func:`app_config.config_dir`.

    Returns:
        An instance. ``existing_url`` is set when another copy is healthy.

    The lock file is ``instance.lock``. The operating system releases it
    when the process exits, including after a crash.
    """
    folder = directory or app_config.config_dir()
    folder.mkdir(parents=True, exist_ok=True)
    lock_path = folder / LOCK_NAME
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    if os.fstat(fd).st_size < 1:
        os.write(fd, b"\0")
        os.fsync(fd)
    if _try_lock(fd):
        (folder / PORT_NAME).unlink(missing_ok=True)
        return Instance(fd, folder, None)
    os.close(fd)
    return Instance(None, folder, _wait_for_url(folder))


def _validate_marker(marker: Path) -> None:
    """Refuse a smoke-marker path that could write inside the repository.

    Args:
        marker: Path from ``SERATO_LIBRARY_SMOKE``.

    Raises:
        SystemExit: If the path is relative, a symlink, a directory, or
            its parent directory does not exist.
    """
    if not marker.is_absolute():
        raise SystemExit(f"{SMOKE_ENV} must be an absolute path.")
    if marker.is_symlink():
        raise SystemExit(f"{SMOKE_ENV} must not be a symlink.")
    if marker.exists() and marker.is_dir():
        raise SystemExit(f"{SMOKE_ENV} must be a file path.")
    if not marker.parent.is_dir():
        raise SystemExit(f"{SMOKE_ENV} directory does not exist: {marker.parent}")


def write_smoke_marker(marker: Path, url: str, token: str) -> None:
    """Write the smoke URL and shutdown token for the release harness.

    Args:
        marker: Absolute file path. Replaced if it already exists.
        url: Loopback origin.
        token: Secret the harness sends in ``X-Serato-Library-Shutdown``.

    Raises:
        SystemExit: If the URL is not loopback.

    The file mode is ``0600``. A crash mid-write cannot leave a partial
    marker, because the bytes are replaced into place.
    """
    loopback = _loopback_url(url)
    if loopback is None:
        raise SystemExit(f"Refusing smoke URL {url!r}.")
    payload = f"{loopback}\n{token}\n".encode("utf-8")
    temporary = marker.with_name(marker.name + ".tmp")
    temporary.unlink(missing_ok=True)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, payload)
    finally:
        os.close(fd)
    os.chmod(temporary, 0o600)
    os.replace(temporary, marker)


def parse_smoke_marker(text: str) -> tuple[str, str] | None:
    """Return the URL and token from a smoke marker, or None.

    Args:
        text: File contents. The first line is the URL and the second is
            the token.

    Returns:
        The pair when both lines are present and the URL is loopback.
        None when the marker is incomplete.
    """
    lines = text.splitlines()
    if len(lines) != 2:
        return None
    url = _loopback_url(lines[0])
    token = lines[1]
    if url is None or not token or any(char in token for char in "\r\n "):
        return None
    return url, token


def smoke_main(marker: Path) -> None:
    """Serve ``/api/health`` until the harness shuts the process down.

    Args:
        marker: Absolute path that receives the URL and the shutdown token.

    Raises:
        SystemExit: If the marker path is unusable or a page asset is missing.

    Does not open the Serato library, a browser, a menu icon, or telemetry.
    The server listens on 127.0.0.1 and a free port.
    """
    _validate_marker(marker)
    missing = static_assets.missing_static_files(server.app_root() / "static")
    if missing:
        raise SystemExit("Missing bundled files: " + ", ".join(missing))
    token = secrets.token_hex(32)
    httpd = server.serve(port=0, require_library=False)
    httpd.shutdown_token = token
    host, port = httpd.server_address
    url = f"http://{host}:{port}"
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        write_smoke_marker(marker, url, token)
        thread.join()
    finally:
        if thread.is_alive():
            httpd.shutdown()
            thread.join(timeout=3)
        httpd.server_close()


def open_browser(url: str) -> None:
    """Open ``url`` in the default browser.

    Args:
        url: Loopback page. Other URLs are ignored.

    A failure is logged. The server keeps running so Quit still works.
    """
    if _loopback_url(url) is None:
        app_log.logger.error("Refusing to open %s", url)
        return
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", url])
        elif sys.platform == "win32":
            os.startfile(url)  # type: ignore[attr-defined]
        else:
            import webbrowser

            webbrowser.open(url)
    except OSError:
        app_log.logger.exception("The browser could not be opened")


def _wait_for_thread(httpd: server.ThreadingHTTPServer, thread: threading.Thread) -> None:
    """Block until ``thread`` finishes, and stop it on SIGTERM or Ctrl-C.

    Args:
        httpd: Listening server.
        thread: Thread running ``serve_forever``.
    """

    def stop(signum: int, frame: object) -> None:
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    thread.join()


def run_tray(url: str, httpd: server.ThreadingHTTPServer, thread: threading.Thread) -> None:
    """Show Quit and Open, and block until Quit or a signal.

    Args:
        url: Page to open from the menu.
        httpd: Listening server. Quit shuts it down.
        thread: Thread running ``serve_forever``.

    On macOS the icon is a menu-bar item. On Windows it is a notification
    area icon. If the toolkit cannot load, the server stays up until a
    signal, which is how a headless run can still be stopped.
    """
    try:
        import pystray
        from PIL import Image
    except (ImportError, OSError, ValueError):
        app_log.logger.exception("The menu icon could not be loaded")
        _wait_for_thread(httpd, thread)
        return
    image_path = server.app_root() / "packaging" / "menu-icon.png"
    if not image_path.is_file():
        raise SystemExit(f"Missing menu icon: {image_path}")
    image = Image.open(image_path)

    def on_open(icon: object, item: object) -> None:
        open_browser(url)

    def on_quit(icon: object, item: object) -> None:
        icon.stop()  # type: ignore[attr-defined]
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    menu = pystray.Menu(
        pystray.MenuItem("Open Serato Library", on_open, default=True),
        pystray.MenuItem("Quit", on_quit),
    )
    icon = pystray.Icon("serato-library", image, "Serato Library", menu)

    def stop(signum: int, frame: object) -> None:
        icon.stop()
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    icon.run()
    thread.join(timeout=3)


def launch() -> None:
    """Start the page, or open the browser if a copy is already running.

    Raises:
        SystemExit: If the Serato library is missing, or the running copy
            does not answer.

    Binds 127.0.0.1 on a free port. Closing the browser does not stop the
    server. Quit on the menu icon does.
    """
    holder = acquire_instance()
    try:
        if holder.existing_url:
            open_browser(holder.existing_url)
            return
        if not server.db_path().exists():
            raise SystemExit(f"Serato library not found at {server.db_path()}")
        httpd = server.serve(port=0, require_library=True)
        host, port = httpd.server_address
        url = f"http://{host}:{port}"
        holder.publish(url)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            open_browser(url)
            run_tray(url, httpd, thread)
        finally:
            if thread.is_alive():
                httpd.shutdown()
                thread.join(timeout=3)
            httpd.server_close()
            snapshots.stop_watch()
            telemetry.shutdown()
    finally:
        holder.release()


def main() -> None:
    """Run the smoke check, or open the library in the browser.

    When ``SERATO_LIBRARY_SMOKE`` is set, :func:`smoke_main` serves health
    and returns after shutdown. Otherwise :func:`launch` runs.

    Raises:
        SystemExit: If the smoke marker is unusable, a page asset is
            missing, or the library is missing.
    """
    marker = os.environ.get(SMOKE_ENV)
    if marker:
        smoke_main(Path(marker))
        return
    launch()


if __name__ == "__main__":
    main()
