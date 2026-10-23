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
  duplicateSpace: "",
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

function lengthLabel(ms) {
  if (ms == null || ms === "") return "";
  const total = Math.floor(Number(ms) / 1000);
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function clockLabel(stamp) {
  if (stamp == null || stamp === "") return "";
  const date = new Date(Number(stamp) * 1000);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function durationLabel(ms) {
  const total = Math.round(Number(ms) / 1000);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (hours) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

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

function colorHex(color) {
  if (color == null || Number(color) === 0xffffff) return "";
  return `#${Number(color).toString(16).padStart(6, "0")}`;
}

function compare(a, b) {
  const key = state.sort;
  const dir = state.sortDir;
  let av = a[key];
  let bv = b[key];
  if (key === "bpm" || key === "length_ms" || key === "start") {
    const an = av == null || av === "" ? null : Number(av);
    const bn = bv == null || bv === "" ? null : Number(bv);
    if (an == null && bn == null) return a.id - b.id;
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

function matchesQuery(track, terms) {
  if (!terms.length) return true;
  const hay = `${track.name} ${track.artist} ${track.album} ${track.genre} ${track.key} ${track.file}`.toLocaleLowerCase();
  return terms.every((term) => hay.includes(term));
}

function queryTerms() {
  return state.query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
}

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

function crateKeep() {
  const terms = state.crateQuery.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  if (!terms.length) return null;
  const byId = new Map(state.crates.map((crate) => [crate.id, crate]));
  const keep = new Set();
  for (const crate of state.crates) {
    if (!terms.every((term) => crate.name.toLocaleLowerCase().includes(term))) continue;
    let current = crate;
    const guard = new Set();
    while (current && !guard.has(current.id)) {
      guard.add(current.id);
      keep.add(current.id);
      current = byId.get(current.parent);
    }
  }
  return keep;
}

function visibleCrates() {
  const children = childLists();
  const keep = crateKeep();
  const ordered = [];
  const seen = new Set();
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

function placeCrateFocus(previousId) {
  const items = [...crateList.querySelectorAll(".crate")];
  if (!items.length) return null;
  const current = items.find((item) => item.dataset.id === previousId) || items[0];
  for (const item of items) item.tabIndex = item === current ? 0 : -1;
  return current;
}

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

function renderShell() {
  const cratesMode = state.mode === "crates";
  const historyMode = state.mode === "history";
  document.getElementById("crate-tools").hidden = !cratesMode;
  document.getElementById("crate-actions").hidden = !cratesMode;
  crateList.hidden = !cratesMode;
  sessionList.hidden = !historyMode;
  modeNote.hidden = cratesMode || historyMode;
  if (state.mode === "missing") modeNote.textContent = "Tracks Serato has marked missing in this space.";
  if (state.mode === "duplicates") modeNote.textContent = "Same title, artist, and length. Open a track to see the other copies.";
  if (state.mode === "stems") modeNote.textContent = "Tracks with a stems analysis state.";
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
  const pool = state.mode === "history" ? state.entries : footerTracks();
  const bytes = pool.reduce((sum, track) => sum + (Number(track.file_size) || 0), 0);
  const ms = pool.reduce((sum, track) => sum + (Number(track.length_ms) || 0), 0);
  crateFoot.textContent = `${pool.length.toLocaleString()} · ${durationLabel(ms)} · ${sizeLabel(bytes)}`;
}

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

function renderList() {
  renderShell();
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

function paintRows() {
  const view = state.view || [];
  const height = list.clientHeight || 600;
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

function selectCrate(id) {
  state.activeCrate = id;
  if (id !== "all") expandAncestors(id);
  list.scrollTop = 0;
  renderList();
}

function focusCrateItem(item) {
  if (!item) return;
  for (const button of crateList.querySelectorAll(".crate")) button.tabIndex = -1;
  item.tabIndex = 0;
  item.focus();
}

async function selectTrack(id) {
  state.selectedId = id;
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
  reveal.textContent = "Reveal in Finder";
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
  body.append(actions);

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
  const ms = (value) => {
    const total = Number(value) / 1000;
    const minutes = Math.floor(total / 60);
    return `${minutes}:${(total - minutes * 60).toFixed(3).padStart(6, "0")}`;
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
    time.textContent = `${mark.position}s`;
    const name = document.createElement("span");
    name.textContent = mark.bpm != null ? `${mark.bpm} BPM` : `${mark.beats} beats`;
    row.append(document.createElement("span"), time, name);
    section.append(row);
  }
  return section;
}

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

function setNotice(text) {
  notice.textContent = text || "";
  notice.hidden = !text;
}

function applyStatus(info) {
  state.serato = info;
  state.writable = Boolean(info?.writable);
  statusLine.textContent = info?.message || "Library";
  renderShell();
}

function lockDown(error) {
  applyStatus(error.payload?.serato || { writable: false, message: error.message });
  setNotice(error.message);
}

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

async function revealTrack(id) {
  try {
    await postJSON("/api/reveal", { id });
  } catch (error) {
    setNotice(error.message);
  }
}

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

async function loadHistory() {
  const response = await fetch("/api/history");
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || "Could not read history.");
  state.historySessions = payload.sessions || [];
  renderSessions();
}

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

async function loadDuplicates() {
  state.duplicateIds = null;
  const response = await fetch(`/api/duplicates?space=${encodeURIComponent(state.space)}`);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || "Could not read duplicates.");
  const ids = new Set();
  for (const group of payload.groups || []) for (const id of group.ids) ids.add(id);
  state.duplicateIds = ids;
  state.duplicateSpace = state.space;
  if (state.mode === "duplicates") renderList();
}

async function openInLibrary(assetId) {
  state.space = "Serato Library";
  spaceSelect.value = state.space;
  state.mode = "crates";
  state.activeCrate = "all";
  state.selectedId = assetId;
  await loadLibrary();
  selectTrack(assetId);
}

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
  if (state.duplicateSpace !== state.space) state.duplicateIds = null;
  applyStatus(library.serato);
  renderList();
}

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
  renderList();
}

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

document.querySelector(".columns").addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (!button?.dataset.sort) return;
  const key = button.dataset.sort;
  if (state.sort === key) state.sortDir *= -1;
  else {
    state.sort = key;
    state.sortDir = key === "bpm" || key === "length_ms" || key === "start" ? -1 : 1;
  }
  renderColumns();
  renderList();
});

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

function showFailure(error) {
  count.textContent = "Library unavailable";
  const failure = document.createElement("p");
  failure.className = "detail-error";
  failure.textContent = error.message;
  detail.replaceChildren(failure);
}

loadLibrary().catch(showFailure);
