"""Settings for sharing and for the Rekordbox export bar.

The sharing choice, the anonymous install id, and the export bar live in
one JSON file under the per-system config directory. A missing file means
the sharing choice has not been made, and sharing stays off. ``False`` is
a real choice and must not be treated as missing. The export bar has its
own defaults and can be saved before that choice.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path

# Single source for the app version. Sentry's release, PostHog's
# app_version, and ``__version__`` all read this string.
APP_VERSION = "1.1.0"
__version__ = APP_VERSION
CONFIG_ENV = "SERATO_LIBRARY_CONFIG_DIR"
LOG_ENV = "SERATO_LIBRARY_LOG_DIR"
SETTINGS_NAME = "settings.json"
# Keys this file is allowed to store. Anything else is dropped on load.
SETTINGS_KEYS = ("install_id", "telemetry_consent", "window", "wizard_complete", "rekordbox")
REKORDBOX_KEYS = ("hot_loops", "memory_cues", "key_notation")
# The same three words rekordbox.py accepts for --key.
REKORDBOX_KEY_NOTATIONS = ("asis", "camelot", "classical")
WINDOW_FIELDS = ("x", "y", "width", "height")
# The desktop window refuses a smaller frame. Origins may be negative
# when a monitor sits left of or above the primary screen.
WINDOW_MIN_WIDTH = 640
WINDOW_MIN_HEIGHT = 480
WINDOW_MAX_EDGE = 8192
WINDOW_MIN_ORIGIN = -8192
WINDOW_MAX_ORIGIN = 32768
_WINDOW_LIMITS = (
    ("x", WINDOW_MIN_ORIGIN, WINDOW_MAX_ORIGIN),
    ("y", WINDOW_MIN_ORIGIN, WINDOW_MAX_ORIGIN),
    ("width", WINDOW_MIN_WIDTH, WINDOW_MAX_EDGE),
    ("height", WINDOW_MIN_HEIGHT, WINDOW_MAX_EDGE),
)
_UUID = uuid.UUID
_settings_lock = threading.RLock()
logger = logging.getLogger("serato.library.config")


@dataclass(frozen=True)
class RekordboxSettings:
    """The Rekordbox export bar.

    Attributes:
        hot_loops: True puts a saved loop on its own free hot-cue pad.
        memory_cues: True also writes each hot cue as a memory cue.
        key_notation: ``asis``, ``camelot``, or ``classical``.
    """

    hot_loops: bool
    memory_cues: bool
    key_notation: str

    def as_json(self) -> dict[str, object]:
        """Return the three export fields.

        Returns:
            ``hot_loops``, ``memory_cues``, and ``key_notation``. ``False``
            is written as false.
        """
        return {
            "hot_loops": self.hot_loops,
            "memory_cues": self.memory_cues,
            "key_notation": self.key_notation,
        }


def default_rekordbox() -> RekordboxSettings:
    """Return the export bar the page shows before a choice is saved.

    Returns:
        Hot loops off, memory cues on, and the key left as stored.
    """
    return RekordboxSettings(hot_loops=False, memory_cues=True, key_notation="asis")


@dataclass(frozen=True)
class WindowGeometry:
    """Pixel size and position of the desktop window.

    Attributes:
        x: Left edge, in pixels. ``0`` is the primary screen's left edge.
            A negative value is a monitor to the left.
        y: Top edge, in pixels. ``0`` is the primary screen's top edge.
        width: Window width, in pixels.
        height: Window height, in pixels.
    """

    x: int
    y: int
    width: int
    height: int

    def __post_init__(self) -> None:
        """Reject a bool or a coordinate outside the stored range.

        Raises:
            ValueError: If a field is not an ``int``, or it falls outside
                the range the desktop window can open.
        """
        for name, low, high in _WINDOW_LIMITS:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"window.{name} must be an integer.")
            if value < low or value > high:
                raise ValueError(f"window.{name} is outside {low}..{high}.")


@dataclass(frozen=True)
class Settings:
    """The sharing choice, the install id, the window frame, setup, and the export bar.

    Attributes:
        install_id: Random UUID for this install, or None until one is saved.
        telemetry_consent: True, False, or None when the person has not chosen.
        rekordbox: Export bar. Defaults apply when the file has no section.
        window: Last saved frame, or None before the window has been placed.
        wizard_complete: True after setup finishes. False is unfinished,
            including a file written before this key existed.
    """

    install_id: str | None
    telemetry_consent: bool | None
    rekordbox: RekordboxSettings = field(default_factory=default_rekordbox)
    window: WindowGeometry | None = None
    wizard_complete: bool = False

    def as_json(self) -> dict[str, object]:
        """Return the settings object for the file.

        Returns:
            The completed telemetry pair when both fields are set, the
            setup flag with that pair, the window frame when one has been
            saved, and the export bar in full. A window or the export bar
            may be stored before the sharing choice.

        Raises:
            ValueError: If the install id and the choice disagree, or if
                ``wizard_complete`` is not a boolean. A partial telemetry
                pair would stick on the next load and hide the prompt.
        """
        has_id = self.install_id is not None
        has_consent = isinstance(self.telemetry_consent, bool)
        if has_id != has_consent:
            raise ValueError("Refusing to write a partial settings file.")
        if not isinstance(self.wizard_complete, bool):
            raise ValueError("wizard_complete must be a boolean.")
        body: dict[str, object] = {"rekordbox": self.rekordbox.as_json()}
        if has_id:
            body["install_id"] = self.install_id
            body["telemetry_consent"] = self.telemetry_consent
            body["wizard_complete"] = self.wizard_complete
        if self.window is not None:
            body["window"] = {
                "x": self.window.x,
                "y": self.window.y,
                "width": self.window.width,
                "height": self.window.height,
            }
        return body


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


def _window_int(value: object, dotted: str, low: int, high: int) -> int | None:
    """Return a screen coordinate, or None when the value cannot be stored.

    Args:
        value: Candidate from the settings file.
        dotted: Full path, such as ``window.x``, used in the warning.
        low: Smallest accepted integer, inclusive.
        high: Largest accepted integer, inclusive.

    Returns:
        The integer when ``value`` is an ``int`` inside the range. None
        for a bool, a float, or any other type. ``0`` is a real origin
        and is kept.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        logger.warning("Config key '%s' has wrong type — ignored", dotted)
        return None
    if value < low or value > high:
        logger.warning("Config key '%s' is outside %s..%s — ignored", dotted, low, high)
        return None
    return value


