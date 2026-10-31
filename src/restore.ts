/**
 * Snapshot list and restore dialog.
 *
 * Typed against the dry-run fields POST /api/snapshots returns. Confirm
 * stays off when restore_blocked is set. Nothing is written until confirm.
 */

import { failureOf, postJSON, readJSON } from "./api";
import type { FrameDiff, PlanName, RestorePlan, SnapshotList } from "./api-types";
import { el } from "./dom";
import { state } from "./state";
import { codedText, formatList, messageParams, serverMessage, t } from "./i18n";

let reloadLibrary: () => Promise<void> = async () => {};

export function bindLibraryReload(reload: () => Promise<void>): void {
  reloadLibrary = reload;
}

// --- snapshots (issue 35). Keep this block together for the TypeScript move in #59. ---

/**
 * Load the snapshot list.
 *
 * Shows a reading line, then the rows or an empty explanation. A failure
 * stays in the panel with a retry. Does not restore anything.
 *
 * @returns {Promise<void>}
 */
export async function loadSnapshots() {
  state.snapshotLoading = true;
  state.snapshotError = "";
  renderSnapshots();
  const response = await fetch("/api/snapshots");
  const payload = await readJSON<SnapshotList>(response);
  if (!response.ok) throw new Error(serverMessage(payload, t("snapshots.unreadable")));
  state.snapshots = payload.snapshots || [];
  state.snapshotUndo = payload.pending_undo || null;
  state.writeBlock = payload.write_block || "";
  state.writeBlockCode = payload.write_block_code || "";
  state.writeBlockParams = messageParams(payload.write_block_params) ?? null;
  state.seratoRunning = Boolean(payload.serato_running);
  state.snapshotLoading = false;
  renderSnapshots();
}

/**
 * Show a snapshot-list failure.
 *
 * @param {Error} error Failed request.
 * @returns {void}
 */
export function failSnapshots(error: unknown) {
  state.snapshotLoading = false;
  state.snapshotError = failureOf(error).message || t("snapshots.unreadable");
  renderSnapshots();
}

/**
 * Paint the snapshot list, the Serato 5 note, and an outside-change undo.
 *
 * Text is set with textContent. Restore stays available as a button on
 * each row; the dialog decides whether confirm is allowed.
 *
 * @returns {void}
 */
export function renderSnapshots() {
  const status = el("snapshots-status");
  const block = el("snapshots-block");
  const undo = el("snapshots-undo");
  const list = el("snapshots-list");
  list.setAttribute("aria-busy", String(state.snapshotLoading));
  if (state.writeBlock) {
    block.hidden = false;
    block.textContent = codedText(state.writeBlock, state.writeBlockCode, state.writeBlockParams);
  } else {
    block.hidden = true;
    block.textContent = "";
  }
  if (state.snapshotUndo && state.snapshotUndo.restore_id) {
    undo.hidden = false;
    el("snapshots-undo-text").textContent = state.snapshotUndo.source === "Lexicon"
      ? t("snapshots.outsideChangeLexicon")
      : t("snapshots.outsideChange");
  } else {
    undo.hidden = true;
  }
  list.replaceChildren();
  if (state.snapshotLoading) {
    status.textContent = t("snapshots.reading");
    return;
  }
  if (state.snapshotError) {
    status.textContent = state.snapshotError;
    const retry = document.createElement("button");
    retry.type = "button";
    retry.textContent = t("common.tryAgain");
    retry.addEventListener("click", () => loadSnapshots().catch((error) => failSnapshots(error)));
    list.append(retry);
    return;
  }
  status.textContent = state.snapshotMessage ? t(state.snapshotMessage) : "";
  if (!state.snapshots.length) {
    const empty = document.createElement("p");
    empty.textContent = t("snapshots.empty");
    list.append(empty);
    return;
  }
  for (const item of state.snapshots) {
    const card = document.createElement("article");
    card.className = "snapshot-card";
    card.setAttribute("role", "listitem");
    const title = document.createElement("p");
    title.textContent = `${item.created || t("snapshots.unknownTime")} · ${item.trigger || t("snapshots.trigger")}`;
    const detail = document.createElement("p");
    const version = item.serato_version && item.serato_version !== "unknown"
      ? t("snapshots.seratoVersion", { version: item.serato_version, build: String(item.serato_build ?? "") })
      : t("snapshots.seratoUnknown");
    const drives = (item.unavailable_drives || []).length
      ? ` ${t("snapshots.unavailableDrives", { drives: formatList(item.unavailable_drives || []) })}`
      : "";
    detail.textContent = `${version}. ${item.reason || ""}${drives}`;
    const restore = document.createElement("button");
    restore.type = "button";
    restore.textContent = t("snapshots.reviewRestore");
    restore.addEventListener("click", () => openSnapshotPlan(item.id).catch((error) => setSnapshotDialogStatus(failureOf(error).message)));
    card.append(title, detail, restore);
    list.append(card);
  }
}

