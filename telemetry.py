"""Anonymous crash reports and usage counts.

Nothing is sent until the person opts in and the matching key is present.
A missing ``SENTRY_DSN`` disables Sentry. A missing ``POSTHOG_KEY`` disables
PostHog. Keys come from the environment, then from ``_build_config``, which
release builds overwrite from GitHub secrets.

Events are an allowlist: ``app_opened``, ``library_scanned``,
``crate_created``, ``backup_made``, ``tags_read``, ``files_changed``,
``related_link_saved``, ``related_link_removed``,
``related_crate_written``, and ``duplicates_merged``. Properties are the
app name ``serato-library-manager``, the app version, the operating
system, a track-count bucket, a file-count bucket, a change type, and a
cue result for a file change, and ``link_direction`` (``one_way`` or
``two_way``) on ``related_link_saved``. ``duplicates_merged`` carries no
extra properties. Track titles, crate names, file paths, and library
rows are not properties, and the Sentry ``before_send`` hook removes
paths if one appears in an exception. Crash reports carry the tag
``app=serato-library-manager``.
"""

from __future__ import annotations

import logging
import os
import platform
import re
import threading
import uuid
from collections.abc import Mapping
from typing import Any

import app_config

try:
    import _build_config as _baked
except ImportError:  # pragma: no cover - the module ships in this repository
    _baked = None  # type: ignore[assignment]

logger = logging.getLogger("serato.library.telemetry")

DEFAULT_POSTHOG_HOST = "https://us.i.posthog.com"
# Shared with the owner's other app, which uses the same PostHog project.
APP_NAME = "serato-library-manager"
EVENT_APP_OPENED = "app_opened"
EVENT_LIBRARY_SCANNED = "library_scanned"
EVENT_CRATE_CREATED = "crate_created"
EVENT_BACKUP_MADE = "backup_made"
EVENT_TAGS_READ = "tags_read"
EVENT_FILES_CHANGED = "files_changed"
EVENT_RELATED_LINK_SAVED = "related_link_saved"
EVENT_RELATED_LINK_REMOVED = "related_link_removed"
EVENT_RELATED_CRATE_WRITTEN = "related_crate_written"
EVENT_DUPLICATES_MERGED = "duplicates_merged"
TRACK_COUNT = "track_count"
TRACK_COUNT_BUCKET = "track_count_bucket"
FILE_COUNT = "file_count"
FILE_COUNT_BUCKET = "file_count_bucket"
CHANGE = "change"
CUES = "cues"
LINK_DIRECTION = "link_direction"
CHANGES = frozenset({"rename", "move", "move_folder", "replace", "delete"})
CUE_RESULTS = frozenset({"copied", "kept", "skipped", "unsupported", "failed"})
LINK_DIRECTIONS = frozenset({"one_way", "two_way"})

# Event name to the caller-supplied properties it may carry. Global
# properties are added here, not by the caller.
EVENTS: dict[str, frozenset[str]] = {
    EVENT_APP_OPENED: frozenset(),
    EVENT_LIBRARY_SCANNED: frozenset({TRACK_COUNT}),
    EVENT_CRATE_CREATED: frozenset(),
    EVENT_BACKUP_MADE: frozenset(),
    EVENT_TAGS_READ: frozenset(),
    EVENT_FILES_CHANGED: frozenset({FILE_COUNT, CHANGE, CUES}),
    EVENT_RELATED_LINK_SAVED: frozenset({LINK_DIRECTION}),
    EVENT_RELATED_LINK_REMOVED: frozenset(),
    EVENT_RELATED_CRATE_WRITTEN: frozenset(),
    EVENT_DUPLICATES_MERGED: frozenset(),
}
BUCKETS = (
    (1, "0"),
    (10, "1-9"),
    (50, "10-49"),
    (100, "50-99"),
    (500, "100-499"),
    (1000, "500-999"),
    (5000, "1000-4999"),
    (10000, "5000-9999"),
)
BUCKET_LABELS = frozenset(label for _, label in BUCKETS) | {"10000+"}
# PostHog adds these. Anything else, including titles and paths, is removed.
POSTHOG_PROPERTY_ALLOWLIST = frozenset(
    {
        "app",
        "app_version",
        "os",
        TRACK_COUNT_BUCKET,
        LINK_DIRECTION,
        "$python_runtime",
        "$python_version",
        "$os",
        "$os_version",
        "$os_distro",
        "$lib",
        "$lib_version",
        "$geoip_disable",
        "$is_server",
        FILE_COUNT_BUCKET,
        CHANGE,
        CUES,
    }
)
POSTHOG_EVENT_KEYS = frozenset({"event", "distinct_id", "properties", "timestamp", "uuid"})
_OS_NAMES = frozenset({"Darwin", "Windows", "Linux"})
_PY_FILE = re.compile(r"^[\w.-]+\.py$")
_TRIM = set(".,;:)]}")
_DELIM = set("\"'\n\r\t<>|`")
_PATH_MARK = "[path]"

