/**
 * Quick-open: one box for tracks in the library and files on disk.
 *
 * Tracks are scored from the loaded library. Files come from
 * GET /api/files?q=, which is read-only. Enter opens the highlighted
 * row. Esc closes the box.
 */

import { readJSONOr } from "./api";
import type { FileEntry, FilesPayload, Track } from "./api-types";
import { copy, fill } from "./copy";
import { el } from "./dom";
import { scoreQuery } from "./fuzzy";
import { ROW, state } from "./state";
import { focusFileByPath, loadFolder, selectCrate, selectTrack, setMode } from "./views";
import { tip } from "./tips";

/** Wait before asking the disk, so a fast typist does not search every letter. */
export const QUICK_OPEN_MS = 200;

const LIMIT = 8;

interface TrackHit {
  kind: "track";
  key: string;
  title: string;
  detail: string;
  score: number;
  trackId: number;
}

interface FileHit {
  kind: "file";
  key: string;
  title: string;
  detail: string;
  score: number;
  path: string;
}

type QuickHit = TrackHit | FileHit;

let returnFocus: HTMLElement | null = null;
let timer = 0;
let requestToken = 0;
let hits: QuickHit[] = [];
let active = 0;
let phase: "idle" | "loading" | "ready" | "error" = "idle";
let truncated = false;
let pendingQuery = "";

/**
 * Return the parent folder of a track path.
 *
 * Windows drive roots keep their slash. A POSIX root is `/`.
 *
 * @param path File path from the file search.
 * @returns The folder that contains the file.
 */
export function parentDirectory(path: string): string {
  const slash = Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\"));
  if (slash < 0) return path;
  const parent = path.slice(0, slash);
  if (/^[A-Za-z]:$/.test(parent)) return `${parent}\\`;
  if (parent === "") return path.slice(0, slash + 1);
  return parent;
}

/**
 * Return whether the quick-open dialog is open.
 *
 * @returns True when the dialog is showing.
 */
export function quickOpenIsOpen(): boolean {
  return el("quick-open").open;
}

/**
 * Show the find box and focus its field.
 *
 * @returns {void}
 */
export function openQuickOpen(): void {
  const dialog = el("quick-open");
  if (dialog.open) return;
  returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  pendingQuery = "";
  hits = [];
  active = 0;
  phase = "idle";
  truncated = false;
  window.clearTimeout(timer);
  el("quick-open-query").value = "";
  el("quick-open-title").textContent = copy.quickOpenTitle;
  el("quick-open-label").textContent = copy.quickOpenLabel;
  el("quick-open-query").placeholder = copy.quickOpenPlaceholder;
  el("quick-open-close").textContent = copy.quickOpenClose;
  el("quick-open-retry").textContent = copy.quickOpenRetry;
  paint();
  dialog.showModal();
  el("quick-open-query").focus();
}

/**
 * Close the find box.
 *
 * Focus returns to the control that opened it.
 *
 * @returns {void}
 */
export function closeQuickOpen(): void {
  const dialog = el("quick-open");
  if (dialog.open) dialog.close();
}

/**
 * Attach quick-open listeners.
 *
 * Called from wireShortcuts after the page markup exists. Does not fetch
 * until the person types.
 *
 * @returns {void}
 */
export function wireQuickOpen(): void {
  const dialog = el("quick-open");
  dialog.addEventListener("keydown", onDialogKey);
  dialog.addEventListener("close", () => {
    window.clearTimeout(timer);
    const node = returnFocus;
    returnFocus = null;
    if (node && node.isConnected) node.focus();
  });
  el("quick-open-query").addEventListener("input", () => schedule());
  el("quick-open-close").addEventListener("click", () => closeQuickOpen());
  el("quick-open-retry").addEventListener("click", () => {
    const query = el("quick-open-query").value.trim();
    if (query) void loadFiles(query, trackHits(query));
  });
}

