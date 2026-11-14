"""Stable codes for the error sentences the server sends to the page.

The server keeps sending the English sentence in ``error`` so older pages
and logs still read. When that sentence is one of the known ones below,
``send_json`` also adds ``code``. The page looks up ``error.<code>`` in
its locale file and falls back to the English text when the code is
missing or unknown. A sentence with a path or other changing part never
gets a code, so it is never mistaken for a fixed one.

``PARAM_CODES`` is the exception: a sentence with a placeholder, such as
the unknown Serato version notice. The page receives ``code`` and
``params`` and fills ``error.<code>``. The English ``error`` or
``message`` is still the filled sentence.

``tests/test_language.py`` checks that every code has an
``error.<code>`` entry in ``locales/en.json`` whose text is the same
sentence, or the same template for a parameterized code, so the two
cannot drift.
"""

from __future__ import annotations

from collections.abc import Mapping

import crate_trees
import folder_sync
import legacy_library
import smart_presets
import tag_cleanup

REGISTRATION_NO_SPACE = (
    "Crates were not registered. This library has no Serato Library space, "
    "so Serato may remove those crate files the next time it opens."
)
"""Plan warning when crate files cannot be stored in the Serato Library space."""

# English sentence -> code. Codes are lowercase words joined by
# underscores and never change once shipped.
ERROR_CODES: dict[str, str] = {
    "Something went wrong. The details are in the local log.": "internal",
    "There is not enough disk space to back up the library.": "backup_no_space",
    "Quit Serato DJ Pro before backing up drive crates. "
    "Serato DJ is still running, so nothing was copied.": "backup_serato_running",
    "That request is not valid.": "invalid_request",
    "The request body is not JSON.": "body_not_json",
    "The request body is not an object.": "body_not_object",
    "That upload is too large.": "upload_too_large",
    "That action is not available.": "action_unavailable",
    "No Serato library was found on this computer.": "no_library",
    "No older Serato library was found.": "no_legacy_library",
    "Choose a crate for a bitrate check.": "bitrate_needs_crate",
    "Choose a crate for a tempo check.": "tempo_needs_crate",
    "Choose a quick or full check.": "scan_depth",
    "Choose a crate for a full decode check.": "scan_full_needs_crate",
    legacy_library.WRITE_BLOCKED: "legacy_read_only",
    "The library could not be saved.": "library_not_saved",
    "Track id is required.": "track_id_required",
    "This file already has artwork.": "artwork_already",
    "This file format cannot take artwork yet.": "artwork_format",
    "Cover lookup failed.": "artwork_lookup",
    "No cover was found for this track.": "artwork_no_cover",
    "This track has no title or artist to search.": "artwork_no_search",
    "That image is not a JPEG or PNG cover.": "artwork_not_image",
    "Confirm the cover before it is saved.": "artwork_needs_confirm",
    "Choose a cover before it is saved.": "artwork_needs_release",
    "The artwork could not be written.": "artwork_write_failed",
    "Track is not in this space.": "track_not_in_space",
    "That track is not in this space.": "track_not_in_space_alt",
    "That track is not in the library.": "track_not_in_library",
    "That space is not available here.": "space_unavailable",
    "That crate is not in this space.": "crate_not_in_space",
    "The window could not be focused.": "focus_failed",
    "Choose whether to share stats before finishing setup.": "setup_needs_consent",
    "Setup could not be saved.": "setup_not_saved",
    "The layout could not be saved.": "layout_not_saved",
    "The sharing choice could not be saved.": "consent_not_saved",
    "The language could not be saved.": "language_not_saved",
    "The theme could not be saved.": "theme_not_saved",
    "The logs folder could not be opened.": "logs_not_opened",
    "Confirm undo before it is saved.": "undo_needs_confirm",
    "There is no outside change to undo.": "nothing_to_undo",
    "That folder could not be read.": "folder_unreadable",
    "That folder is outside the music folders.": "folder_outside_roots",
    "That folder is not the Serato library on this computer.": "folder_not_library",
    "Shortcuts are left alone.": "shortcut_skipped",
    "That path could not be read.": "path_unreadable",
    "That file is not on disk.": "file_not_on_disk",
    "The file could not be moved to the Trash.": "trash_failed",
    "The file could not be moved to the Recycle Bin.": "recycle_failed",
    REGISTRATION_NO_SPACE: "registration_no_space",
    "The file could not be moved. Nothing was changed.": "move_failed",
    "That track is not in a duplicate group.": "not_duplicate",
    "Choose the copy to keep.": "choose_copy",
    "Choose the track to replace.": "choose_replace_from",
    "Choose the track to put in those crates.": "choose_replace_to",
    "Those two tracks are the same.": "replace_same_track",
    "Confirm the crate update before it runs.": "replace_needs_confirm",
    "Choose a folder.": "choose_folder",
    tag_cleanup.CHOOSE_FIELD: "choose_genre_or_artist",
    tag_cleanup.CHOOSE_SPELLING: "choose_spelling",
    tag_cleanup.NOT_IN_GROUP: "spelling_not_in_group",
    "Choose fewer files at once.": "too_many_files",
    "Choose tracks to relink.": "relink_needs_tracks",
    "Two of those tracks are the same.": "relink_duplicate_tracks",
    "Two of those files are the same.": "relink_duplicate_files",
    "That track is still on disk.": "relink_still_on_disk",
    "That file is not an audio file.": "relink_not_audio",
    "Another library track already uses that file.": "file_already_used",
    "That file is already this track.": "file_already_this_track",
    "A track path is required.": "track_path_required",
    "A track cannot be related to itself.": "related_self",
    "Choose a one-way or two-way link.": "related_direction",
    "That link is not in the related tracks.": "related_missing",
    "The related-tracks file could not be saved.": "related_not_saved",
    "The related-tracks file could not be read.": "related_unreadable",
    "That snapshot could not be read.": "snapshot_unreadable",
    "That snapshot is incomplete.": "snapshot_incomplete",
    "That snapshot id is not valid.": "snapshot_id_invalid",
    "That field cannot be edited.": "field_readonly",
    "Rating needs a whole number from 1 to 5.": "rating_invalid",
    "Length needs a whole number of milliseconds.": "length_invalid",
    "Color needs a number.": "color_not_number",
    "Color is out of range.": "color_out_of_range",
    "Smart crate rules need a rules list.": "smart_rules_list",
    smart_presets.BAD_BAND: "preset_bad_band",
    smart_presets.BAD_GENRE: "preset_bad_genre",
    crate_trees.UNKNOWN_TREE: "tree_unknown",
    crate_trees.BAD_BANDS: "tree_bad_bands",
    crate_trees.BAD_GENRES: "tree_bad_genres",
    crate_trees.EMPTY_TREE: "tree_empty",
    folder_sync.SMART: "smart_crate_tracks",
    folder_sync.ROOT_CRATE: "crate_not_root",
    smart_presets.UNKNOWN_PRESET: "preset_unknown",
    smart_presets.BAD_KEY: "preset_bad_key",
    smart_presets.BAD_BPM: "preset_bad_bpm",
    smart_presets.BAD_MONTHS: "preset_bad_months",
    smart_presets.NOT_A_PRESET_CRATE: "preset_not_a_preset_crate",
    smart_presets.PRESET_CRATE_GONE: "preset_crate_gone",
    "Smart crate rules need to be JSON.": "smart_rules_json",
    "That crate name is too long.": "crate_name_too_long",
    "Use a crate name without the Serato name separator.": "crate_name_separator",
    "The space root cannot be renamed.": "root_rename",
    "The space root cannot be deleted.": "root_delete",
    "The space root has no color.": "root_color",
    "The playlist is empty.": "playlist_empty",
    "The note is too long.": "note_too_long",
    "The write did not match, and putting the library back failed.": "write_rollback_failed",
    "The write failed, and putting the library back failed.": "write_undo_failed",
    "The pre-write snapshot does not match its hash.": "write_preimage_mismatch",
}

