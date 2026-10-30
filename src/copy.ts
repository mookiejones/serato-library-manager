/**
 * English copy for shortcuts, quick-open, and file search.
 *
 * Components read these sentences instead of inlining them. A later
 * language pass can replace each value with t("key") without hunting
 * through the handlers. Placeholders use {name}, the same shape as t().
 */

export const copy = {
  shortcutsTitle: "Keyboard shortcuts",
  shortcutsIntro:
    "These keys work anywhere on this screen, except while you are typing in a field. Esc still closes a dialog or clears a search.",
  shortcutsClose: "Close",
  openShortcuts: "Shortcuts",
  playNote: "Space and the left and right arrows play or move through a track once playback is available. Until then, they do nothing.",
  quickOpenTitle: "Find a track or file",
  quickOpenLabel: "Name",
  quickOpenPlaceholder: "Track or file name",
  quickOpenEmpty: "Type a track or file name.",
  quickOpenSearching: "Searching files…",
  quickOpenFileError: "Files on disk could not be searched. Track matches are still listed.",
  quickOpenRetry: "Try again",
  quickOpenNone: "No tracks or files match “{query}”.",
  quickOpenTruncated: "Some files were not searched. Type more of the name.",
  quickOpenClose: "Close",
  quickOpenTrack: "Track",
  quickOpenFile: "File",
  filesSearchLabel: "Search files",
  filesSearchPlaceholder: "Search files",
  filesSearching: "Searching files…",
  filesNoMatches: "No files match “{query}”.",
  filesTruncated: "Some matching files are not listed. Type more of the name.",
  filesSearchResults: "Search results",
  snapshotsNoSearch: "Snapshots has no search. Press Ctrl+K to find a track or a file.",
} as const;

/**
 * Replace {name} placeholders.
 *
 * Unknown names become an empty string. The template stays the English
 * source until it moves to t().
 *
 * @param template Sentence with {name} markers.
 * @param params Values for those markers.
 * @returns The sentence with markers replaced.
 */
export function fill(template: string, params: Record<string, string>): string {
  return template.replace(/\{(\w+)\}/g, (_match, name: string) => params[name] ?? "");
}
