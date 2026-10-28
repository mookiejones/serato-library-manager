/**
 * Serato library page.
 *
 * Loads crates, history, missing tracks, duplicates, stems, and files from
 * the local server on 127.0.0.1 port 8765. Track and crate edits are POST
 * requests to /api/track, /api/crate, /api/import.m3u, /api/reveal, and
 * /api/duplicates/merge. Rekordbox export is GET /api/export.rekordbox.xml.
 * File moves, renames, replacements, and deletes
 * use /api/files. A preview is shown before confirm. Related tracks use
 * /api/related. The track list is virtualized: only rows near the scroll
 * window are in the DOM. Sharing settings and local logs use
 * /api/settings and /api/logs. This file does not open master.sqlite
 * itself, and it does not send library rows anywhere.
 */

// Row height in pixels. It matches --row in app.css. The painter divides
// the scroll offset by this value, so the two must stay equal.
const ROW = 36;
const COLORS = [
  [0xffffff, "None"],
  [0xcc0000, "Red"],
  [0xff8800, "Orange"],
  [0xffcc00, "Yellow"],
  [0x33aa55, "Green"],
  [0x2255cc, "Blue"],
  [0x8833cc, "Purple"],
  [0xe23b8a, "Pink"],
];
const COLOR_NAMES = {
  none: 0xffffff,
  red: 0xcc0000,
  orange: 0xff8800,
  yellow: 0xffcc00,
  green: 0x33aa55,
  blue: 0x2255cc,
  purple: 0x8833cc,
  pink: 0xe23b8a,
};

// Page state. The server remains the source of truth; this object is the
// last payload plus the view the user has open. Writes go through postJSON.
const state = {
  tracks: [],
  byId: new Map(),
  crates: [],
  crateTracks: new Map(),
  rootId: null,
  activeCrate: "all",
  query: "",
  crateQuery: "",
  crateSort: "order",
  sort: "name",
  sortDir: 1,
  selectedId: null,
  request: 0,
  expanded: new Set(),
  space: "Serato Library",
  mode: "crates",
  writable: false,
  serato: null,
  historySessions: [],
  historyId: null,
  entries: [],
  duplicateIds: null,
  duplicateGroups: [],
  duplicateSpace: "",
  telemetryConsent: null,
  telemetryConfigured: false,
  filesPath: "",
  filesParent: null,
  filesEntries: [],
  filesSelected: new Set(),
  filesPick: null,
  filesPickPaths: [],
  filesPickSource: "",
  filesLoading: false,
  filesError: "",
  filesMessage: "",
  filesTruncated: false,
};

const crateList = document.getElementById("crate-list");
const sessionList = document.getElementById("session-list");
const list = document.getElementById("list");
const count = document.getElementById("count");
const search = document.getElementById("search");
const detail = document.getElementById("detail");
const statusLine = document.getElementById("status");
const notice = document.getElementById("notice");
const crateFoot = document.getElementById("crate-foot");
const modeNote = document.getElementById("mode-note");
const spaceSelect = document.getElementById("space");
const spacer = document.createElement("div");
const rows = document.createElement("div");
spacer.className = "spacer";
rows.className = "rows";
spacer.append(rows);
list.append(spacer);

/**
 * Format a track length in milliseconds as m:ss.
 *
 * The list column uses a short label so a virtualized row stays one line.
 * Empty input stays blank. No library request is made.
 *
 * @param {number|string|null|undefined} ms Length in milliseconds.
 * @returns {string} Minutes and zero-padded seconds, or an empty string.
 */