def _parse_window(value: object) -> WindowGeometry | None:
    """Validate the ``window`` object.

    Args:
        value: The ``window`` member of the settings file.

    Returns:
        The frame when ``x``, ``y``, ``width``, and ``height`` are all
        integers in range. None when the object is not a mapping or any
        of those fields is missing or unusable. A partial frame is not
        returned, because the next launch would open at ``0, 0``.
    """
    if not isinstance(value, dict):
        logger.warning("Config key 'window' must be a mapping — ignored")
        return None
    for key in value:
        if key not in WINDOW_FIELDS:
            logger.warning("Unknown config key '%s' — ignored", f"window.{key}")
    parsed: dict[str, int] = {}
    complete = True
    for name, low, high in _WINDOW_LIMITS:
        dotted = f"window.{name}"
        if name not in value:
            logger.warning("Config key '%s' is missing — ignored", dotted)
            complete = False
            continue
        number = _window_int(value[name], dotted, low, high)
        if number is None:
            complete = False
            continue
        parsed[name] = number
    if not complete:
        return None
    return WindowGeometry(parsed["x"], parsed["y"], parsed["width"], parsed["height"])


def _parse(payload: object) -> Settings:
    """Validate a decoded settings object.

    Args:
        payload: JSON value read from the settings file.

    Returns:
        The known fields. Unknown keys and wrong types are dropped. A
        missing consent stays None, which means sharing is off and the
        prompt should be shown. A missing window stays None, which means
        the next launch is centered at the default size.
    """
    if not isinstance(payload, dict):
        logger.warning("Config file must be a mapping — ignored")
        return Settings(install_id=None, telemetry_consent=None, wizard_complete=False)
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
    window = _parse_window(payload["window"]) if "window" in payload else None
    wizard_complete = False
    if "wizard_complete" in payload:
        raw_wizard = payload.get("wizard_complete")
        if isinstance(raw_wizard, bool):
            wizard_complete = raw_wizard
        else:
            logger.warning("Config key 'wizard_complete' has wrong type — ignored")
    if "rekordbox" not in payload:
        rekordbox = default_rekordbox()
    else:
        rekordbox = _parse_rekordbox(payload.get("rekordbox"))
    return Settings(
        install_id=install_id,
        telemetry_consent=consent,
        window=window,
        wizard_complete=wizard_complete,
        rekordbox=rekordbox,
    )

def _parse_bool(value: object, dotted: str, default: bool) -> bool:
    """Return a stored boolean, or the default when the type is wrong.

    Args:
        value: Candidate from the settings file.
        dotted: Full key, such as ``rekordbox.hot_loops``.
        default: Value used when ``value`` is not a boolean. ``False`` is
            a stored choice and is not replaced by the default.

    Returns:
        The boolean, or ``default`` after a warning.
    """
    if isinstance(value, bool):
        return value
    logger.warning("Config key %r has wrong type — ignored", dotted)
    return default