/**
 * Ask for a restore plan and open the dialog.
 *
 * The plan is a dry run. Confirm stays off when the server says the
 * restore is blocked.
 *
 * @param {string} snapshotId Snapshot to review.
 * @returns {Promise<void>}
 */
export async function openSnapshotPlan(snapshotId: string) {
  state.snapshotPlanId = snapshotId;
  const planBox = el("snapshot-plan");
  const block = el("snapshot-block");
  const confirm = el("snapshot-confirm");
  planBox.replaceChildren();
  block.textContent = t("snapshots.readingPlan");
  confirm.disabled = true;
  setSnapshotDialogStatus("");
  el("snapshot-dialog").showModal();
  const plan = await postJSON("/api/snapshots", { action: "plan", id: snapshotId });
  paintSnapshotPlan(plan);
}

/**
 * Fill the restore dialog from a dry-run plan.
 *
 * @param {object} plan Response from action plan. Reads plan.crates,
 *   plan.tracks, plan.cues, plan.grids, plan.dry_run, and plan.restore_blocked.
 * @returns {void}
 */
let lastPlan: RestorePlan | null = null;

/**
 * Paint the open restore dialog again in the active language.
 *
 * @returns {void}
 */
export function repaintSnapshotPlan() {
  if (lastPlan && el("snapshot-dialog").open) paintSnapshotPlan(lastPlan);
}

function paintSnapshotPlan(plan: RestorePlan) {
  lastPlan = plan;
  const planBox = el("snapshot-plan");
  const block = el("snapshot-block");
  const confirm = el("snapshot-confirm");
  planBox.replaceChildren();
  const crates = plan.crates || {};
  const tracks = plan.tracks || {};
  appendPlanLine(planBox, t("plan.cratesAdded"), crates.added);
  appendPlanLine(planBox, t("plan.cratesRemoved"), crates.removed);
  appendPlanLine(planBox, t("plan.cratesChanged"), crates.changed);
  appendPlanLine(planBox, t("plan.cratesUnavailable"), crates.unavailable);
  appendPlanLine(planBox, t("plan.tracksAdded"), tracks.added);
  appendPlanLine(planBox, t("plan.tracksRemoved"), tracks.removed);
  appendPlanLine(planBox, t("plan.tracksUnavailable"), tracks.unavailable);
  appendFrameDiffs(planBox, t("plan.cueChanges"), plan.cues);
  appendFrameDiffs(planBox, t("plan.gridChanges"), plan.grids);
  const deleted = plan.deleted || {};
  appendPlanLine(planBox, t("plan.deletedCrates"), deleted.crates);
  appendPlanLine(planBox, t("plan.deletedTracks"), deleted.tracks);
  appendPlanLine(planBox, t("plan.deletedCues"), deleted.cues);
  appendPlanLine(planBox, t("plan.deletedGrids"), deleted.grids);
  if (plan.restore_blocked) {
    block.textContent = codedText(
      plan.restore_blocked,
      plan.restore_blocked_code,
      messageParams(plan.restore_blocked_params),
    );
    confirm.disabled = true;
  } else {
    block.textContent = plan.dry_run ? t("plan.nothingChanged") : "";
    confirm.disabled = false;
  }
}

