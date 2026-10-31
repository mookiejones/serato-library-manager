/**
 * Tooltip keys for every control.
 *
 * Components set a key with tip() or data-tip="key" instead of inlining
 * the sentence. The text is `tip.<key>` in locales/. Keep each one a short
 * plain sentence that a person who has never seen the app can act on.
 *
 * tooltips.ts shows the text. tooltip-audit.ts fails the tests when a
 * control has no tip.
 */

import { t, type MessageKey } from "./i18n";

type TipId<K> = K extends `tip.${infer Id}` ? Id : never;

export type TipKey = TipId<MessageKey>;

/**
 * Read a tooltip in the active language.
 *
 * @param key Key in the tip part of the catalog.
 * @returns The sentence.
 */
export function tipText(key: TipKey): string {
  return t(`tip.${key}`);
}

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
 * @param key Key in the tip part of the catalog.
 * @param detail Optional line above the tip, such as a full path a row cuts off.
 * @returns {void}
 */
export function tip(control: HTMLElement, key: TipKey, detail?: string): void {
  control.dataset.tip = key;
  if (detail) control.dataset.tipDetail = detail;
}
