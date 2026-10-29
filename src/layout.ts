/**
 * The divider between the track list and the detail pane.
 *
 * Crates, history, missing, duplicates, and stems all share that sheet,
 * so one splitter and one saved width serve every list view. The width
 * is stored in settings.json through POST /api/settings, not in browser
 * storage, because the desktop app can bind a new port on each launch.
 */

import { postJSON } from "./api";
import type { SettingsPayload } from "./api-types";
import { el } from "./dom";
import { mountSplitter, type Splitter } from "./splitter";
import { setNotice } from "./views";

/** Narrowest track list that still shows title, artist, BPM, key, and time. */
export const TRACK_LIST_MIN_WIDTH = 360;
/** Matches the detail column's minmax(300px, …) in app.css. */
export const DETAIL_MIN_WIDTH = 300;
/** Arrow keys repeat quickly. One POST follows the last key in a burst. */
const SAVE_DELAY_MS = 400;

let splitter: Splitter | null = null;
let changedHere = false;
let saveTimer: ReturnType<typeof setTimeout> | undefined;

/**
 * POST the width after a short pause.
 *
 * A failure keeps the width on screen and says it was not saved.
 *
 * @param width Track list width in pixels, or null for the default split.
 * @returns {void}
 */
function save(width: number | null): void {
  changedHere = true;
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    postJSON("/api/settings", { layout: { track_list_width: width } }).catch(() => {
      setNotice("Couldn't save the pane width. It goes back to the last saved width next time.");
    });
  }, SAVE_DELAY_MS);
}

/**
 * Attach the track list splitter. Called once at startup.
 *
 * @returns {void}
 */
export function wireLayout(): void {
  splitter = mountSplitter({
    handle: el("track-splitter"),
    container: el("browser").parentElement as HTMLElement,
    first: el("browser"),
    property: "--track-list-width",
    minFirst: TRACK_LIST_MIN_WIDTH,
    minSecond: DETAIL_MIN_WIDTH,
    onCommit: save,
  });
  window.addEventListener("resize", () => splitter?.refit());
}

/**
 * Apply the saved width from a /api/settings payload.
 *
 * A width the person already changed in this page is kept, so a slow
 * settings response does not snap the divider back.
 *
 * @param payload Settings object from the server.
 * @returns {void}
 */
export function applyLayout(payload: SettingsPayload): void {
  if (!splitter || changedHere) return;
  const width = payload.layout?.track_list_width;
  splitter.set(typeof width === "number" ? width : null);
}