_lock = threading.Lock()
_posthog: Any = None
_sentry_ready = False
_app_opened = False
_atexit_registered = False


def _baked_value(name: str) -> str:
    """Return one string constant from the generated build module.

    Args:
        name: ``SENTRY_DSN``, ``POSTHOG_KEY``, or ``POSTHOG_HOST``.

    Returns:
        The stripped string, or an empty string when the module or the
        attribute is missing or is not a string.
    """
    if _baked is None:
        return ""
    value = getattr(_baked, name, "")
    if not isinstance(value, str):
        return ""
    return value.strip()


def configured_value(name: str) -> str:
    """Return a telemetry key from the environment or the baked module.

    Args:
        name: Environment variable and ``_build_config`` attribute.

    Returns:
        The environment value when it is non-empty, otherwise the baked
        value, otherwise an empty string. An empty string means that
        service is off. A blank environment variable does not hide a baked
        key; unsetting the variable does.
    """
    env = os.environ.get(name)
    if isinstance(env, str) and env.strip():
        return env.strip()
    return _baked_value(name)


def sentry_dsn() -> str:
    """Return the Sentry DSN, or an empty string when Sentry is off.

    Returns:
        ``SENTRY_DSN`` from the environment or ``_build_config``.
    """
    return configured_value("SENTRY_DSN")


def posthog_key() -> str:
    """Return the PostHog project key, or an empty string when PostHog is off.

    Returns:
        ``POSTHOG_KEY`` from the environment or ``_build_config``.
    """
    return configured_value("POSTHOG_KEY")


def posthog_host() -> str:
    """Return the PostHog ingestion host.

    Returns:
        ``POSTHOG_HOST`` when it is set, otherwise
        ``https://us.i.posthog.com``.
    """
    return configured_value("POSTHOG_HOST") or DEFAULT_POSTHOG_HOST


def telemetry_configured() -> bool:
    """Return whether either service has a key.

    Returns:
        True when a Sentry DSN or a PostHog key is available. The sharing
        choice is separate: a key alone does not send anything.
    """
    return bool(sentry_dsn() or posthog_key())


def os_name() -> str:
    """Return a coarse operating-system name.

    Returns:
        ``Darwin``, ``Windows``, ``Linux``, or ``other``. The hostname and
        the kernel build are not included.
    """
    name = platform.system()
    if name in _OS_NAMES:
        return name
    return "other"


def track_count_bucket(count: int) -> str:
    """Group a library size so the exact count is not sent.

    Args:
        count: Number of tracks in the space that was just read.

    Returns:
        A label such as ``1-9`` or ``10000+``.

    Raises:
        TypeError: If ``count`` is a boolean or not an integer.
    """
    if isinstance(count, bool) or not isinstance(count, int):
        raise TypeError("track_count must be an integer.")
    if count < 0:
        count = 0
    for limit, label in BUCKETS:
        if count < limit:
            return label
    return "10000+"


def consent_granted() -> bool:
    """Return whether the person has opted in.

    Returns:
        True only when the saved choice is the boolean True. A missing
        file and a saved False both return False.
    """
    return app_config.load_settings().telemetry_consent is True


def _starts_path(text: str, index: int) -> bool:
    """Return whether a filesystem path begins at ``index``.

    Args:
        text: String that may contain a path.
        index: Candidate start.

    Returns:
        True for a home path, a drive path, a UNC path, or a slash that
        can begin an absolute path.
    """
    if text.startswith("\\\\", index) or text.startswith("//", index):
        return True
    if text.startswith("~/", index) or text.startswith("~\\", index):
        return True
    if (
        index + 2 < len(text)
        and text[index].isalpha()
        and text[index + 1] == ":"
        and text[index + 2] in "\\/"
    ):
        return True
    if text[index] == "/" and (index == 0 or text[index - 1] not in "\\/"):
        if index + 1 < len(text) and text[index + 1] not in "/ \t\n\r":
            return True
    return False


