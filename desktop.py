#!/usr/bin/env python3
"""Open the Serato library in a native window.

The process binds 127.0.0.1 on a free port, then opens that page in the
system web view: WebView2 on Windows, WKWebView on macOS, and WebKitGTK
or Qt WebKit on Linux. Chromium is not bundled. Closing the window shuts
the server down with the desktop shutdown token. A second launch focuses
that window and does not start another server.

``SERATO_LIBRARY_SMOKE`` is the headless release check. It never imports
the web view. ``SERATO_LIBRARY_NO_WINDOW=1`` or ``--no-window`` skips the
window on a normal launch and waits until shutdown.
"""

from __future__ import annotations

import errno
import json
import os
import secrets
import signal
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
WAVEFORM_SMOKE_ENV = "SERATO_LIBRARY_WAVEFORM_SMOKE"
NO_WINDOW_ENV = "SERATO_LIBRARY_NO_WINDOW"
NO_WINDOW_FLAG = "--no-window"
LOCK_NAME = "instance.lock"
PORT_NAME = "instance.port"
FOCUS_NAME = "instance.focus"
WINDOW_TITLE = "Serato Library"
# Walnut page background (--color-bg in static/tokens.css) so the frame
# does not flash white before the page paints.
WINDOW_BACKGROUND = "#231910"
DEFAULT_WIDTH = 1120
DEFAULT_HEIGHT = 720
# A saved position is restored only when at least this much of the title
# bar is on some screen. The strip is the top of the window.
TITLE_BAR_MIN_WIDTH = 100
TITLE_BAR_MIN_HEIGHT = 40
GEOMETRY_SAVE_DELAY = 0.4
_READY_SECONDS = 5.0
_GUI_WINDOWS = "edgechromium"
_GUI_MAC = "cocoa"
_GUI_GTK = "gtk"
_GUI_QT = "qt"
_ALLOWED_GUI = frozenset({_GUI_WINDOWS, _GUI_MAC, _GUI_GTK, _GUI_QT})
_WEBVIEW2_CLIENT = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
_WEBVIEW2_NEED = (86, 0, 622, 0)
_ALREADY_RUNNING = (
    "Serato Library is already running, but its window could not be focused. "
    "Close that window and try again."
)


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

    def publish_focus(self, token: str) -> None:
        """Record the token a later launch sends to focus this window.

        Args:
            token: Secret for ``X-Serato-Library-Focus``. It must not
                contain whitespace.

        Raises:
            SystemExit: If this process does not hold the lock, or the
                token is empty or contains whitespace.

        Writes ``instance.focus`` with mode ``0600``. The page is not
        given this token.
        """
        if self._fd is None:
            raise SystemExit("This launch does not hold the instance lock.")
        if not isinstance(token, str) or not token or any(char in token for char in "\r\n \t"):
            raise SystemExit("Refusing to publish an empty focus token.")
        path = self.directory / FOCUS_NAME
        temporary = path.with_name(FOCUS_NAME + ".tmp")
        temporary.write_text(token + "\n", encoding="utf-8")
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
        "Close its window and try again."
    )


def acquire_instance(directory: Path | None = None) -> Instance:
    """Become the only running copy, or learn the URL of the one that is.

    Args:
        directory: Config directory. None uses :func:`app_config.config_dir`.

    Returns:
        An instance. ``existing_url`` is set when another copy is healthy.

    The lock file is ``instance.lock``. The operating system releases it
    when the process exits, including after a crash. A fresh lock clears
    ``instance.port`` and ``instance.focus`` from the previous process.
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
        (folder / FOCUS_NAME).unlink(missing_ok=True)
        return Instance(fd, folder, None)
    os.close(fd)
    return Instance(None, folder, _wait_for_url(folder))


def read_focus_token(directory: Path) -> str | None:
    """Return the focus token stored beside the page URL, or None.

    Args:
        directory: Config directory that holds ``instance.focus``.

    Returns:
        The token when the file is one non-empty line without whitespace.
        None when the file is missing, unreadable, or not that shape.
    """
    path = directory / FOCUS_NAME
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    lines = text.splitlines()
    if len(lines) != 1:
        return None
    token = lines[0]
    if not token or any(char in token for char in "\r\n \t"):
        return None
    return token


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

    Does not open the Serato library, a window, or telemetry. The server
    listens on 127.0.0.1 and a free port. The web view is not imported.
    When ``SERATO_LIBRARY_WAVEFORM_SMOKE`` is a WAV path, that file is
    analyzed before the server starts. A missing miniaudio extension
    fails the process here.
    """
    _validate_marker(marker)
    _smoke_waveform()
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