/**
 * Add one labelled count or name list to the restore plan.
 *
 * @param {HTMLElement} parent Plan container.
 * @param {string} label Section name.
 * @param {object[]|undefined} rows Diff rows.
 * @returns {void}
 */
function appendPlanLine(parent: HTMLElement, label: string, rows: PlanName[] | undefined) {
  const line = document.createElement("p");
  const items = rows || [];
  if (!items.length) {
    line.textContent = t("plan.none", { label });
  } else {
    const names = items.slice(0, 8).map((item) => item.name || item.path || item.drive_label || t("plan.item"));
    const extra = items.length > names.length ? t("plan.andMore", { count: items.length - names.length }) : "";
    const listed = `${names.join(", ")}${extra}`;
    line.textContent = t("plan.listed", { label, count: items.length, names: listed });
  }
  parent.append(line);
}

/**
 * Add per-file cue or grid differences.
 *
 * @param {HTMLElement} parent Plan container.
 * @param {string} label Section name.
 * @param {object[]|undefined} rows Files whose frames would change.
 * @returns {void}
 */
function appendFrameDiffs(parent: HTMLElement, label: string, rows: FrameDiff[] | undefined) {
  const items = rows || [];
  const line = document.createElement("p");
  if (!items.length) {
    line.textContent = t("plan.none", { label });
    parent.append(line);
    return;
  }
  line.textContent = t("plan.files", { label, count: items.length });
  parent.append(line);
  for (const item of items.slice(0, 12)) {
    const row = document.createElement("p");
    row.textContent = fileName(item.path || "");
    parent.append(row);
  }
}

/**
 * Return the last path segment for a restore line.
 *
 * @param {string} path File path.
 * @returns {string} The file name, or the whole path when it has no slash.
 */
function fileName(path: string) {
  const parts = String(path).split(/[/\\]/);
  return parts[parts.length - 1] || path;
}

/**
 * Set the restore dialog status line.
 *
 * @param {string} message Status text.
 * @returns {void}
 */
export function setSnapshotDialogStatus(message: string) {
  el("snapshot-status").textContent = message;
}

/**
 * Save a manual snapshot and reload the list.
 *
 * @returns {Promise<void>}
 */
export async function takeSnapshot() {
  const button = el("snapshots-take");
  button.disabled = true;
  button.textContent = t("snapshots.saving");
  try {
    await postJSON("/api/snapshots", { action: "create" });
    state.snapshotMessage = "snapshots.saved";
    await loadSnapshots();
  } finally {
    button.disabled = false;
    button.textContent = t("snapshots.take");
  }
}

/**
 * Confirm the open restore after the dry run.
 *
 * @returns {Promise<void>}
 */
export async function confirmSnapshotRestore() {
  const confirm = el("snapshot-confirm");
  confirm.disabled = true;
  confirm.textContent = t("snapshots.restoring");
  setSnapshotDialogStatus("");
  try {
    const undoing = state.snapshotUndo && state.snapshotUndo.restore_id === state.snapshotPlanId;
    const body = undoing
      ? { action: "undo", confirm: true }
      : { action: "restore", id: state.snapshotPlanId, confirm: true };
    await postJSON("/api/snapshots", body);
    el("snapshot-dialog").close();
    state.snapshotMessage = "snapshots.restored";
    await loadSnapshots();
    await reloadLibrary();
  } catch (error) {
    setSnapshotDialogStatus(failureOf(error).message);
    confirm.disabled = false;
  } finally {
    confirm.textContent = t("snapshots.restore");
  }
}