def _consume_path(text: str, start: int) -> int:
    """Return the end index of a path, or ``start`` when it is not one.

    Args:
        text: String containing the candidate.
        start: Index returned by :func:`_starts_path`.

    Returns:
        The index after the path. Spaces stay inside the path only when
        another slash follows them, so a sentence after a path is kept.
        Trailing punctuation is left outside the path.
    """
    end = start
    limit = len(text)
    while end < limit:
        char = text[end]
        if char in _DELIM:
            break
        if char == " ":
            ahead = end + 1
            another = False
            while ahead < limit and text[ahead] not in _DELIM:
                if text[ahead] in "/\\":
                    another = True
                    break
                ahead += 1
            if not another:
                break
        end += 1
    while end > start and text[end - 1] in _TRIM:
        end -= 1
    if end <= start:
        return start
    token = text[start:end]
    if token.startswith("~"):
        return end
    if len(token) >= 3 and token[1] == ":":
        return end
    if token.startswith("\\\\") or token.startswith("//"):
        rest = token[2:]
        if "/" in rest or "\\" in rest:
            return end
        return start
    if token.find("/", 1) != -1:
        return end
    return start


def _redact_token(token: str) -> str:
    """Replace a path with a marker, keeping a Python file's basename.

    Args:
        token: One absolute or home path.

    Returns:
        The ``.py`` basename when that is the whole final component, so a
        stack frame can still name ``server.py``. Every other path becomes
        ``[path]``, including audio files whose names are track titles.
    """
    name = token.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    if _PY_FILE.fullmatch(name):
        return name
    return _PATH_MARK


def scrub_text(text: str) -> str:
    """Remove filesystem paths from one string.

    Args:
        text: Exception text, breadcrumb, or frame path.

    Returns:
        The same text with paths replaced. Short fragments such as
        ``SeratoLibrary/1.0`` are left alone.
    """
    if not text:
        return text
    parts: list[str] = []
    index = 0
    limit = len(text)
    while index < limit:
        if _starts_path(text, index):
            end = _consume_path(text, index)
            if end > index:
                parts.append(_redact_token(text[index:end]))
                index = end
                continue
        parts.append(text[index])
        index += 1
    return "".join(parts)


def _scrub_value(value: object) -> object:
    """Scrub paths in a JSON-like value.

    Args:
        value: A string, mapping, sequence, or scalar from a Sentry event.

    Returns:
        The value with every string passed through :func:`scrub_text`.
        Bytes are replaced so a tag body cannot ride along in an event.
    """
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, bool) or value is None or isinstance(value, (int, float)):
        return value
    if isinstance(value, dict):
        scrubbed: dict[object, object] = {}
        for key, item in value.items():
            scrubbed_key = scrub_text(key) if isinstance(key, str) else key
            scrubbed[scrubbed_key] = _scrub_value(item)
        return scrubbed
    if isinstance(value, (list, tuple)):
        return [_scrub_value(item) for item in value]
    if isinstance(value, (bytes, bytearray)):
        return "[binary]"
    return scrub_text(str(value))


def _is_uuid(value: object) -> bool:
    """Return whether ``value`` is a UUID string.

    Args:
        value: Candidate install id.

    Returns:
        True when ``value`` parses as a UUID.
    """
    if not isinstance(value, str):
        return False
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