function lengthLabel(ms) {
  if (ms == null || ms === "") return "";
  const total = Math.floor(Number(ms) / 1000);
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

/**
 * Format a Unix timestamp for a history row.
 *
 * History stores seconds, while the Date constructor expects milliseconds.
 * An empty or unreadable stamp stays blank so the row does not show
 * "Invalid Date". No request is made.
 *
 * @param {number|string|null|undefined} stamp Seconds since the Unix epoch.
 * @returns {string} A short local date and time, or an empty string.
 */
function clockLabel(stamp) {
  if (stamp == null || stamp === "") return "";
  const date = new Date(Number(stamp) * 1000);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

/**
 * Format a total duration for the crate footer.
 *
 * Hours are included only when the total reaches one hour. The footer
 * uses this for the tracks currently in view. No request is made.
 *
 * @param {number|string} ms Total length in milliseconds.
 * @returns {string} A label such as "12m" or "1h 2m".
 */
function durationLabel(ms) {
  const total = Math.round(Number(ms) / 1000);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (hours) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

/**
 * Format a byte count for the crate footer.
 *
 * Steps through KB, MB, and GB. A missing size is shown as zero bytes.
 * No request is made.
 *
 * @param {number|string|null|undefined} bytes File size in bytes.
 * @returns {string} A one-decimal size with its unit.
 */
function sizeLabel(bytes) {
  const size = Number(bytes) || 0;
  if (size < 1024) return `${size} bytes`;
  const units = ["KB", "MB", "GB"];
  let amount = size / 1024;
  let unit = 0;
  while (amount >= 1024 && unit < units.length - 1) {
    amount /= 1024;
    unit += 1;
  }
  return `${amount.toFixed(1)} ${units[unit]}`;
}

/**
 * Format a Serato color integer as a CSS hex color.
 *
 * White (0xffffff) means the crate or track has no color, so the swatch
 * is omitted. No request is made.
 *
 * @param {number|string|null|undefined} color Serato color integer.
 * @returns {string} "#rrggbb", or an empty string when there is no color.
 */
function colorHex(color) {
  if (color == null || Number(color) === 0xffffff) return "";
  return `#${Number(color).toString(16).padStart(6, "0")}`;
}

/**
 * Compare two tracks for the current list sort.
 *
 * Numeric columns keep empty values after every real value. Text uses the
 * locale, with numbers compared as numbers, so "Track 2" stays before
 * "Track 10". Equal keys fall back to the id so the order is stable.
 * No request is made.
 *
 * @param {object} a First track or history row.
 * @param {object} b Second track or history row.
 * @returns {number} A negative, zero, or positive order for Array sort.
 */
function compare(a, b) {
  const key = state.sort;
  const dir = state.sortDir;
  let av = a[key];
  let bv = b[key];
  if (key === "bpm" || key === "length_ms" || key === "start") {
    const an = av == null || av === "" ? null : Number(av);
    const bn = bv == null || bv === "" ? null : Number(bv);
    if (an == null && bn == null) return a.id - b.id;
    // Empty BPM, length, or start sorts after every real number.
    if (an == null) return 1;
    if (bn == null) return -1;
    if (an !== bn) return (an - bn) * dir;
    return a.id - b.id;
  }
  av = String(av || "").toLocaleLowerCase();
  bv = String(bv || "").toLocaleLowerCase();
  if (!av && bv) return 1;
  if (av && !bv) return -1;
  const order = av.localeCompare(bv, undefined, { numeric: true, sensitivity: "base" });
  if (order !== 0) return order * dir;
  return a.id - b.id;
}

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
function matchesQuery(track, terms) {
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
  const children = new Map();
  for (const crate of state.crates) {
    const key = crate.parent ?? 0;
    if (!children.has(key)) children.set(key, []);
    children.get(key).push(crate);
  }
  for (const list of children.values()) {
    list.sort((a, b) => {
      if (state.crateSort === "name") {
        return a.name.localeCompare(b.name, undefined, { sensitivity: "base" }) || a.id - b.id;
      }
      if (state.crateSort === "added") return (b.added || 0) - (a.added || 0) || a.id - b.id;
      return a.order - b.order || a.id - b.id;
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
    let current = crate;
    const guard = new Set();
    // guard stops a parent cycle from walking the same crate forever.
    while (current && !guard.has(current.id)) {
      guard.add(current.id);
      keep.add(current.id);
      current = byId.get(current.parent);
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
function visibleCrates() {
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
  function walk(parent, depth) {
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
  walk(state.rootId, 0);
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
function expandAncestors(id) {
  const byId = new Map(state.crates.map((crate) => [crate.id, crate]));
  let crate = byId.get(id);
  const guard = new Set();
  while (crate && !guard.has(crate.id)) {
    guard.add(crate.id);
    const parent = byId.get(crate.parent);
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
function hiddenSelectionHolder(visible) {
  if (state.activeCrate === "all") return null;
  if (visible.some((crate) => crate.id === state.activeCrate)) return null;
  const byId = new Map(state.crates.map((crate) => [crate.id, crate]));
  const visibleIds = new Set(visible.map((crate) => crate.id));
  let crate = byId.get(state.activeCrate);
  const guard = new Set();
  while (crate && !guard.has(crate.id)) {
    guard.add(crate.id);
    crate = byId.get(crate.parent);
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
function buildView() {
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
      played: entry.played ? "Yes" : "",
      start: entry.start_time,
      missing: entry.missing,
      entry: true,
      asset_id: entry.asset_id,
      notes: entry.notes,
    }));
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
function crateRow(crate) {
  const row = document.createElement("div");
  row.className = "crate-row";
  if (crate.holds) row.classList.add("holds-selection");
  row.style.paddingLeft = `${crate.depth * 14}px`;

  if (crate.childCount) {
    const open = state.crateQuery ? true : state.expanded.has(crate.id);
    const twist = document.createElement("button");
    twist.type = "button";
    twist.className = "twist";
    twist.tabIndex = -1;
    twist.setAttribute("aria-expanded", String(open));
    twist.setAttribute("aria-label", `${open ? "Collapse" : "Expand"} ${crate.name}`);
    twist.addEventListener("click", () => toggleCrate(crate.id));
    row.append(twist);
  } else {
    const gap = document.createElement("span");
    gap.className = "twist-gap";
    gap.setAttribute("aria-hidden", "true");
    row.append(gap);
  }

  const button = document.createElement("button");
  button.type = "button";
  button.className = "crate";
  button.dataset.id = String(crate.id);
  if (crate.parent != null) button.dataset.parent = String(crate.parent);
  button.setAttribute("role", "treeitem");
  button.setAttribute("aria-level", String(crate.depth + 1));
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
    smart.textContent = "smart";
    button.append(smart);
  }
  const meta = document.createElement("span");
  meta.className = "meta";
  meta.textContent = crate.count.toLocaleString();
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
function placeCrateFocus(previousId) {
  const items = [...crateList.querySelectorAll(".crate")];
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
function renderCrates() {
  const scroll = crateList.scrollTop;
  const active = document.activeElement;
  const restore = crateList.contains(active)
    ? active.closest(".crate-row")?.querySelector(".crate")?.dataset.id ?? null
    : null;
  const terms = queryTerms();
  const matched = terms.length
    ? new Set(state.tracks.filter((track) => matchesQuery(track, terms)).map((track) => track.id))
    : null;
  const crates = visibleCrates();
  const holder = hiddenSelectionHolder(crates);
  crateList.replaceChildren();

  crateList.append(crateRow({
    id: "all",
    name: "All tracks",
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
    crateList.append(crateRow({
      id: crate.id,
      name: crate.name,
      depth: crate.depth || 0,
      childCount: crate.childCount || 0,
      smart: crate.smart,
      parent: crate.parent,
      color: crate.color,
      count: shown,
      holds: holder === crate.id,
    }));
  }
  const focused = placeCrateFocus(restore);
  if (restore && focused) focused.focus({ preventScroll: true });
  crateList.scrollTop = scroll;
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
    lead.textContent = "Matches";
    const parts = crate.rules.rules.map((rule) => {
      const attribute = rule.attribute || "field";
      const operation = String(rule.operation || "").toLowerCase().replaceAll("_", " ");
      return `${attribute} ${operation} “${rule.value ?? ""}”`;
    });
    const join = crate.rules.conjunction === "OR" ? " or " : " and ";
    line.append(lead, document.createTextNode(` ${parts.join(join) || "no rules yet"}`));
  }
  const editor = document.createElement("div");
  editor.className = "rule-edit";
  const area = document.createElement("textarea");
  area.value = JSON.stringify(crate.rules, null, 2);
  area.disabled = !state.writable;
  area.setAttribute("aria-label", "Smart crate rules");
  const save = document.createElement("button");
  save.type = "button";
  save.className = "text-button";
  save.textContent = "Save rules";
  save.disabled = !state.writable;
  save.addEventListener("click", () => saveRules(crate.id, area.value));
  editor.append(area, save);
  const bar = document.querySelector(".browser-bar");
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
function renderColumns() {
  const columns = state.mode === "history"
    ? [["name", "Title"], ["artist", "Artist"], ["deck", "Deck"], ["played", "Played"], ["start", "Time"]]
    : [["name", "Title"], ["artist", "Artist"], ["bpm", "BPM"], ["key", "Key"], ["length_ms", "Time"]];
  const buttons = [...document.querySelectorAll(".columns button")];
  columns.forEach(([key, label], index) => {
    const button = buttons[index];
    button.dataset.sort = key;
    button.textContent = label;
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
function renderShell() {
  const cratesMode = state.mode === "crates";
  const historyMode = state.mode === "history";
  document.getElementById("crate-tools").hidden = !cratesMode;
  document.getElementById("crate-actions").hidden = !cratesMode;
  crateList.hidden = !cratesMode;
  sessionList.hidden = !historyMode;
  modeNote.hidden = cratesMode || historyMode;
  const filesMode = state.mode === "files";
  document.querySelector(".browser").hidden = filesMode;
  document.getElementById("detail").hidden = filesMode;
  document.getElementById("files-panel").hidden = !filesMode;
  if (state.mode === "missing") modeNote.textContent = "Tracks Serato has marked missing in this space.";
  if (state.mode === "duplicates") {
    modeNote.textContent = "Same title, artist, and length. Select a copy, then merge the others into it.";
  }
  if (state.mode === "stems") modeNote.textContent = "Tracks with a stems analysis state.";
  if (filesMode) modeNote.textContent = "Files on disk. Cue points stay in the audio file. Crates follow the path.";
  for (const button of document.querySelectorAll("#views button")) {
    button.setAttribute("aria-selected", String(button.dataset.view === state.mode));
  }
  for (const button of document.querySelectorAll("[data-crate-sort]")) {
    button.setAttribute("aria-pressed", String(button.dataset.crateSort === state.crateSort));
  }
  const crateChosen = state.activeCrate !== "all";
  document.getElementById("crate-new").disabled = !state.writable;
  document.getElementById("crate-rename").disabled = !state.writable || !crateChosen;
  document.getElementById("crate-color").disabled = !state.writable || !crateChosen;
  document.getElementById("crate-delete").disabled = !state.writable || !crateChosen;
  syncMergeButton();
  if (filesMode) {
    const listed = state.filesEntries.filter((entry) => entry.kind === "file").length;
    crateFoot.textContent = state.filesLoading ? "Reading this folder" : `${listed.toLocaleString()} files`;
    return;
  }
  const pool = state.mode === "history" ? state.entries : footerTracks();
  const bytes = pool.reduce((sum, track) => sum + (Number(track.file_size) || 0), 0);
  const ms = pool.reduce((sum, track) => sum + (Number(track.length_ms) || 0), 0);
  crateFoot.textContent = `${pool.length.toLocaleString()} · ${durationLabel(ms)} · ${sizeLabel(bytes)}`;
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
    return state.duplicateIds ? state.tracks.filter((track) => state.duplicateIds.has(track.id)) : [];
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
function renderList() {
  renderShell();
  if (state.mode === "files") {
    renderFiles();
    return;
  }
  renderColumns();
  const view = buildView();
  const noun = state.mode === "history" ? "play" : "track";
  count.textContent = `${view.length.toLocaleString()} ${noun}${view.length === 1 ? "" : "s"}`;
  if (state.mode === "crates") renderCrates();
  else document.querySelector(".rules")?.remove();
  paintRows();
  if (!view.some((track) => track.id === state.selectedId)) {
    if (!view.length) {
      state.selectedId = null;
      const empty = document.createElement("p");
      empty.className = "detail-empty";
      empty.textContent = state.mode === "history" && !state.historyId ? "Choose a session." : "No tracks match.";
      detail.replaceChildren(empty);
    } else if (state.mode === "history") selectEntry(view[0].id);
    else selectTrack(view[0].id);
  }
}

/**
 * Paint only the track rows inside the scroll window.
 *
 * Row height is ROW. Six extra rows above and below the window keep a
 * fast scroll from flashing empty space. Replaces the row container.
 * Does not fetch track details.
 *
 * @returns {void}
 */
function paintRows() {
  const view = state.view || [];
  const height = list.clientHeight || 600;
  // Paint six rows past the window so a fast scroll does not flash empty space.
  const start = Math.max(0, Math.floor(list.scrollTop / ROW) - 6);
  const end = Math.min(view.length, Math.ceil((list.scrollTop + height) / ROW) + 6);
  spacer.style.height = `${view.length * ROW}px`;
  rows.style.transform = `translateY(${start * ROW}px)`;
  rows.replaceChildren();
  if (!view.length) {
    const empty = document.createElement("p");
    empty.className = "empty-list";
    empty.textContent = state.mode === "duplicates" && !state.duplicateIds ? "Reading duplicates" : "No tracks match.";
    rows.append(empty);
    return;
  }
  for (let index = start; index < end; index += 1) {
    const track = view[index];
    const button = document.createElement("button");
    button.type = "button";
    button.className = "row";
    button.setAttribute("role", "option");
    button.setAttribute("aria-selected", String(track.id === state.selectedId));
    button.dataset.id = String(track.id);

    const titleCell = document.createElement("span");
    titleCell.className = "cell";
    const line = document.createElement("span");
    line.className = "title-line";
    const hex = colorHex(track.color);
    if (hex) {
      const swatch = document.createElement("span");
      swatch.className = "swatch";
      swatch.style.background = hex;
      line.append(swatch);
    }
    if (track.emoji) {
      const emoji = document.createElement("span");
      emoji.textContent = track.emoji;
      line.append(emoji);
    }
    const title = document.createElement("span");
    title.className = "title";
    title.textContent = track.name || "Untitled";
    line.append(title);
    if (track.missing) {
      const missing = document.createElement("span");
      missing.className = "missing-word";
      missing.textContent = "missing";
      line.append(missing);
    }
    if (track.stems) {
      const stems = document.createElement("span");
      stems.className = "missing-word";
      stems.textContent = "stems";
      line.append(stems);
    }
    titleCell.append(line);

    const artist = document.createElement("span");
    artist.className = "cell";
    artist.textContent = track.artist;

    const third = document.createElement("span");
    third.className = "cell num";
    const fourth = document.createElement("span");
    fourth.className = "cell num";
    const fifth = document.createElement("span");
    fifth.className = "cell num";
    if (track.entry) {
      third.textContent = track.deck || "";
      fourth.textContent = track.played || "";
      fifth.textContent = clockLabel(track.start);
    } else {
      third.textContent = track.bpm == null ? "" : String(Math.round(Number(track.bpm) * 100) / 100);
      fourth.textContent = track.key;
      fifth.textContent = lengthLabel(track.length_ms);
    }

    button.append(titleCell, artist, third, fourth, fifth);
    button.addEventListener("click", () => (track.entry ? selectEntry(track.id) : selectTrack(track.id)));
    rows.append(button);
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
function toggleCrate(id) {
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
    if (error.status === 409) lockDown(error);
    else setNotice(error.message);
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
function selectCrate(id) {
  state.activeCrate = id;
  if (id !== "all") expandAncestors(id);
  list.scrollTop = 0;
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
function focusCrateItem(item) {
  if (!item) return;
  for (const button of crateList.querySelectorAll(".crate")) button.tabIndex = -1;
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
async function selectTrack(id) {
  state.selectedId = id;
  syncMergeButton();
  paintRows();
  const token = ++state.request;
  const pending = document.createElement("p");
  pending.className = "detail-empty";
  pending.textContent = "Reading attributes";
  detail.replaceChildren(pending);
  try {
    const response = await fetch(`/api/track?id=${id}&space=${encodeURIComponent(state.space)}`);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `Could not read track (${response.status})`);
    if (token !== state.request) return;
    if (payload.serato) applyStatus(payload.serato);
    renderDetail(payload);
  } catch (error) {
    if (token !== state.request) return;
    const failure = document.createElement("p");
    failure.className = "detail-error";
    failure.textContent = error.message;
    detail.replaceChildren(failure);
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
function selectEntry(id) {
  state.selectedId = id;
  paintRows();
  const entry = state.entries.find((item) => item.id === id);
  if (!entry) return;
  const body = document.createElement("div");
  body.className = "detail-body";
  const title = document.createElement("h2");
  title.textContent = entry.name || "Untitled";
  body.append(title);
  if (entry.artist) {
    const artist = document.createElement("p");
    artist.className = "artist";
    artist.textContent = entry.artist;
    body.append(artist);
  }
  const lines = [
    ["Played", entry.played ? "Yes" : "No"],
    ["Deck", entry.deck || "—"],
    ["Started", clockLabel(entry.start_time) || "—"],
    ["File", entry.file || "—"],
  ];
  if (entry.notes) lines.push(["Notes", entry.notes]);
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
    open.type = "button";
    open.className = "text-button";
    open.textContent = "Open in library";
    open.addEventListener("click", () => openInLibrary(entry.asset_id));
    body.append(open);
  }
  detail.replaceChildren(body);
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
function fieldInput(name, label, value, wide = false) {
  const wrap = document.createElement("label");
  if (wide) wrap.className = "wide";
  wrap.append(document.createTextNode(label));
  const input = name === "comments"
    ? document.createElement("textarea")
    : document.createElement("input");
  input.name = name;
  input.value = value ?? "";
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
function renderDetail(track) {
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
  title.textContent = track.title;
  body.append(title);
  if (track.artist) {
    const artist = document.createElement("p");
    artist.className = "artist";
    artist.textContent = track.artist;
    body.append(artist);
  }

  const deck = document.createElement("div");
  deck.className = "deck";
  for (const [label, value] of [["BPM", track.bpm], ["Key", track.key || "—"], ["Time", track.length]]) {
    const cell = document.createElement("div");
    const strong = document.createElement("strong");
    strong.textContent = value || "—";
    if (label === "BPM") strong.style.color = "var(--cadmium)";
    const span = document.createElement("span");
    span.textContent = label;
    cell.append(strong, span);
    deck.append(cell);
  }
  if (track.color) {
    const cell = document.createElement("div");
    const swatch = document.createElement("span");
    swatch.className = "swatch";
    swatch.style.background = track.color;
    swatch.style.width = "18px";
    swatch.style.height = "18px";
    swatch.style.marginTop = "8px";
    const span = document.createElement("span");
    span.textContent = "Color";
    cell.append(swatch, span);
    deck.append(cell);
  }
  body.append(deck);

  const note = document.createElement("p");
  note.className = "lock-note";
  note.textContent = track.serato?.message || statusLine.textContent;
  body.append(note);

  const form = document.createElement("form");
  form.className = "editor";
  const edit = track.edit || {};
  for (const [name, label, wide] of [
    ["name", "Title", true],
    ["artist", "Artist", false],
    ["album", "Album", false],
    ["genre", "Genre", false],
    ["year", "Year", false],
    ["composer", "Composer", false],
    ["remixer", "Remixer", false],
    ["label", "Label", false],
    ["grouping", "Grouping", false],
    ["key", "Key", false],
    ["bpm", "BPM", false],
    ["emoji", "Emoji", false],
    ["comments", "Comments", true],
  ]) {
    form.append(fieldInput(name, label, edit[name], wide));
  }

  const colorLabel = document.createElement("label");
  colorLabel.append(document.createTextNode("Color"));
  const colorSelect = document.createElement("select");
  colorSelect.name = "color";
  const currentColor = Number(edit.color ?? 0xffffff);
  const palette = COLORS.some(([value]) => value === currentColor)
    ? COLORS
    : [...COLORS, [currentColor, colorHex(currentColor) || "Custom"]];
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
  ratingLabel.append(document.createTextNode("Rating"));
  const ratingSelect = document.createElement("select");
  ratingSelect.name = "rating";
  const ratings = [["", "Not rated"], ["0.2", "1 star"], ["0.4", "2 stars"], ["0.6", "3 stars"], ["0.8", "4 stars"], ["1", "5 stars"]];
  if (edit.rating != null && !ratings.some(([value]) => Number(value) === Number(edit.rating))) {
    ratings.push([String(edit.rating), `${edit.rating}`]);
  }
  for (const [value, label] of ratings) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    option.selected = value === (edit.rating == null ? "" : String(edit.rating));
    ratingSelect.append(option);
  }
  ratingLabel.append(ratingSelect);
  form.append(ratingLabel);

  const lock = document.createElement("label");
  lock.className = "check";
  const lockInput = document.createElement("input");
  lockInput.type = "checkbox";
  lockInput.name = "is_beatgrid_locked";
  lockInput.checked = Boolean(edit.is_beatgrid_locked);
  lock.append(lockInput, document.createTextNode("Beatgrid locked"));
  form.append(lock);

  const save = document.createElement("button");
  save.type = "submit";
  save.className = "text-button wide";
  save.textContent = "Save track";
  form.append(save);
  for (const control of form.querySelectorAll("input, select, textarea, button")) control.disabled = !writable;
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    saveTrack(track.id, form);
  });
  body.append(form);

  const actions = document.createElement("div");
  actions.className = "actions";
  const reveal = document.createElement("button");
  reveal.type = "button";
  const manager = track.serato?.file_manager || state.serato?.file_manager || "Finder";
  reveal.textContent = `Reveal in ${manager}`;
  reveal.disabled = !track.file_on_disk;
  reveal.addEventListener("click", () => revealTrack(track.id));
  const prepare = document.createElement("button");
  prepare.type = "button";
  prepare.textContent = track.in_prepare ? "Remove from Prepare" : "Send to Prepare";
  prepare.disabled = !writable;
  prepare.addEventListener("click", () => prepareTrack(track.id, !track.in_prepare));
  const relocate = document.createElement("button");
  relocate.type = "button";
  relocate.textContent = "Relocate";
  relocate.disabled = !writable;
  relocate.addEventListener("click", () => relocateTrack(track));
  const remove = document.createElement("button");
  remove.type = "button";
  remove.textContent = "Remove from library";
  remove.disabled = !writable;
  remove.addEventListener("click", () => removeTrack(track.id));
  actions.append(reveal, prepare, relocate, remove);
  if (state.mode === "duplicates" && selectedDuplicateGroup()) {
    const merge = document.createElement("button");
    merge.type = "button";
    merge.textContent = "Merge copies";
    merge.disabled = !writable;
    merge.addEventListener("click", () => {
      openMergeDialog().catch((error) => setNotice(error.message));
    });
    actions.append(merge);
  }
  body.append(actions);

  body.append(relatedSection(track, writable));
  body.append(markerSection(track));
  if (track.copies?.length) body.append(copySection(track.copies));
  body.append(membershipSection(track, writable));

  for (const group of track.groups) {
    const section = document.createElement("section");
    section.className = "group";
    const heading = document.createElement("h3");
    heading.textContent = group.name;
    section.append(heading);
    const open = group.name !== "Search copies";
    if (!open) {
      const toggle = document.createElement("button");
      toggle.type = "button";
      toggle.className = "text-button";
      toggle.textContent = `Search copies, ${group.fields.length} fields`;
      let shown = false;
      section.hidden = true;
      toggle.addEventListener("click", () => {
        shown = !shown;
        section.hidden = !shown;
        toggle.textContent = shown ? "Hide search copies" : `Search copies, ${group.fields.length} fields`;
      });
      body.append(toggle);
    }
    for (const field of group.fields) {
      const row = document.createElement("div");
      row.className = "field";
      const label = document.createElement("div");
      label.className = "label";
      label.textContent = field.label;
      const column = document.createElement("span");
      column.className = "column";
      column.textContent = field.column;
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
  detail.replaceChildren(body);
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
function markerSection(track) {
  const section = document.createElement("section");
  section.className = "group";
  const heading = document.createElement("h3");
  heading.textContent = "Cues, loops, and beatgrid";
  section.append(heading);
  const note = document.createElement("p");
  note.className = "detail-kicker";
  if (track.markers_unavailable) note.textContent = "The file is not on disk, so cues cannot be read.";
  else if (!track.markers_found) note.textContent = "No Serato cues in this file.";
  else note.textContent = "Read from the audio file. These are not written back.";
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
  const ms = (value) => {
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
  const beatSeconds = (value) => {
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
    name.textContent = cue.name || `Cue ${cue.index + 1}`;
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
    name.textContent = loop.name || `Loop ${loop.index + 1}${loop.locked ? " locked" : ""}`;
    row.append(swatch, time, name);
    section.append(row);
  }
  for (const flip of track.flips || []) {
    const row = document.createElement("div");
    row.className = "marker";
    const time = document.createElement("span");
    time.textContent = flip.enabled ? "On" : "Off";
    const name = document.createElement("span");
    name.textContent = flip.name || `Flip ${flip.index + 1}`;
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
      name.textContent = `${bpmNumber} BPM`;
    } else if (mark.beats != null) {
      name.textContent = `${mark.beats} beats`;
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
function copySection(copies) {
  const section = document.createElement("section");
  section.className = "group";
  const heading = document.createElement("h3");
  heading.textContent = "Other copies";
  section.append(heading);
  for (const copy of copies) {
    const row = document.createElement("div");
    row.className = "copy-row";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "text-button";
    button.textContent = copy.file || `Track ${copy.id}`;
    button.addEventListener("click", () => selectTrack(copy.id));
    const rate = document.createElement("span");
    rate.textContent = copy.bitrate;
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
 * Related-track request counter.
 *
 * A slow reply must not paint into a track the user has already left.
 * Incremented by loadRelated. Not sent anywhere.
 */
let relatedRequest = 0;

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
function relatedSection(track, writable) {
  const section = document.createElement("section");
  section.className = "group";
  section.dataset.trackId = String(track.id);
  const heading = document.createElement("h3");
  heading.id = `related-heading-${track.id}`;
  heading.textContent = "Related tracks";
  section.setAttribute("aria-labelledby", heading.id);
  section.setAttribute("aria-busy", "true");
  const status = document.createElement("p");
  status.className = "detail-kicker";
  status.setAttribute("role", "status");
  const path = track.resolved_path || track.edit?.portable_id || "";
  status.textContent = path ? "Loading related tracks" : "This track has no file path, so it cannot be linked.";
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
async function loadRelated(track, section, writable, query) {
  const token = ++relatedRequest;
  const path = track.resolved_path || track.edit?.portable_id || "";
  const params = new URLSearchParams({ path, space: state.space });
  try {
    const response = await fetch(`/api/related?${params}`);
    const payload = await response.json().catch(() => ({}));
    if (token !== relatedRequest || !section.isConnected) return;
    if (!response.ok) throw new Error(payload.error || "Related tracks could not be loaded.");
    renderRelated(track, section, writable, payload, query);
  } catch (error) {
    if (token !== relatedRequest || !section.isConnected) return;
    section.setAttribute("aria-busy", "false");
    const status = section.querySelector("[role=status]");
    if (status) status.textContent = error.message;
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
function renderRelated(track, section, writable, payload, query) {
  const heading = section.querySelector("h3");
  section.replaceChildren(heading);
  section.setAttribute("aria-busy", "false");
  const saved = Array.isArray(payload.saved) ? payload.saved : [];
  const suggested = Array.isArray(payload.suggested) ? payload.suggested : [];
  const status = document.createElement("p");
  status.className = "detail-kicker";
  status.setAttribute("role", "status");
  status.textContent = saved.length
    ? `${saved.length} saved`
    : "No saved links yet. Search for a track, or save a suggestion.";
  section.append(status);
  if (saved.length) section.append(relatedSavedList(track, section, saved));

  section.append(relatedSearch(track, section, query));

  const suggestHeading = document.createElement("p");
  suggestHeading.className = "detail-kicker";
  suggestHeading.textContent = suggested.length
    ? "Suggested from key, tempo within 6%, and shared crates. Save stores a two-way link."
    : "No suggestions from key, tempo, or shared crates.";
  section.append(suggestHeading);
  if (suggested.length) section.append(relatedSuggestList(track, section, suggested));

  const crate = document.createElement("button");
  crate.type = "button";
  crate.className = "text-button";
  crate.dataset.relatedCrate = "true";
  const crateName = payload.crate_name || "Related";
  crate.textContent = "Update Serato crate";
  crate.disabled = !writable;
  crate.addEventListener("click", () => refreshRelatedCrate(track, section));
  const crateNote = document.createElement("p");
  crateNote.className = "detail-kicker";
  crateNote.textContent = writable
    ? `Creates or refreshes the crate “${crateName}”. Serato must be quit.`
    : "Quit Serato before writing the crate.";
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
function relatedSavedList(track, section, saved) {
  const list = document.createElement("ul");
  list.className = "related-list";
  for (const link of saved) {
    const item = document.createElement("li");
    item.className = "related-row";
    const main = document.createElement("div");
    const other = link.track || {};
    const label = other.title || "Untitled";
    if (other.asset_id != null && other.in_library) {
      const open = document.createElement("button");
      open.type = "button";
      open.className = "text-button";
      open.textContent = label;
      open.addEventListener("click", () => selectTrack(other.asset_id));
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
    if (other.bpm != null && other.bpm !== "") bits.push(`${other.bpm} BPM`);
    bits.push(link.mutual ? "Two-way" : "One-way");
    if (link.rating != null) bits.push(`${link.rating}/5`);
    if (!other.in_library) bits.push("Not in this library");
    meta.textContent = bits.join(" · ");
    main.append(meta);
    if (link.note) {
      const note = document.createElement("p");
      note.className = "related-note";
      note.textContent = link.note;
      main.append(note);
    }
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "text-button";
    remove.textContent = "Remove";
    remove.setAttribute("aria-label", `Remove link to ${label}`);
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
function relatedSearch(track, section, query) {
  const block = document.createElement("div");
  block.className = "related-search";
  const label = document.createElement("label");
  label.append(document.createTextNode("Find a track to link"));
  const input = document.createElement("input");
  input.type = "search";
  input.autocomplete = "off";
  input.placeholder = "Title or artist";
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
      hint.textContent = "Type a title or artist.";
      results.append(hint);
      return;
    }
    const hits = state.tracks
      .filter((item) => item.id !== track.id && matchesQuery(item, terms))
      .slice(0, 8);
    if (!hits.length) {
      const empty = document.createElement("li");
      empty.className = "related-meta";
      empty.textContent = "No tracks match.";
      results.append(empty);
      return;
    }
    for (const hit of hits) {
      const item = document.createElement("li");
      const choose = document.createElement("button");
      choose.type = "button";
      choose.className = "text-button";
      choose.textContent = hit.artist ? `${hit.name || "Untitled"} · ${hit.artist}` : (hit.name || "Untitled");
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
function relatedLinkForm(track, section, form, hit, query) {
  form.hidden = false;
  form.replaceChildren();
  const chosen = document.createElement("p");
  chosen.className = "related-meta";
  chosen.textContent = hit.artist ? `${hit.name || "Untitled"} · ${hit.artist}` : (hit.name || "Untitled");
  const noteLabel = document.createElement("label");
  noteLabel.append(document.createTextNode("Note"));
  const note = document.createElement("input");
  note.type = "text";
  note.maxLength = 500;
  note.placeholder = "blend out of";
  noteLabel.append(note);
  const ratingLabel = document.createElement("label");
  ratingLabel.append(document.createTextNode("Link rating"));
  const rating = document.createElement("select");
  for (const [value, text] of [["", "Not rated"], ["1", "1"], ["2", "2"], ["3", "3"], ["4", "4"], ["5", "5"]]) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = text;
    rating.append(option);
  }
  ratingLabel.append(rating);
  const mutualLabel = document.createElement("label");
  mutualLabel.className = "check";
  const mutual = document.createElement("input");
  mutual.type = "checkbox";
  mutual.checked = true;
  mutualLabel.append(mutual, document.createTextNode("Two-way link"));
  const save = document.createElement("button");
  save.type = "button";
  save.className = "text-button";
  save.textContent = "Save link";
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
function relatedSuggestList(track, section, suggested) {
  const list = document.createElement("ul");
  list.className = "related-list";
  for (const item of suggested) {
    const row = document.createElement("li");
    row.className = "related-row";
    const main = document.createElement("div");
    const name = document.createElement("span");
    name.textContent = item.artist ? `${item.title || "Untitled"} · ${item.artist}` : (item.title || "Untitled");
    const reasons = document.createElement("p");
    reasons.className = "related-meta";
    reasons.textContent = Array.isArray(item.reasons) ? item.reasons.join(" · ") : "";
    main.append(name, reasons);
    const save = document.createElement("button");
    save.type = "button";
    save.className = "text-button";
    save.textContent = "Save";
    save.setAttribute("aria-label", `Save link to ${item.title || "Untitled"}`);
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
async function saveRelated(track, section, body, query) {
  try {
    await postJSON("/api/related", body);
    setNotice("Link saved.");
    const kept = section.querySelector(".related-search input");
    await loadRelated(track, section, Boolean(track.serato?.writable && state.writable), kept ? kept.value : query);
  } catch (error) {
    if (error.status === 409) lockDown(error);
    else setNotice(error.message);
    const status = section.querySelector("[role=status]");
    if (status) status.textContent = error.message;
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
async function removeRelated(track, section, link) {
  const label = link.track?.title || "this track";
  if (!confirm(`Remove the link to “${label}”?`)) return;
  try {
    await postJSON("/api/related", { action: "remove", id: link.id });
    setNotice("Link removed.");
    const kept = section.querySelector(".related-search input");
    await loadRelated(track, section, Boolean(track.serato?.writable && state.writable), kept ? kept.value : "");
  } catch (error) {
    setNotice(error.message);
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
async function refreshRelatedCrate(track, section) {
  const button = section.querySelector("[data-related-crate]");
  if (button) button.disabled = true;
  try {
    const result = await postJSON("/api/related", { action: "crate", asset: track.id, space: state.space });
    setNotice(result.warning || `Crate “${result.name}” updated.`);
    await loadLibrary();
    selectTrack(track.id);
  } catch (error) {
    if (error.status === 409) {
      lockDown(error);
      if (button) button.disabled = true;
    } else {
      setNotice(error.message);
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
function membershipSection(track, writable) {
  const section = document.createElement("section");
  section.className = "group";
  const heading = document.createElement("h3");
  heading.textContent = "Crates";
  section.append(heading);
  const holder = document.createElement("div");
  holder.className = "member-list";
  const chosen = new Set(track.crate_ids || []);
  const crates = [...state.crates].filter((crate) => !crate.smart).sort((a, b) => a.name.localeCompare(b.name));
  for (const crate of crates) {
    const label = document.createElement("label");
    label.className = "member";
    const input = document.createElement("input");
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
    line.textContent = `Smart crates: ${smart.map((crate) => crate.name).join(", ")}`;
    section.append(line);
  }
  section.append(holder);
  return section;
}

/**
 * Move the list selection by one visible row and keep it on screen.
 *
 * History rows call selectEntry. Library rows call selectTrack. The scroll
 * window follows the row so the selection does not leave the viewport.
 *
 * @param {number} delta 1 for the next row, -1 for the previous row.
 * @returns {void}
 */
function moveSelection(delta) {
  const view = state.view || [];
  const index = view.findIndex((track) => track.id === state.selectedId);
  const next = view[Math.max(0, Math.min(view.length - 1, index + delta))];
  if (!next) return;
  if (next.entry) selectEntry(next.id);
  else selectTrack(next.id);
  const rowTop = view.indexOf(next) * ROW;
  if (rowTop < list.scrollTop) list.scrollTop = rowTop;
  if (rowTop + ROW > list.scrollTop + list.clientHeight) {
    list.scrollTop = rowTop + ROW - list.clientHeight;
  }
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
function setNotice(text) {
  notice.textContent = text || "";
  notice.hidden = !text;
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
function applyStatus(info) {
  state.serato = info;
  state.writable = Boolean(info?.writable);
  statusLine.textContent = info?.message || "Library";
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
function lockDown(error) {
  applyStatus(error.payload?.serato || { writable: false, message: error.message });
  setNotice(error.message);
}

/**
 * POST a JSON body and return the decoded payload.
 *
 * Sends Content-Type application/json. A failed response becomes an Error
 * with status and payload so callers can recognize a 409 lock. Does not
 * choose the route; the caller passes /api/track, /api/crate, /api/import.m3u,
 * or /api/reveal.
 *
 * @param {string} url API path.
 * @param {object} body JSON-compatible request body.
 * @returns {Promise<object>} The decoded JSON object.
 */
async function postJSON(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(payload.error || `Request failed (${response.status})`);
    error.status = response.status;
    error.payload = payload;
    throw error;
  }
  return payload;
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
async function saveTrack(id, form) {
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
    is_beatgrid_locked: form.querySelector("[name=is_beatgrid_locked]").checked,
  };
  if (bpm !== "" && Number.isNaN(fields.bpm)) {
    setNotice("BPM needs a number.");
    return;
  }
  try {
    const result = await postJSON("/api/track", { id, space: state.space, fields });
    setNotice(result.warning || "Saved.");
    await loadLibrary();
    selectTrack(id);
  } catch (error) {
    if (error.status === 409) lockDown(error);
    else setNotice(error.message);
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
async function revealTrack(id) {
  try {
    await postJSON("/api/reveal", { id });
  } catch (error) {
    setNotice(error.message);
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
async function prepareTrack(id, add) {
  try {
    const result = await postJSON("/api/crate", { action: "prepare", asset: id, add, space: state.space });
    setNotice(result.warning || (add ? "Sent to Prepare." : "Removed from Prepare."));
    await loadLibrary();
    selectTrack(id);
  } catch (error) {
    if (error.status === 409) lockDown(error);
    else setNotice(error.message);
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
async function relocateTrack(track) {
  const path = prompt("Path to the audio file", track.resolved_path || track.edit?.portable_id || "");
  if (!path) return;
  try {
    const result = await postJSON("/api/track", {
      id: track.id,
      space: state.space,
      fields: { portable_id: path },
    });
    setNotice(result.warning || "File location saved.");
    await loadLibrary();
    selectTrack(track.id);
  } catch (error) {
    if (error.status === 409) lockDown(error);
    else setNotice(error.message);
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
async function removeTrack(id) {
  if (!confirm("Remove this track from the library? The audio file stays on disk.")) return;
  try {
    const result = await postJSON("/api/crate", { action: "remove_library", asset: id, space: state.space });
    setNotice(result.warning || "Removed from the library.");
    state.selectedId = null;
    await loadLibrary();
  } catch (error) {
    if (error.status === 409) lockDown(error);
    else setNotice(error.message);
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
async function setMembership(assetId, crateId, add, input) {
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
    if (error.status === 409) lockDown(error);
    else setNotice(error.message);
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
async function saveRules(id, text) {
  let rules;
  try {
    rules = JSON.parse(text);
  } catch {
    setNotice("Smart crate rules need to be JSON.");
    return;
  }
  try {
    const result = await postJSON("/api/crate", { action: "rules", id, rules, space: state.space });
    setNotice(result.warning || "Rules saved.");
    await loadLibrary();
    selectCrate(id);
  } catch (error) {
    if (error.status === 409) lockDown(error);
    else setNotice(error.message);
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
async function createCrate() {
  const name = prompt("New crate name");
  if (!name || !name.trim()) return;
  const parent = state.activeCrate === "all" ? state.rootId : state.activeCrate;
  try {
    const result = await postJSON("/api/crate", { action: "create", name: name.trim(), parent, space: state.space });
    setNotice(result.warning || "Crate created.");
    await loadLibrary();
    selectCrate(result.id);
  } catch (error) {
    if (error.status === 409) lockDown(error);
    else setNotice(error.message);
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
async function renameCrate() {
  const crate = state.crates.find((item) => item.id === state.activeCrate);
  if (!crate) return;
  const name = prompt("Rename crate", crate.name);
  if (!name || !name.trim() || name.trim() === crate.name) return;
  try {
    const result = await postJSON("/api/crate", { action: "rename", id: crate.id, name: name.trim(), space: state.space });
    setNotice(result.warning || "Crate renamed.");
    await loadLibrary();
    selectCrate(crate.id);
  } catch (error) {
    if (error.status === 409) lockDown(error);
    else setNotice(error.message);
  }
}

/**
 * Prompt for a palette name and save it on the selected crate.
 *
 * The names match COLOR_NAMES. White is sent as null, which is Serato's
 * "no color" value. POST /api/crate with action color. A 409 locks the page.
 *
 * @returns {Promise<void>}
 */
async function colorCrate() {
  const crate = state.crates.find((item) => item.id === state.activeCrate);
  if (!crate) return;
  const choice = prompt("Crate color: none, red, orange, yellow, green, blue, purple, pink");
  if (choice == null) return;
  const color = COLOR_NAMES[choice.trim().toLowerCase()];
  if (color == null) {
    setNotice("Use one of the palette names.");
    return;
  }
  try {
    const result = await postJSON("/api/crate", {
      action: "color",
      id: crate.id,
      color: color === 0xffffff ? null : color,
      space: state.space,
    });
    setNotice(result.warning || "Crate color saved.");
    await loadLibrary();
  } catch (error) {
    if (error.status === 409) lockDown(error);
    else setNotice(error.message);
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
async function deleteCrate() {
  const crate = state.crates.find((item) => item.id === state.activeCrate);
  if (!crate) return;
  if (!confirm(`Delete “${crate.name}” and the crates inside it? The tracks stay in the library.`)) return;
  try {
    const result = await postJSON("/api/crate", { action: "delete", id: crate.id, space: state.space });
    state.activeCrate = "all";
    setNotice(result.warning || "Crate deleted.");
    await loadLibrary();
  } catch (error) {
    if (error.status === 409) lockDown(error);
    else setNotice(error.message);
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
async function importPlaylist(file) {
  const text = await file.text();
  const name = file.name.replace(/\.m3u8?$/i, "") || "Imported playlist";
  const parent = state.activeCrate === "all" ? state.rootId : state.activeCrate;
  try {
    const result = await postJSON("/api/import.m3u", { space: state.space, parent, name, text });
    const missed = result.unmatched_count ? ` ${result.unmatched_count} lines did not match a library track.` : "";
    setNotice(`${result.added} tracks added.${missed}${result.warning ? ` ${result.warning}` : ""}`);
    await loadLibrary();
    selectCrate(result.id);
  } catch (error) {
    if (error.status === 409) lockDown(error);
    else setNotice(error.message);
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
function renderSessions() {
  sessionList.replaceChildren();
  for (const session of state.historySessions) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "crate";
    button.setAttribute("role", "option");
    button.setAttribute("aria-selected", String(session.id === state.historyId));
    const name = document.createElement("span");
    name.className = "name";
    name.textContent = session.name || "Session";
    const meta = document.createElement("span");
    meta.className = "meta";
    meta.textContent = String(session.played || 0);
    button.append(name, meta);
    button.addEventListener("click", () => openSession(session.id));
    sessionList.append(button);
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
async function loadHistory() {
  const response = await fetch("/api/history");
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || "Could not read history.");
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
async function openSession(id) {
  state.historyId = id;
  state.selectedId = null;
  renderSessions();
  const response = await fetch(`/api/history?session=${id}`);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    setNotice(payload.error || "Could not read that session.");
    return;
  }
  state.entries = payload.entries || [];
  list.scrollTop = 0;
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
async function loadDuplicates() {
  state.duplicateIds = null;
  state.duplicateGroups = [];
  const response = await fetch(`/api/duplicates?space=${encodeURIComponent(state.space)}`);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || "Could not read duplicates.");
  const ids = new Set();
  state.duplicateGroups = payload.groups || [];
  for (const group of state.duplicateGroups) for (const id of group.ids) ids.add(id);
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
async function openInLibrary(assetId) {
  state.space = "Serato Library";
  spaceSelect.value = state.space;
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
async function loadLibrary() {
  count.textContent = "Loading the library";
  const response = await fetch(`/api/library?space=${encodeURIComponent(state.space)}`);
  const library = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(library.error || `Could not read the library (${response.status})`);
  const selected = state.selectedId;
  const active = state.activeCrate;
  state.tracks = library.tracks;
  state.byId = new Map(library.tracks.map((track) => [track.id, track]));
  state.crates = library.crates;
  state.rootId = library.root_id;
  state.crateTracks = new Map(library.crates.map((crate) => [crate.id, new Set(crate.tracks)]));
  state.expanded = new Set(library.crates.filter((crate) => crate.expanded).map((crate) => crate.id));
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
function setMode(mode) {
  state.mode = mode;
  list.scrollTop = 0;
  if (mode === "history") {
    state.sort = "start";
    state.sortDir = -1;
    if (!state.historySessions.length) loadHistory().catch((error) => setNotice(error.message));
  } else if (state.sort === "start" || state.sort === "deck" || state.sort === "played") {
    state.sort = "name";
    state.sortDir = 1;
  }
  if (mode === "duplicates" && state.duplicateSpace !== state.space) {
    loadDuplicates().catch((error) => setNotice(error.message));
  }
  if (mode === "files") {
    state.filesLoading = true;
    loadFolder(state.filesPath || "").catch((error) => failFiles(error));
  }
  renderList();
}

// Wire the page controls. These listeners call the functions above; they
// do not open the database themselves. Export builds a download URL for
// GET /api/export.m3u. Rekordbox builds one for GET /api/export.rekordbox.xml.
// Import reads a local file and posts its text.
search.addEventListener("input", () => {
  state.query = search.value;
  list.scrollTop = 0;
  renderList();
});

document.getElementById("crate-search").addEventListener("input", (event) => {
  state.crateQuery = event.target.value;
  renderCrates();
});

document.getElementById("reload").addEventListener("click", () => {
  const jobs = [loadLibrary()];
  if (state.mode === "history") jobs.push(loadHistory());
  if (state.mode === "duplicates") jobs.push(loadDuplicates());
  Promise.all(jobs).catch(showFailure);
});

document.getElementById("export-m3u").addEventListener("click", () => {
  const crate = state.mode === "crates" ? state.activeCrate : "all";
  const link = document.createElement("a");
  link.href = `/api/export.m3u?space=${encodeURIComponent(state.space)}&crate=${encodeURIComponent(crate)}`;
  link.download = "crate.m3u";
  link.click();
});

/**
 * Build the Rekordbox export URL for the current space and crate.
 *
 * The report form asks for the loss report as JSON. The file form is the
 * XML download, which starts only after the dialog is confirmed.
 *
 * @param {boolean} report True asks for the loss report instead of the file.
 * @returns {string} The request path and query.
 */
function rekordboxExportUrl(report) {
  const crate = state.mode === "crates" ? state.activeCrate : "all";
  const memory = document.getElementById("rekordbox-memory").checked ? "1" : "0";
  const key = document.getElementById("rekordbox-key").value;
  const base = `/api/export.rekordbox.xml?space=${encodeURIComponent(state.space)}&crate=${encodeURIComponent(crate)}&memory=${memory}&key=${encodeURIComponent(key)}`;
  return report ? `${base}&report=1` : base;
}

/**
 * Fill the export dialog list with one item per loss-report line.
 *
 * Text is set with textContent. An empty report leaves the list empty.
 *
 * @param {string[]} lines Sentences from the export.
 * @returns {void}
 */
function fillRekordboxReport(lines) {
  const list = document.getElementById("rekordbox-report");
  list.replaceChildren();
  for (const line of lines) {
    const item = document.createElement("li");
    item.textContent = line;
    list.append(item);
  }
}

let rekordboxXml = "";

document.getElementById("export-rekordbox").addEventListener("click", () => {
  rekordboxXml = "";
  fetch(rekordboxExportUrl(true))
    .then((response) => response.json().then((body) => ({ ok: response.ok, body })))
    .then(({ ok, body }) => {
      if (!ok || typeof body.xml !== "string" || !body.xml.startsWith("<?xml")) {
        setNotice(body.error || "The Rekordbox export failed.");
        return;
      }
      rekordboxXml = body.xml;
      fillRekordboxReport(body.report || []);
      document.getElementById("rekordbox-status").textContent = "";
      document.getElementById("rekordbox-dialog").showModal();
    })
    .catch((error) => setNotice(error.message));
});

document.getElementById("rekordbox-cancel").addEventListener("click", () => {
  rekordboxXml = "";
  document.getElementById("rekordbox-dialog").close();
});

document.getElementById("rekordbox-download").addEventListener("click", () => {
  if (!rekordboxXml.startsWith("<?xml")) {
    document.getElementById("rekordbox-status").textContent = "The export did not produce an XML file.";
    return;
  }
  const blob = new Blob([rekordboxXml], { type: "application/xml" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "rekordbox.xml";
  link.click();
  // Safari and Firefox need the object URL until the download has started.
  setTimeout(() => URL.revokeObjectURL(url), 1500);
  rekordboxXml = "";
  document.getElementById("rekordbox-dialog").close();
});

document.getElementById("import-m3u").addEventListener("click", () => {
  if (!state.writable) {
    setNotice(statusLine.textContent);
    return;
  }
  document.getElementById("import-file").click();
});

document.getElementById("import-file").addEventListener("change", (event) => {
  const file = event.target.files?.[0];
  event.target.value = "";
  if (file) importPlaylist(file).catch((error) => setNotice(error.message));
});

spaceSelect.addEventListener("change", () => {
  state.space = spaceSelect.value;
  state.activeCrate = "all";
  state.selectedId = null;
  state.duplicateIds = null;
  state.duplicateGroups = [];
  loadLibrary().then(() => {
    if (state.mode === "duplicates") return loadDuplicates();
    return null;
  }).catch(showFailure);
});

document.getElementById("views").addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (button?.dataset.view) setMode(button.dataset.view);
});

document.querySelector(".sort-crates").addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (!button?.dataset.crateSort) return;
  state.crateSort = button.dataset.crateSort;
  renderCrates();
  renderShell();
});

document.getElementById("crate-new").addEventListener("click", () => createCrate().catch((error) => setNotice(error.message)));
document.getElementById("crate-rename").addEventListener("click", () => renameCrate().catch((error) => setNotice(error.message)));
document.getElementById("crate-color").addEventListener("click", () => colorCrate().catch((error) => setNotice(error.message)));
document.getElementById("crate-delete").addEventListener("click", () => deleteCrate().catch((error) => setNotice(error.message)));
document.getElementById("merge-duplicates").addEventListener("click", () => {
  openMergeDialog().catch((error) => setNotice(error.message));
});
document.getElementById("merge-cancel").addEventListener("click", () => mergeDialog.close());
document.getElementById("merge-confirm").addEventListener("click", () => {
  confirmMerge().catch((error) => setNotice(error.message));
});
document.getElementById("merge-trash").addEventListener("change", () => syncTrashChoice());

document.querySelector(".columns").addEventListener("click", (event) => {
  const button = event.target.closest("button");
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
crateList.addEventListener("keydown", (event) => {
  const item = event.target.closest?.(".crate");
  if (!item || !crateList.contains(item)) return;
  const items = [...crateList.querySelectorAll(".crate")];
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

list.addEventListener("scroll", () => paintRows());
list.addEventListener("keydown", (event) => {
  if (event.key === "ArrowDown") {
    event.preventDefault();
    moveSelection(1);
  } else if (event.key === "ArrowUp") {
    event.preventDefault();
    moveSelection(-1);
  }
});

/**
 * Replace the detail pane when the library cannot be read.
 *
 * Used for the first load and for reload failures. The count line says
 * the library is unavailable. Does not retry by itself.
 *
 * @param {Error} error Failure from loadLibrary or a related request.
 * @returns {void}
 */
function showFailure(error) {
  count.textContent = "Library unavailable";
  const failure = document.createElement("p");
  failure.className = "detail-error";
  failure.textContent = error.message;
  detail.replaceChildren(failure);
}

/**
 * Return the duplicate group that contains the selected track.
 *
 * Groups come from GET /api/duplicates. A track outside that view, or a
 * track that is not in a group, returns null. Does not fetch.
 *
 * @returns {object|null} The group, with an ids array, or null.
 */
function selectedDuplicateGroup() {
  if (state.mode !== "duplicates" || state.selectedId == null) return null;
  return (state.duplicateGroups || []).find((group) => (group.ids || []).includes(state.selectedId)) || null;
}

/**
 * Enable Merge copies when a duplicate group is selected and Serato is quit.
 *
 * The button lives in the duplicates rail. Other views hide it. Does not fetch.
 *
 * @returns {void}
 */
function syncMergeButton() {
  const wrap = document.getElementById("duplicate-actions");
  const button = document.getElementById("merge-duplicates");
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
function crateNamesFor(assetId) {
  return state.crates
    .filter((crate) => !crate.smart && (crate.tracks || []).includes(assetId))
    .map((crate) => crate.name);
}

const mergeDialog = document.getElementById("merge-dialog");
const mergeChoices = document.getElementById("merge-choices");
const mergePreviewBox = document.getElementById("merge-preview");
const mergeStatus = document.getElementById("merge-status");
const mergeTrash = document.getElementById("merge-trash");
const mergeConfirm = document.getElementById("merge-confirm");
let mergePreview = null;
let mergeToken = 0;
let mergeLoading = false;

/**
 * Read the keep-copy radio the dialog currently has selected.
 *
 * Falls back to the track selected in the list. Does not fetch.
 *
 * @returns {number|null} Asset id, or null when no radio is checked.
 */
function selectedMergeKeepId() {
  const checked = mergeChoices.querySelector("input:checked");
  if (checked) return Number(checked.value);
  return state.selectedId;
}

/**
 * Format one merge-preview value for the dialog.
 *
 * Empty values read as "empty". A date added includes the year and the
 * seconds, so two copies added in the same minute still look different.
 * Other values stay as the server sent them. Does not fetch.
 *
 * @param {string} field Column name.
 * @param {unknown} value Value from the plan.
 * @returns {string} Text for one side of a change.
 */
function previewFieldValue(field, value) {
  if (value == null || value === "") return "empty";
  if (field === "time_added") {
    const date = new Date(Number(value) * 1000);
    if (!Number.isNaN(date.getTime())) {
      return date.toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "numeric",
        minute: "2-digit",
        second: "2-digit",
      });
    }
  }
  return String(value);
}

/**
 * Show one merge plan in the dialog.
 *
 * The list is built with text nodes. File paths from the server are not
 * part of this payload. Does not fetch.
 *
 * @param {object|null} preview Plan from POST /api/duplicates/merge, or null while it loads.
 * @returns {void}
 */
function renderMergePreview(preview) {
  mergePreviewBox.replaceChildren();
  if (!preview) {
    const pending = document.createElement("p");
    pending.textContent = "Reading the preview…";
    mergePreviewBox.append(pending);
    return;
  }
  const list = document.createElement("ul");
  list.className = "merge-preview";
  const added = preview.crates_added || [];
  const item = (text) => {
    const line = document.createElement("li");
    line.textContent = text;
    list.append(line);
  };
  if (added.length) {
    const names = added.map((crate) => (
      crate.space && crate.space !== state.space ? `${crate.name} (${crate.space})` : crate.name
    ));
    item(`Add the kept copy to ${names.join(", ")}.`);
  } else if ((preview.crates_kept || []).length) {
    item("The kept copy is already in every crate the others use. It stays where it is.");
  } else {
    item("None of the copies are in a crate.");
  }
  for (const space of preview.spaces_added || []) item(`Add the kept copy to the ${space} space.`);
  if ((preview.fields || []).length) {
    for (const field of preview.fields) {
      const before = previewFieldValue(field.field, field.before);
      const after = previewFieldValue(field.field, field.after);
      item(`${field.label} changes from ${before} to ${after}.`);
    }
  } else {
    item("No empty fields or higher play count to copy.");
  }
  if (preview.history_repointed) {
    const count = Number(preview.history_entries) || 0;
    item(count
      ? `Point ${count} history ${count === 1 ? "entry" : "entries"} at the kept copy.`
      : "No history entries point at the other copies.");
  } else {
    item("This library has no history track id to repoint.");
  }
  const removed = (preview.removed || []).length;
  item(`Remove ${removed} ${removed === 1 ? "copy" : "copies"} from the library.`);
  for (const file of preview.files || []) {
    if (file.reason) item(`${file.file}: ${file.reason}`);
  }
  mergePreviewBox.append(list);
  if (preview.cue_warning) {
    const warning = document.createElement("p");
    warning.className = "merge-warning";
    warning.textContent = preview.cue_warning;
    mergePreviewBox.append(warning);
  }
  const files = document.createElement("p");
  files.id = "merge-file-note";
  files.className = "dialog-note";
  mergePreviewBox.append(files);
}

/**
 * Match the Trash checkbox and the confirm button to the current plan.
 *
 * The checkbox stays off, and stays disabled, unless a duplicate file can
 * be moved safely. Does not fetch.
 *
 * @returns {void}
 */
function syncTrashChoice() {
  const files = mergePreview?.files || [];
  const trashable = files.filter((file) => file.on_disk && !file.blocks_trash);
  const blocked = files.some((file) => file.blocks_trash);
  mergeTrash.disabled = !mergePreview || mergeLoading || blocked || trashable.length === 0;
  if (mergeTrash.disabled) mergeTrash.checked = false;
  const danger = mergeTrash.checked;
  mergeConfirm.classList.toggle("danger", danger);
  mergeConfirm.textContent = mergeLoading ? "Merging…" : (danger ? "Merge and move files to Trash" : "Merge copies");
  mergeConfirm.disabled = mergeLoading || !mergePreview || mergePreview.writable === false;
  const note = document.getElementById("merge-file-note");
  if (!note) return;
  if (danger) note.textContent = `Move ${trashable.map((file) => file.file).join(", ")} to the Trash.`;
  else note.textContent = "Audio files stay on disk.";
}

/**
 * Ask for a merge plan for the selected keep copy.
 *
 * POST /api/duplicates/merge with preview true. A slow reply is ignored
 * when a newer choice has already been made. The dialog shows the error
 * and leaves the library unchanged.
 *
 * @returns {Promise<void>}
 */
async function refreshMergePreview() {
  const keepId = selectedMergeKeepId();
  const token = ++mergeToken;
  mergeLoading = false;
  mergePreview = null;
  mergeStatus.textContent = "";
  renderMergePreview(null);
  syncTrashChoice();
  mergeConfirm.disabled = true;
  try {
    const preview = await postJSON("/api/duplicates/merge", {
      space: state.space,
      keep_id: keepId,
      preview: true,
    });
    if (token !== mergeToken) return;
    mergePreview = preview;
    renderMergePreview(preview);
    if (preview.writable === false) {
      mergeStatus.textContent = "Quit Serato before merging. The preview shows the plan.";
    }
    syncTrashChoice();
  } catch (error) {
    if (token !== mergeToken) return;
    mergePreview = null;
    mergePreviewBox.replaceChildren();
    const failed = document.createElement("p");
    failed.textContent = "The preview could not be read.";
    mergePreviewBox.append(failed);
    mergeStatus.textContent = error.message;
    syncTrashChoice();
  }
}

/**
 * Build the keep-copy radios for the selected duplicate group.
 *
 * The selected track starts checked. Changing the radio loads a new plan.
 * Does not write the library.
 *
 * @returns {void}
 */
function renderMergeChoices() {
  const group = selectedDuplicateGroup();
  mergeChoices.replaceChildren();
  if (!group) return;
  for (const id of group.ids) {
    const track = state.byId.get(id) || { id, file: "", play_count: null, missing: false };
    const label = document.createElement("label");
    label.className = "merge-choice";
    label.htmlFor = `merge-keep-${id}`;
    const input = document.createElement("input");
    input.type = "radio";
    input.name = "merge-keep";
    input.id = `merge-keep-${id}`;
    input.value = String(id);
    input.checked = id === state.selectedId;
    input.addEventListener("change", () => {
      if (input.checked) refreshMergePreview().catch((error) => setNotice(error.message));
    });
    const text = document.createElement("span");
    const name = document.createElement("span");
    name.textContent = track.file || `Track ${id}`;
    const meta = document.createElement("span");
    meta.className = "merge-meta";
    const parts = [];
    if (track.play_count != null) parts.push(`${track.play_count} plays`);
    const crates = crateNamesFor(id);
    if (crates.length) parts.push(crates.join(", "));
    if (track.missing) parts.push("missing");
    meta.textContent = parts.join(" · ");
    text.append(name, meta);
    label.append(input, text);
    mergeChoices.append(label);
  }
}

/**
 * Open the merge dialog for the selected duplicate group.
 *
 * The Trash option starts off. The plan is loaded before Merge can be
 * pressed. Cancel closes the dialog without a request that writes.
 *
 * @returns {Promise<void>}
 */
async function openMergeDialog() {
  if (!selectedDuplicateGroup() || !state.writable) return;
  if (typeof mergeDialog.showModal !== "function") return;
  mergeTrash.checked = false;
  mergeStatus.textContent = "";
  renderMergeChoices();
  if (!mergeDialog.open) mergeDialog.showModal();
  document.getElementById("merge-cancel").focus();
  await refreshMergePreview();
}

/**
 * Merge the selected group into the chosen copy.
 *
 * POST /api/duplicates/merge with confirm true. Moving files also sends
 * confirm_delete_files. The button stays disabled until the request
 * finishes. A 409 locks the page and closes the dialog.
 *
 * @returns {Promise<void>}
 */
async function confirmMerge() {
  const keepId = selectedMergeKeepId();
  if (keepId == null || mergeLoading) return;
  const trash = mergeTrash.checked;
  mergeLoading = true;
  syncTrashChoice();
  mergeStatus.textContent = "";
  try {
    const result = await postJSON("/api/duplicates/merge", {
      space: state.space,
      keep_id: keepId,
      confirm: true,
      delete_files: trash,
      confirm_delete_files: trash,
    });
    mergeDialog.close();
    const count = (result.removed || []).length;
    const name = result.kept?.file || "the kept copy";
    let message = `Merged ${count} ${count === 1 ? "copy" : "copies"} into ${name}.`;
    if (result.warning) message = `${message} ${result.warning}`;
    if (result.cue_warning) message = `${message} ${result.cue_warning}`;
    setNotice(message);
    state.selectedId = keepId;
    await loadLibrary();
    if (state.mode === "duplicates") await loadDuplicates();
    if (state.byId.has(keepId)) selectTrack(keepId);
  } catch (error) {
    mergeStatus.textContent = error.message;
    if (error.status === 409) {
      lockDown(error);
      mergeDialog.close();
    }
  } finally {
    mergeLoading = false;
    syncTrashChoice();
  }
}

const consentDialog = document.getElementById("consent-dialog");
const settingsDialog = document.getElementById("settings-dialog");
const telemetryToggle = document.getElementById("telemetry-toggle");
const telemetryNote = document.getElementById("telemetry-note");
const consentStatus = document.getElementById("consent-status");
const settingsStatus = document.getElementById("settings-status");
const logFallback = document.getElementById("log-fallback");
let consentSettled = false;
let privacySync = false;

/**
 * Describe the current sharing choice in one sentence.
 *
 * The note sits under the settings checkbox. It does not include the
 * install id or any library data. No request is made.
 *
 * @returns {string} Status sentence for the settings dialog.
 */
function telemetryNoteText() {
  if (!state.telemetryConfigured) {
    return "This copy has no telemetry keys, so nothing is sent either way.";
  }
  if (state.telemetryConsent === true) {
    return "Anonymous counts and crash reports can be sent.";
  }
  return "Nothing is sent.";
}

/**
 * Apply a /api/settings payload to the checkbox and the note.
 *
 * privacySync keeps the checkbox assignment from posting the choice
 * again. A null consent leaves the checkbox off. No request is made.
 *
 * @param {object} payload Settings object from the server.
 * @returns {void}
 */
function applyPrivacy(payload) {
  state.telemetryConsent = payload.telemetry_consent ?? null;
  state.telemetryConfigured = Boolean(payload.telemetry_configured);
  privacySync = true;
  telemetryToggle.checked = state.telemetryConsent === true;
  privacySync = false;
  telemetryNote.textContent = telemetryNoteText();
}

/**
 * POST the sharing choice.
 *
 * False is sent as false. The button or checkbox stays disabled until
 * the response arrives. A failure leaves the previous choice in place
 * and shows what to do next.
 *
 * @param {boolean} value True to share, false to send nothing.
 * @param {HTMLElement} status Element that receives the result sentence.
 * @returns {Promise<boolean>} True when the server stored the choice.
 */
async function saveConsent(value, status) {
  status.textContent = "Saving…";
  try {
    const payload = await postJSON("/api/settings", { telemetry_consent: value });
    applyPrivacy(payload);
    status.textContent = value
      ? "Sharing is on. Anonymous counts and crash reports can be sent."
      : "Sharing is off. Nothing is sent.";
    return true;
  } catch (error) {
    status.textContent = "Couldn't save that choice. Try again.";
    return false;
  }
}

/**
 * Open the first-launch dialog when the person has not chosen yet.
 *
 * Focus moves to Don't share. Escape and a failed save are handled by
 * the dialog listeners. No library fields are included.
 *
 * @returns {void}
 */
function showConsent() {
  if (typeof consentDialog.showModal !== "function") return;
  if (consentDialog.open) return;
  consentSettled = false;
  consentStatus.textContent = "";
  consentDialog.showModal();
  document.getElementById("consent-decline").focus();
}

/**
 * Load sharing settings and show the prompt when no choice is saved.
 *
 * GET /api/settings. A failure leaves sharing off and says so. It does
 * not block the library view.
 *
 * @returns {Promise<void>}
 */
async function loadPrivacy() {
  const response = await fetch("/api/settings");
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || "Couldn't load sharing settings.");
  applyPrivacy(payload);
  if (payload.needs_consent_prompt) showConsent();
}

document.getElementById("consent-decline").addEventListener("click", () => {
  saveConsent(false, consentStatus).then((ok) => {
    if (!ok) return;
    consentSettled = true;
    consentDialog.close();
  });
});

document.getElementById("consent-accept").addEventListener("click", () => {
  saveConsent(true, consentStatus).then((ok) => {
    if (!ok) return;
    consentSettled = true;
    consentDialog.close();
  });
});

consentDialog.addEventListener("close", () => {
  if (consentSettled || state.telemetryConsent !== null) return;
  saveConsent(false, consentStatus).then((ok) => {
    if (ok) {
      consentSettled = true;
      return;
    }
    consentDialog.showModal();
  });
});

document.getElementById("open-settings").addEventListener("click", () => {
  settingsStatus.textContent = "";
  logFallback.hidden = true;
  telemetryNote.textContent = telemetryNoteText();
  settingsDialog.showModal();
});

document.getElementById("settings-close").addEventListener("click", () => {
  settingsDialog.close();
});

telemetryToggle.addEventListener("change", () => {
  if (privacySync) return;
  const want = telemetryToggle.checked;
  telemetryToggle.disabled = true;
  saveConsent(want, settingsStatus).then((ok) => {
    telemetryToggle.disabled = false;
    if (ok) {
      consentSettled = true;
      return;
    }
    privacySync = true;
    telemetryToggle.checked = state.telemetryConsent === true;
    privacySync = false;
  });
});

document.getElementById("open-logs").addEventListener("click", () => {
  const button = document.getElementById("open-logs");
  button.disabled = true;
  settingsStatus.textContent = "Opening…";
  postJSON("/api/logs/open", {})
    .then(() => {
      settingsStatus.textContent = "Opened the logs folder.";
    })
    .catch(() => {
      settingsStatus.textContent = "Couldn't open the logs folder.";
    })
    .finally(() => {
      button.disabled = false;
    });
});

document.getElementById("copy-logs").addEventListener("click", async () => {
  const button = document.getElementById("copy-logs");
  button.disabled = true;
  settingsStatus.textContent = "Copying…";
  try {
    const response = await fetch("/api/logs");
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || "Couldn't copy the logs.");
    const text = payload.text || "";
    if (!text) {
      settingsStatus.textContent = "No log entries yet.";
      return;
    }
    let copied = false;
    if (navigator.clipboard && window.isSecureContext) {
      try {
        await navigator.clipboard.writeText(text);
        copied = true;
      } catch (error) {
        copied = false;
      }
    }
    if (copied) {
      logFallback.hidden = true;
      settingsStatus.textContent = payload.truncated
        ? "Copied the latest log entries. Older entries were left out."
        : "Copied the logs.";
      return;
    }
    logFallback.hidden = false;
    logFallback.value = text;
    logFallback.focus();
    logFallback.select();
    settingsStatus.textContent = "Couldn't copy automatically. Select the log text and copy it.";
  } catch (error) {
    settingsStatus.textContent = "Couldn't copy the logs.";
  } finally {
    button.disabled = false;
  }
});

const filesDialog = document.getElementById("files-dialog");
const filesList = document.getElementById("files-list");
const filesStatus = document.getElementById("files-status");
const filesName = document.getElementById("files-name");
const filesReplacement = document.getElementById("files-replacement");
let filesPreview = null;
let filesAction = "";
let filesTrigger = null;

/**
 * Show a folder error in the Files view.
 *
 * @param {Error} error Failed folder read or save.
 * @returns {void}
 */
function failFiles(error) {
  state.filesLoading = false;
  state.filesError = error.message || "That folder could not be read.";
  renderFiles();
}

/**
 * Load one folder from GET /api/files.
 *
 * An empty path asks for the home directory. Selection is cleared because
 * the previous paths are no longer the rows on screen. A success message
 * can be kept when the reload follows a save.
 *
 * @param {string} path Folder to open.
 * @param {{keepMessage?: boolean}} [options] Pass keepMessage to retain the last save note.
 * @returns {Promise<void>}
 */
async function loadFolder(path, options = {}) {
  state.filesLoading = true;
  state.filesError = "";
  if (!options.keepMessage) state.filesMessage = "";
  state.filesSelected = new Set();
  renderFiles();
  const query = path ? `?path=${encodeURIComponent(path)}` : "";
  const response = await fetch(`/api/files${query}`);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || "That folder could not be read.");
  state.filesPath = payload.path || "";
  state.filesParent = payload.parent || null;
  state.filesEntries = Array.isArray(payload.entries) ? payload.entries : [];
  state.filesTruncated = Boolean(payload.truncated);
  state.filesLoading = false;
  if (payload.serato) applyStatus(payload.serato);
  else renderFiles();
  if (payload.serato) renderFiles();
}

/**
 * Paint the folder, the empty and loading states, and the action buttons.
 *
 * Uses text nodes. Shortcuts are labeled and cannot be selected. Writes
 * stay disabled while Serato holds the library.
 *
 * @returns {void}
 */
function renderFiles() {
  if (state.mode !== "files") return;
  const pick = document.getElementById("files-pick");
  const moveHere = document.getElementById("files-move-here");
  const pickCancel = document.getElementById("files-pick-cancel");
  pick.hidden = !state.filesPick;
  moveHere.hidden = !state.filesPick;
  pickCancel.hidden = !state.filesPick;
  document.getElementById("files-path").textContent = state.filesPath || "Home";
  document.getElementById("files-up").disabled = !state.filesParent || state.filesLoading;
  const notes = [];
  if (state.filesLoading) notes.push("Reading this folder.");
  if (state.filesError) notes.push(state.filesError);
  if (state.filesMessage) notes.push(state.filesMessage);
  if (state.filesTruncated) notes.push("Some files are not listed.");
  filesStatus.textContent = notes.join(" ");
  filesList.setAttribute("aria-busy", String(state.filesLoading));
  filesList.replaceChildren();
  if (state.filesLoading && !state.filesEntries.length) {
    const loading = document.createElement("p");
    loading.className = "files-empty";
    loading.textContent = "Reading this folder.";
    filesList.append(loading);
  } else if (!state.filesEntries.length) {
    const empty = document.createElement("p");
    empty.className = "files-empty";
    empty.textContent = state.filesError || "This folder is empty.";
    filesList.append(empty);
  } else {
    const rank = { dir: 0, file: 1, link: 2 };
    const entries = [...state.filesEntries].sort((left, right) => {
      return (rank[left.kind] ?? 3) - (rank[right.kind] ?? 3) || left.name.localeCompare(right.name);
    });
    for (const entry of entries) filesList.append(fileRow(entry));
  }
  const selected = selectedFiles();
  const locked = !state.writable || state.filesLoading;
  document.getElementById("files-rename").disabled = locked || selected.length !== 1;
  document.getElementById("files-move").disabled = locked || !selected.length || Boolean(state.filesPick);
  document.getElementById("files-move-folder").disabled = locked || !state.filesPath || Boolean(state.filesPick);
  document.getElementById("files-replace").disabled = locked || selected.length !== 1;
  document.getElementById("files-delete").disabled = locked || !selected.length;
  moveHere.disabled = locked;
  renderShell();
}

/**
 * Build one folder row.
 *
 * @param {{name: string, kind: string, path: string, in_library?: boolean}} entry Directory entry.
 * @returns {HTMLDivElement} The row.
 */
function fileRow(entry) {
  const row = document.createElement("div");
  row.className = "files-row";
  if (entry.kind === "dir") {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "files-open";
    button.textContent = entry.name;
    button.setAttribute("aria-label", `Open ${entry.name}`);
    button.addEventListener("click", () => {
      loadFolder(entry.path).catch((error) => failFiles(error));
    });
    row.append(button);
    return row;
  }
  if (entry.kind !== "file") {
    const label = document.createElement("span");
    label.className = "files-kind";
    label.textContent = `${entry.name} (shortcut)`;
    row.append(label);
    return row;
  }
  const label = document.createElement("label");
  label.className = "files-file";
  const box = document.createElement("input");
  box.type = "checkbox";
  box.checked = state.filesSelected.has(entry.path);
  box.addEventListener("change", () => {
    if (box.checked) state.filesSelected.add(entry.path);
    else state.filesSelected.delete(entry.path);
    renderFiles();
  });
  const name = document.createElement("span");
  name.textContent = entry.name;
  label.append(box, name);
  if (entry.in_library) {
    const badge = document.createElement("span");
    badge.className = "files-badge";
    badge.textContent = "In library";
    label.append(badge);
  }
  row.append(label);
  return row;
}

/**
 * Return the selected files that are still in this folder.
 *
 * @returns {object[]} Selected file entries.
 */
function selectedFiles() {
  return state.filesEntries.filter((entry) => entry.kind === "file" && state.filesSelected.has(entry.path));
}

/**
 * Open the review dialog for one file action.
 *
 * Delete and a chosen move load the preview immediately. Rename and
 * replace wait until Review, because those need a typed value. Cancel
 * is focused for a delete.
 *
 * @param {string} action File action.
 * @param {HTMLElement|null} trigger Control that opened the dialog.
 * @returns {void}
 */
function openFilesDialog(action, trigger) {
  filesAction = action;
  filesPreview = null;
  filesTrigger = trigger;
  document.getElementById("files-name-label").hidden = action !== "rename";
  document.getElementById("files-replace-label").hidden = action !== "replace";
  document.getElementById("files-summary").textContent = "";
  document.getElementById("files-warning").textContent = "";
  document.getElementById("files-dialog-status").textContent = "";
  document.getElementById("files-changes").replaceChildren();
  const selected = selectedFiles();
  if (action === "rename" && selected.length === 1) filesName.value = selected[0].name;
  if (action === "replace") filesReplacement.value = "";
  const confirm = document.getElementById("files-confirm");
  confirm.classList.toggle("danger", action === "delete");
  confirm.textContent = action === "delete" ? "Move to Trash" : "Confirm";
  syncFilesDialog();
  filesDialog.showModal();
  if (action === "delete" || action === "move" || action === "move_folder") {
    document.getElementById("files-cancel").focus();
    reviewFiles().catch((error) => {
      document.getElementById("files-dialog-status").textContent = error.message;
    });
  } else if (action === "rename") filesName.focus();
  else filesReplacement.focus();
}

/**
 * Enable confirm only after a preview that can be saved.
 *
 * @returns {void}
 */
function syncFilesDialog() {
  const confirm = document.getElementById("files-confirm");
  const review = document.getElementById("files-review");
  const ready = Boolean(filesPreview?.ok && state.writable && filesPreview.needs_confirm);
  confirm.disabled = !ready;
  review.hidden = filesAction === "delete" || filesAction === "move" || filesAction === "move_folder";
  if (!state.writable) {
    document.getElementById("files-dialog-status").textContent = statusLine.textContent;
  }
}

/**
 * Ask for a preview and paint the paths that would change.
 *
 * The response is 200 even when the save would be refused. ok false
 * keeps Confirm disabled and shows the refusal.
 *
 * @returns {Promise<void>}
 */
async function reviewFiles() {
  const body = filesBody(false);
  document.getElementById("files-dialog-status").textContent = "Checking what will change.";
  const payload = await postJSON("/api/files", body);
  filesPreview = payload;
  document.getElementById("files-summary").textContent = payload.summary || "";
  document.getElementById("files-warning").textContent = payload.warning || "";
  document.getElementById("files-dialog-status").textContent = payload.ok ? "" : (payload.error || "That change was not saved.");
  const list = document.getElementById("files-changes");
  list.replaceChildren();
  for (const change of payload.changes || []) {
    const item = document.createElement("li");
    const crates = Array.isArray(change.crates) && change.crates.length ? ` Crates: ${change.crates.join(", ")}.` : "";
    const effect = change.effect === "trash" ? "Trash" : change.to;
    item.textContent = `${change.from} → ${effect}${crates}`;
    list.append(item);
  }
  if (payload.more) {
    const more = document.createElement("li");
    more.textContent = `And ${payload.more} more.`;
    list.append(more);
  }
  if (payload.serato) applyStatus(payload.serato);
  syncFilesDialog();
}

/**
 * Build the JSON body for the current file action.
 *
 * @param {boolean} confirm True only after the person confirms the preview.
 * @returns {object} Request body for POST /api/files.
 */
function filesBody(confirm) {
  const body = { action: filesAction };
  if (confirm) body.confirm = true;
  if (filesAction === "rename") {
    const selected = selectedFiles();
    body.path = selected[0]?.path || state.filesPickPaths[0];
    body.name = filesName.value;
  } else if (filesAction === "move") {
    body.paths = state.filesPickPaths.length ? [...state.filesPickPaths] : selectedFiles().map((entry) => entry.path);
    body.destination = state.filesPath;
  } else if (filesAction === "move_folder") {
    body.path = state.filesPickSource || state.filesPath;
    body.destination = state.filesPath;
  } else if (filesAction === "replace") {
    const selected = selectedFiles();
    body.path = selected[0]?.path || "";
    body.replacement = filesReplacement.value.trim();
  } else if (filesAction === "delete") {
    body.paths = selectedFiles().map((entry) => entry.path);
  }
  return body;
}

/**
 * Close the file dialog and return focus to the control that opened it.
 *
 * @returns {void}
 */
function closeFilesDialog() {
  const trigger = filesTrigger;
  filesTrigger = null;
  if (filesDialog.open) filesDialog.close();
  if (trigger instanceof HTMLElement) trigger.focus();
}

/**
 * Save a confirmed file change and reload the folder and the library.
 *
 * @returns {Promise<void>}
 */
async function confirmFiles() {
  if (!filesPreview?.ok || !state.writable) return;
  const confirm = document.getElementById("files-confirm");
  confirm.disabled = true;
  document.getElementById("files-dialog-status").textContent = "Saving.";
  try {
    const payload = await postJSON("/api/files", filesBody(true));
    if (payload.serato) applyStatus(payload.serato);
    closeFilesDialog();
    state.filesPick = null;
    state.filesPickPaths = [];
    state.filesPickSource = "";
    state.filesMessage = payload.summary || "The files were updated.";
    if (payload.warning) state.filesMessage = `${state.filesMessage} ${payload.warning}`;
    await loadFolder(payload.browse || state.filesPath || "", { keepMessage: true });
    await loadLibrary();
    state.filesMessage = state.filesMessage;
    renderFiles();
  } catch (error) {
    if (error.status === 409) lockDown(error);
    document.getElementById("files-dialog-status").textContent = error.message;
    confirm.disabled = false;
  }
}

document.getElementById("files-up").addEventListener("click", () => {
  if (state.filesParent) loadFolder(state.filesParent).catch((error) => failFiles(error));
});

document.getElementById("files-refresh").addEventListener("click", () => {
  loadFolder(state.filesPath || "").catch((error) => failFiles(error));
});

document.getElementById("files-rename").addEventListener("click", (event) => {
  if (selectedFiles().length !== 1) {
    state.filesError = "Choose one file to rename.";
    renderFiles();
    return;
  }
  openFilesDialog("rename", event.currentTarget);
});

document.getElementById("files-move").addEventListener("click", () => {
  const selected = selectedFiles();
  if (!selected.length) {
    state.filesError = "Choose files to move.";
    renderFiles();
    return;
  }
  state.filesPick = "move";
  state.filesPickPaths = selected.map((entry) => entry.path);
  state.filesError = "";
  state.filesMessage = "Choose the destination folder. Then confirm the move.";
  renderFiles();
});

document.getElementById("files-move-folder").addEventListener("click", () => {
  state.filesPick = "move_folder";
  state.filesPickSource = state.filesPath;
  state.filesError = "";
  state.filesMessage = "Choose the destination folder. Then confirm the move.";
  renderFiles();
});

document.getElementById("files-move-here").addEventListener("click", (event) => {
  openFilesDialog(state.filesPick === "move_folder" ? "move_folder" : "move", event.currentTarget);
});

document.getElementById("files-pick-cancel").addEventListener("click", () => {
  state.filesPick = null;
  state.filesPickPaths = [];
  state.filesPickSource = "";
  state.filesMessage = "";
  renderFiles();
});

document.getElementById("files-replace").addEventListener("click", (event) => {
  if (selectedFiles().length !== 1) {
    state.filesError = "Choose one file to replace.";
    renderFiles();
    return;
  }
  openFilesDialog("replace", event.currentTarget);
});

document.getElementById("files-delete").addEventListener("click", (event) => {
  if (!selectedFiles().length) {
    state.filesError = "Choose files to delete.";
    renderFiles();
    return;
  }
  openFilesDialog("delete", event.currentTarget);
});

document.getElementById("files-review").addEventListener("click", () => {
  reviewFiles().catch((error) => {
    document.getElementById("files-dialog-status").textContent = error.message;
  });
});

document.getElementById("files-confirm").addEventListener("click", () => {
  confirmFiles().catch((error) => {
    document.getElementById("files-dialog-status").textContent = error.message;
  });
});

document.getElementById("files-cancel").addEventListener("click", () => closeFilesDialog());

filesName.addEventListener("input", () => {
  filesPreview = null;
  syncFilesDialog();
});

filesReplacement.addEventListener("input", () => {
  filesPreview = null;
  syncFilesDialog();
});

filesDialog.addEventListener("cancel", (event) => {
  event.preventDefault();
  closeFilesDialog();
});

loadLibrary().catch(showFailure);
loadPrivacy().catch((error) => setNotice(error.message || "Couldn't load sharing settings. Nothing is sent."));
