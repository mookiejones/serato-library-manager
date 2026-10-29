"""Smoke check and single-instance behavior for the desktop app."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

import app_config
import desktop
import server


class SmokeTests(unittest.TestCase):
    """Check the frozen-app smoke path without a window.

    The cases call ``desktop.smoke_main`` against a temporary marker.
    They do not open the Serato database or the web view.
    """

    def test_smoke_serves_health_and_shuts_down(self) -> None:
        """Bind a free port, answer health, and exit when shut down.

        The marker receives the URL and the token. GET ``/api/health``
        returns ``{"ok": true}``. POST with the token stops the thread.
        Telemetry is not started and the web view is not imported.

        Returns:
            None. The test fails if the server stays up or health differs.
        """
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "marker.txt"
            thread = threading.Thread(target=desktop.smoke_main, args=(marker,), daemon=True)
            thread.start()
            deadline_marker = marker
            for _ in range(100):
                if deadline_marker.is_file() and desktop.parse_smoke_marker(
                    deadline_marker.read_text(encoding="utf-8")
                ):
                    break
                thread.join(0.05)
            parsed = desktop.parse_smoke_marker(marker.read_text(encoding="utf-8"))
            self.assertIsNotNone(parsed)
            assert parsed is not None
            url, token = parsed
            with urllib.request.urlopen(url + "/api/health", timeout=5) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(json.loads(response.read().decode("utf-8")), {"ok": True})
            request = urllib.request.Request(
                url + "/api/shutdown",
                data=b"{}",
                headers={server.SHUTDOWN_HEADER: token},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                self.assertEqual(response.status, 200)
            thread.join(5)
            self.assertFalse(thread.is_alive())

    def test_smoke_check_rejects_a_relative_path(self) -> None:
        """Refuse a relative smoke-marker path.

        A relative path could write the marker inside the repository. The
        function raises ``SystemExit`` and does not create a file.

        Returns:
            None. The test fails if ``SystemExit`` is not raised.
        """
        with self.assertRaises(SystemExit):
            desktop.smoke_main(Path("marker.txt"))

    def test_main_smoke_does_not_import_the_web_view(self) -> None:
        """Return from ``main`` after shutdown without importing pywebview.

        Sets ``SERATO_LIBRARY_SMOKE``. A background request shuts the
        server down. The window is not created.

        Returns:
            None. The test fails if ``webview`` is imported.
        """
        import sys

        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "marker.txt"

            def shutdown_when_ready() -> None:
                for _ in range(100):
                    if marker.is_file():
                        parsed = desktop.parse_smoke_marker(marker.read_text(encoding="utf-8"))
                        if parsed:
                            url, token = parsed
                            request = urllib.request.Request(
                                url + "/api/shutdown",
                                data=b"{}",
                                headers={server.SHUTDOWN_HEADER: token},
                                method="POST",
                            )
                            urllib.request.urlopen(request, timeout=5).close()
                            return
                    threading.Event().wait(0.05)
                raise AssertionError("smoke marker was not written")

            helper = threading.Thread(target=shutdown_when_ready, daemon=True)
            helper.start()
            with mock.patch.dict(os.environ, {desktop.SMOKE_ENV: str(marker)}):
                with mock.patch.dict(sys.modules):
                    sys.modules.pop("webview", None)
                    sys.modules.pop("pystray", None)
                    desktop.main()
                    self.assertNotIn("webview", sys.modules)
                    self.assertNotIn("pystray", sys.modules)
            helper.join(5)


class InstanceTests(unittest.TestCase):
    """Check the single-instance lock without opening a window.

    Each case uses its own config directory. The suite's shared settings
    directory is not the lock directory.
    """

    def test_second_launch_observes_the_running_url(self) -> None:
        """Publish a URL from the lock holder and return it to the next launch.

        The second acquire does not receive the file descriptor. A page
        that answers health is required. No window is opened.

        Returns:
            None. The test fails if the second launch does not see the URL.
        """
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            holder = desktop.acquire_instance(folder)
            self.assertIsNone(holder.existing_url)
            httpd = server.serve(port=0, require_library=False)
            host, port = httpd.server_address
            url = f"http://{host}:{port}"
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                holder.publish(url)
                other = desktop.acquire_instance(folder)
                self.assertEqual(other.existing_url, url)
                other.release()
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(3)
                holder.release()

    def test_launch_focuses_the_existing_window_and_does_not_bind(self) -> None:
        """Focus the running window when a copy is already running.

        ``serve`` must not be called. The focus route receives the token
        from ``instance.focus`` and runs the window callback.

        Returns:
            None. The test fails if a second server starts or the window
            callback is skipped.
        """
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            holder = desktop.acquire_instance(folder)
            httpd = server.serve(port=0, require_library=False)
            host, port = httpd.server_address
            url = f"http://{host}:{port}"
            focused: list[str] = []
            httpd.focus_token = "focus-token"
            httpd.focus_window = lambda: focused.append("focused")
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            holder.publish(url)
            holder.publish_focus("focus-token")
            try:
                with mock.patch.object(desktop, "acquire_instance", return_value=desktop.Instance(None, folder, url)):
                    with mock.patch.object(server, "serve") as serve:
                        desktop.launch()
                self.assertEqual(focused, ["focused"])
                serve.assert_not_called()
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(3)
                holder.release()

    def test_stale_port_file_is_cleared_when_the_lock_is_free(self) -> None:
        """Start a new instance after a crash left ``instance.port`` behind.

        The lock file exists and is not held. The port file names a page
        that does not answer. The next launch must take the lock, drop
        that URL, and not wait for it.

        Returns:
            None. The test fails if the stale URL is treated as a running
            copy or is left in place.
        """
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / desktop.LOCK_NAME).write_bytes(b"\0")
            (folder / desktop.PORT_NAME).write_text("http://127.0.0.1:9\n", encoding="utf-8")
            (folder / desktop.FOCUS_NAME).write_text("stale-focus-token\n", encoding="utf-8")
            holder = desktop.acquire_instance(folder)
            try:
                self.assertIsNone(holder.existing_url)
                self.assertFalse((folder / desktop.PORT_NAME).exists())
                self.assertFalse((folder / desktop.FOCUS_NAME).exists())
            finally:
                holder.release()


class WindowChoiceTests(unittest.TestCase):
    """Check the web-view choice and the headless flag.

    These cases do not open a window or import pywebview.
    """

    def test_choose_gui_uses_the_system_web_view(self) -> None:
        """Pick WebView2, WKWebView, or WebKit, and refuse Chromium.

        Windows without the runtime stops. Linux with only Qt WebEngine
        stops. GTK wins when both GTK and Qt WebKit are present.

        Returns:
            None. The test fails if CEF or Qt WebEngine is selected.
        """
        self.assertEqual(
            desktop.choose_gui("win32", webview2=True, gtk=False, qtwebkit=False, qtwebengine=False),
            "edgechromium",
        )
        with self.assertRaises(SystemExit) as missing:
            desktop.choose_gui("win32", webview2=False, gtk=False, qtwebkit=False, qtwebengine=False)
        self.assertIn("WebView2", str(missing.exception))
        self.assertEqual(
            desktop.choose_gui("darwin", webview2=False, gtk=False, qtwebkit=False, qtwebengine=True),
            "cocoa",
        )
        self.assertEqual(
            desktop.choose_gui("linux", webview2=False, gtk=True, qtwebkit=True, qtwebengine=True),
            "gtk",
        )
        self.assertEqual(
            desktop.choose_gui("linux", webview2=False, gtk=False, qtwebkit=True, qtwebengine=False),
            "qt",
        )
        with self.assertRaises(SystemExit) as chromium:
            desktop.choose_gui("linux", webview2=False, gtk=False, qtwebkit=True, qtwebengine=True)
        self.assertIn("Chromium", str(chromium.exception))
        with self.assertRaises(SystemExit):
            desktop.choose_gui("linux", webview2=False, gtk=False, qtwebkit=False, qtwebengine=False)

    def test_webview2_version_rejects_a_bool_and_an_old_build(self) -> None:
        """Keep the WebView2 minimum at 86.0.622.0.

        A bool is not a version. A build just below the minimum is
        refused. A current Edge build is accepted.

        Returns:
            None. The test fails if ``True`` is treated as a build.
        """
        self.assertFalse(desktop.webview2_version_ok(True))
        self.assertFalse(desktop.webview2_version_ok(86))
        self.assertFalse(desktop.webview2_version_ok("86.0.621.9"))
        self.assertTrue(desktop.webview2_version_ok("86.0.622.0"))
        self.assertTrue(desktop.webview2_version_ok("120.0.2210.91"))

    def test_window_background_matches_the_page(self) -> None:
        """Use the page background for the native window frame.

        Reads ``static/tokens.css``. The window color is the walnut
        ``--color-bg`` token, so the frame does not flash a different color.

        Returns:
            None. The test fails if the token and the window color diverge.
        """
        sheet = Path(__file__).resolve().parents[1].joinpath("static", "tokens.css").read_text(encoding="utf-8")
        self.assertIn("--color-bg: #231910", sheet)
        self.assertEqual(desktop.WINDOW_BACKGROUND, "#231910")

    def test_no_window_flag_is_exact(self) -> None:
        """Skip the window only for the exact flag or the value ``1``.

        ``0`` and ``true`` leave the window on. A longer flag does not
        count as ``--no-window``.

        Returns:
            None. The test fails if a nearby value skips the window.
        """
        self.assertTrue(desktop.window_skipped(["--no-window"]))
        self.assertFalse(desktop.window_skipped(["--no-windowed"]))
        self.assertFalse(desktop.window_skipped([]))
        with mock.patch.dict(os.environ, {desktop.NO_WINDOW_ENV: "1"}):
            self.assertTrue(desktop.window_skipped([]))
        with mock.patch.dict(os.environ, {desktop.NO_WINDOW_ENV: "0"}):
            self.assertFalse(desktop.window_skipped([]))
        with mock.patch.dict(os.environ, {desktop.NO_WINDOW_ENV: "true"}):
            self.assertFalse(desktop.window_skipped([]))

    def test_saved_frame_stays_on_a_side_monitor_and_centers_when_the_title_bar_is_hidden(self) -> None:
        """Keep a negative origin when the title bar is on that monitor.

        A monitor left of the primary screen has a negative ``x``. One
        above it has a negative ``y``. The saved position is restored
        when at least 100 by 40 pixels of the title bar are on some
        screen. A sliver, or a window whose body overlaps but whose
        title bar does not, is centered on the screen that contains
        the origin.

        Returns:
            None. The test fails if a side monitor is treated as off-screen
            or a hidden title bar is left in place.
        """
        primary = mock.Mock(x=0, y=0, width=1920, height=1080)
        left = mock.Mock(x=-1920, y=0, width=1920, height=1080)
        above = mock.Mock(x=0, y=-1080, width=1920, height=1080)
        screens = [left, above, primary]
        self.assertTrue(desktop.title_bar_is_visible(-1600, 80, 800, 600, screens))
        self.assertTrue(desktop.title_bar_is_visible(120, -400, 800, 600, screens))
        # Exactly 100 by 40 pixels of the title bar on the left monitor.
        self.assertTrue(desktop.title_bar_is_visible(-2620, 80, 800, 600, screens))
        self.assertFalse(desktop.title_bar_is_visible(-2621, 80, 800, 600, screens))
        # The body crosses the primary screen. The title bar is above it.
        self.assertFalse(desktop.title_bar_is_visible(100, -50, 800, 600, [primary]))
        self.assertEqual(desktop.centered_on_primary(800, 600, screens), (560, 240))
        self.assertEqual(desktop.centered_on_primary(800, 600, [left, primary]), (560, 240))
        self.assertIsNone(desktop.centered_on_primary(800, 600, []))
        self.assertFalse(
            desktop.title_bar_is_visible(0, 0, 800, 600, [mock.Mock(x=True, y=0, width=1920, height=1080)])
        )


class GeometryTests(unittest.TestCase):
    """Check that a move and a resize land in settings.json.

    Each case uses its own config directory. The web view is not opened.
    """

    def setUp(self) -> None:
        """Point settings at an empty directory and clear the frame buffer.

        Returns:
            None.
        """
        self._tmp = tempfile.TemporaryDirectory()
        self.config = Path(self._tmp.name)
        self._env = mock.patch.dict(os.environ, {app_config.CONFIG_ENV: str(self.config)})
        self._env.start()
        desktop.reset_window_geometry()

    def tearDown(self) -> None:
        """Cancel a pending geometry write and remove the directory.

        Returns:
            None.
        """
        desktop.reset_window_geometry()
        self._env.stop()
        self._tmp.cleanup()

    def test_move_and_resize_are_written_together(self) -> None:
        """Store x, y, width, and height after both events.

        A resize alone does not create the file. ``0`` is a real origin.
        A bool width is ignored and does not replace a good size.

        Returns:
            None. The test fails if a partial frame is written.
        """
        desktop.note_window_resized(1120.2, 720.4)
        desktop.flush_window_geometry()
        self.assertFalse((self.config / "settings.json").exists())
        desktop.note_window_moved(0, 15)
        desktop.flush_window_geometry()
        loaded = app_config.load_settings()
        self.assertIsNotNone(loaded.window)
        assert loaded.window is not None
        self.assertEqual(loaded.window.x, 0)
        self.assertEqual(loaded.window.y, 15)
        self.assertEqual(loaded.window.width, 1120)
        self.assertEqual(loaded.window.height, 720)
        desktop.note_window_resized(True, 800)
        desktop.flush_window_geometry()
        again = app_config.load_settings()
        assert again.window is not None
        self.assertEqual(again.window.width, 1120)

    def test_closing_the_window_posts_the_shutdown_token(self) -> None:
        """Stop the server through ``/api/shutdown`` when the window closes.

        A stand-in web view records the title, the URL, and the GUI name,
        then emits resize, move, and close. The real server must stop.
        pywebview itself is not started.

        Returns:
            None. The test fails if the server stays up or the title differs.
        """
        import inspect
        import sys
        import types

        class FakeEvent:
            """Record handlers and call them the way pywebview's Event does."""

            def __init__(self) -> None:
                self.handlers: list[object] = []

            def __iadd__(self, handler: object) -> "FakeEvent":
                self.handlers.append(handler)
                return self

            def set(self, *args: object) -> None:
                for func in list(self.handlers):
                    params = list(inspect.signature(func).parameters)  # type: ignore[arg-type]
                    if len(params) == 0:
                        func()  # type: ignore[operator]
                    else:
                        func(*args)  # type: ignore[operator]

        class FakeWindow:
            """Hold the events and the frame the close path reads."""

            def __init__(self) -> None:
                self.events = types.SimpleNamespace(
                    resized=FakeEvent(),
                    moved=FakeEvent(),
                    shown=FakeEvent(),
                    closed=FakeEvent(),
                )
                self.x = 12
                self.y = 24
                self.width = 1100
                self.height = 700

            def restore(self) -> None:
                self.restored = True

            def show(self) -> None:
                self.shown_called = True

        fake = types.ModuleType("webview")
        window = FakeWindow()

        def create_window(title: str, url: str, **kwargs: object) -> FakeWindow:
            fake.created = {"title": title, "url": url, **kwargs}
            return window

        def start(**kwargs: object) -> None:
            fake.start_kwargs = kwargs
            window.events.resized.set(1100, 700)
            window.events.moved.set(12, 24)
            window.events.shown.set()
            window.events.closed.set()

        fake.create_window = create_window  # type: ignore[attr-defined]
        fake.start = start  # type: ignore[attr-defined]
        fake.screens = []  # type: ignore[attr-defined]
        httpd = server.serve(port=0, require_library=False)
        token = "shutdown-token"
        httpd.shutdown_token = token
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        host, port = httpd.server_address
        url = f"http://{host}:{port}"
        try:
            with mock.patch.object(desktop, "detect_gui", return_value="gtk"):
                with mock.patch.dict(sys.modules, {"webview": fake}):
                    desktop.open_window(url, httpd, thread, token)
            thread.join(5)
            self.assertFalse(thread.is_alive())
            self.assertEqual(fake.created["title"], "Serato Library")  # type: ignore[attr-defined]
            self.assertEqual(fake.created["url"], url)  # type: ignore[attr-defined]
            self.assertIs(fake.created["text_select"], True)  # type: ignore[attr-defined]
            self.assertEqual(fake.created["background_color"], desktop.WINDOW_BACKGROUND)  # type: ignore[attr-defined]
            self.assertEqual(fake.start_kwargs["gui"], "gtk")  # type: ignore[attr-defined]
            self.assertNotIn(fake.start_kwargs["gui"], ("cef", "mshtml"))  # type: ignore[attr-defined]
            loaded = app_config.load_settings()
            self.assertEqual(loaded.window, app_config.WindowGeometry(12, 24, 1100, 700))
        finally:
            if thread.is_alive():
                httpd.shutdown()
                thread.join(3)
            httpd.server_close()
            desktop.reset_window_geometry()

    def test_close_handler_posts_shutdown(self) -> None:
        """Stop the server when ``_close_window`` runs, with no window toolkit.

        Calls the close handler directly. The server is shut down only
        by the shutdown token that handler posts. A handler that skips
        that post leaves the thread running.

        Returns:
            None. The test fails if the server is still accepting after
            the handler returns.
        """
        httpd = server.serve(port=0, require_library=False)
        token = "direct-close-token"
        httpd.shutdown_token = token
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        host, port = httpd.server_address
        url = f"http://{host}:{port}"
        try:
            desktop._close_window(url, token)
            thread.join(5)
            self.assertFalse(thread.is_alive())
        finally:
            if thread.is_alive():
                httpd.shutdown()
                thread.join(3)
            httpd.server_close()


