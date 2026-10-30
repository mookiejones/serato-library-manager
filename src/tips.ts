/**
 * Tooltip text for every control.
 *
 * Components set a key with tip() or data-tip="key" instead of inlining
 * the sentence. A later language pass can replace each value with
 * t("key"), the same way as copy.ts. Keep each one a short plain sentence
 * that a person who has never seen the app can act on.
 *
 * tooltips.ts shows the text. tooltip-audit.ts fails the tests when a
 * control has no tip.
 */

export const tips = {
  space: "Choose which part of your library to show.",
  viewCrates: "Show your crates and their tracks.",
  viewHistory: "Show the sessions you played.",
  viewMissing: "Show tracks whose files cannot be found.",
  viewDuplicates: "Show tracks that are in the library more than once.",
  viewStems: "Show tracks that have stems.",
  viewFiles: "Show the music files on this computer.",
  viewSnapshots: "Show saved copies of your library.",
  crateSearch: "Type a name to narrow the crate list.",
  crateSortOrder: "List crates in your Serato order.",
  crateSortName: "List crates from A to Z.",
  crateSortAdded: "List the newest crates first.",
  crateRow: "Show the tracks in this crate.",
  crateExpand: "Show the crates inside this one.",
  crateCollapse: "Hide the crates inside this one.",
  crateNew: "Make a new crate.",
  crateRename: "Change the name of this crate.",
  crateColor: "Change the color of this crate.",
  crateDelete: "Delete this crate. Its music files stay on disk.",
  crateMember: "Tick to keep this track in this crate.",
  smartRules: "Edit the rules that choose this crate's tracks.",
  smartRulesSave: "Save the rules for this smart crate.",
  mergeCopies: "Keep one copy of this track and remove the others.",
  openShortcuts: "List the keyboard shortcuts.",
  openSettings: "Open settings for sharing, logs, and setup.",
  search: "Type a title or artist to narrow the list.",
  exportM3u: "Download this list as a playlist file.",
  exportRekordbox: "Download a rekordbox.xml file of this library.",
  rekordboxMemory: "Include memory cues in the Rekordbox file.",
  rekordboxHotLoops: "Add saved loops to the Rekordbox file. Each uses a free hot-cue pad.",
  rekordboxKey: "Choose how keys are written in the Rekordbox file.",
  importM3u: "Make a new crate from a playlist file.",
  reload: "Read the library again to pick up new changes.",
  sortColumn: "Sort the list by this column. Click again to reverse it.",
  trackRow: "Show the details of this track.",
  splitter: "Drag to resize the track list. Double-click to reset it.",
  trackTitle: "The track's title.",
  trackArtist: "The artist's name.",
  trackAlbum: "The album name.",
  trackGenre: "The style of music.",
  trackYear: "The year the track came out.",
  trackComposer: "The person who wrote the track.",
  trackRemixer: "The person who remixed the track.",
  trackLabel: "The record label.",
  trackGrouping: "Your own group name for this track.",
  trackKey: "The musical key.",
  trackBpm: "The speed in beats per minute.",
  trackEmoji: "An emoji to mark this track.",
  trackComments: "Your own notes about this track.",
  trackColor: "Choose the color that marks this track.",
  trackRating: "Give this track a star rating.",
  trackGridLock: "Tick to stop the beatgrid from being changed.",
  trackSave: "Save your changes to this track.",
  trackReveal: "Show this track's file on your computer.",
  prepareSend: "Add this track to the Prepare list.",
  prepareRemove: "Take this track off the Prepare list.",
  trackRelocate: "Point this track at its file in a new place.",
  trackRemove: "Remove this track from the library. The file stays on disk.",
  openInLibrary: "Open this stem's track in the library.",
  searchCopies: "Show or hide the fields from the other copies.",
  duplicateCopy: "Show the details of this copy.",
  relatedCrate: "Update the Serato crate that holds these related tracks.",
  relatedOpen: "Show this related track.",
  relatedRemove: "Remove this link. Both tracks stay in the library.",
  relatedSearch: "Type a title or artist to find a track to link.",
  relatedChoose: "Choose this track to link.",
  relatedNote: "Add a note about how these tracks go together.",
  relatedRating: "Rate how well these tracks go together.",
  relatedMutual: "Tick to show the link on both tracks.",
  relatedSave: "Save this link.",
  relatedSuggestionSave: "Save this suggestion as a link.",
  historySession: "Show the tracks played in this session.",
  filesUp: "Go up to the folder that holds this one.",
  filesCrumb: "Go to this folder.",
  filesSearch: "Type a name to find a file in this folder.",
  filesRefresh: "Read this folder again.",
  filesElsewhere: "Look in a folder outside your music folders.",
  filesRunSetup: "Run setup to find your library.",
  filesOpen: "Open this folder.",
  filesDriveMissing: "This drive is not connected. Connect it and try again.",
  filesShortcut: "This is a shortcut to another place on disk.",
  filesSelect: "Tick to choose this file.",
  filesRename: "Change the name of the chosen file.",
  filesMove: "Move the chosen files to another folder.",
  filesMoveFolder: "Move this whole folder.",
  filesReplace: "Swap the chosen file for another. Its cues and crates stay.",
  filesDelete: "Move the chosen files to the Trash.",
  filesMoveHere: "Move the files into this folder.",
  filesPickCancel: "Stop the move. Nothing changes.",
  snapshotsRefresh: "Read the list of snapshots again.",
  snapshotsTake: "Save a copy of your library now.",
  snapshotsUndo: "See what undoing the outside change would do. Nothing changes yet.",
  snapshotsRetry: "Try reading the snapshots again.",
  snapshotRestore: "See what restoring this snapshot would change. Nothing changes yet.",
  consentDecline: "Do not send usage counts or crash reports.",
  consentAccept: "Send anonymous usage counts and crash reports.",
  telemetryToggle: "Tick to send anonymous usage counts and crash reports.",
  copyVersion: "Copy the version number.",
  rerunWizard: "Go through first-time setup again.",
  openLogs: "Open the folder that holds the app's logs.",
  copyLogs: "Copy the app's logs so you can paste them.",
  logFallback: "The app's logs. Select the text to copy it.",
  dialogClose: "Close this box.",
  dialogCancel: "Close this box. Nothing changes.",
  mergeKeep: "Choose this copy to keep.",
  mergeTrash: "Tick to also move the other files to the Trash.",
  mergeConfirm: "Merge the copies into the one you chose.",
  rekordboxDownload: "Download the rekordbox.xml file.",
  filesName: "Type the new name.",
  filesReplacement: "Type the full path of the new file.",
  filesReview: "See what will change. Nothing changes yet.",
  filesConfirm: "Make this change.",
  quickOpenQuery: "Type part of a track or file name.",
  quickOpenRetry: "Search the files on disk again.",
  quickOpenResult: "Open this track or file.",
  snapshotConfirm: "Put your library back to this snapshot.",
  wizardFolderUp: "Go up to the folder that holds this one.",
  wizardFolderUse: "Use the folder you are looking at.",
  wizardFolderClose: "Close the folder list.",
  wizardFolder: "Open this folder.",
  wizardNo: "Do not send usage counts or crash reports.",
  wizardYes: "Send anonymous usage counts and crash reports.",
  wizardBack: "Go back one step.",
  wizardCancel: "Close setup. It runs again next time.",
  wizardSecondary: "Find your library folder yourself.",
  wizardPrimary: "Go on to the next step.",
  rowPlay: "Play this track.",
  playerPrevious: "Go to the track before this one.",
  playerToggle: "Play or pause the track.",
  playerNext: "Go to the next track.",
  playerSeek: "Drag to move through the track.",
  playerVolume: "Change how loud the track plays.",
  playerCue: "Jump to this cue point.",
  waveformOverview: "Click or drag to move through the track.",
  waveformZoomIn: "Show less of the track in more detail.",
  waveformZoomOut: "Show more of the track in less detail.",
} as const;

