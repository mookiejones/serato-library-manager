/**
 * Serato library page.
 *
 * Wires the screen and starts the first load. The view modules do not
 * fetch when they are imported. This file attaches listeners, then calls
 * loadLibrary. Settings load when the dialogs wire. server.py uses port
 * 8765. The desktop app uses a free port, and this page calls the same
 * origin. Snapshot UI is src/restore.ts. This file does not open
 * master.sqlite itself.
 */

import { failureOf } from "./api";
import { wireDialogs } from "./dialogs";
import { el } from "./dom";
import {
  bindLibraryReload,
  confirmSnapshotRestore,
  failSnapshots,
  loadSnapshots,
  openSnapshotPlan,
  setSnapshotDialogStatus,
  takeSnapshot,
} from "./restore";
import { state } from "./state";
import { loadLibrary, showFailure, wireLibrary } from "./views";
import { mountTrackList, wireVirtualScroll } from "./virtual-scroll";

/**
 * Attach the snapshot-list listeners.
 *
 * Refresh, take, undo, and the restore dialog call src/restore.ts.
 * Called once at startup. Does not restore anything by itself.
 *
 * @returns {void}
 */
function wireSnapshots(): void {
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
