"""Rotating logs for the local Serato library app.

Log files stay on this computer. They can name the database path because
the person running the app uses them to debug. They are not uploaded.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import app_config

LOG_NAME = "serato-library.log"
LOGGER_NAME = "serato"
MAX_BYTES = 1_048_576
BACKUP_COUNT = 3
COPY_LIMIT = 200_000
_FILE_HANDLER = "serato-file"
_STREAM_HANDLER = "serato-stream"
logger = logging.getLogger(LOGGER_NAME)


def configure() -> Path:
    """Attach a rotating file log and a warning stream, once.

    Returns:
        The log directory. It is created when it does not exist.

    Raises:
        OSError: If the directory cannot be created. A later failure to
            open the file is logged to stderr and the process keeps running
            without a file handler.

    The format omits ``pathname`` so a log line does not repeat the install
    location of the Python file on every record. The library database path
    is written once, by the caller, when that is useful locally.
    """
    directory = app_config.log_dir()
    directory.mkdir(parents=True, exist_ok=True)
    logger.setLevel(logging.INFO)
    # Keep these records out of the root logger. Sentry's logging
    # integration, if it were enabled, listens there.
    logger.propagate = False
    if not any(getattr(handler, "name", "") == _STREAM_HANDLER for handler in logger.handlers):
        stream = logging.StreamHandler(sys.stderr)
        stream.name = _STREAM_HANDLER
        stream.setLevel(logging.WARNING)
        stream.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
        logger.addHandler(stream)
    target = (directory / LOG_NAME).resolve()
    for handler in list(logger.handlers):
        if getattr(handler, "name", "") != _FILE_HANDLER:
            continue
        current = Path(getattr(handler, "baseFilename", "")).resolve()
        if current == target:
            return directory
        logger.removeHandler(handler)
        handler.close()
    try:
        file_handler = RotatingFileHandler(
            directory / LOG_NAME,
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
            delay=True,
        )
    except OSError:
        logger.warning("The log file could not be opened.")
        return directory
    file_handler.name = _FILE_HANDLER
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    logger.addHandler(file_handler)
    logger.info("Logging started.")
    return directory


def close_files() -> None:
    """Close the rotating log so its directory can be removed.

    Windows will not delete a file that this process still has open.
    The next call to :func:`configure` opens the file again. The stderr
    handler stays in place.
    """
    for handler in list(logger.handlers):
        if getattr(handler, "name", "") != _FILE_HANDLER:
            continue
        logger.removeHandler(handler)
        handler.close()


def _log_files(directory: Path) -> list[Path]:
    """Return the rotating log files that stay inside ``directory``.

    Args:
        directory: Log directory from :func:`app_config.log_dir`.

    Returns:
        Oldest rotated file first, then the current file. Symlinks and
        paths that resolve outside the directory are skipped.
    """
    root = directory.resolve()
    names = [f"{LOG_NAME}.{index}" for index in range(BACKUP_COUNT, 0, -1)]
    names.append(LOG_NAME)
    found: list[Path] = []
    for name in names:
        path = (root / name).resolve()
        if (root / name).is_symlink():
            continue
        if not path.is_file() or not path.is_relative_to(root):
            continue
        found.append(path)
    return found


def read_logs() -> tuple[str, bool]:
    """Read the local log text for the Copy logs action.

    Returns:
        The combined text and whether older bytes were dropped. The text
        is capped at ``COPY_LIMIT`` characters, keeping the newest end.
        An empty string means nothing has been written yet.
    """
    directory = app_config.log_dir()
    if not directory.is_dir():
        return "", False
    chunks: list[str] = []
    for path in _log_files(directory):
        try:
            chunks.append(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            logger.warning("A log file could not be read.")
    text = "".join(chunks)
    if len(text) <= COPY_LIMIT:
        return text, False
    return text[-COPY_LIMIT:], True


def open_directory_command(directory: Path) -> list[str] | None:
    """Build the command that opens a directory in the file manager.

    Args:
        directory: Absolute directory to show.

    Returns:
        Argv for Finder or ``xdg-open``. None on Windows, where
        ``os.startfile`` is used instead of a command list.
    """
    if sys_platform() == "win32":
        return None
    if sys_platform() == "darwin":
        return ["open", str(directory)]
    return ["xdg-open", str(directory)]


def sys_platform() -> str:
    """Return the platform name used to pick a file manager.

    Returns:
        ``sys.platform``. Wrapped so tests can replace this function
        without patching the whole ``sys`` module.
    """
    return sys.platform


def open_logs_folder() -> None:
    """Open the log directory in the host file manager.

    Raises:
        OSError: If the directory cannot be created or the file manager
            cannot be started.
        RuntimeError: If the file manager command exits non-zero.

    The directory is the one :func:`configure` uses. The request does not
    accept a path, so this cannot open an arbitrary folder.
    """
    import os
    import subprocess

    directory = configure()
    command = open_directory_command(directory)
    if command is None:
        os.startfile(directory)  # type: ignore[attr-defined]
        return
    try:
        completed = subprocess.run(command, check=False)
    except OSError as exc:
        raise OSError("The logs folder could not be opened.") from exc
    if completed.returncode != 0:
        raise RuntimeError("The logs folder could not be opened.")