export type TipKey = keyof typeof tips;

/**
 * Controls with a shortcut, by tip key.
 *
 * The values are ids in SHORTCUTS, so the keys shown are never a second
 * copy of the binding. A test checks each id.
 */
export const TIP_SHORTCUTS: Partial<Record<TipKey, string | readonly string[]>> = {
  search: "focus-search",
  crateSearch: "focus-search",
  filesSearch: "focus-search",
  openShortcuts: "cheat-sheet",
  viewCrates: "view-crates",
  viewFiles: "view-files",
  viewHistory: "view-history",
  viewSnapshots: "view-snapshots",
  trackRow: "list-open",
  filesOpen: "list-open",
  quickOpenResult: "list-open",
  dialogClose: "dismiss",
  dialogCancel: "dismiss",
  rowPlay: "play-pause",
  playerToggle: "play-pause",
  playerSeek: ["seek-back", "seek-forward"],
  waveformOverview: ["seek-back", "seek-forward"],
};

/**
 * Give a control its tooltip.
 *
 * This never sets aria-label. The tip describes a control, and the control
 * keeps the name that its text, its label, or its own aria-label gives it.
 *
 * @param control Control to mark.
 * @param key Key in the tips table.
 * @param detail Optional line above the tip, such as a full path a row cuts off.
 * @returns {void}
 */
export function tip(control: HTMLElement, key: TipKey, detail?: string): void {
  control.dataset.tip = key;
  if (detail) control.dataset.tipDetail = detail;
}
