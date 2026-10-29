/**
 * Read-only gig check view.
 *
 * Typed against the fields GET /api/gig-check returns. The request does
 * not write. A newer selection ignores a late response. The report is
 * painted with text nodes. Five steps lead to a done screen. #gig-ready-art
 * is the empty slot for the done artwork Pixel supplies.
 */

import { readJSON } from "./api";
import type { GigReport } from "./api-types";
import { el } from "./dom";
import { state } from "./state";

const STEP_COUNT = 5;
const LIST_CAP = 100;
const UNREACHABLE = "Couldn't reach the library server. Check it's running, then press Check again";

interface GigStep {
  title: string;
  action: string;
  empty: string;
}

const STEPS: readonly GigStep[] = [
  { title: "Drives", action: "Check drives", empty: "No drives are unplugged." },
  { title: "Missing files", action: "Locate missing files", empty: "No files are missing." },
  { title: "Streaming", action: "Review streaming tracks", empty: "No streaming tracks." },
  { title: "Empty crates", action: "Fill empty crates", empty: "No empty crates." },
  { title: "Since last gig", action: "Review changes", empty: "Nothing changed since the last snapshot." },
];

let stepIndex = 0;
let latest: GigReport | null = null;
let checkedAt = "";
let exitGig: () => void = () => {};

/**
 * Attach Check again, Back, the step verb, and Exit gig check.
 *
 * Called once at startup. A later call only replaces the exit handler.
 *
 * @param exit Leaves the Gig view.
 * @returns {void}
 */
export function wireGigCheck(exit: () => void): void {
  exitGig = exit;
  const panel = el("gig-panel");
  if (panel.dataset.gigWired === "true") return;
  panel.dataset.gigWired = "true";
  el("gig-refresh").addEventListener("click", () => {
    void loadGigCheck(true);
  });
  panel.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    const button = target.closest("button");
    if (!(button instanceof HTMLButtonElement) || !latest) return;
    const action = button.dataset.gigAction;
    if (action === "next") stepIndex = Math.min(stepIndex + 1, STEP_COUNT);
    else if (action === "back") stepIndex = Math.max(0, stepIndex - 1);
    else if (action === "exit") {
      exitGig();
      return;
    } else return;
    renderGigReport(latest);
    focusHeading();
  });
}

/**
 * Ask for a read-only gig check of the open space and crate.
 *
 * The previous report stays on screen until this reply arrives. The
 * Check again button is disabled while the request runs.
 *
 * @param keepStep Keep the step the person is on. Check again passes true.
 * @returns {Promise<void>}
 */
export async function loadGigCheck(keepStep = false): Promise<void> {
  const token = ++state.gigToken;
  if (!keepStep) stepIndex = 0;
  beginBusy();
  let settle: "heading" | "retry" | "none" = "none";
  const crate = state.activeCrate === "all" ? "all" : String(state.activeCrate);
  try {
    const response = await fetch(
      `/api/gig-check?space=${encodeURIComponent(state.space)}&crate=${encodeURIComponent(crate)}`,
    );
    if (token !== state.gigToken) return;
    const payload = await readJSON<GigReport>(response).catch((): null => null);
    if (token !== state.gigToken) return;
    if (!response.ok || payload === null) {
      failStatus(payload?.error || "The gig check could not be read.");
      settle = "retry";
      return;
    }
    checkedAt = formatCheckedAt(new Date());
    latest = payload;
    el("gig-status").textContent = "";
    renderGigReport(payload);
    settle = "heading";
  } catch {
    if (token !== state.gigToken) return;
    failStatus(UNREACHABLE);
    settle = "retry";
  } finally {
    if (token !== state.gigToken) return;
    endBusy();
    if (settle === "retry") el("gig-refresh").focus();
    if (settle === "heading") focusHeading();
  }
}

/**
 * Show a gig-check failure in the status line, not in the track detail.
 *
 * The report already on screen stays. Focus moves to Check again.
 *
 * @param {unknown} error Failure from loadGigCheck.
 * @returns {void}
 */
export function showGigFailure(error: unknown): void {
  const message = error instanceof Error && error.message
    ? error.message
    : "The gig check could not be read.";
  failStatus(message);
  endBusy();
  el("gig-refresh").focus();
}

/**
 * Paint the ready score and the current step.
 *
 * Color is not the only signal: the verdict is ✓ Ready or ✕ Not ready.
 *
 * @param {GigReport} payload JSON from GET /api/gig-check.
 * @returns {void}
 */
export function renderGigReport(payload: GigReport): void {
  const report = el("gig-report");
  el("gig-scope").textContent = payload.scope?.crate_name || "Whole space";
  report.replaceChildren(scoreBlock(payload));
  if (stepIndex >= STEP_COUNT) {
    report.append(doneScreen(payload));
    return;
  }
  const step = STEPS[stepIndex]!;
  report.append(kicker(stepIndex), heading(step.title));
  if (stepIndex === STEP_COUNT - 1) renderSince(report, payload);
  else renderStepList(report, step, linesFor(payload, stepIndex));
  report.append(actions(step.action));
}

function beginBusy(): void {
  const button = el("gig-refresh");
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  el("gig-panel").setAttribute("aria-busy", "true");
  el("gig-status").textContent = "Checking the library…";
}

function endBusy(): void {
  const button = el("gig-refresh");
  button.disabled = false;
  button.setAttribute("aria-busy", "false");
  el("gig-panel").setAttribute("aria-busy", "false");
}

function failStatus(message: string): void {
  el("gig-status").textContent = message;
}

function focusHeading(): void {
  const headingNode = document.getElementById("gig-step-heading");
  if (headingNode instanceof HTMLElement) headingNode.focus();
}

