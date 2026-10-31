/**
 * Crates, history, missing tracks, duplicates, stems, and files.
 *
 * The functions paint from state and the elements in index.html. Nothing
 * in this module runs a request when the file is imported. Listeners are
 * attached by wireLibrary, which app.ts calls once at startup.
 */

import { failureOf, fetchLibraryRoots, isLibraryRoot, postJSON, readJSONOr } from "./api";
import type {
  CopyRow,
  Crate,
  DuplicatePayload,
  ErrorBody,
  FileCrumb,
  FileEntry,
  FileRoot,
  FilesPayload,
  HistoryPayload,
  LibraryPayload,
  RelatedPayload,
  RelatedTrack,
  SeratoStatus,
  Track,
} from "./api-types";
import { bridge } from "./bridge";
import { el } from "./dom";
import { clockLabel, colorHex, compare, durationLabel, sizeLabel } from "./format";
import { failSnapshots, loadSnapshots } from "./restore";
import { COLOR_NAMES, COLORS, FILE_ROW, ROOT_ROW, state } from "./state";
import { play } from "./player";
import { playerStrings } from "./player-strings";
import { paintRows } from "./virtual-scroll";
import { codedText, formatNumber, messageParams, serverMessage, t, type MessageKey } from "./i18n";
import { tip, type TipKey } from "./tips";

/**
 * Related-track request counter.
 *
 * A slow reply must not paint into a track the user has already left.
 * Incremented by loadRelated. Not sent anywhere.
 */
let relatedRequest = 0;
// Last track painted in the detail pane, so a language change can repaint it.
let lastDetail: Track | null = null;

/**
 * Return whether a track contains every search term.
 *
 * The haystack is title, artist, album, genre, key, and file. Terms are
 * already lowercased. An empty term list matches everything. No request
 * is made.
 *
 * @param {object} track Track or history row.
 * @param {string[]} terms Lowercased words from the search box.
 * @returns {boolean} True when every term occurs in the haystack.
 */
function matchesQuery(track: Track, terms: string[]) {
  if (!terms.length) return true;
  const hay = `${track.name} ${track.artist} ${track.album} ${track.genre} ${track.key} ${track.file}`.toLocaleLowerCase();
  return terms.every((term) => hay.includes(term));
}

/**
 * Split the track search box into lowercased words.
 *
 * Reads state.query, which the search field copies on each input event.
 * Does not fetch the library.
 *
 * @returns {string[]} Words with empty pieces removed.
 */
function queryTerms() {
  return state.query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
}

/**
 * Group crates by parent and sort each group.
 *
 * The sort follows the crate-sort control: library order, name, or date
 * added. A missing parent is grouped under 0 so those crates still appear.
 * Does not write the database or the DOM.
 *
 * @returns {Map<number, object[]>} Parent id to ordered child crates.
 */
function childLists() {
  const children = new Map<number | null, Crate[]>();
  for (const crate of state.crates) {
    const key = crate.parent ?? 0;
    if (!children.has(key)) children.set(key, []);
    const bucket = children.get(key);
    bucket!.push(crate);
  }
  for (const list of children.values()) {
    list.sort((a: Crate, b: Crate) => {
      if (state.crateSort === "name") {
        return a.name.localeCompare(b.name, undefined, { sensitivity: "base" }) || a.id - b.id;
      }
      if (state.crateSort === "added") return (b.added || 0) - (a.added || 0) || a.id - b.id;
      return (a.order as number) - (b.order as number) || a.id - b.id;
    });
  }
  return children;
}

/**
 * Return the crates that match the crate search, plus their parents.
 *
 * Parents stay so a matching child is not stranded without a path from
 * the root. A cycle in parent ids is stopped by the guard set. Null means
 * the search box is empty and every crate may show. Does not write.
 *
 * @returns {Set<number>|null} Crate ids to keep, or null when there is no query.
 */
function crateKeep() {
  const terms = state.crateQuery.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  if (!terms.length) return null;
  const byId = new Map(state.crates.map((crate) => [crate.id, crate]));
  const keep = new Set();
  for (const crate of state.crates) {
    if (!terms.every((term) => crate.name.toLocaleLowerCase().includes(term))) continue;
    let current: Crate | undefined = crate;
    const guard = new Set<number>();
    // guard stops a parent cycle from walking the same crate forever.
    while (current && !guard.has(current.id)) {
      guard.add(current.id);
      keep.add(current.id);
      current = byId.get(current.parent as number);
    }
  }
  return keep;
}

/**
 * Flatten the crate tree in the order the rail should show.
 *
 * A crate search expands every matching branch. Otherwise only crates
 * whose parent is in state.expanded are walked. Crates whose parent is
 * missing from the payload are listed at the root so they are not hidden.
 *
 * @returns {object[]} Crates with depth and childCount set for the rail.
 */
export function visibleCrates() {
  const children = childLists();
  const keep = crateKeep();
  const ordered = [];
  const seen = new Set();
  /**
   * Append one parent's visible children, then their open descendants.
   *
   * Nested inside visibleCrates. Skips an id already seen so a cycle cannot
   * recurse forever. Does not touch the database.
   *
   * @param {number} parent Parent crate id, or the space root id.
   * @param {number} depth Indent level, starting at 0 under the space root.
   * @returns {void}
   */
  function walk(parent: number | null, depth: number) {
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

/**
 * Open every ancestor of a crate so the selection stays on screen.
 *
 * Writes those ancestor ids into state.expanded. Stops if the parent
 * chain cycles. Does not tell the server; the click that selects the
 * crate saves the expanded flag separately.
 *
 * @param {number} id Crate whose parents should be expanded.
 * @returns {void}
 */
function expandAncestors(id: number | "all") {
  const byId = new Map(state.crates.map((crate) => [crate.id, crate]));
  let crate = id === "all" ? undefined : byId.get(id);
  const guard = new Set();
  while (crate && !guard.has(crate.id)) {
    guard.add(crate.id);
    const parent = byId.get(crate.parent as number);
    if (!parent) break;
    state.expanded.add(parent.id);
    crate = parent;
  }
}

/**
 * Find the visible ancestor of a crate the search has hidden.
 *
 * The rail marks that ancestor so the selection is not lost while the
 * child is filtered out. Returns null when the selection is All tracks
 * or the selected crate is already visible.
 *
 * @param {object[]} visible Crates currently listed.
 * @returns {number|null} Visible ancestor id, or null.
 */
function hiddenSelectionHolder(visible: Crate[]) {
  if (state.activeCrate === "all") return null;
  if (visible.some((crate) => crate.id === state.activeCrate)) return null;
  const byId = new Map(state.crates.map((crate) => [crate.id, crate]));
  const visibleIds = new Set(visible.map((crate) => crate.id));
  let crate = byId.get(state.activeCrate);
  const guard = new Set();
  while (crate && !guard.has(crate.id)) {
    guard.add(crate.id);
    crate = byId.get(crate.parent as number);
    if (crate && visibleIds.has(crate.id)) return crate.id;
  }
  return null;
}

/**
 * Return the tracks that belong to the current view before search.
 *
 * Missing, stems, duplicates, and a single crate each filter state.tracks.
 * All tracks and history are handled by the caller. Does not fetch.
 *
 * @returns {object[]} Tracks for the active mode.
 */
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

/**
 * Build the sorted rows the list will paint.
 *
 * History rows are reshaped so they share the columns of a track row.
 * The result is stored on state.view for the virtualized painter. Does
 * not contact the server.
 *
 * @returns {object[]} Rows after search and sort.
 */
export function buildView() {
  if (state.mode === "history") {
    const terms = queryTerms();
    const result = state.entries.filter((entry) => matchesQuery(entry, terms)).map((entry) => ({
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
      notes: entry.notes,
    } as Track));
    result.sort(compare);
    state.view = result;
    return result;
  }
  const terms = queryTerms();
  const result = modeTracks().filter((track) => matchesQuery(track, terms));
  result.sort(compare);
  state.view = result;
  return result;
}

/**
 * Build one crate-rail row, including its disclosure button.
 *
 * The row is a treeitem. A crate with children gets an expand button that
 * calls toggleCrate. Clicking the name calls selectCrate. Smart crates
 * are labeled. Nothing is written until those handlers run.
 *
 * @param {object} crate Crate fields, plus depth, childCount, and count.
 * @returns {HTMLDivElement} The row, not yet inserted.
 */
function crateRow(crate: {
  id: number | "all";
  name: string;
  depth?: number;
  childCount?: number;
  smart?: boolean;
  count?: number | null;
  parent?: number | null;
  color?: number | string | null;
  holds?: boolean;
}) {
  const row = document.createElement("div");
  row.className = "crate-row";
  if (crate.holds) row.classList.add("holds-selection");
  row.style.paddingLeft = `${(crate.depth as number) * 14}px`;

  if (crate.childCount) {
    const open = state.crateQuery ? true : state.expanded.has(crate.id);
    const twist = document.createElement("button");
    tip(twist, open ? "crateCollapse" : "crateExpand");
    twist.type = "button";
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

  const button = document.createElement("button");
  tip(button, "crateRow");
  button.type = "button";
  button.className = "crate";
  button.dataset.id = String(crate.id);
  if (crate.parent != null) button.dataset.parent = String(crate.parent);
  button.setAttribute("role", "treeitem");
  button.setAttribute("aria-level", String((crate.depth as number) + 1));
  button.setAttribute("aria-selected", String(state.activeCrate === crate.id));
  if (crate.childCount) {
    button.setAttribute("aria-expanded", String(state.crateQuery ? true : state.expanded.has(crate.id)));
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
  button.append(name);
  if (crate.smart) {
    const smart = document.createElement("span");
    smart.className = "smart";
    smart.textContent = t("crates.smartBadge");
    button.append(smart);
  }
  const meta = document.createElement("span");
  meta.className = "meta";
  meta.textContent = formatNumber(crate.count as number);
  button.append(meta);
  button.addEventListener("click", () => selectCrate(crate.id));
  row.append(button);
  return row;
}

/**
 * Keep one crate row tabbable after the rail is redrawn.
 *
 * The roving tabindex stays on the crate that had focus, or the first
 * crate when that id is gone. Does not move DOM focus by itself.
 *
 * @param {string|null} previousId data-id of the crate that held focus.
 * @returns {HTMLElement|null} The tabbable crate button, or null when the rail is empty.
 */
function placeCrateFocus(previousId: string | number | null) {
  const items = [...el("crate-list").querySelectorAll<HTMLButtonElement>(".crate")];
  if (!items.length) return null;
  const current = items.find((item) => item.dataset.id === previousId) || items[0];
  for (const item of items) item.tabIndex = item === current ? 0 : -1;
  return current;
}

/**
 * Redraw the crate rail and restore scroll and focus.
 *
 * Counts reflect the current track search. An All tracks row is always
 * first. Replaces the rail's children. Does not fetch or write the library.
 *
 * @returns {void}
 */
export function renderCrates() {
  const scroll = el("crate-list").scrollTop;
  const active = document.activeElement;
  const restore = el("crate-list").contains(active)
    ? active!.closest(".crate-row")?.querySelector<HTMLElement>(".crate")?.dataset.id ?? null
    : null;
  const terms = queryTerms();
  const matched = terms.length
    ? new Set(state.tracks.filter((track) => matchesQuery(track, terms)).map((track) => track.id))
    : null;
  const crates = visibleCrates();
  const holder = hiddenSelectionHolder(crates);
  el("crate-list").replaceChildren();

  el("crate-list").append(crateRow({
    id: "all",
    name: t("crates.allTracks"),
    depth: 0,
    childCount: 0,
    smart: false,
    count: matched ? matched.size : state.tracks.length,
  }));

  for (const crate of crates) {
    const members = state.crateTracks.get(crate.id) || new Set();
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
      holds: holder === crate.id,
    }));
  }
  const focused = placeCrateFocus(restore);
  if (restore && focused) focused.focus({ preventScroll: true });
  el("crate-list").scrollTop = scroll;
  renderRules();
}

/**
 * Show the smart-crate rule summary and its JSON editor.
 *
 * The editor is disabled while the library is locked. Saving posts the
 * JSON through saveRules. Removes any previous rule block first so a
 * crate change does not leave a stale editor.
 *
 * @returns {void}
 */
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
  const area = document.createElement("textarea");
  tip(area, "smartRules");
  area.value = JSON.stringify(crate.rules, null, 2);
  area.disabled = !state.writable;
  area.setAttribute("aria-label", t("rules.label"));
  const save = document.createElement("button");
  tip(save, "smartRulesSave");
  save.type = "button";
  save.className = "text-button";
  save.textContent = t("rules.save");
  save.disabled = !state.writable;
  save.addEventListener("click", () => saveRules(crate.id, area.value));
  editor.append(area, save);
  const bar = document.querySelector<HTMLElement>(".browser-bar")!;
  bar.after(editor);
  bar.after(line);
}

