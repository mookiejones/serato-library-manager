"""Related-track sidecar, suggestions, and HTTP API.

The suite uses a temporary Serato database and a temporary settings
directory. It does not open the live library and it does not upload
telemetry.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import threading
import unittest
import urllib.parse
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import app_config
import library
import related
import server
import telemetry
from tests.fixture import TempLibrary, open_database

ROOT = Path(__file__).resolve().parents[1]


def _track(
    asset_id: int,
    *,
    path: str,
    title: str,
    artist: str = "DJ",
    length_ms: int | None = 180000,
    bpm: float | None = None,
    key: str = "",
    crates: frozenset[int] = frozenset(),
) -> related.CatalogTrack:
    """Build one in-memory catalog track.

    Args:
        asset_id: Asset id.
        path: Canonical path.
        title: Title.
        artist: Artist. Defaults to ``DJ``.
        length_ms: Length in milliseconds.
        bpm: Tempo, or None.
        key: Key text.
        crates: Crate ids counted toward a shared-crate score.

    Returns:
        A frozen catalog track. Nothing is written.
    """
    return related.CatalogTrack(
        asset_id=asset_id,
        path=path,
        portable_id=path,
        title=title,
        artist=artist,
        length_ms=length_ms,
        bpm=bpm,
        key=key,
        file_name=Path(path).name,
        crate_ids=crates,
    )


class RankingTests(unittest.TestCase):
    """Score keys, tempos, and crates without a database."""

    def test_camelot_relations(self) -> None:
        """Map same, relative, adjacent, and incompatible keys.

        Traditional names use Serato's key table. The wheel wraps from
        12 to 1. A diagonal step is not a match. Nothing is stored.

        Returns:
            None. The test fails if a relation is classified differently.
        """
        self.assertEqual(related.key_relation("8A", "8A"), "same")
        self.assertEqual(related.key_relation("8A", "8B"), "relative")
        self.assertEqual(related.key_relation("Am", "C"), "relative")
        self.assertEqual(related.key_relation("8A", "7A"), "adjacent")
        self.assertEqual(related.key_relation("8A", "9A"), "adjacent")
        self.assertEqual(related.key_relation("12A", "1A"), "adjacent")
        self.assertEqual(related.key_relation("1A", "12A"), "adjacent")
        self.assertIsNone(related.key_relation("8A", "9B"))
        self.assertIsNone(related.key_relation("1A", "4A"))
        self.assertIsNone(related.key_relation("", "8A"))

    def test_bpm_window_includes_half_and_double_time(self) -> None:
        """Accept a tempo inside 6 percent, including half and double time.

        106 is 6 percent above 100. 107 is outside that window. 50 is
        exact half time and 200 is exact double time. Nothing is stored.

        Returns:
            None. The test fails if the window or the label changes.
        """
        self.assertEqual(related.BPM_TOLERANCE, 0.06)
        edge = related.bpm_relation(100, 106)
        self.assertIsNotNone(edge)
        assert edge is not None
        self.assertEqual(edge[0], "tempo")
        self.assertIsNone(related.bpm_relation(100, 107))
        half = related.bpm_relation(128, 64)
        self.assertIsNotNone(half)
        assert half is not None
        self.assertEqual(half[0], "half")
        doubled = related.bpm_relation(100, 200)
        self.assertIsNotNone(doubled)
        assert doubled is not None
        self.assertEqual(doubled[0], "double")
        near_half = related.bpm_relation(100, 53)
        self.assertIsNotNone(near_half)
        assert near_half is not None
        self.assertEqual(near_half[0], "half")

    def test_rank_orders_key_then_tempo_then_crates(self) -> None:
        """Put a same-key exact tempo ahead of a weaker match.

        Four shared crates score the same as three. A track with no
        key, no tempo, and no crate is omitted. Already linked paths
        and the anchor are omitted. Nothing is stored.

        Returns:
            None. The test fails if the order or the cap changes.
        """
        anchor = _track(1, path="/music/anchor.mp3", title="Anchor", bpm=128, key="8A", crates=frozenset({1, 2, 3, 4}))
        best = _track(2, path="/music/best.mp3", title="Best", bpm=128, key="8A", crates=frozenset({1}))
        relative = _track(3, path="/music/relative.mp3", title="Relative", bpm=128, key="8B")
        adjacent = _track(4, path="/music/adjacent.mp3", title="Adjacent", bpm=140, key="9A")
        crates_only = _track(
            5, path="/music/crates.mp3", title="Crates", crates=frozenset({1, 2, 3, 4})
        )
        nowhere = _track(6, path="/music/no.mp3", title="No")
        linked = _track(7, path="/music/linked.mp3", title="Linked", bpm=128, key="8A")
        ranked = related.rank_suggestions(
            anchor,
            [anchor, best, relative, adjacent, crates_only, nowhere, linked],
            {"/music/linked.mp3"},
        )
        self.assertEqual([item["title"] for item in ranked], ["Best", "Relative", "Adjacent", "Crates"])
        self.assertIn("same key", ranked[0]["reasons"])
        self.assertIn("BPM match", ranked[0]["reasons"])
        self.assertIn("1 shared crate", ranked[0]["reasons"])
        self.assertIn("relative key", ranked[1]["reasons"])
        self.assertIn("adjacent key", ranked[2]["reasons"])
        self.assertEqual(ranked[3]["reasons"], ["4 shared crates"])
        crate_score = related.score_pair(anchor, crates_only)
        self.assertIsNotNone(crate_score)
        assert crate_score is not None
        self.assertEqual(crate_score[0], related.SCORE_CRATE_CAP)

    def test_suggestion_list_stops_at_twelve(self) -> None:
        """Return at most twelve suggestions.

        Fifteen same-key tracks are offered. The extra three are cut
        after the score sort. Nothing is stored.

        Returns:
            None. The test fails if the limit changes.
        """
        anchor = _track(1, path="/music/anchor.mp3", title="Anchor", key="5A")
        catalog = [anchor]
        for index in range(2, 17):
            catalog.append(_track(index, path=f"/music/{index}.mp3", title=f"T{index:02d}", key="5A"))
        ranked = related.rank_suggestions(anchor, catalog, set())
        self.assertEqual(len(ranked), related.SUGGEST_LIMIT)
        self.assertEqual(ranked[0]["title"], "T02")


class SidecarTests(unittest.TestCase):
    """Write the sidecar beside a temporary settings directory."""

    def setUp(self) -> None:
        """Point settings and the Serato library at temporary files.

        Returns:
            None.
        """
        self._dir = tempfile.TemporaryDirectory()
        self.config = Path(self._dir.name) / "config"
        self.config.mkdir()
        self._env = mock.patch.dict(os.environ, {app_config.CONFIG_ENV: str(self.config)})
        self._env.start()
        self.library = TempLibrary()
        self.library.__enter__()

    def tearDown(self) -> None:
        """Close the fixture library and delete the temporary directory.

        Returns:
            None.
        """
        self.library.__exit__(None, None, None)
        self._env.stop()
        self._dir.cleanup()

    def test_schema_matches_the_documented_columns(self) -> None:
        """Create version 1 with the published column names.

        Opens the sidecar after one link is saved, then reads
        ``user_version`` and ``table_info``. The doc names every column.
        The live Serato file is not the sidecar.

        Returns:
            None. The test fails if a column is missing from the file or the doc.
        """
        related.add_link(
            "/tmp/serato-related-a.mp3",
            "/tmp/serato-related-b.mp3",
            mutual=False,
            note="blend out of",
            rating=4,
            source_title="Alpha",
            source_artist="One",
            source_length_ms=200000,
            target_title="Beta",
            target_artist="Two",
            target_length_ms=210000,
        )
        self.assertEqual(related.related_db_path(), self.config / "related.sqlite")
        self.assertNotEqual(related.related_db_path(), Path(library.MASTER))
        conn = sqlite3.connect(related.related_db_path())
        try:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            track_columns = tuple(
                row[1] for row in conn.execute("PRAGMA table_info(track)").fetchall()
            )
            link_columns = tuple(
                row[1] for row in conn.execute("PRAGMA table_info(link)").fetchall()
            )
        finally:
            conn.close()
        self.assertEqual(version, related.SCHEMA_VERSION)
        self.assertEqual(track_columns, related.TRACK_COLUMNS)
        self.assertEqual(link_columns, related.LINK_COLUMNS)
        doc = (ROOT / "docs" / "related-tracks.md").read_text(encoding="utf-8")
        for column in related.TRACK_COLUMNS + related.LINK_COLUMNS:
            self.assertIn(f"`{column}`", doc)
        self.assertIn("~/Library/Application Support/Serato Library/related.sqlite", doc)
        self.assertIn("%APPDATA%\\Serato Library\\related.sqlite", doc)
        self.assertIn("6 percent", doc)
        self.assertIn("third shared crate", doc)
        self.assertIn("related.update_path", doc)
        self.assertIn("library.update_related_path", doc)

    def test_one_way_link_is_hidden_from_the_target(self) -> None:
        """Show a one-way link only on the source track.

        The note and the rating round-trip. The target overview has no
        saved row. ``master.sqlite`` is not backed up.

        Returns:
            None. The test fails if the target lists the link.
        """
        saved = related.add_link(
            "Music/same-a.mp3",
            "Music/same-b.mp3",
            mutual=False,
            note="  blend out of  ",
            rating=5,
        )
        self.assertFalse(saved["mutual"])
        source = related.overview("Music/same-a.mp3")
        target = related.overview("Music/same-b.mp3")
        self.assertEqual(len(source["saved"]), 1)
        link = source["saved"][0]
        self.assertEqual(link["note"], "blend out of")
        self.assertEqual(link["rating"], 5)
        self.assertEqual(link["direction"], "outgoing")
        self.assertFalse(link["mutual"])
        self.assertEqual(link["track"]["asset_id"], 2)
        self.assertEqual(target["saved"], [])
        self.assertFalse((self.library.root / "Backups").exists())

    def test_two_way_link_is_visible_from_both_tracks(self) -> None:
        """Show one two-way row from either path.

        Saving the opposite direction as two-way keeps a single row.
        Nothing is written to the Serato crate list.

        Returns:
            None. The test fails if either side misses the link.
        """
        first = related.add_link("Music/same-a.mp3", "Music/same-b.mp3", mutual=True, note="together")
        second = related.add_link("Music/same-b.mp3", "Music/same-a.mp3", mutual=True, note="together")
        self.assertEqual(first["id"], second["id"])
        for portable in ("Music/same-a.mp3", "Music/same-b.mp3"):
            view = related.overview(portable)
            self.assertEqual(len(view["saved"]), 1)
            self.assertTrue(view["saved"][0]["mutual"])
            self.assertEqual(view["saved"][0]["direction"], "mutual")
        conn = sqlite3.connect(related.related_db_path())
        try:
            count = conn.execute("SELECT COUNT(*) FROM link").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(count, 1)

    def test_update_path_and_fallback_keep_the_link(self) -> None:
        """Follow a move by explicit update and by a unique fallback.

        ``update_path`` is the file-manager hook. A later move that skips
        the hook still resolves when the title, artist, and length match
        one row. An ambiguous pair is left in place. A colliding path is
        refused.

        Returns:
            None. The test fails if a link is dropped or a row is stolen.
        """
        related.add_link(
            "/tmp/serato-related-old.mp3",
            "/tmp/serato-related-other.mp3",
            mutual=True,
            source_title="Moved",
            source_artist="Artist",
            source_length_ms=123000,
            target_title="Other",
            target_artist="Artist",
            target_length_ms=124000,
        )
        self.assertTrue(
            library.update_related_path("/tmp/serato-related-old.mp3", "/tmp/serato-related-new.mp3")
        )
        self.assertFalse(related.update_path("/tmp/missing-old.mp3", "/tmp/missing-new.mp3"))
        moved = related.overview("/tmp/serato-related-new.mp3")
        self.assertEqual(moved["saved"][0]["track"]["title"], "Other")
        related.add_link(
            "/tmp/serato-related-copy.mp3",
            "/tmp/serato-related-copy-b.mp3",
            mutual=False,
            source_title="Copy",
            source_artist="Artist",
            source_length_ms=123000,
            target_title="Copy B",
            target_artist="Artist",
            target_length_ms=125000,
        )
        conn = sqlite3.connect(related.related_db_path())
        try:
            conn.execute(
                "UPDATE track SET title = ? WHERE path = ?",
                ("Moved", related.identity_path("/tmp/serato-related-copy.mp3")),
            )
            conn.commit()
        finally:
            conn.close()
        ambiguous = related.overview(
            "/tmp/serato-related-third.mp3",
            title="Moved",
            artist="Artist",
            length_ms=123000,
        )
        self.assertEqual(ambiguous["saved"], [])
        self.assertTrue(_path_exists_in_sidecar("/tmp/serato-related-new.mp3"))
        self.assertTrue(_path_exists_in_sidecar("/tmp/serato-related-copy.mp3"))
        with self.assertRaises(library.LibraryError) as caught:
            related.update_path("/tmp/serato-related-new.mp3", "/tmp/serato-related-other.mp3")
        self.assertEqual(caught.exception.status, 409)
        self.assertTrue(_path_exists_in_sidecar("/tmp/serato-related-new.mp3"))

    def test_unique_fallback_rewrites_the_stored_path(self) -> None:
        """Adopt a new path when only one title, artist, and length match.

        The overview call is what the page does after a move that did not
        go through ``update_path``. The stored path becomes the new one.

        Returns:
            None. The test fails if the old path is still the only key.
        """
        related.add_link(
            "/tmp/serato-related-before.mp3",
            "/tmp/serato-related-dest.mp3",
            mutual=False,
            note="acapella over",
            source_title="Unique",
            source_artist="Vocal",
            source_length_ms=90000,
            target_title="Bed",
            target_artist="Instrumental",
            target_length_ms=91000,
        )
        view = related.overview(
            "/tmp/serato-related-after.mp3",
            title="Unique",
            artist="Vocal",
            length_ms=90050,
        )
        self.assertEqual(view["saved"][0]["note"], "acapella over")
        self.assertEqual(view["saved"][0]["track"]["title"], "Bed")
        self.assertFalse(_path_exists_in_sidecar("/tmp/serato-related-before.mp3"))
        self.assertTrue(_path_exists_in_sidecar("/tmp/serato-related-after.mp3"))

    def test_rejects_bad_link_fields(self) -> None:
        """Refuse a self link, a bad rating, and a long note.

        No sidecar row is required for the rejection. A boolean rating is
        not a star count.

        Returns:
            None. The test fails if a bad value is stored.
        """
        with self.assertRaises(library.LibraryError):
            related.add_link("Music/same-a.mp3", "Music/same-a.mp3", mutual=True)
        with self.assertRaises(library.LibraryError):
            related.add_link("Music/same-a.mp3", "Music/same-b.mp3", mutual=True, rating=6)
        with self.assertRaises(library.LibraryError):
            related.add_link("Music/same-a.mp3", "Music/same-b.mp3", mutual=True, rating=True)
        with self.assertRaises(library.LibraryError):
            related.add_link("Music/same-a.mp3", "Music/same-b.mp3", mutual="yes")
        with self.assertRaises(library.LibraryError):
            related.add_link(
                "Music/same-a.mp3",
                "Music/same-b.mp3",
                mutual=False,
                note="x" * 501,
            )
        self.assertFalse(related.related_db_path().exists())

    def test_remove_deletes_the_link_only(self) -> None:
        """Delete a link and keep the identity row.

        A missing id is a 404. The path can still be resolved afterward.

        Returns:
            None. The test fails if the identity row disappears.
        """
        saved = related.add_link("Music/same-a.mp3", "Music/same-b.mp3", mutual=False)
        related.remove_link(saved["id"])
        view = related.overview("Music/same-a.mp3")
        self.assertEqual(view["saved"], [])
        self.assertTrue(view["track"]["in_library"])
        conn = sqlite3.connect(related.related_db_path())
        try:
            tracks = conn.execute("SELECT COUNT(*) FROM track").fetchone()[0]
        finally:
            conn.close()
        self.assertGreaterEqual(tracks, 1)
        with self.assertRaises(library.LibraryError) as caught:
            related.remove_link(saved["id"])
        self.assertEqual(caught.exception.status, 404)

    def test_suggestions_skip_generated_crates(self) -> None:
        """Ignore a ``Related - `` crate when ranking shared crates.

        The two inserted tracks have no key and no tempo. Sharing only a
        generated crate produces no suggestion. A normal crate does.

        Returns:
            None. The test fails if the generated crate changes the score.
        """
        with open_database(library.MASTER) as conn:
            conn.execute(
                """
                INSERT INTO asset (id, name, artist, bpm, key, length_ms, portable_id, file_name, location_id)
                VALUES
                    (3, 'Left', 'Pair', NULL, '', 100000, 'Music/left.mp3', 'left.mp3', 1),
                    (4, 'Right', 'Pair', NULL, '', 110000, 'Music/right.mp3', 'right.mp3', 1)
                """
            )
            conn.execute("INSERT INTO space_asset (id, asset_id, space_id) VALUES (3, 3, 1)")
            conn.execute("INSERT INTO space_asset (id, asset_id, space_id) VALUES (4, 4, 1)")
        server.invalidate()
        created = library.crate_action({"action": "create", "name": "Related - Ignore"})
        library.crate_action({"action": "add", "id": created["id"], "asset": 3})
        library.crate_action({"action": "add", "id": created["id"], "asset": 4})
        before = related.overview("Music/left.mp3")
        self.assertEqual(before["suggested"], [])
        warmup = library.crate_action({"action": "create", "name": "Warmup"})
        library.crate_action({"action": "add", "id": warmup["id"], "asset": 3})
        library.crate_action({"action": "add", "id": warmup["id"], "asset": 4})
        server.invalidate()
        after = related.overview("Music/left.mp3")
        self.assertEqual([item["title"] for item in after["suggested"]], ["Right"])
        self.assertEqual(after["suggested"][0]["reasons"], ["1 shared crate"])

    def test_refresh_crate_replaces_membership(self) -> None:
        """Create ``Related - Same`` and drop a track after the link is removed.

        The anchor stays out of the crate. The second refresh removes the
        track that is no longer linked. Serato's backup runs because this
        writes the library.

        Returns:
            None. The test fails if the crate membership is stale.
        """
        related.add_link("Music/same-a.mp3", "Music/same-b.mp3", mutual=True)
        first = related.refresh_crate("Music/same-a.mp3")
        self.assertTrue(first["created"])
        self.assertEqual(first["name"], "Related - Same")
        self.assertEqual(first["added"], [2])
        self.assertTrue((self.library.root / "Backups").is_dir())
        related.remove_link(related.overview("Music/same-a.mp3")["saved"][0]["id"])
        second = related.refresh_crate("Music/same-a.mp3")
        self.assertFalse(second["created"])
        self.assertEqual(second["removed"], [2])
        self.assertEqual(second["added"], [])
        self.assertEqual(_crate_members(first["id"]), set())

    def test_newer_sidecar_is_refused(self) -> None:
        """Stop when ``user_version`` is newer than this app.

        The file is created, then the version is raised. A read must fail
        before it rewrites the tables.

        Returns:
            None. The test fails if the newer file is treated as version 1.
        """
        related.add_link("Music/same-a.mp3", "Music/same-b.mp3", mutual=False)
        conn = sqlite3.connect(related.related_db_path())
        try:
            conn.execute("PRAGMA user_version = 2")
            conn.commit()
        finally:
            conn.close()
        with self.assertRaises(library.LibraryError):
            related.overview("Music/same-a.mp3")


class ApiTests(unittest.TestCase):
    """Exercise ``/api/related`` over HTTP."""

    def setUp(self) -> None:
        """Start the fixture library, the sidecar directory, and the server.

        Returns:
            None.
        """
        self._dir = tempfile.TemporaryDirectory()
        self.config = Path(self._dir.name) / "config"
        self.config.mkdir()
        self._env = mock.patch.dict(os.environ, {app_config.CONFIG_ENV: str(self.config)})
        self._env.start()
        self.library = TempLibrary()
        self.library.__enter__()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.httpd.server_address
        self.base = f"http://{host}:{port}"

    def tearDown(self) -> None:
        """Stop the server and delete the temporary files.

        Returns:
            None.
        """
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=3)
        self.library.__exit__(None, None, None)
        self._env.stop()
        self._dir.cleanup()

    def request(self, path: str, payload: dict | None = None) -> tuple[int, dict]:
        """Send one JSON request.

        Args:
            path: Absolute path and query.
            payload: JSON body for POST. None sends GET.

        Returns:
            The status code and the decoded JSON object.
        """
        import urllib.error
        import urllib.request

        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.base + path, data=data, headers=headers)
        try:
            with urllib.request.urlopen(request) as response:
                body = response.read()
                status = response.status
        except urllib.error.HTTPError as exc:
            body = exc.read()
            status = exc.code
            exc.close()
        return status, json.loads(body.decode("utf-8"))

    def test_get_returns_saved_and_suggested(self) -> None:
        """Return the other fixture track as a suggestion, then as a saved link.

        The query uses the Serato portable id. The page script names the
        same JSON fields. No backup is made by the read or the add.

        Returns:
            None. The test fails if the suggestion or the saved link is missing.
        """
        page = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("innerHTML", page)
        for field in ("saved", "suggested", "mutual", "note", "rating", "reasons", "crate_name"):
            self.assertIn(field, page)
        query = urllib.parse.urlencode({"path": "Music/same-a.mp3"})
        status, payload = self.request(f"/api/related?{query}")
        self.assertEqual(status, 200)
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["track"]["asset_id"], 1)
        self.assertEqual(payload["track"]["in_library"], True)
        self.assertEqual(payload["crate_name"], "Related - Same")
        self.assertEqual(payload["saved"], [])
        self.assertEqual(payload["suggested"][0]["asset_id"], 2)
        self.assertIn("same key", payload["suggested"][0]["reasons"])
        status, saved = self.request(
            "/api/related",
            {
                "action": "add",
                "asset": 1,
                "target": 2,
                "mutual": False,
                "note": "blend out of",
                "rating": 4,
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(saved["ok"])
        status, again = self.request(f"/api/related?{query}")
        self.assertEqual(again["saved"][0]["note"], "blend out of")
        self.assertEqual(again["saved"][0]["rating"], 4)
        self.assertNotIn(2, [item["asset_id"] for item in again["suggested"]])
        self.assertFalse((self.library.root / "Backups").exists())
        status, missing = self.request("/api/related")
        self.assertEqual(status, 400)

    def test_add_telemetry_omits_names_and_paths(self) -> None:
        """Record ``related_link_saved`` without the title or the path.

        Consent is on and the PostHog key is set. The recorded properties
        are the direction and the usual app fields. The note is absent.

        Returns:
            None. The test fails if the path or the title is queued.
        """
        app_config.set_telemetry_consent(True)
        fake = _FakePosthog()
        with mock.patch.dict(os.environ, {"POSTHOG_KEY": "phc_test"}):
            with mock.patch("telemetry._make_posthog", return_value=fake):
                telemetry.shutdown()
                status, _saved = self.request(
                    "/api/related",
                    {
                        "action": "add",
                        "asset": 1,
                        "target": 2,
                        "mutual": True,
                        "note": "Secret Title",
                        "rating": 3,
                    },
                )
        self.assertEqual(status, 200)
        self.assertEqual(len(fake.events), 1)
        name, _install, props = fake.events[0]
        self.assertEqual(name, "related_link_saved")
        self.assertEqual(props["link_direction"], "two_way")
        blob = json.dumps(props)
        self.assertNotIn("Secret", blob)
        self.assertNotIn("same-a", blob)
        self.assertNotIn("Music", blob)
        self.assertNotIn("path", props)
        self.assertNotIn("note", props)
        hooked = telemetry.limit_posthog_event(
            {
                "event": "related_link_saved",
                "distinct_id": app_config.load_settings().install_id,
                "properties": {
                    "link_direction": "two_way",
                    "path": "/tmp/secret.mp3",
                    "name": "Secret Title",
                    "$geoip_disable": True,
                },
            }
        )
        self.assertIsNotNone(hooked)
        hook_blob = json.dumps(hooked)
        self.assertNotIn("secret", hook_blob.lower())
        self.assertNotIn("path", hooked["properties"])
        self.assertEqual(hooked["properties"]["link_direction"], "two_way")
        telemetry.shutdown()

    def test_crate_write_waits_for_serato_to_quit(self) -> None:
        """Refuse the crate while Serato is open, then write it after the lock is gone.

        The sidecar link from the add is still there after the 409. The
        successful write names ``Related - Same`` and does not put the
        anchor in the crate.

        Returns:
            None. The test fails if the locked write changes the library.
        """
        status, saved = self.request(
            "/api/related",
            {"action": "add", "asset": 1, "target": 2, "mutual": True, "note": "", "rating": None},
        )
        self.assertEqual(status, 200)
        with open_database(library.MASTER) as conn:
            conn.execute(
                "INSERT INTO lock (owner_process_id, owner_process_name) VALUES (99, 'Serato DJ Pro')"
            )
        with mock.patch.object(library, "_process_is_serato", return_value=True):
            status, locked = self.request("/api/related", {"action": "crate", "asset": 1})
        self.assertEqual(status, 409)
        self.assertFalse((self.library.root / "Backups").exists())
        with open_database(library.MASTER) as conn:
            conn.execute("DELETE FROM lock")
        status, crate = self.request("/api/related", {"action": "crate", "asset": 1})
        self.assertEqual(status, 200)
        self.assertEqual(crate["name"], "Related - Same")
        self.assertEqual(crate["added"], [2])
        self.assertNotIn(1, crate["added"])
        status, removed = self.request("/api/related", {"action": "remove", "id": saved["id"]})
        self.assertEqual(status, 200)
        self.assertTrue(removed["ok"])


def _path_exists_in_sidecar(path: str) -> bool:
    """Return whether the sidecar has this canonical path.

    Args:
        path: Path before canonicalizing.

    Returns:
        True when a ``track`` row uses ``identity_path(path)``.
    """
    key = related.identity_path(path)
    conn = sqlite3.connect(related.related_db_path())
    try:
        row = conn.execute("SELECT 1 FROM track WHERE path = ?", (key,)).fetchone()
    finally:
        conn.close()
    return row is not None


def _crate_members(crate_id: int) -> set[int]:
    """Return asset ids in one fixture crate.

    Args:
        crate_id: Container id.

    Returns:
        Asset ids. The connection is closed before returning.
    """
    conn = sqlite3.connect(library.MASTER)
    try:
        rows = conn.execute(
            """
            SELECT ca.asset_id
            FROM container_asset ca
            JOIN location_container lc ON lc.id = ca.location_container_id
            WHERE lc.container_id = ?
            """,
            (crate_id,),
        ).fetchall()
    finally:
        conn.close()
    return {int(row[0]) for row in rows}


class _FakePosthog:
    """In-memory PostHog stand-in for one test.

    ``capture`` records the arguments. ``shutdown`` marks the client closed.
    No socket is opened.
    """

    def __init__(self) -> None:
        """Start with an empty event list."""
        self.events: list[tuple[str, str, dict[str, object]]] = []
        self.closed = False

    def capture(
        self,
        event: str,
        distinct_id: str | None = None,
        properties: dict[str, object] | None = None,
    ) -> str:
        """Record one capture call.

        Args:
            event: Event name.
            distinct_id: Anonymous install id.
            properties: Properties the app handed over.

        Returns:
            A fixed id so callers can ignore the SDK return value.
        """
        self.events.append((event, distinct_id or "", dict(properties or {})))
        return "fake"

    def shutdown(self) -> None:
        """Mark the client closed."""
        self.closed = True
