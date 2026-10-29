/**
 * Dialogs for Rekordbox export, duplicate merge, sharing, and file changes.
 *
 * Importing this module does not open a dialog and does not fetch.
 * wireDialogs attaches the listeners. app.ts calls it once at startup.
 * Confirm still posts only after the person confirms.
 */

import { failureOf, postJSON, readJSONOr } from "./api";
import type { LibraryStatusNotice, OpenOptions } from "./wizard-view";
import type {
  FilesBody,
  FilesPayload,
  LogsPayload,
  MergePreview,
  SettingsPayload,
} from "./api-types";
import { bridge } from "./bridge";
import { el } from "./dom";
import { state } from "./state";
import {
  applyStatus,
  crateNamesFor,
  failFiles,
  loadDuplicates,
  loadFolder,
  loadLibrary,
  lockDown,
  renderFiles,
  selectTrack,
  selectedDuplicateGroup,
  selectedFiles,
  setNotice,
} from "./views";

let rekordboxXml = "";
let mergePreview: MergePreview | null = null;
let mergeToken = 0;
let mergeLoading = false;
let consentSettled = false;
let privacySync = false;
let filesPreview: FilesPayload | null = null;
let filesAction = "";
let filesTrigger: HTMLElement | null = null;

/**
 * Build the Rekordbox export URL for the current space and crate.
 *
 * The report form asks for the loss report as JSON. The file form is the
 * XML download, which starts only after the dialog is confirmed.
 * Hot loops sends ``hot_loops=1`` while the box is checked and
 * ``hot_loops=0`` while it is clear. The box starts clear.
 * wireDialogs loads the saved export bar before the person exports.
 *
 * @param {boolean} report True asks for the loss report instead of the file.
 * @returns {string} The request path and query.
 */
export function rekordboxExportUrl(report: boolean) {
  const crate = state.mode === "crates" ? state.activeCrate : "all";
  const memory = el("rekordbox-memory").checked ? "1" : "0";
  const hotLoops = el("rekordbox-hot-loops").checked ? "1" : "0";
  const key = el("rekordbox-key").value;
  const base = `/api/export.rekordbox.xml?space=${encodeURIComponent(state.space)}&crate=${encodeURIComponent(crate)}&memory=${memory}&hot_loops=${hotLoops}&key=${encodeURIComponent(key)}`;
  return report ? `${base}&report=1` : base;
}

/** Bumps when the export bar changes, so a late settings response is ignored. */
let rekordboxToken = 0;

/**
 * Apply a saved export bar to the three controls.
 *
 * Only boolean cues and a known key notation are copied. A missing
 * section leaves the controls as they are. Does not fetch.
 *
 * @param {object} payload Settings object from the server.
 * @returns {void}
 */
export function applyRekordboxExport(payload: SettingsPayload): void {
  const section = payload.rekordbox;
  if (section == null) return;
  if (typeof section.hot_loops === "boolean") {
    el("rekordbox-hot-loops").checked = section.hot_loops;
  }
  if (typeof section.memory_cues === "boolean") {
    el("rekordbox-memory").checked = section.memory_cues;
  }
  if (
    section.key_notation === "asis"
    || section.key_notation === "camelot"
    || section.key_notation === "classical"
  ) {
    el("rekordbox-key").value = section.key_notation;
  }
}

/**
 * POST the export bar.
 *
 * The body is the three controls as they are now. A failed request leaves
 * those controls in place, and the export reads them directly.
 *
 * @returns {Promise<void>}
 */
export async function saveRekordboxExport(): Promise<void> {
  const key = el("rekordbox-key").value;
  const notation = key === "camelot" || key === "classical" ? key : "asis";
  const token = ++rekordboxToken;
  try {
    const payload = await postJSON<SettingsPayload>("/api/settings", {
      rekordbox: {
        hot_loops: el("rekordbox-hot-loops").checked,
        memory_cues: el("rekordbox-memory").checked,
        key_notation: notation,
      },
    });
    if (token === rekordboxToken) applyRekordboxExport(payload);
  } catch {
    // The boxes stay as set. The export still uses them.
  }
}

/**
 * Fill the export dialog list with one item per loss-report line.
 *
 * Text is set with textContent. An empty report leaves the list empty.
 *
 * @param {string[]} lines Sentences from the export.
 * @returns {void}
 */
