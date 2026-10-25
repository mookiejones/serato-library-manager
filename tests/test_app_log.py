"""Local log tests.

The cases write under a temporary log directory. They do not upload the
text and they do not launch a file manager.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import app_log


class LogTests(unittest.TestCase):
    """Check the rotating file and the copy/open helpers.

    ``setUp`` points the log directory at a temporary folder and removes
    any file handler left by another test.
    """

    def setUp(self) -> None:
        """Point logs at a fresh directory.

        Returns:
            None.
        """
        self._tmp = tempfile.TemporaryDirectory()
        self.logs = Path(self._tmp.name) / "logs"
        self.logs.mkdir()
        self._env = mock.patch.dict(os.environ, {app_log.app_config.LOG_ENV: str(self.logs)})
        self._env.start()
        app_log.configure()

    def tearDown(self) -> None:
        """Close the file handler and delete the temporary directory.

        Returns:
            None.
        """
        app_log.close_files()
        self._env.stop()
        self._tmp.cleanup()

    def test_configure_uses_a_rotating_file(self) -> None:
        """Write an info line with RotatingFileHandler.

        The handler names the app log file, caps the size, and keeps a
        few backups. The line is readable through the copy helper.

        Returns:
            None. The test fails if the handler type or the text is wrong.
        """
        handlers = [
            handler
            for handler in app_log.logger.handlers
            if getattr(handler, "name", "") == app_log._FILE_HANDLER
        ]
        self.assertEqual(len(handlers), 1)
        handler = handlers[0]
        self.assertIsInstance(handler, app_log.RotatingFileHandler)
        self.assertEqual(handler.maxBytes, app_log.MAX_BYTES)
        self.assertEqual(handler.backupCount, app_log.BACKUP_COUNT)
        app_log.logger.info("Library file: %s", self.logs / "master.sqlite")
        text, truncated = app_log.read_logs()
        self.assertIn("Logging started.", text)
        self.assertIn("master.sqlite", text)
        self.assertFalse(truncated)
        app_log.close_files()
        self.assertFalse(
            any(
                getattr(handler, "name", "") == app_log._FILE_HANDLER
                for handler in app_log.logger.handlers
            )
        )

    def test_symlink_is_not_copied(self) -> None:
        """Skip a log name that is a symlink.

        The symlink targets a file outside the log directory. Copy logs
        must not return that file's contents.

        Returns:
            None. The test fails if the outside text is included.
        """
        outside = Path(self._tmp.name) / "outside.txt"
        outside.write_text("secret-outside", encoding="utf-8")
        for handler in list(app_log.logger.handlers):
            if getattr(handler, "name", "") == app_log._FILE_HANDLER:
                handler.close()
                app_log.logger.removeHandler(handler)
        link = self.logs / app_log.LOG_NAME
        if link.exists():
            link.unlink()
        try:
            link.symlink_to(outside)
        except OSError:
            self.skipTest("symlinks are not available")
        text, _truncated = app_log.read_logs()
        self.assertNotIn("secret-outside", text)

    def test_linux_open_command(self) -> None:
        """Open the log directory with xdg-open on Linux.

        The command list is fixed. The directory is the log directory,
        not a path from the request.

        Returns:
            None. The test fails if the command is not xdg-open.
        """
        with mock.patch("app_log.sys_platform", return_value="linux"):
            command = app_log.open_directory_command(self.logs)
        self.assertEqual(command, ["xdg-open", str(self.logs)])

    def test_windows_open_uses_startfile(self) -> None:
        """Open the log directory with os.startfile on Windows.

        ``subprocess`` is not used. The test replaces ``os.startfile``.
        ``create=True`` covers Linux and macOS, where that function is
        absent. The test does not open a window.

        Returns:
            None. The test fails if startfile is not called with the log directory.
        """
        with mock.patch("app_log.sys_platform", return_value="win32"):
            with mock.patch("os.startfile", create=True) as startfile:
                app_log.open_logs_folder()
        startfile.assert_called_once_with(self.logs)

    def test_open_failure_has_no_path(self) -> None:
        """Raise a generic error when the file manager cannot start.

        The exception text must not include the log directory.

        Returns:
            None. The test fails if the path leaks into the message.
        """
        with mock.patch("app_log.sys_platform", return_value="linux"):
            with mock.patch("subprocess.run", side_effect=OSError("missing")):
                with self.assertRaises(OSError) as caught:
                    app_log.open_logs_folder()
        self.assertNotIn(str(self.logs), str(caught.exception))
        self.assertIn("could not be opened", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
