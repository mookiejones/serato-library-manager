"use strict";
(() => {
  // src/api.ts
  async function readJSON(response) {
    return await response.json();
  }
  async function readJSONOr(response, fallback) {
    return await response.json().catch(() => fallback);
  }
  function failureOf(error) {
    if (error instanceof Error) return error;
    return new Error(typeof error === "string" ? error : "Request failed");
  }
  async function postJSON(url, body) {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
    const payload = await readJSONOr(response, {});
    if (!response.ok) {
      const error = new Error(payload.error || `Request failed (${response.status})`);
      error.status = response.status;
      error.payload = payload;
      throw error;
    }
    return payload;
  }

  // src/bridge.ts
  var bridge = {
    selectTrack(_id) {
    },
    selectEntry(_id) {
    },
    openMergeDialog() {
      return Promise.resolve();
    }
  };

  // src/dom.ts
  function el(id) {
    const node = document.getElementById(id);
    if (node == null) throw new Error(`Missing #${id}`);
    return node;
  }

  // src/state.ts
  var ROW = 36;
  var COLORS = [
    [16777215, "None"],
    [13369344, "Red"],
    [16746496, "Orange"],
    [16763904, "Yellow"],
    [3385941, "Green"],
    [2250188, "Blue"],
    [8926156, "Purple"],
    [14826378, "Pink"]
  ];
  var COLOR_NAMES = {
    none: 16777215,
    red: 13369344,
    orange: 16746496,
    yellow: 16763904,
    green: 3385941,
    blue: 2250188,
    purple: 8926156,
    pink: 14826378
  };
  var state = {
    tracks: [],
    byId: /* @__PURE__ */ new Map(),
    crates: [],
    crateTracks: /* @__PURE__ */ new Map(),
    rootId: null,
    activeCrate: "all",
    query: "",
    crateQuery: "",
    crateSort: "order",
    sort: "name",
    sortDir: 1,
    selectedId: null,
    request: 0,
    expanded: /* @__PURE__ */ new Set(),
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
    filesSelected: /* @__PURE__ */ new Set(),
    filesPick: null,
    filesPickPaths: [],
    filesPickSource: "",
    filesLoading: false,
    filesError: "",
    filesMessage: "",
    filesTruncated: false,
    snapshots: [],
    snapshotLoading: false,
    snapshotError: "",
    snapshotMessage: "",
    snapshotUndo: null,
    writeBlock: "",
    seratoRunning: false,
    snapshotPlanId: "",
    view: []
  };

  // src/format.ts
  function lengthLabel(ms) {
    if (ms == null || ms === "") return "";
    const total = Math.floor(Number(ms) / 1e3);
    const minutes = Math.floor(total / 60);
    const seconds = total % 60;
    return `${minutes}:${String(seconds).padStart(2, "0")}`;
  }
  function clockLabel(stamp) {
    if (stamp == null || stamp === "") return "";
    const date = new Date(Number(stamp) * 1e3);
    if (Number.isNaN(date.getTime())) return "";
    return date.toLocaleString(void 0, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  }
  function durationLabel(ms) {
    const total = Math.round(Number(ms) / 1e3);
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor(total % 3600 / 60);
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
    if (color == null || Number(color) === 16777215) return "";
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
    const order = av.localeCompare(bv, void 0, { numeric: true, sensitivity: "base" });
    if (order !== 0) return order * dir;
    return a.id - b.id;
  }

  // src/restore.ts
  var reloadLibrary = async () => {
  };
  function bindLibraryReload(reload) {
    reloadLibrary = reload;
  }
  async function loadSnapshots() {
    state.snapshotLoading = true;
    state.snapshotError = "";
    renderSnapshots();
    const response = await fetch("/api/snapshots");
    const payload = await readJSON(response);
    if (!response.ok) throw new Error(payload.error || "The snapshots could not be read.");
    state.snapshots = payload.snapshots || [];
    state.snapshotUndo = payload.pending_undo || null;
    state.writeBlock = payload.write_block || "";
    state.seratoRunning = Boolean(payload.serato_running);
    state.snapshotLoading = false;
    renderSnapshots();
  }
  function failSnapshots(error) {
    state.snapshotLoading = false;
    state.snapshotError = failureOf(error).message || "The snapshots could not be read.";
    renderSnapshots();
  }
  function renderSnapshots() {
    const status = el("snapshots-status");
    const block = el("snapshots-block");
    const undo = el("snapshots-undo");
    const list = el("snapshots-list");
    list.setAttribute("aria-busy", String(state.snapshotLoading));
    if (state.writeBlock) {
      block.hidden = false;
      block.textContent = state.writeBlock;
    } else {
      block.hidden = true;
      block.textContent = "";
    }
    if (state.snapshotUndo && state.snapshotUndo.restore_id) {
      undo.hidden = false;
      const source = state.snapshotUndo.source === "Lexicon" ? "Lexicon" : "Something outside this app";
      el("snapshots-undo-text").textContent = `${source} changed the Serato folder. A snapshot was saved after that change. Undo puts back the previous snapshot.`;
    } else {
      undo.hidden = true;
    }
    list.replaceChildren();
    if (state.snapshotLoading) {
      status.textContent = "Reading snapshots";
      return;
    }
    if (state.snapshotError) {
      status.textContent = state.snapshotError;
      const retry = document.createElement("button");
      retry.type = "button";
      retry.textContent = "Try again";
      retry.addEventListener("click", () => loadSnapshots().catch((error) => failSnapshots(error)));
      list.append(retry);
      return;
    }
    status.textContent = state.snapshotMessage;
    if (!state.snapshots.length) {
      const empty = document.createElement("p");
      empty.textContent = "No snapshots yet. Take a snapshot to keep a point you can restore. Snapshots are kept, and this page does not expire them.";
      list.append(empty);
      return;
    }
    for (const item of state.snapshots) {
      const card = document.createElement("article");
      card.className = "snapshot-card";
      card.setAttribute("role", "listitem");
      const title = document.createElement("p");
      title.textContent = `${item.created || "Unknown time"} · ${item.trigger || "snapshot"}`;
      const detail = document.createElement("p");
      const version = item.serato_version && item.serato_version !== "unknown" ? `Serato ${item.serato_version} (build ${item.serato_build})` : "Serato version unknown";
      const drives = (item.unavailable_drives || []).length ? ` Unavailable: ${(item.unavailable_drives || []).join(", ")}.` : "";
      detail.textContent = `${version}. ${item.reason || ""}${drives}`;
      const restore = document.createElement("button");
      restore.type = "button";
      restore.textContent = "Review restore";
      restore.addEventListener("click", () => openSnapshotPlan(item.id).catch((error) => setSnapshotDialogStatus(failureOf(error).message)));
      card.append(title, detail, restore);
      list.append(card);
    }
  }
  async function openSnapshotPlan(snapshotId) {
    state.snapshotPlanId = snapshotId;
    const planBox = el("snapshot-plan");
    const block = el("snapshot-block");
    const confirm2 = el("snapshot-confirm");
    planBox.replaceChildren();
    block.textContent = "Reading what would change";
    confirm2.disabled = true;
    setSnapshotDialogStatus("");
    el("snapshot-dialog").showModal();
    const plan = await postJSON("/api/snapshots", { action: "plan", id: snapshotId });
    paintSnapshotPlan(plan);
  }
  function paintSnapshotPlan(plan) {
    const planBox = el("snapshot-plan");
    const block = el("snapshot-block");
    const confirm2 = el("snapshot-confirm");
    planBox.replaceChildren();
    const crates = plan.crates || {};
    const tracks = plan.tracks || {};
    appendPlanLine(planBox, "Crates added", crates.added);
    appendPlanLine(planBox, "Crates removed", crates.removed);
    appendPlanLine(planBox, "Crates changed", crates.changed);
    appendPlanLine(planBox, "Crates on an unavailable drive", crates.unavailable);
    appendPlanLine(planBox, "Tracks added", tracks.added);
    appendPlanLine(planBox, "Tracks removed", tracks.removed);
    appendPlanLine(planBox, "Tracks on an unavailable drive", tracks.unavailable);
    appendFrameDiffs(planBox, "Cue changes", plan.cues);
    appendFrameDiffs(planBox, "Grid changes", plan.grids);
    const deleted = plan.deleted || {};
    appendPlanLine(planBox, "Deleted crates", deleted.crates);
    appendPlanLine(planBox, "Deleted tracks", deleted.tracks);
    appendPlanLine(planBox, "Deleted cues", deleted.cues);
    appendPlanLine(planBox, "Deleted grids", deleted.grids);
    if (plan.restore_blocked) {
      block.textContent = plan.restore_blocked;
      confirm2.disabled = true;
    } else {
      block.textContent = plan.dry_run ? "Nothing has been changed." : "";
      confirm2.disabled = false;
    }
  }
  function appendPlanLine(parent, label, rows2) {
    const line = document.createElement("p");
    const items = rows2 || [];
    if (!items.length) {
      line.textContent = `${label}: none`;
    } else {
      const names = items.slice(0, 8).map((item) => item.name || item.path || item.drive_label || "item");
      const extra = items.length > names.length ? `, and ${items.length - names.length} more` : "";
      line.textContent = `${label}: ${items.length}. ${names.join(", ")}${extra}`;
    }
    parent.append(line);
  }
  function appendFrameDiffs(parent, label, rows2) {
    const items = rows2 || [];
    const line = document.createElement("p");
    if (!items.length) {
      line.textContent = `${label}: none`;
      parent.append(line);
      return;
    }
    line.textContent = `${label}: ${items.length} file${items.length === 1 ? "" : "s"}`;
    parent.append(line);
    for (const item of items.slice(0, 12)) {
      const row = document.createElement("p");
      row.textContent = fileName(item.path || "");
      parent.append(row);
    }
  }
  function fileName(path) {
    const parts = String(path).split(/[/\\]/);
    return parts[parts.length - 1] || path;
  }
  function setSnapshotDialogStatus(message) {
    el("snapshot-status").textContent = message;
  }
  async function takeSnapshot() {
    const button = el("snapshots-take");
    button.disabled = true;
    button.textContent = "Saving snapshot…";
    try {
      await postJSON("/api/snapshots", { action: "create" });
      state.snapshotMessage = "Snapshot saved.";
      await loadSnapshots();
    } finally {
      button.disabled = false;
      button.textContent = "Take a snapshot";
    }
  }
  async function confirmSnapshotRestore() {
    const confirm2 = el("snapshot-confirm");
    confirm2.disabled = true;
    confirm2.textContent = "Restoring…";
    setSnapshotDialogStatus("");
    try {
      const undoing = state.snapshotUndo && state.snapshotUndo.restore_id === state.snapshotPlanId;
      const body = undoing ? { action: "undo", confirm: true } : { action: "restore", id: state.snapshotPlanId, confirm: true };
      await postJSON("/api/snapshots", body);
      el("snapshot-dialog").close();
      state.snapshotMessage = "Restore finished. The previous library was saved first, so this can be undone from the list.";
      await loadSnapshots();
      await reloadLibrary();
    } catch (error) {
      setSnapshotDialogStatus(failureOf(error).message);
      confirm2.disabled = false;
    } finally {
      confirm2.textContent = "Restore";
    }
  }

  // src/virtual-scroll.ts
  var spacer = document.createElement("div");
  var rows = document.createElement("div");
  spacer.className = "spacer";
  rows.className = "rows";
  spacer.append(rows);
  function mountTrackList() {
    el("list").append(spacer);
  }
  function paintRows() {
    const view = state.view || [];
    const height = el("list").clientHeight || 600;
    const start = Math.max(0, Math.floor(el("list").scrollTop / ROW) - 6);
    const end = Math.min(view.length, Math.ceil((el("list").scrollTop + height) / ROW) + 6);
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
      artist.textContent = track.artist ?? "";
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
        fourth.textContent = track.key ?? "";
        fifth.textContent = lengthLabel(track.length_ms);
      }
      button.append(titleCell, artist, third, fourth, fifth);
      button.addEventListener("click", () => track.entry ? bridge.selectEntry(track.id) : bridge.selectTrack(track.id));
      rows.append(button);
    }
  }
  function moveSelection(delta) {
    const view = state.view || [];
    const index = view.findIndex((track) => track.id === state.selectedId);
    const next = view[Math.max(0, Math.min(view.length - 1, index + delta))];
    if (!next) return;
    if (next.entry) bridge.selectEntry(next.id);
    else bridge.selectTrack(next.id);
    const rowTop = view.indexOf(next) * ROW;
    if (rowTop < el("list").scrollTop) el("list").scrollTop = rowTop;
    if (rowTop + ROW > el("list").scrollTop + el("list").clientHeight) {
      el("list").scrollTop = rowTop + ROW - el("list").clientHeight;
    }
  }
  function wireVirtualScroll() {
    el("list").addEventListener("scroll", () => paintRows());
    el("list").addEventListener("keydown", (event) => {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        moveSelection(1);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        moveSelection(-1);
      }
    });
  }

  // src/views.ts
  var relatedRequest = 0;
  function matchesQuery(track, terms) {
    if (!terms.length) return true;
    const hay = `${track.name} ${track.artist} ${track.album} ${track.genre} ${track.key} ${track.file}`.toLocaleLowerCase();
    return terms.every((term) => hay.includes(term));
  }
  function queryTerms() {
    return state.query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  }
  function childLists() {
    const children = /* @__PURE__ */ new Map();
    for (const crate of state.crates) {
      const key = crate.parent ?? 0;
      if (!children.has(key)) children.set(key, []);
      const bucket = children.get(key);
      bucket.push(crate);
    }
    for (const list of children.values()) {
      list.sort((a, b) => {
        if (state.crateSort === "name") {
          return a.name.localeCompare(b.name, void 0, { sensitivity: "base" }) || a.id - b.id;
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
    const keep = /* @__PURE__ */ new Set();
    for (const crate of state.crates) {
      if (!terms.every((term) => crate.name.toLocaleLowerCase().includes(term))) continue;
      let current = crate;
      const guard = /* @__PURE__ */ new Set();
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
    const seen = /* @__PURE__ */ new Set();
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
  function expandAncestors(id) {
    const byId = new Map(state.crates.map((crate2) => [crate2.id, crate2]));
    let crate = id === "all" ? void 0 : byId.get(id);
    const guard = /* @__PURE__ */ new Set();
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
    if (visible.some((crate2) => crate2.id === state.activeCrate)) return null;
    const byId = new Map(state.crates.map((crate2) => [crate2.id, crate2]));
    const visibleIds = new Set(visible.map((crate2) => crate2.id));
    let crate = byId.get(state.activeCrate);
    const guard = /* @__PURE__ */ new Set();
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
      const terms2 = queryTerms();
      const result2 = state.entries.filter((entry) => matchesQuery(entry, terms2)).map((entry) => ({
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
        notes: entry.notes
      }));
      result2.sort(compare);
      state.view = result2;
      return result2;
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
    const items = [...el("crate-list").querySelectorAll(".crate")];
    if (!items.length) return null;
    const current = items.find((item) => item.dataset.id === previousId) || items[0];
    for (const item of items) item.tabIndex = item === current ? 0 : -1;
    return current;
  }
  function renderCrates() {
    const scroll = el("crate-list").scrollTop;
    const active = document.activeElement;
    const restore = el("crate-list").contains(active) ? active.closest(".crate-row")?.querySelector(".crate")?.dataset.id ?? null : null;
    const terms = queryTerms();
    const matched = terms.length ? new Set(state.tracks.filter((track) => matchesQuery(track, terms)).map((track) => track.id)) : null;
    const crates = visibleCrates();
    const holder = hiddenSelectionHolder(crates);
    el("crate-list").replaceChildren();
    el("crate-list").append(crateRow({
      id: "all",
      name: "All tracks",
      depth: 0,
      childCount: 0,
      smart: false,
      count: matched ? matched.size : state.tracks.length
    }));
    for (const crate of crates) {
      const members = state.crateTracks.get(crate.id) || /* @__PURE__ */ new Set();
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
        holds: holder === crate.id
      }));
    }
    const focused = placeCrateFocus(restore);
    if (restore && focused) focused.focus({ preventScroll: true });
    el("crate-list").scrollTop = scroll;
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
    const columns = state.mode === "history" ? [["name", "Title"], ["artist", "Artist"], ["deck", "Deck"], ["played", "Played"], ["start", "Time"]] : [["name", "Title"], ["artist", "Artist"], ["bpm", "BPM"], ["key", "Key"], ["length_ms", "Time"]];
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
    el("crate-tools").hidden = !cratesMode;
    el("crate-actions").hidden = !cratesMode;
    el("crate-list").hidden = !cratesMode;
    el("session-list").hidden = !historyMode;
    el("mode-note").hidden = cratesMode || historyMode;
    const filesMode = state.mode === "files";
    const snapshotsMode = state.mode === "snapshots";
    document.querySelector(".browser").hidden = filesMode || snapshotsMode;
    el("detail").hidden = filesMode || snapshotsMode;
    el("files-panel").hidden = !filesMode;
    el("snapshots-panel").hidden = !snapshotsMode;
    if (state.mode === "missing") el("mode-note").textContent = "Tracks Serato has marked missing in this space.";
    if (state.mode === "duplicates") {
      el("mode-note").textContent = "Same title, artist, and length. Select a copy, then merge the others into it.";
    }
    if (state.mode === "stems") el("mode-note").textContent = "Tracks with a stems analysis state.";
    if (filesMode) el("mode-note").textContent = "Files on disk. Cue points stay in the audio file. Crates follow the path.";
    if (snapshotsMode) {
      el("mode-note").textContent = "Hash-checked copies of the library, crates, and Serato frames inside audio files. Audio itself is not copied.";
    }
    for (const button of document.querySelectorAll("#views button")) {
      button.setAttribute("aria-selected", String(button.dataset.view === state.mode));
    }
    for (const button of document.querySelectorAll("[data-crate-sort]")) {
      button.setAttribute("aria-pressed", String(button.dataset.crateSort === state.crateSort));
    }
    const crateChosen = state.activeCrate !== "all";
    el("crate-new").disabled = !state.writable;
    el("crate-rename").disabled = !state.writable || !crateChosen;
    el("crate-color").disabled = !state.writable || !crateChosen;
    el("crate-delete").disabled = !state.writable || !crateChosen;
    syncMergeButton();
    if (filesMode) {
      const listed = state.filesEntries.filter((entry) => entry.kind === "file").length;
      el("crate-foot").textContent = state.filesLoading ? "Reading this folder" : `${listed.toLocaleString()} files`;
      return;
    }
    if (snapshotsMode) {
      el("crate-foot").textContent = state.snapshotLoading ? "Reading snapshots" : `${state.snapshots.length.toLocaleString()} snapshots`;
      return;
    }
    const pool = state.mode === "history" ? state.entries : footerTracks();
    const bytes = pool.reduce((sum, track) => sum + (Number(track.file_size) || 0), 0);
    const ms = pool.reduce((sum, track) => sum + (Number(track.length_ms) || 0), 0);
    el("crate-foot").textContent = `${pool.length.toLocaleString()} · ${durationLabel(ms)} · ${sizeLabel(bytes)}`;
  }
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
  function renderList() {
    renderShell();
    if (state.mode === "files") {
      renderFiles();
      return;
    }
    renderColumns();
    const view = buildView();
    const noun = state.mode === "history" ? "play" : "track";
    el("count").textContent = `${view.length.toLocaleString()} ${noun}${view.length === 1 ? "" : "s"}`;
    if (state.mode === "crates") renderCrates();
    else document.querySelector(".rules")?.remove();
    paintRows();
    if (!view.some((track) => track.id === state.selectedId)) {
      if (!view.length) {
        state.selectedId = null;
        const empty = document.createElement("p");
        empty.className = "detail-empty";
        empty.textContent = state.mode === "history" && !state.historyId ? "Choose a session." : "No tracks match.";
        el("detail").replaceChildren(empty);
      } else if (state.mode === "history") selectEntry(view[0].id);
      else selectTrack(view[0].id);
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
      space: state.space
    }).then((result) => {
      if (result.warning) setNotice(result.warning);
    }).catch((error) => {
      if (failureOf(error).status === 409) lockDown(error);
      else setNotice(failureOf(error).message);
    });
  }
  function selectCrate(id) {
    state.activeCrate = id;
    if (id !== "all") expandAncestors(id);
    el("list").scrollTop = 0;
    renderList();
  }
  function focusCrateItem(item) {
    if (!item) return;
    for (const button of el("crate-list").querySelectorAll(".crate")) button.tabIndex = -1;
    item.tabIndex = 0;
    item.focus();
  }
  async function selectTrack(id) {
    state.selectedId = id;
    syncMergeButton();
    paintRows();
    const token = ++state.request;
    const pending = document.createElement("p");
    pending.className = "detail-empty";
    pending.textContent = "Reading attributes";
    el("detail").replaceChildren(pending);
    try {
      const response = await fetch(`/api/track?id=${id}&space=${encodeURIComponent(state.space)}`);
      const payload = await readJSONOr(response, {});
      if (!response.ok) throw new Error(payload.error || `Could not read track (${response.status})`);
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
      ["File", entry.file || "—"]
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
    el("detail").replaceChildren(body);
  }
  function fieldInput(name, label, value, wide = false) {
    const wrap = document.createElement("label");
    if (wide) wrap.className = "wide";
    wrap.append(document.createTextNode(label));
    const input = name === "comments" ? document.createElement("textarea") : document.createElement("input");
    input.name = name;
    input.value = String(value ?? "");
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
    title.textContent = track.title ?? "";
    body.append(title);
    if (track.artist) {
      const artist = document.createElement("p");
      artist.className = "artist";
      artist.textContent = track.artist ?? "";
      body.append(artist);
    }
    const deck = document.createElement("div");
    deck.className = "deck";
    const facts = [["BPM", track.bpm], ["Key", track.key || "—"], ["Time", track.length]];
    for (const [label, value] of facts) {
      const cell = document.createElement("div");
      const strong = document.createElement("strong");
      strong.textContent = String(value || "—");
      if (label === "BPM") strong.className = "bpm";
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
      span.textContent = "Color";
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
    const editorFields = [
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
      ["comments", "Comments", true]
    ];
    for (const [name, label, wide] of editorFields) {
      form.append(fieldInput(name, label, String(edit[name] ?? ""), wide));
    }
    const colorLabel = document.createElement("label");
    colorLabel.append(document.createTextNode("Color"));
    const colorSelect = document.createElement("select");
    colorSelect.name = "color";
    const currentColor = Number(edit.color ?? 16777215);
    const palette = COLORS.some(([value]) => value === currentColor) ? COLORS : [...COLORS, [currentColor, colorHex(currentColor) || "Custom"]];
    for (const [value, label] of palette) {
      const option = document.createElement("option");
      option.value = String(value);
      option.textContent = String(label ?? "");
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
      option.textContent = label ?? "";
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
      const total = Number(value) / 1e3;
      const minutes = Math.floor(total / 60);
      return `${minutes}:${(total - minutes * 60).toFixed(3).padStart(6, "0")}`;
    };
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
      rate.textContent = copy.bitrate == null ? "" : String(copy.bitrate);
      const plays = document.createElement("span");
      plays.textContent = copy.play_count == null ? "" : String(copy.play_count);
      const crates = document.createElement("span");
      crates.textContent = copy.missing ? "missing" : copy.crates || "";
      row.append(button, rate, plays, crates);
      section.append(row);
    }
    return section;
  }
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
  async function loadRelated(track, section, writable, query) {
    const token = ++relatedRequest;
    const path = track.resolved_path || track.edit?.portable_id || "";
    const params = new URLSearchParams({ path, space: state.space });
    try {
      const response = await fetch(`/api/related?${params}`);
      const payload = await readJSONOr(response, {});
      if (token !== relatedRequest || !section.isConnected) return;
      if (!response.ok) throw new Error(payload.error || "Related tracks could not be loaded.");
      renderRelated(track, section, writable, payload, query);
    } catch (error) {
      if (token !== relatedRequest || !section.isConnected) return;
      section.setAttribute("aria-busy", "false");
      const status = section.querySelector("[role=status]");
      if (status) status.textContent = failureOf(error).message;
    }
  }
  function renderRelated(track, section, writable, payload, query) {
    const heading = section.querySelector("h3");
    section.replaceChildren(heading);
    section.setAttribute("aria-busy", "false");
    const saved = Array.isArray(payload.saved) ? payload.saved : [];
    const suggested = Array.isArray(payload.suggested) ? payload.suggested : [];
    const status = document.createElement("p");
    status.className = "detail-kicker";
    status.setAttribute("role", "status");
    status.textContent = saved.length ? `${saved.length} saved` : "No saved links yet. Search for a track, or save a suggestion.";
    section.append(status);
    if (saved.length) section.append(relatedSavedList(track, section, saved));
    section.append(relatedSearch(track, section, query));
    const suggestHeading = document.createElement("p");
    suggestHeading.className = "detail-kicker";
    suggestHeading.textContent = suggested.length ? "Suggested from key, tempo within 6%, and shared crates. Save stores a two-way link." : "No suggestions from key, tempo, or shared crates.";
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
    crateNote.textContent = writable ? `Creates or refreshes the crate “${crateName}”. Serato must be quit.` : "Quit Serato before writing the crate.";
    section.append(crate, crateNote);
  }
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
      const hits = state.tracks.filter((item) => item.id !== track.id && matchesQuery(item, terms)).slice(0, 8);
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
        choose.textContent = hit.artist ? `${hit.name || "Untitled"} · ${hit.artist}` : hit.name || "Untitled";
        choose.addEventListener("click", () => relatedLinkForm(track, section, form, hit, input.value));
        item.append(choose);
        results.append(item);
      }
    };
    input.addEventListener("input", paint);
    paint();
    return block;
  }
  function relatedLinkForm(track, section, form, hit, query) {
    form.hidden = false;
    form.replaceChildren();
    const chosen = document.createElement("p");
    chosen.className = "related-meta";
    chosen.textContent = hit.artist ? `${hit.name || "Untitled"} · ${hit.artist}` : hit.name || "Untitled";
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
        space: state.space
      }, query);
    });
    form.append(chosen, noteLabel, ratingLabel, mutualLabel, save);
  }
  function relatedSuggestList(track, section, suggested) {
    const list = document.createElement("ul");
    list.className = "related-list";
    for (const item of suggested) {
      const row = document.createElement("li");
      row.className = "related-row";
      const main = document.createElement("div");
      const name = document.createElement("span");
      name.textContent = item.artist ? `${item.title || "Untitled"} · ${item.artist}` : item.title || "Untitled";
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
          space: state.space
        }, "");
      });
      row.append(main, save);
      list.append(row);
    }
    return list;
  }
  async function saveRelated(track, section, body, query) {
    try {
      await postJSON("/api/related", body);
      setNotice("Link saved.");
      const kept = section.querySelector(".related-search input");
      await loadRelated(track, section, Boolean(track.serato?.writable && state.writable), kept ? kept.value : query);
    } catch (error) {
      if (failureOf(error).status === 409) lockDown(error);
      else setNotice(failureOf(error).message);
      const status = section.querySelector("[role=status]");
      if (status) status.textContent = failureOf(error).message;
    }
  }
  async function removeRelated(track, section, link) {
    const label = link.track?.title || "this track";
    if (!confirm(`Remove the link to “${label}”?`)) return;
    try {
      await postJSON("/api/related", { action: "remove", id: link.id });
      setNotice("Link removed.");
      const kept = section.querySelector(".related-search input");
      await loadRelated(track, section, Boolean(track.serato?.writable && state.writable), kept ? kept.value : "");
    } catch (error) {
      setNotice(failureOf(error).message);
    }
  }
  async function refreshRelatedCrate(track, section) {
    const button = section.querySelector("[data-related-crate]");
    if (button) button.disabled = true;
    try {
      const result = await postJSON("/api/related", { action: "crate", asset: track.id, space: state.space });
      setNotice(result.warning || `Crate “${result.name}” updated.`);
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
  function setNotice(text) {
    el("notice").textContent = text || "";
    el("notice").hidden = !text;
  }
  function applyStatus(info) {
    state.serato = info;
    state.writable = Boolean(info?.writable);
    el("status").textContent = info?.message || "Library";
    renderShell();
  }
  function lockDown(error) {
    const failed = failureOf(error);
    applyStatus(failed.payload?.serato || { writable: false, message: failed.message });
    setNotice(failed.message);
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
      is_beatgrid_locked: form.querySelector("[name=is_beatgrid_locked]").checked
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
      if (failureOf(error).status === 409) lockDown(error);
      else setNotice(failureOf(error).message);
    }
  }
  async function revealTrack(id) {
    try {
      await postJSON("/api/reveal", { id });
    } catch (error) {
      setNotice(failureOf(error).message);
    }
  }
  async function prepareTrack(id, add) {
    try {
      const result = await postJSON("/api/crate", { action: "prepare", asset: id, add, space: state.space });
      setNotice(result.warning || (add ? "Sent to Prepare." : "Removed from Prepare."));
      await loadLibrary();
      selectTrack(id);
    } catch (error) {
      if (failureOf(error).status === 409) lockDown(error);
      else setNotice(failureOf(error).message);
    }
  }
  async function relocateTrack(track) {
    const path = prompt("Path to the audio file", track.resolved_path || track.edit?.portable_id || "");
    if (!path) return;
    try {
      const result = await postJSON("/api/track", {
        id: track.id,
        space: state.space,
        fields: { portable_id: path }
      });
      setNotice(result.warning || "File location saved.");
      await loadLibrary();
      selectTrack(track.id);
    } catch (error) {
      if (failureOf(error).status === 409) lockDown(error);
      else setNotice(failureOf(error).message);
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
      if (failureOf(error).status === 409) lockDown(error);
      else setNotice(failureOf(error).message);
    }
  }
  async function setMembership(assetId, crateId, add, input) {
    try {
      const result = await postJSON("/api/crate", {
        action: add ? "add" : "remove",
        id: crateId,
        asset: assetId,
        space: state.space
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
      if (failureOf(error).status === 409) lockDown(error);
      else setNotice(failureOf(error).message);
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
      if (failureOf(error).status === 409) lockDown(error);
      else setNotice(failureOf(error).message);
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
      if (failureOf(error).status === 409) lockDown(error);
      else setNotice(failureOf(error).message);
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
        color: color === 16777215 ? null : color,
        space: state.space
      });
      setNotice(result.warning || "Crate color saved.");
      await loadLibrary();
    } catch (error) {
      if (failureOf(error).status === 409) lockDown(error);
      else setNotice(failureOf(error).message);
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
      if (failureOf(error).status === 409) lockDown(error);
      else setNotice(failureOf(error).message);
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
      if (failureOf(error).status === 409) lockDown(error);
      else setNotice(failureOf(error).message);
    }
  }
  function renderSessions() {
    el("session-list").replaceChildren();
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
      el("session-list").append(button);
    }
  }
  async function loadHistory() {
    const response = await fetch("/api/history");
    const payload = await readJSONOr(response, {});
    if (!response.ok) throw new Error(payload.error || "Could not read history.");
    state.historySessions = payload.sessions || [];
    renderSessions();
  }
  async function openSession(id) {
    state.historyId = id;
    state.selectedId = null;
    renderSessions();
    const response = await fetch(`/api/history?session=${id}`);
    const payload = await readJSONOr(response, {});
    if (!response.ok) {
      setNotice(payload.error || "Could not read that session.");
      return;
    }
    state.entries = payload.entries || [];
    el("list").scrollTop = 0;
    renderList();
  }
  async function loadDuplicates() {
    state.duplicateIds = null;
    state.duplicateGroups = [];
    const response = await fetch(`/api/duplicates?space=${encodeURIComponent(state.space)}`);
    const payload = await readJSONOr(response, {});
    if (!response.ok) throw new Error(payload.error || "Could not read duplicates.");
    const ids = /* @__PURE__ */ new Set();
    state.duplicateGroups = payload.groups || [];
    for (const group of state.duplicateGroups) for (const id of group.ids || []) ids.add(id);
    state.duplicateIds = ids;
    state.duplicateSpace = state.space;
    if (state.mode === "duplicates") renderList();
  }
  async function openInLibrary(assetId) {
    state.space = "Serato Library";
    el("space").value = state.space;
    state.mode = "crates";
    state.activeCrate = "all";
    state.selectedId = assetId;
    await loadLibrary();
    selectTrack(assetId);
  }
  async function loadLibrary() {
    el("count").textContent = "Loading the library";
    const response = await fetch(`/api/library?space=${encodeURIComponent(state.space)}`);
    const library = await readJSONOr(response, {});
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
  function setMode(mode) {
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
      loadFolder(state.filesPath || "").catch((error) => failFiles(error));
    }
    if (mode === "snapshots") {
      loadSnapshots().catch((error) => failSnapshots(error));
    }
    renderList();
  }
  function showFailure(error) {
    el("count").textContent = "Library unavailable";
    const failure = document.createElement("p");
    failure.className = "detail-error";
    failure.textContent = failureOf(error).message;
    el("detail").replaceChildren(failure);
  }
  function selectedDuplicateGroup() {
    if (state.mode !== "duplicates" || state.selectedId == null) return null;
    return (state.duplicateGroups || []).find((group) => (group.ids || []).includes(state.selectedId)) || null;
  }
  function syncMergeButton() {
    const wrap = el("duplicate-actions");
    const button = el("merge-duplicates");
    if (!wrap || !button) return;
    const show = state.mode === "duplicates";
    wrap.hidden = !show;
    button.disabled = !show || !state.writable || !selectedDuplicateGroup();
  }
  function crateNamesFor(assetId) {
    return state.crates.filter((crate) => !crate.smart && (crate.tracks || []).includes(assetId)).map((crate) => crate.name);
  }
  function failFiles(error) {
    state.filesLoading = false;
    state.filesError = failureOf(error).message || "That folder could not be read.";
    renderFiles();
  }
  async function loadFolder(path, options = {}) {
    state.filesLoading = true;
    state.filesError = "";
    if (!options.keepMessage) state.filesMessage = "";
    state.filesSelected = /* @__PURE__ */ new Set();
    renderFiles();
    const query = path ? `?path=${encodeURIComponent(path)}` : "";
    const response = await fetch(`/api/files${query}`);
    const payload = await readJSONOr(response, {});
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
  function renderFiles() {
    if (state.mode !== "files") return;
    const pick = el("files-pick");
    const moveHere = el("files-move-here");
    const pickCancel = el("files-pick-cancel");
    pick.hidden = !state.filesPick;
    moveHere.hidden = !state.filesPick;
    pickCancel.hidden = !state.filesPick;
    el("files-path").textContent = state.filesPath || "Home";
    el("files-up").disabled = !state.filesParent || state.filesLoading;
    const notes = [];
    if (state.filesLoading) notes.push("Reading this folder.");
    if (state.filesError) notes.push(state.filesError);
    if (state.filesMessage) notes.push(state.filesMessage);
    if (state.filesTruncated) notes.push("Some files are not listed.");
    el("files-status").textContent = notes.join(" ");
    el("files-list").setAttribute("aria-busy", String(state.filesLoading));
    el("files-list").replaceChildren();
    if (state.filesLoading && !state.filesEntries.length) {
      const loading = document.createElement("p");
      loading.className = "files-empty";
      loading.textContent = "Reading this folder.";
      el("files-list").append(loading);
    } else if (!state.filesEntries.length) {
      const empty = document.createElement("p");
      empty.className = "files-empty";
      empty.textContent = state.filesError || "This folder is empty.";
      el("files-list").append(empty);
    } else {
      const rank = { dir: 0, file: 1, link: 2 };
      const entries = [...state.filesEntries].sort((left, right) => {
        return (rank[left.kind] ?? 3) - (rank[right.kind] ?? 3) || left.name.localeCompare(right.name);
      });
      for (const entry of entries) el("files-list").append(fileRow(entry));
    }
    const selected = selectedFiles();
    const locked = !state.writable || state.filesLoading;
    el("files-rename").disabled = locked || selected.length !== 1;
    el("files-move").disabled = locked || !selected.length || Boolean(state.filesPick);
    el("files-move-folder").disabled = locked || !state.filesPath || Boolean(state.filesPick);
    el("files-replace").disabled = locked || selected.length !== 1;
    el("files-delete").disabled = locked || !selected.length;
    moveHere.disabled = locked;
    renderShell();
  }
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
      const label2 = document.createElement("span");
      label2.className = "files-kind";
      label2.textContent = `${entry.name} (shortcut)`;
      row.append(label2);
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
  function selectedFiles() {
    return state.filesEntries.filter((entry) => entry.kind === "file" && state.filesSelected.has(entry.path));
  }
  function wireLibrary() {
    el("search").addEventListener("input", () => {
      state.query = el("search").value;
      el("list").scrollTop = 0;
      renderList();
    });
    el("crate-search").addEventListener("input", (event) => {
      state.crateQuery = event.target.value;
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
      const file = event.target.files?.[0];
      event.target.value = "";
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
    el("crate-new").addEventListener("click", () => createCrate().catch((error) => setNotice(failureOf(error).message)));
    el("crate-rename").addEventListener("click", () => renameCrate().catch((error) => setNotice(failureOf(error).message)));
    el("crate-color").addEventListener("click", () => colorCrate().catch((error) => setNotice(failureOf(error).message)));
    el("crate-delete").addEventListener("click", () => deleteCrate().catch((error) => setNotice(failureOf(error).message)));
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
    el("crate-list").addEventListener("keydown", (event) => {
      const item = event.target.closest(".crate");
      if (!item || !el("crate-list").contains(item)) return;
      const items = [...el("crate-list").querySelectorAll(".crate")];
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

  // src/dialogs.ts
  var rekordboxXml = "";
  var mergePreview = null;
  var mergeToken = 0;
  var mergeLoading = false;
  var consentSettled = false;
  var privacySync = false;
  var filesPreview = null;
  var filesAction = "";
  var filesTrigger = null;
  function rekordboxExportUrl(report) {
    const crate = state.mode === "crates" ? state.activeCrate : "all";
    const memory = el("rekordbox-memory").checked ? "1" : "0";
    const key = el("rekordbox-key").value;
    const base = `/api/export.rekordbox.xml?space=${encodeURIComponent(state.space)}&crate=${encodeURIComponent(crate)}&memory=${memory}&key=${encodeURIComponent(key)}`;
    return report ? `${base}&report=1` : base;
  }
  function fillRekordboxReport(lines) {
    const list = el("rekordbox-report");
    list.replaceChildren();
    for (const line of lines) {
      const item = document.createElement("li");
      item.textContent = line;
      list.append(item);
    }
  }
  function selectedMergeKeepId() {
    const checked = el("merge-choices").querySelector("input:checked");
    if (checked) return Number(checked.value);
    return state.selectedId;
  }
  function previewFieldValue(field, value) {
    if (value == null || value === "") return "empty";
    if (field === "time_added") {
      const date = new Date(Number(value) * 1e3);
      if (!Number.isNaN(date.getTime())) {
        return date.toLocaleString(void 0, {
          month: "short",
          day: "numeric",
          year: "numeric",
          hour: "numeric",
          minute: "2-digit",
          second: "2-digit"
        });
      }
    }
    return String(value);
  }
  function renderMergePreview(preview) {
    el("merge-preview").replaceChildren();
    if (!preview) {
      const pending = document.createElement("p");
      pending.textContent = "Reading the preview…";
      el("merge-preview").append(pending);
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
      const names = added.map((crate) => crate.space && crate.space !== state.space ? `${crate.name} (${crate.space})` : crate.name);
      item(`Add the kept copy to ${names.join(", ")}.`);
    } else if ((preview.crates_kept || []).length) {
      item("The kept copy is already in every crate the others use. It stays where it is.");
    } else {
      item("None of the copies are in a crate.");
    }
    for (const space of preview.spaces_added || []) item(`Add the kept copy to the ${space} space.`);
    if ((preview.fields || []).length) {
      for (const field of preview.fields || []) {
        const before = previewFieldValue(field.field || "", field.before);
        const after = previewFieldValue(field.field || "", field.after);
        item(`${field.label} changes from ${before} to ${after}.`);
      }
    } else {
      item("No empty fields or higher play count to copy.");
    }
    if (preview.history_repointed) {
      const count = Number(preview.history_entries) || 0;
      item(count ? `Point ${count} history ${count === 1 ? "entry" : "entries"} at the kept copy.` : "No history entries point at the other copies.");
    } else {
      item("This library has no history track id to repoint.");
    }
    const removed = (preview.removed || []).length;
    item(`Remove ${removed} ${removed === 1 ? "copy" : "copies"} from the library.`);
    for (const file of preview.files || []) {
      if (file.reason) item(`${file.file}: ${file.reason}`);
    }
    el("merge-preview").append(list);
    if (preview.cue_warning) {
      const warning = document.createElement("p");
      warning.className = "merge-warning";
      warning.textContent = preview.cue_warning;
      el("merge-preview").append(warning);
    }
    const files = document.createElement("p");
    files.id = "merge-file-note";
    files.className = "dialog-note";
    el("merge-preview").append(files);
  }
  function syncTrashChoice() {
    const files = mergePreview?.files || [];
    const trashable = files.filter((file) => file.on_disk && !file.blocks_trash);
    const blocked = files.some((file) => file.blocks_trash);
    el("merge-trash").disabled = !mergePreview || mergeLoading || blocked || trashable.length === 0;
    if (el("merge-trash").disabled) el("merge-trash").checked = false;
    const danger = el("merge-trash").checked;
    el("merge-confirm").classList.toggle("danger", danger);
    el("merge-confirm").textContent = mergeLoading ? "Merging…" : danger ? "Merge and move files to Trash" : "Merge copies";
    el("merge-confirm").disabled = mergeLoading || !mergePreview || mergePreview.writable === false;
    const note = el("merge-file-note");
    if (!note) return;
    if (danger) note.textContent = `Move ${trashable.map((file) => file.file).join(", ")} to the Trash.`;
    else note.textContent = "Audio files stay on disk.";
  }
  async function refreshMergePreview() {
    const keepId = selectedMergeKeepId();
    const token = ++mergeToken;
    mergeLoading = false;
    mergePreview = null;
    el("merge-status").textContent = "";
    renderMergePreview(null);
    syncTrashChoice();
    el("merge-confirm").disabled = true;
    try {
      const preview = await postJSON("/api/duplicates/merge", {
        space: state.space,
        keep_id: keepId,
        preview: true
      });
      if (token !== mergeToken) return;
      mergePreview = preview;
      renderMergePreview(preview);
      if (preview.writable === false) {
        el("merge-status").textContent = "Quit Serato before merging. The preview shows the plan.";
      }
      syncTrashChoice();
    } catch (error) {
      if (token !== mergeToken) return;
      mergePreview = null;
      el("merge-preview").replaceChildren();
      const failed = document.createElement("p");
      failed.textContent = "The preview could not be read.";
      el("merge-preview").append(failed);
      el("merge-status").textContent = failureOf(error).message;
      syncTrashChoice();
    }
  }
  function renderMergeChoices() {
    const group = selectedDuplicateGroup();
    el("merge-choices").replaceChildren();
    if (!group) return;
    for (const id of group.ids || []) {
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
        if (input.checked) refreshMergePreview().catch((error) => setNotice(failureOf(error).message));
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
      el("merge-choices").append(label);
    }
  }
  async function openMergeDialog() {
    if (!selectedDuplicateGroup() || !state.writable) return;
    if (typeof el("merge-dialog").showModal !== "function") return;
    el("merge-trash").checked = false;
    el("merge-status").textContent = "";
    renderMergeChoices();
    if (!el("merge-dialog").open) el("merge-dialog").showModal();
    el("merge-cancel").focus();
    await refreshMergePreview();
  }
  async function confirmMerge() {
    const keepId = selectedMergeKeepId();
    if (keepId == null || mergeLoading) return;
    const trash = el("merge-trash").checked;
    mergeLoading = true;
    syncTrashChoice();
    el("merge-status").textContent = "";
    try {
      const result = await postJSON("/api/duplicates/merge", {
        space: state.space,
        keep_id: keepId,
        confirm: true,
        delete_files: trash,
        confirm_delete_files: trash
      });
      el("merge-dialog").close();
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
      el("merge-status").textContent = failureOf(error).message;
      if (failureOf(error).status === 409) {
        lockDown(error);
        el("merge-dialog").close();
      }
    } finally {
      mergeLoading = false;
      syncTrashChoice();
    }
  }
  function telemetryNoteText() {
    if (!state.telemetryConfigured) {
      return "This copy has no telemetry keys, so nothing is sent either way.";
    }
    if (state.telemetryConsent === true) {
      return "Anonymous counts and crash reports can be sent.";
    }
    return "Nothing is sent.";
  }
  function applyPrivacy(payload) {
    state.telemetryConsent = payload.telemetry_consent ?? null;
    state.telemetryConfigured = Boolean(payload.telemetry_configured);
    privacySync = true;
    el("telemetry-toggle").checked = state.telemetryConsent === true;
    privacySync = false;
    el("telemetry-note").textContent = telemetryNoteText();
  }
  async function saveConsent(value, status) {
    status.textContent = "Saving…";
    try {
      const payload = await postJSON("/api/settings", { telemetry_consent: value });
      applyPrivacy(payload);
      status.textContent = value ? "Sharing is on. Anonymous counts and crash reports can be sent." : "Sharing is off. Nothing is sent.";
      return true;
    } catch (error) {
      status.textContent = "Couldn't save that choice. Try again.";
      return false;
    }
  }
  function showConsent() {
    if (typeof el("consent-dialog").showModal !== "function") return;
    if (el("consent-dialog").open) return;
    consentSettled = false;
    el("consent-status").textContent = "";
    el("consent-dialog").showModal();
    el("consent-decline").focus();
  }
  async function loadPrivacy() {
    const response = await fetch("/api/settings");
    const payload = await readJSONOr(response, {});
    if (!response.ok) throw new Error(payload.error || "Couldn't load sharing settings.");
    applyPrivacy(payload);
    if (payload.needs_consent_prompt) showConsent();
  }
  function openFilesDialog(action, trigger) {
    filesAction = action;
    filesPreview = null;
    filesTrigger = trigger instanceof HTMLElement ? trigger : null;
    el("files-name-label").hidden = action !== "rename";
    el("files-replace-label").hidden = action !== "replace";
    el("files-summary").textContent = "";
    el("files-warning").textContent = "";
    el("files-dialog-status").textContent = "";
    el("files-changes").replaceChildren();
    const selected = selectedFiles();
    if (action === "rename" && selected.length === 1) el("files-name").value = selected[0].name;
    if (action === "replace") el("files-replacement").value = "";
    const confirm2 = el("files-confirm");
    confirm2.classList.toggle("danger", action === "delete");
    confirm2.textContent = action === "delete" ? "Move to Trash" : "Confirm";
    syncFilesDialog();
    el("files-dialog").showModal();
    if (action === "delete" || action === "move" || action === "move_folder") {
      el("files-cancel").focus();
      reviewFiles().catch((error) => {
        el("files-dialog-status").textContent = failureOf(error).message;
      });
    } else if (action === "rename") el("files-name").focus();
    else el("files-replacement").focus();
  }
  function syncFilesDialog() {
    const confirm2 = el("files-confirm");
    const review = el("files-review");
    const ready = Boolean(filesPreview?.ok && state.writable && filesPreview.needs_confirm);
    confirm2.disabled = !ready;
    review.hidden = filesAction === "delete" || filesAction === "move" || filesAction === "move_folder";
    if (!state.writable) {
      el("files-dialog-status").textContent = el("status").textContent;
    }
  }
  async function reviewFiles() {
    const body = filesBody(false);
    el("files-dialog-status").textContent = "Checking what will change.";
    const payload = await postJSON("/api/files", body);
    filesPreview = payload;
    el("files-summary").textContent = payload.summary || "";
    el("files-warning").textContent = payload.warning || "";
    el("files-dialog-status").textContent = payload.ok ? "" : payload.error || "That change was not saved.";
    const list = el("files-changes");
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
  function filesBody(confirm2) {
    const body = { action: filesAction };
    if (confirm2) body.confirm = true;
    if (filesAction === "rename") {
      const selected = selectedFiles();
      body.path = selected[0]?.path || state.filesPickPaths[0];
      body.name = el("files-name").value;
    } else if (filesAction === "move") {
      body.paths = state.filesPickPaths.length ? [...state.filesPickPaths] : selectedFiles().map((entry) => entry.path);
      body.destination = state.filesPath;
    } else if (filesAction === "move_folder") {
      body.path = state.filesPickSource || state.filesPath;
      body.destination = state.filesPath;
    } else if (filesAction === "replace") {
      const selected = selectedFiles();
      body.path = selected[0]?.path || "";
      body.replacement = el("files-replacement").value.trim();
    } else if (filesAction === "delete") {
      body.paths = selectedFiles().map((entry) => entry.path);
    }
    return body;
  }
  function closeFilesDialog() {
    const trigger = filesTrigger;
    filesTrigger = null;
    if (el("files-dialog").open) el("files-dialog").close();
    if (trigger instanceof HTMLElement) trigger.focus();
  }
  async function confirmFiles() {
    if (!filesPreview?.ok || !state.writable) return;
    const confirm2 = el("files-confirm");
    confirm2.disabled = true;
    el("files-dialog-status").textContent = "Saving.";
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
      if (failureOf(error).status === 409) lockDown(error);
      el("files-dialog-status").textContent = failureOf(error).message;
      confirm2.disabled = false;
    }
  }
  function wireDialogs() {
    el("export-rekordbox").addEventListener("click", () => {
      rekordboxXml = "";
      fetch(rekordboxExportUrl(true)).then((response) => response.json().then((body) => ({ ok: response.ok, body }))).then(({ ok, body }) => {
        if (!ok || typeof body.xml !== "string" || !body.xml.startsWith("<?xml")) {
          setNotice(body.error || "The Rekordbox export failed.");
          return;
        }
        rekordboxXml = body.xml;
        fillRekordboxReport(body.report || []);
        el("rekordbox-status").textContent = "";
        el("rekordbox-dialog").showModal();
      }).catch((error) => setNotice(failureOf(error).message));
    });
    el("rekordbox-cancel").addEventListener("click", () => {
      rekordboxXml = "";
      el("rekordbox-dialog").close();
    });
    el("rekordbox-download").addEventListener("click", () => {
      if (!rekordboxXml.startsWith("<?xml")) {
        el("rekordbox-status").textContent = "The export did not produce an XML file.";
        return;
      }
      const blob = new Blob([rekordboxXml], { type: "application/xml" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "rekordbox.xml";
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1500);
      rekordboxXml = "";
      el("rekordbox-dialog").close();
    });
    el("merge-duplicates").addEventListener("click", () => {
      openMergeDialog().catch((error) => setNotice(failureOf(error).message));
    });
    el("merge-cancel").addEventListener("click", () => el("merge-dialog").close());
    el("merge-confirm").addEventListener("click", () => {
      confirmMerge().catch((error) => setNotice(failureOf(error).message));
    });
    el("merge-trash").addEventListener("change", () => syncTrashChoice());
    el("consent-decline").addEventListener("click", () => {
      saveConsent(false, el("consent-status")).then((ok) => {
        if (!ok) return;
        consentSettled = true;
        el("consent-dialog").close();
      });
    });
    el("consent-accept").addEventListener("click", () => {
      saveConsent(true, el("consent-status")).then((ok) => {
        if (!ok) return;
        consentSettled = true;
        el("consent-dialog").close();
      });
    });
    el("consent-dialog").addEventListener("close", () => {
      if (consentSettled || state.telemetryConsent !== null) return;
      saveConsent(false, el("consent-status")).then((ok) => {
        if (ok) {
          consentSettled = true;
          return;
        }
        el("consent-dialog").showModal();
      });
    });
    el("open-settings").addEventListener("click", () => {
      el("settings-status").textContent = "";
      el("log-fallback").hidden = true;
      el("telemetry-note").textContent = telemetryNoteText();
      el("settings-dialog").showModal();
    });
    el("settings-close").addEventListener("click", () => {
      el("settings-dialog").close();
    });
    el("telemetry-toggle").addEventListener("change", () => {
      if (privacySync) return;
      const want = el("telemetry-toggle").checked;
      el("telemetry-toggle").disabled = true;
      saveConsent(want, el("settings-status")).then((ok) => {
        el("telemetry-toggle").disabled = false;
        if (ok) {
          consentSettled = true;
          return;
        }
        privacySync = true;
        el("telemetry-toggle").checked = state.telemetryConsent === true;
        privacySync = false;
      });
    });
    el("open-logs").addEventListener("click", () => {
      const button = el("open-logs");
      button.disabled = true;
      el("settings-status").textContent = "Opening…";
      postJSON("/api/logs/open", {}).then(() => {
        el("settings-status").textContent = "Opened the logs folder.";
      }).catch(() => {
        el("settings-status").textContent = "Couldn't open the logs folder.";
      }).finally(() => {
        button.disabled = false;
      });
    });
    el("copy-logs").addEventListener("click", async () => {
      const button = el("copy-logs");
      button.disabled = true;
      el("settings-status").textContent = "Copying…";
      try {
        const response = await fetch("/api/logs");
        const payload = await readJSONOr(response, {});
        if (!response.ok) throw new Error(payload.error || "Couldn't copy the logs.");
        const text = payload.text || "";
        if (!text) {
          el("settings-status").textContent = "No log entries yet.";
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
          el("log-fallback").hidden = true;
          el("settings-status").textContent = payload.truncated ? "Copied the latest log entries. Older entries were left out." : "Copied the logs.";
          return;
        }
        el("log-fallback").hidden = false;
        el("log-fallback").value = text;
        el("log-fallback").focus();
        el("log-fallback").select();
        el("settings-status").textContent = "Couldn't copy automatically. Select the log text and copy it.";
      } catch (error) {
        el("settings-status").textContent = "Couldn't copy the logs.";
      } finally {
        button.disabled = false;
      }
    });
    el("files-up").addEventListener("click", () => {
      if (state.filesParent) loadFolder(state.filesParent).catch((error) => failFiles(error));
    });
    el("files-refresh").addEventListener("click", () => {
      loadFolder(state.filesPath || "").catch((error) => failFiles(error));
    });
    el("files-rename").addEventListener("click", (event) => {
      if (selectedFiles().length !== 1) {
        state.filesError = "Choose one file to rename.";
        renderFiles();
        return;
      }
      openFilesDialog("rename", event.currentTarget);
    });
    el("files-move").addEventListener("click", () => {
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
    el("files-move-folder").addEventListener("click", () => {
      state.filesPick = "move_folder";
      state.filesPickSource = state.filesPath;
      state.filesError = "";
      state.filesMessage = "Choose the destination folder. Then confirm the move.";
      renderFiles();
    });
    el("files-move-here").addEventListener("click", (event) => {
      openFilesDialog(state.filesPick === "move_folder" ? "move_folder" : "move", event.currentTarget);
    });
    el("files-pick-cancel").addEventListener("click", () => {
      state.filesPick = null;
      state.filesPickPaths = [];
      state.filesPickSource = "";
      state.filesMessage = "";
      renderFiles();
    });
    el("files-replace").addEventListener("click", (event) => {
      if (selectedFiles().length !== 1) {
        state.filesError = "Choose one file to replace.";
        renderFiles();
        return;
      }
      openFilesDialog("replace", event.currentTarget);
    });
    el("files-delete").addEventListener("click", (event) => {
      if (!selectedFiles().length) {
        state.filesError = "Choose files to delete.";
        renderFiles();
        return;
      }
      openFilesDialog("delete", event.currentTarget);
    });
    el("files-review").addEventListener("click", () => {
      reviewFiles().catch((error) => {
        el("files-dialog-status").textContent = failureOf(error).message;
      });
    });
    el("files-confirm").addEventListener("click", () => {
      confirmFiles().catch((error) => {
        el("files-dialog-status").textContent = failureOf(error).message;
      });
    });
    el("files-cancel").addEventListener("click", () => closeFilesDialog());
    el("files-name").addEventListener("input", () => {
      filesPreview = null;
      syncFilesDialog();
    });
    el("files-replacement").addEventListener("input", () => {
      filesPreview = null;
      syncFilesDialog();
    });
    el("files-dialog").addEventListener("cancel", (event) => {
      event.preventDefault();
      closeFilesDialog();
    });
  }
  bridge.openMergeDialog = openMergeDialog;

  // src/app.ts
  function wireSnapshots() {
    el("snapshots-refresh").addEventListener("click", () => {
      loadSnapshots().catch((error) => failSnapshots(error));
    });
    el("snapshots-take").addEventListener("click", () => {
      takeSnapshot().catch((error) => failSnapshots(error));
    });
    el("snapshots-undo-button").addEventListener("click", () => {
      const pending = state.snapshotUndo;
      if (!pending || !pending.restore_id) return;
      openSnapshotPlan(pending.restore_id).catch((error) => failSnapshots(error));
    });
    el("snapshot-cancel").addEventListener("click", () => {
      el("snapshot-dialog").close();
    });
    el("snapshot-confirm").addEventListener("click", () => {
      confirmSnapshotRestore().catch((error) => setSnapshotDialogStatus(failureOf(error).message));
    });
  }
  mountTrackList();
  wireLibrary();
  wireVirtualScroll();
  wireDialogs();
  wireSnapshots();
  bindLibraryReload(loadLibrary);
  loadLibrary().catch(showFailure);
  loadPrivacy().catch((error) => setNotice(failureOf(error).message || "Couldn't load sharing settings. Nothing is sent."));
})();
//# sourceMappingURL=app.js.map
