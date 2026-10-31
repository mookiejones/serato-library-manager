/**
 * Start the page in the right language and repaint it on a change.
 *
 * app.ts calls wireLocale once, before the first paint. A later change,
 * from Settings or from the saved choice arriving with GET /api/settings,
 * repaints what is on screen from the data the page already holds. The
 * library is not read again.
 */

import { repaintDialogs } from "./dialogs";
import { applyStatic, initialLocale, onLocaleChange, setLocale } from "./i18n";
import { repaintPlayer } from "./player";
import { repaintQuickOpen } from "./quick-open";
import { renderSnapshots, repaintSnapshotPlan } from "./restore";
import { repaintCheatSheet } from "./shortcuts";
import { state } from "./state";
import { repaintVersion } from "./version";
import { repaintViews } from "./views";

/**
 * Repaint everything on screen in the active language.
 *
 * Static markup is translated from its data-i18n attributes. The views,
 * dialogs, snapshot list, and version line repaint from what the page
 * already holds.
 *
 * @returns {void}
 */
export function repaintAll(): void {
  applyStatic(document);
  repaintViews();
  if (state.mode === "snapshots") renderSnapshots();
  repaintSnapshotPlan();
  repaintDialogs();
  repaintCheatSheet();
  repaintQuickOpen();
  repaintPlayer();
  repaintVersion();
}

let stop: (() => void) | null = null;

/**
 * Pick the first locale, translate the markup, and listen for changes.
 *
 * Calling it again replaces the earlier listener, so the page repaints
 * once per change.
 *
 * @returns {void}
 */
export function wireLocale(): void {
  stop?.();
  setLocale(initialLocale());
  applyStatic(document);
  stop = onLocaleChange(repaintAll);
}
