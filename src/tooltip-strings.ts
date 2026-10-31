/**
 * Tooltip keys for t().
 *
 * The sentences live in locales/en.json and locales/es.json under
 * tooltip.*. This module only names those keys and fills placeholders.
 * A language change calls refreshTooltips, which reads the keys again.
 */

import { t, type MessageKey, type Params } from "./i18n";
import type { PrimaryAction } from "./wizard";

export interface TipSpec {
  key: MessageKey;
  params?: Params;
}

function spec(key: MessageKey, params?: Params): TipSpec {
  return params ? { key, params } : { key };
}

export const tips = {
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
  sortAdded: spec("tooltip.sortAdded"),
} as const;

const WIZARD: Record<PrimaryAction, MessageKey> = {
  "get-started": "tooltip.wizard.getStarted",
  looking: "tooltip.wizard.looking",
  "use-library": "tooltip.wizard.useLibrary",
  "check-again": "tooltip.wizard.checkAgain",
  "take-snapshot": "tooltip.wizard.takeSnapshot",
  "try-again": "tooltip.wizard.tryAgain",
  continue: "tooltip.wizard.continue",
  "open-library": "tooltip.wizard.openLibrary",
  none: "tooltip.wizard.none",
};

/** Tooltip for the wizard's main button. Saving uses its own sentence. */
export function wizardPrimaryTip(action: PrimaryAction, saving: boolean): TipSpec {
  if (saving) return spec("tooltip.wizard.saving");
  return spec(WIZARD[action]);
}

/**
 * Play or Pause, including Space, without repeating only the button name.
 *
 * @param action Visible action, already translated.
 * @param name Track title, or empty when nothing is loaded.
 */
export function playTip(action: string, name: string): TipSpec {
  if (name) return spec("tooltip.transportNamed", { action, name });
  return spec("tooltip.transport", { action });
}

/** Column sort. Unknown keys use the visible column name. */
export function sortTip(key: string, label: string): TipSpec {
  const known: Record<string, MessageKey> = {
    name: "tooltip.sortTitle",
    artist: "tooltip.sortArtist",
    bpm: "tooltip.sortBpm",
    key: "tooltip.sortKey",
    length_ms: "tooltip.sortLength",
    deck: "tooltip.sortDeck",
    played: "tooltip.sortPlayed",
    start: "tooltip.sortStart",
  };
  const message = known[key];
  if (message) return spec(message);
  return spec("tooltip.sortBy", { label });
}

/** View tab, or undefined when that view has no tooltip yet. */
export function viewTip(view: string): TipSpec | undefined {
  const known: Record<string, TipSpec> = {
    crates: tips.viewCrates,
    history: tips.viewHistory,
    missing: tips.viewMissing,
    duplicates: tips.viewDuplicates,
    stems: tips.viewStems,
    files: tips.viewFiles,
    snapshots: tips.viewSnapshots,
  };
  return known[view];
}

/** Crate-sort button, or undefined when that key has no tooltip yet. */
export function crateSortTip(key: string): TipSpec | undefined {
  if (key === "order") return tips.sortOrder;
  if (key === "name") return tips.sortCrateName;
  if (key === "added") return tips.sortAdded;
  return undefined;
}

/** Static control looked up by id. */
export function staticTip(id: string): TipSpec | undefined {
  const known: Record<string, TipSpec> = {
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
    "track-splitter": tips.splitter,
  };
  return known[id];
}

export function expandCrate(name: string): TipSpec {
  return spec("tooltip.expandCrate", { name });
}

export function collapseCrate(name: string): TipSpec {
  return spec("tooltip.collapseCrate", { name });
}

export function openCrate(name: string): TipSpec {
  return spec("tooltip.openCrate", { name });
}

export function sessionTip(name: string): TipSpec {
  return spec("tooltip.session", { name });
}

export function playRow(name: string): TipSpec {
  return spec("tooltip.playRow", { name });
}

export function selectRow(name: string): TipSpec {
  return spec("tooltip.selectRow", { name });
}

export function cueTip(label: string): TipSpec {
  return spec("tooltip.cue", { label });
}

export function editField(label: string): TipSpec {
  return spec("tooltip.editField", { label });
}

export function revealTip(manager: string): TipSpec {
  return spec("tooltip.reveal", { name: manager });
}

export function openCopy(name: string): TipSpec {
  return spec("tooltip.openCopy", { name });
}

export function openRelated(name: string): TipSpec {
  return spec("tooltip.openRelated", { name });
}

export function removeRelatedTip(name: string): TipSpec {
  return spec("tooltip.removeRelated", { name });
}

export function chooseRelated(name: string): TipSpec {
  return spec("tooltip.chooseRelated", { name });
}

export function saveSuggestion(name: string): TipSpec {
  return spec("tooltip.saveSuggestion", { name });
}

export function membershipTip(name: string): TipSpec {
  return spec("tooltip.membership", { name });
}

export function openCrumb(name: string): TipSpec {
  return spec("tooltip.openCrumb", { name });
}

export function openFile(name: string): TipSpec {
  return spec("tooltip.openFile", { name });
}

export function missingDrive(name: string): TipSpec {
  return spec("tooltip.missingDrive", { name });
}

export function fileShortcut(name: string): TipSpec {
  return spec("tooltip.fileShortcut", { name });
}

export function selectFile(name: string, path = ""): TipSpec {
  if (path && path !== name) return spec("tooltip.selectFilePath", { name, path });
  return spec("tooltip.selectFile", { name });
}

export function wizardFolder(name: string): TipSpec {
  return spec("tooltip.wizardFolder", { name });
}

export function keepCopy(name: string): TipSpec {
  return spec("tooltip.keepCopy", { name });
}

export function quickOpenHit(kind: string, title: string, detail: string): TipSpec {
  if (detail) return spec("tooltip.quickOpenHitDetail", { kind, title, detail });
  return spec("tooltip.quickOpenHit", { kind, title });
}

/** The sentence for a spec, in the active locale. Tests read this. */
export function tipText(item: TipSpec): string {
  return t(item.key, item.params);
}