def _parse_rekordbox(value: object) -> RekordboxSettings:
    """Validate the export section.

    Args:
        value: The ``rekordbox`` member of the settings file.

    Returns:
        The saved fields. A missing field keeps its default. An unknown
        field and a wrong type are dropped. ``False`` is kept.
    """
    defaults = default_rekordbox()
    if not isinstance(value, dict):
        logger.warning("Config key 'rekordbox' must be a mapping — ignored")
        return defaults
    for key in value:
        if key not in REKORDBOX_KEYS:
            logger.warning("Unknown config key %r — ignored", f"rekordbox.{key}")
    hot_loops = defaults.hot_loops
    memory_cues = defaults.memory_cues
    key_notation = defaults.key_notation
    if "hot_loops" in value:
        hot_loops = _parse_bool(value.get("hot_loops"), "rekordbox.hot_loops", defaults.hot_loops)
    if "memory_cues" in value:
        memory_cues = _parse_bool(value.get("memory_cues"), "rekordbox.memory_cues", defaults.memory_cues)
    if "key_notation" in value:
        raw_key = value.get("key_notation")
        if isinstance(raw_key, str) and raw_key in REKORDBOX_KEY_NOTATIONS:
            key_notation = raw_key
        else:
            logger.warning("Config key 'rekordbox.key_notation' has wrong type — ignored")
    return RekordboxSettings(
        hot_loops=hot_loops,
        memory_cues=memory_cues,
        key_notation=key_notation,
    )


def rekordbox_changes(section: object) -> dict[str, bool | str]:
    """Validate one POST body for the export bar.

    Args:
        section: The ``rekordbox`` object from the request. It must be a
            mapping with at least one known field.

    Returns:
        The fields to merge. Only keys present in ``section`` are included.

    Raises:
        ValueError: If the section is not a mapping, is empty, names an
            unknown field, or gives a field the wrong type. An integer is
            not a boolean.
    """
    if not isinstance(section, dict) or not section:
        raise ValueError("rekordbox must be an object with at least one field.")
    unknown = [key for key in section if key not in REKORDBOX_KEYS]
    if unknown:
        raise ValueError(f"Unknown config key 'rekordbox.{unknown[0]}'.")
    changes: dict[str, bool | str] = {}
    if "hot_loops" in section:
        raw_loops = section.get("hot_loops")
        if not isinstance(raw_loops, bool):
            raise ValueError("rekordbox.hot_loops must be a boolean.")
        changes["hot_loops"] = raw_loops
    if "memory_cues" in section:
        raw_memory = section.get("memory_cues")
        if not isinstance(raw_memory, bool):
            raise ValueError("rekordbox.memory_cues must be a boolean.")
        changes["memory_cues"] = raw_memory
    if "key_notation" in section:
        raw_key = section.get("key_notation")
        if not isinstance(raw_key, str) or raw_key not in REKORDBOX_KEY_NOTATIONS:
            raise ValueError("rekordbox.key_notation must be asis, camelot, or classical.")
        changes["key_notation"] = raw_key
    return changes


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
        return Settings(install_id=None, telemetry_consent=None, wizard_complete=False)
    try:
        text = path.read_text(encoding="utf-8")
        payload: object = json.loads(text)
    except (OSError, UnicodeError, json.JSONDecodeError):
        logger.warning("Config file %s could not be read — ignored", path.name)
        return Settings(install_id=None, telemetry_consent=None, wizard_complete=False)
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
    """Atomically replace the settings file.

    Args:
        settings: Sharing choice, install id, and export bar. A missing
            sharing choice is omitted. The export bar is always written
            in full.

    Raises:
        ValueError: If the install id and the sharing choice disagree.
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
        The settings that were written. A saved window frame is kept.

    Raises:
        ValueError: If ``value`` is not a boolean. Integers are rejected
            because ``bool`` is a subclass of ``int``.
        OSError: If the settings file cannot be written.

    The file is read again under the settings lock immediately before the
    write, so a window save that landed after the last read is not dropped.
    """
    if not isinstance(value, bool):
        raise ValueError("telemetry_consent must be a boolean.")
    with _settings_lock:
        current = load_settings()
        install_id = current.install_id or str(uuid.uuid4())
        updated = Settings(
            install_id=install_id,
            telemetry_consent=value,
            window=current.window,
            wizard_complete=current.wizard_complete is True,
            rekordbox=current.rekordbox,
        )
        save_settings(updated)
        return updated