function onDialogKey(event: KeyboardEvent): void {
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

function schedule(): void {
  window.clearTimeout(timer);
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
  timer = window.setTimeout(() => {
    void loadFiles(query.trim(), tracks);
  }, QUICK_OPEN_MS);
}

async function loadFiles(query: string, tracks: TrackHit[]): Promise<void> {
  const token = ++requestToken;
  phase = "loading";
  try {
    const response = await fetch(`/api/files?q=${encodeURIComponent(query)}`);
    const payload = await readJSONOr<FilesPayload>(response, {});
    if (token !== requestToken) return;
    if (!response.ok) throw new Error(payload.error || copy.quickOpenFileError);
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

function trackHits(query: string): TrackHit[] {
  const text = query.trim();
  if (!text) return [];
  const found: TrackHit[] = [];
  for (const track of state.tracks) {
    const hit = scoreTrack(track, text);
    if (hit) found.push(hit);
  }
  found.sort(byScore);
  return found.slice(0, LIMIT);
}

function scoreTrack(track: Track, query: string): TrackHit | null {
  const title = track.name || "Untitled";
  const artist = track.artist ?? "";
  const album = track.album ?? "";
  const file = track.file ?? "";
  const score = scoreQuery(query, `${title} ${artist} ${album} ${file}`);
  if (score == null) return null;
  const detail = [artist, album].filter((part) => part !== "").join(" · ");
  return { kind: "track", key: `track:${track.id}`, title, detail, score, trackId: track.id };
}

function fileHits(payload: FilesPayload): FileHit[] {
  const rows = Array.isArray(payload.entries) ? payload.entries : [];
  const found: FileHit[] = [];
  for (const entry of rows) {
    if (!isFileEntry(entry)) continue;
    const score = typeof entry.score === "number" ? entry.score : 0;
    found.push({
      kind: "file",
      key: `file:${entry.path}`,
      title: entry.name,
      detail: entry.detail || entry.path,
      score,
      path: entry.path,
    });
  }
  found.sort(byScore);
  return found.slice(0, LIMIT);
}

function isFileEntry(value: unknown): value is FileEntry {
  if (!value || typeof value !== "object") return false;
  const row = value as FileEntry;
  return typeof row.name === "string" && typeof row.path === "string" && typeof row.kind === "string";
}

function mergeHits(tracks: TrackHit[], files: FileHit[]): QuickHit[] {
  return [...tracks, ...files].sort(byScore).slice(0, LIMIT * 2);
}

function byScore(left: QuickHit, right: QuickHit): number {
  return right.score - left.score || left.title.localeCompare(right.title);
}

async function activate(hit: QuickHit): Promise<void> {
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

function paint(): void {
  const status = el("quick-open-status");
  const list = el("quick-open-list");
  const retry = el("quick-open-retry");
  const query = pendingQuery.trim();
  retry.hidden = phase !== "error";
  list.replaceChildren();
  if (!query) status.textContent = copy.quickOpenEmpty;
  else if (phase === "loading") status.textContent = copy.quickOpenSearching;
  else if (phase === "error") status.textContent = copy.quickOpenFileError;
  else if (!hits.length) status.textContent = fill(copy.quickOpenNone, { query });
  else status.textContent = truncated ? copy.quickOpenTruncated : `${hits.length.toLocaleString()} matches`;
  hits.forEach((hit, index) => {
    const item = document.createElement("li");
    const button = document.createElement("button");
    tip(button, "quickOpenResult", hit.detail);
    button.type = "button";
    button.className = "quick-open-option";
    button.id = `quick-open-option-${index}`;
    button.setAttribute("role", "option");
    button.setAttribute("aria-selected", String(index === active));
    button.tabIndex = -1;
    if (index === active) button.classList.add("is-active");
    const kind = document.createElement("span");
    kind.className = "quick-open-kind";
    kind.textContent = hit.kind === "track" ? copy.quickOpenTrack : copy.quickOpenFile;
    const title = document.createElement("span");
    title.className = "quick-open-name";
    title.textContent = hit.title;
    title.title = hit.title;
    const detail = document.createElement("span");
    detail.className = "quick-open-detail";
    detail.textContent = hit.detail;
    button.append(kind, title, detail);
    button.addEventListener("click", () => {
      active = index;
      void activate(hit);
    });
    item.append(button);
    list.append(item);
  });
  const field = el("quick-open-query");
  const current = hits[active];
  if (current) field.setAttribute("aria-activedescendant", `quick-open-option-${active}`);
  else field.removeAttribute("aria-activedescendant");
  const chosen = list.querySelector<HTMLElement>(".is-active");
  if (chosen && typeof chosen.scrollIntoView === "function") chosen.scrollIntoView({ block: "nearest" });
}