class HeadlessLaunchTests(unittest.TestCase):
    """Check a normal launch that skips the window.

    The library file is an empty placeholder. Snapshot and telemetry
    startup are patched so the case does not read a real Serato library.
    """

    def test_no_window_serves_until_shutdown_without_webview(self) -> None:
        """Bind a free port and stop when the shutdown token is posted.

        ``SERATO_LIBRARY_NO_WINDOW=1`` is set. ``webview`` must stay
        unimported. Health answers before the shutdown request.

        Returns:
            None. The test fails if a window module is imported or the
            server stays up.
        """
        import sys

        import files
        import snapshots
        import telemetry

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            config = folder / "config"
            config.mkdir()
            master = folder / "master.sqlite"
            master.write_bytes(b"")
            marker = folder / "ready"

            def shutdown_when_ready() -> None:
                for _ in range(100):
                    port_file = config / desktop.PORT_NAME
                    if port_file.is_file():
                        url = port_file.read_text(encoding="utf-8").strip()
                        if desktop._health_ok(url):
                            self.assertIsNotNone(desktop.read_focus_token(config))
                            token = state["httpd"].shutdown_token
                            self.assertIsInstance(token, str)
                            assert isinstance(token, str)
                            request = urllib.request.Request(
                                url + "/api/shutdown",
                                data=b"{}",
                                headers={server.SHUTDOWN_HEADER: token},
                                method="POST",
                            )
                            urllib.request.urlopen(request, timeout=5).close()
                            marker.write_text("done", encoding="utf-8")
                            return
                    threading.Event().wait(0.05)
                raise AssertionError("the headless server did not answer")

            state: dict[str, server.ThreadingHTTPServer] = {}

            def serve_and_remember(*args: object, **kwargs: object) -> server.ThreadingHTTPServer:
                httpd = original_serve(*args, **kwargs)  # type: ignore[arg-type]
                state["httpd"] = httpd
                return httpd

            original_serve = server.serve
            helper = threading.Thread(target=shutdown_when_ready, daemon=True)
            helper.start()
            env = {
                app_config.CONFIG_ENV: str(config),
                desktop.NO_WINDOW_ENV: "1",
            }
            with mock.patch.dict(os.environ, env):
                with mock.patch.dict(sys.modules):
                    sys.modules.pop("webview", None)
                    with mock.patch.object(server, "db_path", return_value=master):
                        with mock.patch.object(files, "recover_interrupted", return_value="clear"):
                            with mock.patch.object(snapshots, "start_watch"):
                                with mock.patch.object(snapshots, "stop_watch"):
                                    with mock.patch.object(snapshots, "current_store") as store:
                                        store.return_value.check_version.return_value = None
                                        with mock.patch.object(telemetry, "activate"):
                                            with mock.patch.object(telemetry, "note_app_opened"):
                                                with mock.patch.object(telemetry, "shutdown"):
                                                    with mock.patch.object(server, "serve", side_effect=serve_and_remember):
                                                        desktop.launch()
                    self.assertNotIn("webview", sys.modules)
            helper.join(5)
            self.assertTrue(marker.is_file())


if __name__ == "__main__":
    unittest.main()
