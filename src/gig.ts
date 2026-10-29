/**
 * Read-only gig check view.
 *
 * Typed against the fields GET /api/gig-check returns. The request does
 * not write. A newer selection ignores a late response. The report is
 * painted with text nodes.
 */

import { failureOf, readJSON } from "./api";
import type { GigReport } from "./api-types";
import { el } from "./dom";
import { state } from "./state";

/**
 * Ask for a read-only gig check of the open space and crate.
 *
 * @returns {Promise<void>}
 */
export async function loadGigCheck(): Promise<void> {
  const token = ++state.gigToken;
  const report = el("gig-report");
  report.setAttribute("aria-busy", "true");
  el("gig-scope").textContent = "Checking the library";
  const waiting = document.createElement("p");
  waiting.className = "gig-note";
  waiting.textContent = "Checking the library…";
  report.replaceChildren(waiting);
  const crate = state.activeCrate === "all" ? "all" : String(state.activeCrate);
  const response = await fetch(
    `/api/gig-check?space=${encodeURIComponent(state.space)}&crate=${encodeURIComponent(crate)}`,
  );
  const payload = await readJSON<GigReport>(response).catch((): GigReport => ({ ready: false, score: 0, hard_red: false }));
  if (token !== state.gigToken) return;
  report.setAttribute("aria-busy", "false");
  if (!response.ok) throw new Error(payload.error || "The gig check could not be read.");
  renderGigReport(payload);
}

/**
 * Show a gig-check failure in the report, not in the track detail.
 *
 * @param {unknown} error Failure from loadGigCheck.
 * @returns {void}
 */
export function showGigFailure(error: unknown): void {
  const report = el("gig-report");
  report.setAttribute("aria-busy", "false");
  const failure = document.createElement("p");
  failure.className = "detail-error";
  failure.textContent = failureOf(error).message || "The gig check could not be read.";
  report.replaceChildren(failure);
}

/**
 * Add a heading and a list to the gig report.
 *
 * An empty list is skipped. Long lists keep the first 100 lines.
 *
 * @param {HTMLElement} parent Report element.
 * @param {string} heading Section title.
 * @param {string[]} lines Lines to show.
 * @returns {void}
 */
function appendGigList(parent: HTMLElement, heading: string, lines: string[]): void {
  if (!lines.length) return;
  const title = document.createElement("h3");
  title.textContent = heading;
  const list = document.createElement("ul");
  const shown = lines.slice(0, 100);
  for (const line of shown) {
    const item = document.createElement("li");
    item.textContent = line;
    list.append(item);
  }
  parent.append(title, list);
  if (lines.length > shown.length) {
    const more = document.createElement("p");
    more.className = "gig-note";
    more.textContent = `And ${lines.length - shown.length} more.`;
    parent.append(more);
  }
}

/**
 * Paint the ready score and the Holding it back breakdown.
 *
 * Color is not the only signal: the verdict is the word Ready or Not ready.
 *
 * @param {GigReport} payload JSON from GET /api/gig-check.
 * @returns {void}
 */
export function renderGigReport(payload: GigReport): void {
  const report = el("gig-report");
  const crateName = payload.scope?.crate_name;
  el("gig-scope").textContent = crateName
    ? `Checking ${crateName}. Nothing is written.`
    : "Checking the whole space. Nothing is written.";
  report.replaceChildren();
  const scoreLabel = document.createElement("p");
  scoreLabel.className = "visually-hidden";
  scoreLabel.textContent = "Ready score";
  const score = document.createElement("p");
  score.className = "gig-score";
  score.textContent = String(payload.score);
  const verdict = document.createElement("p");
  verdict.className = payload.ready ? "gig-verdict" : "gig-verdict not-ready";
  verdict.textContent = payload.ready ? "Ready" : "Not ready";
  const holdingTitle = document.createElement("h3");
  holdingTitle.textContent = "Holding it back";
  report.append(scoreLabel, score, verdict, holdingTitle);
  const holding = payload.holding_it_back || [];
  if (!holding.length) {
    const clear = document.createElement("p");
    clear.className = "gig-note";
    clear.textContent = "Nothing is holding it back.";
    report.append(clear);
  } else {
    const list = document.createElement("ul");
    for (const line of holding) {
      const item = document.createElement("li");
      item.textContent = line.summary;
      list.append(item);
    }
    report.append(list);
  }
  appendGigList(report, "Missing files", (payload.missing_files || []).map((item) => item.path));
  appendGigList(
    report,
    "Unavailable drives",
    (payload.unavailable_drives || []).map((drive) => `${drive.name}: ${drive.track_count} tracks unavailable`),
  );
  appendGigList(
    report,
    "Streaming tracks",
    (payload.streaming_tracks || []).map((item) => `${item.service}: ${item.title}`),
  );
  appendGigList(
    report,
    "Empty crates",
    (payload.empty_crates || []).map((item) => `${item.name} — ${item.warning}`),
  );
  const since = document.createElement("h3");
  since.textContent = "Since last gig";
  const note = document.createElement("p");
  note.className = "gig-note";
  note.textContent = payload.snapshot_note || "";
  report.append(since, note);
  const changes = payload.changes;
  if (!changes) return;
  const groups: Array<[string, string[]]> = [
    ["Crates added", changes.crates_added || []],
    ["Crates removed", changes.crates_removed || []],
    ["Crates edited", changes.crates_edited || []],
    ["Tracks added", changes.tracks_added || []],
    ["Tracks removed", changes.tracks_removed || []],
    ["Cues edited", changes.cues_edited || []],
    ["Beatgrids edited", changes.grids_edited || []],
    ["Tags edited", changes.tags_edited || []],
  ];
  if (!groups.some(([, lines]) => lines.length)) {
    const same = document.createElement("p");
    same.className = "gig-note";
    same.textContent = "Nothing changed since the last snapshot.";
    report.append(same);
    return;
  }
  for (const [heading, lines] of groups) appendGigList(report, heading, lines);
}
