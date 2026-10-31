"use strict";
var SeratoWizard = (() => {
  var __defProp = Object.defineProperty;
  var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
  var __getOwnPropNames = Object.getOwnPropertyNames;
  var __hasOwnProp = Object.prototype.hasOwnProperty;
  var __export = (target, all) => {
    for (var name in all)
      __defProp(target, name, { get: all[name], enumerable: true });
  };
  var __copyProps = (to, from, except, desc) => {
    if (from && typeof from === "object" || typeof from === "function") {
      for (let key of __getOwnPropNames(from))
        if (!__hasOwnProp.call(to, key) && key !== except)
          __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
    }
    return to;
  };
  var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

  // src/wizard-view.ts
  var wizard_view_exports = {};
  __export(wizard_view_exports, {
    open: () => open
  });

  // locales/en.json
  var en_default = {
    "color.blue": "Blue",
    "color.custom": "Custom",
    "color.green": "Green",
    "color.none": "None",
    "color.orange": "Orange",
    "color.pink": "Pink",
    "color.purple": "Purple",
    "color.red": "Red",
    "color.yellow": "Yellow",
    "column.artist": "Artist",
    "column.bpm": "BPM",
    "column.deck": "Deck",
    "column.key": "Key",
    "column.played": "Played",
    "column.time": "Time",
    "column.title": "Title",
    "common.back": "Back",
    "common.cancel": "Cancel",
    "common.close": "Close",
    "common.confirm": "Confirm",
    "common.delete": "Delete",
    "common.no": "No",
    "common.off": "Off",
    "common.on": "On",
    "common.refresh": "Refresh",
    "common.reload": "Reload",
    "common.remove": "Remove",
    "common.save": "Save",
    "common.saved": "Saved.",
    "common.tryAgain": "Try again",
    "common.up": "Up",
    "common.yes": "Yes",
    "consent.accept": "Share",
    "consent.body": "Counts and actions only, plus the app name, the app version, and the operating system. Track titles, crate names, file paths, and library contents stay on this computer. Sharing stays off unless you turn it on.",
    "consent.decline": "Don't share",
    "copies.heading": "Other copies",
    "count.plays": {
      one: "{count} play",
      other: "{count} plays"
    },
    "count.tracks": {
      one: "{count} track",
      other: "{count} tracks"
    },
    "crates.allTracks": "All tracks",
    "crates.collapse": "Collapse {name}",
    "crates.colorPrompt": "Crate color: {names}",
    "crates.colorSaved": "Crate color saved.",
    "crates.colorUnknown": "Use one of the palette names.",
    "crates.confirmDelete": "Delete “{name}” and the crates inside it? The tracks stay in the library.",
    "crates.created": "Crate created.",
    "crates.deleted": "Crate deleted.",
    "crates.expand": "Expand {name}",
    "crates.find": "Find a crate",
    "crates.heading": "Crates",
    "crates.new": "New",
    "crates.newPrompt": "New crate name",
    "crates.rename": "Rename",
    "crates.renamePrompt": "Rename crate",
    "crates.renamed": "Crate renamed.",
    "crates.smartBadge": "smart",
    "crates.smartList": "Smart crates: {names}",
    "crates.sort": "Sort crates",
    "crates.sort.added": "Added",
    "crates.sort.name": "Name",
    "crates.sort.order": "Order",
    "detail.bpmNumber": "BPM needs a number.",
    "detail.confirmRemove": "Remove this track from the library? The audio file stays on disk.",
    "detail.empty": "Select a track to read its attributes.",
    "detail.hideSearchCopies": "Hide search copies",
    "detail.readFailed": "Could not read track ({status})",
    "detail.reading": "Reading attributes",
    "detail.relocate": "Relocate",
    "detail.relocatePrompt": "Path to the audio file",
    "detail.relocated": "File location saved.",
    "detail.removeFromLibrary": "Remove from library",
    "detail.removePrepare": "Remove from Prepare",
    "detail.removed": "Removed from the library.",
    "detail.removedPrepare": "Removed from Prepare.",
    "detail.reveal": "Reveal in {manager}",
    "detail.saveTrack": "Save track",
    "detail.searchCopies": {
      one: "Search copies, {count} field",
      other: "Search copies, {count} fields"
    },
    "detail.sendPrepare": "Send to Prepare",
    "detail.sentPrepare": "Sent to Prepare.",
    "duplicates.readFailed": "Could not read duplicates.",
    "error.action_unavailable": "That action is not available.",
    "error.body_not_json": "The request body is not JSON.",
    "error.body_not_object": "The request body is not an object.",
    "error.choose_copy": "Choose the copy to keep.",
    "error.color_not_number": "Color needs a number.",
    "error.color_out_of_range": "Color is out of range.",
    "error.consent_not_saved": "The sharing choice could not be saved.",
    "error.crate_name_separator": "Use a crate name without the Serato name separator.",
    "error.crate_name_too_long": "That crate name is too long.",
    "error.crate_not_in_space": "That crate is not in this space.",
    "error.field_readonly": "That field cannot be edited.",
    "error.file_not_on_disk": "That file is not on disk.",
    "error.focus_failed": "The window could not be focused.",
    "error.folder_not_library": "That folder is not the Serato library on this computer.",
    "error.folder_outside_roots": "That folder is outside the music folders.",
    "error.folder_unreadable": "That folder could not be read.",
    "error.internal": "Something went wrong. The details are in the local log.",
    "error.invalid_request": "That request is not valid.",
    "error.language_not_saved": "The language could not be saved.",
    "error.layout_not_saved": "The layout could not be saved.",
    "error.legacy_read_only": "This library was made by an older Serato DJ. This app can show it but cannot change it yet.",
    "error.length_invalid": "Length needs a whole number of milliseconds.",
    "error.library_not_saved": "The library could not be saved.",
    "error.logs_not_opened": "The logs folder could not be opened.",
    "error.move_failed": "The file could not be moved. Nothing was changed.",
    "error.no_legacy_library": "No older Serato library was found.",
    "error.no_library": "No Serato library was found on this computer.",
    "error.not_duplicate": "That track is not in a duplicate group.",
    "error.note_too_long": "The note is too long.",
    "error.nothing_to_undo": "There is no outside change to undo.",
    "error.path_unreadable": "That path could not be read.",
    "error.playlist_empty": "The playlist is empty.",
    "error.rating_invalid": "Rating needs a whole number from 1 to 5.",
    "error.recycle_failed": "The file could not be moved to the Recycle Bin.",
    "error.related_direction": "Choose a one-way or two-way link.",
    "error.related_missing": "That link is not in the related tracks.",
    "error.related_not_saved": "The related-tracks file could not be saved.",
    "error.related_self": "A track cannot be related to itself.",
    "error.related_unreadable": "The related-tracks file could not be read.",
    "error.requestFailed": "Request failed",
    "error.requestStatus": "Request failed ({status})",
    "error.root_color": "The space root has no color.",
    "error.root_delete": "The space root cannot be deleted.",
    "error.root_rename": "The space root cannot be renamed.",
    "error.serato_version_unknown": "Serato version is unknown (build {build}). Writes and restores are off until the installed Serato version can be read. A value that is not a dotted number, including an unreadable plist, is unknown. Snapshots can still be taken and read.",
    "error.setup_needs_consent": "Choose whether to share stats before finishing setup.",
    "error.setup_not_saved": "Setup could not be saved.",
    "error.shortcut_skipped": "Shortcuts are left alone.",
    "error.smart_rules_json": "Smart crate rules need to be JSON.",
    "error.smart_rules_list": "Smart crate rules need a rules list.",
    "error.snapshot_id_invalid": "That snapshot id is not valid.",
    "error.snapshot_incomplete": "That snapshot is incomplete.",
    "error.snapshot_unreadable": "That snapshot could not be read.",
    "error.space_unavailable": "That space is not available here.",
    "error.track_id_required": "Track id is required.",
    "error.track_not_in_library": "That track is not in the library.",
    "error.track_not_in_space": "Track is not in this space.",
    "error.track_not_in_space_alt": "That track is not in this space.",
    "error.track_path_required": "A track path is required.",
    "error.trash_failed": "The file could not be moved to the Trash.",
    "error.undo_needs_confirm": "Confirm undo before it is saved.",
    "error.upload_too_large": "That upload is too large.",
    "export.m3u": "Export",
    "field.album": "Album",
    "field.beatgridLocked": "Beatgrid locked",
    "field.color": "Color",
    "field.comments": "Comments",
    "field.composer": "Composer",
    "field.emoji": "Emoji",
    "field.genre": "Genre",
    "field.grouping": "Grouping",
    "field.label": "Label",
    "field.rating": "Rating",
    "field.remixer": "Remixer",
    "field.year": "Year",
    "files.andMore": "And {count} more.",
    "files.browseElsewhere": "Browse elsewhere…",
    "files.changeCrates": "Crates: {crates}.",
    "files.checking": "Checking what will change.",
    "files.chooseDelete": "Choose files to delete.",
    "files.chooseDestination": "Choose the destination folder. Then confirm the move.",
    "files.chooseMove": "Choose files to move.",
    "files.chooseOneRename": "Choose one file to rename.",
    "files.chooseOneReplace": "Choose one file to replace.",
    "files.contents": "Folder contents",
    "files.driveMissing": "Drive not connected",
    "files.driveMissingLabel": "{name}, Drive not connected",
    "files.empty": "This folder is empty.",
    "files.fileCount": {
      one: "{count} file",
      other: "{count} files"
    },
    "files.inLibrary": "In library",
    "files.moveFolder": "Move this folder",
    "files.moveHere": "Move here",
    "files.moveToFolder": "Move to folder",
    "files.moveToTrash": "Move to Trash",
    "files.newFile": "New file",
    "files.newName": "New name",
    "files.noMatches": "No files match “{query}”.",
    "files.noRoots": "No music folders yet",
    "files.noRootsBody": "Setup finds the folders Serato uses for your music.",
    "files.notSaved": "That change was not saved.",
    "files.nothingUntilConfirm": "Nothing is changed until you confirm.",
    "files.open": "Open {name}",
    "files.path": "Folder path",
    "files.readingFolder": "Reading this folder",
    "files.readingFolderNote": "Reading this folder.",
    "files.readingRoots": "Reading music folders",
    "files.readingRootsNote": "Reading music folders.",
    "files.replaceFile": "Replace file",
    "files.review": "Review",
    "files.reviewTitle": "Review this change",
    "files.rootCount": {
      one: "{count} music folder",
      other: "{count} music folders"
    },
    "files.roots": "Music folders",
    "files.rootsUnreadable": "Music folders could not be read.",
    "files.runSetup": "Run setup",
    "files.saving": "Saving.",
    "files.searchLabel": "Search files",
    "files.searchPlaceholder": "Search files",
    "files.searchResults": "Search results",
    "files.searchTruncated": "Some matching files are not listed. Type more of the name.",
    "files.searching": "Searching files…",
    "files.shortcut": "{name} (shortcut)",
    "files.trash": "Trash",
    "files.truncated": "Some files are not listed.",
    "files.updated": "The files were updated.",
    "format.bytes": {
      one: "{count} byte",
      other: "{count} bytes"
    },
    "format.hoursMinutes": "{hours}h {minutes}m",
    "format.minutes": "{minutes}m",
    "history.chooseSession": "Choose a session.",
    "history.file": "File",
    "history.notes": "Notes",
    "history.openInLibrary": "Open in library",
    "history.readFailed": "Could not read history.",
    "history.session": "Session",
    "history.sessionFailed": "Could not read that session.",
    "history.sessions": "History sessions",
    "history.started": "Started",
    "import.added": {
      one: "{count} track added.",
      other: "{count} tracks added."
    },
    "import.button": "Import",
    "import.defaultName": "Imported playlist",
    "import.unmatched": {
      one: "{count} line did not match a library track.",
      other: "{count} lines did not match a library track."
    },
    "layout.resize": "Resize the track list",
    "layout.widthNotSaved": "Couldn't save the pane width. It goes back to the last saved width next time.",
    "library.loading": "Loading the library",
    "library.readFailed": "Could not read the library ({status})",
    "library.unavailable": "Library unavailable",
    "list.label": "Tracks",
    "list.noMatches": "No tracks match.",
    "list.readingDuplicates": "Reading duplicates",
    "logs.copied": "Copied the logs.",
    "logs.copiedTruncated": "Copied the latest log entries. Older entries were left out.",
    "logs.copyFailed": "Couldn't copy the logs.",
    "logs.copyManual": "Couldn't copy automatically. Select the log text and copy it.",
    "logs.copying": "Copying…",
    "logs.empty": "No log entries yet.",
    "logs.openFailed": "Couldn't open the logs folder.",
    "logs.opened": "Opened the logs folder.",
    "markers.beats": {
      one: "{count} beat",
      other: "{count} beats"
    },
    "markers.bpm": "{bpm} BPM",
    "markers.cue": "Cue {number}",
    "markers.flip": "Flip {number}",
    "markers.heading": "Cues, loops, and beatgrid",
    "markers.loop": "Loop {number}",
    "markers.loopLocked": "Loop {number} locked",
    "markers.none": "No Serato cues in this file.",
    "markers.readOnly": "Read from the audio file. These are not written back.",
    "markers.unavailable": "The file is not on disk, so cues cannot be read.",
    "merge.addToCrates": "Add the kept copy to {crates}.",
    "merge.addToSpace": "Add the kept copy to the {space} space.",
    "merge.alreadyInCrates": "The kept copy is already in every crate the others use. It stays where it is.",
    "merge.confirmTrash": "Merge and move files to Trash",
    "merge.fieldChange": "{label} changes from {before} to {after}.",
    "merge.filesStay": "Audio files stay on disk.",
    "merge.intro": "Keep one copy. The others leave the library. Audio files stay on disk unless you move them to the Trash.",
    "merge.keep": "Copy to keep",
    "merge.keptCopy": "the kept copy",
    "merge.merged": {
      one: "Merged {count} copy into {name}.",
      other: "Merged {count} copies into {name}."
    },
    "merge.merging": "Merging…",
    "merge.noCrates": "None of the copies are in a crate.",
    "merge.noFields": "No empty fields or higher play count to copy.",
    "merge.noHistory": "No history entries point at the other copies.",
    "merge.noHistoryId": "This library has no history track id to repoint.",
    "merge.plays": {
      one: "{count} play",
      other: "{count} plays"
    },
    "merge.previewFailed": "The preview could not be read.",
    "merge.quitSerato": "Quit Serato before merging. The preview shows the plan.",
    "merge.readingPreview": "Reading the preview…",
    "merge.removeCopies": {
      one: "Remove {count} copy from the library.",
      other: "Remove {count} copies from the library."
    },
    "merge.repointHistory": {
      one: "Point {count} history entry at the kept copy.",
      other: "Point {count} history entries at the kept copy."
    },
    "merge.title": "Merge copies",
    "merge.trashFiles": "Move {files} to the Trash.",
    "merge.trashLabel": "Move the other audio files to the Trash",
    "merge.trashNote": "Off by default. Files go to the Trash, where you can restore them. They are not permanently deleted.",
    "mode.duplicates": "Same title, artist, and length. Select a copy, then merge the others into it.",
    "mode.files": "Files on disk. Cue points stay in the audio file. Crates follow the path.",
    "mode.missing": "Tracks Serato has marked missing in this space.",
    "mode.snapshots": "Hash-checked copies of the library, crates, and Serato frames inside audio files. Audio itself is not copied.",
    "mode.stems": "Tracks with a stems analysis state.",
    "plan.andMore": ", and {count} more",
    "plan.cratesAdded": "Crates added",
    "plan.cratesChanged": "Crates changed",
    "plan.cratesRemoved": "Crates removed",
    "plan.cratesUnavailable": "Crates on an unavailable drive",
    "plan.cueChanges": "Cue changes",
    "plan.deletedCrates": "Deleted crates",
    "plan.deletedCues": "Deleted cues",
    "plan.deletedGrids": "Deleted grids",
    "plan.deletedTracks": "Deleted tracks",
    "plan.files": {
      one: "{label}: {count} file",
      other: "{label}: {count} files"
    },
    "plan.gridChanges": "Grid changes",
    "plan.item": "item",
    "plan.listed": "{label}: {count}. {names}",
    "plan.none": "{label}: none",
    "plan.nothingChanged": "Nothing has been changed.",
    "plan.tracksAdded": "Tracks added",
    "plan.tracksRemoved": "Tracks removed",
    "plan.tracksUnavailable": "Tracks on an unavailable drive",
    "player.cannotPlay": "This file cannot be played in this window.",
    "player.cue": "Cue",
    "player.duration": "Duration",
    "player.elapsed": "Elapsed",
    "player.next": "Next",
    "player.notInLibrary": "Not in the library or file missing",
    "player.nothingPlaying": "Nothing playing",
    "player.overview": "Track overview",
    "player.pause": "Pause",
    "player.play": "Play",
    "player.previous": "Previous",
    "player.region": "Player",
    "player.seek": "Seek",
    "player.volume": "Volume",
    "player.waveformReading": "Reading the waveform…",
    "player.waveformUnavailable": "Waveform unavailable for this format",
    "player.zoomIn": "Zoom in",
    "player.zoomOut": "Zoom out",
    "quickOpen.empty": "Type a track or file name.",
    "quickOpen.file": "File",
    "quickOpen.fileError": "Files on disk could not be searched. Track matches are still listed.",
    "quickOpen.label": "Name",
    "quickOpen.matchCount": {
      one: "{count} match",
      other: "{count} matches"
    },
    "quickOpen.matches": "Matches",
    "quickOpen.none": "No tracks or files match “{query}”.",
    "quickOpen.placeholder": "Track or file name",
    "quickOpen.searching": "Searching files…",
    "quickOpen.title": "Find a track or file",
    "quickOpen.track": "Track",
    "quickOpen.truncated": "Some files were not searched. Type more of the name.",
    "rail.heading": "Library",
    "rating.none": "Not rated",
    "rating.stars": {
      one: "{count} star",
      other: "{count} stars"
    },
    "rekordbox.dialogTitle": "Download rekordbox.xml?",
    "rekordbox.download": "Download",
    "rekordbox.failed": "The Rekordbox export failed.",
    "rekordbox.hotLoops": "Hot loops",
    "rekordbox.hotLoopsHelp": "Uses a free hot-cue pad",
    "rekordbox.intro": "These items are not copied into Rekordbox. The file downloads after you confirm.",
    "rekordbox.keyAsis": "Key as stored",
    "rekordbox.keyCamelot": "Camelot key",
    "rekordbox.keyClassical": "Classical key",
    "rekordbox.keyNotation": "Rekordbox key notation",
    "rekordbox.memoryCues": "Memory cues",
    "rekordbox.notXml": "The export did not produce an XML file.",
    "rekordbox.reportLabel": "What is not copied",
    "related.confirmRemove": "Remove the link to “{name}”?",
    "related.crateNote": "Creates or refreshes the crate “{name}”. Serato must be quit.",
    "related.crateUpdated": "Crate “{name}” updated.",
    "related.find": "Find a track to link",
    "related.findPlaceholder": "Title or artist",
    "related.heading": "Related tracks",
    "related.linkRating": "Link rating",
    "related.loadFailed": "Related tracks could not be loaded.",
    "related.loading": "Loading related tracks",
    "related.noPath": "This track has no file path, so it cannot be linked.",
    "related.noSuggestions": "No suggestions from key, tempo, or shared crates.",
    "related.noneSaved": "No saved links yet. Search for a track, or save a suggestion.",
    "related.notInLibrary": "Not in this library",
    "related.note": "Note",
    "related.notePlaceholder": "blend out of",
    "related.oneWay": "One-way",
    "related.quitSerato": "Quit Serato before writing the crate.",
    "related.ratingOutOf": "{rating}/5",
    "related.removeLink": "Remove link to {name}",
    "related.removed": "Link removed.",
    "related.saveLink": "Save link",
    "related.saveLinkTo": "Save link to {name}",
    "related.saved": "Link saved.",
    "related.savedCount": "{count} saved",
    "related.suggested": "Suggested from key, tempo within 6%, and shared crates. Save stores a two-way link.",
    "related.thisTrack": "this track",
    "related.twoWay": "Two-way",
    "related.twoWayLink": "Two-way link",
    "related.typeHint": "Type a title or artist.",
    "related.updateCrate": "Update Serato crate",
    "rules.and": "and",
    "rules.label": "Smart crate rules",
    "rules.matches": "Matches",
    "rules.none": "no rules yet",
    "rules.or": "or",
    "rules.save": "Save rules",
    "rules.saved": "Rules saved.",
    "search.tracks": "Search tracks",
    "settings.about": "About",
    "settings.copyLogs": "Copy logs",
    "settings.copyVersion": "Copy version",
    "settings.language": "Language",
    "settings.languageNotSaved": "Couldn't save the language. It is used until you close the app.",
    "settings.languageSystem": "Same as the system",
    "settings.logText": "Log text",
    "settings.openLogs": "Open logs folder",
    "settings.rerunSetup": "Run setup again",
    "settings.share": "Share anonymous usage stats and crash reports",
    "settings.title": "Settings",
    "sharing.canSend": "Anonymous counts and crash reports can be sent.",
    "sharing.loadFailed": "Couldn't load sharing settings.",
    "sharing.loadFailedOff": "Couldn't load sharing settings. Nothing is sent.",
    "sharing.noKeys": "This copy has no telemetry keys, so nothing is sent either way.",
    "sharing.nothingSent": "Nothing is sent.",
    "sharing.off": "Sharing is off. Nothing is sent.",
    "sharing.on": "Sharing is on. Anonymous counts and crash reports can be sent.",
    "shortcuts.action": "Action",
    "shortcuts.cheatSheet": "Show shortcuts",
    "shortcuts.dismiss": "Close or clear search",
    "shortcuts.focusSearch": "Focus search",
    "shortcuts.groupFind": "Find",
    "shortcuts.groupLists": "Lists",
    "shortcuts.groupPlay": "Play",
    "shortcuts.groupViews": "Views",
    "shortcuts.intro": "These keys work anywhere on this screen, except while you are typing in a field. Esc still closes a dialog or clears a search.",
    "shortcuts.key": "Key",
    "shortcuts.listNext": "Next row",
    "shortcuts.listOpen": "Open the row",
    "shortcuts.listPrevious": "Previous row",
    "shortcuts.open": "Shortcuts",
    "shortcuts.playNote": "Space plays or pauses. Left moves 5 seconds back. Right moves 5 seconds forward.",
    "shortcuts.playPause": "Play or pause",
    "shortcuts.quickOpen": "Find a track or file",
    "shortcuts.seekBack": "Back 5 seconds",
    "shortcuts.seekForward": "Forward 5 seconds",
    "shortcuts.title": "Keyboard shortcuts",
    "shortcuts.viewCrates": "Crates",
    "shortcuts.viewFiles": "Files",
    "shortcuts.viewHistory": "History",
    "shortcuts.viewLibrary": "Library",
    "shortcuts.viewSnapshots": "Snapshots",
    "snapshots.count": {
      one: "{count} snapshot",
      other: "{count} snapshots"
    },
    "snapshots.empty": "No snapshots yet. Take a snapshot to keep a point you can restore. Snapshots are kept, and this page does not expire them.",
    "snapshots.noSearch": "Snapshots has no search. Press Ctrl+K to find a track or a file.",
    "snapshots.outsideChange": "Something outside this app changed the Serato folder. A snapshot was saved after that change. Undo puts back the previous snapshot.",
    "snapshots.outsideChangeLexicon": "Lexicon changed the Serato folder. A snapshot was saved after that change. Undo puts back the previous snapshot.",
    "snapshots.reading": "Reading snapshots",
    "snapshots.readingPlan": "Reading what would change",
    "snapshots.restore": "Restore",
    "snapshots.restoreIntro": "Nothing is changed until you confirm. A new snapshot is saved first, so this restore can be undone.",
    "snapshots.restoreTitle": "Restore this snapshot",
    "snapshots.restored": "Restore finished. The previous library was saved first, so this can be undone from the list.",
    "snapshots.restoring": "Restoring…",
    "snapshots.reviewRestore": "Review restore",
    "snapshots.reviewUndo": "Review undo",
    "snapshots.saved": "Snapshot saved.",
    "snapshots.saving": "Saving snapshot…",
    "snapshots.seratoUnknown": "Serato version unknown",
    "snapshots.seratoVersion": "Serato {version} (build {build})",
    "snapshots.take": "Take a snapshot",
    "snapshots.trigger": "snapshot",
    "snapshots.unavailableDrives": "Unavailable: {drives}.",
    "snapshots.unknownTime": "Unknown time",
    "snapshots.unreadable": "The snapshots could not be read.",
    "space.appleMusic": "Apple Music",
    "space.label": "Space",
    "space.library": "Library",
    "space.prepare": "Prepare",
    "space.video": "Video",
    "status.checking": "Checking Serato",
    "status.library": "Library",
    "tip.consentAccept": "Send anonymous usage counts and crash reports.",
    "tip.consentDecline": "Do not send usage counts or crash reports.",
    "tip.copyLogs": "Copy the app's logs so you can paste them.",
    "tip.copyVersion": "Copy the version number.",
    "tip.crateCollapse": "Hide the crates inside this one.",
    "tip.crateColor": "Change the color of this crate.",
    "tip.crateDelete": "Delete this crate. Its music files stay on disk.",
    "tip.crateExpand": "Show the crates inside this one.",
    "tip.crateMember": "Tick to keep this track in this crate.",
    "tip.crateNew": "Make a new crate.",
    "tip.crateRename": "Change the name of this crate.",
    "tip.crateRow": "Show the tracks in this crate.",
    "tip.crateSearch": "Type a name to narrow the crate list.",
    "tip.crateSortAdded": "List the newest crates first.",
    "tip.crateSortName": "List crates from A to Z.",
    "tip.crateSortOrder": "List crates in your Serato order.",
    "tip.dialogCancel": "Close this box. Nothing changes.",
    "tip.dialogClose": "Close this box.",
    "tip.duplicateCopy": "Show the details of this copy.",
    "tip.exportM3u": "Download this list as a playlist file.",
    "tip.exportRekordbox": "Download a rekordbox.xml file of this library.",
    "tip.filesConfirm": "Make this change.",
    "tip.filesCrumb": "Go to this folder.",
    "tip.filesDelete": "Move the chosen files to the Trash.",
    "tip.filesDriveMissing": "This drive is not connected. Connect it and try again.",
    "tip.filesElsewhere": "Look in a folder outside your music folders.",
    "tip.filesMove": "Move the chosen files to another folder.",
    "tip.filesMoveFolder": "Move this whole folder.",
    "tip.filesMoveHere": "Move the files into this folder.",
    "tip.filesName": "Type the new name.",
    "tip.filesOpen": "Open this folder.",
    "tip.filesPickCancel": "Stop the move. Nothing changes.",
    "tip.filesRefresh": "Read this folder again.",
    "tip.filesRename": "Change the name of the chosen file.",
    "tip.filesReplace": "Swap the chosen file for another. Its cues and crates stay.",
    "tip.filesReplacement": "Type the full path of the new file.",
    "tip.filesReview": "See what will change. Nothing changes yet.",
    "tip.filesRunSetup": "Run setup to find your library.",
    "tip.filesSearch": "Type a name to find a file in this folder.",
    "tip.filesSelect": "Tick to choose this file.",
    "tip.filesShortcut": "This is a shortcut to another place on disk.",
    "tip.filesUp": "Go up to the folder that holds this one.",
    "tip.historySession": "Show the tracks played in this session.",
    "tip.importM3u": "Make a new crate from a playlist file.",
    "tip.logFallback": "The app's logs. Select the text to copy it.",
    "tip.mergeConfirm": "Merge the copies into the one you chose.",
    "tip.mergeCopies": "Keep one copy of this track and remove the others.",
    "tip.mergeKeep": "Choose this copy to keep.",
    "tip.mergeTrash": "Tick to also move the other files to the Trash.",
    "tip.openInLibrary": "Open this stem's track in the library.",
    "tip.openLogs": "Open the folder that holds the app's logs.",
    "tip.openSettings": "Open settings for sharing, logs, and setup.",
    "tip.openShortcuts": "List the keyboard shortcuts.",
    "tip.playerCue": "Jump to this cue point.",
    "tip.playerNext": "Go to the next track.",
    "tip.playerPrevious": "Go to the track before this one.",
    "tip.playerSeek": "Drag to move through the track.",
    "tip.playerToggle": "Play or pause the track.",
    "tip.playerVolume": "Change how loud the track plays.",
    "tip.prepareRemove": "Take this track off the Prepare list.",
    "tip.prepareSend": "Add this track to the Prepare list.",
    "tip.quickOpenQuery": "Type part of a track or file name.",
    "tip.quickOpenResult": "Open this track or file.",
    "tip.quickOpenRetry": "Search the files on disk again.",
    "tip.rekordboxDownload": "Download the rekordbox.xml file.",
    "tip.rekordboxHotLoops": "Add saved loops to the Rekordbox file. Each uses a free hot-cue pad.",
    "tip.rekordboxKey": "Choose how keys are written in the Rekordbox file.",
    "tip.rekordboxMemory": "Include memory cues in the Rekordbox file.",
    "tip.relatedChoose": "Choose this track to link.",
    "tip.relatedCrate": "Update the Serato crate that holds these related tracks.",
    "tip.relatedMutual": "Tick to show the link on both tracks.",
    "tip.relatedNote": "Add a note about how these tracks go together.",
    "tip.relatedOpen": "Show this related track.",
    "tip.relatedRating": "Rate how well these tracks go together.",
    "tip.relatedRemove": "Remove this link. Both tracks stay in the library.",
    "tip.relatedSave": "Save this link.",
    "tip.relatedSearch": "Type a title or artist to find a track to link.",
    "tip.relatedSuggestionSave": "Save this suggestion as a link.",
    "tip.reload": "Read the library again to pick up new changes.",
    "tip.rerunWizard": "Go through first-time setup again.",
    "tip.rowPlay": "Play this track.",
    "tip.search": "Type a title or artist to narrow the list.",
    "tip.searchCopies": "Show or hide the fields from the other copies.",
    "tip.settingsLanguage": "Choose the language for this app.",
    "tip.smartRules": "Edit the rules that choose this crate's tracks.",
    "tip.smartRulesSave": "Save the rules for this smart crate.",
    "tip.snapshotConfirm": "Put your library back to this snapshot.",
    "tip.snapshotRestore": "See what restoring this snapshot would change. Nothing changes yet.",
    "tip.snapshotsRefresh": "Read the list of snapshots again.",
    "tip.snapshotsRetry": "Try reading the snapshots again.",
    "tip.snapshotsTake": "Save a copy of your library now.",
    "tip.snapshotsUndo": "See what undoing the outside change would do. Nothing changes yet.",
    "tip.sortColumn": "Sort the list by this column. Click again to reverse it.",
    "tip.space": "Choose which part of your library to show.",
    "tip.splitter": "Drag to resize the track list. Double-click to reset it.",
    "tip.telemetryToggle": "Tick to send anonymous usage counts and crash reports.",
    "tip.trackAlbum": "The album name.",
    "tip.trackArtist": "The artist's name.",
    "tip.trackBpm": "The speed in beats per minute.",
    "tip.trackColor": "Choose the color that marks this track.",
    "tip.trackComments": "Your own notes about this track.",
    "tip.trackComposer": "The person who wrote the track.",
    "tip.trackEmoji": "An emoji to mark this track.",
    "tip.trackGenre": "The style of music.",
    "tip.trackGridLock": "Tick to stop the beatgrid from being changed.",
    "tip.trackGrouping": "Your own group name for this track.",
    "tip.trackKey": "The musical key.",
    "tip.trackLabel": "The record label.",
    "tip.trackRating": "Give this track a star rating.",
    "tip.trackRelocate": "Point this track at its file in a new place.",
    "tip.trackRemixer": "The person who remixed the track.",
    "tip.trackRemove": "Remove this track from the library. The file stays on disk.",
    "tip.trackReveal": "Show this track's file on your computer.",
    "tip.trackRow": "Show the details of this track.",
    "tip.trackSave": "Save your changes to this track.",
    "tip.trackTitle": "The track's title.",
    "tip.trackYear": "The year the track came out.",
    "tip.viewCrates": "Show your crates and their tracks.",
    "tip.viewDuplicates": "Show tracks that are in the library more than once.",
    "tip.viewFiles": "Show the music files on this computer.",
    "tip.viewHistory": "Show the sessions you played.",
    "tip.viewMissing": "Show tracks whose files cannot be found.",
    "tip.viewSnapshots": "Show saved copies of your library.",
    "tip.viewStems": "Show tracks that have stems.",
    "tip.waveformOverview": "Click or drag to move through the track.",
    "tip.waveformZoomIn": "Show less of the track in more detail.",
    "tip.waveformZoomOut": "Show more of the track in less detail.",
    "tip.wizardBack": "Go back one step.",
    "tip.wizardCancel": "Close setup. It runs again next time.",
    "tip.wizardFolder": "Open this folder.",
    "tip.wizardFolderClose": "Close the folder list.",
    "tip.wizardFolderUp": "Go up to the folder that holds this one.",
    "tip.wizardFolderUse": "Use the folder you are looking at.",
    "tip.wizardNo": "Do not send usage counts or crash reports.",
    "tip.wizardPrimary": "Go on to the next step.",
    "tip.wizardSecondary": "Find your library folder yourself.",
    "tip.wizardYes": "Send anonymous usage counts and crash reports.",
    "track.missingBadge": "missing",
    "track.numbered": "Track {id}",
    "track.stemsBadge": "stems",
    "track.untitled": "Untitled",
    "version.app": "App version",
    "version.copied": "Copied",
    "version.copyFailed": "Couldn't copy the version.",
    "version.unavailable": "Version unavailable",
    "view.crates": "Crates",
    "view.duplicates": "Duplicates",
    "view.files": "Files",
    "view.history": "History",
    "view.label": "Views",
    "view.missing": "Missing",
    "view.snapshots": "Snapshots",
    "view.stems": "Stems",
    "wizard.action.checkAgain": "Check again",
    "wizard.action.continue": "Continue",
    "wizard.action.getStarted": "Get started",
    "wizard.action.looking": "Looking…",
    "wizard.action.openLibrary": "Open my library",
    "wizard.action.takeSnapshot": "Take a safety snapshot",
    "wizard.action.tryAgain": "Try again",
    "wizard.action.useLibrary": "Use this library",
    "wizard.announce": "Step {index} of {count}. {name}.",
    "wizard.blocked": "Close Serato DJ to continue.",
    "wizard.chooseCheckAgain": "Choose Check again.",
    "wizard.chooseFolder": "Choose a folder",
    "wizard.closeFolders": "Close folder list",
    "wizard.consentFailed": "Couldn't save that choice. Try again.",
    "wizard.copySaved": "Safety copy saved.",
    "wizard.done": "Library ready. Snapshot saved.",
    "wizard.finishFailed": "Couldn't save that you finished setup. Try again.",
    "wizard.folders": "Folders",
    "wizard.genericError": "Something went wrong. Try again.",
    "wizard.heading.consent": "Share anonymous usage stats and crash reports?",
    "wizard.heading.library": "Find your library",
    "wizard.heading.snapshot": "Safety snapshot",
    "wizard.heading.welcome": "See your Serato library",
    "wizard.lookFailed": "Couldn't look for your library.",
    "wizard.looking": "Looking for your Serato library.",
    "wizard.no": "No, don't share",
    "wizard.noSubfolders": "This folder has no folders inside it.",
    "wizard.opening": "Opening…",
    "wizard.progressLabel": "Saving a safety copy",
    "wizard.saving": "Saving…",
    "wizard.savingCopy": "Saving a safety copy…",
    "wizard.savingLibraryCopy": "Saving a safety copy of your library.",
    "wizard.snapshotBody": "A backup of your library data is saved before anything is changed.",
    "wizard.snapshotFailed": "The safety copy could not be saved. Your library was not changed. Try again.",
    "wizard.step.consent": "Sharing",
    "wizard.step.done": "Done",
    "wizard.step.library": "Find your library",
    "wizard.step.snapshot": "Safety snapshot",
    "wizard.step.welcome": "Welcome",
    "wizard.stepOf": "Step {index} of {count}",
    "wizard.useFolder": "Use this folder",
    "wizard.welcomeBody": "This app shows the library Serato already keeps on this computer. It will not change anything without asking.",
    "wizard.yes": "Yes, share"
  };

  // locales/es.json
  var es_default = {
    "color.blue": "Azul",
    "color.custom": "Personalizado",
    "color.green": "Verde",
    "color.none": "Ninguno",
    "color.orange": "Naranja",
    "color.pink": "Rosa",
    "color.purple": "Morado",
    "color.red": "Rojo",
    "color.yellow": "Amarillo",
    "column.artist": "Artista",
    "column.bpm": "BPM",
    "column.deck": "Deck",
    "column.key": "Tono",
    "column.played": "Reproducida",
    "column.time": "Tiempo",
    "column.title": "Título",
    "common.back": "Atrás",
    "common.cancel": "Cancelar",
    "common.close": "Cerrar",
    "common.confirm": "Confirmar",
    "common.delete": "Eliminar",
    "common.no": "No",
    "common.off": "Desactivado",
    "common.on": "Activado",
    "common.refresh": "Actualizar",
    "common.reload": "Recargar",
    "common.remove": "Quitar",
    "common.save": "Guardar",
    "common.saved": "Guardado.",
    "common.tryAgain": "Reintentar",
    "common.up": "Subir",
    "common.yes": "Sí",
    "consent.accept": "Compartir",
    "consent.body": "Solo recuentos y acciones, más el nombre de la app, su versión y el sistema operativo. Los títulos de las pistas, los nombres de las cajas, las rutas de los archivos y el contenido de la biblioteca se quedan en este equipo. No se comparte nada a menos que lo actives.",
    "consent.decline": "No compartir",
    "copies.heading": "Otras copias",
    "count.plays": {
      one: "{count} reproducción",
      other: "{count} reproducciones"
    },
    "count.tracks": {
      one: "{count} pista",
      other: "{count} pistas"
    },
    "crates.allTracks": "Todas las pistas",
    "crates.collapse": "Contraer {name}",
    "crates.colorPrompt": "Color de la caja: {names}",
    "crates.colorSaved": "Color de la caja guardado.",
    "crates.colorUnknown": "Usa uno de los nombres de la paleta.",
    "crates.confirmDelete": "¿Eliminar «{name}» y las cajas que contiene? Las pistas se quedan en la biblioteca.",
    "crates.created": "Caja creada.",
    "crates.deleted": "Caja eliminada.",
    "crates.expand": "Expandir {name}",
    "crates.find": "Buscar una caja",
    "crates.heading": "Cajas",
    "crates.new": "Nueva",
    "crates.newPrompt": "Nombre de la nueva caja",
    "crates.rename": "Renombrar",
    "crates.renamePrompt": "Renombrar caja",
    "crates.renamed": "Caja renombrada.",
    "crates.smartBadge": "inteligente",
    "crates.smartList": "Cajas inteligentes: {names}",
    "crates.sort": "Ordenar cajas",
    "crates.sort.added": "Añadidas",
    "crates.sort.name": "Nombre",
    "crates.sort.order": "Orden",
    "detail.bpmNumber": "El BPM debe ser un número.",
    "detail.confirmRemove": "¿Quitar esta pista de la biblioteca? El archivo de audio se queda en el disco.",
    "detail.empty": "Selecciona una pista para ver sus atributos.",
    "detail.hideSearchCopies": "Ocultar copias de búsqueda",
    "detail.readFailed": "No se pudo leer la pista ({status})",
    "detail.reading": "Leyendo atributos",
    "detail.relocate": "Reubicar",
    "detail.relocatePrompt": "Ruta del archivo de audio",
    "detail.relocated": "Ubicación del archivo guardada.",
    "detail.removeFromLibrary": "Quitar de la biblioteca",
    "detail.removePrepare": "Quitar de Prepare",
    "detail.removed": "Quitada de la biblioteca.",
    "detail.removedPrepare": "Quitada de Prepare.",
    "detail.reveal": "Mostrar en {manager}",
    "detail.saveTrack": "Guardar pista",
    "detail.searchCopies": {
      one: "Copias de búsqueda, {count} campo",
      other: "Copias de búsqueda, {count} campos"
    },
    "detail.sendPrepare": "Enviar a Prepare",
    "detail.sentPrepare": "Enviada a Prepare.",
    "duplicates.readFailed": "No se pudieron leer los duplicados.",
    "error.action_unavailable": "Esa acción no está disponible.",
    "error.body_not_json": "El cuerpo de la solicitud no es JSON.",
    "error.body_not_object": "El cuerpo de la solicitud no es un objeto.",
    "error.choose_copy": "Elige la copia que quieres conservar.",
    "error.color_not_number": "El color debe ser un número.",
    "error.color_out_of_range": "El color está fuera de rango.",
    "error.consent_not_saved": "No se pudo guardar la elección sobre compartir datos.",
    "error.crate_name_separator": "Usa un nombre de caja sin el separador de nombres de Serato.",
    "error.crate_name_too_long": "Ese nombre de caja es demasiado largo.",
    "error.crate_not_in_space": "Esa caja no está en este espacio.",
    "error.field_readonly": "Ese campo no se puede editar.",
    "error.file_not_on_disk": "Ese archivo no está en el disco.",
    "error.focus_failed": "No se pudo traer la ventana al frente.",
    "error.folder_not_library": "Esa carpeta no es la biblioteca de Serato de este equipo.",
    "error.folder_outside_roots": "Esa carpeta está fuera de las carpetas de música.",
    "error.folder_unreadable": "No se pudo leer esa carpeta.",
    "error.internal": "Algo salió mal. Los detalles están en el registro local.",
    "error.invalid_request": "Esa solicitud no es válida.",
    "error.language_not_saved": "No se pudo guardar el idioma.",
    "error.layout_not_saved": "No se pudo guardar la disposición.",
    "error.legacy_read_only": "Esta biblioteca la creó una versión anterior de Serato DJ. Esta app puede mostrarla, pero todavía no puede modificarla.",
    "error.length_invalid": "La duración debe ser un número entero de milisegundos.",
    "error.library_not_saved": "No se pudo guardar la biblioteca.",
    "error.logs_not_opened": "No se pudo abrir la carpeta de registros.",
    "error.move_failed": "No se pudo mover el archivo. No se cambió nada.",
    "error.no_legacy_library": "No se encontró ninguna biblioteca antigua de Serato.",
    "error.no_library": "No se encontró ninguna biblioteca de Serato en este equipo.",
    "error.not_duplicate": "Esa pista no está en un grupo de duplicados.",
    "error.note_too_long": "La nota es demasiado larga.",
    "error.nothing_to_undo": "No hay ningún cambio externo que deshacer.",
    "error.path_unreadable": "No se pudo leer esa ruta.",
    "error.playlist_empty": "La lista de reproducción está vacía.",
    "error.rating_invalid": "La valoración debe ser un número entero del 1 al 5.",
    "error.recycle_failed": "No se pudo mover el archivo a la Papelera de reciclaje.",
    "error.related_direction": "Elige un enlace en un sentido o en ambos sentidos.",
    "error.related_missing": "Ese enlace no está en las pistas relacionadas.",
    "error.related_not_saved": "No se pudo guardar el archivo de pistas relacionadas.",
    "error.related_self": "Una pista no puede estar relacionada consigo misma.",
    "error.related_unreadable": "No se pudo leer el archivo de pistas relacionadas.",
    "error.requestFailed": "La solicitud falló",
    "error.requestStatus": "La solicitud falló ({status})",
    "error.root_color": "La raíz del espacio no tiene color.",
    "error.root_delete": "La raíz del espacio no se puede eliminar.",
    "error.root_rename": "La raíz del espacio no se puede renombrar.",
    "error.serato_version_unknown": "La versión de Serato es desconocida (compilación {build}). Las escrituras y las restauraciones están desactivadas hasta que se pueda leer la versión de Serato instalada. Un valor que no es un número con puntos, incluido un plist ilegible, es desconocido. Las instantáneas se pueden tomar y leer.",
    "error.setup_needs_consent": "Elige si quieres compartir estadísticas antes de terminar la configuración.",
    "error.setup_not_saved": "No se pudo guardar la configuración.",
    "error.shortcut_skipped": "Los accesos directos no se tocan.",
    "error.smart_rules_json": "Las reglas de la caja inteligente deben estar en JSON.",
    "error.smart_rules_list": "Las reglas de la caja inteligente necesitan una lista de reglas.",
    "error.snapshot_id_invalid": "Ese identificador de instantánea no es válido.",
    "error.snapshot_incomplete": "Esa instantánea está incompleta.",
    "error.snapshot_unreadable": "No se pudo leer esa instantánea.",
    "error.space_unavailable": "Ese espacio no está disponible aquí.",
    "error.track_id_required": "Se necesita el identificador de la pista.",
    "error.track_not_in_library": "Esa pista no está en la biblioteca.",
    "error.track_not_in_space": "La pista no está en este espacio.",
    "error.track_not_in_space_alt": "Esa pista no está en este espacio.",
    "error.track_path_required": "Se necesita la ruta de la pista.",
    "error.trash_failed": "No se pudo mover el archivo a la Papelera.",
    "error.undo_needs_confirm": "Confirma la acción de deshacer antes de guardarla.",
    "error.upload_too_large": "Ese archivo es demasiado grande.",
    "export.m3u": "Exportar",
    "field.album": "Álbum",
    "field.beatgridLocked": "Beatgrid bloqueado",
    "field.color": "Color",
    "field.comments": "Comentarios",
    "field.composer": "Compositor",
    "field.emoji": "Emoji",
    "field.genre": "Género",
    "field.grouping": "Agrupación",
    "field.label": "Sello",
    "field.rating": "Valoración",
    "field.remixer": "Remezclador",
    "field.year": "Año",
    "files.andMore": "Y {count} más.",
    "files.browseElsewhere": "Explorar otra ubicación…",
    "files.changeCrates": "Cajas: {crates}.",
    "files.checking": "Comprobando qué va a cambiar.",
    "files.chooseDelete": "Elige los archivos que quieres eliminar.",
    "files.chooseDestination": "Elige la carpeta de destino. Después confirma el traslado.",
    "files.chooseMove": "Elige los archivos que quieres mover.",
    "files.chooseOneRename": "Elige un solo archivo para renombrar.",
    "files.chooseOneReplace": "Elige un solo archivo para reemplazar.",
    "files.contents": "Contenido de la carpeta",
    "files.driveMissing": "Unidad no conectada",
    "files.driveMissingLabel": "{name}, unidad no conectada",
    "files.empty": "Esta carpeta está vacía.",
    "files.fileCount": {
      one: "{count} archivo",
      other: "{count} archivos"
    },
    "files.inLibrary": "En la biblioteca",
    "files.moveFolder": "Mover esta carpeta",
    "files.moveHere": "Mover aquí",
    "files.moveToFolder": "Mover a una carpeta",
    "files.moveToTrash": "Mover a la Papelera",
    "files.newFile": "Archivo nuevo",
    "files.newName": "Nombre nuevo",
    "files.noMatches": "Ningún archivo coincide con “{query}”.",
    "files.noRoots": "Todavía no hay carpetas de música",
    "files.noRootsBody": "La configuración encuentra las carpetas que Serato usa para tu música.",
    "files.notSaved": "Ese cambio no se guardó.",
    "files.nothingUntilConfirm": "No se cambia nada hasta que confirmes.",
    "files.open": "Abrir {name}",
    "files.path": "Ruta de la carpeta",
    "files.readingFolder": "Leyendo esta carpeta",
    "files.readingFolderNote": "Leyendo esta carpeta.",
    "files.readingRoots": "Leyendo las carpetas de música",
    "files.readingRootsNote": "Leyendo las carpetas de música.",
    "files.replaceFile": "Reemplazar archivo",
    "files.review": "Revisar",
    "files.reviewTitle": "Revisa este cambio",
    "files.rootCount": {
      one: "{count} carpeta de música",
      other: "{count} carpetas de música"
    },
    "files.roots": "Carpetas de música",
    "files.rootsUnreadable": "No se pudieron leer las carpetas de música.",
    "files.runSetup": "Iniciar configuración",
    "files.saving": "Guardando.",
    "files.searchLabel": "Buscar archivos",
    "files.searchPlaceholder": "Buscar archivos",
    "files.searchResults": "Resultados de la búsqueda",
    "files.searchTruncated": "Algunos archivos que coinciden no están en la lista. Escribe más del nombre.",
    "files.searching": "Buscando archivos…",
    "files.shortcut": "{name} (acceso directo)",
    "files.trash": "Papelera",
    "files.truncated": "Algunos archivos no aparecen en la lista.",
    "files.updated": "Se actualizaron los archivos.",
    "format.bytes": {
      one: "{count} byte",
      other: "{count} bytes"
    },
    "format.hoursMinutes": "{hours} h {minutes} min",
    "format.minutes": "{minutes} min",
    "history.chooseSession": "Elige una sesión.",
    "history.file": "Archivo",
    "history.notes": "Notas",
    "history.openInLibrary": "Abrir en la biblioteca",
    "history.readFailed": "No se pudo leer el historial.",
    "history.session": "Sesión",
    "history.sessionFailed": "No se pudo leer esa sesión.",
    "history.sessions": "Sesiones del historial",
    "history.started": "Inicio",
    "import.added": {
      one: "{count} pista añadida.",
      other: "{count} pistas añadidas."
    },
    "import.button": "Importar",
    "import.defaultName": "Lista importada",
    "import.unmatched": {
      one: "{count} línea no coincidió con ninguna pista de la biblioteca.",
      other: "{count} líneas no coincidieron con ninguna pista de la biblioteca."
    },
    "layout.resize": "Cambiar el tamaño de la lista de pistas",
    "layout.widthNotSaved": "No se pudo guardar el ancho del panel. La próxima vez vuelve al último ancho guardado.",
    "library.loading": "Cargando la biblioteca",
    "library.readFailed": "No se pudo leer la biblioteca ({status})",
    "library.unavailable": "Biblioteca no disponible",
    "list.label": "Pistas",
    "list.noMatches": "Ninguna pista coincide.",
    "list.readingDuplicates": "Leyendo duplicados",
    "logs.copied": "Registros copiados.",
    "logs.copiedTruncated": "Se copiaron las entradas más recientes del registro. Las más antiguas se omitieron.",
    "logs.copyFailed": "No se pudieron copiar los registros.",
    "logs.copyManual": "No se pudo copiar automáticamente. Selecciona el texto del registro y cópialo.",
    "logs.copying": "Copiando…",
    "logs.empty": "Todavía no hay entradas en el registro.",
    "logs.openFailed": "No se pudo abrir la carpeta de registros.",
    "logs.opened": "Se abrió la carpeta de registros.",
    "markers.beats": {
      one: "{count} tiempo",
      other: "{count} tiempos"
    },
    "markers.bpm": "{bpm} BPM",
    "markers.cue": "Cue {number}",
    "markers.flip": "Flip {number}",
    "markers.heading": "Cues, loops y beatgrid",
    "markers.loop": "Loop {number}",
    "markers.loopLocked": "Loop {number} bloqueado",
    "markers.none": "Este archivo no tiene cues de Serato.",
    "markers.readOnly": "Leídos del archivo de audio. No se vuelven a escribir.",
    "markers.unavailable": "El archivo no está en el disco, así que no se pueden leer los cues.",
    "merge.addToCrates": "Añadir la copia conservada a {crates}.",
    "merge.addToSpace": "Añadir la copia conservada al espacio {space}.",
    "merge.alreadyInCrates": "La copia conservada ya está en todas las cajas que usan las demás. Se queda donde está.",
    "merge.confirmTrash": "Combinar y mover archivos a la Papelera",
    "merge.fieldChange": "{label} cambia de {before} a {after}.",
    "merge.filesStay": "Los archivos de audio se quedan en el disco.",
    "merge.intro": "Conserva una copia. Las demás salen de la biblioteca. Los archivos de audio se quedan en el disco a menos que los muevas a la Papelera.",
    "merge.keep": "Copia que se conserva",
    "merge.keptCopy": "la copia conservada",
    "merge.merged": {
      one: "Se combinó {count} copia en {name}.",
      other: "Se combinaron {count} copias en {name}."
    },
    "merge.merging": "Combinando…",
    "merge.noCrates": "Ninguna de las copias está en una caja.",
    "merge.noFields": "No hay campos vacíos ni un número de reproducciones mayor que copiar.",
    "merge.noHistory": "Ninguna entrada del historial apunta a las otras copias.",
    "merge.noHistoryId": "Esta biblioteca no tiene un identificador de pista en el historial que se pueda reasignar.",
    "merge.plays": {
      one: "{count} reproducción",
      other: "{count} reproducciones"
    },
    "merge.previewFailed": "No se pudo leer la vista previa.",
    "merge.quitSerato": "Cierra Serato antes de combinar. La vista previa muestra el plan.",
    "merge.readingPreview": "Leyendo la vista previa…",
    "merge.removeCopies": {
      one: "Quitar {count} copia de la biblioteca.",
      other: "Quitar {count} copias de la biblioteca."
    },
    "merge.repointHistory": {
      one: "Apuntar {count} entrada del historial a la copia conservada.",
      other: "Apuntar {count} entradas del historial a la copia conservada."
    },
    "merge.title": "Combinar copias",
    "merge.trashFiles": "Mover {files} a la Papelera.",
    "merge.trashLabel": "Mover los otros archivos de audio a la Papelera",
    "merge.trashNote": "Desactivado por defecto. Los archivos van a la Papelera, desde donde puedes restaurarlos. No se eliminan para siempre.",
    "mode.duplicates": "Mismo título, artista y duración. Selecciona una copia y combina las demás en ella.",
    "mode.files": "Archivos en el disco. Los cues se quedan en el archivo de audio. Las cajas siguen la ruta.",
    "mode.missing": "Pistas que Serato ha marcado como no encontradas en este espacio.",
    "mode.snapshots": "Copias verificadas por hash de la biblioteca, las cajas y los datos de Serato dentro de los archivos de audio. El audio en sí no se copia.",
    "mode.stems": "Pistas con un estado de análisis de stems.",
    "plan.andMore": " y {count} más",
    "plan.cratesAdded": "Cajas añadidas",
    "plan.cratesChanged": "Cajas modificadas",
    "plan.cratesRemoved": "Cajas quitadas",
    "plan.cratesUnavailable": "Cajas en una unidad no disponible",
    "plan.cueChanges": "Cambios de cues",
    "plan.deletedCrates": "Cajas eliminadas",
    "plan.deletedCues": "Cues eliminados",
    "plan.deletedGrids": "Beatgrids eliminados",
    "plan.deletedTracks": "Pistas eliminadas",
    "plan.files": {
      one: "{label}: {count} archivo",
      other: "{label}: {count} archivos"
    },
    "plan.gridChanges": "Cambios de beatgrid",
    "plan.item": "elemento",
    "plan.listed": "{label}: {count}. {names}",
    "plan.none": "{label}: ninguno",
    "plan.nothingChanged": "No se ha cambiado nada.",
    "plan.tracksAdded": "Pistas añadidas",
    "plan.tracksRemoved": "Pistas quitadas",
    "plan.tracksUnavailable": "Pistas en una unidad no disponible",
    "player.cannotPlay": "Este archivo no se puede reproducir en esta ventana.",
    "player.cue": "Marca",
    "player.duration": "Duración",
    "player.elapsed": "Transcurrido",
    "player.next": "Siguiente",
    "player.notInLibrary": "No está en la biblioteca o falta el archivo",
    "player.nothingPlaying": "Nada en reproducción",
    "player.overview": "Vista general de la pista",
    "player.pause": "Pausa",
    "player.play": "Reproducir",
    "player.previous": "Anterior",
    "player.region": "Reproductor",
    "player.seek": "Posición",
    "player.volume": "Volumen",
    "player.waveformReading": "Leyendo la forma de onda…",
    "player.waveformUnavailable": "Forma de onda no disponible para este formato",
    "player.zoomIn": "Acercar",
    "player.zoomOut": "Alejar",
    "quickOpen.empty": "Escribe el nombre de una pista o de un archivo.",
    "quickOpen.file": "Archivo",
    "quickOpen.fileError": "No se pudieron buscar los archivos del disco. Las pistas que coinciden siguen en la lista.",
    "quickOpen.label": "Nombre",
    "quickOpen.matchCount": {
      one: "{count} coincidencia",
      other: "{count} coincidencias"
    },
    "quickOpen.matches": "Coincidencias",
    "quickOpen.none": "Ninguna pista ni archivo coincide con “{query}”.",
    "quickOpen.placeholder": "Nombre de la pista o del archivo",
    "quickOpen.searching": "Buscando archivos…",
    "quickOpen.title": "Buscar una pista o un archivo",
    "quickOpen.track": "Pista",
    "quickOpen.truncated": "Algunos archivos no se buscaron. Escribe más del nombre.",
    "rail.heading": "Biblioteca",
    "rating.none": "Sin valorar",
    "rating.stars": {
      one: "{count} estrella",
      other: "{count} estrellas"
    },
    "rekordbox.dialogTitle": "¿Descargar rekordbox.xml?",
    "rekordbox.download": "Descargar",
    "rekordbox.failed": "La exportación a Rekordbox falló.",
    "rekordbox.hotLoops": "Bucles de hot cue",
    "rekordbox.hotLoopsHelp": "Usa un pad de hot cue libre",
    "rekordbox.intro": "Estos elementos no se copian a Rekordbox. El archivo se descarga cuando confirmes.",
    "rekordbox.keyAsis": "Tono tal como está guardado",
    "rekordbox.keyCamelot": "Tono Camelot",
    "rekordbox.keyClassical": "Tono clásico",
    "rekordbox.keyNotation": "Notación de tono para Rekordbox",
    "rekordbox.memoryCues": "Cues de memoria",
    "rekordbox.notXml": "La exportación no generó un archivo XML.",
    "rekordbox.reportLabel": "Lo que no se copia",
    "related.confirmRemove": "¿Quitar el enlace con «{name}»?",
    "related.crateNote": "Crea o actualiza la caja «{name}». Serato debe estar cerrado.",
    "related.crateUpdated": "Caja «{name}» actualizada.",
    "related.find": "Buscar una pista para enlazar",
    "related.findPlaceholder": "Título o artista",
    "related.heading": "Pistas relacionadas",
    "related.linkRating": "Valoración del enlace",
    "related.loadFailed": "No se pudieron cargar las pistas relacionadas.",
    "related.loading": "Cargando pistas relacionadas",
    "related.noPath": "Esta pista no tiene ruta de archivo, así que no se puede enlazar.",
    "related.noSuggestions": "No hay sugerencias por tono, tempo o cajas en común.",
    "related.noneSaved": "Todavía no hay enlaces guardados. Busca una pista o guarda una sugerencia.",
    "related.notInLibrary": "No está en esta biblioteca",
    "related.note": "Nota",
    "related.notePlaceholder": "mezclar al salir de",
    "related.oneWay": "En un sentido",
    "related.quitSerato": "Cierra Serato antes de escribir la caja.",
    "related.ratingOutOf": "{rating}/5",
    "related.removeLink": "Quitar el enlace con {name}",
    "related.removed": "Enlace quitado.",
    "related.saveLink": "Guardar enlace",
    "related.saveLinkTo": "Guardar enlace con {name}",
    "related.saved": "Enlace guardado.",
    "related.savedCount": "{count} guardados",
    "related.suggested": "Sugeridas por tono, tempo con un margen del 6 % y cajas en común. Guardar crea un enlace en ambos sentidos.",
    "related.thisTrack": "esta pista",
    "related.twoWay": "En ambos sentidos",
    "related.twoWayLink": "Enlace en ambos sentidos",
    "related.typeHint": "Escribe un título o un artista.",
    "related.updateCrate": "Actualizar caja de Serato",
    "rules.and": "y",
    "rules.label": "Reglas de la caja inteligente",
    "rules.matches": "Coincide",
    "rules.none": "todavía no hay reglas",
    "rules.or": "o",
    "rules.save": "Guardar reglas",
    "rules.saved": "Reglas guardadas.",
    "search.tracks": "Buscar pistas",
    "settings.about": "Acerca de",
    "settings.copyLogs": "Copiar registros",
    "settings.copyVersion": "Copiar versión",
    "settings.language": "Idioma",
    "settings.languageNotSaved": "No se pudo guardar el idioma. Se usa hasta que cierres la app.",
    "settings.languageSystem": "El mismo que el sistema",
    "settings.logText": "Texto del registro",
    "settings.openLogs": "Abrir carpeta de registros",
    "settings.rerunSetup": "Repetir la configuración",
    "settings.share": "Compartir estadísticas de uso anónimas e informes de errores",
    "settings.title": "Ajustes",
    "sharing.canSend": "Se pueden enviar recuentos anónimos e informes de errores.",
    "sharing.loadFailed": "No se pudieron cargar los ajustes de privacidad.",
    "sharing.loadFailedOff": "No se pudieron cargar los ajustes de privacidad. No se envía nada.",
    "sharing.noKeys": "Esta copia no tiene claves de telemetría, así que no se envía nada en ningún caso.",
    "sharing.nothingSent": "No se envía nada.",
    "sharing.off": "Compartir está desactivado. No se envía nada.",
    "sharing.on": "Compartir está activado. Se pueden enviar recuentos anónimos e informes de errores.",
    "shortcuts.action": "Acción",
    "shortcuts.cheatSheet": "Mostrar atajos",
    "shortcuts.dismiss": "Cerrar o borrar la búsqueda",
    "shortcuts.focusSearch": "Enfocar la búsqueda",
    "shortcuts.groupFind": "Buscar",
    "shortcuts.groupLists": "Listas",
    "shortcuts.groupPlay": "Reproducción",
    "shortcuts.groupViews": "Vistas",
    "shortcuts.intro": "Estas teclas funcionan en cualquier parte de esta pantalla, excepto mientras escribes en un campo. Esc sigue cerrando un diálogo o borrando una búsqueda.",
    "shortcuts.key": "Tecla",
    "shortcuts.listNext": "Fila siguiente",
    "shortcuts.listOpen": "Abrir la fila",
    "shortcuts.listPrevious": "Fila anterior",
    "shortcuts.open": "Atajos",
    "shortcuts.playNote": "Espacio reproduce o pausa. Izquierda retrocede 5 segundos. Derecha avanza 5 segundos.",
    "shortcuts.playPause": "Reproducir o pausar",
    "shortcuts.quickOpen": "Buscar una pista o un archivo",
    "shortcuts.seekBack": "Retroceder 5 segundos",
    "shortcuts.seekForward": "Avanzar 5 segundos",
    "shortcuts.title": "Atajos de teclado",
    "shortcuts.viewCrates": "Cajas",
    "shortcuts.viewFiles": "Archivos",
    "shortcuts.viewHistory": "Historial",
    "shortcuts.viewLibrary": "Biblioteca",
    "shortcuts.viewSnapshots": "Instantáneas",
    "snapshots.count": {
      one: "{count} instantánea",
      other: "{count} instantáneas"
    },
    "snapshots.empty": "Todavía no hay instantáneas. Toma una para guardar un punto al que puedas volver. Las instantáneas se conservan y esta página no las caduca.",
    "snapshots.noSearch": "Instantáneas no tiene búsqueda. Pulsa Ctrl+K para buscar una pista o un archivo.",
    "snapshots.outsideChange": "Algo ajeno a esta app cambió la carpeta de Serato. Se guardó una instantánea después de ese cambio. Deshacer restaura la instantánea anterior.",
    "snapshots.outsideChangeLexicon": "Lexicon cambió la carpeta de Serato. Se guardó una instantánea después de ese cambio. Deshacer restaura la instantánea anterior.",
    "snapshots.reading": "Leyendo instantáneas",
    "snapshots.readingPlan": "Leyendo qué cambiaría",
    "snapshots.restore": "Restaurar",
    "snapshots.restoreIntro": "No se cambia nada hasta que confirmes. Primero se guarda una instantánea nueva, así que esta restauración se puede deshacer.",
    "snapshots.restoreTitle": "Restaurar esta instantánea",
    "snapshots.restored": "Restauración terminada. La biblioteca anterior se guardó primero, así que puedes deshacerla desde la lista.",
    "snapshots.restoring": "Restaurando…",
    "snapshots.reviewRestore": "Revisar restauración",
    "snapshots.reviewUndo": "Revisar deshacer",
    "snapshots.saved": "Instantánea guardada.",
    "snapshots.saving": "Guardando instantánea…",
    "snapshots.seratoUnknown": "Versión de Serato desconocida",
    "snapshots.seratoVersion": "Serato {version} (compilación {build})",
    "snapshots.take": "Tomar una instantánea",
    "snapshots.trigger": "instantánea",
    "snapshots.unavailableDrives": "No disponibles: {drives}.",
    "snapshots.unknownTime": "Hora desconocida",
    "snapshots.unreadable": "No se pudieron leer las instantáneas.",
    "space.appleMusic": "Apple Music",
    "space.label": "Espacio",
    "space.library": "Biblioteca",
    "space.prepare": "Prepare",
    "space.video": "Vídeo",
    "status.checking": "Comprobando Serato",
    "status.library": "Biblioteca",
    "tip.consentAccept": "Envía recuentos de uso anónimos e informes de fallos.",
    "tip.consentDecline": "No envía recuentos de uso ni informes de fallos.",
    "tip.copyLogs": "Copia los registros de la app para poder pegarlos.",
    "tip.copyVersion": "Copia el número de versión.",
    "tip.crateCollapse": "Oculta las cajas que hay dentro de esta.",
    "tip.crateColor": "Cambia el color de esta caja.",
    "tip.crateDelete": "Elimina esta caja. Sus archivos de música siguen en el disco.",
    "tip.crateExpand": "Muestra las cajas que hay dentro de esta.",
    "tip.crateMember": "Marca la casilla para mantener esta pista en esta caja.",
    "tip.crateNew": "Crea una caja nueva.",
    "tip.crateRename": "Cambia el nombre de esta caja.",
    "tip.crateRow": "Muestra las pistas de esta caja.",
    "tip.crateSearch": "Escribe un nombre para acotar la lista de cajas.",
    "tip.crateSortAdded": "Muestra primero las cajas más nuevas.",
    "tip.crateSortName": "Ordena las cajas de la A a la Z.",
    "tip.crateSortOrder": "Ordena las cajas como en Serato.",
    "tip.dialogCancel": "Cierra este cuadro. No cambia nada.",
    "tip.dialogClose": "Cierra este cuadro.",
    "tip.duplicateCopy": "Muestra los detalles de esta copia.",
    "tip.exportM3u": "Descarga esta lista como archivo de lista de reproducción.",
    "tip.exportRekordbox": "Descarga un archivo rekordbox.xml de esta biblioteca.",
    "tip.filesConfirm": "Haz este cambio.",
    "tip.filesCrumb": "Ve a esta carpeta.",
    "tip.filesDelete": "Mueve los archivos elegidos a la Papelera.",
    "tip.filesDriveMissing": "Esta unidad no está conectada. Conéctala e inténtalo de nuevo.",
    "tip.filesElsewhere": "Busca en una carpeta fuera de tus carpetas de música.",
    "tip.filesMove": "Mueve los archivos elegidos a otra carpeta.",
    "tip.filesMoveFolder": "Mueve toda esta carpeta.",
    "tip.filesMoveHere": "Mueve los archivos a esta carpeta.",
    "tip.filesName": "Escribe el nombre nuevo.",
    "tip.filesOpen": "Abre esta carpeta.",
    "tip.filesPickCancel": "Detén el movimiento. No cambia nada.",
    "tip.filesRefresh": "Vuelve a leer esta carpeta.",
    "tip.filesRename": "Cambia el nombre del archivo elegido.",
    "tip.filesReplace": "Cambia el archivo elegido por otro. Sus marcas y cajas se conservan.",
    "tip.filesReplacement": "Escribe la ruta completa del archivo nuevo.",
    "tip.filesReview": "Mira qué va a cambiar. Aún no cambia nada.",
    "tip.filesRunSetup": "Ejecuta la instalación para encontrar tu biblioteca.",
    "tip.filesSearch": "Escribe un nombre para buscar un archivo en esta carpeta.",
    "tip.filesSelect": "Marca la casilla para elegir este archivo.",
    "tip.filesShortcut": "Es un acceso directo a otro lugar del disco.",
    "tip.filesUp": "Sube a la carpeta que contiene esta.",
    "tip.historySession": "Muestra las pistas que sonaron en esta sesión.",
    "tip.importM3u": "Crea una caja nueva a partir de un archivo de lista de reproducción.",
    "tip.logFallback": "Los registros de la app. Selecciona el texto para copiarlo.",
    "tip.mergeConfirm": "Fusiona las copias en la que has elegido.",
    "tip.mergeCopies": "Conserva una copia de esta pista y quita las demás.",
    "tip.mergeKeep": "Elige esta copia para conservarla.",
    "tip.mergeTrash": "Marca la casilla para mover también los otros archivos a la Papelera.",
    "tip.openInLibrary": "Abre la pista de este stem en la biblioteca.",
    "tip.openLogs": "Abre la carpeta con los registros de la app.",
    "tip.openSettings": "Abre los ajustes de uso compartido, registros e instalación.",
    "tip.openShortcuts": "Muestra los atajos de teclado.",
    "tip.playerCue": "Salta a esta marca.",
    "tip.playerNext": "Ve a la pista siguiente.",
    "tip.playerPrevious": "Ve a la pista anterior.",
    "tip.playerSeek": "Arrastra para moverte por la pista.",
    "tip.playerToggle": "Reproduce o pausa la pista.",
    "tip.playerVolume": "Cambia el volumen de la pista.",
    "tip.prepareRemove": "Quita esta pista de la lista Preparar.",
    "tip.prepareSend": "Añade esta pista a la lista Preparar.",
    "tip.quickOpenQuery": "Escribe parte del nombre de una pista o un archivo.",
    "tip.quickOpenResult": "Abre esta pista o este archivo.",
    "tip.quickOpenRetry": "Vuelve a buscar los archivos en el disco.",
    "tip.rekordboxDownload": "Descarga el archivo rekordbox.xml.",
    "tip.rekordboxHotLoops": "Añade los bucles guardados al archivo de Rekordbox. Cada uno usa un pad libre.",
    "tip.rekordboxKey": "Elige cómo se escriben las tonalidades en el archivo de Rekordbox.",
    "tip.rekordboxMemory": "Incluye las marcas de memoria en el archivo de Rekordbox.",
    "tip.relatedChoose": "Elige esta pista para enlazarla.",
    "tip.relatedCrate": "Actualiza la caja de Serato que contiene estas pistas relacionadas.",
    "tip.relatedMutual": "Marca la casilla para mostrar el enlace en las dos pistas.",
    "tip.relatedNote": "Añade una nota sobre cómo combinan estas pistas.",
    "tip.relatedOpen": "Muestra esta pista relacionada.",
    "tip.relatedRating": "Valora lo bien que combinan estas pistas.",
    "tip.relatedRemove": "Quita este enlace. Las dos pistas siguen en la biblioteca.",
    "tip.relatedSave": "Guarda este enlace.",
    "tip.relatedSearch": "Escribe un título o un artista para buscar una pista que enlazar.",
    "tip.relatedSuggestionSave": "Guarda esta sugerencia como enlace.",
    "tip.reload": "Vuelve a leer la biblioteca para recoger los cambios nuevos.",
    "tip.rerunWizard": "Vuelve a hacer la instalación inicial.",
    "tip.rowPlay": "Reproduce esta pista.",
    "tip.search": "Escribe un título o un artista para acotar la lista.",
    "tip.searchCopies": "Muestra u oculta los campos de las otras copias.",
    "tip.settingsLanguage": "Elige el idioma de esta app.",
    "tip.smartRules": "Edita las reglas que eligen las pistas de esta caja.",
    "tip.smartRulesSave": "Guarda las reglas de esta caja inteligente.",
    "tip.snapshotConfirm": "Devuelve tu biblioteca a esta instantánea.",
    "tip.snapshotRestore": "Mira qué cambiaría restaurar esta instantánea. Aún no cambia nada.",
    "tip.snapshotsRefresh": "Vuelve a leer la lista de instantáneas.",
    "tip.snapshotsRetry": "Intenta leer las instantáneas de nuevo.",
    "tip.snapshotsTake": "Guarda ahora una copia de tu biblioteca.",
    "tip.snapshotsUndo": "Mira qué haría deshacer el cambio externo. Aún no cambia nada.",
    "tip.sortColumn": "Ordena la lista por esta columna. Vuelve a hacer clic para invertirla.",
    "tip.space": "Elige qué parte de tu biblioteca quieres mostrar.",
    "tip.splitter": "Arrastra para cambiar el tamaño de la lista. Haz doble clic para restablecerlo.",
    "tip.telemetryToggle": "Marca la casilla para enviar recuentos de uso anónimos e informes de fallos.",
    "tip.trackAlbum": "El nombre del álbum.",
    "tip.trackArtist": "El nombre del artista.",
    "tip.trackBpm": "La velocidad en pulsaciones por minuto.",
    "tip.trackColor": "Elige el color que marca esta pista.",
    "tip.trackComments": "Tus propias notas sobre esta pista.",
    "tip.trackComposer": "La persona que escribió la pista.",
    "tip.trackEmoji": "Un emoji para marcar esta pista.",
    "tip.trackGenre": "El estilo de música.",
    "tip.trackGridLock": "Marca la casilla para que no se pueda cambiar el beatgrid.",
    "tip.trackGrouping": "Tu propio nombre de grupo para esta pista.",
    "tip.trackKey": "La tonalidad musical.",
    "tip.trackLabel": "El sello discográfico.",
    "tip.trackRating": "Da a esta pista una valoración en estrellas.",
    "tip.trackRelocate": "Indica dónde está ahora el archivo de esta pista.",
    "tip.trackRemixer": "La persona que hizo el remix de la pista.",
    "tip.trackRemove": "Quita esta pista de la biblioteca. El archivo sigue en el disco.",
    "tip.trackReveal": "Muestra el archivo de esta pista en tu equipo.",
    "tip.trackRow": "Muestra los detalles de esta pista.",
    "tip.trackSave": "Guarda tus cambios en esta pista.",
    "tip.trackTitle": "El título de la pista.",
    "tip.trackYear": "El año en que salió la pista.",
    "tip.viewCrates": "Muestra tus cajas y sus pistas.",
    "tip.viewDuplicates": "Muestra las pistas que están más de una vez en la biblioteca.",
    "tip.viewFiles": "Muestra los archivos de música de este equipo.",
    "tip.viewHistory": "Muestra las sesiones que has pinchado.",
    "tip.viewMissing": "Muestra las pistas cuyos archivos no se encuentran.",
    "tip.viewSnapshots": "Muestra las copias guardadas de tu biblioteca.",
    "tip.viewStems": "Muestra las pistas que tienen stems.",
    "tip.waveformOverview": "Haz clic o arrastra para moverte por la pista.",
    "tip.waveformZoomIn": "Muestra menos de la pista con más detalle.",
    "tip.waveformZoomOut": "Muestra más de la pista con menos detalle.",
    "tip.wizardBack": "Vuelve un paso atrás.",
    "tip.wizardCancel": "Cierra la instalación. Volverá a abrirse la próxima vez.",
    "tip.wizardFolder": "Abre esta carpeta.",
    "tip.wizardFolderClose": "Cierra la lista de carpetas.",
    "tip.wizardFolderUp": "Sube a la carpeta que contiene esta.",
    "tip.wizardFolderUse": "Usa la carpeta que estás viendo.",
    "tip.wizardNo": "No envía recuentos de uso ni informes de fallos.",
    "tip.wizardPrimary": "Pasa al siguiente paso.",
    "tip.wizardSecondary": "Busca tú mismo la carpeta de tu biblioteca.",
    "tip.wizardYes": "Envía recuentos de uso anónimos e informes de fallos.",
    "track.missingBadge": "no encontrada",
    "track.numbered": "Pista {id}",
    "track.stemsBadge": "stems",
    "track.untitled": "Sin título",
    "version.app": "Versión de la app",
    "version.copied": "Copiada",
    "version.copyFailed": "No se pudo copiar la versión.",
    "version.unavailable": "Versión no disponible",
    "view.crates": "Cajas",
    "view.duplicates": "Duplicados",
    "view.files": "Archivos",
    "view.history": "Historial",
    "view.label": "Vistas",
    "view.missing": "No encontradas",
    "view.snapshots": "Instantáneas",
    "view.stems": "Stems",
    "wizard.action.checkAgain": "Volver a buscar",
    "wizard.action.continue": "Continuar",
    "wizard.action.getStarted": "Empezar",
    "wizard.action.looking": "Buscando…",
    "wizard.action.openLibrary": "Abrir mi biblioteca",
    "wizard.action.takeSnapshot": "Tomar una instantánea de seguridad",
    "wizard.action.tryAgain": "Reintentar",
    "wizard.action.useLibrary": "Usar esta biblioteca",
    "wizard.announce": "Paso {index} de {count}. {name}.",
    "wizard.blocked": "Cierra Serato DJ para continuar.",
    "wizard.chooseCheckAgain": "Elige Volver a buscar.",
    "wizard.chooseFolder": "Elegir una carpeta",
    "wizard.closeFolders": "Cerrar la lista de carpetas",
    "wizard.consentFailed": "No se pudo guardar esa elección. Inténtalo de nuevo.",
    "wizard.copySaved": "Copia de seguridad guardada.",
    "wizard.done": "Biblioteca lista. Instantánea guardada.",
    "wizard.finishFailed": "No se pudo guardar que terminaste la configuración. Inténtalo de nuevo.",
    "wizard.folders": "Carpetas",
    "wizard.genericError": "Algo salió mal. Inténtalo de nuevo.",
    "wizard.heading.consent": "¿Compartir estadísticas de uso anónimas e informes de errores?",
    "wizard.heading.library": "Encuentra tu biblioteca",
    "wizard.heading.snapshot": "Instantánea de seguridad",
    "wizard.heading.welcome": "Mira tu biblioteca de Serato",
    "wizard.lookFailed": "No se pudo buscar tu biblioteca.",
    "wizard.looking": "Buscando tu biblioteca de Serato.",
    "wizard.no": "No, no compartir",
    "wizard.noSubfolders": "Esta carpeta no contiene otras carpetas.",
    "wizard.opening": "Abriendo…",
    "wizard.progressLabel": "Guardando una copia de seguridad",
    "wizard.saving": "Guardando…",
    "wizard.savingCopy": "Guardando una copia de seguridad…",
    "wizard.savingLibraryCopy": "Guardando una copia de seguridad de tu biblioteca.",
    "wizard.snapshotBody": "Se guarda una copia de seguridad de los datos de tu biblioteca antes de cambiar nada.",
    "wizard.snapshotFailed": "No se pudo guardar la copia de seguridad. Tu biblioteca no cambió. Inténtalo de nuevo.",
    "wizard.step.consent": "Compartir",
    "wizard.step.done": "Listo",
    "wizard.step.library": "Encuentra tu biblioteca",
    "wizard.step.snapshot": "Instantánea de seguridad",
    "wizard.step.welcome": "Bienvenida",
    "wizard.stepOf": "Paso {index} de {count}",
    "wizard.useFolder": "Usar esta carpeta",
    "wizard.welcomeBody": "Esta app muestra la biblioteca que Serato ya guarda en este equipo. No cambiará nada sin preguntar.",
    "wizard.yes": "Sí, compartir"
  };

  // src/i18n.ts
  var LANGUAGES = ["en", "es"];
  var PSEUDO = "qps-ploc";
  var CATALOGS = {
    en: en_default,
    es: es_default
  };
  var LOCALE_EVENT = "serato-locale";
  function isLanguage(value) {
    return typeof value === "string" && LANGUAGES.includes(value);
  }
  function getLocale() {
    const lang = typeof document === "undefined" ? "" : document.documentElement.lang;
    if (lang === PSEUDO) return PSEUDO;
    return isLanguage(lang) ? lang : "en";
  }
  function onLocaleChange(listener) {
    const handler = () => listener(getLocale());
    document.addEventListener(LOCALE_EVENT, handler);
    return () => document.removeEventListener(LOCALE_EVENT, handler);
  }
  var ACCENTS = {
    a: "à",
    e: "é",
    i: "ï",
    o: "ö",
    u: "ü",
    c: "ç",
    n: "ñ",
    y: "ý",
    A: "Å",
    E: "É",
    I: "Î",
    O: "Ø",
    U: "Û",
    C: "Ç",
    N: "Ñ",
    Y: "Ý"
  };
  function pseudo(text2) {
    const parts = text2.split(/(\{[a-zA-Z0-9_]+\})/);
    const body = parts.map((part) => part.startsWith("{") ? part : part.replace(/[a-zA-Z]/g, (ch) => ACCENTS[ch] ?? ch)).join("");
    const letters = text2.replace(/\{[a-zA-Z0-9_]+\}/g, "").length;
    const pad = "~".repeat(Math.max(1, Math.ceil(letters * 0.3)));
    return `[${body} ${pad}]`;
  }
  function catalogFor(locale) {
    return locale === PSEUDO ? CATALOGS.en : CATALOGS[locale];
  }
  function pick(message, count, locale) {
    if (typeof message === "string") return message;
    if (count === void 0) return message.other;
    const rules = new Intl.PluralRules(locale === PSEUDO ? "en" : locale);
    const exact = count === 0 ? message.zero : void 0;
    return exact ?? message[rules.select(count)] ?? message.other;
  }
  function fill(text2, params, locale) {
    if (!params) return text2;
    const tag = locale === PSEUDO ? "en" : locale;
    return text2.replace(/\{([a-zA-Z0-9_]+)\}/g, (whole, name) => {
      const value = params[name];
      if (value === void 0) return whole;
      return typeof value === "number" ? new Intl.NumberFormat(tag).format(value) : value;
    });
  }
  function t(key, params) {
    const locale = getLocale();
    const message = catalogFor(locale)[key] ?? CATALOGS.en[key];
    const count = typeof params?.count === "number" ? params.count : void 0;
    const template = pick(message, count, locale);
    return fill(locale === PSEUDO ? pseudo(template) : template, params, locale);
  }
  function hasKey(key) {
    return Object.prototype.hasOwnProperty.call(CATALOGS.en, key);
  }
  function codedText(text2, code, params) {
    if (typeof code === "string") {
      const key = `error.${code}`;
      if (hasKey(key)) return t(key, params ?? void 0);
    }
    return text2;
  }
  function serverMessage(body, fallback) {
    if (typeof body?.code === "string") return codedText(body.error || fallback, body.code, body.params);
    return body?.error || fallback;
  }

  // src/wizard.ts
  var STEP_NAME = {
    welcome: "wizard.step.welcome",
    library: "wizard.step.library",
    snapshot: "wizard.step.snapshot",
    consent: "wizard.step.consent",
    done: "wizard.step.done"
  };
  function visibleSteps(needsConsent) {
    const steps = ["welcome", "library", "snapshot"];
    if (needsConsent) steps.push("consent");
    steps.push("done");
    return steps;
  }
  function createWizard(input) {
    return {
      step: "welcome",
      complete: false,
      dismissed: false,
      context: {
        needsConsent: input.needsConsent,
        library: input.library,
        seratoRunning: input.seratoRunning,
        snapshot: "idle",
        consent: null
      }
    };
  }
  function reduceWizard(model2, action) {
    if (model2.dismissed || model2.complete) return model2;
    switch (action.type) {
      case "cancel":
        return { ...model2, dismissed: true, complete: false };
      case "back":
        return goBack(model2);
      case "next":
        return goNext(model2);
      case "library":
        return { ...model2, context: { ...model2.context, library: action.status } };
      case "serato":
        return { ...model2, context: { ...model2.context, seratoRunning: action.running } };
      case "snapshot":
        return { ...model2, context: { ...model2.context, snapshot: action.phase } };
      case "consent":
        return goNext({ ...model2, context: { ...model2.context, consent: action.value } });
      case "finish":
        if (model2.step !== "done") return model2;
        return { ...model2, complete: true };
      default:
        return model2;
    }
  }
  function stepPosition(model2) {
    const steps = visibleSteps(model2.context.needsConsent);
    const found = steps.indexOf(model2.step);
    const index = found < 0 ? 1 : found + 1;
    return { index, count: steps.length, name: t(STEP_NAME[model2.step]) };
  }
  function canGoBack(model2) {
    if (model2.dismissed || model2.complete) return false;
    if (model2.step === "snapshot" && model2.context.snapshot === "saving") return false;
    return visibleSteps(model2.context.needsConsent).indexOf(model2.step) > 0;
  }
  function canAdvance(model2) {
    if (model2.dismissed || model2.complete) return false;
    switch (model2.step) {
      case "welcome":
        return true;
      case "library":
        return model2.context.library === "found";
      case "snapshot":
        return model2.context.snapshot === "saved";
      case "consent":
        return model2.context.consent !== null;
      case "done":
        return false;
      default:
        return false;
    }
  }
  function snapshotBlocked(model2) {
    return model2.step === "snapshot" && model2.context.seratoRunning && model2.context.snapshot !== "saved";
  }
  function primaryAction(model2) {
    switch (model2.step) {
      case "welcome":
        return "get-started";
      case "library":
        if (model2.context.library === "pending") return "looking";
        if (model2.context.library === "found") return "use-library";
        return "check-again";
      case "snapshot":
        if (model2.context.snapshot === "saved") return "continue";
        if (model2.context.snapshot === "error") return "try-again";
        return "take-snapshot";
      case "consent":
        return "none";
      case "done":
        return "open-library";
      default:
        return "none";
    }
  }
  function primaryEnabled(model2) {
    if (model2.dismissed || model2.complete) return false;
    const action = primaryAction(model2);
    if (action === "none" || action === "looking") return false;
    if (model2.step === "snapshot" && model2.context.snapshot === "saving") return false;
    if (snapshotBlocked(model2)) return false;
    return true;
  }
  function stepAnnouncement(model2) {
    const position = stepPosition(model2);
    return t("wizard.announce", { index: position.index, count: position.count, name: position.name });
  }
  function goBack(model2) {
    if (!canGoBack(model2)) return model2;
    const steps = visibleSteps(model2.context.needsConsent);
    const index = steps.indexOf(model2.step);
    const previous = steps[index - 1];
    if (previous === void 0) return model2;
    return { ...model2, step: previous };
  }
  function goNext(model2) {
    if (!canAdvance(model2)) return model2;
    const steps = visibleSteps(model2.context.needsConsent);
    const index = steps.indexOf(model2.step);
    const next = steps[index + 1];
    if (next === void 0) return model2;
    return { ...model2, step: next };
  }

  // src/tips.ts
  function tip(control, key, detail) {
    control.dataset.tip = key;
    if (detail) control.dataset.tipDetail = detail;
  }

  // src/wizard-view.ts
  var LABELS = {
    "get-started": "wizard.action.getStarted",
    looking: "wizard.action.looking",
    "use-library": "wizard.action.useLibrary",
    "check-again": "wizard.action.checkAgain",
    "take-snapshot": "wizard.action.takeSnapshot",
    "try-again": "wizard.action.tryAgain",
    continue: "wizard.action.continue",
    "open-library": "wizard.action.openLibrary"
  };
  var HEADINGS = {
    welcome: "wizard.heading.welcome",
    library: "wizard.heading.library",
    snapshot: "wizard.heading.snapshot",
    consent: "wizard.heading.consent",
    done: "wizard.done"
  };
  var noteKey = (key) => () => t(key);
  var noteText = (value) => () => value;
  var wired = false;
  var starting = false;
  var generation = 0;
  var busy = false;
  var model = createWizard({
    needsConsent: true,
    library: "pending",
    seratoRunning: false
  });
  var options = {};
  var summary = null;
  var nextText = null;
  var statusNote = null;
  var folderOpen = false;
  var folderPath = "";
  var folderParent = null;
  var pollTimer = 0;
  var polling = false;
  function open(next = {}) {
    wire();
    if (starting) return;
    const dialog = wizardDialog();
    if (dialog.open && !next.force) return;
    options = next;
    starting = true;
    void begin(next).finally(() => {
      starting = false;
    });
  }
  function wire() {
    if (wired) return;
    wired = true;
    onLocaleChange(() => {
      if (wizardDialog().open) paint(false);
    });
    button("wizard-primary").addEventListener("click", () => {
      void onPrimary();
    });
    button("wizard-back").addEventListener("click", () => {
      onBack();
    });
    button("wizard-cancel").addEventListener("click", () => {
      cancel();
    });
    button("wizard-secondary").addEventListener("click", () => {
      void showFolders();
    });
    button("wizard-no").addEventListener("click", () => {
      void chooseConsent(false);
    });
    button("wizard-yes").addEventListener("click", () => {
      void chooseConsent(true);
    });
    button("wizard-folder-up").addEventListener("click", () => {
      if (folderParent) void browse(folderParent);
    });
    button("wizard-folder-use").addEventListener("click", () => {
      void useFolder();
    });
    button("wizard-folder-close").addEventListener("click", () => {
      closeFolders();
    });
    wizardDialog().addEventListener("cancel", (event) => {
      event.preventDefault();
      if (folderOpen) {
        closeFolders();
        return;
      }
      cancel();
    });
  }
  async function begin(next) {
    generation += 1;
    const token = generation;
    stopPoll();
    folderOpen = false;
    statusNote = null;
    busy = false;
    const settings = await loadSettings();
    if (token !== generation) return;
    if (settings.wizard_complete && !next.force) return;
    const setup = await loadSetup();
    if (token !== generation) return;
    summary = setup ? noteText(setup.summary) : noteKey("wizard.lookFailed");
    nextText = setup ? noteText(setup.next) : noteKey("wizard.chooseCheckAgain");
    if (setup) publishStatus(setup);
    const library = setup === null ? "error" : setup.found ? "found" : "missing";
    model = createWizard({
      needsConsent: settings.needs_consent_prompt,
      library,
      seratoRunning: setup?.seratoRunning ?? false
    });
    paint(false);
    const dialog = wizardDialog();
    if (!dialog.open) dialog.showModal();
    text("wizard-announce").textContent = stepAnnouncement(model);
    text("wizard-title").focus();
    ensurePoll();
  }
  function onBack() {
    if (!canGoBack(model) || busy) return;
    folderOpen = false;
    statusNote = null;
    model = reduceWizard(model, { type: "back" });
    paint(true);
    ensurePoll();
  }
  function cancel() {
    generation += 1;
    stopPoll();
    folderOpen = false;
    busy = false;
    model = reduceWizard(model, { type: "cancel" });
    closeDialog();
  }
  async function onPrimary() {
    if (busy || !primaryEnabled(model)) return;
    const action = primaryAction(model);
    if (action === "get-started" || action === "use-library" || action === "continue") {
      folderOpen = false;
      statusNote = null;
      model = reduceWizard(model, { type: "next" });
      paint(true);
      ensurePoll();
      if (model.step === "snapshot") void refreshSerato();
      return;
    }
    if (action === "check-again") {
      await recheck();
      return;
    }
    if (action === "take-snapshot" || action === "try-again") {
      await takeSnapshot();
      return;
    }
    if (action === "open-library") {
      await finish();
    }
  }
  async function recheck() {
    const token = generation;
    busy = true;
    statusNote = null;
    paint(false);
    const setup = await loadSetup();
    if (token !== generation) return;
    busy = false;
    if (setup === null) {
      summary = noteKey("wizard.lookFailed");
      nextText = noteKey("wizard.chooseCheckAgain");
      model = reduceWizard(model, { type: "library", status: "error" });
    } else {
      summary = noteText(setup.summary);
      nextText = noteText(setup.next);
      publishStatus(setup);
      model = reduceWizard(model, { type: "serato", running: setup.seratoRunning });
      model = reduceWizard(model, { type: "library", status: setup.found ? "found" : "missing" });
    }
    paint(false);
  }
  async function takeSnapshot() {
    if (snapshotBlocked(model)) return;
    const token = generation;
    busy = true;
    statusNote = null;
    model = reduceWizard(model, { type: "snapshot", phase: "saving" });
    paint(false);
    try {
      await postJSON("/api/snapshots", { action: "create" }, 10 * 60 * 1e3);
      if (token !== generation) return;
      model = reduceWizard(model, { type: "snapshot", phase: "saved" });
    } catch {
      if (token !== generation) return;
      model = reduceWizard(model, { type: "snapshot", phase: "error" });
      statusNote = noteKey("wizard.snapshotFailed");
    } finally {
      if (token === generation) {
        busy = false;
        paint(false);
      }
    }
  }
  async function chooseConsent(value) {
    if (busy || model.step !== "consent") return;
    const token = generation;
    busy = true;
    statusNote = noteKey("wizard.saving");
    paint(false);
    try {
      const payload = await postJSON("/api/settings", { telemetry_consent: value }, 15e3);
      if (token !== generation) return;
      const settings = readSettings(payload);
      if (settings) options.onSettings?.(settings);
      busy = false;
      statusNote = null;
      model = reduceWizard(model, { type: "consent", value });
      paint(true);
    } catch {
      if (token !== generation) return;
      busy = false;
      statusNote = noteKey("wizard.consentFailed");
      paint(false);
    }
  }
  async function finish() {
    const token = generation;
    busy = true;
    statusNote = noteKey("wizard.opening");
    paint(false);
    try {
      const payload = await postJSON("/api/settings", { wizard_complete: true }, 15e3);
      if (token !== generation) return;
      const settings = readSettings(payload);
      if (settings) options.onSettings?.(settings);
      model = reduceWizard(model, { type: "finish" });
      closeDialog();
    } catch (error) {
      if (token !== generation) return;
      statusNote = error instanceof Error ? noteText(error.message) : noteKey("wizard.finishFailed");
      busy = false;
      paint(false);
    }
  }
  async function showFolders() {
    folderOpen = true;
    paint(false);
    await browse(folderPath);
  }
  function closeFolders() {
    folderOpen = false;
    paint(false);
    button("wizard-secondary").focus();
  }
  async function browse(path) {
    const token = generation;
    try {
      const query = path ? `?browse=${encodeURIComponent(path)}` : "?browse=";
      const payload = await getJSON(`/api/setup${query}`, 15e3);
      if (token !== generation) return;
      const listing = readBrowse(payload);
      if (!listing) {
        statusNote = noteKey("error.folder_unreadable");
        paint(false);
        return;
      }
      folderPath = listing.path;
      folderParent = listing.parent;
      text("wizard-folder-name").textContent = listing.name;
      fillFolders(listing.folders);
      button("wizard-folder-up").disabled = listing.parent === null;
      paint(false);
    } catch {
      if (token !== generation) return;
      statusNote = noteKey("error.folder_unreadable");
      paint(false);
    }
  }
  async function useFolder() {
    if (!folderPath || busy) return;
    const token = generation;
    busy = true;
    paint(false);
    try {
      const payload = await postJSON("/api/setup", { folder: folderPath }, 15e3);
      if (token !== generation) return;
      const setup = readSetup(payload);
      if (!setup) {
        statusNote = noteKey("error.folder_unreadable");
        return;
      }
      summary = noteText(setup.summary);
      nextText = noteText(setup.next);
      publishStatus(setup);
      model = reduceWizard(model, { type: "serato", running: setup.seratoRunning });
      model = reduceWizard(model, { type: "library", status: setup.found ? "found" : "missing" });
      if (setup.found) folderOpen = false;
      statusNote = null;
    } catch (error) {
      if (token !== generation) return;
      statusNote = error instanceof Error ? noteText(error.message) : noteKey("error.folder_unreadable");
    } finally {
      if (token === generation) {
        busy = false;
        paint(false);
        if (model.context.library === "found") button("wizard-primary").focus();
      }
    }
  }
  function fillFolders(folders) {
    const list = element("wizard-folder-list");
    list.replaceChildren();
    if (folders.length === 0) {
      const empty = document.createElement("p");
      empty.className = "wizard-folder-empty";
      empty.textContent = t("wizard.noSubfolders");
      list.append(empty);
      return;
    }
    for (const folder of folders) {
      const control = document.createElement("button");
      tip(control, "wizardFolder");
      control.type = "button";
      control.className = "wizard-folder";
      control.textContent = folder.name;
      const nextPath = folder.path;
      control.addEventListener("click", () => {
        void browse(nextPath);
      });
      list.append(control);
    }
  }
  function paint(moveFocus) {
    const position = stepPosition(model);
    text("wizard-step-label").textContent = t("wizard.stepOf", { index: position.index, count: position.count });
    paintSegments(position.index, position.count);
    paintArt();
    text("wizard-title").textContent = t(HEADINGS[model.step]);
    const body = bodyText();
    const bodyNode = text("wizard-body");
    bodyNode.textContent = body;
    bodyNode.hidden = body.length === 0;
    const hint = text("wizard-next");
    const hintText = nextText ? nextText() : "";
    const showHint = model.step === "library" && model.context.library !== "found" && hintText.length > 0;
    hint.hidden = !showHint;
    hint.textContent = showHint ? hintText : "";
    const status = statusFor();
    const statusNode = text("wizard-status");
    statusNode.textContent = status.text;
    statusNode.hidden = status.text.length === 0;
    statusNode.className = status.kind ? `wizard-status is-${status.kind}` : "wizard-status";
    paintProgress();
    element("wizard-consent").hidden = model.step !== "consent";
    element("wizard-folders").hidden = !(folderOpen && model.step === "library");
    const back = button("wizard-back");
    back.hidden = !canGoBack(model);
    back.disabled = busy;
    const secondary = button("wizard-secondary");
    secondary.hidden = model.step !== "library";
    secondary.disabled = busy;
    const primary = button("wizard-primary");
    const action = primaryAction(model);
    primary.hidden = action === "none";
    primary.textContent = model.context.snapshot === "saving" ? t("wizard.savingCopy") : action === "none" ? "" : t(LABELS[action]);
    primary.disabled = busy || !primaryEnabled(model);
    button("wizard-no").disabled = busy;
    button("wizard-yes").disabled = busy;
    button("wizard-cancel").disabled = false;
    if (moveFocus) {
      text("wizard-announce").textContent = stepAnnouncement(model);
      text("wizard-title").focus();
    }
  }
  function bodyText() {
    switch (model.step) {
      case "welcome":
        return t("wizard.welcomeBody");
      case "library":
        if (model.context.library === "pending") return t("wizard.looking");
        return (summary ? summary() : "") || t("wizard.looking");
      case "snapshot":
        return t("wizard.snapshotBody");
      case "consent":
        return t("consent.body");
      case "done":
        return "";
      default:
        return "";
    }
  }
  function statusFor() {
    if (snapshotBlocked(model)) return { text: t("wizard.blocked"), kind: "blocked" };
    if (model.step === "snapshot" && model.context.snapshot === "saved") {
      return { text: t("wizard.copySaved"), kind: "saved" };
    }
    if (model.step === "snapshot" && model.context.snapshot === "saving") {
      return { text: t("wizard.savingLibraryCopy"), kind: "" };
    }
    if (statusNote) return { text: statusNote(), kind: "" };
    return { text: "", kind: "" };
  }
  function paintSegments(current, count) {
    const host = element("wizard-segments");
    host.replaceChildren();
    for (let index = 1; index <= count; index += 1) {
      const segment = document.createElement("span");
      segment.className = "wizard-segment";
      if (index < current) segment.dataset.state = "done";
      else if (index === current) segment.dataset.state = "current";
      else segment.dataset.state = "upcoming";
      host.append(segment);
    }
  }
  function paintArt() {
    const slots = document.querySelectorAll(".wizard-art");
    slots.forEach((slot) => {
      const current = slot.dataset.artSlot === model.step;
      const hasArt = slot.querySelector("svg, img") !== null;
      slot.hidden = !(current && hasArt);
    });
  }
  function publishStatus(setup) {
    if (setup.statusMessage.length === 0) return;
    options.onStatus?.({
      message: setup.statusMessage,
      writable: setup.statusWritable,
      open: setup.seratoRunning,
      serato_running: setup.seratoRunning,
      process: setup.seratoRunning ? "Serato DJ" : null
    });
  }
  function paintProgress() {
    const node = element("wizard-progress");
    if (!(node instanceof HTMLProgressElement)) return;
    const saving = model.step === "snapshot" && model.context.snapshot === "saving";
    const saved = model.step === "snapshot" && model.context.snapshot === "saved";
    node.hidden = !saving && !saved;
    if (saving) node.removeAttribute("value");
    if (saved) node.value = 1;
  }
  function ensurePoll() {
    stopPoll();
    if (!wizardDialog().open) return;
    pollTimer = window.setInterval(() => {
      void refreshSerato();
    }, 2e3);
  }
  async function refreshSerato() {
    if (polling) return;
    if (!wizardDialog().open) {
      stopPoll();
      return;
    }
    polling = true;
    const token = generation;
    try {
      const setup = await loadSetup();
      if (token !== generation || !setup) return;
      publishStatus(setup);
      if (model.step !== "snapshot" || model.context.snapshot === "saved") return;
      const wasBlocked = snapshotBlocked(model);
      model = reduceWizard(model, { type: "serato", running: setup.seratoRunning });
      if (snapshotBlocked(model) !== wasBlocked) paint(false);
    } finally {
      polling = false;
    }
  }
  function stopPoll() {
    if (pollTimer) window.clearInterval(pollTimer);
    pollTimer = 0;
  }
  function closeDialog() {
    stopPoll();
    const dialog = wizardDialog();
    if (dialog.open) dialog.close();
    const target = options.returnFocus;
    if (target instanceof HTMLElement && target.isConnected) target.focus();
  }
  async function loadSettings() {
    try {
      const payload = await getJSON("/api/settings", 15e3);
      return readSettings(payload) ?? fallbackSettings();
    } catch {
      return fallbackSettings();
    }
  }
  async function loadSetup() {
    try {
      const payload = await getJSON("/api/setup", 15e3);
      return readSetup(payload);
    } catch {
      return null;
    }
  }
  function fallbackSettings() {
    return {
      telemetry_consent: null,
      needs_consent_prompt: true,
      wizard_complete: false,
      telemetry_configured: false,
      app_version: ""
    };
  }
  function readSettings(value) {
    if (!isRecord(value) || typeof value.needs_consent_prompt !== "boolean") return null;
    const consent = value.telemetry_consent;
    return {
      telemetry_consent: typeof consent === "boolean" ? consent : null,
      needs_consent_prompt: value.needs_consent_prompt,
      wizard_complete: value.wizard_complete === true,
      telemetry_configured: value.telemetry_configured === true,
      app_version: typeof value.app_version === "string" ? value.app_version : ""
    };
  }
  function readSetup(value) {
    if (!isRecord(value) || typeof value.found !== "boolean" || typeof value.summary !== "string") return null;
    return {
      found: value.found,
      summary: value.summary,
      next: typeof value.next === "string" ? value.next : "",
      seratoRunning: value.serato_running === true,
      statusMessage: typeof value.status_message === "string" ? value.status_message : "",
      statusWritable: value.status_writable === true
    };
  }
  function readBrowse(value) {
    if (!isRecord(value) || typeof value.path !== "string" || typeof value.name !== "string") return null;
    if (!Array.isArray(value.folders)) return null;
    const folders = [];
    for (const entry of value.folders) {
      if (!isRecord(entry) || typeof entry.name !== "string" || typeof entry.path !== "string") continue;
      folders.push({ name: entry.name, path: entry.path });
    }
    const parent = typeof value.parent === "string" ? value.parent : null;
    return { path: value.path, parent, name: value.name, folders };
  }
  async function getJSON(url, timeoutMs) {
    const response = await fetch(url, { signal: AbortSignal.timeout(timeoutMs) });
    const payload = await response.json().catch(() => null);
    if (!response.ok) throw new Error(plainError(payload));
    return payload;
  }
  async function postJSON(url, body, timeoutMs) {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(timeoutMs)
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) throw new Error(plainError(payload));
    return payload;
  }
  function plainError(payload) {
    const raw = isRecord(payload) && typeof payload.error === "string" ? payload.error : "";
    if (!raw || raw.includes("/") || raw.includes("\\") || raw.toLowerCase().includes("sqlite")) {
      return t("wizard.genericError");
    }
    const code = isRecord(payload) && typeof payload.code === "string" ? payload.code : void 0;
    return serverMessage({ error: raw, code }, raw);
  }
  function isRecord(value) {
    return typeof value === "object" && value !== null;
  }
  function wizardDialog() {
    const node = element("wizard");
    if (!(node instanceof HTMLDialogElement)) throw new Error("Missing wizard");
    return node;
  }
  function element(id) {
    const node = document.getElementById(id);
    if (!node) throw new Error(`Missing ${id}`);
    return node;
  }
  function text(id) {
    return element(id);
  }
  function button(id) {
    const node = element(id);
    if (!(node instanceof HTMLButtonElement)) throw new Error(`Missing ${id}`);
    return node;
  }
  return __toCommonJS(wizard_view_exports);
})();
//# sourceMappingURL=wizard.js.map