def scrub_sentry_event(event: dict[str, Any]) -> dict[str, Any]:
    """Remove paths and request data from a Sentry event.

    Args:
        event: Event dictionary the SDK is about to send.

    Returns:
        A copy safe to upload. The request, local variables, and source
        context are removed. ``server_name`` is ``local`` so the machine
        name is not sent. User fields other than a UUID id are removed.
    """
    cleaned: dict[str, Any] = dict(event)
    cleaned.pop("request", None)
    cleaned.pop("extra", None)
    user = cleaned.get("user")
    if isinstance(user, dict) and _is_uuid(user.get("id")):
        cleaned["user"] = {"id": str(user.get("id"))}
    else:
        cleaned.pop("user", None)
    cleaned["server_name"] = "local"
    exception = cleaned.get("exception")
    if isinstance(exception, dict):
        values = exception.get("values")
        if isinstance(values, list):
            for entry in values:
                if not isinstance(entry, dict):
                    continue
                stack = entry.get("stacktrace")
                if not isinstance(stack, dict):
                    continue
                frames = stack.get("frames")
                if not isinstance(frames, list):
                    continue
                for frame in frames:
                    if not isinstance(frame, dict):
                        continue
                    frame.pop("vars", None)
                    frame.pop("pre_context", None)
                    frame.pop("post_context", None)
                    frame.pop("context_line", None)
    scrubbed = _scrub_value(cleaned)
    if not isinstance(scrubbed, dict):
        return {"server_name": "local", "tags": {"app": APP_NAME}}
    scrubbed["server_name"] = "local"
    tags = scrubbed.get("tags")
    if not isinstance(tags, dict):
        tags = {}
    else:
        tags = {key: value for key, value in tags.items() if key != "app"}
    tags["app"] = APP_NAME
    scrubbed["tags"] = tags
    return scrubbed