def _smoke_waveform() -> None:
    """Analyze the smoke WAV when the harness asked for a waveform.

    Returns:
        None when the variable is unset.

    Raises:
        SystemExit: The file cannot be decoded, or the body is not ``SWF1``.
    """
    probe = os.environ.get(WAVEFORM_SMOKE_ENV)
    if not probe:
        return
    import waveform

    try:
        body, _cached = waveform.load(Path(probe))
    except waveform.WaveformUnavailable as exc:
        raise SystemExit("Waveform smoke could not decode the file") from exc
    if not body.startswith(b"SWF1"):
        raise SystemExit("Waveform smoke did not produce a waveform")


def window_skipped(argv: list[str] | None = None) -> bool:
    """Return whether this launch should serve without opening a window.

    Args:
        argv: Arguments after the program name. None reads ``sys.argv``.

    Returns:
        True when ``--no-window`` is one of those arguments, or
        ``SERATO_LIBRARY_NO_WINDOW`` is exactly ``1``. ``0``, ``true``,
        and a blank value leave the window on.

    The smoke path does not call this. ``SERATO_LIBRARY_SMOKE`` never
    opens a window, including when this flag is absent.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if NO_WINDOW_FLAG in args:
        return True
    return os.environ.get(NO_WINDOW_ENV) == "1"


def webview2_version_ok(build: object) -> bool:
    """Return whether a WebView2 build string is new enough to use.

    Args:
        build: ``pv`` registry value. Dotted integers, such as
            ``120.0.2210.91``.

    Returns:
        True when ``build`` is a dotted integer string at or after
        ``86.0.622.0``. False for a bool, a number, or a non-numeric
        piece. A shorter string is padded with zeros on the right.
    """
    if not isinstance(build, str) or not build:
        return False
    parts: list[int] = []
    for piece in build.split("."):
        if not piece.isdigit():
            return False
        parts.append(int(piece))
    if not parts:
        return False
    found = tuple(parts)
    length = max(len(found), len(_WEBVIEW2_NEED))
    found_padded = found + (0,) * (length - len(found))
    need_padded = _WEBVIEW2_NEED + (0,) * (length - len(_WEBVIEW2_NEED))
    return found_padded >= need_padded


def webview2_runtime_installed() -> bool:
    """Return whether the system WebView2 runtime is installed.

    Returns:
        True on Windows when the Evergreen runtime's ``pv`` value is at
        least ``86.0.622.0``. False on every other operating system, and
        when the registry key is missing.

    Reads the registry. Does not download a runtime and does not look
    for a copy bundled with this app.
    """
    if sys.platform != "win32":
        return False
    import winreg

    subkeys = (
        rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{_WEBVIEW2_CLIENT}",
        rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{_WEBVIEW2_CLIENT}",
    )
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for subkey in subkeys:
            try:
                with winreg.OpenKey(root, subkey) as handle:
                    build, _ = winreg.QueryValueEx(handle, "pv")
            except OSError:
                continue
            if webview2_version_ok(build):
                return True
    return False


def _gtk_webkit_available() -> bool:
    """Return whether GTK 3 and WebKit2 can be imported.

    Returns:
        True when ``gi`` can load Gtk 3.0 and WebKit2 4.1, or WebKit2 4.0
        when 4.1 is absent. False when those libraries are not installed.
    """
    try:
        import gi

        gi.require_version("Gtk", "3.0")
        try:
            gi.require_version("WebKit2", "4.1")
        except ValueError:
            gi.require_version("WebKit2", "4.0")
        from gi.repository import Gtk, WebKit2  # noqa: F401
    except Exception:
        return False
    return True


def _qt_webengine_available() -> bool:
    """Return whether Qt WebEngine can be imported.

    Returns:
        True when ``qtpy`` can import ``QWebEngineView``. That engine is
        Chromium, so :func:`choose_gui` will not select it.
    """
    try:
        from qtpy.QtWebEngineWidgets import QWebEngineView  # noqa: F401
    except Exception:
        return False
    return True


def _qt_webkit_available() -> bool:
    """Return whether Qt WebKit can be imported.

    Returns:
        True when PyQt5's ``QWebView`` imports. False when Qt WebKit is
        not installed. Qt WebEngine is a different import and is not
        treated as this engine.
    """
    try:
        from PyQt5.QtWebKitWidgets import QWebView  # noqa: F401
    except Exception:
        return False
    return True


def choose_gui(
    platform: str,
    *,
    webview2: bool,
    gtk: bool,
    qtwebkit: bool,
    qtwebengine: bool,
) -> str:
    """Pick the system web view for this operating system.

    Args:
        platform: ``sys.platform`` value, such as ``win32`` or ``darwin``.
        webview2: True when the Windows WebView2 runtime is installed.
        gtk: True when WebKitGTK can be imported.
        qtwebkit: True when Qt WebKit can be imported.
        qtwebengine: True when Qt WebEngine can be imported. That engine
            is refused because it bundles Chromium.

    Returns:
        ``edgechromium`` on Windows, ``cocoa`` on macOS, ``gtk`` when
        WebKitGTK is present, or ``qt`` when only Qt WebKit is present.

    Raises:
        SystemExit: On Windows without WebView2, on Linux with only Qt
            WebEngine, or on Linux with neither WebKitGTK nor Qt WebKit.
            CEF and MSHTML are not returned.
    """
    if platform == "win32":
        if not webview2:
            raise SystemExit(
                "Serato Library needs the Microsoft Edge WebView2 Runtime. "
                "Install it, then open Serato Library again."
            )
        return _GUI_WINDOWS
    if platform == "darwin":
        return _GUI_MAC
    if gtk:
        return _GUI_GTK
    if qtwebkit and not qtwebengine:
        return _GUI_QT
    if qtwebengine:
        raise SystemExit(
            "Qt WebEngine bundles Chromium and is not used. "
            "Install WebKitGTK, or Qt WebKit without Qt WebEngine."
        )
    raise SystemExit(
        "Serato Library needs WebKitGTK (GTK 3 and WebKit2) or Qt WebKit. "
        "Chromium is not bundled."
    )


def detect_gui() -> str:
    """Choose the system web view for the machine running this process.

    Returns:
        The name :func:`choose_gui` returns for ``sys.platform``.

    Raises:
        SystemExit: When that platform has no accepted web view.

    Probes are imported only for the platform that needs them. Windows
    does not import GTK. macOS does not read the WebView2 registry.
    """
    windows = sys.platform == "win32"
    mac = sys.platform == "darwin"
    linux = not windows and not mac
    return choose_gui(
        sys.platform,
        webview2=webview2_runtime_installed() if windows else False,
        gtk=_gtk_webkit_available() if linux else False,
        qtwebkit=_qt_webkit_available() if linux else False,
        qtwebengine=_qt_webengine_available() if linux else False,
    )


def _screen_box(screen: object) -> tuple[int, int, int, int] | None:
    """Return ``x, y, width, height`` for a screen object, or None.

    Args:
        screen: Object with those four integer attributes. A bool is
            rejected because ``bool`` is a subclass of ``int``.

    Returns:
        The four integers when each one is an ``int``. None otherwise.
    """
    values = []
    for name in ("x", "y", "width", "height"):
        value = getattr(screen, name, None)
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        values.append(value)
    return values[0], values[1], values[2], values[3]


def _overlap(
    ax: int,
    ay: int,
    aw: int,
    ah: int,
    bx: int,
    by: int,
    bw: int,
    bh: int,
) -> tuple[int, int]:
    """Return the width and height of the overlap of two rectangles.

    Args:
        ax: Left edge of the first rectangle.
        ay: Top edge of the first rectangle.
        aw: Width of the first rectangle.
        ah: Height of the first rectangle.
        bx: Left edge of the second rectangle.
        by: Top edge of the second rectangle.
        bw: Width of the second rectangle.
        bh: Height of the second rectangle.

    Returns:
        ``(width, height)`` of the intersection. Either component is ``0``
        when the rectangles do not overlap. Origins may be negative.
    """
    width = min(ax + aw, bx + bw) - max(ax, bx)
    height = min(ay + ah, by + bh) - max(ay, by)
    if width < 0:
        width = 0
    if height < 0:
        height = 0
    return width, height


def title_bar_is_visible(
    x: int,
    y: int,
    width: int,
    height: int,
    screens: list[object],
) -> bool:
    """Return whether a 100 by 40 pixel strip of the title bar is on a screen.

    Args:
        x: Left edge of the window. Negative when the window is on a
            monitor to the left of the primary screen.
        y: Top edge of the window. Negative when the window is on a
            monitor above the primary screen.
        width: Window width.
        height: Window height.
        screens: Screen objects. A bool coordinate is not a screen.

    Returns:
        True when the top 40 pixels of the window share at least
        ``TITLE_BAR_MIN_WIDTH`` by ``TITLE_BAR_MIN_HEIGHT`` pixels with
        one screen. False when that strip is missing, clipped below that
        size, or no screen can be measured.
    """
    if width < TITLE_BAR_MIN_WIDTH or height < TITLE_BAR_MIN_HEIGHT:
        return False
    for screen in screens:
        box = _screen_box(screen)
        if box is None:
            continue
        sx, sy, sw, sh = box
        if sw <= 0 or sh <= 0:
            continue
        overlap_w, overlap_h = _overlap(x, y, width, TITLE_BAR_MIN_HEIGHT, sx, sy, sw, sh)
        if overlap_w >= TITLE_BAR_MIN_WIDTH and overlap_h >= TITLE_BAR_MIN_HEIGHT:
            return True
    return False


def primary_screen(screens: list[object]) -> tuple[int, int, int, int] | None:
    """Return the screen that contains the origin, or the first usable one.

    Args:
        screens: Screen objects in toolkit order.

    Returns:
        ``(x, y, width, height)`` of the screen whose half-open box
        contains ``(0, 0)``. When none does, the first screen with a
        positive size. None when every screen is unusable.
    """
    first: tuple[int, int, int, int] | None = None
    for screen in screens:
        box = _screen_box(screen)
        if box is None:
            continue
        sx, sy, sw, sh = box
        if sw <= 0 or sh <= 0:
            continue
        if first is None:
            first = box
        if sx <= 0 < sx + sw and sy <= 0 < sy + sh:
            return box
    return first


def centered_on_primary(width: int, height: int, screens: list[object]) -> tuple[int, int] | None:
    """Return the top-left corner that centers the window on the primary screen.

    Args:
        width: Window width.
        height: Window height.
        screens: Screen objects. The primary screen is the one that
            contains ``(0, 0)``.

    Returns:
        ``(x, y)`` of the centered window. None when no screen can be
        measured. The coordinates may be negative when the window is
        larger than that screen.
    """
    box = primary_screen(screens)
    if box is None:
        return None
    sx, sy, sw, sh = box
    return sx + (sw - width) // 2, sy + (sh - height) // 2


def _event_int(value: object, low: int, high: int) -> int | None:
    """Return a pixel count from a web-view event, or None.

    Args:
        value: Event argument. Floats from the macOS frame are rounded
            to the nearest integer. Bools are rejected before the ``int``
            check.
        low: Smallest accepted value, inclusive.
        high: Largest accepted value, inclusive.

    Returns:
        The integer inside the range. None when the value cannot be used.
        ``0`` is kept when ``low`` allows it.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        number = value
    elif isinstance(value, float):
        try:
            number = int(round(value))
        except (OverflowError, ValueError):
            return None
    else:
        return None
    if number < low or number > high:
        return None
    return number


