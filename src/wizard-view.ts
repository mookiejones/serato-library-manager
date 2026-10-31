/**
 * First-run wizard screen.
 *
 * The state machine in wizard.ts decides the step. This file paints the
 * dialog, talks to the local server, and moves focus when the step
 * changes. Text from the server is assigned with textContent.
 */

import { onLocaleChange, serverMessage, t, type MessageKey } from "./i18n";
import {
  canGoBack,
  createWizard,
  primaryAction,
  primaryEnabled,
  reduceWizard,
  snapshotBlocked,
  stepAnnouncement,
  stepPosition,
  type LibraryStatus,
  type PrimaryAction,
  type WizardModel,
} from "./wizard";
import { tip } from "./tips";

export interface SettingsPayload {
  telemetry_consent: boolean | null;
  needs_consent_prompt: boolean;
  wizard_complete: boolean;
  telemetry_configured: boolean;
  app_version: string;
}

export interface LibraryStatusNotice {
  message: string;
  writable: boolean;
  open: boolean;
  serato_running: boolean;
  process: string | null;
}

export interface OpenOptions {
  force?: boolean;
  returnFocus?: HTMLElement | null;
  onSettings?: (payload: SettingsPayload) => void;
  onStatus?: (status: LibraryStatusNotice) => void;
}

interface SetupInfo {
  found: boolean;
  summary: string;
  next: string;
  seratoRunning: boolean;
  statusMessage: string;
  statusWritable: boolean;
}

interface FolderRow {
  name: string;
  path: string;
}

const LABELS: Record<Exclude<PrimaryAction, "none">, MessageKey> = {
  "get-started": "wizard.action.getStarted",
  looking: "wizard.action.looking",
  "use-library": "wizard.action.useLibrary",
  "check-again": "wizard.action.checkAgain",
  "take-snapshot": "wizard.action.takeSnapshot",
  "try-again": "wizard.action.tryAgain",
  continue: "wizard.action.continue",
  "open-library": "wizard.action.openLibrary",
};

const HEADINGS: Record<WizardModel["step"], MessageKey> = {
  welcome: "wizard.heading.welcome",
  library: "wizard.heading.library",
  snapshot: "wizard.heading.snapshot",
  consent: "wizard.heading.consent",
  done: "wizard.done",
};

// Notes are stored as functions so a language change repaints them.
type Note = () => string;
const noteKey = (key: MessageKey): Note => () => t(key);
const noteText = (value: string): Note => () => value;

let wired = false;
let starting = false;
let generation = 0;
let busy = false;
let model: WizardModel = createWizard({
  needsConsent: true,
  library: "pending",
  seratoRunning: false,
});
let options: OpenOptions = {};
let summary: Note | null = null;
let nextText: Note | null = null;
let statusNote: Note | null = null;
let folderOpen = false;
let folderPath = "";
let folderParent: string | null = null;
let pollTimer = 0;
let polling = false;

