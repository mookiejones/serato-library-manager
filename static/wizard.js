"use strict";
var SeratoWizard = (() => {
  var __defProp = Object.defineProperty;
  var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
  var __getOwnPropNames = Object.getOwnPropertyNames;
  var __hasOwnProp = Object.prototype.hasOwnProperty;
  var __export = (target, all) => {
    for (var name in all)
      __defProp(target, name, { get: all[name], enumerable: true });
  };
  var __copyProps = (to, from, except, desc) => {
    if (from && typeof from === "object" || typeof from === "function") {
      for (let key of __getOwnPropNames(from))
        if (!__hasOwnProp.call(to, key) && key !== except)
          __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
    }
    return to;
  };
  var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

  // src/wizard-view.ts
  var wizard_view_exports = {};
  __export(wizard_view_exports, {
    open: () => open
  });

  // src/wizard.ts
  var BLOCKED_MESSAGE = "Close Serato DJ to continue.";
  var DONE_MESSAGE = "Library ready. Snapshot saved.";
  var WELCOME_BODY = "This app shows the library Serato already keeps on this computer. It will not change anything without asking.";
  var SNAPSHOT_BODY = "A backup of your library data is saved before anything is changed.";
  var CONSENT_BODY = "Counts and actions only, plus the app name, the app version, and the operating system. Track titles, crate names, file paths, and library contents stay on this computer. Sharing stays off unless you turn it on.";
  var STEP_NAME = {
    welcome: "Welcome",
    library: "Find your library",
    snapshot: "Safety snapshot",
    consent: "Sharing",
    done: "Done"
  };
  function visibleSteps(needsConsent) {
    const steps = ["welcome", "library", "snapshot"];
    if (needsConsent) steps.push("consent");
    steps.push("done");
    return steps;
  }
  function createWizard(input) {
    return {
      step: "welcome",
      complete: false,
      dismissed: false,
      context: {
        needsConsent: input.needsConsent,
        library: input.library,
        seratoRunning: input.seratoRunning,
        snapshot: "idle",
        consent: null
      }
    };
  }
  function reduceWizard(model2, action) {
    if (model2.dismissed || model2.complete) return model2;
    switch (action.type) {
      case "cancel":
        return { ...model2, dismissed: true, complete: false };
      case "back":
        return goBack(model2);
      case "next":
        return goNext(model2);
      case "library":
        return { ...model2, context: { ...model2.context, library: action.status } };
      case "serato":
        return { ...model2, context: { ...model2.context, seratoRunning: action.running } };
      case "snapshot":
        return { ...model2, context: { ...model2.context, snapshot: action.phase } };
      case "consent":
        return goNext({ ...model2, context: { ...model2.context, consent: action.value } });
      case "finish":
        if (model2.step !== "done") return model2;
        return { ...model2, complete: true };
      default:
        return model2;
    }
  }
  function stepPosition(model2) {
    const steps = visibleSteps(model2.context.needsConsent);
    const found = steps.indexOf(model2.step);
    const index = found < 0 ? 1 : found + 1;
    return { index, count: steps.length, name: STEP_NAME[model2.step] };
  }
  function canGoBack(model2) {
    if (model2.dismissed || model2.complete) return false;
    if (model2.step === "snapshot" && model2.context.snapshot === "saving") return false;
    return visibleSteps(model2.context.needsConsent).indexOf(model2.step) > 0;
  }
  function canAdvance(model2) {
    if (model2.dismissed || model2.complete) return false;
    switch (model2.step) {
      case "welcome":
        return true;
      case "library":
        return model2.context.library === "found";
      case "snapshot":
        return model2.context.snapshot === "saved";
      case "consent":
        return model2.context.consent !== null;
      case "done":
        return false;
      default:
        return false;
    }
  }
  function snapshotBlocked(model2) {
    return model2.step === "snapshot" && model2.context.seratoRunning && model2.context.snapshot !== "saved";
  }
  function primaryAction(model2) {
    switch (model2.step) {
      case "welcome":
        return "get-started";
      case "library":
        if (model2.context.library === "pending") return "looking";
        if (model2.context.library === "found") return "use-library";
        return "check-again";
      case "snapshot":
        if (model2.context.snapshot === "saved") return "continue";
        if (model2.context.snapshot === "error") return "try-again";
        return "take-snapshot";
      case "consent":
        return "none";
      case "done":
        return "open-library";
      default:
        return "none";
    }
  }
  function primaryEnabled(model2) {
    if (model2.dismissed || model2.complete) return false;
    const action = primaryAction(model2);
    if (action === "none" || action === "looking") return false;
    if (model2.step === "snapshot" && model2.context.snapshot === "saving") return false;
    if (snapshotBlocked(model2)) return false;
    return true;
  }
  function stepAnnouncement(model2) {
    const position = stepPosition(model2);
    return `Step ${position.index} of ${position.count}. ${position.name}.`;
  }
  function goBack(model2) {
    if (!canGoBack(model2)) return model2;
    const steps = visibleSteps(model2.context.needsConsent);
    const index = steps.indexOf(model2.step);
    const previous = steps[index - 1];
    if (previous === void 0) return model2;
    return { ...model2, step: previous };
  }
  function goNext(model2) {
    if (!canAdvance(model2)) return model2;
    const steps = visibleSteps(model2.context.needsConsent);
    const index = steps.indexOf(model2.step);
    const next = steps[index + 1];
    if (next === void 0) return model2;
    return { ...model2, step: next };
  }

  // src/wizard-view.ts
  var LABELS = {
    "get-started": "Get started",
    looking: "Looking…",
    "use-library": "Use this library",
    "check-again": "Check again",
    "take-snapshot": "Take a safety snapshot",
    "try-again": "Try again",
    continue: "Continue",
    "open-library": "Open my library",
    none: ""
  };
  var HEADINGS = {
    welcome: "See your Serato library",
    library: "Find your library",
    snapshot: "Safety snapshot",
    consent: "Share anonymous usage stats and crash reports?",
    done: DONE_MESSAGE
  };
  var wired = false;
  var starting = false;
  var generation = 0;
  var busy = false;
  var model = createWizard({
    needsConsent: true,
    library: "pending",
    seratoRunning: false
  });
  var options = {};
  var summary = "";
  var nextText = "";
  var statusNote = "";
  var folderOpen = false;
  var folderPath = "";
  var folderParent = null;
  var pollTimer = 0;
  var polling = false;
  function open(next = {}) {
    wire();
    if (starting) return;
    const dialog = wizardDialog();
    if (dialog.open && !next.force) return;
    options = next;
    starting = true;
    void begin(next).finally(() => {
      starting = false;
    });
  }
  function wire() {
    if (wired) return;
    wired = true;
    button("wizard-primary").addEventListener("click", () => {
      void onPrimary();
    });
    button("wizard-back").addEventListener("click", () => {
      onBack();
    });
    button("wizard-cancel").addEventListener("click", () => {
      cancel();
    });
    button("wizard-secondary").addEventListener("click", () => {
      void showFolders();
    });
    button("wizard-no").addEventListener("click", () => {
      void chooseConsent(false);
    });
    button("wizard-yes").addEventListener("click", () => {
      void chooseConsent(true);
    });
    button("wizard-folder-up").addEventListener("click", () => {
      if (folderParent) void browse(folderParent);
    });
    button("wizard-folder-use").addEventListener("click", () => {
      void useFolder();
    });
    button("wizard-folder-close").addEventListener("click", () => {
      closeFolders();
    });
    wizardDialog().addEventListener("cancel", (event) => {
      event.preventDefault();
      if (folderOpen) {
        closeFolders();
        return;
      }
      cancel();
    });
  }
  async function begin(next) {
    generation += 1;
    const token = generation;
    stopPoll();
    folderOpen = false;
    statusNote = "";
    busy = false;
    const settings = await loadSettings();
    if (token !== generation) return;
    if (settings.wizard_complete && !next.force) return;
    const setup = await loadSetup();
    if (token !== generation) return;
    summary = setup?.summary ?? "Couldn't look for your library.";
    nextText = setup?.next ?? "Choose Check again.";
    if (setup) publishStatus(setup);
    const library = setup === null ? "error" : setup.found ? "found" : "missing";
    model = createWizard({
      needsConsent: settings.needs_consent_prompt,
      library,
      seratoRunning: setup?.seratoRunning ?? false
    });
    paint(false);
    const dialog = wizardDialog();
    if (!dialog.open) dialog.showModal();
    text("wizard-announce").textContent = stepAnnouncement(model);
    text("wizard-title").focus();
    ensurePoll();
  }
  function onBack() {
    if (!canGoBack(model) || busy) return;
    folderOpen = false;
    statusNote = "";
    model = reduceWizard(model, { type: "back" });
    paint(true);
    ensurePoll();
  }
  function cancel() {
    generation += 1;
    stopPoll();
    folderOpen = false;
    busy = false;
    model = reduceWizard(model, { type: "cancel" });
    closeDialog();
  }
  async function onPrimary() {
    if (busy || !primaryEnabled(model)) return;
    const action = primaryAction(model);
    if (action === "get-started" || action === "use-library" || action === "continue") {
      folderOpen = false;
      statusNote = "";
      model = reduceWizard(model, { type: "next" });
      paint(true);
      ensurePoll();
      if (model.step === "snapshot") void refreshSerato();
      return;
    }
    if (action === "check-again") {
      await recheck();
      return;
    }
    if (action === "take-snapshot" || action === "try-again") {
      await takeSnapshot();
      return;
    }
    if (action === "open-library") {
      await finish();
    }
  }
  async function recheck() {
    const token = generation;
    busy = true;
    statusNote = "";
    paint(false);
    const setup = await loadSetup();
    if (token !== generation) return;
    busy = false;
    if (setup === null) {
      summary = "Couldn't look for your library.";
      nextText = "Choose Check again.";
      model = reduceWizard(model, { type: "library", status: "error" });
    } else {
      summary = setup.summary;
      nextText = setup.next;
      publishStatus(setup);
      model = reduceWizard(model, { type: "serato", running: setup.seratoRunning });
      model = reduceWizard(model, { type: "library", status: setup.found ? "found" : "missing" });
    }
    paint(false);
  }
  async function takeSnapshot() {
    if (snapshotBlocked(model)) return;
    const token = generation;
    busy = true;
    statusNote = "";
    model = reduceWizard(model, { type: "snapshot", phase: "saving" });
    paint(false);
    try {
      await postJSON("/api/snapshots", { action: "create" }, 10 * 60 * 1e3);
      if (token !== generation) return;
      model = reduceWizard(model, { type: "snapshot", phase: "saved" });
    } catch {
      if (token !== generation) return;
      model = reduceWizard(model, { type: "snapshot", phase: "error" });
      statusNote = "The safety copy could not be saved. Your library was not changed. Try again.";
    } finally {
      if (token === generation) {
        busy = false;
        paint(false);
      }
    }
  }
  async function chooseConsent(value) {
    if (busy || model.step !== "consent") return;
    const token = generation;
    busy = true;
    statusNote = "Saving…";
    paint(false);
    try {
      const payload = await postJSON("/api/settings", { telemetry_consent: value }, 15e3);
      if (token !== generation) return;
      const settings = readSettings(payload);
      if (settings) options.onSettings?.(settings);
      busy = false;
      statusNote = "";
      model = reduceWizard(model, { type: "consent", value });
      paint(true);
    } catch {
      if (token !== generation) return;
      busy = false;
      statusNote = "Couldn't save that choice. Try again.";
      paint(false);
    }
  }
  async function finish() {
    const token = generation;
    busy = true;
    statusNote = "Opening…";
    paint(false);
    try {
      const payload = await postJSON("/api/settings", { wizard_complete: true }, 15e3);
      if (token !== generation) return;
      const settings = readSettings(payload);
      if (settings) options.onSettings?.(settings);
      model = reduceWizard(model, { type: "finish" });
      closeDialog();
    } catch (error) {
      if (token !== generation) return;
      statusNote = error instanceof Error ? error.message : "Couldn't save that you finished setup. Try again.";
      busy = false;
      paint(false);
    }
  }
  async function showFolders() {
    folderOpen = true;
    paint(false);
    await browse(folderPath);
  }
  function closeFolders() {
    folderOpen = false;
    paint(false);
    button("wizard-secondary").focus();
  }
  async function browse(path) {
    const token = generation;
    try {
      const query = path ? `?browse=${encodeURIComponent(path)}` : "?browse=";
      const payload = await getJSON(`/api/setup${query}`, 15e3);
      if (token !== generation) return;
      const listing = readBrowse(payload);
      if (!listing) {
        statusNote = "That folder could not be read.";
        paint(false);
        return;
      }
      folderPath = listing.path;
      folderParent = listing.parent;
      text("wizard-folder-name").textContent = listing.name;
      fillFolders(listing.folders);
      button("wizard-folder-up").disabled = listing.parent === null;
      paint(false);
    } catch {
      if (token !== generation) return;
      statusNote = "That folder could not be read.";
      paint(false);
    }
  }
  async function useFolder() {
    if (!folderPath || busy) return;
    const token = generation;
    busy = true;
    paint(false);
    try {
      const payload = await postJSON("/api/setup", { folder: folderPath }, 15e3);
      if (token !== generation) return;
      const setup = readSetup(payload);
      if (!setup) {
        statusNote = "That folder could not be read.";
        return;
      }
      summary = setup.summary;
      nextText = setup.next;
      publishStatus(setup);
      model = reduceWizard(model, { type: "serato", running: setup.seratoRunning });
      model = reduceWizard(model, { type: "library", status: setup.found ? "found" : "missing" });
      if (setup.found) {
        folderOpen = false;
        statusNote = "";
      } else {
        statusNote = "";
      }
    } catch (error) {
      if (token !== generation) return;
      statusNote = error instanceof Error ? error.message : "That folder could not be read.";
    } finally {
      if (token === generation) {
        busy = false;
        paint(false);
        if (model.context.library === "found") button("wizard-primary").focus();
      }
    }
  }
  function fillFolders(folders) {
    const list = element("wizard-folder-list");
    list.replaceChildren();
    if (folders.length === 0) {
      const empty = document.createElement("p");
      empty.className = "wizard-folder-empty";
      empty.textContent = "This folder has no folders inside it.";
      list.append(empty);
      return;
    }
    for (const folder of folders) {
      const control = document.createElement("button");
      control.type = "button";
      control.className = "wizard-folder";
      control.textContent = folder.name;
      const nextPath = folder.path;
      control.addEventListener("click", () => {
        void browse(nextPath);
      });
      list.append(control);
    }
  }
  function paint(moveFocus) {
    const position = stepPosition(model);
    text("wizard-step-label").textContent = `Step ${position.index} of ${position.count}`;
    paintSegments(position.index, position.count);
    paintArt();
    text("wizard-title").textContent = HEADINGS[model.step];
    const body = bodyText();
    const bodyNode = text("wizard-body");
    bodyNode.textContent = body;
    bodyNode.hidden = body.length === 0;
    const hint = text("wizard-next");
    const showHint = model.step === "library" && model.context.library !== "found" && nextText.length > 0;
    hint.hidden = !showHint;
    hint.textContent = showHint ? nextText : "";
    const status = statusFor();
    const statusNode = text("wizard-status");
    statusNode.textContent = status.text;
    statusNode.hidden = status.text.length === 0;
    statusNode.className = status.kind ? `wizard-status is-${status.kind}` : "wizard-status";
    paintProgress();
    element("wizard-consent").hidden = model.step !== "consent";
    element("wizard-folders").hidden = !(folderOpen && model.step === "library");
    const back = button("wizard-back");
    back.hidden = !canGoBack(model);
    back.disabled = busy;
    const secondary = button("wizard-secondary");
    secondary.hidden = model.step !== "library";
    secondary.disabled = busy;
    const primary = button("wizard-primary");
    const action = primaryAction(model);
    primary.hidden = action === "none";
    primary.textContent = model.context.snapshot === "saving" ? "Saving a safety copy…" : LABELS[action];
    primary.disabled = busy || !primaryEnabled(model);
    button("wizard-no").disabled = busy;
    button("wizard-yes").disabled = busy;
    button("wizard-cancel").disabled = false;
    if (moveFocus) {
      text("wizard-announce").textContent = stepAnnouncement(model);
      text("wizard-title").focus();
    }
  }
  function bodyText() {
    switch (model.step) {
      case "welcome":
        return WELCOME_BODY;
      case "library":
        if (model.context.library === "pending") return "Looking for your Serato library.";
        return summary || "Looking for your Serato library.";
      case "snapshot":
        return SNAPSHOT_BODY;
      case "consent":
        return CONSENT_BODY;
      case "done":
        return "";
      default:
        return "";
    }
  }
  function statusFor() {
    if (snapshotBlocked(model)) return { text: BLOCKED_MESSAGE, kind: "blocked" };
    if (model.step === "snapshot" && model.context.snapshot === "saved") {
      return { text: "Safety copy saved.", kind: "saved" };
    }
    if (model.step === "snapshot" && model.context.snapshot === "saving") {
      return { text: "Saving a safety copy of your library.", kind: "" };
    }
    if (statusNote) return { text: statusNote, kind: "" };
    return { text: "", kind: "" };
  }
  function paintSegments(current, count) {
    const host = element("wizard-segments");
    host.replaceChildren();
    for (let index = 1; index <= count; index += 1) {
      const segment = document.createElement("span");
      segment.className = "wizard-segment";
      if (index < current) segment.dataset.state = "done";
      else if (index === current) segment.dataset.state = "current";
      else segment.dataset.state = "upcoming";
      host.append(segment);
    }
  }
  function paintArt() {
    const slots = document.querySelectorAll(".wizard-art");
    slots.forEach((slot) => {
      const current = slot.dataset.artSlot === model.step;
      const hasArt = slot.querySelector("svg, img") !== null;
      slot.hidden = !(current && hasArt);
    });
  }
  function publishStatus(setup) {
    if (setup.statusMessage.length === 0) return;
    options.onStatus?.({
      message: setup.statusMessage,
      writable: setup.statusWritable,
      open: setup.seratoRunning,
      serato_running: setup.seratoRunning,
      process: setup.seratoRunning ? "Serato DJ" : null
    });
  }
  function paintProgress() {
    const node = element("wizard-progress");
    if (!(node instanceof HTMLProgressElement)) return;
    const saving = model.step === "snapshot" && model.context.snapshot === "saving";
    const saved = model.step === "snapshot" && model.context.snapshot === "saved";
    node.hidden = !saving && !saved;
    if (saving) node.removeAttribute("value");
    if (saved) node.value = 1;
  }
  function ensurePoll() {
    stopPoll();
    if (!wizardDialog().open) return;
    pollTimer = window.setInterval(() => {
      void refreshSerato();
    }, 2e3);
  }
  async function refreshSerato() {
    if (polling) return;
    if (!wizardDialog().open) {
      stopPoll();
      return;
    }
    polling = true;
    const token = generation;
    try {
      const setup = await loadSetup();
      if (token !== generation || !setup) return;
      publishStatus(setup);
      if (model.step !== "snapshot" || model.context.snapshot === "saved") return;
      const wasBlocked = snapshotBlocked(model);
      model = reduceWizard(model, { type: "serato", running: setup.seratoRunning });
      if (snapshotBlocked(model) !== wasBlocked) paint(false);
    } finally {
      polling = false;
    }
  }
  function stopPoll() {
    if (pollTimer) window.clearInterval(pollTimer);
    pollTimer = 0;
  }
  function closeDialog() {
    stopPoll();
    const dialog = wizardDialog();
    if (dialog.open) dialog.close();
    const target = options.returnFocus;
    if (target instanceof HTMLElement && target.isConnected) target.focus();
  }
  async function loadSettings() {
    try {
      const payload = await getJSON("/api/settings", 15e3);
      return readSettings(payload) ?? fallbackSettings();
    } catch {
      return fallbackSettings();
    }
  }
  async function loadSetup() {
    try {
      const payload = await getJSON("/api/setup", 15e3);
      return readSetup(payload);
    } catch {
      return null;
    }
  }
  function fallbackSettings() {
    return {
      telemetry_consent: null,
      needs_consent_prompt: true,
      wizard_complete: false,
      telemetry_configured: false,
      app_version: ""
    };
  }
  function readSettings(value) {
    if (!isRecord(value) || typeof value.needs_consent_prompt !== "boolean") return null;
    const consent = value.telemetry_consent;
    return {
      telemetry_consent: typeof consent === "boolean" ? consent : null,
      needs_consent_prompt: value.needs_consent_prompt,
      wizard_complete: value.wizard_complete === true,
      telemetry_configured: value.telemetry_configured === true,
      app_version: typeof value.app_version === "string" ? value.app_version : ""
    };
  }
  function readSetup(value) {
    if (!isRecord(value) || typeof value.found !== "boolean" || typeof value.summary !== "string") return null;
    return {
      found: value.found,
      summary: value.summary,
      next: typeof value.next === "string" ? value.next : "",
      seratoRunning: value.serato_running === true,
      statusMessage: typeof value.status_message === "string" ? value.status_message : "",
      statusWritable: value.status_writable === true
    };
  }
  function readBrowse(value) {
    if (!isRecord(value) || typeof value.path !== "string" || typeof value.name !== "string") return null;
    if (!Array.isArray(value.folders)) return null;
    const folders = [];
    for (const entry of value.folders) {
      if (!isRecord(entry) || typeof entry.name !== "string" || typeof entry.path !== "string") continue;
      folders.push({ name: entry.name, path: entry.path });
    }
    const parent = typeof value.parent === "string" ? value.parent : null;
    return { path: value.path, parent, name: value.name, folders };
  }
  async function getJSON(url, timeoutMs) {
    const response = await fetch(url, { signal: AbortSignal.timeout(timeoutMs) });
    const payload = await response.json().catch(() => null);
    if (!response.ok) throw new Error(plainError(payload));
    return payload;
  }
  async function postJSON(url, body, timeoutMs) {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(timeoutMs)
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) throw new Error(plainError(payload));
    return payload;
  }
  function plainError(payload) {
    const raw = isRecord(payload) && typeof payload.error === "string" ? payload.error : "";
    if (!raw || raw.includes("/") || raw.includes("\\") || raw.toLowerCase().includes("sqlite")) {
      return "Something went wrong. Try again.";
    }
    return raw;
  }
  function isRecord(value) {
    return typeof value === "object" && value !== null;
  }
  function wizardDialog() {
    const node = element("wizard");
    if (!(node instanceof HTMLDialogElement)) throw new Error("Missing wizard");
    return node;
  }
  function element(id) {
    const node = document.getElementById(id);
    if (!node) throw new Error(`Missing ${id}`);
    return node;
  }
  function text(id) {
    return element(id);
  }
  function button(id) {
    const node = element(id);
    if (!(node instanceof HTMLButtonElement)) throw new Error(`Missing ${id}`);
    return node;
  }
  return __toCommonJS(wizard_view_exports);
})();
//# sourceMappingURL=wizard.js.map