/**
 * Relabel the list headers for tracks or for history.
 *
 * History shows deck, played, and start time. Other views show BPM, key,
 * and length. The active sort is marked. Does not reorder rows; renderList
 * does that.
 *
 * @returns {void}
 */
function markHistoryColumns(): void {
  const history = state.mode === "history";
  document.querySelector(".columns")?.classList.toggle("for-history", history);
  el("list").classList.toggle("for-history", history);
}

export function renderColumns() {
  markHistoryColumns();
  const columns: Array<[string, MessageKey]> = state.mode === "history"
    ? [["name", "column.title"], ["artist", "column.artist"], ["deck", "column.deck"], ["played", "column.played"], ["start", "column.time"]]
    : [["name", "column.title"], ["artist", "column.artist"], ["bpm", "column.bpm"], ["key", "column.key"], ["length_ms", "column.time"]];
  const buttons = [...document.querySelectorAll<HTMLButtonElement>(".columns button")];
  columns.forEach(([key, label], index) => {
    const button = buttons[index]!;
    button.dataset.sort = key;
    button.textContent = t(label);
    button.dataset.active = String(button.dataset.sort === state.sort);
  });
}

/**
 * Show the controls and footer that belong to the current view.
 *
 * Hides crate tools outside the crate view, marks the selected view and
 * crate sort, and disables crate edits while Serato holds the lock. The
 * footer totals the tracks in the view, not the search result.
 *
 * @returns {void}
 */
export function renderShell() {
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
  for (const button of document.querySelectorAll<HTMLButtonElement>("#views button")) {
    button.setAttribute("aria-selected", String(button.dataset.view === state.mode));
  }
  for (const button of document.querySelectorAll<HTMLButtonElement>("[data-crate-sort]")) {
    button.setAttribute("aria-pressed", String(button.dataset.crateSort === state.crateSort));
  }
  const crateChosen = state.activeCrate !== "all";
  el("crate-new").disabled = !state.writable;
  el("crate-rename").disabled = !state.writable || !crateChosen;
  el("crate-color").disabled = !state.writable || !crateChosen;
  el("crate-delete").disabled = !state.writable || !crateChosen;
  syncMergeButton();
  if (filesMode) {
    if (state.filesAtRoots) {
      el("crate-foot").textContent = state.filesLoading
        ? t("files.readingRoots")
        : t("files.rootCount", { count: state.filesRoots.length });
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

/**
 * Return the tracks the footer should count for this view.
 *
 * Ignores the text search so the footer stays the size of the crate,
 * missing set, stem set, or duplicate set. History uses entries instead.
 *
 * @returns {object[]} Tracks included in the footer totals.
 */
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

/**
 * Refresh the shell, the count, and the visible rows.
 *
 * Selects the first row when the previous selection is no longer in the
 * view. History opens a session detail; other views fetch the track.
 * Does not itself request /api/library.
 *
 * @returns {void}
 */
export function renderList() {
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
    } else if (state.mode === "history") selectEntry(view[0]!.id);
    else selectTrack(view[0]!.id);
  }
}

/**
 * Expand or collapse a crate and save that flag when edits are allowed.
 *
 * A crate search forces every match open, so the twist does nothing then.
 * The POST goes to /api/crate with action expanded. A 409 means Serato
 * took the lock and the page stops offering writes.
 *
 * @param {number|string} id Crate id.
 * @returns {void}
 */
export function toggleCrate(id: number | "all") {
  if (state.crateQuery) return;
  if (state.expanded.has(id)) state.expanded.delete(id);
  else state.expanded.add(id);
  renderCrates();
  if (!state.writable) return;
  postJSON("/api/crate", {
    action: "expanded",
    id,
    expanded: state.expanded.has(id),
    space: state.space,
  }).then((result) => {
    if (result.warning) setNotice(result.warning);
  }).catch((error) => {
    if (failureOf(error).status === 409) lockDown(error);
    else setNotice(failureOf(error).message);
  });
}

/**
 * Show one crate, or all tracks, and scroll the list to the top.
 *
 * Opens ancestor crates so the selection is visible. Does not write the
 * database; membership changes go through the detail pane.
 *
 * @param {number|string} id Crate id, or "all".
 * @returns {void}
 */
export function selectCrate(id: number | "all") {
  state.activeCrate = id;
  if (id !== "all") expandAncestors(id);
  el("list").scrollTop = 0;
  renderList();
}

/**
 * Move the roving tabindex and DOM focus to one crate button.
 *
 * Used by the rail's arrow keys. Does nothing when item is missing.
 *
 * @param {HTMLElement|undefined|null} item Crate button to focus.
 * @returns {void}
 */
export function focusCrateItem(item: HTMLElement | undefined) {
  if (!item) return;
  for (const button of el("crate-list").querySelectorAll<HTMLButtonElement>(".crate")) button.tabIndex = -1;
  item.tabIndex = 0;
  item.focus();
}

/**
 * Load one track's detail and ignore a response that lost the race.
 *
 * Increments state.request so a slow reply cannot overwrite a newer
 * selection. GET /api/track reads the row, its crates, and the cue tags.
 * The list selection is painted immediately.
 *
 * @param {number} id Asset id.
 * @returns {Promise<void>}
 */
export async function selectTrack(id: number) {
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
    const payload = await readJSONOr<Track & ErrorBody>(response, {} as Track & ErrorBody);
    if (!response.ok) throw new Error(serverMessage(payload, t("detail.readFailed", { status: String(response.status) })));
    if (token !== state.request) return;
    if (payload.serato) applyStatus(payload.serato);
    renderDetail(payload);
  } catch (error) {
    if (token !== state.request) return;
    const failure = document.createElement("p");
    failure.className = "detail-error";
    failure.textContent = failureOf(error).message;
    el("detail").replaceChildren(failure);
  }
}

/**
 * Show one history entry in the detail pane.
 *
 * History entries are already loaded with the session, so this does not
 * fetch. An entry that still has an asset id can be opened in the library.
 *
 * @param {number} id History entry id.
 * @returns {void}
 */
export function selectEntry(id: number) {
  state.selectedId = id;
  paintRows();
  const entry = state.entries.find((item) => item.id === id);
  if (!entry) return;
  const body = document.createElement("div");
  body.className = "detail-body";
  const title = document.createElement("h2");
  title.textContent = entry.name || t("track.untitled");
  body.append(title);
  if (entry.artist) {
    const artist = document.createElement("p");
    artist.className = "artist";
    artist.textContent = entry.artist;
    body.append(artist);
  }
  const lines: Array<[string, string]> = [
    [t("column.played"), entry.played ? t("common.yes") : t("common.no")],
    [t("column.deck"), entry.deck || "—"],
    [t("history.started"), clockLabel(entry.start_time) || "—"],
    [t("history.file"), entry.file || "—"],
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
    const open = document.createElement("button");
    tip(open, "openInLibrary");
    open.type = "button";
    open.className = "text-button";
    open.textContent = t("history.openInLibrary");
    open.addEventListener("click", () => openInLibrary(entry.asset_id as number));
    body.append(open);
  }
  el("detail").replaceChildren(body);
}

/**
 * Build one labeled editor control for a track field.
 *
 * Comments use a textarea. BPM asks for a decimal keyboard. The control
 * name matches the field save_track accepts. Nothing is saved until the
 * form is submitted.
 *
 * @param {string} name Field name.
 * @param {string} label Visible label.
 * @param {string|number|null|undefined} value Current value.
 * @param {boolean} [wide=false] True when the control spans the pane.
 * @returns {HTMLLabelElement} The labeled control.
 */
function fieldInput(name: string, label: string, value: string | number | null | undefined, tipKey: TipKey, wide: boolean = false) {
  const wrap = document.createElement("label");
  if (wide) wrap.className = "wide";
  wrap.append(document.createTextNode(label));
  const input = name === "comments"
    ? document.createElement("textarea")
    : document.createElement("input");
  tip(input, tipKey);
  input.name = name;
  input.value = String(value ?? "");
  if (name === "bpm") input.inputMode = "decimal";
  wrap.append(input);
  return wrap;
}

/**
 * Fill the detail pane from a /api/track payload.
 *
 * The form edits the fields save_track accepts. Controls stay disabled
 * while the library is locked. Reveal, Prepare, relocate, and remove call
 * the matching POST routes. Related tracks load from /api/related. Cue
 * data is shown and is not written back.
 *
 * @param {object} track Payload from GET /api/track.
 * @returns {void}
 */
