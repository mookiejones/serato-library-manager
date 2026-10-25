"""Settings for sharing anonymous telemetry.

The choice and the anonymous install id live in a JSON file under the
per-system config directory. A missing file means the choice has not been
made, and sharing stays off. ``False`` is a real choice and must not be
treated as missing.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

# Single source for the app version. Sentry's release, PostHog's
# app_version, and ``__version__`` all read this string.
APP_VERSION = "0.1.1"
__version__ = APP_VERSION
CONFIG_ENV = "SERATO_LIBRARY_CONFIG_DIR"
LOG_ENV = "SERATO_LIBRARY_LOG_DIR"
SETTINGS_NAME = "settings.json"
# Keys this file is allowed to store. Anything else is dropped on load.
SETTINGS_KEYS = ("install_id", "telemetry_consent")
_UUID = uuid.UUID
logger = logging.getLogger("serato.library.config")


@dataclass(frozen=True)
class Settings:
    """The sharing choice and the anonymous install id.

    Attributes:
        install_id: Random UUID for this install, or None until one is saved.
        telemetry_consent: True, False, or None when the person has not chosen.
    """

    install_id: str | None
    telemetry_consent: bool | None

    def as_json(self) -> dict[str, object]:
        """Return the full settings object for the file.

        Returns:
            Both stored keys. Consent is a boolean and the id is present.

        Raises:
            ValueError: If either field is still unset. A partial file would
                stick on the next load and hide the prompt.
        """
        if self.install_id is None or not isinstance(self.telemetry_consent, bool):
            raise ValueError("Refusing to write a partial settings file.")
        return {
            "install_id": self.install_id,
            "telemetry_consent": self.telemetry_consent,
        }


def _env_path(name: str) -> Path | None:
    """Return an absolute directory from an environment variable.

    Args:
        name: ``SERATO_LIBRARY_CONFIG_DIR`` or ``SERATO_LIBRARY_LOG_DIR``.

    Returns:
        The path when it is absolute. None when the variable is missing,
        blank, or relative. A relative value is ignored so a test override
        cannot write into the working directory by accident.
    """
    raw = os.environ.get(name, "")
    if not isinstance(raw, str) or not raw.strip():
        return None
    path = Path(raw.strip())
    if not path.is_absolute():
        logger.warning("%s must be an absolute path — ignored", name)
        return None
    return path


def default_config_dir() -> Path:
    """Return the settings directory for this operating system.

    Returns:
        Application Support on macOS, ``%APPDATA%\\Serato Library`` on
        Windows, and ``$XDG_CONFIG_HOME/serato-library`` elsewhere.
    """
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base / "Serato Library"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Serato Library"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "serato-library"


def default_log_dir() -> Path:
    """Return the log directory for this operating system.

    Returns:
        ``~/Library/Logs/Serato Library`` on macOS,
        ``%LOCALAPPDATA%\\Serato Library\\Logs`` on Windows, and
        ``$XDG_STATE_HOME/serato-library/logs`` elsewhere.
    """
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        base = Path(local) if local else Path.home() / "AppData" / "Local"
        return base / "Serato Library" / "Logs"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / "Serato Library"
    xdg = os.environ.get("XDG_STATE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "state"
    return base / "serato-library" / "logs"


def config_dir() -> Path:
    """Return the directory that holds ``settings.json``.

    Returns:
        ``SERATO_LIBRARY_CONFIG_DIR`` when that variable is an absolute
        path, otherwise :func:`default_config_dir`.
    """
    return _env_path(CONFIG_ENV) or default_config_dir()


def log_dir() -> Path:
    """Return the directory that holds the rotating log.

    Returns:
        ``SERATO_LIBRARY_LOG_DIR`` when that variable is an absolute path,
        otherwise :func:`default_log_dir`.
    """
    return _env_path(LOG_ENV) or default_log_dir()


def settings_path() -> Path:
    """Return the settings file path.

    Returns:
        ``settings.json`` inside :func:`config_dir`. The file is not created.
    """
    return config_dir() / SETTINGS_NAME


def _valid_install_id(value: object) -> str | None:
    """Return a canonical UUID string, or None.

    Args:
        value: Candidate install id from the settings file.

    Returns:
        The lowercase hyphenated form when ``value`` is a UUID string.
        None for any other type, including booleans and integers.
    """
    if not isinstance(value, str):
        return None
    try:
        parsed = _UUID(value)
    except ValueError:
        return None
    return str(parsed)


def _parse(payload: object) -> Settings:
    """Validate a decoded settings object.

    Args:
        payload: JSON value read from the settings file.

    Returns:
        The known fields. Unknown keys and wrong types are dropped. A
        missing consent stays None, which means sharing is off and the
        prompt should be shown.
    """
    if not isinstance(payload, dict):
        logger.warning("Config file must be a mapping — ignored")
        return Settings(install_id=None, telemetry_consent=None)
    for key in payload:
        if key not in SETTINGS_KEYS:
            logger.warning("Unknown config key %r — ignored", key)
    install_id = _valid_install_id(payload.get("install_id"))
    if "install_id" in payload and install_id is None:
        logger.warning("Config key 'install_id' has wrong type — ignored")
    if "telemetry_consent" not in payload:
        consent: bool | None = None
    else:
        raw_consent = payload.get("telemetry_consent")
        if isinstance(raw_consent, bool):
            consent = raw_consent
        elif raw_consent is None:
            consent = None
        else:
            logger.warning("Config key 'telemetry_consent' has wrong type — ignored")
            consent = None
    return Settings(install_id=install_id, telemetry_consent=consent)


def load_settings() -> Settings:
    """Load the sharing choice.

    Returns:
        The saved settings. A missing file is an unchosen consent and no
        install id. Nothing is written.

    The file is left in place when it cannot be parsed, so a later save
    can move it aside instead of deleting it unread.
    """
    path = settings_path()
    if not path.is_file():
        return Settings(install_id=None, telemetry_consent=None)
    try:
        text = path.read_text(encoding="utf-8")
        payload: object = json.loads(text)
    except (OSError, UnicodeError, json.JSONDecodeError):
        logger.warning("Config file %s could not be read — ignored", path.name)
        return Settings(install_id=None, telemetry_consent=None)
    return _parse(payload)


def _retire_unreadable(path: Path) -> None:
    """Rename a settings file that is not JSON before a new one replaces it.

    Args:
        path: The current settings file. A readable JSON object is left
            alone. A file that cannot be parsed is renamed beside it so
            the bytes are not thrown away.
    """
    if not path.is_file():
        return
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        retired = path.with_name(path.name + ".unreadable")
        path.replace(retired)
        logger.warning("Unreadable config file was kept as %s", retired.name)
        return
    if not isinstance(payload, dict):
        retired = path.with_name(path.name + ".unreadable")
        path.replace(retired)
        logger.warning("Unreadable config file was kept as %s", retired.name)


def save_settings(settings: Settings) -> None:
    """Atomically replace the settings file with a complete object.

    Args:
        settings: Choice and install id. Both fields must be set.

    Raises:
        ValueError: If the object is missing the id or the boolean choice.
        OSError: If the directory or the file cannot be written.

    The write is a temp file in the same directory followed by replace, so
    a crash cannot leave a half-written JSON object as the settings file.
    """
    body = json.dumps(settings.as_json(), indent=2, sort_keys=True) + "\n"
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    _retire_unreadable(path)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(body, encoding="utf-8")
    temporary.replace(path)


def set_telemetry_consent(value: bool) -> Settings:
    """Store the sharing choice and keep or create the install id.

    Args:
        value: True to allow anonymous reports. False to send nothing.

    Returns:
        The settings that were written.

    Raises:
        ValueError: If ``value`` is not a boolean. Integers are rejected
            because ``bool`` is a subclass of ``int``.
        OSError: If the settings file cannot be written.
    """
    if not isinstance(value, bool):
        raise ValueError("telemetry_consent must be a boolean.")
    current = load_settings()
    install_id = current.install_id or str(uuid.uuid4())
    updated = Settings(install_id=install_id, telemetry_consent=value)
    save_settings(updated)
    return updated
