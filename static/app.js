"use strict";
(() => {
  // src/api.ts
  async function readJSON(response) {
    return await response.json();
  }
  async function readJSONOr(response, fallback) {
    return await response.json().catch(() => fallback);
  }
  function failureOf(error2) {
    if (error2 instanceof Error) return error2;
    return new Error(typeof error2 === "string" ? error2 : "Request failed");
  }
  var ROOT_KINDS = ["music_library", "serato_drive", "user_folder"];
  function isLibraryRoot(value) {
    if (!value || typeof value !== "object") return false;
    const record = value;
    return typeof record.id === "string" && typeof record.path === "string" && typeof record.label === "string" && typeof record.detail === "string" && ROOT_KINDS.includes(record.kind) && typeof record.serato === "boolean" && typeof record.removable === "boolean" && typeof record.missing === "boolean";
  }
  async function fetchLibraryRoots(refresh = false) {
    const response = await fetch(refresh ? "/api/library-roots?refresh=1" : "/api/library-roots");
    const payload = await readJSONOr(response, {
      roots: [],
      computed_at: ""
    });
    if (!response.ok) {
      const error2 = new Error(payload.error || "Music folders could not be read.");
      error2.status = response.status;
      error2.payload = payload;
      throw error2;
    }
    return {
      roots: Array.isArray(payload.roots) ? payload.roots.filter(isLibraryRoot) : [],
      computed_at: typeof payload.computed_at === "string" ? payload.computed_at : ""
    };
  }
  function isVersionSource(value) {
    return value === "release" || value === "git" || value === "dev";
  }
  function isVersionPayload(value) {
    if (!value || typeof value !== "object") return false;
    const record = value;
    return typeof record.version === "string" && record.version.trim() !== "" && (record.commit === null || typeof record.commit === "string") && isVersionSource(record.source);
  }
  async function getVersion() {
    const response = await fetch("/api/version");
    const payload = await readJSONOr(response, null);
    if (!response.ok || !isVersionPayload(payload)) {
      throw new Error("Version unavailable");
    }
    return {
      version: payload.version.trim(),
      commit: payload.commit,
      source: payload.source
    };
  }
  async function postJSON(url, body) {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
    const payload = await readJSONOr(response, {});
    if (!response.ok) {
      const error2 = new Error(payload.error || `Request failed (${response.status})`);
      error2.status = response.status;
      error2.payload = payload;
      throw error2;
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
    },
    openSetup() {
    }
  };

  // src/dom.ts
  function el(id) {
    const node = document.getElementById(id);
    if (node == null) throw new Error(`Missing #${id}`);
    return node;
  }

  // src/splitter.ts
  function clampWidth(width, available, minFirst, minSecond) {
    const max = Math.max(minFirst, available - minSecond);
    return Math.round(Math.min(Math.max(width, minFirst), max));
  }
  function mountSplitter(options) {
    const { handle, container, first, property, minFirst, minSecond, onCommit } = options;
    const step = options.step ?? 16;
    let current = null;
    const available = () => container.clientWidth - handle.offsetWidth;
    const fitted = (width) => clampWidth(width, available(), minFirst, minSecond);
    const shown = () => current == null ? first.getBoundingClientRect().width : fitted(current);
    function paint3() {
      if (current == null) container.style.removeProperty(property);
      else container.style.setProperty(property, `${fitted(current)}px`);
      const room = available();
      handle.setAttribute("aria-valuemin", String(minFirst));
      handle.setAttribute("aria-valuemax", String(Math.max(minFirst, Math.round(room - minSecond))));
      handle.setAttribute("aria-valuenow", String(Math.round(shown())));
    }
    function move(width) {
      current = fitted(width);
      paint3();
    }
    handle.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      event.preventDefault();
      const startX = event.clientX;
      const startWidth = shown();
      let moved = false;
      handle.setPointerCapture?.(event.pointerId);
      handle.dataset.dragging = "true";
      document.body.classList.add("is-resizing");
      const onMove = (next) => {
        moved = true;
        move(startWidth + next.clientX - startX);
      };
      const onEnd = () => {
        handle.removeEventListener("pointermove", onMove);
        handle.removeEventListener("pointerup", onEnd);
        handle.removeEventListener("pointercancel", onEnd);
        delete handle.dataset.dragging;
        document.body.classList.remove("is-resizing");
        if (moved) onCommit(current);
      };
      handle.addEventListener("pointermove", onMove);
      handle.addEventListener("pointerup", onEnd);
      handle.addEventListener("pointercancel", onEnd);
    });
    handle.addEventListener("keydown", (event) => {
      const jump = event.shiftKey ? step * 4 : step;
      let next;
      if (event.key === "ArrowLeft") next = shown() - jump;
      else if (event.key === "ArrowRight") next = shown() + jump;
      else if (event.key === "Home") next = minFirst;
      else if (event.key === "End") next = available() - minSecond;
      else return;
      event.preventDefault();
      const before = current;
      move(next);
      if (current !== before) onCommit(current);
    });
    handle.addEventListener("dblclick", () => {
      current = null;
      paint3();
      onCommit(null);
    });
    paint3();
    return {
      set(width) {
        current = width == null ? null : Math.round(width);
        paint3();
      },
      width: () => current,
      refit: paint3
    };
  }

  // src/copy.ts
  var copy = {
    shortcutsTitle: "Keyboard shortcuts",
    shortcutsIntro: "These keys work anywhere on this screen, except while you are typing in a field. Esc still closes a dialog or clears a search.",
    shortcutsClose: "Close",
    openShortcuts: "Shortcuts",
    playNote: "Space and the left and right arrows play or move through a track once playback is available. Until then, they do nothing.",
    quickOpenTitle: "Find a track or file",
    quickOpenLabel: "Name",
    quickOpenPlaceholder: "Track or file name",
    quickOpenEmpty: "Type a track or file name.",
    quickOpenSearching: "Searching files…",
    quickOpenFileError: "Files on disk could not be searched. Track matches are still listed.",
    quickOpenRetry: "Try again",
    quickOpenNone: "No tracks or files match “{query}”.",
    quickOpenTruncated: "Some files were not searched. Type more of the name.",
    quickOpenClose: "Close",
    quickOpenTrack: "Track",
    quickOpenFile: "File",
    filesSearchLabel: "Search files",
    filesSearchPlaceholder: "Search files",
    filesSearching: "Searching files…",
    filesNoMatches: "No files match “{query}”.",
    filesTruncated: "Some matching files are not listed. Type more of the name.",
    filesSearchResults: "Search results",
    snapshotsNoSearch: "Snapshots has no search. Press Ctrl+K to find a track or a file."
  };
  function fill(template, params) {
    return template.replace(/\{(\w+)\}/g, (_match, name) => params[name] ?? "");
  }

  // src/state.ts
  var ROW = 36;
  var FILE_ROW = 44;
  var ROOT_ROW = 64;
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
    wizardComplete: false,
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
    filesAtRoots: false,
    filesRoots: [],
    filesRoot: null,
    filesBreadcrumb: [],
    filesElsewhere: false,
    filesActive: 0,
    filesQuery: "",
    filesSearching: false,
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
  function failSnapshots(error2) {
    state.snapshotLoading = false;
    state.snapshotError = failureOf(error2).message || "The snapshots could not be read.";
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
      retry.addEventListener("click", () => loadSnapshots().catch((error2) => failSnapshots(error2)));
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
      const title2 = document.createElement("p");
      title2.textContent = `${item.created || "Unknown time"} · ${item.trigger || "snapshot"}`;
      const detail = document.createElement("p");
      const version = item.serato_version && item.serato_version !== "unknown" ? `Serato ${item.serato_version} (build ${item.serato_build})` : "Serato version unknown";
      const drives = (item.unavailable_drives || []).length ? ` Unavailable: ${(item.unavailable_drives || []).join(", ")}.` : "";
      detail.textContent = `${version}. ${item.reason || ""}${drives}`;
      const restore = document.createElement("button");
      restore.type = "button";
      restore.textContent = "Review restore";
      restore.addEventListener("click", () => openSnapshotPlan(item.id).catch((error2) => setSnapshotDialogStatus(failureOf(error2).message)));
      card.append(title2, detail, restore);
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
    } catch (error2) {
      setSnapshotDialogStatus(failureOf(error2).message);
      confirm2.disabled = false;
    } finally {
      confirm2.textContent = "Restore";
    }
  }

  // src/player-strings.ts
  var playerStrings = {
    region: "Player",
    play: "Play",
    pause: "Pause",
    seek: "Seek",
    volume: "Volume",
    elapsed: "Elapsed",
    duration: "Duration",
    nothingPlaying: "Nothing playing",
    untitled: "Untitled",
    cannotPlay: "This file cannot be played in this window."
  };

  // src/player.ts
  var listeners = /* @__PURE__ */ new Set();
  var wired = /* @__PURE__ */ new WeakSet();
  var media = null;
  var trackId = null;
  var title = "";
  var artist = "";
  var playing = false;
  var currentTime = 0;
  var duration = 0;
  var volume = 1;
  var error = "";
  var seeking = false;
  var barUnsubscribe = null;
  var titleNode = null;
  var artistNode = null;
  var statusNode = null;
  var toggleNode = null;
  var seekNode = null;
  var elapsedNode = null;
  var totalNode = null;
  function formatPlayerTime(seconds) {
    if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
    const total = Math.floor(seconds);
    const secs = total % 60;
    const minutes = Math.floor(total / 60);
    if (minutes >= 60) {
      const hours = Math.floor(minutes / 60);
      const mins = minutes % 60;
      return `${hours}:${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
    }
    return `${minutes}:${String(secs).padStart(2, "0")}`;
  }
  function isTypingTarget(target) {
    if (!(target instanceof Element)) return false;
    if (target.closest("input, textarea, select")) return true;
    let current = target;
    while (current) {
      if (current instanceof HTMLElement) {
        const editable = contentEditableState(current);
        if (editable !== null) return editable;
      }
      current = current.parentElement;
    }
    return false;
  }
  function contentEditableState(element) {
    const attr = element.getAttribute("contenteditable");
    if (attr !== null) {
      const value = attr.toLowerCase();
      if (value === "false") return false;
      if (value === "true" || value === "" || value === "plaintext-only") return true;
    }
    const raw = element.contentEditable;
    const prop = typeof raw === "string" ? raw.toLowerCase() : "";
    if (prop === "true" || prop === "plaintext-only") return true;
    if (prop === "false") return false;
    return null;
  }
  function play(nextId) {
    if (!Number.isInteger(nextId) || nextId < 0) return;
    const element = ensureMedia();
    if (trackId !== nextId || element.src === "") {
      const row = state.byId.get(nextId);
      title = row?.name || row?.title || playerStrings.untitled;
      artist = row?.artist ?? "";
      trackId = nextId;
      currentTime = 0;
      duration = 0;
      element.src = trackUrl(nextId);
      element.currentTime = 0;
    }
    error = "";
    playing = true;
    emit();
    const pending = element.play();
    if (pending && typeof pending.then === "function") {
      pending.catch(() => {
        if (trackId !== nextId) return;
        playing = false;
        error = playerStrings.cannotPlay;
        emit();
      });
    }
  }
  function pause() {
    if (trackId === null) return;
    playing = false;
    ensureMedia().pause();
    emit();
  }
  function togglePlayPause() {
    if (trackId === null) return;
    if (playing) pause();
    else play(trackId);
  }
  function seek(seconds) {
    if (!Number.isFinite(seconds) || trackId === null) return;
    const element = ensureMedia();
    let next = seconds < 0 ? 0 : seconds;
    const limit = element.duration;
    if (Number.isFinite(limit) && limit > 0 && next > limit) next = limit;
    element.currentTime = next;
    currentTime = next;
    emit();
  }
  function getPlayerState() {
    return { trackId, title, artist, playing, currentTime, duration, volume, error };
  }
  function subscribe(listener) {
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  }
  function bindSpaceToggle() {
    const onKey = (event) => {
      if (event.key !== " " || event.repeat || event.ctrlKey || event.altKey || event.metaKey) return;
      if (event.defaultPrevented || isTypingTarget(event.target) || isActivationTarget(event.target)) return;
      if (isOpenDialog(event.target)) return;
      event.preventDefault();
      if (trackId === null) {
        const selected = selectedPlayableId();
        if (selected !== null) play(selected);
        return;
      }
      togglePlayPause();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }
  function mountPlayer(host) {
    barUnsubscribe?.();
    barUnsubscribe = null;
    resetPlayback();
    const root = host === void 0 ? document.getElementById("player-bar") : host;
    if (!root) return;
    root.classList.add("player-bar");
    root.setAttribute("role", "region");
    root.setAttribute("aria-label", playerStrings.region);
    const element = ensureMedia();
    root.replaceChildren();
    if (element instanceof Node) root.append(element);
    root.append(buildBar());
    barUnsubscribe = subscribe(() => paintBar());
    paintBar();
  }
  function resetPlayback() {
    trackId = null;
    title = "";
    artist = "";
    playing = false;
    currentTime = 0;
    duration = 0;
    error = "";
    seeking = false;
  }
  function ensureMedia() {
    if (media) return media;
    const audio = document.createElement("audio");
    audio.id = "player-audio";
    audio.preload = "none";
    audio.className = "player-audio";
    audio.volume = volume;
    media = audio;
    wire(audio);
    return audio;
  }
  function wire(element) {
    if (wired.has(element)) return;
    wired.add(element);
    element.addEventListener("play", () => {
      playing = true;
      emit();
    });
    element.addEventListener("pause", () => {
      playing = false;
      emit();
    });
    element.addEventListener("ended", () => {
      playing = false;
      currentTime = element.currentTime;
      emit();
    });
    element.addEventListener("timeupdate", () => {
      currentTime = element.currentTime;
      if (Number.isFinite(element.duration)) duration = element.duration;
      emit();
    });
    element.addEventListener("durationchange", () => {
      duration = Number.isFinite(element.duration) ? element.duration : 0;
      emit();
    });
    element.addEventListener("error", () => {
      playing = false;
      error = playerStrings.cannotPlay;
      emit();
    });
  }
  function trackUrl(nextId) {
    const params = new URLSearchParams({ id: String(nextId), space: state.space });
    return `/api/audio?${params.toString()}`;
  }
  function selectedPlayableId() {
    if (state.mode === "history") return null;
    const selected = state.selectedId;
    if (selected === null) return null;
    const row = state.byId.get(selected);
    if (!row || row.entry) return null;
    return row.id;
  }
  function isActivationTarget(target) {
    if (!(target instanceof Element)) return false;
    return target.closest("button, a, summary, [role='button']") !== null;
  }
  function isOpenDialog(target) {
    if (!(target instanceof Element)) return false;
    const dialog = target.closest("dialog");
    return dialog instanceof HTMLDialogElement && dialog.open;
  }
  function emit() {
    const snapshot = getPlayerState();
    for (const listener of [...listeners]) listener(snapshot);
  }
  function buildBar() {
    const meta = document.createElement("div");
    meta.className = "player-meta";
    titleNode = document.createElement("p");
    titleNode.className = "player-title";
    artistNode = document.createElement("p");
    artistNode.className = "player-artist";
    statusNode = document.createElement("p");
    statusNode.className = "player-status";
    statusNode.setAttribute("role", "status");
    meta.append(titleNode, artistNode, statusNode);
    toggleNode = document.createElement("button");
    toggleNode.type = "button";
    toggleNode.className = "player-toggle";
    toggleNode.addEventListener("click", () => togglePlayPause());
    const seekWrap = document.createElement("div");
    seekWrap.className = "player-seek";
    const elapsedWrap = document.createElement("span");
    elapsedWrap.className = "player-time";
    const elapsedLabel = document.createElement("span");
    elapsedLabel.className = "visually-hidden";
    elapsedLabel.textContent = playerStrings.elapsed;
    elapsedNode = document.createElement("span");
    elapsedWrap.append(elapsedLabel, elapsedNode);
    seekNode = document.createElement("input");
    seekNode.type = "range";
    seekNode.className = "player-range";
    seekNode.min = "0";
    seekNode.max = "0";
    seekNode.step = "0.1";
    seekNode.value = "0";
    seekNode.setAttribute("aria-label", playerStrings.seek);
    seekNode.addEventListener("pointerdown", () => {
      seeking = true;
    });
    const release = () => {
      seeking = false;
    };
    seekNode.addEventListener("pointerup", release);
    seekNode.addEventListener("pointercancel", release);
    seekNode.addEventListener("input", () => {
      if (!seekNode) return;
      seek(Number(seekNode.value));
    });
    const totalWrap = document.createElement("span");
    totalWrap.className = "player-time";
    const totalLabel = document.createElement("span");
    totalLabel.className = "visually-hidden";
    totalLabel.textContent = playerStrings.duration;
    totalNode = document.createElement("span");
    totalWrap.append(totalLabel, totalNode);
    seekWrap.append(elapsedWrap, seekNode, totalWrap);
    const volumeLabel = document.createElement("label");
    volumeLabel.className = "player-volume";
    const volumeText = document.createElement("span");
    volumeText.textContent = playerStrings.volume;
    const volumeInput = document.createElement("input");
    volumeInput.type = "range";
    volumeInput.min = "0";
    volumeInput.max = "1";
    volumeInput.step = "0.01";
    volumeInput.value = String(volume);
    volumeInput.addEventListener("input", () => {
      const next = Number(volumeInput.value);
      if (!Number.isFinite(next)) return;
      volume = Math.min(1, Math.max(0, next));
      ensureMedia().volume = volume;
      emit();
    });
    volumeLabel.append(volumeText, volumeInput);
    const bar = document.createElement("div");
    bar.className = "player-controls";
    bar.append(meta, toggleNode, seekWrap, volumeLabel);
    return bar;
  }
  function paintBar() {
    if (!titleNode || !artistNode || !statusNode || !toggleNode || !seekNode || !elapsedNode || !totalNode) return;
    const loaded = trackId !== null;
    titleNode.textContent = loaded ? title || playerStrings.untitled : playerStrings.nothingPlaying;
    artistNode.textContent = artist;
    artistNode.hidden = artist === "";
    statusNode.textContent = error;
    statusNode.hidden = error === "";
    toggleNode.textContent = playing ? playerStrings.pause : playerStrings.play;
    toggleNode.disabled = !loaded;
    toggleNode.setAttribute("aria-pressed", String(playing));
    const limit = Number.isFinite(duration) && duration > 0 ? duration : 0;
    seekNode.max = String(limit);
    seekNode.disabled = !loaded || limit === 0;
    if (!seeking) seekNode.value = String(Math.min(currentTime, limit || currentTime));
    elapsedNode.textContent = formatPlayerTime(currentTime);
    totalNode.textContent = formatPlayerTime(duration);
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
      const button = document.createElement("div");
      button.className = "row";
      button.setAttribute("role", "option");
      button.setAttribute("aria-selected", String(track.id === state.selectedId));
      button.dataset.id = String(track.id);
      const titleCell = document.createElement("span");
      titleCell.className = "cell";
      const line = document.createElement("span");
      line.className = "title-line";
      if (!track.entry) {
        const playingNow = getPlayerState();
        const playingThis = playingNow.trackId === track.id && playingNow.playing;
        const playButton = document.createElement("button");
        playButton.type = "button";
        playButton.className = "row-play";
        const labelName = track.name || playerStrings.untitled;
        playButton.setAttribute("aria-label", `${playerStrings.play} ${labelName}`);
        playButton.setAttribute("aria-pressed", String(playingThis));
        const icon = document.createElement("span");
        icon.className = "row-play-icon";
        icon.setAttribute("aria-hidden", "true");
        playButton.append(icon);
        playButton.addEventListener("click", (event) => {
          event.stopPropagation();
          bridge.selectTrack(track.id);
          play(track.id);
          el("list").focus({ preventScroll: true });
        });
        playButton.addEventListener("dblclick", (event) => event.stopPropagation());
        line.append(playButton);
      }
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
      const title2 = document.createElement("span");
      title2.className = "title";
      title2.textContent = track.name || "Untitled";
      line.append(title2);
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
      const artist2 = document.createElement("span");
      artist2.className = "cell";
      artist2.textContent = track.artist ?? "";
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
      button.append(titleCell, artist2, third, fourth, fifth);
      button.addEventListener("click", () => {
        if (track.entry) bridge.selectEntry(track.id);
        else bridge.selectTrack(track.id);
        el("list").focus({ preventScroll: true });
      });
      button.addEventListener("dblclick", () => {
        if (!track.entry) play(track.id);
      });
      rows.append(button);
    }
  }
  function moveTrackList(delta) {
    moveSelection(delta);
  }
  function openTrackList() {
    const view = state.view || [];
    const current = view.find((track) => track.id === state.selectedId) ?? view[0];
    if (!current) return;
    if (current.entry) bridge.selectEntry(current.id);
    else void bridge.selectTrack(current.id);
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
      } else if (event.key === "Enter") {
        const selected = state.view.find((item) => item.id === state.selectedId);
        if (!selected || selected.entry) return;
        event.preventDefault();
        play(selected.id);
      }
    });
    let paintedId = null;
    let paintedPlaying = false;
    subscribe((next) => {
      if (next.trackId === paintedId && next.playing === paintedPlaying) return;
      paintedId = next.trackId;
      paintedPlaying = next.playing;
      paintRows();
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
    const active2 = document.activeElement;
    const restore = el("crate-list").contains(active2) ? active2.closest(".crate-row")?.querySelector(".crate")?.dataset.id ?? null : null;
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
    const save2 = document.createElement("button");
    save2.type = "button";
    save2.className = "text-button";
    save2.textContent = "Save rules";
    save2.disabled = !state.writable;
    save2.addEventListener("click", () => saveRules(crate.id, area.value));
    editor.append(area, save2);
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
    el("browser").hidden = filesMode || snapshotsMode;
    el("track-splitter").hidden = filesMode || snapshotsMode;
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
      if (state.filesAtRoots) {
        el("crate-foot").textContent = state.filesLoading ? "Reading music folders" : `${state.filesRoots.length.toLocaleString()} music folders`;
        return;
      }
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
    }).catch((error2) => {
      if (failureOf(error2).status === 409) lockDown(error2);
      else setNotice(failureOf(error2).message);
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
    } catch (error2) {
      if (token !== state.request) return;
      const failure = document.createElement("p");
      failure.className = "detail-error";
      failure.textContent = failureOf(error2).message;
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
    const title2 = document.createElement("h2");
    title2.textContent = entry.name || "Untitled";
    body.append(title2);
    if (entry.artist) {
      const artist2 = document.createElement("p");
      artist2.className = "artist";
      artist2.textContent = entry.artist;
      body.append(artist2);
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
    const title2 = document.createElement("h2");
    title2.textContent = track.title ?? "";
    body.append(title2);
    if (track.artist) {
      const artist2 = document.createElement("p");
      artist2.className = "artist";
      artist2.textContent = track.artist ?? "";
      body.append(artist2);
    }
    const playButton = document.createElement("button");
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
    const save2 = document.createElement("button");
    save2.type = "submit";
    save2.className = "text-button wide";
    save2.textContent = "Save track";
    form.append(save2);
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
        bridge.openMergeDialog().catch((error2) => setNotice(failureOf(error2).message));
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
    for (const copy2 of copies) {
      const row = document.createElement("div");
      row.className = "copy-row";
      const button = document.createElement("button");
      button.type = "button";
      button.className = "text-button";
      button.textContent = copy2.file || `Track ${copy2.id}`;
      button.addEventListener("click", () => selectTrack(copy2.id));
      const rate = document.createElement("span");
      rate.textContent = copy2.bitrate == null ? "" : String(copy2.bitrate);
      const plays = document.createElement("span");
      plays.textContent = copy2.play_count == null ? "" : String(copy2.play_count);
      const crates = document.createElement("span");
      crates.textContent = copy2.missing ? "missing" : copy2.crates || "";
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
    } catch (error2) {
      if (token !== relatedRequest || !section.isConnected) return;
      section.setAttribute("aria-busy", "false");
      const status = section.querySelector("[role=status]");
      if (status) status.textContent = failureOf(error2).message;
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
    const paint3 = () => {
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
      const hits2 = state.tracks.filter((item) => item.id !== track.id && matchesQuery(item, terms)).slice(0, 8);
      if (!hits2.length) {
        const empty = document.createElement("li");
        empty.className = "related-meta";
        empty.textContent = "No tracks match.";
        results.append(empty);
        return;
      }
      for (const hit of hits2) {
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
    input.addEventListener("input", paint3);
    paint3();
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
    const save2 = document.createElement("button");
    save2.type = "button";
    save2.className = "text-button";
    save2.textContent = "Save link";
    save2.addEventListener("click", () => {
      save2.disabled = true;
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
    form.append(chosen, noteLabel, ratingLabel, mutualLabel, save2);
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
      const save2 = document.createElement("button");
      save2.type = "button";
      save2.className = "text-button";
      save2.textContent = "Save";
      save2.setAttribute("aria-label", `Save link to ${item.title || "Untitled"}`);
      save2.addEventListener("click", () => {
        save2.disabled = true;
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
      row.append(main, save2);
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
    } catch (error2) {
      if (failureOf(error2).status === 409) lockDown(error2);
      else setNotice(failureOf(error2).message);
      const status = section.querySelector("[role=status]");
      if (status) status.textContent = failureOf(error2).message;
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
    } catch (error2) {
      setNotice(failureOf(error2).message);
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
    } catch (error2) {
      if (failureOf(error2).status === 409) {
        lockDown(error2);
        if (button) button.disabled = true;
      } else {
        setNotice(failureOf(error2).message);
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
  function lockDown(error2) {
    const failed = failureOf(error2);
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
    } catch (error2) {
      if (failureOf(error2).status === 409) lockDown(error2);
      else setNotice(failureOf(error2).message);
    }
  }
  async function revealTrack(id) {
    try {
      await postJSON("/api/reveal", { id });
    } catch (error2) {
      setNotice(failureOf(error2).message);
    }
  }
  async function prepareTrack(id, add) {
    try {
      const result = await postJSON("/api/crate", { action: "prepare", asset: id, add, space: state.space });
      setNotice(result.warning || (add ? "Sent to Prepare." : "Removed from Prepare."));
      await loadLibrary();
      selectTrack(id);
    } catch (error2) {
      if (failureOf(error2).status === 409) lockDown(error2);
      else setNotice(failureOf(error2).message);
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
    } catch (error2) {
      if (failureOf(error2).status === 409) lockDown(error2);
      else setNotice(failureOf(error2).message);
    }
  }
  async function removeTrack(id) {
    if (!confirm("Remove this track from the library? The audio file stays on disk.")) return;
    try {
      const result = await postJSON("/api/crate", { action: "remove_library", asset: id, space: state.space });
      setNotice(result.warning || "Removed from the library.");
      state.selectedId = null;
      await loadLibrary();
    } catch (error2) {
      if (failureOf(error2).status === 409) lockDown(error2);
      else setNotice(failureOf(error2).message);
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
    } catch (error2) {
      input.checked = !add;
      if (failureOf(error2).status === 409) lockDown(error2);
      else setNotice(failureOf(error2).message);
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
    } catch (error2) {
      if (failureOf(error2).status === 409) lockDown(error2);
      else setNotice(failureOf(error2).message);
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
    } catch (error2) {
      if (failureOf(error2).status === 409) lockDown(error2);
      else setNotice(failureOf(error2).message);
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
    } catch (error2) {
      if (failureOf(error2).status === 409) lockDown(error2);
      else setNotice(failureOf(error2).message);
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
    } catch (error2) {
      if (failureOf(error2).status === 409) lockDown(error2);
      else setNotice(failureOf(error2).message);
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
    } catch (error2) {
      if (failureOf(error2).status === 409) lockDown(error2);
      else setNotice(failureOf(error2).message);
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
    } catch (error2) {
      if (failureOf(error2).status === 409) lockDown(error2);
      else setNotice(failureOf(error2).message);
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
    const active2 = state.activeCrate;
    state.tracks = library.tracks;
    state.byId = new Map(library.tracks.map((track) => [track.id, track]));
    state.crates = library.crates;
    state.rootId = library.root_id;
    state.crateTracks = new Map(library.crates.map((crate) => [crate.id, new Set(crate.tracks)]));
    state.expanded = new Set(library.crates.filter((crate) => crate.expanded).map((crate) => crate.id));
    state.activeCrate = active2 === "all" || library.crates.some((crate) => crate.id === active2) ? active2 : "all";
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
      if (!state.historySessions.length) loadHistory().catch((error2) => setNotice(failureOf(error2).message));
    } else if (state.sort === "start" || state.sort === "deck" || state.sort === "played") {
      state.sort = "name";
      state.sortDir = 1;
    }
    if (mode === "duplicates" && state.duplicateSpace !== state.space) {
      loadDuplicates().catch((error2) => setNotice(failureOf(error2).message));
    }
    if (mode === "files") {
      state.filesLoading = true;
      const path = state.filesAtRoots ? "" : state.filesPath || "";
      loadFolder(path, { elsewhere: state.filesElsewhere && !state.filesAtRoots }).catch((error2) => failFiles(error2));
    }
    if (mode === "snapshots") {
      loadSnapshots().catch((error2) => failSnapshots(error2));
    }
    renderList();
  }
  function showFailure(error2) {
    el("count").textContent = "Library unavailable";
    const failure = document.createElement("p");
    failure.className = "detail-error";
    failure.textContent = failureOf(error2).message;
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
  function failFiles(error2) {
    state.filesLoading = false;
    state.filesError = failureOf(error2).message || "That folder could not be read.";
    renderFiles();
  }
  var filesRequest = 0;
  var FILES_SEARCH_MS = 200;
  var filesSearchTimer = 0;
  var FILE_OVERSCAN = 8;
  async function loadFolder(path, options = {}) {
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
    state.filesSelected = /* @__PURE__ */ new Set();
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
    const payload = await readJSONOr(response, {});
    if (token !== filesRequest) return;
    if (!response.ok) throw new Error(payload.error || "That folder could not be read.");
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
  async function searchFiles(query) {
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
    const payload = await readJSONOr(response, {});
    if (token !== filesRequest) return;
    if (!response.ok) throw new Error(payload.error || "Files could not be searched.");
    const entries = Array.isArray(payload.entries) ? payload.entries.filter(isListedFile) : [];
    state.filesEntries = entries;
    state.filesTruncated = Boolean(payload.truncated);
    state.filesLoading = false;
    state.filesSearching = true;
    state.filesActive = 0;
    state.filesSelected = /* @__PURE__ */ new Set();
    el("files-list").scrollTop = 0;
    renderFiles();
  }
  function isListedFile(value) {
    if (!value || typeof value !== "object") return false;
    const row = value;
    return typeof row.name === "string" && typeof row.path === "string" && typeof row.kind === "string";
  }
  function renderFiles() {
    if (state.mode !== "files") return;
    const pick = el("files-pick");
    const moveHere = el("files-move-here");
    const pickCancel = el("files-pick-cancel");
    pick.hidden = !state.filesPick;
    moveHere.hidden = !state.filesPick;
    pickCancel.hidden = !state.filesPick;
    renderBreadcrumb();
    const elsewhere = el("files-elsewhere");
    elsewhere.textContent = state.filesElsewhere ? "Music folders" : "Browse elsewhere…";
    el("files-up").disabled = !state.filesParent || state.filesLoading;
    const notes = [];
    if (state.filesLoading) notes.push(state.filesAtRoots ? "Reading music folders." : "Reading this folder.");
    if (state.filesError) notes.push(state.filesError);
    if (state.filesMessage) notes.push(state.filesMessage);
    if (state.filesTruncated) notes.push(state.filesSearching ? copy.filesTruncated : "Some files are not listed.");
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
  function renderBreadcrumb() {
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
        button.type = "button";
        button.className = "files-crumb";
        button.textContent = crumb.name;
        button.addEventListener("click", () => {
          loadFolder(crumb.path, { elsewhere: state.filesElsewhere }).catch((error2) => failFiles(error2));
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
  function visibleCrumbs() {
    if (state.filesBreadcrumb.length) return state.filesBreadcrumb;
    if (state.filesAtRoots) return [{ name: "Music folders", path: "" }];
    if (state.filesPath) return [{ name: state.filesPath, path: state.filesPath }];
    return [{ name: "Music folders", path: "" }];
  }
  function filesRowHeight() {
    if (state.filesSearching) return FILE_ROW;
    return state.filesAtRoots ? ROOT_ROW : FILE_ROW;
  }
  function browserRows() {
    if (state.filesSearching) return state.filesEntries;
    if (state.filesAtRoots) {
      return state.filesRoots.map((root) => {
        const entry = {
          name: root.label,
          path: root.path,
          detail: root.detail,
          kind: root.kind === "serato_drive" ? "drive" : "folder",
          missing: root.missing
        };
        return entry;
      });
    }
    const rank = { dir: 0, file: 1, link: 2 };
    return [...state.filesEntries].sort((left, right) => {
      return (rank[left.kind] ?? 3) - (rank[right.kind] ?? 3) || left.name.localeCompare(right.name, void 0, { numeric: true, sensitivity: "base" });
    });
  }
  function paintFileWindow() {
    const list = el("files-list");
    const rows2 = browserRows();
    list.setAttribute("aria-busy", String(state.filesLoading));
    list.setAttribute(
      "aria-label",
      state.filesSearching ? copy.filesSearchResults : state.filesAtRoots ? "Music folders" : "Folder contents"
    );
    if (state.filesLoading && !rows2.length) {
      const reading = state.filesSearching ? copy.filesSearching : state.filesAtRoots ? "Reading music folders." : "Reading this folder.";
      list.replaceChildren(fileNote(reading));
      list.tabIndex = 0;
      return;
    }
    if (state.filesError && !rows2.length) {
      list.replaceChildren(fileNote(state.filesError));
      list.tabIndex = 0;
      return;
    }
    if (state.filesAtRoots && !state.filesRoots.length) {
      list.replaceChildren(rootsEmpty());
      list.tabIndex = -1;
      return;
    }
    if (!rows2.length) {
      const empty = state.filesSearching ? fill(copy.filesNoMatches, { query: state.filesQuery }) : "This folder is empty.";
      list.replaceChildren(fileNote(empty));
      list.tabIndex = 0;
      return;
    }
    list.tabIndex = -1;
    if (state.filesActive >= rows2.length) state.filesActive = rows2.length - 1;
    if (state.filesActive < 0) state.filesActive = 0;
    const rowHeight = filesRowHeight();
    const view = list.clientHeight || 600;
    const maxScroll = Math.max(0, rows2.length * rowHeight - view);
    const scrollTop = Math.min(Math.max(0, list.scrollTop), maxScroll);
    const start = Math.max(0, Math.floor(scrollTop / rowHeight) - FILE_OVERSCAN);
    const end = Math.min(rows2.length, Math.ceil((scrollTop + view) / rowHeight) + FILE_OVERSCAN);
    const spacer2 = fileSpacer(list);
    const windowEl = spacer2.querySelector(".files-window");
    if (!windowEl) return;
    spacer2.style.height = `${rows2.length * rowHeight}px`;
    windowEl.style.transform = `translateY(${start * rowHeight}px)`;
    windowEl.replaceChildren();
    for (let index = start; index < end; index += 1) {
      const entry = rows2[index];
      if (entry) windowEl.append(fileRow(entry, index));
    }
    if (state.filesActive >= start && state.filesActive < end) {
      list.setAttribute("aria-activedescendant", `files-item-${state.filesActive}`);
    } else list.removeAttribute("aria-activedescendant");
  }
  function fileSpacer(list) {
    const first = list.firstElementChild;
    if (first instanceof HTMLDivElement && first.classList.contains("files-spacer") && list.childElementCount === 1) {
      return first;
    }
    list.replaceChildren();
    const spacer2 = document.createElement("div");
    spacer2.className = "files-spacer";
    const windowEl = document.createElement("div");
    windowEl.className = "files-window";
    spacer2.append(windowEl);
    list.append(spacer2);
    return spacer2;
  }
  function fileNote(text) {
    const note = document.createElement("p");
    note.className = "files-empty";
    note.textContent = text;
    return note;
  }
  function rootsEmpty() {
    const box = document.createElement("div");
    box.className = "files-empty-state";
    const heading = document.createElement("h2");
    heading.textContent = "No music folders yet";
    const copy2 = document.createElement("p");
    copy2.textContent = "Setup finds the folders Serato uses for your music.";
    const button = document.createElement("button");
    button.type = "button";
    button.id = "files-run-setup";
    button.className = "files-primary";
    button.textContent = "Run setup";
    button.addEventListener("click", () => bridge.openSetup());
    box.append(heading, copy2, button);
    return box;
  }
  function focusFilesIndex(index) {
    const rows2 = browserRows();
    if (!rows2.length) return;
    state.filesActive = Math.max(0, Math.min(rows2.length - 1, index));
    const list = el("files-list");
    const rowHeight = filesRowHeight();
    const view = list.clientHeight || 600;
    const top = state.filesActive * rowHeight;
    const maxScroll = Math.max(0, rows2.length * rowHeight - view);
    if (top < list.scrollTop) list.scrollTop = top;
    if (top + rowHeight > list.scrollTop + view) list.scrollTop = Math.min(maxScroll, top + rowHeight - view);
    paintFileWindow();
    const control = list.querySelector(`[data-files-index="${state.filesActive}"]`);
    control?.focus();
  }
  function activateFilesIndex(index) {
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
  function openBrowserRow(entry) {
    if (entry.missing) return;
    const elsewhere = state.filesElsewhere && entry.kind === "dir";
    loadFolder(entry.path, { elsewhere }).catch((error2) => failFiles(error2));
  }
  function onFilesKey(event) {
    if (state.mode !== "files") return;
    const list = el("files-list");
    if (!(event.target instanceof Node) || !list.contains(event.target)) return;
    const rows2 = browserRows();
    if (!rows2.length) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp" || event.key === "Home" || event.key === "End") {
      event.preventDefault();
      if (event.key === "ArrowDown") focusFilesIndex(state.filesActive + 1);
      else if (event.key === "ArrowUp") focusFilesIndex(state.filesActive - 1);
      else if (event.key === "Home") focusFilesIndex(0);
      else focusFilesIndex(rows2.length - 1);
      return;
    }
    if (event.key !== "Enter" && event.key !== " ") return;
    const control = event.target instanceof HTMLElement ? event.target.closest("button, input") : null;
    if (control && list.contains(control)) return;
    event.preventDefault();
    activateFilesIndex(state.filesActive);
  }
  function fileRow(entry, index) {
    const row = document.createElement("div");
    row.className = "files-row";
    if (entry.detail && (entry.kind === "folder" || entry.kind === "drive")) row.classList.add("is-root");
    if (entry.missing) row.classList.add("is-missing");
    if (index === state.filesActive) row.classList.add("is-active");
    row.setAttribute("role", "listitem");
    const openKind = entry.kind === "dir" || entry.kind === "folder" || entry.kind === "drive";
    if (openKind) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "files-open";
      button.dataset.filesIndex = String(index);
      button.id = `files-item-${index}`;
      button.tabIndex = index === state.filesActive ? 0 : -1;
      if (entry.kind === "drive" || entry.kind === "folder") button.append(fileIcon(entry.kind === "drive" ? "drive" : "folder"));
      if (entry.detail && (entry.kind === "folder" || entry.kind === "drive")) {
        const copy2 = document.createElement("span");
        copy2.className = "files-root-copy";
        const label2 = document.createElement("span");
        label2.className = "files-root-label";
        label2.textContent = entry.name;
        const detail = document.createElement("span");
        detail.className = "files-root-detail";
        detail.textContent = entry.detail;
        copy2.append(label2, detail);
        button.append(copy2);
      } else {
        const name2 = document.createElement("span");
        name2.textContent = entry.name;
        button.append(name2);
        if (entry.detail) {
          const detail = document.createElement("span");
          detail.className = "files-match-detail";
          detail.textContent = entry.detail;
          button.append(detail);
        }
      }
      button.title = entry.detail ? `${entry.name} ${entry.detail}` : entry.name;
      if (entry.missing) {
        button.setAttribute("aria-disabled", "true");
        button.setAttribute("aria-label", `${entry.name}, Drive not connected`);
        const badge = document.createElement("span");
        badge.className = "files-badge";
        badge.textContent = "Drive not connected";
        button.append(badge);
        button.addEventListener("click", () => {
          state.filesActive = index;
        });
      } else {
        button.setAttribute("aria-label", `Open ${entry.name}`);
        button.addEventListener("click", () => {
          state.filesActive = index;
          openBrowserRow(entry);
        });
      }
      row.append(button);
      return row;
    }
    if (entry.kind !== "file") {
      const label2 = document.createElement("button");
      label2.type = "button";
      label2.className = "files-kind";
      label2.dataset.filesIndex = String(index);
      label2.id = `files-item-${index}`;
      label2.tabIndex = index === state.filesActive ? 0 : -1;
      label2.textContent = `${entry.name} (shortcut)`;
      label2.setAttribute("aria-label", `${entry.name} shortcut`);
      row.append(label2);
      return row;
    }
    const label = document.createElement("label");
    label.className = "files-file";
    const box = document.createElement("input");
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
    name.title = entry.path || entry.name;
    label.append(box, name);
    if (entry.detail) {
      const detail = document.createElement("span");
      detail.className = "files-match-detail";
      detail.textContent = entry.detail;
      detail.title = entry.detail;
      label.append(detail);
    }
    if (entry.in_library) {
      const badge = document.createElement("span");
      badge.className = "files-badge";
      badge.textContent = "In library";
      label.append(badge);
    }
    row.append(label);
    return row;
  }
  function fileIcon(kind) {
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
      kind === "drive" ? "M5 8.5h14v8H5z M8 14.5h.01 M12 14.5h4" : "M4 8.5h6l2 2h8v7.5H4z"
    );
    svg.append(path);
    return svg;
  }
  function isFileRoot(value) {
    if (!value || typeof value !== "object") return false;
    const record = value;
    return typeof record.name === "string" && typeof record.path === "string" && typeof record.kind === "string";
  }
  function isFileCrumb(value) {
    if (!value || typeof value !== "object") return false;
    const record = value;
    return typeof record.name === "string" && typeof record.path === "string";
  }
  function moveFileList(delta) {
    if (!browserRows().length) return;
    focusFilesIndex(state.filesActive + delta);
  }
  function openFileList() {
    if (!browserRows().length) return;
    activateFilesIndex(state.filesActive);
  }
  function focusFileByPath(path) {
    const index = browserRows().findIndex((entry) => entry.path === path);
    if (index < 0) return;
    focusFilesIndex(index);
  }
  function selectedFiles() {
    return state.filesEntries.filter((entry) => entry.kind === "file" && state.filesSelected.has(entry.path));
  }
  function wireLibrary() {
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
      if (file) importPlaylist(file).catch((error2) => setNotice(failureOf(error2).message));
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
    el("crate-new").addEventListener("click", () => createCrate().catch((error2) => setNotice(failureOf(error2).message)));
    el("crate-rename").addEventListener("click", () => renameCrate().catch((error2) => setNotice(failureOf(error2).message)));
    el("crate-color").addEventListener("click", () => colorCrate().catch((error2) => setNotice(failureOf(error2).message)));
    el("crate-delete").addEventListener("click", () => deleteCrate().catch((error2) => setNotice(failureOf(error2).message)));
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

  // src/layout.ts
  var TRACK_LIST_MIN_WIDTH = 360;
  var DETAIL_MIN_WIDTH = 300;
  var SAVE_DELAY_MS = 400;
  var splitter = null;
  var changedHere = false;
  var saveTimer;
  function save(width) {
    changedHere = true;
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
      postJSON("/api/settings", { layout: { track_list_width: width } }).catch(() => {
        setNotice("Couldn't save the pane width. It goes back to the last saved width next time.");
      });
    }, SAVE_DELAY_MS);
  }
  function wireLayout() {
    splitter = mountSplitter({
      handle: el("track-splitter"),
      container: el("browser").parentElement,
      first: el("browser"),
      property: "--track-list-width",
      minFirst: TRACK_LIST_MIN_WIDTH,
      minSecond: DETAIL_MIN_WIDTH,
      onCommit: save
    });
    window.addEventListener("resize", () => splitter?.refit());
  }
  function applyLayout(payload) {
    if (!splitter || changedHere) return;
    const width = payload.layout?.track_list_width;
    splitter.set(typeof width === "number" ? width : null);
  }

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
    const hotLoops = el("rekordbox-hot-loops").checked ? "1" : "0";
    const key = el("rekordbox-key").value;
    const base = `/api/export.rekordbox.xml?space=${encodeURIComponent(state.space)}&crate=${encodeURIComponent(crate)}&memory=${memory}&hot_loops=${hotLoops}&key=${encodeURIComponent(key)}`;
    return report ? `${base}&report=1` : base;
  }
  var rekordboxToken = 0;
  function applyRekordboxExport(payload) {
    const section = payload.rekordbox;
    if (section == null) return;
    if (typeof section.hot_loops === "boolean") {
      el("rekordbox-hot-loops").checked = section.hot_loops;
    }
    if (typeof section.memory_cues === "boolean") {
      el("rekordbox-memory").checked = section.memory_cues;
    }
    if (section.key_notation === "asis" || section.key_notation === "camelot" || section.key_notation === "classical") {
      el("rekordbox-key").value = section.key_notation;
    }
  }
  async function saveRekordboxExport() {
    const key = el("rekordbox-key").value;
    const notation = key === "camelot" || key === "classical" ? key : "asis";
    const token = ++rekordboxToken;
    try {
      const payload = await postJSON("/api/settings", {
        rekordbox: {
          hot_loops: el("rekordbox-hot-loops").checked,
          memory_cues: el("rekordbox-memory").checked,
          key_notation: notation
        }
      });
      if (token === rekordboxToken) applyRekordboxExport(payload);
    } catch {
    }
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
    } catch (error2) {
      if (token !== mergeToken) return;
      mergePreview = null;
      el("merge-preview").replaceChildren();
      const failed = document.createElement("p");
      failed.textContent = "The preview could not be read.";
      el("merge-preview").append(failed);
      el("merge-status").textContent = failureOf(error2).message;
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
        if (input.checked) refreshMergePreview().catch((error2) => setNotice(failureOf(error2).message));
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
    } catch (error2) {
      el("merge-status").textContent = failureOf(error2).message;
      if (failureOf(error2).status === 409) {
        lockDown(error2);
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
    state.wizardComplete = payload.wizard_complete === true;
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
    } catch (error2) {
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
  function openWizard(force, returnFocus3) {
    const wizard = globalThis.SeratoWizard;
    if (!wizard || typeof wizard.open !== "function") return false;
    const options = {
      force,
      returnFocus: returnFocus3,
      onSettings(payload) {
        applyPrivacy(payload);
      },
      onStatus(info) {
        applyStatus({
          message: info.message,
          writable: info.writable,
          open: info.open
        });
      }
    };
    wizard.open(options);
    return true;
  }
  async function loadPrivacy() {
    const token = rekordboxToken;
    const response = await fetch("/api/settings");
    const payload = await readJSONOr(response, {});
    if (!response.ok) throw new Error(payload.error || "Couldn't load sharing settings.");
    applyPrivacy(payload);
    applyLayout(payload);
    if (token === rekordboxToken) applyRekordboxExport(payload);
    if (!state.wizardComplete && openWizard(false, el("search"))) return;
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
      reviewFiles().catch((error2) => {
        el("files-dialog-status").textContent = failureOf(error2).message;
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
    } catch (error2) {
      if (failureOf(error2).status === 409) lockDown(error2);
      el("files-dialog-status").textContent = failureOf(error2).message;
      confirm2.disabled = false;
    }
  }
  function wireDialogs() {
    const saveExportBar = () => {
      saveRekordboxExport().catch(() => {
      });
    };
    el("rekordbox-hot-loops").addEventListener("change", saveExportBar);
    el("rekordbox-memory").addEventListener("change", saveExportBar);
    el("rekordbox-key").addEventListener("change", saveExportBar);
    loadPrivacy().catch((error2) => {
      setNotice(failureOf(error2).message || "Couldn't load sharing settings. Nothing is sent.");
    });
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
      }).catch((error2) => setNotice(failureOf(error2).message));
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
      openMergeDialog().catch((error2) => setNotice(failureOf(error2).message));
    });
    el("merge-cancel").addEventListener("click", () => el("merge-dialog").close());
    el("merge-confirm").addEventListener("click", () => {
      confirmMerge().catch((error2) => setNotice(failureOf(error2).message));
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
    el("rerun-wizard").addEventListener("click", () => {
      el("settings-dialog").close();
      openWizard(true, el("open-settings"));
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
          } catch (error2) {
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
      } catch (error2) {
        el("settings-status").textContent = "Couldn't copy the logs.";
      } finally {
        button.disabled = false;
      }
    });
    el("files-up").addEventListener("click", () => {
      if (state.filesParent) {
        loadFolder(state.filesParent, { elsewhere: state.filesElsewhere }).catch((error2) => failFiles(error2));
      }
    });
    el("files-refresh").addEventListener("click", () => {
      const path = state.filesAtRoots ? "" : state.filesPath;
      loadFolder(path, { elsewhere: state.filesElsewhere && !state.filesAtRoots, refresh: true }).catch((error2) => failFiles(error2));
    });
    el("files-elsewhere").addEventListener("click", () => {
      if (state.filesElsewhere) loadFolder("").catch((error2) => failFiles(error2));
      else loadFolder("", { elsewhere: true }).catch((error2) => failFiles(error2));
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
      reviewFiles().catch((error2) => {
        el("files-dialog-status").textContent = failureOf(error2).message;
      });
    });
    el("files-confirm").addEventListener("click", () => {
      confirmFiles().catch((error2) => {
        el("files-dialog-status").textContent = failureOf(error2).message;
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
  function openSetup() {
    const trigger = document.getElementById("files-run-setup");
    openWizard(true, trigger instanceof HTMLElement ? trigger : el("search"));
  }
  bridge.openSetup = openSetup;

  // src/fuzzy.ts
  var BOUNDARY = /[ ._/\-\\]/;
  function fuzzyScore(needle, haystack) {
    const query = needle.toLocaleLowerCase();
    const text = haystack.toLocaleLowerCase();
    if (!query) return null;
    let score = 0;
    let previous = -2;
    let from = 0;
    for (const letter of query) {
      const found = text.indexOf(letter, from);
      if (found < 0) return null;
      score += 8;
      if (found === previous + 1) score += 16;
      if (found === 0 || BOUNDARY.test(text.charAt(found - 1))) score += 12;
      previous = found;
      from = found + 1;
    }
    if (text.includes(query)) score += 40;
    if (text.startsWith(query)) score += 30;
    score -= Math.floor(Math.max(0, text.length - query.length) / 4);
    return score;
  }
  function scoreQuery(query, name, parentName = "") {
    const terms = query.trim().split(/\s+/).filter(Boolean);
    if (!terms.length) return null;
    let total = 0;
    for (const term of terms) {
      const nameScore = fuzzyScore(term, name);
      if (nameScore != null) {
        total += nameScore + 20;
        continue;
      }
      if (!parentName) return null;
      const parentScore = fuzzyScore(term, parentName);
      if (parentScore == null) return null;
      total += parentScore;
    }
    return total;
  }

  // src/quick-open.ts
  var QUICK_OPEN_MS = 200;
  var LIMIT = 8;
  var returnFocus = null;
  var timer = 0;
  var requestToken = 0;
  var hits = [];
  var active = 0;
  var phase = "idle";
  var truncated = false;
  var pendingQuery = "";
  function parentDirectory(path) {
    const slash = Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\"));
    if (slash < 0) return path;
    const parent = path.slice(0, slash);
    if (/^[A-Za-z]:$/.test(parent)) return `${parent}\\`;
    if (parent === "") return path.slice(0, slash + 1);
    return parent;
  }
  function quickOpenIsOpen() {
    return el("quick-open").open;
  }
  function openQuickOpen() {
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
  function closeQuickOpen() {
    const dialog = el("quick-open");
    if (dialog.open) dialog.close();
  }
  function wireQuickOpen() {
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
  function onDialogKey(event) {
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
  function schedule() {
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
  async function loadFiles(query, tracks) {
    const token = ++requestToken;
    phase = "loading";
    try {
      const response = await fetch(`/api/files?q=${encodeURIComponent(query)}`);
      const payload = await readJSONOr(response, {});
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
  function trackHits(query) {
    const text = query.trim();
    if (!text) return [];
    const found = [];
    for (const track of state.tracks) {
      const hit = scoreTrack(track, text);
      if (hit) found.push(hit);
    }
    found.sort(byScore);
    return found.slice(0, LIMIT);
  }
  function scoreTrack(track, query) {
    const title = track.name || "Untitled";
    const artist = track.artist ?? "";
    const album = track.album ?? "";
    const file = track.file ?? "";
    const score = scoreQuery(query, `${title} ${artist} ${album} ${file}`);
    if (score == null) return null;
    const detail = [artist, album].filter((part) => part !== "").join(" · ");
    return { kind: "track", key: `track:${track.id}`, title, detail, score, trackId: track.id };
  }
  function fileHits(payload) {
    const rows2 = Array.isArray(payload.entries) ? payload.entries : [];
    const found = [];
    for (const entry of rows2) {
      if (!isFileEntry(entry)) continue;
      const score = typeof entry.score === "number" ? entry.score : 0;
      found.push({
        kind: "file",
        key: `file:${entry.path}`,
        title: entry.name,
        detail: entry.detail || entry.path,
        score,
        path: entry.path
      });
    }
    found.sort(byScore);
    return found.slice(0, LIMIT);
  }
  function isFileEntry(value) {
    if (!value || typeof value !== "object") return false;
    const row = value;
    return typeof row.name === "string" && typeof row.path === "string" && typeof row.kind === "string";
  }
  function mergeHits(tracks, files) {
    return [...tracks, ...files].sort(byScore).slice(0, LIMIT * 2);
  }
  function byScore(left, right) {
    return right.score - left.score || left.title.localeCompare(right.title);
  }
  async function activate(hit) {
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
  function paint() {
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
      detail.title = hit.detail;
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
    const chosen = list.querySelector(".is-active");
    if (chosen && typeof chosen.scrollIntoView === "function") chosen.scrollIntoView({ block: "nearest" });
  }

  // src/shortcuts.ts
  var SEEK_SECONDS = 5;
  var SHORTCUT_DEFS = [
    {
      id: "focus-search",
      label: "Focus search",
      group: "Find",
      keys: [{ key: "f", mod: true }, { key: "/" }],
      whileTyping: false
    },
    {
      id: "quick-open",
      label: "Find a track or file",
      group: "Find",
      keys: [{ key: "k", mod: true }],
      whileTyping: false
    },
    {
      id: "dismiss",
      label: "Close or clear search",
      group: "Find",
      keys: [{ key: "Escape" }],
      whileTyping: true
    },
    {
      id: "cheat-sheet",
      label: "Show shortcuts",
      group: "Find",
      keys: [{ key: "?" }],
      whileTyping: false
    },
    {
      id: "list-previous",
      label: "Previous row",
      group: "Lists",
      keys: [{ key: "ArrowUp" }],
      whileTyping: false
    },
    {
      id: "list-next",
      label: "Next row",
      group: "Lists",
      keys: [{ key: "ArrowDown" }],
      whileTyping: false
    },
    {
      id: "list-open",
      label: "Open the row",
      group: "Lists",
      keys: [{ key: "Enter" }],
      whileTyping: false
    },
    {
      id: "play-pause",
      label: "Play or pause",
      group: "Play",
      keys: [{ key: " " }],
      whileTyping: false
    },
    {
      id: "seek-back",
      label: "Back 5 seconds",
      group: "Play",
      keys: [{ key: "ArrowLeft" }],
      whileTyping: false
    },
    {
      id: "seek-forward",
      label: "Forward 5 seconds",
      group: "Play",
      keys: [{ key: "ArrowRight" }],
      whileTyping: false
    },
    {
      id: "view-library",
      label: "Library",
      group: "Views",
      keys: [{ key: "1", mod: true }],
      whileTyping: false
    },
    {
      id: "view-crates",
      label: "Crates",
      group: "Views",
      keys: [{ key: "2", mod: true }],
      whileTyping: false
    },
    {
      id: "view-files",
      label: "Files",
      group: "Views",
      keys: [{ key: "3", mod: true }],
      whileTyping: false
    },
    {
      id: "view-history",
      label: "History",
      group: "Views",
      keys: [{ key: "4", mod: true }],
      whileTyping: false
    },
    {
      id: "view-snapshots",
      label: "Snapshots",
      group: "Views",
      keys: [{ key: "5", mod: true }],
      whileTyping: false
    }
  ];
  var SHORTCUTS = SHORTCUT_DEFS;
  var player = null;
  var returnFocus2 = null;
  var snapshotCursor = 0;
  function chordMatches(chord, event) {
    if (event.altKey) return false;
    const mod = event.ctrlKey || event.metaKey;
    if (mod !== Boolean(chord.mod)) return false;
    if (chord.key === "?") return event.key === "?" && !mod;
    if (event.shiftKey !== Boolean(chord.shift)) return false;
    if (chord.key === " ") return event.key === " ";
    return event.key === chord.key || event.key.toLowerCase() === chord.key.toLowerCase();
  }
  function matchShortcut(event) {
    for (const shortcut of SHORTCUTS) {
      if (shortcut.keys.some((chord) => chordMatches(chord, event))) return shortcut;
    }
    return null;
  }
  function chordLabel(chord) {
    const names = {
      Escape: "Esc",
      " ": "Space",
      ArrowLeft: "Left arrow",
      ArrowRight: "Right arrow",
      ArrowUp: "Up arrow",
      ArrowDown: "Down arrow",
      Enter: "Enter"
    };
    const named = names[chord.key];
    if (named) return named;
    const key = chord.key.length === 1 ? chord.key.toUpperCase() : chord.key;
    return chord.mod ? `Ctrl/Cmd+${key}` : key;
  }
  function isTypingTarget(target) {
    if (!(target instanceof HTMLElement)) return false;
    if (target.isContentEditable) return true;
    const field = target.closest("input, textarea, select");
    if (!(field instanceof HTMLElement)) return false;
    if (field instanceof HTMLInputElement) {
      const inert = /* @__PURE__ */ new Set(["button", "checkbox", "radio", "file", "range", "color", "submit", "reset"]);
      if (inert.has(field.type)) return false;
    }
    return true;
  }
  function openCheatSheet() {
    const dialog = el("shortcuts-dialog");
    if (dialog.open) return;
    rememberFocus();
    renderCheatSheet();
    dialog.showModal();
    el("shortcuts-title").tabIndex = -1;
    el("shortcuts-title").focus();
  }
  function wireShortcuts() {
    document.removeEventListener("keydown", onKey);
    document.addEventListener("keydown", onKey);
    el("open-shortcuts").addEventListener("click", () => openCheatSheet());
    el("shortcuts-close").addEventListener("click", () => el("shortcuts-dialog").close());
    el("shortcuts-dialog").addEventListener("close", () => restoreFocus());
    wireQuickOpen();
  }
  function onKey(event) {
    if (event.isComposing || event.defaultPrevented) return;
    const shortcut = matchShortcut(event);
    if (!shortcut) return;
    if (isTypingTarget(event.target) && !shortcut.whileTyping) return;
    if (shortcut.id !== "dismiss" && topDialog()) return;
    if (skipsListKey(shortcut.id, event.target)) return;
    if (event.repeat && !repeats(shortcut.id)) return;
    runShortcut(shortcut.id, event);
  }
  function repeats(id) {
    return id === "list-previous" || id === "list-next" || id === "seek-back" || id === "seek-forward";
  }
  function skipsListKey(id, target) {
    if (!(target instanceof HTMLElement)) return false;
    if (id === "play-pause" && target.closest("button, a, summary, input, select, textarea, [role='button']")) return true;
    if (id === "list-open" && target.closest("button, a, summary, textarea, select")) return true;
    return false;
  }
  function topDialog() {
    const open = [...document.querySelectorAll("dialog")].filter(
      (node) => node instanceof HTMLDialogElement && node.open
    );
    return open.at(-1) ?? null;
  }
  var HANDLERS = {
    "focus-search": (event) => {
      event.preventDefault();
      focusCurrentSearch();
    },
    "quick-open": (event) => {
      event.preventDefault();
      openQuickOpen();
    },
    dismiss: (event) => {
      dismiss(event);
    },
    "cheat-sheet": (event) => {
      event.preventDefault();
      openCheatSheet();
    },
    "list-previous": (event) => {
      event.preventDefault();
      moveActiveList(-1);
    },
    "list-next": (event) => {
      event.preventDefault();
      moveActiveList(1);
    },
    "list-open": (event) => {
      event.preventDefault();
      openActiveList();
    },
    "play-pause": (event) => {
      if (!player) return;
      event.preventDefault();
      player.togglePlayPause();
    },
    "seek-back": (event) => {
      if (!player) return;
      event.preventDefault();
      player.seekBy(-SEEK_SECONDS);
    },
    "seek-forward": (event) => {
      if (!player) return;
      event.preventDefault();
      player.seekBy(SEEK_SECONDS);
    },
    "view-library": (event) => {
      event.preventDefault();
      showLibrary();
    },
    "view-crates": (event) => {
      event.preventDefault();
      showCrates();
    },
    "view-files": (event) => {
      event.preventDefault();
      setMode("files");
      el("files-list").focus();
    },
    "view-history": (event) => {
      event.preventDefault();
      setMode("history");
      el("list").focus();
    },
    "view-snapshots": (event) => {
      event.preventDefault();
      setMode("snapshots");
      snapshotCursor = 0;
      el("snapshots-list").focus();
    }
  };
  function runShortcut(id, event) {
    const handler = HANDLERS[id];
    handler(event);
  }
  function focusCurrentSearch() {
    if (state.mode === "files") {
      const field2 = el("files-search");
      field2.focus();
      field2.select();
      return;
    }
    if (state.mode === "snapshots") {
      el("snapshots-status").textContent = copy.snapshotsNoSearch;
      return;
    }
    const field = el("search");
    field.focus();
    field.select();
  }
  function showLibrary() {
    setMode("crates");
    selectCrate("all");
    el("list").focus();
  }
  function showCrates() {
    setMode("crates");
    const first = el("crate-list").querySelector(".crate");
    if (first) focusCrateItem(first);
    else el("crate-list").focus();
  }
  function moveActiveList(delta) {
    if (quickOpenIsOpen()) return;
    if (state.mode === "files") {
      moveFileList(delta);
      return;
    }
    if (state.mode === "snapshots") {
      moveSnapshots(delta);
      return;
    }
    moveTrackList(delta);
  }
  function openActiveList() {
    if (quickOpenIsOpen()) return;
    if (state.mode === "files") {
      openFileList();
      return;
    }
    if (state.mode === "snapshots") {
      openSnapshot();
      return;
    }
    openTrackList();
  }
  function moveSnapshots(delta) {
    const cards = snapshotCards();
    if (!cards.length) return;
    snapshotCursor = Math.max(0, Math.min(cards.length - 1, snapshotCursor + delta));
    const card = cards[snapshotCursor];
    card?.querySelector("button")?.focus();
  }
  function openSnapshot() {
    const cards = snapshotCards();
    const card = cards[snapshotCursor] ?? cards[0];
    card?.querySelector("button")?.click();
  }
  function snapshotCards() {
    return [...el("snapshots-list").querySelectorAll(".snapshot-card")];
  }
  function dismiss(event) {
    const dialog = topDialog();
    if (dialog) {
      if (dialog.id === "quick-open") {
        event.preventDefault();
        closeQuickOpen();
        return;
      }
      if (dialog.id === "shortcuts-dialog") {
        event.preventDefault();
        dialog.close();
        return;
      }
      return;
    }
    const active2 = document.activeElement;
    if (active2 instanceof HTMLInputElement && isSearchField(active2)) {
      event.preventDefault();
      if (active2.value) replaceInput(active2, "");
      else active2.blur();
      return;
    }
    if (isTypingTarget(active2)) {
      if (active2 instanceof HTMLElement) active2.blur();
      return;
    }
    if (clearViewSearch()) event.preventDefault();
  }
  function isSearchField(field) {
    return field.id === "search" || field.id === "crate-search" || field.id === "files-search" || field.id === "quick-open-query";
  }
  function clearViewSearch() {
    if (state.mode === "files" && el("files-search").value) {
      replaceInput(el("files-search"), "");
      return true;
    }
    if (state.mode === "crates" && el("crate-search").value && !el("search").value) {
      replaceInput(el("crate-search"), "");
      return true;
    }
    if (el("search").value) {
      replaceInput(el("search"), "");
      return true;
    }
    if (el("crate-search").value) {
      replaceInput(el("crate-search"), "");
      return true;
    }
    return false;
  }
  function replaceInput(field, value) {
    field.value = value;
    field.dispatchEvent(new Event("input", { bubbles: true }));
  }
  function renderCheatSheet() {
    el("shortcuts-title").textContent = copy.shortcutsTitle;
    el("shortcuts-intro").textContent = copy.shortcutsIntro;
    el("shortcuts-close").textContent = copy.shortcutsClose;
    const body = el("shortcuts-body");
    body.replaceChildren();
    const groups = [];
    for (const shortcut of SHORTCUTS) {
      if (!groups.includes(shortcut.group)) groups.push(shortcut.group);
    }
    for (const group of groups) {
      const heading = document.createElement("h3");
      heading.textContent = group;
      body.append(heading);
      if (group === "Play") {
        const note = document.createElement("p");
        note.className = "dialog-note";
        note.textContent = copy.playNote;
        body.append(note);
      }
      const table = document.createElement("table");
      table.className = "shortcut-table";
      const head = document.createElement("thead");
      const headRow = document.createElement("tr");
      const actionHead = document.createElement("th");
      actionHead.scope = "col";
      actionHead.textContent = "Action";
      const keyHead = document.createElement("th");
      keyHead.scope = "col";
      keyHead.textContent = "Key";
      headRow.append(actionHead, keyHead);
      head.append(headRow);
      const rows2 = document.createElement("tbody");
      for (const shortcut of SHORTCUTS) {
        if (shortcut.group !== group) continue;
        const row = document.createElement("tr");
        const action = document.createElement("th");
        action.scope = "row";
        action.textContent = shortcut.label;
        const keys = document.createElement("td");
        shortcut.keys.forEach((chord, index) => {
          if (index > 0) keys.append(document.createTextNode(" or "));
          const kbd = document.createElement("kbd");
          kbd.textContent = chordLabel(chord);
          keys.append(kbd);
        });
        row.append(action, keys);
        rows2.append(row);
      }
      table.append(head, rows2);
      body.append(table);
    }
  }
  function rememberFocus() {
    returnFocus2 = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  }
  function restoreFocus() {
    const node = returnFocus2;
    returnFocus2 = null;
    if (node && node.isConnected) node.focus();
  }

  // src/version.ts
  var VERSION_UNAVAILABLE = "Version unavailable";
  var COPY_FAILED = "Couldn't copy the version.";
  var copyText = "";
  function versionLabel(info) {
    const version = formatVersion(info.version);
    if (info.source === "release") return version;
    const commit = shortCommit(info.commit);
    if (!commit || version.toLowerCase().includes(commit)) return version;
    return `${version} · ${commit}`;
  }
  function formatVersion(version) {
    const trimmed = version.trim();
    if (/^\d+\.\d+\.\d+/.test(trimmed)) return `v${trimmed}`;
    return trimmed;
  }
  function shortCommit(commit) {
    if (commit === null) return null;
    const trimmed = commit.trim().toLowerCase();
    if (!/^[0-9a-f]{7,40}$/.test(trimmed)) return null;
    return trimmed.slice(0, 7);
  }
  function paint2(label) {
    const footer = el("app-version");
    const about = el("about-version");
    el("version-copy-status").textContent = "";
    if (!label) {
      copyText = "";
      footer.hidden = true;
      footer.replaceChildren();
      about.textContent = VERSION_UNAVAILABLE;
      return;
    }
    copyText = label;
    footer.hidden = false;
    footer.replaceChildren();
    const name = document.createElement("span");
    name.className = "visually-hidden";
    name.textContent = "App version ";
    const value = document.createElement("span");
    value.textContent = label;
    footer.append(name, value);
    about.textContent = label;
  }
  async function loadVersion() {
    try {
      paint2(versionLabel(await getVersion()));
    } catch {
      paint2(null);
    }
  }
  async function copyVersion() {
    const status = el("version-copy-status");
    if (!copyText) {
      status.textContent = VERSION_UNAVAILABLE;
      return;
    }
    const writeText = navigator.clipboard?.writeText;
    if (!writeText || !window.isSecureContext) {
      status.textContent = COPY_FAILED;
      return;
    }
    try {
      await writeText.call(navigator.clipboard, copyText);
      status.textContent = "Copied";
    } catch {
      status.textContent = COPY_FAILED;
    }
  }
  function wireVersion() {
    el("copy-version").addEventListener("click", () => {
      void copyVersion();
    });
  }

  // src/app.ts
  function wireSnapshots() {
    el("snapshots-refresh").addEventListener("click", () => {
      loadSnapshots().catch((error2) => failSnapshots(error2));
    });
    el("snapshots-take").addEventListener("click", () => {
      takeSnapshot().catch((error2) => failSnapshots(error2));
    });
    el("snapshots-undo-button").addEventListener("click", () => {
      const pending = state.snapshotUndo;
      if (!pending || !pending.restore_id) return;
      openSnapshotPlan(pending.restore_id).catch((error2) => failSnapshots(error2));
    });
    el("snapshot-cancel").addEventListener("click", () => {
      el("snapshot-dialog").close();
    });
    el("snapshot-confirm").addEventListener("click", () => {
      confirmSnapshotRestore().catch((error2) => setSnapshotDialogStatus(failureOf(error2).message));
    });
  }
  mountTrackList();
  mountPlayer();
  bindSpaceToggle();
  wireLibrary();
  wireVirtualScroll();
  wireShortcuts();
  wireDialogs();
  wireSnapshots();
  wireLayout();
  wireVersion();
  void loadVersion();
  bindLibraryReload(loadLibrary);
  loadLibrary().catch(showFailure);
})();
//# sourceMappingURL=app.js.map