function formatCheckedAt(date: Date): string {
  const hours = date.getHours();
  const minutes = String(date.getMinutes()).padStart(2, "0");
  const suffix = hours >= 12 ? "PM" : "AM";
  const hour12 = hours % 12 || 12;
  return `${hour12}:${minutes} ${suffix}`;
}

function scoreBlock(payload: GigReport): HTMLParagraphElement {
  const score = document.createElement("p");
  score.className = "gig-score";
  const word = payload.ready ? "ready" : "not ready";
  score.setAttribute("aria-label", `Ready score ${payload.score} out of 100, ${word}`);
  const value = document.createElement("span");
  value.className = "gig-score-value";
  value.textContent = `${payload.score}/100`;
  const verdict = document.createElement("span");
  verdict.className = payload.ready ? "gig-verdict" : "gig-verdict not-ready";
  verdict.textContent = payload.ready ? "✓ Ready" : "✕ Not ready";
  score.append(value, verdict);
  return score;
}

function kicker(index: number): HTMLParagraphElement {
  const step = document.createElement("p");
  step.className = "gig-kicker";
  step.textContent = `Step ${index + 1} of ${STEP_COUNT}`;
  return step;
}

function heading(text: string): HTMLHeadingElement {
  const title = document.createElement("h3");
  title.id = "gig-step-heading";
  title.tabIndex = -1;
  title.textContent = text;
  return title;
}

function linesFor(payload: GigReport, index: number): string[] {
  if (index === 0) {
    return (payload.unavailable_drives || []).map((drive) => `${drive.name}: ${drive.track_count} tracks unavailable`);
  }
  if (index === 1) return (payload.missing_files || []).map((item) => item.path);
  if (index === 2) return (payload.streaming_tracks || []).map((item) => `${item.service}: ${item.title}`);
  if (index === 3) return (payload.empty_crates || []).map((item) => `${item.name} — ${item.warning}`);
  return [];
}

function renderStepList(parent: HTMLElement, step: GigStep, lines: string[]): void {
  if (!lines.length) {
    const empty = document.createElement("p");
    empty.className = "gig-note";
    empty.textContent = step.empty;
    parent.append(empty);
    return;
  }
  parent.append(detailsGroup(step.title, lines));
}

function renderSince(parent: HTMLElement, payload: GigReport): void {
  const note = payload.snapshot_note?.trim() ?? "";
  if (note) {
    const line = document.createElement("p");
    line.className = "gig-note";
    line.textContent = note;
    parent.append(line);
  }
  const changes = payload.changes;
  if (!changes) {
    if (!note) parent.append(noteLine("No snapshot to compare."));
    return;
  }
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
  let any = false;
  for (const [label, lines] of groups) {
    if (!lines.length) continue;
    parent.append(detailsGroup(label, lines));
    any = true;
  }
  if (!any) parent.append(noteLine(STEPS[STEP_COUNT - 1]!.empty));
}

function noteLine(text: string): HTMLParagraphElement {
  const line = document.createElement("p");
  line.className = "gig-note";
  line.textContent = text;
  return line;
}

function detailsGroup(label: string, lines: string[]): HTMLDetailsElement {
  const details = document.createElement("details");
  details.className = "gig-group";
  details.open = true;
  const summary = document.createElement("summary");
  summary.textContent = `${label} (${lines.length})`;
  const list = document.createElement("ul");
  const shown = lines.slice(0, LIST_CAP);
  for (const line of shown) list.append(item(line));
  details.append(summary, list);
  if (lines.length > LIST_CAP) {
    const show = document.createElement("button");
    show.type = "button";
    show.className = "gig-show-all";
    show.textContent = `Show all ${lines.length}`;
    show.addEventListener("click", () => {
      list.replaceChildren();
      for (const line of lines) list.append(item(line));
      show.remove();
    });
    details.append(show);
  }
  return details;
}

function item(text: string): HTMLLIElement {
  const row = document.createElement("li");
  row.textContent = text;
  return row;
}

function actions(primary: string | null): HTMLDivElement {
  const bar = document.createElement("div");
  bar.className = "gig-actions";
  const back = document.createElement("button");
  back.type = "button";
  back.dataset.gigAction = "back";
  back.textContent = "Back";
  back.disabled = stepIndex === 0;
  bar.append(back);
  if (primary) {
    const next = document.createElement("button");
    next.type = "button";
    next.className = "gig-primary";
    next.dataset.gigAction = "next";
    next.textContent = primary;
    bar.append(next);
  }
  const exit = document.createElement("button");
  exit.type = "button";
  exit.dataset.gigAction = "exit";
  exit.textContent = "Exit gig check";
  bar.append(exit);
  return bar;
}

function doneScreen(payload: GigReport): DocumentFragment {
  const fragment = document.createDocumentFragment();
  fragment.append(heading("Done"));
  const art = document.createElement("div");
  art.id = "gig-ready-art";
  art.className = "gig-art-slot";
  art.dataset.slot = "gig-ready";
  art.setAttribute("aria-hidden", "true");
  const line = document.createElement("p");
  line.className = "gig-done";
  const crate = payload.scope?.crate_name || "the whole space";
  const lead = payload.ready ? "Ready for the gig" : "Not ready for the gig";
  line.textContent = `${lead}: ${payload.score}/100, checked ${crate} at ${checkedAt}`;
  fragment.append(art, line);
  const holding = (payload.holding_it_back || []).map((item) => item.summary);
  if (holding.length) fragment.append(detailsGroup("Holding it back", holding));
  fragment.append(actions(null));
  return fragment;
}