function fillRekordboxReport(lines: string[]) {
  const list = el("rekordbox-report");
  list.replaceChildren();
  for (const line of lines) {
    const item = document.createElement("li");
    item.textContent = line;
    list.append(item);
  }
}

/**
 * Read the keep-copy radio the dialog currently has selected.
 *
 * Falls back to the track selected in the list. Does not fetch.
 *
 * @returns {number|null} Asset id, or null when no radio is checked.
 */
function selectedMergeKeepId() {
  const checked = el("merge-choices").querySelector<HTMLInputElement>("input:checked");
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
function previewFieldValue(field: string, value: string | number | null | undefined) {
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
function renderMergePreview(preview: MergePreview | null) {
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
  const item = (text: string) => {
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
  el("merge-trash").disabled = !mergePreview || mergeLoading || blocked || trashable.length === 0;
  if (el("merge-trash").disabled) el("merge-trash").checked = false;
  const danger = el("merge-trash").checked;
  el("merge-confirm").classList.toggle("danger", danger);
  el("merge-confirm").textContent = mergeLoading ? "Merging…" : (danger ? "Merge and move files to Trash" : "Merge copies");
  el("merge-confirm").disabled = mergeLoading || !mergePreview || mergePreview.writable === false;
  const note = el("merge-file-note");
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
  el("merge-status").textContent = "";
  renderMergePreview(null);
  syncTrashChoice();
  el("merge-confirm").disabled = true;
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
  if (typeof el("merge-dialog").showModal !== "function") return;
  el("merge-trash").checked = false;
  el("merge-status").textContent = "";
  renderMergeChoices();
  if (!el("merge-dialog").open) el("merge-dialog").showModal();
  el("merge-cancel").focus();
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
      confirm_delete_files: trash,
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
function applyPrivacy(payload: SettingsPayload) {
  state.telemetryConsent = payload.telemetry_consent ?? null;
  state.telemetryConfigured = Boolean(payload.telemetry_configured);
  state.wizardComplete = payload.wizard_complete === true;
  privacySync = true;
  el("telemetry-toggle").checked = state.telemetryConsent === true;
  privacySync = false;
  el("telemetry-note").textContent = telemetryNoteText();
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
async function saveConsent(value: boolean, status: HTMLElement) {
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
  if (typeof el("consent-dialog").showModal !== "function") return;
  if (el("consent-dialog").open) return;
  consentSettled = false;
  el("consent-status").textContent = "";
  el("consent-dialog").showModal();
  el("consent-decline").focus();
}

/**
 * Open setup when it is not finished, or when Settings asks to run it again.
 *
 * The wizard script is a separate bundle. A missing script falls through
 * to the sharing dialog. No library rows are sent.
 *
 * @param force Show setup again after it was completed.
 * @param returnFocus Control to focus when setup closes.
 * @returns True when the wizard script is present.
 */
function openWizard(force: boolean, returnFocus: HTMLElement): boolean {
  const wizard = (globalThis as { SeratoWizard?: { open: (options: OpenOptions) => void } }).SeratoWizard;
  if (!wizard || typeof wizard.open !== "function") return false;
  const options: OpenOptions = {
    force,
    returnFocus,
    onSettings(payload) {
      applyPrivacy(payload);
    },
    onStatus(info: LibraryStatusNotice) {
      applyStatus({
        message: info.message,
        writable: info.writable,
        open: info.open,
      });
    },
  };
  wizard.open(options);
  return true;
}

/**
 * Load sharing settings and show the prompt when no choice is saved.
 *
 * GET /api/settings. A failure leaves sharing off and says so. It does
 * not block the library view. Setup, when it is not finished, asks the
 * sharing question itself.
 *
 * @returns {Promise<void>}
 */
export async function loadPrivacy() {
  const token = rekordboxToken;
  const response = await fetch("/api/settings");
  const payload = await readJSONOr<SettingsPayload>(response, {});
  if (!response.ok) throw new Error(payload.error || "Couldn't load sharing settings.");
  applyPrivacy(payload);
  if (token === rekordboxToken) applyRekordboxExport(payload);
  if (!state.wizardComplete && openWizard(false, el("search"))) return;
  if (payload.needs_consent_prompt) showConsent();
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
function openFilesDialog(action: string, trigger: EventTarget | null) {
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
  if (action === "rename" && selected.length === 1) el("files-name").value = selected[0]!.name;
  if (action === "replace") el("files-replacement").value = "";
  const confirm = el("files-confirm");
  confirm.classList.toggle("danger", action === "delete");
  confirm.textContent = action === "delete" ? "Move to Trash" : "Confirm";
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

/**
 * Enable confirm only after a preview that can be saved.
 *
 * @returns {void}
 */
function syncFilesDialog() {
  const confirm = el("files-confirm");
  const review = el("files-review");
  const ready = Boolean(filesPreview?.ok && state.writable && filesPreview.needs_confirm);
  confirm.disabled = !ready;
  review.hidden = filesAction === "delete" || filesAction === "move" || filesAction === "move_folder";
  if (!state.writable) {
    el("files-dialog-status").textContent = el("status").textContent;
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
  el("files-dialog-status").textContent = "Checking what will change.";
  const payload = await postJSON("/api/files", body);
  filesPreview = payload;
  el("files-summary").textContent = payload.summary || "";
  el("files-warning").textContent = payload.warning || "";
  el("files-dialog-status").textContent = payload.ok ? "" : (payload.error || "That change was not saved.");
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

/**
 * Build the JSON body for the current file action.
 *
 * @param {boolean} confirm True only after the person confirms the preview.
 * @returns {object} Request body for POST /api/files.
 */
function filesBody(confirm: boolean): FilesBody {
  const body: FilesBody = { action: filesAction };
  if (confirm) body.confirm = true;
  if (filesAction === "rename") {
    const selected = selectedFiles();
    body.path = (selected[0]?.path || state.filesPickPaths[0]) as string;
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

/**
 * Close the file dialog and return focus to the control that opened it.
 *
 * @returns {void}
 */
function closeFilesDialog() {
  const trigger = filesTrigger;
  filesTrigger = null;
  if (el("files-dialog").open) el("files-dialog").close();
  if (trigger instanceof HTMLElement) trigger.focus();
}

/**
 * Save a confirmed file change and reload the folder and the library.
 *
 * @returns {Promise<void>}
 */
async function confirmFiles() {
  if (!filesPreview?.ok || !state.writable) return;
  const confirm = el("files-confirm");
  confirm.disabled = true;
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
    confirm.disabled = false;
  }
}

/**
 * Attach dialog listeners for export, merge, sharing, logs, and files.
 *
 * Called once from app.ts. A listener opens a dialog or posts only after
 * the matching control is used.
 *
 * @returns {void}
 */
export function wireDialogs(): void {
  const saveExportBar = () => {
    saveRekordboxExport().catch(() => {
      // saveRekordboxExport already keeps the boxes. This catch is the listener boundary.
    });
  };
  el("rekordbox-hot-loops").addEventListener("change", saveExportBar);
  el("rekordbox-memory").addEventListener("change", saveExportBar);
  el("rekordbox-key").addEventListener("change", saveExportBar);
  loadPrivacy().catch((error: unknown) => {
    setNotice(failureOf(error).message || "Couldn't load sharing settings. Nothing is sent.");
  });
  el("export-rekordbox").addEventListener("click", () => {
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
        el("rekordbox-status").textContent = "";
        el("rekordbox-dialog").showModal();
      })
      .catch((error) => setNotice(failureOf(error).message));
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
    // Safari and Firefox need the object URL until the download has started.
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
    postJSON("/api/logs/open", {})
      .then(() => {
        el("settings-status").textContent = "Opened the logs folder.";
      })
      .catch(() => {
        el("settings-status").textContent = "Couldn't open the logs folder.";
      })
      .finally(() => {
        button.disabled = false;
      });
  });

  el("copy-logs").addEventListener("click", async () => {
    const button = el("copy-logs");
    button.disabled = true;
    el("settings-status").textContent = "Copying…";
    try {
      const response = await fetch("/api/logs");
      const payload = await readJSONOr<LogsPayload>(response, {});
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
        el("settings-status").textContent = payload.truncated
          ? "Copied the latest log entries. Older entries were left out."
          : "Copied the logs.";
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
