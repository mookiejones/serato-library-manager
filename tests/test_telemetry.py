"""Consent, allowlist, and path-scrubbing tests.

Nothing is uploaded. PostHog and Sentry are either faked or given a
transport that records the event in memory.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import app_config
import app_log
import library
import telemetry

try:
    import sentry_sdk
except ImportError:
    sentry_sdk = None
try:
    from posthog import Posthog
except ImportError:
    Posthog = None
from tests.fixture import TempLibrary, open_database

ROOT = Path(__file__).resolve().parents[1]


class FakePosthog:
    """In-memory PostHog stand-in.

    ``capture`` records the arguments. ``shutdown`` marks the client closed.
    No socket is opened.
    """

    def __init__(self) -> None:
        """Start with an empty event list."""
        self.events: list[tuple[str, str, dict[str, object]]] = []
        self.closed = False

    def capture(self, event: str, distinct_id: str | None = None, properties: dict[str, object] | None = None) -> str:
        """Record one capture call.

        Args:
            event: Event name.
            distinct_id: Anonymous install id.
            properties: Properties the app handed over.

        Returns:
            A fixed id so callers can ignore the SDK's return value.
        """
        self.events.append((event, distinct_id or "", dict(properties or {})))
        return "fake"

    def shutdown(self) -> None:
        """Mark the client closed."""
        self.closed = True


@unittest.skipUnless(sentry_sdk is not None, "sentry_sdk is not installed")
class TelemetryCase(unittest.TestCase):
    """Share a temporary settings directory and a fake PostHog client.

    ``tearDown`` shuts the telemetry clients so a test cannot leave a
    background uploader running.
    """

    def setUp(self) -> None:
        """Point settings at a temporary directory and clear client state.

        Returns:
            None.
        """
        self._tmp = tempfile.TemporaryDirectory()
        self.config = Path(self._tmp.name) / "config"
        self.config.mkdir()
        self._env = mock.patch.dict(
            os.environ,
            {
                app_config.CONFIG_ENV: str(self.config),
                "POSTHOG_KEY": "",
                "SENTRY_DSN": "",
                "POSTHOG_HOST": "",
            },
        )
        self._env.start()
        self.fake = FakePosthog()
        self._factory = mock.patch("telemetry._make_posthog", return_value=self.fake)
        self._factory.start()
        telemetry.shutdown()

    def tearDown(self) -> None:
        """Stop clients and delete the temporary directory.

        Returns:
            None.
        """
        telemetry.shutdown()
        self._factory.stop()
        self._env.stop()
        self._tmp.cleanup()
        try:
            sentry_sdk.get_client().close()
        except Exception:
            pass

    def _opt_in(self) -> None:
        """Save an explicit opt-in without starting a real client.

        Returns:
            None.
        """
        app_config.set_telemetry_consent(True)


class ConsentTests(TelemetryCase):
    """Nothing is handed to a client without consent and a key."""

    def test_nothing_is_sent_without_consent(self) -> None:
        """Drop events while the choice is still unset.

        A key is present. The factory and the fake client are not used.
        The settings file is not created by the attempt.

        Returns:
            None. The test fails if a capture is recorded.
        """
        with mock.patch.dict(os.environ, {"POSTHOG_KEY": "phc_test", "SENTRY_DSN": "https://public@o0.ingest.sentry.io/0"}):
            sent = telemetry.capture(telemetry.EVENT_APP_OPENED)
            telemetry.capture_exception(RuntimeError("open /Users/dj/Music/Secret.mp3"))
        self.assertFalse(sent)
        self.assertEqual(self.fake.events, [])
        telemetry._make_posthog.assert_not_called()
        self.assertFalse((self.config / "settings.json").exists())

    def test_nothing_is_sent_when_declined(self) -> None:
        """Drop events when the saved choice is False.

        False must not be treated as a missing value that falls through
        to a default of on.

        Returns:
            None. The test fails if the fake client records an event.
        """
        app_config.set_telemetry_consent(False)
        with mock.patch.dict(os.environ, {"POSTHOG_KEY": "phc_test"}):
            sent = telemetry.capture(
                telemetry.EVENT_CRATE_CREATED,
                {"name": "Friday", "path": "/Users/dj/Music/a.mp3"},
            )
        self.assertFalse(sent)
        self.assertEqual(self.fake.events, [])

    def test_nothing_is_sent_without_keys(self) -> None:
        """Drop events when the person opted in but no key is configured.

        The baked file in this tree is empty, and the environment is empty.
        The factory is not called.

        Returns:
            None. The test fails if a client is constructed.
        """
        self._opt_in()
        sent = telemetry.capture(telemetry.EVENT_APP_OPENED)
        self.assertFalse(sent)
        telemetry._make_posthog.assert_not_called()
        self.assertFalse(telemetry.telemetry_configured())

    def test_opt_in_sends_only_allowlisted_fields(self) -> None:
        """Send an event only after consent, and only with public fields.

        The caller passes a crate name and a path. Those keys are absent
        from the recorded properties. The distinct id is the install id.

        Returns:
            None. The test fails if the name, the path, or a raw track
            count is present.
        """
        self._opt_in()
        with mock.patch.dict(os.environ, {"POSTHOG_KEY": "phc_test"}):
            opened = telemetry.capture(
                telemetry.EVENT_APP_OPENED,
                {"name": "Friday", "app": "/Users/dj/Music/Secret Track.mp3"},
            )
            scanned = telemetry.capture(
                telemetry.EVENT_LIBRARY_SCANNED,
                {"track_count": 2, "name": "Secret Track", "path": "/Users/dj/Music/Secret Track.mp3"},
            )
        self.assertTrue(opened)
        self.assertTrue(scanned)
        self.assertEqual(self.fake.events[0][0], "app_opened")
        self.assertNotIn("name", self.fake.events[0][2])
        self.assertEqual(self.fake.events[0][2]["app"], telemetry.APP_NAME)
        self.assertNotIn("/Users", json.dumps(self.fake.events[0][2]))
        bucket_event = self.fake.events[1]
        self.assertEqual(bucket_event[0], "library_scanned")
        self.assertEqual(bucket_event[2]["track_count_bucket"], "1-9")
        self.assertNotIn("track_count", bucket_event[2])
        self.assertNotIn("name", bucket_event[2])
        self.assertNotIn("path", bucket_event[2])
        self.assertEqual(bucket_event[2]["app"], telemetry.APP_NAME)
        self.assertEqual(bucket_event[2]["app_version"], app_config.APP_VERSION)
        self.assertIn(bucket_event[2]["os"], {"Darwin", "Windows", "Linux", "other"})
        install_id = app_config.load_settings().install_id
        self.assertEqual(bucket_event[1], install_id)

    def test_files_changed_sends_a_bucket_and_drops_paths(self) -> None:
        """Send a file-count range and a change type, never a path or a name.

        A change value that is a path drops the event. A cue value that is
        a path drops it too. A valid replace sends the bucket, the change,
        and the cue result. The exact file count is not a property.

        Returns:
            None. The test fails if a path is present or a bad change is sent.
        """
        self._opt_in()
        dropped = telemetry._allow_properties(
            telemetry.EVENT_FILES_CHANGED,
            {"file_count": 3, "change": "/secret/path", "name": "track.mp3"},
        )
        self.assertIsNone(dropped)
        bad_cues = telemetry._allow_properties(
            telemetry.EVENT_FILES_CHANGED,
            {"file_count": 1, "change": "replace", "cues": "/tmp/new.mp3"},
        )
        self.assertIsNone(bad_cues)
        install_id = app_config.load_settings().install_id
        self.assertIsNone(
            telemetry.limit_posthog_event(
                {
                    "event": telemetry.EVENT_FILES_CHANGED,
                    "distinct_id": install_id,
                    "properties": {
                        "file_count_bucket": "1-9",
                        "change": "/secret/path",
                        "path": "/secret/song.mp3",
                        "$geoip_disable": True,
                    },
                }
            )
        )
        with mock.patch.dict(os.environ, {"POSTHOG_KEY": "phc_test"}):
            sent = telemetry.capture(
                telemetry.EVENT_FILES_CHANGED,
                {
                    "file_count": 12,
                    "change": "rename",
                    "cues": "copied",
                    "path": "/tmp/library/song.mp3",
                    "name": "song.mp3",
                },
            )
        self.assertTrue(sent)
        event = self.fake.events[-1]
        self.assertEqual(event[0], "files_changed")
        self.assertEqual(event[2]["file_count_bucket"], "10-49")
        self.assertEqual(event[2]["change"], "rename")
        self.assertEqual(event[2]["cues"], "copied")
        self.assertNotIn("file_count", event[2])
        self.assertNotIn("path", event[2])
        self.assertNotIn("name", event[2])
        self.assertNotIn("/tmp", json.dumps(event[2]))
        self.assertNotIn("song.mp3", json.dumps(event[2]))

    def test_missing_package_is_a_no_op(self) -> None:
        """Stay quiet when the PostHog package cannot be imported.

        Consent and a key are set. The import raises ImportError. Capture
        returns False and does not raise.

        Returns:
            None. The test fails if the ImportError escapes.
        """
        self._opt_in()
        with mock.patch.dict(os.environ, {"POSTHOG_KEY": "phc_test"}):
            with mock.patch("telemetry._make_posthog", side_effect=ImportError("posthog")):
                sent = telemetry.capture(telemetry.EVENT_BACKUP_MADE)
        self.assertFalse(sent)

    def test_before_send_drops_events_without_consent(self) -> None:
        """Return None from the Sentry hook when sharing is off.

        The event contains a path. None tells the SDK to discard it, so
        the path is not sent.

        Returns:
            None. The test fails if an event is returned.
        """
        event = {"message": "open /Users/dj/Music/Secret Track.mp3", "server_name": "studio-mac"}
        self.assertIsNone(telemetry.before_send(event, {}))


class ScrubTests(TelemetryCase):
    """The before_send hook removes filesystem paths."""

    def test_scrub_text_keeps_the_sentence(self) -> None:
        """Replace absolute paths and leave the words around them.

        Spaces inside ``Application Support`` belong to the path. The
        explanation after the path stays. A Python frame keeps its file
        name. A version string with a slash is not a path.

        Returns:
            None. The test fails if a user path survives or the sentence is eaten.
        """
        unix = telemetry.scrub_text(
            "Could not open /Users/dj/Library/Application Support/Serato/Library/master.sqlite because it is missing"
        )
        self.assertEqual(unix, "Could not open [path] because it is missing")
        windows = telemetry.scrub_text(
            r"Could not open C:\Users\dj\My Music\track.mp3 because it is missing"
        )
        self.assertEqual(windows, "Could not open [path] because it is missing")
        unc = telemetry.scrub_text(r"Missing \\studio\share\Secret Track.mp3 today")
        self.assertNotIn("Secret Track", unc)
        self.assertIn("[path]", unc)
        home = telemetry.scrub_text("Read ~/Music/Secret.mp3 today")
        self.assertEqual(home, "Read [path] today")
        frame = telemetry.scrub_text("/Users/dj/src/server.py")
        self.assertEqual(frame, "server.py")
        self.assertEqual(telemetry.scrub_text("SeratoLibrary/1.0"), "SeratoLibrary/1.0")

    def test_before_send_scrubs_nested_paths(self) -> None:
        """Scrub an exception, a frame, a breadcrumb, and user fields.

        Consent is on, so the hook returns the event instead of dropping
        it. The request and the email are removed. The audio path is gone.

        Returns:
            None. The test fails if the path, the email, or the request remains.
        """
        self._opt_in()
        event = {
            "message": "failed /Users/dj/Music/Secret Track.mp3",
            "server_name": "studio-mac.local",
            "tags": {"app": "/Users/dj/Music/Secret Track.mp3", "level": "error"},
            "user": {"id": "11111111-1111-4111-8111-111111111111", "email": "dj@example.com", "ip_address": "203.0.113.4"},
            "request": {"data": {"name": "Secret Track", "portable_id": "/Users/dj/Music/Secret Track.mp3"}},
            "extra": {"path": "/Users/dj/Music/Secret Track.mp3"},
            "exception": {
                "values": [
                    {
                        "value": "open /Users/dj/Music/Secret Track.mp3",
                        "stacktrace": {
                            "frames": [
                                {
                                    "abs_path": "/Users/dj/src/server.py",
                                    "filename": "/Users/dj/src/server.py",
                                    "function": "load",
                                    "vars": {"path": "/Users/dj/Music/Secret Track.mp3"},
                                    "context_line": "path = '/Users/dj/Music/Secret Track.mp3'",
                                }
                            ]
                        },
                    }
                ]
            },
            "breadcrumbs": {
                "values": [
                    {"message": "open -R /Users/dj/Music/Secret Track.mp3", "data": {"subprocess.cwd": "/Users/dj/Music"}}
                ]
            },
        }
        scrubbed = telemetry.before_send(event, {"exc_info": ("RuntimeError", RuntimeError("x"), None)})
        self.assertIsNotNone(scrubbed)
        blob = json.dumps(scrubbed)
        self.assertNotIn("/Users/dj", blob)
        self.assertNotIn("Secret Track", blob)
        self.assertNotIn("dj@example.com", blob)
        self.assertNotIn("203.0.113.4", blob)
        self.assertNotIn("request", blob)
        self.assertNotIn("portable_id", blob)
        self.assertIn("[path]", blob)
        self.assertIn("server.py", blob)
        self.assertEqual(scrubbed["server_name"], "local")
        self.assertEqual(scrubbed["tags"]["app"], telemetry.APP_NAME)
        self.assertEqual(scrubbed["tags"]["level"], "error")
        self.assertEqual(scrubbed["user"], {"id": "11111111-1111-4111-8111-111111111111"})
        frame = scrubbed["exception"]["values"][0]["stacktrace"]["frames"][0]
        self.assertNotIn("vars", frame)
        self.assertNotIn("context_line", frame)

    def test_sdk_delivers_the_scrubbed_event(self) -> None:
        """Run the hook inside sentry-sdk and keep the path out of the transport.

        The transport stores the event the SDK decided to send. Consent is
        on. The client is closed afterwards.

        Returns:
            None. The test fails if the transport sees the audio path.
        """
        self._opt_in()
        delivered: list[dict[str, object]] = []
        sentry_sdk.init(
            dsn="https://public@o0.ingest.sentry.io/0",
            transport=lambda event: delivered.append(event),
            before_send=telemetry.before_send,
            send_default_pii=False,
            include_local_variables=False,
            include_source_context=False,
            server_name="local",
            environment="local",
            release=app_config.APP_VERSION,
            default_integrations=False,
        )
        try:
            raise RuntimeError("open /Users/dj/Music/Secret Track.mp3")
        except RuntimeError:
            sentry_sdk.capture_exception()
        sentry_sdk.flush(timeout=2)
        self.assertTrue(delivered)
        blob = json.dumps(delivered)
        self.assertNotIn("/Users/dj/Music", blob)
        self.assertNotIn("Secret Track", blob)
        self.assertIn("[path]", blob)
        self.assertEqual(delivered[0]["tags"]["app"], telemetry.APP_NAME)

    def test_sentry_init_keeps_framework_hooks_off(self) -> None:
        """Initialize Sentry without request hooks or personal data.

        ``sentry_sdk.init`` is patched, so no client starts and no request
        leaves the process. Auto-enabling stays off so a framework
        integration cannot attach.

        Returns:
            None. The test fails if a privacy flag is left at the SDK default.
        """
        with mock.patch("sentry_sdk.init") as init, mock.patch("sentry_sdk.set_tag") as set_tag:
            telemetry._init_sentry("https://public@o0.ingest.sentry.io/0")
        set_tag.assert_called_once_with("app", telemetry.APP_NAME)
        kwargs = init.call_args.kwargs
        self.assertFalse(kwargs["auto_enabling_integrations"])
        self.assertFalse(kwargs["send_default_pii"])
        self.assertFalse(kwargs["include_local_variables"])
        self.assertFalse(kwargs["include_source_context"])
        self.assertEqual(kwargs["server_name"], "local")
        self.assertEqual(kwargs["environment"], "local")
        self.assertEqual(kwargs["max_request_body_size"], "never")
        self.assertIs(kwargs["spotlight"], False)
        self.assertEqual(kwargs["traces_sample_rate"], 0)
        disabled = {type(item).__name__ for item in kwargs["disabled_integrations"]}
        self.assertEqual(disabled, {"ArgvIntegration", "LoggingIntegration"})


@unittest.skipUnless(Posthog is not None, "posthog is not installed")
class PosthogHookTests(TelemetryCase):
    """The real PostHog client calls the allowlist hook before upload."""

    def test_posthog_before_send_strips_library_fields(self) -> None:
        """Drop a title and a path from the batch the SDK would upload.

        ``batch_post`` is patched, so the test does not open a socket.
        GeoIP stays disabled.

        Returns:
            None. The test fails if the title or the path is in the batch.
        """
        self._opt_in()
        install_id = app_config.load_settings().install_id
        self.assertIsNotNone(install_id)
        with mock.patch("posthog.client.batch_post") as batch_post, mock.patch("posthog.consumer.batch_post"):
            client = Posthog(
                "phc_test",
                host="https://us.i.posthog.com",
                disable_geoip=True,
                enable_exception_autocapture=False,
                enable_local_evaluation=False,
                capture_exception_code_variables=False,
                sync_mode=True,
                before_send=telemetry.limit_posthog_event,
            )
            try:
                client.capture(
                    "library_scanned",
                    distinct_id=install_id,
                    properties={
                        "track_count_bucket": "10-49",
                        "app": "other-app",
                        "name": "Secret Track",
                        "path": "/Users/dj/Music/Secret Track.mp3",
                    },
                )
            finally:
                client.shutdown()
        batch_post.assert_called_once()
        batch = batch_post.call_args.kwargs["batch"]
        blob = json.dumps(batch)
        self.assertNotIn("Secret Track", blob)
        self.assertNotIn("/Users/dj", blob)
        self.assertNotIn("other-app", blob)
        self.assertIn("10-49", blob)
        self.assertEqual(batch[0]["properties"]["app"], telemetry.APP_NAME)
        self.assertTrue(batch[0]["properties"]["$geoip_disable"])


class BucketTests(unittest.TestCase):
    """Track-count buckets hide the exact library size."""

    def test_boundaries(self) -> None:
        """Map the boundary counts onto the published labels.

        Returns:
            None. The test fails if a boundary falls in the wrong bucket.
        """
        cases = {
            0: "0",
            1: "1-9",
            9: "1-9",
            10: "10-49",
            49: "10-49",
            50: "50-99",
            99: "50-99",
            100: "100-499",
            499: "100-499",
            500: "500-999",
            999: "500-999",
            1000: "1000-4999",
            4999: "1000-4999",
            5000: "5000-9999",
            9999: "5000-9999",
            10000: "10000+",
            10001: "10000+",
        }
        for count, label in cases.items():
            with self.subTest(count=count):
                self.assertEqual(telemetry.track_count_bucket(count), label)

    def test_bool_is_not_a_count(self) -> None:
        """Reject True, because bool is a subclass of int.

        Returns:
            None. The test fails if True is bucketed as 1.
        """
        with self.assertRaises(TypeError):
            telemetry.track_count_bucket(True)  # type: ignore[arg-type]


class PageContractTests(unittest.TestCase):
    """The page and the settings response use the same fields."""

    def test_page_asks_the_consent_question(self) -> None:
        """Show the consent question and the log actions in the page source.

        This does not execute the script. It ties the HTML the person
        reads to the fields ``app.js`` sends and reads.

        Returns:
            None. The test fails if the question or a field name is missing.
        """
        page = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("Share anonymous usage stats and crash reports?", page)
        self.assertIn("Open logs folder", page)
        self.assertIn("Copy logs", page)
        self.assertIn("needs_consent_prompt", script)
        self.assertIn("telemetry_consent", script)
        self.assertIn("/api/settings", script)
        self.assertIn("/api/logs", script)
        self.assertNotIn("innerHTML", script)
        self.assertNotIn("posthog-js", script)
        self.assertNotIn("sentry-js", page)
        self.assertIn("the app name", page)
        privacy = (ROOT / "PRIVACY.md").read_text(encoding="utf-8")
        architecture = (ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")
        self.assertIn(telemetry.APP_NAME, privacy)
        self.assertIn(telemetry.APP_NAME, architecture)
        self.assertIn("app=serato-library-manager", architecture)


class ApiPrivacyTests(unittest.TestCase):
    """HTTP coverage for settings and for events that must stay anonymous.

    The server is the same handler the page uses, on an ephemeral port,
    against a temporary library.
    """

    def setUp(self) -> None:
        """Start a temporary library and server, and isolate settings.

        Returns:
            None.
        """
        self.library = TempLibrary()
        self.library.__enter__()
        self._tmp = tempfile.TemporaryDirectory()
        config = Path(self._tmp.name) / "config"
        logs = Path(self._tmp.name) / "logs"
        config.mkdir()
        logs.mkdir()
        self._env = mock.patch.dict(
            os.environ,
            {
                app_config.CONFIG_ENV: str(config),
                app_config.LOG_ENV: str(logs),
                "POSTHOG_KEY": "phc_test",
                "SENTRY_DSN": "",
                "POSTHOG_HOST": "",
            },
        )
        self._env.start()
        self.fake = FakePosthog()
        self._factory = mock.patch("telemetry._make_posthog", return_value=self.fake)
        self._factory.start()
        telemetry.shutdown()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), __import__("server").Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.httpd.server_address
        self.base = f"http://{host}:{port}"

    def tearDown(self) -> None:
        """Stop the server, the fake client, and the temporary library.

        Returns:
            None.
        """
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=3)
        telemetry.shutdown()
        self._factory.stop()
        self._env.stop()
        app_log.close_files()
        self._tmp.cleanup()
        self.library.__exit__(None, None, None)

    def _request(self, path: str, payload: dict | None = None) -> tuple[int, dict]:
        """Send one JSON request.

        Args:
            path: Absolute path.
            payload: JSON body for POST. None sends GET.

        Returns:
            The status code and the decoded object.
        """
        data = None
        headers: dict[str, str] = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.base + path, data=data, headers=headers)
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_prompt_defaults_off_and_false_round_trips(self) -> None:
        """Show the prompt until a False choice is saved.

        The first GET has a null consent. POST False comes back as False,
        not null, and does not record an analytics event.

        Returns:
            None. The test fails if the default is on or False is lost.
        """
        import urllib.error

        status, payload = self._request("/api/settings")
        self.assertEqual(status, 200)
        self.assertIsNone(payload["telemetry_consent"])
        self.assertTrue(payload["needs_consent_prompt"])
        self.assertTrue(payload["telemetry_configured"])
        status, saved = self._request("/api/settings", {"telemetry_consent": False})
        self.assertEqual(status, 200)
        self.assertIs(saved["telemetry_consent"], False)
        self.assertFalse(saved["needs_consent_prompt"])
        self.assertEqual(self.fake.events, [])
        request = urllib.request.Request(
            self.base + "/api/settings",
            data=json.dumps({"telemetry_consent": 0}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request)
        self.assertEqual(caught.exception.code, 400)
        caught.exception.close()
        self.assertIs(payload["rekordbox"]["hot_loops"], False)
        self.assertIs(payload["rekordbox"]["memory_cues"], True)
        self.assertEqual(payload["rekordbox"]["key_notation"], "asis")

    def test_rekordbox_settings_round_trip_and_reject_bad_types(self) -> None:
        """Save the export bar and refuse a value of the wrong type.

        False for memory cues stays false. A later sharing choice keeps
        that bar. An integer, an unknown field, and a bad notation return
        400 and leave the file as it was.

        Returns:
            None. The test fails if a bad body is stored or false is lost.
        """
        import urllib.error

        status, saved = self._request(
            "/api/settings",
            {
                "rekordbox": {
                    "hot_loops": True,
                    "memory_cues": False,
                    "key_notation": "camelot",
                }
            },
        )
        self.assertEqual(status, 200)
        self.assertIsNone(saved["telemetry_consent"])
        self.assertIs(saved["rekordbox"]["hot_loops"], True)
        self.assertIs(saved["rekordbox"]["memory_cues"], False)
        self.assertEqual(saved["rekordbox"]["key_notation"], "camelot")
        status, narrowed = self._request(
            "/api/settings",
            {"rekordbox": {"hot_loops": False}},
        )
        self.assertEqual(status, 200)
        self.assertIs(narrowed["rekordbox"]["hot_loops"], False)
        self.assertIs(narrowed["rekordbox"]["memory_cues"], False)
        self.assertEqual(narrowed["rekordbox"]["key_notation"], "camelot")
        bad_bodies = (
            {"rekordbox": {"hot_loops": 1}},
            {"rekordbox": {"memory_cues": 0}},
            {"rekordbox": {"key_notation": "open"}},
            {"rekordbox": {"key_notation": True}},
            {"rekordbox": {"nope": True}},
            {"rekordbox": {}},
            {"rekordbox": "yes"},
            {"library_path": "/tmp"},
            {},
        )
        for body in bad_bodies:
            request = urllib.request.Request(
                self.base + "/api/settings",
                data=json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(request)
            self.assertEqual(caught.exception.code, 400, body)
            caught.exception.close()
        status, still = self._request("/api/settings")
        self.assertEqual(status, 200)
        self.assertIs(still["rekordbox"]["memory_cues"], False)
        self.assertEqual(still["rekordbox"]["key_notation"], "camelot")
        status, consented = self._request("/api/settings", {"telemetry_consent": False})
        self.assertEqual(status, 200)
        self.assertIs(consented["telemetry_consent"], False)
        self.assertIs(consented["rekordbox"]["memory_cues"], False)
        self.assertEqual(consented["rekordbox"]["key_notation"], "camelot")

    def test_crate_create_does_not_send_the_name_without_consent(self) -> None:
        """Create a crate without an analytics event when sharing is off.

        The crate name is in the request. The fake client stays empty.

        Returns:
            None. The test fails if any event is recorded.
        """
        status, _payload = self._request(
            "/api/crate",
            {"action": "create", "name": "Friday Warmup", "space": "Serato Library"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(self.fake.events, [])

    def test_crate_create_sends_the_action_only_after_opt_in(self) -> None:
        """Send crate_created after opt-in, without the crate name.

        The backup event is also allowlisted and has no path.

        Returns:
            None. The test fails if the crate name appears in an event.
        """
        self._request("/api/settings", {"telemetry_consent": True})
        self.fake.events.clear()
        status, _payload = self._request(
            "/api/crate",
            {"action": "create", "name": "Friday Warmup", "space": "Serato Library"},
        )
        self.assertEqual(status, 200)
        names = [event[0] for event in self.fake.events]
        self.assertIn("crate_created", names)
        blob = json.dumps(self.fake.events)
        self.assertNotIn("Friday Warmup", blob)
        self.assertNotIn("master.sqlite", blob)

    def test_merge_event_has_no_library_fields(self) -> None:
        """Record duplicates_merged after opt-in, without titles or paths.

        A preview records nothing. A confirmed merge records the event name
        only. The fixture title and file name stay out of the properties.
        With sharing off, the same merge records nothing.

        Returns:
            None. The test fails if a title or a path is attached.
        """
        status, _payload = self._request(
            "/api/duplicates/merge",
            {"keep_id": 1, "space": "Serato Library", "confirm": True},
        )
        self.assertEqual(status, 200)
        self.assertEqual(self.fake.events, [])
        self._request("/api/settings", {"telemetry_consent": True})
        self.fake.events.clear()
        with open_database(library.MASTER) as conn:
            conn.execute(
                """
                INSERT INTO asset
                    (id, name, artist, album, length_ms, file_name, portable_id, location_id, time_added)
                VALUES (2, 'Same', 'Artist', 'Album', 180500, 'same-b.mp3', 'Music/same-b.mp3', 1, 11)
                """
            )
            conn.execute("INSERT INTO space_asset (id, asset_id, space_id) VALUES (2, 2, 1)")
        __import__("server").invalidate()
        status, preview = self._request(
            "/api/duplicates/merge",
            {"keep_id": 1, "preview": True},
        )
        self.assertEqual(status, 200)
        self.assertTrue(preview["preview"])
        self.assertEqual(self.fake.events, [])
        status, _merged = self._request(
            "/api/duplicates/merge",
            {"keep_id": 1, "confirm": True},
        )
        self.assertEqual(status, 200)
        names = [event[0] for event in self.fake.events]
        self.assertIn("duplicates_merged", names)
        blob = json.dumps(self.fake.events)
        self.assertNotIn("Same", blob)
        self.assertNotIn("same-b.mp3", blob)
        self.assertNotIn("Music", blob)

    def test_copy_logs_returns_local_text(self) -> None:
        """Return log text from GET /api/logs and open the folder without a path.

        The open route is stubbed so no file manager starts. The JSON
        error and success bodies do not include the directory.

        Returns:
            None. The test fails if the log line is missing or a path is returned.
        """
        import app_log

        app_log.configure()
        app_log.logger.info("hello from the test")
        status, payload = self._request("/api/logs")
        self.assertEqual(status, 200)
        self.assertIn("hello from the test", payload["text"])
        self.assertNotIn("path", payload)
        with mock.patch("app_log.sys_platform", return_value="linux"):
            with mock.patch("subprocess.run", return_value=mock.Mock(returncode=0)) as run:
                status, opened = self._request("/api/logs/open", {})
        self.assertEqual(status, 200)
        self.assertTrue(opened["ok"])
        self.assertNotIn("path", opened)
        self.assertEqual(run.call_args.args[0][0], "xdg-open")


if __name__ == "__main__":
    unittest.main()
