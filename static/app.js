"use strict";
(() => {
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
    "layout.resizeHint": "Drag to resize. Double-click to reset.",
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
    "player.overviewSeek": "Click or drag to seek",
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
    "rekordbox.downloadTitle": "Download rekordbox.xml",
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
    "wizard.yes": "Yes, share",
    "tooltip.allTracks": "Show every track in this space. Ctrl/Cmd+1.",
    "tooltip.beatgridLock": "Lock the beatgrid so Serato does not move it.",
    "tooltip.chooseRelated": "Choose {name} as the track to link.",
    "tooltip.collapseCrate": "Hide the crates nested under {name}.",
    "tooltip.consentAccept": "Share anonymous stats and crash reports.",
    "tooltip.consentDecline": "Don't share anonymous stats.",
    "tooltip.copyLogs": "Copy the log text.",
    "tooltip.copyVersion": "Copy the app version.",
    "tooltip.crateColor": "Set the color of the selected crate.",
    "tooltip.crateDelete": "Delete the selected crate. The tracks stay in the library.",
    "tooltip.crateNew": "Create a new crate.",
    "tooltip.crateRename": "Rename the selected crate.",
    "tooltip.crateSearch": "Find a crate by name. Esc clears the search.",
    "tooltip.cue": "Move the playhead to {label}.",
    "tooltip.editField": "Edit {label}. Nothing is saved until you save the track.",
    "tooltip.expandCrate": "Show the crates nested under {name}.",
    "tooltip.exportM3u": "Download this list as a playlist file.",
    "tooltip.exportRekordbox": "Download a playlist file Rekordbox can open. You confirm before it downloads.",
    "tooltip.fileShortcut": "{name} is a shortcut. It cannot be opened from here.",
    "tooltip.filesCancel": "Cancel. Nothing is changed. Esc.",
    "tooltip.filesConfirm": "Save this file change.",
    "tooltip.filesDelete": "Move the selected files to the Trash.",
    "tooltip.filesElsewhere": "Browse a folder that is not one of the music folders.",
    "tooltip.filesList": "Folder list. Up arrow and Down arrow move between rows. Enter opens the row.",
    "tooltip.filesMove": "Move the selected files to another folder.",
    "tooltip.filesMoveFolder": "Move this folder.",
    "tooltip.filesMoveHere": "Move the files into this folder.",
    "tooltip.filesMoveTrash": "Move the selected files to the Trash. You can restore them from there.",
    "tooltip.filesMusicFolders": "Go back to the music folders.",
    "tooltip.filesName": "Type the new file name.",
    "tooltip.filesPickCancel": "Cancel choosing a folder.",
    "tooltip.filesRefresh": "Refresh this folder from disk.",
    "tooltip.filesRename": "Rename the selected file.",
    "tooltip.filesReplace": "Replace the selected file and keep its cue points.",
    "tooltip.filesReplacement": "Type the path of the replacement file.",
    "tooltip.filesReview": "Review this change before it is saved.",
    "tooltip.filesSearch": "Search file names. Ctrl/Cmd+F or /. Esc clears the search.",
    "tooltip.filesUp": "Go up to the parent folder.",
    "tooltip.findRelated": "Find a track to link by title or artist.",
    "tooltip.hideSearchCopies": "Hide the fields that were compared.",
    "tooltip.hotLoops": "Copy loops onto a free hot-cue pad in the Rekordbox file.",
    "tooltip.importFile": "Choose a playlist file to import.",
    "tooltip.importM3u": "Add tracks from a playlist file into a new crate.",
    "tooltip.keepCopy": "Keep this copy: {name}. The others leave the library.",
    "tooltip.linkMutual": "Also link that track back to this one.",
    "tooltip.linkNote": "Add a note for this link.",
    "tooltip.language": "Choose the language for this window. Same as the system follows this computer.",
    "tooltip.linkRating": "Rate this link from 1 to 5.",
    "tooltip.logFallback": "Log text, when it could not be copied.",
    "tooltip.membership": "Add this track to {name}, or take it out.",
    "tooltip.memoryCues": "Include memory cues in the Rekordbox file.",
    "tooltip.mergeCancel": "Cancel. Nothing is merged. Esc.",
    "tooltip.mergeConfirm": "Merge the copies into the one you keep.",
    "tooltip.mergeConfirmTrash": "Merge the copies and move the other audio files to the Trash.",
    "tooltip.mergeDuplicates": "Merge the selected copies into the one you keep.",
    "tooltip.mergeTrash": "Move the other audio files to the Trash. You can restore them from there.",
    "tooltip.merging": "Merging the copies.",
    "tooltip.missingDrive": "Connect the drive that holds {name} before opening it.",
    "tooltip.next": "Play the next track in this list.",
    "tooltip.openCopy": "Open this other copy, {name}.",
    "tooltip.openCrate": "Show the tracks in the crate {name}.",
    "tooltip.openCrumb": "Open the folder {name}.",
    "tooltip.openFile": "Open the folder {name}. Enter opens the highlighted row.",
    "tooltip.openInLibrary": "Open this history row in the library.",
    "tooltip.openLogs": "Open the folder that holds the log.",
    "tooltip.openRelated": "Open the linked track {name}.",
    "tooltip.overview": "Overview of the whole track. Click or drag to seek. Left arrow goes back 5 seconds. Right arrow goes forward 5 seconds.",
    "tooltip.playRow": "Start {name}. Space plays or pauses.",
    "tooltip.prepareAdd": "Send this track to Prepare.",
    "tooltip.prepareRemove": "Take this track out of Prepare.",
    "tooltip.previous": "Play the previous track in this list.",
    "tooltip.quickOpen": "Find a track or a file by name. Ctrl/Cmd+K. Esc closes this box.",
    "tooltip.quickOpenClose": "Close find. Esc.",
    "tooltip.quickOpenHit": "Open {kind} {title}. Enter.",
    "tooltip.quickOpenHitDetail": "Open {kind} {title}. {detail}. Enter.",
    "tooltip.quickOpenRetry": "Search files again.",
    "tooltip.rekordboxCancel": "Cancel. The file is not downloaded. Esc.",
    "tooltip.rekordboxDownload": "Download the Rekordbox file.",
    "tooltip.rekordboxKey": "Choose how keys are written in the Rekordbox file.",
    "tooltip.reload": "Reload the library from Serato.",
    "tooltip.relocate": "Point this track at a different audio file.",
    "tooltip.removeRelated": "Remove the saved link to {name}. The audio file stays on disk.",
    "tooltip.removeTrack": "Remove this track from the library. The audio file stays on disk.",
    "tooltip.rerunWizard": "Run setup again.",
    "tooltip.reveal": "Show this file in {name}. The library is not changed.",
    "tooltip.reviewRestore": "Review what restoring this snapshot would change.",
    "tooltip.runSetup": "Run setup to find music folders.",
    "tooltip.saveLink": "Save this link.",
    "tooltip.saveRules": "Save these smart crate rules.",
    "tooltip.saveSuggestion": "Save a two-way link to {name}. Serato is not changed until you update the crate.",
    "tooltip.saveTrack": "Save these track details.",
    "tooltip.search": "Search tracks by title or artist. Ctrl/Cmd+F or /. Esc clears the search.",
    "tooltip.seek": "Move through the track. Left arrow goes back 5 seconds. Right arrow goes forward 5 seconds. Shift with an arrow jumps 30 seconds.",
    "tooltip.selectFile": "Select {name} for rename, move, or delete.",
    "tooltip.selectFilePath": "Select {name} at {path} for rename, move, or delete.",
    "tooltip.selectRow": "Select {name}. Enter opens this row.",
    "tooltip.session": "Show the tracks played in the session {name}.",
    "tooltip.settings": "Open settings.",
    "tooltip.settingsClose": "Close settings. Esc.",
    "tooltip.shortcuts": "Show keyboard shortcuts. ?.",
    "tooltip.shortcutsClose": "Close the shortcut list. Esc.",
    "tooltip.showSearchCopies": "Show the fields that were compared.",
    "tooltip.smartRules": "Edit the smart crate rules. Nothing is saved until you press Save rules.",
    "tooltip.snapshotCancel": "Cancel. Nothing is restored. Esc.",
    "tooltip.snapshotConfirm": "Restore this snapshot. A new snapshot is saved first.",
    "tooltip.snapshotsList": "Snapshot list. Up arrow and Down arrow move between rows. Enter reviews the snapshot.",
    "tooltip.snapshotsRefresh": "Refresh the snapshot list.",
    "tooltip.snapshotsRetry": "Try reading the snapshots again.",
    "tooltip.snapshotsTake": "Save a snapshot of the library.",
    "tooltip.snapshotsUndo": "Review undoing the last outside change.",
    "tooltip.sortAdded": "Sort crates by the date they were added.",
    "tooltip.sortArtist": "Sort tracks by artist.",
    "tooltip.sortBpm": "Sort tracks by tempo.",
    "tooltip.sortBy": "Sort by {label}.",
    "tooltip.sortCrateName": "Sort crates by name.",
    "tooltip.sortDeck": "Sort history by deck.",
    "tooltip.sortKey": "Sort tracks by key.",
    "tooltip.sortLength": "Sort tracks by length.",
    "tooltip.sortOrder": "Sort crates in the saved order.",
    "tooltip.sortPlayed": "Sort history by whether the track was played.",
    "tooltip.sortStart": "Sort history by the time it started.",
    "tooltip.sortTitle": "Sort tracks by title.",
    "tooltip.space": "Choose Library, Video, Apple Music, or Prepare.",
    "tooltip.splitter": "Drag to resize the track list. Double-click to put it back. Arrow keys resize it.",
    "tooltip.telemetry": "Turn anonymous stats and crash reports on or off.",
    "tooltip.trackColor": "Choose a color for this track.",
    "tooltip.trackList": "Track list. Up arrow and Down arrow move between rows. Enter opens the row. Space plays or pauses.",
    "tooltip.trackRating": "Choose a rating for this track.",
    "tooltip.transport": "{action}. Space plays or pauses.",
    "tooltip.transportNamed": "{action} {name}. Space plays or pauses.",
    "tooltip.updateRelated": "Create or refresh the Related crate in Serato. Serato has to be quit.",
    "tooltip.viewCrates": "Show crates. Ctrl/Cmd+2.",
    "tooltip.viewDuplicates": "Show tracks that look like copies of each other.",
    "tooltip.viewFiles": "Show files on disk. Ctrl/Cmd+3.",
    "tooltip.viewHistory": "Show history. Ctrl/Cmd+4.",
    "tooltip.viewMissing": "Show tracks whose files are missing.",
    "tooltip.viewSnapshots": "Show snapshots. Ctrl/Cmd+5.",
    "tooltip.viewStems": "Show tracks that have stems.",
    "tooltip.volume": "Change how loud playback is.",
    "tooltip.wizard.checkAgain": "Look for the Serato library again.",
    "tooltip.wizard.continue": "Continue to the next step.",
    "tooltip.wizard.getStarted": "Start setup.",
    "tooltip.wizard.looking": "Looking for the Serato library.",
    "tooltip.wizard.none": "Continue setup.",
    "tooltip.wizard.openLibrary": "Finish setup and open the library.",
    "tooltip.wizard.saving": "Saving a safety copy of the library.",
    "tooltip.wizard.takeSnapshot": "Save a safety copy of the library.",
    "tooltip.wizard.tryAgain": "Try saving the safety copy again.",
    "tooltip.wizard.useLibrary": "Use the library that was found.",
    "tooltip.wizardBack": "Go back one setup step.",
    "tooltip.wizardCancel": "Cancel setup. The library is not changed. Esc.",
    "tooltip.wizardFolder": "Open the folder {name}.",
    "tooltip.wizardFolderClose": "Close the folder list. Esc.",
    "tooltip.wizardFolderUp": "Go up to the parent folder.",
    "tooltip.wizardFolderUse": "Use this folder as the library.",
    "tooltip.wizardNo": "Don't share anonymous stats.",
    "tooltip.wizardSecondary": "Choose a folder that already has a Serato library.",
    "tooltip.wizardYes": "Share anonymous stats and crash reports.",
    "tooltip.zoomIn": "Show a shorter stretch of the waveform around the playhead.",
    "tooltip.zoomOut": "Show a longer stretch of the waveform around the playhead."
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
    "layout.resizeHint": "Arrastra para cambiar el tamaño. Doble clic para restablecerlo.",
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
    "player.overviewSeek": "Haz clic o arrastra para buscar",
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
    "rekordbox.downloadTitle": "Descargar rekordbox.xml",
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
    "wizard.yes": "Sí, compartir",
    "tooltip.allTracks": "Muestra todas las pistas de este espacio. Ctrl/Cmd+1.",
    "tooltip.beatgridLock": "Bloquea la rejilla de tiempo para que Serato no la mueva.",
    "tooltip.chooseRelated": "Elige {name} como pista para enlazar.",
    "tooltip.collapseCrate": "Oculta las cajas que están dentro de {name}.",
    "tooltip.consentAccept": "Comparte estadísticas anónimas e informes de fallos.",
    "tooltip.consentDecline": "No compartas estadísticas anónimas.",
    "tooltip.copyLogs": "Copia el texto del registro.",
    "tooltip.copyVersion": "Copia la versión de la aplicación.",
    "tooltip.crateColor": "Elige el color de la caja seleccionada.",
    "tooltip.crateDelete": "Elimina la caja seleccionada. Las pistas siguen en la biblioteca.",
    "tooltip.crateNew": "Crea una caja nueva.",
    "tooltip.crateRename": "Cambia el nombre de la caja seleccionada.",
    "tooltip.crateSearch": "Busca una caja por nombre. Esc borra la búsqueda.",
    "tooltip.cue": "Lleva el cursor de reproducción a {label}.",
    "tooltip.editField": "Edita {label}. No se guarda nada hasta que guardes la pista.",
    "tooltip.expandCrate": "Muestra las cajas que están dentro de {name}.",
    "tooltip.exportM3u": "Descarga esta lista como un archivo de lista de reproducción.",
    "tooltip.exportRekordbox": "Descarga un archivo de lista que Rekordbox puede abrir. Confirmas antes de la descarga.",
    "tooltip.fileShortcut": "{name} es un acceso directo. No se puede abrir desde aquí.",
    "tooltip.filesCancel": "Cancela. No se cambia nada. Esc.",
    "tooltip.filesConfirm": "Guarda este cambio de archivo.",
    "tooltip.filesDelete": "Mueve los archivos seleccionados a la papelera.",
    "tooltip.filesElsewhere": "Examina una carpeta que no es una de las carpetas de música.",
    "tooltip.filesList": "Lista de carpetas. Arriba y Abajo cambian de fila. Intro abre la fila.",
    "tooltip.filesMove": "Mueve los archivos seleccionados a otra carpeta.",
    "tooltip.filesMoveFolder": "Mueve esta carpeta.",
    "tooltip.filesMoveHere": "Mueve los archivos a esta carpeta.",
    "tooltip.filesMoveTrash": "Mueve los archivos seleccionados a la papelera. Puedes restaurarlos desde allí.",
    "tooltip.filesMusicFolders": "Vuelve a las carpetas de música.",
    "tooltip.filesName": "Escribe el nombre nuevo del archivo.",
    "tooltip.filesPickCancel": "Cancela la elección de carpeta.",
    "tooltip.filesRefresh": "Actualiza esta carpeta desde el disco.",
    "tooltip.filesRename": "Cambia el nombre del archivo seleccionado.",
    "tooltip.filesReplace": "Sustituye el archivo seleccionado y conserva sus puntos de cue.",
    "tooltip.filesReplacement": "Escribe la ruta del archivo de sustitución.",
    "tooltip.filesReview": "Revisa este cambio antes de guardarlo.",
    "tooltip.filesSearch": "Busca nombres de archivo. Ctrl/Cmd+F o /. Esc borra la búsqueda.",
    "tooltip.filesUp": "Sube a la carpeta superior.",
    "tooltip.findRelated": "Busca una pista para enlazar por título o artista.",
    "tooltip.hideSearchCopies": "Oculta los campos que se compararon.",
    "tooltip.hotLoops": "Copia los bucles a un pad de cue libre en el archivo de Rekordbox.",
    "tooltip.importFile": "Elige un archivo de lista de reproducción para importar.",
    "tooltip.importM3u": "Añade pistas de un archivo de lista a una caja nueva.",
    "tooltip.keepCopy": "Conserva esta copia: {name}. Las demás salen de la biblioteca.",
    "tooltip.linkMutual": "Enlaza también esa pista de vuelta a esta.",
    "tooltip.linkNote": "Añade una nota a este enlace.",
    "tooltip.language": "Elige el idioma de esta ventana. Igual que el sistema sigue el idioma de este ordenador.",
    "tooltip.linkRating": "Valora este enlace de 1 a 5.",
    "tooltip.logFallback": "Texto del registro, cuando no se pudo copiar.",
    "tooltip.membership": "Añade esta pista a {name}, o quítala.",
    "tooltip.memoryCues": "Incluye los cues de memoria en el archivo de Rekordbox.",
    "tooltip.mergeCancel": "Cancela. No se fusiona nada. Esc.",
    "tooltip.mergeConfirm": "Fusiona las copias en la que conservas.",
    "tooltip.mergeConfirmTrash": "Fusiona las copias y mueve los otros archivos de audio a la papelera.",
    "tooltip.mergeDuplicates": "Fusiona las copias seleccionadas en la que conservas.",
    "tooltip.mergeTrash": "Mueve los otros archivos de audio a la papelera. Puedes restaurarlos desde allí.",
    "tooltip.merging": "Fusionando las copias.",
    "tooltip.missingDrive": "Conecta el disco que contiene {name} antes de abrirlo.",
    "tooltip.next": "Reproduce la pista siguiente de esta lista.",
    "tooltip.openCopy": "Abre esta otra copia, {name}.",
    "tooltip.openCrate": "Muestra las pistas de la caja {name}.",
    "tooltip.openCrumb": "Abre la carpeta {name}.",
    "tooltip.openFile": "Abre la carpeta {name}. Intro abre la fila resaltada.",
    "tooltip.openInLibrary": "Abre esta fila del historial en la biblioteca.",
    "tooltip.openLogs": "Abre la carpeta que contiene el registro.",
    "tooltip.openRelated": "Abre la pista enlazada {name}.",
    "tooltip.overview": "Vista de toda la pista. Haz clic o arrastra para buscar. Izquierda retrocede 5 segundos. Derecha avanza 5 segundos.",
    "tooltip.playRow": "Empieza {name}. Espacio reproduce o pausa.",
    "tooltip.prepareAdd": "Envía esta pista a Preparar.",
    "tooltip.prepareRemove": "Quita esta pista de Preparar.",
    "tooltip.previous": "Reproduce la pista anterior de esta lista.",
    "tooltip.quickOpen": "Busca una pista o un archivo por nombre. Ctrl/Cmd+K. Esc cierra este cuadro.",
    "tooltip.quickOpenClose": "Cierra la búsqueda. Esc.",
    "tooltip.quickOpenHit": "Abre {kind} {title}. Intro.",
    "tooltip.quickOpenHitDetail": "Abre {kind} {title}. {detail}. Intro.",
    "tooltip.quickOpenRetry": "Vuelve a buscar archivos.",
    "tooltip.rekordboxCancel": "Cancela. El archivo no se descarga. Esc.",
    "tooltip.rekordboxDownload": "Descarga el archivo de Rekordbox.",
    "tooltip.rekordboxKey": "Elige cómo se escriben las tonalidades en el archivo de Rekordbox.",
    "tooltip.reload": "Vuelve a cargar la biblioteca desde Serato.",
    "tooltip.relocate": "Apunta esta pista a otro archivo de audio.",
    "tooltip.removeRelated": "Quita el enlace guardado a {name}. El archivo de audio sigue en el disco.",
    "tooltip.removeTrack": "Quita esta pista de la biblioteca. El archivo de audio sigue en el disco.",
    "tooltip.rerunWizard": "Ejecuta la configuración otra vez.",
    "tooltip.reveal": "Muestra este archivo en {name}. La biblioteca no cambia.",
    "tooltip.reviewRestore": "Revisa qué cambiaría al restaurar esta instantánea.",
    "tooltip.runSetup": "Ejecuta la configuración para encontrar las carpetas de música.",
    "tooltip.saveLink": "Guarda este enlace.",
    "tooltip.saveRules": "Guarda las reglas de esta caja inteligente.",
    "tooltip.saveSuggestion": "Guarda un enlace en ambos sentidos a {name}. Serato no cambia hasta que actualices la caja.",
    "tooltip.saveTrack": "Guarda estos datos de la pista.",
    "tooltip.search": "Busca pistas por título o artista. Ctrl/Cmd+F o /. Esc borra la búsqueda.",
    "tooltip.seek": "Avanza por la pista. Izquierda retrocede 5 segundos. Derecha avanza 5 segundos. Mayús con una flecha salta 30 segundos.",
    "tooltip.selectFile": "Selecciona {name} para renombrar, mover o eliminar.",
    "tooltip.selectFilePath": "Selecciona {name} en {path} para renombrar, mover o eliminar.",
    "tooltip.selectRow": "Selecciona {name}. Intro abre esta fila.",
    "tooltip.session": "Muestra las pistas reproducidas en la sesión {name}.",
    "tooltip.settings": "Abre los ajustes.",
    "tooltip.settingsClose": "Cierra los ajustes. Esc.",
    "tooltip.shortcuts": "Muestra los atajos de teclado. ?.",
    "tooltip.shortcutsClose": "Cierra la lista de atajos. Esc.",
    "tooltip.showSearchCopies": "Muestra los campos que se compararon.",
    "tooltip.smartRules": "Edita las reglas de la caja inteligente. No se guarda nada hasta que pulses Guardar reglas.",
    "tooltip.snapshotCancel": "Cancela. No se restaura nada. Esc.",
    "tooltip.snapshotConfirm": "Restaura esta instantánea. Antes se guarda una instantánea nueva.",
    "tooltip.snapshotsList": "Lista de instantáneas. Arriba y Abajo cambian de fila. Intro revisa la instantánea.",
    "tooltip.snapshotsRefresh": "Actualiza la lista de instantáneas.",
    "tooltip.snapshotsRetry": "Intenta leer las instantáneas otra vez.",
    "tooltip.snapshotsTake": "Guarda una instantánea de la biblioteca.",
    "tooltip.snapshotsUndo": "Revisa cómo deshacer el último cambio externo.",
    "tooltip.sortAdded": "Ordena las cajas por la fecha en que se añadieron.",
    "tooltip.sortArtist": "Ordena las pistas por artista.",
    "tooltip.sortBpm": "Ordena las pistas por tempo.",
    "tooltip.sortBy": "Ordena por {label}.",
    "tooltip.sortCrateName": "Ordena las cajas por nombre.",
    "tooltip.sortDeck": "Ordena el historial por plato.",
    "tooltip.sortKey": "Ordena las pistas por tonalidad.",
    "tooltip.sortLength": "Ordena las pistas por duración.",
    "tooltip.sortOrder": "Ordena las cajas en el orden guardado.",
    "tooltip.sortPlayed": "Ordena el historial según si la pista se reprodujo.",
    "tooltip.sortStart": "Ordena el historial por la hora de inicio.",
    "tooltip.sortTitle": "Ordena las pistas por título.",
    "tooltip.space": "Elige Biblioteca, Vídeo, Apple Music o Preparar.",
    "tooltip.splitter": "Arrastra para cambiar el ancho de la lista. Doble clic lo devuelve. Las flechas lo redimensionan.",
    "tooltip.telemetry": "Activa o desactiva las estadísticas anónimas y los informes de fallos.",
    "tooltip.trackColor": "Elige un color para esta pista.",
    "tooltip.trackList": "Lista de pistas. Arriba y Abajo cambian de fila. Intro abre la fila. Espacio reproduce o pausa.",
    "tooltip.trackRating": "Elige una valoración para esta pista.",
    "tooltip.transport": "{action}. Espacio reproduce o pausa.",
    "tooltip.transportNamed": "{action} {name}. Espacio reproduce o pausa.",
    "tooltip.updateRelated": "Crea o actualiza la caja Relacionadas en Serato. Serato tiene que estar cerrado.",
    "tooltip.viewCrates": "Muestra las cajas. Ctrl/Cmd+2.",
    "tooltip.viewDuplicates": "Muestra pistas que parecen copias unas de otras.",
    "tooltip.viewFiles": "Muestra los archivos del disco. Ctrl/Cmd+3.",
    "tooltip.viewHistory": "Muestra el historial. Ctrl/Cmd+4.",
    "tooltip.viewMissing": "Muestra las pistas cuyo archivo no se encuentra.",
    "tooltip.viewSnapshots": "Muestra las instantáneas. Ctrl/Cmd+5.",
    "tooltip.viewStems": "Muestra las pistas que tienen stems.",
    "tooltip.volume": "Cambia el volumen de la reproducción.",
    "tooltip.wizard.checkAgain": "Vuelve a buscar la biblioteca de Serato.",
    "tooltip.wizard.continue": "Sigue al paso siguiente.",
    "tooltip.wizard.getStarted": "Empieza la configuración.",
    "tooltip.wizard.looking": "Buscando la biblioteca de Serato.",
    "tooltip.wizard.none": "Continúa la configuración.",
    "tooltip.wizard.openLibrary": "Termina la configuración y abre la biblioteca.",
    "tooltip.wizard.saving": "Guardando una copia de seguridad de la biblioteca.",
    "tooltip.wizard.takeSnapshot": "Guarda una copia de seguridad de la biblioteca.",
    "tooltip.wizard.tryAgain": "Intenta guardar la copia de seguridad otra vez.",
    "tooltip.wizard.useLibrary": "Usa la biblioteca que se encontró.",
    "tooltip.wizardBack": "Vuelve un paso en la configuración.",
    "tooltip.wizardCancel": "Cancela la configuración. La biblioteca no cambia. Esc.",
    "tooltip.wizardFolder": "Abre la carpeta {name}.",
    "tooltip.wizardFolderClose": "Cierra la lista de carpetas. Esc.",
    "tooltip.wizardFolderUp": "Sube a la carpeta superior.",
    "tooltip.wizardFolderUse": "Usa esta carpeta como biblioteca.",
    "tooltip.wizardNo": "No compartas estadísticas anónimas.",
    "tooltip.wizardSecondary": "Elige una carpeta que ya tenga una biblioteca de Serato.",
    "tooltip.wizardYes": "Comparte estadísticas anónimas e informes de fallos.",
    "tooltip.zoomIn": "Muestra un tramo más corto de la forma de onda alrededor del cursor.",
    "tooltip.zoomOut": "Muestra un tramo más largo de la forma de onda alrededor del cursor."
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
  function matchLanguage(tags) {
    for (const tag of tags) {
      const base = tag.toLowerCase().split(/[-_]/)[0];
      if (isLanguage(base)) return base;
    }
    return "en";
  }
  function resolveLocale(saved, tags) {
    return isLanguage(saved) ? saved : matchLanguage(tags);
  }
  function browserTags() {
    if (typeof navigator === "undefined") return [];
    if (Array.isArray(navigator.languages) && navigator.languages.length) return [...navigator.languages];
    return navigator.language ? [navigator.language] : [];
  }
  function getLocale() {
    const lang = typeof document === "undefined" ? "" : document.documentElement.lang;
    if (lang === PSEUDO) return PSEUDO;
    return isLanguage(lang) ? lang : "en";
  }
  function setLocale(locale) {
    const root = document.documentElement;
    if (root.lang === locale) return false;
    root.lang = locale;
    document.dispatchEvent(new CustomEvent(LOCALE_EVENT, { detail: locale }));
    return true;
  }
  function initialLocale() {
    try {
      const wanted = new URLSearchParams(location.search).get("locale");
      if (wanted === PSEUDO) return PSEUDO;
      if (isLanguage(wanted)) return wanted;
    } catch {
    }
    return matchLanguage(browserTags());
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
  function pseudo(text) {
    const parts = text.split(/(\{[a-zA-Z0-9_]+\})/);
    const body = parts.map((part) => part.startsWith("{") ? part : part.replace(/[a-zA-Z]/g, (ch) => ACCENTS[ch] ?? ch)).join("");
    const letters = text.replace(/\{[a-zA-Z0-9_]+\}/g, "").length;
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
  function fill(text, params, locale) {
    if (!params) return text;
    const tag = locale === PSEUDO ? "en" : locale;
    return text.replace(/\{([a-zA-Z0-9_]+)\}/g, (whole, name) => {
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
  function messageParams(value) {
    if (!value || typeof value !== "object") return void 0;
    const params = {};
    for (const [name, item] of Object.entries(value)) {
      if (typeof item === "string" || typeof item === "number" && Number.isFinite(item)) params[name] = item;
    }
    return Object.keys(params).length ? params : void 0;
  }
  function codedText(text, code, params) {
    if (typeof code === "string") {
      const key = `error.${code}`;
      if (hasKey(key)) return t(key, params ?? void 0);
    }
    return text;
  }
  function serverMessage(body, fallback) {
    if (typeof body?.code === "string") return codedText(body.error || fallback, body.code, body.params);
    return body?.error || fallback;
  }
  function applyStatic(root) {
    let count = 0;
    for (const node of root.querySelectorAll("[data-i18n]")) {
      const key = node.dataset.i18n ?? "";
      if (!hasKey(key)) continue;
      node.textContent = t(key);
      count += 1;
    }
    for (const node of root.querySelectorAll("[data-i18n-attr]")) {
      for (const pair of (node.dataset.i18nAttr ?? "").split(";")) {
        const [attr, key] = pair.split(":").map((part) => part.trim());
        if (!attr || !key || !hasKey(key)) continue;
        node.setAttribute(attr, t(key));
      }
      count += 1;
    }
    return count;
  }
  function formatNumber(value, options) {
    const locale = getLocale();
    return new Intl.NumberFormat(locale === PSEUDO ? "en" : locale, options).format(value);
  }
  function formatDate(date, options) {
    const locale = getLocale();
    return new Intl.DateTimeFormat(locale === PSEUDO ? "en" : locale, options).format(date);
  }
  function formatList(items) {
    const locale = getLocale();
    return new Intl.ListFormat(locale === PSEUDO ? "en" : locale, { style: "long", type: "conjunction" }).format(items);
  }

  // src/api.ts
  async function readJSON(response) {
    return await response.json();
  }
  async function readJSONOr(response, fallback) {
    return await response.json().catch(() => fallback);
  }
  function failureOf(error2) {
    if (error2 instanceof Error) return error2;
    return new Error(typeof error2 === "string" ? error2 : t("error.requestFailed"));
  }
  var ROOT_KINDS = ["music_library", "serato_drive", "user_folder"];
  function isLibraryRoot(value) {
    if (!value || typeof value !== "object") return false;
    const record = value;
    return typeof record.id === "string" && typeof record.path === "string" && typeof record.label === "string" && typeof record.detail === "string" && ROOT_KINDS.includes(record.kind) && typeof record.serato === "boolean" && typeof record.removable === "boolean" && typeof record.missing === "boolean";
  }
  async function fetchLibraryRoots(refresh = false) {
    const response = await fetch(refresh ? "/api/library-roots?refresh=1" : "/api/library-roots");
    const payload = await readJSONOr(response, {
      roots: [],
      computed_at: ""
    });
    if (!response.ok) {
      const error2 = new Error(serverMessage(payload, t("files.rootsUnreadable")));
      error2.status = response.status;
      error2.payload = payload;
      throw error2;
    }
    return {
      roots: Array.isArray(payload.roots) ? payload.roots.filter(isLibraryRoot) : [],
      computed_at: typeof payload.computed_at === "string" ? payload.computed_at : ""
    };
  }
  function isVersionSource(value) {
    return value === "release" || value === "git" || value === "dev";
  }
  function isVersionPayload(value) {
    if (!value || typeof value !== "object") return false;
    const record = value;
    return typeof record.version === "string" && record.version.trim() !== "" && (record.commit === null || typeof record.commit === "string") && isVersionSource(record.source);
  }
  async function getVersion() {
    const response = await fetch("/api/version");
    const payload = await readJSONOr(response, null);
    if (!response.ok || !isVersionPayload(payload)) {
      throw new Error(t("version.unavailable"));
    }
    return {
      version: payload.version.trim(),
      commit: payload.commit,
      source: payload.source
    };
  }
  async function postJSON(url, body) {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
    const payload = await readJSONOr(response, {});
    if (!response.ok) {
      const error2 = new Error(serverMessage(payload, t("error.requestStatus", { status: String(response.status) })));
      error2.status = response.status;
      error2.payload = payload;
      throw error2;
    }
    return payload;
  }

  // src/bridge.ts
  var bridge = {
    selectTrack(_id) {
    },
    selectEntry(_id) {
    },
    openMergeDialog() {
      return Promise.resolve();
    },
    openSetup() {
    }
  };

  // src/dom.ts
  function el(id) {
    const node = document.getElementById(id);
    if (node == null) throw new Error(`Missing #${id}`);
    return node;
  }

  // src/splitter.ts
  function clampWidth(width, available, minFirst, minSecond) {
    const max = Math.max(minFirst, available - minSecond);
    return Math.round(Math.min(Math.max(width, minFirst), max));
  }
  function mountSplitter(options) {
    const { handle, container, first, property, minFirst, minSecond, onCommit } = options;
    const step = options.step ?? 16;
    let current2 = null;
    const available = () => container.clientWidth - handle.offsetWidth;
    const fitted = (width) => clampWidth(width, available(), minFirst, minSecond);
    const shown = () => current2 == null ? first.getBoundingClientRect().width : fitted(current2);
    function paint3() {
      if (current2 == null) container.style.removeProperty(property);
      else container.style.setProperty(property, `${fitted(current2)}px`);
      const room = available();
      handle.setAttribute("aria-valuemin", String(minFirst));
      handle.setAttribute("aria-valuemax", String(Math.max(minFirst, Math.round(room - minSecond))));
      handle.setAttribute("aria-valuenow", String(Math.round(shown())));
    }
    function move(width) {
      current2 = fitted(width);
      paint3();
    }
    handle.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      event.preventDefault();
      const startX = event.clientX;
      const startWidth = shown();
      let moved = false;
      handle.setPointerCapture?.(event.pointerId);
      handle.dataset.dragging = "true";
      document.body.classList.add("is-resizing");
      const onMove = (next2) => {
        moved = true;
        move(startWidth + next2.clientX - startX);
      };
      const onEnd = () => {
        handle.removeEventListener("pointermove", onMove);
        handle.removeEventListener("pointerup", onEnd);
        handle.removeEventListener("pointercancel", onEnd);
        delete handle.dataset.dragging;
        document.body.classList.remove("is-resizing");
        if (moved) onCommit(current2);
      };
      handle.addEventListener("pointermove", onMove);
      handle.addEventListener("pointerup", onEnd);
      handle.addEventListener("pointercancel", onEnd);
    });
    handle.addEventListener("keydown", (event) => {
      const jump = event.shiftKey ? step * 4 : step;
      let next2;
      if (event.key === "ArrowLeft") next2 = shown() - jump;
      else if (event.key === "ArrowRight") next2 = shown() + jump;
      else if (event.key === "Home") next2 = minFirst;
      else if (event.key === "End") next2 = available() - minSecond;
      else return;
      event.preventDefault();
      const before = current2;
      move(next2);
      if (current2 !== before) onCommit(current2);
    });
    handle.addEventListener("dblclick", () => {
      current2 = null;
      paint3();
      onCommit(null);
    });
    paint3();
    return {
      set(width) {
        current2 = width == null ? null : Math.round(width);
        paint3();
      },
      width: () => current2,
      refit: paint3
    };
  }

  // src/state.ts
  var ROW = 36;
  var FILE_ROW = 44;
  var ROOT_ROW = 64;
  var COLORS = [
    [16777215, "color.none"],
    [13369344, "color.red"],
    [16746496, "color.orange"],
    [16763904, "color.yellow"],
    [3385941, "color.green"],
    [2250188, "color.blue"],
    [8926156, "color.purple"],
    [14826378, "color.pink"]
  ];
  var COLOR_NAMES = {
    none: 16777215,
    red: 13369344,
    orange: 16746496,
    yellow: 16763904,
    green: 3385941,
    blue: 2250188,
    purple: 8926156,
    pink: 14826378
  };
  var state = {
    tracks: [],
    byId: /* @__PURE__ */ new Map(),
    crates: [],
    crateTracks: /* @__PURE__ */ new Map(),
    rootId: null,
    activeCrate: "all",
    query: "",
    crateQuery: "",
    crateSort: "order",
    sort: "name",
    sortDir: 1,
    selectedId: null,
    request: 0,
    expanded: /* @__PURE__ */ new Set(),
    space: "Serato Library",
    mode: "crates",
    writable: false,
    serato: null,
    historySessions: [],
    historyId: null,
    entries: [],
    duplicateIds: null,
    duplicateGroups: [],
    duplicateSpace: "",
    telemetryConsent: null,
    telemetryConfigured: false,
    wizardComplete: false,
    filesPath: "",
    filesParent: null,
    filesEntries: [],
    filesSelected: /* @__PURE__ */ new Set(),
    filesPick: null,
    filesPickPaths: [],
    filesPickSource: "",
    filesLoading: false,
    filesError: "",
    filesMessage: "",
    filesTruncated: false,
    filesAtRoots: false,
    filesRoots: [],
    filesRoot: null,
    filesBreadcrumb: [],
    filesElsewhere: false,
    filesActive: 0,
    filesQuery: "",
    filesSearching: false,
    snapshots: [],
    snapshotLoading: false,
    snapshotError: "",
    snapshotMessage: "",
    snapshotUndo: null,
    writeBlock: "",
    writeBlockCode: "",
    writeBlockParams: null,
    seratoRunning: false,
    snapshotPlanId: "",
    view: []
  };

  // src/format.ts
  function lengthLabel(ms) {
    if (ms == null || ms === "") return "";
    const total = Math.floor(Number(ms) / 1e3);
    const minutes = Math.floor(total / 60);
    const seconds = total % 60;
    return `${minutes}:${String(seconds).padStart(2, "0")}`;
  }
  function clockLabel(stamp) {
    if (stamp == null || stamp === "") return "";
    const date = new Date(Number(stamp) * 1e3);
    if (Number.isNaN(date.getTime())) return "";
    return formatDate(date, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  }
  function durationLabel(ms) {
    const total = Math.round(Number(ms) / 1e3);
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor(total % 3600 / 60);
    if (hours) return t("format.hoursMinutes", { hours, minutes });
    return t("format.minutes", { minutes });
  }
  function sizeLabel(bytes) {
    const size = Number(bytes) || 0;
    if (size < 1024) return t("format.bytes", { count: size });
    const units = ["KB", "MB", "GB"];
    let amount = size / 1024;
    let unit = 0;
    while (amount >= 1024 && unit < units.length - 1) {
      amount /= 1024;
      unit += 1;
    }
    return `${formatNumber(amount, { minimumFractionDigits: 1, maximumFractionDigits: 1 })} ${units[unit]}`;
  }
  function colorHex(color) {
    if (color == null || Number(color) === 16777215) return "";
    return `#${Number(color).toString(16).padStart(6, "0")}`;
  }
  function compare(a, b) {
    const key = state.sort;
    const dir = state.sortDir;
    let av = a[key];
    let bv = b[key];
    if (key === "bpm" || key === "length_ms" || key === "start") {
      const an = av == null || av === "" ? null : Number(av);
      const bn = bv == null || bv === "" ? null : Number(bv);
      if (an == null && bn == null) return a.id - b.id;
      if (an == null) return 1;
      if (bn == null) return -1;
      if (an !== bn) return (an - bn) * dir;
      return a.id - b.id;
    }
    av = String(av || "").toLocaleLowerCase();
    bv = String(bv || "").toLocaleLowerCase();
    if (!av && bv) return 1;
    if (av && !bv) return -1;
    const locale = getLocale();
    const order = av.localeCompare(bv, locale === PSEUDO ? "en" : locale, { numeric: true, sensitivity: "base" });
    if (order !== 0) return order * dir;
    return a.id - b.id;
  }

  // src/tooltip-strings.ts
  function spec(key, params) {
    return params ? { key, params } : { key };
  }
  var tips = {
    space: spec("tooltip.space"),
    crateSearch: spec("tooltip.crateSearch"),
    mergeDuplicates: spec("tooltip.mergeDuplicates"),
    crateNew: spec("tooltip.crateNew"),
    crateRename: spec("tooltip.crateRename"),
    crateColor: spec("tooltip.crateColor"),
    crateDelete: spec("tooltip.crateDelete"),
    shortcuts: spec("tooltip.shortcuts"),
    settings: spec("tooltip.settings"),
    search: spec("tooltip.search"),
    exportM3u: spec("tooltip.exportM3u"),
    exportRekordbox: spec("tooltip.exportRekordbox"),
    memoryCues: spec("tooltip.memoryCues"),
    hotLoops: spec("tooltip.hotLoops"),
    rekordboxKey: spec("tooltip.rekordboxKey"),
    importM3u: spec("tooltip.importM3u"),
    importFile: spec("tooltip.importFile"),
    reload: spec("tooltip.reload"),
    filesUp: spec("tooltip.filesUp"),
    filesSearch: spec("tooltip.filesSearch"),
    filesRefresh: spec("tooltip.filesRefresh"),
    filesElsewhere: spec("tooltip.filesElsewhere"),
    filesMusicFolders: spec("tooltip.filesMusicFolders"),
    filesRename: spec("tooltip.filesRename"),
    filesMove: spec("tooltip.filesMove"),
    filesMoveFolder: spec("tooltip.filesMoveFolder"),
    filesReplace: spec("tooltip.filesReplace"),
    filesDelete: spec("tooltip.filesDelete"),
    filesMoveHere: spec("tooltip.filesMoveHere"),
    filesPickCancel: spec("tooltip.filesPickCancel"),
    snapshotsRefresh: spec("tooltip.snapshotsRefresh"),
    snapshotsTake: spec("tooltip.snapshotsTake"),
    snapshotsUndo: spec("tooltip.snapshotsUndo"),
    consentDecline: spec("tooltip.consentDecline"),
    consentAccept: spec("tooltip.consentAccept"),
    telemetry: spec("tooltip.telemetry"),
    copyVersion: spec("tooltip.copyVersion"),
    rerunWizard: spec("tooltip.rerunWizard"),
    openLogs: spec("tooltip.openLogs"),
    copyLogs: spec("tooltip.copyLogs"),
    settingsClose: spec("tooltip.settingsClose"),
    logFallback: spec("tooltip.logFallback"),
    mergeTrash: spec("tooltip.mergeTrash"),
    mergeCancel: spec("tooltip.mergeCancel"),
    mergeConfirm: spec("tooltip.mergeConfirm"),
    mergeConfirmTrash: spec("tooltip.mergeConfirmTrash"),
    merging: spec("tooltip.merging"),
    rekordboxCancel: spec("tooltip.rekordboxCancel"),
    rekordboxDownload: spec("tooltip.rekordboxDownload"),
    filesName: spec("tooltip.filesName"),
    filesReplacement: spec("tooltip.filesReplacement"),
    filesCancel: spec("tooltip.filesCancel"),
    filesReview: spec("tooltip.filesReview"),
    filesConfirm: spec("tooltip.filesConfirm"),
    filesMoveTrash: spec("tooltip.filesMoveTrash"),
    shortcutsClose: spec("tooltip.shortcutsClose"),
    quickOpen: spec("tooltip.quickOpen"),
    quickOpenRetry: spec("tooltip.quickOpenRetry"),
    quickOpenClose: spec("tooltip.quickOpenClose"),
    snapshotCancel: spec("tooltip.snapshotCancel"),
    snapshotConfirm: spec("tooltip.snapshotConfirm"),
    wizardFolderUp: spec("tooltip.wizardFolderUp"),
    wizardFolderUse: spec("tooltip.wizardFolderUse"),
    wizardFolderClose: spec("tooltip.wizardFolderClose"),
    wizardNo: spec("tooltip.wizardNo"),
    wizardYes: spec("tooltip.wizardYes"),
    wizardBack: spec("tooltip.wizardBack"),
    wizardCancel: spec("tooltip.wizardCancel"),
    wizardSecondary: spec("tooltip.wizardSecondary"),
    trackList: spec("tooltip.trackList"),
    filesList: spec("tooltip.filesList"),
    snapshotsList: spec("tooltip.snapshotsList"),
    splitter: spec("tooltip.splitter"),
    previous: spec("tooltip.previous"),
    next: spec("tooltip.next"),
    seek: spec("tooltip.seek"),
    volume: spec("tooltip.volume"),
    zoomIn: spec("tooltip.zoomIn"),
    zoomOut: spec("tooltip.zoomOut"),
    overview: spec("tooltip.overview"),
    smartRules: spec("tooltip.smartRules"),
    saveRules: spec("tooltip.saveRules"),
    saveTrack: spec("tooltip.saveTrack"),
    trackColor: spec("tooltip.trackColor"),
    trackRating: spec("tooltip.trackRating"),
    beatgridLock: spec("tooltip.beatgridLock"),
    relocate: spec("tooltip.relocate"),
    removeTrack: spec("tooltip.removeTrack"),
    prepareAdd: spec("tooltip.prepareAdd"),
    prepareRemove: spec("tooltip.prepareRemove"),
    updateRelated: spec("tooltip.updateRelated"),
    findRelated: spec("tooltip.findRelated"),
    linkNote: spec("tooltip.linkNote"),
    linkRating: spec("tooltip.linkRating"),
    language: spec("tooltip.language"),
    linkMutual: spec("tooltip.linkMutual"),
    saveLink: spec("tooltip.saveLink"),
    showSearchCopies: spec("tooltip.showSearchCopies"),
    hideSearchCopies: spec("tooltip.hideSearchCopies"),
    openInLibrary: spec("tooltip.openInLibrary"),
    runSetup: spec("tooltip.runSetup"),
    snapshotsRetry: spec("tooltip.snapshotsRetry"),
    reviewRestore: spec("tooltip.reviewRestore"),
    allTracks: spec("tooltip.allTracks"),
    viewCrates: spec("tooltip.viewCrates"),
    viewHistory: spec("tooltip.viewHistory"),
    viewMissing: spec("tooltip.viewMissing"),
    viewDuplicates: spec("tooltip.viewDuplicates"),
    viewStems: spec("tooltip.viewStems"),
    viewFiles: spec("tooltip.viewFiles"),
    viewSnapshots: spec("tooltip.viewSnapshots"),
    sortTitle: spec("tooltip.sortTitle"),
    sortArtist: spec("tooltip.sortArtist"),
    sortBpm: spec("tooltip.sortBpm"),
    sortKey: spec("tooltip.sortKey"),
    sortLength: spec("tooltip.sortLength"),
    sortDeck: spec("tooltip.sortDeck"),
    sortPlayed: spec("tooltip.sortPlayed"),
    sortStart: spec("tooltip.sortStart"),
    sortOrder: spec("tooltip.sortOrder"),
    sortCrateName: spec("tooltip.sortCrateName"),
    sortAdded: spec("tooltip.sortAdded")
  };
  function playTip(action, name) {
    if (name) return spec("tooltip.transportNamed", { action, name });
    return spec("tooltip.transport", { action });
  }
  function sortTip(key, label) {
    const known = {
      name: "tooltip.sortTitle",
      artist: "tooltip.sortArtist",
      bpm: "tooltip.sortBpm",
      key: "tooltip.sortKey",
      length_ms: "tooltip.sortLength",
      deck: "tooltip.sortDeck",
      played: "tooltip.sortPlayed",
      start: "tooltip.sortStart"
    };
    const message = known[key];
    if (message) return spec(message);
    return spec("tooltip.sortBy", { label });
  }
  function viewTip(view) {
    const known = {
      crates: tips.viewCrates,
      history: tips.viewHistory,
      missing: tips.viewMissing,
      duplicates: tips.viewDuplicates,
      stems: tips.viewStems,
      files: tips.viewFiles,
      snapshots: tips.viewSnapshots
    };
    return known[view];
  }
  function crateSortTip(key) {
    if (key === "order") return tips.sortOrder;
    if (key === "name") return tips.sortCrateName;
    if (key === "added") return tips.sortAdded;
    return void 0;
  }
  function staticTip(id) {
    const known = {
      space: tips.space,
      "crate-search": tips.crateSearch,
      "merge-duplicates": tips.mergeDuplicates,
      "crate-new": tips.crateNew,
      "crate-rename": tips.crateRename,
      "crate-color": tips.crateColor,
      "crate-delete": tips.crateDelete,
      "open-shortcuts": tips.shortcuts,
      "open-settings": tips.settings,
      search: tips.search,
      "export-m3u": tips.exportM3u,
      "export-rekordbox": tips.exportRekordbox,
      "rekordbox-memory": tips.memoryCues,
      "rekordbox-hot-loops": tips.hotLoops,
      "rekordbox-key": tips.rekordboxKey,
      "import-m3u": tips.importM3u,
      "import-file": tips.importFile,
      reload: tips.reload,
      "files-up": tips.filesUp,
      "files-search": tips.filesSearch,
      "files-refresh": tips.filesRefresh,
      "files-elsewhere": tips.filesElsewhere,
      "files-rename": tips.filesRename,
      "files-move": tips.filesMove,
      "files-move-folder": tips.filesMoveFolder,
      "files-replace": tips.filesReplace,
      "files-delete": tips.filesDelete,
      "files-move-here": tips.filesMoveHere,
      "files-pick-cancel": tips.filesPickCancel,
      "snapshots-refresh": tips.snapshotsRefresh,
      "snapshots-take": tips.snapshotsTake,
      "snapshots-undo-button": tips.snapshotsUndo,
      "consent-decline": tips.consentDecline,
      "consent-accept": tips.consentAccept,
      "telemetry-toggle": tips.telemetry,
      "copy-version": tips.copyVersion,
      "rerun-wizard": tips.rerunWizard,
      "open-logs": tips.openLogs,
      "copy-logs": tips.copyLogs,
      "settings-close": tips.settingsClose,
      "log-fallback": tips.logFallback,
      "language-select": tips.language,
      "merge-trash": tips.mergeTrash,
      "merge-cancel": tips.mergeCancel,
      "merge-confirm": tips.mergeConfirm,
      "rekordbox-cancel": tips.rekordboxCancel,
      "rekordbox-download": tips.rekordboxDownload,
      "files-name": tips.filesName,
      "files-replacement": tips.filesReplacement,
      "files-cancel": tips.filesCancel,
      "files-review": tips.filesReview,
      "files-confirm": tips.filesConfirm,
      "shortcuts-close": tips.shortcutsClose,
      "quick-open-query": tips.quickOpen,
      "quick-open-retry": tips.quickOpenRetry,
      "quick-open-close": tips.quickOpenClose,
      "snapshot-cancel": tips.snapshotCancel,
      "snapshot-confirm": tips.snapshotConfirm,
      "wizard-folder-up": tips.wizardFolderUp,
      "wizard-folder-use": tips.wizardFolderUse,
      "wizard-folder-close": tips.wizardFolderClose,
      "wizard-no": tips.wizardNo,
      "wizard-yes": tips.wizardYes,
      "wizard-back": tips.wizardBack,
      "wizard-cancel": tips.wizardCancel,
      "wizard-secondary": tips.wizardSecondary,
      "wizard-primary": spec("tooltip.wizard.getStarted"),
      list: tips.trackList,
      "files-list": tips.filesList,
      "snapshots-list": tips.snapshotsList,
      "track-splitter": tips.splitter
    };
    return known[id];
  }
  function expandCrate(name) {
    return spec("tooltip.expandCrate", { name });
  }
  function collapseCrate(name) {
    return spec("tooltip.collapseCrate", { name });
  }
  function openCrate(name) {
    return spec("tooltip.openCrate", { name });
  }
  function sessionTip(name) {
    return spec("tooltip.session", { name });
  }
  function playRow(name) {
    return spec("tooltip.playRow", { name });
  }
  function selectRow(name) {
    return spec("tooltip.selectRow", { name });
  }
  function cueTip(label) {
    return spec("tooltip.cue", { label });
  }
  function editField(label) {
    return spec("tooltip.editField", { label });
  }
  function revealTip(manager) {
    return spec("tooltip.reveal", { name: manager });
  }
  function openCopy(name) {
    return spec("tooltip.openCopy", { name });
  }
  function openRelated(name) {
    return spec("tooltip.openRelated", { name });
  }
  function removeRelatedTip(name) {
    return spec("tooltip.removeRelated", { name });
  }
  function chooseRelated(name) {
    return spec("tooltip.chooseRelated", { name });
  }
  function saveSuggestion(name) {
    return spec("tooltip.saveSuggestion", { name });
  }
  function membershipTip(name) {
    return spec("tooltip.membership", { name });
  }
  function openCrumb(name) {
    return spec("tooltip.openCrumb", { name });
  }
  function openFile(name) {
    return spec("tooltip.openFile", { name });
  }
  function missingDrive(name) {
    return spec("tooltip.missingDrive", { name });
  }
  function fileShortcut(name) {
    return spec("tooltip.fileShortcut", { name });
  }
  function selectFile(name, path = "") {
    if (path && path !== name) return spec("tooltip.selectFilePath", { name, path });
    return spec("tooltip.selectFile", { name });
  }
  function keepCopy(name) {
    return spec("tooltip.keepCopy", { name });
  }
  function quickOpenHit(kind, title2, detail) {
    if (detail) return spec("tooltip.quickOpenHitDetail", { kind, title: title2, detail });
    return spec("tooltip.quickOpenHit", { kind, title: title2 });
  }

  // src/tooltip.ts
  var TOOLTIP_ID = "app-tooltip";
  var TOOLTIP_HOVER_MS = 400;
  var INTERACTIVE_SELECTOR = [
    "button",
    "input:not([type='hidden'])",
    "select",
    "textarea",
    "a[href]",
    "summary",
    "[role='slider']",
    "[role='button']",
    "[role='tab']",
    "[role='menuitem']",
    "[role='menuitemcheckbox']",
    "[role='menuitemradio']",
    "[role='switch']",
    "[role='option']",
    "[role='separator']",
    "[role='checkbox']",
    "[role='radio']",
    "[tabindex]:not([tabindex='-1'])"
  ].join(",");
  var installed = false;
  var current = null;
  var timer = 0;
  var priorDescribedBy = "";
  var tipParams = /* @__PURE__ */ new WeakMap();
  function writeTooltip(element) {
    const key = element.dataset.tooltipKey ?? "";
    if (!hasKey(key)) throw new Error(`Unknown tooltip key ${key}.`);
    const value = t(key, tipParams.get(element)).trim();
    if (!value) throw new Error("A control tooltip cannot be empty.");
    element.dataset.tooltip = value;
  }
  function syncOpenTooltip() {
    if (!current) return;
    const tip = document.getElementById(TOOLTIP_ID);
    if (!(tip instanceof HTMLElement)) return;
    tip.textContent = current.dataset.tooltip ?? "";
  }
  function setTooltip(element, spec2) {
    element.dataset.tooltipKey = spec2.key;
    if (spec2.params) tipParams.set(element, spec2.params);
    else tipParams.delete(element);
    writeTooltip(element);
    element.removeAttribute("title");
    if (current === element) syncOpenTooltip();
  }
  function buttonEl(spec2) {
    const element = document.createElement("button");
    element.type = "button";
    setTooltip(element, spec2);
    return element;
  }
  function inputEl(spec2) {
    const element = document.createElement("input");
    setTooltip(element, spec2);
    return element;
  }
  function selectEl(spec2) {
    const element = document.createElement("select");
    setTooltip(element, spec2);
    return element;
  }
  function textareaEl(spec2) {
    const element = document.createElement("textarea");
    setTooltip(element, spec2);
    return element;
  }
  function applyStaticTooltips(root = document) {
    root.querySelectorAll("[id]").forEach((node) => {
      const text = staticTip(node.id);
      if (text) setTooltip(node, text);
    });
    root.querySelectorAll("[data-view]").forEach((node) => {
      const text = viewTip(node.dataset.view ?? "");
      if (text) setTooltip(node, text);
    });
    root.querySelectorAll("[data-sort]").forEach((node) => {
      const label = node.textContent?.trim() || node.dataset.sort || "";
      setTooltip(node, sortTip(node.dataset.sort ?? "", label));
    });
    root.querySelectorAll("[data-crate-sort]").forEach((node) => {
      const text = crateSortTip(node.dataset.crateSort ?? "");
      if (text) setTooltip(node, text);
    });
  }
  function refreshTooltips(root = document) {
    root.querySelectorAll("[data-tooltip-key]").forEach((node) => writeTooltip(node));
    if (current && !current.isConnected) {
      hide();
      return;
    }
    syncOpenTooltip();
  }
  function installTooltips() {
    if (installed) return;
    installed = true;
    document.addEventListener("pointerover", onPointerOver);
    document.addEventListener("pointerout", onPointerOut);
    document.addEventListener("focusin", onFocusIn);
    document.addEventListener("focusout", onFocusOut);
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("scroll", onScroll, true);
  }
  function onPointerOver(event) {
    if (event.pointerType && event.pointerType !== "mouse") return;
    const target = tooltipTarget(event.target);
    if (!target) return;
    schedule(target, hoverDelay());
  }
  function onPointerOut(event) {
    if (event.pointerType && event.pointerType !== "mouse") return;
    const target = tooltipTarget(event.target);
    if (!target || tooltipTarget(event.relatedTarget) === target) return;
    if (current === target) hide();
  }
  function onFocusIn(event) {
    const target = tooltipTarget(event.target);
    if (!target) return;
    schedule(target, 0);
  }
  function onFocusOut(event) {
    if (tooltipTarget(event.relatedTarget)) return;
    const target = tooltipTarget(event.target);
    if (target && current === target) hide();
  }
  function onKeyDown(event) {
    if (event.key !== "Escape" || !current) return;
    hide();
  }
  function onScroll() {
    if (current) hide();
  }
  function schedule(target, delay) {
    window.clearTimeout(timer);
    timer = 0;
    if (delay <= 0) {
      show(target);
      return;
    }
    timer = window.setTimeout(() => show(target), delay);
  }
  function show(target) {
    const text = target.dataset.tooltip?.trim() ?? "";
    if (!text) return;
    if (current && current !== target) restoreDescribedBy(current);
    current = target;
    const tip = ensureTip();
    tip.textContent = text;
    openTip(tip);
    place(target, tip);
    addDescribedBy(target);
  }
  function hide() {
    window.clearTimeout(timer);
    timer = 0;
    if (current) restoreDescribedBy(current);
    current = null;
    const tip = document.getElementById(TOOLTIP_ID);
    if (tip instanceof HTMLElement) closeTip(tip);
  }
  function hoverDelay() {
    if (typeof matchMedia !== "function") return TOOLTIP_HOVER_MS;
    return matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : TOOLTIP_HOVER_MS;
  }
  function tooltipTarget(node) {
    if (!(node instanceof Element)) return null;
    const direct = node.closest("[data-tooltip]");
    if (direct?.dataset.tooltip?.trim()) return direct;
    const label = node instanceof HTMLLabelElement ? node : node.closest("label");
    if (!(label instanceof HTMLLabelElement)) return null;
    if (label.control instanceof HTMLElement && label.control.dataset.tooltip?.trim()) return label.control;
    const nested = label.querySelector("[data-tooltip]");
    if (nested?.dataset.tooltip?.trim()) return nested;
    return null;
  }
  function ensureTip() {
    const existing = document.getElementById(TOOLTIP_ID);
    if (existing instanceof HTMLElement) return existing;
    const tip = document.createElement("div");
    tip.id = TOOLTIP_ID;
    tip.className = "app-tooltip";
    tip.setAttribute("role", "tooltip");
    tip.hidden = true;
    tip.setAttribute("popover", "manual");
    document.body.append(tip);
    return tip;
  }
  function openTip(tip) {
    tip.hidden = false;
    if (typeof tip.showPopover !== "function") return;
    try {
      if (!tip.matches(":popover-open")) tip.showPopover();
    } catch {
    }
  }
  function closeTip(tip) {
    if (typeof tip.hidePopover === "function") {
      try {
        if (tip.matches(":popover-open")) tip.hidePopover();
      } catch {
      }
    }
    tip.hidden = true;
  }
  function place(target, tip) {
    const rect = target.getBoundingClientRect();
    const gap = 8;
    const margin = 8;
    tip.style.position = "fixed";
    tip.style.margin = "0";
    tip.style.left = "0px";
    tip.style.top = "0px";
    const tipRect = tip.getBoundingClientRect();
    let top = rect.bottom + gap;
    let left = rect.left;
    if (top + tipRect.height > window.innerHeight - margin) top = Math.max(margin, rect.top - gap - tipRect.height);
    if (left + tipRect.width > window.innerWidth - margin) left = window.innerWidth - margin - tipRect.width;
    tip.style.left = `${Math.round(Math.max(margin, left))}px`;
    tip.style.top = `${Math.round(Math.max(margin, top))}px`;
  }
  function addDescribedBy(target) {
    if (target.dataset.tooltipLive === "1") return;
    target.dataset.tooltipLive = "1";
    priorDescribedBy = target.getAttribute("aria-describedby") ?? "";
    const ids = priorDescribedBy.split(/\s+/).filter((id) => id.length > 0 && id !== TOOLTIP_ID);
    ids.push(TOOLTIP_ID);
    target.setAttribute("aria-describedby", ids.join(" "));
  }
  function restoreDescribedBy(target) {
    if (target.dataset.tooltipLive !== "1") return;
    delete target.dataset.tooltipLive;
    if (priorDescribedBy) target.setAttribute("aria-describedby", priorDescribedBy);
    else target.removeAttribute("aria-describedby");
    priorDescribedBy = "";
  }

  // src/restore.ts
  var reloadLibrary = async () => {
  };
  function bindLibraryReload(reload) {
    reloadLibrary = reload;
  }
  async function loadSnapshots() {
    state.snapshotLoading = true;
    state.snapshotError = "";
    renderSnapshots();
    const response = await fetch("/api/snapshots");
    const payload = await readJSON(response);
    if (!response.ok) throw new Error(serverMessage(payload, t("snapshots.unreadable")));
    state.snapshots = payload.snapshots || [];
    state.snapshotUndo = payload.pending_undo || null;
    state.writeBlock = payload.write_block || "";
    state.writeBlockCode = payload.write_block_code || "";
    state.writeBlockParams = messageParams(payload.write_block_params) ?? null;
    state.seratoRunning = Boolean(payload.serato_running);
    state.snapshotLoading = false;
    renderSnapshots();
  }
  function failSnapshots(error2) {
    state.snapshotLoading = false;
    state.snapshotError = failureOf(error2).message || t("snapshots.unreadable");
    renderSnapshots();
  }
  function renderSnapshots() {
    const status = el("snapshots-status");
    const block = el("snapshots-block");
    const undo = el("snapshots-undo");
    const list = el("snapshots-list");
    list.setAttribute("aria-busy", String(state.snapshotLoading));
    if (state.writeBlock) {
      block.hidden = false;
      block.textContent = codedText(state.writeBlock, state.writeBlockCode, state.writeBlockParams);
    } else {
      block.hidden = true;
      block.textContent = "";
    }
    if (state.snapshotUndo && state.snapshotUndo.restore_id) {
      undo.hidden = false;
      el("snapshots-undo-text").textContent = state.snapshotUndo.source === "Lexicon" ? t("snapshots.outsideChangeLexicon") : t("snapshots.outsideChange");
    } else {
      undo.hidden = true;
    }
    list.replaceChildren();
    if (state.snapshotLoading) {
      status.textContent = t("snapshots.reading");
      return;
    }
    if (state.snapshotError) {
      status.textContent = state.snapshotError;
      const retry = buttonEl(tips.snapshotsRetry);
      retry.textContent = t("common.tryAgain");
      retry.addEventListener("click", () => loadSnapshots().catch((error2) => failSnapshots(error2)));
      list.append(retry);
      return;
    }
    status.textContent = state.snapshotMessage ? t(state.snapshotMessage) : "";
    if (!state.snapshots.length) {
      const empty = document.createElement("p");
      empty.textContent = t("snapshots.empty");
      list.append(empty);
      return;
    }
    for (const item of state.snapshots) {
      const card = document.createElement("article");
      card.className = "snapshot-card";
      card.setAttribute("role", "listitem");
      const title2 = document.createElement("p");
      title2.textContent = `${item.created || t("snapshots.unknownTime")} · ${item.trigger || t("snapshots.trigger")}`;
      const detail = document.createElement("p");
      const version = item.serato_version && item.serato_version !== "unknown" ? t("snapshots.seratoVersion", { version: item.serato_version, build: String(item.serato_build ?? "") }) : t("snapshots.seratoUnknown");
      const drives = (item.unavailable_drives || []).length ? ` ${t("snapshots.unavailableDrives", { drives: formatList(item.unavailable_drives || []) })}` : "";
      detail.textContent = `${version}. ${item.reason || ""}${drives}`;
      const restore = buttonEl(tips.reviewRestore);
      restore.textContent = t("snapshots.reviewRestore");
      restore.addEventListener("click", () => openSnapshotPlan(item.id).catch((error2) => setSnapshotDialogStatus(failureOf(error2).message)));
      card.append(title2, detail, restore);
      list.append(card);
    }
  }
  async function openSnapshotPlan(snapshotId) {
    state.snapshotPlanId = snapshotId;
    const planBox = el("snapshot-plan");
    const block = el("snapshot-block");
    const confirm2 = el("snapshot-confirm");
    planBox.replaceChildren();
    block.textContent = t("snapshots.readingPlan");
    confirm2.disabled = true;
    setSnapshotDialogStatus("");
    el("snapshot-dialog").showModal();
    const plan = await postJSON("/api/snapshots", { action: "plan", id: snapshotId });
    paintSnapshotPlan(plan);
  }
  var lastPlan = null;
  function repaintSnapshotPlan() {
    if (lastPlan && el("snapshot-dialog").open) paintSnapshotPlan(lastPlan);
  }
  function paintSnapshotPlan(plan) {
    lastPlan = plan;
    const planBox = el("snapshot-plan");
    const block = el("snapshot-block");
    const confirm2 = el("snapshot-confirm");
    planBox.replaceChildren();
    const crates = plan.crates || {};
    const tracks = plan.tracks || {};
    appendPlanLine(planBox, t("plan.cratesAdded"), crates.added);
    appendPlanLine(planBox, t("plan.cratesRemoved"), crates.removed);
    appendPlanLine(planBox, t("plan.cratesChanged"), crates.changed);
    appendPlanLine(planBox, t("plan.cratesUnavailable"), crates.unavailable);
    appendPlanLine(planBox, t("plan.tracksAdded"), tracks.added);
    appendPlanLine(planBox, t("plan.tracksRemoved"), tracks.removed);
    appendPlanLine(planBox, t("plan.tracksUnavailable"), tracks.unavailable);
    appendFrameDiffs(planBox, t("plan.cueChanges"), plan.cues);
    appendFrameDiffs(planBox, t("plan.gridChanges"), plan.grids);
    const deleted = plan.deleted || {};
    appendPlanLine(planBox, t("plan.deletedCrates"), deleted.crates);
    appendPlanLine(planBox, t("plan.deletedTracks"), deleted.tracks);
    appendPlanLine(planBox, t("plan.deletedCues"), deleted.cues);
    appendPlanLine(planBox, t("plan.deletedGrids"), deleted.grids);
    if (plan.restore_blocked) {
      block.textContent = codedText(
        plan.restore_blocked,
        plan.restore_blocked_code,
        messageParams(plan.restore_blocked_params)
      );
      confirm2.disabled = true;
    } else {
      block.textContent = plan.dry_run ? t("plan.nothingChanged") : "";
      confirm2.disabled = false;
    }
  }
  function appendPlanLine(parent, label, rows2) {
    const line = document.createElement("p");
    const items = rows2 || [];
    if (!items.length) {
      line.textContent = t("plan.none", { label });
    } else {
      const names = items.slice(0, 8).map((item) => item.name || item.path || item.drive_label || t("plan.item"));
      const extra = items.length > names.length ? t("plan.andMore", { count: items.length - names.length }) : "";
      const listed = `${names.join(", ")}${extra}`;
      line.textContent = t("plan.listed", { label, count: items.length, names: listed });
    }
    parent.append(line);
  }
  function appendFrameDiffs(parent, label, rows2) {
    const items = rows2 || [];
    const line = document.createElement("p");
    if (!items.length) {
      line.textContent = t("plan.none", { label });
      parent.append(line);
      return;
    }
    line.textContent = t("plan.files", { label, count: items.length });
    parent.append(line);
    for (const item of items.slice(0, 12)) {
      const row = document.createElement("p");
      row.textContent = fileName(item.path || "");
      parent.append(row);
    }
  }
  function fileName(path) {
    const parts = String(path).split(/[/\\]/);
    return parts[parts.length - 1] || path;
  }
  function setSnapshotDialogStatus(message) {
    el("snapshot-status").textContent = message;
  }
  async function takeSnapshot() {
    const button2 = el("snapshots-take");
    button2.disabled = true;
    button2.textContent = t("snapshots.saving");
    try {
      await postJSON("/api/snapshots", { action: "create" });
      state.snapshotMessage = "snapshots.saved";
      await loadSnapshots();
    } finally {
      button2.disabled = false;
      button2.textContent = t("snapshots.take");
    }
  }
  async function confirmSnapshotRestore() {
    const confirm2 = el("snapshot-confirm");
    confirm2.disabled = true;
    confirm2.textContent = t("snapshots.restoring");
    setSnapshotDialogStatus("");
    try {
      const undoing = state.snapshotUndo && state.snapshotUndo.restore_id === state.snapshotPlanId;
      const body = undoing ? { action: "undo", confirm: true } : { action: "restore", id: state.snapshotPlanId, confirm: true };
      await postJSON("/api/snapshots", body);
      el("snapshot-dialog").close();
      state.snapshotMessage = "snapshots.restored";
      await loadSnapshots();
      await reloadLibrary();
    } catch (error2) {
      setSnapshotDialogStatus(failureOf(error2).message);
      confirm2.disabled = false;
    } finally {
      confirm2.textContent = t("snapshots.restore");
    }
  }

  // src/player-strings.ts
  var playerStrings = {
    get region() {
      return t("player.region");
    },
    get play() {
      return t("player.play");
    },
    get pause() {
      return t("player.pause");
    },
    get seek() {
      return t("player.seek");
    },
    get volume() {
      return t("player.volume");
    },
    get elapsed() {
      return t("player.elapsed");
    },
    get duration() {
      return t("player.duration");
    },
    get nothingPlaying() {
      return t("player.nothingPlaying");
    },
    get untitled() {
      return t("track.untitled");
    },
    get previous() {
      return t("player.previous");
    },
    get next() {
      return t("player.next");
    },
    get cue() {
      return t("player.cue");
    },
    get cannotPlay() {
      return t("player.cannotPlay");
    },
    get notInLibrary() {
      return t("player.notInLibrary");
    },
    get zoomIn() {
      return t("player.zoomIn");
    },
    get zoomOut() {
      return t("player.zoomOut");
    },
    get overview() {
      return t("player.overview");
    },
    get overviewSeek() {
      return t("player.overviewSeek");
    },
    get waveformReading() {
      return t("player.waveformReading");
    },
    get waveformUnavailable() {
      return t("player.waveformUnavailable");
    }
  };

  // src/waveform.ts
  var TILE_CSS_WIDTH = 256;
  var ZOOM_DEFAULT_PPS = 80;
  var ZOOM_MIN_PPS = 10;
  var ZOOM_MAX_PPS = 320;
  var ZOOM_FACTOR = 1.25;
  var WAVE_BG = { r: 35, g: 25, b: 16 };
  var OUTER_ALPHA = 0.6;
  var PLAYED_SHADE = 0.45;
  var BEAT_HEIGHT_RATIO = 0.12;
  var DOWNBEAT_HEIGHT_RATIO = 0.18;
  var BEAT_ALPHA = 0.28;
  var DOWNBEAT_ALPHA = 0.35;
  var DEFAULT_MARKER_COLOR = { r: 226, g: 59, b: 22 };
  var PLAYHEAD_COLOR = { r: 226, g: 59, b: 22 };
  var BEAT_MARK = { r: 255, g: 255, b: 255 };
  var HEADER_BYTES = 64;
  var HEX_COLOR = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/;
  var MAX_POINTS = 2e7;
  var MAX_TICKS = 8192;
  function parseSwf1(input) {
    const bytes = input instanceof Uint8Array ? input : new Uint8Array(input);
    if (bytes.byteLength < HEADER_BYTES) return null;
    if (bytes[0] !== 83 || bytes[1] !== 87 || bytes[2] !== 70 || bytes[3] !== 49) return null;
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    if (view.getUint16(4, true) !== HEADER_BYTES) return null;
    const version = view.getUint16(6, true);
    const flags = view.getUint16(8, true);
    const analyzerVersion = view.getUint16(10, true);
    const sampleRate = view.getUint32(12, true);
    const detailHzMilli = view.getUint32(16, true);
    const durationMs = view.getUint32(20, true);
    const detailCount = view.getUint32(24, true);
    const overviewCount = view.getUint32(28, true);
    const seratoColumns = view.getUint32(32, true);
    const seratoBands = view.getUint16(36, true);
    const lowHzMilli = view.getUint32(40, true);
    const highHzMilli = view.getUint32(44, true);
    if (detailCount > MAX_POINTS || overviewCount > MAX_POINTS || seratoColumns > MAX_POINTS) return null;
    const detailBytes = detailCount * 6;
    const overviewBytes = overviewCount * 6;
    const seratoBytes = seratoColumns * seratoBands;
    if (!Number.isSafeInteger(detailBytes + overviewBytes + seratoBytes)) return null;
    const end = HEADER_BYTES + detailBytes + overviewBytes + seratoBytes;
    if (end !== bytes.byteLength) return null;
    let offset = HEADER_BYTES;
    const detail = bytes.slice(offset, offset + detailBytes);
    offset += detailBytes;
    const overview = bytes.slice(offset, offset + overviewBytes);
    offset += overviewBytes;
    const serato = bytes.slice(offset, offset + seratoBytes);
    return {
      version,
      flags,
      analyzerVersion,
      sampleRate,
      pointsPerSecond: detailHzMilli / 1e3,
      durationMs,
      detail,
      overview,
      serato,
      detailCount,
      overviewCount,
      seratoColumns,
      seratoBands,
      lowHz: lowHzMilli / 1e3,
      highHz: highHzMilli / 1e3
    };
  }
  function bandColor(low, mid, high) {
    const l = clamp255(low);
    const m = clamp255(mid);
    const h = clamp255(high);
    const max = Math.max(l, m, h);
    if (max === 0) return { r: 0, g: 0, b: 0 };
    return {
      r: Math.round(l / max * 255),
      g: Math.round(m / max * 255),
      b: Math.round(h / max * 255)
    };
  }
  function bandLevel(low, mid, high) {
    return Math.max(clamp255(low), clamp255(mid), clamp255(high)) / 255;
  }
  function seratoColumnLevels(column) {
    let low = 0;
    let mid = 0;
    let high = 0;
    const count = Math.min(column.length, 16);
    for (let index = 0; index < count; index += 1) {
      const value = clamp255(column[index] ?? 0);
      if (index <= 4) low = Math.max(low, value);
      else if (index <= 10) mid = Math.max(mid, value);
      else high = Math.max(high, value);
    }
    return { low, mid, high };
  }
  function beatgridTicks(markers, startSeconds, endSeconds) {
    if (!Number.isFinite(startSeconds) || !Number.isFinite(endSeconds) || endSeconds <= startSeconds) return [];
    const ordered = markers.filter((marker) => Number.isFinite(marker.positionSeconds)).slice();
    ordered.sort((left, right) => left.positionSeconds - right.positionSeconds);
    if (ordered.length === 0) return [];
    const ticks = [];
    let beatIndex = 0;
    for (let index = 0; index < ordered.length; index += 1) {
      const marker = ordered[index];
      if (!marker) continue;
      const next2 = ordered[index + 1];
      if (next2) {
        const beats = marker.beats;
        if (beats === void 0 || !Number.isFinite(beats) || beats < 1) continue;
        const count = Math.round(beats);
        const spacing2 = (next2.positionSeconds - marker.positionSeconds) / beats;
        if (!(spacing2 > 0) || count < 1) continue;
        pushRange(ticks, marker.positionSeconds, spacing2, beatIndex, count, startSeconds, endSeconds);
        beatIndex += count;
        continue;
      }
      const bpm = marker.bpm;
      if (bpm === void 0 || !Number.isFinite(bpm) || bpm <= 0) continue;
      const spacing = 60 / bpm;
      if (!(spacing > 0)) continue;
      const first = Math.max(0, Math.ceil((startSeconds - marker.positionSeconds) / spacing - 1e-9));
      const lastExclusive = Math.ceil((endSeconds - marker.positionSeconds) / spacing - 1e-9);
      if (lastExclusive <= first) continue;
      const emit2 = Math.min(lastExclusive, first + MAX_TICKS);
      pushRange(ticks, marker.positionSeconds, spacing, beatIndex, emit2, startSeconds, endSeconds, first);
    }
    return ticks;
  }
  function timeToX(timeSeconds, playheadSeconds, pixelsPerSecond, width) {
    if (!(pixelsPerSecond > 0) || !Number.isFinite(timeSeconds) || !Number.isFinite(playheadSeconds) || !Number.isFinite(width)) {
      return width / 2;
    }
    return width / 2 + (timeSeconds - playheadSeconds) * pixelsPerSecond;
  }
  function overviewXToTime(x, width, durationSeconds) {
    if (!(width > 0) || !(durationSeconds > 0) || !Number.isFinite(x)) return 0;
    const ratio = Math.min(1, Math.max(0, x / width));
    return ratio * durationSeconds;
  }
  function zoomPixelsPerSecond(current2, direction) {
    const base = Number.isFinite(current2) && current2 > 0 ? current2 : ZOOM_DEFAULT_PPS;
    const next2 = base * (direction > 0 ? ZOOM_FACTOR : 1 / ZOOM_FACTOR);
    if (next2 >= ZOOM_MAX_PPS) return ZOOM_MAX_PPS;
    if (next2 <= ZOOM_MIN_PPS) return ZOOM_MIN_PPS;
    return next2;
  }
  function tileDeviceWidth(dpr) {
    const scale = Number.isFinite(dpr) && dpr > 0 ? dpr : 1;
    return Math.max(1, Math.round(TILE_CSS_WIDTH * scale));
  }
  function colorFromHex(value) {
    if (!HEX_COLOR.test(value)) return null;
    let hex = value.slice(1);
    if (hex.length === 3) {
      const r = hex[0] ?? "";
      const g = hex[1] ?? "";
      const b = hex[2] ?? "";
      hex = `${r}${r}${g}${g}${b}${b}`;
    }
    if (hex.length === 8) hex = hex.slice(0, 6);
    const parsed = Number.parseInt(hex, 16);
    if (!Number.isFinite(parsed)) return null;
    return { r: parsed >> 16 & 255, g: parsed >> 8 & 255, b: parsed & 255 };
  }
  function beatgridFromMarkers(rows2) {
    if (!rows2 || rows2.length === 0) return [];
    const found = [];
    for (const row of rows2) {
      const position = finiteNumber(row.position_seconds) ?? finiteNumber(row.position);
      if (position === null) continue;
      const marker = { positionSeconds: position };
      const beats = finiteNumber(row.beats);
      const bpm = finiteNumber(row.bpm);
      if (beats !== null) marker.beats = beats;
      if (bpm !== null) marker.bpm = bpm;
      found.push(marker);
    }
    return found;
  }
  function loopsFromMarkers(rows2) {
    if (!rows2 || rows2.length === 0) return [];
    const found = [];
    for (const row of rows2) {
      const start = finiteNumber(row.start_ms);
      const end = finiteNumber(row.end_ms);
      if (start === null || end === null || end <= start || start < 0) continue;
      found.push({
        startSeconds: start / 1e3,
        endSeconds: end / 1e3,
        color: typeof row.color === "string" ? row.color : ""
      });
    }
    return found;
  }
  var DetailTiles = class {
    /**
     * Remember one detail buffer.
     *
     * @param detail `N * 6` uint8 bytes.
     * @param pointCount N.
     * @param pointsPerSecond Detail rate from the header. 150 in SWF1.
     */
    constructor(detail, pointCount, pointsPerSecond) {
      this.detail = detail;
      this.pointCount = pointCount;
      this.pointsPerSecond = pointsPerSecond;
    }
    detail;
    pointCount;
    pointsPerSecond;
    tiles = /* @__PURE__ */ new Map();
    blank = null;
    /**
     * Drop cached tiles.
     *
     * Called when the zoom changes so the next frame rebuilds at the new scale.
     */
    clear() {
      this.tiles.clear();
    }
    /**
     * Paint one zoomed frame into `frame`.
     *
     * The playhead is the center column. Tiles outside the view, plus one
     * tile of margin, are not generated. Markers are cues, shaded loops, and
     * beat ticks. Downbeats are taller.
     *
     * @param frame RGBA buffer of `width * height`.
     * @param width Device pixels.
     * @param height Device pixels.
     * @param dpr Device pixel ratio.
     * @param playheadSeconds Audio position.
     * @param pixelsPerSecond CSS pixels per second.
     * @param markers Cues, loops, and the beatgrid. Beat ticks are not drawn
     *   when the grid is empty.
     * @returns How many detail points this call sampled. Zero when every
     *   visible tile was already cached.
     */
    paint(frame, width, height, dpr, playheadSeconds, pixelsPerSecond, markers) {
      const scale = Number.isFinite(dpr) && dpr > 0 ? dpr : 1;
      const pps = pixelsPerSecond > 0 ? pixelsPerSecond : ZOOM_DEFAULT_PPS;
      this.ensureBlank(width, height);
      const blank = this.blank;
      if (!blank || frame.length !== blank.length) return { pointsRead: 0 };
      frame.set(blank);
      const cssWidth = width / scale;
      const tileSeconds = TILE_CSS_WIDTH / pps;
      const tileWidth = tileDeviceWidth(scale);
      const viewStart = playheadSeconds - cssWidth / 2 / pps;
      const viewEnd = playheadSeconds + cssWidth / 2 / pps;
      const first = Math.floor(viewStart / tileSeconds) - 1;
      const last = Math.floor(viewEnd / tileSeconds) + 1;
      let pointsRead = 0;
      const needed = /* @__PURE__ */ new Set();
      for (let index = first; index <= last; index += 1) {
        const key = `${Math.round(pps * 1e3)}|${scale}|${height}|${index}`;
        needed.add(key);
        let tile = this.tiles.get(key);
        if (!tile) {
          const rendered = renderTile(
            this.detail,
            this.pointCount,
            this.pointsPerSecond,
            index * tileSeconds,
            tileSeconds,
            tileWidth,
            height,
            scale
          );
          tile = rendered.pixels;
          pointsRead += rendered.pointsRead;
          this.tiles.set(key, tile);
        }
        const left = timeToX(index * tileSeconds, playheadSeconds, pps, cssWidth) * scale;
        blit(frame, width, height, tile, tileWidth, Math.round(left));
      }
      if (this.tiles.size > 24) {
        for (const key of this.tiles.keys()) {
          if (!needed.has(key)) this.tiles.delete(key);
        }
      }
      drawLoops(frame, width, height, scale, playheadSeconds, pps, cssWidth, markers.loops);
      drawBeats(frame, width, height, scale, playheadSeconds, pps, cssWidth, markers.beatgrid, viewStart, viewEnd);
      drawCues(frame, width, height, scale, playheadSeconds, pps, cssWidth, markers.cues);
      drawPlayhead(frame, width, height);
      return { pointsRead };
    }
    ensureBlank(width, height) {
      const count = width * height * 4;
      if (this.blank && this.blank.length === count) return;
      const blank = new Uint8ClampedArray(count);
      fillBackground(blank);
      this.blank = blank;
    }
  };
  function renderOverview(source, width, height) {
    const pixels = new Uint8ClampedArray(width * height * 4);
    fillBackground(pixels);
    const columns = source.kind === "computed" ? source.count : source.columns.length;
    if (columns < 1 || width < 1 || height < 1) return pixels;
    for (let x = 0; x < width; x += 1) {
      const start = Math.floor(x / width * columns);
      const end = Math.max(start + 1, Math.floor((x + 1) / width * columns));
      let lowPeak = 0;
      let lowRms = 0;
      let midPeak = 0;
      let midRms = 0;
      let highPeak = 0;
      let highRms = 0;
      for (let index = start; index < end && index < columns; index += 1) {
        if (source.kind === "computed") {
          const offset = index * 6;
          lowPeak = Math.max(lowPeak, source.points[offset] ?? 0);
          lowRms = Math.max(lowRms, source.points[offset + 1] ?? 0);
          midPeak = Math.max(midPeak, source.points[offset + 2] ?? 0);
          midRms = Math.max(midRms, source.points[offset + 3] ?? 0);
          highPeak = Math.max(highPeak, source.points[offset + 4] ?? 0);
          highRms = Math.max(highRms, source.points[offset + 5] ?? 0);
        } else {
          const levels = seratoColumnLevels(source.columns[index] ?? []);
          lowPeak = Math.max(lowPeak, levels.low);
          midPeak = Math.max(midPeak, levels.mid);
          highPeak = Math.max(highPeak, levels.high);
          lowRms = lowPeak;
          midRms = midPeak;
          highRms = highPeak;
        }
      }
      paintColumn(pixels, x, width, height, 0, lowPeak, lowRms, midPeak, midRms, highPeak, highRms);
    }
    return pixels;
  }
  function shadePlayed(pixels, width, height, playedX) {
    const end = Math.max(0, Math.min(width, Math.round(playedX)));
    for (let y = 0; y < height; y += 1) {
      const row = y * width;
      for (let x = 0; x < end; x += 1) {
        const offset = (row + x) * 4;
        pixels[offset] = Math.round((pixels[offset] ?? 0) * PLAYED_SHADE);
        pixels[offset + 1] = Math.round((pixels[offset + 1] ?? 0) * PLAYED_SHADE);
        pixels[offset + 2] = Math.round((pixels[offset + 2] ?? 0) * PLAYED_SHADE);
      }
    }
  }
  function drawOverviewMarks(pixels, width, height, durationSeconds, playheadSeconds, markers) {
    if (!(durationSeconds > 0) || width < 1) return;
    const xOf = (seconds) => seconds / durationSeconds * width;
    drawLoops(pixels, width, height, 1, 0, 1, width, markers.loops, xOf);
    drawCues(pixels, width, height, 1, 0, 1, width, markers.cues, xOf);
    const playX = Math.round(Math.min(width - 1, Math.max(0, xOf(playheadSeconds))));
    fillSpan(pixels, width, height, playX, playX + 1, 0, height, PLAYHEAD_COLOR, 1);
  }
  function renderTile(detail, pointCount, pointsPerSecond, startSeconds, tileSeconds, width, height, dpr) {
    const pixels = new Uint8ClampedArray(width * height * 4);
    fillBackground(pixels);
    let pointsRead = 0;
    const rate = pointsPerSecond > 0 ? pointsPerSecond : 150;
    for (let x = 0; x < width; x += 1) {
      const t0 = startSeconds + x / width * tileSeconds;
      const t1 = startSeconds + (x + 1) / width * tileSeconds;
      let i0 = Math.floor(t0 * rate);
      let i1 = Math.ceil(t1 * rate);
      if (i1 <= i0) i1 = i0 + 1;
      if (i0 < 0) i0 = 0;
      if (i1 > pointCount) i1 = pointCount;
      if (i0 >= i1) continue;
      let lowPeak = 0;
      let lowRms = 0;
      let midPeak = 0;
      let midRms = 0;
      let highPeak = 0;
      let highRms = 0;
      for (let index = i0; index < i1; index += 1) {
        pointsRead += 1;
        const offset = index * 6;
        lowPeak = Math.max(lowPeak, detail[offset] ?? 0);
        lowRms = Math.max(lowRms, detail[offset + 1] ?? 0);
        midPeak = Math.max(midPeak, detail[offset + 2] ?? 0);
        midRms = Math.max(midRms, detail[offset + 3] ?? 0);
        highPeak = Math.max(highPeak, detail[offset + 4] ?? 0);
        highRms = Math.max(highRms, detail[offset + 5] ?? 0);
      }
      paintColumn(pixels, x, width, height, 0, lowPeak, lowRms, midPeak, midRms, highPeak, highRms);
    }
    return { pixels, pointsRead };
  }
  function paintColumn(pixels, x, width, height, gutter, lowPeak, lowRms, midPeak, midRms, highPeak, highRms) {
    const peakLevel = bandLevel(lowPeak, midPeak, highPeak);
    const rmsLevel = bandLevel(lowRms, midRms, highRms);
    if (peakLevel <= 0 && rmsLevel <= 0) return;
    const top = Math.min(gutter, height - 1);
    const bandHeight = height - top;
    const mid = top + (bandHeight - 1) / 2;
    const peakHalf = Math.max(peakLevel > 0 ? 0.5 : 0, peakLevel * (bandHeight / 2) * 0.92);
    const rmsHalf = rmsLevel * (bandHeight / 2) * 0.92;
    const y0 = Math.max(top, Math.floor(mid - Math.max(peakHalf, rmsHalf)));
    const y1 = Math.min(height - 1, Math.ceil(mid + Math.max(peakHalf, rmsHalf)));
    const peakColor = bandColor(lowPeak, midPeak, highPeak);
    const rmsColor = bandColor(lowRms, midRms, highRms);
    for (let y = y0; y <= y1; y += 1) {
      const fromMid = Math.abs(y - mid);
      const inner = rmsLevel > 0 && fromMid <= rmsHalf;
      const outer = peakLevel > 0 && fromMid <= peakHalf;
      if (!inner && !outer) continue;
      const color = inner ? rmsColor : peakColor;
      const alpha = inner ? 1 : OUTER_ALPHA;
      blendPixel(pixels, width, x, y, color, alpha);
    }
  }
  function drawLoops(pixels, width, height, dpr, playheadSeconds, pixelsPerSecond, cssWidth, loops, xOf) {
    for (const loop of loops) {
      const color = colorFromHex(loop.color) ?? DEFAULT_MARKER_COLOR;
      const start = xOf ? xOf(loop.startSeconds) : timeToX(loop.startSeconds, playheadSeconds, pixelsPerSecond, cssWidth) * dpr;
      const end = xOf ? xOf(loop.endSeconds) : timeToX(loop.endSeconds, playheadSeconds, pixelsPerSecond, cssWidth) * dpr;
      const left = Math.min(start, end);
      const right = Math.max(start, end);
      fillSpan(pixels, width, height, Math.floor(left), Math.ceil(right), 0, height, color, 0.35);
      const edge = Math.max(1, Math.round(dpr));
      fillSpan(pixels, width, height, Math.round(left), Math.round(left) + edge, 0, height, color, 1);
      fillSpan(pixels, width, height, Math.round(right) - edge, Math.round(right), 0, height, color, 1);
    }
  }
  function drawCues(pixels, width, height, dpr, playheadSeconds, pixelsPerSecond, cssWidth, cues2, xOf) {
    const edge = Math.max(1, Math.round(2 * dpr));
    for (const cue of cues2) {
      const color = colorFromHex(cue.color) ?? DEFAULT_MARKER_COLOR;
      const x = xOf ? xOf(cue.seconds) : timeToX(cue.seconds, playheadSeconds, pixelsPerSecond, cssWidth) * dpr;
      fillSpan(pixels, width, height, Math.round(x) - Math.floor(edge / 2), Math.round(x) - Math.floor(edge / 2) + edge, 0, height, color, 1);
    }
  }
  function drawBeats(pixels, width, height, dpr, playheadSeconds, pixelsPerSecond, cssWidth, markers, viewStart, viewEnd) {
    const ticks = beatgridTicks(markers, viewStart, viewEnd);
    const tickWidth = Math.max(1, Math.round(dpr));
    const regularHeight = Math.max(1, Math.round(height * BEAT_HEIGHT_RATIO));
    const downbeatHeight = Math.max(regularHeight + 1, Math.round(height * DOWNBEAT_HEIGHT_RATIO));
    for (const tick of ticks) {
      const x = Math.round(timeToX(tick.seconds, playheadSeconds, pixelsPerSecond, cssWidth) * dpr);
      const tickHeight = Math.min(tick.downbeat ? downbeatHeight : regularHeight, Math.floor(height / 2) - 1);
      if (tickHeight < 1) continue;
      const alpha = tick.downbeat ? DOWNBEAT_ALPHA : BEAT_ALPHA;
      fillSpan(pixels, width, height, x, x + tickWidth, 0, tickHeight, BEAT_MARK, alpha);
      fillSpan(pixels, width, height, x, x + tickWidth, height - tickHeight, height, BEAT_MARK, alpha);
    }
  }
  function drawPlayhead(pixels, width, height) {
    const x = Math.floor(width / 2);
    fillSpan(pixels, width, height, x, x + 2, 0, height, PLAYHEAD_COLOR, 1);
  }
  function fillSpan(pixels, width, height, x0, x1, y0, y1, color, alpha) {
    const left = Math.max(0, x0);
    const right = Math.min(width, x1);
    const top = Math.max(0, y0);
    const bottom = Math.min(height, y1);
    for (let x = left; x < right; x += 1) {
      for (let y = top; y < bottom; y += 1) blendPixel(pixels, width, x, y, color, alpha);
    }
  }
  function blendPixel(pixels, width, x, y, color, alpha) {
    const offset = (y * width + x) * 4;
    const keep = 1 - alpha;
    pixels[offset] = Math.round(color.r * alpha + (pixels[offset] ?? 0) * keep);
    pixels[offset + 1] = Math.round(color.g * alpha + (pixels[offset + 1] ?? 0) * keep);
    pixels[offset + 2] = Math.round(color.b * alpha + (pixels[offset + 2] ?? 0) * keep);
    pixels[offset + 3] = 255;
  }
  function fillBackground(pixels) {
    for (let index = 0; index < pixels.length; index += 4) {
      pixels[index] = WAVE_BG.r;
      pixels[index + 1] = WAVE_BG.g;
      pixels[index + 2] = WAVE_BG.b;
      pixels[index + 3] = 255;
    }
  }
  function blit(dest, destWidth, destHeight, src, srcWidth, destX) {
    let srcX = 0;
    let copyWidth = srcWidth;
    let dx = destX;
    if (dx < 0) {
      srcX = -dx;
      copyWidth -= srcX;
      dx = 0;
    }
    if (dx + copyWidth > destWidth) copyWidth = destWidth - dx;
    if (copyWidth <= 0) return;
    for (let y = 0; y < destHeight; y += 1) {
      const srcStart = (y * srcWidth + srcX) * 4;
      const destStart = (y * destWidth + dx) * 4;
      dest.set(src.subarray(srcStart, srcStart + copyWidth * 4), destStart);
    }
  }
  function pushRange(ticks, origin, spacing, beatIndex, count, startSeconds, endSeconds, first = 0) {
    const begin = Math.max(first, Math.ceil((startSeconds - origin) / spacing - 1e-9));
    for (let index = begin; index < count; index += 1) {
      const seconds = origin + index * spacing;
      if (seconds < startSeconds - 1e-6) continue;
      if (seconds >= endSeconds - 1e-9) break;
      if (ticks.length >= MAX_TICKS) return;
      ticks.push({ seconds, downbeat: (beatIndex + index) % 4 === 0 });
    }
  }
  function finiteNumber(value) {
    if (typeof value === "number") return Number.isFinite(value) ? value : null;
    if (typeof value !== "string" || value.trim() === "") return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }
  function clamp255(value) {
    if (!Number.isFinite(value)) return 0;
    if (value <= 0) return 0;
    if (value >= 255) return 255;
    return value;
  }

  // src/waveform-view.ts
  var emptyMarkers = () => ({ cues: [], loops: [], beatgrid: [] });
  function mountWaveform(host, hooks) {
    return new WaveformView(host, hooks);
  }
  var WaveformView = class {
    host;
    hooks;
    detail;
    overviewCanvas;
    overviewHit;
    reading;
    note;
    detailWrap;
    zoomIn;
    zoomOut;
    trackId = null;
    token = 0;
    pps = ZOOM_DEFAULT_PPS;
    markers = emptyMarkers();
    tiles = null;
    parsed = null;
    overviewSource = "";
    seratoColumns = [];
    overviewCache = null;
    overviewKey = "";
    raf = 0;
    dragging = false;
    disposed = false;
    detailImage = null;
    overviewImage = null;
    lastAriaKey = "";
    ariaImmediate = false;
    onWheel;
    onResize;
    resizeObserver = null;
    constructor(host, hooks) {
      this.host = host;
      this.hooks = hooks;
      host.classList.add("player-wave");
      host.hidden = true;
      const main = document.createElement("div");
      main.className = "player-wave-main";
      this.detailWrap = document.createElement("div");
      this.detailWrap.className = "waveform-detail-wrap";
      this.detail = document.createElement("canvas");
      this.detail.className = "waveform-detail";
      this.detail.setAttribute("aria-hidden", "true");
      this.reading = document.createElement("p");
      this.reading.className = "waveform-reading";
      this.reading.textContent = playerStrings.waveformReading;
      this.detailWrap.append(this.detail, this.reading);
      this.note = document.createElement("p");
      this.note.className = "waveform-note";
      this.note.hidden = true;
      this.note.textContent = playerStrings.waveformUnavailable;
      this.overviewHit = document.createElement("div");
      this.overviewHit.className = "waveform-overview";
      this.overviewHit.tabIndex = 0;
      this.overviewHit.setAttribute("role", "slider");
      this.overviewHit.setAttribute("aria-label", playerStrings.overview);
      this.overviewHit.setAttribute("aria-orientation", "horizontal");
      setTooltip(this.overviewHit, tips.overview);
      this.overviewCanvas = document.createElement("canvas");
      this.overviewCanvas.setAttribute("aria-hidden", "true");
      this.overviewHit.append(this.overviewCanvas);
      main.append(this.detailWrap, this.note, this.overviewHit);
      const zoom = document.createElement("div");
      zoom.className = "waveform-zoom";
      this.zoomIn = button(playerStrings.zoomIn, "+", tips.zoomIn);
      this.zoomOut = button(playerStrings.zoomOut, "−", tips.zoomOut);
      this.zoomIn.addEventListener("click", () => this.setZoom(zoomPixelsPerSecond(this.pps, 1)));
      this.zoomOut.addEventListener("click", () => this.setZoom(zoomPixelsPerSecond(this.pps, -1)));
      zoom.append(this.zoomIn, this.zoomOut);
      host.append(main, zoom);
      this.onWheel = (event) => this.wheel(event);
      host.addEventListener("wheel", this.onWheel, { passive: false });
      this.overviewHit.addEventListener("pointerdown", (event) => this.pointerDown(event));
      this.overviewHit.addEventListener("pointermove", (event) => this.pointerMove(event));
      this.overviewHit.addEventListener("pointerup", (event) => this.pointerUp(event));
      this.overviewHit.addEventListener("pointercancel", (event) => this.pointerUp(event));
      this.overviewHit.addEventListener("keydown", (event) => this.overviewKeyDown(event));
      this.onResize = () => this.paint();
      if (typeof ResizeObserver === "function") {
        this.resizeObserver = new ResizeObserver(this.onResize);
        this.resizeObserver.observe(host);
      }
      this.syncZoomButtons();
    }
    /**
     * Load one track, or hide the waveform when playback is cleared.
     *
     * The same id does not fetch again. Overview and the SWF1 body are
     * requested together. Playback is not paused from here.
     *
     * @param id Library track id, or null when nothing is loaded.
     */
    setTrack(id) {
      if (this.disposed) return;
      if (id !== null && id === this.trackId) return;
      this.token += 1;
      this.trackId = id;
      this.parsed = null;
      this.tiles = null;
      this.markers = emptyMarkers();
      this.overviewCache = null;
      this.overviewKey = "";
      this.overviewSource = "";
      this.seratoColumns = [];
      delete this.overviewHit.dataset.waveformOverview;
      if (id === null || !Number.isInteger(id) || id < 0) {
        this.host.hidden = true;
        this.stopLoop();
        return;
      }
      this.host.hidden = false;
      this.setPhase("reading");
      const mine = this.token;
      void this.load(id, mine);
    }
    /**
     * Store cues, loops, and the beatgrid for the loaded track.
     *
     * A response for a track that is no longer loaded is ignored.
     *
     * @param id Track the rows belong to.
     * @param markers Marks to draw. Colors stay as stored.
     */
    setMarkers(id, markers) {
      if (id !== this.trackId) return;
      this.markers = markers;
      this.paint();
    }
    /**
     * Show a parsed waveform without fetching.
     *
     * The screenshot harness and tests use this. The host is shown.
     *
     * @param parsed SWF1 sections.
     */
    showComputed(parsed) {
      this.trackId = this.trackId ?? 1;
      this.host.hidden = false;
      this.applyComputed(parsed);
    }
    /** Refresh titles and notes in the active language. Playback is not touched. */
    relabel() {
      this.reading.textContent = playerStrings.waveformReading;
      if (!this.note.hidden) this.note.textContent = playerStrings.waveformUnavailable;
      this.overviewHit.setAttribute("aria-label", playerStrings.overview);
      setTooltip(this.overviewHit, tips.overview);
      this.zoomIn.setAttribute("aria-label", playerStrings.zoomIn);
      setTooltip(this.zoomIn, tips.zoomIn);
      this.zoomOut.setAttribute("aria-label", playerStrings.zoomOut);
      setTooltip(this.zoomOut, tips.zoomOut);
    }
    /**
     * Show the format note and hide the canvases.
     *
     * The screenshot harness uses this for a file that cannot be decoded.
     * Playback is not touched.
     */
    showUnavailable() {
      this.token += 1;
      this.parsed = null;
      this.tiles = null;
      this.overviewSource = "";
      this.seratoColumns = [];
      this.overviewCache = null;
      this.overviewKey = "";
      delete this.overviewHit.dataset.waveformOverview;
      this.host.hidden = false;
      this.setPhase("unavailable");
    }
    /**
     * Follow play, pause, and seek.
     *
     * While audio is playing, frames are scheduled from the audio clock.
     * A paused seek paints once.
     */
    sync() {
      if (this.disposed || this.host.hidden) return;
      if (this.hooks.getPlaying()) this.startLoop();
      else this.stopLoop();
      this.paint();
    }
    /**
     * Current zoom in CSS pixels per second.
     *
     * @returns The zoom the buttons and the wheel last set.
     */
    pixelsPerSecond() {
      return this.pps;
    }
    /**
     * Remove listeners and stop the animation frame.
     */
    destroy() {
      this.disposed = true;
      this.token += 1;
      this.stopLoop();
      this.host.removeEventListener("wheel", this.onWheel);
      this.resizeObserver?.disconnect();
      this.resizeObserver = null;
    }
    async load(id, mine) {
      const overview = this.fetchOverview(id);
      const body = this.fetchWaveform(id);
      void overview.then((serato) => {
        if (mine !== this.token || !serato || serato.length === 0) return;
        if (this.overviewSource === "computed") return;
        this.seratoColumns = serato;
        this.overviewSource = "serato";
        this.overviewHit.dataset.waveformOverview = "serato";
        this.overviewCache = null;
        this.overviewKey = "";
        this.overviewHit.hidden = false;
        this.paint();
      });
      const waveform2 = await body;
      if (mine !== this.token) return;
      if (waveform2 === "unavailable") {
        this.parsed = null;
        this.tiles = null;
        this.setPhase("unavailable");
        this.paint();
        return;
      }
      if (waveform2) this.applyComputed(waveform2);
    }
    applyComputed(parsed) {
      this.parsed = parsed;
      const rate = parsed.pointsPerSecond > 0 ? parsed.pointsPerSecond : 150;
      this.tiles = new DetailTiles(parsed.detail, parsed.detailCount, rate);
      this.overviewSource = "computed";
      this.overviewHit.dataset.waveformOverview = "computed";
      this.overviewCache = null;
      this.overviewKey = "";
      this.setPhase("ready");
      this.paint();
    }
    async fetchOverview(id) {
      try {
        if (typeof fetch !== "function") return null;
        const response = await fetch(waveformUrl(id, true));
        if (!response.ok) return null;
        const payload = await response.json();
        if (!payload || typeof payload !== "object") return null;
        const record = payload;
        if (record.available !== true || !Array.isArray(record.data)) return null;
        const columns = [];
        for (const column of record.data) {
          if (!Array.isArray(column)) continue;
          columns.push(column.map((value) => typeof value === "number" && Number.isFinite(value) ? value : 0));
        }
        return columns;
      } catch {
        return null;
      }
    }
    async fetchWaveform(id) {
      try {
        if (typeof fetch !== "function") return null;
        const response = await fetch(waveformUrl(id, false));
        if (!response.ok) return null;
        const buffer = await response.arrayBuffer();
        const parsed = parseSwf1(buffer);
        if (parsed) return parsed;
        const text = new TextDecoder().decode(buffer);
        try {
          const payload = JSON.parse(text);
          if (payload && typeof payload === "object" && payload.available === false) {
            return "unavailable";
          }
        } catch {
          return null;
        }
        return null;
      } catch {
        return null;
      }
    }
    setPhase(phase2) {
      this.host.dataset.waveformState = phase2;
      const unavailable = phase2 === "unavailable";
      this.note.hidden = !unavailable;
      this.reading.hidden = phase2 !== "reading";
      this.detailWrap.hidden = unavailable;
      this.overviewHit.hidden = this.overviewSource === "";
      this.syncZoomButtons();
    }
    setZoom(next2) {
      if (next2 === this.pps) {
        this.syncZoomButtons();
        return;
      }
      this.pps = next2;
      this.tiles?.clear();
      this.syncZoomButtons();
      this.paint();
    }
    syncZoomButtons() {
      const phase2 = this.host.dataset.waveformState;
      const blocked = phase2 === "reading" || phase2 === "unavailable";
      this.zoomIn.disabled = blocked || this.pps >= ZOOM_MAX_PPS - 1e-9;
      this.zoomOut.disabled = blocked || this.pps <= ZOOM_MIN_PPS + 1e-9;
    }
    wheel(event) {
      if (!event.ctrlKey && !event.metaKey) return;
      if (this.host.dataset.waveformState !== "ready") return;
      event.preventDefault();
      if (event.deltaY < 0) this.setZoom(zoomPixelsPerSecond(this.pps, 1));
      else if (event.deltaY > 0) this.setZoom(zoomPixelsPerSecond(this.pps, -1));
    }
    pointerDown(event) {
      if (event.button !== 0) return;
      this.dragging = true;
      if (typeof this.overviewHit.setPointerCapture === "function") {
        this.overviewHit.setPointerCapture(event.pointerId);
      }
      this.seekOverview(event);
    }
    pointerMove(event) {
      if (!this.dragging) return;
      this.seekOverview(event);
    }
    pointerUp(event) {
      if (!this.dragging) return;
      this.dragging = false;
      if (typeof this.overviewHit.hasPointerCapture === "function" && this.overviewHit.hasPointerCapture(event.pointerId)) {
        this.overviewHit.releasePointerCapture(event.pointerId);
      }
    }
    seekOverview(event) {
      const rect = this.overviewHit.getBoundingClientRect();
      const duration2 = this.duration();
      const x = event.clientX - rect.left;
      this.ariaImmediate = true;
      this.hooks.seek(overviewXToTime(x, rect.width, duration2));
    }
    overviewKeyDown(event) {
      if (event.altKey || event.ctrlKey || event.metaKey || event.repeat) return;
      const forward = event.key === "ArrowRight" || event.key === "ArrowUp";
      const back = event.key === "ArrowLeft" || event.key === "ArrowDown";
      if (!forward && !back) return;
      event.preventDefault();
      event.stopPropagation();
      const step = event.shiftKey ? this.hooks.seekStepLarge : this.hooks.seekStep;
      this.ariaImmediate = true;
      this.hooks.seekBy((forward ? 1 : -1) * step);
    }
    startLoop() {
      if (this.raf !== 0) return;
      const loop = () => {
        this.paint();
        if (this.hooks.getPlaying() && !this.disposed) this.raf = requestAnimationFrame(loop);
        else this.raf = 0;
      };
      this.raf = requestAnimationFrame(loop);
    }
    stopLoop() {
      if (this.raf === 0) return;
      cancelAnimationFrame(this.raf);
      this.raf = 0;
    }
    paint() {
      if (this.disposed || this.host.hidden) return;
      const time = this.hooks.getTime();
      const duration2 = this.duration();
      this.paintDetail(time);
      this.paintOverview(time, duration2);
      const immediate = this.ariaImmediate;
      this.ariaImmediate = false;
      this.updateSlider(time, duration2, immediate);
    }
    paintDetail(time) {
      if (!this.tiles || !this.parsed) return;
      const size = sizeCanvas(this.detail, 96);
      if (!size) return;
      const context = this.detail.getContext("2d");
      if (!context) return;
      const image = this.canvasImage(context, "detail", size.width, size.height);
      this.tiles.paint(image.data, size.width, size.height, size.dpr, time, this.pps, this.markers);
      context.putImageData(image, 0, 0);
    }
    paintOverview(time, duration2) {
      const size = sizeCanvas(this.overviewCanvas, 36);
      if (!size) return;
      const source = this.overviewPixels(size.width, size.height);
      if (!source) return;
      const context = this.overviewCanvas.getContext("2d");
      if (!context) return;
      const image = this.canvasImage(context, "overview", size.width, size.height);
      image.data.set(source);
      const played = duration2 > 0 ? Math.min(duration2, Math.max(0, time)) / duration2 * size.width : 0;
      shadePlayed(image.data, size.width, size.height, played);
      drawOverviewMarks(image.data, size.width, size.height, duration2 > 0 ? duration2 : this.headerDuration(), time, this.markers);
      context.putImageData(image, 0, 0);
    }
    /**
     * One ImageData for a canvas, replaced only when the bitmap size changes.
     *
     * Width and height already include the device pixel ratio, so a DPR
     * change allocates again. Playback reuses the same buffer.
     *
     * @param context Canvas context that owns the buffer.
     * @param which Detail or overview cache.
     * @param width Device pixels.
     * @param height Device pixels.
     * @returns The buffer to draw into.
     */
    canvasImage(context, which, width, height) {
      const current2 = which === "detail" ? this.detailImage : this.overviewImage;
      if (current2 && current2.width === width && current2.height === height) return current2;
      const image = context.createImageData(width, height);
      if (which === "detail") this.detailImage = image;
      else this.overviewImage = image;
      return image;
    }
    overviewPixels(width, height) {
      const key = `${this.overviewSource}|${width}|${height}|${this.token}`;
      if (this.overviewCache && this.overviewKey === key) return this.overviewCache;
      if (this.overviewSource === "computed" && this.parsed && this.parsed.overviewCount > 0) {
        this.overviewCache = renderOverview(
          { kind: "computed", points: this.parsed.overview, count: this.parsed.overviewCount },
          width,
          height
        );
        this.overviewKey = key;
        this.overviewHit.dataset.waveformOverview = "computed";
        return this.overviewCache;
      }
      if (this.overviewSource === "serato" && this.seratoColumns.length > 0) {
        this.overviewCache = renderOverview({ kind: "serato", columns: this.seratoColumns }, width, height);
        this.overviewKey = key;
        this.overviewHit.dataset.waveformOverview = "serato";
        return this.overviewCache;
      }
      return null;
    }
    updateSlider(time, duration2, immediate) {
      const max = duration2 > 0 ? duration2 : 0;
      const now = Math.min(max, Math.max(0, Number.isFinite(time) ? time : 0));
      const key = `${Math.floor(now)}|${max}`;
      if (!immediate && key === this.lastAriaKey) return;
      this.lastAriaKey = key;
      this.overviewHit.setAttribute("aria-valuemin", "0");
      this.overviewHit.setAttribute("aria-valuemax", String(max));
      this.overviewHit.setAttribute("aria-valuenow", String(now));
      this.overviewHit.setAttribute("aria-valuetext", this.hooks.formatTime(now));
    }
    duration() {
      const fromAudio = this.hooks.getDuration();
      if (Number.isFinite(fromAudio) && fromAudio > 0) return fromAudio;
      return this.headerDuration();
    }
    headerDuration() {
      if (!this.parsed || !(this.parsed.durationMs > 0)) return 0;
      return this.parsed.durationMs / 1e3;
    }
  };
  function button(label, text, tooltip) {
    const element = buttonEl(tooltip);
    element.className = "waveform-zoom-button";
    element.textContent = text;
    element.setAttribute("aria-label", label);
    return element;
  }
  function waveformUrl(id, overview) {
    const params = new URLSearchParams({ id: String(id), space: state.space });
    const path = overview ? "/api/waveform/overview" : "/api/waveform";
    return `${path}?${params.toString()}`;
  }
  function sizeCanvas(canvas, cssHeight) {
    const cssWidth = canvas.clientWidth;
    if (!(cssWidth > 0)) return null;
    const dpr = typeof window !== "undefined" && window.devicePixelRatio > 0 ? window.devicePixelRatio : 1;
    const width = Math.max(1, Math.round(cssWidth * dpr));
    const height = Math.max(1, Math.round(cssHeight * dpr));
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }
    return { width, height, dpr };
  }

  // src/player.ts
  var SEEK_STEP_SECONDS = 5;
  var SEEK_STEP_LARGE_SECONDS = 30;
  var listeners = /* @__PURE__ */ new Set();
  var wired = /* @__PURE__ */ new WeakSet();
  var CUE_COLOR = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/;
  var media = null;
  var trackId = null;
  var title = "";
  var artist = "";
  var playing = false;
  var currentTime = 0;
  var duration = 0;
  var volume = 1;
  var error = "";
  var seeking = false;
  var ignoreMediaPause = false;
  var cueToken = 0;
  var cues = [];
  var paintedCueKey = "";
  var barUnsubscribe = null;
  var waveform = null;
  var titleNode = null;
  var artistNode = null;
  var statusNode = null;
  var toggleNode = null;
  var previousNode = null;
  var nextNode = null;
  var seekNode = null;
  var cueLayer = null;
  var elapsedNode = null;
  var totalNode = null;
  var elapsedLabelNode = null;
  var totalLabelNode = null;
  var volumeTextNode = null;
  function formatPlayerTime(seconds) {
    if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
    const total = Math.floor(seconds);
    const secs = total % 60;
    const minutes = Math.floor(total / 60);
    if (minutes >= 60) {
      const hours = Math.floor(minutes / 60);
      const mins = minutes % 60;
      return `${hours}:${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
    }
    return `${minutes}:${String(secs).padStart(2, "0")}`;
  }
  function markersFromCues(rows2) {
    if (!rows2 || rows2.length === 0) return [];
    const found = [];
    for (const cue of rows2) {
      const start = Number(cue.start_ms);
      if (!Number.isFinite(start) || start < 0) continue;
      const index = Number(cue.index);
      const named = typeof cue.name === "string" ? cue.name.trim() : "";
      const fallback = Number.isInteger(index) ? index + 1 : found.length + 1;
      const color = typeof cue.color === "string" && CUE_COLOR.test(cue.color) ? cue.color : "";
      found.push({
        seconds: start / 1e3,
        color,
        label: named || `${playerStrings.cue} ${fallback}`
      });
    }
    return found;
  }
  function playbackErrorText(status) {
    if (status === 403 || status === 404) return playerStrings.notInLibrary;
    return playerStrings.cannotPlay;
  }
  function play(nextId) {
    if (!Number.isInteger(nextId) || nextId < 0) return;
    const element = ensureMedia();
    ignoreMediaPause = true;
    try {
      if (trackId !== nextId || element.src === "") {
        const row = state.byId.get(nextId);
        title = row?.name || row?.title || playerStrings.untitled;
        artist = row?.artist ?? "";
        trackId = nextId;
        currentTime = 0;
        duration = 0;
        element.src = trackUrl(nextId);
        element.currentTime = 0;
        waveform?.setTrack(nextId);
        loadCues(nextId);
      }
      error = "";
      playing = true;
      emit();
      const pending = element.play();
      if (pending && typeof pending.then === "function") {
        pending.catch(() => {
          if (trackId !== nextId) return;
          noteFailure(nextId);
        });
      }
    } finally {
      ignoreMediaPause = false;
    }
  }
  function pause() {
    if (trackId === null) return;
    playing = false;
    ensureMedia().pause();
    emit();
  }
  function togglePlayPause() {
    if (trackId === null) {
      const selected = selectedPlayableId();
      if (selected !== null) play(selected);
      return;
    }
    if (playing) pause();
    else play(trackId);
  }
  function next() {
    moveBy(1);
  }
  function previous() {
    moveBy(-1);
  }
  function seek(seconds) {
    if (!Number.isFinite(seconds) || trackId === null) return;
    const element = ensureMedia();
    let next2 = seconds < 0 ? 0 : seconds;
    const limit = element.duration;
    if (Number.isFinite(limit) && limit > 0 && next2 > limit) next2 = limit;
    element.currentTime = next2;
    currentTime = next2;
    emit();
  }
  function seekBy(deltaSeconds) {
    if (!Number.isFinite(deltaSeconds)) return;
    seek(currentTime + deltaSeconds);
  }
  var playerControls = {
    togglePlayPause,
    seekBy
  };
  function getPlayerState() {
    return { trackId, title, artist, playing, currentTime, duration, volume, error };
  }
  function subscribe(listener) {
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  }
  function mountPlayer(host) {
    barUnsubscribe?.();
    barUnsubscribe = null;
    waveform?.destroy();
    waveform = null;
    resetPlayback();
    const root = host === void 0 ? document.getElementById("player-bar") : host;
    if (!root) return;
    root.classList.add("player-bar");
    root.setAttribute("role", "region");
    root.setAttribute("aria-label", playerStrings.region);
    const element = ensureMedia();
    root.replaceChildren();
    if (element instanceof Node) root.append(element);
    root.append(buildBar());
    barUnsubscribe = subscribe(() => paintBar());
    paintBar();
  }
  function repaintPlayer() {
    const root = document.getElementById("player-bar");
    if (root) root.setAttribute("aria-label", playerStrings.region);
    waveform?.relabel();
    paintBar();
  }
  function resetPlayback() {
    cueToken += 1;
    trackId = null;
    title = "";
    artist = "";
    playing = false;
    currentTime = 0;
    duration = 0;
    error = "";
    seeking = false;
    cues = [];
    paintedCueKey = "";
  }
  function ensureMedia() {
    if (media) return media;
    const audio = document.createElement("audio");
    audio.id = "player-audio";
    audio.preload = "none";
    audio.className = "player-audio";
    audio.volume = volume;
    media = audio;
    wire(audio);
    return audio;
  }
  function wire(element) {
    if (wired.has(element)) return;
    wired.add(element);
    element.addEventListener("play", () => {
      playing = true;
      emit();
    });
    element.addEventListener("pause", () => {
      if (ignoreMediaPause) return;
      playing = false;
      emit();
    });
    element.addEventListener("ended", () => {
      currentTime = Number.isFinite(element.currentTime) ? element.currentTime : currentTime;
      if (!moveBy(1)) {
        playing = false;
        emit();
      }
    });
    element.addEventListener("timeupdate", () => {
      currentTime = element.currentTime;
      if (Number.isFinite(element.duration)) duration = element.duration;
      emit();
    });
    element.addEventListener("durationchange", () => {
      duration = Number.isFinite(element.duration) ? element.duration : 0;
      emit();
    });
    element.addEventListener("error", () => {
      if (trackId === null) return;
      noteFailure(trackId);
    });
  }
  function trackUrl(nextId) {
    const params = new URLSearchParams({ id: String(nextId), space: state.space });
    return `/api/audio?${params.toString()}`;
  }
  function selectedPlayableId() {
    if (state.mode === "history") return null;
    const selected = state.selectedId;
    if (selected === null) return null;
    const row = state.byId.get(selected);
    if (!row || row.entry) return null;
    return row.id;
  }
  function playableRows() {
    return state.view.filter((row) => !row.entry && Number.isInteger(row.id) && row.id >= 0);
  }
  function anchorIndex(rows2) {
    if (trackId !== null) {
      const playingIndex = rows2.findIndex((row) => row.id === trackId);
      if (playingIndex >= 0) return playingIndex;
    }
    if (state.selectedId === null) return -1;
    return rows2.findIndex((row) => row.id === state.selectedId);
  }
  function moveBy(delta) {
    const rows2 = playableRows();
    if (rows2.length === 0) return false;
    const index = anchorIndex(rows2);
    const target = index < 0 ? rows2[delta > 0 ? 0 : rows2.length - 1] : rows2[index + delta];
    if (!target) return false;
    play(target.id);
    return true;
  }
  function loadCues(id) {
    const token = ++cueToken;
    cues = [];
    waveform?.setMarkers(id, { cues: [], loops: [], beatgrid: [] });
    void readCues(id).then(
      (found) => {
        if (token !== cueToken || trackId !== id) return;
        cues = found.cues;
        waveform?.setMarkers(id, found);
        emit();
      },
      () => {
        if (token !== cueToken || trackId !== id) return;
        cues = [];
        waveform?.setMarkers(id, { cues: [], loops: [], beatgrid: [] });
        emit();
      }
    );
  }
  async function readCues(id) {
    const empty = { cues: [], loops: [], beatgrid: [] };
    if (typeof fetch !== "function") return empty;
    const params = new URLSearchParams({ id: String(id), space: state.space });
    const response = await fetch(`/api/track?${params.toString()}`);
    if (!response.ok) return empty;
    const payload = await response.json();
    if (!payload || typeof payload !== "object") return empty;
    const record = payload;
    return {
      cues: markersFromCues(record.cues),
      loops: loopsFromMarkers(record.loops),
      beatgrid: beatgridFromMarkers(record.beatgrid)
    };
  }
  function noteFailure(forId) {
    playing = false;
    void classifyStatus(forId).then((message) => {
      if (trackId !== forId) return;
      playing = false;
      error = message;
      emit();
    });
  }
  async function classifyStatus(forId) {
    try {
      if (typeof fetch !== "function") return playerStrings.cannotPlay;
      const response = await fetch(trackUrl(forId), { method: "HEAD" });
      return playbackErrorText(response.status);
    } catch {
      return playerStrings.cannotPlay;
    }
  }
  function emit() {
    const snapshot = getPlayerState();
    for (const listener of [...listeners]) listener(snapshot);
    waveform?.sync();
  }
  function buildBar() {
    const meta = document.createElement("div");
    meta.className = "player-meta";
    titleNode = document.createElement("p");
    titleNode.className = "player-title";
    artistNode = document.createElement("p");
    artistNode.className = "player-artist";
    statusNode = document.createElement("p");
    statusNode.className = "player-status";
    statusNode.setAttribute("role", "status");
    meta.append(titleNode, artistNode, statusNode);
    previousNode = buttonEl(tips.previous);
    previousNode.className = "player-toggle";
    previousNode.textContent = playerStrings.previous;
    previousNode.addEventListener("click", () => previous());
    toggleNode = buttonEl(playTip(playerStrings.play, ""));
    toggleNode.className = "player-toggle player-play";
    toggleNode.addEventListener("click", () => togglePlayPause());
    nextNode = buttonEl(tips.next);
    nextNode.className = "player-toggle";
    nextNode.textContent = playerStrings.next;
    nextNode.addEventListener("click", () => next());
    const transport = document.createElement("div");
    transport.className = "player-transport";
    transport.append(previousNode, toggleNode, nextNode);
    const seekWrap = document.createElement("div");
    seekWrap.className = "player-seek";
    const elapsedWrap = document.createElement("span");
    elapsedWrap.className = "player-time";
    elapsedLabelNode = document.createElement("span");
    elapsedLabelNode.className = "visually-hidden";
    elapsedLabelNode.textContent = playerStrings.elapsed;
    const elapsedLabel = elapsedLabelNode;
    elapsedNode = document.createElement("span");
    elapsedWrap.append(elapsedLabel, elapsedNode);
    const track = document.createElement("div");
    track.className = "player-seek-track";
    seekNode = inputEl(tips.seek);
    seekNode.type = "range";
    seekNode.className = "player-range";
    seekNode.min = "0";
    seekNode.max = "0";
    seekNode.step = "0.1";
    seekNode.value = "0";
    seekNode.setAttribute("aria-label", playerStrings.seek);
    seekNode.addEventListener("pointerdown", () => {
      seeking = true;
    });
    const release = () => {
      seeking = false;
    };
    seekNode.addEventListener("pointerup", release);
    seekNode.addEventListener("pointercancel", release);
    seekNode.addEventListener("input", () => {
      if (!seekNode) return;
      seek(Number(seekNode.value));
    });
    seekNode.addEventListener("keydown", onSeekKey);
    cueLayer = document.createElement("div");
    cueLayer.className = "player-cues";
    track.append(seekNode, cueLayer);
    const totalWrap = document.createElement("span");
    totalWrap.className = "player-time";
    totalLabelNode = document.createElement("span");
    totalLabelNode.className = "visually-hidden";
    totalLabelNode.textContent = playerStrings.duration;
    const totalLabel = totalLabelNode;
    totalNode = document.createElement("span");
    totalWrap.append(totalLabel, totalNode);
    seekWrap.append(elapsedWrap, track, totalWrap);
    const volumeLabel = document.createElement("label");
    volumeLabel.className = "player-volume";
    volumeTextNode = document.createElement("span");
    volumeTextNode.textContent = playerStrings.volume;
    const volumeText = volumeTextNode;
    const volumeInput = inputEl(tips.volume);
    volumeInput.type = "range";
    volumeInput.min = "0";
    volumeInput.max = "1";
    volumeInput.step = "0.01";
    volumeInput.value = String(volume);
    volumeInput.addEventListener("input", () => {
      const next2 = Number(volumeInput.value);
      if (!Number.isFinite(next2)) return;
      volume = Math.min(1, Math.max(0, next2));
      ensureMedia().volume = volume;
      emit();
    });
    volumeLabel.append(volumeText, volumeInput);
    const bar = document.createElement("div");
    bar.className = "player-controls";
    bar.append(meta, transport, seekWrap, volumeLabel);
    const waveHost = document.createElement("div");
    waveform = mountWaveform(waveHost, {
      seek,
      seekBy,
      getTime: () => {
        const value = ensureMedia().currentTime;
        return Number.isFinite(value) ? value : currentTime;
      },
      getDuration: () => {
        const value = ensureMedia().duration;
        if (Number.isFinite(value) && value > 0) return value;
        return duration;
      },
      getPlaying: () => playing,
      formatTime: formatPlayerTime,
      seekStep: SEEK_STEP_SECONDS,
      seekStepLarge: SEEK_STEP_LARGE_SECONDS
    });
    const stack = document.createElement("div");
    stack.className = "player-stack";
    stack.append(waveHost, bar);
    return stack;
  }
  function onSeekKey(event) {
    if (event.altKey || event.ctrlKey || event.metaKey || event.repeat) return;
    const forward = event.key === "ArrowRight" || event.key === "ArrowUp";
    const back = event.key === "ArrowLeft" || event.key === "ArrowDown";
    if (!forward && !back) return;
    event.preventDefault();
    event.stopPropagation();
    const step = event.shiftKey ? SEEK_STEP_LARGE_SECONDS : SEEK_STEP_SECONDS;
    seekBy((forward ? 1 : -1) * step);
  }
  function paintBar() {
    if (!titleNode || !artistNode || !statusNode || !toggleNode || !previousNode || !nextNode) return;
    if (!seekNode || !elapsedNode || !totalNode) return;
    const loaded = trackId !== null;
    const shownTitle = loaded ? title || playerStrings.untitled : playerStrings.nothingPlaying;
    titleNode.textContent = shownTitle;
    titleNode.title = shownTitle;
    artistNode.textContent = artist;
    artistNode.hidden = artist === "";
    artistNode.title = artist;
    statusNode.textContent = error;
    statusNode.hidden = error === "";
    statusNode.title = error;
    if (elapsedLabelNode) elapsedLabelNode.textContent = playerStrings.elapsed;
    if (totalLabelNode) totalLabelNode.textContent = playerStrings.duration;
    if (volumeTextNode) volumeTextNode.textContent = playerStrings.volume;
    if (previousNode) previousNode.textContent = playerStrings.previous;
    if (nextNode) nextNode.textContent = playerStrings.next;
    seekNode.setAttribute("aria-label", playerStrings.seek);
    const action = playing ? playerStrings.pause : playerStrings.play;
    const named = loaded ? title || playerStrings.untitled : "";
    toggleNode.textContent = action;
    setTooltip(toggleNode, playTip(action, named));
    toggleNode.disabled = !loaded && selectedPlayableId() === null;
    toggleNode.setAttribute("aria-pressed", String(playing));
    toggleNode.setAttribute("aria-label", named ? `${action} ${named}` : action);
    previousNode.disabled = !canMove(-1);
    nextNode.disabled = !canMove(1);
    previousNode.setAttribute("aria-label", playerStrings.previous);
    nextNode.setAttribute("aria-label", playerStrings.next);
    const limit = Number.isFinite(duration) && duration > 0 ? duration : 0;
    seekNode.max = String(limit);
    seekNode.disabled = !loaded || limit === 0;
    if (!seeking) seekNode.value = String(Math.min(currentTime, limit || currentTime));
    elapsedNode.textContent = formatPlayerTime(currentTime);
    totalNode.textContent = formatPlayerTime(duration);
    paintCues(limit);
  }
  function canMove(delta) {
    const rows2 = playableRows();
    if (rows2.length === 0) return false;
    const index = anchorIndex(rows2);
    if (index < 0) return true;
    return Boolean(rows2[index + delta]);
  }
  function paintCues(limit) {
    if (!cueLayer) return;
    const key = `${limit}|${cues.map((cue) => `${cue.seconds}:${cue.label}:${cue.color}`).join(";")}`;
    if (key === paintedCueKey) return;
    paintedCueKey = key;
    cueLayer.replaceChildren();
    if (!(limit > 0) || cues.length === 0) return;
    for (const cue of cues) {
      const label = `${cue.label}, ${formatPlayerTime(cue.seconds)}`;
      const button2 = buttonEl(cueTip(label));
      button2.className = "player-cue";
      const ratio = Math.min(1, Math.max(0, cue.seconds / limit));
      const percent = Math.round(ratio * 1e3) / 10;
      button2.style.left = `${percent}%`;
      if (cue.color) button2.style.setProperty("--cue", cue.color);
      button2.setAttribute("aria-label", label);
      button2.addEventListener("click", () => {
        seek(cue.seconds);
      });
      cueLayer.append(button2);
    }
  }

  // src/virtual-scroll.ts
  var spacer = document.createElement("div");
  var rows = document.createElement("div");
  spacer.className = "spacer";
  rows.className = "rows";
  spacer.append(rows);
  function mountTrackList() {
    el("list").append(spacer);
  }
  function paintRows() {
    const view = state.view || [];
    const height = el("list").clientHeight || 600;
    const start = Math.max(0, Math.floor(el("list").scrollTop / ROW) - 6);
    const end = Math.min(view.length, Math.ceil((el("list").scrollTop + height) / ROW) + 6);
    spacer.style.height = `${view.length * ROW}px`;
    rows.style.transform = `translateY(${start * ROW}px)`;
    rows.replaceChildren();
    if (!view.length) {
      const empty = document.createElement("p");
      empty.className = "empty-list";
      empty.textContent = state.mode === "duplicates" && !state.duplicateIds ? t("list.readingDuplicates") : t("list.noMatches");
      rows.append(empty);
      return;
    }
    for (let index = start; index < end; index += 1) {
      const track = view[index];
      const button2 = document.createElement("div");
      button2.className = "row";
      button2.setAttribute("role", "option");
      button2.setAttribute("aria-selected", String(track.id === state.selectedId));
      button2.dataset.id = String(track.id);
      setTooltip(button2, selectRow(track.name || "Untitled"));
      const titleCell = document.createElement("span");
      titleCell.className = "cell";
      const line = document.createElement("span");
      line.className = "title-line";
      if (!track.entry) {
        const playingNow = getPlayerState();
        const playingThis = playingNow.trackId === track.id && playingNow.playing;
        const playButton = buttonEl(playRow(track.name || playerStrings.untitled));
        playButton.className = "row-play";
        const labelName = track.name || playerStrings.untitled;
        playButton.setAttribute("aria-label", `${playerStrings.play} ${labelName}`);
        playButton.setAttribute("aria-pressed", String(playingThis));
        const icon = document.createElement("span");
        icon.className = "row-play-icon";
        icon.setAttribute("aria-hidden", "true");
        playButton.append(icon);
        playButton.addEventListener("click", (event) => {
          event.stopPropagation();
          bridge.selectTrack(track.id);
          play(track.id);
          el("list").focus({ preventScroll: true });
        });
        playButton.addEventListener("dblclick", (event) => event.stopPropagation());
        line.append(playButton);
      }
      const hex = colorHex(track.color);
      if (hex) {
        const swatch = document.createElement("span");
        swatch.className = "swatch";
        swatch.style.background = hex;
        line.append(swatch);
      }
      if (track.emoji) {
        const emoji = document.createElement("span");
        emoji.textContent = track.emoji;
        line.append(emoji);
      }
      const title2 = document.createElement("span");
      title2.className = "title";
      title2.textContent = track.name || t("track.untitled");
      line.append(title2);
      if (track.missing) {
        const missing = document.createElement("span");
        missing.className = "missing-word";
        missing.textContent = t("track.missingBadge");
        line.append(missing);
      }
      if (track.stems) {
        const stems = document.createElement("span");
        stems.className = "missing-word";
        stems.textContent = t("track.stemsBadge");
        line.append(stems);
      }
      titleCell.append(line);
      const artist2 = document.createElement("span");
      artist2.className = "cell";
      artist2.textContent = track.artist ?? "";
      const third = document.createElement("span");
      third.className = "cell num";
      const fourth = document.createElement("span");
      fourth.className = "cell num";
      const fifth = document.createElement("span");
      fifth.className = "cell num";
      if (track.entry) {
        third.textContent = track.deck || "";
        fourth.textContent = track.played || "";
        fifth.textContent = clockLabel(track.start);
      } else {
        third.textContent = track.bpm == null ? "" : formatNumber(Math.round(Number(track.bpm) * 100) / 100, { maximumFractionDigits: 2 });
        fourth.textContent = track.key ?? "";
        fifth.textContent = lengthLabel(track.length_ms);
      }
      button2.append(titleCell, artist2, third, fourth, fifth);
      button2.addEventListener("click", () => {
        if (track.entry) bridge.selectEntry(track.id);
        else bridge.selectTrack(track.id);
        el("list").focus({ preventScroll: true });
      });
      button2.addEventListener("dblclick", () => {
        if (!track.entry) play(track.id);
      });
      rows.append(button2);
    }
  }
  function moveTrackList(delta) {
    moveSelection(delta);
  }
  function openTrackList() {
    const view = state.view || [];
    const current2 = view.find((track) => track.id === state.selectedId) ?? view[0];
    if (!current2) return;
    if (current2.entry) bridge.selectEntry(current2.id);
    else void bridge.selectTrack(current2.id);
  }
  function moveSelection(delta) {
    const view = state.view || [];
    const index = view.findIndex((track) => track.id === state.selectedId);
    const next2 = view[Math.max(0, Math.min(view.length - 1, index + delta))];
    if (!next2) return;
    if (next2.entry) bridge.selectEntry(next2.id);
    else bridge.selectTrack(next2.id);
    const rowTop = view.indexOf(next2) * ROW;
    if (rowTop < el("list").scrollTop) el("list").scrollTop = rowTop;
    if (rowTop + ROW > el("list").scrollTop + el("list").clientHeight) {
      el("list").scrollTop = rowTop + ROW - el("list").clientHeight;
    }
  }
  function focusedTrack(target) {
    if (!(target instanceof Element)) return void 0;
    const row = target.closest(".row");
    if (!row) return void 0;
    const id = Number(row.getAttribute("data-id"));
    if (!Number.isInteger(id)) return void 0;
    return state.view.find((item) => item.id === id);
  }
  function wireVirtualScroll() {
    el("list").addEventListener("scroll", () => paintRows());
    el("list").addEventListener("keydown", (event) => {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        moveSelection(1);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        moveSelection(-1);
      } else if (event.key === "Enter") {
        const chosen = focusedTrack(event.target) ?? state.view.find((item) => item.id === state.selectedId);
        if (!chosen || chosen.entry) return;
        event.preventDefault();
        void bridge.selectTrack(chosen.id);
        play(chosen.id);
      }
    });
    let paintedId = null;
    let paintedPlaying = false;
    subscribe((next2) => {
      if (next2.trackId === paintedId && next2.playing === paintedPlaying) return;
      paintedId = next2.trackId;
      paintedPlaying = next2.playing;
      paintRows();
    });
  }

  // src/views.ts
  var relatedRequest = 0;
  var lastDetail = null;
  function matchesQuery(track, terms) {
    if (!terms.length) return true;
    const hay = `${track.name} ${track.artist} ${track.album} ${track.genre} ${track.key} ${track.file}`.toLocaleLowerCase();
    return terms.every((term) => hay.includes(term));
  }
  function queryTerms() {
    return state.query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  }
  function childLists() {
    const children = /* @__PURE__ */ new Map();
    for (const crate of state.crates) {
      const key = crate.parent ?? 0;
      if (!children.has(key)) children.set(key, []);
      const bucket = children.get(key);
      bucket.push(crate);
    }
    for (const list of children.values()) {
      list.sort((a, b) => {
        if (state.crateSort === "name") {
          return a.name.localeCompare(b.name, void 0, { sensitivity: "base" }) || a.id - b.id;
        }
        if (state.crateSort === "added") return (b.added || 0) - (a.added || 0) || a.id - b.id;
        return a.order - b.order || a.id - b.id;
      });
    }
    return children;
  }
  function crateKeep() {
    const terms = state.crateQuery.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
    if (!terms.length) return null;
    const byId = new Map(state.crates.map((crate) => [crate.id, crate]));
    const keep = /* @__PURE__ */ new Set();
    for (const crate of state.crates) {
      if (!terms.every((term) => crate.name.toLocaleLowerCase().includes(term))) continue;
      let current2 = crate;
      const guard = /* @__PURE__ */ new Set();
      while (current2 && !guard.has(current2.id)) {
        guard.add(current2.id);
        keep.add(current2.id);
        current2 = byId.get(current2.parent);
      }
    }
    return keep;
  }
  function visibleCrates() {
    const children = childLists();
    const keep = crateKeep();
    const ordered = [];
    const seen = /* @__PURE__ */ new Set();
    function walk(parent, depth) {
      for (const crate of children.get(parent) || []) {
        if (seen.has(crate.id)) continue;
        if (keep && !keep.has(crate.id)) continue;
        seen.add(crate.id);
        crate.depth = depth;
        crate.childCount = (children.get(crate.id) || []).filter((child) => !keep || keep.has(child.id)).length;
        ordered.push(crate);
        if (keep || state.expanded.has(crate.id)) walk(crate.id, depth + 1);
      }
    }
    walk(state.rootId ?? null, 0);
    for (const crate of state.crates) {
      if (seen.has(crate.id)) continue;
      if (keep && !keep.has(crate.id)) continue;
      const parentListed = state.crates.some((item) => item.id === crate.parent);
      if (parentListed) continue;
      seen.add(crate.id);
      crate.depth = 0;
      crate.childCount = (children.get(crate.id) || []).filter((child) => !keep || keep.has(child.id)).length;
      ordered.push(crate);
      if (keep || state.expanded.has(crate.id)) walk(crate.id, 1);
    }
    return ordered;
  }
  function expandAncestors(id) {
    const byId = new Map(state.crates.map((crate2) => [crate2.id, crate2]));
    let crate = id === "all" ? void 0 : byId.get(id);
    const guard = /* @__PURE__ */ new Set();
    while (crate && !guard.has(crate.id)) {
      guard.add(crate.id);
      const parent = byId.get(crate.parent);
      if (!parent) break;
      state.expanded.add(parent.id);
      crate = parent;
    }
  }
  function hiddenSelectionHolder(visible) {
    if (state.activeCrate === "all") return null;
    if (visible.some((crate2) => crate2.id === state.activeCrate)) return null;
    const byId = new Map(state.crates.map((crate2) => [crate2.id, crate2]));
    const visibleIds = new Set(visible.map((crate2) => crate2.id));
    let crate = byId.get(state.activeCrate);
    const guard = /* @__PURE__ */ new Set();
    while (crate && !guard.has(crate.id)) {
      guard.add(crate.id);
      crate = byId.get(crate.parent);
      if (crate && visibleIds.has(crate.id)) return crate.id;
    }
    return null;
  }
  function modeTracks() {
    let tracks = state.tracks;
    if (state.mode === "missing") tracks = tracks.filter((track) => track.missing);
    else if (state.mode === "stems") tracks = tracks.filter((track) => track.stems);
    else if (state.mode === "duplicates") {
      const ids = state.duplicateIds;
      tracks = ids ? tracks.filter((track) => ids.has(track.id)) : [];
    } else if (state.mode === "crates" && state.activeCrate !== "all") {
      const ids = state.crateTracks.get(state.activeCrate);
      tracks = ids ? tracks.filter((track) => ids.has(track.id)) : [];
    }
    return tracks;
  }
  function buildView() {
    if (state.mode === "history") {
      const terms2 = queryTerms();
      const result2 = state.entries.filter((entry) => matchesQuery(entry, terms2)).map((entry) => ({
        id: entry.id,
        name: entry.name,
        artist: entry.artist,
        album: entry.album,
        file: entry.file,
        genre: "",
        key: entry.key,
        bpm: entry.bpm,
        length_ms: entry.length_ms,
        deck: entry.deck,
        played: entry.played ? t("common.yes") : "",
        start: entry.start_time,
        missing: entry.missing,
        entry: true,
        asset_id: entry.asset_id,
        notes: entry.notes
      }));
      result2.sort(compare);
      state.view = result2;
      return result2;
    }
    const terms = queryTerms();
    const result = modeTracks().filter((track) => matchesQuery(track, terms));
    result.sort(compare);
    state.view = result;
    return result;
  }
  function crateRow(crate) {
    const row = document.createElement("div");
    row.className = "crate-row";
    if (crate.holds) row.classList.add("holds-selection");
    row.style.paddingLeft = `${crate.depth * 14}px`;
    if (crate.childCount) {
      const open = state.crateQuery ? true : state.expanded.has(crate.id);
      const twist = buttonEl(open ? collapseCrate(crate.name) : expandCrate(crate.name));
      twist.className = "twist";
      twist.tabIndex = -1;
      twist.setAttribute("aria-expanded", String(open));
      twist.setAttribute("aria-label", t(open ? "crates.collapse" : "crates.expand", { name: crate.name }));
      twist.addEventListener("click", () => toggleCrate(crate.id));
      row.append(twist);
    } else {
      const gap = document.createElement("span");
      gap.className = "twist-gap";
      gap.setAttribute("aria-hidden", "true");
      row.append(gap);
    }
    const button2 = buttonEl(crate.id === "all" ? tips.allTracks : openCrate(crate.name));
    button2.className = "crate";
    button2.dataset.id = String(crate.id);
    if (crate.parent != null) button2.dataset.parent = String(crate.parent);
    button2.setAttribute("role", "treeitem");
    button2.setAttribute("aria-level", String(crate.depth + 1));
    button2.setAttribute("aria-selected", String(state.activeCrate === crate.id));
    if (crate.childCount) {
      button2.setAttribute("aria-expanded", String(state.crateQuery ? true : state.expanded.has(crate.id)));
    }
    const name = document.createElement("span");
    name.className = "name";
    const hex = colorHex(crate.color);
    if (hex) {
      const swatch = document.createElement("span");
      swatch.className = "swatch";
      swatch.style.background = hex;
      name.append(swatch);
    }
    name.append(document.createTextNode(crate.name));
    button2.append(name);
    if (crate.smart) {
      const smart = document.createElement("span");
      smart.className = "smart";
      smart.textContent = t("crates.smartBadge");
      button2.append(smart);
    }
    const meta = document.createElement("span");
    meta.className = "meta";
    meta.textContent = formatNumber(crate.count);
    button2.append(meta);
    button2.addEventListener("click", () => selectCrate(crate.id));
    row.append(button2);
    return row;
  }
  function placeCrateFocus(previousId) {
    const items = [...el("crate-list").querySelectorAll(".crate")];
    if (!items.length) return null;
    const current2 = items.find((item) => item.dataset.id === previousId) || items[0];
    for (const item of items) item.tabIndex = item === current2 ? 0 : -1;
    return current2;
  }
  function renderCrates() {
    const scroll = el("crate-list").scrollTop;
    const active2 = document.activeElement;
    const restore = el("crate-list").contains(active2) ? active2.closest(".crate-row")?.querySelector(".crate")?.dataset.id ?? null : null;
    const terms = queryTerms();
    const matched = terms.length ? new Set(state.tracks.filter((track) => matchesQuery(track, terms)).map((track) => track.id)) : null;
    const crates = visibleCrates();
    const holder = hiddenSelectionHolder(crates);
    el("crate-list").replaceChildren();
    el("crate-list").append(crateRow({
      id: "all",
      name: t("crates.allTracks"),
      depth: 0,
      childCount: 0,
      smart: false,
      count: matched ? matched.size : state.tracks.length
    }));
    for (const crate of crates) {
      const members = state.crateTracks.get(crate.id) || /* @__PURE__ */ new Set();
      let shown = members.size;
      if (matched) {
        shown = 0;
        for (const id of members) if (matched.has(id)) shown += 1;
      }
      el("crate-list").append(crateRow({
        id: crate.id,
        name: crate.name,
        depth: crate.depth || 0,
        childCount: crate.childCount || 0,
        smart: Boolean(crate.smart),
        parent: crate.parent ?? null,
        color: crate.color ?? null,
        count: shown,
        holds: holder === crate.id
      }));
    }
    const focused = placeCrateFocus(restore);
    if (restore && focused) focused.focus({ preventScroll: true });
    el("crate-list").scrollTop = scroll;
    renderRules();
  }
  function renderRules() {
    document.querySelector(".rules")?.remove();
    document.querySelector(".rule-edit")?.remove();
    const crate = state.crates.find((item) => item.id === state.activeCrate);
    if (!crate || !crate.rules || state.mode !== "crates") return;
    const line = document.createElement("p");
    line.className = "rules";
    if (Array.isArray(crate.rules.rules)) {
      const lead = document.createElement("strong");
      lead.textContent = t("rules.matches");
      const parts = crate.rules.rules.map((rule) => {
        const attribute = rule.attribute || "field";
        const operation = String(rule.operation || "").toLowerCase().replaceAll("_", " ");
        return `${attribute} ${operation} “${rule.value ?? ""}”`;
      });
      const join = crate.rules.conjunction === "OR" ? t("rules.or") : t("rules.and");
      line.append(lead, document.createTextNode(` ${parts.join(` ${join} `) || t("rules.none")}`));
    }
    const editor = document.createElement("div");
    editor.className = "rule-edit";
    const area = textareaEl(tips.smartRules);
    area.value = JSON.stringify(crate.rules, null, 2);
    area.disabled = !state.writable;
    area.setAttribute("aria-label", t("rules.label"));
    const save2 = buttonEl(tips.saveRules);
    save2.className = "text-button";
    save2.textContent = t("rules.save");
    save2.disabled = !state.writable;
    save2.addEventListener("click", () => saveRules(crate.id, area.value));
    editor.append(area, save2);
    const bar = document.querySelector(".browser-bar");
    bar.after(editor);
    bar.after(line);
  }
  function markHistoryColumns() {
    const history = state.mode === "history";
    document.querySelector(".columns")?.classList.toggle("for-history", history);
    el("list").classList.toggle("for-history", history);
  }
  function renderColumns() {
    markHistoryColumns();
    const columns = state.mode === "history" ? [["name", "column.title"], ["artist", "column.artist"], ["deck", "column.deck"], ["played", "column.played"], ["start", "column.time"]] : [["name", "column.title"], ["artist", "column.artist"], ["bpm", "column.bpm"], ["key", "column.key"], ["length_ms", "column.time"]];
    const buttons = [...document.querySelectorAll(".columns button")];
    columns.forEach(([key, label], index) => {
      const button2 = buttons[index];
      button2.dataset.sort = key;
      button2.textContent = t(label);
      button2.dataset.active = String(button2.dataset.sort === state.sort);
      setTooltip(button2, sortTip(key, t(label)));
    });
  }
  function renderShell() {
    markHistoryColumns();
    const cratesMode = state.mode === "crates";
    const historyMode = state.mode === "history";
    el("crate-tools").hidden = !cratesMode;
    el("crate-actions").hidden = !cratesMode;
    el("crate-list").hidden = !cratesMode;
    el("session-list").hidden = !historyMode;
    el("mode-note").hidden = cratesMode || historyMode;
    const filesMode = state.mode === "files";
    const snapshotsMode = state.mode === "snapshots";
    el("browser").hidden = filesMode || snapshotsMode;
    el("track-splitter").hidden = filesMode || snapshotsMode;
    el("detail").hidden = filesMode || snapshotsMode;
    el("files-panel").hidden = !filesMode;
    el("snapshots-panel").hidden = !snapshotsMode;
    if (state.mode === "missing") el("mode-note").textContent = t("mode.missing");
    if (state.mode === "duplicates") {
      el("mode-note").textContent = t("mode.duplicates");
    }
    if (state.mode === "stems") el("mode-note").textContent = t("mode.stems");
    if (filesMode) el("mode-note").textContent = t("mode.files");
    if (snapshotsMode) {
      el("mode-note").textContent = t("mode.snapshots");
    }
    for (const button2 of document.querySelectorAll("#views button")) {
      button2.setAttribute("aria-selected", String(button2.dataset.view === state.mode));
    }
    for (const button2 of document.querySelectorAll("[data-crate-sort]")) {
      button2.setAttribute("aria-pressed", String(button2.dataset.crateSort === state.crateSort));
    }
    const crateChosen = state.activeCrate !== "all";
    el("crate-new").disabled = !state.writable;
    el("crate-rename").disabled = !state.writable || !crateChosen;
    el("crate-color").disabled = !state.writable || !crateChosen;
    el("crate-delete").disabled = !state.writable || !crateChosen;
    syncMergeButton();
    if (filesMode) {
      if (state.filesAtRoots) {
        el("crate-foot").textContent = state.filesLoading ? t("files.readingRoots") : t("files.rootCount", { count: state.filesRoots.length });
        return;
      }
      const listed = state.filesEntries.filter((entry) => entry.kind === "file").length;
      el("crate-foot").textContent = state.filesLoading ? t("files.readingFolder") : t("files.fileCount", { count: listed });
      return;
    }
    if (snapshotsMode) {
      el("crate-foot").textContent = state.snapshotLoading ? t("snapshots.reading") : t("snapshots.count", { count: state.snapshots.length });
      return;
    }
    const pool = state.mode === "history" ? state.entries : footerTracks();
    const bytes = pool.reduce((sum, track) => sum + (Number(track.file_size) || 0), 0);
    const ms = pool.reduce((sum, track) => sum + (Number(track.length_ms) || 0), 0);
    el("crate-foot").textContent = `${formatNumber(pool.length)} · ${durationLabel(ms)} · ${sizeLabel(bytes)}`;
  }
  function footerTracks() {
    if (state.mode === "crates" && state.activeCrate !== "all") {
      const ids = state.crateTracks.get(state.activeCrate);
      return ids ? state.tracks.filter((track) => ids.has(track.id)) : [];
    }
    if (state.mode === "missing") return state.tracks.filter((track) => track.missing);
    if (state.mode === "stems") return state.tracks.filter((track) => track.stems);
    if (state.mode === "duplicates") {
      const duplicateIds = state.duplicateIds;
      return duplicateIds ? state.tracks.filter((track) => duplicateIds.has(track.id)) : [];
    }
    return state.tracks;
  }
  function renderList() {
    renderShell();
    if (state.mode === "files") {
      renderFiles();
      return;
    }
    renderColumns();
    const view = buildView();
    el("count").textContent = t(state.mode === "history" ? "count.plays" : "count.tracks", { count: view.length });
    if (state.mode === "crates") renderCrates();
    else document.querySelector(".rules")?.remove();
    paintRows();
    if (!view.some((track) => track.id === state.selectedId)) {
      if (!view.length) {
        state.selectedId = null;
        const empty = document.createElement("p");
        empty.className = "detail-empty";
        empty.textContent = state.mode === "history" && !state.historyId ? t("history.chooseSession") : t("list.noMatches");
        el("detail").replaceChildren(empty);
      } else if (state.mode === "history") selectEntry(view[0].id);
      else selectTrack(view[0].id);
    }
  }
  function toggleCrate(id) {
    if (state.crateQuery) return;
    if (state.expanded.has(id)) state.expanded.delete(id);
    else state.expanded.add(id);
    renderCrates();
    if (!state.writable) return;
    postJSON("/api/crate", {
      action: "expanded",
      id,
      expanded: state.expanded.has(id),
      space: state.space
    }).then((result) => {
      if (result.warning) setNotice(result.warning);
    }).catch((error2) => {
      if (failureOf(error2).status === 409) lockDown(error2);
      else setNotice(failureOf(error2).message);
    });
  }
  function selectCrate(id) {
    state.activeCrate = id;
    if (id !== "all") expandAncestors(id);
    el("list").scrollTop = 0;
    renderList();
  }
  function focusCrateItem(item) {
    if (!item) return;
    for (const button2 of el("crate-list").querySelectorAll(".crate")) button2.tabIndex = -1;
    item.tabIndex = 0;
    item.focus();
  }
  async function selectTrack(id) {
    state.selectedId = id;
    syncMergeButton();
    paintRows();
    const token = ++state.request;
    const pending = document.createElement("p");
    pending.className = "detail-empty";
    pending.textContent = t("detail.reading");
    el("detail").replaceChildren(pending);
    try {
      const response = await fetch(`/api/track?id=${id}&space=${encodeURIComponent(state.space)}`);
      const payload = await readJSONOr(response, {});
      if (!response.ok) throw new Error(serverMessage(payload, t("detail.readFailed", { status: String(response.status) })));
      if (token !== state.request) return;
      if (payload.serato) applyStatus(payload.serato);
      renderDetail(payload);
    } catch (error2) {
      if (token !== state.request) return;
      const failure = document.createElement("p");
      failure.className = "detail-error";
      failure.textContent = failureOf(error2).message;
      el("detail").replaceChildren(failure);
    }
  }
  function selectEntry(id) {
    state.selectedId = id;
    paintRows();
    const entry = state.entries.find((item) => item.id === id);
    if (!entry) return;
    const body = document.createElement("div");
    body.className = "detail-body";
    const title2 = document.createElement("h2");
    title2.textContent = entry.name || t("track.untitled");
    body.append(title2);
    if (entry.artist) {
      const artist2 = document.createElement("p");
      artist2.className = "artist";
      artist2.textContent = entry.artist;
      body.append(artist2);
    }
    const lines = [
      [t("column.played"), entry.played ? t("common.yes") : t("common.no")],
      [t("column.deck"), entry.deck || "—"],
      [t("history.started"), clockLabel(entry.start_time) || "—"],
      [t("history.file"), entry.file || "—"]
    ];
    if (entry.notes) lines.push([t("history.notes"), entry.notes]);
    for (const [label, value] of lines) {
      const row = document.createElement("div");
      row.className = "field";
      const name = document.createElement("div");
      name.className = "label";
      name.textContent = label;
      const text = document.createElement("div");
      text.className = "value";
      text.textContent = value;
      row.append(name, text);
      body.append(row);
    }
    if (entry.asset_id) {
      const open = buttonEl(tips.openInLibrary);
      open.className = "text-button";
      open.textContent = t("history.openInLibrary");
      open.addEventListener("click", () => openInLibrary(entry.asset_id));
      body.append(open);
    }
    el("detail").replaceChildren(body);
  }
  function fieldInput(name, label, value, wide = false) {
    const wrap = document.createElement("label");
    if (wide) wrap.className = "wide";
    wrap.append(document.createTextNode(label));
    const input = name === "comments" ? textareaEl(editField(label)) : inputEl(editField(label));
    input.name = name;
    input.value = String(value ?? "");
    if (name === "bpm") input.inputMode = "decimal";
    wrap.append(input);
    return wrap;
  }
  function renderDetail(track) {
    lastDetail = track;
    const writable = Boolean(track.serato?.writable && state.writable);
    const body = document.createElement("div");
    body.className = "detail-body";
    if (track.album) {
      const kicker = document.createElement("p");
      kicker.className = "detail-kicker";
      kicker.textContent = track.album;
      body.append(kicker);
    }
    const title2 = document.createElement("h2");
    title2.textContent = track.title ?? "";
    body.append(title2);
    if (track.artist) {
      const artist2 = document.createElement("p");
      artist2.className = "artist";
      artist2.textContent = track.artist ?? "";
      body.append(artist2);
    }
    const playTitle = track.title || track.name || playerStrings.untitled;
    const playButton = buttonEl(playRow(playTitle));
    playButton.className = "detail-play";
    playButton.textContent = playerStrings.play;
    playButton.setAttribute("aria-label", `${playerStrings.play} ${playTitle}`);
    playButton.addEventListener("click", () => {
      play(track.id);
    });
    body.append(playButton);
    const deck = document.createElement("div");
    deck.className = "deck";
    const facts = [["column.bpm", track.bpm], ["column.key", track.key || "—"], ["column.time", track.length]];
    for (const [key, value] of facts) {
      const label = t(key);
      const cell = document.createElement("div");
      const strong = document.createElement("strong");
      strong.textContent = String(value || "—");
      if (key === "column.bpm") strong.className = "bpm";
      const span = document.createElement("span");
      span.textContent = label;
      cell.append(strong, span);
      deck.append(cell);
    }
    if (track.color) {
      const cell = document.createElement("div");
      const swatch = document.createElement("span");
      swatch.className = "swatch swatch-lg";
      swatch.style.background = String(track.color ?? "");
      const span = document.createElement("span");
      span.textContent = t("field.color");
      cell.append(swatch, span);
      deck.append(cell);
    }
    body.append(deck);
    const note = document.createElement("p");
    note.className = "lock-note";
    note.textContent = track.serato?.message || el("status").textContent;
    body.append(note);
    const form = document.createElement("form");
    form.className = "editor";
    const edit = track.edit || {};
    const editorFields = [
      ["name", "column.title", true],
      ["artist", "column.artist", false],
      ["album", "field.album", false],
      ["genre", "field.genre", false],
      ["year", "field.year", false],
      ["composer", "field.composer", false],
      ["remixer", "field.remixer", false],
      ["label", "field.label", false],
      ["grouping", "field.grouping", false],
      ["key", "column.key", false],
      ["bpm", "column.bpm", false],
      ["emoji", "field.emoji", false],
      ["comments", "field.comments", true]
    ];
    for (const [name, label, wide] of editorFields) {
      form.append(fieldInput(name, t(label), String(edit[name] ?? ""), wide));
    }
    const colorLabel = document.createElement("label");
    colorLabel.append(document.createTextNode(t("field.color")));
    const colorSelect = selectEl(tips.trackColor);
    colorSelect.name = "color";
    const currentColor = Number(edit.color ?? 16777215);
    const palette = COLORS.map(([value, key]) => [value, t(key)]);
    if (!COLORS.some(([value]) => value === currentColor)) palette.push([currentColor, colorHex(currentColor) || t("color.custom")]);
    for (const [value, label] of palette) {
      const option = document.createElement("option");
      option.value = String(value);
      option.textContent = label;
      option.selected = value === currentColor;
      colorSelect.append(option);
    }
    colorLabel.append(colorSelect);
    form.append(colorLabel);
    const ratingLabel = document.createElement("label");
    ratingLabel.append(document.createTextNode(t("field.rating")));
    const ratingSelect = selectEl(tips.trackRating);
    ratingSelect.name = "rating";
    const ratings = [
      ["", t("rating.none")],
      ...[["0.2", 1], ["0.4", 2], ["0.6", 3], ["0.8", 4], ["1", 5]].map(([value, stars]) => [value, t("rating.stars", { count: stars })])
    ];
    if (edit.rating != null && !ratings.some(([value]) => Number(value) === Number(edit.rating))) {
      ratings.push([String(edit.rating), `${edit.rating}`]);
    }
    for (const [value, label] of ratings) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label ?? "";
      option.selected = value === (edit.rating == null ? "" : String(edit.rating));
      ratingSelect.append(option);
    }
    ratingLabel.append(ratingSelect);
    form.append(ratingLabel);
    const lock = document.createElement("label");
    lock.className = "check";
    const lockInput = inputEl(tips.beatgridLock);
    lockInput.type = "checkbox";
    lockInput.name = "is_beatgrid_locked";
    lockInput.checked = Boolean(edit.is_beatgrid_locked);
    lock.append(lockInput, document.createTextNode(t("field.beatgridLocked")));
    form.append(lock);
    const save2 = buttonEl(tips.saveTrack);
    save2.type = "submit";
    save2.className = "text-button wide";
    save2.textContent = t("detail.saveTrack");
    form.append(save2);
    for (const control of form.querySelectorAll("input, select, textarea, button")) control.disabled = !writable;
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      saveTrack(track.id, form);
    });
    body.append(form);
    const actions = document.createElement("div");
    actions.className = "actions";
    const reveal = buttonEl(revealTip(track.serato?.file_manager || state.serato?.file_manager || "Finder"));
    const manager = track.serato?.file_manager || state.serato?.file_manager || "Finder";
    reveal.textContent = t("detail.reveal", { manager });
    reveal.disabled = !track.file_on_disk;
    reveal.addEventListener("click", () => revealTrack(track.id));
    const prepare = buttonEl(track.in_prepare ? tips.prepareRemove : tips.prepareAdd);
    prepare.textContent = track.in_prepare ? t("detail.removePrepare") : t("detail.sendPrepare");
    prepare.disabled = !writable;
    prepare.addEventListener("click", () => prepareTrack(track.id, !track.in_prepare));
    const relocate = buttonEl(tips.relocate);
    relocate.textContent = t("detail.relocate");
    relocate.disabled = !writable;
    relocate.addEventListener("click", () => relocateTrack(track));
    const remove = buttonEl(tips.removeTrack);
    remove.textContent = t("detail.removeFromLibrary");
    remove.disabled = !writable;
    remove.addEventListener("click", () => removeTrack(track.id));
    actions.append(reveal, prepare, relocate, remove);
    if (state.mode === "duplicates" && selectedDuplicateGroup()) {
      const merge = buttonEl(tips.mergeDuplicates);
      merge.textContent = t("merge.title");
      merge.disabled = !writable;
      merge.addEventListener("click", () => {
        bridge.openMergeDialog().catch((error2) => setNotice(failureOf(error2).message));
      });
      actions.append(merge);
    }
    body.append(actions);
    body.append(relatedSection(track, writable));
    body.append(markerSection(track));
    if (track.copies?.length) body.append(copySection(track.copies));
    body.append(membershipSection(track, writable));
    for (const group of track.groups || []) {
      const section = document.createElement("section");
      section.className = "group";
      const heading = document.createElement("h3");
      heading.textContent = group.name ?? "";
      section.append(heading);
      const open = group.name !== "Search copies";
      if (!open) {
        const toggle = buttonEl(tips.showSearchCopies);
        toggle.className = "text-button";
        toggle.textContent = t("detail.searchCopies", { count: group.fields.length });
        let shown = false;
        section.hidden = true;
        toggle.addEventListener("click", () => {
          shown = !shown;
          section.hidden = !shown;
          toggle.textContent = shown ? t("detail.hideSearchCopies") : t("detail.searchCopies", { count: group.fields.length });
          setTooltip(toggle, shown ? tips.hideSearchCopies : tips.showSearchCopies);
        });
        body.append(toggle);
      }
      for (const field of group.fields) {
        const row = document.createElement("div");
        row.className = "field";
        const label = document.createElement("div");
        label.className = "label";
        label.textContent = field.label ?? "";
        const column = document.createElement("span");
        column.className = "column";
        column.textContent = field.column ?? "";
        label.append(column);
        const value = document.createElement("div");
        value.className = "value";
        if (field.column === "color" && field.display.startsWith("#")) {
          const wrap = document.createElement("span");
          wrap.className = "color-value";
          const swatch = document.createElement("span");
          swatch.className = "swatch";
          swatch.style.background = field.display;
          wrap.append(swatch, document.createTextNode(field.display));
          value.append(wrap);
        } else {
          value.textContent = field.display;
        }
        row.append(label, value);
        section.append(row);
      }
      body.append(section);
    }
    el("detail").replaceChildren(body);
  }
  function markerSection(track) {
    const section = document.createElement("section");
    section.className = "group";
    const heading = document.createElement("h3");
    heading.textContent = t("markers.heading");
    section.append(heading);
    const note = document.createElement("p");
    note.className = "detail-kicker";
    if (track.markers_unavailable) note.textContent = t("markers.unavailable");
    else if (!track.markers_found) note.textContent = t("markers.none");
    else note.textContent = t("markers.readOnly");
    section.append(note);
    const ms = (value) => {
      const total = Number(value) / 1e3;
      const minutes = Math.floor(total / 60);
      return `${minutes}:${(total - minutes * 60).toFixed(3).padStart(6, "0")}`;
    };
    const beatSeconds = (value) => {
      if (value === "" || value == null) return "";
      const number = Number(value);
      if (!Number.isFinite(number)) return "";
      return `${number.toFixed(3)}s`;
    };
    for (const cue of track.cues || []) {
      const row = document.createElement("div");
      row.className = "marker";
      const swatch = document.createElement("span");
      swatch.className = "swatch";
      if (cue.color) swatch.style.background = cue.color;
      const time = document.createElement("span");
      time.textContent = ms(cue.start_ms);
      const name = document.createElement("span");
      name.textContent = cue.name || t("markers.cue", { number: cue.index + 1 });
      row.append(swatch, time, name);
      section.append(row);
    }
    for (const loop of track.loops || []) {
      const row = document.createElement("div");
      row.className = "marker";
      const swatch = document.createElement("span");
      swatch.className = "swatch";
      if (loop.color) swatch.style.background = loop.color;
      const time = document.createElement("span");
      time.textContent = `${ms(loop.start_ms)}–${ms(loop.end_ms)}`;
      const name = document.createElement("span");
      name.textContent = loop.name || t(loop.locked ? "markers.loopLocked" : "markers.loop", { number: loop.index + 1 });
      row.append(swatch, time, name);
      section.append(row);
    }
    for (const flip of track.flips || []) {
      const row = document.createElement("div");
      row.className = "marker";
      const time = document.createElement("span");
      time.textContent = flip.enabled ? t("common.on") : t("common.off");
      const name = document.createElement("span");
      name.textContent = flip.name || t("markers.flip", { number: flip.index + 1 });
      row.append(document.createElement("span"), time, name);
      section.append(row);
    }
    for (const mark of track.beatgrid || []) {
      const row = document.createElement("div");
      row.className = "marker";
      const time = document.createElement("span");
      time.textContent = beatSeconds(mark.position);
      const name = document.createElement("span");
      const bpmNumber = Number(mark.bpm);
      if (mark.bpm != null && mark.bpm !== "" && Number.isFinite(bpmNumber)) {
        name.textContent = t("markers.bpm", { bpm: formatNumber(bpmNumber, { maximumFractionDigits: 20 }) });
      } else if (mark.beats != null) {
        name.textContent = t("markers.beats", { count: Number(mark.beats) });
      } else {
        name.textContent = "";
      }
      row.append(document.createElement("span"), time, name);
      section.append(row);
    }
    return section;
  }
  function copySection(copies) {
    const section = document.createElement("section");
    section.className = "group";
    const heading = document.createElement("h3");
    heading.textContent = t("copies.heading");
    section.append(heading);
    for (const copy of copies) {
      const row = document.createElement("div");
      row.className = "copy-row";
      const button2 = buttonEl(openCopy(copy.file || `Track ${copy.id}`));
      button2.className = "text-button";
      button2.textContent = copy.file || t("track.numbered", { id: String(copy.id) });
      button2.addEventListener("click", () => selectTrack(copy.id));
      const rate = document.createElement("span");
      rate.textContent = copy.bitrate == null ? "" : String(copy.bitrate);
      const plays = document.createElement("span");
      plays.textContent = copy.play_count == null ? "" : String(copy.play_count);
      const crates = document.createElement("span");
      crates.textContent = copy.missing ? "missing" : copy.crates || "";
      row.append(button2, rate, plays, crates);
      section.append(row);
    }
    return section;
  }
  function relatedSection(track, writable) {
    const section = document.createElement("section");
    section.className = "group";
    section.dataset.trackId = String(track.id);
    const heading = document.createElement("h3");
    heading.id = `related-heading-${track.id}`;
    heading.textContent = t("related.heading");
    section.setAttribute("aria-labelledby", heading.id);
    section.setAttribute("aria-busy", "true");
    const status = document.createElement("p");
    status.className = "detail-kicker";
    status.setAttribute("role", "status");
    const path = track.resolved_path || track.edit?.portable_id || "";
    status.textContent = path ? t("related.loading") : t("related.noPath");
    section.append(heading, status);
    if (path) loadRelated(track, section, writable, "");
    return section;
  }
  async function loadRelated(track, section, writable, query) {
    const token = ++relatedRequest;
    const path = track.resolved_path || track.edit?.portable_id || "";
    const params = new URLSearchParams({ path, space: state.space });
    try {
      const response = await fetch(`/api/related?${params}`);
      const payload = await readJSONOr(response, {});
      if (token !== relatedRequest || !section.isConnected) return;
      if (!response.ok) throw new Error(serverMessage(payload, t("related.loadFailed")));
      renderRelated(track, section, writable, payload, query);
    } catch (error2) {
      if (token !== relatedRequest || !section.isConnected) return;
      section.setAttribute("aria-busy", "false");
      const status = section.querySelector("[role=status]");
      if (status) status.textContent = failureOf(error2).message;
    }
  }
  function renderRelated(track, section, writable, payload, query) {
    const heading = section.querySelector("h3");
    section.replaceChildren(heading);
    section.setAttribute("aria-busy", "false");
    const saved = Array.isArray(payload.saved) ? payload.saved : [];
    const suggested = Array.isArray(payload.suggested) ? payload.suggested : [];
    const status = document.createElement("p");
    status.className = "detail-kicker";
    status.setAttribute("role", "status");
    status.textContent = saved.length ? t("related.savedCount", { count: saved.length }) : t("related.noneSaved");
    section.append(status);
    if (saved.length) section.append(relatedSavedList(track, section, saved));
    section.append(relatedSearch(track, section, query));
    const suggestHeading = document.createElement("p");
    suggestHeading.className = "detail-kicker";
    suggestHeading.textContent = suggested.length ? t("related.suggested") : t("related.noSuggestions");
    section.append(suggestHeading);
    if (suggested.length) section.append(relatedSuggestList(track, section, suggested));
    const crate = buttonEl(tips.updateRelated);
    crate.className = "text-button";
    crate.dataset.relatedCrate = "true";
    const crateName = payload.crate_name || "Related";
    crate.textContent = t("related.updateCrate");
    crate.disabled = !writable;
    crate.addEventListener("click", () => refreshRelatedCrate(track, section));
    const crateNote = document.createElement("p");
    crateNote.className = "detail-kicker";
    crateNote.textContent = writable ? t("related.crateNote", { name: crateName }) : t("related.quitSerato");
    section.append(crate, crateNote);
  }
  function relatedSavedList(track, section, saved) {
    const list = document.createElement("ul");
    list.className = "related-list";
    for (const link of saved) {
      const item = document.createElement("li");
      item.className = "related-row";
      const main = document.createElement("div");
      const other = link.track || {};
      const label = other.title || t("track.untitled");
      if (other.asset_id != null && other.in_library) {
        const open = buttonEl(openRelated(label));
        open.className = "text-button";
        open.textContent = label;
        open.addEventListener("click", () => selectTrack(other.asset_id));
        main.append(open);
      } else {
        const name = document.createElement("span");
        name.textContent = label;
        main.append(name);
      }
      const meta = document.createElement("p");
      meta.className = "related-meta";
      const bits = [];
      if (other.artist) bits.push(other.artist);
      if (other.key) bits.push(other.key);
      if (other.bpm != null && other.bpm !== "") bits.push(t("markers.bpm", { bpm: String(other.bpm) }));
      bits.push(link.mutual ? t("related.twoWay") : t("related.oneWay"));
      if (link.rating != null) bits.push(t("related.ratingOutOf", { rating: String(link.rating) }));
      if (!other.in_library) bits.push(t("related.notInLibrary"));
      meta.textContent = bits.join(" · ");
      main.append(meta);
      if (link.note) {
        const note = document.createElement("p");
        note.className = "related-note";
        note.textContent = link.note;
        main.append(note);
      }
      const remove = buttonEl(removeRelatedTip(label));
      remove.className = "text-button";
      remove.textContent = t("common.remove");
      remove.setAttribute("aria-label", t("related.removeLink", { name: label }));
      remove.addEventListener("click", () => removeRelated(track, section, link));
      item.append(main, remove);
      list.append(item);
    }
    return list;
  }
  function relatedSearch(track, section, query) {
    const block = document.createElement("div");
    block.className = "related-search";
    const label = document.createElement("label");
    label.append(document.createTextNode(t("related.find")));
    const input = inputEl(tips.findRelated);
    input.type = "search";
    input.autocomplete = "off";
    input.placeholder = t("related.findPlaceholder");
    input.value = query || "";
    label.append(input);
    const results = document.createElement("ul");
    results.className = "related-results";
    const form = document.createElement("div");
    form.className = "related-form";
    form.hidden = true;
    block.append(label, results, form);
    const paint3 = () => {
      results.replaceChildren();
      form.hidden = true;
      form.replaceChildren();
      const terms = input.value.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
      if (!terms.length) {
        const hint = document.createElement("li");
        hint.className = "related-meta";
        hint.textContent = t("related.typeHint");
        results.append(hint);
        return;
      }
      const hits2 = state.tracks.filter((item) => item.id !== track.id && matchesQuery(item, terms)).slice(0, 8);
      if (!hits2.length) {
        const empty = document.createElement("li");
        empty.className = "related-meta";
        empty.textContent = t("list.noMatches");
        results.append(empty);
        return;
      }
      for (const hit of hits2) {
        const item = document.createElement("li");
        const name = hit.artist ? `${hit.name || t("track.untitled")} · ${hit.artist}` : hit.name || t("track.untitled");
        const choose = buttonEl(chooseRelated(name));
        choose.className = "text-button";
        choose.textContent = hit.artist ? `${hit.name || t("track.untitled")} · ${hit.artist}` : hit.name || t("track.untitled");
        choose.addEventListener("click", () => relatedLinkForm(track, section, form, hit, input.value));
        item.append(choose);
        results.append(item);
      }
    };
    input.addEventListener("input", paint3);
    paint3();
    return block;
  }
  function relatedLinkForm(track, section, form, hit, query) {
    form.hidden = false;
    form.replaceChildren();
    const chosen = document.createElement("p");
    chosen.className = "related-meta";
    chosen.textContent = hit.artist ? `${hit.name || t("track.untitled")} · ${hit.artist}` : hit.name || t("track.untitled");
    const noteLabel = document.createElement("label");
    noteLabel.append(document.createTextNode(t("related.note")));
    const note = inputEl(tips.linkNote);
    note.type = "text";
    note.maxLength = 500;
    note.placeholder = t("related.notePlaceholder");
    noteLabel.append(note);
    const ratingLabel = document.createElement("label");
    ratingLabel.append(document.createTextNode(t("related.linkRating")));
    const rating = selectEl(tips.linkRating);
    for (const [value, text] of [["", t("rating.none")], ["1", "1"], ["2", "2"], ["3", "3"], ["4", "4"], ["5", "5"]]) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = text;
      rating.append(option);
    }
    ratingLabel.append(rating);
    const mutualLabel = document.createElement("label");
    mutualLabel.className = "check";
    const mutual = inputEl(tips.linkMutual);
    mutual.type = "checkbox";
    mutual.checked = true;
    mutualLabel.append(mutual, document.createTextNode(t("related.twoWayLink")));
    const save2 = buttonEl(tips.saveLink);
    save2.className = "text-button";
    save2.textContent = t("related.saveLink");
    save2.addEventListener("click", () => {
      save2.disabled = true;
      saveRelated(track, section, {
        action: "add",
        asset: track.id,
        target: hit.id,
        mutual: mutual.checked,
        note: note.value,
        rating: rating.value === "" ? null : Number(rating.value),
        space: state.space
      }, query);
    });
    form.append(chosen, noteLabel, ratingLabel, mutualLabel, save2);
  }
  function relatedSuggestList(track, section, suggested) {
    const list = document.createElement("ul");
    list.className = "related-list";
    for (const item of suggested) {
      const row = document.createElement("li");
      row.className = "related-row";
      const main = document.createElement("div");
      const name = document.createElement("span");
      name.textContent = item.artist ? `${item.title || t("track.untitled")} · ${item.artist}` : item.title || t("track.untitled");
      const reasons = document.createElement("p");
      reasons.className = "related-meta";
      reasons.textContent = Array.isArray(item.reasons) ? item.reasons.join(" · ") : "";
      main.append(name, reasons);
      const save2 = buttonEl(saveSuggestion(item.title || "Untitled"));
      save2.className = "text-button";
      save2.textContent = t("common.save");
      save2.setAttribute("aria-label", t("related.saveLinkTo", { name: item.title || t("track.untitled") }));
      save2.addEventListener("click", () => {
        save2.disabled = true;
        saveRelated(track, section, {
          action: "add",
          asset: track.id,
          target: item.asset_id,
          mutual: true,
          note: "",
          rating: null,
          space: state.space
        }, "");
      });
      row.append(main, save2);
      list.append(row);
    }
    return list;
  }
  async function saveRelated(track, section, body, query) {
    try {
      await postJSON("/api/related", body);
      setNotice(t("related.saved"));
      const kept = section.querySelector(".related-search input");
      await loadRelated(track, section, Boolean(track.serato?.writable && state.writable), kept ? kept.value : query);
    } catch (error2) {
      if (failureOf(error2).status === 409) lockDown(error2);
      else setNotice(failureOf(error2).message);
      const status = section.querySelector("[role=status]");
      if (status) status.textContent = failureOf(error2).message;
    }
  }
  async function removeRelated(track, section, link) {
    const label = link.track?.title || t("related.thisTrack");
    if (!confirm(t("related.confirmRemove", { name: label }))) return;
    try {
      await postJSON("/api/related", { action: "remove", id: link.id });
      setNotice(t("related.removed"));
      const kept = section.querySelector(".related-search input");
      await loadRelated(track, section, Boolean(track.serato?.writable && state.writable), kept ? kept.value : "");
    } catch (error2) {
      setNotice(failureOf(error2).message);
    }
  }
  async function refreshRelatedCrate(track, section) {
    const button2 = section.querySelector("[data-related-crate]");
    if (button2) button2.disabled = true;
    try {
      const result = await postJSON("/api/related", { action: "crate", asset: track.id, space: state.space });
      setNotice(result.warning || t("related.crateUpdated", { name: String(result.name ?? "") }));
      await loadLibrary();
      selectTrack(track.id);
    } catch (error2) {
      if (failureOf(error2).status === 409) {
        lockDown(error2);
        if (button2) button2.disabled = true;
      } else {
        setNotice(failureOf(error2).message);
        if (button2) button2.disabled = !state.writable;
      }
    }
  }
  function membershipSection(track, writable) {
    const section = document.createElement("section");
    section.className = "group";
    const heading = document.createElement("h3");
    heading.textContent = t("crates.heading");
    section.append(heading);
    const holder = document.createElement("div");
    holder.className = "member-list";
    const chosen = new Set(track.crate_ids || []);
    const crates = [...state.crates].filter((crate) => !crate.smart).sort((a, b) => a.name.localeCompare(b.name));
    for (const crate of crates) {
      const label = document.createElement("label");
      label.className = "member";
      const input = inputEl(membershipTip(crate.name));
      input.type = "checkbox";
      input.checked = chosen.has(crate.id);
      input.disabled = !writable;
      input.addEventListener("change", () => setMembership(track.id, crate.id, input.checked, input));
      const name = document.createElement("span");
      name.textContent = crate.name;
      label.append(input, name);
      holder.append(label);
    }
    const smart = state.crates.filter((crate) => crate.smart && chosen.has(crate.id));
    if (smart.length) {
      const line = document.createElement("p");
      line.className = "detail-kicker";
      line.textContent = t("crates.smartList", { names: smart.map((crate) => crate.name).join(", ") });
      section.append(line);
    }
    section.append(holder);
    return section;
  }
  function repaintViews() {
    if (state.serato) el("status").textContent = statusLine(state.serato);
    renderList();
    if (state.mode === "history") {
      renderSessions();
      if (state.selectedId != null) selectEntry(state.selectedId);
      return;
    }
    const detail = lastDetail;
    if (detail && detail.id === state.selectedId && el("detail").querySelector(".detail-body")) renderDetail(detail);
  }
  function setNotice(text) {
    el("notice").textContent = text || "";
    el("notice").hidden = !text;
  }
  function statusLine(info) {
    if (info?.code) return codedText(info.message || t("status.library"), info.code, messageParams(info.params));
    return info?.message || t("status.library");
  }
  function applyStatus(info) {
    state.serato = info;
    state.writable = Boolean(info?.writable);
    el("status").textContent = statusLine(info);
    renderShell();
  }
  function lockDown(error2) {
    const failed = failureOf(error2);
    applyStatus(failed.payload?.serato || { writable: false, message: failed.message });
    setNotice(failed.message);
  }
  async function saveTrack(id, form) {
    const data = new FormData(form);
    const bpm = data.get("bpm");
    const fields = {
      name: data.get("name") ?? "",
      artist: data.get("artist") ?? "",
      album: data.get("album") ?? "",
      genre: data.get("genre") ?? "",
      year: data.get("year") ?? "",
      composer: data.get("composer") ?? "",
      remixer: data.get("remixer") ?? "",
      label: data.get("label") ?? "",
      grouping: data.get("grouping") ?? "",
      comments: data.get("comments") ?? "",
      key: data.get("key") ?? "",
      emoji: data.get("emoji") ?? "",
      bpm: bpm === "" ? null : Number(bpm),
      color: Number(data.get("color")),
      rating: data.get("rating") === "" ? null : Number(data.get("rating")),
      is_beatgrid_locked: form.querySelector("[name=is_beatgrid_locked]").checked
    };
    if (bpm !== "" && Number.isNaN(fields.bpm)) {
      setNotice(t("detail.bpmNumber"));
      return;
    }
    try {
      const result = await postJSON("/api/track", { id, space: state.space, fields });
      setNotice(result.warning || t("common.saved"));
      await loadLibrary();
      selectTrack(id);
    } catch (error2) {
      if (failureOf(error2).status === 409) lockDown(error2);
      else setNotice(failureOf(error2).message);
    }
  }
  async function revealTrack(id) {
    try {
      await postJSON("/api/reveal", { id });
    } catch (error2) {
      setNotice(failureOf(error2).message);
    }
  }
  async function prepareTrack(id, add) {
    try {
      const result = await postJSON("/api/crate", { action: "prepare", asset: id, add, space: state.space });
      setNotice(result.warning || (add ? t("detail.sentPrepare") : t("detail.removedPrepare")));
      await loadLibrary();
      selectTrack(id);
    } catch (error2) {
      if (failureOf(error2).status === 409) lockDown(error2);
      else setNotice(failureOf(error2).message);
    }
  }
  async function relocateTrack(track) {
    const path = prompt(t("detail.relocatePrompt"), track.resolved_path || track.edit?.portable_id || "");
    if (!path) return;
    try {
      const result = await postJSON("/api/track", {
        id: track.id,
        space: state.space,
        fields: { portable_id: path }
      });
      setNotice(result.warning || t("detail.relocated"));
      await loadLibrary();
      selectTrack(track.id);
    } catch (error2) {
      if (failureOf(error2).status === 409) lockDown(error2);
      else setNotice(failureOf(error2).message);
    }
  }
  async function removeTrack(id) {
    if (!confirm(t("detail.confirmRemove"))) return;
    try {
      const result = await postJSON("/api/crate", { action: "remove_library", asset: id, space: state.space });
      setNotice(result.warning || t("detail.removed"));
      state.selectedId = null;
      await loadLibrary();
    } catch (error2) {
      if (failureOf(error2).status === 409) lockDown(error2);
      else setNotice(failureOf(error2).message);
    }
  }
  async function setMembership(assetId, crateId, add, input) {
    try {
      const result = await postJSON("/api/crate", {
        action: add ? "add" : "remove",
        id: crateId,
        asset: assetId,
        space: state.space
      });
      if (result.warning) setNotice(result.warning);
      await loadLibrary();
      selectTrack(assetId);
    } catch (error2) {
      input.checked = !add;
      if (failureOf(error2).status === 409) lockDown(error2);
      else setNotice(failureOf(error2).message);
    }
  }
  async function saveRules(id, text) {
    let rules;
    try {
      rules = JSON.parse(text);
    } catch {
      setNotice(t("error.smart_rules_json"));
      return;
    }
    try {
      const result = await postJSON("/api/crate", { action: "rules", id, rules, space: state.space });
      setNotice(result.warning || t("rules.saved"));
      await loadLibrary();
      selectCrate(id);
    } catch (error2) {
      if (failureOf(error2).status === 409) lockDown(error2);
      else setNotice(failureOf(error2).message);
    }
  }
  async function createCrate() {
    const name = prompt(t("crates.newPrompt"));
    if (!name || !name.trim()) return;
    const parent = state.activeCrate === "all" ? state.rootId : state.activeCrate;
    try {
      const result = await postJSON("/api/crate", { action: "create", name: name.trim(), parent, space: state.space });
      setNotice(result.warning || t("crates.created"));
      await loadLibrary();
      selectCrate(result.id);
    } catch (error2) {
      if (failureOf(error2).status === 409) lockDown(error2);
      else setNotice(failureOf(error2).message);
    }
  }
  async function renameCrate() {
    const crate = state.crates.find((item) => item.id === state.activeCrate);
    if (!crate) return;
    const name = prompt(t("crates.renamePrompt"), crate.name);
    if (!name || !name.trim() || name.trim() === crate.name) return;
    try {
      const result = await postJSON("/api/crate", { action: "rename", id: crate.id, name: name.trim(), space: state.space });
      setNotice(result.warning || t("crates.renamed"));
      await loadLibrary();
      selectCrate(crate.id);
    } catch (error2) {
      if (failureOf(error2).status === 409) lockDown(error2);
      else setNotice(failureOf(error2).message);
    }
  }
  function colorFromName(choice) {
    const wanted = choice.trim().toLocaleLowerCase();
    const english = COLOR_NAMES[wanted];
    if (english != null) return english;
    return COLORS.find(([, key]) => t(key).toLocaleLowerCase() === wanted)?.[0];
  }
  async function colorCrate() {
    const crate = state.crates.find((item) => item.id === state.activeCrate);
    if (!crate) return;
    const names = COLORS.map(([, key]) => t(key).toLocaleLowerCase());
    const choice = prompt(t("crates.colorPrompt", { names: names.join(", ") }));
    if (choice == null) return;
    const color = colorFromName(choice);
    if (color == null) {
      setNotice(t("crates.colorUnknown"));
      return;
    }
    try {
      const result = await postJSON("/api/crate", {
        action: "color",
        id: crate.id,
        color: color === 16777215 ? null : color,
        space: state.space
      });
      setNotice(result.warning || t("crates.colorSaved"));
      await loadLibrary();
    } catch (error2) {
      if (failureOf(error2).status === 409) lockDown(error2);
      else setNotice(failureOf(error2).message);
    }
  }
  async function deleteCrate() {
    const crate = state.crates.find((item) => item.id === state.activeCrate);
    if (!crate) return;
    if (!confirm(t("crates.confirmDelete", { name: crate.name }))) return;
    try {
      const result = await postJSON("/api/crate", { action: "delete", id: crate.id, space: state.space });
      state.activeCrate = "all";
      setNotice(result.warning || t("crates.deleted"));
      await loadLibrary();
    } catch (error2) {
      if (failureOf(error2).status === 409) lockDown(error2);
      else setNotice(failureOf(error2).message);
    }
  }
  async function importPlaylist(file) {
    const text = await file.text();
    const name = file.name.replace(/\.m3u8?$/i, "") || t("import.defaultName");
    const parent = state.activeCrate === "all" ? state.rootId : state.activeCrate;
    try {
      const result = await postJSON("/api/import.m3u", { space: state.space, parent, name, text });
      const missed = result.unmatched_count ? ` ${t("import.unmatched", { count: Number(result.unmatched_count) })}` : "";
      setNotice(`${t("import.added", { count: Number(result.added) || 0 })}${missed}${result.warning ? ` ${result.warning}` : ""}`);
      await loadLibrary();
      selectCrate(result.id);
    } catch (error2) {
      if (failureOf(error2).status === 409) lockDown(error2);
      else setNotice(failureOf(error2).message);
    }
  }
  function renderSessions() {
    el("session-list").replaceChildren();
    for (const session of state.historySessions) {
      const button2 = buttonEl(sessionTip(session.name || "Session"));
      button2.className = "crate";
      button2.setAttribute("role", "option");
      button2.setAttribute("aria-selected", String(session.id === state.historyId));
      const name = document.createElement("span");
      name.className = "name";
      name.textContent = session.name || t("history.session");
      const meta = document.createElement("span");
      meta.className = "meta";
      meta.textContent = String(session.played || 0);
      button2.append(name, meta);
      button2.addEventListener("click", () => openSession(session.id));
      el("session-list").append(button2);
    }
  }
  async function loadHistory() {
    const response = await fetch("/api/history");
    const payload = await readJSONOr(response, {});
    if (!response.ok) throw new Error(serverMessage(payload, t("history.readFailed")));
    state.historySessions = payload.sessions || [];
    renderSessions();
  }
  async function openSession(id) {
    state.historyId = id;
    state.selectedId = null;
    renderSessions();
    const response = await fetch(`/api/history?session=${id}`);
    const payload = await readJSONOr(response, {});
    if (!response.ok) {
      setNotice(serverMessage(payload, t("history.sessionFailed")));
      return;
    }
    state.entries = payload.entries || [];
    el("list").scrollTop = 0;
    renderList();
  }
  async function loadDuplicates() {
    state.duplicateIds = null;
    state.duplicateGroups = [];
    const response = await fetch(`/api/duplicates?space=${encodeURIComponent(state.space)}`);
    const payload = await readJSONOr(response, {});
    if (!response.ok) throw new Error(serverMessage(payload, t("duplicates.readFailed")));
    const ids = /* @__PURE__ */ new Set();
    state.duplicateGroups = payload.groups || [];
    for (const group of state.duplicateGroups) for (const id of group.ids || []) ids.add(id);
    state.duplicateIds = ids;
    state.duplicateSpace = state.space;
    if (state.mode === "duplicates") renderList();
  }
  async function openInLibrary(assetId) {
    state.space = "Serato Library";
    el("space").value = state.space;
    state.mode = "crates";
    state.activeCrate = "all";
    state.selectedId = assetId;
    await loadLibrary();
    selectTrack(assetId);
  }
  async function loadLibrary() {
    el("count").textContent = t("library.loading");
    const response = await fetch(`/api/library?space=${encodeURIComponent(state.space)}`);
    const library = await readJSONOr(response, {});
    if (!response.ok) throw new Error(serverMessage(library, t("library.readFailed", { status: String(response.status) })));
    const selected = state.selectedId;
    const active2 = state.activeCrate;
    state.tracks = library.tracks;
    state.byId = new Map(library.tracks.map((track) => [track.id, track]));
    state.crates = library.crates;
    state.rootId = library.root_id;
    state.crateTracks = new Map(library.crates.map((crate) => [crate.id, new Set(crate.tracks)]));
    state.expanded = new Set(library.crates.filter((crate) => crate.expanded).map((crate) => crate.id));
    state.activeCrate = active2 === "all" || library.crates.some((crate) => crate.id === active2) ? active2 : "all";
    state.selectedId = selected;
    if (state.duplicateSpace !== state.space) {
      state.duplicateIds = null;
      state.duplicateGroups = [];
    }
    applyStatus(library.serato);
    renderList();
  }
  function setMode(mode) {
    state.mode = mode;
    el("list").scrollTop = 0;
    if (mode === "history") {
      state.sort = "start";
      state.sortDir = -1;
      if (!state.historySessions.length) loadHistory().catch((error2) => setNotice(failureOf(error2).message));
    } else if (state.sort === "start" || state.sort === "deck" || state.sort === "played") {
      state.sort = "name";
      state.sortDir = 1;
    }
    if (mode === "duplicates" && state.duplicateSpace !== state.space) {
      loadDuplicates().catch((error2) => setNotice(failureOf(error2).message));
    }
    if (mode === "files") {
      state.filesLoading = true;
      const path = state.filesAtRoots ? "" : state.filesPath || "";
      loadFolder(path, { elsewhere: state.filesElsewhere && !state.filesAtRoots }).catch((error2) => failFiles(error2));
    }
    if (mode === "snapshots") {
      loadSnapshots().catch((error2) => failSnapshots(error2));
    }
    renderList();
  }
  function showFailure(error2) {
    el("count").textContent = t("library.unavailable");
    const failure = document.createElement("p");
    failure.className = "detail-error";
    failure.textContent = failureOf(error2).message;
    el("detail").replaceChildren(failure);
  }
  function selectedDuplicateGroup() {
    if (state.mode !== "duplicates" || state.selectedId == null) return null;
    return (state.duplicateGroups || []).find((group) => (group.ids || []).includes(state.selectedId)) || null;
  }
  function syncMergeButton() {
    const wrap = el("duplicate-actions");
    const button2 = el("merge-duplicates");
    if (!wrap || !button2) return;
    const show2 = state.mode === "duplicates";
    wrap.hidden = !show2;
    button2.disabled = !show2 || !state.writable || !selectedDuplicateGroup();
  }
  function crateNamesFor(assetId) {
    return state.crates.filter((crate) => !crate.smart && (crate.tracks || []).includes(assetId)).map((crate) => crate.name);
  }
  function failFiles(error2) {
    state.filesLoading = false;
    state.filesError = failureOf(error2).message || t("error.folder_unreadable");
    renderFiles();
  }
  var filesRequest = 0;
  var FILES_SEARCH_MS = 200;
  var filesSearchTimer = 0;
  var FILE_OVERSCAN = 8;
  async function loadFolder(path, options = {}) {
    window.clearTimeout(filesSearchTimer);
    state.filesQuery = "";
    state.filesSearching = false;
    const searchField = document.getElementById("files-search");
    if (searchField instanceof HTMLInputElement) searchField.value = "";
    const elsewhere = options.elsewhere === true;
    const refresh = options.refresh === true;
    const atRoots = path === "" && !elsewhere;
    const token = ++filesRequest;
    state.filesLoading = true;
    state.filesError = "";
    if (!options.keepMessage) state.filesMessage = "";
    state.filesSelected = /* @__PURE__ */ new Set();
    state.filesActive = 0;
    state.filesAtRoots = atRoots;
    state.filesElsewhere = elsewhere;
    if (atRoots) {
      state.filesPath = "";
      state.filesParent = null;
      state.filesEntries = [];
      state.filesBreadcrumb = [];
      state.filesRoot = null;
    }
    renderFiles();
    if (refresh || atRoots) {
      const rootsPayload = await fetchLibraryRoots(refresh);
      if (token !== filesRequest) return;
      state.filesRoots = rootsPayload.roots.filter(isLibraryRoot);
    }
    if (atRoots) {
      state.filesPath = "";
      state.filesParent = null;
      state.filesEntries = [];
      state.filesBreadcrumb = [];
      state.filesRoot = null;
      state.filesElsewhere = false;
      state.filesAtRoots = true;
      state.filesTruncated = false;
      state.filesLoading = false;
      el("files-list").scrollTop = 0;
      renderFiles();
      return;
    }
    const params = new URLSearchParams();
    if (path) params.set("path", path);
    if (elsewhere) params.set("elsewhere", "1");
    const query = params.size ? `?${params.toString()}` : "";
    const response = await fetch(`/api/files${query}`);
    const payload = await readJSONOr(response, {});
    if (token !== filesRequest) return;
    if (!response.ok) throw new Error(serverMessage(payload, t("error.folder_unreadable")));
    state.filesPath = payload.path || "";
    state.filesParent = typeof payload.parent === "string" && payload.parent ? payload.parent : null;
    state.filesEntries = Array.isArray(payload.entries) ? payload.entries : [];
    state.filesRoot = isFileRoot(payload.root) ? payload.root : null;
    state.filesBreadcrumb = Array.isArray(payload.breadcrumb) ? payload.breadcrumb.filter(isFileCrumb) : [];
    state.filesElsewhere = Boolean(payload.elsewhere);
    state.filesAtRoots = !state.filesPath && !state.filesElsewhere;
    state.filesTruncated = Boolean(payload.truncated);
    state.filesLoading = false;
    el("files-list").scrollTop = 0;
    if (payload.serato) applyStatus(payload.serato);
    renderFiles();
  }
  async function searchFiles(query) {
    const token = ++filesRequest;
    const scope = state.filesAtRoots ? "" : state.filesPath;
    const elsewhere = state.filesElsewhere && !state.filesAtRoots;
    state.filesLoading = true;
    state.filesError = "";
    state.filesSearching = true;
    state.filesQuery = query;
    renderFiles();
    const params = new URLSearchParams();
    params.set("q", query);
    if (scope) params.set("path", scope);
    if (elsewhere) params.set("elsewhere", "1");
    const response = await fetch(`/api/files?${params.toString()}`);
    const payload = await readJSONOr(response, {});
    if (token !== filesRequest) return;
    if (!response.ok) throw new Error(payload.error || "Files could not be searched.");
    const entries = Array.isArray(payload.entries) ? payload.entries.filter(isListedFile) : [];
    state.filesEntries = entries;
    state.filesTruncated = Boolean(payload.truncated);
    state.filesLoading = false;
    state.filesSearching = true;
    state.filesActive = 0;
    state.filesSelected = /* @__PURE__ */ new Set();
    el("files-list").scrollTop = 0;
    renderFiles();
  }
  function isListedFile(value) {
    if (!value || typeof value !== "object") return false;
    const row = value;
    return typeof row.name === "string" && typeof row.path === "string" && typeof row.kind === "string";
  }
  function renderFiles() {
    if (state.mode !== "files") return;
    const pick2 = el("files-pick");
    const moveHere = el("files-move-here");
    const pickCancel = el("files-pick-cancel");
    pick2.hidden = !state.filesPick;
    moveHere.hidden = !state.filesPick;
    pickCancel.hidden = !state.filesPick;
    renderBreadcrumb();
    const elsewhere = el("files-elsewhere");
    elsewhere.textContent = state.filesElsewhere ? t("files.roots") : t("files.browseElsewhere");
    setTooltip(elsewhere, state.filesElsewhere ? tips.filesMusicFolders : tips.filesElsewhere);
    el("files-up").disabled = !state.filesParent || state.filesLoading;
    const notes = [];
    if (state.filesLoading) notes.push(state.filesAtRoots ? t("files.readingRootsNote") : t("files.readingFolderNote"));
    if (state.filesError) notes.push(state.filesError);
    if (state.filesMessage) notes.push(state.filesMessage);
    if (state.filesTruncated) notes.push(state.filesSearching ? t("files.searchTruncated") : t("files.truncated"));
    el("files-status").textContent = notes.join(" ");
    const scroll = el("files-list").scrollTop;
    paintFileWindow();
    if (el("files-list").scrollTop !== scroll) el("files-list").scrollTop = scroll;
    const selected = selectedFiles();
    const locked = !state.writable || state.filesLoading || state.filesAtRoots;
    el("files-rename").disabled = locked || selected.length !== 1;
    el("files-move").disabled = locked || !selected.length || Boolean(state.filesPick);
    el("files-move-folder").disabled = locked || !state.filesPath || Boolean(state.filesPick);
    el("files-replace").disabled = locked || selected.length !== 1;
    el("files-delete").disabled = locked || !selected.length;
    moveHere.disabled = locked;
    renderShell();
  }
  function renderBreadcrumb() {
    const nav = el("files-path");
    nav.replaceChildren();
    const list = document.createElement("ol");
    list.className = "files-crumbs";
    const crumbs = visibleCrumbs();
    crumbs.forEach((crumb, index) => {
      const item = document.createElement("li");
      const last = index === crumbs.length - 1;
      if (!last && crumb.path) {
        const button2 = buttonEl(openCrumb(crumb.name));
        button2.className = "files-crumb";
        button2.textContent = crumb.name;
        button2.addEventListener("click", () => {
          loadFolder(crumb.path, { elsewhere: state.filesElsewhere }).catch((error2) => failFiles(error2));
        });
        item.append(button2);
      } else {
        const current2 = document.createElement("span");
        current2.className = "files-crumb";
        current2.setAttribute("aria-current", "page");
        current2.textContent = crumb.name;
        item.append(current2);
      }
      if (!last) {
        const sep = document.createElement("span");
        sep.className = "files-sep";
        sep.setAttribute("aria-hidden", "true");
        sep.textContent = "/";
        item.append(sep);
      }
      list.append(item);
    });
    nav.append(list);
  }
  function visibleCrumbs() {
    if (state.filesBreadcrumb.length) return state.filesBreadcrumb;
    if (state.filesAtRoots) return [{ name: t("files.roots"), path: "" }];
    if (state.filesPath) return [{ name: state.filesPath, path: state.filesPath }];
    return [{ name: t("files.roots"), path: "" }];
  }
  function filesRowHeight() {
    if (state.filesSearching) return FILE_ROW;
    return state.filesAtRoots ? ROOT_ROW : FILE_ROW;
  }
  function browserRows() {
    if (state.filesSearching) return state.filesEntries;
    if (state.filesAtRoots) {
      return state.filesRoots.map((root) => {
        const entry = {
          name: root.label,
          path: root.path,
          detail: root.detail,
          kind: root.kind === "serato_drive" ? "drive" : "folder",
          missing: root.missing
        };
        return entry;
      });
    }
    const rank = { dir: 0, file: 1, link: 2 };
    return [...state.filesEntries].sort((left, right) => {
      return (rank[left.kind] ?? 3) - (rank[right.kind] ?? 3) || left.name.localeCompare(right.name, void 0, { numeric: true, sensitivity: "base" });
    });
  }
  function paintFileWindow() {
    const list = el("files-list");
    const rows2 = browserRows();
    list.setAttribute("aria-busy", String(state.filesLoading));
    list.setAttribute(
      "aria-label",
      state.filesSearching ? t("files.searchResults") : state.filesAtRoots ? t("files.roots") : t("files.contents")
    );
    if (state.filesLoading && !rows2.length) {
      const reading = state.filesSearching ? t("files.searching") : state.filesAtRoots ? t("files.readingRootsNote") : t("files.readingFolderNote");
      list.replaceChildren(fileNote(reading));
      list.tabIndex = 0;
      return;
    }
    if (state.filesError && !rows2.length) {
      list.replaceChildren(fileNote(state.filesError));
      list.tabIndex = 0;
      return;
    }
    if (state.filesAtRoots && !state.filesRoots.length) {
      list.replaceChildren(rootsEmpty());
      list.tabIndex = -1;
      return;
    }
    if (!rows2.length) {
      const empty = state.filesSearching ? t("files.noMatches", { query: state.filesQuery }) : t("files.empty");
      list.replaceChildren(fileNote(empty));
      list.tabIndex = 0;
      return;
    }
    list.tabIndex = -1;
    if (state.filesActive >= rows2.length) state.filesActive = rows2.length - 1;
    if (state.filesActive < 0) state.filesActive = 0;
    const rowHeight = filesRowHeight();
    const view = list.clientHeight || 600;
    const maxScroll = Math.max(0, rows2.length * rowHeight - view);
    const scrollTop = Math.min(Math.max(0, list.scrollTop), maxScroll);
    const start = Math.max(0, Math.floor(scrollTop / rowHeight) - FILE_OVERSCAN);
    const end = Math.min(rows2.length, Math.ceil((scrollTop + view) / rowHeight) + FILE_OVERSCAN);
    const spacer2 = fileSpacer(list);
    const windowEl = spacer2.querySelector(".files-window");
    if (!windowEl) return;
    spacer2.style.height = `${rows2.length * rowHeight}px`;
    windowEl.style.transform = `translateY(${start * rowHeight}px)`;
    windowEl.replaceChildren();
    for (let index = start; index < end; index += 1) {
      const entry = rows2[index];
      if (entry) windowEl.append(fileRow(entry, index));
    }
    if (state.filesActive >= start && state.filesActive < end) {
      list.setAttribute("aria-activedescendant", `files-item-${state.filesActive}`);
    } else list.removeAttribute("aria-activedescendant");
  }
  function fileSpacer(list) {
    const first = list.firstElementChild;
    if (first instanceof HTMLDivElement && first.classList.contains("files-spacer") && list.childElementCount === 1) {
      return first;
    }
    list.replaceChildren();
    const spacer2 = document.createElement("div");
    spacer2.className = "files-spacer";
    const windowEl = document.createElement("div");
    windowEl.className = "files-window";
    spacer2.append(windowEl);
    list.append(spacer2);
    return spacer2;
  }
  function fileNote(text) {
    const note = document.createElement("p");
    note.className = "files-empty";
    note.textContent = text;
    return note;
  }
  function rootsEmpty() {
    const box = document.createElement("div");
    box.className = "files-empty-state";
    const heading = document.createElement("h2");
    heading.textContent = t("files.noRoots");
    const copy = document.createElement("p");
    copy.textContent = t("files.noRootsBody");
    const button2 = buttonEl(tips.runSetup);
    button2.id = "files-run-setup";
    button2.className = "files-primary";
    button2.textContent = t("files.runSetup");
    button2.addEventListener("click", () => bridge.openSetup());
    box.append(heading, copy, button2);
    return box;
  }
  function focusFilesIndex(index) {
    const rows2 = browserRows();
    if (!rows2.length) return;
    state.filesActive = Math.max(0, Math.min(rows2.length - 1, index));
    const list = el("files-list");
    const rowHeight = filesRowHeight();
    const view = list.clientHeight || 600;
    const top = state.filesActive * rowHeight;
    const maxScroll = Math.max(0, rows2.length * rowHeight - view);
    if (top < list.scrollTop) list.scrollTop = top;
    if (top + rowHeight > list.scrollTop + view) list.scrollTop = Math.min(maxScroll, top + rowHeight - view);
    paintFileWindow();
    const control = list.querySelector(`[data-files-index="${state.filesActive}"]`);
    control?.focus();
  }
  function activateFilesIndex(index) {
    const entry = browserRows()[index];
    if (!entry) return;
    if (entry.kind === "file") {
      if (state.filesSelected.has(entry.path)) state.filesSelected.delete(entry.path);
      else state.filesSelected.add(entry.path);
      renderFiles();
      focusFilesIndex(index);
      return;
    }
    if (entry.kind === "link") return;
    openBrowserRow(entry);
  }
  function openBrowserRow(entry) {
    if (entry.missing) return;
    const elsewhere = state.filesElsewhere && entry.kind === "dir";
    loadFolder(entry.path, { elsewhere }).catch((error2) => failFiles(error2));
  }
  function onFilesKey(event) {
    if (state.mode !== "files") return;
    const list = el("files-list");
    if (!(event.target instanceof Node) || !list.contains(event.target)) return;
    const rows2 = browserRows();
    if (!rows2.length) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp" || event.key === "Home" || event.key === "End") {
      event.preventDefault();
      if (event.key === "ArrowDown") focusFilesIndex(state.filesActive + 1);
      else if (event.key === "ArrowUp") focusFilesIndex(state.filesActive - 1);
      else if (event.key === "Home") focusFilesIndex(0);
      else focusFilesIndex(rows2.length - 1);
      return;
    }
    if (event.key !== "Enter" && event.key !== " ") return;
    const control = event.target instanceof HTMLElement ? event.target.closest("button, input") : null;
    if (control && list.contains(control)) return;
    event.preventDefault();
    activateFilesIndex(state.filesActive);
  }
  function fileRow(entry, index) {
    const row = document.createElement("div");
    row.className = "files-row";
    if (entry.detail && (entry.kind === "folder" || entry.kind === "drive")) row.classList.add("is-root");
    if (entry.missing) row.classList.add("is-missing");
    if (index === state.filesActive) row.classList.add("is-active");
    row.setAttribute("role", "listitem");
    const openKind = entry.kind === "dir" || entry.kind === "folder" || entry.kind === "drive";
    if (openKind) {
      const button2 = buttonEl(entry.missing ? missingDrive(entry.name) : openFile(entry.name));
      button2.className = "files-open";
      button2.dataset.filesIndex = String(index);
      button2.id = `files-item-${index}`;
      button2.tabIndex = index === state.filesActive ? 0 : -1;
      if (entry.kind === "drive" || entry.kind === "folder") button2.append(fileIcon(entry.kind === "drive" ? "drive" : "folder"));
      if (entry.detail && (entry.kind === "folder" || entry.kind === "drive")) {
        const copy = document.createElement("span");
        copy.className = "files-root-copy";
        const label2 = document.createElement("span");
        label2.className = "files-root-label";
        label2.textContent = entry.name;
        const detail = document.createElement("span");
        detail.className = "files-root-detail";
        detail.textContent = entry.detail;
        copy.append(label2, detail);
        button2.append(copy);
      } else {
        const name2 = document.createElement("span");
        name2.textContent = entry.name;
        button2.append(name2);
        if (entry.detail) {
          const detail = document.createElement("span");
          detail.className = "files-match-detail";
          detail.textContent = entry.detail;
          button2.append(detail);
        }
      }
      if (entry.missing) {
        button2.setAttribute("aria-disabled", "true");
        button2.setAttribute("aria-label", t("files.driveMissingLabel", { name: entry.name }));
        const badge = document.createElement("span");
        badge.className = "files-badge";
        badge.textContent = t("files.driveMissing");
        button2.append(badge);
        button2.addEventListener("click", () => {
          state.filesActive = index;
        });
      } else {
        button2.setAttribute("aria-label", t("files.open", { name: entry.name }));
        button2.addEventListener("click", () => {
          state.filesActive = index;
          openBrowserRow(entry);
        });
      }
      row.append(button2);
      return row;
    }
    if (entry.kind !== "file") {
      const label2 = buttonEl(fileShortcut(entry.name));
      label2.className = "files-kind";
      label2.dataset.filesIndex = String(index);
      label2.id = `files-item-${index}`;
      label2.tabIndex = index === state.filesActive ? 0 : -1;
      label2.textContent = t("files.shortcut", { name: entry.name });
      label2.setAttribute("aria-label", t("files.shortcut", { name: entry.name }));
      row.append(label2);
      return row;
    }
    const label = document.createElement("label");
    label.className = "files-file";
    const box = inputEl(selectFile(entry.name, entry.path));
    box.type = "checkbox";
    box.dataset.filesIndex = String(index);
    box.id = `files-item-${index}`;
    box.tabIndex = index === state.filesActive ? 0 : -1;
    box.checked = state.filesSelected.has(entry.path);
    box.setAttribute("aria-label", entry.name);
    box.addEventListener("change", () => {
      state.filesActive = index;
      if (box.checked) state.filesSelected.add(entry.path);
      else state.filesSelected.delete(entry.path);
      renderFiles();
    });
    const name = document.createElement("span");
    name.className = "files-name";
    name.textContent = entry.name;
    label.append(box, name);
    if (entry.detail) {
      const detail = document.createElement("span");
      detail.className = "files-match-detail";
      detail.textContent = entry.detail;
      label.append(detail);
    }
    if (entry.in_library) {
      const badge = document.createElement("span");
      badge.className = "files-badge";
      badge.textContent = t("files.inLibrary");
      label.append(badge);
    }
    row.append(label);
    return row;
  }
  function fileIcon(kind) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("width", "20");
    svg.setAttribute("height", "20");
    svg.setAttribute("aria-hidden", "true");
    svg.classList.add("files-icon", kind === "drive" ? "files-icon-drive" : "files-icon-folder");
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("fill", "none");
    path.setAttribute("stroke", "currentColor");
    path.setAttribute("stroke-width", "1.5");
    path.setAttribute("stroke-linejoin", "round");
    path.setAttribute(
      "d",
      kind === "drive" ? "M5 8.5h14v8H5z M8 14.5h.01 M12 14.5h4" : "M4 8.5h6l2 2h8v7.5H4z"
    );
    svg.append(path);
    return svg;
  }
  function isFileRoot(value) {
    if (!value || typeof value !== "object") return false;
    const record = value;
    return typeof record.name === "string" && typeof record.path === "string" && typeof record.kind === "string";
  }
  function isFileCrumb(value) {
    if (!value || typeof value !== "object") return false;
    const record = value;
    return typeof record.name === "string" && typeof record.path === "string";
  }
  function moveFileList(delta) {
    if (!browserRows().length) return;
    focusFilesIndex(state.filesActive + delta);
  }
  function openFileList() {
    if (!browserRows().length) return;
    activateFilesIndex(state.filesActive);
  }
  function focusFileByPath(path) {
    const index = browserRows().findIndex((entry) => entry.path === path);
    if (index < 0) return;
    focusFilesIndex(index);
  }
  function selectedFiles() {
    return state.filesEntries.filter((entry) => entry.kind === "file" && state.filesSelected.has(entry.path));
  }
  function wireLibrary() {
    el("files-list").addEventListener("scroll", () => {
      if (state.mode === "files") paintFileWindow();
    });
    el("files-list").addEventListener("keydown", onFilesKey);
    el("files-search").addEventListener("input", () => {
      window.clearTimeout(filesSearchTimer);
      const value = el("files-search").value;
      state.filesQuery = value;
      if (!value.trim()) {
        if (state.filesAtRoots && !state.filesPath) {
          state.filesSearching = false;
          state.filesEntries = [];
          state.filesError = "";
          state.filesTruncated = false;
          state.filesLoading = false;
          renderFiles();
          return;
        }
        loadFolder(state.filesPath, { elsewhere: state.filesElsewhere && Boolean(state.filesPath) }).catch((error2) => failFiles(error2));
        return;
      }
      filesSearchTimer = window.setTimeout(() => {
        searchFiles(value.trim()).catch((error2) => failFiles(error2));
      }, FILES_SEARCH_MS);
    });
    el("search").addEventListener("input", () => {
      state.query = el("search").value;
      el("list").scrollTop = 0;
      renderList();
    });
    el("crate-search").addEventListener("input", (event) => {
      state.crateQuery = event.target.value;
      renderCrates();
    });
    el("reload").addEventListener("click", () => {
      const jobs = [loadLibrary()];
      if (state.mode === "history") jobs.push(loadHistory());
      if (state.mode === "duplicates") jobs.push(loadDuplicates());
      Promise.all(jobs).catch(showFailure);
    });
    el("export-m3u").addEventListener("click", () => {
      const crate = state.mode === "crates" ? state.activeCrate : "all";
      const link = document.createElement("a");
      link.href = `/api/export.m3u?space=${encodeURIComponent(state.space)}&crate=${encodeURIComponent(crate)}`;
      link.download = "crate.m3u";
      link.click();
    });
    el("import-m3u").addEventListener("click", () => {
      if (!state.writable) {
        setNotice(el("status").textContent);
        return;
      }
      el("import-file").click();
    });
    el("import-file").addEventListener("change", (event) => {
      const file = event.target.files?.[0];
      event.target.value = "";
      if (file) importPlaylist(file).catch((error2) => setNotice(failureOf(error2).message));
    });
    el("space").addEventListener("change", () => {
      state.space = el("space").value;
      state.activeCrate = "all";
      state.selectedId = null;
      state.duplicateIds = null;
      state.duplicateGroups = [];
      loadLibrary().then(() => {
        if (state.mode === "duplicates") return loadDuplicates();
        return null;
      }).catch(showFailure);
    });
    el("views").addEventListener("click", (event) => {
      const button2 = event.target.closest("button");
      if (button2?.dataset.view) setMode(button2.dataset.view);
    });
    document.querySelector(".sort-crates").addEventListener("click", (event) => {
      const button2 = event.target.closest("button");
      if (!button2?.dataset.crateSort) return;
      state.crateSort = button2.dataset.crateSort;
      renderCrates();
      renderShell();
    });
    el("crate-new").addEventListener("click", () => createCrate().catch((error2) => setNotice(failureOf(error2).message)));
    el("crate-rename").addEventListener("click", () => renameCrate().catch((error2) => setNotice(failureOf(error2).message)));
    el("crate-color").addEventListener("click", () => colorCrate().catch((error2) => setNotice(failureOf(error2).message)));
    el("crate-delete").addEventListener("click", () => deleteCrate().catch((error2) => setNotice(failureOf(error2).message)));
    document.querySelector(".columns").addEventListener("click", (event) => {
      const button2 = event.target.closest("button");
      if (!button2?.dataset.sort) return;
      const key = button2.dataset.sort;
      if (state.sort === key) state.sortDir *= -1;
      else {
        state.sort = key;
        state.sortDir = key === "bpm" || key === "length_ms" || key === "start" ? -1 : 1;
      }
      renderColumns();
      renderList();
    });
    el("crate-list").addEventListener("keydown", (event) => {
      const item = event.target.closest(".crate");
      if (!item || !el("crate-list").contains(item)) return;
      const items = [...el("crate-list").querySelectorAll(".crate")];
      const index = items.indexOf(item);
      const id = item.dataset.id === "all" ? "all" : Number(item.dataset.id);
      if (event.key === "ArrowDown") {
        event.preventDefault();
        focusCrateItem(items[Math.min(items.length - 1, index + 1)]);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        focusCrateItem(items[Math.max(0, index - 1)]);
      } else if (event.key === "Home") {
        event.preventDefault();
        focusCrateItem(items[0]);
      } else if (event.key === "End") {
        event.preventDefault();
        focusCrateItem(items[items.length - 1]);
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        if (!state.crateQuery && item.getAttribute("aria-expanded") === "false") toggleCrate(id);
        else if (item.getAttribute("aria-expanded") === "true") focusCrateItem(items[index + 1]);
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        if (!state.crateQuery && item.getAttribute("aria-expanded") === "true") toggleCrate(id);
        else if (item.dataset.parent) {
          focusCrateItem(items.find((button2) => button2.dataset.id === item.dataset.parent));
        }
      } else if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        selectCrate(id);
      }
    });
  }
  bridge.selectTrack = selectTrack;
  bridge.selectEntry = selectEntry;

  // src/layout.ts
  var TRACK_LIST_MIN_WIDTH = 360;
  var DETAIL_MIN_WIDTH = 300;
  var SAVE_DELAY_MS = 400;
  var splitter = null;
  var changedHere = false;
  var saveTimer;
  function save(width) {
    changedHere = true;
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
      postJSON("/api/settings", { layout: { track_list_width: width } }).catch(() => {
        setNotice(t("layout.widthNotSaved"));
      });
    }, SAVE_DELAY_MS);
  }
  function wireLayout() {
    splitter = mountSplitter({
      handle: el("track-splitter"),
      container: el("browser").parentElement,
      first: el("browser"),
      property: "--track-list-width",
      minFirst: TRACK_LIST_MIN_WIDTH,
      minSecond: DETAIL_MIN_WIDTH,
      onCommit: save
    });
    window.addEventListener("resize", () => splitter?.refit());
  }
  function applyLayout(payload) {
    if (!splitter || changedHere) return;
    const width = payload.layout?.track_list_width;
    splitter.set(typeof width === "number" ? width : null);
  }

  // src/dialogs.ts
  var rekordboxXml = "";
  var mergePreview = null;
  var mergeToken = 0;
  var mergeLoading = false;
  var consentSettled = false;
  var privacySync = false;
  var filesPreview = null;
  var filesAction = "";
  var filesTrigger = null;
  function rekordboxExportUrl(report) {
    const crate = state.mode === "crates" ? state.activeCrate : "all";
    const memory = el("rekordbox-memory").checked ? "1" : "0";
    const hotLoops = el("rekordbox-hot-loops").checked ? "1" : "0";
    const key = el("rekordbox-key").value;
    const base = `/api/export.rekordbox.xml?space=${encodeURIComponent(state.space)}&crate=${encodeURIComponent(crate)}&memory=${memory}&hot_loops=${hotLoops}&key=${encodeURIComponent(key)}`;
    return report ? `${base}&report=1` : base;
  }
  var rekordboxToken = 0;
  function applyRekordboxExport(payload) {
    const section = payload.rekordbox;
    if (section == null) return;
    if (typeof section.hot_loops === "boolean") {
      el("rekordbox-hot-loops").checked = section.hot_loops;
    }
    if (typeof section.memory_cues === "boolean") {
      el("rekordbox-memory").checked = section.memory_cues;
    }
    if (section.key_notation === "asis" || section.key_notation === "camelot" || section.key_notation === "classical") {
      el("rekordbox-key").value = section.key_notation;
    }
  }
  async function saveRekordboxExport() {
    const key = el("rekordbox-key").value;
    const notation = key === "camelot" || key === "classical" ? key : "asis";
    const token = ++rekordboxToken;
    try {
      const payload = await postJSON("/api/settings", {
        rekordbox: {
          hot_loops: el("rekordbox-hot-loops").checked,
          memory_cues: el("rekordbox-memory").checked,
          key_notation: notation
        }
      });
      if (token === rekordboxToken) applyRekordboxExport(payload);
    } catch {
    }
  }
  function fillRekordboxReport(lines) {
    const list = el("rekordbox-report");
    list.replaceChildren();
    for (const line of lines) {
      const item = document.createElement("li");
      item.textContent = line;
      list.append(item);
    }
  }
  function selectedMergeKeepId() {
    const checked = el("merge-choices").querySelector("input:checked");
    if (checked) return Number(checked.value);
    return state.selectedId;
  }
  function previewFieldValue(field, value) {
    if (value == null || value === "") return "empty";
    if (field === "time_added") {
      const date = new Date(Number(value) * 1e3);
      if (!Number.isNaN(date.getTime())) {
        return date.toLocaleString(void 0, {
          month: "short",
          day: "numeric",
          year: "numeric",
          hour: "numeric",
          minute: "2-digit",
          second: "2-digit"
        });
      }
    }
    return String(value);
  }
  function renderMergePreview(preview) {
    el("merge-preview").replaceChildren();
    if (!preview) {
      const pending = document.createElement("p");
      pending.textContent = t("merge.readingPreview");
      el("merge-preview").append(pending);
      return;
    }
    const list = document.createElement("ul");
    list.className = "merge-preview";
    const added = preview.crates_added || [];
    const item = (text) => {
      const line = document.createElement("li");
      line.textContent = text;
      list.append(line);
    };
    if (added.length) {
      const names = added.map((crate) => crate.space && crate.space !== state.space ? `${crate.name} (${crate.space})` : crate.name);
      item(t("merge.addToCrates", { crates: names.join(", ") }));
    } else if ((preview.crates_kept || []).length) {
      item(t("merge.alreadyInCrates"));
    } else {
      item(t("merge.noCrates"));
    }
    for (const space of preview.spaces_added || []) item(t("merge.addToSpace", { space }));
    if ((preview.fields || []).length) {
      for (const field of preview.fields || []) {
        const before = previewFieldValue(field.field || "", field.before);
        const after = previewFieldValue(field.field || "", field.after);
        item(t("merge.fieldChange", { label: field.label ?? "", before, after }));
      }
    } else {
      item(t("merge.noFields"));
    }
    if (preview.history_repointed) {
      const count = Number(preview.history_entries) || 0;
      item(count ? t("merge.repointHistory", { count }) : t("merge.noHistory"));
    } else {
      item(t("merge.noHistoryId"));
    }
    const removed = (preview.removed || []).length;
    item(t("merge.removeCopies", { count: removed }));
    for (const file of preview.files || []) {
      if (file.reason) item(`${file.file}: ${file.reason}`);
    }
    el("merge-preview").append(list);
    if (preview.cue_warning) {
      const warning = document.createElement("p");
      warning.className = "merge-warning";
      warning.textContent = preview.cue_warning;
      el("merge-preview").append(warning);
    }
    const files = document.createElement("p");
    files.id = "merge-file-note";
    files.className = "dialog-note";
    el("merge-preview").append(files);
  }
  function syncTrashChoice() {
    const files = mergePreview?.files || [];
    const trashable = files.filter((file) => file.on_disk && !file.blocks_trash);
    const blocked = files.some((file) => file.blocks_trash);
    el("merge-trash").disabled = !mergePreview || mergeLoading || blocked || trashable.length === 0;
    if (el("merge-trash").disabled) el("merge-trash").checked = false;
    const danger = el("merge-trash").checked;
    el("merge-confirm").classList.toggle("danger", danger);
    el("merge-confirm").textContent = mergeLoading ? t("merge.merging") : danger ? t("merge.confirmTrash") : t("merge.title");
    setTooltip(
      el("merge-confirm"),
      mergeLoading ? tips.merging : danger ? tips.mergeConfirmTrash : tips.mergeConfirm
    );
    el("merge-confirm").disabled = mergeLoading || !mergePreview || mergePreview.writable === false;
    const note = el("merge-file-note");
    if (!note) return;
    if (danger) note.textContent = t("merge.trashFiles", { files: trashable.map((file) => file.file).join(", ") });
    else note.textContent = t("merge.filesStay");
  }
  async function refreshMergePreview() {
    const keepId = selectedMergeKeepId();
    const token = ++mergeToken;
    mergeLoading = false;
    mergePreview = null;
    el("merge-status").textContent = "";
    renderMergePreview(null);
    syncTrashChoice();
    el("merge-confirm").disabled = true;
    try {
      const preview = await postJSON("/api/duplicates/merge", {
        space: state.space,
        keep_id: keepId,
        preview: true
      });
      if (token !== mergeToken) return;
      mergePreview = preview;
      renderMergePreview(preview);
      if (preview.writable === false) {
        el("merge-status").textContent = t("merge.quitSerato");
      }
      syncTrashChoice();
    } catch (error2) {
      if (token !== mergeToken) return;
      mergePreview = null;
      el("merge-preview").replaceChildren();
      const failed = document.createElement("p");
      failed.textContent = t("merge.previewFailed");
      el("merge-preview").append(failed);
      el("merge-status").textContent = failureOf(error2).message;
      syncTrashChoice();
    }
  }
  function renderMergeChoices() {
    const group = selectedDuplicateGroup();
    el("merge-choices").replaceChildren();
    if (!group) return;
    for (const id of group.ids || []) {
      const track = state.byId.get(id) || { id, file: "", play_count: null, missing: false };
      const label = document.createElement("label");
      label.className = "merge-choice";
      label.htmlFor = `merge-keep-${id}`;
      const input = inputEl(keepCopy(track.file || `Track ${id}`));
      input.type = "radio";
      input.name = "merge-keep";
      input.id = `merge-keep-${id}`;
      input.value = String(id);
      input.checked = id === state.selectedId;
      input.addEventListener("change", () => {
        if (input.checked) refreshMergePreview().catch((error2) => setNotice(failureOf(error2).message));
      });
      const text = document.createElement("span");
      const name = document.createElement("span");
      name.textContent = track.file || t("track.numbered", { id: String(id) });
      const meta = document.createElement("span");
      meta.className = "merge-meta";
      const parts = [];
      if (track.play_count != null) parts.push(t("merge.plays", { count: Number(track.play_count) }));
      const crates = crateNamesFor(id);
      if (crates.length) parts.push(crates.join(", "));
      if (track.missing) parts.push(t("track.missingBadge"));
      meta.textContent = parts.join(" · ");
      text.append(name, meta);
      label.append(input, text);
      el("merge-choices").append(label);
    }
  }
  async function openMergeDialog() {
    if (!selectedDuplicateGroup() || !state.writable) return;
    if (typeof el("merge-dialog").showModal !== "function") return;
    el("merge-trash").checked = false;
    el("merge-status").textContent = "";
    renderMergeChoices();
    if (!el("merge-dialog").open) el("merge-dialog").showModal();
    el("merge-cancel").focus();
    await refreshMergePreview();
  }
  async function confirmMerge() {
    const keepId = selectedMergeKeepId();
    if (keepId == null || mergeLoading) return;
    const trash = el("merge-trash").checked;
    mergeLoading = true;
    syncTrashChoice();
    el("merge-status").textContent = "";
    try {
      const result = await postJSON("/api/duplicates/merge", {
        space: state.space,
        keep_id: keepId,
        confirm: true,
        delete_files: trash,
        confirm_delete_files: trash
      });
      el("merge-dialog").close();
      const count = (result.removed || []).length;
      const name = result.kept?.file || t("merge.keptCopy");
      let message = t("merge.merged", { count, name });
      if (result.warning) message = `${message} ${result.warning}`;
      if (result.cue_warning) message = `${message} ${result.cue_warning}`;
      setNotice(message);
      state.selectedId = keepId;
      await loadLibrary();
      if (state.mode === "duplicates") await loadDuplicates();
      if (state.byId.has(keepId)) selectTrack(keepId);
    } catch (error2) {
      el("merge-status").textContent = failureOf(error2).message;
      if (failureOf(error2).status === 409) {
        lockDown(error2);
        el("merge-dialog").close();
      }
    } finally {
      mergeLoading = false;
      syncTrashChoice();
    }
  }
  function telemetryNoteText() {
    if (!state.telemetryConfigured) {
      return t("sharing.noKeys");
    }
    if (state.telemetryConsent === true) {
      return t("sharing.canSend");
    }
    return t("sharing.nothingSent");
  }
  function applyLanguage(payload) {
    if (!("language" in payload)) return;
    const saved = isLanguage(payload.language) ? payload.language : null;
    el("language-select").value = saved ?? "";
    if (getLocale() !== PSEUDO) setLocale(resolveLocale(saved, systemLanguages()));
  }
  function systemLanguages() {
    return Array.isArray(navigator.languages) && navigator.languages.length ? [...navigator.languages] : [navigator.language || "en"];
  }
  async function saveLanguage() {
    const value = el("language-select").value;
    const saved = isLanguage(value) ? value : null;
    el("language-status").textContent = "";
    setLocale(resolveLocale(saved, systemLanguages()));
    try {
      await postJSON("/api/settings", { language: saved });
    } catch {
      el("language-status").textContent = t("settings.languageNotSaved");
    }
  }
  function repaintDialogs() {
    el("telemetry-note").textContent = telemetryNoteText();
    if (el("merge-dialog").open) {
      renderMergePreview(mergeLoading ? null : mergePreview);
      syncTrashChoice();
    }
    if (el("files-dialog").open) {
      el("files-confirm").textContent = filesAction === "delete" ? t("files.moveToTrash") : t("common.confirm");
    }
  }
  function applyPrivacy(payload) {
    state.telemetryConsent = payload.telemetry_consent ?? null;
    state.telemetryConfigured = Boolean(payload.telemetry_configured);
    state.wizardComplete = payload.wizard_complete === true;
    privacySync = true;
    el("telemetry-toggle").checked = state.telemetryConsent === true;
    privacySync = false;
    el("telemetry-note").textContent = telemetryNoteText();
  }
  async function saveConsent(value, status) {
    status.textContent = t("wizard.saving");
    try {
      const payload = await postJSON("/api/settings", { telemetry_consent: value });
      applyPrivacy(payload);
      status.textContent = value ? t("sharing.on") : t("sharing.off");
      return true;
    } catch (error2) {
      status.textContent = t("wizard.consentFailed");
      return false;
    }
  }
  function showConsent() {
    if (typeof el("consent-dialog").showModal !== "function") return;
    if (el("consent-dialog").open) return;
    consentSettled = false;
    el("consent-status").textContent = "";
    el("consent-dialog").showModal();
    el("consent-decline").focus();
  }
  function openWizard(force, returnFocus3) {
    const wizard = globalThis.SeratoWizard;
    if (!wizard || typeof wizard.open !== "function") return false;
    const options = {
      force,
      returnFocus: returnFocus3,
      onSettings(payload) {
        applyPrivacy(payload);
      },
      onStatus(info) {
        applyStatus({
          message: info.message,
          writable: info.writable,
          open: info.open
        });
      }
    };
    wizard.open(options);
    return true;
  }
  async function loadPrivacy() {
    const token = rekordboxToken;
    const response = await fetch("/api/settings");
    const payload = await readJSONOr(response, {});
    if (!response.ok) throw new Error(serverMessage(payload, t("sharing.loadFailed")));
    applyPrivacy(payload);
    applyLanguage(payload);
    applyLayout(payload);
    if (token === rekordboxToken) applyRekordboxExport(payload);
    if (!state.wizardComplete && openWizard(false, el("search"))) return;
    if (payload.needs_consent_prompt) showConsent();
  }
  function openFilesDialog(action, trigger) {
    filesAction = action;
    filesPreview = null;
    filesTrigger = trigger instanceof HTMLElement ? trigger : null;
    el("files-name-label").hidden = action !== "rename";
    el("files-replace-label").hidden = action !== "replace";
    el("files-summary").textContent = "";
    el("files-warning").textContent = "";
    el("files-dialog-status").textContent = "";
    el("files-changes").replaceChildren();
    const selected = selectedFiles();
    if (action === "rename" && selected.length === 1) el("files-name").value = selected[0].name;
    if (action === "replace") el("files-replacement").value = "";
    const confirm2 = el("files-confirm");
    confirm2.classList.toggle("danger", action === "delete");
    confirm2.textContent = action === "delete" ? t("files.moveToTrash") : t("common.confirm");
    setTooltip(confirm2, action === "delete" ? tips.filesMoveTrash : tips.filesConfirm);
    syncFilesDialog();
    el("files-dialog").showModal();
    if (action === "delete" || action === "move" || action === "move_folder") {
      el("files-cancel").focus();
      reviewFiles().catch((error2) => {
        el("files-dialog-status").textContent = failureOf(error2).message;
      });
    } else if (action === "rename") el("files-name").focus();
    else el("files-replacement").focus();
  }
  function syncFilesDialog() {
    const confirm2 = el("files-confirm");
    const review = el("files-review");
    const ready = Boolean(filesPreview?.ok && state.writable && filesPreview.needs_confirm);
    confirm2.disabled = !ready;
    review.hidden = filesAction === "delete" || filesAction === "move" || filesAction === "move_folder";
    if (!state.writable) {
      el("files-dialog-status").textContent = el("status").textContent;
    }
  }
  async function reviewFiles() {
    const body = filesBody(false);
    el("files-dialog-status").textContent = t("files.checking");
    const payload = await postJSON("/api/files", body);
    filesPreview = payload;
    el("files-summary").textContent = payload.summary || "";
    el("files-warning").textContent = payload.warning || "";
    el("files-dialog-status").textContent = payload.ok ? "" : serverMessage(payload, t("files.notSaved"));
    const list = el("files-changes");
    list.replaceChildren();
    for (const change of payload.changes || []) {
      const item = document.createElement("li");
      const crates = Array.isArray(change.crates) && change.crates.length ? ` ${t("files.changeCrates", { crates: change.crates.join(", ") })}` : "";
      const effect = change.effect === "trash" ? t("files.trash") : change.to;
      item.textContent = `${change.from} → ${effect}${crates}`;
      list.append(item);
    }
    if (payload.more) {
      const more = document.createElement("li");
      more.textContent = t("files.andMore", { count: Number(payload.more) });
      list.append(more);
    }
    if (payload.serato) applyStatus(payload.serato);
    syncFilesDialog();
  }
  function filesBody(confirm2) {
    const body = { action: filesAction };
    if (confirm2) body.confirm = true;
    if (filesAction === "rename") {
      const selected = selectedFiles();
      body.path = selected[0]?.path || state.filesPickPaths[0];
      body.name = el("files-name").value;
    } else if (filesAction === "move") {
      body.paths = state.filesPickPaths.length ? [...state.filesPickPaths] : selectedFiles().map((entry) => entry.path);
      body.destination = state.filesPath;
    } else if (filesAction === "move_folder") {
      body.path = state.filesPickSource || state.filesPath;
      body.destination = state.filesPath;
    } else if (filesAction === "replace") {
      const selected = selectedFiles();
      body.path = selected[0]?.path || "";
      body.replacement = el("files-replacement").value.trim();
    } else if (filesAction === "delete") {
      body.paths = selectedFiles().map((entry) => entry.path);
    }
    return body;
  }
  function closeFilesDialog() {
    const trigger = filesTrigger;
    filesTrigger = null;
    if (el("files-dialog").open) el("files-dialog").close();
    if (trigger instanceof HTMLElement) trigger.focus();
  }
  async function confirmFiles() {
    if (!filesPreview?.ok || !state.writable) return;
    const confirm2 = el("files-confirm");
    confirm2.disabled = true;
    el("files-dialog-status").textContent = t("files.saving");
    try {
      const payload = await postJSON("/api/files", filesBody(true));
      if (payload.serato) applyStatus(payload.serato);
      closeFilesDialog();
      state.filesPick = null;
      state.filesPickPaths = [];
      state.filesPickSource = "";
      state.filesMessage = payload.summary || t("files.updated");
      if (payload.warning) state.filesMessage = `${state.filesMessage} ${payload.warning}`;
      await loadFolder(payload.browse || state.filesPath || "", { keepMessage: true });
      await loadLibrary();
      state.filesMessage = state.filesMessage;
      renderFiles();
    } catch (error2) {
      if (failureOf(error2).status === 409) lockDown(error2);
      el("files-dialog-status").textContent = failureOf(error2).message;
      confirm2.disabled = false;
    }
  }
  function wireDialogs() {
    const saveExportBar = () => {
      saveRekordboxExport().catch(() => {
      });
    };
    el("rekordbox-hot-loops").addEventListener("change", saveExportBar);
    el("rekordbox-memory").addEventListener("change", saveExportBar);
    el("rekordbox-key").addEventListener("change", saveExportBar);
    loadPrivacy().catch((error2) => {
      setNotice(failureOf(error2).message || t("sharing.loadFailedOff"));
    });
    el("export-rekordbox").addEventListener("click", () => {
      rekordboxXml = "";
      fetch(rekordboxExportUrl(true)).then((response) => response.json().then((body) => ({ ok: response.ok, body }))).then(({ ok, body }) => {
        if (!ok || typeof body.xml !== "string" || !body.xml.startsWith("<?xml")) {
          setNotice(serverMessage(body, t("rekordbox.failed")));
          return;
        }
        rekordboxXml = body.xml;
        fillRekordboxReport(body.report || []);
        el("rekordbox-status").textContent = "";
        el("rekordbox-dialog").showModal();
      }).catch((error2) => setNotice(failureOf(error2).message));
    });
    el("rekordbox-cancel").addEventListener("click", () => {
      rekordboxXml = "";
      el("rekordbox-dialog").close();
    });
    el("rekordbox-download").addEventListener("click", () => {
      if (!rekordboxXml.startsWith("<?xml")) {
        el("rekordbox-status").textContent = t("rekordbox.notXml");
        return;
      }
      const blob = new Blob([rekordboxXml], { type: "application/xml" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "rekordbox.xml";
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1500);
      rekordboxXml = "";
      el("rekordbox-dialog").close();
    });
    el("merge-duplicates").addEventListener("click", () => {
      openMergeDialog().catch((error2) => setNotice(failureOf(error2).message));
    });
    el("merge-cancel").addEventListener("click", () => el("merge-dialog").close());
    el("merge-confirm").addEventListener("click", () => {
      confirmMerge().catch((error2) => setNotice(failureOf(error2).message));
    });
    el("merge-trash").addEventListener("change", () => syncTrashChoice());
    el("consent-decline").addEventListener("click", () => {
      saveConsent(false, el("consent-status")).then((ok) => {
        if (!ok) return;
        consentSettled = true;
        el("consent-dialog").close();
      });
    });
    el("consent-accept").addEventListener("click", () => {
      saveConsent(true, el("consent-status")).then((ok) => {
        if (!ok) return;
        consentSettled = true;
        el("consent-dialog").close();
      });
    });
    el("consent-dialog").addEventListener("close", () => {
      if (consentSettled || state.telemetryConsent !== null) return;
      saveConsent(false, el("consent-status")).then((ok) => {
        if (ok) {
          consentSettled = true;
          return;
        }
        el("consent-dialog").showModal();
      });
    });
    el("open-settings").addEventListener("click", () => {
      el("settings-status").textContent = "";
      el("log-fallback").hidden = true;
      el("telemetry-note").textContent = telemetryNoteText();
      el("settings-dialog").showModal();
    });
    el("language-select").addEventListener("change", () => {
      void saveLanguage();
    });
    el("settings-close").addEventListener("click", () => {
      el("settings-dialog").close();
    });
    el("rerun-wizard").addEventListener("click", () => {
      el("settings-dialog").close();
      openWizard(true, el("open-settings"));
    });
    el("telemetry-toggle").addEventListener("change", () => {
      if (privacySync) return;
      const want = el("telemetry-toggle").checked;
      el("telemetry-toggle").disabled = true;
      saveConsent(want, el("settings-status")).then((ok) => {
        el("telemetry-toggle").disabled = false;
        if (ok) {
          consentSettled = true;
          return;
        }
        privacySync = true;
        el("telemetry-toggle").checked = state.telemetryConsent === true;
        privacySync = false;
      });
    });
    el("open-logs").addEventListener("click", () => {
      const button2 = el("open-logs");
      button2.disabled = true;
      el("settings-status").textContent = t("wizard.opening");
      postJSON("/api/logs/open", {}).then(() => {
        el("settings-status").textContent = t("logs.opened");
      }).catch(() => {
        el("settings-status").textContent = t("logs.openFailed");
      }).finally(() => {
        button2.disabled = false;
      });
    });
    el("copy-logs").addEventListener("click", async () => {
      const button2 = el("copy-logs");
      button2.disabled = true;
      el("settings-status").textContent = t("logs.copying");
      try {
        const response = await fetch("/api/logs");
        const payload = await readJSONOr(response, {});
        if (!response.ok) throw new Error(serverMessage(payload, t("logs.copyFailed")));
        const text = payload.text || "";
        if (!text) {
          el("settings-status").textContent = t("logs.empty");
          return;
        }
        let copied = false;
        if (navigator.clipboard && window.isSecureContext) {
          try {
            await navigator.clipboard.writeText(text);
            copied = true;
          } catch (error2) {
            copied = false;
          }
        }
        if (copied) {
          el("log-fallback").hidden = true;
          el("settings-status").textContent = payload.truncated ? t("logs.copiedTruncated") : t("logs.copied");
          return;
        }
        el("log-fallback").hidden = false;
        el("log-fallback").value = text;
        el("log-fallback").focus();
        el("log-fallback").select();
        el("settings-status").textContent = t("logs.copyManual");
      } catch (error2) {
        el("settings-status").textContent = t("logs.copyFailed");
      } finally {
        button2.disabled = false;
      }
    });
    el("files-up").addEventListener("click", () => {
      if (state.filesParent) {
        loadFolder(state.filesParent, { elsewhere: state.filesElsewhere }).catch((error2) => failFiles(error2));
      }
    });
    el("files-refresh").addEventListener("click", () => {
      const path = state.filesAtRoots ? "" : state.filesPath;
      loadFolder(path, { elsewhere: state.filesElsewhere && !state.filesAtRoots, refresh: true }).catch((error2) => failFiles(error2));
    });
    el("files-elsewhere").addEventListener("click", () => {
      if (state.filesElsewhere) loadFolder("").catch((error2) => failFiles(error2));
      else loadFolder("", { elsewhere: true }).catch((error2) => failFiles(error2));
    });
    el("files-rename").addEventListener("click", (event) => {
      if (selectedFiles().length !== 1) {
        state.filesError = t("files.chooseOneRename");
        renderFiles();
        return;
      }
      openFilesDialog("rename", event.currentTarget);
    });
    el("files-move").addEventListener("click", () => {
      const selected = selectedFiles();
      if (!selected.length) {
        state.filesError = t("files.chooseMove");
        renderFiles();
        return;
      }
      state.filesPick = "move";
      state.filesPickPaths = selected.map((entry) => entry.path);
      state.filesError = "";
      state.filesMessage = t("files.chooseDestination");
      renderFiles();
    });
    el("files-move-folder").addEventListener("click", () => {
      state.filesPick = "move_folder";
      state.filesPickSource = state.filesPath;
      state.filesError = "";
      state.filesMessage = t("files.chooseDestination");
      renderFiles();
    });
    el("files-move-here").addEventListener("click", (event) => {
      openFilesDialog(state.filesPick === "move_folder" ? "move_folder" : "move", event.currentTarget);
    });
    el("files-pick-cancel").addEventListener("click", () => {
      state.filesPick = null;
      state.filesPickPaths = [];
      state.filesPickSource = "";
      state.filesMessage = "";
      renderFiles();
    });
    el("files-replace").addEventListener("click", (event) => {
      if (selectedFiles().length !== 1) {
        state.filesError = t("files.chooseOneReplace");
        renderFiles();
        return;
      }
      openFilesDialog("replace", event.currentTarget);
    });
    el("files-delete").addEventListener("click", (event) => {
      if (!selectedFiles().length) {
        state.filesError = t("files.chooseDelete");
        renderFiles();
        return;
      }
      openFilesDialog("delete", event.currentTarget);
    });
    el("files-review").addEventListener("click", () => {
      reviewFiles().catch((error2) => {
        el("files-dialog-status").textContent = failureOf(error2).message;
      });
    });
    el("files-confirm").addEventListener("click", () => {
      confirmFiles().catch((error2) => {
        el("files-dialog-status").textContent = failureOf(error2).message;
      });
    });
    el("files-cancel").addEventListener("click", () => closeFilesDialog());
    el("files-name").addEventListener("input", () => {
      filesPreview = null;
      syncFilesDialog();
    });
    el("files-replacement").addEventListener("input", () => {
      filesPreview = null;
      syncFilesDialog();
    });
    el("files-dialog").addEventListener("cancel", (event) => {
      event.preventDefault();
      closeFilesDialog();
    });
  }
  bridge.openMergeDialog = openMergeDialog;
  function openSetup() {
    const trigger = document.getElementById("files-run-setup");
    openWizard(true, trigger instanceof HTMLElement ? trigger : el("search"));
  }
  bridge.openSetup = openSetup;

  // src/fuzzy.ts
  var BOUNDARY = /[ ._/\-\\]/;
  function fuzzyScore(needle, haystack) {
    const query = needle.toLocaleLowerCase();
    const text = haystack.toLocaleLowerCase();
    if (!query) return null;
    let score = 0;
    let previous2 = -2;
    let from = 0;
    for (const letter of query) {
      const found = text.indexOf(letter, from);
      if (found < 0) return null;
      score += 8;
      if (found === previous2 + 1) score += 16;
      if (found === 0 || BOUNDARY.test(text.charAt(found - 1))) score += 12;
      previous2 = found;
      from = found + 1;
    }
    if (text.includes(query)) score += 40;
    if (text.startsWith(query)) score += 30;
    score -= Math.floor(Math.max(0, text.length - query.length) / 4);
    return score;
  }
  function scoreQuery(query, name, parentName = "") {
    const terms = query.trim().split(/\s+/).filter(Boolean);
    if (!terms.length) return null;
    let total = 0;
    for (const term of terms) {
      const nameScore = fuzzyScore(term, name);
      if (nameScore != null) {
        total += nameScore + 20;
        continue;
      }
      if (!parentName) return null;
      const parentScore = fuzzyScore(term, parentName);
      if (parentScore == null) return null;
      total += parentScore;
    }
    return total;
  }

  // src/quick-open.ts
  var QUICK_OPEN_MS = 200;
  var LIMIT = 8;
  var returnFocus = null;
  var timer2 = 0;
  var requestToken = 0;
  var hits = [];
  var active = 0;
  var phase = "idle";
  var truncated = false;
  var pendingQuery = "";
  function parentDirectory(path) {
    const slash = Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\"));
    if (slash < 0) return path;
    const parent = path.slice(0, slash);
    if (/^[A-Za-z]:$/.test(parent)) return `${parent}\\`;
    if (parent === "") return path.slice(0, slash + 1);
    return parent;
  }
  function quickOpenIsOpen() {
    return el("quick-open").open;
  }
  function labelQuickOpen() {
    el("quick-open-title").textContent = t("quickOpen.title");
    el("quick-open-label").textContent = t("quickOpen.label");
    el("quick-open-query").placeholder = t("quickOpen.placeholder");
    el("quick-open-close").textContent = t("common.close");
    el("quick-open-retry").textContent = t("common.tryAgain");
    el("quick-open-list").setAttribute("aria-label", t("quickOpen.matches"));
  }
  function repaintQuickOpen() {
    const dialog = document.getElementById("quick-open");
    if (!(dialog instanceof HTMLDialogElement) || !dialog.open) return;
    labelQuickOpen();
    paint();
  }
  function openQuickOpen() {
    const dialog = el("quick-open");
    if (dialog.open) return;
    returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    pendingQuery = "";
    hits = [];
    active = 0;
    phase = "idle";
    truncated = false;
    window.clearTimeout(timer2);
    el("quick-open-query").value = "";
    labelQuickOpen();
    paint();
    dialog.showModal();
    el("quick-open-query").focus();
  }
  function closeQuickOpen() {
    const dialog = el("quick-open");
    if (dialog.open) dialog.close();
  }
  function wireQuickOpen() {
    const dialog = el("quick-open");
    dialog.addEventListener("keydown", onDialogKey);
    dialog.addEventListener("close", () => {
      window.clearTimeout(timer2);
      const node = returnFocus;
      returnFocus = null;
      if (node && node.isConnected) node.focus();
    });
    el("quick-open-query").addEventListener("input", () => schedule2());
    el("quick-open-close").addEventListener("click", () => closeQuickOpen());
    el("quick-open-retry").addEventListener("click", () => {
      const query = el("quick-open-query").value.trim();
      if (query) void loadFiles(query, trackHits(query));
    });
  }
  function onDialogKey(event) {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp" && event.key !== "Enter") return;
    if (!hits.length && event.key !== "Enter") return;
    event.preventDefault();
    if (event.key === "ArrowDown") active = Math.min(hits.length - 1, active + 1);
    else if (event.key === "ArrowUp") active = Math.max(0, active - 1);
    else {
      const chosen = hits[active];
      if (chosen) void activate(chosen);
    }
    if (event.key !== "Enter") paint();
  }
  function schedule2() {
    window.clearTimeout(timer2);
    const query = el("quick-open-query").value;
    pendingQuery = query;
    const tracks = trackHits(query);
    hits = tracks;
    active = 0;
    truncated = false;
    if (!query.trim()) {
      phase = "idle";
      requestToken += 1;
      paint();
      return;
    }
    phase = "loading";
    paint();
    timer2 = window.setTimeout(() => {
      void loadFiles(query.trim(), tracks);
    }, QUICK_OPEN_MS);
  }
  async function loadFiles(query, tracks) {
    const token = ++requestToken;
    phase = "loading";
    try {
      const response = await fetch(`/api/files?q=${encodeURIComponent(query)}`);
      const payload = await readJSONOr(response, {});
      if (token !== requestToken) return;
      if (!response.ok) throw new Error(payload.error || t("quickOpen.fileError"));
      const files = fileHits(payload);
      hits = mergeHits(tracks, files);
      truncated = Boolean(payload.truncated);
      phase = "ready";
      if (active >= hits.length) active = Math.max(0, hits.length - 1);
      paint();
    } catch {
      if (token !== requestToken) return;
      hits = tracks;
      phase = "error";
      paint();
    }
  }
  function trackHits(query) {
    const text = query.trim();
    if (!text) return [];
    const found = [];
    for (const track of state.tracks) {
      const hit = scoreTrack(track, text);
      if (hit) found.push(hit);
    }
    found.sort(byScore);
    return found.slice(0, LIMIT);
  }
  function scoreTrack(track, query) {
    const title2 = track.name || "Untitled";
    const artist2 = track.artist ?? "";
    const album = track.album ?? "";
    const file = track.file ?? "";
    const score = scoreQuery(query, `${title2} ${artist2} ${album} ${file}`);
    if (score == null) return null;
    const detail = [artist2, album].filter((part) => part !== "").join(" · ");
    return { kind: "track", key: `track:${track.id}`, title: title2, detail, score, trackId: track.id };
  }
  function fileHits(payload) {
    const rows2 = Array.isArray(payload.entries) ? payload.entries : [];
    const found = [];
    for (const entry of rows2) {
      if (!isFileEntry(entry)) continue;
      const score = typeof entry.score === "number" ? entry.score : 0;
      found.push({
        kind: "file",
        key: `file:${entry.path}`,
        title: entry.name,
        detail: entry.detail || entry.path,
        score,
        path: entry.path
      });
    }
    found.sort(byScore);
    return found.slice(0, LIMIT);
  }
  function isFileEntry(value) {
    if (!value || typeof value !== "object") return false;
    const row = value;
    return typeof row.name === "string" && typeof row.path === "string" && typeof row.kind === "string";
  }
  function mergeHits(tracks, files) {
    return [...tracks, ...files].sort(byScore).slice(0, LIMIT * 2);
  }
  function byScore(left, right) {
    return right.score - left.score || left.title.localeCompare(right.title);
  }
  async function activate(hit) {
    closeQuickOpen();
    if (hit.kind === "track") {
      if (state.mode === "files" || state.mode === "snapshots" || state.mode === "history") setMode("crates");
      selectCrate("all");
      await selectTrack(hit.trackId);
      const index = state.view.findIndex((row) => row.id === hit.trackId);
      if (index >= 0) el("list").scrollTop = index * ROW;
      return;
    }
    setMode("files");
    await loadFolder(parentDirectory(hit.path));
    focusFileByPath(hit.path);
  }
  function paint() {
    const status = el("quick-open-status");
    const list = el("quick-open-list");
    const retry = el("quick-open-retry");
    const query = pendingQuery.trim();
    retry.hidden = phase !== "error";
    list.replaceChildren();
    if (!query) status.textContent = t("quickOpen.empty");
    else if (phase === "loading") status.textContent = t("quickOpen.searching");
    else if (phase === "error") status.textContent = t("quickOpen.fileError");
    else if (!hits.length) status.textContent = t("quickOpen.none", { query });
    else status.textContent = truncated ? t("quickOpen.truncated") : t("quickOpen.matchCount", { count: hits.length });
    hits.forEach((hit, index) => {
      const item = document.createElement("li");
      const button2 = buttonEl(quickOpenHit(
        hit.kind === "track" ? t("quickOpen.track") : t("quickOpen.file"),
        hit.title,
        hit.detail
      ));
      button2.className = "quick-open-option";
      button2.id = `quick-open-option-${index}`;
      button2.setAttribute("role", "option");
      button2.setAttribute("aria-selected", String(index === active));
      button2.tabIndex = -1;
      if (index === active) button2.classList.add("is-active");
      const kind = document.createElement("span");
      kind.className = "quick-open-kind";
      kind.textContent = hit.kind === "track" ? t("quickOpen.track") : t("quickOpen.file");
      const title2 = document.createElement("span");
      title2.className = "quick-open-name";
      title2.textContent = hit.title;
      const detail = document.createElement("span");
      detail.className = "quick-open-detail";
      detail.textContent = hit.detail;
      button2.append(kind, title2, detail);
      button2.addEventListener("click", () => {
        active = index;
        void activate(hit);
      });
      item.append(button2);
      list.append(item);
    });
    const field = el("quick-open-query");
    const current2 = hits[active];
    if (current2) field.setAttribute("aria-activedescendant", `quick-open-option-${active}`);
    else field.removeAttribute("aria-activedescendant");
    const chosen = list.querySelector(".is-active");
    if (chosen && typeof chosen.scrollIntoView === "function") chosen.scrollIntoView({ block: "nearest" });
  }

  // src/shortcuts.ts
  var SEEK_SECONDS = 5;
  var SHORTCUT_DEFS = [
    {
      id: "focus-search",
      label: "Focus search",
      group: "Find",
      keys: [{ key: "f", mod: true }, { key: "/" }],
      whileTyping: false
    },
    {
      id: "quick-open",
      label: "Find a track or file",
      group: "Find",
      keys: [{ key: "k", mod: true }],
      whileTyping: false
    },
    {
      id: "dismiss",
      label: "Close or clear search",
      group: "Find",
      keys: [{ key: "Escape" }],
      whileTyping: true
    },
    {
      id: "cheat-sheet",
      label: "Show shortcuts",
      group: "Find",
      keys: [{ key: "?" }],
      whileTyping: false
    },
    {
      id: "list-previous",
      label: "Previous row",
      group: "Lists",
      keys: [{ key: "ArrowUp" }],
      whileTyping: false
    },
    {
      id: "list-next",
      label: "Next row",
      group: "Lists",
      keys: [{ key: "ArrowDown" }],
      whileTyping: false
    },
    {
      id: "list-open",
      label: "Open the row",
      group: "Lists",
      keys: [{ key: "Enter" }],
      whileTyping: false
    },
    {
      id: "play-pause",
      label: "Play or pause",
      group: "Play",
      keys: [{ key: " " }],
      whileTyping: false
    },
    {
      id: "seek-back",
      label: "Back 5 seconds",
      group: "Play",
      keys: [{ key: "ArrowLeft" }],
      whileTyping: false
    },
    {
      id: "seek-forward",
      label: "Forward 5 seconds",
      group: "Play",
      keys: [{ key: "ArrowRight" }],
      whileTyping: false
    },
    {
      id: "view-library",
      label: "Library",
      group: "Views",
      keys: [{ key: "1", mod: true }],
      whileTyping: false
    },
    {
      id: "view-crates",
      label: "Crates",
      group: "Views",
      keys: [{ key: "2", mod: true }],
      whileTyping: false
    },
    {
      id: "view-files",
      label: "Files",
      group: "Views",
      keys: [{ key: "3", mod: true }],
      whileTyping: false
    },
    {
      id: "view-history",
      label: "History",
      group: "Views",
      keys: [{ key: "4", mod: true }],
      whileTyping: false
    },
    {
      id: "view-snapshots",
      label: "Snapshots",
      group: "Views",
      keys: [{ key: "5", mod: true }],
      whileTyping: false
    }
  ];
  var SHORTCUTS = SHORTCUT_DEFS;
  var LABEL_KEY = {
    "focus-search": "shortcuts.focusSearch",
    "quick-open": "shortcuts.quickOpen",
    dismiss: "shortcuts.dismiss",
    "cheat-sheet": "shortcuts.cheatSheet",
    "list-previous": "shortcuts.listPrevious",
    "list-next": "shortcuts.listNext",
    "list-open": "shortcuts.listOpen",
    "play-pause": "shortcuts.playPause",
    "seek-back": "shortcuts.seekBack",
    "seek-forward": "shortcuts.seekForward",
    "view-library": "shortcuts.viewLibrary",
    "view-crates": "shortcuts.viewCrates",
    "view-files": "shortcuts.viewFiles",
    "view-history": "shortcuts.viewHistory",
    "view-snapshots": "shortcuts.viewSnapshots"
  };
  var GROUP_KEY = {
    Find: "shortcuts.groupFind",
    Lists: "shortcuts.groupLists",
    Play: "shortcuts.groupPlay",
    Views: "shortcuts.groupViews"
  };
  var player = null;
  var returnFocus2 = null;
  var snapshotCursor = 0;
  function registerPlayerControls(controls) {
    player = controls;
  }
  function chordMatches(chord, event) {
    if (event.altKey) return false;
    const mod = event.ctrlKey || event.metaKey;
    if (mod !== Boolean(chord.mod)) return false;
    if (chord.key === "?") return event.key === "?" && !mod;
    if (event.shiftKey !== Boolean(chord.shift)) return false;
    if (chord.key === " ") return event.key === " ";
    return event.key === chord.key || event.key.toLowerCase() === chord.key.toLowerCase();
  }
  function matchShortcut(event) {
    for (const shortcut of SHORTCUTS) {
      if (shortcut.keys.some((chord) => chordMatches(chord, event))) return shortcut;
    }
    return null;
  }
  function chordLabel(chord) {
    const names = {
      Escape: "Esc",
      " ": "Space",
      ArrowLeft: "Left arrow",
      ArrowRight: "Right arrow",
      ArrowUp: "Up arrow",
      ArrowDown: "Down arrow",
      Enter: "Enter"
    };
    const named = names[chord.key];
    if (named) return named;
    const key = chord.key.length === 1 ? chord.key.toUpperCase() : chord.key;
    return chord.mod ? `Ctrl/Cmd+${key}` : key;
  }
  function isTypingTarget(target) {
    if (!(target instanceof HTMLElement)) return false;
    if (target.isContentEditable) return true;
    const field = target.closest("input, textarea, select");
    if (!(field instanceof HTMLElement)) return false;
    if (field instanceof HTMLInputElement) {
      const inert = /* @__PURE__ */ new Set(["button", "checkbox", "radio", "file", "range", "color", "submit", "reset"]);
      if (inert.has(field.type)) return false;
    }
    return true;
  }
  function openCheatSheet() {
    const dialog = el("shortcuts-dialog");
    if (dialog.open) return;
    rememberFocus();
    renderCheatSheet();
    dialog.showModal();
    el("shortcuts-title").tabIndex = -1;
    el("shortcuts-title").focus();
  }
  function wireShortcuts() {
    document.removeEventListener("keydown", onKey);
    document.addEventListener("keydown", onKey);
    el("open-shortcuts").addEventListener("click", () => openCheatSheet());
    el("shortcuts-close").addEventListener("click", () => el("shortcuts-dialog").close());
    el("shortcuts-dialog").addEventListener("close", () => restoreFocus());
    wireQuickOpen();
  }
  function onKey(event) {
    if (event.isComposing || event.defaultPrevented) return;
    const shortcut = matchShortcut(event);
    if (!shortcut) return;
    if (isTypingTarget(event.target) && !shortcut.whileTyping) return;
    if (shortcut.id !== "dismiss" && topDialog()) return;
    if (skipsListKey(shortcut.id, event.target)) return;
    if (event.repeat && !repeats(shortcut.id)) return;
    runShortcut(shortcut.id, event);
  }
  function repeats(id) {
    return id === "list-previous" || id === "list-next" || id === "seek-back" || id === "seek-forward";
  }
  function skipsListKey(id, target) {
    if (!(target instanceof HTMLElement)) return false;
    if (id === "play-pause" && target.closest("button, a, summary, input, select, textarea, [role='button']")) return true;
    if (id === "list-open" && target.closest("button, a, summary, textarea, select")) return true;
    return false;
  }
  function topDialog() {
    const open = [...document.querySelectorAll("dialog")].filter(
      (node) => node instanceof HTMLDialogElement && node.open
    );
    return open.at(-1) ?? null;
  }
  var HANDLERS = {
    "focus-search": (event) => {
      event.preventDefault();
      focusCurrentSearch();
    },
    "quick-open": (event) => {
      event.preventDefault();
      openQuickOpen();
    },
    dismiss: (event) => {
      dismiss(event);
    },
    "cheat-sheet": (event) => {
      event.preventDefault();
      openCheatSheet();
    },
    "list-previous": (event) => {
      event.preventDefault();
      moveActiveList(-1);
    },
    "list-next": (event) => {
      event.preventDefault();
      moveActiveList(1);
    },
    "list-open": (event) => {
      event.preventDefault();
      openActiveList();
    },
    "play-pause": (event) => {
      if (!player) return;
      event.preventDefault();
      player.togglePlayPause();
    },
    "seek-back": (event) => {
      if (!player) return;
      event.preventDefault();
      player.seekBy(-SEEK_SECONDS);
    },
    "seek-forward": (event) => {
      if (!player) return;
      event.preventDefault();
      player.seekBy(SEEK_SECONDS);
    },
    "view-library": (event) => {
      event.preventDefault();
      showLibrary();
    },
    "view-crates": (event) => {
      event.preventDefault();
      showCrates();
    },
    "view-files": (event) => {
      event.preventDefault();
      setMode("files");
      el("files-list").focus();
    },
    "view-history": (event) => {
      event.preventDefault();
      setMode("history");
      el("list").focus();
    },
    "view-snapshots": (event) => {
      event.preventDefault();
      setMode("snapshots");
      snapshotCursor = 0;
      el("snapshots-list").focus();
    }
  };
  function runShortcut(id, event) {
    const handler = HANDLERS[id];
    handler(event);
  }
  function focusCurrentSearch() {
    if (state.mode === "files") {
      const field2 = el("files-search");
      field2.focus();
      field2.select();
      return;
    }
    if (state.mode === "snapshots") {
      el("snapshots-status").textContent = t("snapshots.noSearch");
      return;
    }
    const field = el("search");
    field.focus();
    field.select();
  }
  function showLibrary() {
    setMode("crates");
    selectCrate("all");
    el("list").focus();
  }
  function showCrates() {
    setMode("crates");
    const first = el("crate-list").querySelector(".crate");
    if (first) focusCrateItem(first);
    else el("crate-list").focus();
  }
  function moveActiveList(delta) {
    if (quickOpenIsOpen()) return;
    if (state.mode === "files") {
      moveFileList(delta);
      return;
    }
    if (state.mode === "snapshots") {
      moveSnapshots(delta);
      return;
    }
    moveTrackList(delta);
  }
  function openActiveList() {
    if (quickOpenIsOpen()) return;
    if (state.mode === "files") {
      openFileList();
      return;
    }
    if (state.mode === "snapshots") {
      openSnapshot();
      return;
    }
    openTrackList();
  }
  function moveSnapshots(delta) {
    const cards = snapshotCards();
    if (!cards.length) return;
    snapshotCursor = Math.max(0, Math.min(cards.length - 1, snapshotCursor + delta));
    const card = cards[snapshotCursor];
    card?.querySelector("button")?.focus();
  }
  function openSnapshot() {
    const cards = snapshotCards();
    const card = cards[snapshotCursor] ?? cards[0];
    card?.querySelector("button")?.click();
  }
  function snapshotCards() {
    return [...el("snapshots-list").querySelectorAll(".snapshot-card")];
  }
  function dismiss(event) {
    const dialog = topDialog();
    if (dialog) {
      if (dialog.id === "quick-open") {
        event.preventDefault();
        closeQuickOpen();
        return;
      }
      if (dialog.id === "shortcuts-dialog") {
        event.preventDefault();
        dialog.close();
        return;
      }
      return;
    }
    const active2 = document.activeElement;
    if (active2 instanceof HTMLInputElement && isSearchField(active2)) {
      event.preventDefault();
      if (active2.value) replaceInput(active2, "");
      else active2.blur();
      return;
    }
    if (isTypingTarget(active2)) {
      if (active2 instanceof HTMLElement) active2.blur();
      return;
    }
    if (clearViewSearch()) event.preventDefault();
  }
  function isSearchField(field) {
    return field.id === "search" || field.id === "crate-search" || field.id === "files-search" || field.id === "quick-open-query";
  }
  function clearViewSearch() {
    if (state.mode === "files" && el("files-search").value) {
      replaceInput(el("files-search"), "");
      return true;
    }
    if (state.mode === "crates" && el("crate-search").value && !el("search").value) {
      replaceInput(el("crate-search"), "");
      return true;
    }
    if (el("search").value) {
      replaceInput(el("search"), "");
      return true;
    }
    if (el("crate-search").value) {
      replaceInput(el("crate-search"), "");
      return true;
    }
    return false;
  }
  function replaceInput(field, value) {
    field.value = value;
    field.dispatchEvent(new Event("input", { bubbles: true }));
  }
  function repaintCheatSheet() {
    const dialog = document.getElementById("shortcuts-dialog");
    if (dialog instanceof HTMLDialogElement && dialog.open) renderCheatSheet();
  }
  function renderCheatSheet() {
    el("shortcuts-title").textContent = t("shortcuts.title");
    el("shortcuts-intro").textContent = t("shortcuts.intro");
    el("shortcuts-close").textContent = t("common.close");
    const body = el("shortcuts-body");
    body.replaceChildren();
    const groups = [];
    for (const shortcut of SHORTCUTS) {
      if (!groups.includes(shortcut.group)) groups.push(shortcut.group);
    }
    for (const group of groups) {
      const heading = document.createElement("h3");
      heading.textContent = t(GROUP_KEY[group]);
      body.append(heading);
      if (group === "Play") {
        const note = document.createElement("p");
        note.className = "dialog-note";
        note.textContent = t("shortcuts.playNote");
        body.append(note);
      }
      const table = document.createElement("table");
      table.className = "shortcut-table";
      const head = document.createElement("thead");
      const headRow = document.createElement("tr");
      const actionHead = document.createElement("th");
      actionHead.scope = "col";
      actionHead.textContent = t("shortcuts.action");
      const keyHead = document.createElement("th");
      keyHead.scope = "col";
      keyHead.textContent = t("shortcuts.key");
      headRow.append(actionHead, keyHead);
      head.append(headRow);
      const rows2 = document.createElement("tbody");
      for (const shortcut of SHORTCUTS) {
        if (shortcut.group !== group) continue;
        const row = document.createElement("tr");
        const action = document.createElement("th");
        action.scope = "row";
        action.textContent = t(LABEL_KEY[shortcut.id]);
        const keys = document.createElement("td");
        shortcut.keys.forEach((chord, index) => {
          if (index > 0) keys.append(document.createTextNode(" or "));
          const kbd = document.createElement("kbd");
          kbd.textContent = chordLabel(chord);
          keys.append(kbd);
        });
        row.append(action, keys);
        rows2.append(row);
      }
      table.append(head, rows2);
      body.append(table);
    }
  }
  function rememberFocus() {
    returnFocus2 = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  }
  function restoreFocus() {
    const node = returnFocus2;
    returnFocus2 = null;
    if (node && node.isConnected) node.focus();
  }

  // src/version.ts
  var copyText = "";
  var painted;
  function versionLabel(info) {
    const version = formatVersion(info.version);
    if (info.source === "release") return version;
    const commit = shortCommit(info.commit);
    if (!commit || version.toLowerCase().includes(commit)) return version;
    return `${version} · ${commit}`;
  }
  function formatVersion(version) {
    const trimmed = version.trim();
    if (/^\d+\.\d+\.\d+/.test(trimmed)) return `v${trimmed}`;
    return trimmed;
  }
  function shortCommit(commit) {
    if (commit === null) return null;
    const trimmed = commit.trim().toLowerCase();
    if (!/^[0-9a-f]{7,40}$/.test(trimmed)) return null;
    return trimmed.slice(0, 7);
  }
  function paint2(label) {
    painted = label;
    const footer = el("app-version");
    const about = el("about-version");
    el("version-copy-status").textContent = "";
    if (!label) {
      copyText = "";
      footer.hidden = true;
      footer.replaceChildren();
      about.textContent = t("version.unavailable");
      return;
    }
    copyText = label;
    footer.hidden = false;
    footer.replaceChildren();
    const name = document.createElement("span");
    name.className = "visually-hidden";
    name.textContent = `${t("version.app")} `;
    const value = document.createElement("span");
    value.textContent = label;
    footer.append(name, value);
    about.textContent = label;
  }
  function repaintVersion() {
    if (painted === void 0) return;
    paint2(painted);
  }
  async function loadVersion() {
    try {
      paint2(versionLabel(await getVersion()));
    } catch {
      paint2(null);
    }
  }
  async function copyVersion() {
    const status = el("version-copy-status");
    if (!copyText) {
      status.textContent = t("version.unavailable");
      return;
    }
    const writeText = navigator.clipboard?.writeText;
    if (!writeText || !window.isSecureContext) {
      status.textContent = t("version.copyFailed");
      return;
    }
    try {
      await writeText.call(navigator.clipboard, copyText);
      status.textContent = t("version.copied");
    } catch {
      status.textContent = t("version.copyFailed");
    }
  }
  function wireVersion() {
    el("copy-version").addEventListener("click", () => {
      void copyVersion();
    });
  }

  // src/locale-wiring.ts
  function repaintAll() {
    applyStatic(document);
    repaintViews();
    if (state.mode === "snapshots") renderSnapshots();
    repaintSnapshotPlan();
    repaintDialogs();
    repaintCheatSheet();
    repaintQuickOpen();
    repaintPlayer();
    repaintVersion();
    refreshTooltips();
  }
  var stop = null;
  function wireLocale() {
    stop?.();
    setLocale(initialLocale());
    applyStatic(document);
    stop = onLocaleChange(repaintAll);
  }

  // src/app.ts
  function wireSnapshots() {
    el("snapshots-refresh").addEventListener("click", () => {
      loadSnapshots().catch((error2) => failSnapshots(error2));
    });
    el("snapshots-take").addEventListener("click", () => {
      takeSnapshot().catch((error2) => failSnapshots(error2));
    });
    el("snapshots-undo-button").addEventListener("click", () => {
      const pending = state.snapshotUndo;
      if (!pending || !pending.restore_id) return;
      openSnapshotPlan(pending.restore_id).catch((error2) => failSnapshots(error2));
    });
    el("snapshot-cancel").addEventListener("click", () => {
      el("snapshot-dialog").close();
    });
    el("snapshot-confirm").addEventListener("click", () => {
      confirmSnapshotRestore().catch((error2) => setSnapshotDialogStatus(failureOf(error2).message));
    });
  }
  wireLocale();
  installTooltips();
  applyStaticTooltips();
  mountTrackList();
  mountPlayer();
  registerPlayerControls(playerControls);
  wireLibrary();
  wireVirtualScroll();
  wireShortcuts();
  wireDialogs();
  wireSnapshots();
  wireLayout();
  wireVersion();
  void loadVersion();
  bindLibraryReload(loadLibrary);
  loadLibrary().catch(showFailure);
})();
//# sourceMappingURL=app.js.map