class _GeometryWriter:
    """Remember the latest move and resize, then write them together.

    The web view reports position and size as separate events. A file
    written from only one of them would be a partial frame, which the
    loader drops. The write waits until both are known, and until the
    events pause, so a drag does not rewrite ``settings.json`` on every
    pixel.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._x: int | None = None
        self._y: int | None = None
        self._width: int | None = None
        self._height: int | None = None
        self._timer: threading.Timer | None = None

    def reset(self) -> None:
        """Drop a frame that has not been written and cancel its timer."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._x = None
            self._y = None
            self._width = None
            self._height = None

    def resize(self, width: object, height: object) -> None:
        """Remember a size when both edges are inside the stored range.

        Args:
            width: Event width. A bool or a value below the minimum is
                ignored, and the previous size is left in place.
            height: Event height, with the same rule.
        """
        width_px = _event_int(width, app_config.WINDOW_MIN_WIDTH, app_config.WINDOW_MAX_EDGE)
        height_px = _event_int(height, app_config.WINDOW_MIN_HEIGHT, app_config.WINDOW_MAX_EDGE)
        if width_px is None or height_px is None:
            return
        with self._lock:
            self._width = width_px
            self._height = height_px
            self._schedule()

    def move(self, x: object, y: object) -> None:
        """Remember a position when both origins are inside the stored range.

        Args:
            x: Event x. ``0`` is kept. A bool is ignored.
            y: Event y, with the same rule.
        """
        x_px = _event_int(x, app_config.WINDOW_MIN_ORIGIN, app_config.WINDOW_MAX_ORIGIN)
        y_px = _event_int(y, app_config.WINDOW_MIN_ORIGIN, app_config.WINDOW_MAX_ORIGIN)
        if x_px is None or y_px is None:
            return
        with self._lock:
            self._x = x_px
            self._y = y_px
            self._schedule()

    def _schedule(self) -> None:
        """Queue one write after the events pause. The caller holds the lock."""
        if self._timer is not None:
            self._timer.cancel()
        self._timer = threading.Timer(GEOMETRY_SAVE_DELAY, self.flush)
        self._timer.daemon = True
        self._timer.start()

    def flush(self) -> None:
        """Write the frame when position and size are both known.

        A missing half is left unwritten. The settings lock inside
        :func:`app_config.save_window_geometry` keeps a sharing choice
        that was saved while the window was moving.
        """
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            values = (self._x, self._y, self._width, self._height)
        if any(item is None for item in values):
            return
        x, y, width, height = values
        if x is None or y is None or width is None or height is None:
            return
        try:
            app_config.save_window_geometry(app_config.WindowGeometry(x, y, width, height))
        except (OSError, ValueError):
            app_log.logger.exception("The window size could not be saved")