def save_window_geometry(geometry: WindowGeometry) -> Settings:
    """Store the desktop window frame and keep a completed sharing choice.

    Args:
        geometry: Size and position to remember. Every field is checked
            again here, including the bool exclusion, so a caller cannot
            persist a frame the loader would drop.

    Returns:
        The settings that were written.

    Raises:
        ValueError: If ``geometry`` is not a :class:`WindowGeometry`.
        OSError: If the settings file cannot be written.

    A sharing choice is included only when both the install id and the
    boolean are already stored. The read and the write share the settings
    lock with :func:`set_telemetry_consent`.
    """
    if not isinstance(geometry, WindowGeometry):
        raise ValueError("window must be a WindowGeometry.")
    with _settings_lock:
        current = load_settings()
        install_id = current.install_id
        consent = current.telemetry_consent
        if not isinstance(consent, bool) or install_id is None:
            install_id = None
            consent = None
        updated = Settings(
            install_id=install_id,
            telemetry_consent=consent,
            window=geometry,
            wizard_complete=current.wizard_complete is True,
            rekordbox=current.rekordbox,
        )
        save_settings(updated)
        return updated


def set_wizard_complete(value: bool) -> Settings:
    """Store whether first-run setup has finished.

    Args:
        value: True when the person opens the library from the last step.
            False leaves setup unfinished. False is a real choice.

    Returns:
        The settings after the decision. When sharing has not been chosen
        yet, False is returned without writing a file. True is refused
        until that choice exists, so a finished flag cannot hide the prompt.

    Raises:
        ValueError: If ``value`` is not a boolean, or True is requested
            before the sharing choice is a boolean.
        OSError: If the settings file cannot be written.
    """
    if not isinstance(value, bool):
        raise ValueError("wizard_complete must be a boolean.")
    with _settings_lock:
        current = load_settings()
        if not isinstance(current.telemetry_consent, bool) or current.install_id is None:
            if value:
                raise ValueError("Choose whether to share stats before finishing setup.")
            return Settings(
                install_id=current.install_id,
                telemetry_consent=current.telemetry_consent,
                window=current.window,
                wizard_complete=False,
                rekordbox=current.rekordbox,
            )
        updated = Settings(
            install_id=current.install_id,
            telemetry_consent=current.telemetry_consent,
            window=current.window,
            wizard_complete=value,
            rekordbox=current.rekordbox,
        )
        save_settings(updated)
        return updated


def update_rekordbox(
    *,
    hot_loops: bool | None = None,
    memory_cues: bool | None = None,
    key_notation: str | None = None,
) -> Settings:
    """Merge export-bar fields into the settings file.

    Args:
        hot_loops: New hot-loops choice. None leaves the saved value.
        memory_cues: New memory-cues choice. None leaves the saved value.
            ``False`` is stored.
        key_notation: ``asis``, ``camelot``, or ``classical``. None leaves
            the saved value.

    Returns:
        The settings that were written. A sharing choice that was already
        saved is kept, and so are the window frame and the setup flag.
        Saving the export bar does not invent a sharing choice.

    Raises:
        ValueError: If a field has the wrong type, or no field was given.
        OSError: If the settings file cannot be written.
    """
    if hot_loops is not None and not isinstance(hot_loops, bool):
        raise ValueError("rekordbox.hot_loops must be a boolean.")
    if memory_cues is not None and not isinstance(memory_cues, bool):
        raise ValueError("rekordbox.memory_cues must be a boolean.")
    if key_notation is not None and (
        not isinstance(key_notation, str) or key_notation not in REKORDBOX_KEY_NOTATIONS
    ):
        raise ValueError("rekordbox.key_notation must be asis, camelot, or classical.")
    if hot_loops is None and memory_cues is None and key_notation is None:
        raise ValueError("rekordbox has no fields to save.")
    with _settings_lock:
        current = load_settings()
        install_id = current.install_id
        consent = current.telemetry_consent
        if not isinstance(consent, bool) or install_id is None:
            install_id = None
            consent = None
        box = current.rekordbox
        updated = Settings(
            install_id=install_id,
            telemetry_consent=consent,
            window=current.window,
            wizard_complete=current.wizard_complete is True,
            rekordbox=RekordboxSettings(
                hot_loops=box.hot_loops if hot_loops is None else hot_loops,
                memory_cues=box.memory_cues if memory_cues is None else memory_cues,
                key_notation=box.key_notation if key_notation is None else key_notation,
            ),
        )
        save_settings(updated)
        return updated