# Code -> English template. ``{name}`` is filled from the params the page
# receives. These are not in ERROR_CODES, because the filled sentence changes.
PARAM_CODES: dict[str, str] = {
    "serato_version_unknown": (
        "Serato version is unknown (build {build}). "
        "Writes and restores are off until the installed Serato version can be read. "
        "A value that is not a dotted number, including an unreadable plist, is unknown. "
        "Snapshots can still be taken and read."
    ),
    "library_log_unconfirmed": (
        "The session log does not confirm this library file ({database}). "
        "Writes and restores are off. Snapshots can still be taken and read."
    ),
    "restore_outside": (
        "Could not put {name} back. Open the local log from Settings, or "
        "read the operation log on Backups."
    ),
}


def render(code: str, params: Mapping[str, str]) -> str:
    """Fill one parameterized English template.

    Args:
        code: A key of :data:`PARAM_CODES`.
        params: Placeholder values. A missing name raises ``KeyError``.

    Returns:
        The English sentence with the placeholders filled.

    Raises:
        KeyError: If ``code`` is not a parameterized notice, or a
            placeholder has no value.
    """
    return PARAM_CODES[code].format_map(dict(params))


def code_for(message: object) -> str | None:
    """Return the code for one error sentence.

    Args:
        message: The ``error`` value about to be sent.

    Returns:
        The stable code, or None when the sentence is not a known one.
    """
    if not isinstance(message, str):
        return None
    return ERROR_CODES.get(message)


def with_code(payload: object) -> object:
    """Add ``code`` beside a known ``error`` sentence.

    Args:
        payload: The JSON object about to be sent.

    Returns:
        A copy with ``code`` added when ``payload`` is a dict whose
        ``error`` is a known sentence and that has no ``code`` yet.
        Otherwise ``payload`` itself, unchanged.
    """
    if not isinstance(payload, dict) or "code" in payload:
        return payload
    code = code_for(payload.get("error"))
    if code is None:
        return payload
    return {**payload, "code": code}