_geometry = _GeometryWriter()


def note_window_resized(*values: object) -> None:
    """Record a resize event from the web view.

    Args:
        values: Width and height. Any other count is ignored so a toolkit
            that emits a different payload cannot store a partial frame.
    """
    if len(values) != 2:
        return
    _geometry.resize(values[0], values[1])


def note_window_moved(*values: object) -> None:
    """Record a move event from the web view.

    Args:
        values: ``x`` and ``y``. Any other count is ignored.
    """
    if len(values) != 2:
        return
    _geometry.move(values[0], values[1])


def flush_window_geometry() -> None:
    """Write the latest frame now, if both position and size are known."""
    _geometry.flush()


def reset_window_geometry() -> None:
    """Forget a frame that has not been written yet.

    The next window starts from an empty record so a previous launch in
    this process cannot mix its size with the new position.
    """
    _geometry.reset()


def post_shutdown(url: str, token: str) -> None:
    """Ask the server to stop, using the desktop shutdown token.

    Args:
        url: Loopback origin.
        token: Value of ``X-Serato-Library-Shutdown`` for this process.

    A second call, after the server has already stopped, is logged and
    ignored. The token is not written to the log.
    """
    request = urllib.request.Request(
        url + "/api/shutdown",
        data=b"{}",
        headers={server.SHUTDOWN_HEADER: token},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            response.read()
    except (OSError, urllib.error.URLError):
        app_log.logger.info("The shutdown request was not answered")


def focus_existing(url: str, directory: Path) -> None:
    """Ask the running copy to bring its window forward.

    Args:
        url: Loopback origin published by that copy.
        directory: Config directory that holds ``instance.focus``.

    Raises:
        SystemExit: If the URL is not loopback, the token is missing, or
            the focus request does not succeed. This process does not
            start a server of its own.
    """
    if _loopback_url(url) is None:
        raise SystemExit(f"Refusing to focus {url!r}.")
    token = read_focus_token(directory)
    if token is None:
        raise SystemExit(_ALREADY_RUNNING)
    request = urllib.request.Request(
        url + "/api/focus",
        data=b"{}",
        headers={server.FOCUS_HEADER: token},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            if response.status != 200:
                raise SystemExit(_ALREADY_RUNNING)
            response.read()
    except urllib.error.HTTPError as exc:
        raise SystemExit(_ALREADY_RUNNING) from exc
    except (OSError, urllib.error.URLError) as exc:
        raise SystemExit(_ALREADY_RUNNING) from exc


def _focus(window: object) -> None:
    """Restore a minimized window and bring it to the front.

    Args:
        window: pywebview window. ``restore`` and ``show`` are called
            when the object provides them. Each call is marshalled onto
            the GUI thread by pywebview.
    """
    restore = getattr(window, "restore", None)
    show = getattr(window, "show", None)
    if callable(restore):
        restore()
    if callable(show):
        show()


def _place_on_screen(window: object) -> None:
    """Center the window when its title bar is not on a screen.

    Args:
        window: pywebview window that has already been shown. Reading
            ``x`` and ``y`` waits until the toolkit has placed it.

    A saved position is kept when a 100 by 40 pixel strip of the title
    bar lies on some screen, including a monitor whose origin is
    negative. Otherwise the window is centered on the primary screen.
    A toolkit that cannot list screens leaves the window where it is.
    """
    try:
        import webview

        screens = list(webview.screens or [])
    except Exception:
        app_log.logger.exception("The window position could not be checked")
        return
    x = getattr(window, "x", None)
    y = getattr(window, "y", None)
    width = getattr(window, "width", None)
    height = getattr(window, "height", None)
    if not all(isinstance(value, int) and not isinstance(value, bool) for value in (x, y, width, height)):
        return
    if title_bar_is_visible(x, y, width, height, screens):
        return
    origin = centered_on_primary(width, height, screens)
    if origin is None:
        return
    move = getattr(window, "move", None)
    if callable(move):
        move(origin[0], origin[1])


def _close_window(url: str, token: str) -> None:
    """Save the frame, then stop the server with the shutdown token.

    Args:
        url: Loopback origin.
        token: Shutdown token for this process.
    """
    flush_window_geometry()
    post_shutdown(url, token)


def _install_stop_signals(stop: object) -> tuple[object, object]:
    """Point SIGTERM and SIGINT at ``stop`` and return the previous handlers.

    Args:
        stop: Callable used as the signal handler.

    Returns:
        The previous SIGTERM and SIGINT handlers, so the caller can put
        them back.

    Raises:
        ValueError: If this is not the main thread. Signals can only be
            set there.
    """
    previous_term = signal.getsignal(signal.SIGTERM)
    previous_int = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGTERM, stop)  # type: ignore[arg-type]
    signal.signal(signal.SIGINT, stop)  # type: ignore[arg-type]
    return previous_term, previous_int


def _restore_stop_signals(previous_term: object, previous_int: object) -> None:
    """Put the previous SIGTERM and SIGINT handlers back.

    Args:
        previous_term: Handler returned by :func:`_install_stop_signals`.
        previous_int: Handler returned by :func:`_install_stop_signals`.
    """
    signal.signal(signal.SIGTERM, previous_term)  # type: ignore[arg-type]
    signal.signal(signal.SIGINT, previous_int)  # type: ignore[arg-type]


def open_window(
    url: str,
    httpd: server.ThreadingHTTPServer,
    thread: threading.Thread,
    token: str,
) -> None:
    """Open ``url`` in the system web view and block until the window closes.

    Args:
        url: Loopback origin.
        httpd: Listening server. Its focus callback is replaced with one
            that restores and shows this window.
        thread: Thread running ``serve_forever``.
        token: Shutdown token. Closing the window POSTs it to
            ``/api/shutdown``.

    Raises:
        SystemExit: If the URL is not loopback, the platform has no
            accepted web view, or the toolkit cannot create the window.

    pywebview is imported here, not at startup, so the smoke check and
    ``--no-window`` do not need a display. The GUI is ``edgechromium``,
    ``cocoa``, ``gtk``, or ``qt``. CEF is not requested.
    """
    if _loopback_url(url) is None:
        raise SystemExit(f"Refusing to open {url!r}.")
    gui = detect_gui()
    if gui not in _ALLOWED_GUI:
        raise SystemExit(f"Refusing web view {gui!r}.")
    import webview

    reset_window_geometry()
    saved = app_config.load_settings().window
    options: dict[str, object] = {
        "width": saved.width if saved is not None else DEFAULT_WIDTH,
        "height": saved.height if saved is not None else DEFAULT_HEIGHT,
        "min_size": (app_config.WINDOW_MIN_WIDTH, app_config.WINDOW_MIN_HEIGHT),
        "text_select": True,
        "focus": True,
        "background_color": WINDOW_BACKGROUND,
    }
    if saved is not None:
        options["x"] = saved.x
        options["y"] = saved.y
    window = webview.create_window(WINDOW_TITLE, url, **options)
    if window is None:
        raise SystemExit("The window could not be created.")
    window.events.resized += note_window_resized
    window.events.moved += note_window_moved
    window.events.shown += lambda: _place_on_screen(window)
    window.events.closed += lambda: _close_window(url, token)
    httpd.focus_window = lambda: _focus(window)

    def stop(signum: int, frame: object) -> None:
        flush_window_geometry()
        destroy = getattr(window, "destroy", None)
        if callable(destroy):
            try:
                destroy()
            except Exception:
                app_log.logger.exception("The window could not be closed")
        threading.Thread(target=post_shutdown, args=(url, token), daemon=True).start()

    previous_term, previous_int = _install_stop_signals(stop)
    try:
        try:
            webview.start(gui=gui, private_mode=True)
        except Exception as exc:
            if type(exc).__name__ != "WebViewException":
                raise
            raise SystemExit(f"The window could not be opened: {exc}") from exc
    finally:
        _restore_stop_signals(previous_term, previous_int)
        flush_window_geometry()
        if thread.is_alive():
            post_shutdown(url, token)


def run_until_stopped(
    httpd: server.ThreadingHTTPServer,
    thread: threading.Thread,
    url: str,
    token: str,
) -> None:
    """Block until the server stops, without opening a window.

    Args:
        httpd: Listening server.
        thread: Thread running ``serve_forever``.
        url: Loopback origin.
        token: Shutdown token. SIGTERM and SIGINT POST it.

    Used when ``--no-window`` or ``SERATO_LIBRARY_NO_WINDOW=1`` is set.
    The web view is not imported.
    """

    def stop(signum: int, frame: object) -> None:
        threading.Thread(target=post_shutdown, args=(url, token), daemon=True).start()

    previous_term, previous_int = _install_stop_signals(stop)
    try:
        thread.join()
    finally:
        _restore_stop_signals(previous_term, previous_int)
        if thread.is_alive():
            post_shutdown(url, token)


def launch() -> None:
    """Start the window, or focus the one that is already open.

    Raises:
        SystemExit: If the running copy does not answer, or its window
            cannot be focused. A missing library still opens the page.

    Binds 127.0.0.1 on a free port. Closing the window shuts the server
    down. ``--no-window`` and ``SERATO_LIBRARY_NO_WINDOW=1`` keep the
    server up without a window until a shutdown request or a signal.
    """
    holder = acquire_instance()
    try:
        if holder.existing_url:
            focus_existing(holder.existing_url, holder.directory)
            return
        httpd = server.serve(port=0, require_library=True)
        host, port = httpd.server_address
        url = f"http://{host}:{port}"
        token = secrets.token_hex(32)
        focus = secrets.token_hex(32)
        httpd.shutdown_token = token
        httpd.focus_token = focus
        httpd.focus_window = lambda: app_log.logger.info(
            "Serato Library is already running without a window"
        )
        holder.publish_focus(focus)
        holder.publish(url)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            if window_skipped():
                run_until_stopped(httpd, thread, url, token)
            else:
                open_window(url, httpd, thread, token)
        finally:
            if thread.is_alive():
                post_shutdown(url, token)
                thread.join(timeout=3)
            if thread.is_alive():
                httpd.shutdown()
                thread.join(timeout=3)
            httpd.server_close()
            snapshots.stop_watch()
            telemetry.shutdown()
    finally:
        holder.release()


def main() -> None:
    """Run the smoke check, or open the library window.

    When ``SERATO_LIBRARY_SMOKE`` is set, :func:`smoke_main` serves health
    and returns after shutdown. Otherwise :func:`launch` runs.
    ``--no-window`` is honored only by :func:`launch`.

    Raises:
        SystemExit: If the smoke marker is unusable, or a page asset is
            missing. A missing library still opens the page.
    """
    marker = os.environ.get(SMOKE_ENV)
    if marker:
        smoke_main(Path(marker))
        return
    launch()


if __name__ == "__main__":
    main()