def before_send(event: dict[str, Any], hint: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Sentry hook that drops or scrubs an event before it is sent.

    Args:
        event: Event the SDK built.
        hint: SDK hint. It is not returned and is not uploaded.

    Returns:
        The scrubbed event when sharing is on. None when the person has
        not opted in, which tells Sentry to discard the event.
    """
    del hint
    if not consent_granted():
        return None
    return scrub_sentry_event(event)


def limit_posthog_event(event: dict[str, Any]) -> dict[str, Any] | None:
    """Drop a PostHog payload that is not on the allowlist.

    Args:
        event: Event dictionary the PostHog client is about to queue.

    Returns:
        A copy whose properties are only the allowlisted counts and SDK
        versions, or None when the event name, the install id, or a
        track-count bucket is not allowed. Returning None makes the
        client skip the upload.
    """
    if not isinstance(event, dict):
        return None
    name = event.get("event")
    if name not in EVENTS:
        return None
    if not _is_uuid(event.get("distinct_id")):
        return None
    if not consent_granted():
        return None
    properties = event.get("properties")
    if properties is None:
        properties = {}
    if not isinstance(properties, dict):
        return None
    if properties.get("$geoip_disable", True) is not True:
        return None
    kept: dict[str, object] = {}
    for key, value in properties.items():
        if key not in POSTHOG_PROPERTY_ALLOWLIST:
            continue
        if key in {TRACK_COUNT_BUCKET, FILE_COUNT_BUCKET} and value not in BUCKET_LABELS:
            return None
        if key == CHANGE and value not in CHANGES:
            return None
        if key == CUES and value not in CUE_RESULTS:
            return None
        if key == LINK_DIRECTION:
            if LINK_DIRECTION not in EVENTS.get(name, frozenset()):
                continue
            if value not in LINK_DIRECTIONS:
                return None
            kept[key] = value
            continue
        if key == "app":
            continue
        if key in {TRACK_COUNT_BUCKET, FILE_COUNT_BUCKET, CHANGE, CUES}:
            kept[key] = value
            continue
        if isinstance(value, str):
            kept[key] = scrub_text(value)
        elif isinstance(value, bool) or isinstance(value, (int, float)):
            kept[key] = value
    kept["app"] = APP_NAME
    kept["app_version"] = app_config.APP_VERSION
    kept["os"] = os_name()
    kept["$geoip_disable"] = True
    limited = {key: event[key] for key in POSTHOG_EVENT_KEYS if key in event}
    limited["properties"] = kept
    limited["event"] = name
    return limited


def _allow_properties(event: str, properties: Mapping[str, object]) -> dict[str, object] | None:
    """Build the properties dictionary for one allowed event.

    Args:
        event: Allowlisted event name.
        properties: Caller properties. Unknown keys are ignored. A
            ``track_count`` integer is replaced with its bucket.

    Returns:
        The properties to hand to PostHog, or None when the track count
        is not an integer or ``link_direction`` is not ``one_way`` or
        ``two_way``. The app name, app version, and operating system are
        always the values this process computed. A path or a title in
        ``properties`` is ignored.
    """
    allowed = EVENTS[event]
    props: dict[str, object] = {
        "app": APP_NAME,
        "app_version": app_config.APP_VERSION,
        "os": os_name(),
    }
    if TRACK_COUNT in allowed:
        if TRACK_COUNT not in properties:
            return None
        try:
            props[TRACK_COUNT_BUCKET] = track_count_bucket(properties[TRACK_COUNT])  # type: ignore[arg-type]
        except TypeError:
            return None
    if FILE_COUNT in allowed:
        if FILE_COUNT not in properties:
            return None
        try:
            props[FILE_COUNT_BUCKET] = track_count_bucket(properties[FILE_COUNT])  # type: ignore[arg-type]
        except TypeError:
            return None
    if CHANGE in allowed:
        change = properties.get(CHANGE)
        if change not in CHANGES:
            return None
        props[CHANGE] = change
    if CUES in properties and CUES in allowed:
        cues = properties.get(CUES)
        if cues not in CUE_RESULTS:
            return None
        props[CUES] = cues
    if LINK_DIRECTION in allowed:
        direction = properties.get(LINK_DIRECTION)
        if direction not in LINK_DIRECTIONS:
            return None
        props[LINK_DIRECTION] = direction
    return props


def _make_posthog(key: str, host: str) -> Any:
    """Construct a PostHog client that does not collect geo or exceptions.

    Args:
        key: PostHog project API key.
        host: Ingestion host.

    Returns:
        A ``Posthog`` client. Feature-flag polling and exception
        autocapture are off. GeoIP is disabled. The before-send hook
        applies the property allowlist again.

    Raises:
        ImportError: If the ``posthog`` package is not installed.
    """
    from posthog import Posthog

    def _on_error(error: BaseException, items: object) -> None:
        del items
        logger.warning("Telemetry upload failed (%s)", type(error).__name__)

    return Posthog(
        key,
        host=host,
        disable_geoip=True,
        enable_exception_autocapture=False,
        enable_local_evaluation=False,
        capture_exception_code_variables=False,
        timeout=3,
        max_retries=1,
        sync_mode=False,
        before_send=limit_posthog_event,
        super_properties={
            "app": APP_NAME,
            "app_version": app_config.APP_VERSION,
            "os": os_name(),
        },
        on_error=_on_error,
    )


def _init_sentry(dsn: str) -> None:
    """Initialize Sentry when a DSN is present.

    Args:
        dsn: Non-empty Sentry DSN.

    Raises:
        ImportError: If ``sentry_sdk`` is not installed.

    Local variables, request bodies, argv, and log breadcrumbs are off.
    Framework auto-enabling is off so an installed library such as Bottle
    cannot attach a request hook. ``server_name`` is the constant
    ``local`` because the default is the machine hostname. The before-send
    hook scrubs paths and drops the event when consent is no longer granted.
    The tag ``app`` is ``serato-library-manager`` so a shared Sentry
    project can tell this app from the other one. The hook sets that tag
    again after scrubbing, so a caller cannot replace it.
    """
    import sentry_sdk
    from sentry_sdk.integrations.argv import ArgvIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration

    sentry_sdk.init(
        dsn=dsn,
        release=app_config.APP_VERSION,
        environment="local",
        server_name="local",
        send_default_pii=False,
        include_local_variables=False,
        include_source_context=False,
        max_request_body_size="never",
        traces_sample_rate=0,
        spotlight=False,
        auto_enabling_integrations=False,
        before_send=before_send,
        disabled_integrations=[ArgvIntegration(), LoggingIntegration()],
    )
    sentry_sdk.set_tag("app", APP_NAME)


def activate() -> None:
    """Start the clients when sharing is on and a key exists.

    A missing package, a missing key, or a declined choice leaves that
    service uninitialized. No network call is made in those cases.
    """
    global _posthog, _sentry_ready, _atexit_registered
    if not consent_granted():
        return
    if not _atexit_registered:
        import atexit

        atexit.register(shutdown)
        _atexit_registered = True
    dsn = sentry_dsn()
    if dsn and not _sentry_ready:
        try:
            _init_sentry(dsn)
        except Exception:
            logger.warning("Crash reporting could not be started.")
        else:
            _sentry_ready = True
    key = posthog_key()
    if key and _posthog is None:
        try:
            _posthog = _make_posthog(key, posthog_host())
        except Exception:
            logger.warning("Usage analytics could not be started.")


def shutdown() -> None:
    """Flush and stop the clients.

    Safe to call more than once. A client that was never started is
    ignored. PostHog's shutdown waits for the short request timeout
    configured on the client.
    """
    global _posthog, _sentry_ready, _app_opened
    client = _posthog
    _posthog = None
    _app_opened = False
    if client is not None:
        try:
            client.shutdown()
        except Exception:
            logger.warning("Usage analytics could not be stopped.")
    if _sentry_ready:
        _sentry_ready = False
        try:
            import sentry_sdk

            sentry_sdk.flush(timeout=2)
            sentry_sdk.get_client().close()
        except Exception:
            logger.warning("Crash reporting could not be stopped.")


def capture(event: str, properties: Mapping[str, object] | None = None) -> bool:
    """Record one allowlisted usage event.

    Args:
        event: One of the allowlisted event names.
        properties: Optional ``track_count`` for ``library_scanned``,
            ``file_count``, ``change``, and ``cues`` for ``files_changed``,
            or ``link_direction`` for ``related_link_saved``. Other keys
            are ignored and are not sent. Paths and names are not accepted
            properties.

    Returns:
        True when the event was handed to PostHog. False when consent,
        the key, the event name, or the package is missing. A False
        result is discarded. It is not queued for a later opt-in.

    The call does not raise. A failure is written to the local log.
    """
    try:
        return _capture(event, properties or {})
    except Exception:
        logger.warning("Telemetry capture failed.")
        return False


def _capture(event: str, properties: Mapping[str, object]) -> bool:
    """Send one event after the consent and allowlist checks.

    Args:
        event: Event name.
        properties: Caller properties.

    Returns:
        True when PostHog accepted the event into its queue.
    """
    if event not in EVENTS:
        return False
    if not consent_granted():
        return False
    key = posthog_key()
    if not key:
        return False
    props = _allow_properties(event, properties)
    if props is None:
        return False
    settings = app_config.load_settings()
    if settings.install_id is None:
        settings = app_config.set_telemetry_consent(True)
    install_id = settings.install_id
    if install_id is None:
        return False
    activate()
    client = _posthog
    if client is None:
        return False
    client.capture(event, distinct_id=install_id, properties=props)
    return True


def capture_exception(exc: BaseException | None = None) -> None:
    """Send one exception to Sentry when sharing and a DSN are on.

    Args:
        exc: Exception to report. None reports the exception in flight.

    Nothing is sent without consent or without a DSN. The before-send
    hook still scrubs paths. Failures are local log lines.
    """
    try:
        if not consent_granted() or not sentry_dsn():
            return
        activate()
        if not _sentry_ready:
            return
        import sentry_sdk

        sentry_sdk.capture_exception(exc)
    except Exception:
        logger.warning("Crash report failed.")


def note_app_opened() -> None:
    """Send ``app_opened`` once for this process after consent.

    A call made before the person opts in does not stick. The next call
    after they opt in still sends the event.
    """
    global _app_opened
    with _lock:
        if _app_opened:
            return
        if capture(EVENT_APP_OPENED):
            _app_opened = True


def public_settings() -> dict[str, object]:
    """Return the sharing state the page is allowed to see.

    Returns:
        Consent, whether the first-launch prompt should show, the saved
        pane layout, whether this build has a key, the app version, and the
        Rekordbox export bar. ``app_version`` is the ``version`` string from
        ``GET /api/version``. The install id and the telemetry keys are not
        included.
    """
    settings = app_config.load_settings()
    return {
        "telemetry_consent": settings.telemetry_consent,
        "needs_consent_prompt": settings.telemetry_consent is None,
        "wizard_complete": settings.wizard_complete is True,
        "layout": {"track_list_width": settings.track_list_width},
        "telemetry_configured": telemetry_configured(),
        "app_version": app_config.APP_VERSION,
        "rekordbox": settings.rekordbox.as_json(),
    }


def set_consent(value: bool) -> dict[str, object]:
    """Save the sharing choice and start or stop the clients.

    Args:
        value: True to share anonymous stats and crash reports. False to
            send nothing.

    Returns:
        The same object as :func:`public_settings`.

    Raises:
        ValueError: If ``value`` is not a boolean.
        OSError: If the settings file cannot be written.
    """
    app_config.set_telemetry_consent(value)
    if value:
        activate()
        note_app_opened()
    else:
        shutdown()
    return public_settings()
