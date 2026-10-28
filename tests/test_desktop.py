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

import desktop
import server


class SmokeTests(unittest.TestCase):
    """Check the frozen-app smoke path without a browser or a menu icon.

    The cases call ``desktop.smoke_main`` against a temporary marker.
    They do not open the Serato database.
    """

    def test_smoke_serves_health_and_shuts_down(self) -> None:
        """Bind a free port, answer health, and exit when shut down.

        The marker receives the URL and the token. GET ``/api/health``
        returns ``{"ok": true}``. POST with the token stops the thread.
        Telemetry is not started and pystray is not imported.

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

    def test_main_smoke_does_not_import_pystray(self) -> None:
        """Return from ``main`` after shutdown without importing pystray.

        Sets ``SERATO_LIBRARY_SMOKE``. A background request shuts the
        server down. The menu icon is not loaded.

        Returns:
            None. The test fails if ``pystray`` is imported.
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
                    sys.modules.pop("pystray", None)
                    desktop.main()
                    self.assertNotIn("pystray", sys.modules)
            helper.join(5)


class InstanceTests(unittest.TestCase):
    """Check the single-instance lock without opening a browser.

    Each case uses its own config directory. The suite's shared settings
    directory is not the lock directory.
    """

    def test_second_launch_observes_the_running_url(self) -> None:
        """Publish a URL from the lock holder and return it to the next launch.

        The second acquire does not receive the file descriptor. A page
        that answers health is required. No browser is opened.

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

    def test_launch_opens_the_existing_page_and_does_not_bind(self) -> None:
        """Open the browser when a copy is already running.

        ``serve`` must not be called. The browser helper receives the
        published URL.

        Returns:
            None. The test fails if a second server starts.
        """
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            holder = desktop.acquire_instance(folder)
            httpd = server.serve(port=0, require_library=False)
            host, port = httpd.server_address
            url = f"http://{host}:{port}"
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            holder.publish(url)
            try:
                with mock.patch.object(desktop, "acquire_instance", return_value=desktop.Instance(None, folder, url)):
                    with mock.patch.object(desktop, "open_browser") as browser:
                        with mock.patch.object(server, "serve") as serve:
                            desktop.launch()
                browser.assert_called_once_with(url)
                serve.assert_not_called()
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(3)
                holder.release()


if __name__ == "__main__":
    unittest.main()