/** Open setup. A finished setup stays closed unless force is set. */
export function open(next: OpenOptions = {}): void {
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

function wire(): void {
  if (wired) return;
  wired = true;
  onLocaleChange(() => {
    if (wizardDialog().open) paint(false);
  });
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

async function begin(next: OpenOptions): Promise<void> {
  generation += 1;
  const token = generation;
  stopPoll();
  folderOpen = false;
  statusNote = null;
  busy = false;
  const settings = await loadSettings();
  if (token !== generation) return;
  if (settings.wizard_complete && !next.force) return;
  const setup = await loadSetup();
  if (token !== generation) return;
  summary = setup ? noteText(setup.summary) : noteKey("wizard.lookFailed");
  nextText = setup ? noteText(setup.next) : noteKey("wizard.chooseCheckAgain");
  if (setup) publishStatus(setup);
  const library: LibraryStatus = setup === null ? "error" : setup.found ? "found" : "missing";
  model = createWizard({
    needsConsent: settings.needs_consent_prompt,
    library,
    seratoRunning: setup?.seratoRunning ?? false,
  });
  paint(false);
  const dialog = wizardDialog();
  if (!dialog.open) dialog.showModal();
  text("wizard-announce").textContent = stepAnnouncement(model);
  text("wizard-title").focus();
  ensurePoll();
}

function onBack(): void {
  if (!canGoBack(model) || busy) return;
  folderOpen = false;
  statusNote = null;
  model = reduceWizard(model, { type: "back" });
  paint(true);
  ensurePoll();
}

function cancel(): void {
  generation += 1;
  stopPoll();
  folderOpen = false;
  busy = false;
  model = reduceWizard(model, { type: "cancel" });
  closeDialog();
}

async function onPrimary(): Promise<void> {
  if (busy || !primaryEnabled(model)) return;
  const action = primaryAction(model);
  if (action === "get-started" || action === "use-library" || action === "continue") {
    folderOpen = false;
    statusNote = null;
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

async function recheck(): Promise<void> {
  const token = generation;
  busy = true;
  statusNote = null;
  paint(false);
  const setup = await loadSetup();
  if (token !== generation) return;
  busy = false;
  if (setup === null) {
    summary = noteKey("wizard.lookFailed");
    nextText = noteKey("wizard.chooseCheckAgain");
    model = reduceWizard(model, { type: "library", status: "error" });
  } else {
    summary = noteText(setup.summary);
    nextText = noteText(setup.next);
    publishStatus(setup);
    model = reduceWizard(model, { type: "serato", running: setup.seratoRunning });
    model = reduceWizard(model, { type: "library", status: setup.found ? "found" : "missing" });
  }
  paint(false);
}

async function takeSnapshot(): Promise<void> {
  if (snapshotBlocked(model)) return;
  const token = generation;
  busy = true;
  statusNote = null;
  model = reduceWizard(model, { type: "snapshot", phase: "saving" });
  paint(false);
  try {
    await postJSON("/api/snapshots", { action: "create" }, 10 * 60 * 1000);
    if (token !== generation) return;
    model = reduceWizard(model, { type: "snapshot", phase: "saved" });
  } catch {
    if (token !== generation) return;
    model = reduceWizard(model, { type: "snapshot", phase: "error" });
    statusNote = noteKey("wizard.snapshotFailed");
  } finally {
    if (token === generation) {
      busy = false;
      paint(false);
    }
  }
}

async function chooseConsent(value: boolean): Promise<void> {
  if (busy || model.step !== "consent") return;
  const token = generation;
  busy = true;
  statusNote = noteKey("wizard.saving");
  paint(false);
  try {
    const payload = await postJSON("/api/settings", { telemetry_consent: value }, 15000);
    if (token !== generation) return;
    const settings = readSettings(payload);
    if (settings) options.onSettings?.(settings);
    busy = false;
    statusNote = null;
    model = reduceWizard(model, { type: "consent", value });
    paint(true);
  } catch {
    if (token !== generation) return;
    busy = false;
    statusNote = noteKey("wizard.consentFailed");
    paint(false);
  }
}

async function finish(): Promise<void> {
  const token = generation;
  busy = true;
  statusNote = noteKey("wizard.opening");
  paint(false);
  try {
    const payload = await postJSON("/api/settings", { wizard_complete: true }, 15000);
    if (token !== generation) return;
    const settings = readSettings(payload);
    if (settings) options.onSettings?.(settings);
    model = reduceWizard(model, { type: "finish" });
    closeDialog();
  } catch (error) {
    if (token !== generation) return;
    statusNote = error instanceof Error ? noteText(error.message) : noteKey("wizard.finishFailed");
    busy = false;
    paint(false);
  }
}

async function showFolders(): Promise<void> {
  folderOpen = true;
  paint(false);
  await browse(folderPath);
}

function closeFolders(): void {
  folderOpen = false;
  paint(false);
  button("wizard-secondary").focus();
}

async function browse(path: string): Promise<void> {
  const token = generation;
  try {
    const query = path ? `?browse=${encodeURIComponent(path)}` : "?browse=";
    const payload = await getJSON(`/api/setup${query}`, 15000);
    if (token !== generation) return;
    const listing = readBrowse(payload);
    if (!listing) {
      statusNote = noteKey("error.folder_unreadable");
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
    statusNote = noteKey("error.folder_unreadable");
    paint(false);
  }
}

async function useFolder(): Promise<void> {
  if (!folderPath || busy) return;
  const token = generation;
  busy = true;
  paint(false);
  try {
    const payload = await postJSON("/api/setup", { folder: folderPath }, 15000);
    if (token !== generation) return;
    const setup = readSetup(payload);
    if (!setup) {
      statusNote = noteKey("error.folder_unreadable");
      return;
    }
    summary = noteText(setup.summary);
    nextText = noteText(setup.next);
    publishStatus(setup);
    model = reduceWizard(model, { type: "serato", running: setup.seratoRunning });
    model = reduceWizard(model, { type: "library", status: setup.found ? "found" : "missing" });
    if (setup.found) folderOpen = false;
    statusNote = null;
  } catch (error) {
    if (token !== generation) return;
    statusNote = error instanceof Error ? noteText(error.message) : noteKey("error.folder_unreadable");
  } finally {
    if (token === generation) {
      busy = false;
      paint(false);
      if (model.context.library === "found") button("wizard-primary").focus();
    }
  }
}

function fillFolders(folders: readonly FolderRow[]): void {
  const list = element("wizard-folder-list");
  list.replaceChildren();
  if (folders.length === 0) {
    const empty = document.createElement("p");
    empty.className = "wizard-folder-empty";
    empty.textContent = t("wizard.noSubfolders");
    list.append(empty);
    return;
  }
  for (const folder of folders) {
    const control = document.createElement("button");
    tip(control, "wizardFolder");
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

function paint(moveFocus: boolean): void {
  const position = stepPosition(model);
  text("wizard-step-label").textContent = t("wizard.stepOf", { index: position.index, count: position.count });
  paintSegments(position.index, position.count);
  paintArt();
  text("wizard-title").textContent = t(HEADINGS[model.step]);
  const body = bodyText();
  const bodyNode = text("wizard-body");
  bodyNode.textContent = body;
  bodyNode.hidden = body.length === 0;
  const hint = text("wizard-next");
  const hintText = nextText ? nextText() : "";
  const showHint = model.step === "library" && model.context.library !== "found" && hintText.length > 0;
  hint.hidden = !showHint;
  hint.textContent = showHint ? hintText : "";
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
  primary.textContent = model.context.snapshot === "saving"
    ? t("wizard.savingCopy")
    : action === "none" ? "" : t(LABELS[action]);
  primary.disabled = busy || !primaryEnabled(model);
  button("wizard-no").disabled = busy;
  button("wizard-yes").disabled = busy;
  button("wizard-cancel").disabled = false;
  if (moveFocus) {
    text("wizard-announce").textContent = stepAnnouncement(model);
    text("wizard-title").focus();
  }
}

function bodyText(): string {
  switch (model.step) {
    case "welcome":
      return t("wizard.welcomeBody");
    case "library":
      if (model.context.library === "pending") return t("wizard.looking");
      return (summary ? summary() : "") || t("wizard.looking");
    case "snapshot":
      return t("wizard.snapshotBody");
    case "consent":
      return t("consent.body");
    case "done":
      return "";
    default:
      return "";
  }
}

function statusFor(): { text: string; kind: "" | "blocked" | "saved" } {
  if (snapshotBlocked(model)) return { text: t("wizard.blocked"), kind: "blocked" };
  if (model.step === "snapshot" && model.context.snapshot === "saved") {
    return { text: t("wizard.copySaved"), kind: "saved" };
  }
  if (model.step === "snapshot" && model.context.snapshot === "saving") {
    return { text: t("wizard.savingLibraryCopy"), kind: "" };
  }
  if (statusNote) return { text: statusNote(), kind: "" };
  return { text: "", kind: "" };
}

function paintSegments(current: number, count: number): void {
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

function paintArt(): void {
  const slots = document.querySelectorAll<HTMLElement>(".wizard-art");
  slots.forEach((slot) => {
    const current = slot.dataset.artSlot === model.step;
    const hasArt = slot.querySelector("svg, img") !== null;
    slot.hidden = !(current && hasArt);
  });
}

function publishStatus(setup: SetupInfo): void {
  if (setup.statusMessage.length === 0) return;
  options.onStatus?.({
    message: setup.statusMessage,
    writable: setup.statusWritable,
    open: setup.seratoRunning,
    serato_running: setup.seratoRunning,
    process: setup.seratoRunning ? "Serato DJ" : null,
  });
}

function paintProgress(): void {
  const node = element("wizard-progress");
  if (!(node instanceof HTMLProgressElement)) return;
  const saving = model.step === "snapshot" && model.context.snapshot === "saving";
  const saved = model.step === "snapshot" && model.context.snapshot === "saved";
  node.hidden = !saving && !saved;
  if (saving) node.removeAttribute("value");
  if (saved) node.value = 1;
}

function ensurePoll(): void {
  stopPoll();
  if (!wizardDialog().open) return;
  pollTimer = window.setInterval(() => {
    void refreshSerato();
  }, 2000);
}

async function refreshSerato(): Promise<void> {
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

function stopPoll(): void {
  if (pollTimer) window.clearInterval(pollTimer);
  pollTimer = 0;
}

function closeDialog(): void {
  stopPoll();
  const dialog = wizardDialog();
  if (dialog.open) dialog.close();
  const target = options.returnFocus;
  if (target instanceof HTMLElement && target.isConnected) target.focus();
}

async function loadSettings(): Promise<SettingsPayload> {
  try {
    const payload = await getJSON("/api/settings", 15000);
    return readSettings(payload) ?? fallbackSettings();
  } catch {
    return fallbackSettings();
  }
}

async function loadSetup(): Promise<SetupInfo | null> {
  try {
    const payload = await getJSON("/api/setup", 15000);
    return readSetup(payload);
  } catch {
    return null;
  }
}

function fallbackSettings(): SettingsPayload {
  return {
    telemetry_consent: null,
    needs_consent_prompt: true,
    wizard_complete: false,
    telemetry_configured: false,
    app_version: "",
  };
}

function readSettings(value: unknown): SettingsPayload | null {
  if (!isRecord(value) || typeof value.needs_consent_prompt !== "boolean") return null;
  const consent = value.telemetry_consent;
  return {
    telemetry_consent: typeof consent === "boolean" ? consent : null,
    needs_consent_prompt: value.needs_consent_prompt,
    wizard_complete: value.wizard_complete === true,
    telemetry_configured: value.telemetry_configured === true,
    app_version: typeof value.app_version === "string" ? value.app_version : "",
  };
}

function readSetup(value: unknown): SetupInfo | null {
  if (!isRecord(value) || typeof value.found !== "boolean" || typeof value.summary !== "string") return null;
  return {
    found: value.found,
    summary: value.summary,
    next: typeof value.next === "string" ? value.next : "",
    seratoRunning: value.serato_running === true,
    statusMessage: typeof value.status_message === "string" ? value.status_message : "",
    statusWritable: value.status_writable === true,
  };
}

function readBrowse(value: unknown): { path: string; parent: string | null; name: string; folders: FolderRow[] } | null {
  if (!isRecord(value) || typeof value.path !== "string" || typeof value.name !== "string") return null;
  if (!Array.isArray(value.folders)) return null;
  const folders: FolderRow[] = [];
  for (const entry of value.folders) {
    if (!isRecord(entry) || typeof entry.name !== "string" || typeof entry.path !== "string") continue;
    folders.push({ name: entry.name, path: entry.path });
  }
  const parent = typeof value.parent === "string" ? value.parent : null;
  return { path: value.path, parent, name: value.name, folders };
}

async function getJSON(url: string, timeoutMs: number): Promise<unknown> {
  const response = await fetch(url, { signal: AbortSignal.timeout(timeoutMs) });
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) throw new Error(plainError(payload));
  return payload;
}

async function postJSON(url: string, body: Record<string, string | boolean>, timeoutMs: number): Promise<unknown> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(timeoutMs),
  });
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) throw new Error(plainError(payload));
  return payload;
}

function plainError(payload: unknown): string {
  const raw = isRecord(payload) && typeof payload.error === "string" ? payload.error : "";
  if (!raw || raw.includes("/") || raw.includes("\\") || raw.toLowerCase().includes("sqlite")) {
    return t("wizard.genericError");
  }
  const code = isRecord(payload) && typeof payload.code === "string" ? payload.code : undefined;
  return serverMessage({ error: raw, code }, raw);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function wizardDialog(): HTMLDialogElement {
  const node = element("wizard");
  if (!(node instanceof HTMLDialogElement)) throw new Error("Missing wizard");
  return node;
}

function element(id: string): HTMLElement {
  const node = document.getElementById(id);
  if (!node) throw new Error(`Missing ${id}`);
  return node;
}

function text(id: string): HTMLElement {
  return element(id);
}

function button(id: string): HTMLButtonElement {
  const node = element(id);
  if (!(node instanceof HTMLButtonElement)) throw new Error(`Missing ${id}`);
  return node;
}