function renderDetail(track: Track) {
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
  const title = document.createElement("h2");
  title.textContent = track.title ?? "";
  body.append(title);
  if (track.artist) {
    const artist = document.createElement("p");
    artist.className = "artist";
    artist.textContent = track.artist ?? "";
    body.append(artist);
  }

  const playButton = document.createElement("button");
  tip(playButton, "rowPlay");
  playButton.type = "button";
  playButton.className = "detail-play";
  const playTitle = track.title || track.name || playerStrings.untitled;
  playButton.textContent = playerStrings.play;
  playButton.setAttribute("aria-label", `${playerStrings.play} ${playTitle}`);
  playButton.addEventListener("click", () => {
    play(track.id);
  });
  body.append(playButton);

  const deck = document.createElement("div");
  deck.className = "deck";
  const facts: Array<[MessageKey, string | number | null | undefined]> = [["column.bpm", track.bpm], ["column.key", track.key || "—"], ["column.time", track.length]];
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
  const editorFields: Array<[string, MessageKey, TipKey, boolean]> = [
    ["name", "column.title", "trackTitle", true],
    ["artist", "column.artist", "trackArtist", false],
    ["album", "field.album", "trackAlbum", false],
    ["genre", "field.genre", "trackGenre", false],
    ["year", "field.year", "trackYear", false],
    ["composer", "field.composer", "trackComposer", false],
    ["remixer", "field.remixer", "trackRemixer", false],
    ["label", "field.label", "trackLabel", false],
    ["grouping", "field.grouping", "trackGrouping", false],
    ["key", "column.key", "trackKey", false],
    ["bpm", "column.bpm", "trackBpm", false],
    ["emoji", "field.emoji", "trackEmoji", false],
    ["comments", "field.comments", "trackComments", true],
  ];
  for (const [name, label, tipKey, wide] of editorFields) {
    form.append(fieldInput(name, t(label), String(edit[name] ?? ""), tipKey, wide));
  }

  const colorLabel = document.createElement("label");
  colorLabel.append(document.createTextNode(t("field.color")));
  const colorSelect = document.createElement("select");
  tip(colorSelect, "trackColor");
  colorSelect.name = "color";
  const currentColor = Number(edit.color ?? 0xffffff);
  const palette: Array<[number, string]> = COLORS.map(([value, key]) => [value, t(key)]);
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
  const ratingSelect = document.createElement("select");
  tip(ratingSelect, "trackRating");
  ratingSelect.name = "rating";
  const ratings: Array<[string, string]> = [
    ["", t("rating.none")],
    ...([["0.2", 1], ["0.4", 2], ["0.6", 3], ["0.8", 4], ["1", 5]] as const).map(([value, stars]): [string, string] => [value, t("rating.stars", { count: stars })]),
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
  const lockInput = document.createElement("input");
  tip(lockInput, "trackGridLock");
  lockInput.type = "checkbox";
  lockInput.name = "is_beatgrid_locked";
  lockInput.checked = Boolean(edit.is_beatgrid_locked);
  lock.append(lockInput, document.createTextNode(t("field.beatgridLocked")));
  form.append(lock);

  const save = document.createElement("button");
  tip(save, "trackSave");
  save.type = "submit";
  save.className = "text-button wide";
  save.textContent = t("detail.saveTrack");
  form.append(save);
  for (const control of form.querySelectorAll<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement | HTMLButtonElement>("input, select, textarea, button")) control.disabled = !writable;
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    saveTrack(track.id, form);
  });
  body.append(form);

  const actions = document.createElement("div");
  actions.className = "actions";
  const reveal = document.createElement("button");
  tip(reveal, "trackReveal");
  reveal.type = "button";
  const manager = track.serato?.file_manager || state.serato?.file_manager || "Finder";
  reveal.textContent = t("detail.reveal", { manager });
  reveal.disabled = !track.file_on_disk;
  reveal.addEventListener("click", () => revealTrack(track.id));
  const prepare = document.createElement("button");
  tip(prepare, track.in_prepare ? "prepareRemove" : "prepareSend");
  prepare.type = "button";
  prepare.textContent = track.in_prepare ? t("detail.removePrepare") : t("detail.sendPrepare");
  prepare.disabled = !writable;
  prepare.addEventListener("click", () => prepareTrack(track.id, !track.in_prepare));
  const relocate = document.createElement("button");
  tip(relocate, "trackRelocate");
  relocate.type = "button";
  relocate.textContent = t("detail.relocate");
  relocate.disabled = !writable;
  relocate.addEventListener("click", () => relocateTrack(track));
  const remove = document.createElement("button");
  tip(remove, "trackRemove");
  remove.type = "button";
  remove.textContent = t("detail.removeFromLibrary");
  remove.disabled = !writable;
  remove.addEventListener("click", () => removeTrack(track.id));
  actions.append(reveal, prepare, relocate, remove);
  if (state.mode === "duplicates" && selectedDuplicateGroup()) {
    const merge = document.createElement("button");
    tip(merge, "mergeCopies");
    merge.type = "button";
    merge.textContent = t("merge.title");
    merge.disabled = !writable;
    merge.addEventListener("click", () => {
      bridge.openMergeDialog().catch((error) => setNotice(failureOf(error).message));
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
      const toggle = document.createElement("button");
      tip(toggle, "searchCopies");
      toggle.type = "button";
      toggle.className = "text-button";
      toggle.textContent = t("detail.searchCopies", { count: group.fields.length });
      let shown = false;
      section.hidden = true;
      toggle.addEventListener("click", () => {
        shown = !shown;
        section.hidden = !shown;
        toggle.textContent = shown ? t("detail.hideSearchCopies") : t("detail.searchCopies", { count: group.fields.length });
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

/**
 * Build the cue, loop, flip, and beatgrid section.
 *
 * The copy says the markers were read from the audio file and are not
 * written back. A missing file is explained instead of showing an empty
 * success. Does not fetch.
 *
 * @param {object} track Track payload including cues, loops, flips, and beatgrid.
 * @returns {HTMLElement} The section, not yet inserted.
 */
function markerSection(track: Track) {
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
  /**
   * Format a cue or loop time as m:ss.sss.
   *
   * Nested in markerSection. Three decimal places keep a cue distinguishable
   * inside one second. Does not read the file again.
   *
   * @param {number|string} value Time in milliseconds.
   * @returns {string} Minutes, seconds, and milliseconds.
   */
  const ms = (value: number | string | null | undefined) => {
    const total = Number(value) / 1000;
    const minutes = Math.floor(total / 60);
    return `${minutes}:${(total - minutes * 60).toFixed(3).padStart(6, "0")}`;
  };
  /**
   * Format a beatgrid position for the panel.
   *
   * Nested in markerSection. Three decimal places hide the binary noise in
   * a stored float, such as 1.2300000190734863. The export does not use
   * this string. A value that is not a finite number is left blank.
   *
   * @param {number|string} value Position in seconds.
   * @returns {string} Seconds with three decimal places, plus "s".
   */
  const beatSeconds = (value: number | string | null | undefined) => {
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
    name.textContent = cue.name || t("markers.cue", { number: (cue.index as number) + 1 });
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
    name.textContent = loop.name || t(loop.locked ? "markers.loopLocked" : "markers.loop", { number: (loop.index as number) + 1 });
    row.append(swatch, time, name);
    section.append(row);
  }
  for (const flip of track.flips || []) {
    const row = document.createElement("div");
    row.className = "marker";
    const time = document.createElement("span");
    time.textContent = flip.enabled ? t("common.on") : t("common.off");
    const name = document.createElement("span");
    name.textContent = flip.name || t("markers.flip", { number: (flip.index as number) + 1 });
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

/**
 * List other copies of this track and let a click select one.
 *
 * Copies share title, artist, and whole-second length. Selecting one
 * calls selectTrack, which fetches that asset. This builder only creates
 * the nodes.
 *
 * @param {object[]} copies Copy summaries from the track payload.
 * @returns {HTMLElement} The section.
 */
function copySection(copies: CopyRow[]) {
  const section = document.createElement("section");
  section.className = "group";
  const heading = document.createElement("h3");
  heading.textContent = t("copies.heading");
  section.append(heading);
  for (const copy of copies) {
    const row = document.createElement("div");
    row.className = "copy-row";
    const button = document.createElement("button");
    tip(button, "duplicateCopy");
    button.type = "button";
    button.className = "text-button";
    button.textContent = copy.file || t("track.numbered", { id: String(copy.id) });
    button.addEventListener("click", () => selectTrack(copy.id as number));
    const rate = document.createElement("span");
    rate.textContent = copy.bitrate == null ? "" : String(copy.bitrate);
    const plays = document.createElement("span");
    plays.textContent = copy.play_count == null ? "" : String(copy.play_count);
    const crates = document.createElement("span");
    crates.textContent = copy.missing ? "missing" : (copy.crates || "");
    row.append(button, rate, plays, crates);
    section.append(row);
  }
  return section;
}

/**
 * Build the related-tracks section and start its request.
 *
 * The section lists saved links, a search box that links another track,
 * and suggestions. Saving a link writes the sidecar file and does not
 * require Serato to be quit. The Serato crate button does. Text from the
 * server is assigned with textContent.
 *
 * @param {object} track Track payload from GET /api/track.
 * @param {boolean} writable False disables the Serato crate button.
 * @returns {HTMLElement} The section, with a loading line until the reply arrives.
 */
function relatedSection(track: Track, writable: boolean) {
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

/**
 * Fetch related tracks for the open track.
 *
 * GET /api/related uses the resolved path. A reply for an older selection
 * is ignored. Does not write the Serato library.
 *
 * @param {object} track Track payload.
 * @param {HTMLElement} section Section built by relatedSection.
 * @param {boolean} writable False disables the Serato crate button.
 * @param {string} query Search text to keep after a refresh.
 * @returns {Promise<void>}
 */
async function loadRelated(track: Track, section: HTMLElement, writable: boolean, query: string) {
  const token = ++relatedRequest;
  const path = track.resolved_path || track.edit?.portable_id || "";
  const params = new URLSearchParams({ path, space: state.space });
  try {
    const response = await fetch(`/api/related?${params}`);
    const payload = await readJSONOr<RelatedPayload>(response, {});
    if (token !== relatedRequest || !section.isConnected) return;
    if (!response.ok) throw new Error(serverMessage(payload, t("related.loadFailed")));
    renderRelated(track, section, writable, payload, query);
  } catch (error) {
    if (token !== relatedRequest || !section.isConnected) return;
    section.setAttribute("aria-busy", "false");
    const status = section.querySelector("[role=status]");
    if (status) status.textContent = failureOf(error).message;
  }
}

/**
 * Paint saved links, the link form, and suggestions.
 *
 * Replaces the section body except the heading. Notes and titles are
 * text, not HTML. Does not fetch.
 *
 * @param {object} track Open track.
 * @param {HTMLElement} section Related section.
 * @param {boolean} writable False disables the Serato crate button.
 * @param {object} payload GET /api/related body.
 * @param {string} query Search text to restore.
 * @returns {void}
 */
function renderRelated(track: Track, section: HTMLElement, writable: boolean, payload: RelatedPayload, query: string) {
  const heading = section.querySelector("h3");
  section.replaceChildren(heading!);
  section.setAttribute("aria-busy", "false");
  const saved = Array.isArray(payload.saved) ? payload.saved : [];
  const suggested = Array.isArray(payload.suggested) ? payload.suggested : [];
  const status = document.createElement("p");
  status.className = "detail-kicker";
  status.setAttribute("role", "status");
  status.textContent = saved.length
    ? t("related.savedCount", { count: saved.length })
    : t("related.noneSaved");
  section.append(status);
  if (saved.length) section.append(relatedSavedList(track, section, saved));

  section.append(relatedSearch(track, section, query));

  const suggestHeading = document.createElement("p");
  suggestHeading.className = "detail-kicker";
  suggestHeading.textContent = suggested.length
    ? t("related.suggested")
    : t("related.noSuggestions");
  section.append(suggestHeading);
  if (suggested.length) section.append(relatedSuggestList(track, section, suggested));

  const crate = document.createElement("button");
  tip(crate, "relatedCrate");
  crate.type = "button";
  crate.className = "text-button";
  crate.dataset.relatedCrate = "true";
  const crateName = payload.crate_name || "Related";
  crate.textContent = t("related.updateCrate");
  crate.disabled = !writable;
  crate.addEventListener("click", () => refreshRelatedCrate(track, section));
  const crateNote = document.createElement("p");
  crateNote.className = "detail-kicker";
  crateNote.textContent = writable
    ? t("related.crateNote", { name: crateName })
    : t("related.quitSerato");
  section.append(crate, crateNote);
}

/**
 * List saved links with a remove button.
 *
 * A track that is still in the library opens when its name is clicked.
 * Does not fetch until the user removes a link.
 *
 * @param {object} track Open track.
 * @param {HTMLElement} section Related section.
 * @param {object[]} saved Saved link objects.
 * @returns {HTMLElement} The list.
 */
function relatedSavedList(track: Track, section: HTMLElement, saved: RelatedTrack[]) {
  const list = document.createElement("ul");
  list.className = "related-list";
  for (const link of saved) {
    const item = document.createElement("li");
    item.className = "related-row";
    const main = document.createElement("div");
    const other = link.track || {};
    const label = other.title || t("track.untitled");
    if (other.asset_id != null && other.in_library) {
      const open = document.createElement("button");
      tip(open, "relatedOpen");
      open.type = "button";
      open.className = "text-button";
      open.textContent = label;
      open.addEventListener("click", () => selectTrack(other.asset_id as number));
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
    const remove = document.createElement("button");
    tip(remove, "relatedRemove");
    remove.type = "button";
    remove.className = "text-button";
    remove.textContent = t("common.remove");
    remove.setAttribute("aria-label", t("related.removeLink", { name: label }));
    remove.addEventListener("click", () => removeRelated(track, section, link));
    item.append(main, remove);
    list.append(item);
  }
  return list;
}

/**
 * Build the search box used to link another track.
 *
 * Matches the tracks already loaded in this space. Choosing one reveals
 * the note, rating, and two-way controls. Does not fetch.
 *
 * @param {object} track Open track.
 * @param {HTMLElement} section Related section.
 * @param {string} query Current search text.
 * @returns {HTMLElement} The search block.
 */
function relatedSearch(track: Track, section: HTMLElement, query: string) {
  const block = document.createElement("div");
  block.className = "related-search";
  const label = document.createElement("label");
  label.append(document.createTextNode(t("related.find")));
  const input = document.createElement("input");
  tip(input, "relatedSearch");
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

  /**
   * Show matches for the current search text.
   *
   * Nested in relatedSearch. An empty box explains what to type. Does
   * not fetch.
   *
   * @returns {void}
   */
  const paint = () => {
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
    const hits = state.tracks
      .filter((item) => item.id !== track.id && matchesQuery(item, terms))
      .slice(0, 8);
    if (!hits.length) {
      const empty = document.createElement("li");
      empty.className = "related-meta";
      empty.textContent = t("list.noMatches");
      results.append(empty);
      return;
    }
    for (const hit of hits) {
      const item = document.createElement("li");
      const choose = document.createElement("button");
      tip(choose, "relatedChoose");
      choose.type = "button";
      choose.className = "text-button";
      choose.textContent = hit.artist ? `${hit.name || t("track.untitled")} · ${hit.artist}` : (hit.name || t("track.untitled"));
      choose.addEventListener("click", () => relatedLinkForm(track, section, form, hit, input.value));
      item.append(choose);
      results.append(item);
    }
  };
  input.addEventListener("input", paint);
  paint();
  return block;
}

/**
 * Show the note, rating, and direction controls for one chosen track.
 *
 * Save posts /api/related. The default direction is two-way. Does not
 * fetch until Save is clicked.
 *
 * @param {object} track Open track.
 * @param {HTMLElement} section Related section.
 * @param {HTMLElement} form Form container inside the search block.
 * @param {object} hit Track from the library list.
 * @param {string} query Search text to restore after a save.
 * @returns {void}
 */
function relatedLinkForm(track: Track, section: HTMLElement, form: HTMLElement, hit: RelatedTrack, query: string) {
  form.hidden = false;
  form.replaceChildren();
  const chosen = document.createElement("p");
  chosen.className = "related-meta";
  chosen.textContent = hit.artist ? `${hit.name || t("track.untitled")} · ${hit.artist}` : (hit.name || t("track.untitled"));
  const noteLabel = document.createElement("label");
  noteLabel.append(document.createTextNode(t("related.note")));
  const note = document.createElement("input");
  tip(note, "relatedNote");
  note.type = "text";
  note.maxLength = 500;
  note.placeholder = t("related.notePlaceholder");
  noteLabel.append(note);
  const ratingLabel = document.createElement("label");
  ratingLabel.append(document.createTextNode(t("related.linkRating")));
  const rating = document.createElement("select");
  tip(rating, "relatedRating");
  for (const [value, text] of [["", t("rating.none")], ["1", "1"], ["2", "2"], ["3", "3"], ["4", "4"], ["5", "5"]] as Array<[string, string]>) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = text;
    rating.append(option);
  }
  ratingLabel.append(rating);
  const mutualLabel = document.createElement("label");
  mutualLabel.className = "check";
  const mutual = document.createElement("input");
  tip(mutual, "relatedMutual");
  mutual.type = "checkbox";
  mutual.checked = true;
  mutualLabel.append(mutual, document.createTextNode(t("related.twoWayLink")));
  const save = document.createElement("button");
  tip(save, "relatedSave");
  save.type = "button";
  save.className = "text-button";
  save.textContent = t("related.saveLink");
  save.addEventListener("click", () => {
    save.disabled = true;
    saveRelated(track, section, {
      action: "add",
      asset: track.id,
      target: hit.id,
      mutual: mutual.checked,
      note: note.value,
      rating: rating.value === "" ? null : Number(rating.value),
      space: state.space,
    }, query);
  });
  form.append(chosen, noteLabel, ratingLabel, mutualLabel, save);
}

/**
 * List suggestions with a one-click save.
 *
 * Each Save posts a two-way link with no note and no rating. Does not
 * fetch until Save is clicked.
 *
 * @param {object} track Open track.
 * @param {HTMLElement} section Related section.
 * @param {object[]} suggested Suggestion objects.
 * @returns {HTMLElement} The list.
 */
function relatedSuggestList(track: Track, section: HTMLElement, suggested: RelatedTrack[]) {
  const list = document.createElement("ul");
  list.className = "related-list";
  for (const item of suggested) {
    const row = document.createElement("li");
    row.className = "related-row";
    const main = document.createElement("div");
    const name = document.createElement("span");
    name.textContent = item.artist ? `${item.title || t("track.untitled")} · ${item.artist}` : (item.title || t("track.untitled"));
    const reasons = document.createElement("p");
    reasons.className = "related-meta";
    reasons.textContent = Array.isArray(item.reasons) ? item.reasons.join(" · ") : "";
    main.append(name, reasons);
    const save = document.createElement("button");
    tip(save, "relatedSuggestionSave");
    save.type = "button";
    save.className = "text-button";
    save.textContent = t("common.save");
    save.setAttribute("aria-label", t("related.saveLinkTo", { name: item.title || t("track.untitled") }));
    save.addEventListener("click", () => {
      save.disabled = true;
      saveRelated(track, section, {
        action: "add",
        asset: track.id,
        target: item.asset_id,
        mutual: true,
        note: "",
        rating: null,
        space: state.space,
      }, "");
    });
    row.append(main, save);
    list.append(row);
  }
  return list;
}

/**
 * POST a new related-track link and reload the section.
 *
 * The body is the add action. A failure stays in the section status and
 * the notice. Titles and paths are not added to the request beyond the
 * asset ids the server already knows.
 *
 * @param {object} track Open track.
 * @param {HTMLElement} section Related section.
 * @param {object} body POST /api/related body.
 * @param {string} query Search text to restore.
 * @returns {Promise<void>}
 */
async function saveRelated(track: Track, section: HTMLElement, body: Record<string, unknown>, query: string) {
  try {
    await postJSON("/api/related", body);
    setNotice(t("related.saved"));
    const kept = section.querySelector<HTMLInputElement>(".related-search input");
    await loadRelated(track, section, Boolean(track.serato?.writable && state.writable), kept ? kept.value : query);
  } catch (error) {
    if (failureOf(error).status === 409) lockDown(error);
    else setNotice(failureOf(error).message);
    const status = section.querySelector("[role=status]");
    if (status) status.textContent = failureOf(error).message;
  }
}

/**
 * Remove one saved link after a confirmation.
 *
 * POST /api/related with action remove. The audio file and the Serato
 * library are not changed.
 *
 * @param {object} track Open track.
 * @param {HTMLElement} section Related section.
 * @param {object} link Saved link, including its id and track title.
 * @returns {Promise<void>}
 */
async function removeRelated(track: Track, section: HTMLElement, link: RelatedTrack) {
  const label = link.track?.title || t("related.thisTrack");
  if (!confirm(t("related.confirmRemove", { name: label }))) return;
  try {
    await postJSON("/api/related", { action: "remove", id: link.id });
    setNotice(t("related.removed"));
    const kept = section.querySelector<HTMLInputElement>(".related-search input");
    await loadRelated(track, section, Boolean(track.serato?.writable && state.writable), kept ? kept.value : "");
  } catch (error) {
    setNotice(failureOf(error).message);
  }
}

/**
 * Create or refresh the Serato crate for this track's saved links.
 *
 * POST /api/related with action crate. Serato must be quit. A 409 locks
 * the page the same way other library writes do.
 *
 * @param {object} track Open track.
 * @param {HTMLElement} section Related section.
 * @returns {Promise<void>}
 */
async function refreshRelatedCrate(track: Track, section: HTMLElement) {
  const button = section.querySelector<HTMLButtonElement>("[data-related-crate]");
  if (button) button.disabled = true;
  try {
    const result = await postJSON("/api/related", { action: "crate", asset: track.id, space: state.space });
    setNotice(result.warning || t("related.crateUpdated", { name: String(result.name ?? "") }));
    await loadLibrary();
    selectTrack(track.id);
  } catch (error) {
    if (failureOf(error).status === 409) {
      lockDown(error);
      if (button) button.disabled = true;
    } else {
      setNotice(failureOf(error).message);
      if (button) button.disabled = !state.writable;
    }
  }
}

/**
 * List normal crates as checkboxes and name the smart crates.
 *
 * Checking a box posts an add or remove. Smart crates are shown but not
 * edited here because their membership comes from rules. The list is
 * built from state.crates, not from a new request.
 *
 * @param {object} track Track payload with crate_ids.
 * @param {boolean} writable False disables every checkbox.
 * @returns {HTMLElement} The section.
 */
function membershipSection(track: Track, writable: boolean) {
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
    const input = document.createElement("input");
    tip(input, "crateMember");
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

/**
 * Paint the library screen again in the active language.
 *
 * Repaints the shell, list headers, crates, rows, files, history
 * sessions, and the open detail pane from what the page already has.
 * The library is not fetched again. The related-tracks list in the
 * detail pane is read again from GET /api/related.
 *
 * @returns {void}
 */
export function repaintViews(): void {
  // The static markup pass resets the status line, so put the server's back.
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

/**
 * Show or hide the notice line above the track list.
 *
 * An empty string hides it. Used for save warnings and request errors.
 * Does not change the library.
 *
 * @param {string} text Notice text.
 * @returns {void}
 */
export function setNotice(text: string) {
  el("notice").textContent = text || "";
  el("notice").hidden = !text;
}

/**
 * Store the lock status and refresh the controls that depend on it.
 *
 * state.writable gates every edit. The status line repeats the server's
 * message, including which file manager Reveal will use.
 *
 * @param {object|null|undefined} info Status payload from /api/status or a library response.
 * @returns {void}
 */
/**
 * The rail status line, in the active language.
 *
 * A notice with a code is translated. `params` fill its placeholders, so
 * the unknown Serato version names the build in Spanish and in the
 * pseudo-locale. A sentence without a code stays as the server sent it.
 *
 * @param info Status payload. Null before the server answers.
 * @returns The text for `#status`.
 */
export function statusLine(info: SeratoStatus | null | undefined): string {
  if (info?.code) return codedText(info.message || t("status.library"), info.code, messageParams(info.params));
  return info?.message || t("status.library");
}

export function applyStatus(info: SeratoStatus | null | undefined) {
  state.serato = info;
  state.writable = Boolean(info?.writable);
  el("status").textContent = statusLine(info);
  renderShell();
}

/**
 * Stop offering writes after Serato takes the database lock.
 *
 * A 409 carries a serato object. The page applies that status and shows
 * the error. Later saves stay disabled until a reload says the lock is gone.
 *
 * @param {Error & {payload?: object, message: string}} error Failed write.
 * @returns {void}
 */
export function lockDown(error: unknown) {
  const failed = failureOf(error);
  applyStatus(failed.payload?.serato || { writable: false, message: failed.message });
  setNotice(failed.message);
}

/**
 * Save the detail form through POST /api/track.
 *
 * Empty BPM is stored as null. A BPM that is not a number is refused in
 * the page before the request. On success the library is reloaded and the
 * same track is selected again. A 409 locks the page.
 *
 * @param {number} id Asset id.
 * @param {HTMLFormElement} form Editor form built by renderDetail.
 * @returns {Promise<void>}
 */
async function saveTrack(id: number, form: HTMLFormElement) {
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
    is_beatgrid_locked: form.querySelector<HTMLInputElement>("[name=is_beatgrid_locked]")!.checked,
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
  } catch (error) {
    if (failureOf(error).status === 409) lockDown(error);
    else setNotice(failureOf(error).message);
  }
}

/**
 * Ask the server to show the audio file in the host file manager.
 *
 * POST /api/reveal. The server runs Finder on macOS and File Explorer on
 * Windows. A missing file is reported in the notice. The database is not
 * modified.
 *
 * @param {number} id Asset id.
 * @returns {Promise<void>}
 */
async function revealTrack(id: number) {
  try {
    await postJSON("/api/reveal", { id });
  } catch (error) {
    setNotice(failureOf(error).message);
  }
}

/**
 * Add or remove a track in the Prepare space.
 *
 * POST /api/crate with action prepare. Reloads the library afterwards.
 * A 409 locks the page. The audio file stays where it is.
 *
 * @param {number} id Asset id.
 * @param {boolean} add True adds the track. False removes it from Prepare.
 * @returns {Promise<void>}
 */
async function prepareTrack(id: number, add: boolean) {
  try {
    const result = await postJSON("/api/crate", { action: "prepare", asset: id, add, space: state.space });
    setNotice(result.warning || (add ? t("detail.sentPrepare") : t("detail.removedPrepare")));
    await loadLibrary();
    selectTrack(id);
  } catch (error) {
    if (failureOf(error).status === 409) lockDown(error);
    else setNotice(failureOf(error).message);
  }
}

/**
 * Point a library row at a different audio path.
 *
 * Prompts for a path and posts it as portable_id. The server accepts the
 * path only when that file exists, and it stores a home-relative id when
 * it can. A 409 locks the page.
 *
 * @param {object} track Track payload. The prompt starts from its resolved path.
 * @returns {Promise<void>}
 */
async function relocateTrack(track: Track) {
  const path = prompt(t("detail.relocatePrompt"), track.resolved_path || track.edit?.portable_id || "");
  if (!path) return;
  try {
    const result = await postJSON("/api/track", {
      id: track.id,
      space: state.space,
      fields: { portable_id: path },
    });
    setNotice(result.warning || t("detail.relocated"));
    await loadLibrary();
    selectTrack(track.id);
  } catch (error) {
    if (failureOf(error).status === 409) lockDown(error);
    else setNotice(failureOf(error).message);
  }
}

/**
 * Remove a track from this space after a confirmation.
 *
 * POST /api/crate with action remove_library. The audio file stays on
 * disk. The selection is cleared and the list reloads. A 409 locks the page.
 *
 * @param {number} id Asset id.
 * @returns {Promise<void>}
 */
async function removeTrack(id: number) {
  if (!confirm(t("detail.confirmRemove"))) return;
  try {
    const result = await postJSON("/api/crate", { action: "remove_library", asset: id, space: state.space });
    setNotice(result.warning || t("detail.removed"));
    state.selectedId = null;
    await loadLibrary();
  } catch (error) {
    if (failureOf(error).status === 409) lockDown(error);
    else setNotice(failureOf(error).message);
  }
}

/**
 * Add or remove a track from one crate.
 *
 * POST /api/crate with action add or remove. If the request fails, the
 * checkbox returns to its previous state. A 409 locks the page. The audio
 * file is not moved.
 *
 * @param {number} assetId Asset id.
 * @param {number} crateId Crate id.
 * @param {boolean} add True adds the membership.
 * @param {HTMLInputElement} input Checkbox to restore on failure.
 * @returns {Promise<void>}
 */
async function setMembership(assetId: number, crateId: number, add: boolean, input: HTMLInputElement) {
  try {
    const result = await postJSON("/api/crate", {
      action: add ? "add" : "remove",
      id: crateId,
      asset: assetId,
      space: state.space,
    });
    if (result.warning) setNotice(result.warning);
    await loadLibrary();
    selectTrack(assetId);
  } catch (error) {
    input.checked = !add;
    if (failureOf(error).status === 409) lockDown(error);
    else setNotice(failureOf(error).message);
  }
}

/**
 * Save smart-crate rules from the JSON editor.
 *
 * The text must parse as JSON before it is sent. POST /api/crate with
 * action rules. Reloads the library and reselects the crate. A 409 locks
 * the page. Invalid JSON is reported and not sent.
 *
 * @param {number} id Smart crate id.
 * @param {string} text Editor contents.
 * @returns {Promise<void>}
 */
async function saveRules(id: number, text: string) {
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
  } catch (error) {
    if (failureOf(error).status === 409) lockDown(error);
    else setNotice(failureOf(error).message);
  }
}

/**
 * Prompt for a name and create a crate under the current selection.
 *
 * All tracks uses the space root as the parent. POST /api/crate with
 * action create. The new crate is selected after the reload. A 409 locks
 * the page.
 *
 * @returns {Promise<void>}
 */
export async function createCrate() {
  const name = prompt(t("crates.newPrompt"));
  if (!name || !name.trim()) return;
  const parent = state.activeCrate === "all" ? state.rootId : state.activeCrate;
  try {
    const result = await postJSON("/api/crate", { action: "create", name: name.trim(), parent, space: state.space });
    setNotice(result.warning || t("crates.created"));
    await loadLibrary();
    selectCrate(result.id as number);
  } catch (error) {
    if (failureOf(error).status === 409) lockDown(error);
    else setNotice(failureOf(error).message);
  }
}

/**
 * Prompt for a new name and rename the selected crate.
 *
 * An empty name, or the same name, does not send a request. POST /api/crate
 * with action rename. A 409 locks the page.
 *
 * @returns {Promise<void>}
 */
export async function renameCrate() {
  const crate = state.crates.find((item) => item.id === state.activeCrate);
  if (!crate) return;
  const name = prompt(t("crates.renamePrompt"), crate.name);
  if (!name || !name.trim() || name.trim() === crate.name) return;
  try {
    const result = await postJSON("/api/crate", { action: "rename", id: crate.id, name: name.trim(), space: state.space });
    setNotice(result.warning || t("crates.renamed"));
    await loadLibrary();
    selectCrate(crate.id);
  } catch (error) {
    if (failureOf(error).status === 409) lockDown(error);
    else setNotice(failureOf(error).message);
  }
}

/**
 * Read a palette name typed at the color prompt.
 *
 * The name can be English or in the active language, in any case.
 *
 * @param {string} choice Text the person typed.
 * @returns {number|undefined} The Serato color, or undefined for an unknown name.
 */
export function colorFromName(choice: string): number | undefined {
  const wanted = choice.trim().toLocaleLowerCase();
  const english = COLOR_NAMES[wanted];
  if (english != null) return english;
  return COLORS.find(([, key]) => t(key).toLocaleLowerCase() === wanted)?.[0];
}

/**
 * Prompt for a palette name and save it on the selected crate.
 *
 * The names match COLOR_NAMES. White is sent as null, which is Serato's
 * "no color" value. POST /api/crate with action color. A 409 locks the page.
 *
 * @returns {Promise<void>}
 */
export async function colorCrate() {
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
      color: color === 0xffffff ? null : color,
      space: state.space,
    });
    setNotice(result.warning || t("crates.colorSaved"));
    await loadLibrary();
  } catch (error) {
    if (failureOf(error).status === 409) lockDown(error);
    else setNotice(failureOf(error).message);
  }
}

/**
 * Delete the selected crate and the crates nested inside it.
 *
 * Asks for confirmation first. Tracks stay in the library. POST /api/crate
 * with action delete, then the rail returns to All tracks. A 409 locks
 * the page.
 *
 * @returns {Promise<void>}
 */
export async function deleteCrate() {
  const crate = state.crates.find((item) => item.id === state.activeCrate);
  if (!crate) return;
  if (!confirm(t("crates.confirmDelete", { name: crate.name }))) return;
  try {
    const result = await postJSON("/api/crate", { action: "delete", id: crate.id, space: state.space });
    state.activeCrate = "all";
    setNotice(result.warning || t("crates.deleted"));
    await loadLibrary();
  } catch (error) {
    if (failureOf(error).status === 409) lockDown(error);
    else setNotice(failureOf(error).message);
  }
}

/**
 * Create a crate from an M3U file chosen in the page.
 *
 * Reads the file text in the browser and posts it to /api/import.m3u.
 * The server adds only tracks whose portable_id matches a playlist line.
 * The notice reports how many lines did not match. A 409 locks the page.
 *
 * @param {File} file Playlist file from the hidden file input.
 * @returns {Promise<void>}
 */
export async function importPlaylist(file: File) {
  const text = await file.text();
  const name = file.name.replace(/\.m3u8?$/i, "") || t("import.defaultName");
  const parent = state.activeCrate === "all" ? state.rootId : state.activeCrate;
  try {
    const result = await postJSON("/api/import.m3u", { space: state.space, parent, name, text });
    const missed = result.unmatched_count ? ` ${t("import.unmatched", { count: Number(result.unmatched_count) })}` : "";
    setNotice(`${t("import.added", { count: Number(result.added) || 0 })}${missed}${result.warning ? ` ${result.warning}` : ""}`);
    await loadLibrary();
    selectCrate(result.id as number);
  } catch (error) {
    if (failureOf(error).status === 409) lockDown(error);
    else setNotice(failureOf(error).message);
  }
}

/**
 * Redraw the history-session list from state.historySessions.
 *
 * Each row selects that session. The meta text is the played count.
 * Does not fetch; loadHistory and openSession do.
 *
 * @returns {void}
 */
export function renderSessions() {
  el("session-list").replaceChildren();
  for (const session of state.historySessions) {
    const button = document.createElement("button");
    tip(button, "historySession");
    button.type = "button";
    button.className = "crate";
    button.setAttribute("role", "option");
    button.setAttribute("aria-selected", String(session.id === state.historyId));
    const name = document.createElement("span");
    name.className = "name";
    name.textContent = session.name || t("history.session");
    const meta = document.createElement("span");
    meta.className = "meta";
    meta.textContent = String(session.played || 0);
    button.append(name, meta);
    button.addEventListener("click", () => openSession(session.id));
    el("session-list").append(button);
  }
}

/**
 * Load history sessions from GET /api/history.
 *
 * Stores them on state and redraws the session rail. Throws when the
 * server reports an error so the caller can show it. Does not open a session.
 *
 * @returns {Promise<void>}
 */
export async function loadHistory() {
  const response = await fetch("/api/history");
  const payload = await readJSONOr<HistoryPayload>(response, {});
  if (!response.ok) throw new Error(serverMessage(payload, t("history.readFailed")));
  state.historySessions = payload.sessions || [];
  renderSessions();
}

/**
 * Load one history session and show its entries.
 *
 * GET /api/history with the session id. Replaces state.entries and resets
 * the scroll position. A failed read stays on the notice line.
 *
 * @param {number} id history_session id.
 * @returns {Promise<void>}
 */
export async function openSession(id: number) {
  state.historyId = id;
  state.selectedId = null;
  renderSessions();
  const response = await fetch(`/api/history?session=${id}`);
  const payload = await readJSONOr<HistoryPayload>(response, {});
  if (!response.ok) {
    setNotice(serverMessage(payload, t("history.sessionFailed")));
    return;
  }
  state.entries = payload.entries || [];
  el("list").scrollTop = 0;
  renderList();
}

/**
 * Load duplicate groups for the current space.
 *
 * GET /api/duplicates. The ids are stored as a set so the list can filter
 * without another request. The list is redrawn only when that view is active.
 *
 * @returns {Promise<void>}
 */
export async function loadDuplicates() {
  state.duplicateIds = null;
  state.duplicateGroups = [];
  const response = await fetch(`/api/duplicates?space=${encodeURIComponent(state.space)}`);
  const payload = await readJSONOr<DuplicatePayload>(response, {});
  if (!response.ok) throw new Error(serverMessage(payload, t("duplicates.readFailed")));
  const ids = new Set<number>();
  state.duplicateGroups = payload.groups || [];
  for (const group of state.duplicateGroups) for (const id of group.ids || []) ids.add(id);
  state.duplicateIds = ids;
  state.duplicateSpace = state.space;
  if (state.mode === "duplicates") renderList();
}

/**
 * Leave history and select the same track in the Serato Library space.
 *
 * Switches the space menu, reloads that space, and fetches the track
 * detail. Used from a history entry that still has an asset id.
 *
 * @param {number} assetId Asset id in the Serato Library space.
 * @returns {Promise<void>}
 */
export async function openInLibrary(assetId: number) {
  state.space = "Serato Library";
  el("space").value = state.space;
  state.mode = "crates";
  state.activeCrate = "all";
  state.selectedId = assetId;
  await loadLibrary();
  selectTrack(assetId);
}

/**
 * Reload the current space from GET /api/library.
 *
 * Replaces tracks, crates, membership sets, and the lock status. Keeps
 * the selected crate and track when they still exist. Clears duplicate
 * ids when the space changed so the duplicate view cannot mix spaces.
 *
 * @returns {Promise<void>} Resolves after the list is painted. Throws on a failed read.
 */
export async function loadLibrary() {
  el("count").textContent = t("library.loading");
  const response = await fetch(`/api/library?space=${encodeURIComponent(state.space)}`);
  const library = await readJSONOr<LibraryPayload>(response, {} as LibraryPayload);
  if (!response.ok) throw new Error(serverMessage(library, t("library.readFailed", { status: String(response.status) })));
  const selected = state.selectedId;
  const active = state.activeCrate;
  state.tracks = library.tracks;
  state.byId = new Map(library.tracks.map((track) => [track.id, track]));
  state.crates = library.crates;
  state.rootId = library.root_id;
  state.crateTracks = new Map(library.crates.map((crate) => [crate.id, new Set(crate.tracks)]));
  state.expanded = new Set<number | "all">(library.crates.filter((crate) => crate.expanded).map((crate) => crate.id));
  state.activeCrate = active === "all" || library.crates.some((crate) => crate.id === active) ? active : "all";
  state.selectedId = selected;
  if (state.duplicateSpace !== state.space) {
    state.duplicateIds = null;
    state.duplicateGroups = [];
  }
  applyStatus(library.serato);
  renderList();
}

/**
 * Switch among crates, history, missing, duplicates, stems, and files.
 *
 * History sorts by start time descending and loads sessions once.
 * Duplicates load when this space has not been scanned yet. Files loads
 * the current folder. Other modes only change which tracks renderList keeps.
 *
 * @param {string} mode View name from the rail buttons.
 * @returns {void}
 */
export function setMode(mode: string) {
  state.mode = mode;
  el("list").scrollTop = 0;
  if (mode === "history") {
    state.sort = "start";
    state.sortDir = -1;
    if (!state.historySessions.length) loadHistory().catch((error) => setNotice(failureOf(error).message));
  } else if (state.sort === "start" || state.sort === "deck" || state.sort === "played") {
    state.sort = "name";
    state.sortDir = 1;
  }
  if (mode === "duplicates" && state.duplicateSpace !== state.space) {
    loadDuplicates().catch((error) => setNotice(failureOf(error).message));
  }
  if (mode === "files") {
    state.filesLoading = true;
    const path = state.filesAtRoots ? "" : (state.filesPath || "");
    loadFolder(path, { elsewhere: state.filesElsewhere && !state.filesAtRoots }).catch((error) => failFiles(error));
  }
  if (mode === "snapshots") {
    loadSnapshots().catch((error) => failSnapshots(error));
  }
  renderList();
}

/**
 * Replace the detail pane when the library cannot be read.
 *
 * Used for the first load and for reload failures. The count line says
 * the library is unavailable. Does not retry by itself.
 *
 * @param {Error} error Failure from loadLibrary or a related request.
 * @returns {void}
 */
export function showFailure(error: unknown) {
  el("count").textContent = t("library.unavailable");
  const failure = document.createElement("p");
  failure.className = "detail-error";
  failure.textContent = failureOf(error).message;
  el("detail").replaceChildren(failure);
}

/**
 * Return the duplicate group that contains the selected track.
 *
 * Groups come from GET /api/duplicates. A track outside that view, or a
 * track that is not in a group, returns null. Does not fetch.
 *
 * @returns {object|null} The group, with an ids array, or null.
 */
export function selectedDuplicateGroup() {
  if (state.mode !== "duplicates" || state.selectedId == null) return null;
  return (state.duplicateGroups || []).find((group) => (group.ids || []).includes(state.selectedId as number)) || null;
}

/**
 * Enable Merge copies when a duplicate group is selected and Serato is quit.
 *
 * The button lives in the duplicates rail. Other views hide it. Does not fetch.
 *
 * @returns {void}
 */
export function syncMergeButton() {
  const wrap = el("duplicate-actions");
  const button = el("merge-duplicates");
  if (!wrap || !button) return;
  const show = state.mode === "duplicates";
  wrap.hidden = !show;
  button.disabled = !show || !state.writable || !selectedDuplicateGroup();
}

/**
 * List normal-crate names that contain one asset.
 *
 * Smart crates are omitted. The names come from the loaded library.
 *
 * @param {number} assetId Asset id.
 * @returns {string[]} Crate names.
 */
export function crateNamesFor(assetId: number) {
  return state.crates
    .filter((crate) => !crate.smart && (crate.tracks || []).includes(assetId))
    .map((crate) => crate.name);
}

/**
 * Show a folder error in the Files view.
 *
 * @param {Error} error Failed folder read or save.
 * @returns {void}
 */
export function failFiles(error: unknown) {
  state.filesLoading = false;
  state.filesError = failureOf(error).message || t("error.folder_unreadable");
  renderFiles();
}

/**
 * Folder request counter.
 *
 * A slow reply must not paint a folder the user has already left.
 */
let filesRequest = 0;

/** Wait before searching the disk, so a fast typist does not search every letter. */
export const FILES_SEARCH_MS = 200;

let filesSearchTimer = 0;

const FILE_OVERSCAN = 8;

/**
 * Load music roots, or one folder.
 *
 * An empty path asks GET /api/library-roots. A folder asks GET /api/files.
 * ``elsewhere`` asks to browse outside those folders. ``refresh`` recomputes
 * the roots. Selection is cleared because the previous paths are no longer
 * the rows on screen. A success message can be kept when the reload follows
 * a save.
 *
 * @param {string} path Folder to open. Empty selects the music roots.
 * @param {{keepMessage?: boolean, elsewhere?: boolean, refresh?: boolean}} [options] keepMessage retains the last save note. elsewhere lists outside the roots. refresh recomputes the roots.
 * @returns {Promise<void>}
 */
export async function loadFolder(path: string, options: { keepMessage?: boolean; elsewhere?: boolean; refresh?: boolean } = {}) {
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
  state.filesSelected = new Set();
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
  const payload = await readJSONOr<FilesPayload>(response, {});
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

/**
 * Search file names under the open folder, or under every music folder.
 *
 * Uses GET /api/files?q=. The request is read-only. A newer folder open
 * or a newer search replaces a slow reply.
 *
 * @param query Name to find.
 * @returns {Promise<void>}
 */
async function searchFiles(query: string): Promise<void> {
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
  const payload = await readJSONOr<FilesPayload>(response, {});
  if (token !== filesRequest) return;
  if (!response.ok) throw new Error(payload.error || "Files could not be searched.");
  const entries = Array.isArray(payload.entries) ? payload.entries.filter(isListedFile) : [];
  state.filesEntries = entries;
  state.filesTruncated = Boolean(payload.truncated);
  state.filesLoading = false;
  state.filesSearching = true;
  state.filesActive = 0;
  state.filesSelected = new Set();
  el("files-list").scrollTop = 0;
  renderFiles();
}

/**
 * Return whether a JSON value is a file-list row.
 *
 * @param value Candidate.
 * @returns True when name, path, and kind are strings.
 */
function isListedFile(value: unknown): value is FileEntry {
  if (!value || typeof value !== "object") return false;
  const row = value as FileEntry;
  return typeof row.name === "string" && typeof row.path === "string" && typeof row.kind === "string";
}

/**
 * Paint the folder, the empty and loading states, and the action buttons.
 *
 * Uses text nodes. Shortcuts are labeled and cannot be selected. Writes
 * stay disabled while Serato holds the library.
 *
 * @returns {void}
 */
export function renderFiles() {
  if (state.mode !== "files") return;
  const pick = el("files-pick");
  const moveHere = el("files-move-here");
  const pickCancel = el("files-pick-cancel");
  pick.hidden = !state.filesPick;
  moveHere.hidden = !state.filesPick;
  pickCancel.hidden = !state.filesPick;
  renderBreadcrumb();
  const elsewhere = el("files-elsewhere");
  elsewhere.textContent = state.filesElsewhere ? t("files.roots") : t("files.browseElsewhere");
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

/**
 * Paint the folder path, starting at the music-root name.
 *
 * The current folder is text. Earlier crumbs are buttons. There is no
 * crumb above the root unless the browse is elsewhere.
 *
 * @returns {void}
 */
function renderBreadcrumb(): void {
  const nav = el("files-path");
  nav.replaceChildren();
  const list = document.createElement("ol");
  list.className = "files-crumbs";
  const crumbs = visibleCrumbs();
  crumbs.forEach((crumb, index) => {
    const item = document.createElement("li");
    const last = index === crumbs.length - 1;
    if (!last && crumb.path) {
      const button = document.createElement("button");
      tip(button, "filesCrumb");
      button.type = "button";
      button.className = "files-crumb";
      button.textContent = crumb.name;
      button.addEventListener("click", () => {
        loadFolder(crumb.path, { elsewhere: state.filesElsewhere }).catch((error) => failFiles(error));
      });
      item.append(button);
    } else {
      const current = document.createElement("span");
      current.className = "files-crumb";
      current.setAttribute("aria-current", "page");
      current.textContent = crumb.name;
      item.append(current);
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

/**
 * Return the crumbs for the open location.
 *
 * @returns {FileCrumb[]} Path crumbs. The root list is one crumb.
 */
function visibleCrumbs(): FileCrumb[] {
  if (state.filesBreadcrumb.length) return state.filesBreadcrumb;
  if (state.filesAtRoots) return [{ name: t("files.roots"), path: "" }];
  if (state.filesPath) return [{ name: state.filesPath, path: state.filesPath }];
  return [{ name: t("files.roots"), path: "" }];
}

/**
 * Return the rows in the order they are shown.
 *
 * Roots keep the order from the server. A folder lists directories, then
 * files, then shortcuts.
 *
 * @returns {FileEntry[]} Rows for the virtual window.
 */
function filesRowHeight(): number {
  if (state.filesSearching) return FILE_ROW;
  return state.filesAtRoots ? ROOT_ROW : FILE_ROW;
}

function browserRows(): FileEntry[] {
  if (state.filesSearching) return state.filesEntries;
  if (state.filesAtRoots) {
    return state.filesRoots.map((root) => {
      const entry: FileEntry = {
        name: root.label,
        path: root.path,
        detail: root.detail,
        kind: root.kind === "serato_drive" ? "drive" : "folder",
        missing: root.missing,
      };
      return entry;
    });
  }
  const rank: Record<string, number> = { dir: 0, file: 1, link: 2 };
  return [...state.filesEntries].sort((left, right) => {
    return (rank[left.kind] ?? 3) - (rank[right.kind] ?? 3)
      || left.name.localeCompare(right.name, undefined, { numeric: true, sensitivity: "base" });
  });
}

/**
 * Paint only the file rows inside the scroll window.
 *
 * Row height is FILE_ROW. Extra rows above and below the window keep a
 * fast scroll from flashing empty space. The spacer is the full height,
 * so the last row can be scrolled into view.
 *
 * @returns {void}
 */
function paintFileWindow(): void {
  const list = el("files-list");
  const rows = browserRows();
  list.setAttribute("aria-busy", String(state.filesLoading));
  list.setAttribute(
    "aria-label",
    state.filesSearching ? t("files.searchResults") : state.filesAtRoots ? t("files.roots") : t("files.contents"),
  );
  if (state.filesLoading && !rows.length) {
    const reading = state.filesSearching
      ? t("files.searching")
      : state.filesAtRoots
        ? t("files.readingRootsNote")
        : t("files.readingFolderNote");
    list.replaceChildren(fileNote(reading));
    list.tabIndex = 0;
    return;
  }
  if (state.filesError && !rows.length) {
    list.replaceChildren(fileNote(state.filesError));
    list.tabIndex = 0;
    return;
  }
  if (state.filesAtRoots && !state.filesRoots.length) {
    list.replaceChildren(rootsEmpty());
    list.tabIndex = -1;
    return;
  }
  if (!rows.length) {
    const empty = state.filesSearching
      ? t("files.noMatches", { query: state.filesQuery })
      : t("files.empty");
    list.replaceChildren(fileNote(empty));
    list.tabIndex = 0;
    return;
  }
  list.tabIndex = -1;
  if (state.filesActive >= rows.length) state.filesActive = rows.length - 1;
  if (state.filesActive < 0) state.filesActive = 0;
  const rowHeight = filesRowHeight();
  const view = list.clientHeight || 600;
  const maxScroll = Math.max(0, rows.length * rowHeight - view);
  const scrollTop = Math.min(Math.max(0, list.scrollTop), maxScroll);
  const start = Math.max(0, Math.floor(scrollTop / rowHeight) - FILE_OVERSCAN);
  const end = Math.min(rows.length, Math.ceil((scrollTop + view) / rowHeight) + FILE_OVERSCAN);
  const spacer = fileSpacer(list);
  const windowEl = spacer.querySelector<HTMLDivElement>(".files-window");
  if (!windowEl) return;
  spacer.style.height = `${rows.length * rowHeight}px`;
  windowEl.style.transform = `translateY(${start * rowHeight}px)`;
  windowEl.replaceChildren();
  for (let index = start; index < end; index += 1) {
    const entry = rows[index];
    if (entry) windowEl.append(fileRow(entry, index));
  }
  if (state.filesActive >= start && state.filesActive < end) {
    list.setAttribute("aria-activedescendant", `files-item-${state.filesActive}`);
  } else list.removeAttribute("aria-activedescendant");
}

/**
 * Return the scroll spacer, creating it when the list is showing rows.
 *
 * @param {HTMLElement} list Files list element.
 * @returns {HTMLDivElement} The spacer that holds the window.
 */
function fileSpacer(list: HTMLElement): HTMLDivElement {
  const first = list.firstElementChild;
  if (first instanceof HTMLDivElement && first.classList.contains("files-spacer") && list.childElementCount === 1) {
    return first;
  }
  list.replaceChildren();
  const spacer = document.createElement("div");
  spacer.className = "files-spacer";
  const windowEl = document.createElement("div");
  windowEl.className = "files-window";
  spacer.append(windowEl);
  list.append(spacer);
  return spacer;
}

/**
 * Build a short status line inside the file list.
 *
 * @param {string} text Sentence to show.
 * @returns {HTMLParagraphElement} The note.
 */
function fileNote(text: string): HTMLParagraphElement {
  const note = document.createElement("p");
  note.className = "files-empty";
  note.textContent = text;
  return note;
}

/**
 * Build the empty state for a library with no music folders.
 *
 * One primary button opens setup. Browse elsewhere stays in the bar.
 *
 * @returns {HTMLDivElement} The empty state.
 */
function rootsEmpty(): HTMLDivElement {
  const box = document.createElement("div");
  box.className = "files-empty-state";
  const heading = document.createElement("h2");
  heading.textContent = t("files.noRoots");
  const copy = document.createElement("p");
  copy.textContent = t("files.noRootsBody");
  const button = document.createElement("button");
  tip(button, "filesRunSetup");
  button.type = "button";
  button.id = "files-run-setup";
  button.className = "files-primary";
  button.textContent = t("files.runSetup");
  button.addEventListener("click", () => bridge.openSetup());
  box.append(heading, copy, button);
  return box;
}

/**
 * Move the keyboard cursor to one row and keep that row on screen.
 *
 * @param {number} index Row index in browserRows.
 * @returns {void}
 */
function focusFilesIndex(index: number): void {
  const rows = browserRows();
  if (!rows.length) return;
  state.filesActive = Math.max(0, Math.min(rows.length - 1, index));
  const list = el("files-list");
  const rowHeight = filesRowHeight();
  const view = list.clientHeight || 600;
  const top = state.filesActive * rowHeight;
  const maxScroll = Math.max(0, rows.length * rowHeight - view);
  if (top < list.scrollTop) list.scrollTop = top;
  if (top + rowHeight > list.scrollTop + view) list.scrollTop = Math.min(maxScroll, top + rowHeight - view);
  paintFileWindow();
  const control = list.querySelector<HTMLElement>(`[data-files-index="${state.filesActive}"]`);
  control?.focus();
}

/**
 * Open the active folder or toggle the active file.
 *
 * @param {number} index Row index in browserRows.
 * @returns {void}
 */
function activateFilesIndex(index: number): void {
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

/**
 * Open a folder, a music root, or a drive.
 *
 * A folder opened while browsing elsewhere stays outside the roots.
 * A root returns to rooted browsing.
 *
 * @param {FileEntry} entry Row to open.
 * @returns {void}
 */
function openBrowserRow(entry: FileEntry): void {
  if (entry.missing) return;
  const elsewhere = state.filesElsewhere && entry.kind === "dir";
  loadFolder(entry.path, { elsewhere }).catch((error) => failFiles(error));
}

/**
 * Handle arrow keys, Home, and End for the file list.
 *
 * @param {KeyboardEvent} event Key event from the list or a row.
 * @returns {void}
 */
function onFilesKey(event: KeyboardEvent): void {
  if (state.mode !== "files") return;
  const list = el("files-list");
  if (!(event.target instanceof Node) || !list.contains(event.target)) return;
  const rows = browserRows();
  if (!rows.length) return;
  if (event.key === "ArrowDown" || event.key === "ArrowUp" || event.key === "Home" || event.key === "End") {
    event.preventDefault();
    if (event.key === "ArrowDown") focusFilesIndex(state.filesActive + 1);
    else if (event.key === "ArrowUp") focusFilesIndex(state.filesActive - 1);
    else if (event.key === "Home") focusFilesIndex(0);
    else focusFilesIndex(rows.length - 1);
    return;
  }
  if (event.key !== "Enter" && event.key !== " ") return;
  const control = event.target instanceof HTMLElement ? event.target.closest("button, input") : null;
  if (control && list.contains(control)) return;
  event.preventDefault();
  activateFilesIndex(state.filesActive);
}

/**
 * Build one folder row.
 *
 * @param {FileEntry} entry Directory entry or music root.
 * @param {number} index Index in browserRows. Used for keyboard focus.
 * @returns {HTMLDivElement} The row.
 */
function fileRow(entry: FileEntry, index: number): HTMLDivElement {
  const row = document.createElement("div");
  row.className = "files-row";
  if (entry.detail && (entry.kind === "folder" || entry.kind === "drive")) row.classList.add("is-root");
  if (entry.missing) row.classList.add("is-missing");
  if (index === state.filesActive) row.classList.add("is-active");
  row.setAttribute("role", "listitem");
  const openKind = entry.kind === "dir" || entry.kind === "folder" || entry.kind === "drive";
  if (openKind) {
    const button = document.createElement("button");
    tip(button, entry.missing ? "filesDriveMissing" : "filesOpen", entry.detail ? `${entry.name} ${entry.detail}` : entry.name);
    button.type = "button";
    button.className = "files-open";
    button.dataset.filesIndex = String(index);
    button.id = `files-item-${index}`;
    button.tabIndex = index === state.filesActive ? 0 : -1;
    if (entry.kind === "drive" || entry.kind === "folder") button.append(fileIcon(entry.kind === "drive" ? "drive" : "folder"));
    if (entry.detail && (entry.kind === "folder" || entry.kind === "drive")) {
      const copy = document.createElement("span");
      copy.className = "files-root-copy";
      const label = document.createElement("span");
      label.className = "files-root-label";
      label.textContent = entry.name;
      const detail = document.createElement("span");
      detail.className = "files-root-detail";
      detail.textContent = entry.detail;
      copy.append(label, detail);
      button.append(copy);
    } else {
      const name = document.createElement("span");
      name.textContent = entry.name;
      button.append(name);
      if (entry.detail) {
        const detail = document.createElement("span");
        detail.className = "files-match-detail";
        detail.textContent = entry.detail;
        button.append(detail);
      }
    }
    if (entry.missing) {
      button.setAttribute("aria-disabled", "true");
      button.setAttribute("aria-label", t("files.driveMissingLabel", { name: entry.name }));
      const badge = document.createElement("span");
      badge.className = "files-badge";
      badge.textContent = t("files.driveMissing");
      button.append(badge);
      button.addEventListener("click", () => {
        state.filesActive = index;
      });
    } else {
      button.setAttribute("aria-label", t("files.open", { name: entry.name }));
      button.addEventListener("click", () => {
        state.filesActive = index;
        openBrowserRow(entry);
      });
    }
    row.append(button);
    return row;
  }
  if (entry.kind !== "file") {
    const label = document.createElement("button");
    tip(label, "filesShortcut", entry.name);
    label.type = "button";
    label.className = "files-kind";
    label.dataset.filesIndex = String(index);
    label.id = `files-item-${index}`;
    label.tabIndex = index === state.filesActive ? 0 : -1;
    label.textContent = t("files.shortcut", { name: entry.name });
    label.setAttribute("aria-label", `${entry.name} shortcut`);
    row.append(label);
    return row;
  }
  const label = document.createElement("label");
  label.className = "files-file";
  const box = document.createElement("input");
  tip(box, "filesSelect", entry.path || entry.name);
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

/**
 * Draw a folder or drive mark with the text color.
 *
 * The shapes are part of the page. They are not a separate icon font.
 *
 * @param {"folder" | "drive"} kind Which mark to draw.
 * @returns {SVGSVGElement} A decorative icon.
 */
function fileIcon(kind: "folder" | "drive"): SVGSVGElement {
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
    kind === "drive"
      ? "M5 8.5h14v8H5z M8 14.5h.01 M12 14.5h4"
      : "M4 8.5h6l2 2h8v7.5H4z",
  );
  svg.append(path);
  return svg;
}

/**
 * Return whether a JSON value is a music root.
 *
 * @param {unknown} value Candidate.
 * @returns {boolean} True when name, path, and kind are strings.
 */
function isFileRoot(value: unknown): value is FileRoot {
  if (!value || typeof value !== "object") return false;
  const record = value as FileRoot;
  return typeof record.name === "string" && typeof record.path === "string" && typeof record.kind === "string";
}

/**
 * Return whether a JSON value is a breadcrumb.
 *
 * @param {unknown} value Candidate.
 * @returns {boolean} True when name and path are strings.
 */
function isFileCrumb(value: unknown): value is FileCrumb {
  if (!value || typeof value !== "object") return false;
  const record = value as FileCrumb;
  return typeof record.name === "string" && typeof record.path === "string";
}

/**
 * Return the selected files that are still in this folder.
 *
 * @returns {object[]} Selected file entries.
 */
/**
 * Move the file-list cursor by one row.
 *
 * @param delta 1 for the next row, -1 for the previous row.
 * @returns {void}
 */
export function moveFileList(delta: number): void {
  if (!browserRows().length) return;
  focusFilesIndex(state.filesActive + delta);
}

/**
 * Open the active file row.
 *
 * A folder opens. A file toggles its checkbox. Does nothing when the
 * list is empty.
 *
 * @returns {void}
 */
export function openFileList(): void {
  if (!browserRows().length) return;
  activateFilesIndex(state.filesActive);
}

/**
 * Move the file-list cursor to a path from quick-open.
 *
 * @param path File path returned by the search.
 * @returns {void}
 */
export function focusFileByPath(path: string): void {
  const index = browserRows().findIndex((entry) => entry.path === path);
  if (index < 0) return;
  focusFilesIndex(index);
}

export function selectedFiles() {
  return state.filesEntries.filter((entry) => entry.kind === "file" && state.filesSelected.has(entry.path));
}

/**
 * Attach the library, crate, history, and list-header listeners.
 *
 * Called once from app.ts after the spacer is mounted. The handlers call
 * the functions in this module. They do not open the database themselves.
 *
 * @returns {void}
 */
export function wireLibrary(): void {
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
      loadFolder(state.filesPath, { elsewhere: state.filesElsewhere && Boolean(state.filesPath) }).catch((error) => failFiles(error));
      return;
    }
    filesSearchTimer = window.setTimeout(() => {
      searchFiles(value.trim()).catch((error) => failFiles(error));
    }, FILES_SEARCH_MS);
  });

  el("search").addEventListener("input", () => {
    state.query = el("search").value;
    el("list").scrollTop = 0;
    renderList();
  });

  el("crate-search").addEventListener("input", (event) => {
    state.crateQuery = (event.target as HTMLInputElement).value;
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
    const file = (event.target as HTMLInputElement).files?.[0];
    (event.target as HTMLInputElement).value = "";
    if (file) importPlaylist(file).catch((error) => setNotice(failureOf(error).message));
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
    const button = (event.target as HTMLElement).closest("button");
    if (button?.dataset.view) setMode(button.dataset.view);
  });
  document.querySelector<HTMLElement>(".sort-crates")!.addEventListener("click", (event) => {
    const button = (event.target as HTMLElement).closest("button");
    if (!button?.dataset.crateSort) return;
    state.crateSort = button.dataset.crateSort;
    renderCrates();
    renderShell();
  });

  el("crate-new").addEventListener("click", () => createCrate().catch((error) => setNotice(failureOf(error).message)));
  el("crate-rename").addEventListener("click", () => renameCrate().catch((error) => setNotice(failureOf(error).message)));
  el("crate-color").addEventListener("click", () => colorCrate().catch((error) => setNotice(failureOf(error).message)));
  el("crate-delete").addEventListener("click", () => deleteCrate().catch((error) => setNotice(failureOf(error).message)));
  document.querySelector<HTMLElement>(".columns")!.addEventListener("click", (event) => {
    const button = (event.target as HTMLElement).closest("button");
    if (!button?.dataset.sort) return;
    const key = button.dataset.sort;
    if (state.sort === key) state.sortDir *= -1;
    else {
      state.sort = key;
      // Numbers open high-to-low. Titles open A-to-Z.
      state.sortDir = key === "bpm" || key === "length_ms" || key === "start" ? -1 : 1;
    }
    renderColumns();
    renderList();
  });

  // Arrow keys follow the tree: Right opens a crate, Left closes it or
  // jumps to the parent. Enter and Space select. The roving tabindex keeps
  // one crate button in the tab order.
  el("crate-list").addEventListener("keydown", (event) => {
    const item = (event.target as HTMLElement).closest<HTMLButtonElement>(".crate");
    if (!item || !el("crate-list").contains(item)) return;
    const items = [...el("crate-list").querySelectorAll<HTMLButtonElement>(".crate")];
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
        focusCrateItem(items.find((button) => button.dataset.id === item.dataset.parent));
      }
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      selectCrate(id);
    }
  });
}

bridge.selectTrack = selectTrack;
bridge.selectEntry = selectEntry;
